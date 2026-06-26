# ai/action_fixer/deployment_fixers.py - split from action_fixer.py
# Deployment option inference / checkbox+process merge / strip invalid
from ._constants import (
    DEPLOYMENT_KEYWORDS,
    PAGE_TAB_NAMES,
    NAVIGATION_PATH_MAP,
    ACTION_NAME_MAP,
    VALID_ACTIONS,
    _VALID_DEPLOY_OPTIONS,
)


def _strip_invalid_deploy_options(plan):
    """
    Remove tab/section names that the AI wrongly adds to process_deployment options.
    E.g. "Contest Superstars" is a tab inside the RBE form, not a home-screen checkbox.
    Any option not in _VALID_DEPLOY_OPTIONS is dropped.
    """
    for step in plan:
        if step.get("action") != "process_deployment":
            continue
        original = list(step.get("options", []))
        valid = [opt for opt in original if opt in _VALID_DEPLOY_OPTIONS]
        if len(valid) != len(original):
            removed = [o for o in original if o not in _VALID_DEPLOY_OPTIONS]
            print(f"   🔧 STRIP deploy options: removed {removed} (not valid home-screen checkboxes)")
            step["options"] = valid
    return plan




def _inject_missing_checkbox_before_download(plan, user_command=""):
    """
    When command says "Chọn N ID bất kỳ -> Export CSV" but AI skips the checkbox step,
    inject checkbox(random_N) immediately before each download step that lacks one.
    """
    import re as _re

    if not plan:
        return plan

    # Parse how many rows the user wants to select (default 1)
    n = 1
    m = _re.search(
        r"chọn\s+(\d+)\s+ID\s+bất\s*kỳ",
        user_command,
        _re.IGNORECASE,
    )
    if not m:
        # No "Chọn N ID bất kỳ" in command — nothing to inject
        return plan
    n = int(m.group(1))

    result = []
    i = 0
    while i < len(plan):
        step = plan[i]
        if step.get("action") == "download":
            # Check if the step immediately before this is a checkbox
            preceding = result[-1] if result else None
            if not preceding or preceding.get("action") != "checkbox":
                print(f"   🔧 INJECT CHECKBOX: Missing checkbox before download → random_{n}")
                result.append({
                    "action": "checkbox",
                    "target": "",
                    "value": f"random_{n}",
                })
        result.append(step)
        i += 1
    return result


def _dedup_consecutive_identical_steps(plan):
    """
    Safety net against model degeneration: greedy decoding can lock into a loop
    and emit the SAME step dozens of times (e.g. 50× upload of the same CSV →
    50 file-chooser dialogs that block the run). Collapse runs of byte-identical
    consecutive steps down to a single occurrence. Only EXACT duplicates are
    removed, so legitimate repeated-but-different steps (two waits, two clicks on
    different targets) are preserved.
    """
    if not plan or not isinstance(plan, list):
        return plan

    import json as _json

    result = []
    prev_key = object()  # sentinel — never equals a real step
    removed = 0
    for step in plan:
        try:
            key = _json.dumps(step, sort_keys=True, ensure_ascii=False)
        except Exception:
            key = repr(step)
        if key == prev_key:
            removed += 1
            continue
        result.append(step)
        prev_key = key
    if removed:
        print(f"   🔧 DEDUP: removed {removed} duplicate consecutive step(s)")
    return result


def _fix_download_filename_in_target(plan):
    """
    Normalize download/upload steps where the AI put the data filename in
    `target` (the button name slot) and left `value` empty — e.g.
    {"action": "download", "target": "Book_test.csv"}. The executor saves using
    `value`; an empty value makes save_as() resolve to the downloads/ directory →
    "[Errno 21] Is a directory". Move the filename into `value` and default the
    button target to Export CSV / Import CSV.
    """
    if not plan:
        return plan

    _exts = (".csv", ".xlsx", ".xls", ".json", ".txt")
    for step in plan:
        if step.get("action") not in ("download", "upload"):
            continue
        value = str(step.get("value") or "").strip()
        target = str(step.get("target") or "").strip()
        if not value and target.lower().endswith(_exts):
            step["value"] = target
            step["target"] = (
                "Export CSV" if step["action"] == "download" else "Import CSV"
            )
            print(
                f"   🔧 FIX DOWNLOAD FILENAME: moved '{target}' from target → value "
                f"(target='{step['target']}')"
            )
    return plan


def _auto_infer_deployment_options(plan, user_command=""):
    """
    Auto-infer deployment options from context if process_deployment has empty options.

    Context sources:
    1. Navigation path (e.g., "Offer" → infer "Offers")
    2. Uploaded filename (e.g., "gacha_*.csv" → infer "Gacha")
    3. Previous actions (e.g., after smart_test_cycle on table)

    Only infers when the user command contains explicit deployment intent.
    Skips inference for commands that just navigate home (e.g. search test cases).
    """
    if not plan:
        return plan

    # Only infer when the command has explicit deployment intent.
    # Without this guard, a "search → logo click" command would auto-deploy
    # whatever feature was last navigated to.
    _cmd_lower = (user_command or "").lower()
    # Deploy cases always end with "-> Process" or contain "Deploy".
    # "Bỏ chọn checkbox" (uncheck a UI filter checkbox) must NOT trigger inference —
    # it contains "checkbox" as a substring so we cannot use "checkbox" as a keyword.
    _DEPLOY_INTENT_KEYWORDS = ["process", "deploy"]
    _has_deploy_intent = any(kw in _cmd_lower for kw in _DEPLOY_INTENT_KEYWORDS)
    if not _has_deploy_intent:
        print("   ℹ️  AUTO-INFER skipped: no deployment intent in command")
        return plan

    # Mapping từ keyword → deployment option name
    # Based on actual Home screen checkboxes
    DEPLOYMENT_INFERENCE_MAP = {
        # === DEPLOYMENT CHECKBOXES (Exact names from Home screen) ===
        # Left column
        "localization": "Localization",
        "excel": "Excel",
        "currency": "Currency",
        "consumables": "Consumables",
        "consumable": "Consumables",
        "faction feud": "Faction Feud",
        "grab bag": "Grab Bag",
        "grabbag": "Grab Bag",
        "chat channels": "Chat Channels",
        "chat channel": "Chat Channels",
        "pve": "PVE",
        "faction mission": "Faction Mission",
        "merch store": "Merch Store",
        "feature setting": "Feature Setting",
        "invasion": "Invasion",
        "mizz missions": "Mizz Missions",
        "mizz mission": "Mizz Missions",
        "subscription 1.5": "Subscription 1.5",
        "feature gate setting": "Feature Gate Setting",
        "versus shop": "Versus Shop",
        "league config": "League Config",
        "champion rewards": "Champion Rewards",
        "battle shop": "Battle Shop",
        "notification": "Notification",
        "reactivation flow & contest": "Reactivation Flow & Contest",
        "reactivation flow": "Reactivation Flow & Contest",
        "auto play & speed up": "Auto Play & Speed Up",
        "auto play": "Auto Play & Speed Up",
        "news modal": "News Modal",
        "stat change": "Stat Change",
        # Right column
        "gacha events": "Gacha Events",
        "gacha event": "Gacha Events",
        "gacha": "Gacha Events",
        "offers": "Offers",
        "offer": "Offers",
        "missions": "Missions",
        "mission": "Missions",
        "fight card": "Fight Card",
        "cash contract": "Cash Contract",
        "liveops message": "LiveOps Message",
        "live ops message": "LiveOps Message",
        "rbe": "RBE",
        "faction lockbox": "Faction Lockbox",
        "promo code": "Promo Code",
        "subscription & vip": "Subscription & VIP",
        "subscription vip": "Subscription & VIP",
        "perks": "Perks",
        "perk": "Perks",
        "effect cap setting": "Effect Cap Setting",
        "social box gacha": "Social Box Gacha",
        "monthly bonus": "Monthly Bonus",
        "versus tournament": "Versus Tournament",
        "player league": "Player League",
        "strap and medal": "Strap and Medal",
        "superstars": "Superstars",
        "superstar": "Superstars",
        "boost": "Boost",
        "faction boss": "Faction Boss",
        "moment poster": "Moment Poster",
        "time challenge": "Time Challenge",
        "social friends": "Social Friends",
        "social friend": "Social Friends",
        "token": "Token",
        # === NAVIGATION CONTEXT (for auto-inference) ===
        "offer section": "Offers",
        "shop tier": "Offers",
        "shop": "Offers",
        "prize wall": "Prize Wall",
        "prizewall": "Prize Wall",
        "live event": "Live Events",
        "event": "Live Events",
        "config": "Data Configs",
        "blueprint": "Hyper Blueprint",
        # === CSV FILENAMES ===
        "gacha_": "Gacha Events",
        "offer_": "Offers",
        "section_": "Offers",
        "shop_": "Offers",
        "prize": "Prize Wall",
        "event_": "Live Events",
        "perk_": "Perks",
        "mission_": "Missions",
        "config_": "Data Configs",
        # Tournament / Versus contexts
        "tournament": "Versus Tournament",
        "versus": "Versus Tournament",
        "tournament_": "Versus Tournament",
    }

    result = []

    for i, step in enumerate(plan):
        action = step.get("action", "")

        # Check if this is a process_deployment with empty options
        if action == "process_deployment":
            options = step.get("options", [])

            if not options or len(options) == 0:
                print(
                    f"   🔍 AUTO-INFER: process_deployment has no options, analyzing context..."
                )

                inferred_option = None

                # Strategy 1: Look backward for navigation path
                for j in range(i - 1, max(-1, i - 10), -1):  # Check up to 10 steps back
                    prev_step = plan[j]
                    prev_action = prev_step.get("action", "")

                    if prev_action == "navigate":
                        path = prev_step.get("path", [])
                        path_str = " ".join(path).lower()

                        # Check each keyword
                        for keyword, option in DEPLOYMENT_INFERENCE_MAP.items():
                            if keyword in path_str:
                                inferred_option = option
                                print(
                                    f"      ✅ Inferred from navigation '{path}' → '{option}'"
                                )
                                break

                        if inferred_option:
                            break

                    # Strategy 2: Look for upload/smart_test_cycle filename
                    elif prev_action in ["upload", "smart_test_cycle", "download"]:
                        filename = prev_step.get("value", "")
                        if filename:
                            filename_lower = filename.lower()

                            for keyword, option in DEPLOYMENT_INFERENCE_MAP.items():
                                if keyword in filename_lower:
                                    inferred_option = option
                                    print(
                                        f"      ✅ Inferred from filename '{filename}' → '{option}'"
                                    )
                                    break

                            if inferred_option:
                                break

                # Apply inferred option
                if inferred_option:
                    step["options"] = [inferred_option]
                    print(
                        f"      🎯 AUTO-INFER: Added option '{inferred_option}' to process_deployment"
                    )
                else:
                    print(f"      ⚠️  Could not infer deployment option from context")
                    print(
                        f"      💡 Tip: Specify explicitly like 'Process với Offers' or 'Chọn Offers rồi Process'"
                    )

        result.append(step)

    return result




def _merge_process_deployment_steps(plan, uncheck_targets=None):
    """
    Merge patterns like:
      1. checkbox(Offers) → process_deployment → click(Process)

      2. process_deployment → checkbox(Offers) → click(Process)
    Into single:
      process_deployment(options=["Offers"])
    """
    if not plan:
        return plan

    # 🆕 DEBUG: Print plan before merge
    print(f"\n   📋 DEBUG - Plan BEFORE merge ({len(plan)} steps):")
    for idx, step in enumerate(plan):
        action = step.get("action", "?")
        target = step.get("target", "")
        value = step.get("value", "")
        options = step.get("options", [])
        if action == "process_deployment":
            print(f"      {idx}: {action} (options={options})")
        elif action == "checkbox":
            print(f"      {idx}: {action} (target={target}, value={value})")
        else:
            print(f"      {idx}: {action} (target={target})")

    merged = []
    i = 0
    while i < len(plan):
        step = plan[i]

        # Check if this starts a process_deployment sequence
        if step.get("action") == "process_deployment":
            options = list(step.get("options", []))

            # 🆕 Look BACKWARD for checkbox that should be merged
            # Pattern: checkbox(Offers) → process_deployment
            k = len(merged) - 1  # Start from last item in merged
            backward_count = 0
            items_to_remove = []  # Track indices to remove

            # Common deployment options keywords
            # Based on actual Home screen checkboxes
            deployment_keywords = DEPLOYMENT_KEYWORDS

            while k >= 0 and backward_count < 3:  # Check up to 3 steps back
                prev_step = merged[k]
                prev_action = prev_step.get("action", "")

                # Check if it's a non-table checkbox (deployment option)
                if prev_action == "checkbox":
                    value = str(prev_step.get("value", ""))
                    target = prev_step.get("target", "")
                    checkbox_label = prev_step.get(
                        "checkbox_label", ""
                    )  # 🆕 AI sometimes uses this field
                    checkbox_field = prev_step.get(
                        "checkbox", ""
                    )  # 🆕 AI also uses "checkbox" field
                    field_attr = prev_step.get(
                        "field", ""
                    )  # 🆕 AI also uses "field" key (e.g. "Faction Feud")
                    deployment_opt = prev_step.get(
                        "_deployment_opt", ""
                    )  # Pre-detected
                    is_uncheck = prev_step.get("_uncheck", False)

                    # 🆕 SMART DETECTION: Check if this is a deployment option
                    is_deployment_option = bool(
                        deployment_opt
                    )  # Already detected in STEP 2

                    # 🆕 Also check 'option' field (AI sometimes uses this key)
                    option_attr = prev_step.get("option", "")

                    if not is_deployment_option:
                        # Fallback: Check all possible fields
                        fields_to_check = [
                            checkbox_field,
                            field_attr,
                            checkbox_label,
                            option_attr,
                            target,
                            value,
                        ]

                        for field in fields_to_check:
                            if field:
                                field_lower = str(field).lower()
                                for keyword in deployment_keywords:
                                    if keyword in field_lower:
                                        is_deployment_option = True
                                        break
                                if is_deployment_option:
                                    break

                    # If not random_ OR is deployment option name, merge it
                    if (
                        not value.startswith("random_") and target != "ID"
                    ) or is_deployment_option:
                        # Prefer _deployment_opt (pre-detected), then other fields
                        opt = (
                            deployment_opt
                            or checkbox_field
                            or field_attr
                            or checkbox_label
                            or option_attr
                            or target
                            or value
                        )
                        # Add uncheck prefix if this is an uncheck operation
                        if is_uncheck and opt:
                            opt_key = f"-{opt}"  # Prefix with - to indicate uncheck
                        else:
                            opt_key = opt
                        if opt_key and opt_key not in options:
                            options.insert(
                                0, opt_key
                            )  # Insert at beginning to preserve order
                            print(
                                f"   🔧 MERGE (backward): checkbox('{opt}'{', uncheck' if is_uncheck else ''}) → process_deployment options"
                            )
                            items_to_remove.append(k)
                        k -= 1
                        backward_count += 1
                        continue

                # 🆕 Also handle click("Versus Tournament") → deployment option
                # AI sometimes generates click instead of checkbox for deployment items
                if prev_action == "click":
                    click_target = str(prev_step.get("target", "")).strip()
                    click_target_lower = click_target.lower()
                    is_deployment_click = any(
                        keyword in click_target_lower for keyword in deployment_keywords
                    )
                    if is_deployment_click:
                        opt_key = click_target
                        if opt_key and opt_key not in options:
                            options.insert(0, opt_key)
                            print(
                                f"   🔧 MERGE (backward): click('{click_target}') → process_deployment options"
                            )
                            items_to_remove.append(k)
                        k -= 1
                        backward_count += 1
                        continue

                # Stop if we hit a navigation or other major action
                if prev_action in [
                    "navigate",
                    "smart_test_cycle",
                    "upload",
                    "download",
                    "edit_row",
                    "clone_row",
                ]:
                    break

                k -= 1
                backward_count += 1

            # Remove absorbed checkboxes (in reverse order to maintain indices)
            for idx in sorted(items_to_remove, reverse=True):
                merged.pop(idx)

            # Look FORWARD for checkbox/click that should be merged
            j = i + 1
            while j < len(plan):
                next_step = plan[j]
                next_action = next_step.get("action", "")

                if next_action == "checkbox":
                    value = str(next_step.get("value", ""))
                    target = next_step.get("target", "")
                    checkbox_label = next_step.get(
                        "checkbox_label", ""
                    )  # 🆕 AI sometimes uses this field
                    checkbox_field = next_step.get(
                        "checkbox", ""
                    )  # 🆕 AI also uses "checkbox" field
                    field_attr = next_step.get(
                        "field", ""
                    )  # 🆕 AI also uses "field" key (e.g. "Faction Feud")
                    deployment_opt = next_step.get(
                        "_deployment_opt", ""
                    )  # Pre-detected
                    is_uncheck = next_step.get("_uncheck", False)

                    # 🆕 SMART DETECTION: Check if this is a deployment option
                    is_deployment_option = bool(
                        deployment_opt
                    )  # Already detected in STEP 2

                    # 🆕 Also check 'option' field (AI sometimes uses this key)
                    option_attr = next_step.get("option", "")

                    if not is_deployment_option:
                        # Fallback: Check all possible fields
                        fields_to_check = [
                            checkbox_field,
                            field_attr,
                            checkbox_label,
                            option_attr,
                            target,
                            value,
                        ]

                        for field in fields_to_check:
                            if field:
                                field_lower = str(field).lower()
                                for keyword in deployment_keywords:
                                    if keyword in field_lower:
                                        is_deployment_option = True
                                        break
                                if is_deployment_option:
                                    break

                    # If not random_ OR is deployment option name, merge it
                    # CRITICAL: Even if value is random_X, if target/checkbox/field/option contains deployment keyword, still merge it
                    if not value.startswith("random_") or is_deployment_option:
                        # Prefer _deployment_opt (pre-detected), then other fields
                        opt = (
                            deployment_opt
                            or checkbox_field
                            or field_attr
                            or checkbox_label
                            or option_attr
                            or target
                            or value
                        )
                        # Add uncheck prefix if this is an uncheck operation
                        if is_uncheck and opt:
                            opt_key = f"-{opt}"
                        else:
                            opt_key = opt
                        if opt_key and opt_key != "ID" and opt_key not in options:
                            options.append(opt_key)
                        print(
                            f"   🔧 MERGE (forward): checkbox('{opt}'{', uncheck' if is_uncheck else ''}) → process_deployment options"
                        )
                        j += 1
                    else:
                        # It's a table checkbox (random_X without deployment keyword)
                        # Only break if we're sure it's NOT a deployment option
                        print(
                            f"   ⚠️  Skipping table checkbox (target='{target}', value='{value}')"
                        )
                        break
                elif next_action == "click":
                    click_fwd_target = next_step.get("target", "")
                    click_fwd_lower = click_fwd_target.lower().strip()
                    # Case A: click("Process"/"Deploy"/etc.) → absorbed button
                    if click_fwd_lower in (
                        "process",
                        "deploy",
                        "bấm process",
                        "nút process",
                        "process button",
                        "button process",
                    ):
                        print(
                            f"   🔧 MERGE: click('Process') → absorbed by process_deployment"
                        )
                        j += 1
                    # Case B: click("Versus Tournament"/"Offers"/etc.) → deployment option
                    elif any(
                        keyword in click_fwd_lower for keyword in deployment_keywords
                    ):
                        opt = click_fwd_target
                        if opt and opt not in options:
                            options.append(opt)
                        print(
                            f"   🔧 MERGE (forward): click('{opt}') → process_deployment options"
                        )
                        j += 1
                    else:
                        break
                else:
                    break

            # [FIX] Filter out button names from options (Process, Deploy, etc.)
            # These are NOT deployment checkboxes!
            button_names = [
                "process",
                "deploy",
                "submit",
                "confirm",
                "ok",
                "yes",
                "save",
            ]
            options = [opt for opt in options if opt.lower() not in button_names]

            # Apply uncheck_targets to existing options that weren't from checkbox steps
            if uncheck_targets:
                new_options = []
                for opt in options:
                    if opt.startswith("-"):
                        new_options.append(opt)  # Already marked as uncheck
                    else:
                        opt_lower = opt.lower().strip()
                        if opt_lower in uncheck_targets or any(
                            t in opt_lower or opt_lower in t for t in uncheck_targets
                        ):
                            new_options.append(f"-{opt}")
                            print(
                                f"   🔧 Applied uncheck prefix to existing option: '{opt}' → '-{opt}'"
                            )
                        else:
                            new_options.append(opt)
                options = new_options

            step["options"] = options

            # 🆕 Debug: Print final options
            if not options:
                print(
                    f"   ⚠️ WARNING: process_deployment has no options (will just click Process button)"
                )
            else:
                print(f"   ✅ process_deployment final options: {options}")

            merged.append(step)
            i = j
        else:
            merged.append(step)
            i += 1

    # 🆕 STEP 4: Filter out invalid/duplicate actions
    # Common deployment options keywords (reuse from module constant)
    deployment_keywords = DEPLOYMENT_KEYWORDS

    filtered = []
    has_process_deployment = False  # Track if we've seen process_deployment

    for idx, step in enumerate(merged):
        action = step.get("action", "")
        target = step.get("target", "")

        # [FIX] Track process_deployment
        if action == "process_deployment":
            has_process_deployment = True

        # [FIX] Filter out navigate/process_deployment after a process_deployment
        # Because process_deployment already navigates to Home page
        if has_process_deployment and idx > 0:
            # Check if previous steps contain process_deployment
            prev_has_deployment = any(
                merged[i].get("action") == "process_deployment" for i in range(idx)
            )

            if prev_has_deployment:
                # Filter navigate to deployment-related pages (The Brick, Home, etc.)
                if action == "navigate":
                    path = step.get("path", [])
                    if not isinstance(path, list):
                        path = [path] if path else []

                    # Deployment-related navigation keywords
                    deployment_nav = ["the brick", "brick", "home", "logo", "main"]

                    # Check if any path element matches deployment navigation
                    is_deployment_nav = any(
                        any(kw in str(p).lower() for kw in deployment_nav) for p in path
                    )

                    if is_deployment_nav:
                        print(
                            f"   🔧 FILTER: Removing navigate after process_deployment (path={path})"
                        )
                        continue

                # Filter duplicate process_deployment → merge options into first one
                if action == "process_deployment":
                    # Find the first process_deployment and merge options into it
                    first_pd = next(
                        (
                            s
                            for s in filtered
                            if s.get("action") == "process_deployment"
                        ),
                        None,
                    )
                    if first_pd is not None:
                        dup_options = step.get("options", [])
                        existing_options = first_pd.get("options", [])
                        for opt in dup_options:
                            if opt and opt not in existing_options:
                                existing_options.append(opt)
                        first_pd["options"] = existing_options
                        if dup_options:
                            print(
                                f"   🔧 FILTER: Merging duplicate process_deployment options {dup_options} → {existing_options}"
                            )
                        else:
                            print(
                                f"   🔧 FILTER: Removing duplicate process_deployment (no new options)"
                            )
                    continue

        # Filter out click actions with empty/whitespace-only target
        if action == "click":
            if not target or not target.strip():
                print(f"   🔧 FILTER: Removing invalid click action (empty target)")
                continue

        # 🆕 Filter out orphaned deployment checkbox (checkbox that should have been merged)
        # If checkbox contains deployment keyword and value is NOT random_X, it's likely a duplicate
        if action == "checkbox":
            value = str(step.get("value", ""))
            checkbox_field = step.get("checkbox", "")
            checkbox_label = step.get("checkbox_label", "")
            field_attr = step.get("field", "")  # 🆕 AI also uses "field" key
            option_attr = step.get("option", "")  # 🆕 AI also uses "option" key

            # target="ID" → table-row checkbox, never a deployment checkbox
            if target.lower().strip() == "id":
                filtered.append(step)
                continue

            # Check if this is a deployment option checkbox
            is_deployment_checkbox = False
            for field in [
                checkbox_field,
                field_attr,
                checkbox_label,
                option_attr,
                target,
                value,
            ]:
                if field:
                    field_lower = str(field).lower()
                    for keyword in deployment_keywords:
                        if keyword in field_lower and not value.startswith("random_"):
                            is_deployment_checkbox = True
                            break
                    if is_deployment_checkbox:
                        break

            # If it's a deployment checkbox, check if there's a process_deployment nearby
            if is_deployment_checkbox:
                # Look backward/forward for process_deployment within 2 steps
                has_nearby_process_deployment = False
                for j in range(max(0, idx - 2), min(len(merged), idx + 3)):
                    if j != idx and merged[j].get("action") == "process_deployment":
                        has_nearby_process_deployment = True
                        break

                if has_nearby_process_deployment:
                    deployment_opt = (
                        checkbox_field
                        or field_attr
                        or checkbox_label
                        or target
                        or value
                    )
                    print(
                        f"   🔧 FILTER: Removing orphaned deployment checkbox('{deployment_opt}') - already merged"
                    )
                    continue

        filtered.append(step)

    # Clean up internal keys from all steps
    # 🆕 SYNTHESIS: If plan has deployment checkboxes but NO process_deployment,
    # synthesize one. Pattern: checkbox(Toggle All) + checkbox(-Excel) + click(Process)
    # becomes: process_deployment(options=["Toggle All", "-Excel"])
    has_pd = any(s.get("action") == "process_deployment" for s in filtered)
    if not has_pd:
        deployment_checkboxes = []
        non_deployment_indices = []
        click_process_idx = None

        for idx, step in enumerate(filtered):
            action = step.get("action", "")
            if action == "checkbox":
                # Check if deployment checkbox (same logic as orphan filter)
                target = step.get("target", "")
                value = str(step.get("value", ""))
                checkbox_field = step.get("checkbox", "")
                field_attr = step.get("field", "")
                checkbox_label = step.get("checkbox_label", "")

                # target="ID" means table-row checkbox (e.g. "Chọn ID 'X'") — never deployment
                if target.lower().strip() == "id":
                    non_deployment_indices.append(idx)
                    continue

                is_dep = False
                opt_name = None
                for f in [checkbox_field, field_attr, checkbox_label, target, value]:
                    if f:
                        f_lower = str(f).lower()
                        for kw in deployment_keywords:
                            if kw in f_lower or f_lower in kw:
                                is_dep = True
                                opt_name = f
                                break
                        if is_dep:
                            break

                if is_dep:
                    deployment_checkboxes.append((idx, opt_name, step))
                else:
                    non_deployment_indices.append(idx)
            elif action == "click" and step.get("target", "").lower() in (
                "process",
                "deploy",
                "bấm process",
                "nút process",
                "process button",
            ):
                click_process_idx = idx

        if deployment_checkboxes and (
            click_process_idx is not None or len(deployment_checkboxes) >= 1
        ):
            # Build options list
            options = []
            for _, opt_name, step in deployment_checkboxes:
                # Check _uncheck flag (set in STEP 2 of fix_action_plan)
                is_uncheck = step.get("_uncheck", False)
                opt = opt_name
                if is_uncheck:
                    opt = f"-{opt}"
                if opt not in options:
                    options.append(opt)

            # Remove absorbed steps and replace with process_deployment
            indices_to_remove = set(idx for idx, _, _ in deployment_checkboxes)
            if click_process_idx is not None:
                indices_to_remove.add(click_process_idx)

            new_filtered = []
            pd_inserted = False
            for idx, step in enumerate(filtered):
                if idx in indices_to_remove:
                    if not pd_inserted:
                        new_filtered.append(
                            {"action": "process_deployment", "options": options}
                        )
                        pd_inserted = True
                        print(
                            f"   🔧 SYNTHESIZE: deployment checkboxes + click(Process) → process_deployment(options={options})"
                        )
                else:
                    new_filtered.append(step)
            if not pd_inserted:
                new_filtered.append(
                    {"action": "process_deployment", "options": options}
                )
                print(
                    f"   🔧 SYNTHESIZE: deployment checkboxes → process_deployment(options={options})"
                )
            filtered = new_filtered

    # Clean up internal keys from all steps
    for step in filtered:
        step.pop("_deployment_opt", None)
        step.pop("_uncheck", None)

    # 🆕 DEBUG: Print plan after merge
    print(f"\n   📋 DEBUG - Plan AFTER merge ({len(filtered)} steps):")
    for idx, step in enumerate(filtered):
        action = step.get("action", "?")
        target = step.get("target", "")
        value = step.get("value", "")
        options = step.get("options", [])
        if action == "process_deployment":
            print(f"      {idx}: {action} (options={options})")
        elif action == "checkbox":
            print(f"      {idx}: {action} (target={target}, value={value})")
        else:
            print(f"      {idx}: {action}")

    return filtered


# Phrases that mean "click the home/Brick logo" (navigate-home, no deploy).
_LOGO_BRICK_PATTERNS = (
    "logo the brick",
    "logo thebrick",
    "logo brick",
    "the brick",
    "bấm logo",
    "click logo",
    "click the brick",
    "bấm the brick",
)


def _inject_missing_final_deployment(plan, user_command=""):
    """
    Guarantee a trailing process_deployment when the command ENDS with a
    "Bấm vào logo The Brick" instruction.

    Every smoke test case finishes by clicking the Brick logo to return home
    (and optionally Process a deploy). The AI frequently drops this final step,
    so the run never navigates home / never records the closing action. This
    fixer deterministically appends {"action":"process_deployment","options":[]}
    when:
      * the LAST "->" segment of the command is a logo-click, AND
      * that segment is NOT a deploy step (no "Process"/"Chọn checkbox"), AND
      * the plan does not already end with process_deployment.

    Deploy cases ("... -> Chọn checkbox X -> Process") already end with
    process_deployment(options=[...]) and are left untouched.
    """
    if not isinstance(plan, list):
        return plan

    cmd = (user_command or "").strip()
    if not cmd:
        return plan

    # Look at the final instruction segment only.
    last_seg = cmd.split("->")[-1].strip().lower()
    is_logo_segment = any(p in last_seg for p in _LOGO_BRICK_PATTERNS)
    if not is_logo_segment:
        return plan
    # If the closing segment is actually a deploy/process step, leave it to the
    # checkbox+process merge logic.
    if "process" in last_seg or "checkbox" in last_seg:
        return plan

    last_action = plan[-1].get("action") if plan and isinstance(plan[-1], dict) else None
    if last_action == "process_deployment":
        return plan

    plan.append({"action": "process_deployment", "options": []})
    print(
        "   🔧 INJECT: appended process_deployment(options=[]) — command ends with "
        "'logo The Brick' but plan was missing the final navigate-home step"
    )
    return plan



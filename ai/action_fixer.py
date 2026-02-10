# action_fixer.py - Post-processing logic để fix AI action names và merge steps


# ============================================================================
# SHARED CONSTANTS
# ============================================================================

# Deployment checkbox keywords - used for merging and filtering
DEPLOYMENT_KEYWORDS = [
    # Left column
    "localization",
    "excel",
    "currency",
    "consumables",
    "consumable",
    "faction feud",
    "grab bag",
    "grabbag",
    "chat channels",
    "chat channel",
    "pve",
    "faction mission",
    "merch store",
    "feature setting",
    "invasion",
    "mizz missions",
    "mizz mission",
    "subscription 1.5",
    "feature gate setting",
    "versus shop",
    "league config",
    "champion rewards",
    "battle shop",
    "notification",
    "reactivation flow",
    "auto play",
    "news modal",
    "stat change",
    # Right column
    "gacha events",
    "gacha event",
    "gacha",
    "offers",
    "offer",
    "missions",
    "mission",
    "fight card",
    "cash contract",
    "liveops message",
    "live ops message",
    "rbe",
    "faction lockbox",
    "promo code",
    "subscription & vip",
    "subscription vip",
    "perks",
    "perk",
    "effect cap setting",
    "social box gacha",
    "monthly bonus",
    "versus tournament",
    "player league",
    "strap and medal",
    "superstars",
    "superstar",
    "boost",
    "faction boss",
    "moment poster",
    "time challenge",
    "social friends",
    "social friend",
    "token",
    # Additional navigation contexts
    "data configs",
    "data config",
    "live events",
    "live event",
    "hyper blueprint",
    "prize wall",
    "shop",
    "store",
    "event",
    "config",
    "blueprint",
]


# ============================================================================
# POST-PROCESSING: FIX INVALID ACTION NAMES (Deterministic - 100% reliable)
# ============================================================================

# Mapping: invalid action name → valid action name
ACTION_NAME_MAP = {
    # Checkbox / Select variations
    "select_random_ids": "checkbox",
    "select_ids": "checkbox",
    "select_random": "checkbox",
    "check_checkbox": "checkbox",
    "select_checkbox": "checkbox",
    "tick_checkbox": "checkbox",
    "select_rows": "checkbox",
    "choose_ids": "checkbox",
    "pick_random": "checkbox",
    # Download / Export variations
    "export_csv": "download",
    "export": "download",
    "export_file": "download",
    "download_csv": "download",
    "download_file": "download",
    # Upload / Import variations
    "import_csv": "upload",
    "import": "upload",
    "import_file": "upload",
    "upload_csv": "upload",
    "upload_file": "upload",
    # Process / Deploy variations
    "click_logo": "process_deployment",
    "click_logo_the_brick": "process_deployment",
    "click_the_brick": "process_deployment",
    "click_brick": "process_deployment",
    "go_home": "process_deployment",
    "process": "process_deployment",
    "deploy": "process_deployment",
    # Click button variations
    "click_button": "click",
    "press_button": "click",
    "tap_button": "click",
    # Navigate variations
    "go_to": "navigate",
    "open_page": "navigate",
    "open_menu": "navigate",
    # Edit variations
    "edit": "edit_row",
    "edit_item": "edit_row",
    # Clone variations
    "clone": "clone_row",
    "clone_item": "clone_row",
    "duplicate": "clone_row",
    # Save variations
    "save": "save_form",
    # Smart test variations
    "test_cycle": "smart_test_cycle",
    "smart_test": "smart_test_cycle",
    "fuzz_test": "smart_test_cycle",
}

VALID_ACTIONS = {
    "navigate",
    "checkbox",
    "download",
    "upload",
    "manipulate_csv",
    "smart_test_cycle",
    "clone_row",
    "edit_row",
    "update_form",
    "save_form",
    "scan_tabs",
    "click",
    "select",
    "wait",
    "wait_for_page_load",
    "process_deployment",
}


def fix_action_plan(plan):
    """
    Post-process AI output: Fix invalid action names and field names.
    This is deterministic and 100% reliable regardless of what AI generates.
    """
    if not plan or not isinstance(plan, list):
        return plan

    fixed_plan = []
    last_filename = None  # Track filename for reuse

    for step in plan:
        if not isinstance(step, dict):
            continue

        action = step.get("action", "")

        # ============================================================
        # STEP 1: Fix action name
        # ============================================================
        if action in ACTION_NAME_MAP:
            old_action = action
            action = ACTION_NAME_MAP[action]
            step["action"] = action
            print(f"   🔧 AUTO-FIX: '{old_action}' → '{action}'")

        # ============================================================
        # STEP 2: Fix field names based on action type
        # ============================================================

        if action == "checkbox":
            # Fix: {count: 2} or {number: 2} → {target: "ID", value: "random_2"}
            if "count" in step:
                step["value"] = f"random_{step.pop('count')}"
            elif "number" in step:
                step["value"] = f"random_{step.pop('number')}"
            if "target" not in step:
                step["target"] = "ID"
            if "value" not in step and "label" in step:
                step["value"] = step.pop("label")
            # Fix: value rỗng → default random_1
            if not step.get("value") or str(step.get("value")).strip() == "":
                step["value"] = "random_1"
                print("   🔧 AUTO-FIX: checkbox value rỗng → random_1")

        elif action == "download":
            # Fix: {filename: "x.csv"} → {target: "Export CSV", value: "x.csv"}
            if "filename" in step:
                step["value"] = step.pop("filename")
            if "file" in step and "value" not in step:
                step["value"] = step.pop("file")
            if "target" not in step:
                step["target"] = "Export CSV"
            # Track filename for reuse
            if step.get("value"):
                last_filename = step["value"]

        elif action == "upload":
            # Fix: {filename: "x.csv"} → {target: "Import CSV", value: "x.csv"}
            if "filename" in step:
                step["value"] = step.pop("filename")
            if "file" in step and "value" not in step:
                step["value"] = step.pop("file")
            if "target" not in step:
                step["target"] = "Import CSV"
            # Reuse filename if empty
            if not step.get("value") and last_filename:
                step["value"] = last_filename
                print(f"   🔧 AUTO-FIX: Reused filename '{last_filename}' for upload")

        elif action == "smart_test_cycle":
            # Fix: {file: "x.csv"} → {value: "x.csv"}
            if "file" in step and "value" not in step:
                step["value"] = step.pop("file")
            if "filename" in step and "value" not in step:
                step["value"] = step.pop("filename")
            # Reuse filename if empty
            if not step.get("value") and last_filename:
                step["value"] = last_filename
                print(
                    f"   🔧 AUTO-FIX: Reused filename '{last_filename}' for smart_test_cycle"
                )
            # Track for next step
            if step.get("value"):
                last_filename = step["value"]

        elif action == "process_deployment":
            # Fix: {target: "The Brick"} → just process_deployment
            if "target" in step and step["target"] in (
                "The Brick",
                "logo The Brick",
                "logo",
            ):
                step.pop("target")
            if "options" not in step:
                step["options"] = []
            if "label" in step:
                # click_button label="Process" → already handled by process_deployment
                step.pop("label", None)

        elif action == "click":
            # Fix: {label: "X"} → {target: "X"}
            if "label" in step and "target" not in step:
                step["target"] = step.pop("label")

            # 🆕 Validate: Skip click actions with no target
            if not step.get("target") or not str(step.get("target")).strip():
                print(f"   🔧 FILTER: Skipping click action with empty target")
                continue

            # 🆕 DETECT: click("The Brick"/"logo") → process_deployment
            target_lower = str(step.get("target", "")).lower()
            brick_keywords = [
                "brick",
                "logo",
                "the brick",
                "brick logo",
                "logo the brick",
            ]

            if any(keyword in target_lower for keyword in brick_keywords):
                # Convert to process_deployment
                old_target = step.get("target")
                step["action"] = "process_deployment"
                step.pop("target", None)  # Remove target field
                step["options"] = step.get("options", [])  # Ensure options field exists
                print(f"   🔧 AUTO-FIX: click('{old_target}') → process_deployment")
                action = "process_deployment"  # Update action variable for subsequent processing

        elif action == "navigate":
            # Fix: {menu: [...]} → {path: [...]}
            if "menu" in step and "path" not in step:
                step["path"] = step.pop("menu")

        # Track download filenames
        if action == "download" and step.get("value"):
            last_filename = step["value"]

        # Skip unknown actions that can't be mapped
        if step.get("action") not in VALID_ACTIONS:
            print(
                f"   ⚠️ SKIP unknown action: '{step.get('action')}' (no mapping found)"
            )
            continue

        fixed_plan.append(step)

    # ============================================================
    # STEP 3: Merge consecutive NAVIGATE steps into path array
    # Pattern: navigate(A) → navigate(B) → navigate(C)
    # Should become: navigate(path=[A, B, C])
    # ============================================================
    fixed_plan = _merge_navigate_steps(fixed_plan)

    # ============================================================
    # STEP 4: Merge consecutive process_deployment-related actions
    # Pattern: click_logo → select_checkbox(Offers) → click_button(Process)
    # Should become: process_deployment(options=["Offers"])
    # ============================================================
    merged_plan = _merge_process_deployment_steps(fixed_plan)

    # ============================================================
    # STEP 5: AUTO-INFER deployment options if empty
    # If process_deployment has no options, infer from context
    # ============================================================
    merged_plan = _auto_infer_deployment_options(merged_plan)

    if len(merged_plan) != len(plan):
        print(
            f"   🔧 AUTO-FIX: Plan {len(plan)} steps → {len(merged_plan)} steps after fix"
        )

    return merged_plan


def _merge_navigate_steps(plan):
    """
    Merge consecutive navigate steps into a single navigate with path array.

    Example:
      Input:  [{"action": "navigate", "target": "A"},
               {"action": "navigate", "target": "B"},
               {"action": "navigate", "target": "C"}]
      Output: [{"action": "navigate", "path": ["A", "B", "C"]}]

    This optimizes navigation by using smart_navigate_path() instead of clicking each menu item separately.
    """
    if not plan:
        return plan

    print(f"\n   📋 DEBUG - Checking for consecutive navigate steps...")

    merged = []
    i = 0

    while i < len(plan):
        step = plan[i]
        action = step.get("action", "")

        if action == "navigate":
            # Start collecting navigate path
            path = []

            # If this navigate already has a path array, use it
            if step.get("path"):
                existing_path = step.get("path")
                if isinstance(existing_path, list):
                    path = existing_path
                else:
                    path = [existing_path]
            else:
                # Single target navigate
                target = step.get("target")
                if target:
                    path = [target]

            # Look forward for more consecutive navigate steps
            j = i + 1
            while j < len(plan):
                next_step = plan[j]
                next_action = next_step.get("action", "")

                if next_action == "navigate":
                    # Merge this into path
                    if next_step.get("path"):
                        next_path = next_step.get("path")
                        if isinstance(next_path, list):
                            path.extend(next_path)
                        else:
                            path.append(next_path)
                    else:
                        next_target = next_step.get("target")
                        if next_target:
                            path.append(next_target)
                    j += 1
                else:
                    # Stop merging if we hit a non-navigate action
                    break

            # Create merged navigate step
            if len(path) > 1:
                merged_step = {"action": "navigate", "path": path}
                print(
                    f"   🔧 MERGE: {len(path)} navigate steps → navigate(path={path})"
                )
                merged.append(merged_step)
            elif len(path) == 1:
                # Single navigate, keep as is
                merged.append({"action": "navigate", "path": path})

            i = j
        else:
            merged.append(step)
            i += 1

    return merged


def _auto_infer_deployment_options(plan):
    """
    Auto-infer deployment options from context if process_deployment has empty options.

    Context sources:
    1. Navigation path (e.g., "Offer" → infer "Offers")
    2. Uploaded filename (e.g., "gacha_*.csv" → infer "Gacha")
    3. Previous actions (e.g., after smart_test_cycle on table)
    """
    if not plan:
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


def _merge_process_deployment_steps(plan):
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

                    # 🆕 SMART DETECTION: Check if this is a deployment option
                    is_deployment_option = False

                    # Check all possible fields that might contain deployment option name
                    fields_to_check = [
                        checkbox_field,  # Check "checkbox" field first!
                        checkbox_label,
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
                        # Prefer "checkbox" field (AI's new convention), then checkbox_label, then target, then value
                        opt = checkbox_field or checkbox_label or target or value
                        if opt and opt not in options:
                            options.insert(
                                0, opt
                            )  # Insert at beginning to preserve order
                            print(
                                f"   🔧 MERGE (backward): checkbox('{opt}') → process_deployment options"
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

                    # 🆕 SMART DETECTION: Check if this is a deployment option
                    # Use same keywords as backward merge
                    is_deployment_option = False

                    # Check all possible fields that might contain deployment option name
                    fields_to_check = [
                        checkbox_field,  # Check "checkbox" field first!
                        checkbox_label,
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
                    # CRITICAL: Even if value is random_X, if target/checkbox contains deployment keyword, still merge it
                    if not value.startswith("random_") or is_deployment_option:
                        # Prefer "checkbox" field (AI's new convention), then checkbox_label, then target, then value
                        opt = checkbox_field or checkbox_label or target or value
                        if opt and opt != "ID" and opt not in options:
                            options.append(opt)
                        print(
                            f"   🔧 MERGE (forward): checkbox('{opt}') → process_deployment options"
                        )
                        j += 1
                    else:
                        # It's a table checkbox (random_X without deployment keyword)
                        # Only break if we're sure it's NOT a deployment option
                        print(
                            f"   ⚠️  Skipping table checkbox (target='{target}', value='{value}')"
                        )
                        break
                elif next_action == "click" and next_step.get("target", "").lower() in (
                    "process",
                    "deploy",
                    "bấm process",
                    "nút process",
                    "process button",
                    "button process",
                ):
                    # click(Process) → absorbed by process_deployment
                    print(
                        f"   🔧 MERGE: click('Process') → absorbed by process_deployment"
                    )
                    j += 1
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

                # Filter duplicate process_deployment
                if action == "process_deployment":
                    print(f"   🔧 FILTER: Removing duplicate process_deployment")
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

            # Check if this is a deployment option checkbox
            is_deployment_checkbox = False
            for field in [checkbox_field, checkbox_label, target, value]:
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
                    deployment_opt = checkbox_field or checkbox_label or target or value
                    print(
                        f"   🔧 FILTER: Removing orphaned deployment checkbox('{deployment_opt}') - already merged"
                    )
                    continue

        filtered.append(step)

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

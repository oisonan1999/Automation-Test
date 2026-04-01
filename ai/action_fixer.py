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
    "tournament",
    "versus",
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
    # Toggle All (special)
    "toggle all",
    "toogle all",
    "select all",
    "check all",
]


# ============================================================================
# NAVIGATION PATH MAP - Auto-resolve partial/shorthand paths to full menu paths
# ============================================================================

# Map: destination keyword (lowercase) → full navigation path
# When user says "Vào Faction Feud Event", AI may generate navigate(["Faction Feud Event"])
# This map resolves it to the full path ["Live Events", "Faction Feud", "Faction Feud Event"]
NAVIGATION_PATH_MAP = {
    # === Live Events ===
    # Faction Feud
    "faction feud event": ["Live Events", "Faction Feud", "Faction Feud Event"],
    "faction feud": ["Live Events", "Faction Feud"],
    # Gacha
    "gacha event": ["Live Events", "Gacha Event", "Gacha Event"],
    # Offer
    "offer": ["Live Events", "Offer", "Offer"],
    "offer section": ["Live Events", "Offer", "Offer Section"],
    "shop tier": ["Live Events", "Offer", "Shop Tier"],
    "store preview": ["Live Events", "Offer", "Store Preview"],
    "drip offer": ["Live Events", "Offer", "Drip Offer"],
    # Versus
    "tournament": ["Live Events", "Versus", "Tournament"],
    "versus tournament": ["Live Events", "Versus", "Tournament"],
    # Mission
    "mission": ["Live Events", "Mission", "Mission"],
    # Fight Card
    "fight card": ["Live Events", "Fight Card", "Fight Card"],
    # Cash Contract
    "cash contract": ["Live Events", "Cash Contract", "Cash Contract"],
    # RBE
    "rbe": ["Live Events", "RBE", "RBE"],
    # Faction Lockbox
    "faction lockbox": ["Live Events", "Faction Lockbox", "Faction Lockbox"],
    # Faction Boss
    "faction boss event": ["Live Events", "Faction Boss", "Faction Boss Event"],
    "faction boss": ["Live Events", "Faction Boss"],
    # Grab Bag
    "grab bag": ["Live Events", "Grab Bag", "Grab Bag"],
    "grabbag": ["Live Events", "Grab Bag", "Grab Bag"],
    # LiveOps Message
    "liveops message": ["Live Events", "LiveOps Message", "LiveOps Message"],
    "live ops message": ["Live Events", "LiveOps Message", "LiveOps Message"],
    # Promo Code
    "promo code": ["Live Events", "Promo Code", "Promo Code"],
    # Social Box Gacha
    "social box gacha": ["Live Events", "Social Box Gacha", "Social Box Gacha"],
    # Monthly Bonus
    "monthly bonus": ["Live Events", "Monthly Bonus", "Monthly Bonus"],
    # Prize Wall
    "prize wall": ["Live Events", "Prize Wall", "Prize Wall"],
    # Invasion
    "invasion": ["Live Events", "Invasion", "Invasion"],
    # Time Challenge
    "time challenge": ["Live Events", "Time Challenge", "Time Challenge"],
    # Moment Poster
    "moment poster": ["Live Events", "Moment Poster", "Moment Poster"],
    # PVE
    "pve": ["Live Events", "PVE", "PVE"],
    # Hyper Blueprint
    "hyper blueprint": ["Live Events", "Hyper Blueprint", "Hyper Blueprint"],
    # === Data Configs ===
    "perk": ["Data Configs", "Perk", "Perk"],
    "boost": ["Data Configs", "Boost", "Boost"],
    "superstar": ["Data Configs", "Superstar", "Superstar"],
    "superstars": ["Data Configs", "Superstar", "Superstar"],
    "currency": ["Data Configs", "Currency", "Currency"],
    "consumable": ["Data Configs", "Consumables", "Consumables"],
    "consumables": ["Data Configs", "Consumables", "Consumables"],
    "token": ["Data Configs", "Token", "Token"],
    "strap and medal": ["Data Configs", "Strap and Medal", "Strap and Medal"],
    "stat change": ["Data Configs", "Stat Change", "Stat Change"],
    "feature setting": ["Settings", "Feature Setting", "Feature Setting"],
    "feature gate setting": [
        "Settings",
        "Feature Gate Setting",
        "Feature Gate Setting",
    ],
    "league config": ["Live Events", "League", "League Config"],
    "champion rewards": ["Data Configs", "Champion Rewards", "Champion Rewards"],
    "player league": ["Live Events", "League", "Player League"],
    "notification": ["Data Configs", "Notification", "Notification"],
    "chat channels": ["Data Configs", "Chat Channels", "Chat Channels"],
    "effect cap setting": ["Data Configs", "Effect Cap Setting", "Effect Cap Setting"],
    "merch store": ["Data Configs", "Merch Store", "Merch Store"],
    "versus shop": ["Data Configs", "Versus Shop", "Versus Shop"],
    "battle shop": ["Data Configs", "Battle Shop", "Battle Shop"],
    "rarity release gate": ["Settings", "Rarity Release Gate"],
}


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
    # Uncheck variations
    "uncheck": "checkbox",
    "uncheck_checkbox": "checkbox",
    "unselect": "checkbox",
    "deselect": "checkbox",
    "untick": "checkbox",
    "uncheck_box": "checkbox",
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
    # Reorder / drag-and-drop variations
    "drag": "reorder",
    "drag_drop": "reorder",
    "drag_and_drop": "reorder",
    "move_to": "reorder",
    "move_item": "reorder",
    "move_row": "reorder",
    "drag_to": "reorder",
    "set_priority": "reorder",
    "change_order": "reorder",
    "reorder_item": "reorder",
    # Smart test variations
    "test_cycle": "smart_test_cycle",
    "smart_test": "smart_test_cycle",
    "fuzz_test": "smart_test_cycle",
    # Check fields variations
    "check_field": "check_fields",
    "verify_fields": "check_fields",
    "verify_field": "check_fields",
    "inspect_fields": "check_fields",
    "check_tab_fields": "check_fields",
    "check_tabs": "check_fields",
    "kiem_tra_fields": "check_fields",
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
    "check_fields",
    "click",
    "select",
    "wait",
    "wait_for_page_load",
    "process_deployment",
    "reorder",
}


def fix_action_plan(plan, user_command=""):
    """
    Post-process AI output: Fix invalid action names and field names.
    This is deterministic and 100% reliable regardless of what AI generates.

    Args:
        plan: The AI-generated action plan (list of dicts)
        user_command: The original user command string (used for clone detection)
    """
    if not plan or not isinstance(plan, list):
        return plan

    fixed_plan = []
    last_filename = None  # Track filename for reuse

    # Pre-parse user command for uncheck patterns
    # e.g. "Bỏ chọn checkbox Excel" → uncheck_targets = ["excel"]
    import re as _re

    uncheck_targets = set()
    uncheck_patterns = [
        r"bỏ\s*chọn\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"bo\s*chon\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"uncheck\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"untick\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"deselect\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"bỏ\s*tick\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
    ]
    cmd_lower = user_command.lower()
    for pattern in uncheck_patterns:
        for m in _re.finditer(pattern, cmd_lower, _re.IGNORECASE):
            uncheck_targets.add(m.group(1).strip().lower())
    if uncheck_targets:
        print(f"   🔍 Detected uncheck targets from command: {uncheck_targets}")

    for step in plan:
        if not isinstance(step, dict):
            continue

        action = step.get("action", "")

        # ============================================================
        # STEP 1: Fix action name (save original for uncheck detection)
        # ============================================================
        step["_original_action"] = action  # Save for uncheck detection
        if action in ACTION_NAME_MAP:
            old_action = action
            action = ACTION_NAME_MAP[action]
            step["action"] = action
            print(f"   🔧 AUTO-FIX: '{old_action}' → '{action}'")

        # ============================================================
        # STEP 2: Fix field names based on action type
        # ============================================================

        if action == "checkbox":
            # ============================================================
            # DETECT DEPLOYMENT-CONTEXT CHECKBOXES
            # If the checkbox target/value/field matches a deployment keyword,
            # keep it as-is (don't default to random_1) so the merge step
            # can pick it up later for process_deployment.
            # ============================================================
            target_val = str(step.get("target", "")).lower().strip()
            value_val = str(step.get("value", "")).lower().strip()
            field_val = str(step.get("field", "")).lower().strip()
            label_val = str(step.get("label", "")).lower().strip()
            checkbox_val = str(step.get("checkbox", "")).lower().strip()

            # Check if any field matches deployment keywords
            is_deployment_checkbox = False
            deployment_opt_name = None
            for check_val, check_key in [
                (checkbox_val, "checkbox"),
                (field_val, "field"),
                (label_val, "label"),
                (target_val, "target"),
                (value_val, "value"),
            ]:
                if check_val:
                    for keyword in DEPLOYMENT_KEYWORDS:
                        if keyword in check_val or check_val in keyword:
                            is_deployment_checkbox = True
                            deployment_opt_name = step.get(check_key, check_val)
                            break
                    if is_deployment_checkbox:
                        break

            # Detect uncheck intent from original action name, value, target, or any field
            original_action = step.get("_original_action", "")
            all_text = " ".join(
                [
                    original_action,
                    value_val,
                    label_val,
                    target_val,
                    field_val,
                    checkbox_val,
                    str(step.get("mode", "")),
                ]
            ).lower()
            is_uncheck = any(
                kw in all_text
                for kw in [
                    "uncheck",
                    "bỏ chọn",
                    "bo chon",
                    "unselect",
                    "deselect",
                    "untick",
                    "bỏ tick",
                    "remove",
                ]
            )

            # Also check if this target matches user command's uncheck targets
            if not is_uncheck and uncheck_targets and deployment_opt_name:
                opt_lower = str(deployment_opt_name).lower().strip()
                if opt_lower in uncheck_targets or any(
                    t in opt_lower or opt_lower in t for t in uncheck_targets
                ):
                    is_uncheck = True
                    print(
                        f"   🔍 Detected uncheck from command context: '{deployment_opt_name}'"
                    )

            if is_deployment_checkbox:
                # Keep deployment checkbox info intact for merge step
                if not step.get("_deployment_opt"):
                    step["_deployment_opt"] = (
                        deployment_opt_name or target_val or value_val
                    )
                if is_uncheck:
                    step["_uncheck"] = True
                # Don't apply random_1 defaults
            else:
                # Normal table checkbox: apply defaults
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

            # 🆕 DETECT: click("Save") / click("Save & Continue") → save_form
            target_lower = str(step.get("target", "")).lower().strip()
            if target_lower in ("save", "save button", "nút save", "bấm save", "lưu"):
                step["action"] = "save_form"
                step["mode"] = "save"
                step.pop("target", None)
                action = "save_form"
                print(f"   🔧 AUTO-FIX: click('Save') → save_form(mode=save)")
            elif target_lower in (
                "save & continue",
                "save and continue",
                "save continue",
            ):
                step["action"] = "save_form"
                step["mode"] = "continue"
                step.pop("target", None)
                action = "save_form"
                print(
                    f"   🔧 AUTO-FIX: click('Save & Continue') → save_form(mode=continue)"
                )

            # 🆕 DETECT: click("The Brick"/"logo") → process_deployment
            elif any(
                keyword in target_lower
                for keyword in [
                    "brick",
                    "logo",
                    "the brick",
                    "brick logo",
                    "logo the brick",
                ]
            ):
                # Convert to process_deployment
                old_target = step.get("target")
                step["action"] = "process_deployment"
                step.pop("target", None)  # Remove target field
                step["options"] = step.get("options", [])  # Ensure options field exists
                print(f"   🔧 AUTO-FIX: click('{old_target}') → process_deployment")
                action = "process_deployment"  # Update action variable for subsequent processing

        elif action in ("edit_row", "clone_row"):
            # Normalize random/any/bất kỳ targets to RANDOM sentinel
            _RANDOM_TARGETS = {
                "random",
                "any",
                "bất kỳ",
                "bat ky",
                "any row",
                "first",
                "một dòng bất kỳ",
                "bất kỳ dòng",
                "random_1",
                "random row",
                "any id",
                "bất kỳ id",
                "id bất kỳ",
            }
            tgt = str(step.get("target", "")).lower().strip()
            # Exact match OR contains "bất kỳ"/"random" pattern
            # Handles cases like "một Superstar bất kỳ", "Superstar bất kỳ", "random superstar"
            is_random_target = (
                tgt in _RANDOM_TARGETS
                or tgt == ""
                or "bất kỳ" in tgt
                or "bat ky" in tgt
                or ("random" in tgt and tgt != "random_1")
            )
            if is_random_target:
                step["target"] = "RANDOM"
                print(
                    f"   🔧 AUTO-FIX: {action}('{tgt or 'empty'}') → {action}('RANDOM') (random row mode)"
                )

        elif action == "navigate":
            # Fix: {menu: [...]} → {path: [...]}
            if "menu" in step and "path" not in step:
                step["path"] = step.pop("menu")

        elif action == "update_form":
            # ============================================================
            # FIX RADIO FIELDS: AI sometimes generates {"radio": "Label text"}
            # or {"radio option": "Use another currency"} instead of
            # {"Use another currency": "select"}
            # Detect these patterns and flip key/value so form_handler
            # can find the radio by its label text.
            # ============================================================
            data = step.get("data", {})
            if data and isinstance(data, dict):
                RADIO_KEY_PATTERNS = {
                    "radio",
                    "radio option",
                    "radio button",
                    "radio btn",
                    "radiobutton",
                    "radio_option",
                    "radio_button",
                    "select radio",
                    "choose radio",
                    "radio selection",
                    "radio_selection",
                }
                new_data = {}
                for k, v in data.items():
                    if k.lower().strip() in RADIO_KEY_PATTERNS and isinstance(v, str):
                        # Flip: use label text as key, "select" as value
                        new_data[v] = "select"
                        print(f"   🔧 AUTO-FIX radio: '{k}': '{v}' → '{v}': 'select'")
                    else:
                        new_data[k] = v
                step["data"] = new_data

            # ============================================================
            # FIX PYTHON LIST STRINGS: AI sometimes wraps multi-value fields
            # in Python list syntax, e.g. "['2026-02-23 00:00:00', '2026-02-23 11:00:00']"
            # Convert these to plain comma-separated strings so form_handler
            # can split them correctly.
            # ============================================================
            data = step.get("data", {})
            if data and isinstance(data, dict):
                import re as _re

                cleaned_data = {}
                for k, v in data.items():
                    if isinstance(v, str):
                        stripped = v.strip()
                        # Matches both ['...', '...'] and ["...", "..."] list literals
                        if stripped.startswith("[") and stripped.endswith("]"):
                            inner = stripped[1:-1]
                            # Remove surrounding quotes from each element and rejoin
                            parts = _re.split(r",\s*", inner)
                            clean_parts = [
                                p.strip().strip("'\"")
                                for p in parts
                                if p.strip().strip("'\"")
                            ]
                            if clean_parts:
                                new_val = ", ".join(clean_parts)
                                print(
                                    f"   🔧 AUTO-FIX list string: '{k}': {stripped!r} → {new_val!r}"
                                )
                                cleaned_data[k] = new_val
                                continue
                    cleaned_data[k] = v
                step["data"] = cleaned_data

        # Track download filenames
        if action == "download" and step.get("value"):
            last_filename = step["value"]

        # Clean up internal keys before adding to plan
        step.pop("_original_action", None)

        # Skip unknown actions that can't be mapped
        if step.get("action") not in VALID_ACTIONS:
            print(
                f"   ⚠️ SKIP unknown action: '{step.get('action')}' (no mapping found)"
            )
            continue

        fixed_plan.append(step)

    # ============================================================
    # STEP 3: Resolve partial/shorthand navigation paths
    # e.g. ["Faction Feud Event"] → ["Live Events", "Faction Feud", "Faction Feud Event"]
    # ============================================================
    fixed_plan = _resolve_navigation_paths(fixed_plan)

    # ============================================================
    # STEP 3b: Merge consecutive NAVIGATE steps into path array
    # Pattern: navigate(A) → navigate(B) → navigate(C)
    # Should become: navigate(path=[A, B, C])
    # ============================================================
    fixed_plan = _merge_navigate_steps(fixed_plan)

    # ============================================================
    # STEP 4: Merge consecutive process_deployment-related actions
    # Pattern: click_logo → select_checkbox(Offers) → click_button(Process)
    # Should become: process_deployment(options=["Offers"])
    # ============================================================
    merged_plan = _merge_process_deployment_steps(
        fixed_plan, uncheck_targets=uncheck_targets
    )

    # ============================================================
    # STEP 5: AUTO-INFER deployment options if empty
    # If process_deployment has no options, infer from context
    # ============================================================
    merged_plan = _auto_infer_deployment_options(merged_plan)

    # ============================================================
    # STEP 6: AUTO-INJECT missing clone_row from user command
    # If user said "Clone ID: X" but AI skipped clone_row entirely,
    # inject it deterministically based on the original command.
    # ============================================================
    merged_plan = _inject_missing_clone_row(merged_plan, user_command)

    # ============================================================
    # STEP 7: AUTO-INJECT save_form(mode=clone) after clone_row
    # Pattern: clone_row → update_form → ???
    # If ??? is not save_form(mode=clone), inject it automatically.
    # Also splits update_form if it mixes modal fields + post-clone fields.
    # Also injects modal update_form from user_command if AI skipped it.
    # ============================================================
    merged_plan = _inject_clone_save(merged_plan, user_command)

    # ============================================================
    # STEP 8: Merge consecutive update_form → save_form(save) sequences
    # Pattern: update_form(A) → save_form(save) → update_form(B) → save_form(save)
    # Becomes: update_form(A ∪ B) → save_form(save)
    # Prevents validation errors when interdependent fields (e.g. PreEvent
    # dates + Active Phase dates) are split across separate save operations.
    # ============================================================
    merged_plan = _merge_consecutive_update_save(merged_plan)

    if len(merged_plan) != len(plan):
        print(
            f"   🔧 AUTO-FIX: Plan {len(plan)} steps → {len(merged_plan)} steps after fix"
        )

    return merged_plan


def _resolve_navigation_paths(plan):
    """
    Resolve partial/shorthand navigation paths using NAVIGATION_PATH_MAP.

    When user says "Vào Faction Feud Event" instead of
    "Vào Live Events -> Faction Feud -> Faction Feud Event",
    the AI generates navigate(path=["Faction Feud Event"]) with only 1 element.
    This function resolves it to the full path.

    Strategy:
    1. If path has 1 element → look up in NAVIGATION_PATH_MAP
    2. If path has 2 elements → check if last element matches a known destination
       and prepend missing parent(s)
    3. If path already has 3+ elements → likely already correct, skip
    """
    if not plan:
        return plan

    for step in plan:
        if step.get("action") != "navigate":
            continue

        path = step.get("path", [])
        target = step.get("target", "")

        # Convert single target to path list
        if not path and target:
            path = [target]

        if not path or not isinstance(path, list):
            continue

        # Build a lookup key from the path
        # Strategy: try matching the LAST element(s) of the path
        original_path = list(path)  # copy for logging

        # CASE 1: Single element path - most common shorthand
        # e.g. ["Faction Feud Event"] or ["Perk"]
        if len(path) == 1:
            key = path[0].strip().lower()
            if key in NAVIGATION_PATH_MAP:
                resolved = NAVIGATION_PATH_MAP[key]
                step["path"] = list(resolved)
                if "target" in step:
                    del step["target"]
                print(f"   🗺️  PATH-RESOLVE: {original_path} → {resolved}")
                continue

        # CASE 2: Two element path - might be missing top-level parent
        # e.g. ["Faction Feud", "Faction Feud Event"] missing "Live Events"
        # or ["Gacha Event", "Gacha Event"] missing "Live Events"
        if len(path) == 2:
            # Try matching the last element
            last_key = path[-1].strip().lower()
            if last_key in NAVIGATION_PATH_MAP:
                resolved = NAVIGATION_PATH_MAP[last_key]
                # Only replace if the resolved path is longer (has more context)
                if len(resolved) > len(path):
                    # Verify the existing path elements match the tail of resolved
                    path_lower = [p.strip().lower() for p in path]
                    resolved_lower = [r.lower() for r in resolved]
                    tail_match = resolved_lower[-len(path) :] == path_lower
                    if tail_match or path_lower[-1] == resolved_lower[-1]:
                        step["path"] = list(resolved)
                        if "target" in step:
                            del step["target"]
                        print(f"   🗺️  PATH-RESOLVE: {original_path} → {resolved}")
                        continue

            # Also try matching the full 2-element join as a key
            full_key = " ".join(p.strip() for p in path).lower()
            if full_key in NAVIGATION_PATH_MAP:
                resolved = NAVIGATION_PATH_MAP[full_key]
                if len(resolved) > len(path):
                    step["path"] = list(resolved)
                    if "target" in step:
                        del step["target"]
                    print(f"   🗺️  PATH-RESOLVE: {original_path} → {resolved}")
                    continue

        # CASE 3: Full path (3+ elements) - check if last element matches a known destination
        # and use the canonical path from the map. Handles plural/singular mismatches.
        # e.g. ["Data Configs", "Superstars", "Superstars"] → ["Data Configs", "Superstar", "Superstar"]
        if len(path) >= 3:
            last_key = path[-1].strip().lower()
            if last_key in NAVIGATION_PATH_MAP:
                resolved = NAVIGATION_PATH_MAP[last_key]
                if len(resolved) == len(path):
                    # Same depth - replace if different (fixes plural/singular mismatch)
                    if [p.strip().lower() for p in path] != [
                        r.lower() for r in resolved
                    ]:
                        step["path"] = list(resolved)
                        if "target" in step:
                            del step["target"]
                        print(
                            f"   🗺️  PATH-RESOLVE (canonical fix): {original_path} → {resolved}"
                        )
                        continue

    return plan


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


def _inject_missing_clone_row(plan, user_command=""):
    """
    AUTO-FIX: Detect when user command mentions "Clone ID: X" but AI
    completely skipped the clone_row action. Inject it deterministically.

    This handles the case where the AI jumps directly to update_form
    without first generating clone_row.

    Detection patterns in user command:
      - "Clone ID: X"
      - "Bấm nút Clone ID: X"
      - "Clone X" (where X looks like an ID)
      - "Bấm Clone X"

    Also ensures "New Event ID" / "New ID" is present in update_form data
    when "New ID: Y" is mentioned in the command.
    """
    import re as _re

    if not plan or not user_command:
        return plan

    # Check if plan already has a clone_row action
    has_clone_row = any(step.get("action") == "clone_row" for step in plan)
    if has_clone_row:
        return plan

    # --- Detect clone target from user command ---
    # Patterns (case-insensitive, Vietnamese + English):
    #   "Clone ID: EventGacha_test_15"
    #   "Bấm nút Clone ID: EventGacha_test_15"
    #   "Bấm Clone EventGacha_test_15"
    #   "Clone EventGacha_test_15"
    #   "Clone một ID bất kỳ"
    #   "Clone bất kỳ"
    #   "Clone random"
    clone_patterns = [
        # "Clone ID: X" or "Bấm nút Clone ID: X" — ID is part of the label
        r"(?:bấm\s+(?:nút\s+)?)?clone\s+id\s*:\s*([\w\-\.]+)",
        # "Clone X" where X looks like an ID (contains underscore or is alphanumeric)
        r"(?:bấm\s+(?:nút\s+)?)?clone\s+([\w\-\.]+(?:_[\w\-\.]+)+)",
        # "Clone bất kỳ", "Clone một ID bất kỳ", "Clone random" → RANDOM
        r"(?:bấm\s+(?:nút\s+)?)?clone\s+(?:một\s+)?(?:\w+\s+)*(?:bất\s*kỳ|random|any)",
    ]

    clone_target = None
    for idx_p, pattern in enumerate(clone_patterns):
        match = _re.search(pattern, user_command, _re.IGNORECASE)
        if match:
            if idx_p == 2:  # Random pattern matched
                clone_target = "RANDOM"
            else:
                clone_target = match.group(1).strip()
            break

    if not clone_target:
        return plan

    print(
        f"   🔧 CRITICAL AUTO-FIX: AI skipped clone_row! Detected 'Clone {clone_target}' in user command."
    )

    # --- Detect New ID from user command (generic: New Event ID, New FF ID, New ID) ---
    new_id = None
    new_id_field_name = "New Event ID"  # default
    new_id_patterns = [
        r"(new\s+(?:\w+\s+)?id)\s*:\s*([\w\-\.]+)",
    ]
    for pattern in new_id_patterns:
        match = _re.search(pattern, user_command, _re.IGNORECASE)
        if match:
            raw_label = match.group(1)
            new_id = match.group(2).strip()
            # Normalize field name
            words = raw_label.split()
            normalized = []
            for w in words:
                if w.lower() == "id":
                    normalized.append("ID")
                elif len(w) <= 2:
                    normalized.append(w.upper())  # Short abbrevs: "ff" → "FF"
                else:
                    normalized.append(w.capitalize())  # "new" → "New"
            new_id_field_name = " ".join(normalized)
            break

    # --- Find injection point ---
    # Insert clone_row AFTER navigate (if any) and BEFORE the first update_form
    inject_index = 0
    for idx, step in enumerate(plan):
        action = step.get("action", "")
        if action == "navigate":
            inject_index = idx + 1
        elif action in ("update_form", "edit_row"):
            inject_index = idx
            break

    # If AI generated edit_row instead of clone_row for the same target, replace it
    replaced_edit = False
    for idx, step in enumerate(plan):
        if step.get("action") == "edit_row" and step.get("target") == clone_target:
            step["action"] = "clone_row"
            replaced_edit = True
            print(
                f"   🔧 AUTO-FIX: Converted edit_row('{clone_target}') → clone_row('{clone_target}')"
            )
            break

    if not replaced_edit:
        # Inject clone_row at the right position
        clone_step = {"action": "clone_row", "target": clone_target}
        plan.insert(inject_index, clone_step)
        print(
            f"   🔧 AUTO-FIX: Injected clone_row('{clone_target}') at position {inject_index}"
        )

    # --- Ensure New ID field is in the update_form data ---
    if new_id:
        # Find the first update_form after clone_row
        clone_idx = None
        for idx, step in enumerate(plan):
            if step.get("action") == "clone_row" and step.get("target") == clone_target:
                clone_idx = idx
                break

        if clone_idx is not None:
            # Look for update_form immediately after clone_row
            for idx in range(clone_idx + 1, len(plan)):
                step = plan[idx]
                if step.get("action") == "update_form":
                    data = step.get("data", {})
                    # Check if any New ID variant is already present (case-insensitive)
                    has_new_id = any(
                        _re.search(r"\bnew\b.*\bid\b", k, _re.IGNORECASE)
                        for k in data.keys()
                    )
                    if not has_new_id:
                        # Insert New ID field at the beginning of data
                        new_data = {new_id_field_name: new_id}
                        new_data.update(data)
                        step["data"] = new_data
                        print(
                            f"   🔧 AUTO-FIX: Added '{new_id_field_name}': '{new_id}' to update_form data"
                        )
                    break
                elif step.get("action") not in ("wait",):
                    # If there's no update_form directly after clone, create one
                    new_update = {
                        "action": "update_form",
                        "data": {new_id_field_name: new_id},
                    }
                    plan.insert(idx, new_update)
                    print(
                        f"   🔧 AUTO-FIX: Created update_form with '{new_id_field_name}': '{new_id}'"
                    )
                    break

    return plan


def _extract_clone_modal_fields(user_command):
    """
    Parse user command to extract clone modal field values.
    Returns a dict of modal fields extracted from the command text.

    Handles patterns like:
      "Clone ID: X -> New ID: Y, gate: Z, radio: Use another currency, currency: W"
      "Clone một ID bất kỳ -> New FF ID: Y, Gate: Z"
      "Clone random -> New Event ID: Y, Gate: Z"
    """
    import re as _re

    if not user_command:
        return {}

    modal_data = {}

    # --- Step 1: Find the "Clone" keyword in the command ---
    clone_start = _re.search(r"\bclone\b", user_command, _re.IGNORECASE)
    if not clone_start:
        return {}

    # --- Step 2: Find the first "->" after "Clone" ---
    arrow_pos = user_command.find("->", clone_start.start())
    if arrow_pos == -1:
        return {}

    # --- Step 3: Extract segment after first "->" up to next action boundary ---
    remaining = user_command[arrow_pos + 2 :].strip()

    # Find the boundary (next major action marker after ->)
    boundary_match = _re.search(
        r"->\s*(?:đợi|wait|sửa|bấm\s+nút\s+save|save|click|vào|export|import|process|logo|the\s+brick)",
        remaining,
        _re.IGNORECASE,
    )
    if boundary_match:
        segment = remaining[: boundary_match.start()].strip()
    else:
        segment = remaining.strip()

    if not segment:
        return {}

    print(f"   🔍 Parsing clone modal fields from segment: '{segment[:100]}...'")

    # --- Extract New [X] ID (generic: handles New Event ID, New FF ID, New ID, etc.) ---
    new_id_match = _re.search(
        r"(new\s+(?:\w+\s+)?id)\s*:\s*([\w\-\.]+)", segment, _re.IGNORECASE
    )
    if new_id_match:
        raw_label = new_id_match.group(1)  # e.g. "New FF ID", "New Event ID"
        value = new_id_match.group(2).strip()
        # Normalize field name: capitalize words, keep ID/FF uppercase
        words = raw_label.split()
        normalized = []
        for w in words:
            if w.lower() == "id":
                normalized.append("ID")
            elif len(w) <= 2:
                normalized.append(w.upper())  # Short abbrevs: "ff" → "FF"
            else:
                normalized.append(w.capitalize())  # "new" → "New", "event" → "Event"
        field_name = " ".join(normalized)
        modal_data[field_name] = value

    # --- Extract Gate ---
    gate_match = _re.search(r"\bgate\s*:\s*([\w\-\.]+)", segment, _re.IGNORECASE)
    if gate_match:
        modal_data["Gate"] = gate_match.group(1).strip()

    # --- Extract Radio selection ---
    # "radio: Use another currency" or "radio: Auto Generate a new currency"
    radio_match = _re.search(
        r"radio\s*:\s*((?:use another currency|auto generate[\w\s]*))",
        segment,
        _re.IGNORECASE,
    )
    if radio_match:
        radio_label = radio_match.group(1).strip()
        # Capitalize properly
        if "use another" in radio_label.lower():
            modal_data["Use another currency"] = "select"
        elif "auto generate" in radio_label.lower():
            modal_data["Auto Generate a new currency"] = "select"
        else:
            modal_data[radio_label] = "select"

    # --- Extract Currency ---
    # Match "currency: X" but NOT "radio: ... currency" or "another currency"
    currency_match = _re.search(
        r"(?<!another\s)(?<!a new\s)\bcurrency\s*:\s*([\w\-\.]+)",
        segment,
        _re.IGNORECASE,
    )
    if currency_match:
        val = currency_match.group(1).strip()
        # Avoid capturing "GachaShard" if it's actually in a radio label context
        if val.lower() not in ("use", "auto", "another", "a"):
            modal_data["Currency"] = val

    if modal_data:
        print(f"   ✅ Extracted clone modal fields: {modal_data}")
    else:
        print(f"   ⚠️ Could not extract clone modal fields from command")

    return modal_data


def _merge_consecutive_update_save(plan):
    """
    Merge consecutive update_form → save_form(save) sequences into a single
    update_form → save_form(save).

    Pattern:
        update_form(A) → save_form(save) → update_form(B) → save_form(save) → ...
    Becomes:
        update_form(A ∪ B ∪ ...) → save_form(save)

    This prevents form validation errors when interdependent fields
    (e.g. PreEvent Phase dates and Active Phase dates) are split across
    separate save operations by the AI.

    Only merges save_form with mode='save'. Does NOT merge 'clone' or 'continue'.
    """
    if not plan or len(plan) < 4:
        return plan

    merged = []
    i = 0

    while i < len(plan):
        step = plan[i]

        # Check if this starts an update_form → save_form(save) sequence
        if (
            step.get("action") == "update_form"
            and i + 1 < len(plan)
            and plan[i + 1].get("action") == "save_form"
            and plan[i + 1].get("mode") == "save"
        ):
            # Collect all consecutive update_form → save_form(save) pairs
            combined_data = dict(step.get("data") or {})
            pairs_count = 1
            j = i + 2  # After the first save_form

            while (
                j < len(plan)
                and plan[j].get("action") == "update_form"
                and j + 1 < len(plan)
                and plan[j + 1].get("action") == "save_form"
                and plan[j + 1].get("mode") == "save"
            ):
                # Merge data from next update_form
                combined_data.update(plan[j].get("data") or {})
                pairs_count += 1
                j += 2  # Skip both update_form and save_form

            if pairs_count > 1:
                # We merged multiple pairs
                print(
                    f"   🔧 MERGE: Combined {pairs_count} update_form+save_form(save) "
                    f"pairs into 1 (fields: {list(combined_data.keys())})"
                )
                merged.append({"action": "update_form", "data": combined_data})
                merged.append({"action": "save_form", "mode": "save"})
                i = j
            else:
                # Only one pair, keep as-is
                merged.append(plan[i])
                i += 1
        else:
            merged.append(step)
            i += 1

    return merged


def _inject_clone_save(plan, user_command=""):
    """
    AUTO-FIX: Inject save_form(mode='clone') after clone_row → update_form pattern.

    The Clone modal has its own set of fields (New Event ID, Gate, radio, Currency).
    After filling the modal, the user must click the Clone button (= save_form mode=clone).
    Any fields that belong to the NEW event page (Schedule, etc.) come AFTER that.

    This function:
    1. Detects clone_row followed by update_form
    2. Splits update_form into MODAL fields + POST-CLONE fields (if mixed)
    3. Injects save_form(mode=clone) between them
    4. If modal update_form is entirely missing, extracts fields from user_command
    """
    # Fields that live INSIDE the Clone modal
    CLONE_MODAL_FIELD_KEYWORDS = {
        "new event id",
        "new id",
        "new ff id",
        "new gacha id",
        "new boss id",
        "new offer id",
        "new mission id",
        "gate",
        "currency",
        "use another currency",
        "auto generate a new currency",
        "auto generate",
        "clone milestones",
    }

    # Fields that belong OUTSIDE the modal (on the new event page after cloning)
    POST_CLONE_FIELD_KEYWORDS = {
        "schedule",
        "date",
        "time",
        "start",
        "end",
        "leaderboard",
        "consumable limit",
        "milestones type",
        "bracket preset",
    }

    def is_modal_field(key):
        import re as _re

        k = key.lower().strip()
        # Direct keyword match
        if any(kw in k for kw in CLONE_MODAL_FIELD_KEYWORDS):
            return True
        # Pattern match: "new ... id" covers all event types
        # e.g. "New FF ID", "New Event ID", "New Boss ID", etc.
        if _re.search(r"\bnew\b.*\bid\b", k):
            return True
        return False

    def is_post_clone_field(key):
        k = key.lower().strip()
        # If explicitly a modal field, don't treat as post-clone
        if is_modal_field(k):
            return False
        return any(kw in k for kw in POST_CLONE_FIELD_KEYWORDS)

    if not plan:
        return plan

    result = []
    i = 0
    while i < len(plan):
        step = plan[i]
        action = step.get("action", "")

        if action == "clone_row":
            result.append(step)
            i += 1

            # Gather consecutive update_form steps that follow clone_row
            update_forms = []
            while i < len(plan) and plan[i].get("action") == "update_form":
                update_forms.append(plan[i])
                i += 1

            if not update_forms:
                # Check if save_form(clone) is immediately after clone_row
                if (
                    i < len(plan)
                    and plan[i].get("action") == "save_form"
                    and plan[i].get("mode") == "clone"
                ):
                    # BAD PATTERN: clone_row → save_form(clone) → [wait?] → update_form(modal fields)
                    # Look ahead to pull modal update_form fields BEFORE save_form(clone)
                    j = i + 1  # start looking past save_form(clone)

                    # Skip wait steps between save_form and update_form
                    skipped_waits = []
                    while j < len(plan) and plan[j].get("action") == "wait":
                        skipped_waits.append(plan[j])
                        j += 1

                    # Collect consecutive update_form steps ahead
                    lookahead_updates = []
                    while j < len(plan) and plan[j].get("action") == "update_form":
                        lookahead_updates.append(plan[j])
                        j += 1

                    if lookahead_updates:
                        # Merge all ahead update_form data to check for modal fields
                        all_data = {}
                        for uf in lookahead_updates:
                            all_data.update(uf.get("data") or {})

                        # Check if any modal fields are in the lookahead
                        has_modal = any(is_modal_field(k) for k in all_data)

                        if has_modal:
                            # Reorder: split modal vs post-clone, emit correctly
                            modal_data = {}
                            post_clone_data = {}
                            mixed_data = {}
                            for key, val in all_data.items():
                                if is_modal_field(key):
                                    modal_data[key] = val
                                elif is_post_clone_field(key):
                                    post_clone_data[key] = val
                                else:
                                    mixed_data[key] = val
                            modal_data.update(mixed_data)

                            if modal_data:
                                result.append(
                                    {"action": "update_form", "data": modal_data}
                                )
                                print(
                                    f"   🔧 AUTO-FIX: Moved misplaced modal fields {list(modal_data.keys())} "
                                    "before save_form(mode=clone)"
                                )
                            result.append({"action": "save_form", "mode": "clone"})
                            for w in skipped_waits:
                                result.append(w)
                            if post_clone_data:
                                result.append(
                                    {"action": "update_form", "data": post_clone_data}
                                )
                                print(
                                    f"   🔧 AUTO-FIX: Placed post-clone fields {list(post_clone_data.keys())} "
                                    "after save_form(mode=clone)"
                                )
                            # Advance i past all consumed steps
                            i = j
                            continue

                    # No modal fields found ahead — try extracting from user command
                    extracted = _extract_clone_modal_fields(user_command)
                    if extracted:
                        result.append({"action": "update_form", "data": extracted})
                        print(
                            f"   🔧 CRITICAL AUTO-FIX: Injected missing modal update_form "
                            f"from user command: {list(extracted.keys())}"
                        )
                        result.append({"action": "save_form", "mode": "clone"})
                        for w in skipped_waits:
                            result.append(w)
                        # Re-emit ahead update_forms as post-clone
                        for uf in lookahead_updates:
                            result.append(uf)
                        i = j
                    else:
                        # Truly nothing — pass through as-is
                        pass
                    continue

                # No update_form AND no save_form(clone) after clone_row
                # Try extracting modal fields from user command
                extracted = _extract_clone_modal_fields(user_command)
                if extracted:
                    result.append({"action": "update_form", "data": extracted})
                    print(
                        f"   🔧 CRITICAL AUTO-FIX: Injected missing modal update_form "
                        f"from user command: {list(extracted.keys())}"
                    )
                result.append({"action": "save_form", "mode": "clone"})
                print("   🔧 AUTO-FIX: Injected save_form(mode=clone) after clone_row")
                continue

            # Check if save_form(mode=clone) is already immediately after update_forms
            already_has = (
                i < len(plan)
                and plan[i].get("action") == "save_form"
                and plan[i].get("mode") == "clone"
            )

            if already_has:
                # Already correct — just pass through
                for uf in update_forms:
                    result.append(uf)
                continue

            # Merge all update_form data into one flat dict to analyse
            all_data = {}
            for uf in update_forms:
                all_data.update(uf.get("data") or {})

            # Split: modal fields vs post-clone fields
            modal_data = {}
            post_clone_data = {}
            mixed_data = {}  # Fields that are neither clearly modal nor post-clone

            for key, val in all_data.items():
                if is_modal_field(key):
                    modal_data[key] = val
                elif is_post_clone_field(key):
                    post_clone_data[key] = val
                else:
                    mixed_data[key] = val

            # Fields in mixed_data that have no clear ownership stay with modal
            # (safe default: they were probably intended for the modal)
            modal_data.update(mixed_data)

            # If no modal fields found in update_form, try extracting from user command
            if not modal_data:
                extracted = _extract_clone_modal_fields(user_command)
                if extracted:
                    modal_data = extracted
                    print(
                        f"   🔧 CRITICAL AUTO-FIX: No modal fields in update_form, "
                        f"extracted from user command: {list(extracted.keys())}"
                    )

            if modal_data:
                result.append({"action": "update_form", "data": modal_data})

            # Always inject the Clone button click
            result.append({"action": "save_form", "mode": "clone"})
            print(
                f"   🔧 AUTO-FIX: Injected save_form(mode=clone) after clone modal fields {list(modal_data.keys())}"
            )

            if post_clone_data:
                result.append({"action": "update_form", "data": post_clone_data})
                print(
                    f"   🔧 AUTO-FIX: Separated post-clone fields {list(post_clone_data.keys())} after Clone button"
                )

            continue

        result.append(step)
        i += 1

    return result

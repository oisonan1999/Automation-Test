# ai/action_fixer/navigation_fixers.py - split from action_fixer.py
# Navigation path resolution / merge / inject initial navigate
import re
from ._constants import (
    DEPLOYMENT_KEYWORDS,
    PAGE_TAB_NAMES,
    NAVIGATION_PATH_MAP,
    ACTION_NAME_MAP,
    VALID_ACTIONS,
    _VALID_DEPLOY_OPTIONS,
)


def _inject_missing_initial_navigate(plan, user_command=""):
    """
    If plan doesn't start with navigate but command starts with 'Vào X',
    inject navigate(X) at the beginning using NAVIGATION_PATH_MAP.
    Handles label prefixes like "Export the Book CSV. Vào PVE -> ...".
    """
    import re as _re

    if not plan:
        return plan

    # Already starts with navigate — nothing to do
    if plan[0].get("action") == "navigate":
        return plan

    # Extract the first segment (before first "->")
    cmd = (user_command or "").strip()
    first_arrow = cmd.find("->")
    first_segment = cmd[:first_arrow].strip() if first_arrow != -1 else cmd

    # Match "Vào X" anywhere in the first segment
    m = _re.search(r"vào\s+(.+?)$", first_segment, _re.IGNORECASE)
    if not m:
        return plan

    nav_target = m.group(1).strip().rstrip(".,;:")
    nav_key = nav_target.lower()

    if nav_key not in NAVIGATION_PATH_MAP:
        # Try partial key match (e.g. "grab bag v2" → "grab bag")
        for k in sorted(NAVIGATION_PATH_MAP, key=len, reverse=True):
            if k in nav_key:
                nav_key = k
                break
        else:
            return plan

    nav_path = NAVIGATION_PATH_MAP[nav_key]
    print(f"   🔧 INJECT INITIAL NAVIGATE: Plan missing first navigate → {nav_path}")

    nav_step = {"action": "navigate", "path": nav_path, "target": nav_path[-1], "value": ""}
    return [nav_step] + plan




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
        # and use the canonical path from the map. Handles plural/singular mismatches AND
        # depth mismatches (e.g. AI generates ["Data Configs", "Live Events", "Rules Based Event"]
        # but canonical is ["Live Events", "RBE"]).
        if len(path) >= 3:
            last_key = path[-1].strip().lower()
            if last_key in NAVIGATION_PATH_MAP:
                resolved = NAVIGATION_PATH_MAP[last_key]
                current_lower = [p.strip().lower() for p in path]
                resolved_lower = [r.lower() for r in resolved]
                if current_lower != resolved_lower:
                    step["path"] = list(resolved)
                    if "target" in step:
                        del step["target"]
                    print(
                        f"   🗺️  PATH-RESOLVE (canonical fix): {original_path} → {resolved}"
                    )
                    continue

    return plan




def _remove_invalid_navigate_to_tabs(plan):
    """
    Remove (or convert to click) navigate steps that target known in-page tabs/buttons.

    Problem: AI sometimes generates navigate(["Contest Superstars"]) when the user says
    "Bấm vào tab Contest Superstars". "Contest Superstars" is a tab inside the RBE form,
    NOT a sidebar navigation item. The navigator deep-scans the sidebar, fails to find it,
    and crashes/refreshes the page.

    Fix: For each navigate step whose single-element path matches a PAGE_TAB_NAMES entry:
    - If a later click(target=X) already exists → REMOVE the navigate (duplicate)
    - Otherwise → CONVERT to click(target=X) so the action is still performed correctly
    """
    if not plan:
        return plan

    result = []
    for i, step in enumerate(plan):
        if step.get("action") != "navigate":
            result.append(step)
            continue

        path = step.get("path", [])
        if len(path) != 1:
            result.append(step)
            continue

        tab_name = path[0].strip().lower()
        if tab_name not in PAGE_TAB_NAMES:
            result.append(step)
            continue

        original_name = path[0].strip()
        # Check if a click to the same target exists later in the plan
        later_click_exists = any(
            s.get("action") == "click"
            and s.get("target", "").strip().lower() == tab_name
            for s in plan[i + 1 :]
        )

        if later_click_exists:
            print(
                f"   🔧 TAB-NAV-FIX: Removed navigate(['{original_name}']) — "
                f"in-page tab, not a sidebar nav item (later click exists)"
            )
        else:
            result.append({"action": "click", "target": original_name})
            print(
                f"   🔧 TAB-NAV-FIX: Converted navigate(['{original_name}']) → "
                f"click('{original_name}') — in-page tab, not a sidebar nav item"
            )

    return result




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


# Filename-with-extension token, e.g. "Book_test.csv" inside a click target.
_FILENAME_IN_TEXT_RE = re.compile(
    r"\b[\w\-]+\.(?:csv|xlsx|xls|json|txt)\b", re.IGNORECASE
)


def _remove_spurious_instruction_clicks(plan, user_command=""):
    """
    The model sometimes duplicates an import/export instruction into BOTH the
    correct upload/download step AND a bogus click whose target is the raw
    instruction text, e.g. {"action":"click","target":"Import CSV file Book_test.csv"}.
    A real button label never contains a data filename (".csv"/".xlsx"/...), so
    any click target carrying such a filename is the misparsed instruction → drop it.

    Also catches a subtler variant with no filename in the click itself: the
    model echoes an "Export/Import <...qualifier...>" clause almost verbatim as
    a click target, e.g. click("Export Chapter theo BookID") lifted straight out
    of "Export Chapter theo BookID file chapter_test.csv". Real button/tab labels
    in this app are short (1-3 words, e.g. "Import/Export Chapters", "Export CSV");
    a 4+-word target starting with Export/Import that also appears verbatim in the
    command is the instruction text, not a button — drop it. (Seen concretely with
    PVE's "Export Chapter" download, which core.py already handles end-to-end
    internally — see automation/core.py's download dispatcher — so no manual click
    is needed or wanted before it.)
    """
    if not plan or not isinstance(plan, list):
        return plan

    cmd_lower = (user_command or "").lower()
    result = []
    for step in plan:
        if step.get("action") == "click":
            target = str(step.get("target") or "")
            target_lower = target.strip().lower()
            if _FILENAME_IN_TEXT_RE.search(target):
                print(
                    f"   🔧 REMOVE SPURIOUS CLICK: target '{target}' is an "
                    f"import/export instruction, not a button"
                )
                continue
            if (
                target_lower
                and re.match(r"^(export|import)\b", target_lower)
                and len(target_lower.split()) >= 4
                and cmd_lower
                and target_lower in cmd_lower
            ):
                print(
                    f"   🔧 REMOVE SPURIOUS CLICK: target '{target}' is a verbose "
                    f"instruction clause copied verbatim from the command, not a button"
                )
                continue
        result.append(step)
    return result


def _remove_redundant_click_after_navigate(plan):
    """
    Remove a click step that immediately follows a navigate step and targets
    a destination the navigate step already visited (any segment of its path,
    not just the last one).

    Qwen2.5 sometimes duplicates a nav destination as a spurious click:
      navigate(path=["Live Events", "Offer", "Offer Section"])
      click(target="Offer Section")     ← removed: navigator already landed here

    It can also duplicate a MIDDLE segment instead of the final one, e.g.
      navigate(path=["Live Events", "PVE", "Classic PVE"])
      click(target="PVE")               ← also removed: already passed through here

    Only fires when the click target exactly matches one of the nav path's
    segments. Clicks targeting other labels (e.g. "Create New") are untouched.
    """
    if not plan or not isinstance(plan, list):
        return plan

    result = []
    for step in plan:
        if step.get("action") == "click" and result:
            prev = result[-1]
            if prev.get("action") == "navigate":
                nav_path = prev.get("path", [])
                if isinstance(nav_path, list):
                    nav_segments = {str(seg).strip().lower() for seg in nav_path}
                elif isinstance(nav_path, str):
                    nav_segments = {nav_path.strip().lower()}
                else:
                    nav_segments = set()
                click_target = str(step.get("target", "")).strip().lower()
                if click_target and click_target in nav_segments:
                    print(
                        f"   🔧 REMOVE REDUNDANT CLICK: click('{step.get('target')}') "
                        f"duplicates a segment navigate already visited — removed"
                    )
                    continue
        result.append(step)
    return result


def _fix_post_deployment_missing_navigate(plan, user_command=""):
    """
    Pattern A: process_deployment → update_form({"ID contains": X})  [no navigate between]
    Pattern B: process_deployment → edit_row/clone_row(X)            [no navigate between]

    AI sometimes skips the "Vào X" navigate step after a logo click when moving
    to the next feature in a multi-feature command (e.g. FCV3 -> logo -> RBE).
    It either (a) generates a filter update_form as if searching for the row, or
    (b) jumps straight to edit_row/clone_row on the next feature's ID, and in
    both cases often also stuffs the next feature's name into the logo's
    process_deployment options as if it were a deploy checkbox. This fixer:
      1. Clears spurious options from the process_deployment (intermediate logo = no deploy)
      2. Injects navigate (from user_command: "Vào X" after each logo marker)
      3. Converts update_form({"ID contains": X}) → edit_row(X) (pattern A only)

    Also handles optional wait steps between process_deployment and the next step.
    """
    import re as _re

    # Extract "Vào X" targets after each logo marker in the user command
    logo_re = _re.compile(
        r"b[aấ]m\s+v[aà]o\s+logo|click\s+logo|logo\s+the\s+brick|b[aấ]m\s+logo",
        _re.IGNORECASE,
    )
    vao_re = _re.compile(r"[>\-]+\s*v[aà]o\s+([\w\s]+?)(?:\s*->|\s*$)", _re.IGNORECASE)

    nav_targets_after_logo = []
    for m in logo_re.finditer(user_command):
        snippet = user_command[m.end() : m.end() + 150]
        vm = vao_re.search(snippet)
        nav_targets_after_logo.append(vm.group(1).strip() if vm else None)

    if not nav_targets_after_logo:
        return plan

    result = []
    i = 0
    logo_count = 0

    while i < len(plan):
        step = plan[i]

        if step.get("action") == "process_deployment":
            # Collect any wait steps that immediately follow
            waits = []
            j = i + 1
            while j < len(plan) and plan[j].get("action") == "wait":
                waits.append(plan[j])
                j += 1

            # Check if next non-wait step is update_form({"ID contains": X})
            # (pattern A) or an edit_row/clone_row already targeting the next
            # feature's ID but missing the navigate before it (pattern B).
            next_step = plan[j] if j < len(plan) else None
            is_misplaced_filter = (
                next_step is not None
                and next_step.get("action") == "update_form"
                and isinstance(next_step.get("data"), dict)
                and list(next_step["data"].keys()) == ["ID contains"]
            )
            is_missing_nav_before_edit = (
                next_step is not None
                and next_step.get("action") in ("edit_row", "clone_row")
            )

            nav_target = (
                nav_targets_after_logo[logo_count]
                if logo_count < len(nav_targets_after_logo)
                else None
            )

            if nav_target and (is_misplaced_filter or is_missing_nav_before_edit):
                # 1. Clear spurious options — an intermediate logo before the
                # next feature's "Vào X" is never a real deploy checkpoint,
                # even if the AI stuffed feature names into options.
                if step.get("options"):
                    print(
                        f"   🔧 POST-DEPLOY: Cleared options {step['options']} → [] "
                        f"(intermediate logo before 'Vào {nav_target}')"
                    )
                    step = dict(step)
                    step["options"] = []
                result.append(step)

                # 2. Re-emit any wait steps that were before the next step
                result.extend(waits)

                # 3. Inject navigate
                nav_lower = nav_target.strip().lower()
                nav_path = NAVIGATION_PATH_MAP.get(nav_lower, [nav_target])
                result.append({"action": "navigate", "path": nav_path})
                print(
                    f"   🔧 POST-DEPLOY: Injected navigate({nav_path}) "
                    f"from command 'Vào {nav_target}'"
                )

                if is_misplaced_filter:
                    # 4a. Convert update_form({"ID contains": X}) → edit_row(X)
                    id_value = next_step["data"]["ID contains"]
                    edit_target = id_value if id_value and id_value.upper() != "RANDOM" else "RANDOM"
                    result.append({"action": "edit_row", "target": edit_target})
                    print(
                        f"   🔧 POST-DEPLOY: Converted update_form(ID contains) → "
                        f"edit_row('{edit_target}')"
                    )
                    i = j + 1  # Skip both waits (already added) and the update_form
                else:
                    # 4b. next_step is already edit_row/clone_row with the right
                    # target — leave it as-is, it'll be appended on the next
                    # loop iteration right after the injected navigate.
                    i = j

                logo_count += 1
                continue

            logo_count += 1

        result.append(step)
        i += 1

    return result


def _remove_redundant_duplicate_navigate(plan):
    """
    Drop a navigate step whose path duplicates an EARLIER navigate already in the
    plan when nothing in between left that page (no edit_row/clone_row). The model
    occasionally re-navigates to the same list page mid-flow (e.g. after an
    upload), which reloads the page and can discard the just-done action.

    A navigate IS kept if an edit_row/clone_row occurred since the last navigate
    to that path — that flow legitimately returns to the list view.
    """
    if not plan or not isinstance(plan, list):
        return plan

    def _path_key(step):
        path = step.get("path")
        if isinstance(path, list):
            segs = path
        elif isinstance(path, str):
            segs = [path]
        else:
            segs = [step.get("target", "")]
        return tuple(str(s).strip().lower() for s in segs if str(s).strip())

    result = []
    seen_paths = set()
    left_page_since_nav = False  # an edit_row/clone_row happened after last nav
    for step in plan:
        action = step.get("action")
        if action == "navigate":
            key = _path_key(step)
            if key and key in seen_paths and not left_page_since_nav:
                print(
                    f"   🔧 REMOVE REDUNDANT NAVIGATE: already on path {list(key)}"
                )
                continue
            seen_paths.add(key)
            left_page_since_nav = False
        elif action in ("edit_row", "clone_row"):
            left_page_since_nav = True
        result.append(step)
    return result



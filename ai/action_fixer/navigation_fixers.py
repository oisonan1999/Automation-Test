# ai/action_fixer/navigation_fixers.py - split from action_fixer.py
# Navigation path resolution / merge / inject initial navigate
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



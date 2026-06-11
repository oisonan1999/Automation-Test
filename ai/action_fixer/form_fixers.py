# ai/action_fixer/form_fixers.py - split from action_fixer.py
# Form step merges: update+save, PVE CSS update
from ._constants import (
    DEPLOYMENT_KEYWORDS,
    PAGE_TAB_NAMES,
    NAVIGATION_PATH_MAP,
    ACTION_NAME_MAP,
    VALID_ACTIONS,
    _VALID_DEPLOY_OPTIONS,
)


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




def _fix_rbe_type_modal_continue(plan):
    """
    Replace save_form that follows a Radio-only update_form with click("Continue").

    Pattern AI generates (wrong):
        click("New Rules Based Event") → update_form({"Radio: Solo": "select"}) → save_form

    Correct (the modal has a "Continue" button, not Save):
        click("New Rules Based Event") → update_form({"Radio: Solo": "select"}) → click("Continue")

    Detection: update_form whose ALL data keys start with "Radio:" or whose values are
    "select"/"on", immediately followed by save_form with no mode or mode="save".
    """
    if not plan or len(plan) < 2:
        return plan

    result = []
    i = 0
    while i < len(plan):
        step = plan[i]
        if (
            step.get("action") == "update_form"
            and isinstance(step.get("data"), dict)
            and len(step["data"]) > 0
            and all(str(k).strip().lower().startswith("radio:") for k in step["data"].keys())
            and i + 1 < len(plan)
            and plan[i + 1].get("action") == "save_form"
            and plan[i + 1].get("mode", "save") in ("save", None, "")
        ):
            result.append(step)
            result.append({"action": "click", "target": "Continue"})
            print(
                f"   🔧 RBE-MODAL: Replaced save_form → click('Continue') after Radio-only update_form"
            )
            i += 2  # skip both update_form and save_form
        else:
            result.append(step)
            i += 1

    return result


def _fix_offer_filter_field(plan):
    """
    Normalize every page-filter field name to the canonical "ID contains".

    EVERY filter page in the Brick UI (Offer, Offer Section, Drip Offer, PVE,
    RBE, Gacha, Currency, ...) uses the SAME "ID contains" search box. The AI
    (and older prompt rules) sometimes emit per-page labels like "Offer Name",
    "Offer ID", "Section ID", etc. for a "Filter ... bất kỳ" command. Those
    labels don't exist on the page → field not found.

    Detection is value-based (the filter sentinel "RANDOM") so we never touch
    real multi-value filters like Boost Result Value2 = "Red".
    """
    _MISNAMED_FILTER_KEYS = {
        "offer name",
        "offer id",
        "section id",
        "section name",
        "id",
        "name",
        "id filter",
        "filter id",
        "search id",
    }

    result = []
    for step in plan:
        if (
            step.get("action") == "update_form"
            and isinstance(step.get("data"), dict)
            and len(step["data"]) == 1
        ):
            (k, v), = step["data"].items()
            is_filter_sentinel = str(v).strip().upper() == "RANDOM"
            needs_rename = k != "ID contains" and (
                is_filter_sentinel or k.lower().strip() in _MISNAMED_FILTER_KEYS
            )
            if needs_rename:
                print(
                    f"   🔧 FILTER-FIELD: Normalized '{k}' → 'ID contains' "
                    f"(all filter pages use the same search box)"
                )
                result.append({"action": "update_form", "data": {"ID contains": v}})
                continue
        result.append(step)

    return result


def _merge_pve_css_update_steps(plan):
    """
    Merge consecutive update_form steps where the first contains 'Contest Superstar'
    and the next contains CSS panel fields (Normal Node 1, Hard Node 1, Hell Node 1,
    RBE, SoftCurrency).

    Problem: AI splits PVE CSS setup into two separate update_form steps:
      Step 1: update_form({'Contest Superstar': 'on'})  <- triggers special-case, no panel data
      Step 2: update_form({'RBE': ..., 'Normal Node 1': ..., 'SoftCurrency': ...})
              <- does NOT trigger special-case -> generic finder fails (0 visible labels)

    Fix: Merge into one step so the special-case handler processes toggle + panel data together.
    """
    import re

    _CSS_PANEL_KEY_RE = re.compile(
        r"(normal|hard|hell)\s*node\s*1|^rbe$|\brbe\b|soft.?currency",
        re.IGNORECASE,
    )

    merged = []
    i = 0
    while i < len(plan):
        step = plan[i]
        if (
            step.get("action") == "update_form"
            and isinstance(step.get("data"), dict)
            and any(
                "contest superstar" in str(k).lower() for k in step["data"].keys()
            )
        ):
            combined_data = dict(step["data"])
            merged_any = False
            j = i + 1
            # Skip over bare wait steps (no data)
            while j < len(plan) and plan[j].get("action") == "wait" and not plan[j].get("data"):
                j += 1
            if j < len(plan) and plan[j].get("action") == "update_form":
                nxt_data = plan[j].get("data") or {}
                has_panel_keys = any(
                    _CSS_PANEL_KEY_RE.search(str(k)) for k in nxt_data.keys()
                )
                if has_panel_keys:
                    combined_data.update(nxt_data)
                    merged_any = True
                    j += 1

            if merged_any:
                print(
                    f"   🔧 MERGE PVE-CSS: Combined 'Contest Superstar' toggle + panel data "
                    f"into one update_form (keys: {list(combined_data.keys())})"
                )
                merged.append({"action": "update_form", "data": combined_data})
                i = j
            else:
                merged.append(step)
                i += 1
        else:
            merged.append(step)
            i += 1

    return merged



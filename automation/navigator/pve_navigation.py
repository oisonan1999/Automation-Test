# automation/navigator/pve_navigation.py - split from navigator.py
# Special: expand PVE accordion via aria-controls
import time
import re
from playwright.sync_api import Page


class PveNavigationMixin:
    """Special: expand PVE accordion via aria-controls"""

    def _try_expand_pve_section(self, page, target_text):
        """
        PVE accordion expander (Chapter Info / Normal Matches / Match panels)
        - Ưu tiên click icon caret/chevron trong header để mở section.
        - Fallback: click chính header container.
        """
        try:
            if not target_text:
                return False

            target = str(target_text).strip()
            target_lower = target.lower()

            # Only handle known PVE collapsibles to avoid side-effects
            is_section = any(
                k in target_lower for k in ["chapter info", "normal matches"]
            )
            is_match_panel = "match" in target_lower  # e.g. "Match 1 !NAME..."
            if not (is_section or is_match_panel):
                return False

            # Regex:
            # - Chapter/Normal: match exact-ish
            # - Match: match contains "Match" (but tighten for "Match 1/2/3..." to avoid
            #   expanding "Match Settings" or other match-related panels)
            match_num = None
            if is_match_panel:
                m = re.search(r"match\s*(\d+)", target_lower, re.IGNORECASE)
                if m:
                    match_num = m.group(1)

            if "chapter info" in target_lower:
                header_re = re.compile(r"chapter\s*info", re.IGNORECASE)
            elif "normal matches" in target_lower:
                header_re = re.compile(r"normal\s*matches", re.IGNORECASE)
            else:
                if match_num is not None:
                    # Avoid strict \b boundaries: Match header text may contain punctuation/newlines (e.g. "Match 1 !!NAME...")
                    header_re = re.compile(rf"match\s*{match_num}", re.IGNORECASE)
                else:
                    header_re = re.compile(r"match", re.IGNORECASE)

            # Candidate headers: containers that contain the text
            candidates = page.locator(
                "header, div, section, fieldset, .panel, .card, [role='tab']"
            ).filter(has_text=header_re)

            count = candidates.count()
            if count <= 0:
                return False

            # Check a few candidates (topmost/closest first usually enough)
            for i in range(min(count, 8)):
                header = candidates.nth(i)
                if not header.is_visible():
                    continue

                # 1) If aria-expanded exists on header or descendant, use it to decide click
                expanded_attr = None
                try:
                    expanded_attr = header.get_attribute("aria-expanded")
                except:
                    expanded_attr = None

                caret_clicked = False

                # 2) Prefer deterministic toggle button (aria-controls / aria-expanded)
                #    Example Normal Matches header (from your HTML):
                #    <button ... aria-expanded="false" aria-controls="match-mode-...">...</button>
                try:
                    toggle_btn = None
                    try:
                        # Normal Matches header in your HTML:
                        # <button ... class="btn-collapse-open not-collapsed"
                        #   aria-expanded="false" aria-controls="match-mode-1-...">...</button>
                        # -> For "normal matches" we MUST click the right-side collapse-open button
                        #    whose aria-controls starts with "match-mode-".
                        if "normal matches" in target_lower:
                            toggle_selector = (
                                "button[aria-controls^='match-mode-'][aria-expanded]"
                            )
                        elif is_match_panel and match_num is not None:
                            # Match panel expander HTML (from user):
                            # <button ... aria-expanded="false" aria-controls="chapter-match-...">
                            # In PVE, match panels use aria-controls="chapter-match-...", not "match-mode-...".
                            # So select by aria-controls contains chapter-match-.
                            toggle_selector = (
                                "button[aria-expanded][aria-controls*='chapter-match-']"
                            )
                        else:
                            toggle_selector = "button[aria-controls][aria-expanded], button[aria-expanded]"

                        toggle_btn = header.locator(toggle_selector).first
                    except:
                        toggle_btn = None

                    if (
                        toggle_btn
                        and toggle_btn.count() > 0
                        and toggle_btn.is_visible()
                    ):
                        try:
                            ea = toggle_btn.get_attribute("aria-expanded")
                        except:
                            ea = None

                        if ea is None or str(ea).lower() in ("false", "0", "no"):
                            toggle_btn.click(force=True)
                            caret_clicked = True
                        else:
                            # Already expanded
                            return True
                except:
                    caret_clicked = False

                # 3) Fallback to caret/chevron/icon heuristic if toggle button not found
                if not caret_clicked:
                    try:
                        caret_control = (
                            header.locator("button, a, span, div")
                            .filter(
                                has=page.locator(
                                    "i[class*='chevron'], i[class*='caret'], i[class*='fa-'], svg[class*='chevron'], svg[class*='caret'], svg[class*='fa-'], [class*='chevron'], [class*='caret']"
                                )
                            )
                            .first
                        )

                        if caret_control.count() > 0 and caret_control.is_visible():
                            caret_expanded = None
                            try:
                                caret_expanded = caret_control.get_attribute(
                                    "aria-expanded"
                                )
                            except:
                                caret_expanded = None

                            effective_expanded = (
                                caret_expanded
                                if caret_expanded is not None
                                else expanded_attr
                            )

                            if effective_expanded is None or str(
                                effective_expanded
                            ).lower() in ("false", "0", "no"):
                                caret_control.click(force=True)
                                caret_clicked = True
                            else:
                                return True
                    except:
                        caret_clicked = False

                # 3) If no caret_control clicked, try aria-expanded descendant
                if not caret_clicked:
                    try:
                        btn_expanded = header.locator("[aria-expanded]").first
                        if btn_expanded.count() > 0 and btn_expanded.is_visible():
                            ea = btn_expanded.get_attribute("aria-expanded")
                            if ea is None or str(ea).lower() in ("false", "0", "no"):
                                btn_expanded.click(force=True)
                                caret_clicked = True
                            else:
                                return True
                    except:
                        pass

                # 4) Fallback: click header itself
                if not caret_clicked:
                    try:
                        header.click(force=True)
                        caret_clicked = True
                    except:
                        caret_clicked = False

                if caret_clicked:
                    time.sleep(0.6)
                    try:
                        self._wait_for_long_loading(page)
                    except:
                        pass

                    # Verify that the panel actually expanded (prefer aria-controls visibility).
                    try:
                        # find the toggle button under header that controls the panel
                        toggle_btn = None
                        try:
                            toggle_btn = header.locator(
                                "button[aria-controls], [role='button'][aria-controls]"
                            ).first
                        except:
                            toggle_btn = None

                        aria_controls = None
                        if toggle_btn and toggle_btn.count() > 0:
                            try:
                                aria_controls = toggle_btn.get_attribute(
                                    "aria-controls"
                                )
                            except:
                                aria_controls = None

                        if aria_controls:
                            panel = page.locator(f"#{aria_controls}")
                            # Wait a bit for DOM visibility (PVE accordion can be slow)
                            try:
                                panel.wait_for(state="visible", timeout=5000)
                            except:
                                panel.wait_for(state="visible", timeout=15000)

                            # Strong verify:
                            # - Normal Matches: must expose Match 1 inside this panel.
                            # - Match N: must expose at least one select2 SSDB search input inside this panel.
                            try:
                                if "normal matches" in target_lower:
                                    match1_in_panel = panel.locator(
                                        "text=Match 1"
                                    ).first
                                    match1_in_panel.wait_for(
                                        state="visible", timeout=8000
                                    )
                                    return True

                                if is_match_panel:
                                    # Match panel render may be slower; accept several stable signals.
                                    # 1) "Match Type" appears in expanded Match settings
                                    # 2) SSDB select2 search input becomes visible
                                    # 3) SSGroup ID label/text appears
                                    try:
                                        match_type = panel.locator(
                                            "text=Match Type"
                                        ).first
                                        match_type.wait_for(
                                            state="visible", timeout=8000
                                        )
                                        return True
                                    except:
                                        pass

                                    try:
                                        ssdb_in_panel = panel.locator(
                                            "input.select2-search__field:visible"
                                        ).first
                                        ssdb_in_panel.wait_for(
                                            state="visible", timeout=8000
                                        )
                                        return True
                                    except:
                                        pass

                                    try:
                                        ssgrp_in_panel = panel.locator(
                                            "text=SSGroup ID"
                                        ).first
                                        if ssgrp_in_panel.count() > 0:
                                            ssgrp_in_panel.wait_for(
                                                state="visible", timeout=2000
                                            )
                                            return True
                                    except:
                                        pass
                            except:
                                pass

                            # fallback: check aria-expanded state directly on the toggle button
                            try:
                                if toggle_btn and toggle_btn.count() > 0:
                                    ea_now = toggle_btn.get_attribute("aria-expanded")
                                    if ea_now and str(ea_now).lower() == "true":
                                        return True
                            except:
                                pass

                            # fallback: check aria-expanded became true somewhere under header
                            try:
                                expanded_now = (
                                    header.locator("[aria-expanded='true']").count() > 0
                                )
                                if expanded_now:
                                    return True
                            except:
                                pass

                        # If still not sure, apply lightweight content checks.
                        if "normal matches" in target_lower:
                            match_re = re.compile(r"Match\s*\d+", re.IGNORECASE)
                            all_matches = page.get_by_text(match_re).all()
                            visible_count = sum(
                                1 for el in all_matches if el.is_visible()
                            )
                            if visible_count >= 1:
                                return True

                        if is_match_panel:
                            ssdb_inp = page.locator(
                                "input.select2-search__field:visible"
                            ).first
                            if ssdb_inp.count() > 0 and ssdb_inp.is_visible():
                                return True

                            ssgrp = page.locator("text=SSGroup ID").first
                            if ssgrp.count() > 0 and ssgrp.is_visible():
                                return True
                    except Exception:
                        pass

        except Exception as e:
            print(f"         ⚠️ _try_expand_pve_section error: {e}")
        return False


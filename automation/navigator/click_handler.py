# automation/navigator/click_handler.py - split from navigator.py
# smart_click: multi-strategy element click
import time
import re
from playwright.sync_api import Page


class ClickHandlerMixin:
    """smart_click: multi-strategy element click"""

    def smart_click(self, page, target_text):
        print(f"      🖱 Smart Click: '{target_text}'")
        target_clean = target_text.strip()
        # AI sometimes echoes the Vietnamese "Bấm vào tab X" phrasing literally into
        # the click target (e.g. "tab PVE" instead of "PVE"). Real UI tab/sidebar
        # elements are never labeled "Tab X" (just "X"), and every matching strategy
        # below searches by substring-in-element-text — a stray "tab " prefix means
        # NONE of them can ever match, since the rendered element text lacks the
        # word "tab" entirely. Strip it up front so every strategy still works.
        target_clean = re.sub(r"^tab\s+", "", target_clean, flags=re.IGNORECASE).strip()
        clicked = False

        # Early-exit: "Filter Data" / "Filter" button — click the page-level Filter button
        # directly instead of running through all strategies.
        if re.fullmatch(r"filter\s*(data)?", target_clean, re.IGNORECASE):
            for _fsel in [
                "button#btn-filter",
                "button:has-text('Filter')",
                "a.btn:has-text('Filter')",
                "input[type='submit'][value*='ilter']",
                "button[type='submit']",
            ]:
                try:
                    _fb = page.locator(_fsel).first
                    if _fb.count() > 0 and _fb.is_visible():
                        _fb.click()
                        print(f"         ✅ Filter button clicked via '{_fsel}'")
                        self._wait_for_long_loading(page)
                        # Settle buffer: the loading spinner clears as soon as the
                        # filter XHR resolves, but the table's row/cell content
                        # (especially far-down rows) can still be mid-render for a
                        # beat after that — a subsequent action (e.g. random
                        # checkbox selection) can hit a <tr> with 0 populated <td>
                        # cells if it queries too early. 2s covers the observed gap.
                        time.sleep(2)
                        return True
                except Exception:
                    continue
            # Last resort: press Enter in the visible search input
            try:
                _inp = page.locator("input[type='text']:visible, input[type='search']:visible").first
                if _inp.count() > 0 and _inp.is_visible():
                    _inp.press("Enter")
                    print(f"         ✅ Filter fallback: pressed Enter in search input")
                    time.sleep(2)
                    self._wait_for_long_loading(page)
                    return True
            except Exception:
                pass

        # RBE UI timing guard:
        # "Contest Superstars" thường nằm trong accordion "Wrapper" và có thể chưa render kịp
        # khi smart_click bắt đầu quét. Thêm 1 đoạn chờ ngắn để tránh FAIL timing.
        # PVE/Classic PVE accordion expansion attempt first.
        # (Classic PVE is often inside a collapsed accordion; if we don't expand,
        # smart_click('Classic PVE') will fail and abort the navigation chain.)
        try:
            t_lower = target_clean.lower()
            if "classic pve" in t_lower or t_lower.strip() == "pve":
                pve_hdr_re = re.compile(r"\bpve\b", re.IGNORECASE)
                hdrs = page.locator(
                    "header, div, section, fieldset, .panel, .card"
                ).filter(has_text=pve_hdr_re)
                for i in range(min(hdrs.count(), 10)):
                    hdr = hdrs.nth(i)
                    if not hdr.is_visible():
                        continue
                    # prefer explicit aria-expanded=false toggle button if present
                    toggle_btn = None
                    try:
                        toggle_btn = hdr.locator(
                            "button[aria-expanded], [role='button'][aria-expanded]"
                        ).first
                    except:
                        toggle_btn = None

                    if toggle_btn and toggle_btn.count() > 0:
                        try:
                            ea = toggle_btn.get_attribute("aria-expanded")
                        except:
                            ea = None
                        if ea is None or str(ea).lower() in ("false", "0", "no"):
                            toggle_btn.click(force=True)
                            time.sleep(1.0)

                            # also try caret/chevron icon inside header
                            try:
                                caret = hdr.locator(
                                    "i[class*='chevron'], i[class*='caret'], [class*='chevron'], [class*='caret'], svg[class*='chevron'], svg[class*='caret']"
                                ).first
                                if caret.count() > 0 and caret.is_visible():
                                    caret.click(force=True)
                                    time.sleep(0.6)
                            except:
                                pass

                            break
                    else:
                        # fallback: click header itself once
                        try:
                            hdr.click(force=True)
                            time.sleep(0.8)
                            break
                        except:
                            pass
        except:
            pass

        # PVE accordion expansion attempt for known PVE sections (Chapter Info / Normal Matches / Match panels)
        try:
            if self._try_expand_pve_section(page, target_clean):
                return True
        except:
            pass

        try:
            t = target_clean.lower()
            if ("contest superstars" in t) or (t.strip() == "contest superstars"):
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=2000)
                except:
                    pass
                time.sleep(1.2)
                self._wait_for_long_loading(page)
        except:
            pass

        # RBE/Contest UI timing guard: “PVP” tab may appear after “Contest Superstars” click + panel load.
        # Add a targeted “PVP” click before generic sidebar fallback (to avoid early FAIL).
        #
        # Modal-scoped click: when "Define Schedules" opens a dialog, "Add Schedule" button
        # may not exist at page level (only inside dialog).
        try:
            if "add schedule" in target_clean.lower():
                add_sched_re = re.compile(r"Add\s*Schedule", re.IGNORECASE)

                modal_scope = page.locator(
                    ".modal.show, .modal.in, [role='dialog']:visible, .swal2-popup:visible"
                ).first

                # Prefer dialog-local search if any modal is open
                if modal_scope.count() > 0 and modal_scope.is_visible():
                    btn = (
                        modal_scope.locator("button, a, [role='button']")
                        .filter(has_text=add_sched_re)
                        .first
                    )
                    if btn.count() > 0 and btn.is_visible():
                        print("         🎯 Modal-scoped click: 'Add Schedule'")
                        btn.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        btn.click(force=True)
                        self._wait_for_long_loading(page)
                        return True

                # Fallback to global search (in case dialog isn't marked .show)
                btn2 = (
                    page.locator("button, a, [role='button']")
                    .filter(has_text=add_sched_re)
                    .first
                )
                if btn2.count() > 0 and btn2.is_visible():
                    print("         🎯 Global click fallback: 'Add Schedule'")
                    btn2.scroll_into_view_if_needed()
                    time.sleep(0.2)
                    btn2.click(force=True)
                    self._wait_for_long_loading(page)
                    return True
        except Exception as _add_sched_e:
            print(
                f"         ⚠️ Modal-scoped 'Add Schedule' click failed: {_add_sched_e}"
            )

        try:
            if target_clean.lower().strip() == "pvp":
                time.sleep(0.8)
                pvp_re = re.compile(r"^\s*pvp\s*$", re.IGNORECASE)
                candidates = page.locator(
                    "button, a, li, span, div[role='button'], .nav-link, .nav-tabs .nav-link, [role='tab']"
                ).filter(has_text=pvp_re)
                if candidates.count() > 0:
                    for i in range(min(candidates.count(), 6)):
                        cand = candidates.nth(i)
                        if cand.is_visible():
                            print("         🎯 PVP targeted click (exact)")
                            cand.scroll_into_view_if_needed()
                            time.sleep(0.2)
                            cand.click(force=True)
                            self._wait_for_long_loading(page)
                            return True

                # Fallback: contains match (handles line breaks / extra text)
                candidates2 = page.locator(
                    "button, a, li, span, div[role='button'], .nav-link, .nav-tabs .nav-link, [role='tab']"
                ).filter(has_text=re.compile(r"pvp", re.IGNORECASE))
                for i in range(min(candidates2.count(), 6)):
                    cand = candidates2.nth(i)
                    if cand.is_visible():
                        print("         🎯 PVP targeted click (contains)")
                        cand.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        cand.click(force=True)
                        self._wait_for_long_loading(page)
                        return True
        except Exception as _pvp_e:
            print(f"         ⚠️ PVP targeted click error: {_pvp_e}")

        # Special reliable retry for "Add Event" (often appears after selecting a tab)
        try:
            if "add event" in target_clean.lower():
                # Primary + fallback patterns (UI may render "Add" and "Event" with extra spacing/newlines)
                add_event_re = re.compile(r"Add\s*Event", re.IGNORECASE)
                add_event_re_fallback = re.compile(
                    r"(Add.*Event|Event.*Add)", re.IGNORECASE
                )

                # Search in likely active contexts first, then global.
                add_event_containers = [
                    ".modal.show",
                    ".modal.in",
                    "[role='dialog']:visible",
                    ".swal2-popup:visible",
                    ".tab-pane.active",
                    ".tab-content .active",
                    "main",
                    "body",
                ]

                # Retry loop (UI may render after animation / load)
                for _ in range(16):
                    try:
                        # 1) Context-aware candidates
                        for csel in add_event_containers:
                            container = page.locator(csel).first
                            if container.count() == 0 or not container.is_visible():
                                continue

                            candidates = container.locator(
                                "button, a, div[role='button'], span[role='button'], li"
                            ).filter(has_text=add_event_re)

                            if candidates.count() > 0:
                                for i in range(min(candidates.count(), 8)):
                                    cand = candidates.nth(i)
                                    if cand.is_visible():
                                        print(
                                            "         🔁 Retry-click 'Add Event' (active container candidates)"
                                        )
                                        cand.scroll_into_view_if_needed()
                                        time.sleep(0.2)
                                        cand.click(force=True)
                                        self._wait_for_long_loading(page)
                                        return True

                        # 2) Global candidates fallback (text + aria/title heuristics)
                        # Some UIs render "Add Event" as icon-only button with aria-label/title,
                        # so we also try a JS-based click by (add && event) tokens.
                        try:
                            js_clicked = page.evaluate("""
() => {
  const els = Array.from(
    document.querySelectorAll("button, a, [role='button'], li")
  );
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const tokenOk = (text) => {
    const t = (text || "").toLowerCase();
    return t.includes("add") && t.includes("event");
  };

  for (const el of els) {
    try {
      const t =
        (el.innerText || "") +
        " " +
        (el.getAttribute("aria-label") || "") +
        " " +
        (el.getAttribute("title") || "");
      if (tokenOk(t) && visible(el)) {
        el.click();
        return true;
      }
    } catch (e) {}
  }
  return false;
}
""")
                            if js_clicked:
                                print(
                                    "         🔁 Retry-click 'Add Event' (JS add+event heuristic)"
                                )
                                self._wait_for_long_loading(page)
                                return True
                        except:
                            pass

                        global_candidates = page.locator(
                            "button, a, div[role='button'], span[role='button'], li"
                        ).filter(has_text=add_event_re)
                        if global_candidates.count() > 0:
                            for i in range(min(global_candidates.count(), 6)):
                                cand = global_candidates.nth(i)
                                if cand.is_visible():
                                    print(
                                        "         🔁 Retry-click 'Add Event' (global fallback)"
                                    )
                                    cand.scroll_into_view_if_needed()
                                    time.sleep(0.2)
                                    cand.click(force=True)
                                    self._wait_for_long_loading(page)
                                    return True
                    except:
                        pass

                    # 3) Final JS sweep (whole page, split text / icon-only / aria-label cases)
                    # Click the first visible element whose normalized text/aria/title contains BOTH "add" and "event".
                    try:
                        js_clicked2 = page.evaluate("""
() => {
  const tokens = ["add", "event"];
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const normalize = (s) => (s || "").toString().toLowerCase().replace(/\\s+/g," ").trim();

  const els = Array.from(document.querySelectorAll("*"));
  for (const el of els) {
    try {
      if (!visible(el)) continue;
      const txt =
        normalize(el.innerText) + " " +
        normalize(el.getAttribute("aria-label")) + " " +
        normalize(el.getAttribute("title"));
      const ok = tokens.every(t => txt.includes(t));
      if (ok) {
        el.click();
        return true;
      }
    } catch (e) {}
  }
  return false;
}
""")
                        if js_clicked2:
                            print(
                                "         🔁 Retry-click 'Add Event' (final JS sweep add+event)"
                            )
                            self._wait_for_long_loading(page)
                            return True
                    except Exception:
                        pass

                    time.sleep(0.4)
        except:
            pass

        # RBE UI: "Contest Superstars" thường nằm trong accordion "Wrapper".
        # Nếu accordion đang collapsed thì phần tử bị ẩn và smart_click không tìm thấy.
        # Try-expand một lần để đảm bảo target có thể visible trước khi click.
        try:
            t = target_clean.lower()
            if t in ("contest superstars", "feeder event") or "contest superstars" in t:
                wrapper_candidates = page.locator(
                    "aside a, #sidebar a, .sidebar a, #left-menu a, "
                    "aside div, #sidebar div, .sidebar div, #left-menu div, "
                    "aside span, #sidebar span, .sidebar span, #left-menu span, "
                    "#left-menu, .sidebar"
                ).filter(has_text=re.compile(r"\bWrapper\b", re.IGNORECASE))

                # Prefer the most "clickable" candidate first
                wrapper_toggle = wrapper_candidates.first
                if wrapper_toggle.count() > 0 and wrapper_toggle.is_visible():
                    print("         🔽 Pre-expand: 'Wrapper' accordion")
                    wrapper_toggle.click(force=True)
                    time.sleep(1.2)

                # If wrapper exists but isn't visible yet, force-click it to expand.
                # NOTE: Do NOT click generic 'text=Wrapper' because it can select the
                # "Wrapper" tab/section (wrong navigation). We only want to expand accordion.
                if wrapper_toggle.count() > 0 and not wrapper_toggle.is_visible():
                    try:
                        print(
                            "         🔽 Pre-expand fallback: force click 'Wrapper' accordion"
                        )
                        wrapper_toggle.click(force=True)
                        time.sleep(1.2)
                    except Exception:
                        pass

                # Targeted DOM search inside Wrapper/sidebar region (more reliable than generic sidebar scan)
                clicked_inside = False
                try:
                    # Be flexible: UI text can include line breaks/spaces, so don't anchor to full-string match.
                    contest_re = re.compile(r"Contest\s*Superstars", re.IGNORECASE)
                    targeted = (
                        page.locator(".sidebar, #left-menu, aside")
                        .locator(
                            "a, button, li, span, div[role='button'], div.menu-item"
                        )
                        .filter(has_text=contest_re)
                    )

                    # Priority: click only items whose *own* text is exactly "Contest Superstars"
                    # (after normalizing whitespace). This avoids clicking accordion/container
                    # elements that merely contain descendant text.
                    contest_exact_re = re.compile(
                        r"^\s*Contest\s*Superstars\s*$", re.IGNORECASE
                    )

                    if targeted.count() > 0:
                        # Click first visible exact match
                        clicked = False
                        for i in range(min(targeted.count(), 8)):
                            cand = targeted.nth(i)
                            if not cand.is_visible():
                                continue

                            try:
                                cand_text = cand.inner_text() or ""
                                cand_norm = re.sub(r"\s+", " ", cand_text).strip()
                            except:
                                cand_norm = ""

                            # Skip obvious wrapper header/container
                            if re.search(r"\bWrapper\b", cand_norm, re.IGNORECASE):
                                continue

                            if contest_exact_re.match(cand_norm):
                                print(
                                    "         🎯 Targeted click (exact): 'Contest Superstars' (inside Wrapper/sidebar)"
                                )
                                cand.scroll_into_view_if_needed()
                                time.sleep(0.2)
                                cand.click(force=True)

                                # Verify selection didn't just stop at Wrapper header
                                time.sleep(1.0)
                                try:
                                    is_active = page.evaluate("""
() => {
  const norm = (s) => (s || "").toString().replace(/\\s+/g," ").trim().toLowerCase();
  const isActiveClass = (el) => {
    const cls = (el && el.className ? el.className : "").toString().toLowerCase();
    return cls.includes('active') || cls.includes('selected') || cls.includes('current');
  };
  const root = document.querySelector('.sidebar, #left-menu, aside') || document.body;
  const els = Array.from(root.querySelectorAll('a, button, li, span, div, [role="button"], .menu-item'));
  const target = 'contest superstars';
  for (const el of els) {
    try {
      const t = norm(el.innerText);
      if (t === target && el.offsetParent !== null && isActiveClass(el)) return true;
    } catch(e) {}
  }
  return false;
}
""")
                                except:
                                    is_active = True  # nếu JS detect fail thì coi như ok để không kẹt

                                if is_active:
                                    self._wait_for_long_loading(page)
                                    clicked = True
                                    return True
                                else:
                                    print(
                                        "         ⚠️ 'Contest Superstars' click did not become active; retrying..."
                                    )
                                    clicked = True
                                    # continue trying other candidates in this loop
                                    continue

                        # Fallback (if exact match fails): click first visible candidate whose text contains contest
                        if not clicked:
                            for i in range(min(targeted.count(), 8)):
                                cand = targeted.nth(i)
                                if not cand.is_visible():
                                    continue
                                try:
                                    cand_text = cand.inner_text() or ""
                                    cand_norm = re.sub(r"\s+", " ", cand_text).strip()
                                except:
                                    cand_norm = ""
                                if re.search(
                                    r"Contest\s*Superstars", cand_norm, re.IGNORECASE
                                ) and not re.search(
                                    r"\bWrapper\b", cand_norm, re.IGNORECASE
                                ):
                                    print(
                                        "         🎯 Targeted click (contains): 'Contest Superstars' (inside Wrapper/sidebar)"
                                    )
                                    cand.scroll_into_view_if_needed()
                                    time.sleep(0.2)
                                    cand.click(force=True)
                                    self._wait_for_long_loading(page)
                                    return True

                    clicked_inside = targeted.count() > 0
                except Exception as _tgt_e:
                    print(
                        f"         ⚠️ Targeted 'Contest Superstars' click failed: {_tgt_e}"
                    )

                # Text-based fallback across the whole page (handles cases outside sidebar selectors).
                try:
                    text_candidates = page.get_by_text(contest_re).all()
                    visible_text_candidates = [
                        c for c in text_candidates if c.is_visible()
                    ]
                    if visible_text_candidates:
                        for i in range(min(len(visible_text_candidates), 6)):
                            cand = visible_text_candidates[i]
                            print(
                                "         🎯 Text-global fallback click: 'Contest Superstars'"
                            )
                            cand.scroll_into_view_if_needed()
                            time.sleep(0.2)
                            cand.click(force=True)
                            self._wait_for_long_loading(page)
                            return True
                except Exception:
                    pass

                # Extra fallback: sometimes it’s rendered outside sidebar (still as a button/link).
                # Search globally for visible elements containing "Contest Superstars".
                try:
                    contest_re = re.compile(r"Contest\s*Superstars", re.IGNORECASE)
                    global_candidates = (
                        page.locator(
                            "main, section, [role='main'], .container, aside, body"
                        )
                        .locator(
                            "a, button, li, span, div[role='button'], div.menu-item"
                        )
                        .filter(has_text=contest_re)
                    )

                    if global_candidates.count() > 0:
                        for i in range(min(global_candidates.count(), 8)):
                            cand = global_candidates.nth(i)
                            if cand.is_visible():
                                print(
                                    "         🎯 Global fallback click: 'Contest Superstars'"
                                )
                                cand.scroll_into_view_if_needed()
                                time.sleep(0.2)
                                cand.click(force=True)
                                self._wait_for_long_loading(page)
                                return True
                except Exception as _g_e:
                    if not clicked_inside:
                        print(
                            f"         ⚠️ Global fallback for 'Contest Superstars' failed: {_g_e}"
                        )

                # JS-based heuristic fallback (handles aria-label/title-only / split text nodes)
                try:
                    js_clicked = page.evaluate("""
() => {
  const tokens = ["contest", "superstars"];
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  const els = Array.from(
    document.querySelectorAll("a, button, [role='button'], li, span, div")
  );

  const normalize = (s) => (s || "").toString().toLowerCase().replace(/\\s+/g," ").trim();

  for (const el of els) {
    try {
      if (!visible(el)) continue;
      const txt =
        normalize(el.innerText) + " " +
        normalize(el.getAttribute("aria-label")) + " " +
        normalize(el.getAttribute("title"));
      const ok = tokens.every(t => txt.includes(t));
      if (ok) {
        el.click();
        return true;
      }
    } catch (e) {}
  }
  return false;
}
""")
                    if js_clicked:
                        print("         🔁 JS heuristic click: 'Contest Superstars'")
                        self._wait_for_long_loading(page)
                        return True
                except Exception:
                    pass
        except Exception:
            pass

        # Dropdown option click (select2/chosen/bootstrap/listbox/etc.)
        # Important: PVP/Classic/Fightcard... thường là option nằm trong overlay dropdown,
        # không nằm ở sidebar/tab nên phải ưu tiên tìm trong các container dropdown đang visible.
        try:
            dropdown_option_selectors = [
                ".select2-results__option",
                ".select2-results__option[role='option']",
                ".chosen-results li",
                ".dropdown-menu.show a",
                ".dropdown-menu.show li",
                ".dropdown-menu.show button",
                "[role='listbox'] [role='option']",
                "[role='listbox'] li",
                "[role='listbox'] div",
                "ul[role='listbox'] li",
                ".ui-autocomplete .ui-menu-item-wrapper",
                ".mat-select-panel .mat-option",
                ".rc-virtual-list .rc-virtual-list-holder-inner div",
            ]

            opt_text = target_clean.strip()
            if opt_text:
                opt_regex = re.compile(
                    r"^\s*" + re.escape(opt_text) + r"\s*$", re.IGNORECASE
                )

                for sel in dropdown_option_selectors:
                    candidates = page.locator(sel).filter(has_text=opt_regex).all()
                    # Only click visible ones
                    visible_candidates = [c for c in candidates if c.is_visible()]
                    if visible_candidates:
                        for cand in visible_candidates[:10]:
                            try:
                                print(
                                    f"         🎯 Dropdown option click: '{target_clean}'"
                                )
                                cand.scroll_into_view_if_needed()
                                time.sleep(0.2)
                                cand.click(force=True)
                                self._wait_for_long_loading(page)
                                return True
                            except Exception:
                                continue
        except Exception:
            pass

        # Special deeper search for "Add Event" which often appears in the active panel/modal
        try:
            if "add event" in target_clean.lower():
                containers = [
                    ".modal.show",
                    ".modal.in",
                    "[role='dialog']:visible",
                    ".swal2-popup:visible",
                    ".tab-pane.active",
                    ".tab-content .active",
                    "section:has(.active)",
                    "main",
                    "body",
                ]

                opt_regex = re.compile(r"^\s*Add\s*Event\s*$", re.IGNORECASE)
                for csel in containers:
                    container = page.locator(csel).first
                    if container.count() == 0:
                        continue
                    if not container.is_visible():
                        continue

                    cand = (
                        container.locator(
                            "button, a, div[role='button'], span[role='button'], li"
                        )
                        .filter(has_text=opt_regex)
                        .first
                    )
                    if cand.count() > 0 and cand.is_visible():
                        print(
                            "         🎯 Special 'Add Event' click (active modal/panel)"
                        )
                        cand.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        cand.click(force=True)
                        self._wait_for_long_loading(page)
                        return True
        except Exception:
            pass

        _nav_map = {
            "daily reward": "daily_reward",
            "division configuration": "division_configuration",
        }
        nav_id = _nav_map.get(target_clean.lower())
        if nav_id:
            if self._click_sidebar_nav_by_id(page, nav_id, target_clean):
                clicked = True
                if nav_id == "daily_reward":
                    try:
                        page.wait_for_selector(
                            "#start_time_send_daily_reward, [name='start_time_send_daily_reward']",
                            state="visible",
                            timeout=8000,
                        )
                        print("         ✅ Daily Reward tab content loaded")
                    except Exception:
                        print(
                            "         ⚠️ Daily Reward fields not visible after nav click"
                        )
                else:
                    time.sleep(0.8)

        if clicked:
            self._wait_for_long_loading(page)
            return clicked

        sidebar_selectors = [
            ".sidebar",
            "#sidebar",
            "#left-menu",
            ".nav-pills",
            ".list-group",
            "div[class*='sidebar']",
            "div[class*='menu']",
            "aside",
            "#menu",
        ]

        for sel in sidebar_selectors:
            try:
                sidebar = page.locator(sel).first
                if sidebar.count() > 0 and sidebar.is_visible():
                    item = (
                        sidebar.locator(
                            "a, button, div[role='button'], li, span, div.menu-item"
                        )
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .first
                    )
                    if item.count() > 0 and item.is_visible():
                        try:
                            bbox = item.bounding_box()
                            if bbox and bbox["height"] > 120:
                                continue
                        except Exception:
                            pass
                        print(f"         ✅ Found '{target_text}' in Sidebar ({sel})")
                        item.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        item.click()
                        clicked = True
                        break
            except:
                continue

        if not clicked:
            try:
                tab = (
                    page.locator(
                        f"a[data-toggle='tab'], button[role='tab'], li.nav-item a"
                    )
                    .filter(has_text=re.compile(re.escape(target_clean), re.IGNORECASE))
                    .first
                )
                if tab.count() > 0 and tab.is_visible():
                    print(f"         ✅ Found Tab '{target_text}'")
                    tab.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    tab.click()
                    clicked = True
            except:
                pass

        # Checkbox-label strategy: find label with exact text → click its checkbox
        # Handles filter toggles like "Hide LiveopsTest gate items", "Hide Feeders", etc.
        # IMPORTANT: require the label text to be essentially the same as the target —
        # only trailing punctuation/asterisk allowed. A label like "Currency ID" must NOT
        # match target "Currency" because "ID" is a distinct extra word (not punctuation).
        if not clicked:
            try:
                lbl_candidates = (
                    page.locator("label")
                    .filter(has_text=re.compile(re.escape(target_clean), re.IGNORECASE))
                    .all()
                )
                for lbl in lbl_candidates:
                    if not lbl.is_visible():
                        continue
                    lbl_text = lbl.inner_text().strip()
                    lbl_norm = re.sub(r"\s+", " ", lbl_text).strip()
                    # Require label text == target (case-insensitive), optionally followed by
                    # only whitespace / colon / asterisk (common form-label suffixes like
                    # "Currency:" or "Hide Feeders *"). Any trailing word (e.g. "Currency ID")
                    # means this is a different field and must be rejected.
                    if not re.fullmatch(
                        re.escape(target_clean) + r"[\s:*]*", lbl_norm, re.IGNORECASE
                    ):
                        continue
                    chk = None
                    try:
                        chk = lbl.locator("input[type='checkbox']").first
                    except Exception:
                        pass
                    if not chk or chk.count() == 0:
                        try:
                            for_attr = lbl.get_attribute("for")
                            if for_attr:
                                chk = page.locator(f"#{for_attr}").first
                        except Exception:
                            pass
                    if chk and chk.count() > 0:
                        chk.scroll_into_view_if_needed()
                        chk.click(force=True)
                        print(f"         ✅ Checkbox toggled via label: '{lbl_text}'")
                    else:
                        lbl.scroll_into_view_if_needed()
                        lbl.click()
                        print(f"         ✅ Label clicked: '{lbl_text}'")
                    time.sleep(0.5)
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            panel_selectors = [
                "button[class*='store-sidebar']",
                "button[class*='sidebar-item']",
                "button[class*='panel-item']",
                ".list-group-item",
                "li[class*='item']",
                "li[class*='section']",
                ".row-item",
                ".section-item",
                "div[class*='sort']",
                "div[class*='item']",
                "div[class*='draggable']",
            ]
            for panel_sel in panel_selectors:
                try:
                    item = (
                        page.locator(panel_sel)
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .first
                    )
                    if item.count() > 0 and item.is_visible():
                        try:
                            bbox = item.bounding_box()
                            if bbox and bbox["height"] > 120:
                                continue
                        except Exception:
                            pass
                        text_preview = item.inner_text().strip()[:60]
                        print(
                            f"         ✅ Found panel item '{text_preview}' via {panel_sel}"
                        )
                        item.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        item.click()
                        clicked = True
                        break
                except:
                    continue

        if not clicked:
            # NOTE: Don't short-circuit PVE accordion expanders.
            # Otherwise "Normal Matches" (aria-expanded=false) will be treated as "already active"
            # and we never click the caret/toggle, so "Match 1" content can't be reached.
            target_lower_for_guard = target_clean.lower()
            is_pve_accordion_target = any(
                k in target_lower_for_guard for k in ["chapter info", "normal matches"]
            ) or bool(re.search(r"\bmatch\b", target_lower_for_guard, re.IGNORECASE))

            if not is_pve_accordion_target:
                try:
                    active_items = (
                        page.locator(
                            "a.active, li.active, div.active, [class*='selected']"
                        )
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .all()
                    )

                    for item in active_items:
                        if item.is_visible():
                            item_text = item.inner_text().strip()
                            # Must be EXACT match (not substring) to avoid parent containers
                            # that contain multiple tab names (e.g. li.active with children
                            # Tasks, Milestones, Leaderboards all inside one active wrapper)
                            if item_text.lower() != target_clean.lower():
                                continue
                            if target_clean.lower() == "daily reward":
                                if self._is_daily_reward_content_loaded(page):
                                    print(
                                        f"         ℹ️ Element '{target_text}' is already active/selected"
                                    )
                                    clicked = True
                                    break
                                print(
                                    f"         ⚠️ '{target_text}' nav active but content missing — re-clicking"
                                )
                                if self._click_sidebar_nav_by_id(
                                    page, "daily_reward", target_clean
                                ):
                                    clicked = True
                                    time.sleep(1)
                                break
                            print(
                                f"         ℹ️ Element '{target_text}' is already active/selected"
                            )
                            clicked = True
                            break
                except:
                    pass

        if not clicked:
            # Dialog/modal thường chứa nút "Add Event" sau khi chọn tab/menu
            try:
                dialog_selectors = [
                    ".modal.show",
                    ".modal.in",
                    ".swal2-popup:visible",
                    "[role='dialog']:visible",
                    ".ui-dialog:visible",
                ]
                for ds in dialog_selectors:
                    dialogs = page.locator(ds)
                    if dialogs.count() > 0:
                        btn_dialog = dialogs.first.locator(
                            "button, a, div[role='button'], span[role='button'], li"
                        ).filter(
                            has_text=re.compile(
                                rf"^\s*{re.escape(target_clean)}\s*$",
                                re.IGNORECASE,
                            )
                        )
                        if btn_dialog.count() > 0:
                            for i in range(min(btn_dialog.count(), 5)):
                                cand = btn_dialog.nth(i)
                                if cand.is_visible():
                                    print(f"         🎯 Dialog click: '{target_text}'")
                                    cand.scroll_into_view_if_needed()
                                    time.sleep(0.2)
                                    cand.click(force=True)
                                    self._wait_for_long_loading(page)
                                    return True

                        # Partial match (e.g. "Add Event" text wraps)
                        btn_dialog2 = dialogs.first.locator(
                            "button, a, div[role='button'], span[role='button'], li"
                        ).filter(
                            has_text=re.compile(
                                re.escape(target_clean),
                                re.IGNORECASE,
                            )
                        )
                        if btn_dialog2.count() > 0:
                            for i in range(min(btn_dialog2.count(), 5)):
                                cand = btn_dialog2.nth(i)
                                if cand.is_visible():
                                    print(
                                        f"         🎯 Dialog partial click: '{target_text}'"
                                    )
                                    cand.scroll_into_view_if_needed()
                                    time.sleep(0.2)
                                    cand.click(force=True)
                                    self._wait_for_long_loading(page)
                                    return True
            except:
                pass

            print("         ⚠️ Sidebar/Tab not found. Trying generic text match...")

            try:
                element = (
                    page.locator("button, a, div[role='button'], span[role='button']")
                    .filter(
                        has_text=re.compile(
                            re.escape(target_clean).replace(r"\ ", r"\s+"),
                            re.IGNORECASE,
                        )
                    )
                    .first
                )
                if element.count() > 0 and element.is_visible():
                    element.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    element.click()
                    clicked = True
            except:
                pass

            if not clicked:
                try:
                    element = (
                        page.locator(
                            "button, a, div[role='button'], span[role='button'], li, div.menu-item"
                        )
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .first
                    )
                    if element.count() > 0 and element.is_visible():
                        element.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        element.click()
                        clicked = True
                except:
                    pass

            if not clicked:
                try:
                    element = page.locator(f"text={target_clean}").first
                    if element.count() > 0 and element.is_visible():
                        element.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        element.click()
                        clicked = True
                except:
                    pass

            if not clicked:
                try:
                    candidates = (
                        page.locator("div, li, span, tr, td")
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .all()
                    )
                    visible = [el for el in candidates if el.is_visible()]
                    if visible:
                        best = min(visible, key=lambda el: len(el.inner_text().strip()))
                        text_preview = best.inner_text().strip()[:80]
                        if target_clean.lower() in text_preview.lower():
                            print(
                                f"         ✅ Strategy D broad match: '{text_preview}'"
                            )
                            best.scroll_into_view_if_needed()
                            time.sleep(0.3)
                            best.click(force=True)
                            clicked = True
                except:
                    pass

        if clicked:
            self._wait_for_long_loading(page)
            return True

        # --------------------------
        # Slow-load retry (fix for cases where tab/header appears late)
        # --------------------------
        try:
            wait_timeout_ms = 8000
            tab_re = re.compile(re.escape(target_clean), re.IGNORECASE)

            late_tab = (
                page.locator(
                    "a[data-toggle='tab'], button[data-toggle='tab'], [role='tab'], "
                    ".nav-tabs .nav-link, li.nav-item a, li.tab-item a, "
                    "button, a"
                )
                .filter(has_text=tab_re)
                .first
            )

            late_tab.wait_for(state="visible", timeout=wait_timeout_ms)
            late_tab.scroll_into_view_if_needed()
            time.sleep(0.3)
            late_tab.click()
            self._wait_for_long_loading(page)
            return True
        except Exception:
            pass

        # Fallback for "Filter Data" / "Filter" button not found:
        # Try common filter button selectors, then press Enter in the visible search input.
        if "filter" in target_clean.lower():
            try:
                for _fsel in [
                    "button#btn-filter",
                    "button:has-text('Filter')",
                    "a.btn:has-text('Filter')",
                    "input[type='submit'][value*='ilter']",
                    "button[type='submit']",
                ]:
                    try:
                        _fb = page.locator(_fsel).first
                        if _fb.count() > 0 and _fb.is_visible():
                            _fb.click()
                            print(f"         ✅ Filter fallback: clicked '{_fsel}'")
                            self._wait_for_long_loading(page)
                            return True
                    except Exception:
                        continue
                # Last resort: press Enter in the visible text / search input
                _inp = page.locator("input[type='text']:visible, input[type='search']:visible").first
                if _inp.count() > 0 and _inp.is_visible():
                    _inp.press("Enter")
                    print(f"         ✅ Filter fallback: pressed Enter in search input")
                    time.sleep(2)
                    self._wait_for_long_loading(page)
                    return True
            except Exception as _fe:
                print(f"         ⚠️ Filter fallback error: {_fe}")

        print(f"         ❌ FAILED: Cannot find clickable element '{target_text}'")
        return False


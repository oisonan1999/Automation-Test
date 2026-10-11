# automation/form_handler/special_panels.py - split from form_handler.py
# Special panels/pages: SSGroup helpers (Contest Superstar -> Phase B)
import time
import re
import random
from playwright.sync_api import Page


class SpecialPanelsMixin:
    """Special panels/pages: SSGroup helpers (Contest Superstar -> Phase B)"""

    def _try_set_ssgroup_id_by_multiselect_search_input(self, page, ssgroup_id):
        """
        Match panel (your provided HTML) uses a multiselect-like component:
          <input id="searchSSGroupId" placeholder="Type to search" aria-controls="listbox-searchSSGroupId">
          <span class="multiselect__single">SS_CPunk_BITW</span>
        So we:
          1) click/fill search input
          2) wait for listbox results by aria-controls
          3) click the option matching ssgroup_id
          4) verify multiselect__single updated
        """
        try:
            if ssgroup_id is None:
                return False

            value_str = str(ssgroup_id).strip()
            if not value_str:
                return False

            # IMPORTANT: scope to the currently expanded Match 1 panel to avoid
            # selecting the multiselect input from some other (already loaded) panel.
            scoped_root = page
            try:
                panel_id = None
                # Find the chevron/toggle button for Match 1 and extract aria-controls.
                # (Don't require aria-expanded=true here; at fill time it can be flaky.)
                match1_el = page.locator("text=Match 1").first
                # More robust: search toggle button anywhere under the Match 1 ancestor
                toggle_btn = match1_el.locator(
                    "xpath=ancestor::*//button[contains(@aria-controls,'chapter-match-')][1]"
                ).first
                if toggle_btn.count() > 0:
                    panel_id = toggle_btn.get_attribute("aria-controls")
                if panel_id:
                    scoped_root = page.locator(f"#{panel_id}")
            except:
                scoped_root = page

            # Collect candidate search inputs within the intended Match 1 panel.
            # If multiple exist, try each one until selection verifies.
            candidate_inputs = scoped_root.locator("input#searchSSGroupId").all()
            if not candidate_inputs:
                candidate_inputs = scoped_root.locator(
                    "input[aria-controls^='listbox-searchSSGroupId'], input[id^='searchSSGroup']"
                ).all()

            if not candidate_inputs:
                return False

            for search_input in candidate_inputs[:3]:
                # Read aria-controls listbox id for THIS input
                listbox_id = None
                try:
                    aria_controls = search_input.get_attribute("aria-controls") or ""
                    # aria-controls can be space-separated
                    listbox_id = aria_controls.split()[0] if aria_controls else None
                except:
                    listbox_id = None

                # Click/open dropdown
                try:
                    search_input.click(force=True)
                except:
                    pass

                # IMPORTANT: the SSGroup input may be width:0 and positioned absolute.
                # Always set via JS + dispatch events (don’t rely on Playwright fill()).
                try:
                    search_input.evaluate(
                        "(el,v)=>{"
                        "  try{el.focus();}catch(e){}"
                        "  el.value='';"
                        "  el.dispatchEvent(new Event('input',{bubbles:true}));"
                        "  el.dispatchEvent(new Event('change',{bubbles:true}));"
                        "  el.value=v;"
                        "  el.dispatchEvent(new Event('input',{bubbles:true}));"
                        "  el.dispatchEvent(new Event('change',{bubbles:true}));"
                        "}",
                        value_str,
                    )
                except:
                    # Fallback: try fill if JS fails
                    try:
                        search_input.fill("")
                        search_input.fill(value_str)
                    except:
                        continue

                time.sleep(0.25)

                # Wait for listbox results (in this UI, options are often NOT guaranteed to have role="option")
                if listbox_id:
                    # The listbox popup might render outside the Match 1 panel container.
                    # Using page-scoped lookup prevents missing the listbox due to strict scoping.
                    listbox = page.locator(f"#{listbox_id}")
                else:
                    listbox = scoped_root.locator("ul, div, [role='listbox']").first

                try:
                    listbox.wait_for(state="attached", timeout=8000)
                except:
                    try:
                        listbox.wait_for(state="visible", timeout=8000)
                    except:
                        pass

                if listbox_id:
                    # Try exact text match anywhere inside the listbox
                    match_opt = (
                        page.locator(f"#{listbox_id}")
                        .filter(
                            has_text=re.compile(
                                r"^\s*" + re.escape(value_str) + r"\s*$"
                            )
                        )
                        .first
                    )

                    # If exact text node isn't clickable, try broader clickable containers inside the listbox
                    if match_opt.count() == 0:
                        match_opt = (
                            page.locator(f"#{listbox_id} li, #{listbox_id} div")
                            .filter(
                                has_text=re.compile(
                                    r"^\s*" + re.escape(value_str) + r"\s*$",
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )

                    # Fallback: contains match
                    if match_opt.count() == 0:
                        match_opt = (
                            page.locator(f"#{listbox_id} li, #{listbox_id} div")
                            .filter(
                                has_text=re.compile(
                                    re.escape(value_str),
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )

                    # Final fallback: any element inside listbox containing the token
                    if match_opt.count() == 0:
                        match_opt = (
                            page.locator(f"#{listbox_id}")
                            .filter(
                                has_text=re.compile(
                                    re.escape(value_str),
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )
                else:
                    match_opt = (
                        scoped_root.locator("li, div, [role='option']")
                        .filter(
                            has_text=re.compile(
                                r"^" + re.escape(value_str) + r"\s*$",
                                re.IGNORECASE,
                            )
                        )
                        .first
                    )

                if match_opt.count() == 0:
                    continue

                match_opt.click(force=True)

                # Verify selection tag updated (inside intended panel)
                # Try to scope selection tag to the same Match panel as this input.
                panel_root = scoped_root
                try:
                    maybe_panel = search_input.locator(
                        "xpath=ancestor::*[contains(@id,'chapter-match-')][1]"
                    ).first
                    if maybe_panel.count() > 0:
                        panel_root = maybe_panel
                except:
                    pass

                # UI may be slow (dropdown list heavy), so wait a bit and re-check.
                for _ in range(20):
                    try:
                        selected = (
                            panel_root.locator("span.multiselect__single")
                            .filter(
                                has_text=re.compile(
                                    re.escape(value_str),
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )
                        if selected.count() > 0:
                            return True
                    except Exception:
                        pass
                    time.sleep(0.5)

                # One last attempt: Enter to confirm selection
                try:
                    page.keyboard.press("Enter")
                except:
                    pass

                time.sleep(0.5)
                try:
                    selected = (
                        scoped_root.locator("span.multiselect__single")
                        .filter(
                            has_text=re.compile(
                                re.escape(value_str),
                                re.IGNORECASE,
                            )
                        )
                        .first
                    )
                    if selected.count() > 0:
                        return True
                except Exception:
                    pass
            # If all candidate inputs failed
            return False
        except Exception:
            return False

    def _try_set_ssgroup_id_by_ssdb_search_placeholder(self, page, ssgroup_id):
        """
        Trong UI PVE Match, field SSGroup ID thường là select2 search có placeholder:
          - "Type to search SSDB" (hoặc tương tự)
        AI đưa data key='SSGroup ID' với value='SS_...'
        => Mở dropdown đúng control theo placeholder rồi chọn option theo value.
        """
        try:
            if ssgroup_id is None:
                return False

            value_str = str(ssgroup_id).strip()
            if not value_str:
                return False

            # Find select2 search input by placeholder tokens
            # (SSDB may vary: "SSDB", "SSD B", etc. -> match broadly)
            search_re = re.compile(r"type\s*to\s*search.*ssdb", re.IGNORECASE)

            # PVE Match panel loads async (you showed vld-icon + skeleton).
            # Wait a bit so the SSDB select2 input exists before we scan containers.
            try:
                page.locator("text=SSGroup ID").first.wait_for(
                    state="visible", timeout=8000
                )
            except:
                pass

            try:
                page.locator("input.select2-search__field").first.wait_for(
                    state="attached", timeout=8000
                )
            except:
                pass

            search_inputs = page.locator("input.select2-search__field").all()
            target_container = None

            def _get_ssdb_token_for_input(input_el):
                try:
                    ph = (input_el.get_attribute("placeholder") or "").strip()
                    aria = (input_el.get_attribute("aria-label") or "").strip()
                    data_ph = (input_el.get_attribute("data-placeholder") or "").strip()
                    role = (input_el.get_attribute("role") or "").strip()
                    combined = " ".join([ph, aria, data_ph, role]).strip()
                    return combined
                except:
                    return ""

            for inp in search_inputs:
                try:
                    token = _get_ssdb_token_for_input(inp)
                    if not token:
                        continue
                    if search_re.search(token):
                        # Prefer select2-container wrapper (click target)
                        container = inp.locator(
                            "xpath=ancestor::span[contains(@class,'select2-container')][1]"
                        ).first
                        if container.count() == 0:
                            container = inp.locator(
                                "xpath=ancestor::span[contains(@class,'select2-selection')][1]"
                            ).first
                        # As a last resort, allow direct parent click target
                        if container.count() == 0:
                            container = inp.locator("xpath=parent::*[1]").first

                        if container.count() > 0:
                            target_container = container
                            try:
                                if container.is_visible():
                                    break
                            except:
                                # Still accept for force-click later
                                break
                except:
                    continue

            # If we found container but it may be hidden, still allow later force-click.

            # Fallback: placeholder contains "Type to search" and we guess it's the SSDB one by nearby SS label text
            if target_container is None:
                generic_inputs = page.locator("input.select2-search__field").all()
                for inp in generic_inputs:
                    try:
                        placeholder = (inp.get_attribute("placeholder") or "").strip()
                        if not placeholder:
                            continue
                        if re.search(r"type\s*to\s*search", placeholder, re.IGNORECASE):
                            container = inp.locator(
                                "xpath=ancestor::span[contains(@class,'select2-container') or contains(@class,'select2-selection')][1]"
                            ).first
                            if container.count() > 0:
                                # Heuristic: prefer ones near left-side match panel controls
                                box = container.bounding_box()
                                if box and box["x"] < 800:
                                    target_container = container
                                    break
                            else:
                                target_container = container
                                break
                    except:
                        continue

            if target_container is None:
                # Fallback robust: mở từng select2 container để đợi input placeholder render
                try:
                    ssdb_token_re = re.compile(r"ssdb", re.IGNORECASE)

                    select2_containers = page.locator(
                        "span.select2-container, span.select2-selection"
                    ).all()

                    for cont in select2_containers:
                        try:
                            if not cont.is_visible():
                                continue
                        except:
                            continue

                        try:
                            cont.click(force=True)
                        except:
                            continue

                        time.sleep(0.25)

                        try:
                            # After opening, search field may exist with placeholder
                            search_inputs_now = page.locator(
                                "input.select2-search__field"
                            ).all()
                            ssdb_found = False
                            for inp in search_inputs_now:
                                try:
                                    ph = (
                                        inp.get_attribute("placeholder") or ""
                                    ).strip()
                                except:
                                    ph = ""
                                if ph and ssdb_token_re.search(ph):
                                    ssdb_found = True
                                    break

                            if ssdb_found:
                                target_container = cont
                                print(
                                    "         ✅ SSGroup ID: Found select2 container by opening/placeholder (SSDB)"
                                )
                                break
                        except:
                            pass

                        # Close dropdown and try next
                        try:
                            page.keyboard.press("Escape")
                        except:
                            pass

                    if target_container is None:
                        return False
                except:
                    return False

            # Primary path: use container determined by placeholder heuristics
            if self._handle_js_dropdown(page, target_container, value_str, "select2"):
                return True

            # Fallback: brute-force visible select2 containers and try to select by option text.
            # This handles cases where SSDB placeholder varies (or doesn't include SSDB token).
            try:
                select2_conts = page.locator(
                    "span.select2-container:visible, span.select2-selection:visible"
                ).all()
                for cont in select2_conts[:10]:
                    try:
                        if not cont.is_visible():
                            continue
                    except:
                        continue

                    try:
                        cont.click(force=True)
                    except:
                        continue

                    time.sleep(0.25)

                    # Find visible search input belonging to THIS opened select2 and type query
                    try:
                        ss_inp = cont.locator(
                            "input.select2-search__field:visible"
                        ).first
                        if ss_inp.count() == 0:
                            # fallback: global visible input (older layouts)
                            ss_inp = page.locator(
                                "input.select2-search__field:visible"
                            ).first
                        ss_inp.wait_for(state="visible", timeout=3000)
                    except:
                        # Close and continue
                        try:
                            page.keyboard.press("Escape")
                        except:
                            pass
                        continue

                    try:
                        ss_inp.fill("")
                        ss_inp.fill(value_str)
                    except:
                        # last resort: JS set value
                        try:
                            ss_inp.evaluate(
                                "(el,v)=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));}",
                                value_str,
                            )
                        except:
                            pass

                    time.sleep(0.5)

                    # Wait for options and click match
                    matched = False
                    try:
                        opts = page.locator(".select2-results__option:visible")
                        # wait for options to render
                        try:
                            opts.first.wait_for(state="visible", timeout=3000)
                        except:
                            pass

                        # prefer exact/equal text match
                        match_opt = opts.filter(
                            has_text=re.compile(r"^" + re.escape(value_str) + r"\s*$")
                        ).first
                        if match_opt.count() > 0 and match_opt.is_visible():
                            match_opt.click(force=True)
                            matched = True
                        else:
                            # contains fallback
                            match_opt2 = opts.filter(
                                has_text=re.compile(re.escape(value_str), re.IGNORECASE)
                            ).first
                            if match_opt2.count() > 0 and match_opt2.is_visible():
                                match_opt2.click(force=True)
                                matched = True
                    except:
                        matched = False

                    # Close dropdown
                    try:
                        page.keyboard.press("Escape")
                    except:
                        pass

                    if matched:
                        print(
                            "         ✅ SSGroup ID set via brute-force select2 option match"
                        )
                        return True
            except:
                pass

            return False
        except Exception as e:
            print(
                f"         ⚠️ _try_set_ssgroup_id_by_ssdb_search_placeholder error: {e}"
            )
            return False


    def _handle_rbe_contest_superstar(self, page, data):
        """RBE Contest Superstar special-case.

        When the 'Defining Schedules' modal is open, the UI rejects a CSS schedule
        outside the parent RBE schedule range. Clamp the update_form Start/End Time
        keys to the advertised range ('restricted to be within RBE schedule: ...').
        Mutates `data` in place; safe no-op when the modal or Start/End keys are absent.
        """
        # ============================
        # SPECIAL: Clamp "Defining Schedules" Start/End Time to RBE restriction
        # ============================
        # If the "Defining Schedules" modal is open, the UI may reject CSS schedule
        # outside the parent RBE schedule range.
        defining_modal = None
        defining_modal_visible = False
        try:
            defining_modal = (
                page.locator(".modal.show, .modal.in, .swal2-popup:visible")
                .filter(has_text=re.compile(r"Defining\s+Schedules", re.IGNORECASE))
                .last
            )
            defining_modal_visible = (
                defining_modal.count() > 0 and defining_modal.is_visible()
            )
        except:
            defining_modal_visible = False

        if defining_modal_visible and isinstance(data, dict):
            try:
                # Find Start/End keys in update_form data
                start_key = None
                end_key = None
                for k in data.keys():
                    kl = str(k).lower().strip()
                    if start_key is None and "start time" in kl:
                        start_key = k
                    if end_key is None and "end time" in kl:
                        end_key = k

                if start_key is not None and end_key is not None:
                    modal_text = defining_modal.inner_text().strip()

                    # Example:
                    # "CSS schedule is restricted to be within RBE schedule: 2026-04-24 19:00 - 2026-04-27 19:00"
                    m = re.search(
                        r"restricted to be within RBE schedule:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{1,2}:[0-9]{2})\s*-\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{1,2}:[0-9]{2})",
                        modal_text,
                        re.IGNORECASE,
                    )
                    if m:
                        from datetime import datetime as _dt

                        def _parse_ymd_hm(v):
                            sv = re.sub(r"[\[\]'\"]", "", str(v)).strip()
                            return _dt.strptime(sv, "%Y-%m-%d %H:%M")

                        allowed_start = _parse_ymd_hm(m.group(1))
                        allowed_end = _parse_ymd_hm(m.group(2))

                        provided_start = _parse_ymd_hm(data[start_key])
                        provided_end = _parse_ymd_hm(data[end_key])

                        # Clamp
                        clamped_start = provided_start
                        clamped_end = provided_end

                        if clamped_start < allowed_start:
                            clamped_start = allowed_start
                        if clamped_start > allowed_end:
                            clamped_start = allowed_end

                        if clamped_end < allowed_start:
                            clamped_end = allowed_start
                        if clamped_end > allowed_end:
                            clamped_end = allowed_end

                        if clamped_start > clamped_end:
                            clamped_end = clamped_start

                        new_start = clamped_start.strftime("%Y-%m-%d %H:%M")
                        new_end = clamped_end.strftime("%Y-%m-%d %H:%M")

                        if new_start != str(data[start_key]) or new_end != str(
                            data[end_key]
                        ):
                            print(
                                f"         🔧 [DefiningSchedules] Clamping {start_key}/{end_key} to allowed range: {new_start} - {new_end}"
                            )
                        data[start_key] = new_start
                        data[end_key] = new_end
            except Exception as _clamp_e:
                print(f"         ⚠️ [DefiningSchedules] Clamp skipped: {_clamp_e}")

    def _handle_pve_contest_superstar(self, page, data):
        """PVE v2 Contest Superstar special-case.

        Toggle Contest Superstar to open the Normal/Hard/Hell panels, then fill SS
        Node 1 + Soft Currency + top-level RBE per visible panel, popping handled keys
        from `data` so the generic fill loop skips them. Only runs when `data` has a
        'contest superstar' key (PVE-only). Never hard-fails the whole automation.
        """
        # ============================
        # SPECIAL CASE: PVE v2 "Contest Superstar" (Normal/Hard/Hell Node 1 + SS/Soft Currency)
        # ============================
        # Bật toggle + điền theo đúng panel visible để tránh misfill sang các field khác (VD: "Gate in Chapter Info").
        # Chỉ chạy khi data chứa key PVE-specific: "contest superstar" hoặc "node 1" (không phải soft currency).
        try:
            has_cs_keys = isinstance(data, dict) and any(
                "contest superstar" in str(k).lower()
                for k in data.keys()
            )
            if has_cs_keys:
                print("         🧩 [Contest Superstar] special-case entered")

                # ── FCV3: Fight Card V3 uses a different toggle name ──
                # PVE v2 toggle: name="contest-superstar-toggle"
                # FCV3 toggle:   name="fight-card-contest-superstar-toggle"
                # Detect FCV3 first; if found, just enable the toggle + "Add CSS" if
                # no CSS rows exist yet, then return — generic fill handles the rest.
                _fcv3_toggle = page.locator(
                    "input[name='fight-card-contest-superstar-toggle']"
                ).first
                if _fcv3_toggle.count() > 0:
                    # Determine desired toggle state
                    _fcv3_toggle_raw = next(
                        (v for k, v in data.items()
                         if str(k).lower().strip() == "contest superstar"),
                        "on",
                    )
                    _fcv3_want_on = str(_fcv3_toggle_raw).lower().strip() in (
                        "true", "1", "on", "yes", "enable", "enabled"
                    )
                    try:
                        _fcv3_cur = _fcv3_toggle.is_checked()
                    except Exception:
                        _fcv3_cur = None

                    if _fcv3_cur is None or _fcv3_cur != _fcv3_want_on:
                        try:
                            _fcv3_toggle.click(force=True)
                        except Exception:
                            try:
                                _fcv3_toggle.evaluate("el => el.click()")
                            except Exception:
                                pass
                        time.sleep(1.0)
                        # Wait for the tabpanel inside the CS accordion card to expand
                        try:
                            _fcv3_toggle.locator(
                                "xpath=ancestor::div[contains(@class,'card')][1]"
                            ).locator("div[role='tabpanel']").first.wait_for(
                                state="visible", timeout=4000
                            )
                        except Exception:
                            time.sleep(0.5)

                    # Pop only the "contest superstar" toggle key; leave remaining
                    # keys (RBE Event, Contest Superstar ID, Rewards, Quantity …)
                    # for the generic fill loop.
                    for _k in list(data.keys()):
                        if str(_k).lower().strip() == "contest superstar":
                            data.pop(_k, None)

                    # If the plan includes "Contest Superstar ID" fields but no CSS
                    # rows exist yet in the panel, click "+ Add CSS" to create one.
                    _fcv3_needs_css_row = any(
                        "contest superstar id" in str(k).lower() for k in data.keys()
                    )
                    if _fcv3_needs_css_row:
                        try:
                            _fcv3_card = _fcv3_toggle.locator(
                                "xpath=ancestor::div[contains(@class,'card')][1]"
                            ).first
                            # If no CSS-row label visible yet, click "Add CSS"
                            if _fcv3_card.locator("text=Contest Superstar ID").count() == 0:
                                _add_btn = _fcv3_card.locator(
                                    "button:has-text('Add CSS')"
                                ).first
                                if _add_btn.count() > 0:
                                    _add_btn.click(force=True)
                                    time.sleep(0.6)
                                    print(
                                        "         🧩 [FCV3 Contest Superstar] Clicked 'Add CSS' to create row"
                                    )
                        except Exception as _fcv3_add_e:
                            print(
                                f"         ⚠️ [FCV3 Contest Superstar] Add CSS check failed: {_fcv3_add_e}"
                            )

                    print(
                        f"         🧩 [Contest Superstar] FCV3 toggle done; "
                        f"keys for generic fill: {list(data.keys())}"
                    )
                    return  # generic fill handles remaining keys for FCV3

                # ── PVE v2 code unchanged below ──
                panels = [("normal", "Normal"), ("hard", "Hard"), ("hell", "Hell")]
                gate_skip: bool = False

                def _is_panel_node1_key(k: str, p_label: str) -> bool:
                    kl = str(k).lower().strip()
                    # Match ONLY the SS Node 1 key, not "Soft Currency (.. Node 1)".
                    # Your log shows soft-currency keys were being mistaken as SS.
                    if "soft currency" in kl:
                        return False
                    if "rbe" in kl:
                        return False
                    return (p_label.lower() in kl) and ("node 1" in kl)

                def _is_soft_currency_key(k: str) -> bool:
                    kl = str(k).lower().strip()
                    # Normalize: Soft Currency / SoftCurrency / Soft_Currency -> softcurrency
                    kl_norm = re.sub(r"[^a-z0-9]+", "", kl)
                    return "softcurrency" in kl_norm

                # 1) Toggle — match ONLY the exact toggle key; "Contest Superstar ID" must not steal this
                toggle_val = None
                for k, v in list(data.items()):
                    kl = str(k).lower().strip()
                    if kl == "contest superstar":
                        toggle_val = v
                        break

                if toggle_val is not None:
                    want_on = str(toggle_val).lower().strip() in (
                        "true",
                        "1",
                        "on",
                        "yes",
                        "enable",
                        "enabled",
                    )
                    gate_skip = want_on
                    toggle = page.locator(
                        "input[type='checkbox'][name='contest-superstar-toggle'], input[name='contest-superstar-toggle']"
                    ).first
                    if toggle.count() > 0:
                        try:
                            cur = toggle.is_checked()
                        except Exception:
                            cur = None
                        if cur is None or cur != want_on:
                            toggle.click(force=True)
                            time.sleep(0.8)

                # Extract SS multiselect per panel (case: Normal Node 1 -> SS value)
                ss_by_panel: dict[str, str] = {"normal": "", "hard": "", "hell": ""}
                for k, v in data.items():
                    for p_key, p_label in panels:
                        if _is_panel_node1_key(k, p_label) and isinstance(v, str):
                            ss_by_panel[p_key] = v.strip()

                def _is_rbe_key(key: str) -> bool:
                    kl = str(key).lower().strip()
                    # "RBE Event" is a Fight Card V3 PVE Contest Superstar field — NOT a PVE v2
                    # top-level RBE selector. Exclude it so generic fill handles it in FCV3.
                    if re.search(r"\brbe\s+event\b", kl):
                        return False
                    # Match generic "RBE" as well as "RBE: ..." style keys/values
                    # (AI may emit exactly "RBE" or "RBE_test_hieunm").
                    return bool(re.search(r"(^|\b)rbe(\b|$)", kl)) or ("rbe" in kl)

                # Soft currency amount: support both generic "Soft Currency" and panel-specific
                amount_generic: str | None = None
                amount_by_panel: dict[str, str] = {"normal": "", "hard": "", "hell": ""}
                for k, v in data.items():
                    if not _is_soft_currency_key(k):
                        continue
                    sv = str(v).strip() if v is not None else ""
                    if not sv:
                        continue
                    kl = str(k).lower().strip()
                    matched_panel = None
                    for p_key, p_label in panels:
                        if p_label.lower() in kl:
                            matched_panel = p_key
                            break
                    if matched_panel:
                        amount_by_panel[matched_panel] = sv
                    else:
                        amount_generic = sv

                # RBE multiselect value (second box): support both generic and panel-specific
                rbe_generic: str | None = None
                rbe_by_panel: dict[str, str] = {"normal": "", "hard": "", "hell": ""}
                for k, v in data.items():
                    if not _is_rbe_key(k):
                        continue
                    rv = str(v).strip() if v is not None else ""
                    if not rv:
                        continue
                    kl = str(k).lower().strip()
                    matched_panel = None
                    for p_key, p_label in panels:
                        if p_label.lower() in kl:
                            matched_panel = p_key
                            break
                    if matched_panel:
                        rbe_by_panel[matched_panel] = rv
                    else:
                        rbe_generic = rv

                # If only generic amount/rbe present, apply to all panels
                if amount_generic:
                    for p_key, _ in panels:
                        if not amount_by_panel[p_key]:
                            amount_by_panel[p_key] = amount_generic
                if rbe_generic:
                    for p_key, _ in panels:
                        if not rbe_by_panel[p_key]:
                            rbe_by_panel[p_key] = rbe_generic

                # Debug early: confirm extracted values before panel interactions
                try:
                    print(
                        "         🧪 [Contest Superstar] extracted: "
                        f"ss_by_panel={ss_by_panel}, "
                        f"amount_generic={amount_generic}, amount_by_panel={amount_by_panel}, "
                        f"rbe_generic={rbe_generic}, rbe_by_panel={rbe_by_panel}"
                    )
                except Exception:
                    pass

                # ✅ Set top-level RBE multiselect (outside Normal/Hard/Hell panels)
                # IMPORTANT: Fill RBE BEFORE the panel loop.
                # In your HTML, RBE fieldset is above the 3-box panel.
                # After RBE selection Vue may re-render and collapse the panels —
                # the panel open guard below handles re-opening them.
                # We add a deliberate 1.5s sleep after RBE so Vue finishes its
                # reactivity cycle before we start clicking panel headers.
                rbe_target: str | None = None
                if rbe_generic:
                    rbe_target = rbe_generic
                else:
                    for _pk in ("normal", "hard", "hell"):
                        if rbe_by_panel.get(_pk):
                            rbe_target = rbe_by_panel[_pk]
                            break

                if rbe_target:
                    try:
                        rbe_fieldset = page.locator(
                            "fieldset:has(legend:has-text('RBE'))"
                        ).first
                        rbe_input = rbe_fieldset.locator(
                            "input[placeholder*='Select option' i], input.multiselect__input"
                        ).first

                        if rbe_fieldset.count() > 0 and rbe_input.count() > 0:
                            try:
                                rbe_input.click(force=True)
                            except Exception:
                                rbe_input.evaluate("el => el.click()")

                            time.sleep(0.25)

                            # Type into the multiselect input to trigger option filtering/loading
                            try:
                                rbe_input.evaluate(
                                    "(el,v)=>{ el.focus&&el.focus(); el.value=''; el.dispatchEvent(new Event('input',{bubbles:true})); el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }",
                                    str(rbe_target),
                                )
                            except Exception:
                                try:
                                    rbe_input.fill(str(rbe_target))
                                except Exception:
                                    pass

                            time.sleep(0.5)

                            # Prefer token match (e.g. RBE_test_hieunm => tokens: test, hieu(n)m)
                            tokens = [t for t in str(rbe_target).split("_") if t]
                            token_pool = tokens[1:] or tokens
                            token_re = (
                                "|".join(re.escape(t) for t in token_pool[:3])
                                if token_pool
                                else re.escape(str(rbe_target))
                            )

                            matched = False
                            for _ in range(12):  # ~2.4s
                                listbox = rbe_fieldset.locator(
                                    "ul[role='listbox']:visible"
                                ).first
                                if listbox.count() == 0:
                                    time.sleep(0.2)
                                    continue

                                option = (
                                    listbox.locator(
                                        "span.multiselect__option, [role='option'], li"
                                    )
                                    .filter(
                                        has_text=re.compile(token_re, re.IGNORECASE)
                                    )
                                    .first
                                )

                                if option.count() > 0:
                                    try:
                                        option.click(force=True)
                                        matched = True
                                        break
                                    except Exception:
                                        pass

                                time.sleep(0.2)

                            if not matched:
                                # Fallback: click first non-empty option
                                listbox = rbe_fieldset.locator(
                                    "ul[role='listbox']:visible"
                                ).first
                                option2 = (
                                    listbox.locator(
                                        "span.multiselect__option, [role='option'], li"
                                    )
                                    .filter(
                                        has_text=re.compile(
                                            r"(No elements found|List is empty)",
                                            re.IGNORECASE,
                                        )
                                    )
                                    .not_.first
                                )
                                if option2.count() > 0:
                                    try:
                                        option2.click(force=True)
                                    except Exception:
                                        pass

                            # ✅ Verify top-level RBE actually selected; if not, retry once.
                            try:
                                normalized_target = (
                                    str(rbe_target)
                                    .lower()
                                    .strip()
                                    .replace("_", " ")
                                    .replace("-", " ")
                                )

                                selected_tag = rbe_fieldset.locator(
                                    "span.multiselect__single"
                                ).first
                                selected_ok = False
                                if selected_tag.count() > 0:
                                    selected_txt = (
                                        selected_tag.inner_text().strip().lower()
                                        if selected_tag.is_visible()
                                        else ""
                                    )
                                    if selected_txt:
                                        # Accept if target or any meaningful token appears
                                        if normalized_target in selected_txt:
                                            selected_ok = True
                                        else:
                                            tokens_norm = [
                                                t
                                                for t in re.split(
                                                    r"[_\s\-]+", normalized_target
                                                )
                                                if t
                                            ]
                                            selected_ok = any(
                                                tok in selected_txt
                                                for tok in tokens_norm[:3]
                                            )

                                if not selected_ok:
                                    # Retry: re-click the best matching option (token_re)
                                    listbox_retry = rbe_fieldset.locator(
                                        "ul[role='listbox']:visible"
                                    ).first
                                    if listbox_retry.count() == 0:
                                        listbox_retry = rbe_fieldset.locator(
                                            "ul[role='listbox']"
                                        ).first
                                    if listbox_retry.count() > 0:
                                        option_retry = (
                                            listbox_retry.locator(
                                                "span.multiselect__option, [role='option'], li"
                                            )
                                            .filter(
                                                has_text=re.compile(
                                                    token_re, re.IGNORECASE
                                                )
                                            )
                                            .first
                                        )
                                        if option_retry.count() > 0:
                                            option_retry.click(force=True)
                                            time.sleep(0.3)
                            except Exception:
                                # Verification should not crash special-case
                                pass

                    except Exception as _rbe_e:
                        print(
                            f"         ⚠️ [Contest Superstar] Set top-level RBE failed: {_rbe_e}"
                        )

                    # ── Give Vue time to finish its reactivity cycle after RBE change ──
                    # RBE selection can trigger watchers that collapse Normal/Hard/Hell panels.
                    # Sleeping here ensures the DOM settles before we click panel headers.
                    time.sleep(1.5)

                # This guarantees we won't later process 'RBE' / 'Soft Currency' / 'Node 1' keys
                # even if a UI operation inside panel application throws.
                # NOTE: only pop exact "contest superstar" toggle key; "Contest Superstar ID"
                # is a FCV3 field that must reach generic fill.
                for k in list(data.keys()):
                    kl = str(k).lower().strip()
                    if kl == "contest superstar":
                        data.pop(k, None)
                        continue

                    # If Contest Superstar toggle is ON, the UI behavior we observed
                    # may cause the automation to end up filling "Gate" incorrectly
                    # (because Normal panel collapses and generic filler runs).
                    # So we explicitly skip any Gate-related keys in this special-case.
                    if gate_skip and "gate" in kl:
                        data.pop(k, None)
                        continue

                    if _is_soft_currency_key(k):
                        data.pop(k, None)
                        continue
                    if _is_rbe_key(k):
                        data.pop(k, None)
                        continue
                    if any((_is_panel_node1_key(k, p_label)) for _, p_label in panels):
                        data.pop(k, None)
                        continue

                # 2) Apply to each panel
                contest_tablist = (
                    page.locator("div[role='tablist']")
                    .filter(has=page.locator(".pve-v2-contest-superstar-reward-bg"))
                    .first
                )
                for p_key, p_label in panels:
                    ss_val = ss_by_panel[p_key]
                    rbe_val = rbe_by_panel[p_key]
                    amt_val = amount_by_panel[p_key]

                    if not ss_val and not rbe_val and not amt_val:
                        continue

                    # Click tab header inside this contest tablist
                    header_btn = (
                        page.locator(
                            "header[role='tab'].pve-v2-contest-superstar-reward-bg button, header[role='tab'] button"
                        )
                        .filter(
                            has_text=re.compile(
                                rf"^\s*{re.escape(p_label)}\s*$", re.IGNORECASE
                            )
                        )
                        .first
                    )
                    if header_btn.count() == 0:
                        continue
                    # Only toggle the panel if it is currently collapsed.
                    # Unconditional click(force=True) may close it when already open.
                    opened = False
                    try:
                        card_chk = header_btn.locator(
                            "xpath=ancestor::div[contains(@class,'card')][1]"
                        ).first
                        panel_chk = card_chk.locator("div[role='tabpanel']").first
                        cls = panel_chk.get_attribute("class") or ""
                        cls_tokens = set(cls.split())
                        opened = ("show" in cls_tokens) or ("in" in cls_tokens)
                        if not opened:
                            try:
                                opened = panel_chk.is_visible()
                            except Exception:
                                opened = False
                    except Exception:
                        opened = False

                    if not opened:
                        try:
                            header_btn.click(force=True)
                        except Exception:
                            header_btn.evaluate("el => el.click()")
                        time.sleep(0.8)
                    else:
                        # Small settle time for already-open panel
                        time.sleep(0.2)

                    # Scope panel_root directly from the card that owns this header button
                    # HTML pattern:
                    #   <div class="card">
                    #     <header role="tab"> <button> Normal </button> </header>
                    #     <div role="tabpanel" ... class="collapse ...">...</div>
                    #   </div>
                    panel_root = None
                    try:
                        card_root = header_btn.locator(
                            "xpath=ancestor::div[contains(@class,'card')][1]"
                        ).first
                        panel_root = card_root.locator("div[role='tabpanel']").first
                        # Ensure it becomes visible after clicking header_btn
                        panel_root.wait_for(state="visible", timeout=5000)
                    except Exception:
                        # Fallback (best-effort): first visible panel
                        try:
                            panel_root = page.locator(
                                "div[role='tabpanel']:visible"
                            ).first
                        except Exception:
                            panel_root = None

                    if not panel_root or panel_root.count() == 0:
                        continue

                    # ============================
                    # Panel open guard (Normal/Hard/Hell are button-collapse panels)
                    # After toggling Contest Superstar, panels may collapse, causing locators to
                    # match outside-panel fields (Gate, etc.). We re-open the panel until the
                    # expected inputs exist inside this panel_root AND the tabpanel is visible.
                    # ============================
                    def _panel_is_open(root) -> bool:
                        """
                        The tabpanel itself must not be display:none.
                        Vue multiselect inputs are always in DOM (width:0/absolute) even when
                        the panel is closed — so checking .count() > 0 is NOT sufficient.
                        """
                        try:
                            # Check the tabpanel display style
                            display = root.evaluate(
                                "el => window.getComputedStyle(el).display"
                            )
                            if display == "none":
                                return False
                            # Also verify that at least one multiselect input DOM node exists
                            return root.locator("input.multiselect__input").count() > 0
                        except Exception:
                            return False

                    def _panel_has_ss_inputs_visible(root):
                        """
                        Vue multiselect input thường có width:0/position:absolute nên ':visible' có thể trả false.
                        Ở đây chỉ cần DOM tồn tại trong panel_root VÀ panel đang mở (không bị display:none).
                        """
                        try:
                            if not _panel_is_open(root):
                                return False
                            return (
                                root.locator(
                                    "input[placeholder*='Type to search' i]"
                                ).count()
                                > 0
                                or root.locator("input[placeholder*='Type' i]").count()
                                > 0
                            )
                        except Exception:
                            return False

                    def _panel_has_soft_currency_inputs_visible(root):
                        """
                        Bỏ ':visible' vì input multiselect đôi khi width:0/absolute vẫn cần fill bằng JS.
                        """
                        try:
                            if not _panel_is_open(root):
                                return False
                            return (
                                root.locator(
                                    "input[placeholder*='Select option' i]"
                                ).count()
                                > 0
                            )
                        except Exception:
                            return False

                    # Refresh attempts: click the panel button until expected INPUTS are actually visible
                    expected_ok = True
                    if ss_val:
                        expected_ok = _panel_has_ss_inputs_visible(panel_root)
                    if expected_ok and amt_val:
                        expected_ok = _panel_has_soft_currency_inputs_visible(
                            panel_root
                        )

                    if not expected_ok:
                        # Try to re-open and wait until inputs appear (handles async re-render after toggle)
                        deadline = time.time() + 10  # up to ~10s
                        did_reopen = False

                        while time.time() < deadline and not expected_ok:
                            # Re-open exactly once, then wait+re-check until visible inputs appear.
                            if not did_reopen:
                                try:
                                    header_btn.click(force=True)
                                    did_reopen = True
                                except Exception:
                                    try:
                                        header_btn.evaluate("el => el.click()")
                                        did_reopen = True
                                    except Exception:
                                        pass

                            # Wait for async re-render (do NOT spam click -> prevents open/close toggling)
                            time.sleep(0.7)

                            # re-resolve panel_root after wait (DOM may re-render)
                            try:
                                panel_root = (
                                    header_btn.locator(
                                        "xpath=ancestor::div[contains(@class,'card')][1]"
                                    )
                                    .first.locator("div[role='tabpanel']")
                                    .first
                                )
                            except Exception:
                                pass

                            if not panel_root or panel_root.count() == 0:
                                continue

                            expected_ok = True
                            if ss_val:
                                expected_ok = _panel_has_ss_inputs_visible(panel_root)
                            if expected_ok and amt_val:
                                expected_ok = _panel_has_soft_currency_inputs_visible(
                                    panel_root
                                )

                        # If still not ok, this panel won't be reliably interactable
                        if not expected_ok:
                            # skip this panel to avoid misfilling outside-panel fields
                            continue

                    # --- Set SS multiselect (first box, placeholder contains "Type to search") ---
                    if ss_val:
                        # ✅ Panel-scope guard:
                        # If the panel just collapsed (observed after toggle), locators like
                        # "Type to search" / "Select option" may match other parts of the UI
                        # (e.g. Gate dropdown). If expected SS input is not present inside panel_root,
                        # do NOT continue; re-open once, then skip this panel if still missing.
                        try:
                            ss_probe = panel_root.locator(
                                "input[placeholder*='Type to search' i]"
                            ).first
                            if ss_probe.count() == 0:
                                # Try to re-open this panel once
                                try:
                                    header_btn.click(force=True)
                                except Exception:
                                    pass
                                time.sleep(0.8)
                                ss_probe = panel_root.locator(
                                    "input[placeholder*='Type to search' i]"
                                ).first
                                if ss_probe.count() == 0:
                                    continue
                        except Exception:
                            # If panel_root is in a bad state, safest is to skip this panel
                            continue

                        # Primary selector (matches your HTML)
                        ss_input = panel_root.locator(
                            "input[placeholder*='Type to search' i]"
                        ).first

                        # Fallback selector (if placeholder changes/localizes slightly)
                        if ss_input.count() == 0:
                            ss_input = panel_root.locator(
                                "input[placeholder*='Type' i]"
                            ).first

                        try:
                            print(
                                f"         🧩 [Contest Superstar] SS target {p_label}: ss_input.count={ss_input.count()} ss_val={ss_val}"
                            )
                        except Exception:
                            pass

                        if ss_input.count() > 0:
                            # ── Open the Vue multiselect using the reliable helper ──
                            # The helper clicks .multiselect__select (the arrow button) and
                            # verifies that .multiselect__content-wrapper switches from
                            # display:none → display:block (Vue's open state indicator).
                            ss_combobox = ss_input.locator(
                                "xpath=ancestor::*[@role='combobox'][1]"
                            ).first
                            if ss_combobox.count() == 0:
                                ss_combobox = ss_input.locator(
                                    "xpath=ancestor::div[contains(@class,'multiselect')][1]"
                                ).first

                            opened = self._open_vue_multiselect(
                                page,
                                ss_combobox if ss_combobox.count() > 0 else ss_input,
                            )
                            if not opened:
                                print(
                                    f"         ⚠️ [Contest Superstar] Could not open SS multiselect ({p_label}), retrying once..."
                                )
                                time.sleep(0.6)
                                opened = self._open_vue_multiselect(
                                    page,
                                    (
                                        ss_combobox
                                        if ss_combobox.count() > 0
                                        else ss_input
                                    ),
                                )

                            time.sleep(0.2)

                            # ── Fill+select using keyboard.type (real InputEvents for Vue) ──
                            _ss_selected = self._fill_vue_multiselect(
                                page,
                                combobox_scope=(
                                    ss_combobox
                                    if ss_combobox.count() > 0
                                    else panel_root
                                ),
                                search_value=str(ss_val),
                                listbox_scope=panel_root,
                            )
                            if _ss_selected:
                                # skip the legacy polling block below
                                pass
                            else:
                                print(
                                    f"         ⚠️ [Contest Superstar] _fill_vue_multiselect failed for SS ({p_label}), running legacy fallback..."
                                )

                            # ── Legacy fallback kept for safety (runs only if new helper failed) ──
                            ss_raw = str(ss_val)  # defined here so outer fallback can always use it
                            if not _ss_selected:
                                ss_parts = [p for p in ss_raw.split("_") if p]
                                candidates: list[str] = []
                                if ss_raw:
                                    candidates.append(ss_raw)
                                candidates.append(ss_raw.replace("_", " "))
                                if len(ss_parts) >= 2:
                                    candidates.append(" ".join(ss_parts[1:]))
                                ss_no_ss = [p for p in ss_parts if p.lower() != "ss"]
                                if ss_no_ss:
                                    candidates.append(" ".join(ss_no_ss))
                                if len(ss_parts) >= 3:
                                    candidates.append(ss_parts[1])
                                    candidates.append(ss_parts[2])
                                deduped: list[str] = []
                                for c in candidates:
                                    c = str(c).strip()
                                    if c and c not in deduped:
                                        deduped.append(c)
                                candidates = deduped[:6]

                            last_texts: list[str] = []
                            if not _ss_selected:
                                for attempt_i, ss_search in enumerate(candidates):
                                    try:
                                        ss_input.evaluate(
                                            "(el,v)=>{ if(!el) return; el.focus&&el.focus(); el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }",
                                            ss_search,
                                        )
                                    except Exception:
                                        try:
                                            ss_input.evaluate(
                                                "(el)=>{ if(!el) return; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }"
                                            )
                                        except Exception:
                                            pass

                                    # Wait a bit for async options to render.
                                    # The UI may show a temporary "No elements found / List is empty" sentinel.
                                    found_real = False
                                    last_texts = []
                                    for _poll_i in range(20):  # ~6s total
                                        time.sleep(0.3)

                                        listbox_check = panel_root.locator(
                                            "ul[role='listbox']"
                                        ).first
                                        if listbox_check.count() == 0:
                                            continue

                                        try:
                                            # Read options from entire panel_root instead of relying on ul[role='listbox']
                                            # (Normal panel sometimes only renders sentinel inside that ul during async load).
                                            all_texts = panel_root.evaluate(
                                                "(el)=>Array.from(el.querySelectorAll('span.multiselect__option,[role=option],li'))"
                                                ".map(x=>(x.textContent||'').trim())"
                                                ".filter(Boolean)"
                                            )
                                            # Filter out sentinel/empty-state items so we can still detect real options
                                            last_texts = [
                                                t
                                                for t in (
                                                    list(all_texts) if all_texts else []
                                                )
                                                if not re.search(
                                                    r"(no elements found|list is empty|consider changing the search query)",
                                                    t,
                                                    re.IGNORECASE,
                                                )
                                            ][:6]
                                        except Exception:
                                            last_texts = []

                                        if len(last_texts) == 0:
                                            continue

                                        found_real = True
                                        break

                                    if not found_real:
                                        continue

                                    # got options => stop trying
                                    break

                            # Debug for last attempt
                            last_joined = " ".join(
                                (t or "").lower() for t in last_texts
                            )
                            if last_texts:
                                try:
                                    print(
                                        f"         🧩 [Contest Superstar] SS search candidates={candidates}, last_options_sample={last_texts}"
                                    )
                                except Exception:
                                    pass

                            # ✅ Fallback strategy:
                            # If search still yields only sentinel texts (No elements found / List is empty),
                            # try to load the full option list (clear input) and then match by tokens.
                            if (not last_texts) or (
                                "no elements found" in last_joined
                                or "list is empty" in last_joined
                            ):
                                try:
                                    ss_tokens = [
                                        t
                                        for t in ss_raw.split("_")
                                        if t and t.lower() != "ss"
                                    ]
                                    token1 = ss_tokens[0] if len(ss_tokens) > 0 else ""
                                    token2 = ss_tokens[1] if len(ss_tokens) > 1 else ""

                                    # Clear + trigger input
                                    try:
                                        ss_input.evaluate(
                                            "(el)=>{ if(!el) return; el.focus&&el.focus(); el.value=''; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }"
                                        )
                                    except Exception:
                                        ss_input.fill("")

                                    # Avoid press("Enter") (can hang); trigger input events via JS.
                                    try:
                                        ss_input.evaluate(
                                            "(el)=>{ if(!el) return; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }"
                                        )
                                    except Exception:
                                        pass

                                    time.sleep(0.9)

                                    listbox_visible2 = panel_root.locator(
                                        "ul[role='listbox']:visible"
                                    ).first
                                    listbox2_any = panel_root.locator(
                                        "ul[role='listbox']"
                                    ).first
                                    listbox2 = (
                                        listbox_visible2
                                        if listbox_visible2.count() > 0
                                        else listbox2_any
                                    )

                                    if listbox2.count() > 0:
                                        # Read all current option texts
                                        opt_texts = listbox2.evaluate(
                                            "(el)=>Array.from(el.querySelectorAll('span.multiselect__option,[role=option],li'))"
                                            ".map(x=>(x.textContent||'').trim())"
                                            ".filter(Boolean)"
                                        )
                                        real_opts = [
                                            t
                                            for t in opt_texts
                                            if not re.search(
                                                r"(no elements found|list is empty)",
                                                t,
                                                re.IGNORECASE,
                                            )
                                        ]

                                        if real_opts:
                                            # Pick best match: must contain token1 and token2 if available
                                            def _score(t: str) -> int:
                                                tl = t.lower()
                                                s = 0
                                                if token1 and token1.lower() in tl:
                                                    s += 2
                                                if token2 and token2.lower() in tl:
                                                    s += 2
                                                # Small bonus for length-ish matches
                                                if (
                                                    token1
                                                    and token2
                                                    and (
                                                        token1.lower() in tl
                                                        or token2.lower() in tl
                                                    )
                                                ):
                                                    s += 1
                                                return s

                                            best = max(real_opts, key=_score)
                                            # Click the option element by exact-ish text match
                                            option_el = (
                                                listbox2.locator(
                                                    "span.multiselect__option, [role='option'], li"
                                                )
                                                .filter(has_text=best)
                                                .first
                                            )
                                            if option_el.count() > 0:
                                                option_el.click(force=True)
                                                print(
                                                    f"         🧯 SS fallback clicked option: '{best}'"
                                                )
                                                last_texts = [best]
                                except Exception as _ss_fb_e:
                                    print(
                                        f"         ⚠️ [Contest Superstar] SS fallback failed: {_ss_fb_e}"
                                    )

                            time.sleep(0.8)

                            listbox_visible = panel_root.locator(
                                "ul[role='listbox']:visible"
                            ).first
                            listbox_any = panel_root.locator("ul[role='listbox']").first

                            # Debug: confirm whether the multiselect listbox exists and is visible
                            try:
                                cnt_vis = listbox_visible.count()
                                cnt_any = listbox_any.count()
                                print(
                                    f"         🧪 [Contest Superstar] SS listbox counts ({p_label}): visible={cnt_vis}, any={cnt_any}"
                                )
                            except Exception:
                                pass

                            listbox = (
                                listbox_visible
                                if listbox_visible.count() > 0
                                else listbox_any
                            )

                            # Debug: see whether multiselect actually has options after opening/filtering
                            if listbox.count() > 0:
                                try:
                                    opt_sample = listbox.evaluate(
                                        "(el)=>Array.from(el.querySelectorAll('span.multiselect__option,[role=option],li'))"
                                        ".filter(x=>x && x.offsetParent!==null)"
                                        ".slice(0,8)"
                                        ".map(x=>(x.textContent||'').trim())"
                                        ".filter(Boolean)"
                                    )
                                    print(
                                        f"         🧪 [Contest Superstar] SS listbox options sample ({p_label}): {opt_sample}"
                                    )
                                except Exception as _ss_dbg_e:
                                    print(
                                        f"         ⚠️ [Contest Superstar] SS listbox debug failed ({p_label}): {_ss_dbg_e}"
                                    )
                            else:
                                try:
                                    print(
                                        f"         ⚠️ [Contest Superstar] SS listbox not found at all ({p_label})"
                                    )
                                except Exception:
                                    pass

                            # ✅ IMPORTANT FIX:
                            # Even if listbox exists, previous code only printed debug and never clicked options.
                            # Now we ALWAYS attempt token-based selection when listbox is present.
                            tokens = [t for t in ss_val.split("_") if t]
                            token_pool = tokens[1:] or tokens
                            option = (
                                listbox.locator(
                                    "span.multiselect__option, [role='option'], li"
                                )
                                .filter(
                                    has_text=re.compile(
                                        "|".join(re.escape(t) for t in token_pool[:2]),
                                        re.IGNORECASE,
                                    )
                                )
                                .first
                            )
                            if option.count() == 0:
                                # IMPORTANT FIX:
                                # The previous code incorrectly applied `.not_` to a `re.Pattern`,
                                # causing: "re.Pattern object has no attribute 'not_'".
                                # Use locator-level exclusion via `has_not_text`.
                                option = (
                                    listbox.locator(
                                        "span.multiselect__option, [role='option'], li"
                                    )
                                    .filter(
                                        has_not_text=re.compile(
                                            r"(No elements found|List is empty)",
                                            re.IGNORECASE,
                                        )
                                    )
                                    .first
                                )

                            try:
                                if option.count() > 0:
                                    option.click(force=True)
                                    time.sleep(0.4)
                            except Exception:
                                pass

                    # --- Set Soft Currency selector (second multiselect inside panel) ---
                    # From your HTML: panel box2 uses placeholder "Select option" (currency type),
                    # while box3 is the number input.
                    if amt_val:
                        currency_type = "SoftCurrency"
                        cur_input = panel_root.locator(
                            "input[placeholder*='Select option' i]"
                        ).first
                        if cur_input.count() > 0:
                            # Find the combobox wrapper for this input
                            cur_combobox = cur_input.locator(
                                "xpath=ancestor::*[@role='combobox'][1]"
                            ).first
                            if cur_combobox.count() == 0:
                                cur_combobox = cur_input.locator(
                                    "xpath=ancestor::div[contains(@class,'multiselect')][1]"
                                ).first

                            # Open using the reliable helper (checks display:block)
                            _cur_opened = self._open_vue_multiselect(
                                page,
                                cur_combobox if cur_combobox.count() > 0 else cur_input,
                            )
                            if not _cur_opened:
                                time.sleep(0.5)
                                _cur_opened = self._open_vue_multiselect(
                                    page,
                                    (
                                        cur_combobox
                                        if cur_combobox.count() > 0
                                        else cur_input
                                    ),
                                )
                            time.sleep(0.2)

                            # Fill using keyboard.type (real InputEvents)
                            _cur_selected = self._fill_vue_multiselect(
                                page,
                                combobox_scope=(
                                    cur_combobox
                                    if cur_combobox.count() > 0
                                    else panel_root
                                ),
                                search_value=currency_type,
                                listbox_scope=panel_root,
                            )

                            if not _cur_selected:
                                # Legacy JS fallback
                                try:
                                    cur_input.evaluate(
                                        "(el,v)=>{ el.focus&&el.focus(); el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }",
                                        currency_type,
                                    )
                                except Exception:
                                    try:
                                        cur_input.fill(currency_type)
                                    except Exception:
                                        pass

                                matched = False
                                for _ in range(10):  # ~2s
                                    listbox = panel_root.locator(
                                        "ul[role='listbox']:visible"
                                    ).first
                                    if listbox.count() == 0:
                                        time.sleep(0.2)
                                        continue

                                    option = (
                                        listbox.locator(
                                            "span.multiselect__option, [role='option'], li"
                                        )
                                        .filter(
                                            has_text=re.compile(
                                                r"^\s*Soft\s+Currency\s*$",
                                                re.IGNORECASE,
                                            )
                                        )
                                        .first
                                    )
                                    if option.count() > 0:
                                        try:
                                            option.click(force=True)
                                            matched = True
                                            break
                                        except Exception:
                                            pass

                                    option2 = (
                                        listbox.locator(
                                            "span.multiselect__option, [role='option'], li"
                                        )
                                        .filter(
                                            has_text=re.compile(
                                                r"soft\s*currency", re.IGNORECASE
                                            )
                                        )
                                        .first
                                    )
                                    if option2.count() > 0:
                                        try:
                                            option2.click(force=True)
                                            matched = True
                                            break
                                        except Exception:
                                            pass

                                    time.sleep(0.2)

                                if not matched:
                                    pass

                    # --- Set Soft currency amount (third box: input[type=number]) ---
                    if amt_val:
                        num_inp = panel_root.locator("input[type='number']").first
                        if num_inp.count() > 0:
                            try:
                                num_inp.evaluate(
                                    "(el,v)=>{ el.focus&&el.focus(); el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }",
                                    amt_val,
                                )
                            except Exception:
                                try:
                                    num_inp.fill(str(amt_val))
                                except Exception:
                                    pass

                # ✅ Final guard: ensure top-level RBE is actually selected before we leave special-case.
                # Observed failure mode: internal extraction may look correct, but UI still shows
                # "Oops... RBE is required when Contest Superstar is enabled and visible."
                if rbe_target:
                    try:

                        def _normalize_rbe_txt(s: str) -> str:
                            return (
                                (s or "")
                                .lower()
                                .strip()
                                .replace("_", " ")
                                .replace("-", " ")
                            )

                        normalized_target = _normalize_rbe_txt(str(rbe_target))
                        tokens = [
                            t
                            for t in re.split(r"[_\s\-]+", str(rbe_target))
                            if t and str(t).strip()
                        ]
                        token_pool = tokens[1:] or tokens
                        token_re = "|".join(
                            re.escape(t) for t in token_pool[:3] if t
                        ) or re.escape(str(rbe_target))

                        def _read_selected_text() -> str:
                            if not rbe_fieldset:
                                return ""
                            texts: list[str] = []
                            for sel in [
                                "span.multiselect__single",
                                ".multiselect__single",
                                "span.multiselect__tag",
                                ".multiselect__tags span",
                            ]:
                                try:
                                    loc = rbe_fieldset.locator(sel).first
                                    if loc.count() > 0 and loc.is_visible():
                                        t = loc.inner_text().strip()
                                        if t:
                                            texts.append(t)
                                except Exception:
                                    continue
                            return " ".join(texts).strip()

                        def _open_and_select_option():
                            nonlocal rbe_fieldset
                            if not rbe_fieldset:
                                return False

                            # Prefer clicking a combobox/selector wrapper; the input may be width:0/hidden.
                            try:
                                combobox = rbe_fieldset.locator(
                                    "[role='combobox'], [role='group']:has(input)"
                                ).first
                                if combobox.count() > 0 and combobox.is_visible():
                                    combobox.click(force=True)
                                else:
                                    # fallback: click likely input and its .multiselect__select
                                    rbe_input_try = rbe_fieldset.locator(
                                        "input[placeholder*='Select option' i], input.multiselect__input"
                                    ).first
                                    if rbe_input_try.count() > 0:
                                        sel = rbe_input_try.locator(
                                            "xpath=ancestor::*[class*='multiselect']//*[contains(@class,'multiselect__select')][1]"
                                        ).first
                                        if sel.count() > 0:
                                            sel.click(force=True)
                                        else:
                                            rbe_input_try.click(force=True)
                            except Exception:
                                # last resort: force click input
                                try:
                                    rbe_input_try = rbe_fieldset.locator(
                                        "input[placeholder*='Select option' i], input.multiselect__input"
                                    ).first
                                    if rbe_input_try.count() > 0:
                                        rbe_input_try.click(force=True)
                                except Exception:
                                    pass

                            time.sleep(0.25)

                            # Click best matching option
                            listbox = rbe_fieldset.locator(
                                "ul[role='listbox']:visible"
                            ).first
                            if listbox.count() == 0:
                                # some UIs render listbox without role
                                listbox = rbe_fieldset.locator(
                                    "[role='listbox']:visible"
                                ).first

                            if listbox.count() == 0:
                                return False

                            option = (
                                listbox.locator(
                                    "span.multiselect__option, [role='option'], li"
                                )
                                .filter(has_text=re.compile(token_re, re.IGNORECASE))
                                .first
                            )

                            if option.count() > 0:
                                option.click(force=True)
                                return True

                            # Fallback: click first non-empty option
                            opt2 = (
                                listbox.locator(
                                    "span.multiselect__option, [role='option'], li"
                                )
                                .filter(
                                    has_not_text=re.compile(
                                        r"(no elements found|list is empty)",
                                        re.IGNORECASE,
                                    )
                                )
                                .first
                            )
                            if opt2.count() > 0:
                                opt2.click(force=True)
                                return True

                            return False

                        rbe_fieldset = page.locator(
                            "fieldset:has(legend:has-text('RBE'))"
                        ).first

                        selected_ok = False
                        for _try in range(6):  # ~3-4s
                            try:
                                if rbe_fieldset.count() == 0:
                                    break

                                # quick check first
                                selected_txt = _read_selected_text()
                                selected_norm = _normalize_rbe_txt(selected_txt)
                                if selected_txt and (
                                    normalized_target in selected_norm
                                    or any(
                                        tok.lower() in selected_norm
                                        for tok in token_pool[:3]
                                        if tok
                                    )
                                ):
                                    selected_ok = True
                                    break

                                if _open_and_select_option():
                                    time.sleep(0.35)
                            except Exception:
                                pass

                        if selected_ok:
                            print(
                                "         ✅ [Contest Superstar] Final guard: top-level RBE selected."
                            )
                        else:
                            print(
                                "         ⚠️ [Contest Superstar] Final guard: top-level RBE still not confirmed (best-effort)."
                            )
                    except Exception as _rbe_final_e:
                        print(
                            f"         ⚠️ [Contest Superstar] Final top-level RBE guard failed: {_rbe_final_e}"
                        )

                # Remove contest-superstar related keys so generic filler won't misfill.
                # Only pop exact "contest superstar" toggle key; "Contest Superstar ID" is
                # a FCV3 field — it must reach generic fill (handled above as a no-op in FCV3).
                for k in list(data.keys()):
                    kl = str(k).lower().strip()
                    if kl == "contest superstar":
                        data.pop(k, None)
                        continue
                    if _is_soft_currency_key(k):
                        data.pop(k, None)
                        continue
                    if _is_rbe_key(k):
                        data.pop(k, None)
                        continue
                    if any((_is_panel_node1_key(k, p_label)) for _, p_label in panels):
                        data.pop(k, None)
                        continue
        except Exception as _cs_e:
            print(f"         ⚠️ [Contest Superstar] special-case crashed: {_cs_e}")
            # Never hard-fail whole automation: if this special-case errors, let generic fill proceed.
            pass

        # Debug: keys left after Contest Superstar special-case pop()
        # Only print when the special-case actually ran (PVE only).
        try:
            if has_cs_keys:
                print(
                    f"         🧩 [Contest Superstar] keys remaining after special-case pops: {list(data.keys())}"
                )
        except Exception:
            pass

    def _handle_restriction_slot_edit(self, page, data):
        """Titan Takeover Boss "Restriction Slot N" special-case.

        The Battle Setup tab shows a read-only preview input + "Edit" button per
        slot (fieldset legend = "Restriction Slot N"). Edit opens a modal with a
        nested Group/AND/OR condition-rule builder (Vue component
        `.restriction-rule-builder`), NOT a single plain input — the generic
        `_handle_inline_edit_field` can't handle it (it only fills one input).

        Trigger: any data key matching "Restriction Slot <N>" (case-insensitive).
        Value format: "Group <M>: [<item1>, <item2>, ...]" (M defaults to 1 if
        omitted). Each item is added as a new "AND condition" row inside Group M
        (first item reuses the modal's existing empty row), then the value is
        typed into that row's Vue Multiselect ("Search requirement..." combobox)
        the same way `_fill_vue_multiselect` fills any other Vue multiselect.
        Pops handled keys from `data` so the generic fill loop skips them.
        """
        if not isinstance(data, dict):
            return

        slot_keys = [
            k for k in list(data.keys())
            if re.match(r"^\s*restriction\s*slot\s*\d+\s*$", str(k), re.IGNORECASE)
        ]
        if not slot_keys:
            return

        for slot_key in slot_keys:
            spec = data.pop(slot_key, None)
            try:
                self._fill_restriction_slot(page, str(slot_key).strip(), spec)
            except Exception as e:
                print(f"         ⚠️ [Restriction Slot] Failed to fill '{slot_key}': {e}")

    def _parse_restriction_slot_spec(self, spec):
        """
        Parse a "Restriction Slot" value into (group_number, [condition_items]).

        Accepts:
          'Group 1: ["Ascended_1","group:Color_Black"]'  -> (1, ["Ascended_1", "group:Color_Black"])
          '["Ascended_1","group:Color_Black"]'           -> (1, [...])   (group defaults to 1)
          'Ascended_1'                                    -> (1, ["Ascended_1"])  (single bare value)
        """
        import json as _json

        s = str(spec).strip()
        m = re.match(r"(?:group\s*(\d+)\s*:\s*)?(\[.*\])\s*$", s, re.IGNORECASE | re.DOTALL)
        if not m:
            return 1, ([s] if s else [])

        group_num = int(m.group(1)) if m.group(1) else 1
        bracket_str = m.group(2)
        try:
            items = _json.loads(bracket_str)
        except Exception:
            # Fallback: naive quoted-string extraction if JSON parsing fails
            # (e.g. AI emitted single quotes or an unterminated bracket).
            items = re.findall(r'"([^"]*)"|\'([^\']*)\'', bracket_str)
            items = [a or b for a, b in items]

        return group_num, [str(it).strip() for it in items if str(it).strip()]

    def _fill_restriction_slot(self, page, slot_label, spec):
        """
        Open the "Edit {slot_label}" modal and set Group N's conditions to the
        parsed item list. See `_handle_restriction_slot_edit` for context.
        """
        group_num, items = self._parse_restriction_slot_spec(spec)
        if not items:
            print(f"         ⚠️ [Restriction Slot] '{slot_label}': nothing to fill (empty spec: {spec!r})")
            return

        print(f"         🧩 [Restriction Slot] '{slot_label}' -> Group {group_num}: {items}")

        # 1) Find the fieldset via its <legend> (exact match so "Slot 1" != "Slot 10").
        # The Battle Setup tab-pane keeps its DOM mounted but hidden when another
        # tab is active (BootstrapVue tabs) — a save/reload can reset the active
        # tab back to the default one, so a prior "click tab Battle Setup" step
        # earlier in the plan is not a reliable guarantee it's still active here.
        # Self-heal: if the legend isn't visible, click the tab ourselves first.
        def _find_visible_legend():
            loc = page.locator("legend").filter(
                has_text=re.compile(rf"^\s*{re.escape(slot_label)}\s*$", re.IGNORECASE)
            ).first
            if loc.count() == 0:
                return None
            try:
                return loc if loc.is_visible() else None
            except Exception:
                return None

        legend = _find_visible_legend()
        if legend is None:
            battle_setup_tab = page.locator("text=Battle Setup").first
            if battle_setup_tab.count() > 0:
                try:
                    battle_setup_tab.click(force=True)
                    time.sleep(1.0)
                except Exception:
                    pass
            legend = _find_visible_legend()

        if legend is None:
            print(
                f"         ⚠️ [Restriction Slot] legend for '{slot_label}' not visible "
                "(Battle Setup tab not active) — giving up"
            )
            return

        fieldset = legend.locator("xpath=ancestor::fieldset[1]").first
        edit_btn = fieldset.locator("button:has-text('Edit')").first
        if edit_btn.count() == 0:
            print(f"         ⚠️ [Restriction Slot] Edit button not found in '{slot_label}' fieldset")
            return

        try:
            edit_btn.scroll_into_view_if_needed(timeout=5000)
        except Exception as e:
            print(f"         ⚠️ [Restriction Slot] scroll_into_view failed for '{slot_label}': {e}")
            return
        edit_btn.click(force=True)
        time.sleep(0.6)

        # 2) Wait for the "Edit Restriction Slot N" modal
        modal = page.locator(".modal.show, .modal.in").filter(
            has_text=re.compile(r"Edit\s+Restriction\s+Slot", re.IGNORECASE)
        ).last
        try:
            modal.wait_for(state="visible", timeout=5000)
        except Exception:
            print(f"         ⚠️ [Restriction Slot] Modal didn't open for '{slot_label}'")
            return

        # 3) Locate (or fall back to) the target Group N card
        group_cards = modal.locator(".group-card").all()
        target_group = None
        for gc in group_cards:
            header = gc.locator(".group-header small").first
            if header.count() > 0:
                try:
                    if header.inner_text().strip().lower() == f"group {group_num}".lower():
                        target_group = gc
                        break
                except Exception:
                    pass
        if target_group is None:
            if not group_cards:
                print(f"         ⚠️ [Restriction Slot] No group-card found in modal for '{slot_label}'")
                self._safe_press_escape(page)
                return
            print(f"         ⚠️ [Restriction Slot] Group {group_num} not found, falling back to first group")
            target_group = group_cards[0]

        def _condition_rows():
            return target_group.locator(".condition-row").all()

        # 4) Fill each item into a condition-row, adding new AND-condition rows as needed.
        # The modal always ships with ONE empty row already present, so item 0 reuses it.
        for idx, item in enumerate(items):
            rows = _condition_rows()
            if idx >= len(rows):
                add_btn = target_group.locator(
                    "button.add-condition-btn:has-text('Add AND condition')"
                ).first
                if add_btn.count() == 0:
                    print(f"         ⚠️ [Restriction Slot] 'Add AND condition' button not found (item {idx}: '{item}')")
                    break
                add_btn.click(force=True)
                time.sleep(0.5)
                rows = _condition_rows()
                if idx >= len(rows):
                    print(f"         ⚠️ [Restriction Slot] Row for item {idx} ('{item}') didn't appear after Add")
                    continue

            row = rows[idx]
            combobox = row.locator(".multiselect.condition-select").first
            if combobox.count() == 0:
                print(f"         ⚠️ [Restriction Slot] No condition-select in row {idx}")
                continue

            opened = self._open_vue_multiselect(page, combobox, timeout_ms=3000)
            if not opened:
                print(f"         ⚠️ [Restriction Slot] Could not open condition-select for item {idx} ('{item}')")

            filled = self._fill_vue_multiselect(page, combobox, item, listbox_scope=combobox)
            if not filled:
                print(f"         ⚠️ [Restriction Slot] Could not select '{item}' for row {idx}")

            time.sleep(0.3)

        # 5) Save the modal (scoped to modal-footer to avoid the outer page's Save)
        save_btn = modal.locator(".modal-footer button:has-text('Save')").first
        if save_btn.count() > 0:
            save_btn.click(force=True)
            print(f"         💾 [Restriction Slot] Saved '{slot_label}'")
            time.sleep(1.0)
        else:
            print(f"         ⚠️ [Restriction Slot] Save button not found in modal footer for '{slot_label}'")

        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass

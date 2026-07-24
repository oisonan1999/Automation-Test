# automation/form_handler/field_finder.py - split from form_handler.py
# Locate input element from a label (normal pages)
import time
import re
import random
from playwright.sync_api import Page


class FieldFinderMixin:
    """Locate input element from a label (normal pages)"""

    def _find_input_element(self, page, label_text):
        print(f"         🔍 Searching for field: '{label_text}'")

        # Known field aliases (Versus Tournament Daily Reward tab)
        # NOTE: IMPORTANT - "Event ID" must NOT map to "EventName".
        # This was causing the automation to type Event Name when the testcase requests Event ID.
        _field_aliases = {
            "time of reward utc": "start_time_send_daily_reward",
            "eventname": "EventName",
            "event name": "EventName",
            # Offer Section clone modal: DOM label is "Section ID" (for='section_id')
            # but AI generates "New Section ID" from test-case text.
            "new section id": "section_id",
        }

        label_key = label_text.lower().strip()
        # Special handling: Event ID (avoid wrong aliasing)
        if label_key in ("event id", "eventid"):
            # Try common casing/underscore variants
            for cand in [
                "EventID",
                "EventId",
                "eventID",
                "eventId",
                "event_id",
                "eventid",
            ]:
                alias_el = page.locator(f"#{cand}, [name='{cand}']").first
                if alias_el.count() > 0 and alias_el.is_visible():
                    print(f"         🎯 Field alias '{label_text}' → #{cand}")
                    return alias_el

        alias = _field_aliases.get(label_key)
        if alias:
            alias_el = page.locator(f"#{alias}, [name='{alias}']").first
            if alias_el.count() > 0 and alias_el.is_visible():
                print(f"         🎯 Field alias '{label_text}' → #{alias}")
                return alias_el

        # ─── Auto-scope to modal if one is open ────────────────────────────────────────
        # Shadow ‘page’ → modal so mọi page.locator() bên dưới đều scoped đúng
        _in_modal = False
        for _ms in [".modal.show", ".modal.in", ".modal[aria-hidden='false']"]:
            try:
                if page.locator(_ms).count() > 0:
                    page = page.locator(_ms).last
                    _in_modal = True
                    print(f"         🔒 Auto-scoped to modal ({_ms})")
                    break
            except Exception:
                pass
        # ───────────────────────────────────────────────────────────────────

        label_lower = label_text.lower().strip()
        # Tạo version không space/underscore để fuzzy match
        label_normalized = re.sub(r"[\s_-]+", "", label_lower)

        # Known LABEL TEXT aliases: the AI sometimes generates a key with an
        # extra/missing word vs. the real on-page label (e.g. "RBE Event ID"
        # when the actual field is labeled just "RBE Event *" — Fight Card V3
        # Contest Superstar panel). Every search strategy below matches by
        # substring-in-element-text, so an extra word means 0 candidates no
        # matter how many fallbacks run. Rewrite to the real label up front.
        _label_text_aliases = {
            "rbe event id": "RBE Event",
        }
        if label_lower in _label_text_aliases:
            label_text = _label_text_aliases[label_lower]
            label_lower = label_text.lower().strip()
            label_normalized = re.sub(r"[\s_-]+", "", label_lower)
            print(f"         🔀 Label alias: rewrote to '{label_text}'")

        # ─── SPECIAL CASE: data-mode inputs (Affiliation War Contribution's
        # "Mode | Value" table: PvE/Showdown/Feud/Contest Task/Titan TakeOver/
        # Gacha/Upgrades). Row labels are bare <td> text that collides with
        # OTHER things on the page (e.g. "Showdown" is also a sidebar nav item
        # for a different RBE feature), so the generic label/container search
        # below picks the wrong element entirely. The app itself disambiguates
        # rows via data-mode="<Mode>" on the value <input> — use that directly
        # before any ambiguous text matching. ────────────────────────────────
        try:
            data_mode_input = page.locator(f"input[data-mode='{label_text}' i]").first
            if data_mode_input.count() > 0 and data_mode_input.is_visible():
                print(f"         🎯 Found input via data-mode='{label_text}'")
                return data_mode_input
        except Exception:
            pass

        # ─── SPECIAL CASE: Condition <select> (Win / Win against any rarity) ─────
        # Tránh việc chọn nhầm select khác trong cùng row/container (VD: event_id/background).
        # HTML thực tế thường là: <select class="condition" ...>
        if label_lower == "condition" or label_normalized == "condition":
            try:
                cond_sel = page.locator("select.condition").first
                if cond_sel.count() > 0:
                    return cond_sel

                # Fallback: name contains "condition"
                cond_sel2 = page.locator("select[name*='condition' i]").first
                if cond_sel2.count() > 0:
                    return cond_sel2
            except Exception:
                pass

        # ─── Keyword fallback for fields that may not have a visible <label> ─────
        # Example: "Superstars or Groups" can be rendered only as a custom select2/multiselect
        # without a direct label element, so label-based lookup fails.
        # We fallback by searching select[name/id] for "superstars"/"groups" keywords.
        if (
            any(k in label_lower for k in ["superstars", "groups", "group"])
            and label_normalized
        ):
            try:
                keyword_words = []
                if "superstars" in label_lower:
                    keyword_words.append("superstars")
                if "groups" in label_lower or "group" in label_lower:
                    keyword_words.append("groups")

                keyword_words = [w for w in keyword_words if w]
                if keyword_words:
                    selects = page.locator("select").all()
                    for sel in selects:
                        try:
                            sel_id = (sel.get_attribute("id") or "").lower()
                            sel_name = (sel.get_attribute("name") or "").lower()
                            sel_class = (sel.get_attribute("class") or "").lower()

                            if any(
                                w in sel_id or w in sel_name or w in sel_class
                                for w in keyword_words
                            ):
                                # Prefer wrapper if hidden/custom dropdown (select2/chosen)
                                if not sel.is_visible():
                                    wrapper = self._find_custom_dropdown_wrapper(sel)
                                    if wrapper:
                                        print(
                                            f"         ✅ Keyword fallback: wrapper for hidden '{label_text}' via select id/name containing {keyword_words}"
                                        )
                                        return wrapper
                                if sel.is_visible():
                                    print(
                                        f"         ✅ Keyword fallback: found select for '{label_text}' via id/name containing {keyword_words}"
                                    )
                                    return sel
                                # If hidden and no wrapper found, still return select (JS fill may work)
                                print(
                                    f"         ⚠️ Keyword fallback: returning hidden select for '{label_text}' (no wrapper found)"
                                )
                                return sel
                        except:
                            continue
            except Exception:
                pass

        # ========================================
        # PRIORITY 0: Direct ID/Name Match (Highest Priority)
        # Tìm element có ID hoặc name khớp với label (underscore/hyphen format)
        # VD: "Boost Result Value2" -> ID "boost_result_value2"
        # [FIX] Skip nếu label chứa ký tự đặc biệt CSS (parentheses, brackets, etc.)
        # VD: "PreEvent Phase Start Date Time(UTC)" chứa () → crash CSS selector
        # ========================================
        _has_css_special = bool(re.search(r'[()\[\]{}#.>+~:,\'"\\]', label_lower))
        if not _has_css_special:
            label_id_format = label_lower.replace(" ", "_").replace("-", "_")

            # CSS selector "#5_star" is invalid (id starts with digit).
            # Use attribute selector [id='...'] which is safe.
            if label_id_format and str(label_id_format)[0].isdigit():
                direct_by_id = page.locator(
                    f"[id='{label_id_format}'], [name='{label_id_format}']"
                ).first
            else:
                direct_by_id = page.locator(
                    f"#{label_id_format}, [name='{label_id_format}']"
                ).first

            if direct_by_id.count() > 0 and direct_by_id.is_visible():
                tag = (direct_by_id.evaluate("el => el.tagName") or "").lower()
                href = direct_by_id.get_attribute("href") or ""
                cls = direct_by_id.get_attribute("class") or ""
                is_nav_link = tag == "a" and ("navigate" in cls or href.startswith("#"))
                if is_nav_link:
                    print(
                        f"         ⚠️ Skip nav link #{label_id_format} "
                        f"(sidebar tab, not form toggle)"
                    )
                else:
                    print(f"         🎯 DIRECT MATCH by ID/name: '{label_id_format}'")
                    return direct_by_id

            # Try with hyphens too
            label_id_hyphen = label_lower.replace(" ", "-").replace("_", "-")

            if label_id_hyphen and str(label_id_hyphen)[0].isdigit():
                direct_by_id_hyphen = page.locator(
                    f"[id='{label_id_hyphen}'], [name='{label_id_hyphen}']"
                ).first
            else:
                direct_by_id_hyphen = page.locator(
                    f"#{label_id_hyphen}, [name='{label_id_hyphen}']"
                ).first

            if direct_by_id_hyphen.count() > 0 and direct_by_id_hyphen.is_visible():
                tag = (direct_by_id_hyphen.evaluate("el => el.tagName") or "").lower()
                href = direct_by_id_hyphen.get_attribute("href") or ""
                cls = direct_by_id_hyphen.get_attribute("class") or ""
                is_nav_link = tag == "a" and ("navigate" in cls or href.startswith("#"))
                if not is_nav_link:
                    print(
                        f"         🎯 DIRECT MATCH by ID/name (hyphen): '{label_id_hyphen}'"
                    )
                    return direct_by_id_hyphen

        # ========================================
        # SECTION-AWARE SEARCH: Handle "Section Name Field Name" patterns
        # VD: "PreEvent Phase Start Date Time(UTC)" → section="PreEvent Phase", field="Start Date Time(UTC)"
        # VD: "Active Phase End Date Time (UTC)" → section="Active Phase", field="End Date Time (UTC)"
        # ========================================
        section_result = self._try_section_aware_search(page, label_text)
        if section_result:
            return section_result

        # ========================================
        # SPECIAL CASE: "New Event ID", "New ID", "New Section ID"
        # Form Clone có input với placeholder chứa "suffix" hoặc label chứa "New"
        # ========================================
        if "new" in label_lower and "id" in label_lower:
            # Case 1: Tìm input có placeholder chứa "suffix"
            suffix_input = page.locator("input[placeholder*='suffix' i]").first
            if suffix_input.count() > 0 and suffix_input.is_visible():
                print(f"         🎯 Found suffix input for '{label_text}'")
                return suffix_input

            # Case 2: Tìm input có placeholder chứa "new" hoặc name chứa "new"
            new_input = page.locator(
                "input[placeholder*='new' i], input[name*='new' i]"
            ).first
            if new_input.count() > 0 and new_input.is_visible():
                print(
                    f"         🎯 Found new input by placeholder/name for '{label_text}'"
                )
                return new_input

            # Case 3: Fallback - Tìm input trong row chứa label "New ... ID"
            row = (
                page.locator("tr, div.form-group, div.row, div.col")
                .filter(has_text=re.compile(r"New.*ID", re.IGNORECASE))
                .first
            )
            if row.count() > 0:
                input_in_row = row.locator(
                    "input[type='text']:visible"
                ).last  # Lấy cái cuối (suffix)
                if input_in_row.count() > 0:
                    print(f"         🎯 Found input in row for '{label_text}'")
                    return input_in_row

        safe_label = re.compile(re.escape(label_text), re.IGNORECASE)

        # [FIX] PREMIER STRATEGY: Trước hết tìm label + parent container + element trong container đó
        # Đây là cách đáng tin cậy nhất để tránh bỏ qua hoặc chọn nhầm
        try:
            label_candidates = (
                page.locator("label, legend, span, h5, th, strong, div, b")
                .filter(has_text=safe_label)
                .all()
            )
            visible_candidates = [c for c in label_candidates if c.is_visible()]

            # [FIX] Sort candidates: exact match first, then by text length (shorter = more precise)
            def _premier_sort_key(el):
                try:
                    txt = el.inner_text().strip().lower()
                    is_exact = txt == label_lower
                    tag = el.evaluate("el => el.tagName")
                    is_label_tag = tag in ["LABEL", "LEGEND"]
                    return (0 if is_exact else 1, 0 if is_label_tag else 1, len(txt))
                except:
                    return (2, 2, 9999)

            visible_candidates.sort(key=_premier_sort_key)

            print(
                f"         📋 Found {len(visible_candidates)} visible label candidates"
            )

            # [NEW] Sắp xếp candidates theo độ match
            for label_el in visible_candidates:
                label_actual_text = label_el.inner_text().strip()

                # [DEBUG] Log which label was checked
                if label_actual_text.lower() == label_lower:
                    print(f"         ✅ Exact label match: '{label_actual_text}'")
                else:
                    print(f"         ~ Partial match: '{label_actual_text[:50]}...'")

                # [CRITICAL] TRỪ CASE: Label chứa radio (skip nếu không exact match)
                has_radio = label_el.locator("input[type='radio']").count() > 0
                if has_radio and label_actual_text.lower() != label_lower:
                    print(f"         ⏭️ Skip (radio label without exact match)")
                    continue

                # [NEW STRATEGY] Tìm parent container (form-group)
                # LUÔN tìm input/select TRONG container này trước, không dùng fallback
                parent_containers = None
                container_source = None
                # [FIX] When inside a modal, try input-group BEFORE row.
                # Clone modal Gate uses div.input-group (not div.form-group).
                # Without this, ancestor::row escapes the modal and picks
                # the main-page's <select id="gate"> (40+ elements) instead
                # of the modal's <select id="id_clone_gate">.
                # Only applies inside modals to avoid breaking regular-page selects.
                _container_xpaths = [
                    "xpath=ancestor::div[contains(@class,'form-group')]",
                    "xpath=ancestor::div[contains(@class,'control-group')]",
                    "xpath=ancestor::fieldset",
                ]
                if _in_modal:
                    _container_xpaths.append(
                        "xpath=ancestor::div[contains(@class,'input-group')"
                        " and not(contains(@class,'input-group-prepend'))"
                        " and not(contains(@class,'input-group-append'))"
                        " and not(contains(@class,'input-group-text'))]"
                    )
                _container_xpaths.append("xpath=ancestor::div[contains(@class,'row')]")
                for xpath in _container_xpaths:
                    try:
                        container = label_el.locator(xpath).first
                        if container.count() > 0 and container.is_visible():
                            parent_containers = container
                            container_source = xpath
                            print(f"         🔗 Found parent container: {xpath}")
                            break
                    except:
                        pass

                if parent_containers:
                    # [FIX] Multiselect (Vue multiselect / custom-vue-multiselect)
                    # "Book Texture Icon" is rendered as <div class="multiselect">...</div>
                    # and the underlying <input> is hidden (style width:0/absolute),
                    # so searching only input/select/textarea will miss it.
                    try:
                        multiselect_box = parent_containers.locator(
                            "div.multiselect"
                        ).first
                        if multiselect_box.count() > 0:
                            # Return the visible wrapper if possible; otherwise still return it
                            if multiselect_box.is_visible():
                                print(
                                    f"         ✅ Found multiselect wrapper for '{label_text}' via fieldset container"
                                )
                                return multiselect_box
                            # Even if not visible, it can still be interacted with using force later
                            print(
                                f"         ⚠️ Found multiselect wrapper for '{label_text}' but it's not visible; returning anyway"
                            )
                            return multiselect_box
                    except:
                        pass

                    # [CRITICAL] Tìm input/select TRONG container này
                    # Không dùng fallback
                    elements = parent_containers.locator(
                        "select, input:not([type='radio']):not([type='button']):not([type='hidden']), textarea"
                    ).all()

                    print(
                        f"         📦 Found {len(elements)} input/select elements in container"
                    )

                    if len(elements) > 0:
                        # [FIX] PRE-SCAN: Tìm hidden SELECT (bị ẩn bởi Chosen.js/Select2) TRƯỚC
                        # Vì select gốc bị ẩn (display:none), code không tìm được nếu chỉ xét visible
                        # VD: select#id_event_type bị Chosen.js ẩn -> phải tìm wrapper của nó
                        _pre_scan_label_norm = label_lower.replace(" ", "_").replace(
                            "-", "_"
                        )
                        _pre_scan_words = [
                            w for w in _pre_scan_label_norm.split("_") if len(w) > 2
                        ]
                        for _el in elements:
                            if (
                                not _el.is_visible()
                                and _el.evaluate("el => el.tagName") == "SELECT"
                            ):
                                _el_name = (_el.get_attribute("name") or "").lower()
                                _el_id = (_el.get_attribute("id") or "").lower()
                                _ps_related = False
                                if (
                                    _pre_scan_label_norm in _el_name
                                    or _pre_scan_label_norm in _el_id
                                ):
                                    _ps_related = True
                                elif _el_name and _el_name in _pre_scan_label_norm:
                                    _ps_related = True
                                elif _el_id and _el_id in _pre_scan_label_norm:
                                    _ps_related = True
                                else:
                                    for _pw in _pre_scan_words:
                                        # Phải khớp cả từ (whole-word) trong name/id, không chỉ substring
                                        _name_parts = re.split(r"[_\-\s]", _el_name)
                                        _id_parts = re.split(r"[_\-\s]", _el_id)
                                        if _pw in _name_parts or _pw in _id_parts:
                                            _ps_related = True
                                            break
                                        if _pw.endswith("s") and (
                                            _pw[:-1] in _name_parts
                                            or _pw[:-1] in _id_parts
                                        ):
                                            _ps_related = True
                                            break
                                if _ps_related:
                                    _wrapper = self._find_custom_dropdown_wrapper(_el)
                                    if _wrapper:
                                        print(
                                            f"         ✅ Found Chosen/Select2 wrapper for hidden SELECT: name='{_el_name}', id='{_el_id}'"
                                        )
                                        return _wrapper
                                    else:
                                        print(
                                            f"         ⚠️ Hidden SELECT matched (name='{_el_name}') but no wrapper found, continuing..."
                                        )

                        # [FIX] Tìm element VISIBLE đầu tiên, KHÔNG lấy mù elements[0]
                        element = None
                        for _el in elements:
                            if _el.is_visible():
                                # [FIX] Validate: element name/id phải liên quan đến label
                                _el_name = (_el.get_attribute("name") or "").lower()
                                _el_id = (_el.get_attribute("id") or "").lower()
                                _el_tag = _el.evaluate("el => el.tagName")
                                _label_norm = label_lower.replace(" ", "_").replace(
                                    "-", "_"
                                )
                                _label_words = [
                                    w for w in _label_norm.split("_") if len(w) > 2
                                ]

                                # Check if element is related to label
                                _is_related = False
                                # Direct name/id match
                                if _label_norm in _el_name or _label_norm in _el_id:
                                    _is_related = True
                                elif _el_name in _label_norm and _el_name:
                                    _is_related = True
                                elif _el_id in _label_norm and _el_id:
                                    _is_related = True
                                else:
                                    # Word-level match (whole-word only, không dùng substring)
                                    # VD: "type" KHÔNG được match "time_deduct_type" (chỉ match "event_type")
                                    _el_name_parts = set(re.split(r"[_\-\s]", _el_name))
                                    _el_id_parts = set(re.split(r"[_\-\s]", _el_id))
                                    for _w in _label_words:
                                        if _w in _el_name_parts or _w in _el_id_parts:
                                            _is_related = True
                                            break
                                        # Singular form (schedules -> schedule)
                                        if _w.endswith("s") and (
                                            _w[:-1] in _el_name_parts
                                            or _w[:-1] in _el_id_parts
                                        ):
                                            _is_related = True
                                            break

                                # Nếu container nhỏ (form-group/control-group) VÀ ít elements, accept thậm chí không related
                                # [FIX] Thêm điều kiện len(elements) <= 4 để tránh chọn nhầm trong container lớn
                                # VD: PreEvent Phase control-group có 14 elements → KHÔNG phải tight container
                                _is_tight_container = (
                                    container_source
                                    in [
                                        "xpath=ancestor::div[contains(@class,'form-group')]",
                                        "xpath=ancestor::div[contains(@class,'control-group')]",
                                        "xpath=ancestor::fieldset",
                                    ]
                                    and len(elements) <= 4
                                )

                                if _is_related or _is_tight_container:
                                    element = _el
                                    break
                                else:
                                    print(
                                        f"         ⏭️ Skip visible but unrelated element: tag={_el_tag}, name='{_el_name}', id='{_el_id}'"
                                    )

                        if not element and len(elements) <= 3:
                            # Fallback: nếu tất cả visible elements đều không related VÀ container nhỏ (<=3)
                            # [FIX] Chỉ fallback khi container thực sự nhỏ, tránh chọn nhầm trong container lớn
                            for _el in elements:
                                if _el.is_visible():
                                    element = _el
                                    print(
                                        f"         ⚠️ Using first visible element as fallback (small container: {len(elements)} elements)"
                                    )
                                    break

                        if not element:
                            print(
                                f"         ⚠️ All {len(elements)} elements in container are hidden, skip"
                            )
                            continue

                        print(f"         ✅ Found element in same form-group container")

                        # Validate: Kiểm tra element name/id có liên quan đến label không
                        el_name = element.get_attribute("name") or ""
                        el_id = element.get_attribute("id") or ""
                        el_type = element.evaluate("el => el.tagName") or "UNKNOWN"

                        print(
                            f"         🔍 Element: tag={el_type}, name='{el_name}', id='{el_id}'"
                        )

                        # Nếu element là select, check name/id để tránh nhầm lẫn
                        if el_type == "SELECT":
                            el_name_norm = el_name.lower().replace("-", "_")
                            el_id_norm = el_id.lower().replace("-", "_")
                            label_norm = label_lower.replace(" ", "_").replace("-", "_")

                            # [FIX] More strict validation - check if any significant word from label appears in element name/id
                            # VD: "Leaderboard Types" -> words: ["leaderboard", "types", "type"]
                            label_words = label_norm.split("_")
                            # Remove common words that don't add meaning
                            meaningful_words = [
                                w
                                for w in label_words
                                if len(w) > 2 and w not in ["the", "and", "for"]
                            ]

                            # Also check singular form (types -> type)
                            expanded_words = meaningful_words.copy()
                            for word in meaningful_words:
                                if word.endswith("s"):
                                    expanded_words.append(word.rstrip("s"))

                            # Check if ANY meaningful word from label appears in element name/id
                            is_related = False
                            for word in expanded_words:
                                if word in el_name_norm or word in el_id_norm:
                                    is_related = True
                                    break

                            # [DEBUG] Log validation details
                            print(
                                f"         🔬 Validation: label_norm='{label_norm}', meaningful_words={meaningful_words}"
                            )
                            print(
                                f"         🔬 Element: name_norm='{el_name_norm}', id_norm='{el_id_norm}'"
                            )
                            print(f"         ✓ Related: {is_related}")

                            # [FIX] Nếu name/id không match NHƯNG chỉ có 1 element duy nhất trong container
                            # → Cho phép vì có thể đây là field đúng (tránh bỏ qua)
                            if not is_related:
                                if len(elements) == 1:
                                    print(
                                        f"         ⚠️ Element name/id không match label, NHƯNG chỉ có 1 element → Accept"
                                    )
                                    is_related = True  # Override
                                else:
                                    print(
                                        f"         ⚠️ Element name/id không match label, skip container này"
                                    )
                                    continue

                        # Element tìm thấy trong container - check if visible
                        if not element.is_visible():
                            # Hidden SELECT - tìm wrapper
                            if el_type == "SELECT":
                                wrapper = self._find_custom_dropdown_wrapper(element)
                                if wrapper:
                                    print(
                                        f"         ✅ Found wrapper for hidden SELECT"
                                    )
                                    return wrapper

                        print(f"         ✅ Returning element from container search")
                        return element
        except Exception as e:
            print(f"         ⚠️ Container-based search error: {e}")

        # ─── BOOTSTRAP INPUT-GROUP: span.input-group-text as pseudo-label ────────────
        # Handles: <div class="input-group">
        #            <div class="input-group-prepend"><span class="input-group-text">Offer Name</span></div>
        #            <input type="text" class="form-control" name="name">
        #          </div>
        # The span has no 'for' attr so it's missed by normal label→for flow.
        try:
            igt_spans = page.locator("span.input-group-text, .input-group-prepend span").all()
            for span in igt_spans:
                if not span.is_visible():
                    continue
                span_text = span.inner_text().strip().lower()
                span_normalized = re.sub(r"[\s_-]+", "", span_text)
                if span_text == label_lower or span_normalized == label_normalized:
                    input_group = span.locator(
                        "xpath=ancestor::div[contains(@class,'input-group')"
                        " and not(contains(@class,'input-group-prepend'))"
                        " and not(contains(@class,'input-group-append'))"
                        " and not(contains(@class,'input-group-text'))]"
                    ).first
                    if input_group.count() > 0:
                        inp = input_group.locator("input, textarea").first
                        if inp.count() > 0 and inp.is_visible():
                            print(f"         🎯 Bootstrap input-group match: '{span_text}' → input")
                            return inp
        except Exception:
            pass
        # ─────────────────────────────────────────────────────────────────────────────

        # [OLD CODE] Fallback đến label candidates search
        candidates = (
            page.locator("label, legend, span, h5, th, strong, div, b")
            .filter(has_text=safe_label)
            .all()
        )
        visible_candidates = [c for c in candidates if c.is_visible()]

        # [NEW] FUZZY MATCHING: Nếu không tìm thấy exact match, tìm fuzzy match
        # VD: "New SectionID" sẽ match với "New Section ID"
        if not visible_candidates:
            all_labels = page.locator("label, legend, span, h5, th, strong").all()
            for lbl in all_labels:
                if lbl.is_visible():
                    lbl_text = lbl.inner_text().strip().lower()
                    lbl_normalized = re.sub(r"[\s_-]+", "", lbl_text)
                    if lbl_normalized == label_normalized:
                        visible_candidates.append(lbl)
                        print(
                            f"         🔍 Fuzzy Match: '{label_text}' matched with '{lbl.inner_text()}'"
                        )

        # SORT: Ưu tiên EXACT MATCH (text ngắn nhất khớp với label_text)
        # Sau đó ưu tiên thẻ LABEL hoặc LEGEND
        def sort_key(el):
            text = el.inner_text().strip().lower()
            is_exact = text == label_lower
            tag = el.evaluate("el => el.tagName")
            is_label_or_legend = tag in ["LABEL", "LEGEND"]
            text_len = len(text)
            # Ưu tiên: exact match -> label/legend tag -> text ngắn nhất
            return (0 if is_exact else 1, 0 if is_label_or_legend else 1, text_len)

        visible_candidates.sort(key=sort_key)

        print(f"         📋 Found {len(visible_candidates)} label candidates")

        for label_el in visible_candidates:
            # ========================================
            # [FIX] SKIP: Label chứa RADIO BUTTON
            # Tránh việc tìm "Currency" mà click nhầm vào radio "Auto Generate a new currency"
            # ========================================
            has_radio = label_el.locator("input[type='radio']").count() > 0
            if has_radio:
                # Chỉ skip nếu text KHÔNG khớp chính xác
                label_text_actual = label_el.inner_text().strip().lower()
                if label_text_actual != label_text.lower():
                    print(
                        f"         ⏭️ Skip radio label: '{label_el.inner_text().strip()[:30]}...'"
                    )
                    continue

            # [NEW] SPECIAL: Nếu là LEGEND tag, tìm trong parent fieldset
            tag = label_el.evaluate("el => el.tagName")
            if tag == "LEGEND":
                try:
                    # Tìm fieldset chứa legend này
                    fieldset = label_el.locator("xpath=ancestor::fieldset").first
                    if fieldset.count() > 0:
                        # Tìm multiselect wrapper trong fieldset
                        multiselect = fieldset.locator("div.multiselect").first
                        if multiselect.count() > 0 and multiselect.is_visible():
                            print(
                                f"         🎯 Found multiselect in fieldset for legend '{label_text}'"
                            )
                            return multiselect

                        # Tìm select/input trong fieldset
                        field = fieldset.locator(
                            "select, input:not([type='radio']), textarea"
                        ).first
                        if field.count() > 0:
                            # Nếu select ẩn, tìm wrapper
                            if (
                                not field.is_visible()
                                and field.evaluate("el => el.tagName") == "SELECT"
                            ):
                                wrapper = self._find_custom_dropdown_wrapper(field)
                                if wrapper:
                                    return wrapper
                            return field
                except:
                    pass

            # A. Check 'for' attribute (HIGHEST PRIORITY)
            for_attr = label_el.get_attribute("for")
            if for_attr:
                print(f"         🔗 Label has for='{for_attr}'")
                target = page.locator(f"#{for_attr}").first
                if target.count() > 0:
                    # [FIX] Skip nếu target là radio
                    target_type = target.get_attribute("type")
                    if target_type == "radio":
                        print(f"         ⏭️ Skip radio target for '{for_attr}'")
                        continue

                    # [FIX CRITICAL] Validate target match với label text
                    # Tránh trường hợp tìm nhầm element không liên quan
                    # VD: Label "Leaderboard Types" có for="tag" nhưng tag là field khác
                    try:
                        # Kiểm tra xem target có phải là field đúng không bằng cách:
                        # 1. So sánh name attribute với label text
                        # 2. So sánh id với label text (normalized)
                        target_id = target.get_attribute("id") or ""
                        target_name = target.get_attribute("name") or ""

                        # Normalize label và target để so sánh
                        label_normalized = label_lower.replace(" ", "_").replace(
                            "-", "_"
                        )
                        id_normalized = target_id.replace("-", "_").lower()
                        name_normalized = target_name.replace("-", "_").lower()

                        # Check if target ID/name relates to label
                        is_related = (
                            label_normalized in id_normalized
                            or id_normalized in label_normalized
                            or label_normalized in name_normalized
                            or name_normalized in label_normalized
                        )

                        if not is_related:
                            # ID/name không liên quan → Có thể tìm nhầm
                            print(
                                f"         ⚠️ Target id/name ('{target_id}'/'{target_name}') doesn't match label '{label_text}'"
                            )
                            print(f"         🔍 Searching for better match...")

                            # Tìm element có ID/name khớp với label
                            # VD: "Leaderboard Types" → tìm id="leaderboard_type" hoặc name="leaderboard_type"
                            better_match = None

                            # Pattern 1: leaderboard_type, leaderboard-type, leaderboardtype
                            id_patterns = [
                                label_normalized,
                                label_normalized.rstrip("s"),  # "types" -> "type"
                                label_lower.replace(" ", "_"),
                                label_lower.replace(" ", "-"),
                                label_lower.replace(" ", ""),
                            ]

                            # [FIX] Thu thập TẤT CẢ candidates match pattern
                            all_candidates = []

                            for pattern in id_patterns:
                                # Try by ID - collect all matches
                                candidates_by_id = page.locator(
                                    f"#{pattern}, [id*='{pattern}']"
                                ).all()
                                for cand in candidates_by_id:
                                    if cand.is_visible():
                                        all_candidates.append(("id", pattern, cand))

                                # Try by name - collect all matches
                                candidates_by_name = page.locator(
                                    f"[name='{pattern}'], [name*='{pattern}']"
                                ).all()
                                for cand in candidates_by_name:
                                    if cand.is_visible():
                                        all_candidates.append(("name", pattern, cand))

                            if all_candidates:
                                print(
                                    f"         📋 Found {len(all_candidates)} potential matches"
                                )

                                # [STRATEGY 1] Chọn candidate TRONG CÙNG CONTAINER với label
                                label_containers = []
                                try:
                                    for container_xpath in [
                                        "xpath=ancestor::div[contains(@class,'form-group')]",
                                        "xpath=ancestor::div[contains(@class,'control-group')]",
                                        "xpath=ancestor::fieldset",
                                        "xpath=ancestor::div[contains(@class,'row')]",
                                        "xpath=../..",  # 2 levels up
                                    ]:
                                        container = label_el.locator(
                                            container_xpath
                                        ).first
                                        if container.count() > 0:
                                            label_containers.append(container)
                                except:
                                    pass

                                # Check candidates trong container
                                for match_type, pattern, cand in all_candidates:
                                    for label_container in label_containers:
                                        try:
                                            # Check if candidate is child of label's container
                                            container_inputs = label_container.locator(
                                                "select, input"
                                            ).all()
                                            for ci in container_inputs:
                                                try:
                                                    if ci.evaluate(
                                                        "(el, other) => el.isSameNode(other)",
                                                        cand,
                                                    ):
                                                        better_match = cand
                                                        print(
                                                            f"         ✅ Found match in same container by {match_type}: '{pattern}'"
                                                        )
                                                        break
                                                except:
                                                    pass
                                            if better_match:
                                                break
                                        except:
                                            pass
                                    if better_match:
                                        break

                                # [STRATEGY 2] Nếu không tìm được trong container, chọn GẦN NHẤT với label
                                if not better_match:
                                    try:
                                        label_box = label_el.bounding_box()
                                        if label_box:
                                            min_distance = float("inf")
                                            closest_candidate = None

                                            for (
                                                match_type,
                                                pattern,
                                                cand,
                                            ) in all_candidates:
                                                try:
                                                    cand_box = cand.bounding_box()
                                                    if cand_box:
                                                        # Tính khoảng cách
                                                        distance = abs(
                                                            cand_box["x"]
                                                            - label_box["x"]
                                                        ) + abs(
                                                            cand_box["y"]
                                                            - label_box["y"]
                                                        )

                                                        # Ưu tiên field DƯỚI hoặc PHẢI label
                                                        is_below_or_right = (
                                                            cand_box["y"]
                                                            >= label_box["y"] - 50
                                                        )

                                                        if (
                                                            distance < min_distance
                                                            and is_below_or_right
                                                        ):
                                                            min_distance = distance
                                                            closest_candidate = (
                                                                match_type,
                                                                pattern,
                                                                cand,
                                                            )
                                                except:
                                                    pass

                                            if closest_candidate:
                                                match_type, pattern, cand = (
                                                    closest_candidate
                                                )
                                                better_match = cand
                                                print(
                                                    f"         ✅ Found closest match by {match_type} ({min_distance:.0f}px): '{pattern}'"
                                                )
                                    except:
                                        pass

                                # [STRATEGY 3] Fallback: Lấy candidate đầu tiên
                                if not better_match and all_candidates:
                                    match_type, pattern, cand = all_candidates[0]
                                    better_match = cand
                                    print(
                                        f"         ⚠️ Using first match by {match_type}: '{pattern}'"
                                    )

                            if better_match:
                                target = better_match
                            else:
                                print(
                                    f"         ⚠️ No better match found, using original target #{for_attr}"
                                )

                    except Exception as validate_err:
                        print(f"         ⚠️ Validation error: {validate_err}")
                        # Continue with original target

                    print(
                        f"         ✅ Found target by for attribute: #{target.get_attribute('id') or for_attr}"
                    )

                    # Nếu target bị ẩn (Select), thử tìm wrapper ngay lập tức
                    if not target.is_visible():
                        tag_name = target.evaluate("el => el.tagName")
                        if tag_name == "SELECT":
                            print(
                                f"         🔍 Target is hidden SELECT, looking for wrapper..."
                            )
                            wrapper = self._find_custom_dropdown_wrapper(target)
                            if wrapper:
                                print(f"         ✅ Found custom dropdown wrapper")
                                return wrapper
                    return target

            # B. Check Input lồng bên trong (SKIP RADIO)
            nested = label_el.locator(
                "input:not([type='radio']), select, textarea"
            ).first
            if nested.count() > 0:
                if (
                    not nested.is_visible()
                    and nested.evaluate("el => el.tagName") == "SELECT"
                ):
                    wrapper = self._find_custom_dropdown_wrapper(nested)
                    if wrapper:
                        return wrapper
                return nested

            # C. Check Sibling (Input/Select2/Chosen/Multiselect nằm ngay sau Label)
            # [FIX]: Loại bỏ radio khỏi xpath, thêm multiselect
            sibling = label_el.locator(
                "xpath=following::input[not(@type='radio')] | following::select | following::textarea | following::span[contains(@class,'select2-container')] | following::div[contains(@class,'chosen-container')] | following::div[contains(@class,'multiselect')]"
            ).first

            if sibling.count() > 0:
                # Nếu tìm thấy wrapper hiển thị ngay -> Trả về
                if sibling.is_visible():
                    return sibling

                # Nếu tìm thấy select ẩn -> Tìm wrapper của nó
                tag = None
                try:
                    tag = sibling.evaluate("el => el.tagName")
                except:
                    pass

                if tag == "SELECT" and not sibling.is_visible():
                    wrapper = self._find_custom_dropdown_wrapper(sibling)
                    if wrapper:
                        return wrapper
                return sibling

            try:
                parent = label_el.locator("xpath=..")
                cousin = parent.locator("input, select, textarea").first
                if cousin.count() > 0:
                    return cousin
            except:
                pass

        placeholder = page.locator(f"[placeholder='{label_text}']").first
        if placeholder.count() > 0:
            return placeholder

        # [NEW] Fallback: Tìm dropdown wrapper gần với label text
        # Dùng cho trường hợp không tìm được bằng cách thông thường
        try:
            # Tìm tất cả dropdown wrappers hiển thị
            wrappers = page.locator(
                "div.multiselect, div.chosen-container, span.select2-container"
            ).all()
            visible_wrappers = [w for w in wrappers if w.is_visible()]

            if visible_wrappers:
                # Tìm wrapper gần nhất với text label
                for wrapper in visible_wrappers:
                    try:
                        # Check xem có text label gần wrapper này không
                        parent = wrapper.locator(
                            "xpath=ancestor::div[@class='form-group'] | ancestor::fieldset | ancestor::div[contains(@class,'col')]"
                        ).first
                        if parent.count() > 0:
                            parent_text = parent.inner_text().lower()
                            if label_lower in parent_text:
                                print(
                                    f"         🎯 Found wrapper by proximity for '{label_text}'"
                                )
                                return wrapper
                    except:
                        pass
        except:
            pass

        # [NEW] Fallback 2: Tìm select element hiển thị có label gần
        # [IMPROVED] Hạn chế scope để tránh bỏ qua field đúng
        try:
            selects = page.locator("select:visible").all()
            # [FIX] Sort selects by proximity to visible labels (làm giảm false matches)
            label_candidates_boxes = []
            for cand in visible_candidates:
                try:
                    box = cand.bounding_box()
                    if box:
                        label_candidates_boxes.append(box)
                except:
                    pass

            for sel in selects:
                try:
                    # [CRITICAL] Nếu select có name/id khác biệt xa so với label, BỎ QUA
                    # VD: Label "Leaderboard Types" không nên match select có name="rbe_id"
                    sel_name = sel.get_attribute("name") or ""
                    sel_id = sel.get_attribute("id") or ""

                    # Check if select name/id is related to label
                    sel_name_normalized = sel_name.lower().replace("-", "_")
                    sel_id_normalized = sel_id.lower().replace("-", "_")
                    label_normalized = label_lower.replace(" ", "_")

                    # Build list of acceptable name patterns
                    acceptable_patterns = [
                        label_normalized,  # "leaderboard_types"
                        label_normalized.rstrip("s"),  # "leaderboard_type"
                        label_lower.replace(" ", "_"),  # "leaderboard_types"
                        label_lower.replace(" ", "-").lower(),  # "leaderboard-types"
                    ]

                    is_related = False
                    for pattern in acceptable_patterns:
                        if (
                            pattern in sel_name_normalized
                            or pattern in sel_id_normalized
                        ):
                            is_related = True
                            break

                    if not is_related:
                        # Select name/id không liên quan đến label -> BỎ QUA
                        print(
                            f"         ⏭️ Skip unrelated select (name='{sel_name}', id='{sel_id}')"
                        )
                        continue

                    # Tìm label gần select này
                    parent = sel.locator(
                        "xpath=ancestor::div[@class='form-group'] | ancestor::div[contains(@class,'col')]"
                    ).first
                    if parent.count() > 0:
                        parent_text = parent.inner_text().lower()
                        if label_lower in parent_text:
                            print(
                                f"         🎯 Found select by proximity for '{label_text}'"
                            )
                            return sel
                except:
                    pass
        except:
            pass

        print(f"         ❌ Could not find input for '{label_text}'")
        print(f"         💡 Available labels on page:")
        try:
            all_page_labels = page.locator("label:visible").all()[:10]  # First 10
            for lbl in all_page_labels:
                lbl_text = lbl.inner_text().strip()
                lbl_for = lbl.get_attribute("for")
                print(f"            - '{lbl_text[:50]}' (for='{lbl_for}')")
        except:
            pass

        return None

    # ============================
    # SECTION-AWARE FIELD SEARCH
    # ============================
    def _try_section_aware_search(self, page, label_text):
        """
        Tách label thành Section + Field name nếu có prefix section.
        VD: "PreEvent Phase Start Date Time(UTC)" → section="PreEvent Phase", field="Start Date Time(UTC)"
        VD: "Active Phase End Date Time (UTC)" → section="Active Phase", field="End Date Time (UTC)"
        """
        section_prefixes = [
            "PreEvent Phase",
            "Pre-Event Phase",
            "Pre Event Phase",
            "Active Phase",
            "Post Event Settings",
            "Post Event",
        ]

        for prefix in section_prefixes:
            if label_text.lower().startswith(prefix.lower()):
                # Tách field name (phần còn lại sau prefix)
                field_name = label_text[len(prefix) :].strip()
                if field_name:
                    print(
                        f"         🔍 Section-aware: section='{prefix}', field='{field_name}'"
                    )
                    result = self._find_field_in_section(page, prefix, field_name)
                    if result:
                        return result
        return None

    def _find_field_in_section(self, page, section_name, field_name):
        """
        Tìm input trong một section cụ thể (dùng khi có nhiều section
        có cùng label name, VD: PreEvent Phase vs Active Phase đều có
        "Start Date Time (UTC)")
        """
        try:
            section_lower = section_name.lower().strip()
            field_lower = field_name.lower().strip()

            # ========================================
            # STRATEGY 1: Tìm fieldset/div có header chứa section name
            # ========================================
            container_selectors = [
                "fieldset",
                "div.card",
                "div.panel",
                "div[class*='phase']",
                "div[class*='section']",
                "div.form-section",
                "div.card-body",
            ]

            for sel in container_selectors:
                containers = page.locator(sel).all()

                for container in containers:
                    if not container.is_visible():
                        continue

                    # Kiểm tra xem container có chứa section name trong header không
                    container_text = ""
                    try:
                        container_text = container.inner_text()[:200].lower()
                    except:
                        continue

                    if section_lower not in container_text:
                        continue

                    # Verify là header section (không phải chỉ mentioned trong content)
                    has_section_header = False
                    try:
                        headers = container.locator(
                            "legend, h2, h3, h4, h5, strong, b, .card-header, .panel-heading"
                        ).all()
                        for h in headers:
                            if (
                                h.is_visible()
                                and section_lower in h.inner_text().lower()
                            ):
                                has_section_header = True
                                break
                    except:
                        pass

                    if not has_section_header:
                        continue

                    print(f"         📍 Found section container: '{section_name}'")

                    # Tìm field trong container này
                    field_regex = re.compile(re.escape(field_name), re.IGNORECASE)

                    # Tìm label trong container
                    labels = (
                        container.locator("label, legend, span, strong, b")
                        .filter(has_text=field_regex)
                        .all()
                    )
                    visible_labels = [l for l in labels if l.is_visible()]
                    visible_labels.sort(key=lambda el: len(el.inner_text().strip()))

                    for lbl in visible_labels:
                        lbl_text = lbl.inner_text().strip()
                        if len(lbl_text) > len(field_name) * 3:
                            continue

                        # Tìm input liên kết
                        for_attr = lbl.get_attribute("for")
                        if for_attr:
                            target = page.locator(f"#{for_attr}").first
                            if target.count() > 0:
                                if not target.is_visible():
                                    wrapper = self._find_custom_dropdown_wrapper(target)
                                    if wrapper:
                                        return wrapper
                                print(
                                    f"         ✅ [Section] Found by 'for' attr: #{for_attr}"
                                )
                                return target

                        # Input lồng bên trong label
                        nested = lbl.locator(
                            "input:not([type='radio']), select, textarea"
                        ).first
                        if nested.count() > 0:
                            return nested

                        # Sibling input
                        sibling = lbl.locator(
                            "xpath=following::input[not(@type='radio')][1] | following::select[1]"
                        ).first
                        if sibling.count() > 0 and sibling.is_visible():
                            # Verify sibling is within same section container
                            try:
                                sib_box = sibling.bounding_box()
                                cont_box = container.bounding_box()
                                if sib_box and cont_box:
                                    if (
                                        sib_box["y"] >= cont_box["y"]
                                        and sib_box["y"]
                                        <= cont_box["y"] + cont_box["height"]
                                    ):
                                        print(
                                            f"         ✅ [Section] Found sibling input for '{field_name}'"
                                        )
                                        return sibling
                            except:
                                return sibling

                    # Fallback: Tìm datetime inputs trong section (theo thứ tự Start/End)
                    datetime_inputs = container.locator(
                        "input.flatpickr-input, input[data-toggle='flatpickr'], "
                        "input[data-toggle='datetimepicker'], input.datetimepicker, "
                        "input.datepicker, input[type='datetime-local']"
                    ).all()
                    visible_dt = [i for i in datetime_inputs if i.is_visible()]

                    # Cũng tìm thêm text inputs có khả năng là datetime
                    if not visible_dt:
                        text_inputs = container.locator("input[type='text']").all()
                        for inp in text_inputs:
                            if inp.is_visible():
                                inp_class = (inp.get_attribute("class") or "").lower()
                                inp_placeholder = (
                                    inp.get_attribute("placeholder") or ""
                                ).lower()
                                inp_id = (inp.get_attribute("id") or "").lower()
                                if any(
                                    kw in inp_class + inp_placeholder + inp_id
                                    for kw in [
                                        "date",
                                        "time",
                                        "calendar",
                                        "picker",
                                        "utc",
                                    ]
                                ):
                                    visible_dt.append(inp)

                    if visible_dt:
                        if "start" in field_lower and len(visible_dt) >= 1:
                            print(
                                f"         ✅ [Section] Found START datetime in '{section_name}'"
                            )
                            return visible_dt[0]
                        elif "end" in field_lower and len(visible_dt) >= 2:
                            print(
                                f"         ✅ [Section] Found END datetime in '{section_name}'"
                            )
                            return visible_dt[1]
                        elif len(visible_dt) == 1:
                            return visible_dt[0]

            # ========================================
            # STRATEGY 2: Proximity-based search (tìm theo vị trí Y)
            # Tìm section header trên trang, rồi tìm field phía dưới nó
            # ========================================
            print(f"         🔍 [Section] Strategy 2: Proximity search...")
            section_headers = (
                page.locator("legend, h2, h3, h4, h5, strong, b, span")
                .filter(has_text=re.compile(re.escape(section_name), re.IGNORECASE))
                .all()
            )

            for header in section_headers:
                if not header.is_visible():
                    continue
                header_box = header.bounding_box()
                if not header_box:
                    continue

                # Tìm tất cả labels phía dưới section header
                all_labels = (
                    page.locator("label, legend, span, strong")
                    .filter(has_text=re.compile(re.escape(field_name), re.IGNORECASE))
                    .all()
                )

                for lbl in all_labels:
                    if not lbl.is_visible():
                        continue
                    lbl_box = lbl.bounding_box()
                    if not lbl_box:
                        continue

                    # Label phải nằm DƯỚI section header (y lớn hơn)
                    # và không quá xa (trong khoảng 500px)
                    if (
                        lbl_box["y"] > header_box["y"]
                        and lbl_box["y"] - header_box["y"] < 500
                    ):
                        # Tìm input gần label này
                        for_attr = lbl.get_attribute("for")
                        if for_attr:
                            target = page.locator(f"#{for_attr}").first
                            if target.count() > 0:
                                print(
                                    f"         ✅ [Proximity] Found field '{field_name}' under '{section_name}'"
                                )
                                return target

                        sibling = lbl.locator(
                            "xpath=following::input[not(@type='radio')][1] | following::select[1]"
                        ).first
                        if sibling.count() > 0 and sibling.is_visible():
                            print(
                                f"         ✅ [Proximity] Found sibling for '{field_name}'"
                            )
                            return sibling

            return None
        except Exception as e:
            print(f"         ⚠️ Section search error: {e}")
            return None

    # ============================
    # INLINE EDIT FIELD HANDLER
    # ============================

# automation/navigator/navigator_core.py - split from navigator.py
# Core nav: path resolution, sidebar nav, loading waits, popup safety
import time
import re
from playwright.sync_api import Page


class NavigatorCoreMixin:
    """Core nav: path resolution, sidebar nav, loading waits, popup safety"""

    def _safe_compile(self, text):
        if not text:
            return re.compile(r"^$")
        safe_text = re.escape(str(text)).replace(r"\ ", r"\s+")
        return re.compile(safe_text, re.IGNORECASE)

    def smart_navigate(self, page, target):
        """
        Điều hướng thông minh:
        - Nếu target là List (VD: ["Menu", "SubMenu"]) -> Gọi _smart_navigate_path (Của bạn)
        - Nếu target là String (VD: "Menu") -> Gọi smart_click hoặc goto
        """
        # DEBUG: Print target type and value
        print(
            f"   🔍 DEBUG smart_navigate - Type: {type(target).__name__}, Value: {target}"
        )

        try:
            page.wait_for_load_state("domcontentloaded", timeout=3000)
        except:
            pass
        # CASE 1: BREADCRUMB LIST (Path Navigation)
        if isinstance(target, list):
            print(f"   ✅ Detected LIST path, calling _smart_navigate_path")
            # Gọi hàm chuyên biệt của bạn
            self._smart_navigate_path(page, target)
            return

        # CASE 2: SINGLE TARGET (String)
        print(f"      🧭 Navigating to: {target}")
        target_str = str(target)
        try:
            if "/" not in target_str and "http" not in target_str:
                self.smart_click(page, target_str)
            else:
                page.goto(target_str)
                self._wait_for_long_loading(page)
        except:
            print(f"      ⚠️ Navigation fallback failed for {target}")

    def _smart_navigate_path(self, page, path_list):
        print(f"📍 Nav: {'->'.join(path_list)}")
        # Bỏ networkidle wait để tăng tốc, menu thường đã sẵn sàng

        # PERF/SPEED: Fast path for known PVE -> Classic PVE navigation.
        # BUT: if 'Classic PVE' isn't visible yet (sidebar accordion collapsed),
        # smart_click can fail and leave us stuck. Only do fast-path if visible.
        try:
            if path_list and str(path_list[-1]).strip().lower() == "classic pve":
                classic_text = str(path_list[-1]).strip()
                classic_loc = (
                    page.locator(
                        "aside a, #left-menu a, .sidebar a, #sidebar a, a, button, [role='button']"
                    )
                    .filter(
                        has_text=re.compile(r"^\s*Classic\s*PVE\s*$", re.IGNORECASE)
                    )
                    .first
                )

                if classic_loc.count() > 0 and classic_loc.is_visible():
                    print(
                        "   ⚡️ Fast path: smart_click('Classic PVE') (Classic PVE already visible)"
                    )
                    self.smart_click(page, classic_text)
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=3000)
                    except:
                        pass
                    # PVE heavy render: wait for React skeletons / aria-busy to complete.
                    # Your Match 1 HTML contains b-skeleton wrappers with aria-busy="true".
                    try:
                        for _ in range(12):  # ~3.6s
                            busy_visible = False
                            skeleton_visible = False
                            try:
                                busy_visible = (
                                    page.locator("[aria-busy='true']:visible").count()
                                    > 0
                                )
                            except:
                                busy_visible = False
                            try:
                                skeleton_visible = (
                                    page.locator(".b-skeleton:visible").count() > 0
                                )
                            except:
                                skeleton_visible = False

                            if not busy_visible and not skeleton_visible:
                                break
                            time.sleep(0.3)
                    except:
                        pass

                    time.sleep(1.0)
                    # Không return sớm: tiếp tục chạy vòng scan navigate bình thường
                    # để đảm bảo tab/menu đã thực sự vào đúng context.
                else:
                    print(
                        "   ℹ️ Skip fast-path for 'Classic PVE' (not visible yet); let full path scan handle accordion."
                    )
        except:
            pass

        for i, item_name in enumerate(path_list):
            item_name = str(item_name).strip()
            is_first_step = i == 0
            is_last_step = i == len(path_list) - 1
            regex_name = self._safe_compile(item_name)

            target_element = None

            try:
                # 1. Lấy tất cả ứng viên chứa từ khóa (Partial Match)
                # Thêm div[class*='menu'] để bắt các menu div nếu có
                menu_base = page.locator(
                    "a, button, div, span, li, b, strong, h1, h2, h3, h4, h5, h6, .dropdown-item, .nav-link, [role='menuitem'], [role='button']"
                ).filter(has_text=regex_name)

                # PERF FIX:
                # Tránh `.all()` + lọc is_visible() trên số lượng lớn (có thể gây treo/timeout ở bước navigate).
                # Chỉ sample phần đầu + phần cuối để vẫn bắt được menu cha/con.
                candidate_count = menu_base.count()
                visible_candidates = []

                front_limit = min(candidate_count, 20)
                for ci in range(front_limit):
                    el = menu_base.nth(ci)
                    try:
                        if el.is_visible():
                            visible_candidates.append(el)
                    except:
                        pass

                tail_limit = 20
                if candidate_count > front_limit:
                    tail_start = max(front_limit, candidate_count - tail_limit)
                    for ci in range(tail_start, candidate_count):
                        el = menu_base.nth(ci)
                        try:
                            if el.is_visible():
                                visible_candidates.append(el)
                        except:
                            pass

                # 2b. SINGULAR/PLURAL FALLBACK: Nếu không tìm thấy, thử biến thể số ít/số nhiều
                # VD: "Superstars" không match menu "Superstar" → thử "Superstar"
                # VD: "Superstar" không match → thử "Superstars"
                if not visible_candidates:
                    alt_name = None
                    if item_name.lower().endswith("s") and len(item_name) > 2:
                        alt_name = item_name[:-1]  # Bỏ 's' cuối
                    else:
                        alt_name = item_name + "s"  # Thêm 's'

                    alt_regex = self._safe_compile(alt_name)
                    alt_base = page.locator(
                        "a, button, div, span, li, b, strong, h1, h2, h3, h4, h5, h6, .dropdown-item, .nav-link, [role='menuitem'], [role='button']"
                    ).filter(has_text=alt_regex)

                    alt_count = alt_base.count()
                    alt_visible = []

                    front_limit = min(alt_count, 20)
                    for ci in range(front_limit):
                        el = alt_base.nth(ci)
                        try:
                            if el.is_visible():
                                alt_visible.append(el)
                        except:
                            pass

                    tail_limit = 20
                    if alt_count > front_limit:
                        tail_start = max(front_limit, alt_count - tail_limit)
                        for ci in range(tail_start, alt_count):
                            el = alt_base.nth(ci)
                            try:
                                if el.is_visible():
                                    alt_visible.append(el)
                            except:
                                pass

                    if alt_visible:
                        print(
                            f"   🔄 Singular/Plural fallback: '{item_name}' → '{alt_name}' ({len(alt_visible)} matches)"
                        )
                        visible_candidates = alt_visible
                        item_name = alt_name  # Cập nhật tên để exact match đúng

                if visible_candidates:
                    # --- BƯỚC LỌC THÔNG MINH (QUAN TRỌNG) ---

                    # Nhóm 1: Khớp CHÍNH XÁC 100% (Case-insensitive)
                    # Ví dụ: Text là "Perk", User tìm "Perk" -> Trúng. "Perk Slot" -> Trượt.
                    exact_matches = []
                    for el in visible_candidates:
                        text = el.inner_text().strip().lower()
                        if text == item_name.lower():
                            exact_matches.append(el)

                    # LOGIC CHỌN MỤC TIÊU:
                    if exact_matches:
                        # Nếu có khớp chính xác:
                        # - Bước 1 (Menu Cha): Chọn cái ĐẦU TIÊN (thường là Parent Menu trên thanh chính)
                        # - Bước >1 (Menu Con): Chọn cái CUỐI CÙNG (thường là Child Menu vừa xổ ra)
                        #   (Điều này giải quyết được cả vụ Boost -> Boost trùng tên)
                        need_parent = is_first_step
                        if not is_last_step and i + 1 < len(path_list):
                            next_name = str(path_list[i + 1]).strip()
                            if next_name.lower() == item_name.lower():
                                need_parent = True
                                print(
                                    f"   🔄 Detected Parent of same-name submenu. Selecting Parent [0]."
                                )

                        if need_parent:
                            target_element = exact_matches[0]
                        else:
                            target_element = exact_matches[-1]

                        print(f"   ⚡️ Exact Match Selected: '{item_name}'")

                    else:
                        # Nếu KHÔNG có khớp chính xác (User gõ tắt hoặc tên dài):
                        # Dùng lại logic cũ: Lấy cái cuối cùng (để bắt menu con)
                        # Nhưng ưu tiên cái nào ngắn nhất (gần với từ khóa nhất) để tránh bắt nhầm "Perk Slot"
                        best_candidate = visible_candidates[-1]
                        min_len = 9999
                        for el in visible_candidates:
                            txt_len = len(el.inner_text())
                            if txt_len < min_len:
                                min_len = txt_len
                                best_candidate = el

                        target_element = best_candidate
                        print(
                            f"   ⚠️ Không khớp chính xác, chọn kết quả gần đúng nhất: '{target_element.inner_text()}'"
                        )

            except Exception as e:
                print(f"   ⚠️ Lỗi Locator: {e}")

            # --- FALLBACK: QUÉT SÂU (Nếu cách trên thất bại hoàn toàn) ---
            if not target_element:
                print(f"   🐢 Turbo mode miss, deep scanning...")
                all_locs = page.get_by_text(regex_name).all()
                vis = [l for l in all_locs if l.is_visible()]
                if vis:
                    target_element = vis[-1]  # Lấy cái cuối cùng

            if not target_element:
                raise Exception(f"Không tìm thấy Menu '{item_name}'")

            # --- THAO TÁC ---
            try:
                target_element.scroll_into_view_if_needed()
            except Exception as e:
                # DOM can detach during animations / re-renders; don't fail the whole navigation.
                print(
                    f"         ⚠️ scroll_into_view_if_needed failed (detached DOM): {e}"
                )
            if not is_first_step:
                time.sleep(0.1)
            target_element.hover(force=True)
            time.sleep(0.05)

            if not is_last_step:
                next_item = path_list[i + 1]

                # LOGIC CHÍNH XÁC: Kiểm tra trùng tên TRƯỚC
                if item_name.lower() == str(next_item).strip().lower():
                    print(
                        f"   🔄 Same-name submenu detected: '{item_name}' -> '{next_item}'. FORCE CLICK."
                    )
                    target_element.click()
                    time.sleep(0.3)

                    wait_start = time.time()
                    submenu_found = False
                    while time.time() - wait_start < 2:
                        try:
                            next_regex = self._safe_compile(next_item)
                            all_matches = page.get_by_text(next_regex, exact=True).all()
                            visible_count = sum(
                                1 for el in all_matches if el.is_visible()
                            )
                            if visible_count >= 2:
                                print(
                                    f"   ✅ Submenu '{next_item}' appeared ({visible_count} visible)."
                                )
                                submenu_found = True
                                break
                        except:
                            pass
                        time.sleep(0.1)

                    if not submenu_found:
                        print(
                            f"   ⚠️ Warning: Submenu '{next_item}' may not be visible yet."
                        )
                else:
                    should_click = True
                    try:
                        next_regex = self._safe_compile(next_item)
                        next_cand = page.get_by_text(next_regex, exact=True).all()
                        for n in next_cand:
                            if n.is_visible():
                                should_click = False
                                print(
                                    f"   ℹ️ Submenu '{next_item}' already visible. Skip click."
                                )
                                break
                    except:
                        pass

                    if should_click:
                        target_element.click()
                        time.sleep(0.2)
            else:
                print(f"   🎯 Click: {item_name}")
                if target_element.is_visible():
                    target_element.click()
                else:
                    target_element.evaluate("e => e.click()")

        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except:
            pass

    def _handle_locked_item_popup(self, page):
        try:
            print("      🔍 Checking for Locked Item popup...")
            # Regression speed-up: giảm đợi để không vượt tool timeout (45s)
            time.sleep(0.1)

            lock_btn = page.locator(".btn-acquire-lock, a.btn-acquire-lock").first

            try:
                lock_btn.wait_for(state="visible", timeout=1500)
                print("      🔒 Detected Locked Item popup (Class match).")
                print("       Clicking 'Acquire Lock' button...")

                lock_btn.click(force=True)

                try:
                    page.locator(".btn-acquire-lock").first.wait_for(
                        state="hidden", timeout=1500
                    )
                    print("      ✅ Lock popup closed")
                except:
                    pass

                try:
                    page.wait_for_load_state("domcontentloaded", timeout=1500)
                except:
                    pass

                time.sleep(0.8)
                print("      ✅ Lock acquired successfully!")
                return True
            except:
                pass

            print("      🔍 Checking for lock popup by text...")
            popup_selectors = [
                ".modal-content",
                ".modal.show",
                "#vit_locker",
                ".swal2-popup",
                "[role='dialog']",
                ".popup",
                ".dialog",
            ]

            popup_found = None
            for selector in popup_selectors:
                try:
                    popup = (
                        page.locator(selector)
                        .filter(
                            has_text=re.compile(
                                "locked|is locked|acquire lock", re.IGNORECASE
                            )
                        )
                        .first
                    )

                    if popup.count() > 0 and popup.is_visible():
                        popup_found = popup
                        print(f"      🔒 Detected lock popup via selector: {selector}")
                        break
                except:
                    continue

            if popup_found:
                btn_patterns = [
                    "Acquire Lock",
                    "Acquire",
                    "Unlock",
                    "Kick",
                    "Take Lock",
                    "Override",
                ]

                btn = None
                for pattern in btn_patterns:
                    try:
                        btn_candidate = (
                            popup_found.locator("a, button")
                            .filter(
                                has_text=re.compile(re.escape(pattern), re.IGNORECASE)
                            )
                            .first
                        )

                        if btn_candidate.count() > 0 and btn_candidate.is_visible():
                            btn = btn_candidate
                            print(f"      🎯 Found button: '{pattern}'")
                            break
                    except:
                        continue

                if btn:
                    print("      🔓 Clicking lock button...")
                    btn.click(force=True)

                    try:
                        popup_found.wait_for(state="hidden", timeout=5000)
                        print("      ✅ Lock popup closed")
                    except:
                        pass

                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        pass

                    time.sleep(1.5)
                    print("      ✅ Lock acquired successfully!")
                    return True
                else:
                    print("      ⚠️ Lock popup found but no action button detected")

            print("      🔍 Global scan for acquire lock button...")
            try:
                global_lock_btn = (
                    page.locator("a, button")
                    .filter(
                        has_text=re.compile(
                            "Acquire Lock|Acquire|Take Lock", re.IGNORECASE
                        )
                    )
                    .first
                )

                if global_lock_btn.count() > 0 and global_lock_btn.is_visible():
                    print("      🔒 Found lock button via global scan")
                    print("      🔓 Clicking button...")
                    global_lock_btn.click(force=True)

                    try:
                        global_lock_btn.wait_for(state="hidden", timeout=5000)
                    except:
                        pass

                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        pass

                    time.sleep(1.5)
                    print("      ✅ Lock acquired successfully!")
                    return True
            except:
                pass

            print("      ℹ️ No lock popup detected (item is unlocked)")
            return False
        except Exception as e:
            print(f"      ⚠️ Error checking lock popup: {e}")
            return False

    def _is_daily_reward_content_loaded(self, page):
        try:
            return (
                page.locator(
                    "#start_time_send_daily_reward, [name='start_time_send_daily_reward']"
                ).count()
                > 0
            )
        except Exception:
            return False

    def _click_sidebar_nav_by_id(self, page, nav_id, label):
        selectors = [
            f"aside a#{nav_id}",
            f".sidebar a#{nav_id}",
            f"#left-menu a#{nav_id}",
            f"a.navigate-ajax#{nav_id}",
            f"a[href='#{nav_id}']",
        ]
        for sel in selectors:
            try:
                link = page.locator(sel).first
                if link.count() > 0 and link.is_visible():
                    print(f"         ✅ Sidebar nav '{label}' via {sel}")
                    link.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    link.click()
                    return True
            except Exception:
                continue
        return False

    def _wait_for_long_loading(self, page, timeout_ms: int = 45000):
        """
        Block until ALL transient loading indicators are gone.

        Uses page.wait_for_function() — evaluates all selectors atomically in the
        browser's own JS engine, no per-selector Playwright round-trips.

        Specific selectors only (no .fa-spin / [class*='loading'] which also match
        decorative/always-on elements and cause false positives).
        """
        print("         ⏳ Waiting for page to finish loading...")

        # JS function: returns true when NO visible transient loading element exists.
        # Visibility = not hidden by display/visibility/opacity AND has non-zero bbox.
        _LOADING_GONE_FN = """() => {
            const sels = [
                'div.loader',
                '.spinner-border',
                '.spinner-grow',
                '.swal2-loading',
                '.blockUI',
                '.vld-overlay.is-active',
                'svg[viewBox="0 0 120 30"]',
                '.b-skeleton',
                '[aria-busy="true"]',
                '.vld-icon'
            ];
            for (const sel of sels) {
                try {
                    for (const el of document.querySelectorAll(sel)) {
                        const s = window.getComputedStyle(el);
                        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) return false;
                    }
                } catch(e) {}
            }
            return true;
        }"""

        try:
            page.wait_for_function(_LOADING_GONE_FN, timeout=timeout_ms, polling=250)
            print("         ✅ Page ready (all spinners cleared).")
        except Exception:
            # Recheck immediately: exception may fire as spinner just disappeared
            try:
                is_clear = page.evaluate(f"({_LOADING_GONE_FN})()")
                if is_clear:
                    print("         ✅ Page ready (spinner cleared just before timeout).")
                else:
                    print(
                        f"         ⚠️ Spinner still visible after {timeout_ms // 1000}s — continuing anyway."
                    )
            except Exception:
                print(
                    f"         ⚠️ Spinner check failed after {timeout_ms // 1000}s — continuing anyway."
                )

        # Network idle: short fallback, non-fatal
        try:
            page.wait_for_load_state("networkidle", timeout=2500)
        except Exception:
            pass

        # Brief settle for React re-renders that occur after network goes idle
        time.sleep(0.5)

    def _is_sidebar_item(self, page, text):
        try:
            sidebar_selectors = [
                ".sidebar",
                "#sidebar",
                ".nav-pills",
                ".list-group",
                "aside",
            ]
            for sel in sidebar_selectors:
                sidebar = page.locator(sel).first
                if sidebar.is_visible():
                    if sidebar.locator(f"text={text}").count() > 0:
                        return True
        except:
            pass
        return False

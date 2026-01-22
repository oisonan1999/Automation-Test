# automation_modules/navigator.py
import time
import re
from playwright.sync_api import Page

class NavigatorMixin:
    """Chứa logic tìm kiếm menu và điều hướng"""

    def _safe_compile(self, text):
        if not text: return re.compile(r"^$")
        safe_text = re.escape(str(text)).replace(r"\ ", r"\s+")
        return re.compile(safe_text, re.IGNORECASE)

    def _smart_navigate_path(self, page, path_list):
        print(f"📍 Nav: {'->'.join(path_list)}")
        
        for i, item_name in enumerate(path_list):
            is_first_step = (i == 0)
            is_last_step = (i == len(path_list) - 1)
            regex_name = self._safe_compile(item_name)
            
            target_element = None
            
            try:
                # 1. Lấy tất cả ứng viên chứa từ khóa (Partial Match)
                # Thêm div[class*='menu'] để bắt các menu div nếu có
                raw_candidates = page.locator("a, button, .dropdown-item, .nav-link, [role='menuitem'], div[role='button']").filter(has_text=regex_name).all()
                
                # 2. Lọc danh sách hiển thị (Visible)
                visible_candidates = [el for el in raw_candidates if el.is_visible()]
                
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
                        if is_first_step: target_element = exact_matches[0]
                        else: target_element = exact_matches[-1]
                        print(f"   ⚡️ Chọn kết quả khớp chính xác (Exact Match): '{item_name}'")
                    
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
                        print(f"   ⚠️ Không khớp chính xác, chọn kết quả gần đúng nhất: '{target_element.inner_text()}'")

            except Exception as e: print(f"   ⚠️ Lỗi Locator: {e}")

            # --- FALLBACK: QUÉT SÂU (Nếu cách trên thất bại hoàn toàn) ---
            if not target_element:
                print(f"   🐢 Turbo mode miss, deep scanning...")
                all_locs = page.get_by_text(regex_name).all()
                vis = [l for l in all_locs if l.is_visible()]
                if vis: target_element = vis[-1] # Lấy cái cuối cùng

            if not target_element: raise Exception(f"Không tìm thấy Menu '{item_name}'")

            # --- THAO TÁC ---
            target_element.scroll_into_view_if_needed()
            if not is_first_step: time.sleep(0.5) # Chờ menu xổ xuống

            target_element.hover(force=True)
            time.sleep(0.2)

            if not is_last_step:
                next_item = path_list[i+1]
                # Kiểm tra xem menu con đã hiện chưa. 
                # Nếu chưa HOẶC nếu menu con trùng tên cha (Perk -> Perk), click để mở.
                next_regex = self._safe_compile(next_item)
                
                should_click = True
                try:
                    # Nếu tìm thấy menu con KHỚP CHÍNH XÁC đang hiện -> Không cần click
                    # (Tránh trường hợp click lại làm đóng menu)
                    next_cand = page.get_by_text(next_regex, exact=True).all()
                    for n in next_cand:
                         if n.is_visible(): should_click = False; break
                except: pass

                # Với trường hợp trùng tên (Perk -> Perk), luôn Click cha để chắc chắn
                if item_name.lower() == next_item.lower(): should_click = True

                if should_click:
                    target_element.click()
                    time.sleep(0.5)
            else:
                # Bước cuối
                print(f"   🎯 Click: {item_name}")
                if target_element.is_visible(): target_element.click()
                else: target_element.evaluate("e => e.click()")

        try: page.wait_for_load_state("domcontentloaded", timeout=5000)
        except: pass
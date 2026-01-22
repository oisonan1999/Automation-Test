# automation_modules/form_handler.py
import time
import re
import random
from playwright.sync_api import Page

class FormHandlerMixin:
    """Chứa logic tương tác với Form, Checkbox, Row"""
    def _safe_check(self, locator):
        try:
            # 1. Scroll dòng ra GIỮA MÀN HÌNH (Tránh bị Sticky Header che)
            locator.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
            time.sleep(0.2)
            
            if locator.is_checked(): return True

            # 2. Click thông thường
            try: locator.check(force=True, timeout=1000)
            except: pass
            if locator.is_checked(): return True

            # 3. Click vào ô cha (td) hoặc label nếu click input không ăn
            # (Đôi khi input bị ẩn, phải click vào cell)
            locator.evaluate("el => { el.click(); if(!el.checked) el.checked=true; el.dispatchEvent(new Event('change', {bubbles: true})); }")
            time.sleep(0.1)
            
            return locator.is_checked()
        except: return False

    def handle_checkbox(self, page, target, value):
        logs = []
        try:
            if not self.wait_for_table_data(page): return [{"step": "Checkbox", "status": "FAIL", "details": "Table Empty"}]
            
            # Lọc bỏ Header, chỉ lấy dòng dữ liệu
            all_rows = page.locator("tbody tr").filter(has=page.locator("td"))
            total_rows = all_rows.count()
            
            print(f"   📊 Tìm thấy {total_rows} dòng dữ liệu khả dụng.")

            if "random" in value.lower():
                num_to_select = 1
                match = re.search(r'random.*?(\d+)', value.lower())
                if match: num_to_select = int(match.group(1))
                
                num_to_select = min(num_to_select, total_rows)
                
                selected_ids = []
                used_indices = set() # Theo dõi các dòng đã thử
                
                # --- VÒNG LẶP KIÊN TRÌ (WHILE LOOP) ---
                # Chạy cho đến khi tick đủ số lượng yêu cầu
                attempts = 0
                max_attempts = num_to_select * 3 # Cho phép thử gấp 3 lần số cần thiết
                
                while len(selected_ids) < num_to_select and attempts < max_attempts:
                    attempts += 1
                    
                    # 1. Chọn 1 index ngẫu nhiên chưa từng dùng
                    idx = random.randint(0, total_rows - 1)
                    if idx in used_indices: continue # Nếu trùng thì quay lại chọn cái khác
                    
                    used_indices.add(idx) # Đánh dấu đã dùng
                    
                    row = all_rows.nth(idx)
                    chk = row.locator("input[type='checkbox']").first
                    
                    # 2. Thử Tick
                    if self._safe_check(chk):
                        # Thành công -> Lưu ID
                        try:
                            cell_text = row.locator("td").nth(1).inner_text().strip()
                            if not cell_text: cell_text = row.locator("td").nth(2).inner_text().strip()
                            
                            self.memory['LAST_SELECTED'] = cell_text
                            if 'SELECTED_IDS' not in self.memory: self.memory['SELECTED_IDS'] = []
                            self.memory['SELECTED_IDS'].append(cell_text)
                            
                            selected_ids.append(cell_text)
                            print(f"   ✅ Đã tick dòng {idx+1}: {cell_text}")
                        except: pass
                    else:
                        print(f"   ⚠️ Lỗi tick dòng {idx+1}. Robot sẽ tự chọn dòng khác bù vào...")
                    
                    # Nghỉ xíu để Web load
                    time.sleep(0.2)

                if len(selected_ids) < num_to_select:
                    print(f"   ⚠️ Đã cố hết sức nhưng chỉ tick được {len(selected_ids)}/{num_to_select}.")
                else:
                    print(f"   🎉 Hoàn thành: Đã chọn đủ {len(selected_ids)} dòng.")

                logs.append({"step": "Checkbox", "status": "PASS", "details": f"Selected: {selected_ids}"})
                
            elif "all" in value.lower():
                h = page.locator("thead input[type='checkbox']").first
                if h.is_visible(): 
                    self._safe_check(h)
                    time.sleep(1) # Chờ select all tác dụng
                else:
                    # Fallback tick từng cái
                    for i in range(min(total_rows, 20)):
                        self._safe_check(all_rows.nth(i).locator("input[type='checkbox']").first)
                        time.sleep(0.1)
                logs.append({"step": "Checkbox", "status": "PASS", "details": "Select All"})
            else:
                # Chọn đích danh (Target)
                target_regex = self._safe_compile(target)
                target_row = all_rows.filter(has_text=target_regex).first
                
                if target_row.is_visible():
                     chk = target_row.locator("input[type='checkbox']").first
                     self._safe_check(chk)
                     logs.append({"step": "Checkbox", "status": "PASS", "details": target})
                else:
                     logs.append({"step": "Checkbox", "status": "FAIL", "details": f"Not found: {target}"})

        except Exception as e: logs.append({"step": "Checkbox", "status": "FAIL", "details": str(e)})
        return logs
    
    def _click_icon_in_row(self, page, target_text, action_type):
        if target_text == "LAST_SELECTED":
            target_text = self.memory.get('LAST_SELECTED', "")
            if not target_text:
                print("   ⚠️ Memory rỗng! Dùng fallback lấy dòng đầu tiên...")
                target_text = page.locator("tbody tr").first.locator("td").nth(1).inner_text().strip()
            else:
                print(f"   🧠 Recall Memory: '{target_text}'")

        print(f"   🔎 Tìm dòng '{target_text}' để {action_type}...")

        js_script = """
            (args) => {
                const targetText = args.text.toLowerCase().trim();
                const action = args.action; 
                const rows = Array.from(document.querySelectorAll('tbody tr'));
                
                for (const row of rows) {
                    if (row.innerText.toLowerCase().includes(targetText)) {
                        let btn = null;
                        if (action === 'edit') {
                            btn = row.querySelector("i[class*='edit'], i[class*='pencil'], .btn-edit");
                        } else {
                            btn = row.querySelector("i[class*='clone'], i[class*='copy'], i[class*='share'], .btn-clone");
                        }
                        if (btn) {
                            (btn.closest('button') || btn.closest('a') || btn).click();
                            return "Clicked via Icon";
                        }
                        const buttons = row.querySelectorAll("button, a.btn, a[class*='btn']");
                        if (buttons.length > 0) {
                            if (buttons.length >= 2) { (action === 'edit' ? buttons[0] : buttons[1]).click(); } 
                            else { buttons[0].click(); }
                            return "Clicked via Position";
                        }
                    }
                }
                return "Row Not Found";
            }
        """
        result = page.evaluate(js_script, {"text": str(target_text), "action": action_type})
        
        if "Clicked" in result: print(f"   ✅ JS Click Success: {result}")
        elif "Row Not Found" in result:
            if self._auto_filter_data(page, target_text):
                 page.evaluate(js_script, {"text": str(target_text), "action": action_type})
            else:
                 raise Exception(f"Không tìm thấy dòng '{target_text}'")

# ============================
    # 4. SMART FORM FILLER (FULL FEATURES)
    # ============================
    def _smart_update_form(self, page, data_dict):
        print(f"   📝 Updating Form: {data_dict}")
        self._handle_locked_item_popup(page)

        # 1. SCOPE
        try:
            modal = page.locator(".modal.show .modal-content, .modal-content:visible").last
            if not modal.is_visible(): 
                modal = page; is_modal = False
            else: is_modal = True
        except: modal = page; is_modal = False

        # 2. TAB
        if "Tab" in data_dict:
            t = data_dict.pop("Tab")
            r = self._safe_compile(t)
            el = modal.locator(".nav-link, button[role='tab']").filter(has_text=r).first
            if not el.is_visible(): el = page.locator(".sidebar a").filter(has_text=r).first
            if el.is_visible(): el.click(); time.sleep(1)

        # 3. FILL DATA
        try:
            for key, value in data_dict.items():
                print(f"      👉 Xử lý '{key}' -> '{value}'")
                target_input = None
                
                # --- A. RADIO BUTTON SCAN (Chỉ chạy nếu Value khớp với Label của Radio) ---
                try:
                    radio_label = modal.locator("label").filter(has_text=re.compile(re.escape(str(value)), re.IGNORECASE)).first
                    if radio_label.is_visible():
                        if modal.locator("input[type='radio']").count() > 0:
                            print(f"         ✅ Found Radio Label: '{value}'")
                            radio_label.click(); time.sleep(0.5); continue 
                except: pass

                # --- B. MAPPING ---
                k_map = {
                    "id": ["ffID", "New Event ID", "New ID", "Target", "Key", "Code", "BagID", "Gacha ID"],
                    "gate": ["ff_gate", "Gate", "Condition", "clone_gate"],
                    "currency": ["Currency", "Type", "Cost Type"],
                    "currency value": ["Currency", "Money Type", "Search for a currency"] # Thêm placeholder
                }
                cands = [key]
                for k, v in k_map.items():
                    if k in key.lower(): cands.extend(v)
                
                if "id" in key.lower() and "ffID" not in cands: cands.insert(0, "ffID")
                if "gate" in key.lower() and "ff_gate" not in cands: cands.insert(0, "ff_gate")

                # --- C. TÌM KIẾM ---
                # 1. Exact ID
                for term in cands:
                    if " " not in term:
                        el = modal.locator(f"#{term}").first
                        if el.count(): target_input=el; break 
                
                # 2. Label Match
                if not target_input:
                    for term in cands:
                        reg = re.compile(re.escape(term), re.IGNORECASE)
                        if is_modal: labels = modal.locator("label, span, h5, h4, strong").filter(has_text=reg).all()
                        else: labels = modal.locator("label, span, h5, th, strong").filter(has_text=reg).all()

                        for lbl in labels:
                            if not lbl.is_visible(): continue
                            
                            # Quét các phần tử input ngay sau label
                            # Lấy nhiều hơn 1 candidate để lọc (đề phòng radio nằm trước select)
                            candidates = lbl.locator("xpath=following::input | following::select | following::span[contains(@class,'select2-container')]").all()
                            
                            for cand in candidates[:3]: # Kiểm tra 3 phần tử gần nhất
                                if not cand.is_visible() and cand.evaluate("e=>e.tagName.toLowerCase()") != "select":
                                    continue # Bỏ qua input ẩn (trừ select ẩn)

                                cand_type = cand.get_attribute("type")
                                cand_tag = cand.evaluate("e=>e.tagName.toLowerCase()")

                                # --- LOGIC QUAN TRỌNG: CHECK RADIO ---
                                if cand_type == "radio":
                                    # Nếu đang tìm 'currency value' (giá trị cụ thể), tuyệt đối không lấy Radio
                                    if "value" in key.lower(): continue
                                    
                                    # Nếu giá trị cần điền là 1 chuỗi dài (ID), không lấy Radio
                                    if len(str(value)) > 15 and " " not in str(value).strip(): continue
                                
                                # --- LOGIC CHECKBOX ---
                                if cand_type == "checkbox" and str(value).lower() not in ["true", "false", "on", "off"]:
                                    continue 

                                target_input = cand
                                break # Tìm thấy input hợp lệ thì dừng
                            
                            if target_input: break
                        if target_input: break
                
                # 3. Attribute/Placeholder
                if not target_input:
                    for term in cands:
                        els = modal.locator("input:visible, select, textarea:visible").all()
                        for el in els:
                            n = (el.get_attribute("name") or "").lower()
                            i = (el.get_attribute("id") or "").lower()
                            if term.lower() in n or term.lower() in i: target_input=el; break
                        if not target_input:
                            ph = modal.get_by_placeholder(re.compile(term, re.IGNORECASE)).first
                            if ph.is_visible(): target_input=ph
                        if target_input: break

                # 4. Blind Heuristic
                if not target_input and "id" in key.lower():
                     vis = [t for t in modal.locator("input[type='text']").all() if t.is_visible()]
                     if vis: target_input=vis[0]; print("         ⚠️ Blind ID pick")

                if not target_input: print(f"      ❌ Give up: {key}"); continue

                # --- D. THỰC HIỆN ACTION ---
                cls = target_input.get_attribute("class") or ""
                tag = target_input.evaluate("e=>e.tagName.toLowerCase()")
                
                # FIX SELECT2 HIDDEN
                if tag == "select":
                    if not target_input.is_visible() or "select2-hidden-accessible" in cls:
                        print("         ℹ️ Detect Select2 Hidden -> Switching to Container")
                        s2 = target_input.locator("xpath=following-sibling::span[contains(@class,'select2')]").first
                        if s2.is_visible(): 
                            target_input = s2
                            cls = "select2-container"
                        else:
                            try:
                                sel_id = target_input.get_attribute("id")
                                if sel_id:
                                    s2_alt = page.locator(f".select2-selection[aria-labelledby*='{sel_id}']").first
                                    if s2_alt.is_visible(): target_input = s2_alt; cls="select2-container"
                            except: pass

                is_s2 = "select2" in cls or "selection" in cls or ("gate" in key.lower() and tag!="select")
                typ = target_input.get_attribute("type")

                # -> SELECT2
                if is_s2 and typ!="checkbox" and typ!="radio":
                    print("         ↳ Action: Select2")
                    target_input.click(); time.sleep(0.5)
                    box = page.locator(".select2-container--open input.select2-search__field").last
                    if box.is_visible():
                        box.fill(str(value)); time.sleep(1.0)
                        opt = page.locator(".select2-results__option--highlighted").first
                        if not opt.is_visible(): opt = page.locator(f".select2-results__option:has-text('{value}')").first
                        if opt.is_visible(): opt.click()
                        else: page.keyboard.press("Enter")
                    else: page.keyboard.type(str(value)); page.keyboard.press("Enter")
                
                # -> RADIO
                elif typ == "radio":
                     print("         ↳ Action: Radio Click")
                     target_input.click()

                # -> TEXT
                else:
                    print("         ↳ Action: Fill Text")
                    target_input.click(); target_input.fill(""); target_input.fill(str(value))
                    if any(k in key.lower() for k in ["date","time"]): page.keyboard.press("Enter")

        except Exception as e: print(f"Form Error: {e}")

# ============================
    # 6. HELPERS
    # ============================
    def _save_form(self, page):
        print("   💾 Saving/Cloning...")

        # 1. XÁC ĐỊNH PHẠM VI (SCOPE): ƯU TIÊN MODAL
        try:
            # Tìm modal đang hiển thị
            modal = page.locator(".modal.show .modal-content, .modal-content:visible").last
            if modal.is_visible():
                scope = modal
                print("   🎯 Scope: Button trong Popup (Modal)")
            else:
                scope = page
                print("   🎯 Scope: Button trên Page")
        except: scope = page

        # 2. DANH SÁCH TỪ KHÓA (TEXT)
        # Ưu tiên Clone, Create cho trường hợp sao chép
        target_texts = ["Clone", "Save & Continue", "Save All", "Save", "Create", "Update", "Submit", "Duplicate"]
        
        # 3. CHIẾN THUẬT 1: TÌM THEO TEXT (Mạnh nhất)
        for text in target_texts:
            # Tìm button hoặc thẻ a dạng button có chứa text
            # Dùng .last để ưu tiên nút nằm bên phải/dưới cùng (thường là nút Save/Clone)
            btn = scope.locator(f"button:has-text('{text}'), a.btn:has-text('{text}')").last
            
            if btn.is_visible():
                print(f"      👉 Click nút: '{text}'")
                btn.click()
                self._wait_after_save(page)
                return

        # 4. CHIẾN THUẬT 2: TÌM THEO CLASS (Bootstrap)
        # Nếu text không khớp (vd: Icon only), tìm theo màu nút
        # btn-primary (Xanh dương - Clone), btn-success (Xanh lá - Save), btn-danger (Đỏ - Delete)
        class_selectors = ["button.btn-primary", "button.btn-success", "input[type='submit']"]
        
        for sel in class_selectors:
            btn = scope.locator(sel).last
            if btn.is_visible():
                print(f"      👉 Click nút theo Class: '{sel}'")
                btn.click()
                self._wait_after_save(page)
                return

        print("      ❌ Không tìm thấy nút Save/Clone nào khả thi.")

    def _wait_after_save(self, page):
        """Hàm phụ: Chờ thông báo thành công hoặc Popup đóng lại"""
        time.sleep(1)
        try:
            # Chờ Toast Message xanh lá hiện lên
            page.locator(".toast-success, .alert-success").wait_for(state="visible", timeout=2000)
            print("      ✅ Thành công (Toast detected).")
        except:
            pass
        
        try:
            # Chờ Modal đóng lại (nếu vừa bấm trong modal)
            page.locator(".modal-backdrop").wait_for(state="hidden", timeout=2000)
        except: pass

    def _handle_locked_item_popup(self, page):
        try:
            popup = page.locator(".modal-content, .popover").filter(has_text="locked this item").first
            if popup.is_visible(timeout=2000):
                print("   ⚠️ Locked Item Popup detected.")
                btn = popup.locator("button, a").filter(has_text=re.compile("Acquire|Unlock|Edit", re.IGNORECASE)).first
                if btn.is_visible(): btn.click(); time.sleep(2)
                else: popup.locator("button:has-text('Close')").click()
        except: pass

    def _auto_filter_data(self, page, keyword):
        try:
            search_input = None
            placeholders = ["ID", "Search", "Name", "Filter", "Title"]
            for p in placeholders:
                inp = page.get_by_placeholder(re.compile(p, re.IGNORECASE)).first
                if inp.is_visible(): search_input = inp; break
            
            if not search_input: search_input = page.locator("input[type='text']:visible").first

            if search_input and search_input.is_visible():
                print(f"      👉 Auto Filter: '{keyword}'")
                search_input.fill(keyword)
                search_input.press("Enter")
                time.sleep(2)
                return True
        except: pass
        return False
    
    def wait_for_table_data(self, page, timeout=10):
        s = time.time()
        while time.time()-s < timeout:
            if page.locator("tbody tr").count() > 0: return True
            time.sleep(0.5)
        return False

    def close_popup(self, page):
        try:
            page.keyboard.press("Escape")
            btn = page.locator("button:has-text('Close')").first
            if btn.is_visible(): btn.click()
        except: pass
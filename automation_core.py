# automation_core.py
import time
import re
import os
import csv
import json
import random
import shutil
from playwright.sync_api import sync_playwright
import pandas as pd
import io

DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

class BrickAutomation:
    def __init__(self):
        if not os.path.exists(DOWNLOAD_DIR): os.makedirs(DOWNLOAD_DIR)
        self.memory = {} # Trí nhớ ngắn hạn cho robot

    def get_existing_page(self, p):
        try:
            # Kết nối vào trình duyệt Chrome đang mở sẵn qua cổng Debug
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            if len(context.pages) > 0: page = context.pages[0]
            else: page = context.new_page()
            return browser, page
        except Exception as e:
            raise Exception(f"Không thể kết nối Chrome! Hãy chạy lệnh debug port 9222. Lỗi: {e}")

    def _safe_compile(self, text):
        if not text: return re.compile(r"^$")
        safe_text = re.escape(str(text)).replace(r"\ ", r"\s+")
        return re.compile(safe_text, re.IGNORECASE)

    # ============================
    # 1. NAVIGATION (MENU)
    # ============================
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

    # ============================
    # 2. CHECKBOX & MEMORY
    # ============================
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

    # ============================
    # 3. EDIT/CLONE (JS CLICK)
    # ============================
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
    # 5. CSV & UPLOAD (ĐÃ KHÔI PHỤC ĐẦY ĐỦ)
    # ============================
    def _process_csv_manipulation(self, filename, operation, data_instruction):
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if not os.path.exists(filepath): return f"Error: File {filename} not found."
        
        print(f"   🔧 CSV: {operation} -> {data_instruction}")
        rows = []; headers = []
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                r_headers = next(csv.reader(f)); headers = [h.strip() for h in r_headers]
                f.seek(0); reader = csv.DictReader(f, fieldnames=headers); next(reader); rows = list(reader)
        except Exception as e: return f"Read Error: {e}"

        def find_col(n):
            for h in headers: 
                if h.lower() == n.lower().strip(): return h
            return None
        
        def safe_split(text):
            if "=" in text: return text.split("=", 1)
            if ":" in text: return text.split(":", 1)
            return None, None

        # --- HÀM MỚI: DỌN DẸP GIÁ TRỊ RÁC ---
        def clean_val(v):
            if not v: return ""
            # Xóa khoảng trắng và dấu phẩy thừa ở 2 đầu
            # Ví dụ: " delete, " -> "delete"
            return v.strip().strip(",").strip()

        try:
            # --- ADD LOGIC ---
            if operation == "add":
                col, vals_str = safe_split(data_instruction)
                if not col: return "Invalid ADD format"
                t_col = find_col(col)
                if not t_col: return f"Column '{col}' not found"
                
                # Tách values bằng dấu phẩy
                vals = [x.strip() for x in vals_str.split(",")]
                tmpl = rows[0].copy() if rows else {h:"" for h in headers}
                
                for v in vals:
                    nr = tmpl.copy()
                    # Clean giá trị trước khi thêm
                    nr[t_col] = clean_val(v)
                    rows.append(nr)
                msg = f"Added {len(vals)} rows"

            # --- EDIT LOGIC (FIX LỖI DẤU PHẨY) ---
            elif operation == "edit":
                # Xử lý trường hợp AI vẫn cố tình gộp dòng (Chốt chặn 1)
                clean_instr = data_instruction
                if data_instruction.count("|") > 1 and "," in data_instruction:
                     print("      ⚠️ Phát hiện cú pháp gộp, tự động cắt lấy lệnh đầu tiên...")
                     clean_instr = data_instruction.split(",")[0]

                if "|" not in clean_instr: return "Invalid EDIT format"
                
                f_part, s_part = clean_instr.split("|", 1)
                fc, fv = safe_split(f_part)
                sc, sv = safe_split(s_part)
                
                ftc = find_col(fc); stc = find_col(sc)
                if not ftc or not stc: return f"Column not found: {fc} or {sc}"
                
                # Dọn dẹp dữ liệu tìm kiếm và dữ liệu thay thế (Chốt chặn 2)
                fv = clean_val(fv)
                sv = clean_val(sv) # <--- ĐÂY LÀ CHỖ SỬA LỖI QUAN TRỌNG NHẤT
                
                cnt = 0
                for r in rows:
                    if r[ftc].strip() == fv: 
                        r[stc] = sv
                        cnt+=1
                msg = f"Edited {cnt} rows ({sc}={sv})"

            # --- DELETE LOGIC ---
            elif operation == "delete":
                col, val = safe_split(data_instruction)
                t_col = find_col(col)
                val = clean_val(val) # Clean giá trị cần xóa
                
                if t_col:
                    initial = len(rows)
                    rows = [r for r in rows if r[t_col].strip() != val]
                    msg = f"Deleted {initial - len(rows)} rows"
                else: msg = "Col not found"

            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                w = csv.DictWriter(f, fieldnames=headers); w.writeheader(); w.writerows(rows)
            return f"Success: {msg}"
        except Exception as e: return f"Logic Error: {e}"


    def _modify_csv(self, fp, col, val):
        # Helper function cho Smart Test
        try:
            rows = []
            with open(fp, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                for row in reader:
                    if col in row: row[col] = val
                    rows.append(row)
            with open(fp, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
        except: pass

    def _generate_fuzzed_data(self, original_df):
        fuzzed_rows = []
        columns = original_df.columns.tolist()
        
        if not original_df.empty: base_row = original_df.iloc[0].to_dict()
        else: base_row = {col: "Sample" for col in columns}

        # Helper để tạo case
        def add_case(row_mod, name, keyword):
            r = row_mod.copy()
            r["TEST_CASE"] = name
            r["EXPECTED_KEYWORD"] = keyword # Từ khóa kỳ vọng xuất hiện trong thông báo lỗi
            fuzzed_rows.append(r)

        # 1. EMPTY FIELDS (Bắt lỗi Required)
        for col in columns:
            if "id" in col.lower() or "name" in col.lower() or "gate" in col.lower():
                r = base_row.copy(); r[col] = ""
                add_case(r, f"Bỏ trống '{col}'", f"{col} is required")

        # 2. TYPE MISMATCH (Bắt lỗi Number/Format)
        for col in columns:
            col_lower = col.lower()
            if any(x in col_lower for x in ['cost', 'price', 'amount', 'stock']):
                r = base_row.copy(); r[col] = "NotANumber"
                add_case(r, f"Nhập chữ vào cột số '{col}'", "valid integer")
                
                r2 = base_row.copy(); r2[col] = "-9999"
                add_case(r2, f"Số âm trong '{col}'", "must be positive")

        # 3. SPECIAL CHARS (Bắt lỗi Format/Regex)
        for col in columns:
            if "id" in col.lower():
                r = base_row.copy(); r[col] = "ID_@#$%^&*"
                add_case(r, f"Ký tự lạ trong '{col}'", "invalid format")
                
                r2 = base_row.copy(); r2[col] = "<script>alert(1)</script>"
                add_case(r2, f"XSS Script trong '{col}'", "invalid format")

        return pd.DataFrame(fuzzed_rows)
    
    def _ensure_popup_closed(self, page):
        """Chỉ dùng để dọn dẹp TRƯỚC khi bắt đầu upload"""
        targets = [".swal2-container", ".modal.show", ".modal-backdrop", ".swal2-overlay"]
        has_popup = False
        for sel in targets:
            if page.locator(sel).count() > 0: has_popup = True
        
        if has_popup:
            try:
                # Ưu tiên xóa DOM để nhanh gọn
                page.evaluate("""
                    document.querySelectorAll('.swal2-container, .modal-backdrop, .modal.show').forEach(e => e.remove());
                    document.body.classList.remove('swal2-shown', 'swal2-height-auto', 'modal-open');
                    document.body.style.overflow = 'auto';
                    document.body.style.height = 'auto';
                """)
                time.sleep(0.5)
            except: pass
    
    def _perform_upload_action(self, page, file_path):
        """
        Hàm Upload "Bao sân": Bấm nút -> Confirm -> Chờ Success.
        Trả về: (Success: Bool, Message: String)
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                print(f"      🔄 Upload attempt {attempt+1}...")
                # 1. Dọn dẹp chiến trường
                self._ensure_popup_closed(page)

                # 2. Chọn file
                with page.expect_file_chooser(timeout=3000) as fc_info:
                    btn = page.locator("button:has-text('Import CSV'), a:has-text('Import CSV')").first
                    if not btn.is_visible(): btn = page.locator(".btn-import, [title='Import']").first
                    
                    if btn.is_visible():
                        btn.scroll_into_view_if_needed()
                        btn.click(force=True)
                    else:
                        page.locator("input[type='file']").evaluate("e => e.click()")
                
                file_chooser = fc_info.value
                file_chooser.set_files(file_path)
                
                # 3. VÒNG LẶP CHỜ KẾT QUẢ (WAIT LOOP)
                # Thay vì chờ Confirm rồi thoát, ta chờ Confirm -> Bấm -> Chờ Success luôn
                start_wait = time.time()
                while time.time() - start_wait < 20: # Chờ tối đa 20s cho mỗi lần thử
                    
                    # A. TÌM THẤY SUCCESS (Ưu tiên số 1)
                    # Tìm text "Success" hoặc icon check xanh
                    success_signal = page.locator(".swal2-success-ring, .toast-success").or_(page.locator("text=Success"))
                    if success_signal.first.is_visible():
                        print("      ✅ Success detected inside upload loop!")
                        return True, "Success"

                    # B. TÌM THẤY LỖI (Import Failed)
                    error_signal = page.locator(".swal2-validation-error, .swal2-x-mark").or_(page.locator("text=Import Failed"))
                    if error_signal.first.is_visible():
                        err_text = error_signal.first.inner_text()
                        print(f"      ❌ Error detected: {err_text[:50]}")
                        # Nếu đây là file Valid mà bị lỗi -> Return False luôn, không Retry (vì Retry cũng lỗi thế thôi)
                        return False, f"Upload Failed: {err_text[:50]}"

                    # C. TÌM NÚT CONFIRM (Nếu chưa bấm)
                    confirm_btn = page.locator(".modal.show button.btn-primary:has-text('Upload'), button.swal2-confirm, button:has-text('Confirm')").first
                    if confirm_btn.is_visible():
                        # Chỉ bấm nếu chưa thấy success
                        confirm_btn.click(force=True)
                        time.sleep(1) # Chờ server phản hồi sau khi bấm
                        continue # Quay lại đầu vòng lặp while để check tiếp

                    time.sleep(0.5)
                
                # Nếu hết 20s mà không thấy gì -> Retry loop lớn
                print("      ⚠️ Timeout waiting for response. Retrying...")
                continue

            except Exception as e:
                print(f"      ⚠️ Exception: {e}")
                time.sleep(1)
        
        return False, "Max retries exceeded"
    
    def smart_test_cycle(self, page, target_csv):
        logs = []
        try:
            # ... (Phần A: Chuẩn bị file - GIỮ NGUYÊN) ...
            file_path = os.path.join(DOWNLOAD_DIR, target_csv)
            if not os.path.exists(file_path):
                 files = sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)))
                 if files: file_path = os.path.join(DOWNLOAD_DIR, files[-1]); target_csv = files[-1]
            original_df = pd.read_csv(file_path)
            
            # --- PHASE 1: NEGATIVE TESTING (FUZZING) ---
            print("   🧪 PHASE 1: Running Fuzz Tests...")
            fuzzed_df = self._generate_fuzzed_data(original_df)
            fuzz_path = os.path.join(DOWNLOAD_DIR, f"fuzzed_{target_csv}")
            meta_cols = ["TEST_CASE", "EXPECTED_KEYWORD"]
            save_cols = [c for c in fuzzed_df.columns if c not in meta_cols]
            fuzzed_df[save_cols].to_csv(fuzz_path, index=False)
            
            # Upload File Lỗi (Gọi hàm Upload mới)
            # Hàm này sẽ trả về False (vì file lỗi sẽ sinh ra Error Popup)
            # Nhưng ta cần verify cái Error Text đó
            self._ensure_popup_closed(page)
            
            # Lưu ý: Với Fuzzing, ta kỳ vọng nó Fail, nên ta sẽ tự handle việc check error
            # Tuy nhiên để đơn giản, ta cứ gọi upload, nó sẽ trả về (False, "Upload Failed...")
            # Sau đó ta đọc lại popup trên màn hình
            
            # Thực hiện upload (Chấp nhận nó sẽ báo Fail)
            self._perform_upload_action(page, fuzz_path) 
            
            # Verify Lỗi (Đọc popup đang hiện trên màn hình)
            print("      🛡️ Analyzing Error Popup...")
            popup_text = ""
            try:
                any_popup = page.locator(".swal2-popup, .modal-content").first
                if any_popup.is_visible():
                    popup_text = any_popup.inner_text().lower()
                else:
                    popup_text = "no popup appeared"
                self._ensure_popup_closed(page) # Đóng ngay
            except: popup_text = "error reading popup"

            for idx, row in fuzzed_df.iterrows():
                expected = str(row["EXPECTED_KEYWORD"]).lower()
                if expected in popup_text:
                    res = "PASS"; detail = f"Caught: '{expected}'"
                else:
                    res = "FAIL"; detail = f"Missed: '{expected}'"
                    if "no popup" in popup_text: detail = "System did not block invalid data!"
                logs.append({"step": f"Test Case #{idx+1}", "test_case": row["TEST_CASE"], "status": "EXECUTED", "result": res, "details": detail})

            # --- PHASE 2: POSITIVE TESTING (VALID DATA) ---
            print("   ✨ PHASE 2: Verify Valid Import...")
            
            valid_df = original_df.iloc[[0]].copy()
            current_timestamp = int(time.time())
            
            # 1. LOGIC SINH ID (GRABBAG PREFIX)
            for col in valid_df.columns:
                col_lower = col.lower()
                if "id" in col_lower or "key" in col_lower:
                    if "bagid" in col_lower:
                        new_id = f"Grabbag_Auto_{current_timestamp}"
                        valid_df[col] = new_id
                    else:
                        valid_df[col] = f"Auto_{current_timestamp}"

            # 2. LOGIC BUSINESS RULE: ShowInStore = 0 -> Clear Offers
            # Tìm tên cột thực tế (không phân biệt hoa thường)
            show_col = next((c for c in valid_df.columns if c.lower() == "showinstore"), None)
            
            if show_col:
                # Lấy giá trị của dòng đầu tiên
                val = str(valid_df.iloc[0][show_col]).strip()
                
                # Nếu giá trị là 0
                if val == "0" or val == "False":
                    print("      ℹ️ Detect ShowInStore=0. Clearing Offer dependent columns...")
                    
                    # Danh sách các cột cần xóa trắng
                    dependent_cols = ["OfferDisplayID", "OfferParentID", "OfferSectionID"]
                    
                    for dep in dependent_cols:
                        # Tìm tên cột thực tế trong file CSV
                        target_col = next((c for c in valid_df.columns if c.lower() == dep.lower()), None)
                        if target_col:
                            # Gán giá trị rỗng
                            valid_df.at[valid_df.index[0], target_col] = "" # Hoặc np.nan nếu cần

            valid_path = os.path.join(DOWNLOAD_DIR, f"valid_{target_csv}")
            valid_df.to_csv(valid_path, index=False)
            
            # Upload File Sạch
            self._ensure_popup_closed(page)
            is_success, msg = self._perform_upload_action(page, valid_path)
            
            if is_success:
                final_res = "PASS"
                final_detail = "Successfully imported valid data"
                self._ensure_popup_closed(page)
            else:
                final_res = "FAIL"
                final_detail = msg

            logs.append({"step": "Final Sanity Check", "test_case": "Import Valid Data", "status": "EXECUTED", "result": final_res, "details": final_detail})

        except Exception as e:
            logs.append({"step": "Smart Cycle", "status": "CRASH", "result": "ERROR", "details": str(e)})
        
        return logs
    
    def handle_upload(self, page, target_btn_name, file_name):
        """
        Hàm Upload file đơn lẻ (được nâng cấp để dùng chung logic dọn dẹp với Smart Cycle)
        """
        logs = []
        try:
            # 1. Xác định file
            real_file_name = file_name
            # Nếu user nói chung chung "file csv", thử lấy file fuzzed gần nhất
            if not real_file_name or "file" in real_file_name.lower():
                real_file_name = self.memory.get('LAST_FUZZED_FILE', file_name)
            
            file_path = os.path.join(DOWNLOAD_DIR, real_file_name)
            if not os.path.exists(file_path):
                return [{"step": "Upload", "status": "FAIL", "details": f"File not found: {real_file_name}"}]

            print(f"   📤 Uploading: {real_file_name}")

            # 2. GỌI HÀM DỌN DẸP (HARDCORE CLEANUP)
            # Đảm bảo không còn popup nào từ bước trước ám quẻ
            self._ensure_popup_closed(page)

            # 3. THỰC HIỆN UPLOAD (Dùng lại hàm _perform_upload_action đã viết ở bước trước)
            # Hàm này đã có logic Retry và Force Click
            success = self._perform_upload_action(page, file_path)
            
            status = "FAIL"
            detail = "Upload trigger failed"

            if success:
                print("   🛡️ Checking upload result...")
                # 4. CHỜ KẾT QUẢ (SUCCESS HOẶC ERROR)
                try:
                    # Chờ 1 trong 2 hiện tượng: Lỗi hoặc Thành công
                    # swal2-success-ring: Vòng tròn xanh
                    # swal2-validation-error: Dấu X đỏ hoặc thông báo lỗi
                    any_result = page.locator(".swal2-success-ring, .toast-success, .alert-success").or_(
                                 page.locator(".swal2-validation-error, .swal2-x-mark, .modal-content:has-text('Failed')")).or_(
                                 page.locator("text=Success")).or_(page.locator("text=Import Failed"))
                    
                    any_result.first.wait_for(state="visible", timeout=15000)
                    
                    # Phân tích xem nó là Success hay Fail
                    found_text = any_result.first.inner_text().lower() if any_result.first.is_visible() else ""
                    is_success_icon = page.locator(".swal2-success-ring").is_visible()
                    
                    if is_success_icon or "success" in found_text:
                        status = "PASS"
                        detail = "Upload successfully"
                        print("      ✅ Success detected!")
                    else:
                        status = "FAIL"
                        detail = f"Upload failed: {found_text[:50]}..."
                        print(f"      ⚠️ Error detected: {detail}")

                except Exception as e:
                    status = "TIMEOUT"
                    detail = "No response from server after upload"

                # 5. DỌN DẸP LẦN CUỐI (QUAN TRỌNG)
                # Dù Pass hay Fail, BẮT BUỘC xóa sổ popup để không chặn bước sau
                self._ensure_popup_closed(page)

            logs.append({"step": "Upload", "status": status, "details": detail})

        except Exception as e:
            logs.append({"step": "Upload", "status": "CRASH", "details": str(e)})
            self._ensure_popup_closed(page) # Cứu vãn

        return logs
    
    # ============================Hàm CŨ (ĐÃ BỎ QUA)============================

    # def smart_csv_test(self, page, btn, fn):
    #     op = os.path.join(DOWNLOAD_DIR, fn)
    #     fp = os.path.join(DOWNLOAD_DIR, "fuzzed_" + fn)
    #     logs = []
    #     if not os.path.exists(op): return [{"step":"Smart","status":"FAIL","details":"No file"}]
        
    #     shutil.copy(op, fp)
    #     try:
    #         with open(fp,'r', encoding='utf-8-sig') as f: h=next(csv.reader(f)); h=[x.strip() for x in h]
    #         # Neg Test: Tìm cột Cost/Price để sửa
    #         c = next((x for x in h if any(k in x.lower() for k in ['cost','price'])), h[0])
    #         self._modify_csv(fp, c, "BAD_DATA")
            
    #         s,m = self._upload_file(page, btn, fp)
    #         logs.append({"step":"Neg Test","status":"PASS" if not s else "WARN","details": f"Bad Data: {m}"})
    #         self.close_popup(page)

    #         # Restore
    #         s,m = self._upload_file(page, btn, op) 
    #         logs.append({"step":"Restore","status":"PASS" if s else "FAIL","details": m})
    #         self.close_popup(page)
    #     except Exception as e: logs.append({"step":"Err","status":"FAIL","details":str(e)})
    #     return logs

    def _find_upload_trigger(self, page, name):
        try: 
            if page.get_by_role("button", name=self._safe_compile(name)).first.is_visible(): return page.get_by_role("button", name=self._safe_compile(name)).first
        except: pass
        for k in ["Import","Upload"]:
            try: 
                b = page.get_by_role("button", name=re.compile(k, re.IGNORECASE)).first
                if b.is_visible() and "export" not in b.inner_text().lower(): return b
            except: pass
        return page.locator("button:has(i[class*='import']), button:has(i[class*='upload'])").first

    def _upload_file(self, page, name, fp):
        try:
            t = self._find_upload_trigger(page, name)
            if not t: return False, "No button"
            with page.expect_file_chooser() as fc: t.click()
            fc.value.set_files(fp)
            try: page.wait_for_load_state("networkidle",timeout=5000)
            except: pass
            time.sleep(1)
            err = page.locator(".alert-danger, .error, .modal-title:has-text('Error')").first
            if err.is_visible(): return False, err.inner_text()
            return True, "Success"
        except Exception as e: return False, str(e)

    def _find_download_trigger(self, page, specific_name):
        c = []
        try: c.extend(page.get_by_role("button", name=self._safe_compile(specific_name)).all())
        except: pass
        if not c:
            for k in ["Export", "Download"]: 
                try: c.extend(page.get_by_role("button", name=re.compile(k, re.IGNORECASE)).all())
                except: pass
        v = [b for b in c if b.is_visible() and not any(x in b.inner_text().lower() for x in ["import","upload"])]
        if v:
            for b in v: 
                if b.is_enabled(): return b
            return v[0]
        return None

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

    # ============================
    # MAIN EXECUTION
    # ============================
    def execute_action(self, action_plan):
        report_logs = []
        if isinstance(action_plan, dict): action_plan = [action_plan]
        
        with sync_playwright() as p:
            try:
                browser, page = self.get_existing_page(p)
                for step in action_plan:
                    act = step.get("action"); tgt = str(step.get("target","")); val=str(step.get("value",""))
                    data = step.get("data", {})
                    op = step.get("operation", ""); data_instr = step.get("data", "")
                    popup_data = step.get("data", {}) if act in ["fill_popup", "update_form"] else {}

                    print(f"▶️ Executing: {act} -> {tgt} {val}")

                    if act == "navigate": self._smart_navigate_path(page, step.get("path", [tgt, val]))
                    elif act == "checkbox": report_logs.extend(self.handle_checkbox(page, tgt, val))
                    elif act == "edit_row": self._click_icon_in_row(page, tgt, 'edit')
                    elif act == "clone_row": self._click_icon_in_row(page, tgt, 'clone')
                    elif act == "update_form": 
                        self._smart_update_form(page, popup_data)
                        report_logs.append({"step":"Form","status":"PASS","details":str(popup_data)})
                    elif act == "save_form": 
                        self._save_form(page)
                        report_logs.append({"step":"Save","status":"PASS","details":"OK"})
                    
                    elif act == "download":
                        try:
                            btn = self._find_download_trigger(page, tgt)
                            if btn:
                                with page.expect_download(timeout=30000) as dl:
                                    if btn.is_visible(): btn.click()
                                    else: btn.evaluate("el=>el.click()")
                                dl.value.save_as(os.path.join(DOWNLOAD_DIR, val))
                                report_logs.append({"step": "Download", "status": "PASS", "details": val})
                            else: report_logs.append({"step": "Download", "status": "FAIL", "details": "No Export button"})
                        except Exception as e: report_logs.append({"step": "Download", "status": "FAIL", "details": str(e)})

                    elif act == "smart_test_cycle":
                         logs = self.smart_test_cycle(page, val)
                         logs.extend(self.smart_test_cycle(page, val))
                         report_logs.extend(logs)

                    elif act == "upload": 
                         logs = self.handle_upload(page, tgt, val)
                         logs.extend(self.handle_upload(page, tgt, val))
                        #  report_logs.append({"step":"Upload","status":"PASS" if s else "FAIL","details":m})
                         self.close_popup(page)
                    
                    elif act == "manipulate_csv":
                        report_logs.append({"step":"CSV","status":"PASS","details":op})
                        res = self._process_csv_manipulation(tgt, op, data_instr)
                        report_logs.append({"step": "CSV", "status": "PASS" if "Success" in res else "FAIL", "details": res})

                    time.sleep(1)
                
                return report_logs
            except Exception as e: 
                print(f"CRASH: {e}")
                return [{"step": "System", "status": "CRASH", "details": str(e)}]
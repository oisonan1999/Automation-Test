# automation_modules/smart_tester.py
import os
import time
import pandas as pd
import re
import shutil
import csv
from playwright.sync_api import Page
from streamlit import columns
from .constants import DOWNLOAD_DIR

class SmartTesterMixin:
    """Chứa logic Smart Cycle, Upload, Fuzzing"""
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
            col_lower = col.lower()
            # Chỉ Fuzzing những cột có vẻ là bắt buộc (ID, Name, Gate)
            if "id" in col_lower or "name" in col_lower or "gate" in col_lower:
                # Nếu cột gốc không rỗng mới test lỗi rỗng
                # (Tránh test lỗi rỗng trên cột vốn dĩ được phép rỗng)
                val = str(base_row.get(col, ""))
                if val and val.lower() != "nan":
                    r = base_row.copy(); r[col] = ""
                    add_case(r, f"Bỏ trống '{col}'", f"{col} is required")

        # 2. TYPE MISMATCH (Bắt lỗi Number/Format)
        for col in columns:
            col_lower = col.lower()
            if any(x in col_lower for x in ['cost', 'price', 'amount', 'stock', 'weight']):
                r = base_row.copy(); r[col] = "NotANumber"
                add_case(r, f"Nhập chữ vào cột số '{col}'", "valid integer")
                r2 = base_row.copy(); r2[col] = "-9999"
                add_case(r2, f"Số âm trong '{col}'", "must be positive")

        # 3. SPECIAL CHARS (Bắt lỗi Format/Regex)
        for col in columns:
            if "id" in col.lower():
                r = base_row.copy(); r[col] = "ID_@#$%^&*"
                add_case(r, f"Ký tự lạ trong '{col}'", "invalid format")
                # XSS Test nhẹ
                r2 = base_row.copy(); r2[col] = "<script>alert(1)</script>"
                add_case(r2, f"XSS Script trong '{col}'", "invalid format")

        return pd.DataFrame(fuzzed_rows)
    
    def _ensure_popup_closed(self, page):
        """Dọn dẹp popup: Ưu tiên click nút đóng trước, xóa DOM sau"""
        # 1. Thử click nút OK/Close/Cancel (Cách lịch sự)
        try:
            # Tìm các nút đóng phổ biến
            close_btns = page.locator(".swal2-confirm, .swal2-cancel, .btn-close, .close, button:has-text('Close'), button:has-text('OK')").all()
            for btn in close_btns:
                if btn.is_visible():
                    btn.click()
                    time.sleep(0.2)
        except: pass
        
        time.sleep(0.5)

        # 2. Xóa DOM (Biện pháp mạnh - Cleanup)
        try:
            page.evaluate("""
                document.querySelectorAll('.swal2-container, .modal-backdrop, .modal.show').forEach(e => e.remove());
                document.body.classList.remove('swal2-shown', 'swal2-height-auto', 'modal-open');
                document.body.style.overflow = 'auto';
                document.body.style.height = 'auto';
            """)
        except: pass

    def _perform_upload_action(self, page, file_path):
        """Hàm Upload bao sân: Bấm nút -> Confirm -> Chờ kết quả"""
        max_retries = 3
        wait_timeout = 40
        for attempt in range(max_retries):
            try:
                print(f"      🔄 Upload attempt {attempt+1}...")
                self._ensure_popup_closed(page)
                
                # 1. Chọn file
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
                
                # 2. Vòng lặp chờ kết quả (Tối đa 20s)
                start_wait = time.time()
                while time.time() - start_wait < wait_timeout: 
                    # --- CHIẾN THUẬT MỚI: QUÉT TOÀN BỘ POPUP ---
                    # Tìm bất kỳ popup nào đang hiện (Success, Error, Confirm)
                    popup = page.locator(".swal2-popup, .modal-content, .toast-message").first
                    
                    if popup.is_visible():
                        # Lấy toàn bộ text để phân tích
                        text = popup.inner_text().lower()
                        clean_text = text.replace("\n", " ").strip()[:150] # Lấy 150 ký tự đầu
                        
                        # A. Phân tích: SUCCESS
                        if "success" in text or "hoàn thành" in text:
                            print("      ✅ Success detected!")
                            return True, "Success"
                        
                        # B. Phân tích: ERROR
                        # Nếu thấy từ khóa lỗi -> Return False ngay (đừng bấm OK vội)
                        error_keywords = ["failed", "error", "invalid", "duplicate", "missing", "required", "not found", "lỗi", "thất bại", "warning"]
                        if any(k in text for k in error_keywords) and "confirm" not in text:
                            print(f"      ❌ Error detected: {clean_text}")
                            return False, f"Upload Failed: {clean_text}"

                        # C. Phân tích: CONFIRM (Chỉ bấm nếu là câu hỏi xác nhận)
                        # Tìm nút bấm
                        confirm_btn = popup.locator("button.swal2-confirm, button.btn-primary").first
                        if confirm_btn.is_visible():
                            btn_text = confirm_btn.inner_text().lower()
                            
                            # Chỉ bấm nếu nút là "Upload", "Confirm", "Yes", "Save"
                            # HOẶC nếu text popup có chứa câu hỏi "are you sure", "confirm"
                            is_action_btn = any(x in btn_text for x in ["upload", "confirm", "yes", "save"])
                            is_confirm_msg = any(x in text for x in ["are you sure", "overwrite", "tiếp tục"])
                            
                            if is_action_btn or is_confirm_msg:
                                print(f"      👉 Confirming Upload: {btn_text}")
                                confirm_btn.click(force=True)
                                time.sleep(1)
                                continue
                            
                            # Nếu là nút "OK" đơn thuần mà không có từ khóa Error/Success -> Có thể là Info
                            # Robot sẽ chờ thêm chút nữa xem có thay đổi gì không
                    
                    time.sleep(0.5)
                
                print("      ⚠️ Timeout waiting for response. Retrying...")
                continue

            except Exception as e:
                print(f"      ⚠️ Exception: {e}")
                time.sleep(1)
        
        return False, "Max retries exceeded"
    
    def smart_test_cycle(self, page, target_csv):
        logs = []
        try:
            # 1. Chuẩn bị file
            file_path = os.path.join(DOWNLOAD_DIR, target_csv)
            if not os.path.exists(file_path):
                 files = sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)))
                 if files: file_path = os.path.join(DOWNLOAD_DIR, files[-1]); target_csv = files[-1]
            original_df = pd.read_csv(file_path)
            
            # 2. Phase 1: Fuzzing
            print("   🧪 PHASE 1: Running Fuzz Tests...")
            fuzzed_df = self._generate_fuzzed_data(original_df)
            fuzz_path = os.path.join(DOWNLOAD_DIR, f"fuzzed_{target_csv}")
            meta_cols = ["TEST_CASE", "EXPECTED_KEYWORD"]
            save_cols = [c for c in fuzzed_df.columns if c not in meta_cols]
            fuzzed_df[save_cols].to_csv(fuzz_path, index=False)
            
            self._ensure_popup_closed(page)
            self._perform_upload_action(page, fuzz_path) 
            
            print("      🛡️ Analyzing Error Popup...")
            popup_text = ""
            try:
                # Đọc lỗi kỹ hơn cho Fuzzing phase
                any_popup = page.locator(".swal2-popup, .modal-content, .alert-danger").first
                if any_popup.is_visible(): popup_text = any_popup.inner_text().lower()
                else: popup_text = "no popup appeared"
                self._ensure_popup_closed(page)
            except: popup_text = "error reading popup"

            for idx, row in fuzzed_df.iterrows():
                expected = str(row["EXPECTED_KEYWORD"]).lower()
                if expected in popup_text: res = "PASS"; detail = f"Caught: '{expected}'"
                else: res = "FAIL"; detail = f"Missed: '{expected}'"
                logs.append({"step": f"Test Case #{idx+1}", "test_case": row["TEST_CASE"], "status": "EXECUTED", "result": res, "details": detail})

            # 3. Phase 2: Valid Data (FIX #2 & #3)
            print("   ✨ PHASE 2: Verify Valid Import...")
            valid_df = original_df.iloc[[0]].copy()
            current_timestamp = int(time.time())
            
            # --- LOGIC SINH ID THÔNG MINH (SMART PREFIX) ---
            for col in valid_df.columns:
                col_lower = col.lower()
                
                # tab_id: Là Enum cố định (feature, prize_wall...)
                # group_id: Thường là FK, không nên random
                exclude_list = ["tab_id", "tabid", "group_id", "parent_id"]
                if any(ex in col_lower for ex in exclude_list):
                    print(f"      ℹ️ Skipping ID generation for excluded column: '{col}'")
                    continue
                # Chỉ xử lý các cột là Key hoặc ID
                if "id" in col_lower or "key" in col_lower:
                    original_val = valid_df.iloc[0][col]
                    
                    # FIX #2: Nếu cột gốc RỖNG, thì KHÔNG sinh giá trị mới (Giữ nguyên rỗng)
                    if pd.isna(original_val) or str(original_val).strip() == "":
                        continue 

                    # FIX #3: Prefix động dựa theo tên cột
                    prefix = "" # Mặc định
                    
                    if "bagid" in col_lower: prefix = "Grabbag_"
                    elif "boost" in col_lower: prefix = "Boost_"
                    elif "wrestler" in col_lower: prefix = "Wrestler_"
                    elif "skin" in col_lower: prefix = "Skin_"
                    elif "perk" in col_lower: prefix = "Perk_"
                    elif "gear" in col_lower: prefix = "Gear_"
                    elif "offer" in col_lower: prefix = "offer_"
                    elif "section" in col_lower in col_lower: prefix = "Section_" # Ví dụ OfferSectionID
                    
                    # Tạo ID mới: Prefix + Auto + Timestamp
                    new_id = f"{prefix}Auto_{current_timestamp}"
                    valid_df[col] = new_id
                    print(f"      ℹ️ Generated ID for '{col}': {new_id}")

            # Logic ShowInStore (Giữ nguyên)
            show_col = next((c for c in valid_df.columns if c.lower() == "showinstore"), None)
            if show_col:
                val = str(valid_df.iloc[0][show_col]).strip()
                if val == "0" or val == "False":
                    dependent_cols = ["OfferDisplayID", "OfferParentID", "OfferSectionID"]
                    for dep in dependent_cols:
                        target_col = next((c for c in valid_df.columns if c.lower() == dep.lower()), None)
                        if target_col: valid_df.at[valid_df.index[0], target_col] = "" 

            valid_path = os.path.join(DOWNLOAD_DIR, f"valid_{target_csv}")
            valid_df.to_csv(valid_path, index=False)
            
            self._ensure_popup_closed(page)
            is_success, msg = self._perform_upload_action(page, valid_path)
            
            final_res = "PASS" if is_success else "FAIL"
            final_detail = "Successfully imported valid data" if is_success else msg
            self._ensure_popup_closed(page)

            logs.append({"step": "Final Sanity Check", "test_case": "Import Valid Data", "status": "EXECUTED", "result": final_res, "details": final_detail})

        except Exception as e:
            logs.append({"step": "Smart Cycle", "status": "CRASH", "result": "ERROR", "details": str(e)})
        
        return logs
    
    def handle_upload(self, page, target_btn_name, file_name):
        """Hàm xử lý Upload chính"""
        logs = []
        try:
            real_file_name = file_name
            
            # Chỉ fallback khi tên file là 'file.csv' hoặc rỗng
            if not real_file_name or real_file_name.lower().strip() == "file.csv":
                real_file_name = self.memory.get('LAST_FUZZED_FILE', file_name)
            
            file_path = os.path.join(DOWNLOAD_DIR, real_file_name)
            if not os.path.exists(file_path):
                return [{"step": "Upload", "status": "FAIL", "details": f"File not found: {real_file_name}"}]

            print(f"   📤 Uploading: {real_file_name}")
            self._ensure_popup_closed(page)

            # Gọi hàm thực thi và lấy kết quả trực tiếp
            success, msg = self._perform_upload_action(page, file_path)
            
            status = "PASS" if success else "FAIL"
            detail = "Upload successfully" if success else f"Upload failed: {msg}"
            
            self._ensure_popup_closed(page)

            logs.append({"step": "Upload", "status": status, "details": detail})

        except Exception as e:
            logs.append({"step": "Upload", "status": "CRASH", "details": str(e)})
            self._ensure_popup_closed(page)
        
        return logs
    
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
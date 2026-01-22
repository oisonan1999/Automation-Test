# automation_modules/smart_tester.py
import os
import time
import pandas as pd
import re
import shutil
import csv
from playwright.sync_api import Page
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
        """Hàm Upload bao sân: Bấm nút -> Confirm -> Chờ kết quả"""
        max_retries = 3
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
                        # Fallback: click vào input file ẩn
                        page.locator("input[type='file']").evaluate("e => e.click()")
                
                file_chooser = fc_info.value
                file_chooser.set_files(file_path)
                
                # 2. Vòng lặp chờ kết quả (Tối đa 20s)
                start_wait = time.time()
                while time.time() - start_wait < 20: 
                    # A. Check Success (Ưu tiên)
                    success_signal = page.locator(".swal2-success-ring, .toast-success").or_(page.locator("text=Success"))
                    if success_signal.first.is_visible():
                        print("      ✅ Success detected!")
                        return True, "Success"

                    # B. Check Error (NÂNG CẤP: Đọc lỗi kỹ hơn)
                    # Tìm bất kỳ dấu hiệu lỗi nào
                    error_indicators = page.locator(".swal2-validation-error, .swal2-x-mark, .swal2-icon-error").or_(
                                       page.locator("text=Import Failed")).or_(
                                       page.locator(".modal-title:has-text('Error')"))
                    
                    if error_indicators.first.is_visible():
                        # Cố gắng đọc nội dung lỗi từ các container text phổ biến
                        err_text = ""
                        
                        # Ưu tiên 1: Validation Message của SweetAlert (Thường chứa lỗi CSV)
                        if page.locator("#swal2-validation-message").is_visible():
                            err_text = page.locator("#swal2-validation-message").inner_text()
                        
                        # Ưu tiên 2: HTML Container chính
                        elif page.locator("#swal2-html-container").is_visible():
                            err_text = page.locator("#swal2-html-container").inner_text()
                            
                        # Ưu tiên 3: Nếu là modal Bootstrap
                        elif page.locator(".modal-body").is_visible():
                            err_text = page.locator(".modal-body").inner_text()
                            
                        # Fallback: Lấy text từ chính element phát hiện lỗi (nếu nó là text)
                        if not err_text:
                            err_text = error_indicators.first.inner_text()
                            
                        if not err_text: err_text = "Unknown Error (Icon detected but no text)"
                        
                        print(f"      ❌ Error detected: {err_text[:100]}")
                        return False, f"Upload Failed: {err_text[:100]}"

                    # C. Check Confirm Button (Nếu cần bấm thêm bước xác nhận)
                    confirm_btn = page.locator(".modal.show button.btn-primary:has-text('Upload'), button.swal2-confirm, button:has-text('Confirm')").first
                    if confirm_btn.is_visible():
                        confirm_btn.click(force=True)
                        time.sleep(1)
                        continue 

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
                any_popup = page.locator(".swal2-popup, .modal-content").first
                if any_popup.is_visible(): popup_text = any_popup.inner_text().lower()
                else: popup_text = "no popup appeared"
                self._ensure_popup_closed(page)
            except: popup_text = "error reading popup"

            for idx, row in fuzzed_df.iterrows():
                expected = str(row["EXPECTED_KEYWORD"]).lower()
                if expected in popup_text: res = "PASS"; detail = f"Caught: '{expected}'"
                else: res = "FAIL"; detail = f"Missed: '{expected}'"
                logs.append({"step": f"Test Case #{idx+1}", "test_case": row["TEST_CASE"], "status": "EXECUTED", "result": res, "details": detail})

            # 3. Phase 2: Valid Data
            print("   ✨ PHASE 2: Verify Valid Import...")
            valid_df = original_df.iloc[[0]].copy()
            current_timestamp = int(time.time())
            
            # Logic sinh ID
            for col in valid_df.columns:
                col_lower = col.lower()
                if "id" in col_lower or "key" in col_lower:
                    if "bagid" in col_lower: new_id = f"Grabbag_Auto_{current_timestamp}"
                    else: new_id = f"Auto_{current_timestamp}"
                    valid_df[col] = new_id

            # Logic ShowInStore
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
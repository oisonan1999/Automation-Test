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
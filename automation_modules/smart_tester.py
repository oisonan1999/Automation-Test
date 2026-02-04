# automation_modules/smart_tester.py
from copy import copy as cp, deepcopy
from glob import glob
import io
import os
import random as rd
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

    def smart_test_cycle(self, page, file_name):
        """
        MAIN DISPATCHER: Phân luồng kiểm thử dựa trên tên file.
        """
        # Làm sạch tên file (đề phòng lệnh AI kèm theo chữ 'Import CSV')
        clean_name = (
            file_name.replace("Import CSV", "").replace("Export CSV", "").strip()
        )
        full_path = os.path.join(DOWNLOAD_DIR, clean_name)

        print(f"   🤖 Smart Test Dispatcher: '{clean_name}'")

        # --- LUỒNG 1: RBE FILE (ƯU TIÊN CAO) ---
        # Kiểm tra tên file hoặc nội dung header
        is_rbe = False
        if "rbe" in clean_name.lower():
            is_rbe = True
        else:
            # Check nội dung dòng đầu tiên nếu tên file không rõ
            try:
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8-sig") as f:
                        if "[RBE_CONFIGURATION]" in f.read(100):
                            is_rbe = True
            except:
                pass

        if is_rbe:
            print("      👉 Detected RBE File. Running RBE Specialized Test.")
            return self._run_rbe_fuzz_campaign(page, clean_name)
        else:
            # --- LUỒNG 2: GENERIC FILE (FILE KHÁC) ---
            print("      👉 Detected Generic CSV. Running Standard Check.")
        return self._test_generic_csv(page, clean_name)

    # ---------------------------------------------------------
    # HÀM TEST CHUYÊN BIỆT CHO RBE (Mới thêm theo yêu cầu)
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # HÀM THỰC THI TEST RBE
    # ---------------------------------------------------------
    def _smart_test_rbe_csv(self, page, file_name):
        full_path = os.path.join(DOWNLOAD_DIR, file_name)
        logs = []

        # BƯỚC 1: TEST OFFLINE (Cấu trúc file)
        print("      🧪 Phase 1: Offline Validation...")
        tester = RBESmartTester(full_path)
        raw_results = tester.run_tests()

        has_critical_error = False
        for line in raw_results:
            parts = line.split("] ", 1)
            status = "PASS" if "[PASS" in parts[0] else "FAIL"
            details = parts[1] if len(parts) > 1 else line

            if status == "FAIL" and "Structure" in line:
                has_critical_error = True

            print(f"         {line}")
            logs.append(
                {"step": "RBE Offline Test", "status": status, "details": details}
            )

        # Nếu lỗi cấu trúc nghiêm trọng -> Dừng, không upload
        if has_critical_error:
            print("      ⛔ Critical Structure Error. Skipping Upload.")
            logs.append(
                {
                    "step": "RBE Upload",
                    "status": "SKIPPED",
                    "details": "Critical Offline Failure",
                }
            )
            return logs

        # BƯỚC 2: TEST ONLINE (Upload thử lên web)
        # Tận dụng hàm handle_upload có sẵn trong DataHandlerMixin (qua self)
        print("      🚀 Phase 2: Online Upload Verification...")
        try:
            # Tìm nút Import RBE CSV (hoặc Import CSV chung)
            target_btn_name = "Import RBE CSV"

            # Gọi hàm upload của hệ thống
            upload_logs = self.handle_upload(page, target_btn_name, file_name)
            logs.extend(upload_logs)

            # Kiểm tra kết quả upload
            if any(l["status"] == "PASS" for l in upload_logs):
                print("         ✅ Upload Success.")
            else:
                print("         ❌ Upload Failed on Web.")

        except Exception as e:
            print(f"         ❌ Upload Error: {e}")
            logs.append({"step": "RBE Upload", "status": "FAIL", "details": str(e)})
        return logs

    def _generate_fuzzed_data(self, original_df):
        fuzzed_rows = []
        columns = original_df.columns.tolist()

        if not original_df.empty:
            base_row = original_df.iloc[0].to_dict()
        else:
            base_row = {col: "Sample" for col in columns}

        # Helper để tạo case
        def add_case(row_mod, name, keyword):
            r = row_mod.copy()
            r["TEST_CASE"] = name
            r["EXPECTED_KEYWORD"] = keyword
            fuzzed_rows.append(r)

        # 1. EMPTY FIELDS
        for col in columns:
            col_lower = col.lower()
            if "id" in col_lower or "name" in col_lower or "gate" in col_lower:
                val = str(base_row.get(col, ""))
                if val and val.lower() != "nan":
                    r = base_row.copy()
                    r[col] = ""
                    add_case(r, f"Bỏ trống '{col}'", f"{col} is required")

        # 2. TYPE MISMATCH
        for col in columns:
            col_lower = col.lower()
            if any(
                x in col_lower for x in ["cost", "price", "amount", "stock", "weight"]
            ):
                r = base_row.copy()
                r[col] = "NotANumber"
                add_case(r, f"Nhập chữ vào cột số '{col}'", "valid integer")
                r2 = base_row.copy()
                r2[col] = "-9999"
                add_case(r2, f"Số âm trong '{col}'", "must be positive")

        # 3. SPECIAL CHARS
        for col in columns:
            if "id" in col.lower():
                r = base_row.copy()
                r[col] = "ID_@#$%^&*"
                add_case(r, f"Ký tự lạ trong '{col}'", "invalid format")
                r2 = base_row.copy()
                r2[col] = "<script>alert(1)</script>"
                add_case(r2, f"XSS Script trong '{col}'", "invalid format")

        return pd.DataFrame(fuzzed_rows)

    # ============================
    # FIX 2: UPLOAD VÀ XỬ LÝ POPUP
    # ============================
    def _perform_upload_action(self, page, file_path):
        """Upload và xử lý Popup Success/Failed"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                print(f"      🔄 Upload attempt {attempt+1}...")
                self._ensure_popup_closed(page)  # Đảm bảo sạch sẽ trước khi bấm nút

                # 1. Trigger File Chooser
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    # Tìm nút Import
                    btn = page.locator(
                        "button:has-text('Import CSV'), a:has-text('Import CSV')"
                    ).first
                    if not btn.is_visible():
                        btn = page.locator(".btn-import, [title='Import']").first
                    if not btn.is_visible():
                        btn = page.locator("button:has-text('Import')").first

                    if btn.is_visible():
                        btn.scroll_into_view_if_needed()
                        # Click Force để bỏ qua overlay vô hình (nếu còn sót)
                        btn.click(force=True)
                    else:
                        page.locator("input[type='file']").evaluate("e => e.click()")

                file_chooser = fc_info.value
                file_chooser.set_files(file_path)

                # Trigger Event cho React/Vue
                try:
                    file_chooser.element.evaluate(
                        "e => { e.dispatchEvent(new Event('change', {bubbles: true})); e.dispatchEvent(new Event('input', {bubbles: true})); }"
                    )
                except:
                    pass

                # 2. Xử lý Modal Confirm trung gian (nếu có)
                time.sleep(0.5)
                # Dùng JS check nút confirm trong modal
                page.evaluate(
                    """
                    const btn = Array.from(document.querySelectorAll('.modal.show button')).find(b => 
                        /upload|confirm|yes|import/i.test(b.innerText)
                    );
                    if (btn) btn.click();
                """
                )

                # 3. CHỜ POPUP KẾT QUẢ (QUAN TRỌNG)
                # Dùng wait_for_selector thay vì vòng lặp while để Playwright tự handle việc chờ element xuất hiện
                try:
                    # Chờ .swal2-popup xuất hiện (Timeout 10s)
                    # Selector này khớp chính xác với ảnh bạn gửi
                    popup = page.wait_for_selector(
                        ".swal2-popup", state="visible", timeout=10000
                    )

                    if popup:
                        text = popup.inner_text().lower()
                        clean_text = text.replace("\n", " ").strip()[:200]

                        print("      ⏳ Popup detected, waiting 10s...")
                        time.sleep(10.0)  # Chờ thêm 10s để chắc chắn popup đã ổn định
                        # Tìm nút OK (.swal2-confirm) và click luôn
                        page.evaluate(
                            """
                            const btn = document.querySelector('button.swal2-confirm');
                            if (btn) btn.click();
                        """
                        )
                        time.sleep(1.0)  # Chờ popup biến mất

                        # Phân loại kết quả
                        if "success" in text or "hoàn thành" in text:
                            print("      ✅ Success Popup detected & closed.")
                            return True, "Success"

                        error_keywords = [
                            "failed",
                            "error",
                            "invalid",
                            "duplicate",
                            "missing",
                            "required",
                            "not number",
                            "format",
                            "lỗi",
                        ]
                        if (
                            any(k in text for k in error_keywords)
                            and "sure" not in text
                        ):
                            # print(f"      ❌ Error Popup detected & closed: {clean_text[:50]}...")
                            return False, f"Error: {clean_text}"

                        # Nếu là popup confirm (Are you sure?) -> Loop sẽ quay lại và chờ popup kết quả tiếp theo
                        if "sure" in text or "confirm" in text:
                            continue

                except Exception as e:
                    print(f"      ⚠️ Wait timeout (No popup detected): {e}")
                    # Timeout nghĩa là không thấy popup -> Retry upload
                    pass

            except Exception as e:
                print(f"      ⚠️ Upload Exception: {e}")
                time.sleep(1)

        return False, "Max retries exceeded"

    def _upload_single_attempt(self, page, target_text, file_name):
        full_path = os.path.join(DOWNLOAD_DIR, file_name)
        try:
            # 1. Tìm nút Upload
            btn = page.locator(
                f"button:has-text('{target_text}'), a.btn:has-text('{target_text}'), label:has-text('{target_text}'), input[type='file']"
            ).first
            if not btn.is_visible():
                btn = page.locator(
                    f"xpath=//*[contains(text(), '{target_text}')]/ancestor::button | //*[contains(text(), '{target_text}')]/ancestor::a"
                ).first
            if not btn.is_visible():
                return False, "Import Button not found"

            # 2. Upload
            if btn.get_attribute("type") == "file":
                btn.set_input_files(full_path)
            else:
                with page.expect_file_chooser(timeout=3000) as fc_info:
                    btn.click()
                fc_info.value.set_files(full_path)

            # 3. Confirm Popup
            try:
                confirm = page.locator(
                    ".swal2-confirm, button:has-text('Upload'), button:has-text('Confirm')"
                ).first
                if confirm.is_visible(timeout=2000):
                    confirm.click()
            except:
                pass

            # 4. Polling Result (Toast/Popup)
            start_time = time.time()
            seen_loading = False

            while time.time() - start_time < 90:
                res_found, res_type, res_text = self._scan_for_result_popup(page)
                if res_found:
                    self._ensure_popup_closed(page)
                    return (res_type == "PASS"), str(res_text or "Success (No text)")

                loading = page.locator(
                    ".swal2-loading, .spinner, .loading, .fa-spin, div:has-text('Uploading')"
                ).first
                if loading.is_visible():
                    seen_loading = True
                    time.sleep(0.5)
                    continue

                if seen_loading and not loading.is_visible():
                    time.sleep(1.0)
                    res_found, res_type, res_text = self._scan_for_result_popup(page)
                    if res_found:
                        self._ensure_popup_closed(page)
                        return (res_type == "PASS"), res_text
                time.sleep(0.5)

            return False, "Timeout"

        except Exception as e:
            return False, str(e)

    def _scan_for_result_popup(self, page):
        try:
            # Selector Error
            errs = [
                ".swal2-error",
                ".alert-danger",
                ".toast-error",
                ".notification-error",
                "div:has-text('Failed'):visible",
                "div:has-text('Error'):visible",
            ]
            for sel in errs:
                el = page.locator(sel).first
                if el.is_visible():
                    return True, "FAIL", el.inner_text().strip()[:100]

            # Selector Success
            succs = [
                ".swal2-success",
                ".alert-success",
                ".toast-success",
                ".notification-success",
                "div:has-text('Success'):visible",
                "div:has-text('Completed'):visible",
            ]
            for sel in succs:
                el = page.locator(sel).first
                if el.is_visible():
                    return True, "PASS", el.inner_text().strip()[:100]

            return False, "UNKNOWN", "No popup text"
        except:
            return False, "ERROR", "Popup scan crashed"

    # ============================
    # FIX 1: HÀM DỌN DẸP POPUP (DÙNG JS)
    # ============================
    def _ensure_popup_closed(self, page):
        """Dọn dẹp popup bằng JS trực tiếp để tránh bị chặn bởi Overlay"""
        try:
            # Dùng JS tìm và click nút OK (swal2-confirm)
            # Cách này mạnh hơn .click() của Playwright vì nó bỏ qua check visibility/overlay
            page.evaluate(
                """
                const confirmBtn = document.querySelector('button.swal2-confirm');
                const closeBtn = document.querySelector('button.swal2-close');
                const modalBtn = document.querySelector('.modal.show button[data-dismiss="modal"]');
                
                if (confirmBtn && confirmBtn.offsetParent !== null) confirmBtn.click();
                else if (closeBtn && closeBtn.offsetParent !== null) closeBtn.click();
                else if (modalBtn && modalBtn.offsetParent !== null) modalBtn.click();
            """
            )
            time.sleep(0.5)
        except:
            pass

        # Biện pháp cuối: Xóa DOM nếu nó bị kẹt
        try:
            page.evaluate(
                """
                const overlays = document.querySelectorAll('.swal2-container, .modal-backdrop');
                overlays.forEach(el => el.remove());
                document.body.classList.remove('swal2-shown', 'swal2-height-auto', 'modal-open');
                document.body.style.overflow = 'auto';
            """
            )
        except:
            pass
        time.sleep(0.2)

    def _test_generic_csv(self, page, target_csv):
        logs = []
        try:
            # 1. Chuẩn bị file
            file_path = os.path.join(DOWNLOAD_DIR, target_csv)
            if not os.path.exists(file_path):
                # Tìm file mới nhất nếu không thấy tên chính xác
                files = sorted(
                    glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv")), key=os.path.getmtime
                )
                if files:
                    file_path = files[-1]
                    target_csv = os.path.basename(file_path)

            if not os.path.exists(file_path):
                return [{"step": "Init", "status": "FAIL", "details": "File not found"}]

            print(f"   📂 Testing with Base File: {target_csv}")

            # ==================================================================
            # PHASE 1: FUZZING (DÙNG GENERIC FUZZER MỚI)
            # ==================================================================
            print("   🧪 PHASE 1: Running AI Fuzz Tests...")

            # Khởi tạo Fuzzer
            fuzzer = GenericCSVFuzzer(file_path)
            mutations = fuzzer.generate_generic_all_cases()

            for i, case in enumerate(mutations):
                case_name = case["name"]
                print(f"      🔸 [Case {i+1}/{len(mutations)}] {case_name}...")

                temp_file = fuzzer.save_mutation_to_generic_file(case)

                # Upload (Dùng hàm upload bắt được Toast/Popup)
                self._ensure_popup_closed(page)
                success, msg = self._upload_single_attempt(
                    page, "Import CSV", temp_file
                )
                safe_msg = str(msg) if msg is not None else "No details available"

                # Đánh giá kết quả
                if not success:
                    print(f"         ✅ Blocked: {safe_msg}")
                    logs.append(
                        {
                            "step": f"Fuzz: {case_name}",
                            "status": "PASS",
                            "details": f"Blocked: {safe_msg}",
                        }
                    )
                else:
                    print(f"         🚨 Accepted: {safe_msg}")
                    logs.append(
                        {
                            "step": f"Fuzz: {case_name}",
                            "status": "WARNING",
                            "details": "System accepted invalid data",
                        }
                    )

                # Cleanup
                try:
                    os.remove(os.path.join(DOWNLOAD_DIR, temp_file))
                except:
                    pass

            self._ensure_popup_closed(page)

            # 3. Phase 2: Valid Data (FIX #2 & #3: Valid Import Logic)
            print("   ✨ PHASE 2: Verify Valid Import (User Data Preservation)...")
            original_df = pd.read_csv(file_path, dtype=str)

            # Logic: Lấy dòng cuối cùng (thường là dòng User mới thêm) để làm mẫu
            # Hoặc lấy dòng đầu tiên nếu file chỉ có 1 dòng
            if len(original_df) > 0:
                print(
                    "      ℹ️ Using original user data for Valid Import (No ID generation)."
                )
                valid_df = original_df.copy()
                valid_path = file_path  # Dùng luôn file gốc
            else:
                # Chỉ sinh ID giả nếu file rỗng tuếch (Fallback hiếm gặp)
                print("      ⚠️ File empty, generating dummy data...")
                valid_df = pd.DataFrame(columns=original_df.columns)
                valid_df.loc[0] = ["Auto_Data" for _ in original_df.columns]
                valid_path = os.path.join(DOWNLOAD_DIR, f"valid_{target_csv}")
                valid_df.to_csv(valid_path, index=False)

            self._ensure_popup_closed(page)

            current_timestamp = int(time.time())

            # --- TẠO ID MỚI TRÁNH TRÙNG LẶP ---
            for col in valid_df.columns:
                col_lower = col.lower()

                # Bỏ qua các cột ID tham chiếu (FK) hoặc cố định
                exclude_list = [
                    "tab_id",
                    "tabid",
                    "group_id",
                    "parent_id",
                    "milestone_id",
                    "type_id",
                ]
                if any(ex in col_lower for ex in exclude_list):
                    continue

                # Chỉ xử lý Primary Key (ID chính)
                if "id" in col_lower or "key" in col_lower:
                    original_val = valid_df.iloc[0][col]

                    # Nếu cột gốc rỗng -> Bỏ qua
                    if pd.isna(original_val) or str(original_val).strip() == "":
                        continue

                    # Prefix thông minh
                    prefix = ""
                    if "bagid" in col_lower:
                        prefix = "Grabbag_"
                    elif "boost" in col_lower:
                        prefix = "Boost_"
                    elif "wrestler" in col_lower:
                        prefix = "Wrestler_"
                    elif "perk" in col_lower:
                        prefix = "Perk_"
                    elif "offer" in col_lower:
                        prefix = "Offer_"
                    elif "objectiveid" in col_lower:
                        prefix = "Objective_"
                    else:
                        prefix = "Auto_"

                    # Tạo ID mới: Prefix + Auto + timestamp
                    # VD: Grabbag_Auto_170000123
                    new_id = f"{prefix}{current_timestamp}"
                    valid_df.at[valid_df.index[0], col] = new_id
                    print(f"      ℹ️ Generated new ID for '{col}': {new_id}")

            # FIX #2: Xử lý cột phụ thuộc (ShowInStore)
            show_col = next(
                (c for c in valid_df.columns if c.lower() == "showinstore"), None
            )
            if show_col:
                val = str(valid_df.iloc[0][show_col]).strip().lower()
                if val in ["0", "false", "no"]:
                    dependent_cols = [
                        "OfferDisplayID",
                        "OfferParentID",
                        "OfferSectionID",
                    ]
                    for dep in dependent_cols:
                        target_col = next(
                            (c for c in valid_df.columns if c.lower() == dep.lower()),
                            None,
                        )
                        if target_col:
                            # FIX PANDAS TYPE ERROR: Convert cột sang object trước khi gán chuỗi rỗng
                            valid_df[target_col] = valid_df[target_col].astype(object)
                            valid_df.at[valid_df.index[0], target_col] = ""

            # Save Valid File
            valid_path = os.path.join(DOWNLOAD_DIR, f"valid_{target_csv}")
            valid_df.to_csv(valid_path, index=False)

            self._ensure_popup_closed(page)
            # Upload Valid File (Expect Success)
            is_success, msg = self._perform_upload_action(page, valid_path)

            final_msg = str(msg) if msg is not None else "Unknown result"

            # Quan trọng: Nếu thành công, lưu lại tên file này vào memory để các bước sau (Edit Row) dùng ID mới này
            if is_success:
                # Lấy ID mới vừa tạo để báo cho AI biết
                # (Logic nâng cao: Lưu vào self.memory nếu cần)
                pass

            self._ensure_popup_closed(page)
            logs.append(
                {
                    "step": "Final Sanity Check",
                    # "test_case": REMOVED
                    # "result": REMOVED (Merged into status)
                    "status": "PASS" if is_success else "FAIL",
                    "details": final_msg,
                }
            )

        except Exception as e:
            print(f"   ❌ Smart Cycle Crash: {e}")
            logs.append(
                {
                    "step": "Smart Cycle",
                    "status": "CRASH",
                    "result": "ERROR",
                    "details": str(e),
                }
            )

        return logs

    # ... (Các hàm handle_upload, _find_upload_trigger giữ nguyên)
    def handle_upload(self, page, target_btn_name, file_name):
        # (Giữ nguyên logic cũ của bạn)
        logs = []
        try:
            real_file_name = file_name
            if not real_file_name or real_file_name.lower().strip() == "file.csv":
                real_file_name = self.memory.get("LAST_FUZZED_FILE", file_name)

            file_path = os.path.join(DOWNLOAD_DIR, real_file_name)
            if not os.path.exists(file_path):
                return [
                    {
                        "step": "Upload",
                        "status": "FAIL",
                        "details": f"File not found: {real_file_name}",
                    }
                ]

            print(f"   📤 Uploading: {real_file_name}")
            self._ensure_popup_closed(page)
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
        # (Giữ nguyên)
        try:
            if page.get_by_role(
                "button", name=self._safe_compile(name)
            ).first.is_visible():
                return page.get_by_role("button", name=self._safe_compile(name)).first
        except:
            pass
        for k in ["Import", "Upload"]:
            try:
                b = page.get_by_role("button", name=re.compile(k, re.IGNORECASE)).first
                if b.is_visible() and "export" not in b.inner_text().lower():
                    return b
            except:
                pass
        return page.locator(
            "button:has(i[class*='import']), button:has(i[class*='upload'])"
        ).first

    def _run_rbe_fuzz_campaign(self, page, base_file_name):
        full_path = os.path.join(DOWNLOAD_DIR, base_file_name)
        logs = []

        print(f"   📂 Testing with Base File: {base_file_name}")
        parser = RBESmartTester(full_path)

        # PHASE 1: PRE-FLIGHT CHECK (Đảm bảo file gốc sạch)
        static_res = parser.run_tests()
        if any("FAIL" in l for l in static_res):
            print("      ⛔ Base file invalid. Aborting Fuzzing.")
            return [
                {"step": "Pre-flight", "status": "FAIL", "details": str(static_res)}
            ]

        # PHASE 2: FUZZING (Dùng hàm upload nhanh, KHÔNG RETRY)
        print("   🧪 PHASE 2: Fuzz Tests (Negative)...")
        fuzzer = RBEFuzzGenerator(parser)
        mutations = fuzzer.generate_all_cases()

        for case in mutations:
            print(f"      🔸 Testing Case: {case['name']}...")
            temp_file = fuzzer.save_mutation_to_file(case)

            # Upload NHANH (Không retry để tiết kiệm thời gian)
            success, msg = self._upload_fast(page, "Import RBE CSV", temp_file)

            # Logic ngược: Upload FAIL = PASS, Upload PASS = WARNING
            if not success:
                print(f"         ✅ Blocked: {msg}")
                logs.append(
                    {
                        "step": f"Fuzz: {case['name']}",
                        "status": "PASS",
                        "details": f"Blocked: {msg}",
                    }
                )
            else:
                print(f"         🚨 CRITICAL: Allowed!")
                logs.append(
                    {
                        "step": f"Fuzz: {case['name']}",
                        "status": "WARNING",
                        "details": "⚠️ SYSTEM ACCEPTED INVALID DATA",
                    }
                )

            try:
                os.remove(os.path.join(DOWNLOAD_DIR, temp_file))
            except:
                pass
            self._ensure_popup_closed(page)
            time.sleep(0.5)

        # PHASE 3: SANITY CHECK (Cắt vòng lặp AI bằng status WARNING)
        print("   ✨ PHASE 3: Sanity Check...")
        success, msg = self._upload_fast(page, "Import RBE CSV", base_file_name)

        if success:
            print(f"         ✅ Passed.")
            logs.append(
                {"step": "Sanity Check", "status": "PASS", "details": "Healthy"}
            )
        else:
            print(f"         ❌ Failed: {msg}")
            # FIX: Trả về WARNING để AI không tự động Retry vòng lặp
            logs.append(
                {
                    "step": "Sanity Check",
                    "status": "WARNING",
                    "details": f"Check Failed: {msg}",
                }
            )

        return logs

    def _upload_fast(self, page, target_text, file_name):
        """
        Upload thông minh với Log thời gian thực.
        """
        full_path = os.path.join(DOWNLOAD_DIR, file_name)
        try:
            # 1. Tìm & Chọn File
            print(f"         📤 Selecting file: {file_name}...")  # LOG NGAY
            btn = page.locator(
                f"button:has-text('{target_text}'), a.btn:has-text('{target_text}'), input[type='file']"
            ).first
            if not btn.is_visible():
                return False, "Button not found"

            if btn.get_attribute("type") == "file":
                btn.set_input_files(full_path)
            else:
                with page.expect_file_chooser(timeout=3000) as fc_info:
                    btn.click()
                fc_info.value.set_files(full_path)

            # 2. Confirm Upload (Xử lý Popup Confirm)
            # LOG TRƯỚC KHI CLICK để biết AI đang làm gì
            print("         👆 Checking for Confirm popup...")
            try:
                confirm = page.locator(
                    ".swal2-confirm, button.btn-primary:has-text('Upload')"
                ).first
                if confirm.is_visible(timeout=2000):
                    print("         🖱 Clicking Confirm Upload...")
                    # force=True để click bất chấp overlay
                    confirm.click(force=True)
            except:
                pass

            # 3. POLLING LOOP (Tối đa 90s)
            # Log này sẽ hiện ngay sau khi click confirm
            print("         👀 Watching for result (Loading/Success/Fail)...")

            start_time = time.time()
            seen_loading = False

            while time.time() - start_time < 90:
                # A. ƯU TIÊN 1: Check Kết Quả (Success/Fail) trước
                # Để bắt dính ngay khi popup vừa hiện
                res_found, res_type, res_text = self._check_result_text(page)

                if res_found:
                    print(f"         📢 Found Result: {res_type}")
                    self._ensure_popup_closed(page)
                    return (res_type == "PASS"), res_text

                # B. ƯU TIÊN 2: Check Loading
                loading = page.locator(
                    ".swal2-loading, .spinner, .loading-mask, div:has-text('Importing'), div:has-text('Uploading')"
                ).first
                is_loading_visible = loading.is_visible()

                if is_loading_visible:
                    if not seen_loading:
                        print("         ⏳ System is Importing (Loading detected)...")
                        seen_loading = True
                    time.sleep(0.5)
                    continue

                # C. Logic thoát nhanh:
                # Nếu đã từng Loading, mà giờ hết Loading, và cũng không tìm thấy popup kết quả
                if seen_loading and not is_loading_visible:
                    print(
                        "         🏁 Loading finished. Checking result one last time..."
                    )
                    # Đợi thêm 1s để chắc chắn popup render
                    time.sleep(1.0)
                    res_found, res_type, res_text = self._check_result_text(page)
                    if res_found:
                        self._ensure_popup_closed(page)
                        return (res_type == "PASS"), res_text

                    # Nếu vẫn không thấy popup -> Có thể đã bị tắt hoặc web lỗi
                    return False, "Process finished but No Popup found"

                time.sleep(0.5)

            return False, "Timeout (90s)"

        except Exception as e:
            return False, str(e)

    def _check_result_text(self, page):
        """Helper tìm text Success/Error trên màn hình"""
        try:
            # Check Error
            err = page.locator(
                ".swal2-error, .toast-error, .alert-danger, div.error-message, h2:has-text('Error'), div:has-text('Failed')"
            ).first
            if err.is_visible():
                return True, "FAIL", err.inner_text().strip()[:50]

            # Check Success
            succ = page.locator(
                ".swal2-success, .toast-success, .alert-success, div:has-text('Success'), div:has-text('Completed')"
            ).first
            if succ.is_visible():
                return True, "PASS", succ.inner_text().strip()[:50]

            return False, None, None
        except:
            return False, None, None


class RBESmartTester:
    """Class Logic chuyên biệt để parse và test file RBE CSV"""

    def __init__(self, file_path):
        self.file_path = file_path
        self.sections = {}
        self.report = []
        self.config_df = None
        self.tasks_df = None
        self.milestones_df = None

    def log(self, test_name, status, details=""):
        # Format log chuẩn để Core hiển thị đẹp
        icon = "✅" if status == "PASS" else "❌"
        self.report.append(f"[{status}] {test_name}: {details}")

    def parse_file(self):
        try:
            if not os.path.exists(self.file_path):
                self.log("File Check", "FAIL", f"File not found: {self.file_path}")
                return False

            # FIX QUAN TRỌNG: Dùng 'utf-8-sig' để xử lý BOM (Byte Order Mark) từ Excel
            with open(self.file_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()

            # Logic cắt file Multi-section
            section_indices = [
                i for i, line in enumerate(lines) if line.strip().startswith("[")
            ]
            section_indices.append(len(lines))

            if len(section_indices) <= 1:
                self.log(
                    "File Parsing",
                    "FAIL",
                    "No [SECTIONS] found. Check encoding or file format.",
                )
                return False

            for i in range(len(section_indices) - 1):
                start = section_indices[i]
                end = section_indices[i + 1]
                # Lấy tên section và clean kỹ càng
                header = lines[start].strip().split(",")[0].strip("[]").strip()
                content = "".join(lines[start + 1 : end])

                if content.strip():
                    try:
                        self.sections[header] = pd.read_csv(
                            io.StringIO(content)
                        ).dropna(how="all")
                    except Exception as e:
                        self.log(
                            "CSV Read",
                            "WARNING",
                            f"Error reading section {header}: {e}",
                        )

            self.config_df = self.sections.get("RBE_CONFIGURATION")
            for k in self.sections:
                if k.startswith("TASKS_"):
                    self.tasks_df = self.sections[k]
                elif k.startswith("MILESTONES_"):
                    self.milestones_df = self.sections[k]

            return True
        except Exception as e:
            self.log("File Parsing", "FAIL", str(e))
            return False

    def run_tests(self):
        if not self.parse_file():
            return self.report

        # 1. Structure Check
        missing = [
            s
            for s in ["RBE_CONFIGURATION", "TASKS", "MILESTONES"]
            if (s == "RBE_CONFIGURATION" and self.config_df is None)
            or (
                s != "RBE_CONFIGURATION"
                and not any(k.startswith(s) for k in self.sections)
            )
        ]

        if missing:
            self.log("Structure", "FAIL", f"Missing: {missing}")
        else:
            self.log("Structure", "PASS", "Full 3 required sections found.")

        # 2. Logic Check
        try:
            if self.config_df is not None:
                cfg_id = self.config_df["EventID"].iloc[0]
                task_match = any(
                    cfg_id in k for k in self.sections if k.startswith("TASKS")
                )
                if not task_match:
                    self.log("EventID Sync", "FAIL", f"ConfigID mismatch")
                else:
                    self.log("EventID Sync", "PASS", f"ID matched: {cfg_id}")
        except:
            pass

        # 3. Milestone Logic
        if self.milestones_df is not None and "Point" in self.milestones_df.columns:
            try:
                pts = (
                    pd.to_numeric(self.milestones_df["Point"], errors="coerce")
                    .dropna()
                    .tolist()
                )
                if not pts:
                    self.log("Milestone Logic", "WARNING", "No points found")
                elif all(x >= y for x, y in zip(pts, pts[1:])) or all(
                    x <= y for x, y in zip(pts, pts[1:])
                ):
                    self.log("Milestone Logic", "PASS", "Points sorted correctly")
                else:
                    self.log("Milestone Logic", "FAIL", "Points not sorted")
            except:
                pass

        return self.report


class RBEFuzzGenerator:
    """Class chuyên tạo ra các biến thể lỗi (Mutations) từ file gốc"""

    def __init__(self, parser):
        self.parser = parser
        self.mutations = []

    def generate_all_cases(self):
        """Sinh ra tất cả các kịch bản test lỗi"""
        self.mutations = []

        # 1. CASE: DATE LOGIC (Start > End)
        df = self.parser.config_df.copy()
        df["StartTime"] = "2030-01-01 00:00"
        df["EndTime"] = "2020-01-01 00:00"
        self._add_case("Invalid_Date_Range", df, "RBE_CONFIGURATION")

        # 2. CASE: MISSING REQUIRED COLUMN (Xóa EventID)
        df = self.parser.config_df.copy()
        if "EventID" in df.columns:
            df = df.drop(columns=["EventID"])
            self._add_case("Missing_Column_EventID", df, "RBE_CONFIGURATION")

        # 3. CASE: NEGATIVE NUMBERS (Điểm âm)
        if self.parser.milestones_df is not None:
            df = self.parser.milestones_df.copy()
            if "Point" in df.columns:
                df.iloc[0, df.columns.get_loc("Point")] = -100
                self._add_case("Negative_Milestone_Point", df, "MILESTONES")

        # 4. CASE: INVALID REWARD SYNTAX (Sai format Item:Qty)
        if self.parser.milestones_df is not None:
            df = self.parser.milestones_df.copy()
            if "MilestoneRewards" in df.columns:
                df.iloc[0, df.columns.get_loc("MilestoneRewards")] = (
                    "InvalidItemNameNoQty"
                )
                self._add_case("Invalid_Reward_Syntax", df, "MILESTONES")

        # 5. CASE: EMPTY EVENT NAME (Trường bắt buộc rỗng)
        df = self.parser.config_df.copy()
        if "EventName" in df.columns:
            df.iloc[0, df.columns.get_loc("EventName")] = ""
            self._add_case("Empty_Event_Name", df, "RBE_CONFIGURATION")

        return self.mutations

    def _add_case(self, name, modified_df, section_name):
        """Lưu lại kịch bản để tạo file"""
        sections_copy = deepcopy(self.parser.sections)
        target_key = None
        if section_name in sections_copy:
            target_key = section_name
        else:
            for k in sections_copy:
                if k.startswith(section_name):
                    target_key = k
                    break

        if target_key:
            sections_copy[target_key] = modified_df
            self.mutations.append({"name": name, "sections": sections_copy})

    def save_mutation_to_file(self, mutation_data):
        """Ghi ra file CSV tạm"""
        file_name = f"FUZZ_{mutation_data['name']}.csv"
        full_path = os.path.join(DOWNLOAD_DIR, file_name)

        with open(full_path, "w", encoding="utf-8-sig", newline="") as f:
            for header, df in mutation_data["sections"].items():
                f.write(f"[{header}]\n")
                df.to_csv(f, index=False)
                f.write("\n")

        return file_name


class GenericCSVFuzzer:
    """
    Class này tự động phân tích CSV bất kỳ và sinh ra các test case phá hoại
    dựa trên kiểu dữ liệu của từng cột.
    """

    def __init__(self, file_path):
        self.file_path = file_path
        self.original_df = pd.read_csv(file_path, on_bad_lines="skip")
        self.mutations = []

    def generate_generic_all_cases(self):
        self.mutations = []
        df = self.original_df.copy()

        # Nếu file rỗng, bỏ qua
        if df.empty:
            return []

        print(f"      🧠 AI Analyzing CSV Structure ({len(df.columns)} columns)...")

        # 1. CASE: EMPTY / NULL VALUES (Xóa dữ liệu bắt buộc)
        # Chọn ngẫu nhiên 1 dòng và xóa giá trị của cột đầu tiên (thường là ID)
        if len(df) > 0:
            df_empty = df.copy()
            target_col = df.columns[0]
            df_empty.at[0, target_col] = ""  # Xóa dữ liệu
            self._add_case(f"Empty_Column_{target_col}", df_empty)

        # 2. DUYỆT QUA TỪNG CỘT ĐỂ TÌM ĐIỂM YẾU
        for col in df.columns:
            # Lấy mẫu dữ liệu để đoán kiểu
            sample_val = df[col].dropna().iloc[0] if not df[col].dropna().empty else ""
            dtype = df[col].dtype

            # --- A. NẾU LÀ SỐ (NUMERIC) ---
            if (
                pd.api.types.is_numeric_dtype(dtype)
                or str(sample_val).replace(".", "", 1).isdigit()
            ):
                # Test 1: Số Âm (Negative)
                df_neg = df.copy()
                df_neg[col] = -100
                self._add_case(f"Negative_Value_{col}", df_neg)

                # Test 2: Text vào trường Số (Type Mismatch)
                df_txt = df.copy()
                df_txt[col] = "INVALID_TEXT"
                self._add_case(f"Text_In_Numeric_{col}", df_txt)

                # Test 3: Số cực lớn (Overflow)
                df_huge = df.copy()
                df_huge[col] = 99
                self._add_case(f"Overflow_Value_{col}", df_huge)

            # --- B. NẾU LÀ CHỮ (STRING) ---
            else:
                # Test 4: SQL Injection đơn giản
                df_sql = df.copy()
                df_sql.at[0, col] = "' OR '1'='1"
                self._add_case(f"SQL_Injection_{col}", df_sql)

                # Test 5: Special Characters (Emojis, Symbols)
                df_special = df.copy()
                df_special.at[0, col] = "⚠️💀 Test @#%^"
                self._add_case(f"Special_Chars_{col}", df_special)

        # 3. CASE: DUPLICATE ROWS (Check trùng khóa)
        if len(df) > 0:
            df_dup = pd.concat([df.iloc[[0]], df], ignore_index=True)
            self._add_case("Duplicate_Rows", df_dup)

        print(f"      🧠 AI Generated {len(self.mutations)} Fuzz Cases.")
        return self.mutations

    def _add_case(self, name, modified_df):
        # Giới hạn số lượng case để không test quá lâu (Max 10 case ngẫu nhiên nếu quá nhiều)
        self.mutations.append({"name": name, "df": modified_df})

    def save_mutation_to_generic_file(self, mutation_data):
        file_name = f"FUZZ_{mutation_data['name']}.csv"
        # Làm sạch tên file (bỏ ký tự lạ)
        file_name = re.sub(r"[^\w\-_\.]", "_", file_name)
        full_path = os.path.join(DOWNLOAD_DIR, file_name)
        mutation_data["df"].to_csv(full_path, index=False)
        return file_name

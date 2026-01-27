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

                        print("      ⏳ Popup detected, waiting 2s...")
                        time.sleep(2.0)  # Chờ thêm 2s để chắc chắn popup đã ổn định
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

    def smart_test_cycle(self, page, target_csv):
        logs = []
        try:
            # 1. Chuẩn bị file (Lấy file mới nhất trong thư mục Download)
            file_path = os.path.join(DOWNLOAD_DIR, target_csv)
            if not os.path.exists(file_path):
                files = sorted(
                    os.listdir(DOWNLOAD_DIR),
                    key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)),
                )
                if files:
                    target_csv = files[-1]
                    file_path = os.path.join(DOWNLOAD_DIR, files[-1])

            # Đọc file gốc (dữ liệu User)
            original_df = pd.read_csv(
                file_path, dtype=str
            )  # Đọc str để bảo toàn format
            print(f"   📂 Testing with Base File: {target_csv}")

            # 2. Phase 1: Fuzzing (Giữ nguyên logic cũ)
            print("   🧪 PHASE 1: Running Fuzz Tests...")
            fuzzed_df = self._generate_fuzzed_data(original_df)
            fuzz_path = os.path.join(DOWNLOAD_DIR, f"fuzzed_{target_csv}")
            meta_cols = ["TEST_CASE", "EXPECTED_KEYWORD"]
            save_cols = [c for c in fuzzed_df.columns if c not in meta_cols]
            fuzzed_df[save_cols].to_csv(fuzz_path, index=False)

            self._ensure_popup_closed(page)
            # Upload Fuzz File (Expect Fail)
            self._perform_upload_action(page, fuzz_path)
            logs.append(
                {
                    "step": "Fuzzing",
                    "status": "EXECUTED",
                    "details": "Uploaded bad data & handled error popups",
                }
            )

            # Check Error message
            print("      🛡️ Analyzing Error Popup...")
            popup_text = ""
            try:
                any_popup = page.locator(
                    ".swal2-popup, .modal-content, .alert-danger, .toast-error"
                ).first
                if any_popup.is_visible():
                    popup_text = any_popup.inner_text().lower()
                else:
                    popup_text = "no popup"
                self._ensure_popup_closed(page)
            except:
                popup_text = "error reading"

            for idx, row in fuzzed_df.iterrows():
                expected = str(row["EXPECTED_KEYWORD"]).lower()
                if expected in popup_text:
                    res = "PASS"
                    detail = f"Caught: '{expected}'"
                else:
                    res = "FAIL"
                    detail = f"Missed: '{expected}'"
                logs.append(
                    {
                        "step": f"Test Case #{idx+1}",
                        "test_case": row["TEST_CASE"],
                        "status": "EXECUTED",
                        "result": res,
                        "details": detail,
                    }
                )

            # 3. Phase 2: Valid Data (FIX #2 & #3: Valid Import Logic)
            print("   ✨ PHASE 2: Verify Valid Import (User Data Preservation)...")

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
                    else:
                        prefix = "Auto_"

                    # Tạo ID mới: Prefix + Auto + timestamp
                    # VD: Grabbag_Auto_170000123
                    new_id = f"{prefix}Auto_{current_timestamp}"
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

            final_res = "PASS" if is_success else "FAIL"
            final_detail = (
                "Successfully imported valid user data" if is_success else msg
            )

            # Quan trọng: Nếu thành công, lưu lại tên file này vào memory để các bước sau (Edit Row) dùng ID mới này
            if is_success:
                # Lấy ID mới vừa tạo để báo cho AI biết
                # (Logic nâng cao: Lưu vào self.memory nếu cần)
                pass

            self._ensure_popup_closed(page)
            logs.append(
                {
                    "step": "Final Sanity Check",
                    "test_case": "Import Valid User Data",
                    "status": "EXECUTED",
                    "result": final_res,
                    "details": final_detail,
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

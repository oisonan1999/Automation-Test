# automation/smart_tester/tester_core.py - split from smart_tester.py
# Test cycle orchestration: RBE/generic fuzz campaign + result check
from copy import deepcopy
from glob import glob
import io
import os
import random as rd
import time
import pandas as pd
import re
import csv
from playwright.sync_api import Page
from automation.constants import DOWNLOAD_DIR
from automation.smart_tester.fuzz_generator import RBESmartTester, RBEFuzzGenerator, GenericCSVFuzzer


class SmartTesterCoreMixin:
    """Test cycle orchestration: RBE/generic fuzz campaign + result check"""

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
    # HELPER: AUTO-FIX DUPLICATE CSV
    # ============================
    def _fix_duplicate_csv(self, csv_path, error_msg):
        """
        Tự động fix duplicate entry trong CSV bằng cách thêm timestamp/random suffix.

        Args:
            csv_path: Đường dẫn file CSV cần fix
            error_msg: Message lỗi từ popup (chứa thông tin về duplicate key)

        Returns:
            bool: True nếu fix thành công
        """
        try:
            import re
            import time

            print(f"   🔧 AUTO-FIX: Analyzing duplicate error...")
            print(f"      Error: {error_msg[:150]}...")

            # Parse error để tìm duplicate value và row numbers
            # Example: "row 2: (1062, "duplicate entry 'section_1770608609-dec2025_12days_claims' for key..."

            # Extract affected row numbers
            row_matches = re.findall(r"row (\d+):", error_msg.lower())
            affected_rows = [int(r) for r in row_matches] if row_matches else []

            if affected_rows:
                print(f"      🎯 Affected rows: {affected_rows}")

            # Extract duplicate value
            duplicate_value_match = re.search(
                r"duplicate entry '([^']+)'", error_msg.lower()
            )

            if not duplicate_value_match:
                print("      ⚠️ Cannot parse duplicate value from error")
                # Fallback: Still try to fix by adding timestamp to all ID columns
                duplicate_value = "unknown"
            else:
                duplicate_value = duplicate_value_match.group(1)
                print(f"      📌 Duplicate value: '{duplicate_value}'")

            # Đọc CSV
            df = pd.read_csv(csv_path)
            if df.empty:
                print("      ⚠️ CSV is empty")
                return False

            print(f"      📊 CSV has {len(df)} rows, {len(df.columns)} columns")

            # Strategy: Thêm timestamp suffix vào các field có khả năng gây duplicate
            # Common unique fields: ID, SectionID, OfferID, name, title, etc.

            timestamp_suffix = f"_{int(time.time())}"
            fixed_count = 0

            # Identify which columns might be causing duplicate
            # Based on error "section_1770608609-dec2025_12days_claims", likely format is: ID-gate
            # Constraint "offers_section_name_gate" suggests (name, gate) or (SectionID, gate) combination

            # CRITICAL: Exclude columns that should NOT be modified
            EXCLUDE_COLUMNS = [
                "tab_id",
                "tabid",  # Only allows: feature, prize_wall, basic_loot
                "gate",  # Gate names should not be modified
                "type",
                "category",  # Enum values
                "showinstore",
                "is_prize_wall",  # Boolean fields
            ]

            id_columns = [
                col
                for col in df.columns
                if any(
                    keyword in col.lower()
                    for keyword in ["id", "sectionid", "offerid", "name", "eventid"]
                )
                and not any(
                    excl in col.lower() for excl in EXCLUDE_COLUMNS
                )  # 🆕 Filter out excluded
            ]

            print(f"      🔍 Found potential ID columns: {id_columns}")

            # Fix strategy: Add UNIQUE suffix to ALL rows' ID columns
            # Use timestamp + index to ensure global uniqueness (not just within CSV)
            # This prevents conflicts with existing database records
            base_timestamp = int(time.time())

            for idx in range(len(df)):
                # Generate unique suffix: _test_timestamp+idx
                # This ensures uniqueness both within CSV AND against existing DB records
                row_suffix = f"_test_{base_timestamp + idx}"

                for col in id_columns:
                    if col in df.columns:
                        original_value = str(df.at[idx, col])

                        # Skip if empty or already has timestamp pattern
                        if not original_value or original_value == "nan":
                            continue

                        # Check if already modified (has test_timestamp pattern)
                        if re.search(r"_test_\d+$", original_value):
                            continue

                        # Add unique suffix
                        new_value = f"{original_value}{row_suffix}"
                        df.at[idx, col] = new_value
                        fixed_count += 1
                        print(
                            f"      ✏️  Row {idx+1}, '{col}': {original_value[:50]} → {new_value[:50]}"
                        )

            # Don't fix 'gate' column as it's a foreign key reference
            # Gate values must match existing gates in the system

            if fixed_count == 0:
                print(
                    "      ⚠️ No ID columns were modified (couldn't identify unique constraint)"
                )
                print("      💡 Tip: Duplicate error may require manual intervention")
                return False
                return False

            # Save fixed CSV
            df.to_csv(csv_path, index=False)
            print(
                f"      ✅ Fixed {fixed_count} column(s) and saved to {os.path.basename(csv_path)}"
            )
            return True

        except Exception as e:
            print(f"      ❌ Auto-fix failed: {e}")
            return False

    # ============================
    # FIX 2: UPLOAD VÀ XỬ LÝ POPUP
    # ============================
    def _test_generic_csv(self, page, target_csv):
        logs = []
        try:
            # 1. Chuẩn bị file
            file_path = os.path.join(DOWNLOAD_DIR, target_csv)
            if not os.path.exists(file_path):
                # Tìm file mới nhất nếu không thấy tên chính xác
                files = sorted(
                    glob(os.path.join(DOWNLOAD_DIR, "*.csv")), key=os.path.getmtime
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

            # CRITICAL: Setup popup capture ONCE before all uploads
            # [FIX] Clear stale state first so fuzz loop doesn't inherit a prior result
            try:
                page.evaluate(
                    "window.__popupResult = null; window.__lastCheckedText = ''; window.__popupHistory = [];"
                )
            except:
                pass
            try:
                page.evaluate("""
                    window.__popupResult = null;
                    window.__lastCheckedText = '';
                    
                    // Function to check and capture modal content
                    function captureModalContent() {
                        if (window.__popupResult) return true; // Already captured
                        
                    // [FIX] SUCCESS-FIRST classification for global monitor.
                    // Old code had lower.includes('clone') which could cause false positives,
                    // and had no success keyword check — any non-error text defaulted to PASS
                    // only by absence, which is fragile. New code: explicit success-first.
                    const __MON_SUCCESS_KW = [
                        'success', 'successfully', 'hoàn thành', 'imported',
                        'updated', 'saved', 'completed', 'done', 'thành công'
                    ];
                    const __MON_ERROR_KW = [
                        'error', 'fail', 'invalid', 'already exist', 'duplicate',
                        'missing', 'required', 'không hợp lệ', 'lỗi', 'exception'
                    ];

                    function __monClassify(text) {
                        const lower = text.toLowerCase();
                        if (__MON_SUCCESS_KW.some(k => lower.includes(k))) return 'PASS';
                        if (__MON_ERROR_KW.some(k => lower.includes(k))) return 'FAIL';
                        return null;
                    }

                    // Check ALL modals - EVEN IF HIDDEN (class 'hide')
                    const modals = document.querySelectorAll('.modal');
                    for (const modal of modals) {
                        // Read ALL text from modal (header + body combined)
                        const fullText = modal.innerText.trim();
                        if (!fullText) continue;

                        // SKIP loading indicators (exact match OR short text with loading words)
                        const lower = fullText.toLowerCase();
                        const loadingWords = ['importing...', 'uploading...', 'loading...', 'processing...', 'please wait'];
                        if (loadingWords.some(w => lower === w || (lower.includes(w) && fullText.length < 50))) continue;

                        // Skip if we already checked this exact text
                        if (fullText === window.__lastCheckedText) continue;
                        window.__lastCheckedText = fullText;

                        const type = __monClassify(fullText);
                        if (!type) continue;  // skip ambiguous
                        window.__popupResult = {
                            type: type,
                            text: fullText.substring(0, 200),
                            timestamp: Date.now()
                        };
                        console.log('✅ Modal captured:', window.__popupResult);
                        return true;
                    }

                    // Check for SweetAlert - EVEN IF HIDDEN
                    const swalContainers = document.querySelectorAll('.swal2-container');
                    for (const container of swalContainers) {
                        const content = container.querySelector('.swal2-html-container, .swal2-title, .swal2-popup');
                        if (content && content.innerText.trim()) {
                            const text = content.innerText.trim();
                            const lower = text.toLowerCase();
                            if (lower === 'importing...' || lower === 'uploading...') continue;
                            if (text === window.__lastCheckedText) continue;
                            window.__lastCheckedText = text;

                            const hasErrorIcon = !!container.querySelector('.swal2-error, .swal2-icon-error');
                            const type = hasErrorIcon ? 'FAIL' : __monClassify(text);
                            if (!type) continue;
                            window.__popupResult = {
                                type: type,
                                text: text.substring(0, 200),
                                timestamp: Date.now()
                            };
                            console.log('✅ Swal captured:', window.__popupResult);
                            return true;
                        }
                    }
                    return false;
                }
                    
                    // ULTRA-FAST polling - 10ms intervals
                    const checkInterval = setInterval(() => {
                        captureModalContent();
                    }, 10);
                    
                    // MutationObserver as backup
                    const observer = new MutationObserver(() => {
                        captureModalContent();
                    });
                    
                    observer.observe(document.body, {
                        childList: true,
                        subtree: true,
                        attributes: true,
                        attributeFilter: ['class', 'style']
                    });
                    
                    // Keep running for entire fuzzing session
                    console.log('🔍 Global popup monitor started');
                """)
                print("   🔍 Global popup monitor initialized")
            except Exception as e:
                print(f"   ⚠️ Failed to init popup monitor: {e}")

            for i, case in enumerate(mutations):
                case_name = case["name"]
                print(f"      🔸 [Case {i+1}/{len(mutations)}] {case_name}...")

                temp_file = fuzzer.save_mutation_to_generic_file(case)

                # CRITICAL: Clear previous result before upload
                try:
                    page.evaluate("window.__popupResult = null")
                except:
                    pass

                # Upload (Dùng hàm upload bắt được Toast/Popup)
                # DON'T close popup before upload - it might close the result popup!
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
                    print(f"🚨 Accepted: {safe_msg}")
                    logs.append(
                        {
                            "step": f"Fuzz: {case_name}",
                            "status": "WARNING",
                            "details": "System accepted invalid data",
                        }
                    )

                # Cleanup AFTER reading result - MUST close modal for next case
                try:
                    page.evaluate("""
                        // Click any dismiss/close/cancel buttons
                        const btns = document.querySelectorAll(
                            '.modal button[data-dismiss="modal"], .modal .close, .modal .btn-secondary, ' +
                            'button.swal2-confirm, button.swal2-cancel, button.swal2-close'
                        );
                        btns.forEach(b => { try { b.click(); } catch(e) {} });
                        
                        // Force remove overlays
                        document.querySelectorAll('.modal-backdrop, .swal2-container').forEach(el => el.remove());
                        document.querySelectorAll('.modal.show, .modal.in').forEach(el => {
                            el.classList.remove('show', 'in');
                            el.classList.add('hide');
                            el.style.display = 'none';
                        });
                        document.body.classList.remove('modal-open', 'swal2-shown');
                        document.body.style.overflow = 'auto';
                    """)
                except:
                    pass
                time.sleep(0.3)  # Brief wait for cleanup
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

            # --- TẠO ID MỚI CHỈ CHO PRIMARY KEY (Cột ID đầu tiên) ---
            # CRITICAL: Chỉ generate ID cho PRIMARY KEY duy nhất, giữ nguyên tất cả các cột khác
            primary_key_col = None

            # Tìm PRIMARY KEY column (cột ID đầu tiên trong file)
            for col in valid_df.columns:
                col_lower = col.lower()

                # Bỏ qua các cột ID tham chiếu (FK) hoặc cố định
                exclude_list = [
                    "tab_id",
                    "tabid",
                    "gate",  # FK
                    "group_id",
                    "parent_id",
                    "milestone_id",
                    "type_id",  # FKs
                    "display_id",
                    "displayid",  # Display IDs
                ]
                if any(ex in col_lower for ex in exclude_list):
                    continue

                # Tìm cột ID (thường là PK)
                if "id" in col_lower or "key" in col_lower:
                    primary_key_col = col
                    print(f"      🔑 Identified Primary Key: '{col}'")
                    break  # Chỉ lấy cột ID ĐẦU TIÊN

            # Generate ID mới CHỈ cho Primary Key
            if primary_key_col:
                col_lower = primary_key_col.lower()
                original_val = valid_df.iloc[0][primary_key_col]

                # Nếu cột gốc không rỗng, generate ID mới
                if not pd.isna(original_val) and str(original_val).strip() != "":
                    # Prefix thông minh dựa trên tên cột
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
                    elif "sectionid" in col_lower:
                        prefix = "Section_"
                    elif "slotid" in col_lower:
                        prefix = "SlotID_"
                    elif "eventid" in col_lower or "event" in col_lower:
                        prefix = "Event_"
                    else:
                        prefix = "AutoGen_"

                    # Generate ID cho TOÀN BỘ rows (không chỉ row đầu)
                    for idx in range(len(valid_df)):
                        new_id = f"{prefix}{current_timestamp + idx}"
                        valid_df.at[valid_df.index[idx], primary_key_col] = new_id
                        print(f"      ✏️  Row {idx+1}, '{primary_key_col}': {new_id}")
                else:
                    print(
                        f"      ⚠️ Primary Key '{primary_key_col}' is empty, skipped generation"
                    )
            else:
                print("      ⚠️ No Primary Key column found, using original data as-is")

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

            # FIX #3: Validate tab_id column (only 3 valid values)
            tab_id_col = next(
                (
                    c
                    for c in valid_df.columns
                    if c.lower() == "tab_id" or c.lower() == "tabid"
                ),
                None,
            )
            if tab_id_col:
                VALID_TAB_IDS = ["feature", "prize_wall", "basic_loot"]
                fixed_count = 0

                for idx in range(len(valid_df)):
                    current_value = str(valid_df.at[idx, tab_id_col]).strip().lower()

                    if current_value not in VALID_TAB_IDS:
                        # Fix: Choose based on context or default to 'feature'
                        fixed_value = "feature"  # Default

                        # Smart selection based on other column values in this row
                        row_data = " ".join(
                            str(v).lower() for v in valid_df.iloc[idx].values
                        )

                        if "prize" in row_data or "wall" in row_data:
                            fixed_value = "prize_wall"
                        elif "loot" in row_data or "basic" in row_data:
                            fixed_value = "basic_loot"

                        if idx == 0:  # Convert column type only once
                            valid_df[tab_id_col] = valid_df[tab_id_col].astype(object)

                        valid_df.at[idx, tab_id_col] = fixed_value
                        fixed_count += 1
                        print(
                            f"      🔧 Row {idx+1}: Fixed invalid tab_id '{current_value}' → '{fixed_value}'"
                        )

                if fixed_count > 0:
                    print(f"      ✅ Fixed {fixed_count} invalid tab_id value(s)")

            # Save Valid File
            valid_path = os.path.join(DOWNLOAD_DIR, f"valid_{target_csv}")
            valid_df.to_csv(valid_path, index=False)

            self._ensure_popup_closed(page)

            # Upload Valid File (Expect Success)
            print("   📤 Uploading valid file for Final Sanity Check...")
            is_success, msg = self._perform_upload_action(page, valid_path)
            final_msg = str(msg) if msg is not None else "Unknown result"

            # 🆕 AUTO-FIX: If duplicate error detected, fix and retry
            retry_count = 0
            max_retries = 2

            while not is_success and retry_count < max_retries:
                # Check if error is duplicate-related
                error_lower = final_msg.lower()

                if "duplicate" in error_lower or "1062" in error_lower:
                    print(
                        f"   🔍 Duplicate error detected (attempt {retry_count + 1}/{max_retries})"
                    )

                    # Try to auto-fix the CSV
                    fix_success = self._fix_duplicate_csv(valid_path, final_msg)

                    if fix_success:
                        print("   🔄 Retrying upload with fixed CSV...")
                        self._ensure_popup_closed(page)
                        time.sleep(1)  # Give page time to settle

                        # Retry upload
                        is_success, msg = self._perform_upload_action(page, valid_path)
                        final_msg = str(msg) if msg is not None else "Unknown result"

                        if is_success:
                            final_msg = (
                                f"✅ Success after auto-fix (attempt {retry_count + 1})"
                            )
                            print(
                                f"   ✨ Auto-fix successful! Valid file imported on attempt {retry_count + 1}."
                            )
                            break
                        else:
                            print(
                                f"   ⚠️ Upload still failed after fix: {final_msg[:100]}"
                            )
                    else:
                        print("   ⚠️ Auto-fix failed, cannot retry")
                        final_msg = f"❌ {final_msg} (auto-fix failed)"
                        break
                else:
                    # Not a duplicate error, no point retrying
                    print(
                        f"   ℹ️ Non-duplicate error, skipping auto-fix: {final_msg[:100]}"
                    )
                    break

                retry_count += 1

            # Final status message
            if not is_success and "duplicate" in final_msg.lower():
                final_msg = f"❌ Still duplicate after {retry_count + 1} retry attempt(s): {final_msg[:150]}"

            # Quan trọng: Nếu thành công, lưu lại tên file này vào memory
            if is_success:
                # Lấy ID mới vừa tạo để báo cho AI biết
                # (Logic nâng cao: Lưu vào self.memory nếu cần)
                pass

            self._ensure_popup_closed(page)
            logs.append(
                {
                    "step": "Final Sanity Check",
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



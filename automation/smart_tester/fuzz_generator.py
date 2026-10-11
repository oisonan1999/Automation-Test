# automation/smart_tester/fuzz_generator.py - split from smart_tester.py
# Standalone fuzz/parser classes (not mixins)
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

# automation_modules/data_handler.py
import os
import csv
import re
from .constants import DOWNLOAD_DIR

class DataHandlerMixin:
    """Chứa logic xử lý file CSV, Download"""
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



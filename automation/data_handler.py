# automation/data_handler.py
import os
import csv
import re
from automation.constants import DOWNLOAD_DIR


class DataHandlerMixin:
    """Chứa logic xử lý file CSV, Download"""

    def _process_csv_manipulation(self, filename, operation, data_instruction):
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if not os.path.exists(filepath):
            return f"Error: File {filename} not found."

        print(f"   🔧 CSV: {operation} -> {data_instruction}")

        # apply_rename_map works on the raw file TEXT, not parsed rows/columns.
        # Needed for exports like Gacha Weight's, which stack several distinct
        # mini-tables (each with its own header row) in one CSV — the
        # single-header-row/DictReader model below can't address a column that
        # isn't on line 1. Handled here, before any row parsing, and returns
        # early so the generic DictWriter write-back further down (which
        # assumes a single fixed header) never runs on this file.
        if operation == "apply_rename_map":
            rename_map = getattr(self, "_last_csv_rename_map", None)
            if not rename_map:
                return (
                    "Error: no rename map available — run a 'uniquify' "
                    "manipulate_csv step on another file earlier in this plan first"
                )
            try:
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    content = f.read()
                cnt = 0
                for old_v, new_v in rename_map.items():
                    n = content.count(old_v)
                    if n:
                        content = content.replace(old_v, new_v)
                        cnt += n
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                return (
                    f"Success: Replaced {cnt} occurrence(s) across "
                    f"{len(rename_map)} renamed value(s)"
                )
            except Exception as e:
                return f"Logic Error: {e}"

        rows = []
        headers = []
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                r_headers = next(csv.reader(f))
                headers = [h.strip() for h in r_headers]
                f.seek(0)
                reader = csv.DictReader(f, fieldnames=headers)
                next(reader)
                rows = list(reader)
        except Exception as e:
            return f"Read Error: {e}"

        def find_col(n):
            for h in headers:
                if h.lower() == n.lower().strip():
                    return h
            return None

        def safe_split(text):
            if "=" in text:
                return text.split("=", 1)
            if ":" in text:
                return text.split(":", 1)
            return None, None

        # --- HÀM MỚI: DỌN DẸP GIÁ TRỊ RÁC ---
        def clean_val(v):
            if not v:
                return ""
            # Xóa khoảng trắng và dấu phẩy thừa ở 2 đầu
            # Ví dụ: " delete, " -> "delete"
            return v.strip().strip(",").strip()

        try:
            # --- ADD LOGIC ---
            if operation == "add":
                col, vals_str = safe_split(data_instruction)
                if not col:
                    return "Invalid ADD format"
                t_col = find_col(col)
                if not t_col:
                    return f"Column '{col}' not found"

                # Tách values bằng dấu phẩy
                vals = [x.strip() for x in vals_str.split(",")]
                tmpl = rows[0].copy() if rows else {h: "" for h in headers}

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
                    print(
                        "      ⚠️ Phát hiện cú pháp gộp, tự động cắt lấy lệnh đầu tiên..."
                    )
                    clean_instr = data_instruction.split(",")[0]

                if "|" not in clean_instr:
                    return "Invalid EDIT format"

                f_part, s_part = clean_instr.split("|", 1)
                fc, fv = safe_split(f_part)
                sc, sv = safe_split(s_part)

                ftc = find_col(fc)
                stc = find_col(sc)
                if not ftc or not stc:
                    return f"Column not found: {fc} or {sc}"

                # Dọn dẹp dữ liệu tìm kiếm và dữ liệu thay thế (Chốt chặn 2)
                fv = clean_val(fv)
                sv = clean_val(sv)  # <--- ĐÂY LÀ CHỖ SỬA LỖI QUAN TRỌNG NHẤT

                cnt = 0
                for r in rows:
                    if r[ftc].strip() == fv:
                        r[stc] = sv
                        cnt += 1
                msg = f"Edited {cnt} rows ({sc}={sv})"

            # --- SET LOGIC (ghi đè TẤT CẢ dòng) ---
            # Format: "ColumnName=NewValue"  (không cần filter)
            elif operation == "set":
                col, sv = safe_split(data_instruction)
                if not col:
                    return "Invalid SET format"
                t_col = find_col(col)
                if not t_col:
                    return f"Column '{col}' not found"
                sv = clean_val(sv)
                for r in rows:
                    r[t_col] = sv
                msg = f"Set {len(rows)} rows ({col}={sv})"

            # --- UNIQUIFY LOGIC ---
            # Format: "ColumnName=SUFFIX". Auto-discovers every distinct value
            # already present in the column and appends the SAME suffix to
            # each — rows sharing an original value stay mapped to the exact
            # same new value (group-preserving), unlike "set" which overwrites
            # every row to one fixed value. Stores the old->new mapping on
            # `self` so a later `apply_rename_map` step (typically on a
            # companion file that references these same names, e.g. Gacha
            # Weight referencing Gacha Pool's names) can re-apply it.
            elif operation == "uniquify":
                col, suffix = safe_split(data_instruction)
                if not col:
                    return "Invalid UNIQUIFY format"
                t_col = find_col(col)
                if not t_col:
                    return f"Column '{col}' not found"
                suffix = clean_val(suffix)
                if not suffix:
                    return "Invalid UNIQUIFY format: empty suffix"
                rename_map = {}
                for r in rows:
                    old_v = r[t_col]
                    if old_v not in rename_map:
                        rename_map[old_v] = f"{old_v}{suffix}"
                    r[t_col] = rename_map[old_v]
                self._last_csv_rename_map = rename_map
                msg = (
                    f"Uniquified {len(rename_map)} distinct value(s) in "
                    f"column '{col}' (+{suffix})"
                )

            # --- DELETE LOGIC ---
            elif operation == "delete":
                col, val = safe_split(data_instruction)
                t_col = find_col(col)
                val = clean_val(val)  # Clean giá trị cần xóa

                if t_col:
                    initial = len(rows)
                    rows = [r for r in rows if r[t_col].strip() != val]
                    msg = f"Deleted {initial - len(rows)} rows"
                else:
                    msg = "Col not found"

            with open(filepath, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=headers)
                w.writeheader()
                w.writerows(rows)
            return f"Success: {msg}"
        except Exception as e:
            return f"Logic Error: {e}"

    def _modify_csv(self, fp, col, val):
        # Helper function cho Smart Test
        try:
            rows = []
            with open(fp, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                for row in reader:
                    if col in row:
                        row[col] = val
                    rows.append(row)
            with open(fp, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
        except:
            pass

    def _find_download_trigger(self, page, specific_name):
        c = []
        try:
            c.extend(
                page.get_by_role("button", name=self._safe_compile(specific_name)).all()
            )
        except:
            pass
        if not c:
            for k in ["Export", "Download"]:
                try:
                    c.extend(
                        page.get_by_role(
                            "button", name=re.compile(k, re.IGNORECASE)
                        ).all()
                    )
                except:
                    pass
        v = [
            b
            for b in c
            if b.is_visible()
            and not any(x in b.inner_text().lower() for x in ["import", "upload"])
        ]

        # Disambiguate look-alike buttons (e.g. "Export LOC" vs "Export To CSV")
        # that both match the generic "Export"/"Download" fallback keyword above.
        # Prefer buttons whose text also contains the significant (non-generic)
        # words of specific_name, e.g. "csv" in target "Export CSV".
        if specific_name and v:
            generic_words = {"export", "download", "the", "to", "a", "an", "file"}
            sig_words = [
                w
                for w in re.findall(r"\w+", specific_name.lower())
                if w not in generic_words
            ]
            if sig_words:
                exact = [
                    b
                    for b in v
                    if all(w in b.inner_text().lower() for w in sig_words)
                ]
                if exact:
                    v = exact

        if v:
            for b in v:
                if b.is_enabled():
                    return b
            return v[0]
        return None

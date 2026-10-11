# automation/data_handler.py
import os
import csv
import re
from automation.constants import DOWNLOAD_DIR


# ---------------------------------------------------------------------------
# Per-run suffix chain handling (uniquify / apply_rename_map)
# ---------------------------------------------------------------------------
# The gacha pool/weight fixtures in downloads/ are rewritten IN PLACE every run
# (there is no fresh export step for them), so `uniquify` used to append its
# per-run suffix on top of the previous run's suffix, forever:
#   GachaPool_Aug2026_wk3_FEATURED
#     _hieunm_test_08191045_4176_0819105028_hieunm_test_08191056_c737_hieunm_test_08191121_0392
# (118 chars after 3 runs — heading for the DB column limit, and unreadable in
# the UI). Strip any previously-appended chain first, then append exactly one.
#
# The two chunk shapes are the two suffix generators in
# action_fixer/deployment_fixers.py `_inject_gacha_pool_weight_uniquify`:
# the run's unique_id (`_hieunm_test_<MMDDHHMM>_<4 hex>`) and its no-unique_id
# fallback (a bare `_<MMDDHHMMSS>` timestamp).
_BARE_TS_CHUNK = r"_\d{8,14}"


def _suffix_chunk_regex(suffix):
    """Regex source matching ONE appended suffix chunk, derived STRUCTURALLY from
    `suffix` itself: literal words stay literal, digit/hex runs are generalized
    so a chunk from an earlier run (different timestamp) still matches. Keeping
    the literal words ("hieunm_test") is what makes stripping safe — it can't
    chew into a real pool name."""
    tokens = [t for t in re.split(r"[_\s]+", str(suffix or "")) if t]
    if not tokens:
        return None
    # No literal word to anchor on (e.g. the bare `_MMDDHHMMSS` fallback suffix
    # from action_fixer) → every token would be a generalized digit/hex class,
    # which is indistinguishable from a real trailing name segment like
    # "GachaPool_20260819". Refuse to strip rather than corrupt the name; that
    # path just keeps the old append-only behaviour.
    if all(re.fullmatch(r"[0-9a-fA-F]+", t) for t in tokens):
        return None
    parts = []
    for t in tokens:
        if re.fullmatch(r"[0-9a-fA-F]+", t):
            # Hex-permissive even for all-digit tokens: the unique_id's 4-char
            # random tail is hex, so THIS run's copy can be "0392" while an
            # earlier run's was "c737". A digits-only class here would fail to
            # match that earlier chunk and abort the strip loop mid-chain.
            parts.append(r"[0-9a-fA-F]{%d,%d}" % (max(1, len(t) - 4), len(t) + 6))
        else:
            parts.append(re.escape(t))
    return r"_" + r"_".join(parts)


def _chain_regex(chunk_regex):
    """One or more consecutive appended chunks (structural or bare timestamp)."""
    return r"(?:(?:" + chunk_regex + r")|(?:" + _BARE_TS_CHUNK + r"))+"


def _drifted_name_regex(base, chunk_regex):
    """Regex matching `base` even when a run-suffix chain has been spliced in at
    ANY `_` boundary, not just appended at the end.

    Needed because an older (pre-longest-first) apply_rename_map replaced the
    shorter name inside the longer one, leaving the companion file with e.g.
    `GachaPool_..._FEATURED_hieunm_test_08191045_4176_SHARDS_EXTRA` — the chain
    sits in the MIDDLE. Every base token stays literal, so this can only match a
    real occurrence of the base with chain noise around its joints.
    """
    if not base or not chunk_regex:
        return None
    tokens = [t for t in str(base).split("_") if t]
    if not tokens:
        return None
    chain = _chain_regex(chunk_regex)
    parts = [re.escape(tokens[0])]
    for t in tokens[1:]:
        parts.append(r"(?:" + chain + r")?_" + re.escape(t))
    # Trailing chain optional; the lookahead stops a shorter name from matching
    # inside a longer sibling (…_FEATURED must not match …_FEATURED_SHARDS_EXTRA).
    return "".join(parts) + r"(?:" + chain + r")?(?![A-Za-z0-9_])"


def _strip_run_suffixes(value, chunk_regex, max_chunks=12):
    """Remove a trailing chain of previously-appended run suffixes from `value`.

    A bare-timestamp chunk is only stripped when a structural chunk sits
    immediately before it — that is how the observed garbage chains are built,
    and it means a pristine name that merely ends in digits (e.g.
    "GachaPool_20260819") is never touched.
    """
    out = str(value or "")
    if not chunk_regex:
        return out
    tail_re = re.compile(chunk_regex + r"$")
    bare_re = re.compile(_BARE_TS_CHUNK + r"$")
    for _ in range(max_chunks):
        m = tail_re.search(out)
        if m and m.start() > 0:
            out = out[: m.start()]
            continue
        mb = bare_re.search(out)
        if mb and mb.start() > 0:
            candidate = out[: mb.start()]
            if tail_re.search(candidate):  # part of a suffix chain, not the name
                out = candidate
                continue
        break
    # Also drop chains spliced INTO the middle of the name (see
    # _drifted_name_regex) — the structural chunk only, never a bare timestamp,
    # since a mid-name numeric run is plausibly part of the real name.
    out = re.sub(chunk_regex + r"(?=_)", "", out)
    return out


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
            bases = getattr(self, "_last_csv_rename_bases", None) or {}
            chunk_re = getattr(self, "_last_csv_suffix_chunk_re", None)
            try:
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    content = f.read()
                cnt = 0
                fuzzy = 0
                # Longest first: a shorter name can be a prefix of a longer one
                # (…_FEATURED vs …_FEATURED_SHARDS_EXTRA) and must not shadow it.
                for old_v in sorted(rename_map, key=len, reverse=True):
                    new_v = rename_map[old_v]
                    n = content.count(old_v)
                    if n:
                        content = content.replace(old_v, new_v)
                        cnt += n
                        continue
                    # Exact old value absent → this file's copy of the name
                    # carries a different suffix chain than the pool file did
                    # (files drift when one is uniquified more often than the
                    # other). Re-anchor on the base name + any suffix chain.
                    base = bases.get(old_v)
                    pattern = _drifted_name_regex(base, chunk_re)
                    if not pattern:
                        continue
                    # lambda replacement: `new_v` is data, never a regex template
                    content, k = re.subn(pattern, lambda _m, _n=new_v: _n, content)
                    if k:
                        cnt += k
                        fuzzy += 1
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                return (
                    f"Success: Replaced {cnt} occurrence(s) across "
                    f"{len(rename_map)} renamed value(s)"
                    + (f" ({fuzzy} matched by base name after suffix drift)" if fuzzy else "")
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
                # Strip the previous run's suffix chain before appending this
                # run's — these fixtures are rewritten in place every run, so
                # plain appending stacks suffixes forever (see module header).
                chunk_re = _suffix_chunk_regex(suffix)
                rename_map = {}
                bases = {}
                restacked = 0
                for r in rows:
                    old_v = r[t_col]
                    if old_v not in rename_map:
                        base = _strip_run_suffixes(old_v, chunk_re)
                        if base != old_v:
                            restacked += 1
                        bases[old_v] = base
                        rename_map[old_v] = f"{base}{suffix}"
                    r[t_col] = rename_map[old_v]
                self._last_csv_rename_map = rename_map
                # Bases are kept so apply_rename_map can still match a companion
                # file whose copy of these names carries a DIFFERENT (older or
                # shorter) suffix chain — that desync is exactly what made the
                # gacha weight import fail with "Gacha Pool ... does not exist".
                self._last_csv_rename_bases = bases
                self._last_csv_suffix_chunk_re = chunk_re
                msg = (
                    f"Uniquified {len(rename_map)} distinct value(s) in "
                    f"column '{col}' (+{suffix})"
                    + (
                        f", stripped a stale suffix chain from {restacked}"
                        if restacked
                        else ""
                    )
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

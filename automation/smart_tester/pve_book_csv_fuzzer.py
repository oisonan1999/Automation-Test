# automation/smart_tester/pve_book_csv_fuzzer.py
"""Deterministic (non-LLM) fuzz-test tool for PVE Book CSV import.

Same philosophy as the existing RBE fuzz campaign (fuzz_generator.py /
tester_core.py): mutations are generated in plain Python/pandas, not by the AI —
only the upload + popup classification touch the browser.

Built to reproduce two real production bugs:
- "Import CSV Error" popups whose per-line message is a stringified JS object
  ("Line 36: [object Object]") instead of a readable message.
- Re-importing a Book CSV that omits already-existing Chapter IDs is hard-blocked
  ("Chapter ID(s) X exist in this book but are missing from the CSV..."), even
  though incremental/partial chapter updates should be supported.
"""
import datetime
import json
import os
import re
import time
import uuid

import pandas as pd

from automation.constants import DOWNLOAD_DIR

_PROJECT_ROOT = os.path.dirname(DOWNLOAD_DIR)
PVE_BOOK_FUZZ_STATE_FILE = os.path.join(_PROJECT_ROOT, "config", "pve_book_fuzz_state.json")

ALL_CATEGORIES = ("structural", "hierarchy", "focus_column", "business_replay")

_MALFORMED_TEXTS = ("[object object]", "[object error]", "[object array]", "undefined", "nan")

_MISSING_CHAPTER_RE = re.compile(
    r"chapter\s+id\(s\)\s*(.+?)\s*exist\s+in\s+this\s+book\s+but\s+are\s+missing\s+from\s+the\s+csv",
    re.IGNORECASE | re.DOTALL,
)

_CONFIRM_ROUND_RE = re.compile(r"^(continue|proceed|yes)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Small state file — kept separate from config/smoke_last_ids.json on purpose,
# so this tool's test-Book memory never cross-contaminates the smoke runner's.
# ---------------------------------------------------------------------------
def _load_pve_book_fuzz_state():
    try:
        if os.path.exists(PVE_BOOK_FUZZ_STATE_FILE):
            with open(PVE_BOOK_FUZZ_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_pve_book_fuzz_state(state):
    try:
        os.makedirs(os.path.dirname(PVE_BOOK_FUZZ_STATE_FILE), exist_ok=True)
        with open(PVE_BOOK_FUZZ_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"   ⚠️ Could not save PVE Book fuzz state: {e}")


# ---------------------------------------------------------------------------
# Hierarchy inference — Chapter Number / Map Type / Node relationship
# ---------------------------------------------------------------------------
def infer_map_type_node_counts(df):
    """map_type -> max Node number observed for that map type across the file.

    e.g. for the sample Book CSV this yields
    {"ZMap_Daily_3_A_Base": 3, "ZMap_FC_1": 1}.
    """
    counts = {}
    if "Map Type" not in df.columns or "Node" not in df.columns:
        return counts
    node_numeric = pd.to_numeric(df["Node"], errors="coerce")
    for map_type, idx in df.groupby("Map Type").groups.items():
        vals = node_numeric.loc[idx].dropna()
        if not vals.empty:
            counts[str(map_type)] = int(vals.max())
    return counts


# ---------------------------------------------------------------------------
# Popup parsing helpers (module-level — no browser state, just text in/out)
# ---------------------------------------------------------------------------
def is_malformed_error_text(text):
    """True for stringified-JS-object artifacts ('[object Object]', 'undefined',
    ...) — signals a FRONTEND bug in the error message itself, independent of
    whether blocking the import was the correct call."""
    if not text:
        return False
    t = str(text).strip().lower()
    return t in _MALFORMED_TEXTS or t.startswith("[object ")


def parse_import_csv_error_popup(text):
    """Best-effort parse of the 'Import CSV Error' Line/Error table into
    [{"line": 36, "error": "[object Object]"}, ...]. The exact DOM shape hasn't
    been verified live yet — this works off the popup's flattened innerText,
    pairing a bare line-number line with the line right after it. Refine this
    against the real markup once verified via CDP."""
    if not text or "import csv error" not in text.lower():
        return None
    lines = [l.strip(" \t•-") for l in text.splitlines() if l.strip()]
    rows = []
    i = 0
    while i < len(lines) - 1:
        if lines[i].isdigit() and lines[i].lower() not in ("line",):
            rows.append({"line": int(lines[i]), "error": lines[i + 1]})
            i += 2
        else:
            i += 1
    return rows or None


def parse_missing_chapter_popup(text):
    """Extracts Chapter IDs out of 'Chapter ID(s) X, Y exist in this book but are
    missing from the CSV...'. Returns the list of IDs, or None if the popup text
    doesn't match this shape."""
    if not text:
        return None
    m = _MISSING_CHAPTER_RE.search(text)
    if not m:
        return None
    ids = [x.strip() for x in re.split(r"[,\n]", m.group(1)) if x.strip()]
    return ids or None


def _read_full_visible_dialog_text(page):
    """Full (untrimmed) innerText of whatever result dialog is currently visible.
    Uses getBoundingClientRect()/computed style rather than offsetParent — swal2
    and bootstrap-modal roots are `position:fixed`, for which offsetParent is
    always null in Chrome (documented gotcha elsewhere in this codebase)."""
    try:
        return page.evaluate("""
            () => {
                const nodes = document.querySelectorAll(
                    '.modal .modal-body, .modal .modal-content, .swal2-popup, [role="dialog"]'
                );
                for (const el of nodes) {
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const visible = r.width > 0 && r.height > 0
                        && style.visibility !== 'hidden' && style.display !== 'none';
                    if (visible && el.innerText && el.innerText.trim()) {
                        return el.innerText.trim();
                    }
                }
                return '';
            }
        """) or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Case generator
# ---------------------------------------------------------------------------
class PVEBookCSVFuzzer:
    """Parses a PVE Book CSV's Chapter/Map Type/Node hierarchy and generates
    fuzz cases focused on Book ID, Chapter Number, Node, CSS Req List,
    CSS Reward ID, CSS Reward Quantity, CSS RBE ID."""

    FOCUS_COLUMNS = [
        "Book ID",
        "Chapter Number",
        "Node",
        "CSS Req List",
        "CSS Reward ID",
        "CSS Reward Quantity",
        "CSS RBE ID",
    ]
    _REQUIRED_COLUMNS = FOCUS_COLUMNS + ["Map Type", "Difficulty", "Chapter Loc ID"]

    def __init__(self, df):
        missing = [c for c in self._REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"CSV doesn't look like a PVE Book CSV — missing required column(s): {missing}"
            )
        self.df = df.copy()
        self.base_book_id = str(self.df["Book ID"].iloc[0]) if len(self.df) else "Book"
        self.map_type_node_counts = infer_map_type_node_counts(self.df)
        self._case_seq = 0

    def _fresh_case_df(self):
        """Copy of the base df with a case-unique Book ID, so every generated
        case targets an independent (nonexistent) Book and never collides with
        a previous case's possibly-accepted import."""
        self._case_seq += 1
        df = self.df.copy()
        df["Book ID"] = f"{self.base_book_id}_F{self._case_seq:03d}"
        return df

    @staticmethod
    def _case(name, category, columns_touched, mutated_df, expected, note=""):
        return {
            "name": name,
            "category": category,
            "columns_touched": columns_touched,
            "mutated_df": mutated_df,
            "expected": expected,
            "note": note,
        }

    def generate_cases(self, categories, max_per_category):
        categories = set(categories)
        cases = []
        if "structural" in categories:
            cases.extend(self._cap(self._gen_structural_cases(), max_per_category))
        if "hierarchy" in categories:
            cases.extend(self._cap(self._gen_hierarchy_cases(), max_per_category))
        if "focus_column" in categories:
            cases.extend(self._cap(self._gen_focus_column_cases(), max_per_category))
        return cases

    @staticmethod
    def _cap(cases, max_n):
        if max_n and len(cases) > max_n:
            print(f"      ⚠️ PVE Book Fuzz: capping {len(cases)} -> {max_n} case(s) (max_per_category)")
            cases = cases[:max_n]
        return cases

    # -- structural: required-field integrity on the focus columns -------
    def _gen_structural_cases(self):
        cases = []

        df = self._fresh_case_df()
        df.at[0, "Book ID"] = ""
        cases.append(self._case("blank_book_id", "structural", ["Book ID"], df, "reject"))

        df = self._fresh_case_df()
        last = df.index[-1]
        df.at[last, "Book ID"] = f"{df.at[last, 'Book ID']}_OTHER"
        cases.append(self._case("multiple_book_ids_in_one_file", "structural", ["Book ID"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "Chapter Number"] = ""
        cases.append(self._case("blank_chapter_number", "structural", ["Chapter Number"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "Chapter Number"] = "abc"
        cases.append(self._case("non_numeric_chapter_number", "structural", ["Chapter Number"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "Chapter Number"] = "-1"
        cases.append(self._case("negative_chapter_number", "structural", ["Chapter Number"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "Node"] = ""
        cases.append(self._case("blank_node", "structural", ["Node"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "Node"] = "abc"
        cases.append(self._case("non_numeric_node", "structural", ["Node"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "CSS Reward ID"] = ""
        cases.append(self._case(
            "css_reward_id_blank_quantity_filled", "structural",
            ["CSS Reward ID", "CSS Reward Quantity"], df, "reject",
        ))

        df = self._fresh_case_df()
        df.at[0, "CSS Reward Quantity"] = ""
        cases.append(self._case(
            "css_reward_quantity_blank_id_filled", "structural",
            ["CSS Reward ID", "CSS Reward Quantity"], df, "reject",
        ))

        df = self._fresh_case_df()
        df.at[0, "CSS RBE ID"] = ""
        cases.append(self._case(
            "css_rbe_id_blank_while_css_req_filled", "structural",
            ["CSS RBE ID", "CSS Req List"], df, "reject",
        ))

        df = self._fresh_case_df()
        df.at[0, "CSS Req List"] = "Rarity_99"
        cases.append(self._case("css_req_list_unknown_rarity_token", "structural", ["CSS Req List"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "CSS Reward Quantity"] = "-500"
        cases.append(self._case("negative_css_reward_quantity", "structural", ["CSS Reward Quantity"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "CSS Reward Quantity"] = "not_a_number"
        cases.append(self._case(
            "non_numeric_css_reward_quantity", "structural", ["CSS Reward Quantity"], df, "reject",
        ))

        # Soft/unconfirmed rule -> exploratory, never asserted PASS/FAIL
        df = self._fresh_case_df()
        df.at[0, "CSS RBE ID"] = f"{df.at[0, 'CSS RBE ID']}_DIFFERENT"
        cases.append(self._case(
            "css_rbe_id_inconsistent_within_book", "structural", ["CSS RBE ID"], df, "unknown",
            note="Assumes CSS RBE ID should be uniform across one book — not confirmed with dev team.",
        ))

        return cases

    # -- focus_column: remaining type/format variants on the 7 named cols --
    def _gen_focus_column_cases(self):
        cases = []

        df = self._fresh_case_df()
        df.at[0, "CSS Req List"] = ",,Rarity_5,,"
        cases.append(self._case("css_req_list_stray_commas", "focus_column", ["CSS Req List"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "CSS Reward ID"] = "Currency_DOES_NOT_EXIST_XYZ"
        cases.append(self._case(
            "css_reward_id_unrecognized_reference", "focus_column", ["CSS Reward ID"], df, "unknown",
            note="Can't validate against the real reward DB offline — exploratory only.",
        ))

        df = self._fresh_case_df()
        df.at[0, "CSS Reward Quantity"] = "0"
        cases.append(self._case(
            "zero_css_reward_quantity", "focus_column", ["CSS Reward Quantity"], df, "unknown",
            note="Unclear if 0 is a valid 'no reward' sentinel.",
        ))

        df = self._fresh_case_df()
        df.at[0, "Node"] = "999"
        cases.append(self._case(
            "node_out_of_range_for_map_type", "focus_column", ["Node"], df, "unknown",
            note="Extending beyond the observed max node count isn't necessarily invalid.",
        ))

        df = self._fresh_case_df()
        df.at[0, "Book ID"] = f"{df.at[0, 'Book ID']} <script>alert(1)</script>"
        cases.append(self._case("book_id_special_chars", "focus_column", ["Book ID"], df, "reject"))

        df = self._fresh_case_df()
        df.at[0, "Chapter Number"] = "0"
        cases.append(self._case(
            "zero_chapter_number", "focus_column", ["Chapter Number"], df, "unknown",
            note="Unclear if Chapter Number is 1-indexed by hard rule.",
        ))

        return cases

    # -- hierarchy: Chapter Number / Map Type / Node relationship ---------
    def _gen_hierarchy_cases(self):
        cases = []
        df0 = self.df
        chapters = df0["Chapter Number"].dropna().unique().tolist()
        map_types = df0["Map Type"].dropna().unique().tolist()

        # 1. Same chapter, different Map Type across its Difficulty rows.
        if chapters and len(map_types) > 1:
            target_chapter = chapters[0]
            rows0 = df0[df0["Chapter Number"] == target_chapter]
            if rows0["Difficulty"].nunique() > 1:
                other_map_type = next((m for m in map_types if m != rows0["Map Type"].iloc[0]), None)
                if other_map_type:
                    df = self._fresh_case_df()
                    rows = df[df["Chapter Number"] == target_chapter]
                    hard_idx = rows[rows["Difficulty"].astype(str).str.lower() == "hard"].index
                    target_idx = hard_idx[0] if len(hard_idx) else rows.index[-1]
                    df.at[target_idx, "Map Type"] = other_map_type
                    cases.append(self._case(
                        "map_type_inconsistent_across_difficulties", "hierarchy",
                        ["Chapter Number", "Map Type"], df, "reject",
                    ))

        # 2. Map Type changed without adjusting Node rows -> count mismatch.
        for map_type, node_count in self.map_type_node_counts.items():
            other_map_type = next(
                (m for m in map_types if m != map_type and self.map_type_node_counts.get(m) != node_count),
                None,
            )
            if not other_map_type:
                continue
            rows0 = df0[df0["Map Type"] == map_type]
            if rows0.empty:
                continue
            chapter = rows0["Chapter Number"].iloc[0]
            df = self._fresh_case_df()
            df.loc[df["Chapter Number"] == chapter, "Map Type"] = other_map_type
            cases.append(self._case(
                "map_type_changed_node_count_mismatch", "hierarchy",
                ["Chapter Number", "Map Type", "Node"], df, "reject",
            ))
            break

        # 3. Duplicate Node within the same Chapter+Difficulty.
        if len(df0) > 1:
            df = self._fresh_case_df()
            idx0, idx1 = df.index[0], df.index[1]
            df.at[idx1, "Chapter Number"] = df.at[idx0, "Chapter Number"]
            df.at[idx1, "Difficulty"] = df.at[idx0, "Difficulty"]
            df.at[idx1, "Node"] = df.at[idx0, "Node"]
            cases.append(self._case(
                "duplicate_node_same_chapter_difficulty", "hierarchy",
                ["Chapter Number", "Node"], df, "reject",
            ))

        # 4. Node-number gap (skip Node "2") for a map type with >=3 nodes.
        for map_type, node_count in self.map_type_node_counts.items():
            if node_count < 3:
                continue
            rows0 = df0[df0["Map Type"] == map_type]
            chapter = rows0["Chapter Number"].iloc[0]
            difficulty = rows0["Difficulty"].iloc[0]
            df = self._fresh_case_df()
            mask = (
                (df["Chapter Number"] == chapter)
                & (df["Difficulty"] == difficulty)
                & (df["Node"].astype(str) == "2")
            )
            if mask.any():
                df = df[~mask].reset_index(drop=True)
                cases.append(self._case(
                    "node_number_gap", "hierarchy", ["Chapter Number", "Node"], df, "reject",
                ))
            break

        # 5. Referential garbage Map Type.
        df = self._fresh_case_df()
        df.at[0, "Map Type"] = "ZMap_DOES_NOT_EXIST_XYZ"
        cases.append(self._case("unknown_map_type", "hierarchy", ["Map Type"], df, "reject"))

        # 6. Extra node beyond the inferred max (exploratory).
        if chapters:
            rows0 = df0[df0["Chapter Number"] == chapters[0]]
            max_node = pd.to_numeric(rows0["Node"], errors="coerce").max()
            extra_row = rows0.iloc[[0]].copy()
            extra_row["Node"] = str(int(max_node) + 1) if pd.notna(max_node) else "99"
            df = self._fresh_case_df()
            extra_row["Book ID"] = df["Book ID"].iloc[0]
            df = pd.concat([df, extra_row], ignore_index=True)
            cases.append(self._case(
                "extra_node_beyond_inferred_max", "hierarchy", ["Node"], df, "unknown",
                note="Extending beyond the observed max isn't necessarily a violation.",
            ))

        return cases


# ---------------------------------------------------------------------------
# Mixin: orchestrates upload + classify + report for every generated case
# ---------------------------------------------------------------------------
class PVEBookFuzzTesterMixin:
    """run_pve_book_csv_fuzz(): the PVE Book CSV import fuzz-test entry point."""

    def run_pve_book_csv_fuzz(self, page, base_file_name, options=None):
        options = options or {}
        categories = set(options.get("categories") or ALL_CATEGORIES)
        max_per_category = int(options.get("max_per_category") or 5)

        full_path = os.path.join(DOWNLOAD_DIR, base_file_name)
        if not os.path.exists(full_path):
            entry = {"step": "PVE Book Fuzz Init", "status": "FAIL", "details": f"File not found: {base_file_name}"}
            return [entry], [entry]

        try:
            base_df = pd.read_csv(full_path, dtype=str).fillna("")
        except Exception as e:
            entry = {"step": "PVE Book Fuzz Init", "status": "FAIL", "details": f"Cannot parse CSV: {e}"}
            return [entry], [entry]

        try:
            fuzzer = PVEBookCSVFuzzer(base_df)
        except ValueError as e:
            entry = {"step": "PVE Book Fuzz Init", "status": "FAIL", "details": str(e)}
            return [entry], [entry]

        report_logs = []
        structured = []

        stateless_categories = [c for c in ("structural", "hierarchy", "focus_column") if c in categories]
        cases = fuzzer.generate_cases(stateless_categories, max_per_category)
        print(f"   🧪 PVE Book CSV Fuzz: generated {len(cases)} case(s) across {stateless_categories}")

        for case in cases:
            result = self._run_pve_book_fuzz_case(page, case)
            report_logs.append({
                "step": f"PVE Book Fuzz: {case['name']}",
                "status": result["verdict"],
                "details": result["note"],
            })
            structured.append(result)

        if "business_replay" in categories:
            for result in self._run_pve_book_business_replay(page, base_df):
                report_logs.append({
                    "step": f"PVE Book Fuzz: {result['case']}",
                    "status": result["verdict"],
                    "details": result["note"],
                })
                structured.append(result)

        return report_logs, structured

    # -- per-case upload + classify ---------------------------------------
    def _run_pve_book_fuzz_case(self, page, case):
        t0 = time.time()
        case_file = re.sub(r"[^\w\-.]", "_", f"pve_book_fuzz_{case['name']}.csv")
        case_path = os.path.join(DOWNLOAD_DIR, case_file)
        case["mutated_df"].to_csv(case_path, index=False)

        try:
            outcome, popup_text = self._pve_book_upload_and_classify(page, case_file)
        except Exception as e:
            outcome, popup_text = "unknown", f"Upload crashed: {e}"
        finally:
            try:
                os.remove(case_path)
            except Exception:
                pass

        verdict, note = self._judge_pve_book_fuzz_result(case["expected"], outcome, popup_text)
        if case.get("note"):
            note = f"{note} ({case['note']})"

        return {
            "case": case["name"],
            "category": case["category"],
            "columns_touched": ", ".join(case.get("columns_touched") or []),
            "expected": case["expected"],
            "actual": outcome,
            "popup_text": popup_text,
            "verdict": verdict,
            "note": note,
            "duration_s": round(time.time() - t0, 1),
        }

    def _judge_pve_book_fuzz_result(self, expected, actual, popup_text):
        """Verdict matrix — mirrors the RBE campaign's 'blocked=good, accepted=bad'
        convention, extended with a message-quality axis (WARNING) and an
        exploratory tier (INFO) for rules that aren't confirmed."""
        if expected == "unknown":
            return "INFO", f"Exploratory case — actual={actual}: {popup_text[:180]}"

        if expected == "reject":
            if actual == "reject":
                error_rows = parse_import_csv_error_popup(popup_text) or []
                malformed = is_malformed_error_text(popup_text) or any(
                    is_malformed_error_text(row.get("error")) for row in error_rows
                )
                if malformed:
                    return "WARNING", f"Blocked correctly, but error message is unreadable: {popup_text[:180]}"
                return "PASS", f"Blocked correctly: {popup_text[:180]}"
            if actual == "accept":
                return "FAIL", "System accepted invalid data"
            return "INFO", f"Could not determine outcome: {popup_text[:180]}"

        if expected == "accept":
            if actual == "accept":
                return "PASS", "Imported successfully"
            if actual == "reject":
                missing = parse_missing_chapter_popup(popup_text)
                extra = f" Missing chapter IDs reported: {missing}" if missing else ""
                return "FAIL", f"System rejected valid data: {popup_text[:180]}{extra}"
            return "INFO", f"Could not determine outcome: {popup_text[:180]}"

        return "INFO", f"Unhandled expectation '{expected}': {popup_text[:180]}"

    def _click_confirm_round_if_present(self, page):
        """Clicks a pre-import 'Are you sure? / Warning -> Continue' round, never
        the final result — only Continue/Proceed/Yes buttons match, deliberately
        excluding OK so a genuine result dialog is never dismissed unread."""
        try:
            buttons = page.locator(
                ".modal.show, .modal.in, [role='dialog']:visible, .swal2-popup:visible"
            ).locator("button").all()
            for b in buttons:
                try:
                    if not b.is_visible():
                        continue
                    text = (b.inner_text() or "").strip()
                    if _CONFIRM_ROUND_RE.match(text):
                        b.click(force=True)
                        return text
                except Exception:
                    continue
        except Exception:
            pass
        return None

    _IMPORT_TRIGGER_SELECTOR_TEMPLATES = (
        "button:has-text('{t}')",
        "a:has-text('{t}')",
        "label:has-text('{t}')",
        "[role='button']:has-text('{t}')",
    )

    def _find_pve_book_import_trigger(self, page, target_text):
        """Finds the visible 'Import Book CSV' trigger. Tries each selector TYPE
        separately (button / a / label / role=button) with its own visibility
        check — a single combined `sel1, sel2, sel3` locator's `.first` picks by
        raw DOM order across ALL alternatives, which previously misfired: a
        hidden, unrelated `<input type=file>` elsewhere on the page (e.g. for a
        totally different upload widget) sorted before the real button in the
        DOM and got picked instead, reporting 'not found' even though the real
        button was plainly visible."""
        for tpl in self._IMPORT_TRIGGER_SELECTOR_TEMPLATES:
            try:
                loc = page.locator(tpl.format(t=target_text)).first
                if loc.count() > 0 and loc.is_visible():
                    return loc
            except Exception:
                continue
        # Last resort: a bare visible file input (most triggers are a styled
        # button/label wrapping a hidden input, already handled above).
        try:
            file_input = page.locator("input[type='file']").first
            if file_input.count() > 0 and file_input.is_visible():
                return file_input
        except Exception:
            pass
        return None

    def _pve_book_upload_and_classify(self, page, file_name, timeout_s=150):
        """Selects the file on the 'Import Book CSV' trigger, then polls (up to
        timeout_s — imports can be slow) until a result popup is classified.
        Reuses self._scan_for_result_popup for PASS/FAIL classification, and
        reads the full untrimmed dialog text separately for the Book-specific
        parsers (parse_import_csv_error_popup / parse_missing_chapter_popup)."""
        full_path = os.path.join(DOWNLOAD_DIR, file_name)
        try:
            page.evaluate("window.__popupResult = null;")
        except Exception:
            pass

        btn = self._find_pve_book_import_trigger(page, "Import Book CSV")
        if btn is None:
            print("      ❌ PVE Book Fuzz: 'Import Book CSV' trigger not found/visible "
                  "(tried button/a/label/role=button + bare file input)")
            return "unknown", "Import Book CSV button not found"

        try:
            if btn.get_attribute("type") == "file":
                btn.set_input_files(full_path)
            else:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    btn.click()
                fc_info.value.set_files(full_path)
        except Exception as e:
            return "unknown", f"Could not select file: {e}"

        try:
            confirm = page.locator(".swal2-confirm, button.btn-primary:has-text('Upload')").first
            if confirm.is_visible(timeout=2000):
                confirm.click(force=True)
        except Exception:
            pass

        deadline = time.time() + timeout_s
        outcome, popup_text = "unknown", ""
        confirm_rounds = 0
        while time.time() < deadline:
            clicked = self._click_confirm_round_if_present(page)
            if clicked and confirm_rounds < 3:
                confirm_rounds += 1
                print(f"      🟠 PVE Book Fuzz: confirm/warning round {confirm_rounds} -> clicked '{clicked}'")
                time.sleep(0.8)
                continue

            found, kind, scan_text = self._scan_for_result_popup(page)
            if found and kind in ("PASS", "FAIL"):
                outcome = "accept" if kind == "PASS" else "reject"
                popup_text = _read_full_visible_dialog_text(page) or scan_text or ""
                break
            time.sleep(1.0)

        if outcome == "unknown" and not popup_text:
            popup_text = f"No result popup within {timeout_s}s (import may not have completed)"

        self._ensure_popup_closed(page)
        return outcome, popup_text

    # -- business_replay: baseline create -> incremental update -> partial ---
    def _run_pve_book_business_replay(self, page, base_df):
        results = []

        ts = datetime.datetime.now().strftime("%m%d%H%M")
        rnd = uuid.uuid4().hex[:4]
        new_book_id = f"PVEFUZZ_{ts}_{rnd}"

        baseline_df = base_df.copy()
        baseline_df["Book ID"] = new_book_id
        if "Chapter Loc ID" in baseline_df.columns:
            baseline_df["Chapter Loc ID"] = baseline_df["Chapter Loc ID"].apply(
                lambda v: f"{v}_{new_book_id}" if str(v).strip() else v
            )

        t0 = time.time()
        outcome, popup_text = self._upload_business_replay_variant(
            page, baseline_df, f"business_baseline_{new_book_id}"
        )
        verdict, note = self._judge_pve_book_fuzz_result("accept", outcome, popup_text)
        results.append({
            "case": "business_replay_baseline_create", "category": "business_replay",
            "columns_touched": "Book ID, Chapter Loc ID", "expected": "accept",
            "actual": outcome, "popup_text": popup_text, "verdict": verdict, "note": note,
            "duration_s": round(time.time() - t0, 1),
        })

        if verdict != "PASS":
            results.append({
                "case": "business_replay_skipped", "category": "business_replay",
                "columns_touched": "", "expected": "-", "actual": "-", "popup_text": "",
                "verdict": "INFO",
                "note": "Baseline book creation did not clearly succeed — skipping incremental/partial-removal replay.",
                "duration_s": 0,
            })
            return results

        chapter_loc_ids = []
        if "Chapter Loc ID" in baseline_df.columns:
            chapter_loc_ids = [v for v in baseline_df["Chapter Loc ID"].tolist() if str(v).strip()]
        state = _load_pve_book_fuzz_state()
        state["last_book_id"] = new_book_id
        state["last_chapter_loc_ids"] = chapter_loc_ids
        _save_pve_book_fuzz_state(state)

        # Incremental update: same Book ID + all Chapter Loc IDs, one harmless
        # value changed -> the app should accept this without complaint.
        incr_df = baseline_df.copy()
        if "Hype" in incr_df.columns:
            incr_df["Hype"] = incr_df["Hype"].apply(
                lambda v: "FALSE" if str(v).strip().upper() == "TRUE" else "TRUE"
            )
        t1 = time.time()
        outcome, popup_text = self._upload_business_replay_variant(
            page, incr_df, f"business_incremental_{new_book_id}"
        )
        verdict, note = self._judge_pve_book_fuzz_result("accept", outcome, popup_text)
        results.append({
            "case": "business_replay_incremental_update", "category": "business_replay",
            "columns_touched": "Hype", "expected": "accept",
            "actual": outcome, "popup_text": popup_text, "verdict": verdict, "note": note,
            "duration_s": round(time.time() - t1, 1),
        })

        # Partial chapter removal — the P0 repro. Desired behavior is "accept"
        # (incremental chapter updates should work), so a FAIL here with the
        # captured popup text/chapter-ID list IS the bug artifact the team needs.
        if "Chapter Number" in baseline_df.columns and baseline_df["Chapter Number"].nunique() > 1:
            chapters = sorted(baseline_df["Chapter Number"].dropna().unique().tolist(), key=str)
            drop_chapter = chapters[-1]
            partial_df = baseline_df[baseline_df["Chapter Number"] != drop_chapter].copy()
            t2 = time.time()
            outcome, popup_text = self._upload_business_replay_variant(
                page, partial_df, f"business_partial_{new_book_id}"
            )
            verdict, note = self._judge_pve_book_fuzz_result("accept", outcome, popup_text)
            results.append({
                "case": "business_replay_partial_chapter_removal", "category": "business_replay",
                "columns_touched": "Chapter Number, Chapter Loc ID", "expected": "accept",
                "actual": outcome, "popup_text": popup_text, "verdict": verdict, "note": note,
                "duration_s": round(time.time() - t2, 1),
            })

        return results

    def _upload_business_replay_variant(self, page, df, name):
        file_name = re.sub(r"[^\w\-.]", "_", f"pve_book_fuzz_{name}.csv")
        file_path = os.path.join(DOWNLOAD_DIR, file_name)
        df.to_csv(file_path, index=False)
        try:
            return self._pve_book_upload_and_classify(page, file_name)
        except Exception as e:
            return "unknown", f"Upload crashed: {e}"
        finally:
            try:
                os.remove(file_path)
            except Exception:
                pass

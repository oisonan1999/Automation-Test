import streamlit as st
import pandas as pd
import json
import os
import sys
import io
import re
import glob

# --- DEV HOT-RELOAD ---------------------------------------------------------
# Streamlit rerun lại app.py mỗi lần tương tác, nhưng Python cache module đã
# import trong sys.modules → sửa code trong ai/* hay automation/* sẽ KHÔNG được
# nạp lại nếu không restart terminal. Block này phát hiện thay đổi (theo mtime)
# rồi purge module + cache + instance automation cũ, để các import bên dưới đọc
# code mới ngay trong cùng lần rerun. Tắt bằng DEV_AUTORELOAD=0 (vd: production).
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_WATCH_DIRS = ("ai", "automation")


def _project_code_mtime():
    latest = 0.0
    for d in _WATCH_DIRS:
        for path in glob.glob(os.path.join(_PROJECT_ROOT, d, "**", "*.py"), recursive=True):
            try:
                latest = max(latest, os.path.getmtime(path))
            except OSError:
                pass
    return latest


if os.environ.get("DEV_AUTORELOAD", "1") == "1":
    _sig = _project_code_mtime()
    _last = st.session_state.get("_code_sig")
    if _last is not None and _sig != _last:
        _watch_prefixes = tuple(os.path.join(_PROJECT_ROOT, d) for d in _WATCH_DIRS)
        for _name in list(sys.modules):
            _mod = sys.modules.get(_name)
            _f = getattr(_mod, "__file__", "") or ""
            if _f.startswith(_watch_prefixes):
                del sys.modules[_name]
        st.cache_data.clear()
        st.cache_resource.clear()
        st.session_state.pop("automation", None)  # rebuild với class mới
    st.session_state["_code_sig"] = _sig
# ---------------------------------------------------------------------------

from ai.brain import (
    parse_command_to_json,
    save_scenario,
    load_scenarios,
    delete_scenarios,
)
import ai.brain as brain_module
from automation.core import BrickAutomation
from ai import plan_cache

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Brick AI Automation By HieuNM", layout="wide")

# --- CUSTOM CSS ---
st.markdown(
    """
<style>
    .stButton>button {
        width: 100%;
    }
    .mode-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
        margin-left: 8px;
    }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🤖 Brick QA Automation AI By HieuNM")

# --- KHỞI TẠO STATE (Bộ nhớ đệm) ---
if "automation" not in st.session_state:
    st.session_state.automation = BrickAutomation()
if "current_plan" not in st.session_state:
    st.session_state.current_plan = None
if "input_text" not in st.session_state:
    st.session_state.input_text = ""
if "run_execution" not in st.session_state:
    st.session_state.run_execution = False
if "test_logs" not in st.session_state:
    st.session_state.test_logs = []
if "last_mode_used" not in st.session_state:
    st.session_state.last_mode_used = None
if "pending_save_dialog" not in st.session_state:
    st.session_state.pending_save_dialog = None
if "pending_delete_dialog" not in st.session_state:
    st.session_state.pending_delete_dialog = None
if "scenario_notice" not in st.session_state:
    st.session_state.scenario_notice = None
if "loaded_scenario_command" not in st.session_state:
    st.session_state.loaded_scenario_command = None
if "loaded_scenario_plan" not in st.session_state:
    st.session_state.loaded_scenario_plan = None

# --- SMOKE BRICK LIVE STATE ---
if "smoke_run_execution" not in st.session_state:
    st.session_state.smoke_run_execution = False
if "smoke_results" not in st.session_state:
    st.session_state.smoke_results = []
if "smoke_selected_csv" not in st.session_state:
    st.session_state.smoke_selected_csv = "downloads/smoketestBrickLive.csv"
if "smoke_last_summary" not in st.session_state:
    st.session_state.smoke_last_summary = None
_SMOKE_ID_CACHE_FILE = os.path.join(os.path.dirname(__file__), "config", "smoke_last_ids.json")

def _load_smoke_ids():
    try:
        if os.path.exists(_SMOKE_ID_CACHE_FILE):
            with open(_SMOKE_ID_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_smoke_ids(mapping: dict):
    try:
        os.makedirs(os.path.dirname(_SMOKE_ID_CACHE_FILE), exist_ok=True)
        with open(_SMOKE_ID_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"   ⚠️ Could not save smoke IDs: {e}")

if "smoke_last_created_id_by_feature" not in st.session_state:
    # Key = value from CSV column "Features" (e.g. "RBE", "PVE", "Gacha"...)
    # Value = last unique ID generated for a CREATE/CLONE case in that feature
    # Loaded from disk so it persists across Streamlit restarts
    st.session_state.smoke_last_created_id_by_feature = _load_smoke_ids()
if "smoke_use_golden" not in st.session_state:
    # Bật cache "golden plan": case nào đã PASS sạch thì lần sau chạy thẳng plan đã
    # lưu, bỏ qua AI (nhanh + xác định). Tắt để luôn nhờ AI sinh lại plan.
    st.session_state.smoke_use_golden = True
if "smoke_use_claude_haiku" not in st.session_state:
    st.session_state.smoke_use_claude_haiku = False
if "smoke_running" not in st.session_state:
    st.session_state.smoke_running = False
if "smoke_current_idx" not in st.session_state:
    st.session_state.smoke_current_idx = 0
if "smoke_df_csv" not in st.session_state:
    st.session_state.smoke_df_csv = None
if "smoke_total_cases" not in st.session_state:
    st.session_state.smoke_total_cases = 0
if "smoke_waiting_for_deploy" not in st.session_state:
    st.session_state.smoke_waiting_for_deploy = False
if "smoke_deploy_info" not in st.session_state:
    st.session_state.smoke_deploy_info = {}

# --- AI RUN GOLDEN STATE ---
if "airun_use_golden" not in st.session_state:
    st.session_state.airun_use_golden = True
if "airun_use_claude_careful" not in st.session_state:
    st.session_state.airun_use_claude_careful = False
if "airun_raw_input" not in st.session_state:
    st.session_state.airun_raw_input = None
if "airun_generated_unique_id" not in st.session_state:
    st.session_state.airun_generated_unique_id = None
if "airun_last_id" not in st.session_state:
    st.session_state.airun_last_id = None
if "airun_golden_used" not in st.session_state:
    st.session_state.airun_golden_used = False

automation = st.session_state.automation


# ============================================================
# SMOKE BRICK LIVE HELPERS
# ============================================================

SMOKE_OUTPUT_PREFIX = "downloads/smoketestBrickLive_report_"


def _parse_smoke_csv(csv_source) -> pd.DataFrame:
    """
    csv_source:
      - str path (ví dụ: downloads/Testcasesmokelive.csv)
      - bytes/bytearray (khi user upload file)
    """
    if isinstance(csv_source, (bytes, bytearray)):
        df = pd.read_csv(
            io.BytesIO(csv_source),
            dtype=str,
            keep_default_na=False,
        )
    else:
        df = pd.read_csv(
            str(csv_source),
            dtype=str,
            keep_default_na=False,
        )

    # Ensure expected columns exist
    for col in ["Features", "Testcase", "Result", "Note"]:
        if col not in df.columns:
            df[col] = ""

    # Normalize empty strings
    df["Features"] = df["Features"].fillna("").astype(str)
    df["Testcase"] = df["Testcase"].fillna("").astype(str)
    df["Result"] = df["Result"].fillna("").astype(str)
    df["Note"] = df["Note"].fillna("").astype(str)
    return df


def _normalize_smoke_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    CSV bạn đang dùng có format:
      - 'Features' có thể bị trống ở nhiều dòng kế tiếp
      - cần forward-fill 'Features' theo dòng
    """
    df = df.copy()
    df["Features"] = df["Features"].replace("", pd.NA).ffill().fillna("").astype(str)
    return df


def _build_testcase_display(testcase: str) -> str:
    """
    Hiển thị ngắn gọn cho dropdown:
      - Nếu có format "<label>: <steps>" -> lấy "<label>"
      - Ngược lại: lấy nguyên chuỗi (đã strip)
    """
    text = str(testcase or "").strip()
    if not text:
        return ""
    label, _steps = _split_testcase_label_and_steps(text)
    return label if label else text


def _build_smoke_dropdowns(
    df: pd.DataFrame, selected_feature_value: str | None
) -> tuple[list[str], dict[str, str]]:
    """
    Returns:
      - testcase_display_options: list of display strings (including "Tất cả Testcase")
      - display_to_value: mapping display -> raw testcase value
    """
    if selected_feature_value:
        df_f = df[df["Features"].astype(str).eq(selected_feature_value)]
    else:
        df_f = df

    raw_values = [str(x or "").strip() for x in df_f["Testcase"].astype(str).tolist()]
    raw_values = [x for x in raw_values if x]

    # Unique while keeping order
    seen: set[str] = set()
    unique_raw: list[str] = []
    for v in raw_values:
        if v not in seen:
            seen.add(v)
            unique_raw.append(v)

    # Build unique display strings
    display_to_value: dict[str, str] = {}
    display_options: list[str] = ["Tất cả Testcase"]

    # If duplicates display label, disambiguate with suffix
    label_count: dict[str, int] = {}
    for raw in unique_raw:
        base = _build_testcase_display(raw)
        base = base[:120]  # keep dropdown readable
        label_count[base] = label_count.get(base, 0) + 1
        display = base if label_count[base] == 1 else f"{base} (#{label_count[base]})"
        display_options.append(display)
        display_to_value[display] = raw

    return display_options, display_to_value


def _build_case_command(feature: str, testcase: str) -> str:
    feature = str(feature or "").strip()
    testcase = str(testcase or "").strip()
    # Add feature navigation context for better AI reliability
    if feature:
        return f"Vào {feature} -> {testcase}"
    return testcase


_PLAN_FIELD_TO_FEATURE = {
    "book name": "PVE",
    "rules based tournament id": "RBE",
    "cloned rules based tournament id": "RBE",
    "new event id": "Gacha",
    "new ff id": "Faction Feud",
    "new tournament id": "Showdown",
    "bracket id": "Showdown",
    "nrb id": "Showdown",
    "new offer id": "Offer",
    "new section id": "Offer Section",
    "currency id": "Currency",
    "grabbag id": "Grabbag",
    "new tier id": "Fight Card Slots",
    "fightcard id": "Fight Card",
    "faction boss battle name": "Faction Boss",
    "new key": "Perk/Perk Slot",
    "new superstar id": "SuperStar",
    "loc id": "Localization",
    "moment poster id": "Moment Poster",
}


def _extract_id_from_plan(action_plan: list, feature_key: str):
    """Scan action_plan for the actual ID that was filled for the given feature.

    Reads from update_form data in reverse so the last-filled value wins.
    Returns None when no matching field is found.
    """
    if not action_plan:
        return None
    for step in reversed(action_plan):
        if step.get("action") == "update_form":
            data = step.get("data") or {}
            for key, val in data.items():
                feat = _PLAN_FIELD_TO_FEATURE.get(str(key).lower().strip())
                if feat == feature_key and val and str(val).strip():
                    return str(val).strip()
    return None


def _make_unique_hieunm_test_id() -> str:
    """
    Generate a unique ID for weekly runs.
    Prefix must be: hieunm_test
    """
    import datetime as _dt
    import uuid as _uuid

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    rnd = _uuid.uuid4().hex[:6]
    return f"hieunm_test_{ts}_{rnd}"


def _substitute_last_clone_id(command: str, smoke_ids: dict) -> tuple[str, str | None]:
    """
    In manual AI Run mode, substitute "ID vừa clone/tạo" phrases with the
    actual last-created ID. Always reads FRESH from the JSON file so that
    the value is always in sync with what's on disk (not stale session state).

    Returns (substituted_command, last_id_used).  last_id_used is None when no
    "vừa clone/tạo" pattern is found or no matching ID is available.

    Strategy: scan smoke_ids keys (e.g. "RBE", "PVE", "Gacha") and pick the
    one whose name appears in the command. If multiple match, use the first.
    Fallback: use the only entry if dict has exactly one key.
    """
    import re as _re

    _vua_broad = r"(?:[vj][ưừữu]a|vua)"
    # Trigger: any word followed by "vừa clone/tạo" — covers "ID vừa clone", "Book vừa clone", etc.
    _vua_pattern = _re.compile(
        rf"\S+\s+{_vua_broad}\s+(?:clone|t[ạa]o)",
        _re.IGNORECASE,
    )
    if not _vua_pattern.search(command):
        return command, None

    # Always read fresh from disk to avoid session-state drift; fallback to passed smoke_ids
    fresh_ids = _load_smoke_ids() or smoke_ids
    if not fresh_ids:
        return command, None

    # Entity-word hints: e.g. "Book" in context → use PVE feature's last ID
    _ENTITY_HINTS = {"book": "PVE", "chapter": "PVE"}

    def _get_id_for_context(context_upper: str) -> str | None:
        """
        Given the text before a 'vừa clone/tạo' occurrence (upper-cased), return the
        last-created ID for the nearest (rightmost) matching feature keyword.
        Cross-feature commands ("Vào Fight Card V3 -> ... Sửa RBE Event: ... RBE vừa clone")
        need per-occurrence resolution instead of one global feature pick.
        """
        best_feat = None
        best_pos = -1
        for fk, fid in fresh_ids.items():
            if not fid:
                continue
            p = context_upper.rfind(fk.upper())
            if p > best_pos:
                best_pos = p
                best_feat = fk
        # Entity hints as fallback
        if not best_feat or best_pos < 0:
            ctx_lower = context_upper.lower()
            for ent, hint_feat in _ENTITY_HINTS.items():
                if ent in ctx_lower and hint_feat in fresh_ids:
                    fid = fresh_ids[hint_feat]
                    _id = fid[-1] if isinstance(fid, list) and fid else fid
                    if _id:
                        print(f"   🔁 Entity hint: '{ent}' → feature '{hint_feat}', id='{_id}'")
                        return _id
        if best_feat is None:
            # Fallback: single entry in dict
            if len(fresh_ids) == 1:
                _v = next(iter(fresh_ids.values()))
                return _v[-1] if isinstance(_v, list) and _v else _v
            return None
        fid = fresh_ids[best_feat]
        return fid[-1] if isinstance(fid, list) and fid else fid

    # Order matters: most specific patterns first (Sửa/Filter before bare entity).
    # Use finditer + right-to-left substitution so earlier match positions stay valid.
    substitutions = [
        # FIELD-VALUE phrasing (highest priority): "...: Hãy lấy ID RBE vừa clone" → clean bare ID
        # (no "ID:" prefix — this is a form-field VALUE, not a row selector).
        (rf"(?:H[ãa]y\s+)?l[ấa]y\s+ID\s+(?:c[ủu]a\s+)?\S+\s+{_vua_broad}\s+(?:clone|t[ạa]o)(?:\s+ho[ặa]c\s+(?:clone|t[ạa]o))?", "{id}"),
        (rf"S[ửu]a\s+(?:\d+\s+)?\S+\s+{_vua_broad}\s+clone(?:\s+ho[ặa]c\s+t[ạa]o)?", "Sửa ID: {id}"),
        (rf"S[ửu]a\s+(?:\d+\s+)?\S+\s+{_vua_broad}\s+t[ạa]o(?:\s+ho[ặa]c\s+clone)?", "Sửa ID: {id}"),
        (rf"Filter\s+(?:\d+\s+)?\S+\s+{_vua_broad}\s+clone(?:\s+ho[ặa]c\s+t[ạa]o)?", "Filter ID: {id}"),
        (rf"Filter\s+(?:\d+\s+)?\S+\s+{_vua_broad}\s+t[ạa]o(?:\s+ho[ặa]c\s+clone)?", "Filter ID: {id}"),
        (rf"(?:\d+\s+)?\S+\s+{_vua_broad}\s+clone(?:\s+ho[ặa]c\s+t[ạa]o)?", "ID: {id}"),
        (rf"(?:\d+\s+)?\S+\s+{_vua_broad}\s+t[ạa]o(?:\s+ho[ặa]c\s+clone)?", "ID: {id}"),
    ]

    primary_last_id = None  # leftmost substitution's ID (used for golden plan {{LAST_ID}} token)

    for pattern, fmt in substitutions:
        matches = list(_re.finditer(pattern, command, flags=_re.IGNORECASE))
        if not matches:
            continue
        # Apply right-to-left so left-side positions remain valid during string mutation
        for m in reversed(matches):
            context_upper = command[: m.start()].upper()
            mid = _get_id_for_context(context_upper)
            if mid is None:
                continue
            replacement = fmt.format(id=mid)
            print(f"   🔁 Per-occurrence sub: '{m.group(0)}' → '{replacement}' (id={mid})")
            command = command[: m.start()] + replacement + command[m.end() :]
            primary_last_id = mid  # right-to-left: last write = leftmost match's ID

    # primary_last_id = ID of the leftmost substituted occurrence
    if primary_last_id is None:
        return command, None

    return command, primary_last_id


def _is_deploy_case(label: str, steps: str) -> bool:
    return "deploy" in f"{label} {steps}".lower()


def _should_force_unique_id(case_label: str, testcase_text: str) -> bool:
    """
    Force unique ID only when the test case explicitly requests ID generation via
    the Vietnamese pattern "hãy tự generate ... bắt đầu bằng <prefix>".
    This avoids false-positives for labels like "Clone Chapter then Save" which use
    "clone" as a sub-action verb (not creating a new top-level item).
    """
    import re as _re
    text = f"{case_label or ''} {testcase_text or ''}"
    return bool(_re.search(r'h[aã]y\s+t[uự]\s+generate', text, _re.IGNORECASE))


def _pregenerate_unique_id(command: str) -> str | None:
    """
    If command contains "hãy tự generate ... bắt đầu bằng <prefix>", pre-generate
    a unique ID now (same logic as the smoke loop) so we can use it for golden
    lookup/tokenization before the AI call.  Returns None if the pattern is absent.
    """
    import re as _re, datetime as _dt, uuid as _uuid
    if not _re.search(r'h[aã]y\s+t[uự]\s+generate', command, _re.IGNORECASE):
        return None
    _pfix_m = _re.search(r"bắt\s+đầu\s+bằng\s+(\S+)", command, _re.IGNORECASE)
    _pfix = _re.sub(r"[.,;:]*$", "", _pfix_m.group(1)).strip() if _pfix_m else "hieunm_test"
    _ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    _rnd = _uuid.uuid4().hex[:6]
    return f"{_pfix}_{_ts}_{_rnd}"


def _split_testcase_label_and_steps(testcase: str) -> tuple[str, str]:
    """
    CSV format: "<label>: <steps>"
    - label: hiển thị / summary (ví dụ: "Search for an RBE")
    - steps: phần mô tả sau ":" để AI thực thi (ví dụ: "Vào RBE -> Filter ...")
    """
    text = str(testcase or "").strip()
    if not text:
        return "", ""

    if ":" not in text:
        return text, ""

    label, steps = text.split(":", 1)
    return label.strip(), steps.strip()


def _extract_smoke_status_from_logs(logs: list[dict]) -> tuple[str, str]:
    """
    Core logs items are like: {"step": "...", "status": "PASS|FAIL|WARNING|CRASH", "details": "..."}.
    We return (status, note_detail).
    """
    if not logs:
        return "FAIL", "No execution logs"

    # Priority: CRASH > FAIL > WARNING > PASS
    status_rank = {
        "CRASH": 4,
        "FAIL": 3,
        "WARNING": 2,
        "PASS": 1,
        "SKIPPED": 0,
        "UNKNOWN": 0,
    }

    # Allow the first log (even UNKNOWN/SKIPPED) to "win" so we can show a better note
    best = ("UNKNOWN", -1, "")

    def _upd(s: str, details: str):
        nonlocal best
        s_up = (s or "").upper().strip()
        rank = status_rank.get(s_up, 0)
        if rank > best[1]:
            best = (s_up, rank, details or "")

    for item in logs:
        if not isinstance(item, dict):
            continue
        s = item.get("status") or item.get("result") or item.get("state")
        details = item.get("details") or item.get("detail") or ""
        _upd(str(s), str(details))

    # Also try to pick a meaningful detail for FAIL/WARNING
    final_status = best[0] if best[0] != "UNKNOWN" else "FAIL"
    note = best[2] or ""

    # If PASS but we still have verbose fail-like text in details, downgrade
    if final_status == "PASS":
        joined = " ".join(
            str(x.get("details", "")) for x in logs if isinstance(x, dict)
        ).lower()
        if "fail" in joined or "crash" in joined or "error" in joined:
            final_status = "FAIL"
            note = "Execution contained error keywords in logs"

    if final_status == "UNKNOWN":
        final_status = "FAIL"

    # If we have logs but none carried meaningful execution info, explain it
    if final_status == "FAIL" and not note:
        note = "Only navigation executed (no execution/log-producing steps)"

    return final_status, note[:500] if note else ""


def _smart_update_csv_result(
    df: pd.DataFrame, idx: int, result: str, note: str
) -> None:
    df.at[idx, "Result"] = str(result or "")
    df.at[idx, "Note"] = str(note or "")


@st.dialog("✅ Lưu kịch bản thành công")
def _show_save_success_dialog(scenario_name):
    st.success(f"Kịch bản **「{scenario_name}」** đã được lưu.")
    st.caption("File: `config/scenarios.json` — có thể load lại từ danh sách bên phải.")
    if st.button("Đóng", type="primary", width='stretch'):
        st.session_state.pending_save_dialog = None
        st.rerun()


@st.dialog("🗑 Xác nhận xóa kịch bản")
def _show_delete_confirm_dialog(scenario_names):
    st.warning(
        f"Bạn sắp xóa **{len(scenario_names)}** kịch bản. Thao tác không thể hoàn tác."
    )
    for name in scenario_names:
        st.markdown(f"- {name}")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Xóa vĩnh viễn", type="primary", width='stretch'):
            removed = delete_scenarios(scenario_names)
            st.session_state.pending_delete_dialog = None
            remaining = load_scenarios()
            sel = st.session_state.get("selected_file")
            if not remaining:
                if "selected_file" in st.session_state:
                    del st.session_state["selected_file"]
            elif sel in scenario_names or sel not in remaining:
                st.session_state.selected_file = next(iter(remaining))
            st.session_state.scenario_notice = (
                "deleted",
                removed,
                list(scenario_names),
            )
            st.rerun()
    with col_cancel:
        if st.button("Hủy", width='stretch'):
            st.session_state.pending_delete_dialog = None
            st.rerun()


# Popup sau khi lưu / thông báo sau khi xóa
if st.session_state.pending_save_dialog:
    _show_save_success_dialog(st.session_state.pending_save_dialog)

if st.session_state.pending_delete_dialog:
    _show_delete_confirm_dialog(st.session_state.pending_delete_dialog)

if st.session_state.scenario_notice:
    kind, *rest = st.session_state.scenario_notice
    if kind == "deleted":
        count, names = rest[0], rest[1]
        st.toast(f"Đã xóa {count} kịch bản.", icon="🗑")
        if names:
            st.info(f"Đã xóa: {', '.join(names)}")
    st.session_state.scenario_notice = None


# --- HÀM CALLBACK (LOAD KỊCH BẢN) ---
def load_scenario_callback():
    selected = st.session_state.selected_file
    saved = load_scenarios()

    if selected in saved:
        data = saved[selected]
        if isinstance(data, list):
            plan_to_load = data
            cmd_to_load = "Kịch bản cũ"
        else:
            plan_to_load = data.get("plan", [])
            cmd_to_load = data.get("command", "")

        st.session_state.input_text = cmd_to_load
        st.session_state.current_plan = plan_to_load
        st.session_state.loaded_scenario_command = cmd_to_load
        st.session_state.loaded_scenario_plan = plan_to_load
        st.session_state.test_logs = []


# --- GIAO DIỆN ---
col1, col2 = st.columns([2, 1])

with col1:
    # === INPUT AREA ===
    user_input = st.text_area(
        "Nhập lệnh test của bạn:",
        height=150,
        placeholder="Ví dụ: Vào Data Configs -> Perk -> Perk -> Edit ABC...",
        key="input_text",
    )

    # === MODE SELECTOR ===
    st.markdown("### ⚙️ Chế độ chạy")
    if "run_mode" not in st.session_state:
        st.session_state.run_mode = "AI Run (theo lệnh)"

    run_mode = st.radio(
        "Chọn chế độ",
        ["AI Run (theo lệnh)", "Smoke Brick Live (theo CSV)"],
        horizontal=True,
        index=0,
        key="run_mode",
    )

    # === BUTTONS ===
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        run_btn = st.button("🚀 Chạy Ngay", type="primary", width='stretch')
    with col_btn2:
        save_name = st.text_input("Tên kịch bản:", placeholder="Regression Test 1")
        save_btn = st.button("💾 Lưu Kịch Bản", width='stretch')

    st.divider()

    # === AI Run Golden Plan controls ===
    if run_mode == "AI Run (theo lệnh)":
        st.checkbox(
            "♻️ Dùng Golden Plan cache (bỏ qua AI cho lệnh đã PASS)",
            key="airun_use_golden",
            help=(
                "Lệnh nào chạy PASS hoàn toàn sẽ được lưu lại plan. Lần sau gõ đúng "
                "lệnh đó sẽ chạy thẳng plan đã lưu (chỉ thay ID động), không cần AI. "
                "Nếu replay fail thì tự huỷ cache, lần sau AI sinh lại."
            ),
        )
        _airun_golden_n = plan_cache.golden_count()
        st.caption(f"💾 {_airun_golden_n} golden plan đã lưu (chung với Smoke)")

        st.checkbox(
            "🧪 Careful Mode (Claude Sonnet 5 thay vì Qwen local)",
            key="airun_use_claude_careful",
            help=(
                "Dùng Claude API để sinh action plan thay vì Qwen3 qua Ollama. "
                "Chính xác hơn với lệnh tiếng Việt phức tạp, nhưng cần ANTHROPIC_API_KEY "
                "trong .env và tốn phí mỗi lần gọi. Tự fallback về Qwen nếu Claude lỗi."
            ),
        )

    # Smoke UI chỉ hiển thị khi đang chọn radio Smoke
    smoke_run_btn = False
    if run_mode == "Smoke Brick Live (theo CSV)":
        st.markdown("### 🔥 Smoke Brick Live")

        uploaded_smoke_csv = st.file_uploader(
            "Import CSV testcases",
            type=["csv"],
            accept_multiple_files=False,
            key="smoke_upload_csv",
            help="Upload file CSV (ví dụ downloads/smoketestBrickLive.csv) để chạy Smoke theo từng case.",
        )

        if uploaded_smoke_csv is not None:
            try:
                # Không ghi ra downloads/*_imported.csv nữa — giữ trong RAM để chạy & download cuối cùng
                st.session_state.smoke_selected_csv = (
                    uploaded_smoke_csv.getbuffer().tobytes()
                )
            except Exception as e:
                st.error(f"Không đọc được file upload: {str(e)[:200]}")
                st.stop()

        smoke_csv = st.selectbox(
            "CSV đầu vào (nếu không import file mới)",
            [
                "downloads/Testcasesmokelive.csv",
            ],
            index=0,
            key="smoke_csv_choice",
        )
        if uploaded_smoke_csv is None:
            st.session_state.smoke_selected_csv = smoke_csv

        # === Smoke scope selector (Feature / Testcase filtering) ===
        if "smoke_scope_mode" not in st.session_state:
            st.session_state.smoke_scope_mode = "Chạy toàn bộ testcase"

        if "smoke_testcase_feature_choice" not in st.session_state:
            st.session_state.smoke_testcase_feature_choice = "(Tất cả Features)"
        if "smoke_testcase_item_choice" not in st.session_state:
            st.session_state.smoke_testcase_item_choice = "Tất cả Testcase"
        if "smoke_feature_only_choice" not in st.session_state:
            st.session_state.smoke_feature_only_choice = ""

        # Parse CSV once for dropdown options (runs on every rerun)
        df_for_dropdowns = None
        try:
            df_for_dropdowns = _parse_smoke_csv(st.session_state.smoke_selected_csv)
            df_for_dropdowns = _normalize_smoke_features(df_for_dropdowns)
        except Exception as e:
            st.warning(f"Không đọc được CSV để tạo dropdown: {str(e)[:200]}")

        smoke_scope_mode = st.radio(
            "Chọn phạm vi Smoke",
            [
                "Chạy toàn bộ testcase",
                "Chạy theo testcase (Feature + Testcase)",
                "Chạy theo feature (bỏ qua testcase)",
            ],
            index=(
                [
                    "Chạy toàn bộ testcase",
                    "Chạy theo testcase (Feature + Testcase)",
                    "Chạy theo feature (bỏ qua testcase)",
                ].index(st.session_state.smoke_scope_mode)
                if st.session_state.smoke_scope_mode
                in [
                    "Chạy toàn bộ testcase",
                    "Chạy theo testcase (Feature + Testcase)",
                    "Chạy theo feature (bỏ qua testcase)",
                ]
                else 0
            ),
            key="smoke_scope_mode",
            horizontal=False,
        )

        # Build Feature options (preserve order)
        features_order: list[str] = []
        if df_for_dropdowns is not None and "Features" in df_for_dropdowns.columns:
            seen_features: set[str] = set()
            for f in df_for_dropdowns["Features"].astype(str).tolist():
                f2 = (f or "").strip()
                if f2 and f2 not in seen_features:
                    seen_features.add(f2)
                    features_order.append(f2)

        if smoke_scope_mode == "Chạy theo testcase (Feature + Testcase)":
            feature_options = ["(Tất cả Features)"] + features_order
            cur_feature = st.session_state.smoke_testcase_feature_choice
            if cur_feature not in feature_options:
                cur_feature = "(Tất cả Features)"
                st.session_state.smoke_testcase_feature_choice = cur_feature

            st.selectbox(
                "Chọn Feature",
                options=feature_options,
                index=feature_options.index(cur_feature),
                key="smoke_testcase_feature_choice",
            )

            selected_feature_value = (
                None
                if st.session_state.smoke_testcase_feature_choice == "(Tất cả Features)"
                else st.session_state.smoke_testcase_feature_choice
            )

            testcase_display_options = ["Tất cả Testcase"]
            display_to_value: dict[str, str] = {}
            if df_for_dropdowns is not None:
                testcase_display_options, display_to_value = _build_smoke_dropdowns(
                    df_for_dropdowns, selected_feature_value
                )

            cur_case = st.session_state.smoke_testcase_item_choice
            if cur_case not in testcase_display_options:
                cur_case = "Tất cả Testcase"
                if (
                    cur_case not in testcase_display_options
                    and testcase_display_options
                ):
                    cur_case = testcase_display_options[0]
                st.session_state.smoke_testcase_item_choice = cur_case

            st.selectbox(
                "Chọn Testcase",
                options=testcase_display_options,
                index=(
                    testcase_display_options.index(cur_case)
                    if cur_case in testcase_display_options
                    else 0
                ),
                key="smoke_testcase_item_choice",
            )

            # keep in session_state for run-time mapping (not strictly required)
            st.session_state.smoke_testcase_display_to_value = display_to_value

        elif smoke_scope_mode == "Chạy theo feature (bỏ qua testcase)":
            if not features_order:
                features_order = ["(Trống)"]

            cur_feature = st.session_state.smoke_feature_only_choice
            if cur_feature not in features_order:
                cur_feature = features_order[0]
                st.session_state.smoke_feature_only_choice = cur_feature

            st.selectbox(
                "Chọn Feature",
                options=features_order,
                index=features_order.index(cur_feature),
                key="smoke_feature_only_choice",
            )

        smoke_limit = st.number_input(
            "Giới hạn số case (0 = chạy hết)",
            min_value=0,
            max_value=10000,
            value=0,
            step=1,
            key="smoke_limit",
            help="Nếu bạn muốn smoke nhanh, set ví dụ 10/20.",
        )

        smoke_run_btn = st.button(
            "🚀 Chạy Smoke Brick Live",
            type="primary",
            width='stretch',
        )

        # === Golden plan cache controls ===
        st.checkbox(
            "♻️ Dùng Golden Plan cache (bỏ qua AI cho case đã PASS)",
            key="smoke_use_golden",
            help=(
                "Case nào chạy PASS hoàn toàn sẽ được lưu lại plan. Lần sau chạy thẳng "
                "plan đó (chỉ thay ID động), không cần AI sinh lại → nhanh & ổn định. "
                "Nếu replay fail thì tự huỷ cache và nhờ AI sinh lại."
            ),
        )
        _golden_n = plan_cache.golden_count()
        _gc1, _gc2 = st.columns([3, 2])
        with _gc1:
            st.caption(f"💾 Đã lưu {_golden_n} golden plan")
        with _gc2:
            if st.button("🗑 Xoá golden", width='stretch', disabled=_golden_n == 0):
                removed = plan_cache.clear_all()
                st.success(f"Đã xoá {removed} golden plan.")
                st.rerun()

        st.checkbox(
            "🤖 Dùng Claude Haiku thay Qwen (khi không có golden)",
            key="smoke_use_claude_haiku",
            help=(
                "Khi không có golden plan, dùng Claude Haiku (Anthropic API) để sinh "
                "action plan thay vì Qwen3 qua Ollama. Chính xác hơn với các "
                "lệnh phức tạp, nhưng cần ANTHROPIC_API_KEY trong .env. Tự fallback "
                "về Qwen nếu Claude lỗi hoặc thiếu API key."
            ),
        )

with col2:
    st.subheader("📂 Kịch bản đã lưu")
    saved_scenarios = load_scenarios()
    if saved_scenarios:
        scenario_names = list(saved_scenarios.keys())
        st.selectbox("Chọn kịch bản:", scenario_names, key="selected_file")
        st.button(
            "📂 Load Kịch Bản",
            width='stretch',
            on_click=load_scenario_callback,
        )

        st.divider()
        st.markdown("**🗑 Xóa kịch bản cũ**")
        st.caption("Chọn các kịch bản không còn dùng rồi bấm xóa.")
        scenarios_to_delete = st.multiselect(
            "Kịch bản cần xóa:",
            options=scenario_names,
            placeholder="Chọn một hoặc nhiều kịch bản...",
            key="scenarios_to_delete",
            label_visibility="collapsed",
        )
        delete_btn = st.button(
            "🗑 Xóa kịch bản đã chọn",
            width='stretch',
            disabled=not scenarios_to_delete,
        )
        if delete_btn and scenarios_to_delete:
            st.session_state.pending_delete_dialog = list(scenarios_to_delete)
            st.rerun()
    else:
        st.info("Chưa có kịch bản nào.")

# --- HIỂN THỊ JSON PLAN ---
if st.session_state.current_plan:
    st.divider()
    st.subheader("📋 Kế hoạch hành động (JSON):")

    st.metric("Số bước", len(st.session_state.current_plan))

    st.json(st.session_state.current_plan)


# --- HELPER: Streaming stdout logs to Streamlit ---
class StreamingLogCapture:
    """Capture stdout and stream it to a Streamlit container in real-time"""

    def __init__(self, st_container):
        self.buffer = io.StringIO()
        self.original_stdout = None
        self.st_container = st_container

    def __enter__(self):
        self.original_stdout = sys.stdout
        sys.stdout = self
        return self

    def __exit__(self, *args):
        sys.stdout = self.original_stdout

    def write(self, text):
        if self.original_stdout:
            self.original_stdout.write(text)
        self.buffer.write(text)
        # Update Streamlit element in real-time
        current = self.buffer.getvalue()
        if current.strip():
            self.st_container.code(current, language="text")

    def flush(self):
        if self.original_stdout:
            self.original_stdout.flush()

    def getvalue(self):
        return self.buffer.getvalue()


# --- XỬ LÝ SỰ KIỆN CHẠY (AI BRAIN) ---
if st.session_state.run_mode == "AI Run (theo lệnh)" and run_btn and user_input:
    with st.status("🧠 AI đang suy nghĩ...", expanded=True) as status:
        # Placeholder cho real-time logs
        log_placeholder = st.empty()

        # --- Golden Plan Cache: lookup trước khi gọi AI ---
        raw_input = user_input  # giữ nguyên để làm golden key (ổn định qua các lần chạy)
        _unique_id_airun = _pregenerate_unique_id(raw_input)
        _processed_input, _last_id_airun = _substitute_last_clone_id(
            raw_input,
            st.session_state.smoke_last_created_id_by_feature,
        )

        # Lưu vào session state để Phase 2 (execute) dùng sau rerun
        st.session_state.airun_raw_input = raw_input
        st.session_state.airun_generated_unique_id = _unique_id_airun
        st.session_state.airun_last_id = _last_id_airun

        _airun_golden_used = False
        action_plan = None
        if st.session_state.get("airun_use_golden", True):
            action_plan = plan_cache.get_golden_plan(
                "manual", raw_input, _unique_id_airun, _last_id_airun
            )
            if action_plan is not None:
                _airun_golden_used = True
                print(f"   ⚡ AI Run golden hit ({len(action_plan)} steps) — bỏ qua AI")

        if not _airun_golden_used:
            # Nếu đã pre-generate unique ID, thêm constraint vào command cho AI
            if _unique_id_airun:
                import re as _re_uid
                _pfix_m = _re_uid.search(r"bắt\s+đầu\s+bằng\s+(\S+)", _processed_input, _re_uid.IGNORECASE)
                _pfix = _re_uid.sub(r"[.,;:]*$", "", _pfix_m.group(1)).strip() if _pfix_m else "hieunm_test"
                _processed_input = (
                    f"{_processed_input}\n\nYêu cầu: Với các bước CREATE hoặc CLONE, hãy tạo/điền ID duy nhất "
                    f"bắt đầu bằng '{_pfix}' và sử dụng đúng giá trị sau: {_unique_id_airun}. "
                    f"Nếu có chỗ yêu cầu nhập '... ID ...' thì hãy thay bằng {_unique_id_airun}."
                )

            # Gọi AI với streaming log
            with StreamingLogCapture(log_placeholder) as ai_log:
                action_plan = parse_command_to_json(
                    _processed_input,
                    use_fast_mode=not st.session_state.get("airun_use_claude_careful", False),
                    context_plan=st.session_state.loaded_scenario_plan,
                    base_command=st.session_state.loaded_scenario_command,
                    forced_unique_id=_unique_id_airun,
                )

        # Lưu kết quả
        st.session_state.current_plan = action_plan
        st.session_state.airun_golden_used = _airun_golden_used
        st.session_state.run_execution = True
        st.session_state.test_logs = []

        # Lưu mode đã dùng (đọc từ brain module - phản ánh mode thực tế sau auto-switch)
        if not _airun_golden_used:
            st.session_state.last_mode_used = brain_module.last_actual_mode

        _label = "⚡ Golden plan loaded!" if _airun_golden_used else "✅ AI đã phân tích xong!"
        status.update(label=_label, state="complete", expanded=False)

    st.rerun()

# --- XỬ LÝ SỰ KIỆN THỰC THI (ROBOT ACTION) ---
if st.session_state.run_execution and st.session_state.current_plan:
    with st.status("🤖 AI đang thực thi...", expanded=True) as status:
        # Placeholder cho real-time logs
        exec_log_placeholder = st.empty()

        # Capture execution logs with streaming
        with StreamingLogCapture(exec_log_placeholder) as exec_log:
            logs = automation.execute_action(st.session_state.current_plan)

        st.session_state.test_logs = logs

        # --- Golden Plan Cache: ghi nhận kết quả sau chạy (chỉ AI Run mode) ---
        if st.session_state.run_mode == "AI Run (theo lệnh)":
            _ar_raw = st.session_state.get("airun_raw_input")
            _ar_golden_used = st.session_state.get("airun_golden_used", False)
            _ar_unique_id = st.session_state.get("airun_generated_unique_id")
            _ar_last_id = st.session_state.get("airun_last_id")
            if _ar_raw:
                _ar_status, _ = _extract_smoke_status_from_logs(logs)
                if _ar_status == "PASS" and not _ar_golden_used:
                    if plan_cache.record_success(
                        "manual", _ar_raw, st.session_state.current_plan,
                        _ar_unique_id, _ar_last_id,
                    ):
                        print(f"   💾 AI Run golden saved: {_ar_raw[:60]}")
                elif _ar_golden_used and _ar_status in {"FAIL", "CRASH"}:
                    plan_cache.invalidate("manual", _ar_raw)
                    print(f"   ♻️ AI Run golden {_ar_status} → huỷ cache (lần sau AI sinh lại)")

        status.update(label="✅ Hoàn thành!", state="complete", expanded=False)

    st.session_state.run_execution = False
    st.rerun()


# --- DEPLOY CONFIRM WAITING ---
if st.session_state.get("smoke_waiting_for_deploy", False):
    deploy_info = st.session_state.get("smoke_deploy_info", {})
    _dep_feature = deploy_info.get("feature", "")
    _dep_case = deploy_info.get("case", "")
    _dep_next = deploy_info.get("next_idx", 0)
    _dep_total = st.session_state.get("smoke_total_cases", 0)

    st.warning(
        f"⏸️ **Automation đang tạm dừng — Đang chờ bạn kiểm tra Deploy**\n\n"
        f"**Feature:** {_dep_feature}  \n"
        f"**Case vừa chạy:** {_dep_case}  \n\n"
        f"Hệ thống đã bấm **Process**. Vui lòng kiểm tra diff trên trình duyệt và "
        f"xác nhận deploy hoàn tất, sau đó bấm nút bên dưới để tiếp tục.  \n\n"
        f"*({_dep_next}/{_dep_total} cases đã xong)*"
    )
    if st.button("▶️ Deploy xong, tiếp tục chạy", type="primary", width='stretch'):
        st.session_state.smoke_waiting_for_deploy = False
        st.rerun()


# --- KHỞI TẠO SMOKE BRICK LIVE (khi bấm nút Run) ---
if st.session_state.run_mode == "Smoke Brick Live (theo CSV)" and smoke_run_btn:
    st.session_state.test_logs = []
    st.session_state.smoke_results = []
    st.session_state.smoke_last_summary = None

    if not st.session_state.smoke_selected_csv:
        st.error("Vui lòng chọn CSV cho Smoke Brick Live.")
        st.stop()

    df_in = _parse_smoke_csv(st.session_state.smoke_selected_csv)
    df_in["Features"] = (
        df_in["Features"].replace("", pd.NA).ffill().fillna("").astype(str)
    )

    # === Apply smoke filtering based on UI selection ===
    smoke_scope_mode = st.session_state.get("smoke_scope_mode", "Chạy toàn bộ testcase")

    if smoke_scope_mode == "Chạy theo feature (bỏ qua testcase)":
        feature_choice = st.session_state.get("smoke_feature_only_choice", "")
        feature_choice = str(feature_choice or "").strip()
        if feature_choice and feature_choice != "(Trống)":
            df_in = df_in[df_in["Features"].astype(str).eq(feature_choice)].copy()

    elif smoke_scope_mode == "Chạy theo testcase (Feature + Testcase)":
        feature_choice = st.session_state.get(
            "smoke_testcase_feature_choice", "(Tất cả Features)"
        )
        feature_choice = str(feature_choice or "").strip()
        if feature_choice and feature_choice != "(Tất cả Features)":
            df_in = df_in[df_in["Features"].astype(str).eq(feature_choice)].copy()

        testcase_choice_display = st.session_state.get(
            "smoke_testcase_item_choice", "Tất cả Testcase"
        )
        testcase_choice_display = str(testcase_choice_display or "").strip()
        if testcase_choice_display and testcase_choice_display != "Tất cả Testcase":
            display_to_value = st.session_state.get("smoke_testcase_display_to_value")
            raw_testcase_value = None
            if isinstance(display_to_value, dict):
                raw_testcase_value = display_to_value.get(testcase_choice_display)
            if not raw_testcase_value:
                try:
                    _opts, _map = _build_smoke_dropdowns(df_in, None)
                    raw_testcase_value = _map.get(testcase_choice_display)
                except Exception:
                    raw_testcase_value = None
            if raw_testcase_value:
                df_in = df_in[
                    df_in["Testcase"]
                    .astype(str)
                    .str.strip()
                    .eq(str(raw_testcase_value).strip())
                ].copy()

    if st.session_state.smoke_limit and int(st.session_state.smoke_limit) > 0:
        df_in = df_in.iloc[: int(st.session_state.smoke_limit)].copy()

    df_in = df_in.reset_index(drop=True)
    total_cases = len(df_in)

    st.session_state.smoke_running = True
    st.session_state.smoke_current_idx = 0
    st.session_state.smoke_total_cases = total_cases
    st.session_state.smoke_df_csv = df_in.to_csv(index=False)
    st.session_state.smoke_waiting_for_deploy = False
    st.session_state.smoke_deploy_info = {}

    st.info(f"Smoke Brick Live: chạy {total_cases} case từ CSV.")
    st.rerun()


# --- CHẠY SMOKE BRICK LIVE (loop từng case, hỗ trợ resume sau deploy) ---
if st.session_state.get("smoke_running", False) and not st.session_state.get("smoke_waiting_for_deploy", False):
    if not st.session_state.get("smoke_df_csv"):
        st.session_state.smoke_running = False
    else:
        df_in = pd.read_csv(
            io.StringIO(st.session_state.smoke_df_csv),
            dtype=str,
            keep_default_na=False,
        ).fillna("")
        total_cases = st.session_state.smoke_total_cases
        start_idx = st.session_state.smoke_current_idx
        smoke_records = list(st.session_state.smoke_results)

        progress = st.progress(start_idx / total_cases if total_cases > 0 else 0)
        current_status_box = st.empty()
        live_table_box = st.empty()

        if smoke_records:
            live_table_box.dataframe(
                pd.DataFrame(smoke_records), width='stretch', hide_index=True
            )

        for idx in range(start_idx, total_cases):
            row = df_in.iloc[idx]
            feature = str(row.get("Features", "") or "").strip()
            testcase = str(row.get("Testcase", "") or "").strip()

            if not testcase:
                smoke_records.append(
                    {"Features": feature, "Testcase": testcase, "Result": "SKIPPED", "Note": "Empty testcase"}
                )
                st.session_state.smoke_results = smoke_records
                progress.progress((idx + 1) / total_cases)
                live_table_box.dataframe(pd.DataFrame(smoke_records), width='stretch', hide_index=True)
                continue

            label, steps = _split_testcase_label_and_steps(testcase)
            display_case = label if label else testcase
            exec_steps = steps if steps else testcase

            current_status_box.markdown(
                f"**Case {idx+1}/{total_cases}**  \n"
                f"- Feature: `{feature}`  \n"
                f"- Testcase: `{display_case}`"
            )

            if steps:
                # IMPORTANT: do NOT prepend `label` to the command sent to the AI.
                # CSV format is "<label>: <steps>" where label is a human-readable
                # title (e.g. "Import the Gacha Pool CSV") meant only for the UI
                # dropdown/status display. Titles are almost always imperative verb
                # phrases ("Import ...", "Clone ...", "Edit ..."), so when prepended
                # they read just like another "-> step" to the LLM — it then
                # hallucinates a SPURIOUS extra action from the title itself (e.g. an
                # "upload: Gacha Pool CSV" step right after navigate, before the real
                # upload step later in `steps`), which fails at runtime ("Button not
                # found") and marks the whole case FAIL even though every real step
                # passed. `exec_steps` already starts with its own "Vào ..." navigate,
                # so nothing is lost by dropping the label here.
                case_command = exec_steps
            else:
                case_command = _build_case_command(feature, exec_steps)

            generated_unique_id = None
            if _should_force_unique_id(label, testcase):
                import datetime as _dt_uid, uuid as _uuid_uid
                # Extract the actual prefix from "bắt đầu bằng X" in the command so the
                # injected ID respects feature-specific prefixes (e.g. LTPVE_hieunm_test,
                # FightCard_hieunm_test) instead of always forcing plain "hieunm_test".
                _pfix_m = re.search(r"bắt\s+đầu\s+bằng\s+(\S+)", case_command, re.IGNORECASE)
                if _pfix_m:
                    _pfix = re.sub(r"[.,;:]*$", "", _pfix_m.group(1)).strip()
                else:
                    _pfix = "hieunm_test"
                _ts_uid = _dt_uid.datetime.now().strftime("%Y%m%d_%H%M%S")
                _rnd_uid = _uuid_uid.uuid4().hex[:6]
                unique_id = f"{_pfix}_{_ts_uid}_{_rnd_uid}"
                generated_unique_id = unique_id
                case_command = (
                    f"{case_command}\n\n"
                    f"Yêu cầu: Với các bước CREATE hoặc CLONE, hãy tạo/điền ID duy nhất "
                    f"bắt đầu bằng '{_pfix}' và sử dụng đúng giá trị sau: {unique_id}. "
                    f"Nếu có chỗ yêu cầu nhập '... ID ...' thì hãy thay bằng {unique_id}."
                )

            feature_key = str(feature).strip()
            # Prefer a more specific sub-feature key over the CSV feature column.
            # E.g. "Edit an Offer Section" is under CSV feature "Offer" (because the
            # CSV Features column is blank and forward-filled), but the correct last ID
            # lives under the "Offer Section" key in smoke_last_ids.json.
            # MATCH ONLY in the NAVIGATION scope — look for "Vào <key>" pattern in the
            # testcase text. Matching anywhere in the full case_command is wrong: e.g.
            # "Edit an Offer" contains "Offer Section: ..." as a FORM FIELD VALUE, which
            # would incorrectly override feature_key to "Offer Section" and pull the wrong ID.
            _ids_dict = st.session_state.smoke_last_created_id_by_feature
            _best_key = feature_key
            # Navigation scope: steps that start with "Vào" carry the actual feature target.
            # Build a lightweight search string from "Vào X" substrings only.
            _nav_scope = " ".join(
                m.group(0) for m in re.finditer(r"vào\s+\S+(?:\s+\S+){0,3}", case_command, re.IGNORECASE)
            ).lower()
            for _k in _ids_dict:
                if (
                    len(_k) > len(_best_key)
                    and _k.lower() in _nav_scope
                    and _ids_dict[_k]
                ):
                    _best_key = _k
            if _best_key != feature_key:
                print(f"   🔁 Sub-feature override: '{feature_key}' → '{_best_key}' (nav-scope match)")
                feature_key = _best_key
            _raw_id = _ids_dict.get(feature_key)
            if isinstance(_raw_id, list):
                last_created_id = _raw_id[-1] if _raw_id else None
            else:
                last_created_id = _raw_id

            if last_created_id:
                case_command = re.sub(r"Sửa\s+ID\s+bất\s+kỳ", f"Sửa ID: {last_created_id}", case_command, flags=re.IGNORECASE)
                # NOTE: "Filter một ID bất kỳ" means "filter any random ID" → do NOT replace with last_created_id

            # "X vừa clone/tạo" can reference a DIFFERENT feature than feature_key within
            # the SAME testcase, e.g. "Vào Fight Card V3 -> Sửa ID vừa clone -> ... -> Sửa
            # RBE Event: Hãy lấy ID RBE vừa clone ... -> Vào RBE -> Sửa ID vừa clone".
            # Blanket-substituting every occurrence with the single feature_key-based
            # last_created_id would wrongly reuse the Fight Card ID for the RBE
            # occurrences too. _substitute_last_clone_id resolves each occurrence
            # independently by its nearest preceding feature keyword.
            case_command, _vua_clone_id = _substitute_last_clone_id(
                case_command, st.session_state.smoke_last_created_id_by_feature
            )

            _vua_pattern = r"[^\s]*\s*v[uưừữ]a\s+(clone|tạo)"
            if not _vua_clone_id and re.search(_vua_pattern, case_command, re.IGNORECASE):
                note = f"Skipped: no last_created_id for feature '{feature_key}' (no prior clone/create passed)"
                print(f"   ⏭️ {note}")
                smoke_records.append({"Features": feature, "Testcase": display_case, "Result": "SKIPPED", "Note": note})
                st.session_state.smoke_results = smoke_records
                progress.progress((idx + 1) / total_cases)
                live_table_box.dataframe(pd.DataFrame(smoke_records), width='stretch', hide_index=True)
                continue

            golden_used = False
            try:
                _golden_plan = None
                if st.session_state.get("smoke_use_golden", True):
                    _golden_plan = plan_cache.get_golden_plan(
                        feature, testcase, generated_unique_id, last_created_id
                    )

                if _golden_plan is not None:
                    action_plan = _golden_plan
                    golden_used = True
                    print(f"   ⚡ Golden plan hit ({len(action_plan)} steps) — bỏ qua AI")
                else:
                    _smoke_use_haiku = st.session_state.get("smoke_use_claude_haiku", False)
                    _smoke_mode_label = "Claude Haiku" if _smoke_use_haiku else "Qwen (Fast)"
                    with st.status(f"🧠 AI đang phân tích ({_smoke_mode_label})...", expanded=False):
                        action_plan = parse_command_to_json(
                            case_command,
                            use_fast_mode=not _smoke_use_haiku,
                            context_plan=None,
                            base_command=None,
                            forced_unique_id=generated_unique_id,
                        )

                if not action_plan:
                    smoke_records.append({"Features": feature, "Testcase": display_case, "Result": "FAIL", "Note": "Empty action plan (AI returned no steps)"})
                    st.session_state.smoke_results = smoke_records
                    progress.progress((idx + 1) / total_cases)
                    live_table_box.dataframe(pd.DataFrame(smoke_records), width='stretch', hide_index=True)
                    continue
            except Exception as e:
                smoke_records.append({"Features": feature, "Testcase": display_case, "Result": "CRASH", "Note": f"AI parse crashed: {str(e)[:250]}"})
                st.session_state.smoke_results = smoke_records
                progress.progress((idx + 1) / total_cases)
                live_table_box.dataframe(pd.DataFrame(smoke_records), width='stretch', hide_index=True)
                continue

            try:
                exec_log_placeholder = st.empty()
                with st.status("🤖 Automation đang chạy...", expanded=False):
                    with StreamingLogCapture(exec_log_placeholder) as exec_log:
                        logs = automation.execute_action(action_plan)

                status_str, note_detail = _extract_smoke_status_from_logs(logs)

                # === Golden plan cache ===
                # Lưu khi PASS sạch (case chưa dùng golden). Nếu đang replay golden mà
                # FAIL/CRASH (UI drift / row bị xoá) → huỷ golden + nhờ AI sinh lại ngay
                # trong cùng lần chạy (self-heal). WARNING vẫn giữ golden, không thrash.
                if status_str == "PASS" and not golden_used:
                    if plan_cache.record_success(
                        feature, testcase, action_plan,
                        generated_unique_id, last_created_id, label=display_case,
                    ):
                        print(f"   💾 Golden saved: {display_case[:60]}")
                elif golden_used and status_str in {"FAIL", "CRASH"}:
                    print(f"   ♻️ Golden replay {status_str} → huỷ cache + retry bằng AI")
                    plan_cache.invalidate(feature, testcase)
                    try:
                        _smoke_use_haiku = st.session_state.get("smoke_use_claude_haiku", False)
                        _smoke_mode_label = "Claude Haiku" if _smoke_use_haiku else "Qwen (Fast)"
                        with st.status(f"🧠 AI retry ({_smoke_mode_label}, golden fail)...", expanded=False):
                            action_plan = parse_command_to_json(
                                case_command,
                                use_fast_mode=not _smoke_use_haiku,
                                context_plan=None,
                                base_command=None,
                                forced_unique_id=generated_unique_id,
                            )
                        if action_plan:
                            with st.status("🤖 Automation retry...", expanded=False):
                                with StreamingLogCapture(exec_log_placeholder) as exec_log:
                                    logs = automation.execute_action(action_plan)
                            status_str, note_detail = _extract_smoke_status_from_logs(logs)
                            if status_str == "PASS":
                                plan_cache.record_success(
                                    feature, testcase, action_plan,
                                    generated_unique_id, last_created_id, label=display_case,
                                )
                                print(f"   💾 Golden re-saved sau AI retry: {display_case[:60]}")
                        else:
                            status_str, note_detail = "FAIL", "Golden fail + AI retry trả về plan rỗng"
                    except Exception as _retry_e:
                        status_str, note_detail = "CRASH", f"AI retry crashed: {str(_retry_e)[:200]}"

                if feature and str(status_str).strip().upper() in {"PASS", "WARNING"}:
                    # Prefer the ID actually filled in the form (from action_plan update_form data)
                    # over the pre-generated generic ID.  This handles cases where _inject_generated_ids
                    # in brain.py created a feature-prefixed ID (e.g. LTPVE_hieunm_test_*) that
                    # differs from the generic hieunm_test_* produced by _make_unique_hieunm_test_id.
                    actual_id = _extract_id_from_plan(action_plan, feature_key)
                    id_to_save = actual_id or generated_unique_id
                    if id_to_save:
                        # Reload from disk first so we don't overwrite IDs written by
                        # _persist_clone_id (core.py) during execution.
                        _fresh = _load_smoke_ids()
                        _existing = _fresh.get(feature_key, [])
                        if isinstance(_existing, str):
                            _existing = [_existing] if _existing else []
                        if id_to_save not in _existing:
                            _existing.append(id_to_save)
                        st.session_state.smoke_last_created_id_by_feature[feature_key] = _existing
                        _save_smoke_ids(st.session_state.smoke_last_created_id_by_feature)
                        _src = "plan" if actual_id else "pre-gen"
                        print(f"   🧠 Smoke: saved smoke_last_created_id_by_feature[{feature_key}]={_existing} (status={status_str}, src={_src})")

                smoke_records.append({"Features": feature, "Testcase": display_case, "Result": status_str, "Note": note_detail})
            except Exception as e:
                smoke_records.append({"Features": feature, "Testcase": display_case, "Result": "CRASH", "Note": f"Automation crashed: {str(e)[:250]}"})

            st.session_state.smoke_results = smoke_records
            progress.progress((idx + 1) / total_cases)
            live_table_box.dataframe(pd.DataFrame(smoke_records), width='stretch', hide_index=True)

            # Sau mỗi deploy case: dừng lại chờ user kiểm tra diff
            if _is_deploy_case(label, steps):
                st.session_state.smoke_current_idx = idx + 1
                st.session_state.smoke_waiting_for_deploy = True
                st.session_state.smoke_deploy_info = {
                    "feature": feature,
                    "case": label or display_case,
                    "next_idx": idx + 1,
                }
                st.rerun()

        # Tất cả cases xong
        st.session_state.smoke_running = False
        st.session_state.smoke_current_idx = 0

        try:
            import datetime as _dt
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_name = f"{SMOKE_OUTPUT_PREFIX}{ts}.csv"
            df_out = pd.DataFrame(smoke_records)
            buf = io.BytesIO()
            df_out.to_csv(buf, index=False, encoding="utf-8-sig")
            output_bytes = buf.getvalue()
            st.session_state.smoke_last_summary = {
                "output_bytes": output_bytes,
                "file_name": out_name,
                "total_cases": total_cases,
            }
        except Exception as e:
            st.session_state.smoke_last_summary = {
                "output_bytes": None,
                "file_name": None,
                "total_cases": total_cases,
                "save_error": str(e)[:200],
            }

        st.success("✅ Smoke Brick Live finished!")
        st.session_state.smoke_results = smoke_records
        st.rerun()

# --- HIỂN THỊ BẢNG KẾT QUẢ SMOKE BRICK LIVE ---
if (
    st.session_state.run_mode == "Smoke Brick Live (theo CSV)"
    and st.session_state.smoke_results
):
    st.subheader("🔥 Smoke Brick Live — Báo cáo theo Feature & Case")
    try:
        df_smoke = pd.DataFrame(st.session_state.smoke_results)

        # Guard: DataFrame phải có cột cần thiết
        if "Features" not in df_smoke.columns:
            df_smoke["Features"] = ""
        if "Testcase" not in df_smoke.columns:
            df_smoke["Testcase"] = ""
        if "Result" not in df_smoke.columns:
            df_smoke["Result"] = ""

        # === Overview metrics ===
        status_col = "Result"
        total = len(df_smoke)
        pass_count = df_smoke[status_col].astype(str).str.upper().eq("PASS").sum()
        fail_count = (
            df_smoke[status_col].astype(str).str.upper().isin(["FAIL", "CRASH"]).sum()
        )
        warning_count = df_smoke[status_col].astype(str).str.upper().eq("WARNING").sum()
        crash_count = df_smoke[status_col].astype(str).str.upper().eq("CRASH").sum()

        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        with col_stat1:
            st.metric("Tổng số case", total)
        with col_stat2:
            st.metric("✅ PASS", pass_count)
        with col_stat3:
            st.metric("❌ FAIL/CRASH", fail_count)
        with col_stat4:
            st.metric("⚠️ WARNING", warning_count)

        if crash_count > 0:
            st.error(f"🚨 Có {crash_count} case bị CRASH.")

        # === Overall table (case-level) ===
        def color_highlight_smoke(val):
            v = str(val).upper()
            if v == "PASS":
                color = "#28a745"
            elif v == "WARNING":
                color = "#ff8c00"
            elif v in ["FAIL", "CRASH"]:
                color = "#dc3545"
            elif v == "SKIPPED":
                color = "#6c757d"
            else:
                color = "black"
            return f"color: {color}; font-weight: bold"

        st.markdown("**📌 Danh sách case (giao diện bảng):**")
        target_col = "Result"
        st.dataframe(
            df_smoke.style.map(color_highlight_smoke, subset=[target_col]),
            width='stretch',
            hide_index=True,
        )

        # === Feature summary + per-feature breakdown ===
        st.divider()
        st.markdown("**📦 Breakdown theo Feature:**")

        # Normalize sort by the first appearance order
        feature_order = []
        seen = set()
        for f in df_smoke["Features"].astype(str).tolist():
            f2 = (f or "").strip()
            if f2 and f2 not in seen:
                seen.add(f2)
                feature_order.append(f2)

        # Fallback if empty order
        if not feature_order:
            feature_order = sorted(df_smoke["Features"].astype(str).unique().tolist())

        for feature in feature_order:
            df_f = df_smoke[df_smoke["Features"].astype(str).eq(feature)]
            if df_f.empty:
                continue

            pass_f = df_f["Result"].astype(str).str.upper().eq("PASS").sum()
            warning_f = df_f["Result"].astype(str).str.upper().eq("WARNING").sum()
            fail_f = (
                df_f["Result"].astype(str).str.upper().isin(["FAIL", "CRASH"]).sum()
            )
            total_f = len(df_f)

            with st.expander(
                f"Feature: {feature}  —  {pass_f} PASS / {warning_f} WARNING / {fail_f} FAIL+CRASH  (total {total_f})"
            ):
                st.dataframe(
                    df_f[["Testcase", "Result", "Note"]].style.map(
                        color_highlight_smoke, subset=["Result"]
                    ),
                    width='stretch',
                    hide_index=True,
                )

        # === Download report CSV (IN-MEMORY) ===
        out_bytes = (
            st.session_state.smoke_last_summary.get("output_bytes")
            if st.session_state.smoke_last_summary
            else None
        )
        out_name = (
            st.session_state.smoke_last_summary.get("file_name")
            if st.session_state.smoke_last_summary
            else None
        )

        if out_bytes and out_name:
            st.download_button(
                label="⬇️ Tải Smoke report CSV",
                data=out_bytes,
                file_name=os.path.basename(out_name),
                mime="text/csv",
                width='stretch',
            )

    except Exception as e:
        st.error(f"Lỗi hiển thị Smoke report: {e}")

# --- HIỂN THỊ BẢNG KẾT QUẢ AI RUN ---
if st.session_state.test_logs:
    st.subheader("📊 Kết quả chi tiết")
    report_logs = st.session_state.test_logs

    try:
        df_log = pd.DataFrame(report_logs)

        # Tô màu
        def color_highlight(val):
            v_lower = str(val).lower()
            if "pass" in v_lower:
                color = "#28a745"
            elif "warning" in v_lower:
                color = (
                    "#ff8c00"  # Orange cho WARNING (dữ liệu không hợp lệ bị chấp nhận)
                )
            elif "fail" in v_lower or "crash" in v_lower:
                color = "#dc3545"
            else:
                color = "black"
            return f"color: {color}; font-weight: bold"

        target_col = "result" if "result" in df_log.columns else "status"

        if not df_log.empty and target_col in df_log.columns:
            st.dataframe(
                df_log.style.map(color_highlight, subset=[target_col]),
                width='stretch',
            )

            # === THỐNG KÊ ===
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)

            total = len(df_log)
            pass_count = (
                df_log[target_col].astype(str).str.lower().str.contains("pass").sum()
            )
            fail_count = (
                df_log[target_col]
                .astype(str)
                .str.lower()
                .str.contains("fail|crash")
                .sum()
            )
            warning_count = (
                df_log[target_col].astype(str).str.lower().str.contains("warning").sum()
            )

            with col_stat1:
                st.metric("Tổng số bước", total)
            with col_stat2:
                st.metric(
                    "✅ PASS",
                    pass_count,
                    delta=f"{pass_count/total*100:.1f}%" if total > 0 else "0%",
                )
            with col_stat3:
                st.metric(
                    "❌ FAIL",
                    fail_count,
                    delta=f"-{fail_count/total*100:.1f}%" if total > 0 else "0%",
                    delta_color="inverse",
                )
            with col_stat4:
                st.metric(
                    "⚠️ WARNING",
                    warning_count,
                    delta=f"{warning_count/total*100:.1f}%" if total > 0 else "0%",
                    delta_color="inverse",
                )

            # Hiển thị cảnh báo nổi bật nếu có WARNING
            if warning_count > 0:
                st.error(
                    f"🚨 CẢNH BÁO BẢO MẬT: {warning_count} test case với dữ liệu không hợp lệ đã bị hệ thống CHẤP NHẬN! "
                    f"Vui lòng kiểm tra các dòng có status WARNING bên dưới."
                )
        else:
            st.dataframe(df_log, width='stretch')

    except Exception as e:
        st.error(f"Lỗi hiển thị bảng: {e}")
        st.write(report_logs)

# --- XỬ LÝ SỰ KIỆN LƯU ---
if save_btn:
    if not save_name.strip():
        st.toast("Vui lòng nhập tên kịch bản.", icon="⚠️")
    elif not st.session_state.current_plan:
        st.toast("Chưa có kế hoạch JSON để lưu. Hãy chạy AI trước.", icon="⚠️")
    else:
        save_scenario(
            save_name.strip(),
            st.session_state.current_plan,
            user_input,
        )
        st.session_state.pending_save_dialog = save_name.strip()
        st.toast(f"Đã lưu kịch bản 「{save_name.strip()}」", icon="💾")
        st.rerun()

# --- FOOTER ---
st.divider()
st.markdown(
    """
<div style='text-align: center; color: #666; font-size: 12px;'>
    <p>💡 <b>Pro Tips:</b></p>
    <ul style='list-style: none; padding: 0;'>
        <li>🔹 Mô tả lệnh chi tiết, rõ ràng để AI generate đúng steps</li>
        <li>🔹 Dùng Golden Plan Cache để bỏ qua AI với các case đã chạy PASS</li>
        <li>🔹 Nếu AI hiểu sai → Sửa lệnh và chạy lại</li>
    </ul>
</div>
""",
    unsafe_allow_html=True,
)

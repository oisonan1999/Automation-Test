import streamlit as st
import pandas as pd
import json
import os
import sys
import io
import re
from ai.brain import (
    parse_command_to_json,
    save_scenario,
    load_scenarios,
    delete_scenarios,
)
import ai.brain as brain_module
from automation.core import BrickAutomation

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
    .fast-mode {
        background-color: #00D084;
        color: white;
    }
    .careful-mode {
        background-color: #FF6B6B;
        color: white;
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
if "use_fast_mode" not in st.session_state:
    st.session_state.use_fast_mode = True  # Mặc định Fast Mode
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
if "smoke_last_created_id_by_feature" not in st.session_state:
    # Key = value from CSV column "Features" (e.g. "RBE", "PVE", "Gacha"...)
    # Value = last unique ID generated for a CREATE/CLONE case in that feature
    st.session_state.smoke_last_created_id_by_feature = {}

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


def _should_force_unique_id(case_label: str, testcase_text: str) -> bool:
    """
    Force unique ID for cases that are Create / Clone.
    We use English keywords because CSV label/steps are English.
    """
    text = f"{case_label or ''} {testcase_text or ''}".lower()
    return ("create" in text) or ("clone" in text)


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
    if st.button("Đóng", type="primary", use_container_width=True):
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
        if st.button("Xóa vĩnh viễn", type="primary", use_container_width=True):
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
        if st.button("Hủy", use_container_width=True):
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

    # === Tùy chọn AI Mode (chỉ dùng khi ở AI Run) ===
    st.markdown("### ⚙️ Tùy chọn AI Mode")

    col_mode1, col_mode2 = st.columns([3, 1])

    with col_mode1:
        use_fast_mode = st.checkbox(
            "⚡ Fast Mode (1 model - nhanh gấp 3x, phù hợp 90% lệnh)",
            value=st.session_state.use_fast_mode,
            key="fast_mode_checkbox",
            help="""
✅ Fast Mode (Khuyến nghị):
• Chỉ dùng 1 model (Qwen2.5-Coder)
• Thời gian: ~20-40 giây
• Độ chính xác: 90-95% với lệnh đơn giản
• Auto chuyển sang Careful Mode nếu phát hiện phức tạp

❌ Careful Mode (Cho lệnh phức tạp):
• Dùng 2 models (DeepSeek-R1 + Qwen2.5-Coder)
• Thời gian: ~1-2 phút
• Độ chính xác: 95-98%
            """,
        )
        st.session_state.use_fast_mode = use_fast_mode

    with col_mode2:
        if use_fast_mode:
            st.markdown(
                '<span class="mode-badge fast-mode">⚡ FAST</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="mode-badge careful-mode">🧠 CAREFUL</span>',
                unsafe_allow_html=True,
            )

    # === INFO BOX ===
    if use_fast_mode:
        st.info(
            "💡 Fast Mode đang BẬT. Hệ thống sẽ tự động phát hiện lệnh phức tạp và chuyển mode nếu cần."
        )
    else:
        st.warning("⏳ Careful Mode đang BẬT. AI sẽ phân tích kỹ hơn (~1-2 phút).")

    # === BUTTONS ===
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        run_btn = st.button("🚀 Chạy Ngay", type="primary", use_container_width=True)
    with col_btn2:
        save_name = st.text_input("Tên kịch bản:", placeholder="Regression Test 1")
        save_btn = st.button("💾 Lưu Kịch Bản", use_container_width=True)

    st.divider()

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
                "downloads/smoketestBrickLive.csv",
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
            use_container_width=True,
        )

with col2:
    st.subheader("📂 Kịch bản đã lưu")
    saved_scenarios = load_scenarios()
    if saved_scenarios:
        scenario_names = list(saved_scenarios.keys())
        st.selectbox("Chọn kịch bản:", scenario_names, key="selected_file")
        st.button(
            "📂 Load Kịch Bản",
            use_container_width=True,
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
            use_container_width=True,
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

    # Hiển thị thông tin mode
    col_info1, col_info2 = st.columns([1, 3])
    with col_info1:
        st.metric("Số bước", len(st.session_state.current_plan))
    with col_info2:
        if st.session_state.last_mode_used == "fast":
            st.success("✅ Được tạo bởi: Fast Mode (1 model)")
        elif st.session_state.last_mode_used == "careful":
            st.warning("✅ Được tạo bởi: Careful Mode (2 models)")

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
        # Hiển thị mode
        if st.session_state.use_fast_mode:
            st.info("⚡ Đang sử dụng Fast Mode...")
        else:
            st.info("🧠 Đang sử dụng Careful Mode...")

        # Placeholder cho real-time logs
        log_placeholder = st.empty()

        # Gọi AI với streaming log
        with StreamingLogCapture(log_placeholder) as ai_log:
            action_plan = parse_command_to_json(
                user_input,
                use_fast_mode=st.session_state.use_fast_mode,
                context_plan=st.session_state.loaded_scenario_plan,
                base_command=st.session_state.loaded_scenario_command,
            )

        # Lưu kết quả
        st.session_state.current_plan = action_plan
        st.session_state.run_execution = True
        st.session_state.test_logs = []

        # Lưu mode đã dùng (đọc từ brain module - phản ánh mode thực tế sau auto-switch)
        st.session_state.last_mode_used = brain_module.last_actual_mode

        status.update(
            label="✅ AI đã phân tích xong!", state="complete", expanded=False
        )

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
        status.update(label="✅ Hoàn thành!", state="complete", expanded=False)

    st.session_state.run_execution = False
    st.rerun()


# --- XỬ LÝ SMOKE BRICK LIVE (THEO CSV) ---
if st.session_state.run_mode == "Smoke Brick Live (theo CSV)" and smoke_run_btn:
    # Clear AI-run logs to avoid confusing UI
    st.session_state.test_logs = []
    st.session_state.smoke_results = []
    st.session_state.smoke_last_summary = None

    # Basic guard
    if not st.session_state.smoke_selected_csv:
        st.error("Vui lòng chọn CSV cho Smoke Brick Live.")
        st.stop()

    df_in = _parse_smoke_csv(st.session_state.smoke_selected_csv)

    # Forward-fill Features (CSV của bạn để trống Features cho các dòng testcase cùng feature)
    # Replace "" -> NaN -> ffill
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

            # Fallback: rebuild mapping from current df_in
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

    # Apply limit (0 = run all)
    if st.session_state.smoke_limit and int(st.session_state.smoke_limit) > 0:
        df_in = df_in.iloc[: int(st.session_state.smoke_limit)].copy()

    total_cases = len(df_in)
    st.info(f"Smoke Brick Live: chạy {total_cases} case từ CSV.")

    # Placeholders for incremental UI
    progress = st.progress(0)
    current_status_box = st.empty()
    live_table_box = st.empty()

    smoke_records = []

    for idx in range(total_cases):
        row = df_in.iloc[idx]
        feature = str(row.get("Features", "") or "").strip()
        testcase = str(row.get("Testcase", "") or "").strip()

        # Skip empty testcase rows (defensive)
        if not testcase:
            df_in.at[df_in.index[idx], "Result"] = "SKIPPED"
            df_in.at[df_in.index[idx], "Note"] = "Empty testcase"
            smoke_records.append(
                {
                    "Features": feature,
                    "Testcase": testcase,
                    "Result": "SKIPPED",
                    "Note": "Empty testcase",
                }
            )
            progress.progress((idx + 1) / total_cases)
            continue

        label, steps = _split_testcase_label_and_steps(testcase)
        display_case = label if label else testcase
        exec_steps = steps if steps else testcase

        current_status_box.markdown(
            f"**Case {idx+1}/{total_cases}**  \n"
            f"- Feature: `{feature}`  \n"
            f"- Testcase: `{display_case}`"
        )

        # 1) Build AI command for this testcase
        #    If CSV provides explicit steps after ":", pass BOTH:
        #    - label (without colon) to give the AI better context
        #    - steps (actual execution steps)
        if steps:
            case_command = f"{label}. {exec_steps}"
        else:
            case_command = _build_case_command(feature, exec_steps)

        generated_unique_id = None

        # Force unique ID for Create/Clone cases
        if _should_force_unique_id(label, testcase):
            unique_id = _make_unique_hieunm_test_id()
            generated_unique_id = unique_id
            case_command = (
                f"{case_command}\n\n"
                f"Yêu cầu: Với các bước CREATE hoặc CLONE, hãy tạo/điền ID duy nhất "
                f"bắt đầu bằng 'hieunm_test' và sử dụng đúng giá trị sau: {unique_id}. "
                f"Nếu có chỗ yêu cầu nhập '... ID ...' thì hãy thay bằng {unique_id}."
            )

        # ✅ Safety guard (GENERAL): After we successfully CREATE/CLONE an entity
        # in a given Feature, later cases of the SAME Feature must ONLY edit/filter
        # that generated ID — never "Sửa ID bất kỳ" (random) / "Filter một ID bất kỳ".
        feature_key = str(feature).strip()
        last_created_id = st.session_state.smoke_last_created_id_by_feature.get(
            feature_key
        )

        if last_created_id:
            # CSV phrases:
            # - "Sửa ID bất kỳ"
            # - "Filter một ID bất kỳ"
            case_command = re.sub(
                r"Sửa\s+ID\s+bất\s+kỳ",
                f"Sửa ID: {last_created_id}",
                case_command,
                flags=re.IGNORECASE,
            )
            case_command = re.sub(
                r"Filter\s+một\s+ID\s+bất\s+kỳ",
                f"Filter ID: {last_created_id}",
                case_command,
                flags=re.IGNORECASE,
            )

            # Extra: support commands like "Vào ID vừa tạo hoặc clone -> ..."
            # by replacing them with the concrete ID.
            case_command = re.sub(
                r"Sửa\s+ID\s+j[ữu]a\s+clone",
                f"Sửa ID: {last_created_id}",
                case_command,
                flags=re.IGNORECASE,
            )
            case_command = re.sub(
                r"Filter\s+ID\s+j[ữu]a\s+clone",
                f"Filter ID: {last_created_id}",
                case_command,
                flags=re.IGNORECASE,
            )

            case_command = re.sub(
                r"ID\s+j[ữu]a\s+clone\s*(?:hoặc\s+tạo)?",
                f"ID: {last_created_id}",
                case_command,
                flags=re.IGNORECASE,
            )
            case_command = re.sub(
                r"ID\s+j[ữu]a\s+clone",
                f"ID: {last_created_id}",
                case_command,
                flags=re.IGNORECASE,
            )

            # Keep existing “ID vừa tạo …” support
            case_command = re.sub(
                r"ID\s+j[ữu]a\s+tạo\s*(?:hoặc\s+clone)?",
                f"ID: {last_created_id}",
                case_command,
                flags=re.IGNORECASE,
            )
            case_command = re.sub(
                r"ID\s+j[ữu]a\s+tạo",
                f"ID: {last_created_id}",
                case_command,
                flags=re.IGNORECASE,
            )

        # 2) Parse to JSON action plan
        #    (Smoke mode chạy trực tiếp automation; dùng lại fast_mode checkbox)
        try:
            with st.status("🧠 AI đang phân tích...", expanded=False):
                action_plan = parse_command_to_json(
                    case_command,
                    use_fast_mode=st.session_state.use_fast_mode,
                    context_plan=None,
                    base_command=None,
                )

            if not action_plan:
                df_in.at[df_in.index[idx], "Result"] = "FAIL"
                df_in.at[df_in.index[idx], "Note"] = (
                    "Empty action plan (AI returned no steps)"
                )
                smoke_records.append(
                    {
                        "Features": feature,
                        "Testcase": display_case,
                        "Result": "FAIL",
                        "Note": "Empty action plan (AI returned no steps)",
                    }
                )
                progress.progress((idx + 1) / total_cases)
                continue
        except Exception as e:
            df_in.at[df_in.index[idx], "Result"] = "CRASH"
            df_in.at[df_in.index[idx], "Note"] = f"AI parse crashed: {str(e)[:250]}"
            smoke_records.append(
                {
                    "Features": feature,
                    "Testcase": display_case,
                    "Result": "CRASH",
                    "Note": f"AI parse crashed: {str(e)[:250]}",
                }
            )
            progress.progress((idx + 1) / total_cases)
            continue

        # 3) Execute action plan
        try:
            exec_log_placeholder = st.empty()
            with st.status("🤖 Automation đang chạy...", expanded=False):
                with StreamingLogCapture(exec_log_placeholder) as exec_log:
                    logs = automation.execute_action(action_plan)

            status_str, note_detail = _extract_smoke_status_from_logs(logs)
            df_in.at[df_in.index[idx], "Result"] = status_str
            df_in.at[df_in.index[idx], "Note"] = note_detail

            # ✅ Save the generated unique ID after successful CREATE/CLONE
            # for THIS feature, so later cases of the same feature are safe.
            if (
                generated_unique_id
                and feature
                and str(status_str).strip().upper() in {"PASS", "WARNING"}
            ):
                feature_key = str(feature).strip()
                st.session_state.smoke_last_created_id_by_feature[feature_key] = (
                    generated_unique_id
                )
                print(
                    f"   🧠 Smoke: saved smoke_last_created_id_by_feature[{feature_key}]={generated_unique_id} (status={status_str})"
                )

            smoke_records.append(
                {
                    "Features": feature,
                    "Testcase": display_case,
                    "Result": status_str,
                    "Note": note_detail,
                }
            )
        except Exception as e:
            df_in.at[df_in.index[idx], "Result"] = "CRASH"
            df_in.at[df_in.index[idx], "Note"] = f"Automation crashed: {str(e)[:250]}"
            smoke_records.append(
                {
                    "Features": feature,
                    "Testcase": display_case,
                    "Result": "CRASH",
                    "Note": f"Automation crashed: {str(e)[:250]}",
                }
            )

        # 4) Update live table (so user sees results per case)
        progress.progress((idx + 1) / total_cases)
        live_table_box.dataframe(
            pd.DataFrame(smoke_records),
            use_container_width=True,
            hide_index=True,
        )

    # Save report CSV (IN-MEMORY only: không ghi ra downloads/*)
    try:
        import datetime as _dt

        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"{SMOKE_OUTPUT_PREFIX}{ts}.csv"
        df_out = df_in.copy()

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

    # Force rerun to render smoke section below reliably
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
            use_container_width=True,
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
                    use_container_width=True,
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
                use_container_width=True,
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
                use_container_width=True,
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
            st.dataframe(df_log, use_container_width=True)

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
        <li>🔹 Lệnh đơn giản (2-4 bước) → Dùng Fast Mode</li>
        <li>🔹 Lệnh phức tạp (>5 bước) → Hệ thống tự chuyển Careful Mode</li>
        <li>🔹 Nếu AI hiểu sai → Bỏ tick Fast Mode và thử lại</li>
    </ul>
</div>
""",
    unsafe_allow_html=True,
)

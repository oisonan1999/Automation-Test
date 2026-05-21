import streamlit as st
import pandas as pd
import json
import os
import sys
import io
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

automation = st.session_state.automation


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
if run_btn and user_input:
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

# --- HIỂN THỊ BẢNG KẾT QUẢ ---
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

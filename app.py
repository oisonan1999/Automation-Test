import streamlit as st
import pandas as pd
import json
import os
from ai_brain import parse_command_to_json, save_scenario, load_scenarios
from automation_core import BrickAutomation

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

automation = st.session_state.automation


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
        st.selectbox(
            "Chọn kịch bản:", list(saved_scenarios.keys()), key="selected_file"
        )
        st.button(
            "📂 Load Kịch Bản",
            use_container_width=True,
            on_click=load_scenario_callback,
        )
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

# --- XỬ LÝ SỰ KIỆN CHẠY (AI BRAIN) ---
if run_btn and user_input:
    with st.spinner("🧠 AI đang suy nghĩ..."):
        # Hiển thị mode
        if st.session_state.use_fast_mode:
            st.info("⚡ Đang sử dụng Fast Mode...")
        else:
            st.info("🧠 Đang sử dụng Careful Mode...")

        # Gọi AI
        action_plan = parse_command_to_json(
            user_input, use_fast_mode=st.session_state.use_fast_mode
        )

        # Lưu kết quả
        st.session_state.current_plan = action_plan
        st.session_state.run_execution = True
        st.session_state.test_logs = []

        # Lưu mode đã dùng
        if st.session_state.use_fast_mode:
            st.session_state.last_mode_used = "fast"
        else:
            st.session_state.last_mode_used = "careful"

        st.rerun()

# --- XỬ LÝ SỰ KIỆN THỰC THI (ROBOT ACTION) ---
if st.session_state.run_execution and st.session_state.current_plan:
    with st.status("🤖 AI đang thực thi...", expanded=True) as status:
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
            col_stat1, col_stat2, col_stat3 = st.columns(3)

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
        else:
            st.dataframe(df_log, use_container_width=True)

    except Exception as e:
        st.error(f"Lỗi hiển thị bảng: {e}")
        st.write(report_logs)

# --- XỬ LÝ SỰ KIỆN LƯU ---
if save_btn and save_name and st.session_state.current_plan:
    save_scenario(save_name, st.session_state.current_plan, user_input)
    st.success(f"✅ Đã lưu kịch bản: {save_name}")
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

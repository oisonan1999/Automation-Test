import streamlit as st
import pandas as pd
import json
import os
from ai_brain import parse_command_to_json, save_scenario, load_scenarios
from automation_core import BrickAutomation

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Brick AI Automation By HieuNM", layout="wide")
st.title("🤖 Brick QA Automation AI By HieuNM")

# --- KHỞI TẠO STATE (BỘ NHỚ ĐỆM) ---
if 'automation' not in st.session_state: st.session_state.automation = BrickAutomation()
if 'current_plan' not in st.session_state: st.session_state.current_plan = None
if 'input_text' not in st.session_state: st.session_state.input_text = ""
if 'run_execution' not in st.session_state: st.session_state.run_execution = False
if 'test_logs' not in st.session_state: st.session_state.test_logs = [] # <--- MỚI: Lưu kết quả test

automation = st.session_state.automation 

# --- HÀM CALLBACK (LOAD KỊCH BẢN) ---
def load_scenario_callback():
    selected = st.session_state.selected_file
    saved = load_scenarios()
    
    if selected in saved:
        data = saved[selected]
        if isinstance(data, list):
            plan_to_load = data; cmd_to_load = "Kịch bản cũ"
        else:
            plan_to_load = data.get("plan", []); cmd_to_load = data.get("command", "")
            
        st.session_state.input_text = cmd_to_load
        st.session_state.current_plan = plan_to_load
        st.session_state.test_logs = [] # Reset logs khi load kịch bản mới

# --- GIAO DIỆN ---
col1, col2 = st.columns([2, 1])

with col1:
    user_input = st.text_area(
        "Nhập lệnh test của bạn:", 
        height=150, 
        placeholder="Ví dụ: Export CSV -> Smart Cycle test file csv...",
        key="input_text" 
    )
    
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
        st.selectbox("Chọn kịch bản:", list(saved_scenarios.keys()), key="selected_file")
        st.button("📂 Load Kịch Bản", use_container_width=True, on_click=load_scenario_callback)
    else:
        st.info("Chưa có kịch bản nào.")

# --- HIỂN THỊ JSON PLAN ---
if st.session_state.current_plan:
    st.divider()
    st.subheader("📋 Kế hoạch hành động (JSON):")
    st.json(st.session_state.current_plan)

# --- XỬ LÝ SỰ KIỆN CHẠY (AI BRAIN) ---
if run_btn and user_input:
    with st.spinner('🧠 AI đang suy nghĩ...'):
        action_plan = parse_command_to_json(user_input)
        st.session_state.current_plan = action_plan 
        st.session_state.run_execution = True # Bật cờ chạy
        st.session_state.test_logs = []       # Reset log cũ
        st.rerun()

# --- XỬ LÝ SỰ KIỆN THỰC THI (ROBOT ACTION) ---
if st.session_state.run_execution and st.session_state.current_plan:
    with st.status("🤖 Robot đang thực thi...", expanded=True) as status:
        # Gọi Robot và lưu kết quả vào session_state
        logs = automation.execute_action(st.session_state.current_plan)
        st.session_state.test_logs = logs # <--- LƯU VÀO STATE
        
        status.update(label="✅ Hoàn thành!", state="complete", expanded=False)
    
    st.session_state.run_execution = False # Tắt cờ chạy
    st.rerun() # Rerun để hiển thị bảng kết quả ổn định

# --- HIỂN THỊ BẢNG KẾT QUẢ (TÔ MÀU RESULT) ---
# Phần này nằm ngoài vòng lặp if run_execution, nên nó luôn hiển thị nếu có dữ liệu
if st.session_state.test_logs:
    st.subheader("📊 Kết quả chi tiết")
    report_logs = st.session_state.test_logs
    
    try:
        df_log = pd.DataFrame(report_logs)
        
        # Logic tô màu cột Result (Mới) hoặc Status (Cũ)
        def color_highlight(val):
            v_lower = str(val).lower()
            if "pass" in v_lower: color = '#28a745' # Xanh lá
            elif "fail" in v_lower or "crash" in v_lower: color = '#dc3545' # Đỏ
            else: color = 'black'
            return f'color: {color}; font-weight: bold'

        # Ưu tiên cột 'result' (Smart Cycle), nếu không có thì dùng 'status'
        target_col = 'result' if 'result' in df_log.columns else 'status'
        
        if not df_log.empty and target_col in df_log.columns:
            st.dataframe(
                df_log.style.map(color_highlight, subset=[target_col]), 
                use_container_width=True
            )
        else:
            st.dataframe(df_log, use_container_width=True)
            
    except Exception as e:
        st.error(f"Lỗi hiển thị bảng: {e}")
        st.write(report_logs)

# --- XỬ LÝ SỰ KIỆN LƯU ---
if save_btn and save_name and st.session_state.current_plan:
    save_scenario(save_name, st.session_state.current_plan, user_input)
    st.success(f"Đã lưu kịch bản: {save_name}")
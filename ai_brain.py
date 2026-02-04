# ai_brain.py
import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv()

MODEL_REASONING = "deepseek-r1:14b"
MODEL_FORMATTING = "qwen2.5-coder:14b"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
SCENARIO_FILE = "scenarios.json"


def load_scenarios():
    if not os.path.exists(SCENARIO_FILE):
        return {}
    try:
        with open(SCENARIO_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    except:
        return {}


def save_scenario(name, plan, user_command=""):
    data = load_scenarios()
    # Lưu cả câu lệnh gốc và kế hoạch JSON
    data[name] = {"command": user_command, "plan": plan}
    with open(SCENARIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clean_json_string(text):
    """
    Hàm làm sạch chuỗi JSON (Nuclear Cleaning):
    Loại bỏ mọi thứ không phải là cú pháp JSON hợp lệ để tránh lỗi parse.
    """
    if not text:
        return "[]"

    # 1. Xóa Markdown code block (```json ... ```)
    text = re.sub(r"```json|```", "", text)

    # 2. Xóa comment HTML (ĐÂY LÀ NGUYÊN NHÂN GÂY LỖI CỦA BẠN)
    # Sử dụng [\s\S] để bắt cả ký tự xuống dòng
    text = re.sub(r"", "", text)

    # 3. Xóa comment Block kiểu C /* ... */
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)

    # 4. Xóa comment dòng kiểu JS // ...
    # (Dùng cờ MULTILINE để xóa từ // đến hết dòng)
    text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)

    # 5. Trích xuất đoạn JSON list [...] hoặc object {...} nằm ngoài cùng
    match_list = re.search(r"\[[\s\S]*\]", text)
    if match_list:
        text = match_list.group(0)
    else:
        # Nếu không thấy list, thử tìm object {}
        match_obj = re.search(r"\{[\s\S]*\}", text)
        if match_obj:
            text = match_obj.group(0)

    # 6. Xóa dấu phẩy thừa ở cuối (Trailing commas) - Lỗi phổ biến của LLM
    # VD: { "a": 1, } -> { "a": 1 }
    text = re.sub(r",\s*(\}|\])", r"\1", text)

    return text.strip()


def call_ollama(model_name, prompt, stream=False):
    """Hàm gọi API Ollama chung cho cả 2 model"""
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": stream,
        "options": {
            "temperature": 0.0,  # Giữ nhiệt độ thấp để kết quả ổn định
            "num_ctx": 4096,  # Tăng context window nếu lệnh dài
        },
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            print(f"⚠️ Error calling {model_name}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Connection Error ({model_name}): {e}")
        return None


def parse_command_to_json(user_command, context_plan=None):
    print("\n🧠 AI Pipeline Started...")

    # =========================================================================
    # BƯỚC 1: SUY LUẬN (REASONING PHASE) - Model: DeepSeek-R1
    # Nhiệm vụ: Hiểu tiếng Việt, phân tích logic, phá giải các yêu cầu phức tạp.
    # =========================================================================
    print(f"   1️⃣  DeepSeek-R1 are currently analyzing the requirements...")
    #   4. Identify any implicit steps (e.g., "Export" usually means we need to wait a few seconds for a download).
    reasoning_prompt = f"""
    Analyze the following QA Automation Command provided by the user.
    
    USER COMMAND: "{user_command}"
    
    YOUR TASK:
    1. Understand the user's intent in Vietnamese/English.
    2. Break it down into a logical sequence of steps.
    3. Extract key details like:
       - Menu paths (e.g., "Data Configs -> Perk -> Perk", "Live Events -> Offer -> Offer").
       - File names (e.g., "file2.csv").
       - Specific actions (Upload, Export, Add rows).
       - Data values (e.g., "BagID=Grabbag_hnm").
    
    5. Identify specific actions:
       - "Chọn/Tick X dòng" -> Checkbox action.
       - "Bất kỳ/Random" -> Value should imply random.
       - "Export... tên là X" -> Download action with specific filename.
       - "Thêm dòng... vào file" -> Manipulate CSV action.
    6. Extract Data:
       - If adding rows: Extract Column Name and Values (e.g., BagID = A, B).
    7. "Scan tabs..." -> Means we are inside a detail page and need to check multiple tabs.
    8. "Sửa Cost..., Sửa Stock..." -> Means we are filling a form.
    9. Identify actions: navigate, click, wait, download, upload.
    10. "Chọn League 5" -> Click on Sidebar "League 5".
    11. "Đợi trang load" -> Wait action.
    12. "Export CSV" -> Download action.

    Output ONLY the logical analysis/plan in plain text. Do NOT generate JSON yet.
    """

    # Gọi DeepSeek
    raw_analysis = call_ollama(MODEL_REASONING, reasoning_prompt)
    unload_model(MODEL_REASONING)
    if not raw_analysis:
        return []

    # Lọc bỏ thẻ <think>...</think> đặc trưng của DeepSeek-R1 để tránh gây nhiễu cho bước sau
    analysis_clean = re.sub(
        r"<think>.*?</think>", "", raw_analysis, flags=re.DOTALL
    ).strip()

    # In ra một phần suy nghĩ để bạn theo dõi (Debug)
    print(
        f"      📝 Analysis from DeepSeek: {analysis_clean[:100].replace(chr(10), ' ')}..."
    )

    # =========================================================================
    # BƯỚC 2: ĐỊNH DẠNG (FORMATTING PHASE) - Model: Qwen2.5-Coder
    # Nhiệm vụ: Nhìn vào bản phân tích của DeepSeek và viết code JSON chuẩn xác.
    # =========================================================================
    print(f"   2️⃣  Qwen2.5-Coder is converting to JSON Action Plan...")

    formatting_prompt = f"""
    You are a Senior QA Automation AI and a Strict JSON Converter.
    I will provide you with a User Command and an Expert Analysis (from DeepSeek).
    
    Task: Convert them into a detailed, sequential JSON Action Plan.

    AVAILABLE ACTIONS:
    1. "navigate": {{ "action": "navigate", "path": ["Menu1", "Menu2", "Menu3] }}
    2. "checkbox": 
       - Rule: Use for "Chọn", "Tick", "Select".
       - Format: {{ "action": "checkbox", "target": "ColumnName", "value": "random_N" or "all" }}
       - Example: "Chọn 2 BagID bất kỳ" -> value: "random_2", target: "BagID".
    3. "download": 
       - Rule: Use for "Export".
       - Format: {{ "action": "download", "target": "Export CSV", "value": "filename.csv" }}
    4. "upload": {{ "action": "upload", "target": "Import CSV", "value": "filename.csv" }}
    5. "manipulate_csv": 
       - Rule: Use for "Thêm dòng", "Sửa dòng", "Add rows".
       - Format: {{ "action": "manipulate_csv", "target": "filename.csv", "operation": "add", "data": "ColName=Val1,Val2" }}
       - Example: "Thêm 2 dòng BagID là A, B vào file.csv" 
         -> {{ "action": "manipulate_csv", "target": "file.csv", "operation": "add", "data": "BagID=A,B" }}
    6. "smart_test_cycle": {{ "action": "smart_test_cycle", "target": "Import CSV", "value": "file.csv" }}
    7. "clone_row": {{ "action": "clone_row", "target": "ID" }}
    8. "edit_row": {{ "action": "edit_row", "target": "ID" }}
    9. "update_form": {{ "action": "update_form", "data": {{ "Label": "Value", ... }} }}
       - Used to fill forms/popups. 
       - MUST extract ALL fields mentioned in user command.
       - Use "Tab" key if user says "Go to tab X".
       - Use "Field" keys for Inputs, Selects, Toggles.
    10. "save_form": {{ "action": "save_form" }}
    11. "scan_tabs": 
        - Rule: Use when user says "Scan tabs", "Quét các tab", "Duyệt qua các tab".
        - IMPORTANT: If user lists fields to update immediately after "Scan tabs", PUT THEM INSIDE "data".
        - Format: {{ "action": "scan_tabs", "data": {{ "Field1": "Val1", "Field2": "Val2" }} }}
    12. "process_deployment": {{ "action": "process_deployment", "options": ["Option1", "Option2"] }}
        - Use when user says: "Click The Brick", "Process", "Deploy", "Tick X then Process".
    13. "click": {{ "action": "click", "target": "Name" }}
    14. "wait": {{ "action": "wait" }}
    CRITICAL RULES:
    1. **SEQUENCE IS KING**: Process command strictly LEFT to RIGHT.
       - "Go to A -> B -> C -> Clone D" => 1. navigate [A,B,C], 2. clone D.
    2. **STRICT JSON ONLY**: Output ONLY the JSON array.
    3. **NO COMMENTS**: Do NOT output // or . If you do, the system will crash.
    4. **NO MARKDOWN**: No ```json tags.

    2. **FORM DATA EXTRACTION (CRITICAL)**:
       - Command: "Set ID: A, Gate: B, Currency: C and Currency Value: D"
       - You MUST extract ALL 4 fields into one "update_form" action.
       - Ignore connectors like "and", "và", "then", "with".
       - Output: 
         {{
           "action": "update_form", 
           "data": {{
             "ID": "A", 
             "Gate": "B", 
             "Currency": "C", 
             "Currency Value": "D"
           }}
         }}

    3. **CLONE FLOW**:
       - Command: "Clone 'A' to 'B', gate 'C'..."
       - Output:
         [
           {{ "action": "clone_row", "target": "A" }},
           {{ "action": "update_form", "data": {{ "ID": "B", "Gate": "C", ... }} }},
           {{ "action": "save_form" }}
         ]
    4. **TABLE vs FORM DISTINCTION**:
       - Command: "Bấm nút Edit của BagID: ABC" 
         -> CORRECT: {{ "action": "edit_row", "target": "ABC" }}
         -> WRONG:   {{ "action": "update_form", "data": {{ "BagID": "ABC" }} }} (Do NOT do this)
    5. **SEQUENCE**:
       - "Edit A -> Scan tabs -> Set B" 
         => 1. edit_row(A), 2. scan_tabs(B)
    CRITICAL EXAMPLES:
    
    Ex 1: "Edit ID ABC -> Quét các tab -> Sửa Cost: 10, Sửa Stock: 5"
    WRONG: [{{ "action": "edit_row" }}, {{ "action": "scan_tabs", "data": {{}} }}, {{ "action": "update_form", "data": {{ "Cost": "10" }} }}]
    CORRECT: [
      {{ "action": "edit_row", "target": "ABC" }},
      {{ "action": "scan_tabs", "data": {{ "Cost": "10", "Stock": "5" }} }}  <-- MERGED HERE
    ]

    Ex 2: "... -> Vào tab Pulls -> Sửa Quantity: 10"
    CORRECT: [
      {{ "action": "update_form", "data": {{ "Tab": "Pulls", "Quantity": "10" }} }}
    ]
    
    Ex 3: "User: "Vào Gacha Info sửa Cost 10 -> Save & Continue -> Vào tab Milestones"
    JSON: [
      {{ "action": "update_form", "data": {{ "Tab": "Gacha Info", "Cost": "10" }} }},
      {{ "action": "save_form", "mode": "continue" }},
      {{ "action": "update_form", "data": {{ "Tab": "Milestones" }} }}
    ]"
    
    Ex 4: "User: "Bấm nút The Brick -> Tick chọn 'Hyper Blueprint' -> Bấm Process"
    JSON: [
      {{ "action": "process_deployment", "options": ["Hyper Blueprint"] }}
    ]"

    INPUT CONTEXT:
    - Original Command: "{user_command}"
    - Expert Analysis:
    {analysis_clean}

    OUTPUT REQUIREMENT:
    - Output ONLY the raw JSON list [ ... ].
    - No markdown formatting (no ```json).
    - No explanations.
    """

    # Gọi Qwen
    json_output = call_ollama(MODEL_FORMATTING, formatting_prompt)
    unload_model(MODEL_FORMATTING)

    # Làm sạch và Parse JSON
    final_json_str = clean_json_string(json_output)

    try:
        plan = json.loads(final_json_str)
        print(f"   ✅ Đã tạo thành công {len(plan)} bước hành động.")
        if (
            plan
            and plan[-1].get("action") == "manipulate_csv"
            and "Import" in user_command
        ):
            print("   ⚠️ Auto-fix: Adding missing Upload step.")
            target_file = plan[-1].get("target")
            plan.append(
                {"action": "upload", "target": "Import CSV", "value": target_file}
            )
        return plan
    except json.JSONDecodeError as e:
        print(f"   ❌ Lỗi Parse JSON từ Qwen: {e}")
        print(f"   Raw output: {json_output}")
        return []


def unload_model(model_name):
    # Gửi request rỗng với keep_alive=0 để unload ngay lập tức
    try:
        requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "keep_alive": 0},
        )
        print(f"   🧹 Đã giải phóng VRAM model: {model_name}")
    except:
        pass

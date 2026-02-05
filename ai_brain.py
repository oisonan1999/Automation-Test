# ai_brain.py - OPTIMIZED VERSION với Hybrid Pipeline
import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv()

# === CONFIGURATION ===
MODEL_REASONING = "deepseek-r1:14b"
MODEL_FORMATTING = "qwen2.5-coder:14b"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
SCENARIO_FILE = "scenarios.json"


# ============================================================================
# HELPER FUNCTIONS (Giữ nguyên)
# ============================================================================


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
    Loại bỏ mọi thứ không phải là cú phápJSON hợp lệ để tránh lỗi parse.
    """
    if not text:
        return "[]"

    # 0. [CRITICAL] Fix double braces từ LLM ({{ -> {, }} -> })
    # LLM hay copy pattern từ f-string examples và trả về {{ }} thay vì { }
    text = text.replace("{{", "{").replace("}}", "}")

    # 1. Xóa Markdown code block (```json ... ```)
    text = re.sub(r"```json|```", "", text)

    # 2. Xóa comment HTML (ĐÂY LÀ NGUYÊN NHÂN GÂY LỖI CỦA BẠN)
    # Sử dụng [\s\S] để bắt cả ký tự xuống dòng
    text = re.sub(r"<!--[\s\S]*?-->", "", text)

    # 3. Xóa comment Block kiểu C /* ... */
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)

    # 4. Xóa comment dòng kiểu JS // ...
    # (Dùng cờ MULTILINE để xóa từ // đến hết dòng)
    text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)

    # 5. Trích xuất đoạn JSON list [...] hoặc object {...} nằm ngoài cùng
    # [FIX] Dùng rfind() thay vì regex để tìm ] cuối cùng
    first_bracket = text.find("[")
    last_bracket = text.rfind("]")

    if first_bracket != -1:
        if last_bracket != -1 and last_bracket > first_bracket:
            # Có cả [ và ] - extract từ [ đến ]
            text = text[first_bracket : last_bracket + 1]
        else:
            # Có [ nhưng thiếu ] - lấy từ [ đến hết (sẽ fix brackets sau)
            text = text[first_bracket:]
    else:
        # Nếu không thấy list, thử tìm object {}
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1:
            if last_brace != -1 and last_brace > first_brace:
                text = text[first_brace : last_brace + 1]
            else:
                text = text[first_brace:]

    # 6. [NEW] Chuyển single quotes thành double quotes (Fix lỗi LLM hay trả về 'key' thay vì "key")
    # Chỉ chuyển quotes bao quanh keys và string values, không chuyển trong nội dung string
    # Pattern: Tìm 'text' không nằm trong double quotes
    def replace_single_quotes(match):
        s = match.group(0)
        # Nếu đã có double quote bao ngoài thì giữ nguyên
        if s.startswith('"'):
            return s
        # Chuyển 'text' -> "text"
        return '"' + s[1:-1] + '"'

    # Pattern match: 'any text' (single quoted strings)
    text = re.sub(r"'([^'\\]*(\\.[^'\\]*)*)'", replace_single_quotes, text)

    # 8. [NEW] Fix incomplete JSON (bị cắt output)
    # Nếu JSON không đóng đúng, tự động thêm closing brackets
    text = text.strip()
    if text:
        # 8.1. Xóa dấu phẩy thừa CHỈ KHI ở cuối (trailing comma)
        # CRITICAL: Chỉ xóa pattern rõ ràng, không xóa comma hợp lệ

        # Safe: Xóa `,]` (trailing comma in array)
        text = re.sub(r",\s*]", "]", text)

        # DANGER: KHÔNG xóa `,}` vì regex sẽ match nhầm trong `}},`
        # Chỉ xóa nếu `,}` ở cuối file (end of string)
        text = re.sub(r",\s*}\s*$", "}", text)

        # Trailing comma ở cuối file
        text = re.sub(r'"\s*,\s*$', '"', text)

        # 8.2. Fix truncated string values ("hieunm_sec... -> "hieunm_sec")
        if text and not text.endswith(('"', "}", "]")):
            # Tìm dấu quote mở cuối cùng
            last_quote_pos = text.rfind('"')
            if last_quote_pos != -1:
                quotes_before = text[:last_quote_pos].count('"')
                if quotes_before % 2 == 0:  # Số chẵn = quote mở
                    if text.endswith("..."):
                        text = text[:-3]
                    text += '"'
            else:
                # Không tìm thấy quote - có thể bị cắt giữa chừng
                last_colon = text.rfind(":")
                if last_colon != -1:
                    text = text[: last_colon + 1] + ' ""'

        # 8.3. Fix incomplete key-value pairs
        text = re.sub(r':\s*"([^"]*?)$', r': "\1"', text)

        # 8.4. Đếm số mở/đóng ngoặc và thêm thiếu
        open_braces = text.count("{")
        close_braces = text.count("}")
        open_brackets = text.count("[")
        close_brackets = text.count("]")

        # 8.5. Thêm closing brackets nếu thiếu
        # Strategy: Phân tích cấu trúc để thêm đúng vị trí

        if open_braces > close_braces:
            missing_braces = open_braces - close_braces
            print(f"   🔧 Auto-fix: Need to add {missing_braces} missing '}}'")

            # Tìm vị trí comma cuối cùng trước last object
            # Pattern: `...},\n    {"action": "save_form"}`
            # Cần thêm } SAU "r80"} (trước dấu comma đầu tiên sau nó)

            # Find position after last complete data object
            # Look for pattern: "value"}}, OR "value"},
            last_complete = max(text.rfind('"}}'), text.rfind('"}},'))

            if last_complete == -1:
                # Not found - find last "value"},
                last_complete = text.rfind('"},')

            if last_complete != -1:
                # Insert after the closing "
                insert_pos = last_complete + 1  # After "
                text = text[:insert_pos] + "}" * missing_braces + text[insert_pos:]
                print(f"   ✅ Inserted }} after position {insert_pos}")
            else:
                # Fallback: add before final ]
                last_bracket_pos = text.rfind("]")
                if last_bracket_pos != -1:
                    text = (
                        text[:last_bracket_pos]
                        + "}" * missing_braces
                        + text[last_bracket_pos:]
                    )
                else:
                    text += "}" * missing_braces

        if open_brackets > close_brackets:
            missing_brackets = open_brackets - close_brackets
            print(f"   🔧 Auto-fix: Will add {missing_brackets} missing ']'")
            text += "]" * missing_brackets

    return text.strip()


def call_ollama(model_name, prompt, stream=False, optimized=False):
    """
    Hàm gọi API Ollama

    Args:
        model_name: Tên model
        prompt: Prompt text
        stream: Streaming mode
        optimized: Nếu True, dùng config nhanh hơn (giảm context, giới hạn output)
    """
    # Config mặc định (Careful Mode)
    options = {
        "temperature": 0.1,
        "num_ctx": 2867,
        "num_gpu": 99,
    }

    # Config tối ưu tốc độ (Fast Mode)
    if optimized:
        options = {
            "temperature": 0.1,
            "num_ctx": 8192,  # ⬆️ Tăng lên để đủ chứa prompt + output
            "num_predict": 4096,  # ⬆️ Tăng lên 4096 để tránh cắt output JSON
            "num_gpu": 99,
        }

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": stream,
        "options": options,
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


# ============================================================================
# COMPLEXITY DETECTION (MỚI)
# ============================================================================


def detect_complexity(user_command):
    """
    Phát hiện độ phức tạp của lệnh

    Returns:
        bool: True nếu lệnh phức tạp (cần dùng 2 models)
    """
    command_lower = user_command.lower()

    # 1. Từ khóa logic phức tạp
    complex_keywords = [
        "nếu",
        "if",
        "else",
        "otherwise",
        "trong trường hợp",
        "tất cả các tab",
        "all tabs",
        "mọi tab",
        "every tab",
        "với mỗi",
        "for each",
        "từng",
        "each",
        "sau đó tìm",
        "then find",
        "rồi tìm",
        "hoặc",
        "or",
        "và nếu",
        "and if",
        "lặp lại",
        "repeat",
        "loop",
    ]

    has_complex_logic = any(kw in command_lower for kw in complex_keywords)

    # 2. Đếm số bước (dấu -> hoặc →)
    num_steps = command_lower.count("->") + command_lower.count("→")
    many_steps = num_steps > 7  # Tăng từ 5 lên 7 để tránh false positive

    # 3. Độ dài lệnh (lệnh quá dài thường phức tạp)
    is_very_long = len(user_command) > 350  # Tăng từ 250 lên 350

    # 4. Có chứa nhiều actions khác nhau
    action_keywords = [
        "navigate",
        "edit",
        "clone",
        "upload",
        "download",
        "scan",
        "export",
        "import",
        "delete",
        "add",
        "update",
    ]
    action_count = sum(1 for kw in action_keywords if kw in command_lower)
    many_actions = action_count > 6  # Tăng từ 4 lên 6

    # KẾT LUẬN
    is_complex = has_complex_logic or many_steps or is_very_long or many_actions

    if is_complex:
        print(
            f"   🔍 Complexity Detection: COMPLEX (logic={has_complex_logic}, steps={num_steps}, len={len(user_command)}, actions={action_count})"
        )
    else:
        print(f"   🔍 Complexity Detection: SIMPLE")

    return is_complex


# ============================================================================
# SINGLE MODEL PIPELINE (Fast Mode)
# ============================================================================


def single_model_pipeline(user_command):
    """
    Pipeline nhanh - Chỉ dùng 1 model (Qwen2.5-Coder)
    Thời gian: ~20-40 giây
    """
    print(f"   ⚡ FAST MODE: Single-model pipeline")

    # Prompt tối ưu - Ngắn gọn, đi thẳng vào vấn đề
    prompt = f"""You are a QA Automation AI. Convert this Vietnamese/English command to a JSON Action Plan.

USER COMMAND: "{user_command}"

AVAILABLE ACTIONS:
1. navigate: {{"action": "navigate", "path": ["Menu1", "Menu2", "Menu3"]}}
2. checkbox: {{"action": "checkbox", "target": "ColumnName", "value": "random_N" or "all" or "specific_id"}}
3. download: {{"action": "download", "target": "Export CSV", "value": "filename.csv"}}
4. upload: {{"action": "upload", "target": "Import CSV", "value": "filename.csv"}}
5. manipulate_csv: {{"action": "manipulate_csv", "target": "file.csv", "operation": "add/edit/delete", "data": "ColName=Val1,Val2"}}
6. smart_test_cycle: {{"action": "smart_test_cycle", "value": "file.csv"}}
7. clone_row: {{"action": "clone_row", "target": "ID"}}
8. edit_row: {{"action": "edit_row", "target": "ID"}}
9. update_form: {{"action": "update_form", "data": {{"Field1": "Value1", "Field2": "Value2"}}}}
   - For radio buttons, use EXACT label text as key with value "select"
   - Example: {{"Use another currency": "select"}}
10. save_form: {{"action": "save_form"}}
11. scan_tabs: {{"action": "scan_tabs", "data": {{"Field": "Value"}}}}
12. click: {{"action": "click", "target": "ButtonName"}}
13. wait: {{"action": "wait"}}

RULES:
- Process LEFT to RIGHT
- Output ONLY JSON array - MUST be valid, complete JSON
- NO markdown tags (no ```json)
- NO comments
- CRITICAL: Always close all brackets properly {{}}, []
- CRITICAL: Do NOT truncate the JSON output

EXAMPLES:
Input: "Vào Data Configs -> Perk -> Perk -> Edit ABC"
Output: [{{"action":"navigate","path":["Data Configs","Perk","Perk"]}},{{"action":"edit_row","target":"ABC"}}]

Input: "Vào Live Events -> Offer -> Offer Section -> Clone quanvm_section_1 -> New SectionID: hieunm_section_1, gate: r80"
Output: [{{"action":"navigate","path":["Live Events","Offer","Offer Section"]}},{{"action":"clone_row","target":"quanvm_section_1"}},{{"action":"update_form","data":{{"New SectionID":"hieunm_section_1","gate":"r80"}}}},{{"action":"save_form"}}]

Input: "Clone EventGacha_ABC -> New ID: test_1, gate: feb2026_live, chọn Use another currency, currency: GachaShard_XYZ"
Output: [{{"action":"clone_row","target":"EventGacha_ABC"}},{{"action":"update_form","data":{{"New Event ID":"test_1","Gate":"feb2026_live","Use another currency":"select","Currency":"GachaShard_XYZ"}}}},{{"action":"save_form"}}]

Input: "Edit BossEvent_ABC -> Acquire lock -> sửa gate: LiveOpsTest -> Save -> Click menu Boss Details -> sửa Wrestler ID: SS_TheRock"
Output: [{{"action":"edit_row","target":"BossEvent_ABC"}},{{"action":"click","target":"Acquire lock"}},{{"action":"update_form","data":{{"Gate":"LiveOpsTest"}}}},{{"action":"save_form"}},{{"action":"click","target":"Boss Details"}},{{"action":"update_form","data":{{"Wrestler ID":"SS_TheRock"}}}}]

Input: "Vào Scout Missions tab -> sửa Scout Phase Start Time: 2025-08-20 10:00, End Time: 2025-08-25 15:00"
Output: [{{"action":"click","target":"Scout Missions"}},{{"action":"update_form","data":{{"Scout Phase Start Time":"2025-08-20 10:00","End Time":"2025-08-25 15:00"}}}}]

Now convert the USER COMMAND above. Output JSON only:"""

    # Gọi model với config tối ưu
    json_output = call_ollama(MODEL_FORMATTING, prompt, optimized=True)
    unload_model(MODEL_FORMATTING)

    if not json_output:
        return []

    # [DEBUG] Check raw output length
    if len(json_output) > 3000:
        print(
            f"   ⚠️  Warning: Model output is very long ({len(json_output)} chars). May indicate verbosity issue."
        )

    # Parse JSON
    final_json_str = clean_json_string(json_output)

    try:
        plan = json.loads(final_json_str)
        print(f"   ✅ Fast Mode: Tạo thành công {len(plan)} bước")
        return plan
    except json.JSONDecodeError as e:
        print(f"   ❌ Fast Mode Parse Error: {e}")
        print(f"   Raw output (first 500 chars): {json_output[:500]}...")
        print(f"   Cleaned output (first 500 chars): {final_json_str[:500]}...")

        # [DEBUG] Show full cleaned output if short enough
        if len(final_json_str) < 2000:
            print(f"   📝 Full Cleaned JSON:\n{final_json_str}")

        print(
            f"   ⚠️  Tip: Lệnh này có thể phức tạp, hãy thử tắt Fast Mode và chạy lại."
        )
        return []


# ============================================================================
# DUAL MODEL PIPELINE (Careful Mode) - GIỮ NGUYÊN CODE CŨ
# ============================================================================


def dual_model_pipeline(user_command):
    """
    Pipeline cẩn thận - Dùng 2 models (DeepSeek-R1 + Qwen2.5-Coder)
    Thời gian: ~1-2 phút
    """
    print(f"   🧠 CAREFUL MODE: Dual-model pipeline")

    # =========================================================================
    # BƯỚC 1: SUY LUẬN (REASONING PHASE) - Model: DeepSeek-R1
    # =========================================================================
    print(f"   1️⃣  DeepSeek-R1 are currently analyzing the requirements...")

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

    # Lọc bỏ thẻ <think>...</think>
    analysis_clean = re.sub(
        r"<think>.*?</think>", "", raw_analysis, flags=re.DOTALL
    ).strip()

    print(
        f"      📝 Analysis from DeepSeek: {analysis_clean[:100].replace(chr(10), ' ')}..."
    )

    # =========================================================================
    # BƯỚC 2: ĐỊNH DẠNG (FORMATTING PHASE) - Model: Qwen2.5-Coder
    # =========================================================================
    print(f"   2️⃣  Qwen2.5-Coder is converting to JSON Action Plan...")

    formatting_prompt = f"""
    You are a Senior QA Automation AI and a Strict JSON Converter.
    I will provide you with a User Command and an Expert Analysis (from DeepSeek).
    
    Task: Convert them into a detailed, sequential JSON Action Plan.

    AVAILABLE ACTIONS:
    1. "navigate": {{{{ "action": "navigate", "path": ["Menu1", "Menu2", "Menu3] }}}}
    2. "checkbox": 
       - Rule: Use for "Chọn", "Tick", "Select".
       - Format: {{{{ "action": "checkbox", "target": "ColumnName", "value": "random_N" or "all" }}}}
       - Example: "Chọn 2 BagID bất kỳ" -> value: "random_2", target: "BagID".
    3. "download": 
       - Rule: Use for "Export".
       - Format: {{{{ "action": "download", "target": "Export CSV", "value": "filename.csv" }}}}
    4. "upload": {{{{ "action": "upload", "target": "Import CSV", "value": "filename.csv" }}}}
    5. "manipulate_csv": 
       - Rule: Use for "Thêm dòng", "Sửa dòng", "Add rows".
       - Format: {{{{ "action": "manipulate_csv", "target": "filename.csv", "operation": "add", "data": "ColName=Val1,Val2" }}}}
       - Example: "Thêm 2 dòng BagID là A, B vào file.csv" 
         -> {{{{ "action": "manipulate_csv", "target": "file.csv", "operation": "add", "data": "BagID=A,B" }}}}
    6. "smart_test_cycle": {{{{ "action": "smart_test_cycle", "target": "Import CSV", "value": "file.csv" }}}}
    7. "clone_row": {{{{ "action": "clone_row", "target": "ID" }}}}
    8. "edit_row": {{{{ "action": "edit_row", "target": "ID" }}}}
    9. "update_form": {{{{ "action": "update_form", "data": {{{{ "Label": "Value", ... }}}} }}}}
       - Used to fill forms/popups. 
       - MUST extract ALL fields mentioned in user command.
       - Use "Tab" key if user says "Go to tab X".
       - Use "Field" keys for Inputs, Selects, Toggles.
    10. "save_form": {{{{ "action": "save_form" }}}}
    11. "scan_tabs": 
        - Rule: Use when user says "Scan tabs", "Quét các tab", "Duyệt qua các tab".
        - IMPORTANT: If user lists fields to update immediately after "Scan tabs", PUT THEM INSIDE "data".
        - Format: {{{{ "action": "scan_tabs", "data": {{{{ "Field1": "Val1", "Field2": "Val2" }}}} }}}}
    12. "process_deployment": {{{{ "action": "process_deployment", "options": ["Option1", "Option2"] }}}}
        - Use when user says: "Click The Brick", "Process", "Deploy", "Tick X then Process".
    13. "click": {{{{ "action": "click", "target": "Name" }}}}
    14. "wait": {{{{ "action": "wait" }}}}
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
         {{{{
           "action": "update_form", 
           "data": {{{{
             "ID": "A", 
             "Gate": "B", 
             "Currency": "C", 
             "Currency Value": "D"
           }}}}
         }}}}

    3. **CLONE FLOW (CRITICAL)**:
       - Command: "Clone 'A' -> New ID: B, gate: C, chọn radio Use another currency, currency: D"
       - THE FORM DATA MUST INCLUDE:
         * Input fields: "New Event ID" or just the suffix part
         * Dropdown fields: "Gate", "Currency"  
         * Radio buttons: Use EXACT label text as key (e.g., "Use another currency": "select")
       - Output:
         [
           {{{{ "action": "clone_row", "target": "A" }}}},
           {{{{ "action": "update_form", "data": {{{{ 
               "New Event ID": "B",
               "Gate": "C", 
               "Use another currency": "select",
               "Currency": "D"
           }}}} }}}},
           {{{{ "action": "save_form" }}}}
         ]
       - IMPORTANT: Radio button label MUST be the EXACT text shown on screen.
       - For radio: value can be "select", "true", "on", or "1".
       
    4. **TABLE vs FORM DISTINCTION**:
       - Command: "Bấm nút Edit của BagID: ABC" 
         -> CORRECT: {{{{ "action": "edit_row", "target": "ABC" }}}}
         -> WRONG:   {{{{ "action": "update_form", "data": {{{{ "BagID": "ABC" }}}} }}}} (Do NOT do this)
    5. **SEQUENCE**:
       - "Edit A -> Scan tabs -> Set B" 
         => 1. edit_row(A), 2. scan_tabs(B)
    CRITICAL EXAMPLES:
    
    Ex 1: "Edit ID ABC -> Quét các tab -> Sửa Cost: 10, Sửa Stock: 5"
    WRONG: [{{{{ "action": "edit_row" }}}}, {{{{ "action": "scan_tabs", "data": {{{{}}}} }}}}, {{{{ "action": "update_form", "data": {{{{ "Cost": "10" }}}} }}}}]
    CORRECT: [
      {{{{ "action": "edit_row", "target": "ABC" }}}},
      {{{{ "action": "scan_tabs", "data": {{{{ "Cost": "10", "Stock": "5" }}}} }}}}  <-- MERGED HERE
    ]

    Ex 2: "... -> Vào tab Pulls -> Sửa Quantity: 10"
    CORRECT: [
      {{{{ "action": "update_form", "data": {{{{ "Tab": "Pulls", "Quantity": "10" }}}} }}}}
    ]
    
    Ex 3: "User: "Vào Gacha Info sửa Cost 10 -> Save & Continue -> Vào tab Milestones"
    JSON: [
      {{{{ "action": "update_form", "data": {{{{ "Tab": "Gacha Info", "Cost": "10" }}}} }}}},
      {{{{ "action": "save_form", "mode": "continue" }}}},
      {{{{ "action": "update_form", "data": {{{{ "Tab": "Milestones" }}}} }}}}
    ]"
    
    Ex 4: "User: "Bấm nút The Brick -> Tick chọn 'Hyper Blueprint' -> Bấm Process"
    JSON: [
      {{{{ "action": "process_deployment", "options": ["Hyper Blueprint"] }}}}
    ]"
    
    Ex 5: "Clone EventGacha_ABC -> New ID: test_1, gate: feb2026_live, chọn radio Use another currency, currency: GachaShard_XYZ"
    JSON: [
      {{{{ "action": "clone_row", "target": "EventGacha_ABC" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "New Event ID": "test_1",
          "Gate": "feb2026_live",
          "Use another currency": "select",
          "Currency": "GachaShard_XYZ"
      }}}} }}}},
      {{{{ "action": "save_form" }}}}
    ]
    
    Ex 6: "Edit BossEvent_ABC -> Acquire lock -> sửa gate: LiveOpsTest -> Save -> Click menu Boss Details -> sửa Wrestler ID: SS_TheRock"
    JSON: [
      {{{{ "action": "edit_row", "target": "BossEvent_ABC" }}}},
      {{{{ "action": "click", "target": "Acquire lock" }}}},
      {{{{ "action": "update_form", "data": {{{{ "Gate": "LiveOpsTest" }}}} }}}},
      {{{{ "action": "save_form" }}}},
      {{{{ "action": "click", "target": "Boss Details" }}}},
      {{{{ "action": "update_form", "data": {{{{ "Wrestler ID": "SS_TheRock" }}}} }}}}
    ]
    
    Ex 7: "Vào Scout Missions tab -> sửa Scout Phase Start Time: 2025-08-20 10:00, End Time: 2025-08-25 15:00 -> Save"
    JSON: [
      {{{{ "action": "click", "target": "Scout Missions" }}}},
      {{{{ "action": "update_form", "data": {{{{ 
          "Scout Phase Start Time": "2025-08-20 10:00",
          "End Time": "2025-08-25 15:00"
      }}}} }}}},
      {{{{ "action": "save_form" }}}}
    ]

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
        print(f"   ✅ Careful Mode: Đã tạo thành công {len(plan)} bước hành động.")

        # Auto-fix: Thêm bước Upload nếu thiếu
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


# ============================================================================
# MAIN ENTRY POINT - HYBRID PIPELINE
# ============================================================================


def parse_command_to_json(user_command, use_fast_mode=True, context_plan=None):
    """
    Main function - Chuyển đổi lệnh thành JSON Action Plan

    Args:
        user_command: Lệnh từ user (tiếng Việt hoặc English)
        use_fast_mode: True = Fast (1 model), False = Careful (2 models)
        context_plan: Kế hoạch trước đó (không dùng hiện tại)

    Returns:
        List[dict]: JSON Action Plan
    """
    print("\n🧠 AI Pipeline Started...")
    print(
        f"   📝 Command: {user_command[:80]}{'...' if len(user_command) > 80 else ''}"
    )

    # BƯỚC 1: Auto-detect complexity (chỉ khi dùng Fast Mode)
    if use_fast_mode:
        is_complex = detect_complexity(user_command)

        # Nếu phát hiện phức tạp, tự động chuyển sang Careful Mode
        if is_complex:
            print(
                "   ⚠️  Command phức tạp phát hiện! Tự động chuyển sang Careful Mode..."
            )
            use_fast_mode = False

    # BƯỚC 2: Chọn pipeline
    if use_fast_mode:
        plan = single_model_pipeline(user_command)

        # Auto-fallback: Nếu Fast Mode thất bại, tự động chuyển sang Careful Mode
        if not plan or len(plan) == 0:
            print("   ⚠️  Fast Mode failed! Auto-switching to Careful Mode...")
            plan = dual_model_pipeline(user_command)
    else:
        plan = dual_model_pipeline(user_command)

    # BƯỚC 3: Auto-fix nếu cần
    if (
        plan
        and plan[-1].get("action") == "manipulate_csv"
        and "Import" in user_command
        and not any(step.get("action") == "upload" for step in plan)
    ):
        print("   🔧 Auto-fix: Adding missing Upload step.")
        target_file = plan[-1].get("target")
        plan.append({"action": "upload", "target": "Import CSV", "value": target_file})

    return plan

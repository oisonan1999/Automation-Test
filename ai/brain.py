# ai/brain.py - OPTIMIZED VERSION với Hybrid Pipeline
# Logic chính: Pipeline gọi AI, parse JSON, điều phối Fast/Careful mode
# Prompts được tách ra prompts.py, action fixing được tách ra action_fixer.py
import os
import json
import re
import requests
from dotenv import load_dotenv

from ai.prompts import get_fast_mode_prompt, get_reasoning_prompt, get_formatting_prompt
from ai.action_fixer import fix_action_plan

load_dotenv()

# Module-level variable to track the actual mode used in the last parse
last_actual_mode = "fast"

# === CONFIGURATION ===
MODEL_REASONING = "deepseek-r1:8b"  # 8B: 19.7 tok/s vs 14B: 11.4 tok/s trên M4. Output chỉ là analysis text → 8B đủ chất lượng
MODEL_FORMATTING = "qwen2.5-coder:14b"  # Giữ 14B cho formatting vì cần JSON chính xác
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
SCENARIO_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "scenarios.json"
)


# ============================================================================
# HELPER FUNCTIONS
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
    # [FIX] Chỉ thay thế khi {{ bao quanh identifier/text (f-string style), KHÔNG được thay }}
    # trong JSON hợp lệ vì "}}" là 2 closing braces của nested objects (VD: "data":{...}})
    # Thay "{{word}}" → "{word}" (chỉ fix f-string templates thực sự)
    text = re.sub(r"\{\{([^{}]+)\}\}", r"{\1}", text)

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

    # 7. [NEW] Fix LLM merging two fields: "val1 - Key2":"val2" → "val1","Key2":"val2"
    # Xảy ra khi LLM viết nhầm: "Start Time UTC":"07:00 - End Time UTC":"07:15"
    # mà đúng phải là:          "Start Time UTC":"07:00","End Time UTC":"07:15"
    # Pattern: SPACE DASH SPACE [TitleCase key name] QUOTE COLON QUOTE
    # Dấu hiệu nhận biết: chuỗi kết thúc bằng [TitleCase]":"  → rõ ràng là key JSON bị chèn vào value
    text = re.sub(r' - ([A-Z][A-Za-z0-9 ()]+)"(\s*:\s*")', r'","\1"\2', text)

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


def call_ollama(model_name, prompt, stream=False, optimized=False, careful_phase=None):
    """
    Hàm gọi API Ollama

    Args:
        model_name: Tên model
        prompt: Prompt text
        stream: Streaming mode
        optimized: Nếu True, dùng config nhanh hơn (Fast Mode)
        careful_phase: "reasoning" | "formatting" - Tối ưu cho từng phase của Careful Mode
    """
    # Config mặc định (Careful Mode legacy)
    options = {
        "temperature": 0.1,
        "num_ctx": 2867,
        "num_gpu": 99,
    }

    # Config tối ưu cho Careful Mode - Reasoning Phase (DeepSeek-R1:8b)
    if careful_phase == "reasoning":
        options = {
            "temperature": 0.1,
            "num_ctx": 4096,  # Đủ cho reasoning prompt (~2k tokens)
            "num_predict": 1024,  # ⬇️ Giảm từ 2048: <think>~500 + analysis~300 = ~800 tokens là đủ
            "num_gpu": 99,
            "num_batch": 1024,  # Prompt processing nhanh hơn trên Apple Silicon M4
        }
    # Config tối ưu cho Careful Mode - Formatting Phase (Qwen2.5-Coder)
    elif careful_phase == "formatting":
        options = {
            "temperature": 0.1,
            "num_ctx": 8192,  # ⬆️ Đủ cho formatting prompt lớn (~6k tokens)
            "num_predict": 4096,  # Đủ cho JSON output
            "num_gpu": 99,
            "num_batch": 1024,  # ⬆️ Xử lý prompt nhanh hơn trên Apple Silicon M4
        }
    # Config tối ưu tốc độ (Fast Mode)
    elif optimized:
        options = {
            "temperature": 0.0,  # Set to 0 for strict adherence to rules
            "num_ctx": 8192,  # Đủ chứa Fast Mode prompt (~4k tokens) + output
            "num_predict": 1024,  # ⬇️ Giảm từ 4096: max output ~400-600 tokens cho lệnh đơn giản
            "num_gpu": 99,
            "num_batch": 1024,  # Xử lý prompt nhanh hơn trên Apple Silicon M4
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


def ensure_clean_context():
    """
    Force-unload tất cả model đang loaded để đảm bảo lần load tiếp theo
    dùng đúng num_ctx từ request (không bị kế thừa context 131K từ lần load trước).

    VẤN ĐỀ GỐC: Nếu model đã load với num_ctx=131072 (default),
    Ollama có thể giữ allocation đó cho các request sau dù num_ctx nhỏ hơn.
    → KV cache 131K chiếm ~20GB trên model 8B/14B → swap → chậm 10x.
    """
    try:
        response = requests.get("http://localhost:11434/api/ps")
        if response.status_code == 200:
            models = response.json().get("models", [])
            for m in models:
                ctx = m.get("context_length", 0)
                name = m.get("name", "")
                if ctx > 16384:  # Model đang load với context quá lớn (131K default)
                    print(
                        f"   ⚠️  Model {name} loaded với context={ctx} (quá lớn!) → Force unload..."
                    )
                    unload_model(name)
                # ✅ KHÔNG unload nữa nếu model đang ở ctx hợp lý (8192):
                # Unload mọi lần = cold-start mỗi request = tốn 15-30s reload từ disk!
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
    # PHÂN LOẠI: Từ dài (>= 4 ký tự) dùng substring match, từ ngắn dùng word boundary regex
    # để tránh false positive (ví dụ: "or" match trong "Normal", "Tournament")

    # Từ khóa dài - an toàn dùng substring match
    long_keywords = [
        "nếu",
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
        "và nếu",
        "and if",
        "lặp lại",
        "repeat",
        "loop",
    ]

    # Từ khóa ngắn - PHẢI dùng word boundary regex để tránh match trong từ khác
    # "or" match "Normal/Tournament", "if" match "notify/modify"
    short_keyword_patterns = [
        r"\bor\b",  # "or" nhưng KHÔNG match "Normal", "Tournament", "Leaderboard"
        r"\bif\b",  # "if" nhưng KHÔNG match "notify", "modify", "config"
    ]

    has_long_keyword = any(kw in command_lower for kw in long_keywords)
    has_short_keyword = any(
        re.search(pat, command_lower) for pat in short_keyword_patterns
    )
    has_complex_logic = has_long_keyword or has_short_keyword

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
        # Debug: Hiển thị keyword nào trigger
        trigger_details = []
        if has_complex_logic:
            matched_long = [kw for kw in long_keywords if kw in command_lower]
            matched_short = [
                pat for pat in short_keyword_patterns if re.search(pat, command_lower)
            ]
            trigger_details.append(f"logic_keywords={matched_long + matched_short}")
        if many_steps:
            trigger_details.append(f"steps={num_steps}")
        if is_very_long:
            trigger_details.append(f"len={len(user_command)}")
        if many_actions:
            trigger_details.append(f"actions={action_count}")
        print(f"   🔍 Complexity Detection: COMPLEX ({', '.join(trigger_details)})")
    else:
        print(
            f"   🔍 Complexity Detection: SIMPLE (steps={num_steps}, len={len(user_command)}, actions={action_count})"
        )

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

    # Đảm bảo không có model nào đang load với context khổng lồ
    ensure_clean_context()

    prompt = get_fast_mode_prompt(user_command)

    # Gọi model với config tối ưu (temperature=0 để less creative)
    json_output = call_ollama(MODEL_FORMATTING, prompt, optimized=True)
    # ✅ KHÔNG unload sau Fast Mode: giữ model warm cho request tiếp theo
    # (Careful Mode sẽ tự unload khi cần VRAM cho DeepSeek-R1)

    if not json_output:
        return []

    # [DEBUG] Print raw model output to see what AI generated
    print(f"\n   🔍 DEBUG - RAW MODEL OUTPUT (first 800 chars):")
    print(f"   {json_output[:800]}...")

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
    Pipeline cẩn thận - Dùng 2 models (DeepSeek-R1:8b + Qwen2.5-Coder:14b)
    Thời gian dự kiến: ~40-60 giây (M4 24GB)
    """
    print(f"   🧠 CAREFUL MODE: Dual-model pipeline")

    # CRITICAL: Force-unload models có context lớn để tránh swap (131K ctx = 25GB!)
    ensure_clean_context()

    # =========================================================================
    # BƯỚC 1: SUY LUẬN (REASONING PHASE) - Model: DeepSeek-R1:8b
    # =========================================================================
    print(f"   1️⃣  DeepSeek-R1 are currently analyzing the requirements...")

    reasoning_prompt = get_reasoning_prompt(user_command)

    # Gọi DeepSeek-R1:8b với config tối ưu cho reasoning phase
    raw_analysis = call_ollama(
        MODEL_REASONING, reasoning_prompt, careful_phase="reasoning"
    )
    # Unload reasoning model ngay sau khi xong để nhường VRAM cho formatting model
    # R1:8b (5.2GB) + Qwen:14b (9GB) = 14.2GB + KV caches có thể gây memory pressure
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

    formatting_prompt = get_formatting_prompt(user_command, analysis_clean)

    # Gọi Qwen với config tối ưu cho formatting phase
    json_output = call_ollama(
        MODEL_FORMATTING, formatting_prompt, careful_phase="formatting"
    )
    # Unload formatting model sau khi xong
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
    global last_actual_mode

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
        last_actual_mode = "fast"
        plan = single_model_pipeline(user_command)

        # Auto-fallback: Nếu Fast Mode thất bại, tự động chuyển sang Careful Mode
        if not plan or len(plan) == 0:
            print("   ⚠️  Fast Mode failed! Auto-switching to Careful Mode...")
            last_actual_mode = "careful"
            plan = dual_model_pipeline(user_command)
    else:
        last_actual_mode = "careful"
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

    # BƯỚC 4: POST-PROCESSING - Fix invalid action names (CRITICAL)
    print("\n   🔧 POST-PROCESSING: Fixing AI action names...")
    plan = fix_action_plan(plan, user_command)

    # DEBUG: Print FULL plan để kiểm tra
    print("\n" + "=" * 60)
    print("🔍 DEBUG - FINAL FIXED PLAN:")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    print("=" * 60 + "\n")

    return plan

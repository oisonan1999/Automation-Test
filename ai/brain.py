# ai/brain.py - OPTIMIZED VERSION với Hybrid Pipeline
# Logic chính: Pipeline gọi AI, parse JSON, điều phối Fast/Careful mode
# Prompts được tách ra prompts.py, action fixing được tách ra action_fixer.py
import os
import json
import re
import time
from copy import deepcopy
import requests
from dotenv import load_dotenv

try:
    import anthropic
except ImportError:
    anthropic = None

from ai.prompts import (
    get_fast_mode_prompt,
    get_reasoning_prompt,
    get_formatting_prompt,
    get_patch_prompt,
)
from ai.action_fixer import fix_action_plan

load_dotenv()

# Module-level variable to track the actual mode used in the last parse
last_actual_mode = "fast"

# Periodic model reload: force-unload after this many formatting calls to clear VRAM fragmentation.
_RELOAD_EVERY_N_CALLS = 15
_formatting_call_count = 0

# === CONFIGURATION ===
# MODEL_REASONING = "deepseek-r1:8b"  # Unused: dual-model pipeline disabled (Qwen alone = 100% correct)
MODEL_FORMATTING = "qwen3:8b"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

# Careful Mode (Claude API) — opt-in alternative to the Ollama fast pipeline
MODEL_CLAUDE_CAREFUL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Mushigen gateway (internal AI control plane) — same Bedrock-passthrough env
# vars Claude Code CLI uses. When CLAUDE_CODE_USE_BEDROCK=1, call_claude() talks
# to ANTHROPIC_BEDROCK_BASE_URL with a bearer token instead of api.anthropic.com.
# Rollback: unset CLAUDE_CODE_USE_BEDROCK and set ANTHROPIC_API_KEY in .env.
CLAUDE_USE_BEDROCK_GATEWAY = os.getenv("CLAUDE_CODE_USE_BEDROCK") == "1"
ANTHROPIC_BEDROCK_BASE_URL = os.getenv("ANTHROPIC_BEDROCK_BASE_URL")
ANTHROPIC_AUTH_TOKEN = os.getenv("ANTHROPIC_AUTH_TOKEN")
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
    return True


def delete_scenarios(names):
    """Xóa một hoặc nhiều kịch bản khỏi scenarios.json. Trả về số kịch bản đã xóa."""
    if not names:
        return 0
    data = load_scenarios()
    deleted = 0
    for name in names:
        key = str(name).strip()
        if key and key in data:
            del data[key]
            deleted += 1
    if deleted:
        with open(SCENARIO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return deleted


def _normalize_command_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def clean_json_string(text):
    """
    Hàm làm sạch chuỗi JSON (Nuclear Cleaning):
    Loại bỏ mọi thứ không phải là cú phápJSON hợp lệ để tránh lỗi parse.
    """
    if not text:
        return "[]"

    # 0. [CRITICAL] Fix double braces từ LLM ({{ -> {, }} -> })
    # LLM hay copy pattern từ f-string examples và trả về {{ }} thay vì { }
    # Nếu text chứa {{ thì TOÀN BỘ output đang ở "double-brace mode" — thay thế tất cả.
    # Valid JSON không bao giờ có {{ nên phát hiện {{ là đủ để kích hoạt fix toàn cục.
    if "{{" in text:
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

    # 6b. [NEW] Quote bare/unquoted object keys (Fix lỗi LLM đôi khi "quên" quote key
    # khi copy một object tương tự object trước đó trong cùng list, ví dụ:
    # {"action":"manipulate_csv",...} rồi tới {action:"manipulate_csv",...} (thiếu quote).
    # Chỉ match khi key đứng ngay sau { hoặc , VÀ theo sau : là một JSON value hợp lệ
    # (", [, {, số, true/false/null) — tránh việc quote nhầm nội dung text tự do
    # bên trong một string value (vd "Attempt: 10000" không bị đụng tới).
    text = re.sub(
        r'([{,])(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:\s*)(?=["\[{]|-?\d|true\b|false\b|null\b)',
        r'\1\2"\3"\4',
        text,
    )

    # 7. [NEW] Fix LLM merging two fields: "val1 - Key2":"val2" → "val1","Key2":"val2"
    # Xảy ra khi LLM viết nhầm: "Start Time UTC":"07:00 - End Time UTC":"07:15"
    # mà đúng phải là:          "Start Time UTC":"07:00","End Time UTC":"07:15"
    # Pattern: SPACE DASH SPACE [TitleCase key name] QUOTE COLON QUOTE
    # Dấu hiệu nhận biết: chuỗi kết thúc bằng [TitleCase]":"  → rõ ràng là key JSON bị chèn vào value
    text = re.sub(r' - ([A-Z][A-Za-z0-9 ()]+)"(\s*:\s*")', r'","\1"\2', text)

    # 7b. [NEW] Fix LLM merging two fields: "val1, Key2":"val2" → "val1","Key2":"val2"
    # Xảy ra khi lệnh có dạng "Field1: val1, Field2: val2" mà LLM gom thành một value:
    # "Superstars or Groups":"Body_OOsbourne, Attempt":"10000" (SAI)
    # → "Superstars or Groups":"Body_OOsbourne","Attempt":"10000" (ĐÚNG)
    # Pattern: COMMA SPACE [TitleCase key name] QUOTE COLON QUOTE
    text = re.sub(r', ([A-Z][A-Za-z0-9 ()]+)"(\s*:\s*")', r'","\1"\2', text)

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
    Hàm gọi API Ollama với timing instrumentation

    Args:
        model_name: Tên model
        prompt: Prompt text
        stream: Streaming mode
        optimized: Nếu True, dùng config nhanh hơn (Fast Mode)
        careful_phase: "reasoning" | "formatting" - Tối ưu cho từng phase của Careful Mode

    Returns:
        str: Response text (None nếu lỗi)
    """
    # Config mặc định (Careful Mode legacy)
    options = {
        "temperature": 0.1,
        "num_ctx": 2867,
        "num_gpu": 99,
    }

    # Config tối ưu cho Careful Mode - Formatting Phase (Qwen3)
    # (Reasoning phase / DeepSeek disabled — Qwen single-model pipeline only)
    if careful_phase == "formatting":
        options = {
            "temperature": 0.0,  # 0.0 = hoàn toàn deterministic → JSON nhất quán hơn qua nhiều lần gọi
            "num_ctx": 20480,  # ⬆️ Tăng từ 12288: prompt eval thực tế ~12258 tokens → cần buffer ~8k cho output
            "num_predict": 2048,  # ✅ Giảm từ 4096: JSON output thực tế không bao giờ vượt 1500 tokens
            # Anti-degeneration: greedy decoding (temp=0) can lock into an infinite
            # repetition loop (e.g. the model emitting the same {"action":...} object
            # 50+ times). repeat_penalty over a short window breaks the loop while
            # leaving genuinely-varied multi-step JSON untouched.
            "repeat_penalty": 1.2,
            "repeat_last_n": 64,
            "num_gpu": 99,
            "num_batch": 2048,
            "flash_attn": True,
        }
    # Config tối ưu tốc độ (Fast Mode)
    elif optimized:
        options = {
            "temperature": 0.0,
            "num_ctx": 6144,    # ⬇️ Từ 12288: prompt thực tế ~1750 tokens max → KV cache nhỏ hơn 2x → ~30-40% nhanh hơn
            "num_predict": 1200, # ⬇️ Từ 1500: JSON output không bao giờ vượt 1000 tokens
            # Anti-degeneration: see formatting-phase note above — breaks the greedy
            # repetition loop that produced 50× duplicated import steps.
            "repeat_penalty": 1.2,
            "repeat_last_n": 64,
            "num_gpu": 99,
            "num_batch": 2048,
            "flash_attn": True,
        }

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": stream,
        "options": options,
        # keep_alive: Giữ model trong VRAM để tận dụng Prompt Prefix KV Caching
        # Lần gọi đầu: prompt eval ~84s (full 7715 tokens)
        # Lần gọi sau: prompt eval ~1-5s (chỉ eval phần user command mới)
        "keep_alive": "10m",
        # think=False: Qwen3 has a "thinking" mode that emits a <think>...</think>
        # reasoning block before the answer. We need raw JSON only — the chain-of-
        # thought would break clean_json_string's parsing AND add latency for no
        # benefit on this deterministic template-filling task. Ignored harmlessly
        # by models without "thinking" capability (e.g. qwen2.5-coder).
        "think": False,
    }

    wall_start = time.time()
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        wall_elapsed = time.time() - wall_start

        if response.status_code == 200:
            data = response.json()
            response_text = data.get("response", "")

            # === TIMING METRICS từ Ollama API (nanoseconds → seconds) ===
            total_ns = data.get("total_duration", 0)
            load_ns = data.get("load_duration", 0)
            prompt_eval_ns = data.get("prompt_eval_duration", 0)
            eval_ns = data.get("eval_duration", 0)
            prompt_tokens = data.get("prompt_eval_count", 0)
            output_tokens = data.get("eval_count", 0)

            total_s = total_ns / 1e9
            load_s = load_ns / 1e9
            prompt_eval_s = prompt_eval_ns / 1e9
            eval_s = eval_ns / 1e9

            # Tính tokens/sec
            prompt_tps = prompt_tokens / prompt_eval_s if prompt_eval_s > 0 else 0
            output_tps = output_tokens / eval_s if eval_s > 0 else 0

            # Hiển thị timing report
            phase_label = careful_phase or ("fast" if optimized else "default")
            print(f"\n   ⏱️  TIMING [{model_name}] ({phase_label}):")
            print(f"      Model load:    {load_s:6.2f}s")
            print(
                f"      Prompt eval:   {prompt_eval_s:6.2f}s ({prompt_tokens} tokens → {prompt_tps:.1f} tok/s)"
            )
            print(
                f"      Generation:    {eval_s:6.2f}s ({output_tokens} tokens → {output_tps:.1f} tok/s)"
            )
            print(f"      Total (API):   {total_s:6.2f}s")
            print(f"      Total (wall):  {wall_elapsed:6.2f}s")

            return response_text
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
    Force-unload models loaded với context quá lớn (131K default → swap → chậm 10x).
    KHÔNG unload khi ctx hợp lý — giữ warm để tận dụng prompt-prefix KV caching.
    """
    try:
        response = requests.get("http://localhost:11434/api/ps")
        if response.status_code == 200:
            models = response.json().get("models", [])
            for m in models:
                ctx = m.get("context_length", 0)
                name = m.get("name", "")
                if ctx > 24576:
                    print(
                        f"   ⚠️  Model {name} loaded với context={ctx} (quá lớn!) → Force unload..."
                    )
                    unload_model(name)
    except:
        pass


def _maybe_periodic_reload():
    """
    Sau mỗi _RELOAD_EVERY_N_CALLS lần gọi formatting model, force-unload tất cả
    để giải phóng VRAM fragmentation tích lũy qua nhiều session calls.
    Model sẽ cold-start lần tiếp theo (~15-30s) nhưng VRAM sạch hoàn toàn.
    """
    global _formatting_call_count
    _formatting_call_count += 1
    if _formatting_call_count >= _RELOAD_EVERY_N_CALLS:
        print(
            f"   🔄 PERIODIC RELOAD: {_formatting_call_count} calls reached "
            f"(threshold={_RELOAD_EVERY_N_CALLS}) → force-unloading all models..."
        )
        unload_model(MODEL_FORMATTING)
        _formatting_call_count = 0


# ============================================================================
# SINGLE MODEL PIPELINE
# ============================================================================


def single_model_pipeline(user_command):
    """
    Pipeline nhanh - Chỉ dùng 1 model (Qwen3)
    """
    print(f"   ⚡ FAST MODE: Single-model pipeline")
    pipeline_start = time.time()

    # Đảm bảo không có model nào đang load với context khổng lồ
    _maybe_periodic_reload()
    ensure_clean_context()

    prompt = get_fast_mode_prompt(user_command)

    json_output = call_ollama(MODEL_FORMATTING, prompt, optimized=True)
    # Keep model warm: Prompt prefix KV caching reduces prompt eval from ~84s → 1-5s next call

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
        pipeline_elapsed = time.time() - pipeline_start
        print(
            f"   ✅ Fast Mode: Tạo thành công {len(plan)} bước ({pipeline_elapsed:.1f}s total)"
        )
        return plan
    except json.JSONDecodeError as e:
        print(f"   ❌ Fast Mode Parse Error: {e}")
        print(f"   Raw (first 500): {json_output[:500]}...")
        if len(final_json_str) < 2000:
            print(f"   📝 Cleaned:\n{final_json_str}")

        # Retry once: flush VRAM fragmentation then call again
        print("   🔄 Retry Fast Mode (fresh context)...")
        unload_model(MODEL_FORMATTING)
        time.sleep(1)
        json_output_retry = call_ollama(MODEL_FORMATTING, prompt, optimized=True)
        if json_output_retry:
            retry_str = clean_json_string(json_output_retry)
            try:
                plan_retry = json.loads(retry_str)
                print(f"   ✅ Fast Mode retry OK: {len(plan_retry)} bước")
                return plan_retry
            except json.JSONDecodeError:
                print("   ❌ Qwen retry failed → returning empty plan")
        return []


# ============================================================================
# CAREFUL MODE PIPELINE (Claude API)
# ============================================================================


def _call_claude_via_mushigen(prompt, model_name, wall_start):
    """
    Gọi Claude qua Mushigen (Bedrock-shaped gateway) — cùng cơ chế
    ANTHROPIC_BEDROCK_BASE_URL + ANTHROPIC_AUTH_TOKEN mà Claude Code CLI dùng.
    Trả về response text, hoặc None nếu request lỗi.
    """
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}],
    }
    # "effort" 400s on Haiku 4.5 (only Fable 5 / Opus / Sonnet 5 / Sonnet 4.6
    # support it) and Haiku isn't built for deep adaptive thinking — only
    # send these on the larger models that actually support them.
    if "haiku" not in model_name:
        body["thinking"] = {"type": "adaptive"}
        body["output_config"] = {"effort": "high"}
    try:
        resp = requests.post(
            f"{ANTHROPIC_BEDROCK_BASE_URL}/model/{model_name}/invoke",
            headers={
                "Authorization": f"Bearer {ANTHROPIC_AUTH_TOKEN}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()
        wall_elapsed = time.time() - wall_start
        text = next(
            (b["text"] for b in data.get("content", []) if b.get("type") == "text"),
            "",
        )
        usage = data.get("usage", {})
        print(f"\n   ⏱️  TIMING [{model_name}] (careful/claude via mushigen):")
        print(f"      Total (wall):  {wall_elapsed:6.2f}s")
        print(
            f"      Tokens: in={usage.get('input_tokens')} out={usage.get('output_tokens')} "
            f"cache_read={usage.get('cache_read_input_tokens', 0)}"
        )
        return text
    except Exception as e:
        print(f"❌ Claude API Error via Mushigen ({model_name}): {e}")
        return None


def call_claude(prompt, model_name=None):
    """
    Gọi Claude API cho Careful Mode.
    Ưu tiên Mushigen (CLAUDE_CODE_USE_BEDROCK=1); fallback SDK 'anthropic' gọi
    thẳng api.anthropic.com nếu có ANTHROPIC_API_KEY. Trả về response text,
    hoặc None nếu thiếu config/SDK hoặc lỗi request.
    """
    model_name = model_name or MODEL_CLAUDE_CAREFUL
    wall_start = time.time()

    if CLAUDE_USE_BEDROCK_GATEWAY and ANTHROPIC_BEDROCK_BASE_URL and ANTHROPIC_AUTH_TOKEN:
        return _call_claude_via_mushigen(prompt, model_name, wall_start)

    if anthropic is None:
        print(
            "   ❌ Careful Mode (Claude): package 'anthropic' chưa được cài. "
            "Chạy: pip install anthropic"
        )
        return None
    if not ANTHROPIC_API_KEY:
        print(
            "   ❌ Careful Mode (Claude): thiếu ANTHROPIC_API_KEY trong .env "
            "(hoặc thiếu CLAUDE_CODE_USE_BEDROCK/ANTHROPIC_BEDROCK_BASE_URL/"
            "ANTHROPIC_AUTH_TOKEN cho Mushigen)"
        )
        return None

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        # "effort" 400s on Haiku 4.5 (only Fable 5 / Opus / Sonnet 5 / Sonnet 4.6
        # support it) and Haiku isn't built for deep adaptive thinking — only
        # send these on the larger models that actually support them.
        kwargs = {}
        if "haiku" not in model_name:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": "high"}
        response = client.messages.create(
            model=model_name,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        wall_elapsed = time.time() - wall_start
        text = next((b.text for b in response.content if b.type == "text"), "")

        usage = response.usage
        print(f"\n   ⏱️  TIMING [{model_name}] (careful/claude):")
        print(f"      Total (wall):  {wall_elapsed:6.2f}s")
        print(
            f"      Tokens: in={usage.input_tokens} out={usage.output_tokens} "
            f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)}"
        )
        return text
    except Exception as e:
        print(f"❌ Claude API Error ({model_name}): {e}")
        return None


def claude_careful_pipeline(user_command):
    """
    Careful Mode - Dùng Claude (Anthropic API) thay cho Qwen để tăng độ chính xác
    khi hiểu lệnh tiếng Việt phức tạp và format JSON đúng schema.
    Fallback về Fast Mode (Qwen) nếu Claude lỗi (thiếu key, network, parse fail 2 lần).
    """
    print(f"   🧪 CAREFUL MODE (Claude): {MODEL_CLAUDE_CAREFUL}")
    pipeline_start = time.time()

    prompt = get_fast_mode_prompt(user_command)
    raw_output = call_claude(prompt)

    if not raw_output:
        print("   ⚠️  Careful Mode (Claude) không khả dụng → fallback Fast Mode (Qwen3).")
        return single_model_pipeline(user_command)

    print(f"\n   🔍 DEBUG - RAW CLAUDE OUTPUT (first 800 chars):")
    print(f"   {raw_output[:800]}...")

    final_json_str = clean_json_string(raw_output)
    try:
        plan = json.loads(final_json_str)
        pipeline_elapsed = time.time() - pipeline_start
        print(
            f"   ✅ Careful Mode (Claude): Tạo thành công {len(plan)} bước ({pipeline_elapsed:.1f}s total)"
        )
        return plan
    except json.JSONDecodeError as e:
        print(f"   ❌ Careful Mode (Claude) Parse Error: {e}")
        print(f"   Raw (first 500): {raw_output[:500]}...")

        print("   🔄 Retry Careful Mode (Claude)...")
        retry_output = call_claude(prompt)
        if retry_output:
            retry_str = clean_json_string(retry_output)
            try:
                plan_retry = json.loads(retry_str)
                print(f"   ✅ Careful Mode (Claude) retry OK: {len(plan_retry)} bước")
                return plan_retry
            except json.JSONDecodeError:
                print("   ❌ Careful Mode (Claude) retry cũng fail.")

        print("   ⚠️  Falling back to Fast Mode (Qwen3).")
        return single_model_pipeline(user_command)


def patch_model_pipeline(user_command, base_command, base_plan):
    """
    Pipeline patch cho scenario đã load sẵn.
    Chỉ dùng 1 model để sửa plan hiện có thay vì chạy lại reasoning + formatting.
    """
    print(f"   🩹 PATCH MODE: Reusing loaded scenario plan")
    pipeline_start = time.time()

    ensure_clean_context()

    patch_prompt = get_patch_prompt(user_command, base_command, base_plan)
    json_output = call_ollama(MODEL_FORMATTING, patch_prompt, optimized=True)

    if not json_output:
        print("   ❌ Patch Mode failed: empty response.")
        return []

    print(f"\n   🔍 DEBUG - RAW PATCH OUTPUT (first 600 chars):")
    print(f"   {json_output[:600]}...")

    final_json_str = clean_json_string(json_output)

    try:
        plan = json.loads(final_json_str)
        pipeline_elapsed = time.time() - pipeline_start
        print(
            f"   ✅ Patch Mode: Đã tạo thành công {len(plan)} bước hành động ({pipeline_elapsed:.1f}s total)"
        )
        return plan
    except json.JSONDecodeError as e:
        print(f"   ❌ Patch Mode Parse Error: {e}")
        print(f"   Raw output: {json_output}")
        print(f"   Cleaned output: {final_json_str[:800]}...")
        return []


# ============================================================================
# MAIN ENTRY POINT - HYBRID PIPELINE
# ============================================================================


def _inject_current_date(user_command: str) -> str:
    """
    Replace date placeholders with today's date before the AI pipeline sees the command.
    Used in smoke-test CSV files so end-time dates are always "current day", not stale.

    Tokens:
      {{TODAY_ISO}}  → YYYY-MM-DD   (for RBE / Gacha: "2026-07-08 11:00")
      {{TODAY_MDY}}  → MM/DD/YYYY   (for Offer / PVE / SD / FF / Grabbag: "07/08/2026 11:00 AM")
    """
    import datetime as _dt

    if "{{TODAY" not in user_command:
        return user_command
    today = _dt.date.today()
    user_command = user_command.replace("{{TODAY_ISO}}", today.strftime("%Y-%m-%d"))
    user_command = user_command.replace("{{TODAY_MDY}}", today.strftime("%m/%d/%Y"))
    return user_command


def _inject_generated_ids(user_command: str, forced_id: str | None = None) -> str:
    """
    Preprocessing: replace 'hãy tự generate một ID duy nhất bắt đầu bằng <prefix>'
    with '<prefix>_<timestamp>_<random>' before the AI pipeline sees the command.
    Prevents the AI from reusing previously-seen IDs from its context window.

    If `forced_id` is given, use it verbatim instead of generating a fresh one.
    Callers (app.py) pre-generate an ID up front to look up/tokenize the golden
    plan cache; without this, brain.py would silently mint its OWN different ID
    here, the plan would end up with that (different) ID baked in, and golden
    tokenization would fail to find the caller's ID to replace with {{UNIQUE_ID}}
    — permanently freezing a stale, already-used ID into the golden template.
    """
    import datetime as _dt
    import uuid as _uuid

    # Count word ("một"/"1") and the "nhất"/"nhát" (typo) adjective both vary
    # across testcase authors — match loosely on structure instead of the
    # exact literal phrase, or rows using a different wording silently skip
    # ID injection and the AI copies the raw instruction into the plan.
    _pattern = re.compile(
        r"hãy tự generate\s+\S+\s+ID\s+duy\s+\S+\s+bắt đầu bằng\s+(\S+)",
        re.IGNORECASE,
    )

    def _make_id(match):
        token = match.group(1).strip()
        # Separate the prefix from any trailing punctuation so it stays in output
        m = re.match(r"^(.*?)([.,;]*)$", token)
        prefix = m.group(1) if m else token
        trailing = m.group(2) if m else ""
        if forced_id:
            return f"{forced_id}{trailing}"
        ts = _dt.datetime.now().strftime("%m%d%H%M%S")
        rnd = _uuid.uuid4().hex[:4]
        return f"{prefix}_{ts}_{rnd}{trailing}"

    result, count = _pattern.subn(_make_id, user_command)
    if count:
        print(f"   🔑 Auto-generated {count} unique ID(s) before AI processing")
    return result


def parse_command_to_json(
    user_command,
    use_fast_mode=True,
    context_plan=None,
    base_command=None,
    forced_unique_id=None,
):
    """
    Main function - Chuyển đổi lệnh thành JSON Action Plan

    Args:
        user_command: Lệnh từ user (tiếng Việt hoặc English)
        use_fast_mode: True = Fast Mode (Qwen local qua Ollama),
            False = Careful Mode (Claude API, fallback về Qwen nếu Claude lỗi)
        context_plan: Kế hoạch trước đó (nếu có)
        base_command: Câu lệnh gốc của scenario đã load (nếu có)
        forced_unique_id: ID caller đã pre-generate (vd để golden-cache lookup) —
            dùng ID này thay vì để _inject_generated_ids tự sinh ID khác, tránh
            lệch giữa ID thực trong plan và ID dùng để tokenize golden.

    Returns:
        List[dict]: JSON Action Plan
    """
    global last_actual_mode

    # Preprocess: replace date placeholders ({{TODAY_ISO}}/{{TODAY_MDY}}) then unique IDs
    user_command = _inject_current_date(user_command)
    user_command = _inject_generated_ids(user_command, forced_id=forced_unique_id)

    print("\n🧠 AI Pipeline Started...")
    print(
        f"   📝 Command: {user_command[:80]}{'...' if len(user_command) > 80 else ''}"
    )

    plan = []
    base_plan = context_plan if isinstance(context_plan, list) else None
    has_context = bool(base_plan and base_command)

    if has_context:
        base_norm = _normalize_command_text(base_command)
        user_norm = _normalize_command_text(user_command)

        if user_norm == base_norm:
            print("   ♻️  Loaded scenario unchanged → reuse existing plan without AI.")
            plan = deepcopy(base_plan)
            last_actual_mode = "context_reuse"
        else:
            print("   🩹 Loaded scenario modified → using patch pipeline.")
            plan = patch_model_pipeline(user_command, base_command, base_plan)
            last_actual_mode = "patch"

            if not plan:
                print("   ⚠️  Patch pipeline failed → fallback to normal AI pipeline.")
                has_context = False

    if not has_context:
        if use_fast_mode:
            last_actual_mode = "fast"
            plan = single_model_pipeline(user_command)
        else:
            last_actual_mode = "careful_claude"
            plan = claude_careful_pipeline(user_command)

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

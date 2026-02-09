# ai_brain.py - OPTIMIZED VERSION với Hybrid Pipeline
import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv()

# === CONFIGURATION ===
MODEL_REASONING = "deepseek-r1:14b"
MODEL_FORMATTING = "qwen2.5-coder:14b-instruct-q4_K_M"
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
            "temperature": 0.0,  # Set to 0 for strict adherence to rules
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
# POST-PROCESSING: FIX INVALID ACTION NAMES (Deterministic - 100% reliable)
# ============================================================================

# Mapping: invalid action name → valid action name
ACTION_NAME_MAP = {
    # Checkbox / Select variations
    "select_random_ids": "checkbox",
    "select_ids": "checkbox",
    "select_random": "checkbox",
    "check_checkbox": "checkbox",
    "select_checkbox": "checkbox",
    "tick_checkbox": "checkbox",
    "select_rows": "checkbox",
    "choose_ids": "checkbox",
    "pick_random": "checkbox",
    # Download / Export variations
    "export_csv": "download",
    "export": "download",
    "export_file": "download",
    "download_csv": "download",
    "download_file": "download",
    # Upload / Import variations
    "import_csv": "upload",
    "import": "upload",
    "import_file": "upload",
    "upload_csv": "upload",
    "upload_file": "upload",
    # Process / Deploy variations
    "click_logo": "process_deployment",
    "click_logo_the_brick": "process_deployment",
    "click_the_brick": "process_deployment",
    "click_brick": "process_deployment",
    "go_home": "process_deployment",
    "process": "process_deployment",
    "deploy": "process_deployment",
    # Click button variations
    "click_button": "click",
    "press_button": "click",
    "tap_button": "click",
    # Navigate variations
    "go_to": "navigate",
    "open_page": "navigate",
    "open_menu": "navigate",
    # Edit variations
    "edit": "edit_row",
    "edit_item": "edit_row",
    # Clone variations
    "clone": "clone_row",
    "clone_item": "clone_row",
    "duplicate": "clone_row",
    # Save variations
    "save": "save_form",
    # Smart test variations
    "test_cycle": "smart_test_cycle",
    "smart_test": "smart_test_cycle",
    "fuzz_test": "smart_test_cycle",
}

VALID_ACTIONS = {
    "navigate",
    "checkbox",
    "download",
    "upload",
    "manipulate_csv",
    "smart_test_cycle",
    "clone_row",
    "edit_row",
    "update_form",
    "save_form",
    "scan_tabs",
    "click",
    "select",
    "wait",
    "wait_for_page_load",
    "process_deployment",
}


def fix_action_plan(plan):
    """
    Post-process AI output: Fix invalid action names and field names.
    This is deterministic and 100% reliable regardless of what AI generates.
    """
    if not plan or not isinstance(plan, list):
        return plan

    fixed_plan = []
    last_filename = None  # Track filename for reuse

    for step in plan:
        if not isinstance(step, dict):
            continue

        action = step.get("action", "")

        # ============================================================
        # STEP 1: Fix action name
        # ============================================================
        if action in ACTION_NAME_MAP:
            old_action = action
            action = ACTION_NAME_MAP[action]
            step["action"] = action
            print(f"   🔧 AUTO-FIX: '{old_action}' → '{action}'")

        # ============================================================
        # STEP 2: Fix field names based on action type
        # ============================================================

        if action == "checkbox":
            # Fix: {count: 2} or {number: 2} → {target: "ID", value: "random_2"}
            if "count" in step:
                step["value"] = f"random_{step.pop('count')}"
            elif "number" in step:
                step["value"] = f"random_{step.pop('number')}"
            if "target" not in step:
                step["target"] = "ID"
            if "value" not in step and "label" in step:
                step["value"] = step.pop("label")
            # Fix: value rỗng → default random_1
            if not step.get("value") or str(step.get("value")).strip() == "":
                step["value"] = "random_1"
                print("   🔧 AUTO-FIX: checkbox value rỗng → random_1")

        elif action == "download":
            # Fix: {filename: "x.csv"} → {target: "Export CSV", value: "x.csv"}
            if "filename" in step:
                step["value"] = step.pop("filename")
            if "file" in step and "value" not in step:
                step["value"] = step.pop("file")
            if "target" not in step:
                step["target"] = "Export CSV"
            # Track filename for reuse
            if step.get("value"):
                last_filename = step["value"]

        elif action == "upload":
            # Fix: {filename: "x.csv"} → {target: "Import CSV", value: "x.csv"}
            if "filename" in step:
                step["value"] = step.pop("filename")
            if "file" in step and "value" not in step:
                step["value"] = step.pop("file")
            if "target" not in step:
                step["target"] = "Import CSV"
            # Reuse filename if empty
            if not step.get("value") and last_filename:
                step["value"] = last_filename
                print(f"   🔧 AUTO-FIX: Reused filename '{last_filename}' for upload")

        elif action == "smart_test_cycle":
            # Fix: {file: "x.csv"} → {value: "x.csv"}
            if "file" in step and "value" not in step:
                step["value"] = step.pop("file")
            if "filename" in step and "value" not in step:
                step["value"] = step.pop("filename")
            # Reuse filename if empty
            if not step.get("value") and last_filename:
                step["value"] = last_filename
                print(
                    f"   🔧 AUTO-FIX: Reused filename '{last_filename}' for smart_test_cycle"
                )
            # Track for next step
            if step.get("value"):
                last_filename = step["value"]

        elif action == "process_deployment":
            # Fix: {target: "The Brick"} → just process_deployment
            if "target" in step and step["target"] in (
                "The Brick",
                "logo The Brick",
                "logo",
            ):
                step.pop("target")
            if "options" not in step:
                step["options"] = []
            if "label" in step:
                # click_button label="Process" → already handled by process_deployment
                step.pop("label", None)

        elif action == "click":
            # Fix: {label: "X"} → {target: "X"}
            if "label" in step and "target" not in step:
                step["target"] = step.pop("label")

            # 🆕 Validate: Skip click actions with no target
            if not step.get("target") or not str(step.get("target")).strip():
                print(f"   🔧 FILTER: Skipping click action with empty target")
                continue

            # 🆕 DETECT: click("The Brick"/"logo") → process_deployment
            target_lower = str(step.get("target", "")).lower()
            brick_keywords = [
                "brick",
                "logo",
                "the brick",
                "brick logo",
                "logo the brick",
            ]

            if any(keyword in target_lower for keyword in brick_keywords):
                # Convert to process_deployment
                old_target = step.get("target")
                step["action"] = "process_deployment"
                step.pop("target", None)  # Remove target field
                step["options"] = step.get("options", [])  # Ensure options field exists
                print(f"   🔧 AUTO-FIX: click('{old_target}') → process_deployment")
                action = "process_deployment"  # Update action variable for subsequent processing

        elif action == "navigate":
            # Fix: {menu: [...]} → {path: [...]}
            if "menu" in step and "path" not in step:
                step["path"] = step.pop("menu")

        # Track download filenames
        if action == "download" and step.get("value"):
            last_filename = step["value"]

        # Skip unknown actions that can't be mapped
        if step.get("action") not in VALID_ACTIONS:
            print(
                f"   ⚠️ SKIP unknown action: '{step.get('action')}' (no mapping found)"
            )
            continue

        fixed_plan.append(step)

    # ============================================================
    # STEP 3: Merge consecutive process_deployment-related actions
    # Pattern: click_logo → select_checkbox(Offers) → click_button(Process)
    # Should become: process_deployment(options=["Offers"])
    # ============================================================
    merged_plan = _merge_process_deployment_steps(fixed_plan)

    # ============================================================
    # STEP 4: AUTO-INFER deployment options if empty
    # If process_deployment has no options, infer from context
    # ============================================================
    merged_plan = _auto_infer_deployment_options(merged_plan)

    if len(merged_plan) != len(plan):
        print(
            f"   🔧 AUTO-FIX: Plan {len(plan)} steps → {len(merged_plan)} steps after fix"
        )

    return merged_plan


def _auto_infer_deployment_options(plan):
    """
    Auto-infer deployment options from context if process_deployment has empty options.

    Context sources:
    1. Navigation path (e.g., "Offer" → infer "Offers")
    2. Uploaded filename (e.g., "gacha_*.csv" → infer "Gacha")
    3. Previous actions (e.g., after smart_test_cycle on table)
    """
    if not plan:
        return plan

    # Mapping từ keyword → deployment option name
    DEPLOYMENT_INFERENCE_MAP = {
        # Navigation paths
        "offer section": "Offers",
        "offer": "Offers",
        "shop tier": "Offers",
        "shop": "Offers",
        "gacha": "Gacha",
        "prize wall": "Prize Wall",
        "prizewall": "Prize Wall",
        "live event": "Live Events",
        "event": "Live Events",
        "perk": "Data Configs",
        "consumable": "Data Configs",
        "currency": "Data Configs",
        "config": "Data Configs",
        "blueprint": "Hyper Blueprint",
        # CSV filenames
        "gacha_": "Gacha",
        "offer_": "Offers",
        "section_": "Offers",
        "shop_": "Offers",
        "prize": "Prize Wall",
        "event_": "Live Events",
        "perk_": "Data Configs",
        "config_": "Data Configs",
    }

    result = []

    for i, step in enumerate(plan):
        action = step.get("action", "")

        # Check if this is a process_deployment with empty options
        if action == "process_deployment":
            options = step.get("options", [])

            if not options or len(options) == 0:
                print(
                    f"   🔍 AUTO-INFER: process_deployment has no options, analyzing context..."
                )

                inferred_option = None

                # Strategy 1: Look backward for navigation path
                for j in range(i - 1, max(-1, i - 10), -1):  # Check up to 10 steps back
                    prev_step = plan[j]
                    prev_action = prev_step.get("action", "")

                    if prev_action == "navigate":
                        path = prev_step.get("path", [])
                        path_str = " ".join(path).lower()

                        # Check each keyword
                        for keyword, option in DEPLOYMENT_INFERENCE_MAP.items():
                            if keyword in path_str:
                                inferred_option = option
                                print(
                                    f"      ✅ Inferred from navigation '{path}' → '{option}'"
                                )
                                break

                        if inferred_option:
                            break

                    # Strategy 2: Look for upload/smart_test_cycle filename
                    elif prev_action in ["upload", "smart_test_cycle", "download"]:
                        filename = prev_step.get("value", "")
                        if filename:
                            filename_lower = filename.lower()

                            for keyword, option in DEPLOYMENT_INFERENCE_MAP.items():
                                if keyword in filename_lower:
                                    inferred_option = option
                                    print(
                                        f"      ✅ Inferred from filename '{filename}' → '{option}'"
                                    )
                                    break

                            if inferred_option:
                                break

                # Apply inferred option
                if inferred_option:
                    step["options"] = [inferred_option]
                    print(
                        f"      🎯 AUTO-INFER: Added option '{inferred_option}' to process_deployment"
                    )
                else:
                    print(f"      ⚠️  Could not infer deployment option from context")
                    print(
                        f"      💡 Tip: Specify explicitly like 'Process với Offers' or 'Chọn Offers rồi Process'"
                    )

        result.append(step)

    return result


def _merge_process_deployment_steps(plan):
    """
    Merge patterns like:
      1. checkbox(Offers) → process_deployment → click(Process)

      2. process_deployment → checkbox(Offers) → click(Process)
    Into single:
      process_deployment(options=["Offers"])
    """
    if not plan:
        return plan

    # 🆕 DEBUG: Print plan before merge
    print(f"\n   📋 DEBUG - Plan BEFORE merge ({len(plan)} steps):")
    for idx, step in enumerate(plan):
        action = step.get("action", "?")
        target = step.get("target", "")
        value = step.get("value", "")
        options = step.get("options", [])
        if action == "process_deployment":
            print(f"      {idx}: {action} (options={options})")
        elif action == "checkbox":
            print(f"      {idx}: {action} (target={target}, value={value})")
        else:
            print(f"      {idx}: {action} (target={target})")

    merged = []
    i = 0
    while i < len(plan):
        step = plan[i]

        # Check if this starts a process_deployment sequence
        if step.get("action") == "process_deployment":
            options = list(step.get("options", []))

            # 🆕 Look BACKWARD for checkbox that should be merged
            # Pattern: checkbox(Offers) → process_deployment
            k = len(merged) - 1  # Start from last item in merged
            backward_count = 0
            items_to_remove = []  # Track indices to remove

            # Common deployment options keywords
            deployment_keywords = [
                "offers",
                "offer",
                "data configs",
                "data config",
                "live events",
                "live event",
                "hyper blueprint",
                "prize wall",
                "gacha",
                "shop",
                "store",
                "event",
                "config",
                "blueprint",
            ]

            while k >= 0 and backward_count < 3:  # Check up to 3 steps back
                prev_step = merged[k]
                prev_action = prev_step.get("action", "")

                # Check if it's a non-table checkbox (deployment option)
                if prev_action == "checkbox":
                    value = str(prev_step.get("value", ""))
                    target = prev_step.get("target", "")
                    checkbox_label = prev_step.get(
                        "checkbox_label", ""
                    )  # 🆕 AI sometimes uses this field
                    checkbox_field = prev_step.get(
                        "checkbox", ""
                    )  # 🆕 AI also uses "checkbox" field

                    # 🆕 SMART DETECTION: Check if this is a deployment option
                    is_deployment_option = False

                    # Check all possible fields that might contain deployment option name
                    fields_to_check = [
                        checkbox_field,  # Check "checkbox" field first!
                        checkbox_label,
                        target,
                        value,
                    ]

                    for field in fields_to_check:
                        if field:
                            field_lower = str(field).lower()
                            for keyword in deployment_keywords:
                                if keyword in field_lower:
                                    is_deployment_option = True
                                    break
                            if is_deployment_option:
                                break

                    # If not random_ OR is deployment option name, merge it
                    if (
                        not value.startswith("random_") and target != "ID"
                    ) or is_deployment_option:
                        # Prefer "checkbox" field (AI's new convention), then checkbox_label, then target, then value
                        opt = checkbox_field or checkbox_label or target or value
                        if opt and opt not in options:
                            options.insert(
                                0, opt
                            )  # Insert at beginning to preserve order
                            print(
                                f"   🔧 MERGE (backward): checkbox('{opt}') → process_deployment options"
                            )
                            items_to_remove.append(k)
                        k -= 1
                        backward_count += 1
                        continue

                # Stop if we hit a navigation or other major action
                if prev_action in [
                    "navigate",
                    "smart_test_cycle",
                    "upload",
                    "download",
                    "edit_row",
                    "clone_row",
                ]:
                    break

                k -= 1
                backward_count += 1

            # Remove absorbed checkboxes (in reverse order to maintain indices)
            for idx in sorted(items_to_remove, reverse=True):
                merged.pop(idx)

            # Look FORWARD for checkbox/click that should be merged
            j = i + 1
            while j < len(plan):
                next_step = plan[j]
                next_action = next_step.get("action", "")

                if next_action == "checkbox":
                    value = str(next_step.get("value", ""))
                    target = next_step.get("target", "")
                    checkbox_label = next_step.get(
                        "checkbox_label", ""
                    )  # 🆕 AI sometimes uses this field
                    checkbox_field = next_step.get(
                        "checkbox", ""
                    )  # 🆕 AI also uses "checkbox" field

                    # 🆕 SMART DETECTION: Check if this is a deployment option
                    # Use same keywords as backward merge
                    is_deployment_option = False

                    # Check all possible fields that might contain deployment option name
                    fields_to_check = [
                        checkbox_field,  # Check "checkbox" field first!
                        checkbox_label,
                        target,
                        value,
                    ]

                    for field in fields_to_check:
                        if field:
                            field_lower = str(field).lower()
                            for keyword in deployment_keywords:
                                if keyword in field_lower:
                                    is_deployment_option = True
                                    break
                            if is_deployment_option:
                                break

                    # If not random_ OR is deployment option name, merge it
                    if not value.startswith("random_") or is_deployment_option:
                        # Prefer "checkbox" field (AI's new convention), then checkbox_label, then target, then value
                        opt = checkbox_field or checkbox_label or target or value
                        if opt and opt != "ID" and opt not in options:
                            options.append(opt)
                        print(
                            f"   🔧 MERGE (forward): checkbox('{opt}') → process_deployment options"
                        )
                        j += 1
                    else:
                        # It's a table checkbox (random_X without deployment keyword)
                        break
                elif next_action == "click" and next_step.get("target", "").lower() in (
                    "process",
                    "deploy",
                    "bấm process",
                    "nút process",
                    "process button",
                    "button process",
                ):
                    # click(Process) → absorbed by process_deployment
                    print(
                        f"   🔧 MERGE: click('Process') → absorbed by process_deployment"
                    )
                    j += 1
                else:
                    break

            step["options"] = options

            # 🆕 Debug: Print final options
            if not options:
                print(
                    f"   ⚠️ WARNING: process_deployment has no options (will just click Process button)"
                )
            else:
                print(f"   ✅ process_deployment final options: {options}")

            merged.append(step)
            i = j
        else:
            merged.append(step)
            i += 1

    # 🆕 STEP 4: Filter out invalid/duplicate actions
    # Common deployment options keywords (reuse from merge logic)
    deployment_keywords = [
        "offers",
        "offer",
        "data configs",
        "data config",
        "live events",
        "live event",
        "hyper blueprint",
        "prize wall",
        "gacha",
        "shop",
        "store",
        "event",
        "config",
        "blueprint",
    ]

    filtered = []
    for idx, step in enumerate(merged):
        action = step.get("action", "")
        target = step.get("target", "")

        # Filter out click actions with empty/whitespace-only target
        if action == "click":
            if not target or not target.strip():
                print(f"   🔧 FILTER: Removing invalid click action (empty target)")
                continue

        # 🆕 Filter out orphaned deployment checkbox (checkbox that should have been merged)
        # If checkbox contains deployment keyword and value is NOT random_X, it's likely a duplicate
        if action == "checkbox":
            value = str(step.get("value", ""))
            checkbox_field = step.get("checkbox", "")
            checkbox_label = step.get("checkbox_label", "")

            # Check if this is a deployment option checkbox
            is_deployment_checkbox = False
            for field in [checkbox_field, checkbox_label, target, value]:
                if field:
                    field_lower = str(field).lower()
                    for keyword in deployment_keywords:
                        if keyword in field_lower and not value.startswith("random_"):
                            is_deployment_checkbox = True
                            break
                    if is_deployment_checkbox:
                        break

            # If it's a deployment checkbox, check if there's a process_deployment nearby
            if is_deployment_checkbox:
                # Look backward/forward for process_deployment within 2 steps
                has_nearby_process_deployment = False
                for j in range(max(0, idx - 2), min(len(merged), idx + 3)):
                    if j != idx and merged[j].get("action") == "process_deployment":
                        has_nearby_process_deployment = True
                        break

                if has_nearby_process_deployment:
                    deployment_opt = checkbox_field or checkbox_label or target or value
                    print(
                        f"   🔧 FILTER: Removing orphaned deployment checkbox('{deployment_opt}') - already merged"
                    )
                    continue

        filtered.append(step)

    # 🆕 DEBUG: Print plan after merge
    print(f"\n   📋 DEBUG - Plan AFTER merge ({len(filtered)} steps):")
    for idx, step in enumerate(filtered):
        action = step.get("action", "?")
        target = step.get("target", "")
        value = step.get("value", "")
        options = step.get("options", [])
        if action == "process_deployment":
            print(f"      {idx}: {action} (options={options})")
        elif action == "checkbox":
            print(f"      {idx}: {action} (target={target}, value={value})")
        else:
            print(f"      {idx}: {action}")

    return filtered


# ============================================================================
# SINGLE MODEL PIPELINE (Fast Mode)
# ============================================================================


def single_model_pipeline(user_command):
    """
    Pipeline nhanh - Chỉ dùng 1 model (Qwen2.5-Coder)
    Thời gian: ~20-40 giây
    """
    print(f"   ⚡ FAST MODE: Single-model pipeline")

    # FEW-SHOT LEARNING: Show 5 examples để model học pattern
    prompt = f"""You are a strict JSON converter. You MUST use action names from examples below.

CRITICAL: ONLY these action names are valid:
navigate, checkbox, download, upload, smart_test_cycle, process_deployment, clone_row, edit_row, update_form, save_form, click

LEARN FROM THESE 5 EXAMPLES (COPY the action names EXACTLY):

Example 1:
Input: "Vào Live Events -> Offer -> Offer Section -> Chọn 2 ID -> Export CSV test.csv"
Output: [{{"action":"navigate","path":["Live Events","Offer","Offer Section"]}},{{"action":"checkbox","target":"ID","value":"random_2"}},{{"action":"download","target":"Export CSV","value":"test.csv"}}]

Example 2:
Input: "Export CSV data.csv -> Smart test cycle data.csv -> Import CSV data.csv"
Output: [{{"action":"download","target":"Export CSV","value":"data.csv"}},{{"action":"smart_test_cycle","value":"data.csv"}},{{"action":"upload","target":"Import CSV","value":"data.csv"}}]

Example 3:
Input: "Click logo The Brick -> Chọn checkbox Offers -> Bấm Process"
Output: [{{"action":"process_deployment","options":["Offers"]}}]

Example 4:
Input: "Vào Data Configs -> Perk -> Edit ABC123"
Output: [{{"action":"navigate","path":["Data Configs","Perk"]}},{{"action":"edit_row","target":"ABC123"}}]

Example 5:
Input: "Clone EventGacha_ABC -> New ID: test_1, Gate: feb2026"
Output: [{{"action":"clone_row","target":"EventGacha_ABC"}},{{"action":"update_form","data":{{"New Event ID":"test_1","Gate":"feb2026"}}}},{{"action":"save_form"}}]

Example 6:
Input: "Vào Offer Section -> Chọn 2 ID -> Export test.csv -> Smart test -> Import -> Process"
Output: [{{"action":"navigate","path":["Live Events","Offer","Offer Section"]}},{{"action":"checkbox","target":"ID","value":"random_2"}},{{"action":"download","target":"Export CSV","value":"test.csv"}},{{"action":"smart_test_cycle","value":"test.csv"}},{{"action":"upload","target":"Import CSV","value":"test.csv"}},{{"action":"process_deployment","options":["Offers"]}}]

Example 7:
Input: "Bấm logo The Brick"
Output: [{{"action":"process_deployment","options":[]}}]

Example 8:
Input: "Click The Brick"
Output: [{{"action":"process_deployment","options":[]}}]

CRITICAL RULES:
- NEVER use {{"action":"click","target":"The Brick"}} or {{"action":"click","target":"logo"}}
- "Click The Brick", "Bấm logo", "Click logo" → ALWAYS use {{"action":"process_deployment","options":[]}}
- When user says "Process" after test/upload: Try to infer deployment option from navigation context
- If navigated to "Offer" area → use options:["Offers"]
- If navigated to "Gacha" area → use options:["Gacha"]  
- If navigated to "Live Events" → use options:["Live Events"]
- If unsure, leave options empty []

NOW CONVERT THIS COMMAND (use same action names as examples above):
"{user_command}"

Output ONLY JSON array:"""

    # Gọi model với config tối ưu (temperature=0 để less creative)
    json_output = call_ollama(MODEL_FORMATTING, prompt, optimized=True)
    unload_model(MODEL_FORMATTING)

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

    ⚠️ CRITICAL RULE #0 - ONLY USE THESE ACTIONS:
    You MUST ONLY use action names from this exact list. NO OTHER action names allowed:
    - navigate, checkbox, download, upload, manipulate_csv, smart_test_cycle
    - clone_row, edit_row, update_form, save_form, scan_tabs, click, wait, process_deployment
    
    INVALID action names (NEVER USE): select_random_ids, export_csv, import_csv, click_logo, select_checkbox, click_button ❌

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
    6. "smart_test_cycle": {{{{ "action": "smart_test_cycle", "value": "file.csv" }}}}
       - Use for: "smart test", "test cycle", "kiểm thử file".
       - Auto runs fuzz tests, uploads valid data, then navigates to Home.
       - After this, user may ask to select checkboxes and Process.
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
    3. **NO COMMENTS**: Do NOT output // or <!---->. If you do, the system will crash.
    4. **NO MARKDOWN**: No ```json tags.

    5. **FILE NAME REUSE** (CRITICAL):
       - "file csv đó", "file đó", "that file", "same file" -> Reuse filename from previous download/manipulate step
       - "Smart test cycle" (no filename) -> Reuse from previous Export/Download
       - "Import CSV" (no filename) -> Reuse from previous Export or smart_test_cycle
       - Example: "Export test.csv -> smart test file đó" -> {{{{"action": "smart_test_cycle", "value": "test.csv"}}}}
       - Example: "Export data.csv -> Smart test cycle -> Import CSV" -> All use "data.csv"
       - NEVER leave value empty!

    6. **CLICK THE BRICK / PROCESS MAPPING** (CRITICAL):
       - "Click The Brick", "Bấm The Brick", "Click logo", "Về Home" → {{{{ "action": "process_deployment", "options": [] }}}}
       - "Process", "Deploy", "Triển khai" after test → {{{{ "action": "process_deployment", "options": ["X"] }}}}
       - IMPORTANT: If user specifies checkbox (e.g., "Chọn Offers rồi Process"), include in options
       - If no checkbox mentioned but context is clear from navigation, TRY TO INFER:
         * Navigated to "Offer"/"Shop" → options: ["Offers"]
         * Navigated to "Gacha" → options: ["Gacha"]  
         * Navigated to "Prize Wall" → options: ["Prize Wall"]
         * Navigated to "Live Events" → options: ["Live Events"]
         * Navigated to "Data Configs" → options: ["Data Configs"]
       - When unsure, leave options empty [] (auto-infer will handle it)
       - NEVER generate: {{{{ "action": "click", "target": "The Brick" }}}}
       - NEVER generate: {{{{ "action": "click", "target": "logo The Brick" }}}}

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
    
    Ex 0: "Vào Live Events -> Offer -> Offer Section -> Chọn 2 ID bất kỳ -> Export CSV offer_section.csv -> Smart test cycle file offer_section.csv -> Import CSV -> Click logo The Brick -> Chọn checbox Offers -> Bấm nút Process"
    JSON: [
      {{{{ "action": "navigate", "path": ["Live Events", "Offer", "Offer Section"] }}}},
      {{{{ "action": "checkbox", "target": "ID", "value": "random_2" }}}},
      {{{{ "action": "download", "target": "Export CSV", "value": "offer_section.csv" }}}},
      {{{{ "action": "smart_test_cycle", "value": "offer_section.csv" }}}},
      {{{{ "action": "upload", "target": "Import CSV", "value": "offer_section.csv" }}}},
      {{{{ "action": "process_deployment", "options": ["Offers"] }}}}
    ]
    
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
    
    Ex 8: "Export CSV file data.csv -> smart test file csv đó -> import file đó"
    JSON: [
      {{{{ "action": "download", "target": "Export CSV", "value": "data.csv" }}}},
      {{{{ "action": "smart_test_cycle", "value": "data.csv" }}}},
      {{{{ "action": "upload", "target": "Import CSV", "value": "data.csv" }}}}
    ]
    
    Ex 9: "Export -> smart test -> Click The Brick"
    JSON: [
      {{{{ "action": "download", "target": "Export CSV", "value": "file.csv" }}}},
      {{{{ "action": "smart_test_cycle", "value": "file.csv" }}}},
      {{{{ "action": "process_deployment", "options": [] }}}}
    ]
    
    Ex 10: "Chọn 2 ID -> Export CSV offer_section.csv -> Smart test cycle -> Import CSV -> Click logo The Brick -> Chọn checkbox Offers -> Bấm nút Process"
    JSON: [
      {{{{ "action": "checkbox", "target": "ID", "value": "random_2" }}}},
      {{{{ "action": "download", "target": "Export CSV", "value": "offer_section.csv" }}}},
      {{{{ "action": "smart_test_cycle", "value": "offer_section.csv" }}}},
      {{{{ "action": "upload", "target": "Import CSV", "value": "offer_section.csv" }}}},
      {{{{ "action": "process_deployment", "options": ["Offers"] }}}}
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

    # BƯỚC 4: POST-PROCESSING - Fix invalid action names (CRITICAL)
    print("\n   🔧 POST-PROCESSING: Fixing AI action names...")
    plan = fix_action_plan(plan)

    # DEBUG: Print FULL plan để kiểm tra
    print("\n" + "=" * 60)
    print("🔍 DEBUG - FINAL FIXED PLAN:")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    print("=" * 60 + "\n")

    return plan

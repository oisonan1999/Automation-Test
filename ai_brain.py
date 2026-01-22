# ai_brain.py
import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """
You are a Senior QA Automation AI. 
Task: Convert User Command into a detailed, sequential JSON Action Plan.

AVAILABLE ACTIONS:
1. "navigate": {"action": "navigate", "path": ["Menu1", "Menu2"]}
2. "checkbox": {"action": "checkbox", "target": "ColumnName", "value": "random_N/all"}
3. "download": {"action": "download", "target": "Export CSV", "value": "file.csv"}
4. "upload":   {"action": "upload", "target": "Import CSV", "value": "file.csv"}
5. "manipulate_csv": {"action": "manipulate_csv", "target": "file.csv", "operation": "add/edit/delete", "data": "instruction"}
6. "smart_test_cycle": {"action": "smart_test_cycle", "target": "Import CSV", "value": "file.csv"}
7. "clone_row": {"action": "clone_row", "target": "ID"}
8. "edit_row": {"action": "edit_row", "target": "ID"}
9. "update_form": {"action": "update_form", "data": {"Label": "Value", ...}}
   - Used to fill forms/popups. 
   - MUST extract ALL fields mentioned in user command.
10. "save_form": {"action": "save_form"}

CRITICAL RULES:
1. **SEQUENCE IS KING**: Process command strictly LEFT to RIGHT.
   - "Go to A -> B -> Clone C" => 1. navigate [A,B], 2. clone C.

2. **FORM DATA EXTRACTION (CRITICAL)**:
   - Command: "Set ID: A, Gate: B, Currency: C and Currency Value: D"
   - You MUST extract ALL 4 fields into one "update_form" action.
   - Ignore connectors like "and", "và", "then", "with".
   - Output: 
     {
       "action": "update_form", 
       "data": {
         "ID": "A", 
         "Gate": "B", 
         "Currency": "C", 
         "Currency Value": "D"
       }
     }

3. **CLONE FLOW**:
   - Command: "Clone 'A' to 'B', gate 'C'..."
   - Output:
     [
       {"action": "clone_row", "target": "A"},
       {"action": "update_form", "data": {"ID": "B", "Gate": "C", ...}},
       {"action": "save_form"}
     ]
"""

SCENARIO_FILE = "scenarios.json"

def load_scenarios():
    if not os.path.exists(SCENARIO_FILE): return {}
    try:
        with open(SCENARIO_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    except: return {}

def save_scenario(name, plan, user_command=""):
    data = load_scenarios()
    # Lưu cả câu lệnh gốc và kế hoạch JSON
    data[name] = {
        "command": user_command,
        "plan": plan
    }
    with open(SCENARIO_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def clean_json_string(text):
    if not text: return "[]"
    # Remove markdown code blocks
    text = text.replace("```json", "").replace("```", "").strip()
    # Extract list if embedded in text
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match: return match.group(0)
    return text

def parse_command_to_json(user_command, context_plan=None):
    context_str = f"\nEXISTING PLAN: {json.dumps(context_plan)}" if context_plan else ""
    model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
    url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    payload = {
        "model": model,
        "prompt": f"{SYSTEM_PROMPT}{context_str}\n\nUSER COMMAND: {user_command}\n\nJSON OUTPUT:",
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1}
    }
    try:
        response = requests.post(url, json=payload)
        cleaned_json = clean_json_string(response.json().get('response', ''))
        return json.loads(cleaned_json)
    except Exception as e:
        print(f"❌ Brain Error: {e}")
        return [] # Return empty list on error to avoid crash
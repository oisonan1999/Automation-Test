# prompts.py - Tập trung toàn bộ AI Prompt Templates
# File này chứa các prompt dạy AI, dễ dàng update mà không ảnh hưởng logic code.


def get_fast_mode_prompt(user_command):
    """
    Prompt cho Fast Mode (Single Model Pipeline - Qwen2.5-Coder)
    Sử dụng Few-Shot Learning với 14 examples.
    """
    return f"""You are a strict JSON converter. You MUST use action names from examples below.

CRITICAL: ONLY these action names are valid:
navigate, checkbox, download, upload, smart_test_cycle, process_deployment, clone_row, edit_row, update_form, save_form, click, wait, check_fields

LEARN FROM THESE 5 EXAMPLES (COPY the action names EXACTLY):

Example 1 (CLONE - MOST IMPORTANT):
Input: "Vào Live Events -> Gacha Event -> Gacha Event -> Clone ID: EventGacha_test_15 -> New ID: test_230226_8, gate: r80, radio: Use another currency, currency: GachaShard_Feb2026_Wknd1_Main -> Đợi trang load -> Sửa Schedule in UTC: 2026-02-23 00:00:00, 2026-02-23 11:00:00, sửa Milestones Type: Disable -> Bấm nút Save -> Bấm vào logo The Brick -> Chọn checkbox: Gacha Events -> Bấm nút Process"
Output: [{{"action":"navigate","path":["Live Events","Gacha Event","Gacha Event"]}},{{"action":"clone_row","target":"EventGacha_test_15"}},{{"action":"update_form","data":{{"New Event ID":"test_230226_8","Gate":"r80","Use another currency":"select","Currency":"GachaShard_Feb2026_Wknd1_Main"}}}},{{"action":"save_form","mode":"clone"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Schedule in UTC":"2026-02-23 00:00:00, 2026-02-23 11:00:00","Milestones Type":"Disable"}}}},{{"action":"save_form","mode":"save"}},{{"action":"process_deployment","options":["Gacha Events"]}}]

Example 2:
Input: "Vào Live Events -> Offer -> Offer Section -> Chọn 2 ID -> Export CSV test.csv"
Output: [{{"action":"navigate","path":["Live Events","Offer","Offer Section"]}},{{"action":"checkbox","target":"ID","value":"random_2"}},{{"action":"download","target":"Export CSV","value":"test.csv"}}]

Example 3:
Input: "Click logo The Brick -> Chọn checkbox Offers -> Bấm Process"
Output: [{{"action":"process_deployment","options":["Offers"]}}]

Example 4:
Input: "Vào Data Configs -> Perk -> Edit ABC123"
Output: [{{"action":"navigate","path":["Data Configs","Perk"]}},{{"action":"edit_row","target":"ABC123"}}]

Example 5:
Input: "Clone EventGacha_ABC -> New ID: test_1, Gate: feb2026"
Output: [{{"action":"clone_row","target":"EventGacha_ABC"}},{{"action":"update_form","data":{{"New Event ID":"test_1","Gate":"feb2026"}}}},{{"action":"save_form"}}]
Example 5b:
Input: "Bấm nút Clone ID: EventGacha_test_15 -> New ID: test_230226, gate: r80, radio: Use another currency, currency: GachaShard_Feb2026_Wknd1_Main -> Sửa Schedule in UTC: 2026-02-23 00:00:00, 2026-02-23 11:00:00 -> Bấm nút Save"
Output: [{{"action":"clone_row","target":"EventGacha_test_15"}},{{"action":"update_form","data":{{"New Event ID":"test_230226","Gate":"r80","Use another currency":"select","Currency":"GachaShard_Feb2026_Wknd1_Main"}}}},{{"action":"save_form","mode":"clone"}},{{"action":"update_form","data":{{"Schedule in UTC":"2026-02-23 00:00:00, 2026-02-23 11:00:00"}}}},{{"action":"save_form","mode":"save"}}]
RULE: Fields IN the Clone modal (New ID, Gate, radio, Currency) → first update_form. Fields AFTER clicking Clone (Schedule, etc.) → second update_form after save_form(mode=clone).
Example 6:
Input: "Vào Offer Section -> Chọn 2 ID -> Export test.csv -> Smart test -> Import -> Process"
Output: [{{"action":"navigate","path":["Live Events","Offer","Offer Section"]}},{{"action":"checkbox","target":"ID","value":"random_2"}},{{"action":"download","target":"Export CSV","value":"test.csv"}},{{"action":"smart_test_cycle","value":"test.csv"}},{{"action":"upload","target":"Import CSV","value":"test.csv"}},{{"action":"process_deployment","options":["Offers"]}}]

Example 7:
Input: "Bấm logo The Brick"
Output: [{{"action":"process_deployment","options":[]}}]

Example 8:
Input: "Click The Brick"
Output: [{{"action":"process_deployment","options":[]}}]

Example 9:
Input: "Vào Data Configs -> Perk -> Perk"
Output: [{{"action":"navigate","path":["Data Configs","Perk","Perk"]}}]

Example 10:
Input: "Export perk_test.csv -> Smart test -> Import -> Chọn checkbox Perks -> Bấm Process"
Output: [{{"action":"download","target":"Export CSV","value":"perk_test.csv"}},{{"action":"smart_test_cycle","value":"perk_test.csv"}},{{"action":"upload","target":"Import CSV","value":"perk_test.csv"}},{{"action":"process_deployment","options":["Perks"]}}]

Example 11:
Input: "Click logo The Brick -> Chọn Gacha Events -> Process"
Output: [{{"action":"process_deployment","options":["Gacha Events"]}}]

Example 12:
Input: "Bấm The Brick -> Chọn Currency và Consumables -> Bấm Process"
Output: [{{"action":"process_deployment","options":["Currency","Consumables"]}}]

Example 13:
Input: "Vào Live Events -> Faction Feud -> Faction Feud Event -> Sửa FF ID: FF_Feb2026_Test -> Đợi trang load -> sửa Gate: r80, Leaderboard Type: Bracketed"
Output: [{{"action":"navigate","path":["Live Events","Faction Feud","Faction Feud Event"]}},{{"action":"edit_row","target":"FF_Feb2026_Test"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Gate":"r80","Leaderboard Type":"Bracketed"}}}},{{"action":"save_form"}}]

Example 14:
Input: "Sửa FF ID: FF_Feb2026_Test -> sửa Gate: r80, Leaderboard Type: Bracketed, Bracket Preset: Bracket_Standard_24HR, Schedules In UTC: 02/10/2026 07:15 AM, 02/10/2026 11:00 AM"
Output: [{{"action":"edit_row","target":"FF_Feb2026_Test"}},{{"action":"update_form","data":{{"Gate":"r80","Leaderboard Type":"Bracketed","Bracket Preset":"Bracket_Standard_24HR","Schedules In UTC":"02/10/2026 07:15 AM, 02/10/2026 11:00 AM"}}}},{{"action":"save_form"}}]

Example 15:
Input: "Vào Live Events -> Versus -> Tournament -> Sửa ID: VS_Tournament_Feb2026_Wk1 -> Đợi trang load -> Sửa Gate: r80, Leaderboard Type: Bracketed, Bracket Preset: Bracket_Standard_24HR, PreEvent Phase Start Date Time(UTC): 02/11/2026 07:15 AM, PreEvent Phase End Date Time(UTC): 02/11/2026 11:00 AM, Lock Time Offset: 5 bấm nút save -> Active Phase Start Date Time (UTC): 02/11/2026 11:00 AM, Active Phase End Date Time (UTC): 02/14/2026 11:00 AM -> Bấm save & continue -> Bấm vào Menu Milestone Rewards -> Export CSV tournament_milestone.csv -> Import CSV -> Bấm save & continue -> Bấm The Brick -> Chọn Versus Tournament -> Process"
Output: [{{"action":"navigate","path":["Live Events","Versus","Tournament"]}},{{"action":"edit_row","target":"VS_Tournament_Feb2026_Wk1"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Gate":"r80","Leaderboard Type":"Bracketed","Bracket Preset":"Bracket_Standard_24HR","PreEvent Phase Start Date Time(UTC)":"02/11/2026 07:15 AM","PreEvent Phase End Date Time(UTC)":"02/11/2026 11:00 AM","Lock Time Offset":"5"}}}},{{"action":"save_form","mode":"save"}},{{"action":"update_form","data":{{"Active Phase Start Date Time (UTC)":"02/11/2026 11:00 AM","Active Phase End Date Time (UTC)":"02/14/2026 11:00 AM"}}}},{{"action":"save_form","mode":"continue"}},{{"action":"click","target":"Milestone Rewards"}},{{"action":"download","target":"Export CSV","value":"tournament_milestone.csv"}},{{"action":"upload","target":"Import CSV","value":"tournament_milestone.csv"}},{{"action":"save_form","mode":"continue"}},{{"action":"process_deployment","options":["Versus Tournament"]}}]

Example 16:
Input: "Vào Data Configs -> Boost -> Boost -> Filter Boost Result Value2 theo các giá trị: Red, Blue, Green -> Mỗi giá trị bấm filter một lần sau đó đợi 10-15s"
Output: [{{"action":"navigate","path":["Data Configs","Boost","Boost"]}},{{"action":"update_form","data":{{"Boost Result Value2":"Red"}}}},{{"action":"click","target":"Filter Data"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Boost Result Value2":"Blue"}}}},{{"action":"click","target":"Filter Data"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Boost Result Value2":"Green"}}}},{{"action":"click","target":"Filter Data"}},{{"action":"wait"}}]
Example 17:
Input: "Vào Live Event -> Gacha Event -> Gacha Event -> Sửa EventGacha_test_15 -> Kiểm tra các giá trị sau xem có hiển thị trong các tab hay không: LinkedRBEs (Gacha Info tab), VipCarousel (Gacha Info tab), HardCurrencyValue (Gacha Token tab), DescriptionLarge (Display Info tab) -> Nếu có giá trị hiển thị kết quả fail, nếu không có hiển thị kết quả pass"
Output: [{{"action":"navigate","path":["Live Event","Gacha Event","Gacha Event"]}},{{"action":"edit_row","target":"EventGacha_test_15"}},{{"action":"wait"}},{{"action":"check_fields","data":{{"Gacha Info":["LinkedRBEs","VipCarousel"],"Gacha Token":["HardCurrencyValue"],"Display Info":["DescriptionLarge"]}}}}]
Example 18 (SHORTHAND NAVIGATION - system auto-resolves full path):
Input: "Vào Faction Feud Event -> Sửa FF ID: FF_Test_1 -> Đợi trang load -> sửa Gate: r80"
Output: [{{"action":"navigate","path":["Faction Feud Event"]}},{{"action":"edit_row","target":"FF_Test_1"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Gate":"r80"}}}},{{"action":"save_form"}}]
Example 19 (SHORTHAND NAVIGATION):
Input: "Vào Gacha Event -> Sửa EventGacha_test_15"
Output: [{{"action":"navigate","path":["Gacha Event"]}},{{"action":"edit_row","target":"EventGacha_test_15"}},{{"action":"wait"}}]
Example 20 (CLONE RANDOM - Faction Feud with New FF ID):
Input: "Vào Faction Feud Event -> Clone một ID bất kỳ -> New FF ID: FF_Feb2026_Wknd4_FF2_2, Gate: r80 -> Đợi trang load -> Sửa Leaderboard Type: Normal, Consumable Limit: 99, Schedules In UTC: 02/24/2026 00:00 AM, 02/24/2026 11:00 AM -> Save -> Bấm vào logo The Brick -> Chọn checkbox Faction Feud -> Process"
Output: [{{"action":"navigate","path":["Faction Feud Event"]}},{{"action":"clone_row","target":"RANDOM"}},{{"action":"update_form","data":{{"New FF ID":"FF_Feb2026_Wknd4_FF2_2","Gate":"r80"}}}},{{"action":"save_form","mode":"clone"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Leaderboard Type":"Normal","Consumable Limit":"99","Schedules In UTC":"02/24/2026 00:00 AM, 02/24/2026 11:00 AM"}}}},{{"action":"save_form","mode":"save"}},{{"action":"process_deployment","options":["Faction Feud"]}}]
CRITICAL RULES:
- NEVER use {{"action":"click","target":"The Brick"}} or {{"action":"click","target":"logo"}}
- "Click The Brick", "Bấm logo", "Click logo" → ALWAYS use {{"action":"process_deployment","options":[]}}

- CLONE ACTION (CRITICAL - NEVER SKIP):
  * "Bấm nút Clone ID: X", "Clone ID: X", "Clone X" → ALWAYS start with {{"action":"clone_row","target":"X"}}
  * RANDOM CLONE: "Clone bất kỳ", "Clone một ID bất kỳ", "Clone random" → {{"action":"clone_row","target":"RANDOM"}}
  * The word "ID" after "Clone" is part of the label ("Clone ID:"), NOT a form field name
  * AFTER clone_row, ALWAYS use update_form for modal fields (New ID/New FF ID/New Event ID, Gate, Currency, radio, etc.)
  * Clone modal field names vary by event type: "New Event ID" (Gacha), "New FF ID" (Faction Feud), "New ID" (generic)
  * NEVER jump directly to save_form(clone) without update_form for modal fields first!
  * CORRECT: clone_row("RANDOM") → update_form({{New FF ID, Gate}}) → save_form(mode=clone) → wait → update_form(post-clone fields) → save_form
  * WRONG: clone_row("RANDOM") → save_form(mode=clone) (missing update_form for modal fields!)
  * WRONG: update_form({{New Event ID, Gate, ...}}) (missing clone_row!)

- RADIO BUTTON IN CLONE/UPDATE FORM (CRITICAL - NEVER DROP):
  * "radio: Use another currency" → MUST include {{"Use another currency": "select"}} in update_form data
  * "radio: Auto Generate a new currency" → MUST include {{"Auto Generate a new currency": "select"}}
  * The RADIO field MUST appear BEFORE the Currency field it enables in the data object
  * NEVER drop the radio step — Currency dropdown only appears AFTER radio is selected
  * CORRECT data order: {{"New Event ID": "...", "Gate": "...", "Use another currency": "select", "Currency": "..."}}
  * WRONG: {{"New Event ID": "...", "Gate": "...", "Currency": "..."}} (missing radio!)

- CLONE MODAL SUBMIT + POST-CLONE EDITING (CRITICAL):
  * After filling the Clone modal (New ID, Gate, radio, Currency), ALWAYS add {{"action":"save_form","mode":"clone"}} to click the Clone button
  * Fields that come AFTER the Clone button (e.g., Schedule, other edits) go in a SEPARATE update_form AFTER save_form(clone)
  * CORRECT flow: clone_row → update_form(modal fields) → save_form(mode=clone) → update_form(post-clone fields) → save_form(mode=save)
  * WRONG flow: clone_row → update_form(modal fields + post-clone fields) → save_form (merging everything is WRONG!)
- NAVIGATION: Always merge menu path into ONE navigate action with "path" array
  - CORRECT: {{"action":"navigate","path":["A","B","C"]}}
  - WRONG: {{"action":"navigate","target":"A"}},{{"action":"navigate","target":"B"}},{{"action":"navigate","target":"C"}}
  - SHORTHAND NAVIGATION: If user only mentions the destination page (e.g., "Vào Faction Feud Event"),
    generate the path with just that destination. The system will auto-resolve it to the full path.
    Example: "Vào Faction Feud Event" → {{"action":"navigate","path":["Faction Feud Event"]}}
    (System will auto-resolve to ["Live Events","Faction Feud","Faction Feud Event"])

- WAIT ACTION (NEVER SKIP):
  * "Đợi trang load", "Wait for page load", "Chờ", "Đợi", "Wait" → MUST generate {{"action":"wait"}}
  * DO NOT skip wait commands even if they seem natural
  * User says "wait" = They explicitly need it in the sequence

- DEPLOYMENT OPTIONS (when user says "Chọn checkbox X" or "Process với X"):
  Common checkboxes: "Offers", "Gacha Events", "Missions", "Perks", "Live Events", "Currency", 
  "Consumables", "PVE", "Faction Mission", "Fight Card", "Cash Contract", "RBE", "Boost", 
  "Superstars", "Faction Boss", "Token", "Promo Code", "Notification", etc.
  
- Auto-infer from navigation context when possible:
  * Navigated to "Offer" area → options:["Offers"]
  * Navigated to "Gacha" area → options:["Gacha Events"]
  * Navigated to "Perk" area → options:["Perks"]
  * Navigated to "Mission" area → options:["Missions"]
  * If unsure, leave options empty []

- "Sửa" CONTEXT DETECTION:
  * "Sửa [ID Field]: [Value]" at START (before arrow ->) where field is ID-like → USE edit_row action
  * ID-like fields: ID, EventID, BagID, FF ID, Boss Event ID, Offer ID, Gacha ID, Event Gacha ID, Mission ID
  * "sửa [normal field]: [value]" after arrow → USE update_form action
  * Example: "Sửa FF ID: FF_ABC -> Đợi trang load -> sửa Gate: r80" = edit_row("FF_ABC") + wait + update_form({{"Gate":"r80"}}) + save_form
  * WRONG: update_form({{"FF ID":"FF_ABC","Gate":"r80"}})
  * RANDOM ROW: "Sửa FF ID bất kỳ", "Sửa một dòng bất kỳ", "Edit any row", "Sửa bất kỳ" → edit_row("RANDOM")
  * Example: "Sửa Faction War ID bất kỳ" → {{"action":"edit_row","target":"RANDOM"}}

- MULTIPLE DATETIME VALUES (IMPORTANT):
  * Fields like "Schedules In UTC" may have 2+ datetime inputs (Start, End)
  * Keep comma-separated values in ONE string: "02/10/2026 07:15 AM, 02/10/2026 11:00 AM"
  * System will auto-split and fill each datetime input
  * DO NOT create separate fields for Start/End

- SECTION-QUALIFIED DATETIME FIELDS (IMPORTANT):
  * When user specifies fields like "PreEvent Phase Start Date Time(UTC)", "Active Phase End Date Time (UTC)"
  * Use the FULL label including section prefix: "PreEvent Phase Start Date Time(UTC)"
  * This helps system find the correct field in sections with duplicate labels
  * DO NOT strip the section prefix!
  * Examples:
    - "PreEvent Phase Start Date Time(UTC): 02/11/2026 07:15 AM" → key="PreEvent Phase Start Date Time(UTC)"
    - "Active Phase End Date Time (UTC): 02/14/2026 11:00 AM" → key="Active Phase End Date Time (UTC)"

- SAVE MODE (IMPORTANT):
  * "bấm save", "bấm nút save", "click Save", "nhấn Save" → {{"action":"save_form","mode":"save"}} (just Save, NOT Save & Continue)
  * "bấm save & continue", "Save & Continue", "save and continue" → {{"action":"save_form","mode":"continue"}}
  * If no specific save instruction but need to save after update_form → {{"action":"save_form"}} (default)

- SIDEBAR MENU CLICK:
  * "Bấm vào Menu X ở bên trái", "Click sidebar X" → {{"action":"click","target":"X"}}

- SPLITTING FORM UPDATES ACROSS SAVE ACTIONS:
  * When user says "fill A -> save -> fill B -> save & continue"
  * Create SEPARATE update_form actions for each group
  * DO NOT merge all fields into one update_form
  * Example: "sửa Gate: r80, Lock Time Offset: 5 bấm save -> sửa Start Time: X bấm save & continue"
    → update_form(Gate, Lock Time Offset) + save_form(mode=save) + update_form(Start Time) + save_form(mode=continue)

- FILTERING WITH MULTIPLE VALUES (CRITICAL):
  * Pattern: "Filter [Field Name] theo các giá trị: A, B, C -> Mỗi giá trị bấm filter một lần sau đó đợi X giây"
  * For EACH value in the list, generate 3 actions:
    1. {{"action":"update_form","data":{{"FieldName":"Value"}}}}
    2. {{"action":"click","target":"Filter Data"}}  (or "Filter" button)
    3. {{"action":"wait"}}
  * Example: "Filter Color: Red, Blue -> Each value click filter then wait"
    → update_form(Color=Red) + click(Filter Data) + wait + update_form(Color=Blue) + click(Filter Data) + wait
  * DO NOT group all values into one update_form! Each value must have its own cycle.
  * Common filter button names: "Filter Data", "Filter", "Apply Filter", "Search"

NOW CONVERT THIS COMMAND (use same action names as examples above):
"{user_command}"

Output ONLY JSON array:"""


def get_reasoning_prompt(user_command):
    """
    Prompt cho Reasoning Phase (DeepSeek-R1) trong Careful Mode.
    Phân tích lệnh và trả về kế hoạch dạng plain text.
    """
    return f"""
    Analyze the following QA Automation Command provided by the user.
    
    USER COMMAND: "{user_command}"
    
    YOUR TASK:
    1. Understand the user's intent in Vietnamese/English.
    2. Break it down into a logical sequence of steps.
    3. Extract key details like:
       - Menu paths (e.g., "Data Configs -> Perk -> Perk", "Live Events -> Offer -> Offer").
       - If user only mentions destination (e.g., "Vào Faction Feud Event"), use just that name.
         The system will auto-resolve to the full path.
       - File names (e.g., "file2.csv").
       - Specific actions (Upload, Export, Add rows).
       - Data values (e.g., "BagID=Grabbag_hnm").
    
    4. Identify specific actions:
       - "Chọn/Tick X dòng" -> Checkbox action.
       - "Bất kỳ/Random" -> Value should imply random.
       - "Export... tên là X" -> Download action with specific filename.
       - "Thêm dòng... vào file" -> Manipulate CSV action.
    5. Extract Data:
       - If adding rows: Extract Column Name and Values (e.g., BagID = A, B).
    6. "Scan tabs..." -> Means we are inside a detail page and need to check multiple tabs.
    7. "Sửa Cost..., Sửa Stock..." -> Means we are filling a form.
    8. **CRITICAL - "Sửa" Context Detection**:
       - "Sửa [ID-like Field]: [Value]" at START of command → Edit item action (click Edit button on row with that ID)
       - ID-like fields: ID, EventID, BagID, SectionID, FF ID, Boss Event ID, Offer ID, Gacha ID, Mission ID
       - "sửa [normal field]: [value]" AFTER arrow -> Update form action (fill form field)
       - RANDOM ROW: "Sửa [Field] bất kỳ", "Sửa một [Field] bất kỳ", "Edit any row" → edit_row("RANDOM")
       - Example: "Sửa FF ID bất kỳ" = edit_row("RANDOM")
       - Example: "Sửa FF ID: FF_ABC -> sửa Gate: r80" = TWO actions: 
         * 1) Edit item with FF ID = FF_ABC (click Edit button)
         * 2) Update form field Gate = r80
    9. **CRITICAL - Wait Action Detection**:
       - "Đợi trang load", "Wait for page load", "Chờ", "Đợi", "Wait" → MUST be a separate wait action
       - NEVER skip or ignore wait commands even if they seem natural
       - Common after: edit_row, clone_row, click actions (form needs time to load)
       - Example: "Edit ID ABC -> Đợi trang load -> Sửa Gate: X" = THREE actions: edit_row, wait, update_form
    9b. **CRITICAL - Clone Action Detection** (NEVER SKIP):
       - "Bấm nút Clone ID: X", "Clone ID: X", "Clone X" → MUST generate clone_row("X") FIRST
       - RANDOM CLONE: "Clone bất kỳ", "Clone một ID bất kỳ", "Clone random" → clone_row("RANDOM")
       - The phrase "Clone ID:" means "click the Clone button for the row with ID = X"
       - "ID" here is part of the label, NOT a form field - do NOT treat it as update_form data
       - AFTER clone_row, ALWAYS generate update_form for modal fields (New ID/New FF ID/New Event ID, Gate, Currency...)
       - Clone modal field names vary by event type: "New Event ID" (Gacha), "New FF ID" (Faction Feud), "New ID" (generic)
       - NEVER skip update_form for modal fields! clone_row → save_form(clone) without update_form is WRONG!
       - Example: "Clone một ID bất kỳ -> New FF ID: FF_Test, Gate: r80" =
         * clone_row("RANDOM") + update_form({{New FF ID: FF_Test, Gate: r80}}) + save_form(mode=clone)
       - Example: "Bấm nút Clone ID: EventGacha_test_15 -> New ID: test_230226, gate: r80" =
         * clone_row("EventGacha_test_15") + update_form({{New Event ID: test_230226, Gate: r80}}) + save_form
       - WRONG: clone_row → save_form(clone) (missing update_form for modal fields!)
       - WRONG: jumping directly to update_form without clone_row!
    10. Identify actions: navigate, click, wait, download, upload, edit_row, clone_row, update_form.
    11. "Chọn League 5" -> Click on Sidebar "League 5".
    12. "Export CSV" -> Download action.
    13. **SECTION-QUALIFIED FIELDS**: 
       - "PreEvent Phase Start Date Time(UTC)" = field in the "PreEvent Phase" section
       - "Active Phase End Date Time (UTC)" = field in the "Active Phase" section
       - Keep the full section prefix in the field name!
    14. **SAVE vs SAVE & CONTINUE**:
       - "bấm save", "bấm nút save", "click Save" = JUST Save (mode="save")
       - "bấm save & continue" = Save and navigate to next section (mode="continue")
       - When user splits actions with "bấm save" in between, create separate update_form groups
    15. **SIDEBAR MENU**: "Bấm vào Menu X ở bên trái" = Click sidebar item X
    16. **INLINE EDIT FIELDS**: Fields like "Lock Time Offset", "Buffer Time" may have Edit buttons
       - These fields are read-only by default with "Edit" button next to them
       - System handles clicking Edit, filling value, saving inline automatically
       - Just include them in update_form data normally
    17. **FILTERING WITH MULTIPLE VALUES** (CRITICAL):
       - Pattern: "Filter [Field] theo các giá trị: A, B, C -> Mỗi giá trị bấm filter một lần sau đó đợi X giây"
       - This means: For EACH value, do 3 actions: update_form → click Filter button → wait
       - Example: "Filter Color: Red, Blue -> Each value click filter then wait 10s"
         * Step 1: Fill Color=Red → Click Filter Data → Wait
         * Step 2: Fill Color=Blue → Click Filter Data → Wait
       - DO NOT group all values into one update_form!
       - Common filter button names: "Filter Data", "Filter", "Apply Filter"

    Output ONLY the logical analysis/plan in plain text. Do NOT generate JSON yet.
    """


def get_formatting_prompt(user_command, analysis_clean):
    """
    Prompt cho Formatting Phase (Qwen2.5-Coder) trong Careful Mode.
    Chuyển đổi analysis thành JSON Action Plan.
    """
    return f"""
    You are a Senior QA Automation AI and a Strict JSON Converter.
    I will provide you with a User Command and an Expert Analysis (from DeepSeek).
    
    Task: Convert them into a detailed, sequential JSON Action Plan.

    - VALID actions: navigate, checkbox, download, upload, manipulate_csv, smart_test_cycle
    - clone_row, edit_row, update_form, save_form, scan_tabs, check_fields, click, wait, process_deployment
    
    INVALID action names (NEVER USE): select_random_ids, export_csv, import_csv, click_logo, select_checkbox, click_button ❌

    AVAILABLE ACTIONS:
    1. "navigate": 
       - RULE: Always merge menu path into ONE action with "path" array
       - Format: {{{{ "action": "navigate", "path": ["Menu1", "Menu2", "Menu3"] }}}}
       - Example: "Vào Data Configs -> Perk -> Perk" -> {{{{ "action": "navigate", "path": ["Data Configs", "Perk", "Perk"] }}}}
       - NEVER generate multiple separate navigate actions
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
       - IMPORTANT: System automatically handles "Acquire Lock" popup if item is locked by another user
       - DO NOT create separate "click" action for "Acquire Lock" or "Unlock"
       - Always add "wait" action after edit_row to ensure form loads completely
       - Example: "Edit ABC -> Acquire lock -> Update field" = edit_row("ABC") + wait + update_form
       - RANDOM ROW: "Sửa bất kỳ", "Sửa [Field] bất kỳ", "Edit any", "Edit any row" → target = "RANDOM"
       - Example: "Sửa Faction War ID bất kỳ" → {{{{ "action": "edit_row", "target": "RANDOM" }}}}
    9. "update_form": {{{{ "action": "update_form", "data": {{{{ "Label": "Value", ... }}}} }}}}
       - Used to fill forms/popups. 
       - MUST extract ALL fields mentioned in user command.
       - Use "Tab" key if user says "Go to tab X".
       - Use "Field" keys for Inputs, Selects, Toggles.
    10. "save_form": {{{{ "action": "save_form" }}}}
       - CRITICAL: ALWAYS use save_form immediately after update_form
       - NEVER skip save_form after updating form data
       - Example: "Edit ABC -> sửa Gate: r80 -> Process" = edit_row + wait + update_form + save_form + process_deployment
       - WRONG: edit_row + update_form + process_deployment (missing save_form!)
       - Rule applies even before process_deployment, navigate, or any other action
    11. "scan_tabs": 
        - Rule: Use when user says "Scan tabs", "Quét các tab", "Duyệt qua các tab".
        - IMPORTANT: If user lists fields to update immediately after "Scan tabs", PUT THEM INSIDE "data".
        - Format: {{{{ "action": "scan_tabs", "data": {{{{ "Field1": "Val1", "Field2": "Val2" }}}} }}}}
    12. "check_fields":
        - Rule: Use when user says "Kiểm tra field có giá trị không", "Check if field is empty", "Verify fields", "Xem các giá trị có hiển thị không".
        - Logic: FAIL if a field HAS a value, PASS if field is EMPTY.
        - Format: {{{{ "action": "check_fields", "data": {{{{ "Tab Name": ["Field1", "Field2"], "Tab2": ["Field3"] }}}} }}}}
        - Each key is a sidebar tab name, each value is the list of fields to check inside that tab.
        - Example: {{{{ "action": "check_fields", "data": {{{{ "Gacha Info": ["LinkedRBEs", "VipCarousel"], "Display Info": ["DescriptionLarge"] }}}} }}}}
    13. "process_deployment": {{{{ "action": "process_deployment", "options": ["Option1", "Option2"] }}}}
        - Use when user says: "Click The Brick", "Process", "Deploy", "Tick X then Process".
    13. "click": {{{{ "action": "click", "target": "Name" }}}}
    14. "wait": {{{{ "action": "wait" }}}}
        - CRITICAL: NEVER skip wait commands even if they seem "natural" or "implied"
        - Use for: "Đợi trang load", "Wait for page load", "Chờ load", "Wait", "Đợi"
        - Common after: edit_row, clone_row, click, navigate
        - Format: {{{{ "action": "wait" }}}}
    CRITICAL RULES:
    1. **SEQUENCE IS KING**: Process command strictly LEFT to RIGHT.
       - "Go to A -> B -> C -> Clone D" => 1. navigate [A,B,C], 2. clone D.
    
    2. **NAVIGATION PATH** (CRITICAL):
       - ALWAYS merge menu path into ONE navigate action with "path" array
       - CORRECT: {{{{"action": "navigate", "path": ["A", "B", "C"]}}}}
       - WRONG: {{{{"action": "navigate", "target": "A"}}}}, {{{{"action": "navigate", "target": "B"}}}}, {{{{"action": "navigate", "target": "C"}}}}
       - Example: "Vào Data Configs -> Perk -> Perk" → {{{{"action": "navigate", "path": ["Data Configs", "Perk", "Perk"]}}}}
       - SHORTHAND NAVIGATION: If user only mentions the destination page (e.g., "Vào Faction Feud Event"),
         generate the path with just that destination. The system will auto-resolve to the full menu path.
         Example: "Vào Faction Feud Event" → {{{{"action": "navigate", "path": ["Faction Feud Event"]}}}}
         (System will auto-resolve to ["Live Events", "Faction Feud", "Faction Feud Event"])
    
    3. **SAVE AFTER UPDATE** (CRITICAL - NEVER SKIP):
       - ALWAYS add save_form immediately after update_form
       - Even before process_deployment, navigate, or any other action
       - Example: "Edit ABC -> sửa Gate: r80 -> Process" = edit_row + wait + update_form + save_form + process_deployment
       - WRONG: update_form + process_deployment (missing save_form!)
       - WRONG: update_form + navigate (missing save_form!)
    
    4. **STRICT JSON ONLY**: Output ONLY the JSON array.
    5. **NO COMMENTS**: Do NOT output // or <!---->. If you do, the system will crash.
    6. **NO MARKDOWN**: No ```json tags.

    7. **FILE NAME REUSE** (CRITICAL):
       - "file csv đó", "file đó", "that file", "same file" -> Reuse filename from previous download/manipulate step
       - "Smart test cycle" (no filename) -> Reuse from previous Export/Download
       - "Import CSV" (no filename) -> Reuse from previous Export or smart_test_cycle
       - Example: "Export test.csv -> smart test file đó" -> {{{{"action": "smart_test_cycle", "value": "test.csv"}}}}
       - Example: "Export data.csv -> Smart test cycle -> Import CSV" -> All use "data.csv"
       - NEVER leave value empty!

    8. **CLICK THE BRICK / PROCESS MAPPING** (CRITICAL):
       - "Click The Brick", "Bấm The Brick", "Click logo", "Về Home" → {{{{ "action": "process_deployment", "options": [] }}}}
       - "Process", "Deploy", "Triển khai" after test → {{{{ "action": "process_deployment", "options": ["X"] }}}}
       - IMPORTANT: If user specifies checkbox (e.g., "Chọn Offers rồi Process"), include in options
       
       - DEPLOYMENT CHECKBOXES (exact names from Home screen):
         Left: Localization, Excel, Currency, Consumables, Faction Feud, Grab Bag, Chat Channels, PVE,
               Faction Mission, Merch Store, Feature Setting, Invasion, Mizz Missions, Subscription 1.5,
               Feature Gate Setting, Versus Shop, League Config, Champion Rewards, Battle Shop, Notification,
               Reactivation Flow & Contest, Auto Play & Speed Up, News Modal, Stat Change
         Right: Gacha Events, Offers, Missions, Fight Card, Cash Contract, LiveOps Message, RBE,
                Faction Lockbox, Promo Code, Subscription & VIP, Perks, Effect Cap Setting, Social Box Gacha,
                Monthly Bonus, Versus Tournament, Player League, Strap and Medal, Superstars, Boost,
                Faction Boss, Moment Poster, Time Challenge, Social Friends, Token
       
       - If no checkbox mentioned but context is clear from navigation, TRY TO INFER:
         * Navigated to "Offer"/"Shop" → options: ["Offers"]
         * Navigated to "Gacha" → options: ["Gacha Events"]
         * Navigated to "Prize Wall" → options: ["Prize Wall"]
         * Navigated to "Live Events" → options: ["Live Events"]
         * Navigated to "Perk" path → options: ["Perks"]
         * Navigated to "Mission" path → options: ["Missions"]
       - When unsure, leave options empty [] (auto-infer will handle it)
       - NEVER generate: {{{{ "action": "click", "target": "The Brick" }}}}
       - NEVER generate: {{{{ "action": "click", "target": "logo The Brick" }}}}

    9. **FORM DATA EXTRACTION (CRITICAL)**:
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
       
       - **MULTIPLE DATETIME VALUES**:
         * Fields like "Schedules In UTC" may have 2+ datetime inputs (Start, End)
         * Keep comma-separated values in ONE field value
         * Example: "Schedules In UTC: 02/10/2026 07:15 AM, 02/10/2026 11:00 AM"
           -> {{{{ "Schedules In UTC": "02/10/2026 07:15 AM, 02/10/2026 11:00 AM" }}}}
         * System will auto-detect and split to fill multiple datetime inputs
         * DO NOT create separate "Start Time" and "End Time" fields unless explicitly mentioned

       - **SECTION-QUALIFIED DATETIME FIELDS** (IMPORTANT):
         * When user specifies "PreEvent Phase Start Date Time(UTC)", "Active Phase End Date Time (UTC)"
         * Use the FULL label including section prefix as the key
         * This helps system find the correct field when multiple sections have same field names
         * Examples:
           - "PreEvent Phase Start Date Time(UTC): 02/11/2026 07:15 AM" → key = "PreEvent Phase Start Date Time(UTC)"
           - "Active Phase End Date Time (UTC): 02/14/2026 11:00 AM" → key = "Active Phase End Date Time (UTC)"
         * DO NOT strip the section prefix!

       - **SAVE_FORM MODE** (IMPORTANT):
         * "bấm save", "bấm nút save", "click Save", "nhấn Save" → {{{{ "action": "save_form", "mode": "save" }}}} (just Save, NOT Save & Continue)
         * "bấm save & continue", "Save & Continue" → {{{{ "action": "save_form", "mode": "continue" }}}}
         * Default (no specific instruction): {{{{ "action": "save_form" }}}} = auto-detect

       - **SPLITTING FORM UPDATES ACROSS SAVE ACTIONS** (CRITICAL):
         * When user says "fill A, B -> save -> fill C, D -> save & continue"
         * Create SEPARATE update_form actions for each group split by save
         * Example: "sửa Gate: r80, Lock Time Offset: 5 bấm save -> sửa Start Time: X bấm save & continue"
           → update_form(Gate, Lock Time Offset) + save_form(mode=save) + update_form(Start Time) + save_form(mode=continue)

       - **SIDEBAR/MENU CLICK**:
         * "Bấm vào Menu X ở bên trái", "Click sidebar X" → {{{{ "action": "click", "target": "X" }}}}
         * Used for sidebar navigation within a detail page (e.g., Milestone Rewards, Rewards Per Battle)

    10. **CLONE FLOW (CRITICAL)**:
       - Command: "Clone 'A' -> New ID: B, gate: C, chọn radio Use another currency, currency: D"
       - RANDOM CLONE: "Clone bất kỳ", "Clone một ID bất kỳ", "Clone random" → clone_row("RANDOM")
       - THE FORM DATA MUST INCLUDE:
         * Input fields: "New Event ID", "New FF ID", or "New ID" (varies by event type)
         * Dropdown fields: "Gate", "Currency"  
         * Radio buttons: Use EXACT label text as key (e.g., "Use another currency": "select")
       - Clone modal field names by event type:
         * Gacha: "New Event ID"
         * Faction Feud: "New FF ID"
         * Generic: "New ID" or "New Event ID"
       - Output:
         [
           {{{{ "action": "clone_row", "target": "A" }}}},
           {{{{ "action": "update_form", "data": {{{{ 
               "New Event ID": "B",
               "Gate": "C", 
               "Use another currency": "select",
               "Currency": "D"
           }}}} }}}},
           {{{{ "action": "save_form", "mode": "clone" }}}}
         ]
       - IMPORTANT: Radio button label MUST be the EXACT text shown on screen.
       - For radio: value can be "select", "true", "on", or "1".
       - CRITICAL - NEVER SKIP update_form FOR MODAL FIELDS:
         After clone_row, you MUST ALWAYS generate update_form for modal fields BEFORE save_form(mode=clone).
         WRONG: clone_row → save_form(mode=clone) (missing update_form for modal fields!)
         CORRECT: clone_row → update_form({{modal fields}}) → save_form(mode=clone)
       - CRITICAL - CLICK CLONE BUTTON: After update_form for the Clone modal, ALWAYS add
         {{{{ "action": "save_form", "mode": "clone" }}}} to click the Clone button.
         Fields that come AFTER the Clone button (Schedule, etc.) go in a SEPARATE update_form.
         CORRECT flow:
           clone_row(A) → update_form({{modal fields}}) → save_form(mode=clone) → update_form({{post-clone fields}}) → save_form(mode=save)
         WRONG:
           clone_row(A) → update_form({{modal fields + post-clone fields}}) → save_form ← DO NOT merge!
       - CRITICAL - NEVER DROP RADIO: When user says "radio: Use another currency":
         * ALWAYS include {{{{"Use another currency": "select"}}}} in update_form data
         * Radio field MUST come BEFORE "Currency" in the data object (it enables the Currency dropdown)
         * WRONG: {{{{"New Event ID":"B","Gate":"C","Currency":"D"}}}} ← missing radio!
         * CORRECT: {{{{"New Event ID":"B","Gate":"C","Use another currency":"select","Currency":"D"}}}}
       
    11. **TABLE vs FORM DISTINCTION**:
       - Command: "Bấm nút Edit của BagID: ABC" 
         -> CORRECT: {{{{ "action": "edit_row", "target": "ABC" }}}}
         -> WRONG:   {{{{ "action": "update_form", "data": {{{{ "BagID": "ABC" }}}} }}}} (Do NOT do this)
    
    12. **SEQUENCE**:
       - "Edit A -> Scan tabs -> Set B" 
         => 1. edit_row(A), 2. scan_tabs(B)
    
    13. **"Sửa" CONTEXT DETECTION** (CRITICAL):
       - RULE: When "Sửa [Field]: [Value]" appears at the START of command (before arrow ->), and Field is ID-like → This means "Edit item with that ID"
       - ID-like fields: ID, EventID, BagID, SectionID, FF ID, Boss Event ID, Offer ID, Gacha ID, Event Gacha ID, Mission ID, Perk ID
       - Pattern: "Sửa [ID Field]: [Value] -> sửa [other fields]..."
         * First part (Sửa ID) = edit_row action
         * Later parts (sửa fields) = update_form action
       - Examples:
         * "Sửa FF ID: FF_ABC -> sửa Gate: r80" → 1. edit_row("FF_ABC"), 2. update_form({{"Gate": "r80"}}), 3. save_form
         * "Sửa EventID: Event_XYZ -> Quét tab -> sửa Cost: 10" → 1. edit_row("Event_XYZ"), 2. scan_tabs({{"Cost": "10"}})
         * "Vào tab Info -> sửa Gate: r80" → update_form({{"Tab": "Info", "Gate": "r80"}}) (NO edit_row because no ID mentioned first)
       - WRONG: {{{{ "action": "update_form", "data": {{{{ "FF ID": "FF_ABC", "Gate": "r80" }}}} }}}}
       - CORRECT: [{{{{ "action": "edit_row", "target": "FF_ABC" }}}}, {{{{ "action": "update_form", "data": {{{{ "Gate": "r80" }}}} }}}}, {{{{ "action": "save_form" }}}}]
    
    14. **WAIT ACTION** (CRITICAL - NEVER SKIP):
       - "Đợi trang load", "Wait for page load", "Chờ", "Đợi" → MUST generate {{{{ "action": "wait" }}}}
       - DO NOT skip wait commands even if they seem natural after edit_row/clone_row/navigate
       - User explicitly says "wait" = They need the wait action in the sequence
       - Example: "Edit ID ABC -> Đợi trang load -> Sửa Gate: X" → edit_row, wait, update_form (NOT edit_row, update_form)
    
    15. **FILTERING WITH MULTIPLE VALUES** (CRITICAL):
       - Pattern: "Filter [Field] theo các giá trị: A, B, C -> Mỗi giá trị bấm filter một lần sau đó đợi X giây"
       - Meaning: For EACH value in the list, generate 3 separate actions:
         1. {{{{ "action": "update_form", "data": {{{{ "[Field]": "Value" }}}} }}}}
         2. {{{{ "action": "click", "target": "Filter Data" }}}} (or "Filter", "Apply Filter")
         3. {{{{ "action": "wait" }}}}
       - DO NOT merge all values into one update_form! Each value must have its own full cycle.
       - Example: "Filter Color theo: Red, Blue -> Mỗi giá trị bấm filter rồi đợi 10s"
         → update_form(Color=Red) + click(Filter Data) + wait
         → update_form(Color=Blue) + click(Filter Data) + wait
       - If list has 10 values → Generate 30 actions (10 values × 3 actions each)
    
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
      {{{{ "action": "scan_tabs", "data": {{{{ "Cost": "10", "Stock": "5" }}}} }}}}
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
    
    Ex 5: "Clone EventGacha_ABC -> New ID: test_1, gate: feb2026_live, chọn radio Use another currency, currency: GachaShard_XYZ -> Sửa Schedule in UTC: 2026-02-23 00:00:00, 2026-02-23 11:00:00 -> Save"
    JSON: [
      {{{{ "action": "clone_row", "target": "EventGacha_ABC" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "New Event ID": "test_1",
          "Gate": "feb2026_live",
          "Use another currency": "select",
          "Currency": "GachaShard_XYZ"
      }}}} }}}},
      {{{{ "action": "save_form", "mode": "clone" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "Schedule in UTC": "2026-02-23 00:00:00, 2026-02-23 11:00:00"
      }}}} }}}},
      {{{{ "action": "save_form", "mode": "save" }}}}
    ]
    NOTE: save_form(mode="clone") clicks the Clone button in the modal.
          Fields AFTER the modal (Schedule, etc.) go in a SEPARATE update_form after save_form(clone).
          WRONG: merging "Schedule in UTC" into the first update_form!
    
    Ex 6: "Edit BossEvent_ABC -> Acquire lock -> sửa gate: LiveOpsTest -> Save -> Click menu Boss Details -> sửa Wrestler ID: SS_TheRock"
    JSON: [
      {{{{ "action": "edit_row", "target": "BossEvent_ABC" }}}},
      {{{{ "action": "wait" }}}},
      {{{{ "action": "update_form", "data": {{{{ "Gate": "LiveOpsTest" }}}} }}}},
      {{{{ "action": "save_form" }}}},
      {{{{ "action": "navigate", "target": "Boss Details" }}}},
      {{{{ "action": "update_form", "data": {{{{ "Wrestler ID": "SS_TheRock" }}}} }}}},
      {{{{ "action": "save_form" }}}}
    ]
    IMPORTANT NOTE: "Acquire lock" popup is handled AUTOMATICALLY by system after edit_row - DO NOT create separate click action for it!
    
    Ex 7: "Edit FF_Feb2026_Test -> sửa Gate: r80, Leaderboard Type: Bracketed, Bracket Preset: Bracket_Standard_24HR, Schedules In UTC: 02/10/2026 07:15 AM, 02/10/2026 11:00 AM -> Process Faction Feud"
    CRITICAL: MUST have save_form BEFORE process_deployment!
    JSON: [
      {{{{ "action": "edit_row", "target": "FF_Feb2026_Test" }}}},
      {{{{ "action": "wait" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "Gate": "r80",
          "Leaderboard Type": "Bracketed",
          "Bracket Preset": "Bracket_Standard_24HR",
          "Schedules In UTC": "02/10/2026 07:15 AM, 02/10/2026 11:00 AM"
      }}}} }}}},
      {{{{ "action": "save_form" }}}},
      {{{{ "action": "process_deployment", "options": ["Faction Feud"] }}}}
    ]
    WRONG (missing save_form): edit_row -> update_form -> process_deployment ❌
    
    Ex 8: "Vào Scout Missions tab -> sửa Scout Phase Start Time: 2025-08-20 10:00, End Time: 2025-08-25 15:00 -> Save"
    JSON: [
      {{{{ "action": "click", "target": "Scout Missions" }}}},
      {{{{ "action": "update_form", "data": {{{{ 
          "Scout Phase Start Time": "2025-08-20 10:00",
          "End Time": "2025-08-25 15:00"
      }}}} }}}},
      {{{{ "action": "save_form" }}}}
    ]
    
    Ex 9: "Export CSV file data.csv -> smart test file csv đó -> import file đó"
    JSON: [
      {{{{ "action": "download", "target": "Export CSV", "value": "data.csv" }}}},
      {{{{ "action": "smart_test_cycle", "value": "data.csv" }}}},
      {{{{ "action": "upload", "target": "Import CSV", "value": "data.csv" }}}}
    ]
    
    Ex 10: "Export -> smart test -> Click The Brick"
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
    
    Ex 11: "Vào Live Events -> Faction Feud -> Faction Feud Event -> Sửa FF ID: FF_Feb2026_Wknd2_Test_1 -> Đợi trang load -> sửa Gate: r80, Leaderboard Type: Bracketed"
    JSON: [
      {{{{ "action": "navigate", "path": ["Live Events", "Faction Feud", "Faction Feud Event"] }}}},
      {{{{ "action": "edit_row", "target": "FF_Feb2026_Wknd2_Test_1" }}}},
      {{{{ "action": "wait" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "Gate": "r80",
          "Leaderboard Type": "Bracketed"
      }}}} }}}},
      {{{{ "action": "save_form" }}}}
    ]
    
    Ex 12: "Sửa FF ID: FF_Feb2026_Test -> sửa Gate: r80, Leaderboard Type: Bracketed, Bracket Preset: Bracket_Standard_24HR, Schedules In UTC: 02/10/2026 07:15 AM, 02/10/2026 11:00 AM"
    EXPLANATION: 
      - "Bracket Preset" only appears AFTER changing "Leaderboard Type" to "Bracketed"
      - "Schedules In UTC" has 2 datetime inputs (Start, End) - keep comma-separated in ONE field
      - System will auto-split and fill both datetime inputs
    JSON: [
      {{{{ "action": "edit_row", "target": "FF_Feb2026_Test" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "Gate": "r80",
          "Leaderboard Type": "Bracketed",
          "Bracket Preset": "Bracket_Standard_24HR",
          "Schedules In UTC": "02/10/2026 07:15 AM, 02/10/2026 11:00 AM"
      }}}} }}}},
      {{{{ "action": "save_form" }}}}
    ]

    Ex 13: "Vào Live Events -> Versus -> Tournament -> Sửa ID: VS_Tournament_Feb2026_Wk1 -> Đợi trang load -> Sửa Gate: r80, Leaderboard Type: Bracketed, Bracket Preset: Bracket_Standard_24HR, PreEvent Phase Start Date Time(UTC): 02/11/2026 07:15 AM, PreEvent Phase End Date Time(UTC): 02/11/2026 11:00 AM, Lock Time Offset: 5 bấm nút save -> Active Phase Start Date Time (UTC): 02/11/2026 11:00 AM, Active Phase End Date Time (UTC): 02/14/2026 11:00 AM -> Bấm save & continue -> Bấm vào Menu Milestone Rewards -> Export CSV tournament_milestone.csv -> Import CSV -> Bấm save & continue -> Bấm The Brick -> Chọn Versus Tournament -> Process"
    EXPLANATION:
      - Section-qualified datetime fields: "PreEvent Phase Start Date Time(UTC)" keeps the section prefix
      - Lock Time Offset has an Edit button on the web page - system handles inline edit automatically
      - "bấm nút save" = save_form with mode="save" (just Save, NOT Save & Continue)
      - "Bấm save & continue" = save_form with mode="continue"
      - Separate update_form groups split by save actions
      - "Bấm vào Menu Milestone Rewards" = click sidebar item
      - Export then Import CSV reuses filename
    JSON: [
      {{{{ "action": "navigate", "path": ["Live Events", "Versus", "Tournament"] }}}},
      {{{{ "action": "edit_row", "target": "VS_Tournament_Feb2026_Wk1" }}}},
      {{{{ "action": "wait" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "Gate": "r80",
          "Leaderboard Type": "Bracketed",
          "Bracket Preset": "Bracket_Standard_24HR",
          "PreEvent Phase Start Date Time(UTC)": "02/11/2026 07:15 AM",
          "PreEvent Phase End Date Time(UTC)": "02/11/2026 11:00 AM",
          "Lock Time Offset": "5"
      }}}} }}}},
      {{{{ "action": "save_form", "mode": "save" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "Active Phase Start Date Time (UTC)": "02/11/2026 11:00 AM",
          "Active Phase End Date Time (UTC)": "02/14/2026 11:00 AM"
      }}}} }}}},
      {{{{ "action": "save_form", "mode": "continue" }}}},
      {{{{ "action": "click", "target": "Milestone Rewards" }}}},
      {{{{ "action": "download", "target": "Export CSV", "value": "tournament_milestone.csv" }}}},
      {{{{ "action": "upload", "target": "Import CSV", "value": "tournament_milestone.csv" }}}},
      {{{{ "action": "save_form", "mode": "continue" }}}},
      {{{{ "action": "process_deployment", "options": ["Versus Tournament"] }}}}
    ]

    Ex 14: "Vào Data Configs -> Boost -> Boost -> Filter Boost Result Value2 theo các giá trị: Blast, Protect, Countdown -> Mỗi giá trị bấm filter một lần sau đó đợi 10-15s"
    EXPLANATION:
      - User wants to filter by multiple values, testing EACH value separately
      - For EACH value: fill the field → click Filter button → wait
      - DO NOT combine all values into one update_form!
      - Pattern repeats for each value in the list
    JSON: [
      {{{{ "action": "navigate", "path": ["Data Configs", "Boost", "Boost"] }}}},
      {{{{ "action": "update_form", "data": {{{{ "Boost Result Value2": "Blast" }}}} }}}},
      {{{{ "action": "click", "target": "Filter Data" }}}},
      {{{{ "action": "wait" }}}},
      {{{{ "action": "update_form", "data": {{{{ "Boost Result Value2": "Protect" }}}} }}}},
      {{{{ "action": "click", "target": "Filter Data" }}}},
      {{{{ "action": "wait" }}}},
      {{{{ "action": "update_form", "data": {{{{ "Boost Result Value2": "Countdown" }}}} }}}},
      {{{{ "action": "click", "target": "Filter Data" }}}},
      {{{{ "action": "wait" }}}}
    ]

    Ex 15: "Vào Live Event -> Gacha Event -> Gacha Event -> Sửa EventGacha_test_15 -> Kiểm tra các giá trị sau xem có hiển thị trong các tab hay không: LinkedRBEs (Gacha Info tab), VipCarousel (Gacha Info tab), HardCurrencyValue (Gacha Token tab), CurrencyLinkedRBEs (Gacha Token tab), DescriptionLarge (Display Info tab), DetailHeadliner (Display Info tab) -> Nếu có giá trị hiển thị kết quả fail, nếu không có hiển thị kết quả pass"
    EXPLANATION:
      - User wants to check if fields are EMPTY (expected) or have unexpected values
      - check_fields action navigates to each sidebar tab and reads each field
      - FAIL = field has a value (unexpected); PASS = field is empty (expected)
      - Group fields by their tab, each key = tab name, value = list of field names
    JSON: [
      {{{{ "action": "navigate", "path": ["Live Event", "Gacha Event", "Gacha Event"] }}}},
      {{{{ "action": "edit_row", "target": "EventGacha_test_15" }}}},
      {{{{ "action": "wait" }}}},
      {{{{ "action": "check_fields", "data": {{{{
          "Gacha Info": ["LinkedRBEs", "VipCarousel"],
          "Gacha Token": ["HardCurrencyValue", "CurrencyLinkedRBEs"],
          "Display Info": ["DescriptionLarge", "DetailHeadliner"]
      }}}} }}}}
    ]

    Ex 16 (CLONE RANDOM - Faction Feud with New FF ID):
    Input: "Vào Faction Feud Event -> Clone một ID bất kỳ -> New FF ID: FF_Feb2026_Wknd4_FF2_2, Gate: r80 -> Đợi trang load -> Sửa Leaderboard Type: Normal, Consumable Limit: 99, Schedules In UTC: 02/24/2026 00:00 AM, 02/24/2026 11:00 AM -> Save -> Bấm vào logo The Brick -> Chọn checkbox Faction Feud -> Process"
    EXPLANATION:
      - "Clone một ID bất kỳ" = clone a random row → clone_row("RANDOM")
      - Clone modal fields: "New FF ID" (Faction Feud uses this instead of "New Event ID"), "Gate"
      - MUST have update_form for modal fields BEFORE save_form(mode=clone)!
      - After save_form(clone), wait for page load, then fill post-clone fields
      - Post-clone fields: Leaderboard Type, Consumable Limit, Schedules In UTC
    JSON: [
      {{{{ "action": "navigate", "path": ["Faction Feud Event"] }}}},
      {{{{ "action": "clone_row", "target": "RANDOM" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "New FF ID": "FF_Feb2026_Wknd4_FF2_2",
          "Gate": "r80"
      }}}} }}}},
      {{{{ "action": "save_form", "mode": "clone" }}}},
      {{{{ "action": "wait" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "Leaderboard Type": "Normal",
          "Consumable Limit": "99",
          "Schedules In UTC": "02/24/2026 00:00 AM, 02/24/2026 11:00 AM"
      }}}} }}}},
      {{{{ "action": "save_form", "mode": "save" }}}},
      {{{{ "action": "process_deployment", "options": ["Faction Feud"] }}}}
    ]
    NOTE: clone_row("RANDOM") MUST be followed by update_form for modal fields!
          WRONG: clone_row("RANDOM") → save_form(mode=clone) (missing update_form!)
          CORRECT: clone_row("RANDOM") → update_form({{New FF ID, Gate}}) → save_form(mode=clone)

    INPUT CONTEXT:
    - Original Command: "{user_command}"
    - Expert Analysis:
    {analysis_clean}

    OUTPUT REQUIREMENT:
    - Output ONLY the raw JSON list [ ... ].
    - No markdown formatting (no ```json).
    - No explanations.
    """

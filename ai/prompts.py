# prompts.py - Tập trung toàn bộ AI Prompt Templates
# File này chứa các prompt dạy AI, dễ dàng update mà không ảnh hưởng logic code.


def get_fast_mode_prompt(user_command):
    """
    Prompt cho Fast Mode (Single Model Pipeline - Qwen2.5-Coder)
    Sử dụng Few-Shot Learning với 14 examples.
    """
    return f"""You are a strict JSON converter. You MUST use action names from examples below.

CRITICAL: ONLY these action names are valid:
navigate, checkbox, download, upload, manipulate_csv, smart_test_cycle, process_deployment, clone_row, edit_row, update_form, save_form, click, wait, check_fields, reorder

LEARN FROM THESE 5 EXAMPLES (COPY the action names EXACTLY):

Example 1 (CLONE - MOST IMPORTANT):
Input: "Vào Live Events -> Gacha Event -> Gacha Event -> Clone ID: EventGacha_test_15 -> New ID: test_230226_8, gate: r80, radio: Use another currency, currency: GachaShard_Feb2026_Wknd1_Main -> Đợi trang load -> Sửa Schedule in UTC: 2026-02-23 00:00:00, 2026-02-23 11:00:00, sửa Milestones Type: Disable -> Bấm nút Save -> Bấm vào logo The Brick -> Chọn checkbox: Gacha Events -> Bấm nút Process"
Output: [{{"action":"navigate","path":["Live Events","Gacha Event","Gacha Event"]}},{{"action":"clone_row","target":"EventGacha_test_15"}},{{"action":"update_form","data":{{"New Event ID":"test_230226_8","Gate":"r80","Use another currency":"select","Currency":"GachaShard_Feb2026_Wknd1_Main"}}}},{{"action":"save_form","mode":"clone"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Schedule in UTC":"2026-02-23 00:00:00, 2026-02-23 11:00:00","Milestones Type":"Disable"}}}},{{"action":"save_form","mode":"save"}},{{"action":"process_deployment","options":["Gacha Events"]}}]

Example 2:
Input: "Vào Live Events -> Offer -> Offer Section -> Chọn 2 ID bất kỳ -> Export CSV test.csv"
Output: [{{"action":"navigate","path":["Live Events","Offer","Offer Section"]}},{{"action":"checkbox","target":"ID","value":"random_2"}},{{"action":"download","target":"Export CSV","value":"test.csv"}}]
RULE: "Chọn N [entity] bất kỳ" = checkbox(random_N), NOT edit_row. "Chọn/Tick/Select" + table row = checkbox. Only "Sửa/Edit" = edit_row.

Example 2b (SPECIFIC ID checkbox - NOT random):
Input: "Vào PVE -> Chọn ID "LTPVE_May2026_Wk4_Contest" -> Export CSV"
Output: [{{"action":"navigate","path":["Live Events","PVE","Classic PVE"]}},{{"action":"checkbox","target":"ID","value":"LTPVE_May2026_Wk4_Contest"}},{{"action":"download","target":"Export CSV"}}]
RULE: "Chọn ID 'SPECIFIC_ID'" = checkbox(target="ID", value="SPECIFIC_ID"). Use the EXACT ID string as value. NEVER use process_deployment for this. This selects a specific named row, different from "Chọn N ID bất kỳ" (random selection).

Example 3:
Input: "Click logo The Brick -> Chọn checkbox Offers -> Bấm Process"
Output: [{{"action":"process_deployment","options":["Offers"]}}]

Example 4:
Input: "Vào Data Configs -> Perk -> Edit ABC123"
Output: [{{"action":"navigate","path":["Data Configs","Perk"]}},{{"action":"edit_row","target":"ABC123"}}]

Example 4b (Superstar - EDIT RANDOM):
Input: "Vào Superstar -> Đợi trang load -> Sửa một Superstar bất kỳ"
Output: [{{"action":"navigate","path":["Superstar"]}},{{"action":"wait"}},{{"action":"edit_row","target":"RANDOM"}}]
RULE: "Sửa một [entity] bất kỳ" = edit_row("RANDOM"). The word before "bất kỳ" is the entity type, NOT a target ID.
RULE: "Sửa ID vừa clone" / "Sửa ID vừa tạo" = edit_row("RANDOM"). NEVER invent placeholder strings like "cloned_item_id".

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

Example 7 (NAVIGATE HOME ONLY — no Process):
Input: "Bấm logo The Brick"
Output: [{{"action":"process_deployment","options":[]}}]
RULE: "Bấm logo The Brick" or "Click logo" ALONE (WITHOUT "Chọn checkbox" and WITHOUT "Process" after it) = navigate home only. options MUST be []. Do NOT add any checkbox names to options.

Example 8 (NAVIGATE HOME ONLY — no Process):
Input: "Click The Brick"
Output: [{{"action":"process_deployment","options":[]}}]
RULE: Same — "Click The Brick" alone = navigate home, options=[]. NEVER add checkboxes unless user says "Chọn checkbox X -> Process".

Example 9:
Input: "Vào Data Configs -> Perk -> Perk"
Output: [{{"action":"navigate","path":["Data Configs","Perk","Perk"]}}]

Example 10b (EDIT CSV FILE - CRITICAL PATTERN):
Input: "Vào Perk -> Chọn 2 ID bất kỳ -> Export CSV -> Sửa Event Type: PVE_STIPULATION -> Import CSV file đó -> Bấm vào logo The Brick -> Chọn checkbox Perks -> Process"
Output: [{{"action":"navigate","path":["Perk"]}},{{"action":"checkbox","target":"ID","value":"random_2"}},{{"action":"download","target":"Export CSV","value":"perk.csv"}},{{"action":"manipulate_csv","target":"perk.csv","operation":"set","data":"Event Type=PVE_STIPULATION"}},{{"action":"upload","target":"Import CSV","value":"perk.csv"}},{{"action":"process_deployment","options":["Perks"]}}]
RULE for Example 10b: When "Sửa [Field]: [Value]" appears BETWEEN a download (Export CSV) and an upload (Import CSV), it means EDIT THE CSV FILE, NOT the web form. Use {{"action":"manipulate_csv","target":"<filename>","operation":"set","data":"<ColumnName>=<Value>"}}. The filename is the same as the downloaded file. NEVER use update_form for CSV file edits.

Example 10:
Input: "Export perk_test.csv -> Smart test -> Import -> Chọn checkbox Perks -> Bấm Process"
Output: [{{"action":"download","target":"Export CSV","value":"perk_test.csv"}},{{"action":"smart_test_cycle","value":"perk_test.csv"}},{{"action":"upload","target":"Import CSV","value":"perk_test.csv"}},{{"action":"process_deployment","options":["Perks"]}}]

Example 10c (STANDALONE PAGE-LEVEL IMPORT - no Export, no edit):
Input: "Vào PVE -> Import CSV file Book_test.csv -> Bấm vào logo The Brick"
Output: [{{"action":"navigate","path":["Live Events","PVE","Classic PVE"]}},{{"action":"upload","target":"Import CSV","value":"Book_test.csv"}},{{"action":"process_deployment","options":[]}}]
RULE for Example 10c: "Import CSV file <name>" on a list page (no preceding Export, no edit_row) is a SINGLE page-level import → exactly ONE {{"action":"upload","target":"Import CSV","value":"<name>"}}. NEVER emit "import_csv" or "process_import" (INVALID actions). NEVER repeat the import step — emit it ONCE only.

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
Output: [{{"action":"navigate","path":["Live Events","Versus","Tournament"]}},{{"action":"edit_row","target":"VS_Tournament_Feb2026_Wk1"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Gate":"r80","Leaderboard Type":"Bracketed","Bracket Preset":"Bracket_Standard_24HR","PreEvent Phase Start Date Time(UTC)":"02/11/2026 07:15 AM","PreEvent Phase End Date Time(UTC)":"02/11/2026 11:00 AM","Lock Time Offset":"5","Active Phase Start Date Time (UTC)":"02/11/2026 11:00 AM","Active Phase End Date Time (UTC)":"02/14/2026 11:00 AM"}}}},{{"action":"save_form","mode":"continue"}},{{"action":"click","target":"Milestone Rewards"}},{{"action":"download","target":"Export CSV","value":"tournament_milestone.csv"}},{{"action":"upload","target":"Import CSV","value":"tournament_milestone.csv"}},{{"action":"save_form","mode":"continue"}},{{"action":"process_deployment","options":["Versus Tournament"]}}]
RULE for Example 15: Inline edit fields (Lock Time Offset, Buffer Time, Post Event Duration) have their own inline Save buttons handled AUTOMATICALLY by the system. "bấm Save" after these fields = inline save (auto-handled), NOT main form Save. ALL phase fields (PreEvent + Active Phase) MUST go in ONE update_form because the form validates ALL phases on main Save.

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
Example 21 (CLONE Tournament + post-clone edit + Save & Continue - CRITICAL):
Input: "Vào Tournament -> Clone ID: VS_Tournament_Feb2026_Wknd3, New Tournament ID: VS_Tournament_HieuNM_Test_5, Gate: r80 -> Đợi trang load -> Sửa Leaderboard Type: Normal, Active Phase Schedules In UTC: 02/27/2026 03:30, 02/27/2026 04:00, Energy restart mode radio: Daily, Regen Time: 60 -> Save & Continue -> Bấm vào logo The Brick -> Chọn checkbox Versus Tournament -> Process"
Output: [{{"action":"navigate","path":["Tournament"]}},{{"action":"clone_row","target":"VS_Tournament_Feb2026_Wknd3"}},{{"action":"update_form","data":{{"New Tournament ID":"VS_Tournament_HieuNM_Test_5","Gate":"r80"}}}},{{"action":"save_form","mode":"clone"}},{{"action":"wait"}},{{"action":"update_form","data":{{"Leaderboard Type":"Normal","Active Phase Schedules In UTC":"02/27/2026 03:30, 02/27/2026 04:00","Energy restart mode radio":"Daily","Regen Time":"60"}}}},{{"action":"save_form","mode":"continue"}},{{"action":"process_deployment","options":["Versus Tournament"]}}]
RULE for Example 21: After save_form(mode=clone) closes the modal, "Đợi trang load" is a wait, then ALL fields mentioned before "Save & Continue" go into a NEW update_form, then save_form(mode=continue). NEVER jump from save_form(clone) directly to save_form(continue) without update_form in between!
Example 22 (STORE PREVIEW - Click a section/panel item by name):
Input: "Vào Offer -> Store Preview -> Đợi trang load -> Bấm vào Section_Drip_Offers"
Output: [{{"action":"navigate","path":["Live Events","Offer","Store Preview"]}},{{"action":"wait"}},{{"action":"click","target":"Section_Drip_Offers"}}]
RULE for Example 22: Items shown in content panels (Sections list, Offers list, etc.) are clicked with {{"action":"click","target":"ItemName"}}. Use only the name part WITHOUT the numeric ID in parentheses (e.g., "Section_Drip_Offers" NOT "Section_Drip_Offers (2147483647)").
Example 23 (REORDER / DRAG-AND-DROP priority):
Input: "Vào Store Preview -> Đợi trang load -> Bấm vào Section_Drip_Offers -> Kéo offer alex_drip_test lên vị trí 1"
Output: [{{"action":"navigate","path":["Live Events","Offer","Store Preview"]}},{{"action":"wait"}},{{"action":"click","target":"Section_Drip_Offers"}},{{"action":"reorder","target":"alex_drip_test","position":1}}]
RULE for Example 23: Use {{"action":"reorder"}} when user wants to drag an item to change its order/priority.
  - "target": name/ID of the item to drag (text matching the list row)
  - "position": 1-based destination index (1 = top/highest priority)
  - "before": name of the item to insert BEFORE (alternative to position)
  - "after": name of the item to insert AFTER (alternative to position)
  - Accepted phrasings: "kéo ... lên", "kéo ... xuống", "đổi thứ tự", "đổi priority", "drag ... to position", "move ... up/down", "đặt ... lên đầu"
  - EXAMPLES:
    * "Kéo alex_drip_test lên đầu" → {{"action":"reorder","target":"alex_drip_test","position":1}}
    * "Kéo alex_drip_test xuống dưới" (NO anchor = move to bottom of list) → {{"action":"reorder","target":"alex_drip_test","position":9999}}
    * "Kéo alex_drip_test lên trên" (NO anchor = move to top of list) → {{"action":"reorder","target":"alex_drip_test","position":1}}
    * "Kéo alex_drip_test xuống dưới quanvm_test_drip_offer_1" → {{"action":"reorder","target":"alex_drip_test","after":"quanvm_test_drip_offer_1"}}
    * "Đặt alex_drip_test trước quanvm_test_drip_offer_1" → {{"action":"reorder","target":"alex_drip_test","before":"quanvm_test_drip_offer_1"}}
    * "Di chuyển offer_A lên vị trí 2" → {{"action":"reorder","target":"offer_A","position":2}}
  - CRITICAL: "kéo X xuống dưới" / "move X down" WITHOUT naming another item → position:9999 (last). NEVER emit all-None!
  - CRITICAL: "target" MUST be the exact item name extracted from the user command (non-empty string). NEVER output {{"target":""}}, {{"target":null}}, or omit "target". If you cannot identify the item name, do NOT emit a reorder action at all.
Example 24 (SEARCH/FILTER - uses filter input, NOT checkbox):
Input: "Vào PVE -> Filter 1 Book bất kỳ -> Bấm vào logo The Brick"
Output: [{{"action":"navigate","path":["PVE"]}},{{"action":"update_form","data":{{"ID contains":"RANDOM"}}}},{{"action":"click","target":"Filter Data"}},{{"action":"process_deployment","options":[]}}]
RULE for Example 24: "Filter N/một [entity] bất kỳ" = type a keyword in the "ID contains" search box + click "Filter Data". Use "RANDOM" as the value — it will be resolved to an actual row ID at runtime. This is a SEARCH action, NOT checkbox row-selection. NEVER use checkbox for "Filter" — only "Chọn/Tick" means checkbox.
Example 24b (OFFER FILTER — also uses "ID contains"):
Input: "Vào Offer -> Filter một ID bất kỳ -> Bấm vào logo The Brick"
Output: [{{"action":"navigate","path":["Offer"]}},{{"action":"update_form","data":{{"ID contains":"RANDOM"}}}},{{"action":"click","target":"Filter Data"}},{{"action":"process_deployment","options":[]}}]
RULE for Example 24b: EVERY filter page (Offer, Offer Section, Drip Offer, PVE, RBE, Gacha, Currency, etc.) uses the SAME "ID contains" search box. ALWAYS use the key "ID contains" for any "Filter ... bất kỳ" command. NEVER use "Offer Name" or any other label.
CRITICAL RULES:
- NEVER use {{"action":"click","target":"The Brick"}} or {{"action":"click","target":"logo"}}
- "Bấm logo The Brick" / "Click logo" ALONE (no "Chọn checkbox" and no "Process" after) → {{"action":"process_deployment","options":[]}} (navigate home only, options MUST be [])
- ONLY add options AND use process_deployment with options when command EXPLICITLY says "Chọn checkbox X" AND "Bấm Process" / "Process" after the logo click
- EXAMPLE: "... -> Bấm vào logo The Brick" (end of command) → {{"action":"process_deployment","options":[]}}
- EXAMPLE: "... -> Bấm vào logo The Brick -> Chọn checkbox RBE -> Process" → {{"action":"process_deployment","options":["RBE"]}}

- CLONE ACTION (CRITICAL - NEVER SKIP):
  * "Bấm nút Clone ID: X", "Clone ID: X", "Clone X" → ALWAYS start with {{"action":"clone_row","target":"X"}}
  * RANDOM CLONE: "Clone bất kỳ", "Clone một ID bất kỳ", "Clone random" → {{"action":"clone_row","target":"RANDOM"}}
  * The word "ID" after "Clone" is part of the label ("Clone ID:"), NOT a form field name
  * AFTER clone_row, ALWAYS use update_form for modal fields (New ID/New FF ID/New Event ID, Gate, Currency, radio, etc.)
  * Clone modal field names vary by event type: "New Event ID" (Gacha), "New FF ID" (Faction Feud), "Cloned Rules Based Tournament ID" (RBE), "New ID" (generic)
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
  * CORRECT flow: clone_row → update_form(modal fields) → save_form(mode=clone) → wait → update_form(post-clone fields) → save_form(mode=save/continue)
  * WRONG flow: clone_row → update_form(modal fields + post-clone fields) → save_form (merging everything is WRONG!)
  * NEVER skip update_form between save_form(clone) and save_form(continue/save)!
  * "Đợi trang load -> Sửa X, Y, Z -> Save & Continue" AFTER clone = wait → update_form(X,Y,Z) → save_form(continue)
  * WRONG: save_form(clone) → save_form(continue)  ← MISSING update_form is ALWAYS WRONG!
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
  * "sửa [field]: [value]" BETWEEN a download/Export and an upload/Import step → USE manipulate_csv (editing the CSV file, NOT the web form)
  * manipulate_csv schema: {{"action":"manipulate_csv","target":"<filename>","operation":"set","data":"<ColumnName>=<Value>"}}
  * The target filename MUST match the previously downloaded file. Separate multiple CSV column edits with separate manipulate_csv steps.
  * Example: "Export perk.csv → Sửa Event Type: PVE_STIPULATION → Import perk.csv" = download + manipulate_csv(set,Event Type=PVE_STIPULATION) + upload. NEVER update_form here.
  * Example: "Sửa FF ID: FF_ABC -> Đợi trang load -> sửa Gate: r80" = edit_row("FF_ABC") + wait + update_form({{"Gate":"r80"}}) + save_form
  * WRONG: update_form({{"FF ID":"FF_ABC","Gate":"r80"}})
  * RANDOM ROW: "Sửa FF ID bất kỳ", "Sửa một dòng bất kỳ", "Edit any row", "Sửa bất kỳ" → edit_row("RANDOM")
  * "Sửa một [entity] bất kỳ" (e.g., "Sửa một Superstar bất kỳ") → edit_row("RANDOM"). The word before "bất kỳ" is entity type, NOT target ID.
  * Example: "Sửa Faction War ID bất kỳ" → {{"action":"edit_row","target":"RANDOM"}}
  * Example: "Sửa một Superstar bất kỳ" → {{"action":"edit_row","target":"RANDOM"}}
  * RECENTLY CLONED/CREATED ROW: "Sửa ID vừa clone", "Sửa ID vừa tạo", "edit the just-cloned row" → edit_row("RANDOM")
  * NEVER invent placeholder strings like "cloned_item_id", "last_clone_id", "new_item_id" — always use "RANDOM" when no concrete ID is given

- MULTIPLE DATETIME VALUES (IMPORTANT):
  * Fields like "Schedules In UTC" may have 2+ datetime inputs (Start, End)
  * Keep comma-separated values in ONE string: "02/10/2026 07:15 AM, 02/10/2026 11:00 AM"
  * System will auto-split and fill each datetime input
  * DO NOT create separate fields for Start/End

- MULTIPLE FIELDS SEPARATED BY COMMA (IMPORTANT):
  * When command has "Field1: val1, Field2: val2" (each part has its own colon), they are SEPARATE fields
  * Create SEPARATE JSON keys for each: {{"Field1": "val1", "Field2": "val2"}}
  * WRONG: {{"Field1": "val1, Field2": "val2"}} — merging key into the value is invalid JSON
  * Example: "Enter Superstars or Groups: Body_OOsbourne, Attempt: 10000"
    → {{"Superstars or Groups": "Body_OOsbourne", "Attempt": "10000"}}
  * Rule: if a segment after a comma contains ":", it is a new field, NOT part of the previous value

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

- SIDEBAR / PANEL ITEM CLICK:
  * "Bấm vào Menu X ở bên trái", "Click sidebar X" → {{"action":"click","target":"X"}}
  * "Bấm vào Section_Drip_Offers", "Click Section_Drip_Offers" → {{"action":"click","target":"Section_Drip_Offers"}}
  * Items in content panels (Store Preview sections, Offer lists, etc.) use {{"action":"click","target":"ItemName"}}
  * Use ONLY the name part — DO NOT include numeric IDs in parentheses

- REORDER / DRAG-AND-DROP (items with ≡ handles):
  * Use when user wants to change the order/priority of rows or panel items by dragging
  * The ≡ (3-line) icon on a row indicates it is draggable
  * Schema: {{"action":"reorder","target":"<item_name>","position":<1-based-int>}}
    OR:    {{"action":"reorder","target":"<item_name>","before":"<other_item>"}}
    OR:    {{"action":"reorder","target":"<item_name>","after":"<other_item>"}}
  * "target": name/ID of the item to drag (exact text shown in the list)
  * "position": 1-based destination index (1 = top/first = highest priority)
  * "before": insert target before this named item
  * "after":  insert target after this named item
  * Accepted phrasings: "kéo ... lên trên", "kéo ... xuống dưới", "đổi thứ tự", "đổi priority",
    "di chuyển ... lên vị trí X", "đặt ... lên đầu", "move ... up", "drag ... to position X"
  * EXAMPLES:
    - "Kéo alex_drip_test lên đầu" → {{"action":"reorder","target":"alex_drip_test","position":1}}
    - "Kéo alex_drip_test xuống dưới quanvm_test_drip_offer_1" → {{"action":"reorder","target":"alex_drip_test","after":"quanvm_test_drip_offer_1"}}
    - "Đặt alex_drip_test trước quanvm_test_drip_offer_1" → {{"action":"reorder","target":"alex_drip_test","before":"quanvm_test_drip_offer_1"}}
    - "Di chuyển offer_A lên vị trí 2" → {{"action":"reorder","target":"offer_A","position":2}}

- INLINE EDIT FIELDS (Lock Time Offset, Buffer Time, Post Event Duration, Player-Base Gathering Time):
  * These fields have their own Edit button and inline Save button on the web page
  * System handles clicking Edit, filling value, and clicking inline Save AUTOMATICALLY
  * When user says "Sửa Lock Time Offset: 5 sau đó bấm Save", the "bấm Save" = inline save (auto-handled)
  * DO NOT generate a separate save_form action for inline edit fields!
  * Just include them in update_form data normally, system auto-handles the rest

- MULTI-PHASE FORMS (Tournament, etc.) - FILL ALL BEFORE SAVE:
  * Forms with multiple phases (PreEvent, Active, Post Event) validate ALL phases when main Save is clicked
  * ALL phase fields MUST go in ONE update_form before save_form
  * "bấm Save" after inline edit fields (Lock Time Offset, Buffer Time, Post Event Duration) = inline save, NOT main Save
  * Only the FINAL "Save" or "Save & Continue" at the end of ALL fields = main save_form
  * CORRECT: update_form(PreEvent fields + Lock Time Offset + Active Phase fields + Buffer Time + Post Event Duration) → save_form(mode=continue)
  * WRONG: update_form(PreEvent fields) → save_form(mode=save) → update_form(Active Phase fields) → save_form(mode=continue)
  * The WRONG pattern causes validation error: "Active Phase End Date must be after Start Date"

- SPLITTING FORM UPDATES ACROSS SAVE ACTIONS:
  * When user says "fill A -> save -> fill B -> save & continue" AND the fields are in DIFFERENT pages/sections loaded by Save
  * Create SEPARATE update_form actions for each group
  * EXCEPTION: Do NOT split if fields are on the SAME page (e.g., multi-phase forms like Tournament)
  * EXCEPTION: "bấm Save" after inline edit fields (Lock Time Offset, Buffer Time, Post Event Duration) is NOT a main save

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

- FILTER SINGLE ITEM (CRITICAL - NOT a checkbox):
  * "Filter 1/một/N [entity] bất kỳ" → fill the filter search box with "RANDOM" + click "Filter Data"
  * "RANDOM" is a sentinel resolved at runtime to an actual visible row ID in the table.
  * "Filter" ALWAYS means using the search input box — NEVER a checkbox row-selection
  * ONLY "Chọn/Tick/Select N [entity]" triggers {{"action":"checkbox"}}
  * ⚠️ The filter field name is ALWAYS "ID contains" — EVERY page (PVE, RBE, Gacha,
    Currency, Fight Card, Superstar, Offer, Offer Section, Drip Offer, etc.) uses the
    same "ID contains" search box. NEVER use "Offer Name" or any per-page label.
  * Example (PVE): "Filter 1 Book bất kỳ" → update_form({{"ID contains":"RANDOM"}}) + click("Filter Data")
  * Example (Offer): "Filter một ID bất kỳ" on Offer page → update_form({{"ID contains":"RANDOM"}}) + click("Filter Data")
  * WRONG: {{"action":"checkbox","target":"Book","value":"random_1"}} for "Filter 1 Book bất kỳ"
  * CORRECT (all pages): update_form({{"ID contains":"RANDOM"}}) + click("Filter Data")

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
       - RECENTLY CLONED/CREATED: "Sửa ID vừa clone", "Sửa ID vừa tạo" → edit_row("RANDOM"). NEVER use placeholder strings like "cloned_item_id".
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
       - Clone modal field names vary by event type: "New Event ID" (Gacha), "New FF ID" (Faction Feud), "Cloned Rules Based Tournament ID" (RBE), "New ID" (generic)
       - NEVER skip update_form for modal fields! clone_row → save_form(clone) without update_form is WRONG!
       - Example: "Clone một ID bất kỳ -> New FF ID: FF_Test, Gate: r80" =
         * clone_row("RANDOM") + update_form({{New FF ID: FF_Test, Gate: r80}}) + save_form(mode=clone)
       - Example: "Bấm nút Clone ID: EventGacha_test_15 -> New ID: test_230226, gate: r80" =
         * clone_row("EventGacha_test_15") + update_form({{New Event ID: test_230226, Gate: r80}}) + save_form
       - WRONG: clone_row → save_form(clone) (missing update_form for modal fields!)
       - WRONG: jumping directly to update_form without clone_row!
       - POST-CLONE FIELDS (CRITICAL): Fields mentioned AFTER "Đợi trang load" / "wait" come AFTER save_form(clone)
         * Pattern: clone modal → save_form(clone) → wait → update_form(post-clone fields) → save_form(mode=save/continue)
         * NEVER: save_form(clone) → save_form(continue) without update_form in between!
         * "Đợi trang load -> Sửa X -> Save & Continue" = wait + update_form(X) + save_form(mode=continue)
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
       - EXCEPTION: "bấm Save" after inline edit fields (Lock Time Offset, Buffer Time, Post Event Duration) = inline save (auto-handled), NOT main save
       - For multi-phase forms (Tournament): ALL phases go in ONE update_form, only the FINAL Save generates save_form
    15. **SIDEBAR / PANEL ITEM CLICK**: "Bấm vào Menu X ở bên trái" = Click sidebar item X (action: click, target: X).
        Also applies to items in content panels, e.g. "Bấm vào Section_Drip_Offers" in Store Preview = click(target="Section_Drip_Offers").
        Use ONLY the name part — do NOT include numeric IDs in parentheses.
    16. **INLINE EDIT FIELDS** (CRITICAL - Lock Time Offset, Buffer Time, Post Event Duration, Player-Base Gathering Time):
       - These fields are read-only by default with "Edit" button next to them
       - System handles clicking Edit, filling value, and clicking inline Save AUTOMATICALLY
       - Just include them in update_form data normally
       - When user says "Sửa Lock Time Offset: 5 sau đó bấm Save", the "bấm Save" = inline save (auto-handled)
       - DO NOT generate a separate save_form action for inline edit field saves!
       - DO NOT split update_form at inline edit fields' save points!
    16b. **MULTI-PHASE FORMS (Tournament, etc.) - FILL ALL BEFORE SAVE** (CRITICAL):
       - Forms with multiple phases (PreEvent Phase, Active Phase, Post Event) validate ALL phases on main Save
       - ALL phase fields MUST go in ONE update_form, then ONE save_form at the end
       - WRONG: update_form(PreEvent) → save_form → update_form(Active) → save_form (causes validation error!)
       - CORRECT: update_form(PreEvent + Active + inline fields) → save_form(mode=continue)
    17. **FILTERING WITH MULTIPLE VALUES** (CRITICAL):
       - Pattern: "Filter [Field] theo các giá trị: A, B, C -> Mỗi giá trị bấm filter một lần sau đó đợi X giây"
       - This means: For EACH value, do 3 actions: update_form → click Filter button → wait
       - Example: "Filter Color: Red, Blue -> Each value click filter then wait 10s"
         * Step 1: Fill Color=Red → Click Filter Data → Wait
         * Step 2: Fill Color=Blue → Click Filter Data → Wait
       - DO NOT group all values into one update_form!
       - Common filter button names: "Filter Data", "Filter", "Apply Filter"
    18. **REORDER / DRAG-AND-DROP** (items with ≡ handle):
       - Use when user says: "kéo ... lên", "kéo ... xuống", "đổi thứ tự", "đổi priority",
         "di chuyển lên vị trí X", "đặt lên đầu", "move up", "drag to position"
       - These are list/panel items with a 3-line grip (≡) that can be reordered
       - Extract: WHAT to move (target name), WHERE to move it (position number, or before/after which item)
       - Example: "Kéo alex_drip_test lên đầu" = reorder action, target=alex_drip_test, position=1
       - Example: "Kéo alex_drip_test xuống dưới quanvm_test_drip_offer_1" = reorder, after=quanvm_test_drip_offer_1

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
    - clone_row, edit_row, update_form, save_form, scan_tabs, check_fields, click, wait, process_deployment, reorder
    
    INVALID action names (NEVER USE): select_random_ids, export_csv, import_csv, click_logo, select_checkbox, click_button ❌

    AVAILABLE ACTIONS:
    1. "navigate": 
       - RULE: Always merge menu path into ONE action with "path" array
       - Format: {{{{ "action": "navigate", "path": ["Menu1", "Menu2", "Menu3"] }}}}
       - Example: "Vào Data Configs -> Perk -> Perk" -> {{{{ "action": "navigate", "path": ["Data Configs", "Perk", "Perk"] }}}}
       - NEVER generate multiple separate navigate actions
    2. "checkbox":
       - Rule: Use ONLY for selecting rows in a DATA TABLE ("Chọn", "Tick", "Select" a row/ID).
       - Format: {{{{ "action": "checkbox", "target": "ColumnName", "value": "random_N" or "all" or "SPECIFIC_ID" }}}}
       - Example (random): "Chọn 2 BagID bất kỳ" -> value: "random_2", target: "BagID".
       - Example (specific ID): "Chọn ID 'LTPVE_May2026_Wk4_Contest'" -> {{{{"action":"checkbox","target":"ID","value":"LTPVE_May2026_Wk4_Contest"}}}}
       - RULE: "Chọn ID 'X'" or "Chọn [entity] 'X'" with a NAMED ID = checkbox with value="X" (exact ID string). NOT process_deployment.
       - ⚠️ IMPORTANT: "Bỏ chọn checkbox <Label>" / "Tick checkbox <Label>" / "Un-tick <Label>" referring to a FILTER or UI toggle (NOT a table row) → use update_form instead:
         Example: "Bỏ chọn checkbox Hide LiveOpsTest gate items" → {{{{"action":"update_form","data":{{{{"Hide LiveOpsTest gate items checkbox":"false"}}}}}}}}
         Example: "Tick checkbox Hide Feeders" → {{{{"action":"update_form","data":{{{{"Hide Feeders checkbox":"true"}}}}}}}}
         Rule: if the target of "checkbox" is a page filter/UI label (not a column in the table), use update_form with key "<Label> checkbox".
       - ⚠️ CRITICAL: "Filter N/một [entity] bất kỳ" is NOT a checkbox action!
         "Filter" = search using the filter input box + click "Filter Data".
         "RANDOM" is a sentinel resolved at runtime to an actual visible row ID.
         Only "Chọn/Tick/Select N [entity]" triggers checkbox action.
         ⚠️ Filter field name is ALWAYS "ID contains" on EVERY page
           (Offer/Offer Section/Drip Offer/PVE/RBE/Gacha/Currency/etc.).
           NEVER use "Offer Name" or any other label.
         WRONG: {{{{"action":"checkbox","target":"Book","value":"random_1"}}}} for "Filter 1 Book bất kỳ"
         CORRECT (all pages): update_form({{"ID contains":"RANDOM"}}) + click("Filter Data")
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
       - "Sửa một [entity] bất kỳ" (e.g., "Sửa một Superstar bất kỳ") → target = "RANDOM" (the entity type is NOT a target ID)
       - RECENTLY CLONED/CREATED: "Sửa ID vừa clone", "Sửa ID vừa tạo" → target = "RANDOM". NEVER invent placeholder strings like "cloned_item_id", "last_clone_id", "new_item_id".
       - Example: "Sửa Faction War ID bất kỳ" → {{{{ "action": "edit_row", "target": "RANDOM" }}}}
       - Example: "Sửa một Superstar bất kỳ" → {{{{ "action": "edit_row", "target": "RANDOM" }}}}
       - Example: "Sửa ID vừa clone" → {{{{ "action": "edit_row", "target": "RANDOM" }}}}
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
    15. "reorder": {{{{ "action": "reorder", "target": "item_name", "position": N }}}}
        - Use when user wants to drag an item (with ≡ handle) to change its order/priority
        - "target": the name/ID of the item to drag
        - One of: "position" (1-based int), "before" (item name), or "after" (item name)
        - Accepted phrasings: "kéo ... lên", "kéo ... xuống", "đổi thứ tự", "đổi priority",
          "di chuyển ... lên vị trí X", "đặt ... lên đầu", "move ... up", "drag ... to position X"
        - EXAMPLES:
          * "Kéo alex_drip_test lên đầu" → {{{{ "action": "reorder", "target": "alex_drip_test", "position": 1 }}}}
          * "Kéo alex_drip_test xuống dưới quanvm" → {{{{ "action": "reorder", "target": "alex_drip_test", "after": "quanvm" }}}}
          * "Đặt offer_A trước offer_B" → {{{{ "action": "reorder", "target": "offer_A", "before": "offer_B" }}}}
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
       - "Bấm vào logo The Brick" / "Click logo" / "Về Home" ALONE (without "Chọn checkbox" and without "Process") → {{{{ "action": "process_deployment", "options": [] }}}} (navigate home only — do NOT add any checkbox to options)
       - ONLY generate process_deployment WITH options when command EXPLICITLY has BOTH "Chọn checkbox X" AND "Bấm Process" / "Process" keywords
       - EXAMPLE "Bấm vào logo The Brick" alone → {{{{ "action": "process_deployment", "options": [] }}}}
       - EXAMPLE "Bấm vào logo The Brick -> Chọn checkbox RBE -> Process" → {{{{ "action": "process_deployment", "options": ["RBE"] }}}}
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
         * Example: "Schedules In UTC: 02/10/2026, 07:15 AM - 02/10/2026, 11:00 AM"
           -> {{{{ "Schedules In UTC": "02/10/2026, 07:15 AM - 02/10/2026, 11:00 AM" }}}}
         * System will auto-detect and split to fill multiple datetime inputs
         * DO NOT create separate "Start Time" and "End Time" fields unless explicitly mentioned

       - **MULTIPLE FIELDS SEPARATED BY COMMA** (CRITICAL):
         * When command has "Field1: val1, Field2: val2" (each part has its own colon), they are SEPARATE fields
         * Create SEPARATE JSON keys: {{{{ "Field1": "val1", "Field2": "val2" }}}}
         * WRONG: {{{{ "Field1": "val1, Field2": "val2" }}}} — this is invalid JSON and wrong semantics
         * Example: "Enter Superstars or Groups: Body_OOsbourne, Attempt: 10000"
           -> {{{{ "Superstars or Groups": "Body_OOsbourne", "Attempt": "10000" }}}}
         * Rule: if a segment after a comma contains ":", treat it as a new field key

       - **SECTION-QUALIFIED DATETIME FIELDS** (IMPORTANT):
         * When user specifies "PreEvent Phase Start Date Time(UTC)", "Active Phase End Date Time (UTC)"
         * Use the FULL label including section prefix as the key
         * This helps system find the correct field when multiple sections have same field names
         * Examples:
           - "PreEvent Phase Start Date Time(UTC): 02/11/2026, 07:15 AM" → key = "PreEvent Phase Start Date Time(UTC)"
           - "Active Phase End Date Time (UTC): 02/14/2026, 11:00 AM" → key = "Active Phase End Date Time (UTC)"
         * DO NOT strip the section prefix!

       - **SAVE_FORM MODE** (IMPORTANT):
         * "bấm save", "bấm nút save", "click Save", "nhấn Save" → {{{{ "action": "save_form", "mode": "save" }}}} (just Save, NOT Save & Continue)
         * "bấm save & continue", "Save & Continue" → {{{{ "action": "save_form", "mode": "continue" }}}}
         * Default (no specific instruction): {{{{ "action": "save_form" }}}} = auto-detect

       - **INLINE EDIT FIELDS** (Lock Time Offset, Buffer Time, Post Event Duration, Player-Base Gathering Time):
         * These have Edit + inline Save buttons handled AUTOMATICALLY by the system
         * "Sửa Lock Time Offset: 5 sau đó bấm Save" → the "bấm Save" is the inline save (auto-handled)
         * DO NOT generate a separate save_form action for inline edit field saves!
         * Just include them in update_form data; system auto-handles Edit → fill → inline Save

       - **MULTI-PHASE FORMS - FILL ALL BEFORE SAVE** (CRITICAL):
         * Tournament and similar forms with multiple phases (PreEvent, Active, Post Event) validate ALL phases on main Save
         * ALL phase fields + inline edit fields MUST go in ONE update_form, then ONE save_form
         * WRONG: update_form(PreEvent) → save_form(save) → update_form(Active) → save_form(continue)
           This causes: "Active Phase End Date must be after Start Date" validation error!
         * CORRECT: update_form(PreEvent + Lock Time Offset + Active Phase + Buffer Time + Post Event Duration) → save_form(continue)

       - **SPLITTING FORM UPDATES ACROSS SAVE ACTIONS**:
         * When user says "fill A, B -> save -> fill C, D -> save & continue" AND fields are on DIFFERENT pages
         * Create SEPARATE update_form actions for each group split by save
         * EXCEPTION: Do NOT split if all fields are on the SAME page (e.g., multi-phase forms)
         * EXCEPTION: "bấm Save" after inline edit fields = inline save (auto-handled), NOT main form save

       - **SIDEBAR/PANEL ITEM CLICK**:
         * "Bấm vào Menu X ở bên trái", "Click sidebar X" → {{{{ "action": "click", "target": "X" }}}}
         * "Bấm vào Section_Drip_Offers", "Bấm vào [any panel item]" → {{{{ "action": "click", "target": "Section_Drip_Offers" }}}}
         * Used for sidebar navigation AND for clicking items in content panels (Store Preview sections, offer/section list items, etc.)
         * Use ONLY the name part — do NOT include numeric IDs in parentheses, e.g. use "Section_Drip_Offers" not "Section_Drip_Offers (2147483647)"

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
         * RBE: "Cloned Rules Based Tournament ID"
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
           clone_row(A) → update_form({{modal fields}}) → save_form(mode=clone) → wait → update_form({{post-clone fields}}) → save_form(mode=save/continue)
         WRONG:
           clone_row(A) → update_form({{modal fields + post-clone fields}}) → save_form ← DO NOT merge!
         WRONG (CRITICAL - NEVER DO THIS):
           save_form(mode=clone) → save_form(mode=continue) ← ALWAYS need update_form in between!
         "Đợi trang load -> Sửa X, Y -> Save & Continue" after clone = wait → update_form(X,Y) → save_form(mode=continue)
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
          CRITICAL: NEVER generate save_form(clone) immediately followed by save_form(continue/save)!
          "Đợi trang load -> Sửa X, Y -> Save & Continue" after clone MUST become:
          wait → update_form(X, Y fields) → save_form(mode=continue)   ← ALWAYS required!
    
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
      - Lock Time Offset has an Edit button - system handles inline edit + inline save AUTOMATICALLY
      - "bấm nút save" after Lock Time Offset = inline save (auto-handled), NOT main form Save
      - ALL phase fields (PreEvent + Active) MUST go in ONE update_form because form validates all phases on Save
      - WRONG: split into two update_forms with save_form in between → causes "Active Phase End Date must be after Start Date" error!
      - "Bấm save & continue" at the END = main save_form with mode="continue"
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
          "Lock Time Offset": "5",
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

    Ex 17 (CLONE Tournament + post-clone edit + Save & Continue):
    Input: "Vào Tournament -> Clone ID: VS_Tournament_Feb2026_Wknd3, New Tournament ID: VS_Tournament_HieuNM_Test_5, Gate: r80 -> Đợi trang load -> Sửa Leaderboard Type: Normal, Active Phase Schedules In UTC: 02/27/2026 03:30, 02/27/2026 04:00, Energy restart mode radio: Daily, Regen Time: 60 -> Save & Continue -> Bấm vào logo The Brick -> Chọn checkbox Versus Tournament -> Process"
    EXPLANATION:
      - Clone modal fields (before "Đợi trang load"): New Tournament ID, Gate → go in first update_form
      - save_form(mode=clone) closes the modal
      - "Đợi trang load" → wait action
      - Post-clone fields (after "Đợi trang load", before "Save & Continue"): Leaderboard Type, Schedules, radio, Regen Time → go in second update_form
      - "Save & Continue" → save_form(mode=continue)
      - CRITICAL: NEVER skip the second update_form! save_form(clone) cannot be directly followed by save_form(continue)!
    JSON: [
      {{{{ "action": "navigate", "path": ["Tournament"] }}}},
      {{{{ "action": "clone_row", "target": "VS_Tournament_Feb2026_Wknd3" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "New Tournament ID": "VS_Tournament_HieuNM_Test_5",
          "Gate": "r80"
      }}}} }}}},
      {{{{ "action": "save_form", "mode": "clone" }}}},
      {{{{ "action": "wait" }}}},
      {{{{ "action": "update_form", "data": {{{{
          "Leaderboard Type": "Normal",
          "Active Phase Schedules In UTC": "02/27/2026 03:30, 02/27/2026 04:00",
          "Energy restart mode radio": "Daily",
          "Regen Time": "60"
      }}}} }}}},
      {{{{ "action": "save_form", "mode": "continue" }}}},
      {{{{ "action": "process_deployment", "options": ["Versus Tournament"] }}}}
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


def get_patch_prompt(user_command, base_command, base_plan):
    """
    Prompt cho chế độ patch context.
    Dùng khi user đã load một scenario có sẵn và chỉ sửa vài data nhỏ.
    Model sẽ ưu tiên tái sử dụng plan cũ, chỉ chỉnh các field/step bị thay đổi.
    """
    base_plan_json = base_plan
    if not isinstance(base_plan_json, str):
        import json as _json

        base_plan_json = _json.dumps(base_plan_json, ensure_ascii=False, indent=2)

    return f"""
You are a strict JSON action-plan patcher.

You will receive:
1) BASE COMMAND: the previously loaded scenario command
2) BASE JSON PLAN: the previously loaded plan
3) NEW COMMAND: the edited command

Your job:
- Return the JSON plan for NEW COMMAND.
- If NEW COMMAND is only a small edit of BASE COMMAND, preserve the existing step order and modify only the changed fields.
- If the command changed more substantially, you may rewrite the plan, but still output only the final JSON array.
- Do NOT explain anything.
- Do NOT output markdown.
- Do NOT wrap the result in code fences.

Hard rules:
- Keep valid action names only.
- Keep navigation merged into one navigate action with path array.
- Keep save_form modes exactly when required.
- Preserve existing steps unless they must change.
- If the command is identical, return the base plan unchanged.

BASE COMMAND:
{base_command}

BASE JSON PLAN:
{base_plan_json}

NEW COMMAND:
{user_command}

OUTPUT ONLY JSON ARRAY:
"""

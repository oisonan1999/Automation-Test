# Brick QA Automation — Tài liệu cấu trúc dự án

> **Tác giả:** HieuNM  
> **Mục đích:** Hệ thống QA Automation dùng AI để chuyển lệnh ngôn ngữ tự nhiên (tiếng Việt/Anh) thành hành động tự động trên web app **"The Brick"** — công cụ quản lý LiveOps cho game mobile.

---

## Mục lục

- [[#Tổng quan kiến trúc]]
- [[#Cấu trúc thư mục]]
- [[#Chi tiết từng thành phần]]
  - [[#1. app.py — Giao diện người dùng]]
  - [[#2. ai/brain.py — AI Orchestrator]]
  - [[#3. ai/prompts.py — Prompt Templates]]
  - [[#4. ai/action_fixer.py — Post-Processing Engine]]
  - [[#5. automation/core.py — Execution Engine]]
  - [[#6. automation/navigator.py — Navigation Engine]]
  - [[#7. automation/form_handler.py — Form Handler]]
  - [[#8. automation/table_handler.py — Table Handler]]
  - [[#9. automation/smart_tester.py — Smart Test Cycle]]
  - [[#10. config/ — Cấu hình]]
- [[#Technology Stack]]
- [[#Điểm đặc biệt của thiết kế]]

---

## Tổng quan kiến trúc

```
User Input (tiếng Việt/Anh)
        ↓
    AI Layer (ai/)
  Phân tích → JSON Action Plan
        ↓
  Automation Layer (automation/)
  Thực thi từng bước trên browser
        ↓
  Kết quả hiển thị trên Streamlit UI (app.py)
```

---

## Cấu trúc thư mục

```
project/
├── app.py                    # UI chính (Streamlit)
├── ai/                       # AI Layer
│   ├── __init__.py
│   ├── brain.py              # Orchestrator pipeline
│   ├── prompts.py            # Prompt templates
│   └── action_fixer.py       # Post-processing / auto-fix
├── automation/               # Browser Automation Layer
│   ├── __init__.py
│   ├── core.py               # Entry point, dispatcher
│   ├── navigator.py          # Menu navigation, click
│   ├── form_handler.py       # Form filling, dropdown, save
│   ├── table_handler.py      # Checkbox, edit/clone row, reorder
│   ├── data_handler.py       # CSV download/upload/manipulate
│   ├── smart_tester.py       # Fuzz testing cycle
│   └── constants.py          # Đường dẫn download
├── config/
│   ├── auth.json             # Cookie/session đăng nhập
│   └── scenarios.json        # Kịch bản đã lưu
├── scripts/
│   ├── setup_login.py        # Script đăng nhập lần đầu
│   ├── start_chrome.sh       # Khởi động Chrome debug (Mac)
│   └── start_chrome_win.sh   # Khởi động Chrome debug (Windows)
├── downloads/                # Thư mục chứa file CSV
├── .env                      # Config API keys, URL
└── requirements.txt
```

---

## Chi tiết từng thành phần

### 1. app.py — Giao diện người dùng

Là điểm vào chính của ứng dụng, xây dựng bằng **Streamlit**. Cung cấp:

- **Text area** nhập lệnh tự nhiên
- **Fast Mode / Careful Mode** toggle — chọn pipeline AI
- **Load / Save kịch bản** — lưu để tái sử dụng sau
- **Hiển thị JSON Plan** — xem kế hoạch AI tạo ra trước khi chạy
- **Bảng kết quả** với màu sắc phân biệt PASS / FAIL / WARNING
- **Streaming log** real-time trong quá trình AI xử lý và automation chạy

Kết nối với browser Chrome thông qua **CDP (Chrome DevTools Protocol)** trên cổng `9222`.

---

### 2. ai/brain.py — AI Orchestrator

Đây là bộ não điều phối toàn bộ pipeline AI. Có hai chế độ hoạt động:

#### Fast Mode (Single Model Pipeline)

- Chỉ dùng model `qwen2.5-coder:14b`
- Dùng few-shot prompting với 20+ examples chi tiết
- Thời gian xử lý: ~20–40 giây
- Tự động fallback sang Careful Mode nếu thất bại

#### Careful Mode (Dual Model Pipeline)

```
Bước 1: DeepSeek-R1:8b (Reasoning Phase)
        → Phân tích lệnh, xác định intent
        → Output: plain text analysis
        → Unload ngay để nhường VRAM

Bước 2: Qwen2.5-Coder:14b (Formatting Phase)
        → Nhận analysis từ bước 1
        → Output: JSON Action Plan chính xác
```

#### Complexity Detection

Tự động phát hiện lệnh phức tạp để escalate sang Careful Mode dựa trên:

| Tiêu chí | Ngưỡng |
|----------|--------|
| Từ khóa logic | "nếu", "hoặc", "for each", "lặp lại", `\bor\b`, `\bif\b` |
| Số bước (dấu `->`) | > 7 bước |
| Độ dài lệnh | > 350 ký tự |
| Số lượng action keywords | > 6 từ |

#### Cấu hình Model

| Biến | Giá trị | Mục đích |
|------|---------|----------|
| `MODEL_REASONING` | `deepseek-r1:8b` | Reasoning phase (19.7 tok/s) |
| `MODEL_FORMATTING` | `qwen2.5-coder:14b` | Formatting phase (JSON chính xác) |
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | Endpoint Ollama local |

#### Context Management

- Dùng `keep_alive: "10m"` để giữ model trong VRAM giữa các request (tận dụng KV cache)
- `ensure_clean_context()` force-unload model nếu đang load với context > 16384 (tránh swap RAM)

---

### 3. ai/prompts.py — Prompt Templates

Chứa 3 prompt functions tách biệt:

#### `get_fast_mode_prompt(user_command)`

Prompt cho Qwen chạy một mình trong Fast Mode. Bao gồm:

- **23 examples** chi tiết covering các tình huống: navigate, clone, edit, process deployment, filter, check_fields, reorder...
- **CRITICAL RULES** về action mapping (không dùng `click("The Brick")`, phải dùng `process_deployment`)
- Quy tắc phân biệt context:
  - CSV edit (giữa Export và Import) → `manipulate_csv`, KHÔNG dùng `update_form`
  - Clone modal fields vs post-clone fields
  - Inline edit fields (Lock Time Offset...) được system tự xử lý

#### `get_reasoning_prompt(user_command)`

Prompt cho DeepSeek-R1 trong Careful Mode — chỉ phân tích intent, KHÔNG tạo JSON. Hướng dẫn phân tích:

- Menu paths, filenames, action types
- Context detection cho "Sửa" (edit row ID vs update form field)
- Clone flow, wait actions, section-qualified fields
- Multi-phase forms, filtering với multiple values

#### `get_formatting_prompt(user_command, analysis_clean)`

Prompt cho Qwen format JSON từ analysis của DeepSeek. Có đầy đủ schema của 15 action types và 13 critical examples.

---

### 4. ai/action_fixer.py — Post-Processing Engine

Xử lý **deterministic** (không phụ thuộc AI) để sửa và chuẩn hóa output. Pipeline gồm 8 bước:

| Bước | Chức năng |
|------|-----------|
| **1** | Fix invalid action names (`export_csv` → `download`, `click_logo` → `process_deployment`, `uncheck` → `checkbox`...) |
| **2** | Fix field names theo action type (checkbox defaults, download/upload filename, deployment checkbox detection) |
| **3** | Resolve shorthand navigation paths (`["Faction Feud Event"]` → `["Live Events","Faction Feud","Faction Feud Event"]`) |
| **3b** | Merge consecutive navigate steps thành một path array duy nhất |
| **4** | Merge checkbox + process_deployment steps (backward + forward scan) |
| **5** | Auto-infer deployment options từ navigation context nếu để trống |
| **6** | Auto-inject missing `clone_row` nếu AI bỏ qua (detect từ user command) |
| **7** | Auto-inject `save_form(mode=clone)` sau clone flow, tách modal fields vs post-clone fields |
| **8** | Merge consecutive `update_form → save_form(save)` để tránh validation error trên multi-phase forms |

#### Hai constants quan trọng

**`DEPLOYMENT_KEYWORDS`** — 60+ tên checkbox trên Home screen (Offers, Gacha Events, Faction Feud, Missions, Perks, v.v.)

**`NAVIGATION_PATH_MAP`** — Map từ tên destination ngắn → full menu path. Ví dụ:

```python
"faction feud event": ["Live Events", "Faction Feud", "Faction Feud Event"],
"gacha event":        ["Live Events", "Gacha Event", "Gacha Event"],
"perk":               ["Data Configs", "Perk", "Perk"],
"tournament":         ["Live Events", "Versus", "Tournament"],
```

#### Uncheck Detection

Phát hiện intent "bỏ chọn" từ user command bằng regex patterns (tiếng Việt + English):
`bỏ chọn`, `bo chon`, `uncheck`, `untick`, `deselect`, `bỏ tick`

Các option bị uncheck được prefix `-` trong `options` list của `process_deployment`.

---

### 5. automation/core.py — Execution Engine

Dispatcher chính, nhận JSON Action Plan và thực thi từng bước qua Playwright.

#### Kết nối Browser

```python
browser = p.chromium.connect_over_cdp("http://localhost:9222")
```

Kết nối vào Chrome/Brave đang mở với remote debugging port 9222.

#### 16 Action Types được xử lý

| Action | Mô tả |
|--------|-------|
| `navigate` | Điều hướng menu theo path array |
| `checkbox` | Chọn dòng trong bảng (random / all / specific) |
| `click` | Click button, sidebar item, panel item |
| `wait` | Chờ spinner/loading hoàn tất |
| `edit_row` | Click icon Edit trên một dòng cụ thể |
| `clone_row` | Click icon Clone trên một dòng cụ thể |
| `update_form` | Điền form fields (input, select, radio, datetime...) |
| `save_form` | Bấm Save / Save & Continue / Clone button |
| `download` | Export CSV (với file chooser) |
| `upload` | Import CSV |
| `manipulate_csv` | Sửa nội dung file CSV offline (add/edit/set/delete) |
| `smart_test_cycle` | Chạy fuzz test cycle tự động |
| `scan_tabs` | Quét tất cả tab sidebar để update |
| `check_fields` | Kiểm tra field có giá trị không (PASS nếu trống) |
| `reorder` | Kéo thả đổi thứ tự items trong list |
| `process_deployment` | Navigate về Home, tick checkbox, bấm Process |

#### Safety Net

Trước khi execute, core áp dụng thêm một lớp `SAFETY_MAP` để fix action names còn sót. Sau khi execute xong toàn bộ plan, tự động reload trang (trừ khi có `process_deployment`).

#### Windows Compatibility

Trên Windows, tạm chuyển sang `WindowsProactorEventLoopPolicy` trước khi khởi động Playwright (vì Streamlit/Tornado dùng SelectorEventLoop không hỗ trợ subprocess).

---

### 6. automation/navigator.py — Navigation Engine

#### `_smart_navigate_path(page, path_list)`

Duyệt từng item trong path, click menu theo thứ tự. Xử lý các edge cases:

- **Exact match** ưu tiên hơn partial match
- **Same-name submenu** (VD: `Perk → Perk`): force click để toggle, đợi 2s cho submenu xuất hiện
- **Singular/Plural fallback**: `"Superstars"` tự thử `"Superstar"` nếu không tìm thấy

#### `smart_click(page, target_text)`

Tìm element theo thứ tự ưu tiên:
1. Sidebar selectors (`.sidebar`, `#sidebar`, `.nav-pills`...)
2. Tab selectors (`[data-toggle='tab']`, `[role='tab']`)
3. Content panel items (`.list-group-item`, `button[class*='store-sidebar']`...)
4. Already active elements
5. Generic exact text match (button, a, div[role='button'])
6. Contains match
7. Playwright `text=` selector
8. Broad div/li/span partial match

#### `_handle_locked_item_popup(page)`

Tự động xử lý popup "Item Locked by another user":
- Strategy 1: Tìm `.btn-acquire-lock` class
- Strategy 2: Tìm modal chứa text "locked/acquire lock"
- Strategy 3: Global scan cho Acquire Lock button

#### `process_deployment(page, options)`

1. Kiểm tra đã ở Home page chưa (tìm text "Process Blueprints")
2. Nếu chưa: click logo The Brick, đợi 7s
3. Tick/untick từng checkbox (hỗ trợ prefix `-` cho uncheck, xử lý "Toggle All")
4. Click nút Process

#### `_wait_for_long_loading(page)`

Polling spinner với 2 giai đoạn:
- **Phục kích**: Poll 8 lần × 0.5s để bắt spinner khi render
- **Chờ biến mất**: `wait_for(state="hidden", timeout=30000)` sau khi phát hiện

Spinner selectors: `body[style*='cursor: progress']`, `i.fa.fa-cog.fa-spin`, `.spinner-border`, `.blockUI`, v.v.

---

### 7. automation/form_handler.py — Form Handler

File lớn nhất (~1600 dòng), xử lý mọi loại form interaction.

#### `_smart_update_form(page, data)`

Main dispatcher, duyệt từng field theo thứ tự ưu tiên:

```
1. Radio button by label text (value = "select"/"true"/"on"...)
2. Radio by value (label suffix "radio", VD: "Energy restart mode radio": "Daily")
3. Datetime / Schedule fields (flatpickr, comma-separated values)
4. Early inline edit detection (fields với nút Edit riêng)
5. Tìm element bình thường → fill smartly
```

Sau mỗi field: trigger `change` + `input` events để reveal conditional fields (VD: đổi "Leaderboard Type" → hiện "Bracket Preset").

#### `_find_input_element(page, label_text)`

Tìm input theo label với nhiều chiến lược (theo thứ tự ưu tiên):

1. **Direct ID/name match** (skip nếu label có CSS special chars)
2. **Section-aware search** (PreEvent Phase, Active Phase, Post Event...)
3. **New Event ID special case** (tìm input với placeholder "suffix")
4. **Premier strategy**: label → form-group container → input bên trong (validate name/id match)
5. **Label `for` attribute** → target element (với validation và better-match fallback)
6. **Nested input** trong label
7. **Sibling input** (following sibling)
8. **Fuzzy matching** (normalize spaces/underscores)
9. **Dropdown wrapper fallback** (Chosen.js, Select2, Vue Multiselect)

#### `_fill_element_smartly(page, element, value)`

Auto-detect loại element và fill phù hợp:

| Element Type | Xử lý |
|-------------|-------|
| Checkbox/Radio | `click(force=True)`, trigger blur |
| Flatpickr/Datepicker | JS API `_flatpickr.setDate()` → fallback JS force set |
| Hidden SELECT (Chosen/Select2/Multiselect) | Tìm wrapper → `_handle_js_dropdown()` |
| Visible SELECT | `select_option(label=)` → `select_option(value=)` → fuzzy match → wrapper |
| Input text | `fill("")` → `fill(value)` → press Tab |

#### `_handle_js_dropdown(page, container, value, lib_type)`

Mở dropdown và tìm option:
1. Click trigger để mở
2. Poll 3s đợi options load (JS evaluate, không dùng `.all()` vì chậm với 2500+ options)
3. **Strategy A**: JS evaluate tìm và click option trực tiếp (exact match trước, partial match sau)
4. **Strategy B**: Dùng search box nếu có (type search term, đợi filter, click result)

#### `_save_form(page, mode)`

Modes: `"save"` | `"continue"` | `"clone"`

- **JS-level network interception**: Monkey-patch `XMLHttpRequest` + `fetch` để bắt HTTP 4xx/5xx errors trực tiếp
- **SweetAlert2 detection**: Distinguish error / warning (overlapping...) / success
- **Bootstrap toast/alert detection**: Đọc `.toast-message` riêng (tránh lẫn "×" close button)
- **Auto-fix datetime**: Nếu có lỗi `"time data ... does not match format"`, tự fix và retry save

#### `_fill_schedule_datetime_smart(page, label_text, values)`

Xử lý datetime cho schedule fields:

- **Section-aware**: Tách prefix (VD: "Active Phase Schedules In UTC" → tìm trong section "Active Phase")
- **Format detection**: Đọc format từ ô hiện tại (`TIME_DASH_DATE`, `DATE_COMMA_TIME_AMPM`...) và reformat value
- **12-hour fix**: Auto-convert `00:00 AM` → `12:00 AM`
- **Multiple values**: Comma-separated → fill từng input theo thứ tự
- **Single value**: Tìm ô trống đầu tiên để fill

#### `check_fields_in_tabs(page, tabs_dict)`

Duyệt qua dict `{"Tab Name": ["Field1", "Field2"]}`:
- Click tab trong sidebar
- Đọc giá trị từng field
- **Logic**: field CÓ giá trị → FAIL (unexpected), field TRỐNG → PASS (expected)

---

### 8. automation/table_handler.py — Table Handler

#### `handle_checkbox(page, target_col, value)`

Chọn dòng trong bảng theo 3 modes:

**Random** (`random_N`):
- Chọn N dòng ngẫu nhiên, lưu ID vào `self.memory["SELECTED_IDS"]`
- Retry tối đa `N * 3` lần

**All**:
- Click header checkbox, fallback tick từng dòng (tối đa 20)

**Specific text**:
- Tìm dòng khớp regex
- Nếu không thấy → auto filter → tìm lại

#### `_click_icon_in_row(page, target_text, action_type)`

Click icon Edit/Clone trong một dòng cụ thể:

- Nhận `target_text` là ID hoặc `"RANDOM"` (chọn ngẫu nhiên)
- Dùng **JS evaluate** để tìm row theo text và click icon nhanh (tránh Playwright round-trips)
- Sau `edit_row`: gọi `_handle_locked_item_popup()` với timeout 1s

#### `drag_to_reorder(page, target, position, before, after)`

Kéo thả đổi thứ tự items:

1. **Detect drag handles**: Duyệt qua `DRAG_HANDLE_SELECTORS` (`fa-bars`, `fa-grip`, `[class*='drag']`...)
2. **Column scoping**: Cluster handles theo tọa độ X (± 150px) để tránh kéo nhầm sang panel khác
3. **Collect items**: Thu thập text + bbox của mỗi handle
4. **Find source**: Match target text với items
5. **Calculate dest**: Từ `position` (1-based), `before`, hoặc `after`
6. **Smooth drag**: 20 steps với `mouse.move()`, kết hợp `mouse.down()` và `mouse.up()`

---

### 9. automation/smart_tester.py — Smart Test Cycle

Chạy fuzz testing tự động cho CSV files.

#### Flow chính: `_test_generic_csv(page, target_csv)`

**Phase 1 — Fuzzing (Negative Testing)**:

`GenericCSVFuzzer` phân tích cấu trúc CSV và sinh test cases:

| Case Type | Mô tả |
|-----------|-------|
| Empty fields | Xóa giá trị cột đầu tiên (thường là ID) |
| Negative numbers | Điền -100 vào cột numeric |
| Type mismatch | Điền text vào cột số |
| Overflow | Điền số cực lớn (99) |
| SQL Injection | `' OR '1'='1` |
| Special chars | `⚠️💀 Test @#%^` |
| Duplicate rows | Nhân đôi dòng đầu tiên |

Upload từng case → **upload FAIL = PASS** (system đã block invalid data)

**Phase 2 — Valid Import (Sanity Check)**:
- Generate ID mới cho primary key (timestamp-based để unique)
- Fix `tab_id` column (chỉ cho phép: `feature`, `prize_wall`, `basic_loot`)
- Upload → expect SUCCESS
- **Auto-fix duplicate**: Nếu lỗi 1062 (duplicate entry), tự thêm `_test_{timestamp}` suffix và retry (tối đa 2 lần)

#### RBE Specialized Testing

File RBE có format multi-section:
```csv
[RBE_CONFIGURATION]
EventID,StartTime,EndTime,...

[TASKS_EventID]
...

[MILESTONES_EventID]
...
```

`RBESmartTester` parse và validate:
- Structure check (đủ 3 sections)
- EventID sync giữa sections
- Milestone points sorted correctly

`RBEFuzzGenerator` sinh mutations cho RBE: invalid date range, missing columns, negative points, invalid reward syntax, empty event name.

#### JS Popup Capture

Inject vào browser **trước** khi upload để bắt result nhanh:

```javascript
// Poll 10ms intervals + MutationObserver
window.__popupResult = null;
// Capture từ .modal, .swal2-container...
// Phân loại PASS/FAIL theo keywords
```

---

### 10. config/ — Cấu hình

#### `config/auth.json`

Chứa Google cookies và session cookies cho The Brick staging environment. Được tạo bởi `scripts/setup_login.py` — mở browser, user đăng nhập thủ công, script lưu `storage_state`.

#### `config/scenarios.json`

Lưu các kịch bản test với format:

```json
{
  "Tên kịch bản": {
    "command": "Lệnh gốc của user",
    "plan": [ { "action": "...", ... } ]
  }
}
```

Có thể load lại qua UI Streamlit để chạy lại mà không cần nhập lệnh.

---

## Technology Stack

| Thành phần | Công nghệ |
|-----------|-----------|
| UI | Streamlit |
| AI Models | Qwen2.5-Coder:14b, DeepSeek-R1:8b (Ollama local) |
| Browser Automation | Playwright (Python), kết nối qua CDP |
| Target Browser | Chrome/Brave với `--remote-debugging-port=9222` |
| Data Processing | Pandas, CSV |
| Config | python-dotenv |
| Packaging | pip + requirements.txt |

### Cài đặt môi trường

```bash
# Cài dependencies Python
pip install -r requirements.txt

# Cài Playwright browsers
playwright install chromium

# Kéo models về Ollama
ollama pull qwen2.5-coder:14b
ollama pull deepseek-r1:8b

# Lần đầu: đăng nhập để lấy cookie
python scripts/setup_login.py

# Khởi động Chrome debug (Mac)
bash scripts/start_chrome.sh

# Chạy app
streamlit run app.py
```

---

## Điểm đặc biệt của thiết kế

### Hybrid AI Pipeline

Fast Mode cho ~90% lệnh đơn giản, tự động escalate sang Careful Mode khi phát hiện phức tạp. Auto-fallback hai chiều:

```
Fast Mode thất bại  →  thử Careful Mode
Careful Mode thất bại  →  fallback Fast Mode
```

### Deterministic Post-Processing

`action_fixer.py` không phụ thuộc AI — đảm bảo output hợp lệ dù AI tạo ra action names sai. Đây là safety net quan trọng, đặc biệt hữu ích khi model không follow instructions chính xác.

### Short-term Memory System

`self.memory` dict lưu ngắn hạn giữa các steps trong cùng một execution:

```python
self.memory["LAST_SELECTED"]  # ID dòng vừa chọn/edit
self.memory["SELECTED_IDS"]   # Danh sách IDs đã chọn
self.memory["LAST_FUZZED_FILE"]  # Filename dùng trong smart test
```

### Network Interception cho Save Validation

Inject JS monkey-patch `XMLHttpRequest` và `fetch` trước khi click Save, đọc HTTP response codes sau khi click. Chính xác hơn chỉ xem UI popup vì bắt được error response body trực tiếp từ API.

### Prompt Prefix KV Caching

Dùng `keep_alive: "10m"` để giữ model warm trong VRAM. Lần gọi đầu: prompt eval ~84s (full 7715 tokens). Lần gọi sau: prompt eval ~1–5s (chỉ eval phần user command mới thêm vào).

### Column Scoping trong Drag & Drop

Khi reorder, cluster drag handles theo tọa độ X ± 150px để tránh kéo nhầm item sang panel/column khác trên cùng trang.

---

## Luồng dữ liệu end-to-end (ví dụ)

```
User nhập: "Vào Faction Feud Event -> Clone một ID bất kỳ -> New FF ID: FF_Test, Gate: r80 -> Save"

1. brain.py detect: SIMPLE (3 bước, 70 chars) → Fast Mode
2. prompts.py: Tạo few-shot prompt với user command
3. Qwen2.5-Coder: Output JSON
   [navigate, clone_row(RANDOM), update_form({New FF ID, Gate}), save_form(clone)]
4. action_fixer.py:
   - Resolve "Faction Feud Event" → ["Live Events","Faction Feud","Faction Feud Event"]
   - Validate clone flow (inject save_form nếu thiếu)
5. core.py execute từng step:
   - navigator._smart_navigate_path(["Live Events","Faction Feud","Faction Feud Event"])
   - table_handler._click_icon_in_row(RANDOM, "clone")
   - form_handler._smart_update_form({New FF ID: FF_Test, Gate: r80})
   - form_handler._save_form(mode="clone")
6. Kết quả hiển thị trong Streamlit table
```

---

*Tài liệu được tạo tự động từ source code analysis. Cập nhật lần cuối: 2025.*

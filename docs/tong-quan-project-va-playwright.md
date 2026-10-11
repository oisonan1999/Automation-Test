# AutoGameOps — Tài liệu tổng quan Project & Cơ chế Playwright

> Tài liệu này giải thích project **AutoGameOps** theo cách dễ hiểu nhất có thể — dành cho
> người mới join project, chưa từng đọc code. Phần 2 đi sâu vào **Playwright** (thư viện điều
> khiển trình duyệt), liệt kê toàn bộ hàm/biến then chốt được dùng và mục đích của từng cái.
>
> Khảo sát trực tiếp từ code thật (không chỉ dựa vào comment) ngày 2026-09-16.

---

## MỤC LỤC

1. [Project này là gì?](#1-project-này-là-gì)
2. [Project được viết bằng ngôn ngữ / công nghệ gì?](#2-project-được-viết-bằng-ngôn-ngữ--công-nghệ-gì)
3. [Các thành phần chính trong project](#3-các-thành-phần-chính-trong-project)
4. [Luồng hoạt động end-to-end](#4-luồng-hoạt-động-end-to-end)
5. [Playwright là gì và tại sao project dùng nó](#5-playwright-là-gì-và-tại-sao-project-dùng-nó)
6. [Cách Playwright kết nối vào trình duyệt (CDP attach)](#6-cách-playwright-kết-nối-vào-trình-duyệt-cdp-attach)
7. [Vòng đời một "action" — từ JSON đến hành động thật trên trình duyệt](#7-vòng-đời-một-action--từ-json-đến-hành-động-thật-trên-trình-duyệt)
8. [5 nhóm việc (mixin) mà Playwright thực hiện](#8-5-nhóm-việc-mixin-mà-playwright-thực-hiện)
9. [Danh sách TOÀN BỘ hàm Playwright (API) được dùng trong project](#9-danh-sách-toàn-bộ-hàm-playwright-api-được-dùng-trong-project)
10. [Danh sách các biến/quy ước đặt tên hay gặp](#10-danh-sách-các-biếnquy-ước-đặt-tên-hay-gặp)
11. [Cơ chế xử lý popup/modal đặc biệt](#11-cơ-chế-xử-lý-popupmodal-đặc-biệt)
12. [Cơ chế Upload / Download file](#12-cơ-chế-upload--download-file)
13. [Những "cạm bẫy" (gotcha) quan trọng khi dùng Playwright trong project này](#13-những-cạm-bẫy-gotcha-quan-trọng-khi-dùng-playwright-trong-project-này)

---

## 1. Project này là gì?

**AutoGameOps** là một **công cụ test tự động (QA automation)** nội bộ, dùng để test trang
quản trị game ops có tên **"The Brick"** (một web app quản lý các tính năng trong game: RBE,
Offer, PVE, Gacha, Currency, Fight Card, Localization, Showdown, v.v.).

Ý tưởng cốt lõi:

> Người dùng gõ một câu lệnh test bằng **tiếng Việt hoặc tiếng Anh** (ví dụ: *"Vào RBE, clone
> 1 dòng bất kỳ, đổi Gate thành 5, rồi Save"*) → AI đọc câu đó và **tự soạn ra một "kế hoạch
> hành động" dạng JSON** → một bot Playwright **thực thi từng bước JSON đó thật** trên trình
> duyệt Chrome đang mở sẵn → kết quả PASS/FAIL được ghi log và hiển thị lại cho người dùng.

Nói cách khác, đây là một hệ thống 3 tầng:

```
Câu lệnh con người (VI/EN)
        │
        ▼
   [ TẦNG AI ]        ai/brain.py, ai/prompts.py, ai/action_fixer/
   Câu lệnh → JSON action plan (đã được validate/sửa lỗi tự động)
        │
        ▼
   [ TẦNG THỰC THI ]  automation/core.py + các package con
   JSON action plan → Playwright điều khiển Chrome thật → PASS/FAIL
        │
        ▼
   [ TẦNG GIAO DIỆN ]  app.py (Streamlit)
   Hiển thị kết quả, log, cho phép chạy lại/chạy hàng loạt CSV test case
```

## 2. Project được viết bằng ngôn ngữ / công nghệ gì?

Toàn bộ project viết bằng **Python 3**. Các thư viện/công nghệ chính:

| Công nghệ | Dùng để làm gì | File liên quan |
|---|---|---|
| **Streamlit** | Vẽ giao diện web nội bộ (nút bấm, ô nhập lệnh, bảng log, upload CSV...) | `app.py` |
| **Ollama** (chạy LLM local, ví dụ Qwen3) | "Bộ não" chính dịch câu lệnh người dùng → JSON action plan | `ai/brain.py` (gọi HTTP tới `http://localhost:11434/api/generate`) |
| **Anthropic Claude** (qua `claude-agent-sdk`) | Dùng cho **self-heal**: khi 1 test case fail, một agent Claude tự đọc log lỗi, tự sửa code, tự test lại | `ai/self_heal.py` |
| **Playwright** (`playwright.sync_api`) | Điều khiển trình duyệt Chrome thật để thực hiện click/gõ/chọn dropdown... giống người dùng thật | `automation/core.py` và toàn bộ `automation/*` |
| **pandas** | Đọc/sửa file CSV test case, sinh dữ liệu fuzz (dữ liệu lỗi cố ý để test validate) | `automation/data_handler.py`, `automation/smart_tester/` |
| **JSON** | Định dạng "action plan" — cầu nối giữa AI và Playwright | mọi nơi |

Về **trình duyệt**: project **không** để Playwright tự mở một Chrome mới, mà **gắn (attach)
vào một Chrome đang chạy sẵn** trên máy, qua cổng debug `9222` (Chrome DevTools Protocol —
CDP). Điều này rất quan trọng, xem chi tiết ở [mục 6](#6-cách-playwright-kết-nối-vào-trình-duyệt-cdp-attach).

## 3. Các thành phần chính trong project

```
app.py                     Giao diện Streamlit — nơi người dùng nhập lệnh, xem log, chạy CSV smoke test
ai/
  brain.py                 "Bộ não": gửi câu lệnh cho Ollama/Claude, nhận JSON, dọn dẹp JSON lỗi
  prompts.py               Toàn bộ system prompt / hướng dẫn cho AI (rất dài — chứa ví dụ mẫu cho từng action)
  action_fixer/            Bộ "sửa lỗi" JSON: AI đôi khi sinh sai định dạng — package này tự vá lại
  plan_cache.py            "Golden Plan Cache" — nhớ lại plan đã PASS để khỏi phải hỏi AI lại lần sau
  self_heal.py             Agent Claude tự sửa code khi 1 test case fail (đứng ngoài luồng Playwright)
  ai_locator_fallback.py   AI hỗ trợ tìm element khi cách tìm thông thường thất bại

automation/
  core.py                  "Trái tim": kết nối Chrome, nhận JSON action plan, điều phối (dispatch) từng bước
  constants.py             Hằng số chung (đường dẫn thư mục downloads/)
  data_handler.py          Đọc/sửa file CSV (không dùng Playwright — thao tác file thuần)
  navigator/                Điều hướng menu, click thông minh, mở khu vực PVE, "Process Deployment"
  form_handler/             Điền form: tìm field, điền giá trị, xử lý dropdown, ngày giờ, bấm Save
  table_handler/            Làm việc với bảng dữ liệu: tick checkbox, filter, click icon Edit/Clone, kéo-thả sắp xếp
  smart_tester/             Test CSV: upload file, tạo dữ liệu "fuzz" (dữ liệu sai) để kiểm tra validate, đọc popup kết quả

downloads/                 Nơi lưu file CSV test case + file export ra từ web
config/                    golden_plans.json (cache plan đã PASS), smoke_last_ids.json (nhớ ID vừa tạo)
docs/                      Tài liệu — bao gồm chính file bạn đang đọc
```

**Vì sao code lại chia nhỏ thành "package" (thư mục) như trên?** Trước đây mỗi file này là
MỘT file khổng lồ (`form_handler.py` từng dài ~8000 dòng!). Ngày 2026-06 project đã **tách**
mỗi file lớn thành nhiều file nhỏ theo chức năng, nhưng vẫn giữ nguyên tên class/hàm cũ (kỹ
thuật gọi là **Mixin** trong Python — nhiều class nhỏ được "trộn" lại thành 1 class lớn duy
nhất là `BrickAutomation`). Nhờ vậy code cũ gọi hàm `self.smart_click(...)` vẫn chạy đúng, dù
`smart_click` giờ nằm trong file khác.

## 4. Luồng hoạt động end-to-end

Đây là một vòng chạy đầy đủ, từ lúc người dùng gõ lệnh tới lúc thấy kết quả:

1. **Người dùng mở app** (`streamlit run app.py`), nhập câu lệnh test (VI hoặc EN), hoặc chọn
   chạy hàng loạt từ file `downloads/Testcasesmokelive.csv`.
2. **`ai/brain.py` — `parse_command_to_json()`** nhận câu lệnh:
   - Tiền xử lý: nếu câu lệnh có dạng *"hãy tự generate một ID duy nhất bắt đầu bằng X"* →
     tự sinh ID thật (ví dụ `X_09161530a1b2`) để AI không phải tự nghĩ ID (hàm
     `_inject_generated_ids`).
   - Gửi câu lệnh (kèm prompt hướng dẫn từ `ai/prompts.py`) cho **Ollama** (mode nhanh) hoặc
     **DeepSeek/Claude careful pipeline** (mode kỹ, khi câu lệnh phức tạp) → nhận về JSON.
   - Dọn JSON bị lỗi format (LLM hay trả JSON thiếu dấu `}`, có comment thừa...) bằng
     `clean_json_string()`.
3. **`ai/action_fixer/` — `fix_action_plan()`** kiểm tra JSON vừa nhận, tự vá các lỗi biết
   trước (thiếu bước `navigate` đầu, thiếu `save_form` sau clone, sai tên field, v.v.) — đây là
   "lưới an toàn" cho những lỗi lặp lại nhiều lần của AI.
4. **`automation/core.py` — `BrickAutomation.execute_action(action_plan)`** nhận JSON đã
   được vá, chạy `_execute_with_playwright()`:
   - Mở `sync_playwright()`, **gắn vào Chrome đang chạy sẵn** ở cổng `9222`.
   - Lặp qua từng bước (`step`) trong JSON, gọi đúng hàm Playwright tương ứng (chi tiết ở
     [mục 7](#7-vòng-đời-một-action--từ-json-đến-hành-động-thật-trên-trình-duyệt)).
   - Mỗi bước ghi lại kết quả PASS/FAIL/UNKNOWN vào `report_logs`.
5. **Kết quả trả về `app.py`**, hiển thị log từng bước, tổng kết PASS/FAIL cho test case.
6. Nếu chạy theo **CSV hàng loạt (smoke test)**:
   - Nếu case PASS **sạch** (không lỗi), `ai/plan_cache.py` **lưu lại JSON plan đó** (đã thay
     ID cụ thể bằng placeholder `{{UNIQUE_ID}}`/`{{LAST_ID}}`) vào `config/golden_plans.json`
     — lần sau chạy lại case này, hệ thống **dùng lại plan cũ, không cần hỏi AI nữa** → nhanh
     hơn và ổn định hơn (LLM không phải lúc nào cũng sinh JSON giống nhau).
   - Nếu case FAIL và người dùng chạy **đơn lẻ** (không phải full CSV), `ai/self_heal.py` có
     thể được gọi: một agent Claude đọc log lỗi, tự sửa code trong `ai/` hoặc `automation/`,
     rồi tự chạy lại case đó để kiểm chứng — tự "vá" lỗi mà không cần con người.

## 5. Playwright là gì và tại sao project dùng nó

**Playwright** là một thư viện (do Microsoft phát triển) cho phép **điều khiển trình duyệt
bằng code** — giống như có một "người dùng ảo" tự mở trang, click nút, gõ chữ, chọn dropdown,
tick checkbox... Nó thường dùng để viết test tự động cho web app.

Project dùng **`playwright.sync_api`** (bản **đồng bộ/sync**, không phải async) — nghĩa là
code viết tuần tự bình thường (`page.click(...)`, xong dòng này mới chạy dòng kế), không cần
`async`/`await`. Đây là lựa chọn hợp lý vì Streamlit (giao diện) cũng chạy theo kiểu đồng bộ
từng script mỗi lần người dùng bấm nút.

> **Ghi chú kỹ thuật (Windows):** Vì Streamlit dùng loại event loop không hỗ trợ subprocess
> trên Windows, `execute_action()` trong `automation/core.py` tạm đổi
> `asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())` trước khi chạy
> Playwright, rồi đổi lại policy cũ ngay sau đó (`finally`) — nếu không làm vậy, Playwright sẽ
> báo lỗi không tạo được subprocess trên Windows.

## 6. Cách Playwright kết nối vào trình duyệt (CDP attach)

Đây là điểm đặc biệt nhất của project: Playwright **không tự mở trình duyệt mới**, mà **gắn
vào một Chrome đang mở sẵn** trên máy người dùng (Chrome đó phải được chạy với cờ debug port
9222). Lý do: người dùng đã đăng nhập sẵn tài khoản The Brick trên Chrome đó, tránh phải login
lại mỗi lần test.

Hàm chịu trách nhiệm: **`BrickAutomation.get_existing_page(self, p)`** trong `automation/core.py`:

```python
def get_existing_page(self, p):
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]
    if len(context.pages) > 0:
        page = context.pages[0]
    else:
        page = context.new_page()
    return browser, page
```

Giải thích từng biến:

| Biến | Là gì | Ý nghĩa |
|---|---|---|
| `p` | Đối tượng Playwright (`with sync_playwright() as p:`) | Điểm khởi đầu mọi thao tác Playwright |
| `browser` | `p.chromium.connect_over_cdp(...)` | Đại diện cho **cả trình duyệt Chrome** đang chạy, gắn qua CDP port 9222 |
| `context` | `browser.contexts[0]` | Một "hồ sơ trình duyệt" (browser context) — chứa cookie, session, các tab đang mở |
| `page` | `context.pages[0]` (hoặc `context.new_page()` nếu chưa có tab nào) | **Một tab cụ thể** — đây là biến quan trọng nhất, hầu hết mọi hàm Playwright trong project đều nhận `page` làm tham số đầu tiên |

Nếu không kết nối được (Chrome chưa mở port debug), hàm raise lỗi tiếng Việt nhắc người dùng:
*"Không thể kết nối Chrome! Hãy chạy lệnh debug port 9222."*

Toàn bộ vòng đời Playwright nằm trong:

```python
with sync_playwright() as p:
    browser, page = self.get_existing_page(p)
    ... # chạy toàn bộ các bước action_plan tại đây, dùng chung 1 page
```

→ Một biến `page` **duy nhất** được truyền xuyên suốt qua tất cả các hàm xử lý (navigate,
click, fill form, save...) trong toàn bộ vòng chạy 1 action plan.

## 7. Vòng đời một "action" — từ JSON đến hành động thật trên trình duyệt

JSON action plan là một **danh sách các "step"** (bước), mỗi step có dạng:

```json
{ "action": "click", "target": "Save", "value": "", "data": {} }
```

`automation/core.py` định nghĩa tập hành động hợp lệ, gọi là **`VALID_ACTIONS`**:

```
navigate, checkbox, download, upload, manipulate_csv, smart_test_cycle,
clone_row, edit_row, update_form, save_form, scan_tabs, check_fields,
click, select, wait, wait_for_page_load, process_deployment, reorder,
delete_all_tasks, pve_book_fuzz_test
```

Nếu AI lỡ sinh ra tên action sai/khác (ví dụ `"export_csv"` thay vì `"download"`), có một
**`SAFETY_MAP`** tự động đổi lại về đúng tên hợp lệ trước khi thực thi — một lớp bảo vệ nữa
phòng khi `action_fixer` bên tầng AI bỏ sót lỗi.

Bảng dưới đây liệt kê **mỗi loại action → hàm Playwright thật xử lý nó**:

| `action` trong JSON | Hàm xử lý (đều nhận `page`) | Playwright làm gì bên trong |
|---|---|---|
| `navigate` | `smart_navigate(page, target)` → `_smart_navigate_path` | Click vào menu sidebar theo từng cấp, hoặc `page.goto(url)` nếu target là URL |
| `click` / `select` | `smart_click(page, target_text)` | Thử nhiều "chiến lược" tìm & click 1 phần tử (nút, tab, link...) |
| `checkbox` | `_smart_update_form(...)` (nếu là toggle on/off) **hoặc** `handle_checkbox(page, target_col, value)` (nếu là chọn dòng trong bảng) | Tick checkbox trong form, hoặc tick checkbox đầu dòng trong bảng dữ liệu (hỗ trợ chọn ngẫu nhiên `random_N`) |
| `update_form` | `_smart_update_form(page, data)` | Điền toàn bộ các field trong `data` (text, dropdown, ngày giờ, toggle...) |
| `save_form` | `_save_form(page, mode)` | Tìm nút Save/Create/Clone phù hợp và bấm, bắt lỗi validate trả về từ server |
| `clone_row` / `edit_row` | `_click_icon_in_row(page, target_text, "clone"/"edit")` | Tìm đúng dòng trong bảng (theo tên/ID, hoặc random), bấm icon Edit/Clone |
| `download` | Xử lý trực tiếp trong `core.py` bằng `page.expect_download(...)` | Bấm nút Export, chờ file download xong, lưu vào `downloads/` với tên đúng |
| `upload` | `handle_upload(page, target_btn_name, file_name)` | Bấm nút Import, mở "file chooser" của OS, chọn file CSV |
| `manipulate_csv` | `_process_csv_manipulation(...)` (KHÔNG dùng Playwright — chỉ đọc/sửa file CSV bằng pandas) | Sửa 1 cột trong file CSV local trước khi upload |
| `smart_test_cycle` | `smart_test_cycle(page, file_name)` | Test 2 vòng: upload dữ liệu SAI (fuzz) để chắc web validate đúng → rồi upload dữ liệu ĐÚNG |
| `scan_tabs` / `check_fields` | `scan_all_tabs`, `check_fields_in_tabs` | Duyệt qua từng tab trong form, đọc giá trị hiện tại của field để so sánh |
| `wait` / `wait_for_page_load` | `_wait_for_long_loading(page)` | Chờ cho tới khi spinner loading trên trang biến mất |
| `process_deployment` | `process_deployment(page, options)` | Bấm logo "The Brick" + tick các checkbox deploy + bấm nút Process |
| `reorder` | `drag_to_reorder(page, target, position, before, after)` | Kéo-thả 1 dòng trong bảng tới vị trí khác |

Trước mỗi bước `click`/`select`/`update_form`/`save_form`/`navigate`/`process_deployment`,
`core.py` luôn tự động gọi 2 hàm "dọn đường":

```python
self._ensure_swal2_clone_confirmation_yes(page)   # tự bấm Yes nếu có popup xác nhận SweetAlert2
self._ensure_rbe_are_you_sure_closed(page)         # tự đóng popup Bootstrap "Are you sure?"
```

→ Đảm bảo không có popup che khuất làm bước tiếp theo bị "trượt" (click hụt).

## 8. 5 nhóm việc (mixin) mà Playwright thực hiện

`BrickAutomation` (trong `automation/core.py`) là 1 class "gộp" (kế thừa) 5 nhóm hàm nhỏ hơn,
mỗi nhóm phụ trách 1 mảng việc Playwright riêng:

| Package | Vai trò dùng Playwright |
|---|---|
| `automation/navigator/` | **Điều hướng**: click sidebar menu, mở accordion PVE, click theo path nhiều cấp, bấm logo deploy |
| `automation/form_handler/` | **Điền form**: tìm input theo tên field (label), điền text/số, mở & chọn dropdown (select2/chosen/vue-multiselect), điền ngày-giờ (flatpickr), bật/tắt toggle, chọn radio, bấm Save và đọc lỗi validate |
| `automation/table_handler/` | **Làm việc với bảng**: tick checkbox theo cột/giá trị (hoặc random N dòng), filter bảng theo từ khoá, click icon Edit/Clone trên 1 dòng cụ thể, kéo-thả sắp xếp lại thứ tự dòng |
| `automation/data_handler/` | **File CSV** (KHÔNG dùng Playwright) — đọc/sửa cột trong CSV bằng pandas, tìm nút "Export" tương ứng |
| `automation/smart_tester/` | **Test CSV**: upload file (native OS file chooser hoặc modal riêng), sinh dữ liệu "fuzz" (sai cố ý) để test validate, đọc popup/growl kết quả (thành công/lỗi/cảnh báo) sau khi upload |

## 9. Danh sách TOÀN BỘ hàm Playwright (API) được dùng trong project

Đây là kết quả quét thực tế (grep) toàn bộ `automation/*.py` và `ai/*.py` — liệt kê **mọi hàm
Playwright (`page.` / `locator.`) đang được gọi**, sắp theo số lần dùng nhiều → ít, kèm mục
đích cụ thể trong project:

| Hàm Playwright | Số lần dùng | Mục đích trong project |
|---|---|---|
| `.locator(selector)` | 568 | **Hàm được dùng nhiều nhất tuyệt đối** — tìm 1 (hoặc nhiều) phần tử trên trang bằng CSS selector, text, hoặc XPath. Gần như mọi hàm trong `form_handler/`, `table_handler/`, `navigator/` đều bắt đầu bằng 1 `page.locator(...)` |
| `.count()` | 367 | Kiểm tra locator tìm được **bao nhiêu phần tử** (0 = không tìm thấy) — luôn được gọi TRƯỚC khi thao tác, để tránh lỗi "element not found" |
| `.is_visible()` | 309 | Kiểm tra phần tử có **đang hiển thị** trên màn hình không (phần tử có thể tồn tại trong DOM nhưng bị ẩn/che) — dùng để chọn đúng phần tử "thật" giữa nhiều phần tử trùng tên |
| `.click(force=True/False)` | 224 | Click chuột vào phần tử — nút bấm, tab, icon, checkbox, option dropdown... `force=True` dùng khi phần tử bị 1 lớp khác che (ví dụ overlay loading) |
| `.evaluate(js_code)` | 171 | Chạy **JavaScript trực tiếp trong trang** — dùng cho các việc Playwright API thuần không làm được: đọc `innerText`, gọi `.click()` qua JS (né một số hạn chế của click chuột thật), tương tác với jQuery/Select2 nội bộ của trang |
| `.inner_text()` | 114 | Đọc **text hiển thị** của 1 phần tử (đã qua CSS, khác `.text_content()` là lấy toàn bộ text kể cả phần bị ẩn) — dùng để so khớp tên dòng trong bảng, label field, nội dung popup |
| `.all()` | 106 | Lấy **toàn bộ danh sách phần tử** khớp locator (dạng list Python) để `for` loop qua từng cái — ví dụ loop qua tất cả các dòng bảng, tất cả option trong 1 dropdown |
| `.scroll_into_view_if_needed()` | 46 | Cuộn trang để phần tử hiện ra trong khung nhìn trước khi click/check — cần vì bảng dữ liệu The Brick thường rất dài, phần tử nằm ngoài viewport sẽ không click được |
| `.nth(index)` | 31 | Lấy phần tử thứ N (đếm từ 0) trong danh sách kết quả locator — ví dụ ô thứ 2 (`nth(1)`) trong 1 dòng bảng |
| `.press(key)` | 30 | Gõ 1 phím đặc biệt (`Tab`, `Enter`, `Escape`) — dùng để đóng dropdown, xác nhận giá trị, thoát khỏi picker |
| `.bounding_box()` | 29 | Lấy toạ độ (x, y, width, height) thật của phần tử trên màn hình — dùng khi cần tính toán vị trí (ví dụ kéo-thả `reorder`, hoặc kiểm tra phần tử có nằm trong viewport hay không) |
| `.wait_for_load_state(state)` | 27 | Chờ trang đạt trạng thái tải nhất định (`"domcontentloaded"`, `"load"`, `"networkidle"`) — dùng sau khi `navigate`/`goto` |
| `.is_checked()` | 27 | Kiểm tra 1 checkbox/radio đang **được tick hay chưa** — để tránh tick lại (toggle nhầm ngược) |
| `.fill(text)` | 27 | Điền text vào input/textarea (xoá nội dung cũ rồi gõ mới ngay lập tức, không giả lập từng phím) — dùng cho các field text/số thông thường |
| `.input_value()` | 10 | Đọc **giá trị hiện tại** của input/select — dùng ở `check_fields_in_tabs` để so sánh giá trị đã lưu vs. giá trị mong đợi |
| `.focus()` | 10 | Đưa con trỏ chuột/focus vào phần tử trước khi gõ hoặc trước khi bấm phím tắt |
| `.wait_for_selector(selector)` | 7 | Chờ (block) tới khi 1 selector xuất hiện trên DOM — dùng khi cần chắc chắn 1 phần tử render xong trước khi đọc/thao tác nó |
| `.reload()` | 7 | Tải lại trang — dùng sau khi 1 popup thành công tự `location.reload()` (ví dụ sau import CSV) để đồng bộ trạng thái Playwright với trang |
| `.get_by_role(role, name=...)` | 7 | Tìm phần tử theo **role** (accessibility role, ví dụ `"button"`) + tên — cách tìm ổn định hơn CSS selector khi HTML hay đổi class |
| `.select_option(value/label)` | 6 | Chọn 1 option trong `<select>` HTML gốc (không phải dropdown custom kiểu select2/chosen) |
| `.on(event, handler)` | 6 | Đăng ký lắng nghe sự kiện của `page` — 2 sự kiện chính được dùng: `"dialog"` (bắt alert/confirm JS gốc của browser) và `"filechooser"` (bắt sự kiện mở file picker của OS) |
| `.is_editable()` | 6 | Kiểm tra input có đang **bị disable/readonly** hay không trước khi điền |
| `.check(force=True)` | 6 | Tick checkbox/radio (cách "chuẩn" của Playwright, tự mô phỏng click thật) |
| `.set_input_files(path)` | 5 | **Gán file trực tiếp** vào `<input type="file">` — cách upload nhanh, không cần đợi popup file chooser của OS |
| `.get_by_text(text)` | 5 | Tìm phần tử theo **nội dung text hiển thị** — hay dùng để tìm nút theo label khi không biết CSS selector |
| `.expect_file_chooser()` | 5 | Context manager: "chờ và bắt" sự kiện file chooser của hệ điều hành mở ra sau khi bấm nút Import, để có thể set file vào ngay khi nó xuất hiện |
| `.type(text)` | 4 | Gõ từng ký tự (giả lập bàn phím thật, chậm hơn `.fill()`) — dùng cho các ô search cần trigger sự kiện `keyup` từng phím (ví dụ search box của select2) |
| `.is_enabled()` | 4 | Kiểm tra nút bấm có đang bị disable không (ví dụ nút Save bị disable khi form thiếu field bắt buộc) |
| `.uncheck()` | 3 | Bỏ tick checkbox — ngược với `.check()` |
| `.wait_for_function(js)` | 2 | Chờ cho tới khi 1 biểu thức JavaScript trả về `true` — dùng cho điều kiện chờ phức tạp mà `wait_for_selector` không diễn tả được |
| `.new_page()` | 2 | Tạo tab mới trong context — chỉ dùng khi Chrome CDP chưa có tab nào mở sẵn |
| `.goto(url)` | 2 | Điều hướng thẳng tới 1 URL — hiếm dùng vì phần lớn nav là click menu, chỉ dùng khi target là link đầy đủ |
| `.get_by_placeholder(text)` | 2 | Tìm input theo text placeholder (gợi ý) của nó |
| `.expect_download()` | 2 | Context manager: "chờ và bắt" sự kiện download bắt đầu, để lấy được đối tượng file đã tải và đổi tên/di chuyển nó |
| `.press_sequentially(text)` | 1 | Gõ từng phím có delay (bản mới của `.type()` trong Playwright hiện đại) |
| `.hover()` | 1 | Rê chuột vào phần tử (không click) — dùng khi UI cần hover để hiện ra menu/tooltip |
| `.wait_for_timeout(ms)` | 1 | Chờ cứng N milliseconds — cách "chờ tạm" ít được ưu tiên (thường bị coi là code smell trong Playwright, chỉ dùng khi không có cách chờ theo điều kiện) |
| `.expect_navigation()` | 1 | Chờ trang chuyển sang URL khác sau 1 hành động |
| `.title()` | 1 | Đọc tiêu đề trang (`<title>`) |
| `.is_disabled()` | 1 | Kiểm tra phần tử có bị disable — ngược logic với `.is_enabled()`, dùng ở 1 nhánh cụ thể |

> Ghi chú: `page.keyboard.press(...)` và `dialog.accept()/dialog.dismiss()` cũng được dùng
> (xem [mục 11](#11-cơ-chế-xử-lý-popupmodal-đặc-biệt)) — đây là API con của `page.keyboard`
> và của đối tượng `dialog` nhận được từ event `"dialog"`, không nằm trực tiếp trên
> `page`/`locator` nên được tách riêng khỏi bảng trên.

## 10. Danh sách các biến/quy ước đặt tên hay gặp

Code trong project không đặt tên biến Playwright tuỳ tiện — có 1 số quy ước lặp lại xuyên suốt
hàng chục file, giúp đọc code nhất quán:

| Tên biến | Kiểu dữ liệu Playwright | Ý nghĩa |
|---|---|---|
| `page` | `Page` | Tab trình duyệt đang làm việc — **tham số đầu tiên của gần như mọi hàm** trong `automation/` |
| `browser` | `Browser` | Đại diện cả trình duyệt Chrome (chỉ dùng ở `core.py`, nơi kết nối CDP) |
| `context` | `BrowserContext` | "Hồ sơ" trình duyệt chứa các tab/cookie (chỉ dùng ở `get_existing_page`) |
| `container` | `Locator` | Khung chứa 1 dropdown/component phức tạp (ví dụ khung `.select2-container`) — dùng làm gốc để tìm các phần tử con bên trong nó |
| `wrapper` | `Locator` | Tương tự `container` — khung bọc ngoài của 1 custom dropdown (select2/chosen/vue-multiselect) |
| `modal` / `modal_el` | `Locator` hoặc biến JS | Popup/modal đang mở (Bootstrap `.modal.show`/`.modal.in`, hoặc SweetAlert2 `.swal2-popup`) |
| `opt` | `Locator` | 1 option cụ thể trong danh sách kết quả dropdown (`.select2-results__option`) |
| `sel` / `hidden_select` | `Locator` | Phần tử `<select>` HTML gốc (thường bị ẩn — dropdown custom vẽ đè lên trên nó) |
| `inp` | `Locator` | 1 input cụ thể (thường là ô ngày-giờ flatpickr, hoặc filter box) |
| `btn` / `trigger` | `Locator` | Nút bấm sẽ được click (Save, Import, Export, Filter...) |
| `dl` | Đối tượng trả về từ `page.expect_download()` | Chứa `dl.value.suggested_filename` và `dl.value.save_as(path)` |
| `fc_info` | Đối tượng trả về từ `page.expect_file_chooser()` | Chứa `.value` là `FileChooser`, gọi `.set_files(path)` trên đó |
| `dialogs_seen` | `list[dict]` | Danh sách các browser alert/confirm (`dialog`) đã bắt được trong quá trình `_save_form` |
| `label_text` / `target_text` / `tgt` | `str` | Tên field/label/nút mà JSON action plan chỉ định — input của các hàm tìm phần tử (`_find_input_element`, `smart_click`...) |
| `val` | `str` | Giá trị cần điền/so sánh, lấy từ `step["value"]` trong JSON |
| `data` / `popup_data` | `dict` | Toàn bộ các field cần điền trong 1 bước `update_form`, dạng `{"Tên field": "giá trị"}` |

## 11. Cơ chế xử lý popup/modal đặc biệt

The Brick dùng khá nhiều loại popup khác nhau (Bootstrap modal, SweetAlert2, browser alert
gốc), và mỗi loại "chặn" luồng automation theo cách khác nhau nếu không được xử lý đúng:

- **`page.on("dialog", handle_dialog)`** (trong `_save_form`, `form_save.py`): bắt các
  **alert/confirm/prompt gốc của trình duyệt** (không phải HTML popup — đây là popup hệ điều
  hành/Chrome vẽ ra). Handler gọi `dialog.accept()` để tự bấm OK; nếu trang đã bị đóng/chuyển
  hướng thì fallback qua `dialog.dismiss()`, tránh crash do "Not attached to an active page".
- **`_ensure_swal2_clone_confirmation_yes(page)`** (`core.py`): tự tìm và bấm nút "Yes" trên
  popup xác nhận **SweetAlert2** (thư viện popup JS phổ biến, class `.swal2-popup`), được gọi
  trước MỌI bước click/select/update_form/save_form/navigate/process_deployment.
- **`_ensure_rbe_are_you_sure_closed(page)`** (`core.py`): tự đóng popup xác nhận kiểu
  **Bootstrap modal** ("Are you sure?" — ví dụ khi lịch RBE nằm ngoài khoảng cho phép).
- **Phát hiện đang ở trong "clone modal"** (`dropdown_handler.py`): dùng JS
  `/Clone/i.test(modalEl.innerText)` để biết đang chọn dropdown TRONG modal Clone hay ở form
  bình thường — vì cách chọn Select2 an toàn khác nhau giữa 2 trường hợp (xem
  [mục 13](#13-những-cạm-bẫy-gotcha-quan-trọng-khi-dùng-playwright-trong-project-này)).

## 12. Cơ chế Upload / Download file

**Download (`action: "download"`, xử lý trực tiếp trong `core.py`):**

```python
with page.expect_download(timeout=30000) as dl:
    btn.click()          # hoặc btn.evaluate("el=>el.click()") nếu btn bị che
save_name = val hoặc tên_file_từ_target hoặc dl.value.suggested_filename
dl.value.save_as(os.path.join(DOWNLOAD_DIR, save_name))
```

`page.expect_download()` là 1 **context manager** — nó "canh" sẵn sự kiện download SẼ xảy ra
bên trong block `with`, rồi cung cấp đối tượng `dl` sau khi thoát block. `dl.value` là
`Download` object của Playwright, có `.suggested_filename` (tên file browser gợi ý) và
`.save_as(path)` (di chuyển file tải về tới đúng thư mục `downloads/` với tên mong muốn).

**Upload (`action: "upload"`, xử lý trong `smart_tester/upload_handler.py`):** có 2 kiểu UI
khác nhau trên The Brick, nên code có 2 cách xử lý:

1. **File input ẩn có sẵn trong DOM**: gọi trực tiếp `file_input.set_input_files(path)` —
   không cần chờ popup OS nào cả, nhanh nhất.
2. **Nút bấm mở "file chooser" thật của hệ điều hành** (nút không gắn sẵn `<input type=file>`
   nhìn thấy được): phải dùng
   ```python
   with page.expect_file_chooser(timeout=...) as fc_info:
       trigger.click()
   fc_info.value.set_files(path)
   ```
   `page.expect_file_chooser()` canh sự kiện `filechooser` sắp nổ ra khi click, `fc_info.value`
   là đối tượng `FileChooser`, gọi `.set_files(path)` để "chọn" file mà không cần dialog thật
   của OS hiện lên (Playwright chặn dialog OS lại và tự cấp file).

> Có 1 lớp bảo vệ bổ sung: `page.on("filechooser", lambda fc: fc.set_files([]))` — đăng ký
> tạm 1 listener "hứng và huỷ" bất kỳ file chooser bất ngờ nào bật lên ngoài dự kiến (ví dụ do
> click nhầm nút Import 2 lần), rồi **gỡ listener này ngay trong `finally`** để không xung đột
> với `expect_file_chooser()` ở lần upload kế tiếp.

## 13. Những "cạm bẫy" (gotcha) quan trọng khi dùng Playwright trong project này

Đây là các bài học thực tế (đã từng gây lỗi live) liên quan trực tiếp tới cách Playwright
tương tác với DOM đặc thù của The Brick — rất hữu ích để hiểu TẠI SAO code lại viết "vòng vèo"
ở một số chỗ trông có vẻ đơn giản:

- **`opt.click()` trong Select2 khi đang ở "clone modal" sẽ làm modal tự đóng.** Vì
  `opt.click()` phát ra 1 sự kiện click ở cấp `<body>`, và Bootstrap coi đây là "click ra
  ngoài `.modal-dialog`" → tự đóng modal trước khi giá trị được lưu. Cách vá: khi phát hiện
  đang trong modal Clone, dùng jQuery **gán giá trị trực tiếp bằng code**
  (`$sel.val(optId).trigger('change')`) thay vì giả lập click chuột thật.
- **`offsetParent !== null` luôn = `false` với phần tử `position: fixed`.** Nhiều popup quan
  trọng (`.swal2-container`, `.modal.show`) dùng CSS `position: fixed` — nên các đoạn code
  kiểm tra "phần tử có đang hiển thị" bằng `offsetParent` sẽ LUÔN báo sai (báo ẩn dù đang hiện
  rõ trên màn hình). Phải dùng `getBoundingClientRect()` + style tính toán (computed style)
  thay thế.
- **Select2 hiển thị placeholder "Searching…" dùng CHUNG class với option thật**
  (`.select2-results__option`), chỉ khác ở thuộc tính `aria-disabled="true"`. Nếu code không
  loại trừ `aria-disabled`, nó sẽ đếm nhầm placeholder là "1 option đã load xong" và bỏ qua
  chờ thêm → tưởng không tìm thấy option, rơi vào nhánh xử lý chậm hơn (gõ tay + Enter) một
  cách không cần thiết.
- **Named form control tên `"contains"` sẽ "che" luôn hàm `Node.prototype.contains` của
  chính DOM node đó** (ví dụ `<input name="contains">` bên trong `<form>`) — gọi
  `form.contains(el)` sẽ ném lỗi `TypeError: f.contains is not a function` vì JavaScript ưu
  tiên tìm thuộc tính riêng (`form.contains` = cái input) trước khi tìm hàm kế thừa từ
  prototype. Fix: gọi `Node.prototype.contains.call(form, el)` thay vì `form.contains(el)`.
- **Click lại nút "Import" đã từng bấm 1 lần có thể mở lại file chooser của OS** — nếu vòng
  lặp "bấm nút Confirm sau khi upload" tìm nút bằng selector KHÔNG giới hạn phạm vi trong modal
  (ví dụ `button:has-text('Import')` không kèm `.modal`/`.swal2-popup` phía trước), nó có thể
  vô tình khớp luôn nút Import gốc ở ngoài trang → bấm lại → mở native OS dialog → **treo cứng
  toàn bộ automation** (Playwright không tự đóng được dialog thật của hệ điều hành).

---

## Tóm tắt nhanh (nếu chỉ đọc 1 đoạn)

AutoGameOps là **Python + Streamlit + Ollama/Claude + Playwright**: người dùng gõ lệnh test
tiếng Việt/Anh → AI dịch ra JSON các bước hành động → `automation/core.py` **gắn Playwright
vào 1 Chrome đang mở sẵn qua CDP port 9222** (`page.chromium.connect_over_cdp`, biến `page` là
tab làm việc chính) → lặp qua từng bước JSON, gọi đúng hàm Playwright tương ứng
(`.locator().click()/.fill()/.check()`, `.evaluate()` cho các trường hợp JS đặc biệt như
Select2, `.expect_download()`/`.expect_file_chooser()` cho upload/download) → ghi log PASS/FAIL
→ nếu PASS sạch thì lưu lại JSON đó làm "golden plan" để lần sau khỏi cần hỏi AI lại.

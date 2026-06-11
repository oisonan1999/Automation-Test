# automation/core.py
import ast
import time
import re
import os
import json
import sys
import asyncio
from playwright.sync_api import sync_playwright

# Map from clone-modal field name (lowercase) → feature key in smoke_last_ids.json
_CLONE_FIELD_TO_FEATURE = {
    "book name": "PVE",
    "rules based tournament id": "RBE",
    "cloned rules based tournament id": "RBE",
    "new event id": "Gacha",
    "new ff id": "Faction Feud",
    "new tournament id": "Showdown",
    "bracket id": "Showdown",
    "nrb id": "Showdown",
    "new offer id": "Offer",
    "new section id": "Offer Section",
    "currency id": "Currency",
    "grabbag id": "Grabbag",
    "new tier id": "Fight Card Slots",
    "fightcard id": "Fight Card",
    "faction boss battle name": "Faction Boss",
    "new key": "Perk/Perk Slot",
    "new superstar id": "SuperStar",
    "loc id": "Localization",
    "moment poster id": "Moment Poster",
}

_SMOKE_ID_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "smoke_last_ids.json")


def _persist_clone_id(last_update_form_data: dict):
    """
    After save_form(mode='clone') succeeds, extract the new ID from the most
    recent update_form data and persist it to smoke_last_ids.json.
    Logs a confirmation line so the user knows it was saved.
    """
    if not last_update_form_data:
        return

    new_id = None
    feature = None
    for key, val in last_update_form_data.items():
        if _CLONE_FIELD_TO_FEATURE.get(key.lower().strip()) and val:
            new_id = str(val).strip()
            feature = _CLONE_FIELD_TO_FEATURE[key.lower().strip()]
            break

    if not new_id or not feature:
        return

    try:
        ids = {}
        if os.path.exists(_SMOKE_ID_FILE):
            with open(_SMOKE_ID_FILE, "r", encoding="utf-8") as f:
                ids = json.load(f)
        existing = ids.get(feature, [])
        if isinstance(existing, str):
            existing = [existing]
        if new_id not in existing:
            existing.append(new_id)
        ids[feature] = existing
        os.makedirs(os.path.dirname(_SMOKE_ID_FILE), exist_ok=True)
        with open(_SMOKE_ID_FILE, "w", encoding="utf-8") as f:
            json.dump(ids, f, ensure_ascii=False, indent=2)
        print(f"      💾 Clone ID saved → '{feature}': '{new_id}' (smoke_last_ids.json)")
    except Exception as e:
        print(f"      ⚠️ Could not save clone ID: {e}")

# --- IMPORT CÁC MODULE CON ---
from automation.constants import DOWNLOAD_DIR
from automation.navigator import NavigatorMixin
from automation.form_handler import FormHandlerMixin
from automation.table_handler import TableHandlerMixin
from automation.data_handler import DataHandlerMixin
from automation.smart_tester import SmartTesterMixin


class BrickAutomation(
    NavigatorMixin,
    TableHandlerMixin,
    FormHandlerMixin,
    DataHandlerMixin,
    SmartTesterMixin,
):
    def __init__(self):
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)
        self.memory = {}  # Trí nhớ ngắn hạn cho robot

    def close_popup(self, page):
        """
        Override popup closer so Smoke path (core.py) also auto-dismisses
        blocking modals like "DNU Warning".
        Uses SmartTesterMixin._ensure_popup_closed when available.
        """
        # CRITICAL: Import CSV Warning popup cần bấm "Continue" để app thực sự ghi đè.
        try:
            warning_modal = (
                page.locator(
                    ".modal.show, .modal.in, [role='dialog']:visible, .swal2-popup:visible, .swal-modal:visible"
                )
                .filter(has_text=re.compile(r"\bwarning\b", re.IGNORECASE))
                .first
            )
            continue_btn = warning_modal.locator(
                "button:has-text('Continue'), button:has-text('Proceed')"
            ).first
            if (
                warning_modal.count() > 0
                and warning_modal.is_visible()
                and continue_btn.is_visible()
            ):
                print(
                    "      🟠 Warning popup detected (continue needed) -> clicking Continue..."
                )
                continue_btn.click(force=True)
                time.sleep(0.35)
                return
        except Exception:
            pass

        try:
            ensure_fn = getattr(self, "_ensure_popup_closed", None)
            if callable(ensure_fn):
                ensure_fn(page)
                return
        except Exception:
            pass

        # Fallback minimal close
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

        try:
            btn = page.locator(
                "button:has-text('OK'), button:has-text('Close'), button:has-text('Confirm')"
            ).first
            if btn.is_visible():
                btn.click(force=True)
        except Exception:
            pass

    def _ensure_swal2_clone_confirmation_yes(self, page, max_rounds=5):
        """
        Auto-confirm SweetAlert2 clone prompt:
        e.g. "Do you want to clone the Contest Superstar Section?"
        Popup has buttons "Yes" (swal2-confirm) and "No"/"No" (cancel/deny).
        """
        try:
            for _ in range(max_rounds):
                popup = page.locator(".swal2-popup:visible").first
                if popup.count() == 0 or not popup.is_visible():
                    return False

                text = ""
                try:
                    text = popup.inner_text(timeout=500).strip().lower()
                except:
                    text = (popup.get_attribute("data-text") or "").lower()

                # Only handle clone prompts
                if "clone" not in text:
                    return False

                yes_btn = popup.locator(
                    "button.swal2-confirm, button:has-text('Yes'), button:has-text('yes')"
                ).first

                if yes_btn.count() > 0 and yes_btn.is_visible():
                    print(
                        "      🟡 SweetAlert2 clone confirmation detected -> clicking Yes..."
                    )
                    yes_btn.click(force=True)
                    time.sleep(0.35)

                    # Wait briefly for popup to disappear
                    try:
                        popup.wait_for(state="hidden", timeout=3000)
                    except:
                        pass
                    return True

                time.sleep(0.2)
        except Exception:
            return False

        return False

    def _ensure_rbe_are_you_sure_closed(self, page):
        """
        Dismiss two categories of blocking popups that appear in RBE/Contest flows:

        1. Confirmation modals:
           "Are you sure?" / "This event schedule is outside of the RBE's schedule"
        2. DNU Warning:
           "[X] is currently in the DNU list" (SweetAlert2 or Bootstrap modal, OK only)

        IMPORTANT: Never dismiss the "Defining Schedules" modal - that is a real data entry
        dialog, not a blocking confirmation.
        """
        dismissed = False
        try:
            # --- PASS 1: Confirmation modals ("Are you sure" / "outside of RBE schedule") ---
            # Regex is intentionally specific: requires "are you sure" OR the exact phrase
            # "outside of the rbe.*schedule". The old bare "rbe.*schedule" pattern was too
            # broad and matched the "Defining Schedules" modal body text, causing it to be
            # dismissed before "Add Schedule" could be clicked.
            confirm_re = re.compile(
                r"(are you sure|outside of the rbe.*schedule)",
                re.IGNORECASE,
            )

            candidates = page.locator(
                ".modal.show, .modal.in, [role='dialog']:not([aria-hidden='true']), .swal2-popup:visible"
            )
            count = candidates.count()
            for i in range(count):
                try:
                    modal = candidates.nth(i)
                    if not modal.is_visible():
                        continue
                    modal_text = modal.inner_text(timeout=600).strip()
                    # Skip "Defining Schedules" modal - it is a data entry form, not a confirmation
                    if "defining schedules" in modal_text.lower():
                        continue
                    if not confirm_re.search(modal_text):
                        continue
                    # Prefer explicit OK-like button; never guess on generic primary button
                    btn = modal.locator(
                        "button:has-text('OK'), button:has-text('Ok'), "
                        "button:has-text('Confirm'), button:has-text('Yes'), "
                        "button:has-text('Proceed'), button:has-text('Continue')"
                    ).first
                    if btn.count() > 0 and btn.is_visible():
                        print("      🔕 Are-you-sure modal detected; clicking OK...")
                        btn.click(force=True)
                        time.sleep(0.35)
                        dismissed = True
                except Exception:
                    continue
        except Exception:
            pass

        try:
            # --- PASS 2: DNU Warning popup ---
            # "PointCurrency_XXX is currently in the DNU list" - SweetAlert2 or Bootstrap.
            # Only has an OK button; must be dismissed so subsequent actions can proceed.
            #
            # IMPORTANT: use specific phrase matching, NOT bare "dnu" — gate dropdown options
            # in clone modals contain "DNU" gate names, causing the entire clone modal to
            # match and btn-primary (= Clone button) to be clicked prematurely.
            dnu_re = re.compile(
                r"dnu\s+warning|currently in the dnu\s+(list|blacklist)|is in the dnu\s+(list|blacklist)",
                re.IGNORECASE,
            )
            dnu_candidates = page.locator(
                ".modal.show, .modal.in, .swal2-popup:visible, [role='dialog']:visible"
            ).filter(has_text=dnu_re)
            if dnu_candidates.count() > 0 and dnu_candidates.first.is_visible():
                dnu_modal = dnu_candidates.first
                # Never use button.btn-primary — it matches Clone/Save buttons in regular modals.
                # DNU warning modals only have an explicit OK/Confirm button.
                ok_btn = dnu_modal.locator(
                    "button:has-text('OK'), button:has-text('Ok'), "
                    "button.swal2-confirm"
                ).first
                if ok_btn.count() > 0 and ok_btn.is_visible():
                    print("      🔔 DNU Warning detected; clicking OK to dismiss...")
                    ok_btn.click(force=True)
                    time.sleep(0.35)
                    dismissed = True
        except Exception:
            pass

        return dismissed

    def get_existing_page(self, p):
        try:
            # Kết nối vào trình duyệt Chrome đang mở sẵn qua cổng Debug
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            if len(context.pages) > 0:
                page = context.pages[0]
            else:
                page = context.new_page()
            return browser, page
        except Exception as e:
            raise Exception(
                f"Không thể kết nối Chrome! Hãy chạy lệnh debug port 9222. Lỗi: {e}"
            )

    # ============================
    # MAIN EXECUTION
    # ============================
    def execute_action(self, action_plan):
        report_logs = []
        if isinstance(action_plan, str):
            try:
                # Clean sơ bộ comment
                text = re.sub(r"", "", action_plan, flags=re.DOTALL)
                text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
                action_plan = json.loads(text)
            except:
                return [
                    {
                        "step": "System",
                        "status": "FAIL",
                        "details": "JSON Parse Error in Core",
                    }
                ]

        if isinstance(action_plan, dict):
            action_plan = [action_plan]

        # === Windows Fix: Playwright cần ProactorEventLoop để tạo subprocess ===
        # Streamlit/Tornado dùng SelectorEventLoop (không hỗ trợ subprocess trên Windows)
        # → Tạm chuyển sang ProactorEventLoopPolicy chỉ trong lúc chạy Playwright
        _original_policy = None
        if sys.platform == "win32":
            _original_policy = asyncio.get_event_loop_policy()
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        try:
            return self._execute_with_playwright(action_plan)
        finally:
            if _original_policy is not None:
                asyncio.set_event_loop_policy(_original_policy)

    def _execute_with_playwright(self, action_plan):
        """Core logic chạy Playwright - được gọi sau khi event loop policy đã được set đúng."""
        report_logs = []
        last_update_form_data = {}  # Track most recent update_form data for clone ID capture
        with sync_playwright() as p:
            try:
                browser, page = self.get_existing_page(p)

                # VALIDATION + AUTO-FIX: Fix invalid actions as safety net
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
                    "check_fields",
                    "click",
                    "select",
                    "wait",
                    "wait_for_page_load",
                    "process_deployment",
                    "reorder",
                }

                # Safety-net mapping (in case ai_brain.py fix_action_plan missed something)
                SAFETY_MAP = {
                    "select_random_ids": "checkbox",
                    "select_ids": "checkbox",
                    "check_checkbox": "checkbox",
                    "select_checkbox": "checkbox",
                    "export_csv": "download",
                    "export": "download",
                    "import_csv": "upload",
                    "import": "upload",
                    "click_logo": "process_deployment",
                    "click_logo_the_brick": "process_deployment",
                    "click_the_brick": "process_deployment",
                    "click_button": "click",
                    "press_button": "click",
                    "process": "process_deployment",
                    "deploy": "process_deployment",
                    "smart_test": "smart_test_cycle",
                    "test_cycle": "smart_test_cycle",
                    "save": "save_form",
                    "edit": "edit_row",
                    "clone": "clone_row",
                    "drag": "reorder",
                    "drag_drop": "reorder",
                    "drag_and_drop": "reorder",
                    "move_to": "reorder",
                    "move_item": "reorder",
                    "set_priority": "reorder",
                    "edit_csv": "manipulate_csv",
                    "modify_csv": "manipulate_csv",
                    "update_csv": "manipulate_csv",
                    # check_fields variants
                    "check_field": "check_fields",
                    "verify_fields": "check_fields",
                    "verify_field": "check_fields",
                    "inspect_fields": "check_fields",
                    "check_tab_fields": "check_fields",
                    "check_tabs": "check_fields",
                }

                for step in action_plan:
                    act = step.get("action")

                    # Auto-fix invalid action name via safety map
                    if act not in VALID_ACTIONS and act in SAFETY_MAP:
                        old_act = act
                        act = SAFETY_MAP[act]
                        step["action"] = act
                        print(f"   🔧 CORE AUTO-FIX: '{old_act}' → '{act}'")
                        # Also fix common field name issues
                        if act == "checkbox" and "count" in step:
                            step["value"] = f"random_{step.pop('count')}"
                            step.setdefault("target", "ID")
                        if act == "download" and "filename" in step:
                            step["value"] = step.pop("filename")
                            step.setdefault("target", "Export CSV")
                        if act == "upload" and "filename" in step:
                            step["value"] = step.pop("filename")
                            step.setdefault("target", "Import CSV")
                        if act == "click" and "label" in step and "target" not in step:
                            step["target"] = step.pop("label")

                    # Still invalid after mapping? Skip with warning
                    if act not in VALID_ACTIONS:
                        error_msg = (
                            f"❌ INVALID ACTION: '{act}' is not in allowed list!"
                        )
                        print(f"\n{'='*60}")
                        print(f"🚨 AI GENERATED INVALID ACTION (no mapping found)!")
                        print(f"   Invalid: '{act}'")
                        print(f"   Valid actions: {', '.join(sorted(VALID_ACTIONS))}")
                        print(f"   Full step: {step}")
                        print(f"{'='*60}\n")
                        report_logs.append(
                            {
                                "step": "Validation",
                                "status": "FAIL",
                                "details": error_msg,
                            }
                        )
                        continue  # Skip this invalid action

                    tgt = (
                        str(step.get("target", ""))
                        if step.get("target", None) is not None
                        else ""
                    )
                    val = (
                        str(step.get("value", ""))
                        if step.get("value", None)
                        is not None  # FIX: Check value not target!
                        else ""
                    )
                    data = step.get("data", {})
                    op = step.get("operation", "")
                    data_instr = step.get("data", "")
                    popup_data = (
                        step.get("data", {})
                        if act in ["fill_popup", "update_form"]
                        else {}
                    )

                    print(f"▶️ Executing: {act} -> {tgt} {val}")

                    # Nếu đang có popup confirm "Are you sure?" kiểu Bootstrap (ví dụ:
                    # "This event schedule is outside of the RBE's schedule...") thì phải OK trước
                    # khi tiếp tục các bước click/update/save, tránh AI bị block/nhảy bước sai.
                    try:
                        if act in {"click", "select", "update_form", "save_form",
                                   "navigate", "process_deployment"}:
                            # Handle SweetAlert2 clone confirmation first (Yes/No)
                            self._ensure_swal2_clone_confirmation_yes(page)
                            # Then handle existing Bootstrap confirmation modals
                            self._ensure_rbe_are_you_sure_closed(page)
                    except Exception:
                        pass

                    if act == "navigate":
                        nav_data = step.get("path") if step.get("path") else tgt
                        print(
                            f"   🔍 Navigator: {type(nav_data).__name__}, value: {nav_data}"
                        )
                        if isinstance(nav_data, str) and nav_data.strip().startswith(
                            "["
                        ):
                            try:
                                nav_data = ast.literal_eval(nav_data)
                            except:
                                pass
                        try:
                            self.smart_navigate(page, nav_data)
                            report_logs.append(
                                {
                                    "step": "Navigate",
                                    "status": "UNKNOWN",
                                    "details": str(nav_data)[:200],
                                }
                            )
                        except Exception as e:
                            report_logs.append(
                                {
                                    "step": "Navigate",
                                    "status": "FAIL",
                                    "details": f"{str(e)[:200]}",
                                }
                            )
                            # Stop this case so smoke classification is accurate
                            break
                    elif act == "checkbox":
                        val_lower = val.lower().strip()

                        # 1. Các giá trị TOGGLE FORM (Boolean)
                        is_form_toggle = val_lower in [
                            "on",
                            "off",
                            "true",
                            "false",
                            "1",
                            "0",
                            "yes",
                            "no",
                            "enable",
                            "disable",
                        ]

                        # 2. Các giá trị TABLE SELECT (Random/All/Specific ID)
                        # Nếu không phải toggle -> Mặc định là tìm dòng trong bảng
                        is_table_selection = not is_form_toggle
                        if not is_form_toggle and self._is_sidebar_item(page, tgt):
                            print(
                                f"      🔄 Detect Sidebar Item '{tgt}' in Checkbox command. Switching to CLICK."
                            )
                            click_success = self.smart_click(page, tgt)
                            report_logs.append(
                                {
                                    "step": "Sidebar Click",
                                    "status": "PASS" if click_success else "FAIL",
                                    "details": f"Redirected from Checkbox: {tgt}"
                                    + ("" if click_success else " - Element not found"),
                                }
                            )

                        if is_form_toggle:
                            print(
                                f"      🔄 Detect Toggle Value ('{val}'). Priority: FORM."
                            )
                            self._smart_update_form(page, {tgt: val})
                            report_logs.append(
                                {
                                    "step": "Form Toggle",
                                    "status": "PASS",
                                    "details": f"{tgt}={val}",
                                }
                            )

                        elif is_table_selection:
                            print(
                                f"      📊 Detect Selection Value ('{val}'). Priority: TABLE."
                            )
                            try:
                                # Gọi hàm xử lý bảng (có tích hợp Search & Filter)
                                logs = self.handle_checkbox(page, tgt, val)
                                report_logs.extend(logs)
                            except Exception as e:
                                print(f"      ⚠️ Table Checkbox failed: {e}")
                                # Chỉ fallback sang Form nếu thực sự thất bại ở bảng
                                # (Phòng trường hợp input text bình thường mà user gọi nhầm lệnh checkbox)
                                self._smart_update_form(page, {tgt: val})
                                report_logs.append(
                                    {
                                        "step": "Checkbox",
                                        "status": "FAIL",
                                        "details": str(e),
                                    }
                                )
                    elif act == "click" or act == "select":
                        # Ưu tiên dùng hàm smart_click chuyên biệt
                        click_success = self.smart_click(page, tgt)
                        report_logs.append(
                            {
                                "step": "Click",
                                "status": "PASS" if click_success else "FAIL",
                                "details": tgt
                                + ("" if click_success else " - Element not found"),
                            }
                        )

                        # [FIX] Nếu click thất bại, dừng execution để không làm hỏng các bước sau
                        if not click_success:
                            print(
                                f"      ⚠️ Click failed for '{tgt}'. Stopping execution to prevent errors."
                            )
                            break
                    elif act == "wait" or act == "wait_for_page_load":
                        print("      ⏳ Explicit WAIT requested...")
                        # Gọi hàm chờ Loading chuyên dụng
                        self._wait_for_long_loading(page)
                        report_logs.append(
                            {
                                "step": "Wait",
                                "status": "PASS",
                                "details": "Waited for Spinner",
                            }
                        )
                    elif act == "edit_row":
                        self._click_icon_in_row(page, tgt, "edit")
                    elif act == "clone_row":
                        self._click_icon_in_row(page, tgt, "clone")
                    elif act == "update_form":
                        self._smart_update_form(page, popup_data)
                        last_update_form_data = popup_data  # Track for clone ID capture
                        report_logs.append(
                            {
                                "step": "Form",
                                "status": "PASS",
                                "details": str(popup_data),
                            }
                        )
                    elif act == "save_form":
                        mode = step.get("mode", "save")
                        save_result = self._save_form(page, mode=mode)
                        if isinstance(save_result, str) and save_result.startswith(
                            "Error:"
                        ):
                            report_logs.append(
                                {
                                    "step": "Save",
                                    "status": "FAIL",
                                    "details": save_result,
                                }
                            )
                            print(f"      ❌ Save failed: {save_result}")
                            print(
                                f"      🛑 Stopping execution due to save error. Remaining steps will be skipped."
                            )
                            break  # STOP: Không chạy tiếp các bước sau khi Save bị lỗi
                        else:
                            report_logs.append(
                                {
                                    "step": "Save",
                                    "status": "PASS",
                                    "details": f"OK (mode={mode})",
                                }
                            )
                            # [CRITICAL] After save_form(clone), check for Locked Item popup
                            # Cloning navigates to the new item's edit page which may be locked
                            if mode == "clone":
                                # Persist the new clone ID so downstream "vừa clone" substitution works
                                _persist_clone_id(last_update_form_data)
                                print(
                                    "      ⏳ Waiting for cloned item page to load..."
                                )
                                # Regression speed-up: reduce sleep aggressively to reach edit_row before tool timeout.
                                time.sleep(0.1)
                                popup_handled = self._handle_locked_item_popup(page)
                                if popup_handled:
                                    time.sleep(0.1)
                                    print(
                                        "      ✅ Lock handled for cloned item. Ready to update form."
                                    )
                                else:
                                    time.sleep(0.1)

                    elif act == "download":
                        try:
                            # PVE Export Chapters special handling:
                            # For Export Chapter, BookID must come from page header "Event: <BookID> (....)"
                            # Then fill into input#searchChapterTemplate and select inside #listbox-searchChapterTemplate.
                            if str(tgt or "").strip().lower() == "export chapter":
                                book_id = None
                                try:
                                    # 1) Extract BookID from page text: "Event: LTPVE_.... (4149)"
                                    # We'll scan visible text nodes and match "Event:" prefix.
                                    book_id = page.evaluate("""() => {
                                        const re = /Event:\\s*([^:\\s(]+)\\s*(?=[:(])/i;
                                        const walker = document.createTreeWalker(
                                            document.body,
                                            NodeFilter.SHOW_TEXT,
                                            null,
                                            false
                                        );
                                        let node;
                                        while(node = walker.nextNode()){
                                            const t = (node.nodeValue || '').trim();
                                            if(!t) continue;
                                            const m = t.match(re);
                                            if(m && m[1]) return m[1].trim();
                                        }
                                        return null;
                                    }""")
                                    if book_id:
                                        book_id = str(book_id).strip()
                                        print(
                                            f"   🔍 Export Chapter: extracted BookID from page: '{book_id}'"
                                        )
                                except Exception as _extract_e:
                                    print(
                                        f"   ⚠️ Export Chapter: failed extracting BookID from page: {_extract_e}"
                                    )
                                    book_id = None

                                # 2) Fallback: if extraction fails, try from downloads/chapter_test.csv
                                if not book_id:
                                    try:
                                        import csv as _csv

                                        csv_path = os.path.join(
                                            DOWNLOAD_DIR, str(val or "chapter_test.csv")
                                        )
                                        prefer_path = os.path.join(
                                            DOWNLOAD_DIR, "chapter_test.csv"
                                        )
                                        if os.path.exists(prefer_path):
                                            csv_path = prefer_path

                                        if os.path.exists(csv_path):
                                            with open(
                                                csv_path, "r", encoding="utf-8-sig"
                                            ) as f:
                                                reader = _csv.DictReader(f)
                                                headers = reader.fieldnames or []
                                                book_col = None
                                                for h in headers:
                                                    hl = str(h).strip().lower()
                                                    if (
                                                        hl == "bookid"
                                                        or hl == "book id"
                                                        or hl.endswith("bookid")
                                                        or "bookid" in hl
                                                    ):
                                                        book_col = h
                                                        break
                                                if book_col is None and headers:
                                                    book_col = headers[0]
                                                for r in reader:
                                                    raw_book_id = (
                                                        r.get(book_col)
                                                        if book_col
                                                        else None
                                                    )
                                                    if raw_book_id:
                                                        book_id = str(
                                                            raw_book_id
                                                        ).strip()
                                                    break
                                    except Exception as _csv_e:
                                        print(
                                            f"   ⚠️ Export Chapter: CSV fallback BookID error: {_csv_e}"
                                        )

                                # 3) Select BookID using the correct multiselect in DOM
                                if book_id:
                                    try:
                                        ok = self._select_book_id_in_chapter_template_multiselect(
                                            page, book_id
                                        )
                                        if ok:
                                            time.sleep(1.0)
                                        else:
                                            print(
                                                "   ⚠️ Export Chapter: BookID selection failed (best-effort)."
                                            )
                                    except Exception as _sel_e:
                                        print(
                                            f"   ⚠️ Export Chapter: BookID selection exception: {_sel_e}"
                                        )
                                else:
                                    print(
                                        "   ⚠️ Export Chapter: BookID is empty; skipping template selection (best-effort)."
                                    )

                            btn = self._find_download_trigger(page, tgt)
                            if btn:
                                with page.expect_download(timeout=30000) as dl:
                                    if btn.is_visible():
                                        btn.click()
                                    else:
                                        btn.evaluate("el=>el.click()")
                                # IMPORTANT: Some UI actions (esp. Import CSV) may trigger temp downloads
                                # like "*_imported.csv" and "*_report_*.csv". We must NOT persist them
                                # into DOWNLOAD_DIR, otherwise user sees "imported/report" artifacts.
                                filename_lower = str(val or "").lower()
                                tgt_lower = str(tgt or "").lower()

                                is_temp_artifact = any(
                                    kw in filename_lower
                                    for kw in [
                                        "_imported",
                                        "imported",
                                        "_report",
                                        "report_",
                                    ]
                                ) or any(kw in tgt_lower for kw in ["import", "report"])

                                if is_temp_artifact:
                                    report_logs.append(
                                        {
                                            "step": "Download",
                                            "status": "SKIP",
                                            "details": f"Discarded temp download: {val}",
                                        }
                                    )
                                    # Do not save_as into DOWNLOAD_DIR
                                else:
                                    dl.value.save_as(os.path.join(DOWNLOAD_DIR, val))
                                    report_logs.append(
                                        {
                                            "step": "Download",
                                            "status": "PASS",
                                            "details": val,
                                        }
                                    )
                            else:
                                report_logs.append(
                                    {
                                        "step": "Download",
                                        "status": "FAIL",
                                        "details": "No Export button",
                                    }
                                )
                        except Exception as e:
                            report_logs.append(
                                {
                                    "step": "Download",
                                    "status": "FAIL",
                                    "details": str(e),
                                }
                            )

                    elif act == "smart_test_cycle":
                        logs = self.smart_test_cycle(page, val)
                        if logs and isinstance(logs, list):
                            report_logs.extend(logs)
                        else:
                            print("      ⚠️ Smart Test returned no logs.")

                    elif act == "upload":
                        upload_logs = self.handle_upload(page, tgt, val)
                        report_logs.extend(upload_logs)
                        self.close_popup(page)

                    elif act == "manipulate_csv":
                        report_logs.append(
                            {"step": "CSV", "status": "PASS", "details": op}
                        )
                        res = self._process_csv_manipulation(tgt, op, data_instr)
                        report_logs.append(
                            {
                                "step": "CSV",
                                "status": "PASS" if "Success" in res else "FAIL",
                                "details": res,
                            }
                        )

                    elif act == "scan_tabs":
                        self.scan_all_tabs(page, data)
                        report_logs.append(
                            {
                                "step": "Deep Scan",
                                "status": "PASS",
                                "details": "Checked all tabs",
                            }
                        )

                    elif act == "check_fields":
                        # data là dict: {"Tab Name": ["Field1", "Field2"]} hoặc list fields
                        tabs_data = step.get("data", step.get("tabs", {}))
                        field_logs = self.check_fields_in_tabs(page, tabs_data)
                        if field_logs:
                            report_logs.extend(field_logs)
                        else:
                            report_logs.append(
                                {
                                    "step": "Check Fields",
                                    "status": "WARN",
                                    "details": "No fields were checked (empty tabs_dict)",
                                }
                            )

                    elif act == "reorder":
                        reorder_target = step.get("target", "")
                        reorder_position = step.get("position", None)
                        reorder_before = step.get("before", None)
                        reorder_after = step.get("after", None)
                        print(
                            f"   🖱️  Reorder: '{reorder_target}' pos={reorder_position} before={reorder_before} after={reorder_after}"
                        )
                        if not reorder_target or not str(reorder_target).strip():
                            msg = "Reorder skipped: AI did not provide a target item name. Please re-run and specify the item to drag (e.g. 'Kéo alex_drip_test xuống dưới')."
                            print(f"   ❌ {msg}")
                            report_logs.append(
                                {"step": "Reorder", "status": "SKIP", "details": msg}
                            )
                        else:
                            try:
                                reorder_logs = self.drag_to_reorder(
                                    page,
                                    target=reorder_target,
                                    position=reorder_position,
                                    before=reorder_before,
                                    after=reorder_after,
                                )
                                report_logs.extend(reorder_logs)
                            except Exception as e:
                                print(f"   ❌ Reorder Error: {e}")
                                report_logs.append(
                                    {
                                        "step": "Reorder",
                                        "status": "FAIL",
                                        "details": str(e),
                                    }
                                )

                    elif act == "process_deployment":
                        options = step.get("options", [])
                        print(f"   🚀 Process Deployment: {options}")
                        # Dismiss any lingering popup before navigating home
                        try:
                            swal = page.locator(".swal2-popup")
                            if swal.count() > 0 and swal.first.is_visible():
                                ok_btn = swal.first.locator(
                                    "button.swal2-confirm, button:has-text('OK'), button:has-text('Yes')"
                                )
                                if ok_btn.count() > 0 and ok_btn.first.is_visible():
                                    ok_btn.first.click(force=True)
                                    time.sleep(0.3)
                                    print("      ✅ Dismissed lingering popup before navigating home")
                        except Exception:
                            pass
                        try:
                            self.process_deployment(page, options)
                            report_logs.append(
                                {
                                    "step": "Process Deployment",
                                    "status": "PASS",
                                    "details": f"Processed: {', '.join(options) if options else 'Default'}",
                                }
                            )
                        except Exception as e:
                            print(f"   ❌ Process Deployment Error: {e}")
                            report_logs.append(
                                {
                                    "step": "Process Deployment",
                                    "status": "FAIL",
                                    "details": str(e),
                                }
                            )

                    time.sleep(1)
                # ====================================================
                # [MỚI] TỰ ĐỘNG REFRESH TRANG SAU KHI HOÀN THÀNH
                # Skip refresh if process_deployment was executed (user is already on Home page)
                # ====================================================
                has_process_deployment = any(
                    step.get("action") == "process_deployment" for step in action_plan
                )

                if has_process_deployment:
                    print(
                        "   ℹ️  Skipping page refresh (process_deployment already navigated to Home)"
                    )
                else:
                    print("   🔄 Job Finished. Refreshing page to clean state...")
                    try:
                        # Reload trang
                        page.reload()
                        # Chờ nhẹ 1 chút để đảm bảo trang load xong cơ bản
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=5000)
                        except:
                            pass
                    except Exception as e:
                        print(f"   ⚠️ Refresh warning: {e}")
                return report_logs
            except Exception as e:
                print(f"CRASH: {e}")
                return [{"step": "System", "status": "CRASH", "details": str(e)}]

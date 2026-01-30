# automation_core.py
import ast
import time
import re
import os
import csv
import json
import random
import shutil
from playwright.sync_api import sync_playwright
import pandas as pd
import io

# --- IMPORT CÁC MODULE CON ---
from automation_modules.constants import DOWNLOAD_DIR
from automation_modules.navigator import NavigatorMixin
from automation_modules.form_handler import FormHandlerMixin
from automation_modules.data_handler import DataHandlerMixin
from automation_modules.smart_tester import SmartTesterMixin


class BrickAutomation(
    NavigatorMixin, FormHandlerMixin, DataHandlerMixin, SmartTesterMixin
):
    def __init__(self):
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)
        self.memory = {}  # Trí nhớ ngắn hạn cho robot

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

        with sync_playwright() as p:
            try:
                browser, page = self.get_existing_page(p)
                for step in action_plan:
                    act = step.get("action")
                    tgt = (
                        str(step.get("target", ""))
                        if step.get("target", None) is not None
                        else ""
                    )
                    val = (
                        str(step.get("value", ""))
                        if step.get("target", None) is not None
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

                    if act == "navigate":
                        # Lấy path hoặc target
                        nav_data = step.get("path") if step.get("path") else tgt

                        # FIX AN TOÀN: Nếu là String nhưng nhìn giống List "['A', 'B']"
                        # Trường hợp AI trả về string thay vì list thật
                        if (
                            isinstance(nav_data, str)
                            and nav_data.strip().startswith("[")
                            and nav_data.strip().endswith("]")
                        ):
                            try:
                                nav_data = ast.literal_eval(nav_data)
                            except:
                                pass

                        # Xử lý Logic
                        if isinstance(nav_data, list):
                            print(
                                f"      🔗 Detected Breadcrumb Navigation: {nav_data}"
                            )
                            for item in nav_data:
                                # Click từng thành phần trong chuỗi điều hướng
                                self.smart_click(page, str(item))
                        else:
                            # Điều hướng đơn lẻ
                            self._smart_navigate_path(page, str(nav_data))
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
                            self.smart_click(page, tgt)
                            report_logs.append(
                                {
                                    "step": "Sidebar Click",
                                    "status": "PASS",
                                    "details": f"Redirected from Checkbox: {tgt}",
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
                        self.smart_click(page, tgt)
                        report_logs.append(
                            {"step": "Click", "status": "PASS", "details": tgt}
                        )
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
                        report_logs.append(
                            {
                                "step": "Form",
                                "status": "PASS",
                                "details": str(popup_data),
                            }
                        )
                    elif act == "save_form":
                        self._save_form(page)
                        report_logs.append(
                            {"step": "Save", "status": "PASS", "details": "OK"}
                        )

                    elif act == "download":
                        try:
                            btn = self._find_download_trigger(page, tgt)
                            if btn:
                                with page.expect_download(timeout=30000) as dl:
                                    if btn.is_visible():
                                        btn.click()
                                    else:
                                        btn.evaluate("el=>el.click()")
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
                        report_logs.extend(logs)

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

                    time.sleep(1)
                # ====================================================
                # [MỚI] TỰ ĐỘNG REFRESH TRANG SAU KHI HOÀN THÀNH
                # ====================================================
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

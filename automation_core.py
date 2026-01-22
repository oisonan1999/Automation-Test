# automation_core.py
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

class BrickAutomation(NavigatorMixin, FormHandlerMixin, DataHandlerMixin, SmartTesterMixin):
    def __init__(self):
        if not os.path.exists(DOWNLOAD_DIR): os.makedirs(DOWNLOAD_DIR)
        self.memory = {} # Trí nhớ ngắn hạn cho robot

    def get_existing_page(self, p):
        try:
            # Kết nối vào trình duyệt Chrome đang mở sẵn qua cổng Debug
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            if len(context.pages) > 0: page = context.pages[0]
            else: page = context.new_page()
            return browser, page
        except Exception as e:
            raise Exception(f"Không thể kết nối Chrome! Hãy chạy lệnh debug port 9222. Lỗi: {e}")

    # ============================
    # MAIN EXECUTION
    # ============================
    def execute_action(self, action_plan):
        report_logs = []
        if isinstance(action_plan, dict): action_plan = [action_plan]
        
        with sync_playwright() as p:
            try:
                browser, page = self.get_existing_page(p)
                for step in action_plan:
                    act = step.get("action"); tgt = str(step.get("target","")); val=str(step.get("value",""))
                    data = step.get("data", {})
                    op = step.get("operation", ""); data_instr = step.get("data", "")
                    popup_data = step.get("data", {}) if act in ["fill_popup", "update_form"] else {}

                    print(f"▶️ Executing: {act} -> {tgt} {val}")

                    if act == "navigate": self._smart_navigate_path(page, step.get("path", [tgt, val]))
                    elif act == "checkbox": report_logs.extend(self.handle_checkbox(page, tgt, val))
                    elif act == "edit_row": self._click_icon_in_row(page, tgt, 'edit')
                    elif act == "clone_row": self._click_icon_in_row(page, tgt, 'clone')
                    elif act == "update_form": 
                        self._smart_update_form(page, popup_data)
                        report_logs.append({"step":"Form","status":"PASS","details":str(popup_data)})
                    elif act == "save_form": 
                        self._save_form(page)
                        report_logs.append({"step":"Save","status":"PASS","details":"OK"})
                    
                    elif act == "download":
                        try:
                            btn = self._find_download_trigger(page, tgt)
                            if btn:
                                with page.expect_download(timeout=30000) as dl:
                                    if btn.is_visible(): btn.click()
                                    else: btn.evaluate("el=>el.click()")
                                dl.value.save_as(os.path.join(DOWNLOAD_DIR, val))
                                report_logs.append({"step": "Download", "status": "PASS", "details": val})
                            else: report_logs.append({"step": "Download", "status": "FAIL", "details": "No Export button"})
                        except Exception as e: report_logs.append({"step": "Download", "status": "FAIL", "details": str(e)})

                    elif act == "smart_test_cycle":
                         logs = self.smart_test_cycle(page, val)
                         logs.extend(self.smart_test_cycle(page, val))
                         report_logs.extend(logs)

                    elif act == "upload": 
                         logs = self.handle_upload(page, tgt, val)
                         logs.extend(self.handle_upload(page, tgt, val))
                        #  report_logs.append({"step":"Upload","status":"PASS" if s else "FAIL","details":m})
                         self.close_popup(page)
                    
                    elif act == "manipulate_csv":
                        report_logs.append({"step":"CSV","status":"PASS","details":op})
                        res = self._process_csv_manipulation(tgt, op, data_instr)
                        report_logs.append({"step": "CSV", "status": "PASS" if "Success" in res else "FAIL", "details": res})

                    time.sleep(1)
                
                return report_logs
            except Exception as e: 
                print(f"CRASH: {e}")
                return [{"step": "System", "status": "CRASH", "details": str(e)}]
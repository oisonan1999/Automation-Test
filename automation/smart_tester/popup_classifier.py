# automation/smart_tester/popup_classifier.py - split from smart_tester.py
# Result popup: scan, classify success/error, ensure closed
from copy import deepcopy
from glob import glob
import io
import os
import random as rd
import time
import pandas as pd
import re
import csv
from playwright.sync_api import Page
from automation.constants import DOWNLOAD_DIR


class PopupClassifierMixin:
    """Result popup: scan, classify success/error, ensure closed"""

    def _classify_popup_message(self, text):
        """PASS/FAIL/None from popup text. Success keywords always beat error heuristics."""
        if not text or not str(text).strip():
            return None
        lower = str(text).lower()
        if any(
            k in lower
            for k in (
                "success",
                "successfully",
                "hoàn thành",
                "imported",
                "thành công",
                "completed",
                "done",
            )
        ):
            return "PASS"
        if re.search(r"\bfail(ed|ure)?\b", lower) or any(
            k in lower
            for k in (
                "error",
                "invalid",
                "duplicate",
                "missing",
                "required",
                "lỗi",
                "không hợp lệ",
                "exception",
                "cannot",
                "unable",
            )
        ):
            return "FAIL"
        return None

    def _resolve_upload_popup_outcome(self, popup_data):
        """Re-classify in Python so 'Import CSV successfully!' is never reported as FAIL."""
        if not popup_data:
            return False, ""
        text = str(popup_data.get("text") or "")
        py_type = self._classify_popup_message(text)
        if py_type:
            is_pass = py_type == "PASS"
            if py_type == "PASS" and popup_data.get("type") == "FAIL":
                print(f"   🔧 Popup reclassified PASS (was JS FAIL): {text[:80]}")
            return is_pass, text[:100]
        js_type = popup_data.get("type")
        return js_type == "PASS", text[:100]

    def _scan_for_result_popup(self, page):
        try:
            # Check Error popup first (priority) - Wait actively for 2s
            try:
                err = page.wait_for_selector(
                    ".swal2-error, .alert-danger, .toast-error, .notification-error, .swal2-icon-error, [class*='error'][class*='icon'], .error-message",
                    state="visible",
                    timeout=2000,
                )
                if err:
                    text = err.inner_text().strip()[:200]
                    print(f"   🔍 DEBUG: Found ERROR popup: {text[:50]}...")
                    return True, "FAIL", text
            except Exception as e:
                print(f"   🔍 DEBUG: No error popup found ({type(e).__name__})")

            # Check Success popup - Wait actively for 2s
            try:
                succ = page.wait_for_selector(
                    ".swal2-success, .alert-success, .toast-success, .notification-success, .swal2-icon-success, [class*='success'][class*='icon']",
                    state="visible",
                    timeout=2000,
                )
                if succ:
                    text = succ.inner_text().strip()[:200]
                    print(f"   🔍 DEBUG: Found SUCCESS popup: {text[:50]}...")
                    return True, "PASS", text
            except Exception as e:
                print(f"   🔍 DEBUG: No success popup found ({type(e).__name__})")

            # NEW: Check generic modal body content and classify by keywords
            # First try: Use evaluate() to read DOM directly (can read hidden modals)
            try:
                dom_result = page.evaluate("""
                    () => {
                        const modals = document.querySelectorAll('.modal .modal-body');
                        const results = [];
                        
                        for (const modal of modals) {
                            // Read innerText even if modal is hidden
                            if (modal && modal.innerText && modal.innerText.trim()) {
                                const text = modal.innerText.trim();
                                const isVisible = modal.offsetParent !== null;
                                results.push({ text: text, isVisible: isVisible });
                            }
                        }
                        
                        // Also check popup history if available
                        if (window.__popupHistory && window.__popupHistory.length > 0) {
                            const lastPopup = window.__popupHistory[window.__popupHistory.length - 1];
                            return { text: lastPopup.text, type: lastPopup.type, fromHistory: true };
                        }
                        
                        return results.length > 0 ? results[0] : null;
                    }
                """)

                if dom_result:
                    text = dom_result.get("text", "")
                    if text:
                        # Check if type already determined from history
                        if dom_result.get("type"):
                            result_type = dom_result["type"]
                            print(f"   🔍 DEBUG: Retrieved from history: {result_type}")
                            return True, result_type, text[:200]

                        # Otherwise classify based on keywords
                        error_keywords = [
                            "error",
                            "fail",
                            "invalid",
                            "lỗi",
                            "không hợp lệ",
                            "không thành công",
                        ]
                        is_error = any(kw in text.lower() for kw in error_keywords)

                        is_visible = dom_result.get("isVisible", False)
                        print(
                            f"   🔍 DEBUG: Modal found (visible={is_visible}): {text[:80]}..."
                        )
                        print(
                            f"   🔍 DEBUG: Classified as: {'FAIL' if is_error else 'PASS'}"
                        )

                        return True, ("FAIL" if is_error else "PASS"), text[:200]
            except Exception as e:
                print(f"   🔍 DEBUG: DOM modal check failed ({type(e).__name__})")

            # Fallback: Try Playwright locator (in case evaluate fails)
            try:
                modals = page.locator(".modal .modal-body").all()
                if len(modals) > 0:
                    print(
                        f"   🔍 DEBUG: Checking {len(modals)} modal-body elements (Playwright)"
                    )
                for idx, modal in enumerate(modals):
                    try:
                        # Read text without checking visibility first
                        text = modal.inner_text(timeout=500).strip()
                        if text:
                            # Classify based on keywords
                            error_keywords = [
                                "error",
                                "fail",
                                "invalid",
                                "lỗi",
                                "không hợp lệ",
                                "không thành công",
                            ]
                            is_error = any(kw in text.lower() for kw in error_keywords)

                            print(f"   🔍 DEBUG: Modal {idx+1} content: {text[:80]}...")
                            print(
                                f"   🔍 DEBUG: Classified as: {'FAIL' if is_error else 'PASS'}"
                            )

                            return (
                                True,
                                ("FAIL" if is_error else "PASS"),
                                text[:200],
                            )
                    except:
                        continue
            except Exception as e:
                print(f"   🔍 DEBUG: Modal body check failed ({type(e).__name__})")

            # DEBUG: Print all visible elements to help identify popup
            try:
                visible_els = page.locator(
                    "[class*='swal'], [class*='alert'], [class*='toast'], [class*='modal']"
                ).all()
                if visible_els:
                    print(
                        f"   🔍 DEBUG: Found {len(visible_els)} potential popup elements"
                    )
                    for idx, el in enumerate(visible_els[:3]):
                        try:
                            classes = el.get_attribute("class")
                            print(f"      Element {idx+1}: {classes}")
                        except:
                            pass
            except:
                pass

            return False, "UNKNOWN", "No popup text"
        except Exception as ex:
            print(f"   ⚠️ DEBUG: Popup scan crashed: {type(ex).__name__}: {ex}")
            return False, "ERROR", "Popup scan crashed"

    # ============================
    # FIX 1: HÀM DỌN DẸP POPUP (DÙNG JS)
    # ============================
    def _ensure_popup_closed(self, page):
        """Dọn dẹp popup bằng JS trực tiếp để tránh bị chặn bởi Overlay"""
        try:
            # CRITICAL: Some import flows show a blocking "Warning" modal that requires clicking
            # "Continue/Proceed" to actually apply CSV overwrite.
            # If we generic-close it here (Escape/OK), the import may be skipped.
            # Handle sequential import confirmation modals (2 popups in a row in your screenshot)
            # Goal: click Continue/Proceed fast, without relying on modal text == "Warning".
            try:
                for _ in range(5):
                    continue_btn = (
                        page.locator(
                            ".modal.show, .modal.in, [role='dialog']:visible, .swal2-popup:visible, .swal-modal:visible"
                        )
                        .locator(
                            "button:has-text('Continue'), button:has-text('Proceed')"
                        )
                        .first
                    )
                    if continue_btn.count() > 0 and continue_btn.is_visible():
                        print(
                            "      🟠 Continue/Proceed popup detected in _ensure_popup_closed -> clicking..."
                        )
                        continue_btn.click(force=True)
                        time.sleep(0.35)
                        continue
                    break
            except Exception:
                pass
            # Dùng JS tìm và click nút OK/Close/Confirm
            # Cách này mạnh hơn .click() của Playwright vì nó bỏ qua check visibility/overlay
            page.evaluate("""
                // =============================
                // 0) Special case: DNU Warning
                // =============================
                // Popup ví dụ trong ảnh:
                // - Title: "DNU Warning"
                // - Body: "... is currently in the DNU list"
                // - Button: "OK"
                try {
                    const dialogs = Array.from(
                        document.querySelectorAll(
                            '.modal.show, .modal.in, [role="dialog"], .swal2-container'
                        )
                    );
                    const dnu = dialogs.find(el => {
                        const t = (el && el.innerText) ? el.innerText : '';
                        return /dnu\\s*warning/i.test(t) || /dnu\\s*list/i.test(t);
                    });

                    if (dnu) {
                        const okBtn = Array.from(dnu.querySelectorAll('button, a'))
                            .find(b => {
                                const txt = (b && b.textContent) ? b.textContent.trim() : '';
                                return b.offsetParent !== null && /^ok$/i.test(txt);
                            });

                        if (okBtn) {
                            okBtn.click();
                            return;
                        }
                        // Fallback: nếu không match đúng text "OK", bấm nút primary gần đó
                        const fallbackOk = Array.from(dnu.querySelectorAll('button, a'))
                            .find(b => {
                                const cls = (b.getAttribute('class') || '').toLowerCase();
                                const txt = (b && b.textContent) ? b.textContent.trim() : '';
                                return b.offsetParent !== null && (cls.includes('btn-primary') || /^ok$/i.test(txt));
                            });
                        if (fallbackOk) {
                            fallbackOk.click();
                            return;
                        }
                    }
                } catch(e) {}

                // =============================
                // 1) SweetAlert buttons
                // =============================
                const confirmBtn = document.querySelector('button.swal2-confirm');
                const closeBtn = document.querySelector('button.swal2-close');

                // =============================
                // 2) Bootstrap modal buttons
                // =============================
                const modalBtn = document.querySelector('.modal.show button[data-dismiss="modal"]');
                const modalClose = document.querySelector('.modal.show .close');
                const modalConfirm = document.querySelector('.modal.show button.btn-primary');

                // =============================
                // 3) Generic close buttons
                // =============================
                const genericClose = document.querySelector(
                    '.popup button[class*="close"], .dialog button[class*="close"]'
                );

                // =============================
                // 4) Continue/Proceed buttons (import warnings)
                // =============================
                const continueBtn = Array.from(
                    document.querySelectorAll(
                        '.modal.show button, .swal2-popup button, [role="dialog"]:visible button'
                    )
                ).find(b => {
                    const txt = (b && b.textContent) ? b.textContent.trim() : '';
                    return b && b.offsetParent !== null && /^(continue|proceed)$/i.test(txt);
                });

                if (continueBtn) {
                    continueBtn.click();
                    return;
                }

                // Click first available button (use .offsetParent to check if truly visible)
                if (confirmBtn && confirmBtn.offsetParent !== null) {
                    confirmBtn.click();
                } else if (closeBtn && closeBtn.offsetParent !== null) {
                    closeBtn.click();
                } else if (modalBtn && modalBtn.offsetParent !== null) {
                    modalBtn.click();
                } else if (modalClose && modalClose.offsetParent !== null) {
                    modalClose.click();
                } else if (modalConfirm && modalConfirm.offsetParent !== null) {
                    modalConfirm.click();
                } else if (genericClose && genericClose.offsetParent !== null) {
                    genericClose.click();
                }
            """)
            time.sleep(0.4)  # Tăng thời gian chờ để đảm bảo animation hoàn tất
        except:
            pass

        # Biện pháp cuối: Xóa DOM nếu nó bị kẹt
        try:
            page.evaluate("""
                // Remove all overlay containers
                const overlays = document.querySelectorAll('.swal2-container, .modal-backdrop, .modal.show');
                overlays.forEach(el => el.remove());
                
                // Clean body classes
                document.body.classList.remove('swal2-shown', 'swal2-height-auto', 'modal-open');
                
                // Restore scroll
                document.body.style.overflow = 'auto';
                document.body.style.paddingRight = '';
            """)
        except:
            pass
        time.sleep(0.2)


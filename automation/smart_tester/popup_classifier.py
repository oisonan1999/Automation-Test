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


# Toast/growl/dialog texts that are PROMPTS emitted BEFORE the import request is
# even sent — never an import RESULT.
#
# Confirmed live by reading Gacha Event's own jQuery handlers
# (`jQuery._data(el,'events')`): clicking "Import from CSV" (`.btn-import-pool`)
# first growls "Saving gacha pool, please wait...", then clicks the page's Save,
# and only in that save's ajax callback opens the file chooser while growling
#     vit_message('Gacha pool has been saved, please select CSV file', 'success')
# `$.bootstrapGrowl` renders that as `.alert.alert-success`, and its text contains
# "saved" — so `_scan_for_result_popup` matched it as the import SUCCESS popup and
# returned PASS *before the import POST had even been fired*. That is exactly the
# false PASS behind "Gacha Pool tab is empty but the run says imported".
_PRE_IMPORT_PROMPT_RE = re.compile(
    r"please\s+select\s+(a\s+|the\s+)?(csv|file)"
    r"|please\s+choose\s+(a\s+|the\s+)?(csv|file)"
    r"|please\s+wait"
    r"|has\s+been\s+saved\s*,\s*please"
    r"|vui\s+lòng\s+(chọn|đợi)"
    r"|đang\s+lưu",
    re.IGNORECASE,
)


class PopupClassifierMixin:
    """Result popup: scan, classify success/error, ensure closed"""

    def _is_pre_import_prompt_text(self, text):
        """True for growls/dialogs that only ASK for input ("...please select CSV
        file", "Saving..., please wait") — these must never be classified as an
        import result. See _PRE_IMPORT_PROMPT_RE for the live-verified case."""
        if not text:
            return False
        return bool(_PRE_IMPORT_PROMPT_RE.search(str(text)))

    def _first_result_text(self, page, selector, timeout=2000):
        """First visible element matching `selector` whose text is a real result
        (not a pre-import prompt). Returns None if there is no such element.

        Iterates ALL matches instead of trusting `wait_for_selector`'s first hit:
        a pre-import growl and the genuine result popup can be on screen at the
        same time, and the growl is usually the older/earlier node.
        """
        try:
            page.wait_for_selector(selector, state="visible", timeout=timeout)
        except Exception:
            return None
        try:
            candidates = page.locator(selector).all()
        except Exception:
            return None
        for el in candidates:
            try:
                if not el.is_visible():
                    continue
                text = (el.inner_text(timeout=500) or "").strip()[:200]
                if not text:
                    continue
                if self._is_pre_import_prompt_text(text):
                    print(
                        f"   ⏭️ Ignoring pre-import prompt toast (not a result): {text[:70]}"
                    )
                    continue
                return text
            except Exception:
                continue
        return None

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
            err_text = self._first_result_text(
                page,
                ".swal2-error, .alert-danger, .toast-error, .notification-error, .swal2-icon-error, [class*='error'][class*='icon'], .error-message",
            )
            if err_text:
                print(f"   🔍 DEBUG: Found ERROR popup: {err_text[:50]}...")
                return True, "FAIL", err_text
            print("   🔍 DEBUG: No error popup found")

            # Check Success popup - Wait actively for 2s.
            # NOTE: pre-import prompt growls are filtered out inside
            # _first_result_text — they render as `.alert-success` too.
            succ_text = self._first_result_text(
                page,
                ".swal2-success, .alert-success, .toast-success, .notification-success, .swal2-icon-success, [class*='success'][class*='icon']",
            )
            if succ_text:
                print(f"   🔍 DEBUG: Found SUCCESS popup: {succ_text[:50]}...")
                return True, "PASS", succ_text
            print("   🔍 DEBUG: No success popup found")

            # NEW: Check generic modal body content and classify by keywords
            # First try: Use evaluate() to read DOM directly (can read hidden modals)
            try:
                dom_result = page.evaluate("""
                    () => {
                        const modals = document.querySelectorAll('.modal .modal-body');
                        const results = [];

                        for (const modal of modals) {
                            // Only VISIBLE modals are real result popups. A hidden
                            // modal-body (e.g. the Offer edit FORM that contains a
                            // "Gate:" label) must NOT be mistaken for an import result
                            // — that caused a false PASS while the real Warning popups
                            // were still waiting to be confirmed.
                            if (!(modal && modal.innerText && modal.innerText.trim()
                                && modal.offsetParent !== null)) continue;
                            // A genuine result/confirmation popup is just message text
                            // + buttons — it never contains fillable form controls. A
                            // visible modal WITH inputs/selects is a data-entry FORM
                            // (e.g. Clone/Add Currency) that happens to be open for an
                            // unrelated reason; its field labels/help text ("Currency ID
                            // ... Only alpha-numeric ... allowed", a Gate <select>'s
                            // default option) can read exactly like a validation error
                            // and must not be mistaken for the actual import result.
                            if (modal.querySelector('input:not([type=hidden]), select, textarea')) continue;
                            results.push({ text: modal.innerText.trim(), isVisible: true });
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
                    if text and self._is_pre_import_prompt_text(text):
                        print(
                            f"   ⏭️ Ignoring pre-import prompt modal (not a result): {text[:70]}"
                        )
                        text = ""
                    if text:
                        # Check if type already determined from history
                        if dom_result.get("type"):
                            result_type = dom_result["type"]
                            print(f"   🔍 DEBUG: Retrieved from history: {result_type}")
                            return True, result_type, text[:200]

                        # Otherwise classify with the shared keyword set (broader than a
                        # bare error-word list — catches validation phrasing like "Only
                        # alpha-numeric ... allowed. No spaces allowed." that names no
                        # literal "error"/"invalid"/"fail" word). A visible modal that
                        # matches neither PASS nor FAIL keywords defaults to FAIL: a
                        # genuine success confirmation always uses positive language
                        # (success/thành công/completed/imported), so unrecognized text
                        # is far more likely an unanticipated validation/error dialog.
                        classified = self._classify_popup_message(text)
                        result_type = classified or "FAIL"

                        is_visible = dom_result.get("isVisible", False)
                        print(
                            f"   🔍 DEBUG: Modal found (visible={is_visible}): {text[:80]}..."
                        )
                        print(f"   🔍 DEBUG: Classified as: {result_type}")

                        return True, result_type, text[:200]
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
                        # Skip hidden modals — only a visible modal is a real result
                        # popup (a hidden edit FORM modal would otherwise false-PASS).
                        if not modal.is_visible():
                            continue
                        # Same form-vs-result-popup filter as the DOM path above: a
                        # visible modal with fillable controls is a data-entry FORM
                        # (e.g. Clone/Add Currency) open for an unrelated reason, not
                        # the actual import result — its field hints can read exactly
                        # like a validation error.
                        if (
                            modal.locator(
                                "input:not([type='hidden']), select, textarea"
                            ).count()
                            > 0
                        ):
                            continue
                        text = modal.inner_text(timeout=500).strip()
                        if text and self._is_pre_import_prompt_text(text):
                            print(
                                f"   ⏭️ Ignoring pre-import prompt modal (not a result): {text[:70]}"
                            )
                            continue
                        if text:
                            # Same shared-keyword classification as the DOM path above,
                            # defaulting ambiguous text to FAIL rather than PASS.
                            classified = self._classify_popup_message(text)
                            result_type = classified or "FAIL"

                            print(f"   🔍 DEBUG: Modal {idx+1} content: {text[:80]}...")
                            print(f"   🔍 DEBUG: Classified as: {result_type}")

                            return (
                                True,
                                result_type,
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


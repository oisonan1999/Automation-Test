# automation/smart_tester/upload_handler.py - split from smart_tester.py
# CSV upload: trigger find, attempt loops, overwrite confirm
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


class UploadHandlerMixin:
    """CSV upload: trigger find, attempt loops, overwrite confirm"""

    def _perform_upload_action(self, page, file_path):
        """Upload và xử lý Popup Success/Failed"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                print(f"      🔄 Upload attempt {attempt+1}...")
                self._ensure_popup_closed(page)  # Đảm bảo sạch sẽ trước khi bấm nút

                # 1. Trigger File Chooser
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    # Tìm nút Import
                    btn = page.locator(
                        "button:has-text('Import CSV'), a:has-text('Import CSV')"
                    ).first
                    if not btn.is_visible():
                        btn = page.locator(".btn-import, [title='Import']").first
                    if not btn.is_visible():
                        btn = page.locator("button:has-text('Import')").first

                    if btn.is_visible():
                        btn.scroll_into_view_if_needed()
                        # Click Force để bỏ qua overlay vô hình (nếu còn sót)
                        btn.click(force=True)
                    else:
                        page.locator("input[type='file']").evaluate("e => e.click()")

                file_chooser = fc_info.value
                file_chooser.set_files(file_path)

                # Trigger Event cho React/Vue
                try:
                    file_chooser.element.evaluate(
                        "e => { e.dispatchEvent(new Event('change', {bubbles: true})); e.dispatchEvent(new Event('input', {bubbles: true})); }"
                    )
                except:
                    pass

                # 2. [FIX] Xử lý Confirmation Popup "Are you sure?" (nếu có)
                time.sleep(1)  # Đợi popup xuất hiện
                try:
                    # Tìm confirmation popup
                    popup = page.locator(
                        ".modal.show, .swal2-popup:visible, .swal-modal:visible"
                    ).first
                    if popup.count() > 0 and popup.is_visible():
                        print(f"      🔔 Confirmation popup detected for import")

                        # Tìm nút "Yes, do it!" hoặc các nút confirm khác
                        confirm_btn = popup.locator(
                            "button:has-text('Yes'), button:has-text('yes'), "
                            "button:has-text('Confirm'), button:has-text('confirm'), "
                            "button:has-text('OK'), button:has-text('ok'), "
                            "button:has-text('Continue'), button:has-text('continue'), "
                            "button:has-text('do it'), button:has-text('Do it'), "
                            "button.confirm, button.swal2-confirm, "
                            "button[class*='confirm'], a:has-text('Yes')"
                        ).first

                        if confirm_btn.count() > 0 and confirm_btn.is_visible():
                            confirm_btn_text = confirm_btn.inner_text().strip()
                            print(
                                f"      ✅ Clicking confirmation button: '{confirm_btn_text}'"
                            )
                            confirm_btn.click()
                            time.sleep(0.5)  # Đợi popup confirm đóng
                        else:
                            print(
                                f"      ⚠️ Confirmation popup detected but no button found"
                            )
                except Exception as conf_err:
                    print(f"      ℹ️ No confirmation popup: {conf_err}")

                # 3. CHỜ POPUP KẾT QUẢ (QUAN TRỌNG)
                # Dùng wait_for_selector thay vì vòng lặp while để Playwright tự handle việc chờ element xuất hiện
                try:
                    # Chờ .swal2-popup xuất hiện (Timeout 10s)
                    # Selector này khớp chính xác với ảnh bạn gửi
                    popup = page.wait_for_selector(
                        ".swal2-popup", state="visible", timeout=3000
                    )

                    if popup:
                        text = popup.inner_text().lower()
                        clean_text = text.replace("\n", " ").strip()[:200]

                        print("      ⏳ Popup detected, waiting ~2-3s...")
                        time.sleep(2.0)  # Chờ ngắn để popup ổn định
                        # Tìm nút OK (.swal2-confirm) và click luôn
                        page.evaluate("""
                            const btn = document.querySelector('button.swal2-confirm');
                            if (btn) btn.click();
                        """)
                        time.sleep(1.0)  # Chờ popup biến mất

                        # Phân loại kết quả
                        if "success" in text or "hoàn thành" in text:
                            print("      ✅ Success Popup detected & closed.")
                            self._ensure_popup_closed(
                                page
                            )  # Đảm bảo popup đã đóng hoàn toàn
                            return True, "Success"

                        error_keywords = [
                            "failed",
                            "error",
                            "invalid",
                            "duplicate",
                            "missing",
                            "required",
                            "not number",
                            "format",
                            "lỗi",
                        ]
                        if (
                            any(k in text for k in error_keywords)
                            and "sure" not in text
                        ):
                            # print(f"      ❌ Error Popup detected & closed: {clean_text[:50]}...")
                            self._ensure_popup_closed(
                                page
                            )  # Đảm bảo popup đã đóng hoàn toàn
                            return False, f"Error: {clean_text}"

                        # Nếu là popup confirm (Are you sure?) -> Loop sẽ quay lại và chờ popup kết quả tiếp theo
                        if "sure" in text or "confirm" in text:
                            continue

                except Exception as e:
                    print(f"      ⚠️ Wait timeout (No popup detected): {e}")
                    # Timeout nghĩa là không thấy popup -> Retry upload
                    pass

            except Exception as e:
                print(f"      ⚠️ Upload Exception: {e}")
                time.sleep(1)

        self._ensure_popup_closed(page)  # Đảm bảo popup đã đóng sau tất cả retry
        return False, "Max retries exceeded"

    def _try_upload_via_import_from_csv_modal(self, page, file_path):
        """
        Currency (and any other page sharing this exact UI shape) uses a
        two-step "Import From CSV" pattern the generic path below can't
        handle: a page-level trigger button labeled "Import From CSV" opens
        a Bootstrap modal (title "Import from CSV") containing a plain
        native <input type="file"> and a modal-scoped submit button labeled
        just "Import" — no "CSV" in it (confirmed via live CDP DOM dump:
        `<div id="csv_upload">...<input type="file" id="csv_file">...
        <button class="btn btn-primary import-csv">Import</button>`).

        The generic logic in this function fails on this shape for two
        reasons:
        1. It searches page-wide for `input[type='file']` and finds this
           modal's input while the modal is still hidden (`.modal.hide`),
           setting the file directly on it. The modal is a shared reusable
           component (Currency's page also has a near-identical sibling
           "Scan Currencies" modal with its own file input) — if opening it
           resets the form, the selection is silently lost. This matches
           the observed symptom: the run reported "uploaded" yet the
           re-opened modal still showed "No file chosen".
        2. Its submit-button search requires the literal text "Import CSV";
           this modal's button just says "Import", so it's never clicked
           and the form is never actually submitted.

        Detection is purely DOM-based (trigger text "Import From CSV" +
        the modal that appears containing an `input[type=file]`), gated on
        the trigger containing the word "From" — no other feature's "Import
        CSV" trigger uses that wording, so this cannot misfire on the
        ordinary direct-file-chooser pattern used everywhere else.

        Returns (success, msg, None) if this pattern was found and handled
        to completion, or None if the pattern isn't present at all (caller
        falls back to the generic upload logic below, completely unchanged).
        """
        try:
            trigger = (
                page.locator("button, a, [role='button']")
                .filter(has_text=re.compile(r"import\s+from\s+csv", re.IGNORECASE))
                .first
            )
            if trigger.count() == 0 or not trigger.is_visible(timeout=500):
                return None

            trigger.scroll_into_view_if_needed()
            trigger.click(force=True)

            modal = (
                page.locator(".modal")
                .filter(has=page.locator("input[type='file']"))
                .filter(has_text=re.compile(r"import from csv", re.IGNORECASE))
                .first
            )
            modal.wait_for(state="visible", timeout=5000)

            file_input = modal.locator("input[type='file']").first
            file_input.set_input_files(file_path)
            print("   🧾 [Import-From-CSV modal] File set on modal-scoped input")

            submit_btn = (
                modal.locator("button, a, [role='button']")
                .filter(has_text=re.compile(r"^\s*Import\s*$", re.IGNORECASE))
                .first
            )
            submit_btn.wait_for(state="visible", timeout=2000)
            submit_btn.click(force=True)
            print("   🧾 [Import-From-CSV modal] Clicked modal 'Import' submit button")
        except Exception as e:
            print(f"   ℹ️ [Import-From-CSV modal] pattern not detected/failed to handle: {e}")
            return None

        # Shared post-submit result detection — same building blocks the
        # generic path below uses (network idle, confirmation prompts, then
        # the result-popup scanner), so classification stays consistent.
        try:
            page.wait_for_load_state("networkidle", timeout=60000)
        except Exception:
            pass
        try:
            self._confirm_csv_overwrite_prompt_if_present(page, max_rounds=5)
        except Exception:
            pass
        if hasattr(self, "_wait_for_long_loading"):
            try:
                self._wait_for_long_loading(page, timeout_ms=20000)
            except Exception:
                pass

        found, res_type, res_text = self._scan_for_result_popup(page)
        self._ensure_popup_closed(page)
        if found:
            return (res_type == "PASS", str(res_text or "")[:100], None)

        # No popup at all — this UI style dismisses its own modal on a
        # successful ajax submit, so a still-open modal signals the submit
        # failed silently (client-side validation, network error, etc.)
        # rather than being a silent success.
        try:
            still_open = modal.is_visible(timeout=500)
        except Exception:
            still_open = False
        if still_open:
            return (False, "Import modal still open after submit — likely failed", None)
        return (True, "Import completed (modal closed, no popup)", None)

    def _upload_fuzz_fast(self, page, target_text, file_name, cached_selector=None):
        """Optimized upload for fuzzing: 15s timeout, cached selector. Returns (success, msg, selector)"""
        full_path = os.path.join(DOWNLOAD_DIR, file_name)
        try:
            btn = None

            # Currency-style "Import From CSV" -> separate modal pattern (see
            # docstring of _try_upload_via_import_from_csv_modal). Detected
            # purely from the DOM, so pages using the ordinary single-click
            # file-chooser pattern fall through to the logic below unchanged.
            _modal_result = self._try_upload_via_import_from_csv_modal(page, full_path)
            if _modal_result is not None:
                return _modal_result

            # Wait for any post-Export loading spinner to clear BEFORE locating the
            # Import control. On pages like Gacha Pool, exporting leaves a spinner up
            # while the table re-renders; if we run now the hidden input[type='file']
            # isn't in the DOM yet, so btn falls through to the plain "Import CSV"
            # submit button. Clicking that opens the native OS file dialog LATE (after
            # expect_file_chooser already timed out) → the dialog blocks the whole run.
            # Settling first lets the file-input path (set_input_files, no native
            # dialog) be taken instead.
            if hasattr(self, "_wait_for_long_loading"):
                try:
                    self._wait_for_long_loading(page, timeout_ms=15000)
                except Exception:
                    pass

            # Chapter Import UI requires:
            # 1) Click/select file in custom-file input[type='file']
            # 2) THEN click submit button "Import CSV"
            # If we pick the submit button as btn, file chooser won't open and import fails.
            target_lower = str(target_text or "").lower()

            # Chapter Import UI đôi khi được AI gọi là "Import Chapter ..." (không phải "Import CSV").
            # Nếu không nhận diện đúng thì ta có thể bấm nhầm submit button => không mở filechooser => timeout.
            is_import_csv_ui = (
                "import csv" in target_lower or target_lower.strip() == "import csv"
            )

            is_import_chapter_ui = (
                "import chapter" in target_lower
                or ("import" in target_lower and "chapter" in target_lower)
                or ("chapters" in target_lower and "import" in target_lower)
            )

            is_chapter_csv_file = str(file_name or "").lower().endswith(".csv") and (
                "chapter" in str(file_name or "").lower()
            )

            is_import_csv_ui = bool(
                is_import_csv_ui or is_import_chapter_ui or is_chapter_csv_file
            )

            submit_import_btn = None
            if is_import_csv_ui:
                try:
                    submit_import_btn = (
                        page.locator("button, a, [role='button']")
                        .filter(
                            has_text=re.compile(r"^\s*Import\s*CSV\s*$", re.IGNORECASE)
                        )
                        .first
                    )
                    if submit_import_btn.count() == 0:
                        submit_import_btn = (
                            page.locator("button, a, [role='button']")
                            .filter(has_text=re.compile(r"Import\s*CSV", re.IGNORECASE))
                            .first
                        )
                except:
                    submit_import_btn = None

                # Force btn to be the real file input (if present)
                # IMPORTANT: custom-file input[type='file'] can be hidden (z-index:-5),
                # but set_input_files works without it being visible.
                try:
                    file_input = (
                        page.locator(
                            "div.custom-file input[type='file'], input[type='file']"
                        )
                        .filter(has_not=page.locator("[disabled]"))
                        .first
                    )
                    if file_input.count() > 0:
                        btn = file_input
                        cached_selector = "input[type='file']"
                except:
                    pass

            # Use cache if available
            # IMPORTANT: if we already discovered a correct btn (e.g. custom-file input),
            # don't overwrite it by re-fetching the first generic match.
            if cached_selector and not btn:
                try:
                    btn = page.locator(cached_selector).first
                    # File inputs (custom-file) có thể bị hidden (z-index:-5).
                    # set_input_files vẫn hoạt động bình thường => không cần is_visible().
                    if "input[type='file']" not in str(cached_selector).lower():
                        if not btn.is_visible(timeout=500):
                            btn = None
                            cached_selector = None
                except:
                    btn = None
                    cached_selector = None

            # Find button with reduced strategies
            if not btn:
                # Strategy 1: Exact text (1s timeout)
                try:
                    btn = page.locator(
                        f"button:has-text('{target_text}'), a.btn:has-text('{target_text}')"
                    ).first
                    btn.wait_for(state="visible", timeout=1000)
                    if btn.is_visible():
                        cached_selector = f"button:has-text('{target_text}')"
                except:
                    pass

            # Strategy 2: Keywords (reduced from 5 to 2)
            if not btn or not btn.is_visible():
                for keyword in ["Import", "Upload"]:
                    try:
                        btn = page.locator(f"button:has-text('{keyword}')").first
                        if btn.is_visible(timeout=500):
                            cached_selector = f"button:has-text('{keyword}')"
                            break
                    except:
                        continue

            # Strategy 3: Input file (skip XPath - slow)
            if not btn or not btn.is_visible():
                try:
                    btn = page.locator("input[type='file']").first
                    if btn.count() > 0:
                        cached_selector = "input[type='file']"
                except:
                    pass

            if not btn or not btn.is_visible():
                self._ensure_popup_closed(page)
                return False, "Button not found", cached_selector

            # 1.5. Setup popup capture BEFORE uploading file (CRITICAL for fast popups)
            # [FIX] Clear any stale result from previous upload BEFORE injecting new listener.
            # Root cause of false-FAIL: a previous upload's __popupResult stays in DOM memory
            # and gets read at ~232ms before the new popup even renders.
            try:
                page.evaluate(
                    "window.__popupResult = null; window.__popupHistory = [];"
                )
            except:
                pass

            print("   🎬 Injecting JS popup capture script...")
            try:
                page.evaluate("""
                window.__popupResult = null;
                window.__popupHistory = [];

                // [FIX] SUCCESS-FIRST classification.
                // Old code used isError=true/false with no success check, so
                // "Import CSV successfully!" → isError=false → PASS was actually correct,
                // BUT the stale result from a prior upload was FAIL and got read first.
                // New code: explicit success keywords checked before error keywords.
                const __SUCCESS_KW = [
                    'success', 'successfully', 'hoàn thành', 'imported',
                    'updated', 'saved', 'completed', 'done', 'thành công'
                ];
                const __ERROR_KW = [
                    'error', 'fail', 'invalid', 'duplicate', 'missing',
                    'required', 'not number', 'format', 'does not match',
                    'không hợp lệ', 'lỗi', 'exception', 'cannot', 'unable'
                ];

                function __classifyText(text) {
                    const lower = text.toLowerCase();
                    if (__SUCCESS_KW.some(k => lower.includes(k))) return 'PASS';
                    // 'fail' must not match inside 'successfully'
                    if (/\\bfail(ed|ure)?\\b/.test(lower)) return 'FAIL';
                    if (__ERROR_KW.filter(k => k !== 'fail').some(k => lower.includes(k))) return 'FAIL';
                    return null;
                }

                function __storePopupResult(result) {
                    if (!result || !result.type) return;
                    const prev = window.__popupResult;
                    if (!prev || result.type === 'PASS') {
                        window.__popupResult = result;
                    } else if (prev.type !== 'PASS') {
                        window.__popupResult = result;
                    }
                }

                function __classifySwal(container, text) {
                    let classified = __classifyText(text);
                    if (classified) return classified;
                    const hasSuccess = !!container.querySelector('.swal2-success, .swal2-icon-success');
                    const hasError = !!container.querySelector('.swal2-error, .swal2-icon-error');
                    if (hasSuccess) return 'PASS';
                    if (hasError) return 'FAIL';
                    return null;
                }

                // Function to check and capture modal content (reads even hidden modals)
                function captureModalContent() {
                    // Check ALL modals (including hidden ones)
                    const modals = document.querySelectorAll('.modal');
                    for (const modal of modals) {
                        // [FIX] Skip hidden Bootstrap modals (stale .modal-body text caused false FAIL)
                        if (!modal.classList.contains('show') && modal.offsetParent === null) continue;
                        const body = modal.querySelector('.modal-body');
                        if (body && body.innerText && body.innerText.trim()) {
                            const text = body.innerText.trim();
                            const classified = __classifyText(text);
                            if (!classified) continue;  // skip ambiguous/loading text
                            const result = {
                                type: classified,
                                text: text,
                                timestamp: Date.now()
                            };
                            __storePopupResult(result);
                            window.__popupHistory.push(result);
                            return true;
                        }
                    }

                    // Check for SweetAlert
                    const swalContainers = document.querySelectorAll('.swal2-container');
                    for (const container of swalContainers) {
                        const content = container.querySelector('.swal2-html-container, .swal2-title');
                        if (content && content.innerText && content.innerText.trim()) {
                            const text = content.innerText.trim();
                            // Pre-import overwrite confirmation — not a pass/fail result yet
                            if (/are you sure|wish to proceed|overrides implemented data|importing data via csv/i.test(text)) continue;
                            const classified = __classifySwal(container, text);
                            if (!classified) continue;
                            const result = {
                                type: classified,
                                text: text,
                                timestamp: Date.now()
                            };
                            __storePopupResult(result);
                            window.__popupHistory.push(result);
                            return true;
                        }
                    }
                    return false;
                }

                // IMMEDIATE check (run once before interval starts)
                captureModalContent();

                // Check every 20ms for super fast capture
                const checkInterval = setInterval(() => {
                    captureModalContent();
                }, 20);

                // MutationObserver for instant capture when DOM changes
                const observer = new MutationObserver(() => {
                    captureModalContent();
                });

                observer.observe(document.body, {
                    childList: true,
                    subtree: true,
                    attributes: true,
                    attributeFilter: ['class', 'style']
                });

                // Cleanup after 10 seconds
                setTimeout(() => {
                    observer.disconnect();
                    clearInterval(checkInterval);
                }, 10000);
            """)
                time.sleep(0.1)  # Let script initialize
            except Exception as e:
                print(f"   ⚠️ JS injection failed: {e}")

            # 2. Upload File
            try:
                if btn.get_attribute("type") == "file":
                    btn.set_input_files(full_path)
                else:
                    # Prefer a hidden file input if one exists now (the spinner has
                    # cleared by this point) — set_input_files never opens the native
                    # OS dialog, so it can't time out or block the run.
                    file_input = page.locator("input[type='file']").first
                    if file_input.count() > 0:
                        file_input.set_input_files(full_path)
                    else:
                        # Fallback: click the trigger and catch the OS file chooser.
                        # 8s (was 3s) — clicks right after a heavy page render can take
                        # >3s for the chooser event to fire; a too-short timeout left
                        # the native dialog open and blocking.
                        with page.expect_file_chooser(timeout=8000) as fc_info:
                            btn.click()
                        fc_info.value.set_files(full_path)
                time.sleep(0.3)  # Reduced from 0.5s

                # If this is the Chapter Import UI, click the submit button after file is set
                if "is_import_csv_ui" in locals() and is_import_csv_ui:
                    try:
                        if (
                            submit_import_btn
                            and submit_import_btn.count() > 0
                            and submit_import_btn.is_visible()
                        ):
                            submit_import_btn.click(force=True)
                            print(
                                "   🧾 [Chapter Import] Clicked submit button: Import CSV"
                            )
                            time.sleep(0.4)
                    except Exception as _click_import_err:
                        print(
                            f"   ⚠️ [Chapter Import] Failed to click Import CSV button: {_click_import_err}"
                        )

                # SweetAlert "Are you sure? / Yes, do it!" must be confirmed before result toasts
                self._confirm_csv_overwrite_prompt_if_present(page)

                # Wait for the import API call to finish (network idle = server done processing).
                # Gacha Weight import has NO success popup — the page just silently refreshes the
                # table after the server call completes. Waiting for networkidle is the only
                # reliable signal that the import is done; absence of error = PASS.
                print("   ⏳ Waiting for import to complete (network idle)...")
                try:
                    page.wait_for_load_state("networkidle", timeout=60000)
                    print("   ✅ Network idle — import finished.")
                except Exception:
                    print("   ⚠️ Network idle timeout (60s), checking for result anyway...")

                # Check for explicit error/success popup that appeared during the wait
                # (other features DO show a popup; Gacha Weight does not).
                try:
                    popup_data = page.evaluate("window.__popupResult")
                    if popup_data:
                        is_pass, msg = self._resolve_upload_popup_outcome(popup_data)
                        print(f"   🎯 Popup captured after network idle: {'PASS' if is_pass else 'FAIL'} — {msg[:80]}")
                        page.evaluate("window.__popupResult = null")
                        self._ensure_popup_closed(page)
                        return (is_pass, msg, cached_selector)
                except Exception:
                    pass

                # The Offer import shows a spinner FIRST, then the Warning swal2 popup
                # appears only AFTER the spinner clears (client-side JS processes the
                # server response, hides the spinner, THEN renders the Warning popup).
                # Calling wait_for_selector before the spinner clears means the popup
                # isn't in the DOM yet → _confirm finds nothing. Must clear spinner first.
                if hasattr(self, "_wait_for_long_loading"):
                    try:
                        self._wait_for_long_loading(page, timeout_ms=20000)
                    except Exception:
                        pass

                # Use state="attached" (DOM presence) not "visible" — swal2 plays a
                # CSS fade-in animation; "visible" waits for the animation to finish but
                # that takes longer than _confirm's .is_visible() timeout. Use "attached"
                # to detect the popup the moment it's in the DOM, then sleep(0.5) so
                # the animation completes before _confirm checks .is_visible().
                try:
                    page.wait_for_selector(
                        "div.swal2-container .swal2-popup, .modal.show",
                        state="attached",
                        timeout=3000,
                    )
                    time.sleep(0.5)  # let swal2 fade-in animation complete
                except Exception:
                    pass  # no popup → silent import (OK to continue)
                # Now click through any confirmation popups: swal2 "Warning" (live gate /
                # offer override) → blue Continue, then Bootstrap modal "are you sure" → Continue.
                # Each click waits for networkidle internally so the actual import POST is captured.
                self._confirm_csv_overwrite_prompt_if_present(page, max_rounds=5)

                # Re-check for the real result popup now that any Warning confirmation
                # has been cleared (it may only have appeared after clicking Continue).
                try:
                    popup_data = page.evaluate("window.__popupResult")
                    if popup_data:
                        is_pass, msg = self._resolve_upload_popup_outcome(popup_data)
                        print(
                            f"   🎯 Popup captured after Warning confirm: {'PASS' if is_pass else 'FAIL'} — {msg[:80]}"
                        )
                        page.evaluate("window.__popupResult = null")
                        self._ensure_popup_closed(page)
                        return (is_pass, msg, cached_selector)
                except Exception:
                    pass

                # Wait for any post-confirm spinner (Gacha Pool: after dismissing the
                # OK result modal a second table-reload spinner appears; must clear it
                # before the blocking-modal check below or it finds the toast too early).
                if hasattr(self, "_wait_for_long_loading"):
                    try:
                        self._wait_for_long_loading(page, timeout_ms=20000)
                    except Exception:
                        pass

                # Prefer a real BLOCKING modal (.swal2-popup — has a backdrop, needs an
                # explicit click to dismiss) over a passing toast notification. A toast
                # can carry a "success" CSS class for a merely informational/
                # intermediate message without that being the actual final result —
                # only the modal requires (and gets) an explicit OK/Continue click here.
                try:
                    modal_popup = page.locator(".swal2-popup:visible").first
                    if modal_popup.count() > 0 and modal_popup.is_visible(timeout=2000):
                        modal_text = modal_popup.inner_text(timeout=1000).strip()
                        is_success_icon = (
                            modal_popup.locator(".swal2-icon-success").count() > 0
                        )
                        is_error_icon = (
                            modal_popup.locator(".swal2-icon-error").count() > 0
                        )
                        py_type = self._classify_popup_message(modal_text)
                        if is_error_icon:
                            py_type = "FAIL"
                        elif is_success_icon and py_type != "FAIL":
                            py_type = "PASS"
                        confirm_btn = modal_popup.locator(
                            "button.swal2-confirm, button:has-text('OK'), "
                            "button:has-text('Ok'), button:has-text('Continue')"
                        ).first
                        if confirm_btn.count() > 0 and confirm_btn.is_visible():
                            print(
                                f"   🟢 Final result modal detected -> clicking OK/Continue: {modal_text[:80]}"
                            )
                            confirm_btn.click(force=True)
                            time.sleep(0.4)
                            # Dismissing this modal triggers a page reload (table
                            # re-render) — a SECOND spinner appears after the one we
                            # already waited out before this modal showed up. Must wait
                            # it out too, or the caller's next step (save_form) searches
                            # for the Save button while this reload is still in flight
                            # and finds nothing.
                            if hasattr(self, "_wait_for_long_loading"):
                                try:
                                    self._wait_for_long_loading(page, timeout_ms=20000)
                                except Exception:
                                    pass
                        if py_type:
                            self._ensure_popup_closed(page)
                            return (
                                py_type == "PASS",
                                modal_text[:100],
                                cached_selector,
                            )
                except Exception:
                    pass

                # No blocking modal found either → fall back to the broader scan
                # (covers toast-only success, e.g. Gacha Weight which shows no popup
                # at all and silently refreshes the table).
                try:
                    found, res_type, res_text = self._scan_for_result_popup(page)
                    if found:
                        print(
                            f"   🎯 Result popup found: {res_type} — {str(res_text)[:80]}"
                        )
                        self._ensure_popup_closed(page)
                        return (
                            (res_type == "PASS"),
                            str(res_text or "")[:100],
                            cached_selector,
                        )
                except Exception:
                    pass

                print("   ✅ Import completed — no error detected (silent-success).")
                self._ensure_popup_closed(page)
                return (True, "Import completed successfully", cached_selector)

                # CRITICAL: Check for popup IMMEDIATELY after file upload (legacy path,
                # only reached if the networkidle+confirm block above throws an uncaught error)
                print("   🔍 Checking popup after file upload...")
                start_check = time.time()

                # IMMEDIATE SYNCHRONOUS CHECK - Read DOM directly (catches already-hidden modals)
                try:
                    immediate_result = page.evaluate("""
                        () => {
                            // Force capture again (in case modal appeared and closed during upload)
                            // [FIX] Use success-first classification, same as main captureModalContent
                            const SUCCESS_KW = ['success', 'successfully', 'hoàn thành', 'imported', 'thành công'];
                            function classify(text) {
                                const lower = text.toLowerCase();
                                if (SUCCESS_KW.some(k => lower.includes(k))) return 'PASS';
                                if (/\\bfail(ed|ure)?\\b/.test(lower)) return 'FAIL';
                                if (['error','invalid','lỗi','duplicate','missing'].some(k => lower.includes(k))) return 'FAIL';
                                return null;
                            }
                            const modals = document.querySelectorAll('.modal');
                            for (const modal of modals) {
                                if (!modal.classList.contains('show') && modal.offsetParent === null) continue;
                                const body = modal.querySelector('.modal-body');
                                if (body && body.innerText && body.innerText.trim()) {
                                    const text = body.innerText.trim();
                                    const type = classify(text);
                                    if (!type) continue;
                                    return { type: type, text: text };
                                }
                            }
                            // Check if already captured by observer
                            return window.__popupResult;
                        }
                    """)

                    if immediate_result:
                        is_pass, msg = self._resolve_upload_popup_outcome(
                            immediate_result
                        )
                        print(
                            f"   🎯 IMMEDIATE capture at {int((time.time()-start_check)*1000)}ms: {'PASS' if is_pass else 'FAIL'}"
                        )
                        page.evaluate("window.__popupResult = null")
                        self._ensure_popup_closed(page)
                        return (is_pass, msg, cached_selector)
                except Exception as e:
                    print(f"   🔍 Immediate check failed: {e}")

                # Polling check (in case popup appears later)
                for i in range(15):  # Check 15 times × 50ms = 750ms
                    popup_data = page.evaluate("window.__popupResult")
                    if popup_data:
                        is_pass, msg = self._resolve_upload_popup_outcome(popup_data)
                        print(
                            f"   🎯 JS caught popup at {int((time.time()-start_check)*1000)}ms: {'PASS' if is_pass else 'FAIL'}"
                        )
                        page.evaluate("window.__popupResult = null")
                        self._ensure_popup_closed(page)
                        return (is_pass, msg, cached_selector)
                    time.sleep(0.05)  # 50ms intervals for faster detection

            except Exception as upload_err:
                self._ensure_popup_closed(page)
                return False, f"Upload failed: {upload_err}", cached_selector

            # 3. Confirm button - popup will be captured by JS listener (already injected)
            # IMPORTANT: scope confirm buttons to an actual dialog (.modal / .swal2).
            # A bare "button:has-text('Import')" also matches the PAGE-LEVEL "Import CSV"
            # trigger button; clicking it re-opens the OS file chooser → the native dialog
            # blocks execution and must be closed manually (gacha pool bug).
            confirm_clicked = False
            # Defensive: if any click below still re-triggers the file input, swallow the
            # chooser so the native OS dialog can never block the run.
            def _swallow_file_chooser(fc):
                try:
                    fc.set_files([])
                except Exception:
                    pass

            page.on("filechooser", _swallow_file_chooser)
            try:
                time.sleep(0.2)
                for selector in [
                    ".swal2-confirm:visible",
                    ".modal.show button:has-text('Import'):visible",
                    ".modal.in button:has-text('Import'):visible",
                    ".modal.show button:has-text('Confirm'):visible",
                    ".modal.in button:has-text('Confirm'):visible",
                    ".swal2-popup button:has-text('Confirm'):visible",
                ]:
                    try:
                        confirm_btn = page.locator(selector).first
                        if confirm_btn.is_visible(timeout=300):
                            confirm_btn.click()
                            confirm_clicked = True

                            # CRITICAL: Check IMMEDIATELY after click - FASTER (20ms intervals)
                            for i in range(100):  # Ch# Reset for next case
                                page.evaluate("window.__popupResult = null")
                                # Check for 2s total (100 × 0.02s = 2s)
                                popup_data = page.evaluate("window.__popupResult")
                                if popup_data:
                                    is_pass, msg = self._resolve_upload_popup_outcome(
                                        popup_data
                                    )
                                    print(
                                        f"   🎯 JS captured popup at {i*20}ms: {'PASS' if is_pass else 'FAIL'}"
                                    )
                                    self._ensure_popup_closed(page)
                                    return (is_pass, msg, cached_selector)
                                time.sleep(0.02)  # 20ms intervals = 50 checks/second!

                            # If JS failed, try direct Python check as fallback
                            print("   ⚠️ JS capture timeout, trying Python fallback...")

                            # NEW: Use evaluate to read DOM directly (can read hidden elements)
                            try:
                                fallback_result = page.evaluate("""
                                    () => {
                                        const modals = document.querySelectorAll('.modal');
                                        const results = [];
                                        
                                        for (const modal of modals) {
                                            const body = modal.querySelector('.modal-body');
                                            // Read innerText even if display:none
                                            if (body && body.innerText && body.innerText.trim()) {
                                                const text = body.innerText.trim();
                                                const isVisible = body.offsetParent !== null;
                                                results.push({
                                                    text: text,
                                                    isVisible: isVisible
                                                });
                                            }
                                        }
                                        
                                        // Also check history
                                        if (window.__popupHistory && window.__popupHistory.length > 0) {
                                            const lastPopup = window.__popupHistory[window.__popupHistory.length - 1];
                                            return lastPopup;
                                        }
                                        
                                        return results.length > 0 ? results[0] : null;
                                    }
                                """)

                                if fallback_result:
                                    is_pass, msg = self._resolve_upload_popup_outcome(
                                        fallback_result
                                    )
                                    if msg:
                                        print(
                                            f"   🔍 Python fallback (DOM read): {msg[:80]}..."
                                        )
                                        print(
                                            f"   🎯 Classified: {'PASS' if is_pass else 'FAIL'}"
                                        )
                                        self._ensure_popup_closed(page)
                                        return (is_pass, msg, cached_selector)
                            except Exception as e:
                                print(f"   🔍 DEBUG: Direct DOM read failed: {e}")

                            # Last resort: Try Playwright locator API
                            try:
                                modals = page.locator(".modal .modal-body").all()
                                print(
                                    f"   🔍 DEBUG: Found {len(modals)} modal-body elements (Playwright)"
                                )
                                for idx, modal in enumerate(modals):
                                    try:
                                        # Try to read text even if not visible
                                        text = modal.inner_text(timeout=500).strip()
                                        if text:
                                            is_pass, msg = (
                                                self._resolve_upload_popup_outcome(
                                                    {"type": None, "text": text}
                                                )
                                            )
                                            py_type = self._classify_popup_message(text)
                                            if py_type:
                                                is_pass = py_type == "PASS"

                                            print(
                                                f"   🔍 DEBUG: Modal {idx+1} text: {text[:80]}..."
                                            )
                                            print(
                                                f"   🎯 Playwright classified: {'PASS' if is_pass else 'FAIL'}"
                                            )
                                            self._ensure_popup_closed(page)
                                            return (
                                                is_pass,
                                                msg or text[:100],
                                                cached_selector,
                                            )
                                    except Exception as e:
                                        print(
                                            f"   🔍 DEBUG: Modal {idx+1} read error: {e}"
                                        )
                                        continue
                            except Exception as e:
                                print(f"   🔍 DEBUG: Python fallback failed: {e}")
                            break
                    except:
                        continue
            except:
                pass
            finally:
                try:
                    page.remove_listener("filechooser", _swallow_file_chooser)
                except Exception:
                    pass

            # 4. Polling Result — 60s timeout.
            # Fast path: poll window.__popupResult every 200ms (re-injected observer above has 60s TTL).
            # Slow path: fall back to _scan_for_result_popup only when the fast poll misses.
            start_time = time.time()
            seen_loading = False
            _slow_scan_interval = 5.0  # run _scan_for_result_popup at most every 5s
            _last_slow_scan = 0.0

            while time.time() - start_time < 60:
                # Fast: check JS-observer result first (no selector wait → no 4s penalty)
                try:
                    popup_data = page.evaluate("window.__popupResult")
                    if popup_data:
                        is_pass, msg = self._resolve_upload_popup_outcome(popup_data)
                        elapsed = int((time.time() - start_time) * 1000)
                        print(f"   🎯 Observer captured result at {elapsed}ms: {'PASS' if is_pass else 'FAIL'}")
                        page.evaluate("window.__popupResult = null")
                        self._ensure_popup_closed(page)
                        return (is_pass, msg, cached_selector)
                except Exception:
                    pass

                # Slow: run _scan_for_result_popup (4s cost) at most every 5s
                now = time.time()
                if now - _last_slow_scan >= _slow_scan_interval:
                    _last_slow_scan = now
                    res_found, res_type, res_text = self._scan_for_result_popup(page)
                    if res_found:
                        self._ensure_popup_closed(page)
                        return (
                            (res_type == "PASS"),
                            str(res_text or "")[:100],
                            cached_selector,
                        )

                time.sleep(0.2)

            self._ensure_popup_closed(page)
            return False, "Timeout (60s)", cached_selector

        except Exception as e:
            self._ensure_popup_closed(page)
            return False, str(e), cached_selector

    def _confirm_csv_overwrite_prompt_if_present(self, page, max_rounds=6):
        """
        Click through ALL pre/mid-import confirmation popups until none remain or a
        result popup (success/error text) appears. Handles:
          - swal2 "Are you sure?" / "Warning" (live gate, offer override) → any blue/green btn
          - Bootstrap modal "These offers are in a Live gate, are you sure to continue?" → Continue
        After each click, waits for networkidle in case the click triggers the actual import.
        """
        _RESULT_KW = [
            "success", "successfully", "hoàn thành", "imported", "thành công",
            "error", "fail", "invalid", "duplicate", "missing", "required", "lỗi",
        ]
        # The Offer import shows a spinner FIRST; the Warning popup(s) only render
        # AFTER it clears, so each round must (a) wait the spinner out, then (b) wait
        # for a confirmation button to appear — instead of breaking the instant
        # nothing is visible yet (the old bug: the Warning popups showed up a beat
        # later and were never clicked, so the run jumped straight to the next step).
        _CONFIRM_BTN_SEL = (
            "div.swal2-container button.swal2-confirm, "
            "div.swal2-container button:has-text('Continue'), "
            "div.swal2-container button:has-text('Yes'), "
            ".modal.show button:has-text('Continue'), "
            ".modal.in button:has-text('Continue'), "
            ".modal.show button:has-text('Yes'), "
            ".modal.in button:has-text('Yes'), "
            ".modal.show button:has-text('Proceed'), "
            ".modal.in button:has-text('Proceed')"
        )
        for _round in range(max_rounds):
            found = False

            # Clear the import spinner, then actively wait for a confirmation popup to
            # appear (it renders only once the spinner is gone). Break only when none
            # shows up within the window — not on the first empty check.
            if hasattr(self, "_wait_for_long_loading"):
                try:
                    self._wait_for_long_loading(page, timeout_ms=20000)
                except Exception:
                    pass
            try:
                page.wait_for_selector(
                    _CONFIRM_BTN_SEL, state="visible", timeout=2500
                )
            except Exception:
                break  # no (more) confirmation popups appeared

            # 1. swal2 container (any visible, with a Continue/Yes/confirm button)
            try:
                container = (
                    page.locator("div.swal2-container")
                    .filter(
                        has=page.locator(
                            "button.swal2-confirm, button:has-text('Continue'), button:has-text('Yes')"
                        )
                    )
                    .first
                )
                if container.count() > 0 and container.is_visible(timeout=350):
                    text = (container.inner_text(timeout=1000) or "").lower()
                    if any(k in text for k in _RESULT_KW):
                        break  # actual result popup — stop, let result-check handle it
                    btn = container.locator(
                        "button.swal2-confirm, button:has-text('Continue'), "
                        "button:has-text('Yes'), button:has-text('do it')"
                    ).first
                    if btn.count() > 0 and btn.is_visible(timeout=300):
                        try:
                            btn_label = btn.inner_text(timeout=300).strip()
                        except Exception:
                            btn_label = "?"
                        print(
                            f"   ✅ Import confirmation ({_round+1}) swal2 → clicking '{btn_label}'..."
                        )
                        btn.click(timeout=8000)
                        try:
                            page.evaluate(
                                "window.__popupResult = null; window.__popupHistory = [];"
                            )
                        except Exception:
                            pass
                        time.sleep(0.4)
                        try:
                            page.wait_for_load_state("networkidle", timeout=20000)
                        except Exception:
                            pass
                        found = True
                        continue
            except Exception:
                pass

            # 2. Bootstrap modal with Continue/Yes button (e.g. "live gate" second confirmation)
            try:
                modal = (
                    page.locator(".modal.show, .modal.in")
                    .filter(
                        has=page.locator(
                            "button:has-text('Continue'), button:has-text('Yes'), button:has-text('Proceed')"
                        )
                    )
                    .first
                )
                if modal.count() > 0 and modal.is_visible(timeout=300):
                    text = (modal.inner_text(timeout=1000) or "").lower()
                    if any(k in text for k in _RESULT_KW):
                        break  # actual result modal — stop
                    btn = modal.locator(
                        "button:has-text('Continue'), button:has-text('Yes'), button:has-text('Proceed')"
                    ).first
                    if btn.count() > 0 and btn.is_visible(timeout=300):
                        try:
                            btn_label = btn.inner_text(timeout=300).strip()
                        except Exception:
                            btn_label = "?"
                        print(
                            f"   ✅ Import confirmation ({_round+1}) modal → clicking '{btn_label}'..."
                        )
                        btn.click(force=True)
                        time.sleep(0.4)
                        try:
                            page.wait_for_load_state("networkidle", timeout=20000)
                        except Exception:
                            pass
                        found = True
                        continue
            except Exception:
                pass

            if not found:
                break

    def _upload_single_attempt(self, page, target_text, file_name):
        """Original upload for non-fuzz operations (keeps longer timeouts)"""
        success, msg, _ = self._upload_fuzz_fast(page, target_text, file_name, None)
        return success, msg

    def handle_upload(self, page, target_btn_name, file_name):
        logs = []
        try:
            real_file_name = file_name
            if not real_file_name or real_file_name.lower().strip() == "file.csv":
                real_file_name = self.memory.get("LAST_FUZZED_FILE", file_name)

            if not str(real_file_name or "").strip():
                return [{"step": "Upload", "status": "FAIL", "details": "Upload filename is empty — check the action plan (upload.value)"}]

            file_path = os.path.join(DOWNLOAD_DIR, real_file_name)
            if not os.path.exists(file_path):
                return [
                    {
                        "step": "Upload",
                        "status": "FAIL",
                        "details": f"File not found: {real_file_name}",
                    }
                ]

            print(f"   📤 Uploading: {real_file_name}")
            self._ensure_popup_closed(page)

            # [FIX] Clear any stale JS popup result left over from a previous upload.
            # Without this, _upload_fuzz_fast reads the old result at ~232ms and reports
            # the PREVIOUS upload's outcome instead of the current one.
            try:
                page.evaluate(
                    "window.__popupResult = null; window.__popupHistory = [];"
                )
            except:
                pass

            # [FIX] Dùng _upload_single_attempt (đội JS popup capture mạnh hơn _perform_upload_action)
            max_fix_retries = 2
            success, msg = False, "Not started"
            for fix_attempt in range(max_fix_retries + 1):
                success, msg = self._upload_single_attempt(
                    page, target_btn_name or "Import CSV", real_file_name
                )

                # Safety net: message says success but classifier returned fail
                if not success and self._classify_popup_message(msg) == "PASS":
                    print(f"      🔧 Upload corrected to PASS from message: {msg[:80]}")
                    success = True

                if success:
                    print(f"      ✅ Upload succeeded on attempt {fix_attempt + 1}")
                    break

                # Upload thất bại - in rõ lỗi
                print(f"      ❌ Upload failed (attempt {fix_attempt + 1}): {msg}")

                if fix_attempt >= max_fix_retries:
                    break

                # [AUTO-FIX] Thử sửa CSV nếu lỗi duplicate
                msg_lower = (msg or "").lower()
                if any(
                    k in msg_lower
                    for k in ["duplicate", "already exist", "exists", "unique"]
                ):
                    print(f"      🔧 Duplicate error detected, trying auto-fix...")
                    fixed = self._fix_duplicate_csv(file_path, msg)
                    if fixed:
                        print(f"      🔄 CSV fixed, retrying upload...")
                        self._ensure_popup_closed(page)
                        continue
                    else:
                        print(f"      ⚠️ Auto-fix failed, cannot retry")
                        break
                else:
                    # Lỗi không phải duplicate → không fix được, dừng
                    print(f"      ℹ️ Non-fixable error, stopping retries")
                    break

            status = "PASS" if success else "FAIL"
            detail = "Upload successfully" if success else f"Upload failed: {msg}"
            self._ensure_popup_closed(page)
            logs.append({"step": "Upload", "status": status, "details": detail})
        except Exception as e:
            logs.append({"step": "Upload", "status": "CRASH", "details": str(e)})
            self._ensure_popup_closed(page)
        return logs

    def _find_upload_trigger(self, page, name):
        # (Giữ nguyên)
        try:
            if page.get_by_role(
                "button", name=self._safe_compile(name)
            ).first.is_visible():
                return page.get_by_role("button", name=self._safe_compile(name)).first
        except:
            pass
        for k in ["Import", "Upload"]:
            try:
                b = page.get_by_role("button", name=re.compile(k, re.IGNORECASE)).first
                if b.is_visible() and "export" not in b.inner_text().lower():
                    return b
            except:
                pass
        return page.locator(
            "button:has(i[class*='import']), button:has(i[class*='upload'])"
        ).first

    def _upload_fast(self, page, target_text, file_name):
        """
        Upload thông minh với Log thời gian thực.
        """
        full_path = os.path.join(DOWNLOAD_DIR, file_name)
        try:
            # 1. Tìm & Chọn File
            print(f"         📤 Selecting file: {file_name}...")  # LOG NGAY
            btn = page.locator(
                f"button:has-text('{target_text}'), a.btn:has-text('{target_text}'), input[type='file']"
            ).first
            if not btn.is_visible():
                return False, "Button not found"

            if btn.get_attribute("type") == "file":
                btn.set_input_files(full_path)
            else:
                with page.expect_file_chooser(timeout=3000) as fc_info:
                    btn.click()
                fc_info.value.set_files(full_path)

            # 2. Confirm Upload (Xử lý Popup Confirm)
            # LOG TRƯỚC KHI CLICK để biết AI đang làm gì
            print("         👆 Checking for Confirm popup...")
            try:
                confirm = page.locator(
                    ".swal2-confirm, button.btn-primary:has-text('Upload')"
                ).first
                if confirm.is_visible(timeout=2000):
                    print("         🖱 Clicking Confirm Upload...")
                    # force=True để click bất chấp overlay
                    confirm.click(force=True)
            except:
                pass

            # 3. POLLING LOOP (Tối đa 90s)
            # Log này sẽ hiện ngay sau khi click confirm
            print("         👀 Watching for result (Loading/Success/Fail)...")

            start_time = time.time()
            seen_loading = False

            while time.time() - start_time < 90:
                # A. ƯU TIÊN 1: Check Kết Quả (Success/Fail) trước
                # Để bắt dính ngay khi popup vừa hiện
                res_found, res_type, res_text = self._check_result_text(page)

                if res_found:
                    print(f"         📢 Found Result: {res_type}")
                    self._ensure_popup_closed(page)
                    return (res_type == "PASS"), res_text

                # B. ƯU TIÊN 2: Check Loading
                loading = page.locator(
                    ".swal2-loading, .spinner, .loading-mask, div:has-text('Importing'), div:has-text('Uploading')"
                ).first
                is_loading_visible = loading.is_visible()

                if is_loading_visible:
                    if not seen_loading:
                        print("         ⏳ System is Importing (Loading detected)...")
                        seen_loading = True
                    time.sleep(0.5)
                    continue

                # C. Logic thoát nhanh:
                # Nếu đã từng Loading, mà giờ hết Loading, và cũng không tìm thấy popup kết quả
                if seen_loading and not is_loading_visible:
                    print(
                        "         🏁 Loading finished. Checking result one last time..."
                    )
                    # Đợi thêm 1s để chắc chắn popup render
                    time.sleep(1.0)
                    res_found, res_type, res_text = self._check_result_text(page)
                    if res_found:
                        self._ensure_popup_closed(page)
                        return (res_type == "PASS"), res_text

                    # Nếu vẫn không thấy popup -> Có thể đã bị tắt hoặc web lỗi
                    return False, "Process finished but No Popup found"

                time.sleep(0.5)

            return False, "Timeout (90s)"

        except Exception as e:
            return False, str(e)


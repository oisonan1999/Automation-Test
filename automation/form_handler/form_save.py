# automation/form_handler/form_save.py - split from form_handler.py
# Save form, capture response, error popup + confirm dismissal
import time
import re
import random
from playwright.sync_api import Page


class FormSaveMixin:
    """Save form, capture response, error popup + confirm dismissal"""

    def _save_form(self, page, mode="save"):
        """
        Hợp nhất:
        1. Ưu tiên tìm nút theo context (Clone, Create, Save...)
        2. Fallback về logic tìm text linh hoạt.
        3. Hỗ trợ scope Modal.
        """

        def handle_dialog(dialog):
            try:
                print(f"      🚨 Browser Alert detected: {dialog.message}")
            except Exception:
                pass

            # Playwright crash fix:
            # Sometimes dialog events fire after the page is no longer attached/active,
            # which causes: ProtocolError: Page.handleJavaScriptDialog: Not attached to an active page
            # -> swallow the error and continue automation.
            try:
                dialog.accept()  # Bấm OK để tắt alert đi
            except Exception as e:
                print(f"      ⚠️ Dialog accept skipped (likely page detached): {e}")
                try:
                    dialog.dismiss()
                except Exception:
                    pass

        # Xóa listener cũ (nếu có) để tránh duplicate
        try:
            page.remove_listener("dialog", handle_dialog)
        except:
            pass

        page.on("dialog", handle_dialog)

        print(f"   💾 Action: Save/Submit (Mode: {mode})...")

        try:
            # 1. Xác định phạm vi (Scope) - Ưu tiên Modal nếu đang mở
            # Bootstrap 4/5 uses .modal.show; Bootstrap 2 uses .modal.in
            scope = page
            for modal_sel in [
                ".modal.show",
                ".modal.in",
                ".modal[aria-hidden='false']",
            ]:
                candidate = page.locator(modal_sel)
                if candidate.count() > 0 and candidate.last.is_visible():
                    scope = candidate.last
                    print(f"      📍 Scope: Modal detected ({modal_sel})")
                    break

            target_btn = None

            # Detect PVE Match 1 context (multiselect input exists only there)
            # Fight Card V3's PVE tab reuses the same PVE-v2 Book Info + Chapter
            # panel layout (own "Save Book Info" up top, own "Save"/"Save & Continue"
            # bar at the bottom of the Chapter panel — that's where Contest Superstar
            # lives), but has no #searchSSGroupId since there's no Match/SSDB search
            # box here. Without this, mode="save" falls into the non-PVE branch which
            # prioritizes "Save Book Info" — wrong button, doesn't persist the CS panel.
            is_pve_match_page = (
                page.locator("#searchSSGroupId").count() > 0
                or page.locator(
                    "input[name='fight-card-contest-superstar-toggle']"
                ).count() > 0
            )

            # =========================================================
            # CHIẾN THUẬT 1: TÌM NÚT THEO THỨ TỰ ƯU TIÊN CAO
            # Hỗ trợ mode="save" / mode="clone" / mode="continue"
            # =========================================================
            if mode == "clone":
                # Mode "clone": Bấm nút Clone trong modal (ưu tiên tuyệt đối)
                priority_buttons = [
                    "Create book and Open in V2",  # PVE clone submit button
                    "Save Changes",  # Affiliation War Contribution clone form (full page, not modal)
                    "Clone",
                    "Submit",
                    "Confirm",
                    "OK",
                ]
            elif mode == "save":
                # Mode "save":
                # - On PVE we MUST prefer the green Match Save button (text "Save"),
                #   not the generic "Save Book Info" button elsewhere.
                if is_pve_match_page:
                    priority_buttons = [
                        "Save",  # prefer Match Save (green button)
                        "Save Book Info",
                        "Save Book",
                        "Save Book Information",
                        "Update",
                        "Submit",
                        "Confirm",
                        "OK",
                    ]
                else:
                    # Default non-PVE: keep original safety (prefer Save Book Info)
                    priority_buttons = [
                        "Save Book Info",
                        "Save Book",
                        "Save Book Information",
                        "Save Changes",  # Affiliation War Contribution (custom UI, not Bootstrap)
                        "Save",  # fallback generic (exact match)
                        "Update",
                        "Submit",
                        "Confirm",
                        "OK",
                    ]
            else:
                # Mode "continue" (default): Ưu tiên Save & Continue
                priority_buttons = [
                    "Save & Continue",
                    "Save and Continue",
                    "Continue",
                    "Save Changes",  # Affiliation War Contribution (custom UI, not Bootstrap)
                    "Save",
                    "Update",
                    "Clone",
                    "Create",
                    "Submit",
                    "Confirm",
                    "OK",
                    "Yes",
                ]

            for btn_text in priority_buttons:
                if mode == "save" and btn_text.lower() == "save":
                    # EXACT MATCH generic "Save" nhưng KHÔNG match "Save & Continue"
                    # CRITICAL PERF: do NOT call .all() on every button/a.btn/input on
                    # the page and check .is_visible() one by one — on heavy pages
                    # (Gacha Pool table with many rows) that's 2000+ elements, each
                    # .is_visible() a separate CDP round-trip => 3+ MINUTES, which
                    # looks exactly like the automation being "stuck" at the Save
                    # step. Pre-filter to elements whose text contains "save" first
                    # (one batched Playwright query) — narrows ~2500 candidates down
                    # to a handful (~8) before the Python-side visibility/exact-match
                    # loop, in ~1-2s instead of minutes.
                    save_like_btns = (
                        scope.locator("button, a.btn, input[type='submit']")
                        .filter(has_text=re.compile(r"save", re.IGNORECASE))
                        .all()
                    )
                    for candidate_btn in save_like_btns:
                        if candidate_btn.is_visible():
                            try:
                                txt = candidate_btn.inner_text().strip()
                                # Remove icons/emojis, check if remaining text is just "Save"
                                txt_clean = re.sub(r"[^\w\s&]", "", txt).strip()
                                if (
                                    re.match(r"^save$", txt_clean, re.IGNORECASE)
                                    and "continue" not in txt.lower()
                                ):
                                    target_btn = candidate_btn
                                    print(
                                        f"      🎯 Found exact 'Save' button (mode=save fallback)"
                                    )
                                    break
                            except:
                                pass
                    if target_btn:
                        break
                else:
                    # Prefer exact/contains match for the contextual button text
                    btn = (
                        scope.locator("button, a.btn, input[type='submit']")
                        .filter(
                            has_text=re.compile(
                                rf"\\b{re.escape(btn_text)}\\b|^{re.escape(btn_text)}$|{re.escape(btn_text)}",
                                re.IGNORECASE,
                            )
                        )
                        .last
                    )
                    if btn.count() > 0 and btn.is_visible():
                        try:
                            found_txt = btn.inner_text().strip()
                        except:
                            found_txt = btn_text
                        print(
                            f"      🎯 Found button for mode=save: '{found_txt}' (wanted '{btn_text}')"
                        )
                        target_btn = btn
                        break

            # =========================================================
            # CHIẾN THUẬT 2: TÌM THEO CLASS
            # =========================================================
            if not target_btn or not target_btn.is_visible():
                class_selectors = [
                    "button.btn-primary",
                    "button.btn-success",
                    "button.btn-info",
                    "button.awc-btn--primary",  # Affiliation War Contribution custom UI
                    "input[type='submit']",
                ]
                for sel in class_selectors:
                    btn = scope.locator(sel).last
                    if btn.count() > 0 and btn.is_visible():
                        target_btn = btn
                        print(f"      ⚠️ Fallback class match: {sel}")
                        break

            # =========================================================
            # THỰC HIỆN CLICK (với Network Response Interception)
            # =========================================================
            if target_btn and target_btn.is_visible():
                # PVE: choose the correct green "Save" button (bottom save bar),
                # not the nearby "Save" next to the SSDB/multiselect dropdown.
                # Also: per your request, no extra ~30s wait here (wait only during SSGroup ID fill).
                if is_pve_match_page:
                    try:
                        save_candidates = (
                            scope.locator("button, a.btn, input[type='submit']")
                            .filter(has_text=re.compile(r"^\s*Save\s*$", re.IGNORECASE))
                            .all()
                        )

                        best = None
                        best_score = (-1, -1)  # (green_flag, y)
                        for cand in save_candidates:
                            try:
                                if not cand.is_visible():
                                    continue
                                box = cand.bounding_box()
                                y = box["y"] if box and "y" in box else -1
                                cls = ""
                                try:
                                    cls = (cand.get_attribute("class") or "").lower()
                                except:
                                    cls = ""

                                # Prefer green buttons (btn-success). If class isn't present,
                                # still fall back to bottom-most (max y).
                                green_flag = (
                                    1
                                    if "btn-success" in cls or "btn-green" in cls
                                    else 0
                                )
                                score = (green_flag, y)
                                if score > best_score:
                                    best_score = score
                                    best = cand
                            except:
                                continue

                        if best is not None:
                            target_btn = best
                            print(
                                f"      🎯 PVE Save button chosen at bottom (score={best_score})"
                            )
                    except Exception as _pve_save_pick_err:
                        print(
                            f"      ⚠️ PVE Save button picking failed: {_pve_save_pick_err}"
                        )

                target_btn.scroll_into_view_if_needed()
                time.sleep(0.5)

                # --- JAVASCRIPT-LEVEL NETWORK INTERCEPTION ---
                # Playwright response events don't work over CDP (connect_over_cdp).
                # Instead, inject JS to monkey-patch XMLHttpRequest & fetch
                # to capture POST/PUT/PATCH responses directly in the browser.
                try:
                    page.evaluate("""() => {
                        window.__save_network_errors = [];
                        window.__save_network_all = [];

                        // --- Intercept XMLHttpRequest (jQuery $.ajax uses this) ---
                        const origXHROpen = XMLHttpRequest.prototype.open;
                        const origXHRSend = XMLHttpRequest.prototype.send;

                        XMLHttpRequest.prototype.open = function(method, url) {
                            this.__method = method;
                            this.__url = url;
                            return origXHROpen.apply(this, arguments);
                        };

                        XMLHttpRequest.prototype.send = function() {
                            const xhr = this;
                            const origOnReady = xhr.onreadystatechange;
                            xhr.onreadystatechange = function() {
                                if (xhr.readyState === 4) {
                                    const method = (xhr.__method || '').toUpperCase();
                                    if (['POST', 'PUT', 'PATCH'].includes(method)) {
                                        const info = {
                                            method: method,
                                            url: xhr.__url,
                                            status: xhr.status,
                                            statusText: xhr.statusText,
                                            body: null
                                        };
                                        if (xhr.status >= 400) {
                                            try { info.body = xhr.responseText.substring(0, 2000); } catch(e) {}
                                        }
                                        window.__save_network_all.push(info);
                                        if (xhr.status >= 400) {
                                            window.__save_network_errors.push(info);
                                        }
                                    }
                                }
                                if (origOnReady) origOnReady.apply(this, arguments);
                            };
                            // Also handle addEventListener('load') pattern
                            xhr.addEventListener('load', function() {
                                const method = (xhr.__method || '').toUpperCase();
                                if (['POST', 'PUT', 'PATCH'].includes(method) && xhr.status >= 400) {
                                    const existing = window.__save_network_errors.find(e => e.url === xhr.__url && e.status === xhr.status);
                                    if (!existing) {
                                        window.__save_network_errors.push({
                                            method: method,
                                            url: xhr.__url,
                                            status: xhr.status,
                                            statusText: xhr.statusText,
                                            body: xhr.responseText ? xhr.responseText.substring(0, 2000) : null
                                        });
                                    }
                                }
                            });
                            return origXHRSend.apply(this, arguments);
                        };

                        // --- Intercept fetch() API ---
                        const origFetch = window.fetch;
                        window.fetch = function(input, init) {
                            const method = ((init && init.method) || 'GET').toUpperCase();
                            const url = (typeof input === 'string') ? input : input.url;
                            return origFetch.apply(this, arguments).then(response => {
                                if (['POST', 'PUT', 'PATCH'].includes(method)) {
                                    const info = {
                                        method: method,
                                        url: url,
                                        status: response.status,
                                        statusText: response.statusText,
                                        body: null
                                    };
                                    window.__save_network_all.push(info);
                                    if (response.status >= 400) {
                                        response.clone().text().then(t => {
                                            info.body = t.substring(0, 2000);
                                        }).catch(() => {});
                                        window.__save_network_errors.push(info);
                                    }
                                }
                                return response;
                            });
                        };
                    }""")
                    print("      🔌 Network interceptor injected (JS-level)")
                except Exception as inject_err:
                    print(
                        f"      ⚠️ Failed to inject network interceptor: {inject_err}"
                    )

                target_btn.click(force=True)
                print("      ✅ Clicked successfully.")

                # Chờ network settle; clone mode causes full-page navigation so give more time
                _idle_timeout = 45000 if mode == "clone" else 15000
                try:
                    page.wait_for_load_state("networkidle", timeout=_idle_timeout)
                except:
                    pass
                time.sleep(2)

                # For clone mode the page navigates; also wait for any spinners/loaders
                if mode == "clone":
                    try:
                        if hasattr(self, "_wait_for_long_loading"):
                            self._wait_for_long_loading(page)
                    except Exception:
                        pass

                # --- READ CAPTURED NETWORK ERRORS ---
                network_error = None
                try:
                    all_responses = page.evaluate(
                        "() => window.__save_network_all || []"
                    )
                    errors = page.evaluate("() => window.__save_network_errors || []")
                    print(
                        f"      📊 Captured responses: {len(all_responses)} total, {len(errors)} errors"
                    )

                    for resp in all_responses:
                        print(
                            f"      📡 {resp.get('method')} {resp.get('status')} {str(resp.get('url',''))[:100]}"
                        )

                    if errors:
                        err = errors[0]
                        error_detail = f"HTTP {err.get('status')} {err.get('statusText','')} - {err.get('method','')} {err.get('url','')}"
                        if err.get("body"):
                            body_text = re.sub(
                                r"<[^>]+>", " ", err["body"][:1000]
                            ).strip()
                            body_text = re.sub(r"\s+", " ", body_text)[:500]
                            error_detail += f" | Response: {body_text}"
                        print(f"      🌐 Network Error: {error_detail[:500]}")
                        network_error = error_detail
                except Exception as read_err:
                    print(f"      ⚠️ Could not read network capture: {read_err}")

                # Cleanup interceptor
                try:
                    page.evaluate("""() => {
                        delete window.__save_network_errors;
                        delete window.__save_network_all;
                    }""")
                except:
                    pass

                # Gọi hàm wait và detect error popup
                save_result = None
                if hasattr(self, "_wait_after_save"):
                    save_result = self._wait_after_save(
                        page, network_error=network_error
                    )
                else:
                    # Logic wait mặc định nếu chưa có hàm riêng
                    if network_error:
                        save_result = {"success": False, "error_message": network_error}
                    else:
                        try:
                            page.wait_for_load_state("networkidle", timeout=3000)
                        except:
                            time.sleep(2)

                # Check if save_result indicates an error
                if save_result and isinstance(save_result, dict):
                    if not save_result.get("success", True):
                        error_msg = save_result.get("error_message", "Unknown error")
                        print(f"      ❌ Save failed with error: {error_msg}")

                        # ========================================
                        # AUTO-FIX: Datetime format errors
                        # e.g. "time data '02/24/2026 00:00 AM' does not match format '%m/%d/%Y %I:%M %p'"
                        # ========================================
                        if (
                            "time data" in error_msg
                            and "does not match format" in error_msg
                        ):
                            print(
                                "      🔧 Attempting to auto-fix datetime format error..."
                            )
                            fixed = self._auto_fix_datetime_on_page(page, error_msg)
                            if fixed:
                                print("      🔄 Retrying save after datetime fix...")
                                time.sleep(1)
                                target_btn.scroll_into_view_if_needed()
                                time.sleep(0.3)
                                target_btn.click(force=True)
                                retry_result = (
                                    self._wait_after_save(page)
                                    if hasattr(self, "_wait_after_save")
                                    else None
                                )
                                if (
                                    retry_result
                                    and isinstance(retry_result, dict)
                                    and not retry_result.get("success", True)
                                ):
                                    return f"Error: {retry_result.get('error_message', 'Retry failed')}"
                                return "Success"

                        return f"Error: {error_msg}"

                return "Success"

            print("      ❌ Không tìm thấy nút Save/Action nào khả thi.")
            return "Fail"

        except Exception as e:
            print(f"      ⚠️ Save Error: {e}")
            return "Error"
        finally:
            # Gỡ listener để không ảnh hưởng các bước sau
            try:
                page.remove_listener("dialog", handle_dialog)
            except:
                pass

    def _wait_after_save(self, page, network_error=None):
        """Hàm phụ: Chờ thông báo thành công hoặc Popup đóng lại.
        Args:
            page: Playwright page object
            network_error: Optional string with HTTP error details from network interception
        Returns:
            dict: {"success": True/False, "error_message": str or None}
        """
        time.sleep(1)

        # ========================================
        # CHECK 0: Network-level HTTP errors (4xx, 5xx)
        # Đây là nguồn thông tin chính xác nhất vì đọc trực tiếp từ API response
        # ========================================
        if network_error:
            print(f"      🌐 Network error from API: {network_error}")
            # Vẫn kiểm tra UI popup để lấy thêm chi tiết nếu có
            ui_error = self._detect_ui_error_popup(page)
            if ui_error:
                combined_msg = f"{network_error} | UI: {ui_error}"
            else:
                combined_msg = network_error
            return {"success": False, "error_message": combined_msg}

        # ========================================
        # CHECK 1: Detect SweetAlert2 error popup (e.g., datetime format error)
        # ========================================
        try:
            # PVE dropdown/load can be slow; give more time for the success/error swal to appear
            swal_popup = page.locator(".swal2-popup")
            swal_popup.wait_for(state="visible", timeout=8000)

            popup_text = ""
            if swal_popup.is_visible():
                popup_text = swal_popup.inner_text().strip()

            if popup_text:
                clean_text = popup_text.replace("\n", " ").strip()[:500]
                print(f"      🚨 Popup detected after save: {clean_text[:200]}")

                # Click OK/Confirm to dismiss the popup
                try:
                    ok_btn = swal_popup.locator(
                        "button.swal2-confirm, button:has-text('OK')"
                    )
                    if ok_btn.count() > 0 and ok_btn.first.is_visible():
                        ok_btn.first.click(force=True)
                        # Wait until popup fully closes so caller doesn't refresh early
                        try:
                            swal_popup.wait_for(state="hidden", timeout=5000)
                        except:
                            time.sleep(0.5)
                except:
                    try:
                        page.evaluate("""
                            const btn = document.querySelector('button.swal2-confirm');
                            if (btn) btn.click();
                        """)
                        time.sleep(0.5)
                    except:
                        pass

                text_lower = popup_text.lower()
                error_keywords = [
                    "error",
                    "failed",
                    "invalid",
                    "duplicate",
                    "missing",
                    "required",
                    "not number",
                    "format",
                    "does not match",
                    "time data",
                    "lỗi",
                    "không hợp lệ",
                ]
                warning_keywords = [
                    "overlapping",
                    "overlap",
                    "already exists",
                    "are you sure",
                    "confirm",
                    "warning",
                    "proceed",
                    "continue",
                ]

                _success_keywords = (
                    "success", "hoàn thành", "good job", "has been saved",
                    "saved successfully", "changes saved", "created successfully",
                    "updated successfully", "deleted successfully",
                )
                if any(k in text_lower for k in error_keywords):
                    print(f"      ❌ Error popup detected: {clean_text[:200]}")
                    return {"success": False, "error_message": clean_text}
                elif any(k in text_lower for k in _success_keywords):
                    print("      ✅ Success popup detected.")
                    return {"success": True, "error_message": None}
                elif any(k in text_lower for k in warning_keywords):
                    print(
                        f"      ⚠️ Warning popup auto-dismissed (OK clicked): {clean_text[:200]}"
                    )
                    return {"success": True, "error_message": None}
                else:
                    print(f"      ⚠️ Unknown popup: {clean_text[:200]}")
                    return {"success": False, "error_message": clean_text}
        except:
            # No SweetAlert2 popup — that's fine, check other indicators
            pass

        # ========================================
        # CHECK 2: Detect Bootstrap alert/toast errors
        # Toastr toast structure: .toast > .toast-close-button + .toast-title + .toast-message
        # Phải target .toast-message cụ thể, không lấy inner_text() cả toast (sẽ bị lẫn "×", "Close")
        # ========================================
        try:
            error_toast = page.locator(".toast-error, .alert-danger, .alert-error")
            if error_toast.count() > 0 and error_toast.first.is_visible():
                # Ưu tiên lấy nội dung từ .toast-message (phần chứa chi tiết lỗi)
                err_text = ""
                try:
                    toast_msg = error_toast.first.locator(".toast-message")
                    if toast_msg.count() > 0:
                        err_text = toast_msg.first.inner_text().strip()[:500]
                except:
                    pass

                # Nếu không có .toast-message, thử lấy từ .toast-title
                if not err_text:
                    try:
                        toast_title = error_toast.first.locator(".toast-title")
                        if toast_title.count() > 0:
                            err_text = toast_title.first.inner_text().strip()[:300]
                    except:
                        pass

                # Fallback: lấy toàn bộ text nhưng loại bỏ "×" và "Close"
                if not err_text:
                    raw_text = error_toast.first.inner_text().strip()
                    err_text = re.sub(r"^[×x✕]\s*", "", raw_text, flags=re.IGNORECASE)
                    err_text = re.sub(
                        r"\bClose\b\s*", "", err_text, flags=re.IGNORECASE
                    ).strip()[:300]

                # Nếu sau khi clean vẫn chỉ còn "error" hoặc chuỗi rỗng → thêm note
                if not err_text or err_text.lower().strip() in ("error", "err", ""):
                    err_text = "Server error (toast had no details). Check Network tab for HTTP response."

                print(f"      ❌ Error toast detected: {err_text}")
                return {"success": False, "error_message": err_text}
        except:
            pass

        # ========================================
        # CHECK 3: Success indicators
        # ========================================
        try:
            # Chờ Toast Message xanh lá hiện lên (đảm bảo popup success đã hiện trước khi refresh)
            page.locator(".toast-success, .alert-success").wait_for(
                state="visible", timeout=8000
            )
            print("      ✅ Thành công (Toast detected).")
            return {"success": True, "error_message": None}
        except:
            pass

        try:
            # Chờ Modal đóng lại (nếu vừa bấm trong modal)
            page.locator(".modal-backdrop").wait_for(state="hidden", timeout=2000)
        except:
            pass

        return {"success": True, "error_message": None}

    def _detect_ui_error_popup(self, page):
        """Kiểm tra nhanh xem có popup lỗi nào đang hiển thị trên UI không.
        Dùng khi đã biết có network error, muốn lấy thêm thông tin từ UI.
        Returns:
            str or None: Nội dung popup lỗi, hoặc None nếu không tìm thấy.
        """
        try:
            # Check SweetAlert2
            swal = page.locator(".swal2-popup")
            if swal.count() > 0 and swal.is_visible():
                text = swal.inner_text().strip()[:500]
                # Dismiss popup
                try:
                    ok_btn = swal.locator("button.swal2-confirm, button:has-text('OK')")
                    if ok_btn.count() > 0 and ok_btn.first.is_visible():
                        ok_btn.first.click(force=True)
                        time.sleep(0.5)
                except:
                    pass
                return text
        except:
            pass

        try:
            # Check Bootstrap toast/alert errors
            error_el = page.locator(".toast-error, .alert-danger, .alert-error")
            if error_el.count() > 0 and error_el.first.is_visible():
                return error_el.first.inner_text().strip()[:300]
        except:
            pass

        try:
            # Check generic error message containers
            error_msg = page.locator(
                ".error-message, .form-error, #error-container, .validation-error"
            )
            if error_msg.count() > 0 and error_msg.first.is_visible():
                return error_msg.first.inner_text().strip()[:300]
        except:
            pass

        return None

    def _dismiss_are_you_sure_confirmations(self, page):
        """
        Auto-dismiss blocking confirmation dialogs like:
          - "Are you sure?"
          - "This event schedule is outside of the RBE's schedule"
        Usually shows OK (blue) / Cancel (grey).
        """
        try:
            import re as _re

            dialog_candidates = page.locator(
                ".modal.show, .modal.in, [role='dialog']:visible, .swal2-popup:visible"
            )

            # Filter to only dialogs containing our keywords
            confirm_re = _re.compile(
                r"(are you sure|outside of the rbe.*schedule|outside.*rbe|wish to proceed|proceed.*anyway)",
                _re.IGNORECASE,
            )

            dismissed_any = False

            # We iterate by index to avoid locator re-evaluation issues after click
            count = dialog_candidates.count()
            for i in range(count):
                try:
                    d = dialog_candidates.nth(i)
                    if not d.is_visible():
                        continue
                    # NOTE: Do NOT auto-dismiss Bootstrap modal "Defining Schedules".
                    # In your case, its Close button is the actual "Save/confirm" for schedules.
                    # Clicking it early prevents filling End Time.
                    d_text = d.inner_text().strip()
                    if not d_text:
                        continue
                    if "defining schedules" in d_text.lower():
                        continue
                    if not confirm_re.search(d_text):
                        continue

                    # Prefer OK / Confirm / Yes. NEVER click "Close" or fallback "primary".
                    ok_btn = d.locator(
                        "button:has-text('OK'), button:has-text('Ok'), button:has-text('Confirm'), "
                        "button:has-text('Yes'), button:has-text('Proceed'), button:has-text('Continue')"
                    ).first

                    if ok_btn.count() > 0 and ok_btn.is_visible():
                        print(
                            f"      ✅ Auto-dismiss confirmation modal (OK): {d_text[:120]}..."
                        )
                        ok_btn.click(force=True)
                        dismissed_any = True
                    else:
                        # If no explicit OK/Confirm-like button exists, do not touch the modal.
                        # (Avoids cases where the only button is "Close" which is a real Save/submit.)
                        continue

                    # Wait briefly for modal to disappear/backdrop to hide
                    try:
                        d.wait_for(state="hidden", timeout=3000)
                    except:
                        pass
                    try:
                        page.locator(".modal-backdrop").first.wait_for(
                            state="hidden", timeout=2000
                        )
                    except:
                        pass

                    # After dismissing one, re-check remaining dialogs quickly
                    time.sleep(0.3)
                except Exception:
                    continue

            return dismissed_any
        except Exception:
            return False

    def close_popup(self, page):
        try:
            self._safe_press_escape(page)
            btn = page.locator("button:has-text('Close')").first
            if btn.is_visible():
                btn.click()
        except:
            pass

    # ============================
    # AUTO-FIX: DATETIME FORMAT ERROR
    # ============================

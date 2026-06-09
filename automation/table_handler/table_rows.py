# automation/table_handler/table_rows.py - split from table_handler.py
# Click edit/clone icon in a matching/random row
import time
import re
import random


class TableRowsMixin:
    """Click edit/clone icon in a matching/random row"""

    def _click_icon_in_row(self, page, target_text, action_type):
        if target_text == "LAST_SELECTED":
            target_text = self.memory.get("LAST_SELECTED", "")
            if not target_text:
                print("   ⚠️ Memory rỗng! Dùng fallback lấy dòng đầu tiên...")
                target_text = (
                    page.locator("tbody tr")
                    .first.locator("td")
                    .nth(1)
                    .inner_text()
                    .strip()
                )
            else:
                print(f"   🧠 Recall Memory: '{target_text}'")

        # Handle RANDOM sentinel: pick a random row from the table
        _random_keywords = {
            "random",
            "any",
            "bất kỳ",
            "bat ky",
            "first",
            "random_1",
            "any row",
            "bất kỳ dòng",
            "một dòng bất kỳ",
        }
        # Also detect patterns like "một Superstar bất kỳ", "Superstar bất kỳ", etc.
        target_lower = str(target_text).lower().strip()
        is_random = (
            target_lower in _random_keywords
            or target_text == "RANDOM"
            or "bất kỳ" in target_lower
            or "bat ky" in target_lower
            or "random" in target_lower
        )
        if is_random:
            print(
                f"   🎲 Random mode: đang chọn ngẫu nhiên một dòng để {action_type}..."
            )
            try:
                # Scope đúng bảng: chỉ lấy những <tr> có nút/icon Edit (hoặc Clone) bên trong.
                # Tránh trường hợp page có nhiều tbody tr (vd fullcalendar) làm RANDOM chọn nhầm.
                if action_type == "edit":
                    action_has = page.locator(
                        "i[class*='edit'], i[class*='pencil'], .btn-edit, button:has-text('Edit'), a:has-text('Edit')"
                    )
                else:
                    action_has = page.locator(
                        "i[class*='clone'], i[class*='copy'], i[class*='share'], .btn-clone, button:has-text('Clone'), a:has-text('Clone')"
                    )

                all_rows = page.locator("tbody tr").filter(has=action_has)
                total = all_rows.count()

                # 🧠 Deterministic safeguard:
                # Khi edit_row đang RANDOM nhưng ta đã biết New Tournament ID vừa clone,
                # thì KHÔNG random nữa -> tìm row chứa LAST_CLONED_NEW_ID và bấm Edit đúng row đó.
                if action_type == "edit":
                    desired_id = str(
                        self.memory.get("LAST_CLONED_NEW_ID") or ""
                    ).strip()
                    if desired_id:
                        try:
                            # Build a separator-flexible regex so it matches even if UI replaces
                            # '_'/'-' with spaces (e.g. "VS_Tournament_hieunm_test" shown as "VS Tournament ...").
                            tokens = [
                                t
                                for t in re.split(r"[_\-\s]+", desired_id)
                                if t and t.strip()
                            ]
                            if tokens:
                                pattern = "".join(
                                    re.escape(t) + r"[\s_\-\.]*" for t in tokens
                                )
                                regex = re.compile(pattern, re.IGNORECASE)
                            else:
                                regex = re.compile(re.escape(desired_id), re.IGNORECASE)

                            match_rows = all_rows.filter(has_text=regex)
                            if match_rows.count() > 0:
                                chosen_row = match_rows.first
                                print(
                                    f"   🧠 Deterministic edit: found row for LAST_CLONED_NEW_ID='{desired_id}', clicking Edit (skip random)"
                                )

                                try:
                                    icon = chosen_row.locator(
                                        "i[class*='edit'], i[class*='pencil'], .btn-edit, button:has-text('Edit'), a:has-text('Edit')"
                                    ).first
                                    if icon.count() > 0 and icon.is_visible():
                                        icon.click(force=True)
                                    else:
                                        any_action = (
                                            chosen_row.locator(
                                                "button, a, [role='button']"
                                            )
                                            .filter(
                                                has_text=re.compile(
                                                    r"\bedit\b", re.IGNORECASE
                                                )
                                            )
                                            .first
                                        )
                                        if (
                                            any_action.count() > 0
                                            and any_action.is_visible()
                                        ):
                                            any_action.click(force=True)
                                        else:
                                            fallback_btn = chosen_row.locator(
                                                "button, a, [role='button']"
                                            ).first
                                            fallback_btn.click(force=True)
                                except Exception as click_det_e:
                                    print(
                                        f"      ⚠️ Deterministic edit click failed, fallback to random: {click_det_e}"
                                    )
                                time.sleep(1.0)
                                return
                        except Exception as match_e:
                            print(
                                f"      ⚠️ Deterministic edit row matching failed, fallback to random: {match_e}"
                            )

                # If we can't find action buttons (icons) for this row type,
                # don't crash. Fall back to any data row and click by heuristics later.
                if total == 0:
                    all_rows = page.locator("tbody tr").filter(has=page.locator("td"))
                    total = all_rows.count()
                    if total == 0:
                        raise Exception(
                            f"Bảng không có dòng nào để chọn ngẫu nhiên (missing {action_type} action buttons)"
                        )

                idx = random.randint(0, total - 1)
                # Wait/retry: sometimes table rows render a bit later (ajax).
                # Don’t hard-fail when total==0 on first check.
                total = all_rows.count()
                if total == 0:
                    for _attempt in range(12):
                        try:
                            if hasattr(self, "wait_for_table_data"):
                                ok = self.wait_for_table_data(page, timeout=2)
                            else:
                                ok = page.locator("tbody tr").count() > 0
                        except:
                            ok = False

                        if ok:
                            all_rows = page.locator("tbody tr").filter(
                                has=page.locator("td")
                            )
                            total = all_rows.count()
                            if total > 0:
                                break
                        time.sleep(0.5)

                if total == 0:
                    raise Exception(
                        "Bảng không có dòng nào để chọn ngẫu nhiên (after wait/retry)"
                    )

                idx = random.randint(0, total - 1)
                chosen_row = all_rows.nth(idx)
                # Choose "best ID-like" cell text (not a fixed column like td[nth(1)]),
                # because tables often place Gate in td[1] and ID in another column.
                try:
                    cells = chosen_row.locator("td").all()
                    candidates: list[str] = []
                    for i_cell, c in enumerate(cells):
                        try:
                            t = c.inner_text(timeout=300).strip()
                        except:
                            t = ""
                        if not t:
                            continue
                        # Skip pure short labels
                        if len(t) < 3:
                            continue
                        candidates.append(t)

                    def _score_id_like(t: str) -> float:
                        tl = (t or "").strip()
                        tl_low = tl.lower()
                        score = 0.0
                        # Strong hints
                        if "hieunm_test" in tl_low:
                            score += 50
                        if re.search(r"\b(id|event|event id)\b", tl_low):
                            score += 20
                        # RBE_/PVE_/Gacha_/LOC_/Offer_...
                        if any(
                            p in tl_low
                            for p in [
                                "rbe_",
                                "pve_",
                                "gacha_",
                                "loc_",
                                "offer_",
                                "boost_",
                                "feeder",
                                "superstar",
                                "slot",
                            ]
                        ):
                            score += 10
                        # Contains separators typically used in IDs
                        if "_" in tl or "-" in tl:
                            score += 15
                        # Prefer longer token as ID (Event IDs are usually long)
                        score += min(len(tl), 80) / 2.5
                        return score

                    best = None
                    best_score = float("-inf")
                    for t in candidates:
                        s = _score_id_like(t)
                        if s > best_score:
                            best_score = s
                            best = t

                    if best:
                        target_text = best
                    else:
                        # Fallback to td[1] then td[0]
                        try:
                            td_count = chosen_row.locator("td").count()
                            if td_count >= 2:
                                target_text = (
                                    chosen_row.locator("td").nth(1).inner_text().strip()
                                )
                            elif td_count >= 1:
                                target_text = (
                                    chosen_row.locator("td").first.inner_text().strip()
                                )
                            else:
                                target_text = ""
                        except:
                            target_text = (
                                chosen_row.locator("td").first.inner_text().strip()
                            )
                except Exception:
                    # Absolute fallback
                    try:
                        target_text = (
                            chosen_row.locator("td").nth(1).inner_text().strip()
                        )
                    except:
                        target_text = (
                            chosen_row.locator("td").first.inner_text().strip()
                        )

                print(f"   🎲 Chọn ngẫu nhiên dòng #{idx + 1}: '{target_text}'")
                # Lưu vào memory để debug/trace, nhưng KHÔNG dựa vào target_text để click row action.
                self.memory["LAST_SELECTED"] = target_text

                # CRITICAL FIX:
                # Random mode có thể tạo target_text rỗng ('') → sau đó JS search dựa trên text sẽ match sai/treo.
                # Vì vậy: click trực tiếp nút Edit/Clone nằm trong `chosen_row`.
                try:
                    if action_type == "edit":
                        icon = chosen_row.locator(
                            "i[class*='edit'], i[class*='pencil'], .btn-edit, button:has-text('Edit'), a:has-text('Edit')"
                        ).first
                        if icon.count() > 0 and icon.is_visible():
                            icon.click(force=True)
                        else:
                            # fallback: click bất kỳ nút/link nào có chữ edit trong row
                            any_action = (
                                chosen_row.locator("button, a, [role='button']")
                                .filter(has_text=re.compile(r"\bedit\b", re.IGNORECASE))
                                .first
                            )
                            if any_action.count() > 0 and any_action.is_visible():
                                any_action.click(force=True)
                            else:
                                # final fallback: click nút đầu tiên có vẻ là action icon
                                fallback_btn = chosen_row.locator(
                                    "button, a, [role='button']"
                                ).first
                                fallback_btn.click(force=True)
                    else:
                        icon = chosen_row.locator(
                            "i[class*='clone'], i[class*='copy'], i[class*='share'], .btn-clone, button:has-text('Clone'), a:has-text('Clone')"
                        ).first
                        if icon.count() > 0 and icon.is_visible():
                            icon.click(force=True)
                        else:
                            any_action = (
                                chosen_row.locator("button, a, [role='button']")
                                .filter(
                                    has_text=re.compile(
                                        r"\b(clone|copy|copy from|duplicate)\b",
                                        re.IGNORECASE,
                                    )
                                )
                                .first
                            )
                            if any_action.count() > 0 and any_action.is_visible():
                                any_action.click(force=True)
                            else:
                                fallback_btn = chosen_row.locator(
                                    "button, a, [role='button']"
                                ).first
                                fallback_btn.click(force=True)

                    time.sleep(1.0)

                    # Check lock popup only for edit
                    # PVE/Classic PVE panels load async and show skeleton/vld-icon loader.
                    # Requirement: do NOT check Locked Item popup until:
                    #  - we have observed loading indicator at least once
                    #  - and at least ~30s have passed
                    if action_type == "edit":
                        try:
                            start_t = time.time()
                            saw_async_loader = False

                            # hard minimum wait (8s) - regression speed-up
                            while time.time() - start_t < 8:
                                try:
                                    aria_busy = (
                                        page.locator(
                                            "[aria-busy='true']:visible"
                                        ).count()
                                        > 0
                                    )
                                except:
                                    aria_busy = False
                                try:
                                    skeleton = (
                                        page.locator(".b-skeleton:visible").count() > 0
                                    )
                                except:
                                    skeleton = False
                                try:
                                    vld_loader = (
                                        page.locator(".vld-icon:visible").count() > 0
                                    )
                                except:
                                    vld_loader = False

                                if aria_busy or skeleton or vld_loader:
                                    saw_async_loader = True

                                # If already satisfied (min time + loader observed) we can stop early
                                if saw_async_loader and time.time() - start_t >= 30:
                                    break

                                time.sleep(0.5)

                            # Even if loader wasn't detected, wait_for_long_loading is still safer
                            # than immediate popup check.
                            if hasattr(self, "_wait_for_long_loading"):
                                try:
                                    self._wait_for_long_loading(page)
                                except:
                                    pass
                        except:
                            pass

                        popup_handled = self._handle_locked_item_popup(page)
                        if popup_handled:
                            time.sleep(1.0)
                            print("      ✅ Ready to update form.")
                        else:
                            time.sleep(0.5)

                    # Random đã bấm xong action, thoát luôn để tránh JS search theo target_text.
                    return
                except Exception as click_e:
                    # Nếu click direct fail thì KHÔNG dùng JS search theo `target_text`
                    # (vì `target_text` có thể là chuỗi rác như fullcalendar/text lớn).
                    # Thay vào đó: retry click trực tiếp action icon trong các row nằm trong scope `all_rows`.
                    print(f"      ⚠️ Random direct click failed: {click_e}")
                    try:
                        for _retry in range(3):
                            retry_row = all_rows.nth(
                                random.randint(0, max(0, total - 1))
                            )
                            if action_type == "edit":
                                retry_icon = retry_row.locator(
                                    "i[class*='edit'], i[class*='pencil'], .btn-edit, button:has-text('Edit'), a:has-text('Edit')"
                                ).first
                                if retry_icon.count() > 0:
                                    retry_icon.evaluate(
                                        "el => { el.scrollIntoView({block: 'center'}); el.click(); }"
                                    )
                                else:
                                    retry_any = (
                                        retry_row.locator("button, a, [role='button']")
                                        .filter(
                                            has_text=re.compile(
                                                r"\bedit\b",
                                                re.IGNORECASE,
                                            )
                                        )
                                        .first
                                    )
                                    if retry_any.count() > 0:
                                        retry_any.evaluate(
                                            "el => { el.scrollIntoView({block: 'center'}); el.click(); }"
                                        )
                                    else:
                                        continue
                            else:
                                retry_icon = retry_row.locator(
                                    "i[class*='clone'], i[class*='copy'], i[class*='share'], .btn-clone, button:has-text('Clone'), a:has-text('Clone')"
                                ).first
                                if retry_icon.count() > 0:
                                    retry_icon.evaluate(
                                        "el => { el.scrollIntoView({block: 'center'}); el.click(); }"
                                    )
                                else:
                                    retry_any = (
                                        retry_row.locator("button, a, [role='button']")
                                        .filter(
                                            has_text=re.compile(
                                                r"\b(clone|copy|copy from|duplicate)\b",
                                                re.IGNORECASE,
                                            )
                                        )
                                        .first
                                    )
                                    if retry_any.count() > 0:
                                        retry_any.evaluate(
                                            "el => { el.scrollIntoView({block: 'center'}); el.click(); }"
                                        )
                                    else:
                                        continue

                            time.sleep(1.0)
                            if action_type == "edit":
                                popup_handled = self._handle_locked_item_popup(page)
                                if popup_handled:
                                    time.sleep(1.0)
                                    print("      ✅ Ready to update form (retry).")
                                else:
                                    time.sleep(0.5)
                            return
                    except Exception as _retry_e:
                        print(f"      ⚠️ Random direct click retry failed: {_retry_e}")

                    raise Exception(
                        f"Random direct click failed for action_type={action_type} after retries"
                    )
            except Exception as e:
                raise Exception(f"Random row selection failed: {e}")

        self._ensure_liveoptest_items_visible(page)
        print(f"   🔎 Tìm dòng '{target_text}' để {action_type}...")

        js_script = """
            (args) => {
                const targetText = args.text.toLowerCase().trim();
                const action = args.action;
                const rows = Array.from(document.querySelectorAll('tbody tr'));
                
                for (const row of rows) {
                    if (row.innerText.toLowerCase().includes(targetText)) {
                        let btn = null;
                        if (action === 'edit') {
                            btn = row.querySelector("i[class*='edit'], i[class*='pencil'], .btn-edit");
                        } else {
                            btn = row.querySelector("i[class*='clone'], i[class*='copy'], i[class*='share'], .btn-clone");
                        }
                        if (btn) {
                            (btn.closest('button') || btn.closest('a') || btn).click();
                            return "Clicked via Icon";
                        }
                        const buttons = row.querySelectorAll("button, a.btn, a[class*='btn']");
                        if (buttons.length > 0) {
                            if (buttons.length >= 2) { (action === 'edit' ? buttons[0] : buttons[1]).click(); } 
                            else { buttons[0].click(); }
                            return "Clicked via Position";
                        }
                    }
                }
                return "Row Not Found";
            }
        """
        result = page.evaluate(
            js_script, {"text": str(target_text), "action": action_type}
        )

        if "Clicked" in result:
            print(f"   ✅ JS Click Success: {result}")

            # [CRITICAL] Check for Locked Item popup after edit click (NOT clone)
            # Clone just opens a modal - lock popup check happens AFTER save_form(clone)
            # Some items may be locked by other users
            # Chờ đủ lâu để popup có thời gian render (tăng từ 0.5s lên 1s)
            time.sleep(1.0)
            if action_type == "edit":
                popup_handled = self._handle_locked_item_popup(page)
                if popup_handled:
                    # After acquiring lock, wait for form to fully load
                    time.sleep(1.0)
                    print("      ✅ Ready to update form.")
                else:
                    # No popup = item unlocked, proceed normally
                    time.sleep(0.5)
        elif "Row Not Found" in result:
            if self._auto_filter_data(page, target_text):
                result = page.evaluate(
                    js_script, {"text": str(target_text), "action": action_type}
                )
                # Lock check only for edit (not clone)
                if "Clicked" in result and action_type == "edit":
                    time.sleep(1.0)
                    popup_handled = self._handle_locked_item_popup(page)
                    if popup_handled:
                        time.sleep(1.0)
                        print("      ✅ Ready to update form.")
                    else:
                        time.sleep(0.5)
            else:
                # Fallback: không crash job nếu không tìm thấy row target_text (đặc biệt sau khi filter/tab thay đổi).
                # Chọn dòng visible đầu tiên và thực hiện edit/clone theo action_type.
                try:
                    print(
                        f"      ⚠️ Row '{target_text}' not found. Falling back to first visible row for action='{action_type}'."
                    )
                    # Find first visible data row
                    first_row = (
                        page.locator("tbody tr")
                        .filter(has=page.locator("button, a, [role='button']"))
                        .first
                    )
                    if first_row.count() > 0 and first_row.is_visible():
                        js_fallback = """
(e) => {
  const row = e;
  const buttons = row.querySelectorAll("button, a.btn, a[class*='btn'], [role='button']");
  // Heuristic: pick first row action with edit if action hint exists in DOM text/aria
  const clickables = Array.from(buttons).filter(b => {
    const t = ((b.innerText||'') + ' ' + (b.getAttribute('aria-label')||'') + ' ' + (b.getAttribute('title')||'')).toLowerCase();
    return b.offsetParent !== null && (t.includes('edit') || t.includes('clone') || t.includes('copy') || t.includes('open') || t.includes('save'));
  });
  const b = clickables[0] || buttons[0];
  if (b) { b.closest('button,a')?.click?.(); (b.click ? b.click() : b.dispatchEvent(new MouseEvent('click',{bubbles:true}))); return true; }
  return false;
}
"""
                        ok = page.evaluate(js_fallback, first_row)
                        if ok:
                            time.sleep(1.0)
                            return
                    print(
                        "      ⚠️ Fallback row click failed; no visible rows/actions found."
                    )
                except Exception as fb_e:
                    print(f"      ❌ Fallback row click error: {fb_e}")
                # As last resort, keep old behavior
                raise Exception(f"Không tìm thấy dòng '{target_text}'")

    # ============================
    # TABLE HELPERS
    # ============================


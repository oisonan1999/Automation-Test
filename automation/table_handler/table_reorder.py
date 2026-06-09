# automation/table_handler/table_reorder.py - split from table_handler.py
# Drag-and-drop row/panel reorder
import time
import re
import random


class TableReorderMixin:
    """Drag-and-drop row/panel reorder"""

    def drag_to_reorder(self, page, target, position=None, before=None, after=None):
        """
        Kéo thả một item (row/panel-item) để đổi thứ tự ưu tiên.

        Tìm drag handle (dấu ≡) của target item, sau đó kéo đến vị trí mong muốn.

        Args:
            page:     Playwright Page object
            target:   Text/ID của item cần di chuyển (khớp với text content)
            position: Vị trí đích (1-based). position=1 = lên đầu danh sách.
            before:   Tên item mà target sẽ được đặt TRƯỚC.
            after:    Tên item mà target sẽ được đặt SAU.

        Returns:
            list of log dicts
        """
        logs = []
        print(
            f"\n   🖱️  REORDER: '{target}' → position={position} before={before} after={after}"
        )

        # ----------------------------------------------------------------
        # 1. Tìm handle selector có drag handles trên trang
        # ----------------------------------------------------------------
        DRAG_HANDLE_SELECTORS = [
            "i.fa-bars",
            "i.fa-grip",
            "i.fa-grip-vertical",
            "i.fa-grip-lines",
            "[class*='drag']",
            "[class*='handle']",
            "[class*='sort']",
            "span[class*='drag']",
            "svg[class*='drag']",
            ".drag-handle",
            ".sort-handle",
            "[draggable='true']",
        ]

        drag_rows = None

        # Chiến lược: Tìm handle selector có nhiều hơn 1 handle
        for handle_sel in DRAG_HANDLE_SELECTORS:
            handles = page.locator(handle_sel)
            count = handles.count()
            if count > 1:
                drag_rows = handle_sel
                print(f"      ✓ Found {count} drag handles via '{handle_sel}'")
                break

        if not drag_rows:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": "No draggable items found on page",
                }
            )
            return logs

        drag_handle_sel = drag_rows

        # Guard: target rỗng → fail ngay, tránh match nhầm item đầu tiên
        if not target or not target.strip():
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": "Reorder target is empty. Please specify the item name to drag.",
                }
            )
            print("      ❌ Reorder aborted: target is empty string.")
            return logs

        # ----------------------------------------------------------------
        # 2. Thu thập tất cả rows có drag handle và text content
        #    Scope về đúng cột/panel chứa target bằng cách cluster theo
        #    tọa độ X của drag handle (cùng cột = cùng X ± 150px)
        # ----------------------------------------------------------------
        print(f"      📌 Handle selector: '{drag_handle_sel}'")

        all_handles_full = page.locator(drag_handle_sel)
        total_full = all_handles_full.count()

        # ── Bước 2a: Thu thập bbox + text cho mọi handle ─────────────────
        raw_items = []  # list of (global_idx, text, handle, bbox)
        target_lower_pre = target.lower().strip()

        def _quick_text(h):
            """Lấy text ngắn gọn của item chứa handle h."""
            for steps in range(1, 5):
                xpath_str = "/".join([".."] * steps)
                try:
                    row = h.locator(f"xpath={xpath_str}")
                    if row.count() == 0:
                        continue
                    bbox = row.bounding_box()
                    if bbox is None or bbox["height"] > 150:
                        continue
                    text = row.inner_text(timeout=500).strip().replace("\n", " ")
                    if len(text) > 200:
                        continue
                    return text
                except Exception:
                    continue
            try:
                return (
                    all_handles_full.nth(0)
                    .locator("xpath=..")
                    .inner_text(timeout=500)[:100]
                )
            except Exception:
                return ""

        for i in range(total_full):
            h = all_handles_full.nth(i)
            try:
                bbox = h.bounding_box()
                text = _quick_text(h)
                raw_items.append((i, text, h, bbox))
            except Exception:
                raw_items.append((i, "", h, None))

        # ── Bước 2b: Tìm source item và lấy X của handle đó ──────────────
        source_x = None
        for idx, text, h, bbox in raw_items:
            if target_lower_pre in text.lower() or text.lower().startswith(
                target_lower_pre
            ):
                if bbox:
                    source_x = bbox["x"]
                    print(f"      🎯 Source handle X = {source_x:.0f}")
                break

        # ── Bước 2c: Lọc chỉ những handle cùng cột (|x - source_x| ≤ 150) ─
        X_TOLERANCE = 150  # px
        if source_x is not None:
            same_col = [
                (idx, text, h, bbox)
                for idx, text, h, bbox in raw_items
                if bbox and abs(bbox["x"] - source_x) <= X_TOLERANCE
            ]
            if len(same_col) > 1:
                print(
                    f"      ✅ Scoped to {len(same_col)} handles in same column (X ≈ {source_x:.0f})"
                )
                # Bọc lại dưới dạng cấu trúc tương thích với code bên dưới
                scoped_items = same_col
            else:
                print(
                    f"      ⚠️  Column scope found only {len(same_col)} item(s), using all handles"
                )
                scoped_items = raw_items
        else:
            print(f"      ⚠️  Source X not found, using all handles")
            scoped_items = raw_items

        # Xây dựng all_handles tương thích (dùng global index list, không dùng locator)
        # Thay thế all_handles.nth(i) bằng trực tiếp scoped_items
        total = len(scoped_items)
        print(f"      📋 Total drag handles found: {total}")

        def _get_row_for_handle(handle):
            """Trả về (row_locator, text) của item chứa handle.
            Đi từ direct parent lên dần đến khi tìm được element có text
            nhỏ gọn (không phải container chứa nhiều items)."""
            for steps in range(1, 5):  # thử lên 1-4 cấp
                xpath_str = "/".join([".."] * steps)  # "..", "../..", "../../.." …
                try:
                    row = handle.locator(f"xpath={xpath_str}")
                    if row.count() == 0:
                        continue
                    # Kiểm tra bbox — nếu phần tử quá cao (>150px) thì đang ở container
                    bbox = row.bounding_box()
                    if bbox is None:
                        continue
                    if bbox["height"] > 150:
                        continue  # Quá cao → chứa nhiều items → đi tiếp
                    text = row.inner_text(timeout=1000).strip().replace("\n", " ")
                    # Nếu text quá dài (>200 chars) → likely container text
                    if len(text) > 200:
                        continue
                    return row, text
                except Exception:
                    continue
            # Fallback: direct parent bất kể
            try:
                row = handle.locator("xpath=..")
                text = row.inner_text(timeout=1000).strip().replace("\n", " ")
                return row, text[:200]
            except Exception:
                return None, ""

        # Map text → index (0-based) — dùng scoped_items đã thu thập sẵn
        # scoped_items: list of (global_idx, text, handle, bbox)
        items = []
        for local_i, (global_idx, text, handle, bbox) in enumerate(scoped_items):
            items.append((local_i, text, handle, None))
            print(f"         [{local_i+1}] {text[:100]}")

        if not items:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": "Could not read draggable item texts",
                }
            )
            return logs

        # ----------------------------------------------------------------
        # 3. Tìm source item (target)
        # ----------------------------------------------------------------
        source_idx = None
        target_lower = target.lower().strip()
        for idx, text, handle, row in items:
            if target_lower in text.lower() or text.lower().startswith(target_lower):
                source_idx = idx
                print(f"      ✅ Source found at index {idx+1}: '{text[:60]}'")
                break

        if source_idx is None:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": f"Source item '{target}' not found in draggable list",
                }
            )
            return logs

        # ----------------------------------------------------------------
        # 4. Tính destination index
        # ----------------------------------------------------------------
        dest_idx = None

        # ── Fallback: nếu không có position/before/after, di chuyển xuống 1 bước ────
        if position is None and before is None and after is None:
            dest_idx = min(source_idx + 1, total - 1)
            print(
                f"      ⚠️  No position/before/after given → defaulting to move down 1 step (index {dest_idx})"
            )

        if position is not None:
            # position là 1-based; 9999 = last
            dest_idx = max(0, min(int(position) - 1, total - 1))
            print(f"      🎯 Destination by position={position} → index {dest_idx}")

        elif before is not None:
            before_lower = before.lower().strip()
            for idx, text, handle, row in items:
                if before_lower in text.lower():
                    dest_idx = idx
                    # Nếu source đang ở trước dest, dest thực sự là dest-1 sau khi source rời
                    print(
                        f"      🎯 Destination BEFORE '{text[:60]}' → index {dest_idx}"
                    )
                    break

        elif after is not None:
            after_lower = after.lower().strip()
            for idx, text, handle, row in items:
                if after_lower in text.lower():
                    dest_idx = min(idx + 1, total - 1)
                    print(
                        f"      🎯 Destination AFTER '{text[:60]}' → index {dest_idx}"
                    )
                    break

        if dest_idx is None:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": f"Could not determine destination position",
                }
            )
            return logs

        if source_idx == dest_idx:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "PASS",
                    "details": f"'{target}' already at position {dest_idx+1}, no move needed",
                }
            )
            return logs

        # ----------------------------------------------------------------
        # 5. Thực hiện kéo thả
        # ----------------------------------------------------------------
        source_handle = items[source_idx][2]
        dest_handle = items[dest_idx][2]
        # Dùng bbox đã fetch sẵn từ scoped_items để tránh stale re-fetch
        src_box_pre = scoped_items[source_idx][3]
        dest_box_pre = scoped_items[dest_idx][3]

        try:
            # Scroll source vào view
            source_handle.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.3)

            src_box = source_handle.bounding_box() or src_box_pre
            dest_box = dest_handle.bounding_box() or dest_box_pre

            if not src_box or not dest_box:
                raise Exception("Could not get bounding boxes for drag handles")

            src_x = src_box["x"] + src_box["width"] / 2
            src_y = src_box["y"] + src_box["height"] / 2
            dest_x = dest_box["x"] + dest_box["width"] / 2

            # Đặt dest_y: nếu kéo lên → Y trên của dest, nếu kéo xuống → Y dưới của dest
            if source_idx > dest_idx:
                # Kéo lên: thả ở cạnh trên của dest item
                dest_y = dest_box["y"] + 4
            else:
                # Kéo xuống: thả ở cạnh dưới của dest item
                dest_y = dest_box["y"] + dest_box["height"] - 4

            print(
                f"      🖱️  Drag ({src_x:.0f},{src_y:.0f}) → ({dest_x:.0f},{dest_y:.0f})"
            )

            mouse = page.mouse
            mouse.move(src_x, src_y)
            time.sleep(0.2)
            mouse.down()
            time.sleep(0.3)

            # Di chuyển mượt mà theo từng bước nhỏ
            steps = 20
            for step in range(1, steps + 1):
                mid_x = src_x + (dest_x - src_x) * step / steps
                mid_y = src_y + (dest_y - src_y) * step / steps
                mouse.move(mid_x, mid_y)
                time.sleep(0.02)

            time.sleep(0.3)
            mouse.up()
            time.sleep(0.5)

            # Chờ UI cập nhật
            page.wait_for_load_state("networkidle", timeout=5000)
            time.sleep(0.5)

            move_desc = f"'{target}' moved from position {source_idx+1} to {dest_idx+1}"
            print(f"      ✅ {move_desc}")
            logs.append({"step": "Reorder", "status": "PASS", "details": move_desc})

        except Exception as e:
            print(f"      ❌ Drag failed: {e}")
            logs.append(
                {"step": "Reorder", "status": "FAIL", "details": f"Drag error: {e}"}
            )

        return logs

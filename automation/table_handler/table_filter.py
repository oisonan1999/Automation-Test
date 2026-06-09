# automation/table_handler/table_filter.py - split from table_handler.py
# Filter/search table data, locate data table, wait for rows
import time
import re
import random


class TableFilterMixin:
    """Filter/search table data, locate data table, wait for rows"""

    def _ensure_liveoptest_items_visible(self, page):
        """Auto-uncheck 'Hide LiveopsTest gate items' checkbox if present and checked."""
        try:
            result = page.evaluate("""
                () => {
                    const allEls = document.querySelectorAll('label, span, div');
                    for (const el of allEls) {
                        if (!/hide liveo[p]?stest/i.test(el.textContent || '')) continue;
                        if (!el.offsetParent) continue;
                        let chk = el.querySelector('input[type="checkbox"]');
                        if (!chk && el.previousElementSibling && el.previousElementSibling.tagName === 'INPUT')
                            chk = el.previousElementSibling;
                        if (!chk) chk = el.parentElement && el.parentElement.querySelector('input[type="checkbox"]');
                        if (chk && chk.checked) { chk.click(); return true; }
                        if (chk && !chk.checked) return false;
                    }
                    return null;
                }
            """)
            if result is True:
                print("   🔓 Auto-unchecked 'Hide LiveopsTest gate items'")
                time.sleep(0.8)
        except Exception as e:
            print(f"   ⚠️ _ensure_liveoptest_items_visible: {e}")

    def _auto_filter_data(self, page, keyword):
        self._ensure_liveoptest_items_visible(page)
        try:
            search_input = None
            placeholders = ["ID", "Search", "Name", "Filter", "Title"]
            for p in placeholders:
                inp = page.get_by_placeholder(re.compile(p, re.IGNORECASE)).first
                if inp.is_visible():
                    search_input = inp
                    break

            if not search_input:
                search_input = page.locator("input[type='text']:visible").first

            if search_input and search_input.is_visible():
                print(f"      👉 Auto Filter: '{keyword}'")
                search_input.fill(keyword)
                # Try clicking the Filter button explicitly before pressing Enter
                _filter_clicked = False
                try:
                    _filter_btn = page.locator(
                        "button#btn-filter, button:has-text('Filter'), a.btn:has-text('Filter')"
                    ).first
                    if _filter_btn.count() > 0 and _filter_btn.is_visible():
                        _filter_btn.click()
                        _filter_clicked = True
                        print(f"      🔘 Clicked Filter button")
                except Exception:
                    pass
                if not _filter_clicked:
                    search_input.press("Enter")
                time.sleep(2)
                return True
        except:
            pass
        return False

    def wait_for_table_data(self, page, timeout=10):
        """Chờ bảng có dữ liệu"""
        s = time.time()
        while time.time() - s < timeout:
            if page.locator("tbody tr").count() > 0:
                return True
            time.sleep(0.5)
        return False

    def _find_data_table(self, page):
        """Tìm bảng chứa checkbox (loại bỏ bảng layout/header)"""
        tables = page.locator("table").all()
        for tbl in tables:
            if not tbl.is_visible():
                continue
            if tbl.locator("tbody tr input[type='checkbox']").count() > 0:
                return tbl
        return page.locator("table").last

    def _perform_table_filter(self, page, col_name, value):
        """Tự động điền Filter và bấm nút"""
        self._ensure_liveoptest_items_visible(page)
        # 1. Tìm Input
        search_input = None
        placeholders = [f"{col_name} Contains", f"{col_name}", "Search", "Filter", "ID"]

        for p in placeholders:
            inp = page.get_by_placeholder(re.compile(p, re.IGNORECASE)).first
            if inp.is_visible():
                search_input = inp
                print(f"      👉 Found Filter Input: '{p}'")
                break

        if not search_input:
            search_input = page.locator(
                ".filter-box input, .card-header input, input.form-control"
            ).first

        if search_input and search_input.is_visible():
            search_input.fill(str(value))

            # 2. Bấm nút Filter
            btn = (
                page.locator("button, a.btn")
                .filter(has_text=re.compile("Filter|Search|Go", re.IGNORECASE))
                .first
            )
            if not btn.is_visible():
                btn = page.locator(
                    "button:has(i.fa-search), button:has(i.fa-filter)"
                ).first

            if btn.is_visible():
                btn.click()
            else:
                search_input.press("Enter")

            # Chờ reload
            time.sleep(2.0)
            page.wait_for_load_state("networkidle")
            return True

        return False

    # ============================
    # DRAG-AND-DROP REORDER
    # ============================


"""
Golden Plan Cache
=================

Khi một smoke test case chạy PASS hoàn toàn (mọi step Playwright thành công,
không CRASH/block), ta "đóng băng" đúng action plan đã chạy thành công thành một
TEMPLATE và lưu lại. Lần chạy sau, nếu case đó đã có golden plan, ta BỎ QUA LLM
hoàn toàn, nạp lại template và chỉ bơm lại phần data động (ID sinh mới, ID vừa
clone) → chạy nhanh, xác định, không phụ thuộc vào việc LLM có sinh đủ/đúng step.

Tại sao tokenize thay vì cache nguyên plan:
- Mỗi run, ID create/clone là duy nhất (vd hieunm_test_20260609_...), và tham chiếu
  "ID vừa clone" trỏ tới ID runtime khác nhau. Đây là những thứ DUY NHẤT thay đổi
  giữa các lần chạy của cùng một case. Ta thay chúng bằng placeholder
  {{UNIQUE_ID}} / {{LAST_ID}} khi lưu, và bơm giá trị mới khi replay.
- Mọi dữ liệu tĩnh khác (ngày, tên field, schedule...) cố định trong CSV nên cache
  nguyên văn là đúng.

Key = (feature + nội dung testcase gốc trong CSV) đã chuẩn hoá khoảng trắng — ổn
định qua các lần chạy vì CSV không đổi.
"""

import os
import re
import json
import datetime

GOLDEN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "golden_plans.json"
)

_UNIQUE_TOKEN = "{{UNIQUE_ID}}"
_LAST_TOKEN = "{{LAST_ID}}"
# Không tokenize chuỗi quá ngắn để tránh thay nhầm các giá trị tình cờ trùng.
_MIN_TOKEN_LEN = 4


# --- Persistence ------------------------------------------------------------
def load_golden() -> dict:
    if not os.path.exists(GOLDEN_FILE):
        return {}
    try:
        with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_store(store: dict) -> None:
    try:
        os.makedirs(os.path.dirname(GOLDEN_FILE), exist_ok=True)
        with open(GOLDEN_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"   ⚠️ Could not save golden_plans.json: {e}")


def golden_key(feature: str, testcase_raw: str) -> str:
    norm = re.sub(r"\s+", " ", (testcase_raw or "").strip()).lower()
    return f"{(feature or '').strip().lower()}||{norm}"


def golden_count() -> int:
    return len(load_golden())


def clear_all() -> int:
    n = golden_count()
    _save_store({})
    return n


def invalidate(feature: str, testcase_raw: str) -> bool:
    store = load_golden()
    key = golden_key(feature, testcase_raw)
    if key in store:
        del store[key]
        _save_store(store)
        return True
    return False


# --- Tokenize / Detokenize --------------------------------------------------
def tokenize_plan(plan, unique_id: str | None, last_id: str | None):
    """Trả về (template, uses_unique, uses_last). Thay giá trị ID động bằng placeholder."""
    s = json.dumps(plan, ensure_ascii=False)
    # Thay chuỗi dài trước để tránh chồng lấn một phần.
    pairs = [(_UNIQUE_TOKEN, unique_id), (_LAST_TOKEN, last_id)]
    pairs.sort(key=lambda kv: len(kv[1] or ""), reverse=True)
    uses_unique = uses_last = False
    for token, val in pairs:
        if val and isinstance(val, str) and len(val) >= _MIN_TOKEN_LEN and val in s:
            s = s.replace(val, token)
            if token == _UNIQUE_TOKEN:
                uses_unique = True
            else:
                uses_last = True
    return json.loads(s), uses_unique, uses_last


def detokenize_plan(template, unique_id: str | None, last_id: str | None):
    s = json.dumps(template, ensure_ascii=False)
    s = s.replace(_UNIQUE_TOKEN, unique_id or "")
    s = s.replace(_LAST_TOKEN, last_id or "")
    return json.loads(s)


# --- Public API used by the smoke runner ------------------------------------
def get_golden_plan(feature, testcase_raw, unique_id, last_id):
    """Trả về plan sẵn sàng chạy (đã bơm data) nếu có golden hợp lệ, ngược lại None."""
    store = load_golden()
    entry = store.get(golden_key(feature, testcase_raw))
    if not entry or "template" not in entry:
        return None
    # Nếu template cần một placeholder mà run hiện tại không có giá trị tương ứng →
    # không replay (tránh bơm chuỗi rỗng làm hỏng plan); để runner fallback sang AI.
    if entry.get("uses_unique") and not unique_id:
        return None
    if entry.get("uses_last") and not last_id:
        return None
    try:
        return detokenize_plan(entry["template"], unique_id, last_id)
    except Exception as e:
        print(f"   ⚠️ Golden detokenize failed: {e}")
        return None


def record_success(feature, testcase_raw, plan, unique_id, last_id, label=""):
    """Lưu plan đã chạy PASS sạch thành golden template."""
    try:
        template, uses_unique, uses_last = tokenize_plan(plan, unique_id, last_id)
        store = load_golden()
        store[golden_key(feature, testcase_raw)] = {
            "feature": feature,
            "label": label or (testcase_raw or "")[:120],
            "step_count": len(template) if isinstance(template, list) else 1,
            "uses_unique": uses_unique,
            "uses_last": uses_last,
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "template": template,
        }
        _save_store(store)
        return True
    except Exception as e:
        print(f"   ⚠️ Could not record golden plan: {e}")
        return False

# AI-fallback locator: last-resort field finder when every heuristic in
# field_finder.py fails. Calls Claude Sonnet with a compact DOM snapshot of
# the current scope (page or open modal) and asks it to pick the right
# element. Isolated from the Ollama-based action-plan pipeline in brain.py.
import json
import os

import anthropic

_client = None

# Elements are tagged with this temp attribute during the snapshot so an
# AI-picked index can be resolved back to a real Locator without relying on
# id/name (many fields have neither).
_SNAPSHOT_ATTR = "data-ai-fb-idx"

_SNAPSHOT_JS = f"""
(root) => {{
    const container = root || document;
    const nodes = container.querySelectorAll('label, input, select, textarea, button');
    const result = [];
    let idx = 0;
    nodes.forEach((el) => {{
        if (el.offsetParent === null) return;
        el.setAttribute('{_SNAPSHOT_ATTR}', String(idx));
        const tag = el.tagName.toLowerCase();
        result.push({{
            index: idx,
            tag: tag,
            id: el.id || null,
            name: el.getAttribute('name') || null,
            cls: el.className || null,
            placeholder: el.getAttribute('placeholder') || null,
            text: (tag === 'label' || tag === 'button') ? el.innerText.trim().slice(0, 80) : null,
        }});
        idx += 1;
    }});
    return result;
}}
"""

_CLEANUP_JS = f"""
(elOrArg, maybeArg) => {{
    // Locator.evaluate() passes (element, arg); Page.evaluate() passes (arg)
    // with no element — disambiguate by checking for an actual DOM node.
    const isElement = elOrArg && elOrArg.nodeType === 1;
    const root = isElement ? elOrArg : null;
    const arg = isElement ? maybeArg : elOrArg;
    const keepIndex = (arg && arg.keepIndex !== undefined) ? arg.keepIndex : null;
    const container = root || document;
    container.querySelectorAll('[{_SNAPSHOT_ATTR}]').forEach((el) => {{
        if (keepIndex !== null && el.getAttribute('{_SNAPSHOT_ATTR}') === String(keepIndex)) return;
        el.removeAttribute('{_SNAPSHOT_ATTR}');
    }});
}}
"""

_SNAPSHOT_LIMIT = 150


def _get_client():
    global _client
    if _client is None:
        # Prefer a standalone ANTHROPIC_API_KEY. Fall back to the internal
        # Mushigen gateway when that's all this environment provides — it
        # speaks the AWS Bedrock InvokeModel wire format (/model/{id}/invoke),
        # not /v1/messages, so it needs AnthropicBedrock, not Anthropic().
        # AnthropicBedrock already reads ANTHROPIC_BEDROCK_BASE_URL itself;
        # passing api_key (vs AWS creds) makes it send a plain Bearer token.
        if os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") and not os.environ.get(
            "ANTHROPIC_API_KEY"
        ):
            _client = anthropic.AnthropicBedrock(
                api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
            )
        else:
            _client = anthropic.Anthropic()
    return _client


def capture_dom_snapshot(scope):
    """scope: a Playwright Page or Locator. Tags matched elements with
    _SNAPSHOT_ATTR so the caller can resolve an index back to a real element."""
    snapshot = scope.evaluate(_SNAPSHOT_JS)
    return snapshot[:_SNAPSHOT_LIMIT]


def cleanup_snapshot_attrs(scope, keep_index=None):
    """Removes the temp snapshot attribute from every tagged element in
    scope, except keep_index (kept because the returned Locator still
    depends on it to re-resolve the element on later actions)."""
    try:
        scope.evaluate(_CLEANUP_JS, {"keepIndex": keep_index})
    except Exception:
        pass


def ask_ai_for_locator(field_label, dom_snapshot):
    """Returns {"found": True, "index": int, "reason": str} or None."""
    if not dom_snapshot:
        return None

    # NOTE: the Mushigen gateway proxies AWS Bedrock InvokeModel and rejects
    # output_config.format (structured outputs) — so JSON is enforced only
    # via prompt instruction, then salvaged with brain.py's clean_json_string,
    # same as the Ollama pipeline has to do for the same reason.
    try:
        response = _get_client().messages.create(
            model="claude-sonnet-5",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f'Field cần điền: "{field_label}"\n\n'
                        "Danh sách phần tử trên trang (index bắt đầu từ 0):\n"
                        f"{json.dumps(dom_snapshot, ensure_ascii=False)}\n\n"
                        "Chọn index của phần tử đúng nhất để điền field trên. "
                        "Nếu không có phần tử nào phù hợp, trả found=false.\n\n"
                        'Trả lời CHỈ bằng một JSON object hợp lệ, không giải thích, '
                        "không dùng markdown code block, đúng format:\n"
                        '{"found": true, "index": 0, "reason": "..."}'
                    ),
                }
            ],
        )
    except Exception as e:
        print(f"         ⚠️ AI-fallback locator API error: {e}")
        return None

    try:
        text = next(b.text for b in response.content if b.type == "text")
    except Exception as e:
        print(f"         ⚠️ AI-fallback locator parse error: {e}")
        return None

    # Sonnet returns clean JSON almost always — try that first. Only fall
    # back to clean_json_string's aggressive quote-fixing (built for sloppy
    # Ollama output) when direct parse fails, since it can corrupt an
    # already-valid JSON string that happens to contain apostrophes.
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        try:
            from ai.brain import clean_json_string

            result = json.loads(clean_json_string(text))
        except Exception as e:
            print(f"         ⚠️ AI-fallback locator parse error: {e}")
            return None

    if not result.get("found"):
        return None
    return result

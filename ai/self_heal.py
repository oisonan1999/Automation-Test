# ai/self_heal.py — autonomous diagnose → fix → self-test loop for standalone smoke
# failures. Invoked only from app.py, only when running a single testcase/feature (the
# full-CSV run never triggers this). Uses claude_agent_sdk in-process: under the hood it
# spawns the `claude` CLI as a managed subprocess, but the caller-side integration here
# is a plain function call — no manual subprocess/JSON plumbing. Same tier as
# ai/ai_locator_fallback.py (isolated LLM helper, no Playwright/page dependency of its
# own — the agent drives its own browser interaction via its Bash tool).
import asyncio
import json
import os
import re
import shutil
import time

MEMORY_DIR = os.path.expanduser(
    "~/.claude/projects/-Users-hieunm-Documents-AutoGameOps/memory"
)

# The agent may only touch these directories via Write/Edit — enforced by the PreToolUse
# hook (_pre_tool_use_guard), not just the prompt, since prompt instructions alone are
# not a real security boundary.
ALLOWED_EDIT_DIRS = ("ai", "automation")

SELF_HEAL_OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "fixed": {"type": "boolean"},
            "files_changed": {"type": "array", "items": {"type": "string"}},
            "root_cause": {"type": "string"},
            "fix_description": {"type": "string"},
            "how_to_apply": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["fixed", "files_changed", "summary"],
    },
}

SYSTEM_PROMPT = """You are a self-heal agent for the AutoGameOps QA automation repo.

Read CLAUDE.md at the repo root in full before touching anything. Also check
~/.claude/projects/-Users-hieunm-Documents-AutoGameOps/memory/MEMORY.md for prior bugs
similar to this one — this repo's bug history shows the root cause is often in a
DIFFERENT file than where the failure surfaced, not the file the traceback points at.

Your job, in order:
1. Diagnose the ROOT CAUSE of the failure described in the user message.
2. Apply the MINIMAL targeted fix. You may only edit files under ai/ or automation/.
   Never use git (no commit/add/push — you have no reason to invoke git at all). Never
   touch config/golden_plans.json, anything under downloads/, .env, or CSV test data.
3. SELF-TEST your fix on the SAME live browser (already CDP-attached at
   localhost:9222 — do not relaunch Chrome or navigate away from wherever it already
   is). Use a Bash-run Python snippet against this repo's own automation module, e.g.:
       python3 -c "
       from automation.core import BrickAutomation
       automation = BrickAutomation()
       print(automation.execute_action(<steps>))
       "
   Use the repo's own .venv interpreter if one exists (check for .venv/bin/python3
   before assuming a bare python3 has the right packages installed).
   IMPORTANT: a plain FAIL (as opposed to CRASH) usually means the page has already
   been reloaded by the time you're reading this, wiping whatever modal/tab state
   earlier steps in the plan had built up. If the failing step depends on that state
   (e.g. a modal opened by a preceding clone_row/edit_row, or a tab click), replay a
   short PREFIX of the action plan ending at the failing step, not just the bare single
   step — use your own judgment about how far back the prefix needs to start.
   Confirm the returned execution logs no longer contain status FAIL or CRASH for that
   step before declaring the fix verified.
4. Only after your self-test in step 3 actually passes, return your final structured
   result. Do NOT set "fixed": true unless you actually reproduced a passing self-test.

You do not need to write anything under ~/.claude/.../memory/ yourself — the caller
handles recording this fix from the structured fields you return.
"""


def build_failure_context(*, feature, testcase, case_command, action_plan, report_logs):
    """Assemble the failure payload for the self-heal agent. Prefers the log entry that
    carries a real traceback (added by automation/core.py's per-branch/outer excepts)
    over a bare FAIL/CRASH note; since every hard-fail branch `break`s the step loop,
    the last FAIL/CRASH entry in report_logs is the one that actually stopped
    execution."""
    failing_entry = None
    for entry in reversed(report_logs or []):
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "")).upper()
        if status not in ("FAIL", "CRASH"):
            continue
        if entry.get("traceback"):
            failing_entry = entry
            break
        if failing_entry is None:
            failing_entry = entry
    failing_entry = failing_entry or {}
    return {
        "feature": feature,
        "testcase": testcase,
        "case_command": case_command,
        "action_plan": action_plan,
        "report_logs": report_logs,
        "failing_entry": failing_entry,
        "step_idx": failing_entry.get("step_idx"),
        "step_data": failing_entry.get("step_data"),
        "traceback": failing_entry.get("traceback", ""),
    }


def _build_user_prompt(context):
    failing_entry = context.get("failing_entry", {})
    return (
        "A smoke-test case just failed.\n\n"
        f"Feature: {context.get('feature')}\n"
        f"Testcase: {context.get('testcase')}\n"
        f"Original command: {context.get('case_command')}\n"
        f"Failing step index (0-based) in the action plan: {context.get('step_idx')}\n"
        f"Failing step data: {json.dumps(context.get('step_data'), ensure_ascii=False)}\n"
        f"Reported status/details: {failing_entry.get('status')} / {failing_entry.get('details')}\n"
        f"Full traceback (if any):\n{context.get('traceback', '')}\n\n"
        f"Full action plan for context:\n{json.dumps(context.get('action_plan'), ensure_ascii=False)}\n\n"
        f"Full execution log for context:\n{json.dumps(context.get('report_logs'), ensure_ascii=False)}\n"
    )


def _guard_violation(tool_name, tool_input, repo_root):
    """Shared guard logic: returns a deny reason string, or None to allow.
    Denies any Bash command mentioning git, and any Write/Edit target outside
    ai/ or automation/."""
    if tool_name == "Bash":
        cmd = str((tool_input or {}).get("command", ""))
        if re.search(r"\bgit\b", cmd):
            return "git is not permitted in self-heal sessions"
        return None
    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = str((tool_input or {}).get("file_path", ""))
        abs_path = path if os.path.isabs(path) else os.path.join(repo_root, path)
        abs_path = os.path.abspath(abs_path)
        allowed_roots = [os.path.join(repo_root, d) for d in ALLOWED_EDIT_DIRS]
        if not any(
            abs_path == root or abs_path.startswith(root + os.sep) for root in allowed_roots
        ):
            return f"self-heal may only edit files under {'/'.join(ALLOWED_EDIT_DIRS)}/"
        return None
    return None


async def _pre_tool_use_guard(hook_input, _tool_use_id, _context, repo_root):
    """PreToolUse hook: the guardrail layer beyond the prompt instructions.

    Deliberately a hook rather than `can_use_tool`: the SDK auto-approves any
    tool named in `allowed_tools` BEFORE consulting can_use_tool (it emits
    CanUseToolShadowedWarning saying exactly that), so the callback never ran and
    the git/edit-path restrictions were silently inert. A PreToolUse hook is
    always consulted.
    """
    tool_name = hook_input.get("tool_name") or ""
    tool_input = hook_input.get("tool_input") or {}
    reason = _guard_violation(tool_name, tool_input, repo_root)
    if reason:
        print(f"   🛡️ self-heal guard DENIED {tool_name}: {reason}")
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    return {}


async def _stream_single_prompt(text):
    """`can_use_tool` only works in the SDK's streaming mode, which requires the
    prompt to be an AsyncIterable of message dicts — passing a plain string
    raises "can_use_tool callback requires streaming mode. Please provide prompt
    as an AsyncIterable instead of a string." and self-heal never even starts.
    This yields the one user message the old string prompt carried."""
    yield {
        "type": "user",
        "message": {"role": "user", "content": text},
        "parent_tool_use_id": None,
        "session_id": "self-heal",
    }


async def _run_self_heal_async(context, repo_root, timeout_s, max_turns, max_budget_usd):
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, ResultMessage, query

    async def _guard(hook_input, tool_use_id, context):
        return await _pre_tool_use_guard(hook_input, tool_use_id, context, repo_root)

    options = ClaudeAgentOptions(
        cwd=repo_root,
        allowed_tools=["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        permission_mode="acceptEdits",  # required: this session runs unattended
        system_prompt=SYSTEM_PROMPT,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        output_format=SELF_HEAL_OUTPUT_SCHEMA,
        hooks={
            "PreToolUse": [
                HookMatcher(matcher="Bash|Write|Edit|MultiEdit|NotebookEdit", hooks=[_guard])
            ]
        },
    )

    result_message = None
    async with asyncio.timeout(timeout_s):
        async for message in query(
            prompt=_stream_single_prompt(_build_user_prompt(context)), options=options
        ):
            if isinstance(message, ResultMessage):
                result_message = message

    if result_message is None:
        return {
            "fixed": False,
            "files_changed": [],
            "summary": "Self-heal agent produced no result message",
        }
    if result_message.is_error:
        return {
            "fixed": False,
            "files_changed": [],
            "summary": f"Self-heal agent errored: {result_message.result or result_message.stop_reason}",
        }
    structured = result_message.structured_output
    if isinstance(structured, dict) and "fixed" in structured:
        return structured
    return {
        "fixed": False,
        "files_changed": [],
        "summary": f"Self-heal agent returned no structured output: {(result_message.result or '')[:300]}",
    }


def run_self_heal(context, *, repo_root, timeout_s=300, max_turns=30, max_budget_usd=2.0):
    """Never raises: a bug in this new feature must never take down an otherwise-
    working smoke run. Runs one one-shot claude_agent_sdk session with Read/Edit/Write/
    Grep/Glob/Bash tools, scoped via a PreToolUse hook to editing only ai/automation and
    never touching git. On a reported fix, deterministically writes the memory entry
    from the agent's structured fields (not left to the agent to free-write)."""
    if shutil.which("claude") is None:
        return {
            "fixed": False,
            "files_changed": [],
            "summary": "claude CLI not found on PATH; self-heal skipped",
        }
    try:
        result = asyncio.run(
            _run_self_heal_async(context, repo_root, timeout_s, max_turns, max_budget_usd)
        )
    except TimeoutError:
        return {
            "fixed": False,
            "files_changed": [],
            "summary": f"Self-heal agent timed out after {timeout_s}s",
        }
    except Exception as e:
        return {"fixed": False, "files_changed": [], "summary": f"Self-heal internal error: {str(e)[:300]}"}

    if result.get("fixed"):
        try:
            _write_memory_entry(context, result)
        except Exception as e:
            result["summary"] = f"{result.get('summary', '')} (memory write failed: {str(e)[:150]})"
    return result


def _slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:50]


def _write_memory_entry(context, result):
    """Deterministically author the memory .md + MEMORY.md index line from the agent's
    structured fields. Kept in plain Python (not delegated to the agent's own Bash/
    Write tools) so the frontmatter format stays consistent regardless of how the model
    phrases things, and the write stays inside this process rather than the agent
    reaching outside its intended ai/automation scope."""
    os.makedirs(MEMORY_DIR, exist_ok=True)
    feature = context.get("feature") or "unknown-feature"
    summary_slug = _slugify(result.get("summary", "")) or "fix"
    slug = f"feedback_self_heal_{_slugify(feature)}_{summary_slug}"[:80].rstrip("-")
    today = time.strftime("%Y-%m-%d")
    description = (result.get("summary") or "Self-heal fix").replace('"', "'")[:140]
    files_lines = "\n".join(f"- `{f}`" for f in result.get("files_changed") or []) or "- (none reported)"

    body = f"""---
name: {slug}
description: "{description}"
metadata:
  type: feedback
---

Self-heal agent auto-fixed a smoke-test failure for feature "{feature}", testcase
"{context.get('testcase', '')}".

**Root cause:** {result.get('root_cause') or '(not provided)'}

**Fix:** {result.get('fix_description') or '(not provided)'}

**Files changed:**
{files_lines}

**Why:** Self-heal agent's own diagnosis, verified by re-running the failing action
plan step (or a short prefix ending at it) against the live browser before reporting
fixed=true.

**How to apply:** {result.get('how_to_apply') or '(not provided)'}
"""
    with open(os.path.join(MEMORY_DIR, f"{slug}.md"), "w", encoding="utf-8") as f:
        f.write(body)

    title = str(feature).replace("_", " ").title() if feature else "Self-Heal"
    index_line = f"- [{title} Self-Heal Fix]({slug}.md) — {description}. Fixed {today}.\n"
    with open(os.path.join(MEMORY_DIR, "MEMORY.md"), "a", encoding="utf-8") as f:
        f.write(index_line)

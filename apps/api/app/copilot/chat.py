"""One question, answered: the model asks for tools until it has what it needs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.copilot import playbook
from app.copilot.gateway import Gateway
from app.copilot.tools import ToolContext, run_tool, tool_specs

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)

SYSTEM_RULES = """\
You are the Organic IQ copilot, an internal assistant for SMA Marketing staff. You work on one client at a time: {client_name} ({domain}). Today is {today}.

How you work:
- Every figure, date, URL and status you state must come from a tool result in this conversation. If a tool did not return it, say you do not have it. Never estimate or fill in a number.
- The Decision Engine decides the monthly plan. You read its saved record and explain it. Do not invent actions, change the constraint, or argue with the engine; if you think something is off, say what and why and recommend someone review it.
- Before explaining a drop or a problem, check data health. A stale or disconnected source is a likelier cause than a ranking change, and the engine withholds a client whose data is more than 7 days stale.
- Quote the month and the data-through date when you cite the plan.
- You cannot change anything yet. When an action is warranted, say precisely what to do and where (assign this slot, re-run that sync); staff will do it.
- Be brief. Lead with the answer, then the evidence. Plain sentences, no filler.

Reference: the Organic IQ process.

{process}
"""


def system_prompt(client_name: str, domain: str, today: date | None = None) -> str:
    return SYSTEM_RULES.format(
        client_name=client_name,
        domain=domain,
        today=(today or date.today()).isoformat(),
        process=playbook.core_text(),
    )


@dataclass
class ChatResult:
    reply: str
    #: Every message this turn produced, in order, ready to store:
    #: assistant tool calls, tool results, and the final answer.
    messages: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0
    exhausted: bool = False


def clean_reply(text: str | None) -> str:
    return _THINK.sub("", text or "").strip()


def run_chat(
    ctx: ToolContext,
    gateway: Gateway,
    history: list[dict[str, Any]],
    user_message: str,
    *,
    max_rounds: int,
    today: date | None = None,
) -> ChatResult:
    """`history` is the stored conversation so far (user / assistant / tool
    messages, without the system prompt, which is rebuilt every turn so the
    date and playbook are current)."""
    specs = tool_specs()
    convo: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": system_prompt(ctx.client.client_name, ctx.client.domain, today),
        },
        *history,
        {"role": "user", "content": user_message},
    ]
    produced: list[dict[str, Any]] = []

    for round_no in range(1, max_rounds + 1):
        message = gateway.complete(convo, specs)
        calls = message.get("tool_calls") or []
        if not calls:
            reply = clean_reply(message.get("content"))
            produced.append({"role": "assistant", "content": reply})
            return ChatResult(reply=reply, messages=produced, rounds=round_no)

        assistant = {
            "role": "assistant",
            "content": clean_reply(message.get("content")) or None,
            "tool_calls": calls,
        }
        convo.append(assistant)
        produced.append(assistant)
        for call in calls:
            fn = call.get("function") or {}
            result = run_tool(ctx, fn.get("name", ""), fn.get("arguments"))
            tool_msg = {
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": json.dumps(result, default=str),
            }
            convo.append(tool_msg)
            produced.append(tool_msg)

    reply = (
        "I could not finish that in the allowed number of lookups. "
        "Try a narrower question, for example one month or one data source."
    )
    produced.append({"role": "assistant", "content": reply})
    return ChatResult(reply=reply, messages=produced, rounds=max_rounds, exhausted=True)

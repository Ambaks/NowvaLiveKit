"""LLM script generation for the choreographed coaching demo."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from agent.services.coaching_constants import COACHING_PERSONA

logger = logging.getLogger(__name__)

NARRATION_TIMEOUT_SECONDS = 8.0
DEMO_LINE_WORD_LIMIT = 18

_SCRIPT_PROMPT = (
    f"{COACHING_PERSONA} "
    "You just watched the user do 1 assessment squat and found the form issues listed "
    "below. The screen will show their own skeleton with each correction animated, one "
    "issue at a time.\n"
    "Return ONLY a JSON object — no markdown, no extra text — shaped exactly like:\n"
    '{"intro": "...", "cue_lines": ["..."], "outro": "..."}\n'
    "Rules: intro is one short sentence inviting them to look at the screen. cue_lines "
    "has exactly one line per issue, in the given order, each under "
    f"{DEMO_LINE_WORD_LIMIT} words, naming the fix and referencing what is moving on "
    "screen. outro is one short sentence telling them to squat again with "
    "these fixes. Sound human and encouraging, never robotic."
)


class DemoScript(BaseModel):
    intro: str
    cue_lines: list[str]
    outro: str


def build_fallback_script(cues: list[dict]) -> DemoScript:
    cue_lines = [
        f"Next one — {cue.get('magnitude_text', 'a small adjustment')}. "
        "Watch the highlighted joints."
        for cue in cues
    ]
    return DemoScript(
        intro="Take a look at the screen real quick. This is you at the bottom of your squat.",
        cue_lines=cue_lines,
        outro="Easy as that!",
    )


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_demo_script(raw_text: str, expected_count: int) -> DemoScript | None:
    try:
        payload = json.loads(_strip_code_fences(raw_text))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    intro = payload.get("intro")
    cue_lines = payload.get("cue_lines")
    outro = payload.get("outro")

    if not isinstance(intro, str) or not intro.strip():
        return None
    if not isinstance(outro, str) or not outro.strip():
        return None
    if not isinstance(cue_lines, list) or len(cue_lines) != expected_count:
        return None
    if not all(isinstance(line, str) and line.strip() for line in cue_lines):
        return None

    return DemoScript(intro=intro.strip(), cue_lines=[line.strip() for line in cue_lines], outro=outro.strip())


async def generate_demo_lines(llm_obj, cues: list[dict]) -> DemoScript:
    """One LLM call producing the full demo script; deterministic fallback on any failure."""
    from livekit.agents import llm as lk_llm

    try:
        chat_ctx = lk_llm.ChatContext.empty()
        chat_ctx.add_message(role="system", content=_SCRIPT_PROMPT)
        chat_ctx.add_message(role="user", content=json.dumps(cues))

        response_text = ""
        async with llm_obj.chat(chat_ctx=chat_ctx) as stream:
            async for chunk in stream:
                if chunk.delta and chunk.delta.content:
                    response_text += chunk.delta.content

        script = parse_demo_script(response_text, expected_count=len(cues))
        if script is not None:
            return script
        logger.warning(
            f"[DEMO NARRATION] Script parse failed — using fallback. raw[:120]={response_text[:120]!r}"
        )
    except Exception:
        logger.exception("[DEMO NARRATION] LLM script generation failed — using fallback")

    return build_fallback_script(cues)

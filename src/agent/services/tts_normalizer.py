"""
Deterministic backstop that strips written-text artifacts from agent speech
before it reaches Cartesia TTS. Prompt rules are the primary defense; this
catches stragglers (emoji, markdown, unit symbols) that would otherwise be
read aloud. Inline tags like <break time="400ms"/> and [laughter] pass through.
"""

from __future__ import annotations

import re
from typing import AsyncIterable

# Emoji, pictographs, dingbats, flags, and joiners. Conservative ranges —
# arrows and math operators are handled by targeted replacements instead.
_EMOJI_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"  # emoticons, pictographs, transport, supplemental
    "☀-➿"          # misc symbols and dingbats
    "⬀-⯿"          # misc symbols and arrows (stars, circles)
    "︀-️"          # variation selectors
    "‍"                 # zero-width joiner
    "]+"
)

# Text emoticons like :) ;-) :D at a word boundary.
_EMOTICON_RE = re.compile(r"(?:^|(?<=\s))[:;]-?[)(DPpOo](?=\s|$|[.,!?])")

_MARKDOWN_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MARKDOWN_BULLET_RE = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)

_DIGIT_RANGE_RE = re.compile(r"(?<=\d)\s*[–—-]\s*(?=\d)")
_DIGIT_TIMES_RE = re.compile(r"(?<=\d)\s*[×]\s*")
_DIGIT_X_DIGIT_RE = re.compile(r"(?<=\d)x(?=\d)")
# Only score-style slashes ("84/100", "7/10") — never dates like 04/20/2023.
_SCORE_RE = re.compile(r"(?<=\d)/(?=100\b|10\b)")
_ARROW_RE = re.compile(r"\s*(?:->|→|⇒)\s*")


def normalize_tts_text(text: str) -> str:
    # Symbol expansions first, while the surrounding digits are intact.
    text = text.replace("°", " degrees")
    text = text.replace("%", " percent")
    text = _DIGIT_TIMES_RE.sub(" times ", text)
    text = _DIGIT_X_DIGIT_RE.sub(" by ", text)
    text = _DIGIT_RANGE_RE.sub(" to ", text)
    text = _SCORE_RE.sub(" out of ", text)
    text = _ARROW_RE.sub(" to ", text)

    # Written-text markup that TTS would read aloud.
    text = _MARKDOWN_HEADER_RE.sub("", text)
    text = _MARKDOWN_BULLET_RE.sub("", text)
    text = text.replace("**", "").replace("*", "").replace("`", "")
    text = re.sub(r"(?<=\w)_(?=\w)", " ", text)

    text = _EMOJI_RE.sub("", text)
    text = _EMOTICON_RE.sub("", text)

    # Speech has no paragraphs. Collapse newlines and space runs within the
    # chunk only — never trim chunk edges, or streamed words would join.
    text = text.replace("\n", " ")
    text = re.sub(r"  +", " ", text)
    return text


async def normalize_stream(text: AsyncIterable[str]) -> AsyncIterable[str]:
    async for chunk in text:
        cleaned = normalize_tts_text(chunk)
        if cleaned:
            yield cleaned

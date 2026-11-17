"""
Claude Vision agent — the creative core of the system.

Two functions:

1. analyze_photo(image_bytes, word_pool)
   - Receives a compressed photo + 25 candidate words
   - Claude selects the 3 (or N) words with the strongest visual connection
   - Returns: photo description, selected words, per-word anchors/cues, vivid story

2. enrich_photo(photo_description, word, definition)
   - No image needed — uses the saved description from analyze_photo
   - Finds a visual anchor for ONE additional word the user manually wants to add
   - Returns: visual_anchor, memory_cue

Image compression:
   iPhone photos are 4-8 MB. We compress to ~800px / 85% JPEG (~150-300 KB)
   before sending to Claude — plenty of detail for visual analysis.
"""

import base64
import io
import json
import logging
from typing import Optional

from functools import lru_cache

from kindle_srs.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, WORDS_PER_PHOTO

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _anthropic():
    import anthropic
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a visual memory architect with a vivid, precise imagination.
Your specialty: creating powerful mnemonic anchors by connecting vocabulary \
to real-world images. You find the unexpected, visceral, sensory connections \
that make words stick for years. You write with knife-sharp imagery — \
no vague metaphors, only concrete sensory detail.\
"""

_USER_ANALYZE = """\
I'm learning vocabulary by anchoring words to photos I take in my daily life.

Look at this photo carefully. I need you to:

1. Identify the key VISUAL elements — objects, textures, light, shadows, spatial \
relationships, colors, mood, anything a person standing there would notice.

2. From the word pool below, select exactly {n} words that have the STRONGEST \
possible connection to something LITERALLY VISIBLE in this photo. \
Prefer concrete, visceral connections over abstract ones. \
Skip words that would only connect loosely or metaphorically.

3. For each selected word:
   - visual_anchor: map it precisely to one visible element \
("the peeling yellow paint on the left wall → dilapidated")
   - memory_cue: one sharp sentence the user will never forget \
("whenever you see something unmaintained and crumbling, think: dilapidated")
   - brief_definition: core meaning in ≤10 words

4. Write a vivid story of 4-6 sentences set INSIDE this photo. \
The reader should feel like they are standing in the scene. \
Use ALL {n} selected words naturally — woven in, not forced. \
Make it slightly uncanny or emotionally charged: memories need an edge to stick.

WORD POOL:
{pool}

Return ONLY valid JSON, no markdown, no other text:
{{
  "photo_description": "one concrete sentence describing the scene",
  "selected_words": ["word1", "word2", "word3"],
  "cards": [
    {{
      "word": "word1",
      "visual_anchor": "...",
      "memory_cue": "...",
      "brief_definition": "..."
    }}
  ],
  "story": "..."
}}\
"""

_USER_ENRICH = """\
A user took a photo. Here is how it was described:

"{description}"

They want to add this vocabulary word to that photo's memory card:

Word: {word}
Definition: {definition}

Find the most vivid, concrete visual connection between this word and \
something likely visible in that scene. Then write a sharp memory cue.

Return ONLY valid JSON:
{{
  "visual_anchor": "specific visual element in the scene → word",
  "memory_cue": "one sentence rule the user will never forget"
}}\
"""


# ── Image compression ─────────────────────────────────────────────────────────

def _compress(image_bytes: bytes, max_px: int = 1200, quality: int = 85) -> bytes:
    """Resize to max_px on longest side and re-encode as JPEG."""
    from PIL import Image
    try:  # HEIC/HEIF support (iPhone default format)
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass  # pillow-heif not installed: HEIC files will fail

    img = Image.open(io.BytesIO(image_bytes))

    # Normalise to RGB (handles HEIC converted to JPEG, PNG with alpha, etc.)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > max_px:
        ratio = max_px / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    compressed = buf.getvalue()
    logger.debug(f"Image compressed: {len(image_bytes):,} → {len(compressed):,} bytes")
    return compressed


def _parse_json(raw: str) -> Optional[dict]:
    """Parse the model's JSON reply, tolerating code fences or a sentence around it."""
    raw = raw.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end < start:
        logger.error(f"No JSON object in reply: {raw[:200]}")
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}\nRaw: {raw[:400]}")
        return None
    return data if isinstance(data, dict) else None


def cards_in_pool(result: dict, word_pool: list[dict], limit: int) -> list[dict]:
    """Keep only cards whose word was actually offered, once each, up to `limit`.

    The model is asked to choose from the pool, but nothing forces it to, and a
    word from outside the pool could be one already assigned to another photo.
    """
    offered = {w["word"].strip().lower(): w["word"] for w in word_pool}
    kept, seen = [], set()
    for card in result.get("cards") or []:
        key = str(card.get("word", "")).strip().lower()
        if key in offered and key not in seen:
            seen.add(key)
            kept.append({**card, "word": offered[key]})
        if len(kept) == limit:
            break
    return kept


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_photo(image_bytes: bytes, word_pool: list[dict],
                  n_words: int = WORDS_PER_PHOTO) -> Optional[dict]:
    """
    Send a photo + word pool to Claude Vision.

    word_pool items must have: 'word', optionally 'definition', 'context'.

    Returns dict with keys:
        photo_description, selected_words, cards (list), story
    Returns None on failure.
    """
    compressed = _compress(image_bytes)
    b64 = base64.standard_b64encode(compressed).decode("utf-8")

    # Format the word pool for the prompt
    lines = []
    for w in word_pool:
        defn = w.get("definition") or "?"
        ctx = w.get("context", "")
        ctx_note = f' (e.g. "{ctx[:70]}")' if ctx else ""
        lines.append(f"- {w['word']}: {defn}{ctx_note}")
    pool_text = "\n".join(lines)

    prompt = _USER_ANALYZE.format(n=n_words, pool=pool_text)

    try:
        response = _anthropic().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1800,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        result = _parse_json(response.content[0].text)
        if result:
            logger.info(
                f"Agent selected: {result.get('selected_words', [])} "
                f"for photo ({len(compressed):,} bytes)"
            )
        return result

    except Exception as e:
        logger.error(f"Claude Vision error: {e}")
        return None


def enrich_photo(photo_description: str, word: str,
                 definition: str) -> Optional[dict]:
    """
    Find a visual anchor for ONE additional word given only the photo's
    text description (no image needed — cheaper and faster).

    Returns dict with keys: visual_anchor, memory_cue
    Returns None on failure.
    """
    prompt = _USER_ENRICH.format(
        description=photo_description,
        word=word,
        definition=definition or "?",
    )

    try:
        response = _anthropic().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json(response.content[0].text)

    except Exception as e:
        logger.error(f"Claude enrich error: {e}")
        return None

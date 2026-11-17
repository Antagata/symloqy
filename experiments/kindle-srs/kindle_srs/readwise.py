"""
Readwise API client.

Pulls both:
  - Kindle Vocabulary Builder words  (short highlights, 1-4 words)
  - Regular book highlights           (used as context sentences)

Uses cursor-based pagination and stores the last-synced timestamp in DB meta
so each run only fetches new items.
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

READWISE_BASE = "https://readwise.io/api/v2"


class ReadwiseClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {token}"})

    # ── Low-level pagination ──────────────────────────────────────────────────

    def _paginate(self, endpoint: str, params: dict | None = None) -> list[dict]:
        results = []
        url = f"{READWISE_BASE}/{endpoint}/"
        current_params = dict(params or {})
        current_params.setdefault("page_size", 1000)

        while url:
            resp = self.session.get(url, params=current_params)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("results", []))
            url = data.get("next")
            current_params = {}  # next URL already has params encoded

        return results

    # ── Books ─────────────────────────────────────────────────────────────────

    def get_books(self) -> dict[int, dict]:
        """Return a dict of book_id → book metadata."""
        books = self._paginate("books")
        return {b["id"]: b for b in books}

    # ── Highlights ────────────────────────────────────────────────────────────

    def get_highlights(self, updated_after: Optional[str] = None) -> list[dict]:
        params = {}
        if updated_after:
            params["updated__gt"] = updated_after
        return self._paginate("highlights", params)

    # ── Main sync: vocabulary + highlights ───────────────────────────────────

    def sync(self, last_synced: Optional[str] = None) -> tuple[list[dict], str]:
        """
        Fetch new items since last_synced (ISO datetime string).

        Returns:
            (items, latest_updated_at)
            items: list of dicts ready for database.upsert_word()
        """
        logger.info(f"Readwise sync — fetching highlights since: {last_synced or 'beginning'}")
        highlights = self.get_highlights(updated_after=last_synced)
        books = self.get_books()

        if not highlights:
            logger.info("No new highlights from Readwise.")
            return [], last_synced or ""

        # Track latest timestamp for next sync
        latest = max(h.get("updated", "") or "" for h in highlights)

        items = []
        for h in highlights:
            text = (h.get("text") or "").strip()
            if not text or len(text) > 200:
                # Skip empty or very long highlights (not vocabulary)
                continue

            book = books.get(h.get("book_id"), {})
            book_title = book.get("title", "") or ""
            source_type = _classify_source(text, book)

            items.append({
                "readwise_id":  str(h["id"]),
                "word":         text,
                "definition":   None,
                "ipa":          None,
                # Readwise stores user notes in the 'note' field — good context
                "context":      (h.get("note") or "").strip() or None,
                "source_book":  book_title,
                "source_type":  source_type,
            })

        vocab_count = sum(1 for i in items if i["source_type"] == "vocabulary")
        highlight_count = len(items) - vocab_count
        logger.info(
            f"Readwise: {len(highlights)} raw highlights → "
            f"{vocab_count} vocabulary + {highlight_count} highlights to import"
        )

        return items, latest


def _classify_source(text: str, book: dict) -> str:
    """
    Decide if a highlight is 'vocabulary' (single word / short phrase)
    or 'highlight' (longer passage used as context).
    """
    book_title = (book.get("title") or "").lower()
    word_count = len(text.split())

    # Kindle Vocabulary Builder items are always vocabulary
    if "vocabulary" in book_title and "kindle" in book_title:
        return "vocabulary"

    # Short items (≤4 words) from any source treated as vocabulary
    if word_count <= 4:
        return "vocabulary"

    return "highlight"

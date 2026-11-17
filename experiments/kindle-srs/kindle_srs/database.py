"""
Supabase database layer — mirrors the original SQLite interface exactly.

All functions accept `conn` as first argument (ignored; the real client is
module-level). Callers that were written for SQLite work unchanged.

Tables (srs_* prefix, same Supabase project as STE):
  srs_photos        — iPhone photo metadata
  srs_words         — vocabulary from Readwise / manual import
  srs_cards         — photo + word pairing with visual anchor + memory cue
  srs_sessions      — daily session (2 photos, stories)
  srs_session_cards — junction: session <-> cards
  srs_reviews       — future Anki-like review log
  srs_meta          — key-value store for sync cursors
"""

import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client():
    """Supabase client with the service-role key (bypasses RLS), created on first use."""
    from supabase import create_client
    from kindle_srs.config import SUPABASE_URL, SUPABASE_SERVICE_KEY, require
    require(("SUPABASE_URL", "SUPABASE_SERVICE_KEY"))
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


class _Lazy:
    def __getattr__(self, name):
        return getattr(_client(), name)


_supabase = _Lazy()


def ilike_exact(text: str) -> str:
    """Escape LIKE wildcards so ilike() does a case-insensitive *exact* match."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_conn(db_path: str = None):
    """Return the Supabase client.

    Every function below still takes `conn` first: the module started on SQLite
    and kept that interface when it moved to Supabase. The argument is unused.
    """
    return _supabase


# ── Meta (key-value store for sync cursors etc.) ─────────────────────────────

def get_meta(conn, key: str) -> Optional[str]:
    result = _supabase.table("srs_meta").select("value").eq("key", key).maybe_single().execute()
    return result.data["value"] if result.data else None


def set_meta(conn, key: str, value: str):
    _supabase.table("srs_meta").upsert({"key": key, "value": value}).execute()


# ── Words ─────────────────────────────────────────────────────────────────────

def upsert_word(conn, word: dict) -> int:
    """Insert or ignore a word. Returns the word's DB id."""
    word_text = word.get("word", "").strip()
    payload = {
        "word":        word_text,
        "definition":  word.get("definition"),
        "ipa":         word.get("ipa"),
        "context":     word.get("context"),
        "source_book": word.get("source_book"),
        "source_type": word.get("source_type"),
        "readwise_id": word.get("readwise_id"),
    }
    # ignore_duplicates=True → equivalent to INSERT OR IGNORE (no overwrite)
    _supabase.table("srs_words").upsert(
        payload, on_conflict="word", ignore_duplicates=True
    ).execute()
    result = _supabase.table("srs_words").select("id").ilike("word", ilike_exact(word_text)).maybe_single().execute()
    return result.data["id"]


def get_candidate_words(conn, limit: int = 25) -> list[dict]:
    """
    Return unassigned short vocabulary words for Claude to choose from.
    Excludes long highlight sentences (> 60 chars).
    Prioritises vocabulary items, then shortest words first.
    """
    result = _supabase.table("srs_words") \
        .select("id, word, definition, context, source_book, source_type, imported_at") \
        .eq("status", "new") \
        .limit(1000) \
        .execute()
    rows = [r for r in result.data if len(r.get("word", "")) <= 60]
    rows.sort(key=lambda r: (
        0 if r.get("source_type") == "vocabulary" else 1,
        len(r.get("word", "")),
        r.get("imported_at", ""),
    ))
    return rows[:limit]


def mark_words_assigned(conn, word_ids: list[int]):
    if not word_ids:
        return
    _supabase.table("srs_words").update({"status": "assigned"}).in_("id", word_ids).execute()


def mark_words_consolidated(conn, words: list[str]):
    """Mark specific words (by text) as consolidated/mastered."""
    if not words:
        return
    _supabase.table("srs_words").update({"status": "consolidated"}).in_("word", words).execute()


def mark_all_new_consolidated(conn):
    """Mark ALL 'new' words as consolidated (fresh-start command)."""
    _supabase.table("srs_words").update({"status": "consolidated"}).eq("status", "new").execute()


def get_word_by_text(conn, word: str) -> Optional[dict]:
    """Case-insensitive exact lookup."""
    result = _supabase.table("srs_words") \
        .select("*") \
        .ilike("word", ilike_exact(word.strip())) \
        .maybe_single() \
        .execute()
    return result.data if result.data else None


def get_words_by_status(conn, status: str) -> list[dict]:
    """Return all words with the given status, shortest first."""
    result = _supabase.table("srs_words") \
        .select("id, word, source_type, source_book") \
        .eq("status", status) \
        .order("word") \
        .execute()
    rows = result.data or []
    rows.sort(key=lambda r: len(r.get("word", "")))
    return rows


def total_words(conn) -> int:
    result = _supabase.table("srs_words").select("id", count="exact").execute()
    return result.count or 0


def new_words_count(conn) -> int:
    result = _supabase.table("srs_words").select("id", count="exact").eq("status", "new").execute()
    return result.count or 0


# ── Photos ─────────────────────────────────────────────────────────────────────

def upsert_photo(conn, filename: str, drive_file_id: str) -> int:
    _supabase.table("srs_photos").upsert(
        {"filename": filename, "drive_file_id": drive_file_id},
        on_conflict="filename",
        ignore_duplicates=True,
    ).execute()
    result = _supabase.table("srs_photos").select("id").eq("filename", filename).maybe_single().execute()
    return result.data["id"]


def get_unprocessed_photos(conn, limit: int = 2) -> list[dict]:
    result = _supabase.table("srs_photos") \
        .select("id, filename, drive_file_id") \
        .eq("processed", False) \
        .order("uploaded_at") \
        .limit(limit) \
        .execute()
    return result.data or []


def get_photo_by_id(conn, photo_id: int) -> Optional[dict]:
    result = _supabase.table("srs_photos").select("*").eq("id", photo_id).maybe_single().execute()
    return result.data if result.data else None


def mark_photo_processed(conn, photo_id: int, description: str):
    _supabase.table("srs_photos").update({"processed": True, "description": description}).eq("id", photo_id).execute()


def get_all_photos(conn) -> list[dict]:
    result = _supabase.table("srs_photos") \
        .select("*, srs_cards(id)") \
        .order("uploaded_at", desc=True) \
        .execute()
    photos = []
    for row in result.data or []:
        card_count = len(row.pop("srs_cards", []) or [])
        row["card_count"] = card_count
        photos.append(row)
    return photos


def increment_photo_usage(conn, photo_id: int):
    current = _supabase.table("srs_photos").select("times_used").eq("id", photo_id).maybe_single().execute()
    if current.data:
        _supabase.table("srs_photos").update(
            {"times_used": (current.data.get("times_used") or 0) + 1}
        ).eq("id", photo_id).execute()


# ── Cards ──────────────────────────────────────────────────────────────────────

def insert_card(conn, photo_id: int, word_id: int,
                visual_anchor: str, memory_cue: str,
                manually_added: bool = False) -> int:
    _supabase.table("srs_cards").upsert(
        {
            "photo_id":      photo_id,
            "word_id":       word_id,
            "visual_anchor": visual_anchor,
            "memory_cue":    memory_cue,
            "manually_added": manually_added,
        },
        on_conflict="photo_id,word_id",
        ignore_duplicates=True,
    ).execute()
    result = _supabase.table("srs_cards") \
        .select("id") \
        .eq("photo_id", photo_id) \
        .eq("word_id", word_id) \
        .maybe_single() \
        .execute()
    return result.data["id"]


def get_cards_for_photo(conn, photo_id: int) -> list[dict]:
    result = _supabase.table("srs_cards") \
        .select("id, visual_anchor, memory_cue, manually_added, srs_words(word, definition, ipa, context, source_book)") \
        .eq("photo_id", photo_id) \
        .order("created_at") \
        .execute()
    cards = []
    for row in result.data or []:
        word_data = row.pop("srs_words", {}) or {}
        row.update(word_data)
        cards.append(row)
    return cards


def total_cards(conn) -> int:
    result = _supabase.table("srs_cards").select("id", count="exact").execute()
    return result.count or 0


# ── Sessions ───────────────────────────────────────────────────────────────────

def create_session(conn, session_date: str,
                   photo1_id: int, photo2_id: int,
                   story1: str, story2: str) -> int:
    payload = {
        "session_date": session_date,
        "photo1_id":    photo1_id,
        "photo2_id":    photo2_id,
        "story_photo1": story1,
        "story_photo2": story2,
    }
    _supabase.table("srs_sessions").upsert(payload, on_conflict="session_date").execute()
    result = _supabase.table("srs_sessions") \
        .select("id") \
        .eq("session_date", session_date) \
        .maybe_single() \
        .execute()
    return result.data["id"]


def link_session_cards(conn, session_id: int, card_ids: list[int]):
    if not card_ids:
        return
    rows = [{"session_id": session_id, "card_id": cid} for cid in card_ids]
    _supabase.table("srs_session_cards").upsert(
        rows, on_conflict="session_id,card_id", ignore_duplicates=True
    ).execute()


def mark_email_sent(conn, session_id: int):
    _supabase.table("srs_sessions").update({"email_sent": True}).eq("id", session_id).execute()


def session_exists(conn, session_date: str) -> bool:
    result = _supabase.table("srs_sessions") \
        .select("id") \
        .eq("session_date", session_date) \
        .maybe_single() \
        .execute()
    return result.data is not None


def session_has_cards(conn, session_date: str) -> bool:
    """Returns True only if a session exists AND has at least one card linked."""
    result = _supabase.table("srs_sessions") \
        .select("id, srs_session_cards(card_id)") \
        .eq("session_date", session_date) \
        .maybe_single() \
        .execute()
    if not result.data:
        return False
    return len(result.data.get("srs_session_cards", []) or []) > 0


def delete_empty_session(conn, session_date: str):
    """
    Remove an empty session (no cards) and reset its photos to unprocessed
    so they will be picked up and re-analyzed on the next run.
    """
    result = _supabase.table("srs_sessions") \
        .select("id, photo1_id, photo2_id") \
        .eq("session_date", session_date) \
        .maybe_single() \
        .execute()
    if not result.data:
        return

    session = result.data
    for photo_id in [session.get("photo1_id"), session.get("photo2_id")]:
        if not photo_id:
            continue
        cards = _supabase.table("srs_cards").select("id", count="exact").eq("photo_id", photo_id).execute()
        if not cards.count:
            _supabase.table("srs_photos").update({"processed": False}).eq("id", photo_id).execute()

    _supabase.table("srs_sessions").delete().eq("id", session["id"]).execute()

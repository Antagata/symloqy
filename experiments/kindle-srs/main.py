"""
KindleSRS v2 — Visual Memory System
====================================
Entry point for the daily automated run (cron or manual).

Steps:
  1. Connect to Supabase (srs_* tables, see schema.sql)
  2. Sync new words from Readwise (vocabulary + highlights)
  3. Register new photos from a Google Drive folder (read only)
  4. Run today's session: Claude Vision → cards + stories
  5. Send an HTML email (no image, just stories + anchors + cues)
"""

import logging
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")



def main():
    from kindle_srs import database as db
    from kindle_srs.readwise import ReadwiseClient
    from kindle_srs.session import sync_photos, run_session
    from kindle_srs.email_sender import send_email
    from kindle_srs.config import READWISE_TOKEN, require

    require()

    today = date.today().isoformat()
    logger.info(f"=== KindleSRS daily run — {today} ===")

    # ── 1. Database ───────────────────────────────────────────────────────────
    conn = db.get_conn()

    # ── 2. Readwise sync ──────────────────────────────────────────────────────
    last_synced = db.get_meta(conn, "readwise_last_synced")
    rw = ReadwiseClient(READWISE_TOKEN)

    try:
        items, latest = rw.sync(last_synced=last_synced)
        imported = 0
        for item in items:
            if item.get("word"):
                db.upsert_word(conn, item)
                imported += 1
        if imported:
            logger.info(f"Readwise: imported {imported} new word(s).")
        if latest:
            db.set_meta(conn, "readwise_last_synced", latest)
    except Exception as e:
        logger.error(f"Readwise sync failed: {e}")

    logger.info(
        f"DB stats: {db.total_words(conn)} total words, "
        f"{db.new_words_count(conn)} unassigned, "
        f"{db.total_cards(conn)} cards."
    )

    # ── 3. Photo sync (Drive → DB registry, read-only from Drive) ────────────
    try:
        sync_photos(conn)
    except Exception as e:
        logger.error(f"Photo sync failed: {e}")

    # ── 4. Session ────────────────────────────────────────────────────────────
    photo_blocks = run_session(conn)
    conn.close()

    if not photo_blocks:
        logger.warning(
            "No session generated today — either no unprocessed photos "
            "or a session already ran. Nothing to email."
        )
        return

    # ── 5. Email ──────────────────────────────────────────────────────────────
    try:
        send_email(today, photo_blocks)
    except Exception as e:
        logger.error(f"Email failed: {e}")
        sys.exit(1)

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()

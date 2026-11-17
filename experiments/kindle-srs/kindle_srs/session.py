"""
Daily session orchestrator.

Flow for each run:
  1. Sync new photos from Drive → register in DB
  2. Pick PHOTOS_PER_SESSION unprocessed photos
  3. For each photo:
       a. Download + compress
       b. Pull candidate word pool from DB
       c. Call Claude Vision agent → description, selected words, story, cards
       d. Save cards + mark words assigned
       e. Mark photo processed
  4. Build email payload (description + story + cards per photo)
  5. Return payload (main.py sends the email)
"""

import logging
from datetime import date

from kindle_srs import database as db
from kindle_srs import drive, agent
from kindle_srs.config import (
    DRIVE_PHOTOS_FOLDER,
    PHOTOS_PER_SESSION,
    WORDS_PER_PHOTO,
    CANDIDATE_POOL_SIZE,
)

logger = logging.getLogger(__name__)


def sync_photos(conn, known_filenames: set | None = None) -> int:
    """
    Check Drive for new photos not yet in DB, register them.
    Returns count of newly registered photos.
    """
    if known_filenames is None:
        known_filenames = {p["filename"] for p in db.get_all_photos(conn)}

    drive_photos = drive.list_drive_photos(DRIVE_PHOTOS_FOLDER)
    new_count = 0

    for file_id, filename in drive_photos:
        if filename not in known_filenames:
            db.upsert_photo(conn, filename, file_id)
            new_count += 1

    if new_count:
        logger.info(f"Registered {new_count} new photo(s) from Drive.")
    return new_count


def run_session(conn) -> list[dict] | None:
    """
    Process PHOTOS_PER_SESSION unprocessed photos.

    Returns a list of photo_blocks for the email, or None if
    not enough unprocessed photos are available.
    Each block: { description, story, cards: [{word, visual_anchor, memory_cue,
                                               definition, brief_definition}] }
    """
    today = date.today().isoformat()

    if db.session_exists(conn, today):
        if db.session_has_cards(conn, today):
            logger.info(f"Session already exists for {today} with cards, skipping.")
            return None
        else:
            # Previous run created an empty session (e.g. word-matching failed).
            # Delete it so we can retry cleanly today.
            logger.info(f"Found empty session for {today}, retrying.")
            db.delete_empty_session(conn, today)

    photos = db.get_unprocessed_photos(conn, limit=PHOTOS_PER_SESSION)

    if len(photos) < PHOTOS_PER_SESSION:
        logger.warning(
            f"Only {len(photos)} unprocessed photo(s) available "
            f"(need {PHOTOS_PER_SESSION}). "
            "Upload more photos to the Drive photos folder."
        )
        if not photos:
            return None
        # Proceed with however many we have

    photo_blocks = []
    session_photo_ids = []
    session_stories = []
    all_card_ids = []

    for photo_meta in photos:
        photo_id = photo_meta["id"]
        filename = photo_meta["filename"]
        file_id = photo_meta["drive_file_id"]

        logger.info(f"Processing photo: {filename}")

        # Download image
        try:
            image_bytes = drive.download_file(file_id)
        except Exception as e:
            logger.error(f"Could not download {filename}: {e}")
            continue

        # Get candidate words (not yet assigned to any photo)
        candidates = db.get_candidate_words(conn, limit=CANDIDATE_POOL_SIZE)
        if len(candidates) < WORDS_PER_PHOTO:
            logger.warning(
                f"Only {len(candidates)} unassigned word(s) available. "
                "Import more words from Readwise."
            )
            if not candidates:
                continue

        # Call Claude Vision
        result = agent.analyze_photo(image_bytes, candidates, n_words=WORDS_PER_PHOTO)
        if not result:
            logger.error(f"Agent returned no result for {filename}")
            continue

        description = result.get("photo_description", filename)
        story = result.get("story", "")
        agent_cards = agent.cards_in_pool(result, candidates, limit=WORDS_PER_PHOTO)
        by_word = {c["word"]: c for c in candidates}

        card_ids = []
        assigned_ids = []
        email_cards = []

        for card_data in agent_cards:
            word_text = card_data["word"]
            word_row = by_word[word_text]   # candidates already carry id + definition

            card_id = db.insert_card(
                conn,
                photo_id=photo_id,
                word_id=word_row["id"],
                visual_anchor=card_data.get("visual_anchor", ""),
                memory_cue=card_data.get("memory_cue", ""),
            )
            card_ids.append(card_id)
            assigned_ids.append(word_row["id"])

            email_cards.append({
                "word":          word_text,
                "visual_anchor": card_data.get("visual_anchor", ""),
                "memory_cue":    card_data.get("memory_cue", ""),
                "definition":    word_row.get("definition") or card_data.get("brief_definition", ""),
                "brief_definition": card_data.get("brief_definition", ""),
            })

        if not email_cards:
            logger.error(f"No usable cards for {filename}: the model picked no words from the pool.")
            continue

        # Mark words as assigned so they don't appear in future pools
        db.mark_words_assigned(conn, assigned_ids)

        # Mark photo as processed
        db.mark_photo_processed(conn, photo_id, description)
        db.increment_photo_usage(conn, photo_id)

        session_photo_ids.append(photo_id)
        session_stories.append(story)
        all_card_ids.extend(card_ids)

        photo_blocks.append({
            "description": description,
            "story":       story,
            "cards":       email_cards,
        })

        logger.info(
            f"Photo '{filename}' → {len(email_cards)} cards: "
            f"{[c['word'] for c in email_cards]}"
        )

    if not photo_blocks:
        return None

    # A session row has two photo slots (PHOTOS_PER_SESSION is capped at 2).
    # With one photo, the second slot repeats it and its story is empty.
    session_id = db.create_session(
        conn,
        session_date=today,
        photo1_id=session_photo_ids[0],
        photo2_id=session_photo_ids[-1],
        story1=session_stories[0],
        story2=session_stories[1] if len(session_stories) > 1 else "",
    )
    db.link_session_cards(conn, session_id, all_card_ids)

    total_new = db.new_words_count(conn)
    total_cards = db.total_cards(conn)
    logger.info(
        f"Session {today} saved. "
        f"Cards this session: {len(all_card_ids)}. "
        f"Total cards: {total_cards}. "
        f"Words remaining: {total_new}."
    )

    return photo_blocks

"""
enrich.py — CLI tool to manually add more words to an existing photo card.

Usage:
  python enrich.py                    # interactive mode
  python enrich.py --photo-id 3 --word "ephemeral"
  python enrich.py --list             # list all photos with card counts

When you notice that a photo could anchor more words than Claude initially
selected (e.g. a rich street scene with a dozen visual details), use this
tool to add them. Claude will find the visual connection using the saved
photo description — no need to re-download the image.
"""

import argparse
import logging
import sys

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("enrich")


def get_conn():
    from kindle_srs import database as db
    return db.get_conn(), None


def list_photos(conn):
    from kindle_srs import database as db

    photos = db.get_all_photos(conn)
    if not photos:
        print("No photos in database yet.")
        return

    print(f"\n{'ID':>4}  {'Cards':>5}  {'Used':>4}  Description / Filename")
    print("─" * 72)
    for p in photos:
        desc = p.get("description") or p.get("filename") or "—"
        desc = desc[:55]
        proc = "✓" if p["processed"] else "·"
        print(f"{p['id']:>4}  {p['card_count']:>5}  {p['times_used']:>4}  {proc} {desc}")
    print()


def show_photo(conn, photo_id: int):
    from kindle_srs import database as db

    row = db.get_photo_by_id(conn, photo_id)
    if not row:
        print(f"Photo ID {photo_id} not found.")
        return
    cards = db.get_cards_for_photo(conn, photo_id)

    print(f"\nPhoto #{photo_id}: {row['filename']}")
    print(f"Description: {row['description'] or '(not processed yet)'}")
    print(f"\nCurrent cards ({len(cards)}):")
    for c in cards:
        tag = " [manual]" if c["manually_added"] else ""
        print(f"  · {c['word']}{tag}")
        print(f"      ↳ {c['visual_anchor']}")
        print(f"      💡 {c['memory_cue']}")
    print()


def add_word_to_photo(conn, db_path: str, photo_id: int, word_text: str):
    from kindle_srs import database as db, agent as ag

    # Get photo description
    row = db.get_photo_by_id(conn, photo_id)
    if not row:
        print(f"Photo ID {photo_id} not found.")
        return
    if not row["processed"] or not row["description"]:
        print("This photo hasn't been processed yet (no Claude description). Run main.py first.")
        return

    # Get or create the word
    word_row = db.get_word_by_text(conn, word_text)
    if not word_row:
        print(f"Word '{word_text}' not in database. Adding with empty definition.")
        db.upsert_word(conn, {
            "word": word_text,
            "definition": None,
            "ipa": None,
            "context": None,
            "source_book": "manual",
            "source_type": "manual",
            "readwise_id": None,
        })
        word_row = db.get_word_by_text(conn, word_text)

    definition = word_row.get("definition") or ""

    print(f"\nAsking Claude to connect '{word_text}' to this scene...")
    print(f"Scene: {row['description']}\n")

    result = ag.enrich_photo(
        photo_description=row["description"],
        word=word_text,
        definition=definition,
    )

    if not result:
        print("Claude returned no result. Try again.")
        return

    visual_anchor = result.get("visual_anchor", "")
    memory_cue = result.get("memory_cue", "")

    print(f"  ↳ {visual_anchor}")
    print(f"  💡 {memory_cue}")

    confirm = input("\nSave this card? [Y/n] ").strip().lower()
    if confirm in ("", "y", "yes"):
        db.insert_card(
            conn,
            photo_id=photo_id,
            word_id=word_row["id"],
            visual_anchor=visual_anchor,
            memory_cue=memory_cue,
            manually_added=True,
        )
        db.mark_words_assigned(conn, [word_row["id"]])
        print(f"✓ Card saved.")
    else:
        print("Cancelled.")


def interactive(conn, db_path: str):
    print("\n=== KindleSRS Enrichment Tool ===")
    list_photos(conn)

    photo_id = input("Enter photo ID to enrich (or q to quit): ").strip()
    if photo_id.lower() == "q":
        return
    try:
        photo_id = int(photo_id)
    except ValueError:
        print("Invalid ID.")
        return

    show_photo(conn, photo_id)

    while True:
        word = input("Word to add (or q to quit): ").strip()
        if word.lower() == "q":
            break
        if word:
            add_word_to_photo(conn, db_path, photo_id, word)


def main():
    parser = argparse.ArgumentParser(description="Manually enrich photo vocabulary cards.")
    parser.add_argument("--list",     action="store_true", help="List all photos")
    parser.add_argument("--show",     type=int, metavar="PHOTO_ID", help="Show cards for a photo")
    parser.add_argument("--photo-id", type=int, help="Photo ID to enrich")
    parser.add_argument("--word",     type=str, help="Word to add to the photo")
    args = parser.parse_args()

    conn, db_path = get_conn()

    if args.list:
        list_photos(conn)
    elif args.show:
        show_photo(conn, args.show)
    elif args.photo_id and args.word:
        add_word_to_photo(conn, db_path, args.photo_id, args.word)
    else:
        interactive(conn, db_path)


if __name__ == "__main__":
    main()

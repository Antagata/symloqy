"""
Quick utility to view and manage words in the SRS database.
Usage:
  python manage_words.py list              # show all 'new' words
  python manage_words.py master word1 word2 ...  # mark specific words as mastered
  python manage_words.py master-all        # mark ALL 'new' words as mastered (fresh start)
"""

import sys
from dotenv import load_dotenv
load_dotenv()

from kindle_srs import database as db

conn = db.get_conn()
command = sys.argv[1] if len(sys.argv) > 1 else "list"

if command == "list":
    rows = db.get_words_by_status(conn, "new")
    print(f"\n{'ID':<6} {'Word':<30} {'Type':<12} {'Book'}")
    print("-" * 80)
    for r in rows:
        print(f"{r['id']:<6} {r['word']:<30} {r.get('source_type') or '':<12} {r.get('source_book') or ''}")
    print(f"\nTotal: {len(rows)} new words")

elif command == "master":
    words = sys.argv[2:]
    if not words:
        print("Provide word(s) to master, e.g.: python manage_words.py master ephemeral ubiquitous")
        sys.exit(1)
    db.mark_words_consolidated(conn, words)
    print(f"Marked {len(words)} word(s) as mastered: {words}")

elif command == "master-all":
    before = db.new_words_count(conn)
    db.mark_all_new_consolidated(conn)
    print(f"Marked all {before} 'new' words as mastered.")

else:
    print(__doc__)

# KindleSRS: visual memory anchors with Claude Vision

**Status: prototype, image idea suspended.** The code works as a daily batch job, but it is no longer developed. The project's focus moved to [Voice SRS](../../voice-srs/).

## Idea

The idea is to anchor new words to places you have actually seen. Each day the job takes a few of your own photos and the words you highlighted while reading. Claude Vision picks the words that connect to something *literally visible* in each photo and writes a visual anchor and a memory cue for each word. It also writes a short story set inside the scene. You get it all as an email and read it while looking at the photo.

## Flow

1. **Readwise sync:** new Kindle highlights. Highlights of 4 words or fewer, or anything from Kindle Vocabulary Builder, count as vocabulary. Incremental by cursor.
2. **Photo sync:** new images in a Google Drive folder (read-only, service account) are registered.
3. **Session:** for each of N unprocessed photos:
   - the photo is downloaded and compressed (≤1200 px JPEG, HEIC supported) and sent to Claude with a pool of 25 unassigned words
   - Claude returns strict JSON: `photo_description`, `selected_words`, `cards[{word, visual_anchor, memory_cue, brief_definition}]`, `story`
   - cards and the session are saved, and the words are marked as assigned
4. **Email:** an HTML digest is sent over Gmail SMTP with an app password.

`enrich.py` adds a word to an existing photo using only its saved text description. That makes a second, cheaper call, with no image.

## Setup

```bash
pip install -r requirements.txt          # Python 3.10+
cp .env.example .env                     # fill in your own values
# create the tables: paste schema.sql into the Supabase SQL editor
python main.py                           # one daily run
python enrich.py --list                  # inspect photos and add words
python manage_words.py list              # inspect the word queue
```

Share your Drive photo folder with the service account's email address. Run `main.py` once a day from any scheduler, such as cron, Railway cron or GitHub Actions.

## Safeguards

- **Config is checked at startup, not at import.** `main.py` lists every missing variable in one error. Modules import without credentials, so they can be tested.
- **Model output is validated.** The JSON reply is parsed even when it is wrapped in a code fence or a sentence. Cards are kept only for words that were actually in the candidate pool, each word once, up to the limit. A word Claude invents, or one already used for another photo, is dropped.
- **Model output is escaped** before it goes into the HTML email.
- **Word lookups are exact.** LIKE wildcards in a word (`%`, `_`) are escaped.

## Tests

```bash
python -m unittest discover -s tests      # 12 tests, no network or credentials
```

They cover JSON parsing, filtering cards to the pool, HTML escaping, config validation, wildcard escaping, image compression and highlight classification.

## Known limitations

- Reviews are not implemented. The `srs_reviews` table exists, but nothing writes to it.
- The Supabase and Drive calls are not covered by tests.
- The robustness fixes, and a fix to the photo-sync step (a leftover SQLite call), have been unit-tested but not yet run against a live database.

## What it taught us

The pipeline works, but the anchors didn't feel memorable. A random photo from your camera roll usually has nothing to do with the words. The next experiment flips the direction: start from the learner's **own best sentences** and turn them into images. That is the planned **Symlopic** session type (see the main README).

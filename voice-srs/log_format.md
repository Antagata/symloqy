# Session-log format

The session log is the only interface between the voice coach and the scheduler. The coach writes it as an email, and the scheduler parses it the next morning. Keeping it line-based and tolerant of small mistakes is what makes the setup hold up with no server.

**Email**
- To and from: `you@example.com`
- Subject: `Symloqy — Session Log YYYY-MM-DD`
- Body: one line per item and nothing else. There are no greetings, headings or review dates.

## Line types

| Prefix | Fields | Affects schedule? | Meaning |
|---|---|---|---|
| `NEW:` | word \| definition \| example \| week and batch | yes | First time the word was taught. It starts at stage 0. |
| `REVIEW:` | word \| `PRODUCED` / `RECALLED` / `HESITANT` / `FORGOTTEN` | yes | Outcome of the first attempt today. |
| `LINK:` | word \| word \| relation | no | A real connection: contrast, same root or same story. Builds the vocabulary map. |
| `BEST:` | sentence | no | A refined sentence the learner chose to keep. Feeds the Sentences tab. |
| `RECALL:` | sentence | no | The learner recalled one of their saved sentences from the word alone. |
| `DROP:` | word | yes | Remove the word from the schedule. |
| `MODE:` | `SYMLOPIC` | no | The call used an image (a photo, or a sketch of a saved sentence). Logged once per call. |
| `STICK:` | word | no | The learner said the image made this word stick. Feeds the Symlopic comparison. |

## Grades

| Grade | Rule |
|---|---|
| `PRODUCED` | Used unprompted, or used with a real person outside the session |
| `RECALLED` | Retrieved without help |
| `HESITANT` | Needed any clue, or struggled |
| `FORGOTTEN` | The coach had to give the answer |

## Example (made up)

```text
NEW: lambent | softly glowing or flickering; lightly brilliant | The lambent candlelight made the old library feel alive. | W47 2026-11-16
REVIEW: sardonic | HESITANT
LINK: sardonic | sarcastic | contrast
```

Rules the coach follows:
- Each item appears in exactly one log.
- Several logs per day are normal.
- A log goes out after every 5 locked items and at the end of every call.

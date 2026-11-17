# Experiment: does scheduled spoken review beat no review?

**Status:** running since November 2026. There are no results yet. Until the results are in, nothing in this repository should be read as evidence that the method works.

## Hypothesis

Words reviewed in spaced voice sessions (1 / 3 / 7 / 14 / 30 days) are recalled cold, from meaning to word, more often after 30 days than words that were taught once in the same kind of session and then left alone.

- **H₀:** there is no difference in 30-day cold recall between reviewed words and control words.
- **H₁:** reviewed words have higher 30-day cold recall.

## Design

| Item | Choice |
|---|---|
| Participants | One learner (n = 1). This is a personal experiment, not a study. |
| Unit | A word |
| Start condition | When there are more than 20 active words |
| Assignment | Each new word is randomly assigned. 80% go to the **treatment** group (normal schedule) and 20% to the **control** group (taught once, then held out of all reviews). |
| Blinding | The learner doesn't know which words are in the control group. The scheduler records the assignment, and the coach never sees it. |
| Treatment | The normal schedule: due on days 1, 3, 7, 14 and 30, graded RECALLED / HESITANT / FORGOTTEN / PRODUCED |
| Control | Taught once (a `NEW:` line), then no reviews until the test |
| Test | 30 days after a word's first log, a **cold test from meaning to word**: the coach gives the definition and the learner must produce the word, with no clues |

## Metrics

| Metric | Definition |
|---|---|
| **Primary: 30-day cold recall** | Share of words produced correctly with no clue, per group |
| Partial recall | Share of words recalled after one clue, per group |
| Production rate | Share of words that ever got a `PRODUCED` grade (treatment group only) |
| Cost | Total review minutes spent per word recalled at day 30 |
| Load | Reviews per day against the 30-review cap |

## Analysis plan

- Report both groups' proportions with 95% confidence intervals (Wilson).
- Compare them with Fisher's exact test, because the groups are small.
- Report the raw counts next to the percentages, every time.
- List the threats to validity next to the results:
  - n = 1
  - the learner knows a control group exists
  - words can be met outside the sessions (books, conversations)
  - the coach grades the test, and it is an LLM

## How results will be reported

- A results table appended to this file: group, n words, cold recall, partial recall, 95% CI.
- The raw data needed to reproduce the table, exported from the logs with the words removed or anonymised.
- The result will be published whichever way it comes out, including a null result.

## Results

*Coming.*

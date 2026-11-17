"""
Reference implementation of the Symloqy scheduling rules.

The live scheduler is a scheduled Claude routine that follows
../scheduler_routine_spec.md in natural language. A prompt can't be unit-tested,
so this module restates the same rules as plain, dependency-free Python:

  * it pins down the edge cases the spec describes (first grade per day,
    early reviews, the orbit pool, the entry rule, drops, the allowance);
  * tests/test_srs_schedule.py checks them;
  * the routine's Due emails can be compared against it.

It doesn't send or read email. The input is the text of the session logs, and
the output is a DuePlan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

INTERVALS = (1, 3, 7, 14, 30)          # days, indexed by stage 0..4
ORBIT = len(INTERVALS)                  # stage 5 = orbit pool, never "finished"
GRADES = ("PRODUCED", "RECALLED", "HESITANT", "FORGOTTEN")
DAILY_CAP = 30


# ── Parsing ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Event:
    day: date
    kind: str                 # NEW | REVIEW | DROP
    word: str                 # normalised to lower case
    grade: str | None = None
    definition: str = ""
    example: str = ""
    batch: str = ""


_LINE = re.compile(r"^\s*(NEW|REVIEW|DROP|LINK|BEST|RECALL)\s*:\s*(.*?)\s*$", re.IGNORECASE)


def parse_log(text: str, day: date) -> list[Event]:
    """Parse one Session Log body.

    Lines that don't change the schedule (LINK, BEST, RECALL) and malformed
    lines are skipped. A grade is never guessed: a REVIEW line without a valid
    grade is ignored.
    """
    events: list[Event] = []
    for raw in text.splitlines():
        m = _LINE.match(raw)
        if not m:
            continue
        kind, rest = m.group(1).upper(), m.group(2)
        fields = [f.strip() for f in rest.split("|")]
        word = fields[0].lower() if fields and fields[0] else ""
        if not word:
            continue
        if kind == "NEW":
            fields += [""] * (4 - len(fields))
            events.append(Event(day, "NEW", word, definition=fields[1],
                                example=fields[2], batch=fields[3]))
        elif kind == "REVIEW":
            grade = fields[1].upper() if len(fields) > 1 else ""
            if grade in GRADES:
                events.append(Event(day, "REVIEW", word, grade=grade))
        elif kind == "DROP":
            events.append(Event(day, "DROP", word))
    return events


# ── State ─────────────────────────────────────────────────────────────────────

@dataclass
class WordState:
    word: str
    stage: int = 0
    due: date | None = None          # None while in orbit
    last_grade: str | None = None
    last_reviewed: date | None = None
    first_studied: date | None = None
    times_reviewed: int = 0
    dropped: bool = False
    definition: str = ""
    example: str = ""
    batch: str = ""

    @property
    def in_orbit(self) -> bool:
        return self.stage >= ORBIT


@dataclass
class Schedule:
    words: dict[str, WordState] = field(default_factory=dict)
    ignored: set[str] = field(default_factory=set)   # words outside the Words tab


def replay(events: Iterable[Event], allowed_words: Iterable[str]) -> Schedule:
    """Rebuild the whole schedule from every event, oldest first.

    `allowed_words` is column A of the Words tab. A word enters the schedule
    only from there: events for any other word go to `Schedule.ignored`.
    """
    allowed = {w.strip().lower() for w in allowed_words if w.strip()}
    sched = Schedule()
    graded_today: set[tuple[str, date]] = set()

    # sorted() is stable, so events from the same day keep their log order.
    for ev in sorted(events, key=lambda e: e.day):
        if ev.word not in allowed:
            sched.ignored.add(ev.word)
            continue
        st = sched.words.get(ev.word)

        if ev.kind == "NEW":
            if st is None:
                sched.words[ev.word] = WordState(
                    ev.word, stage=0, due=ev.day + timedelta(days=INTERVALS[0]),
                    first_studied=ev.day, definition=ev.definition,
                    example=ev.example, batch=ev.batch)
            elif st.dropped:
                st.dropped = False          # only a NEW line revives a dropped word
            # A repeated NEW adds nothing and does not reset the schedule.

        elif ev.kind == "DROP":
            if st is None:
                st = sched.words[ev.word] = WordState(ev.word)
            st.dropped = True

        elif ev.kind == "REVIEW":
            if st is None or st.dropped:
                continue                    # can't review a word that was never taught
            key = (ev.word, ev.day)
            if key in graded_today:
                continue                    # only the first grade of the day counts
            graded_today.add(key)
            _apply_grade(st, ev.grade, ev.day)

    return sched


def _apply_grade(st: WordState, grade: str, day: date) -> None:
    early = st.due is not None and day < st.due
    st.last_grade, st.last_reviewed = grade, day
    st.times_reviewed += 1

    if grade == "FORGOTTEN":
        st.stage = 0
    elif early:
        return                              # before the due date only FORGOTTEN counts
    elif grade in ("PRODUCED", "RECALLED"):
        st.stage = min(st.stage + 1, ORBIT)
    # HESITANT: same stage

    st.due = None if st.in_orbit else day + timedelta(days=INTERVALS[st.stage])


# ── Daily plan ────────────────────────────────────────────────────────────────

@dataclass
class DuePlan:
    due: list[WordState]
    beyond_cap: list[WordState]
    surprise: WordState | None
    new_word_allowance: int
    next_new_words: list[str]


def new_word_allowance(backlog: int, queued: int) -> int:
    """5 / 3 / 1 by backlog beyond the cap, and never 0 while words are queued."""
    if queued == 0:
        return 0
    if backlog <= 10:
        return 5
    if backlog <= 30:
        return 3
    return 1


def plan_day(sched: Schedule, today: date, words_tab: list[str],
             cap: int = DAILY_CAP) -> DuePlan:
    active = [w for w in sched.words.values() if not w.dropped]
    due = [w for w in active if not w.in_orbit and w.due is not None and w.due <= today]
    # Words last graded FORGOTTEN come first, then the most overdue.
    due.sort(key=lambda w: (w.last_grade != "FORGOTTEN", w.due, w.word))

    orbit = [w for w in active if w.in_orbit]
    surprise = min(orbit, key=lambda w: (w.last_reviewed or date.min, w.word), default=None)

    known = set(sched.words)            # includes dropped words
    queued = []
    for w in words_tab:
        key = w.strip().lower()
        if key and key not in known and key not in queued:
            queued.append(key)

    backlog = max(0, len(due) - cap)
    allowance = new_word_allowance(backlog, len(queued))
    return DuePlan(due=due[:cap], beyond_cap=due[cap:], surprise=surprise,
                   new_word_allowance=allowance, next_new_words=queued[:allowance])

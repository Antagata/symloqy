"""Tests for the reference scheduler. Run from the repo root with:

    python -m unittest discover -s voice-srs/reference/tests
"""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from srs_schedule import (  # noqa: E402
    ORBIT, Event, new_word_allowance, parse_log, plan_day, replay,
)

D0 = date(2026, 11, 16)


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def new(word, n=0):
    return Event(day(n), "NEW", word)


def rev(word, grade, n):
    return Event(day(n), "REVIEW", word, grade=grade)


class ParseLogTest(unittest.TestCase):
    def test_standard_lines(self):
        text = (
            "NEW: Lambent | softly glowing | The lambent light. | W47 2026-11-16\n"
            "REVIEW: sardonic | hesitant\n"
            "LINK: sardonic | sarcastic | contrast\n"
            "BEST: A sentence worth keeping.\n"
            "DROP: jelly\n"
        )
        evs = parse_log(text, D0)
        self.assertEqual([(e.kind, e.word) for e in evs],
                         [("NEW", "lambent"), ("REVIEW", "sardonic"), ("DROP", "jelly")])
        self.assertEqual(evs[0].batch, "W47 2026-11-16")
        self.assertEqual(evs[1].grade, "HESITANT")

    def test_never_guesses_a_grade(self):
        self.assertEqual(parse_log("REVIEW: sardonic | pretty good", D0), [])
        self.assertEqual(parse_log("REVIEW: sardonic", D0), [])

    def test_new_without_batch_is_accepted(self):
        (ev,) = parse_log("NEW: lambent | softly glowing | example", D0)
        self.assertEqual(ev.batch, "")

    def test_ignores_prose(self):
        self.assertEqual(parse_log("Great session today!\nHere is your log:", D0), [])


class ReplayTest(unittest.TestCase):
    def test_new_word_due_next_day(self):
        s = replay([new("lambent")], ["lambent"])
        self.assertEqual(s.words["lambent"].due, day(1))

    def test_full_ladder_then_orbit(self):
        evs, n = [new("w")], 0
        for interval in (1, 3, 7, 14, 30):
            n += interval
            evs.append(rev("w", "RECALLED", n))
        st = replay(evs, ["w"]).words["w"]
        self.assertEqual(st.stage, ORBIT)
        self.assertIsNone(st.due)

    def test_hesitant_keeps_stage(self):
        st = replay([new("w"), rev("w", "RECALLED", 1), rev("w", "HESITANT", 4)], ["w"]).words["w"]
        self.assertEqual(st.stage, 1)
        self.assertEqual(st.due, day(4 + 3))

    def test_forgotten_resets(self):
        st = replay([new("w"), rev("w", "RECALLED", 1), rev("w", "FORGOTTEN", 4)], ["w"]).words["w"]
        self.assertEqual((st.stage, st.due), (0, day(5)))

    def test_early_review_only_forgotten_counts(self):
        st = replay([new("w"), rev("w", "RECALLED", 1), rev("w", "RECALLED", 2)], ["w"]).words["w"]
        self.assertEqual((st.stage, st.due), (1, day(4)))      # day-2 review was early
        st = replay([new("w"), rev("w", "RECALLED", 1), rev("w", "FORGOTTEN", 2)], ["w"]).words["w"]
        self.assertEqual((st.stage, st.due), (0, day(3)))

    def test_only_first_grade_of_the_day_counts(self):
        st = replay([new("w"), rev("w", "FORGOTTEN", 1), rev("w", "RECALLED", 1)], ["w"]).words["w"]
        self.assertEqual(st.stage, 0)
        self.assertEqual(st.last_grade, "FORGOTTEN")

    def test_repeated_new_does_not_reset(self):
        st = replay([new("w"), rev("w", "RECALLED", 1), new("w", 2)], ["w"]).words["w"]
        self.assertEqual(st.stage, 1)

    def test_entry_rule_ignores_words_outside_the_words_tab(self):
        s = replay([new("w"), new("jelly"), rev("jelly", "RECALLED", 1)], ["w"])
        self.assertNotIn("jelly", s.words)
        self.assertEqual(s.ignored, {"jelly"})

    def test_drop_and_revive(self):
        s = replay([new("w"), Event(day(1), "DROP", "w"), rev("w", "RECALLED", 1)], ["w"])
        self.assertTrue(s.words["w"].dropped)
        self.assertEqual(s.words["w"].times_reviewed, 0)
        s = replay([new("w"), Event(day(1), "DROP", "w"), new("w", 2)], ["w"])
        self.assertFalse(s.words["w"].dropped)

    def test_events_are_replayed_oldest_first(self):
        shuffled = [rev("w", "RECALLED", 1), new("w")]
        self.assertEqual(replay(shuffled, ["w"]).words["w"].stage, 1)


class PlanDayTest(unittest.TestCase):
    def test_forgotten_first_then_most_overdue(self):
        evs = [new("a"), new("b", 1), new("c"),
               rev("c", "RECALLED", 1), rev("c", "FORGOTTEN", 4)]
        s = replay(evs, ["a", "b", "c"])
        plan = plan_day(s, day(10), ["a", "b", "c"])
        self.assertEqual([w.word for w in plan.due], ["c", "a", "b"])

    def test_cap_and_backlog(self):
        words = [f"w{i}" for i in range(45)]
        s = replay([new(w) for w in words], words)
        plan = plan_day(s, day(1), words + ["queued"], cap=30)
        self.assertEqual((len(plan.due), len(plan.beyond_cap)), (30, 15))
        self.assertEqual(plan.new_word_allowance, 3)
        self.assertEqual(plan.next_new_words, ["queued"])

    def test_surprise_is_longest_unseen_orbit_word(self):
        evs = []
        for w, offset in (("old", 0), ("recent", 5)):
            evs.append(new(w, offset))
            n = offset
            for interval in (1, 3, 7, 14, 30):
                n += interval
                evs.append(rev(w, "RECALLED", n))
        plan = plan_day(replay(evs, ["old", "recent"]), day(100), ["old", "recent"])
        self.assertEqual(plan.surprise.word, "old")
        self.assertEqual(plan.due, [])

    def test_dropped_words_are_not_due_or_queued(self):
        s = replay([new("w"), Event(day(0), "DROP", "w")], ["w"])
        plan = plan_day(s, day(5), ["w"])
        self.assertEqual((plan.due, plan.next_new_words), ([], []))


class AllowanceTest(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual([new_word_allowance(b, 9) for b in (0, 10, 11, 30, 31, 500)],
                         [5, 5, 3, 3, 1, 1])

    def test_never_zero_while_words_are_queued(self):
        self.assertEqual(new_word_allowance(10_000, 1), 1)
        self.assertEqual(new_word_allowance(0, 0), 0)


if __name__ == "__main__":
    unittest.main()

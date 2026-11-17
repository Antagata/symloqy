"""Unit tests for the parts of KindleSRS that don't need network or credentials.

Run from experiments/kindle-srs:  python -m unittest discover -s tests
"""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kindle_srs import agent, config, database, email_sender  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    from kindle_srs.readwise import _classify_source
except ImportError:  # pragma: no cover (requests missing)
    _classify_source = None


class ParseJsonTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(agent._parse_json('{"a": 1}'), {"a": 1})

    def test_code_fence_and_preamble(self):
        raw = 'Here you go:\n```json\n{"story": "x"}\n```'
        self.assertEqual(agent._parse_json(raw), {"story": "x"})

    def test_garbage(self):
        self.assertIsNone(agent._parse_json("sorry, I can't see the image"))
        self.assertIsNone(agent._parse_json("{not json}"))


class CardsInPoolTest(unittest.TestCase):
    POOL = [{"id": 1, "word": "Lambent"}, {"id": 2, "word": "tawny"}, {"id": 3, "word": "sere"}]

    def test_drops_words_not_offered_and_duplicates(self):
        result = {"cards": [{"word": "lambent "}, {"word": "invented"}, {"word": "LAMBENT"},
                            {"word": "tawny"}]}
        kept = agent.cards_in_pool(result, self.POOL, limit=3)
        self.assertEqual([c["word"] for c in kept], ["Lambent", "tawny"])  # pool spelling

    def test_respects_limit(self):
        result = {"cards": [{"word": "lambent"}, {"word": "tawny"}, {"word": "sere"}]}
        self.assertEqual(len(agent.cards_in_pool(result, self.POOL, limit=2)), 2)

    def test_missing_cards(self):
        self.assertEqual(agent.cards_in_pool({}, self.POOL, limit=3), [])


class EmailTest(unittest.TestCase):
    def test_model_output_is_escaped(self):
        html = email_sender.build_html("2026-11-17", [{
            "description": "<script>alert(1)</script>",
            "story": "a & b",
            "cards": [{"word": "<b>x</b>", "visual_anchor": "<img src=x>", "memory_cue": "\"q\""}],
        }])
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("a &amp; b", html)


class ConfigTest(unittest.TestCase):
    def test_require_lists_every_missing_variable(self):
        with self.assertRaises(RuntimeError) as ctx:
            config.require(("SYMLOQY_TEST_MISSING_A", "SYMLOQY_TEST_MISSING_B"))
        self.assertIn("SYMLOQY_TEST_MISSING_A", str(ctx.exception))
        self.assertIn("SYMLOQY_TEST_MISSING_B", str(ctx.exception))

    def test_photos_per_session_is_capped(self):
        self.assertIn(config.PHOTOS_PER_SESSION, (1, 2))


class IlikeExactTest(unittest.TestCase):
    def test_wildcards_are_escaped(self):
        self.assertEqual(database.ilike_exact("50%_off"), "50\\%\\_off")
        self.assertEqual(database.ilike_exact("plain"), "plain")


@unittest.skipIf(Image is None, "Pillow not installed")
class CompressTest(unittest.TestCase):
    def test_resizes_and_converts_to_jpeg(self):
        buf = io.BytesIO()
        Image.new("RGBA", (4000, 2000), (200, 100, 50, 255)).save(buf, format="PNG")
        out = Image.open(io.BytesIO(agent._compress(buf.getvalue(), max_px=1200)))
        self.assertEqual(out.format, "JPEG")
        self.assertEqual(out.size, (1200, 600))


@unittest.skipIf(_classify_source is None, "requests not installed")
class ClassifySourceTest(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(_classify_source("a long passage of five words", {"title": "Kindle Vocabulary Builder"}), "vocabulary")
        self.assertEqual(_classify_source("lambent", {"title": "Some Novel"}), "vocabulary")
        self.assertEqual(_classify_source("one two three four five", {"title": "Some Novel"}), "highlight")


if __name__ == "__main__":
    unittest.main()

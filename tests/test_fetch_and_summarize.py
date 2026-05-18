import datetime
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path


def load_module():
    fake_arxiv = types.ModuleType("arxiv")
    fake_arxiv.SortCriterion = types.SimpleNamespace(SubmittedDate="submittedDate")
    fake_arxiv.Client = object
    fake_arxiv.Search = object
    sys.modules.setdefault("arxiv", fake_arxiv)

    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = lambda *args, **kwargs: None
    sys.modules.setdefault("openai", fake_openai)

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", fake_dotenv)

    fake_dateutil = types.ModuleType("dateutil")
    fake_tz = types.ModuleType("dateutil.tz")
    fake_tz.tzutc = lambda: datetime.timezone.utc
    fake_dateutil.tz = fake_tz
    sys.modules.setdefault("dateutil", fake_dateutil)
    sys.modules.setdefault("dateutil.tz", fake_tz)

    path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_and_summarize.py"
    spec = importlib.util.spec_from_file_location("fetch_and_summarize", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FetchAndSummarizeTests(unittest.TestCase):
    def test_arxiv_search_query_includes_target_date_range(self):
        os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
        module = load_module()

        lower = datetime.datetime(2026, 5, 15, tzinfo=datetime.timezone.utc)
        upper = datetime.datetime(2026, 5, 16, tzinfo=datetime.timezone.utc)

        query = module.build_arxiv_search_query(lower, upper)

        self.assertIn("submittedDate:[202605150000 TO 202605160000]", query)

    def test_target_windows_cover_previous_three_utc_days(self):
        os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
        module = load_module()

        now = datetime.datetime(2026, 5, 18, 8, 37, tzinfo=datetime.timezone.utc)
        windows = module.get_target_windows(now)

        self.assertEqual(
            [
                (
                    datetime.datetime(2026, 5, 15, tzinfo=datetime.timezone.utc),
                    datetime.datetime(2026, 5, 16, tzinfo=datetime.timezone.utc),
                ),
                (
                    datetime.datetime(2026, 5, 16, tzinfo=datetime.timezone.utc),
                    datetime.datetime(2026, 5, 17, tzinfo=datetime.timezone.utc),
                ),
                (
                    datetime.datetime(2026, 5, 17, tzinfo=datetime.timezone.utc),
                    datetime.datetime(2026, 5, 18, tzinfo=datetime.timezone.utc),
                ),
            ],
            windows,
        )


if __name__ == "__main__":
    unittest.main()

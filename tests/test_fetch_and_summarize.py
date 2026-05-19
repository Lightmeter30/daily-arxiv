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

    def test_arxiv_search_query_uses_explicit_all_field_for_keywords(self):
        os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
        module = load_module()

        lower = datetime.datetime(2026, 5, 15, tzinfo=datetime.timezone.utc)
        upper = datetime.datetime(2026, 5, 16, tzinfo=datetime.timezone.utc)

        query = module.build_arxiv_search_query(lower, upper)

        self.assertIn('all:"Gaussian Splatting"', query)
        self.assertNotIn(' OR "Gaussian Splatting"', query)

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

    def test_arxiv_http_errors_are_retryable(self):
        os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
        module = load_module()

        self.assertTrue(module.is_retryable_arxiv_error(Exception("HTTP 429")))
        self.assertTrue(module.is_retryable_arxiv_error(Exception("HTTP 500")))
        self.assertTrue(module.is_retryable_arxiv_error(Exception("HTTP 503")))
        self.assertFalse(module.is_retryable_arxiv_error(Exception("HTTP 406")))

    def test_parse_abs_page_extracts_paper_metadata(self):
        os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
        module = load_module()
        html = """
        <meta name="citation_author" content="Ada Lovelace" />
        <meta name="citation_author" content="Grace Hopper" />
        <div class="dateline">[Submitted on 15 May 2026]</div>
        <h1 class="title mathjax"><span class="descriptor">Title:</span>Robust Gaussian Splatting for SLAM</h1>
        <blockquote class="abstract mathjax">
          <span class="descriptor">Abstract:</span>This paper studies Gaussian Splatting for robust SLAM.
        </blockquote>
        <td class="tablecell subjects">
          <span class="primary-subject">Computer Vision and Pattern Recognition (cs.CV)</span>; Robotics (cs.RO)
        </td>
        """

        paper = module.parse_abs_page("2605.12345", html)

        self.assertEqual(paper["id"], "https://arxiv.org/abs/2605.12345")
        self.assertEqual(paper["title"], "Robust Gaussian Splatting for SLAM")
        self.assertEqual(paper["authors"], ["Ada Lovelace", "Grace Hopper"])
        self.assertEqual(paper["published"], "2026-05-15")
        self.assertEqual(paper["category"], "cs.CV")
        self.assertIn("Gaussian Splatting", paper["abstract"])

    def test_html_keyword_filter_matches_title_and_abstract(self):
        os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
        module = load_module()

        self.assertTrue(module.matches_keywords("A SLAM System", "No abstract keyword"))
        self.assertTrue(module.matches_keywords("Other Title", "Uses Gaussian Splatting"))
        self.assertFalse(module.matches_keywords("Other Title", "No relevant phrase"))

    def test_parse_list_page_extracts_dated_title_candidates(self):
        os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
        module = load_module()
        page_html = """
        <h3>Mon, 18 May 2026 (showing first 2 entries )</h3>
        <dt><a href ="/abs/2605.16258" title="Abstract" id="2605.16258">arXiv:2605.16258</a></dt>
        <dd><div class='meta'>
        <div class='list-title mathjax'><span class='descriptor'>Title:</span>
          IVGT: Implicit Visual Geometry Transformer for Neural Scene Representation
        </div>
        </div></dd>
        <dt><a href ="/abs/2605.16241" title="Abstract" id="2605.16241">arXiv:2605.16241</a></dt>
        <dd><div class='meta'>
        <div class='list-title mathjax'><span class='descriptor'>Title:</span>
          Offline Semantic Guidance
        </div>
        </div></dd>
        """

        candidates = module.parse_list_page_candidates(page_html)

        self.assertEqual(
            candidates,
            [
                {"id": "2605.16258", "title": "IVGT: Implicit Visual Geometry Transformer for Neural Scene Representation", "published": "2026-05-18"},
                {"id": "2605.16241", "title": "Offline Semantic Guidance", "published": "2026-05-18"},
            ],
        )


if __name__ == "__main__":
    unittest.main()

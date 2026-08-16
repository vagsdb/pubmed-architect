"""Static integrity tests for the GitHub Pages application."""

from html.parser import HTMLParser
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).parent
DOCS = ROOT / "docs"


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.assets = []
        self.views = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
            if values["id"].endswith("-view"):
                self.views.add(values["id"])
        if tag == "script" and values.get("src"):
            self.assets.append(values["src"])
        if tag == "link" and values.get("rel") == "stylesheet" and values.get("href"):
            self.assets.append(values["href"])


class TestWebIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (DOCS / "index.html").read_text(encoding="utf-8")
        cls.parser = PageParser()
        cls.parser.feed(cls.html)

    def test_ids_are_unique(self):
        duplicates = {item for item in self.parser.ids if self.parser.ids.count(item) > 1}
        self.assertEqual(duplicates, set())

    def test_local_assets_exist(self):
        local = [asset for asset in self.parser.assets if not asset.startswith(("http://", "https://"))]
        missing = [asset for asset in local if not (DOCS / asset).is_file()]
        self.assertEqual(missing, [])

    def test_research_os_views_exist(self):
        expected = {"dashboard-view", "search-view", "library-view", "evidence-view", "builder-view", "review-view"}
        self.assertTrue(expected.issubset(self.parser.views))

    def test_content_security_policy_allows_required_apis(self):
        for domain in ("https://eutils.ncbi.nlm.nih.gov", "https://api.openai.com", "https://api.anthropic.com"):
            self.assertIn(domain, self.html)

    def test_strict_style_policy_has_no_inline_styles(self):
        self.assertNotIn("style=", self.html)
        for script in ("app.js", "ai.js", "research-os.js"):
            self.assertNotIn("style=", (DOCS / script).read_text(encoding="utf-8"))

    def test_javascript_syntax(self):
        for script in ("app.js", "ai.js", "research-os.js"):
            result = subprocess.run(["node", "--check", str(DOCS / script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_current_pages_artifact_action(self):
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("actions/checkout@v6", workflow)
        self.assertIn("actions/configure-pages@v5", workflow)
        self.assertIn("actions/upload-pages-artifact@v4", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)


if __name__ == "__main__":
    unittest.main()

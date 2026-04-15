#!/usr/bin/env python3
"""Tests for DOI support across pubmed_api and pubmed_insights."""

import json
import re
import unittest
from unittest.mock import patch, MagicMock

from pubmed_api import PubMedClient

# Also test the helpers inside pubmed_insights
import pubmed_insights as insights


# ── pubmed_api.PubMedClient ──────────────────────────────────────────


class TestIsDoi(unittest.TestCase):
    """PubMedClient.is_doi() should detect valid DOI patterns."""

    def test_standard_doi(self):
        self.assertTrue(PubMedClient.is_doi("10.1038/s41586-023-06291-2"))

    def test_doi_with_long_registrant(self):
        self.assertTrue(PubMedClient.is_doi("10.1016/j.cell.2023.04.007"))

    def test_doi_with_whitespace(self):
        self.assertTrue(PubMedClient.is_doi("  10.1038/s41586-023-06291-2  "))

    def test_plain_pmid_is_not_doi(self):
        self.assertFalse(PubMedClient.is_doi("35901745"))

    def test_short_number_not_doi(self):
        self.assertFalse(PubMedClient.is_doi("12345"))

    def test_empty_string(self):
        self.assertFalse(PubMedClient.is_doi(""))

    def test_doi_prefix_only(self):
        self.assertFalse(PubMedClient.is_doi("10.1038"))

    def test_almost_doi_no_suffix(self):
        self.assertFalse(PubMedClient.is_doi("10.1038/"))


class TestResolveIds(unittest.TestCase):
    """resolve_ids() should pass PMIDs through and resolve DOIs."""

    def setUp(self):
        self.client = PubMedClient()

    def test_pure_pmids_unchanged(self):
        with patch.object(self.client, "doi_to_pmids", return_value={}) as mock:
            result = self.client.resolve_ids(["111", "222"])
        self.assertEqual(result, ["111", "222"])
        mock.assert_not_called()

    def test_doi_resolved(self):
        doi = "10.1038/s41586-023-06291-2"
        with patch.object(
            self.client, "doi_to_pmids", return_value={doi: "99999"}
        ) as mock:
            result = self.client.resolve_ids([doi])
        mock.assert_called_once_with([doi])
        self.assertIn("99999", result)

    def test_mixed_list(self):
        doi = "10.1016/j.cell.2023.04.007"
        with patch.object(
            self.client, "doi_to_pmids", return_value={doi: "88888"}
        ):
            result = self.client.resolve_ids(["111", doi, "222"])
        self.assertEqual(sorted(result), sorted(["111", "222", "88888"]))


class TestDoiTopmids(unittest.TestCase):
    """doi_to_pmids() should call esearch and parse the response."""

    def setUp(self):
        self.client = PubMedClient()

    def _fake_get(self, endpoint, params):
        """Return a fake esearch JSON response with one PMID."""
        return json.dumps(
            {"esearchresult": {"idlist": ["12345"]}}
        ).encode()

    def test_single_doi(self):
        with patch.object(self.client, "_get", side_effect=self._fake_get):
            mapping = self.client.doi_to_pmids(["10.1038/s41586-023-06291-2"])
        self.assertEqual(mapping, {"10.1038/s41586-023-06291-2": "12345"})

    def test_unresolvable_doi_omitted(self):
        def _empty(endpoint, params):
            return json.dumps(
                {"esearchresult": {"idlist": []}}
            ).encode()

        with patch.object(self.client, "_get", side_effect=_empty):
            mapping = self.client.doi_to_pmids(["10.9999/nonexistent"])
        self.assertEqual(mapping, {})


class TestFetchDetailsAcceptsDoi(unittest.TestCase):
    """fetch_details() should resolve DOIs before fetching."""

    def setUp(self):
        self.client = PubMedClient()

    def test_doi_triggers_resolve(self):
        doi = "10.1038/s41586-023-06291-2"
        with patch.object(
            self.client, "resolve_ids", return_value=["12345"]
        ) as mock_resolve, patch.object(
            self.client, "_get", return_value=b"<PubmedArticleSet></PubmedArticleSet>"
        ):
            self.client.fetch_details([doi])
        mock_resolve.assert_called_once_with([doi])


class TestFindRelatedAcceptsDoi(unittest.TestCase):
    """find_related() should resolve a DOI to PMID first."""

    def setUp(self):
        self.client = PubMedClient()

    def test_doi_resolved_before_elink(self):
        doi = "10.1038/s41586-023-06291-2"
        with patch.object(
            self.client, "doi_to_pmids", return_value={doi: "12345"}
        ), patch.object(
            self.client,
            "_get",
            return_value=b"<eLinkResult></eLinkResult>",
        ):
            self.client.find_related(doi)

    def test_pmid_passed_directly(self):
        with patch.object(
            self.client,
            "_get",
            return_value=b"<eLinkResult></eLinkResult>",
        ) as mock_get:
            self.client.find_related("12345")
        # _get should have been called (not rejected)
        mock_get.assert_called_once()


# ── pubmed_insights helpers ──────────────────────────────────────────


class TestInsightsIsDoi(unittest.TestCase):
    def test_valid_doi(self):
        self.assertTrue(insights._is_doi("10.1038/s41586-023-06291-2"))

    def test_pmid(self):
        self.assertFalse(insights._is_doi("35901745"))

    def test_empty(self):
        self.assertFalse(insights._is_doi(""))


class TestInsightsResolveId(unittest.TestCase):
    def test_pmid_passthrough(self):
        self.assertEqual(insights._resolve_id("12345"), "12345")

    def test_doi_resolved(self):
        fake_json = json.dumps(
            {"esearchresult": {"idlist": ["99999"]}}
        )
        with patch.object(insights, "_api", return_value=fake_json):
            result = insights._resolve_id("10.1038/s41586-023-06291-2")
        self.assertEqual(result, "99999")

    def test_unresolvable_doi_exits(self):
        fake_json = json.dumps({"esearchresult": {"idlist": []}})
        with patch.object(insights, "_api", return_value=fake_json):
            with self.assertRaises(SystemExit):
                insights._resolve_id("10.9999/nonexistent")


class TestInsightsResolveIds(unittest.TestCase):
    def test_mixed(self):
        fake_json = json.dumps(
            {"esearchresult": {"idlist": ["88888"]}}
        )
        with patch.object(insights, "_api", return_value=fake_json):
            result = insights._resolve_ids(
                ["111", "10.1038/s41586-023-06291-2"]
            )
        self.assertEqual(result, ["111", "88888"])


if __name__ == "__main__":
    unittest.main()

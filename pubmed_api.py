"""
PubMed API client using NCBI E-utilities.
No external dependencies — uses only urllib and xml from the standard library.
"""

import urllib.request
import urllib.parse
import json
import re
import xml.etree.ElementTree as ET
import time

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
_DOI_RE = re.compile(r'^10\.\d{4,9}/[^\s]+$')


class PubMedClient:
    """Lightweight client for the NCBI E-utilities API."""

    def __init__(self, email: str = ""):
        self.email = email
        self._last_request = 0.0

    # ── internal helpers ──────────────────────────────────────────────

    def _throttle(self):
        """NCBI allows max 3 req/s without an API key."""
        gap = time.time() - self._last_request
        if gap < 0.35:
            time.sleep(0.35 - gap)
        self._last_request = time.time()

    def _get(self, endpoint: str, params: dict) -> bytes:
        self._throttle()
        if self.email:
            params["email"] = self.email
        url = BASE_URL + endpoint + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url, headers={"User-Agent": "PubMedArchitect/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()

    # ── identifier helpers ─────────────────────────────────────────────

    @staticmethod
    def is_doi(identifier: str) -> bool:
        """Return True if *identifier* looks like a DOI (e.g. 10.1234/...)."""
        return bool(_DOI_RE.match(identifier.strip()))

    def doi_to_pmids(self, dois: list[str]) -> dict[str, str]:
        """Resolve a list of DOIs to PMIDs via E-search.

        Returns a dict mapping each DOI to its PMID (DOIs that cannot be
        resolved are silently omitted).
        """
        mapping: dict[str, str] = {}
        for doi in dois:
            doi = doi.strip()
            data = self._get(
                "esearch.fcgi",
                {"db": "pubmed", "term": f"{doi}[AID]", "retmode": "json"},
            )
            result = json.loads(data)
            ids = result.get("esearchresult", {}).get("idlist", [])
            if ids:
                mapping[doi] = ids[0]
        return mapping

    def resolve_ids(self, identifiers: list[str]) -> list[str]:
        """Accept a mixed list of PMIDs and DOIs; return a list of PMIDs."""
        pmids: list[str] = []
        dois: list[str] = []
        for ident in identifiers:
            ident = ident.strip()
            if self.is_doi(ident):
                dois.append(ident)
            else:
                pmids.append(ident)
        if dois:
            mapping = self.doi_to_pmids(dois)
            pmids.extend(mapping.values())
        return pmids

    # ── public API ────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        max_results: int = 20,
        sort: str = "relevance",
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> tuple[list, int]:
        """Return (list of PMID strings, total_count) matching *query*.

        *sort* can be ``"relevance"`` (default), ``"pub+date"`` (newest first),
        or ``"first+author"``.
        *from_year* / *to_year* restrict publication dates (inclusive).
        """
        params: dict = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": sort,
        }
        if from_year:
            params["mindate"] = f"{from_year}/01/01"
            params["datetype"] = "pdat"
        if to_year:
            params["maxdate"] = f"{to_year}/12/31"
            params["datetype"] = "pdat"
        data = self._get("esearch.fcgi", params)
        result = json.loads(data)
        sr = result.get("esearchresult", {})
        return sr.get("idlist", []), int(sr.get("count", 0))

    def fetch_details(self, identifiers: list) -> list:
        """Fetch full article metadata for a list of PMIDs or DOIs."""
        if not identifiers:
            return []
        pmids = self.resolve_ids(identifiers)
        if not pmids:
            return []
        data = self._get(
            "efetch.fcgi",
            {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
        )
        return self._parse_articles(data)

    def find_related(self, identifier: str, max_results: int = 15) -> list:
        """Return PMIDs of articles related to *identifier* (PMID or DOI)."""
        pmid = identifier.strip()
        if self.is_doi(pmid):
            mapping = self.doi_to_pmids([pmid])
            if not mapping:
                return []
            pmid = mapping[pmid]
        data = self._get(
            "elink.fcgi",
            {
                "dbfrom": "pubmed",
                "db": "pubmed",
                "id": pmid,
                "cmd": "neighbor_score",
                "retmode": "xml",
            },
        )
        root = ET.fromstring(data)
        ids = []
        for link_set_db in root.iter("LinkSetDb"):
            name = link_set_db.findtext("LinkName", "")
            if name == "pubmed_pubmed":
                for link in link_set_db.findall("Link"):
                    lid = link.findtext("Id", "")
                    if lid and lid != pmid:
                        ids.append(lid)
                    if len(ids) >= max_results:
                        break
        return ids

    # ── XML parsing ───────────────────────────────────────────────────

    @staticmethod
    def _text(elem) -> str:
        """Collect all text inside an element (including children)."""
        return "".join(elem.itertext()).strip() if elem is not None else ""

    def _parse_articles(self, xml_data: bytes) -> list:
        root = ET.fromstring(xml_data)
        articles = []
        for pa in root.findall(".//PubmedArticle"):
            a = self._parse_one(pa)
            if a:
                articles.append(a)
        return articles

    def _parse_one(self, pa) -> dict | None:
        mc = pa.find("MedlineCitation")
        if mc is None:
            return None
        art = mc.find("Article")
        if art is None:
            return None

        pmid = self._text(mc.find("PMID"))
        title = self._text(art.find("ArticleTitle")) or "No title"

        # abstract
        ab_elem = art.find("Abstract")
        abstract = ""
        if ab_elem is not None:
            parts = []
            for t in ab_elem.findall("AbstractText"):
                label = t.get("Label", "")
                txt = self._text(t)
                parts.append(f"{label}: {txt}" if label else txt)
            abstract = "\n".join(parts)

        # authors
        authors = []
        al = art.find("AuthorList")
        if al is not None:
            for au in al.findall("Author"):
                last = au.findtext("LastName", "")
                fore = au.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {fore[0]}" if fore else last)

        # journal + year
        journal = ""
        year = ""
        volume = ""
        issue = ""
        pages = ""
        j = art.find("Journal")
        if j is not None:
            journal = (
                j.findtext("ISOAbbreviation", "") or j.findtext("Title", "")
            )
            ji = j.find("JournalIssue")
            if ji is not None:
                volume = ji.findtext("Volume", "")
                issue = ji.findtext("Issue", "")
                pd = ji.find("PubDate")
                if pd is not None:
                    year = pd.findtext("Year", "")
                    if not year:
                        year = (pd.findtext("MedlineDate", "") or "")[:4]
        pages = art.findtext("Pagination/MedlinePgn", "")

        # DOI
        doi = ""
        for aid in pa.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text or ""
                break

        # MeSH terms
        mesh = [
            self._text(d)
            for mh in mc.findall(".//MeshHeading")
            if (d := mh.find("DescriptorName")) is not None
        ]

        # keywords
        keywords = [
            kw.text
            for kw in mc.findall(".//Keyword")
            if kw.text
        ]

        return {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "journal": journal,
            "year": year,
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "doi": doi,
            "mesh_terms": mesh,
            "keywords": keywords,
        }

    # ── citation formatting helpers ───────────────────────────────────

    @staticmethod
    def format_apa(a: dict) -> str:
        auths = ", ".join(a["authors"][:6])
        if len(a["authors"]) > 6:
            auths += ", ... "
        return (
            f'{auths} ({a["year"]}). {a["title"]} '
            f'{a["journal"]}, {a["volume"]}'
            f'{"(" + a["issue"] + ")" if a["issue"] else ""}'
            f'{", " + a["pages"] if a["pages"] else ""}. '
            f'{"https://doi.org/" + a["doi"] if a["doi"] else "PMID: " + a["pmid"]}'
        )

    @staticmethod
    def format_vancouver(a: dict) -> str:
        auths = ", ".join(a["authors"][:6])
        if len(a["authors"]) > 6:
            auths += ", et al"
        return (
            f'{auths}. {a["title"]} '
            f'{a["journal"]}. {a["year"]}'
            f'{"; " + a["volume"] if a["volume"] else ""}'
            f'{"(" + a["issue"] + ")" if a["issue"] else ""}'
            f'{":" + a["pages"] if a["pages"] else ""}. '
            f'{"doi: " + a["doi"] if a["doi"] else "PMID: " + a["pmid"]}'
        )

    @staticmethod
    def format_bibtex(a: dict) -> str:
        key = (a["authors"][0].split()[0] if a["authors"] else "Unknown") + a["year"]
        return (
            f"@article{{{key},\n"
            f'  author  = {{{" and ".join(a["authors"])}}},\n'
            f'  title   = {{{a["title"]}}},\n'
            f'  journal = {{{a["journal"]}}},\n'
            f'  year    = {{{a["year"]}}},\n'
            f'  volume  = {{{a["volume"]}}},\n'
            f'  number  = {{{a["issue"]}}},\n'
            f'  pages   = {{{a["pages"]}}},\n'
            f'  doi     = {{{a["doi"]}}},\n'
            f"  pmid    = {{{a['pmid']}}}\n"
            f"}}"
        )

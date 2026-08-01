#!/usr/bin/env python3
"""
pubmed insights — Research intelligence engine

Usage:  pubmed insights <subcommand> [args]

Identifiers:  Every <id> below accepts a PMID (e.g. 35901745)
              or a DOI  (e.g. 10.1038/s41586-023-06291-2).
              DOIs are resolved to PMIDs automatically via NCBI.

Subcommands
  ──────────────────────────────────────────────────────────────
  article  <id>                       Deep breakdown of a single article
  mined                               Cross-analysis of all mined articles
  compare  <id1> <id2>                Side-by-side comparison
  gaps                                Identify gaps in your mined collection
  rank     <query>                    Score & rank mined articles against a query
  timeline                            Chronological view of your mined collection
  brief                               One-page research brief of your collection
  scan     <query> [-n max]           Live search → full keyword/MeSH landscape report
  ask      <question> [-n N]          Ask a question — evidence synthesis from PubMed
  mesh     <id> [id …]                MeSH terms for one or more articles
  meshmap  <id> [id …]                Cross-article MeSH analysis
  ── Elite Commands ─────────────────────────────────────────────
  pico     -P pop -I int [-C cmp] -O out [-n max] [-f type]
                                      PICO framework → precision PubMed query builder
  author   <name> [-n max]            Deep author profile: history, themes, collaborators
  digest   <query> [-d days] [-n max] Recent-literature digest (default: last 90 days)
  heatmap                             Year × MeSH topic density map of mined collection
  network                             Co-authorship network from mined collection
  matrix   <id> [id …]                Pairwise MeSH similarity matrix
  fulltext <id>                       Check PMC free full-text availability
  help                                Show this help

What you get
  ──────────────────────────────────────────────────────────────
  article   study type, structured abstract sections with word counts
            and extracted p-values/ORs/sample sizes, major vs minor
            MeSH, keywords, funding, reference count, DOI

  mined     year/journal distribution, top MeSH thematic core (★ major),
            keyword frequency, recurring authors, unique MeSH angles,
            suggested follow-up searches

  compare   boxed article cards (title, journal, year, study type, refs,
            DOI), temporal gap, abstract key figures side-by-side,
            Jaccard MeSH similarity (major/minor split), keyword overlap,
            shared authors, funding, study design match, bridge searches

  gaps      core themes (≥50% of articles), under-explored angles,
            missing study types, strong MeSH co-occurrence pairs,
            gap-filling search suggestions

  rank      token-weighted relevance score (title ×3, MeSH ×2,
            keywords ×2, abstract ×1, recency +1) with score bars

  timeline  articles grouped by year in boxed frames with major MeSH
            labels and author/journal context

  brief     collection overview, core themes with bars, top keywords,
            articles with quantitative data, missing study types,
            under-explored MeSH, suggested next searches

  mesh      per-article MeSH listing with ★ major-topic flag and
            qualifier subheadings, batched in one API request

  meshmap   per-article listing + cross-article analysis: shared by
            all, shared by some (with frequency bars), unique per
            article, suggested searches from shared major topics

  scan      live PubMed search → aggregate top N results into a full
            landscape report: thematic core (MeSH ≥20%), full MeSH
            frequency table with bars, author keywords, study types,
            top journals, year distribution, strongest MeSH
            co-occurrences, and ready-to-paste PubMed precision
            searches using [MH], [pt] and [tiab] field tags

  ask       natural-language question → evidence synthesis report:
            searches PubMed, fetches top N articles, extracts
            conclusion/results sentences from structured abstracts,
            ranks findings by query relevance, groups evidence by
            themes (MeSH), reports study-type breakdown, key
            statistics, and full per-article source cards

  pico      builds a Boolean PubMed query from PICO elements, runs a
            live scan, ranks evidence by study type, shows MeSH variant
            queries and precision search formulas ready to paste

  author    full author profile: publication timeline, top journals,
            study-type breakdown, MeSH research themes, top keywords,
            frequent collaborators, recent publications, field searches

  digest    date-filtered PubMed search (last N days) showing new
            articles as a reading digest with abstracts, study types,
            MeSH tags, and active-journal summary for the period

  heatmap   ASCII heat-grid: rows = years, columns = top 8 MeSH topics,
            cells shaded by publication density — reveals when each
            research theme surged or declined in your mined collection

  network   co-authorship analysis: central figures, collaboration pairs
            (≥2 shared articles), hub-spoke ASCII diagram, follow-up
            author-pair searches

  matrix    pairwise Jaccard MeSH similarity table for 2+ articles —
            colour-coded (green ≥70%, yellow ≥40%), most-similar pairs
            ranked, divergent-angle bridge searches

  fulltext  checks PMC elink for free full text; returns PMCID,
            PDF link, and alternative open-access fallbacks

Examples
  ──────────────────────────────────────────────────────────────
  pubmed insights article 35901745
  pubmed insights article 10.1038/s41586-023-06291-2
  pubmed insights compare 35901745 34567890
  pubmed insights rank "idiopathic pulmonary fibrosis treatment"
  pubmed insights timeline
  pubmed insights brief
  pubmed insights mesh 39748378 38651330 36499287
  pubmed insights meshmap 39748378 10.1038/s41586-023-06291-2
  pubmed insights scan "idiopathic pulmonary fibrosis" -n 100
  pubmed insights scan "CRISPR cancer therapy"
  pubmed insights ask "Does metformin reduce cancer risk?"
  pubmed insights ask "What is the role of gut microbiome in depression?" -n 80
  pubmed insights mined
  pubmed insights gaps
  pubmed insights pico -P "type 2 diabetes" -I "metformin" -O "HbA1c" -f rct
  pubmed insights author "Smith J" -n 50
  pubmed insights digest "CRISPR cancer" -d 90
  pubmed insights heatmap
  pubmed insights network
  pubmed insights matrix 35901745 34567890 33456789
  pubmed insights fulltext 35901745

Environment
  MINE_FILE   path to mined.json  (default: same directory as this script)
"""

import sys, os, json, re
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.parse import quote_plus
from urllib.error import URLError
from collections import Counter, defaultdict

# ── ANSI palette ───────────────────────────────────────────────────────
B   = '\033[1m'
D   = '\033[2m'
C   = '\033[0;36m'
Y   = '\033[1;33m'
G   = '\033[0;32m'
M   = '\033[0;35m'
RED = '\033[0;31m'
R   = '\033[0m'

BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'

# ── Low-level helpers ──────────────────────────────────────────────────

def _api(endpoint: str) -> str:
    url = f'{BASE}/{endpoint}'
    req = Request(url, headers={'User-Agent': 'PubMedInsights/2.0'})
    try:
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode('utf-8')
    except URLError as e:
        print(f'{RED}Network error:{R} {e}', file=sys.stderr)
        sys.exit(1)


def _txt(el) -> str:
    return ''.join(el.itertext()).strip() if el is not None else ''


def _mine_path() -> str:
    return os.environ.get(
        'MINE_FILE',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mined.json'),
    )


def _load_mine() -> list:
    path = _mine_path()
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _is_doi(identifier: str) -> bool:
    """Return True if *identifier* looks like a DOI (10.xxxx/…)."""
    return bool(re.match(r'^10\.\d{4,9}/.+$', identifier.strip()))


def _resolve_id(identifier: str) -> str:
    """If *identifier* is a DOI, resolve it to a PMID; otherwise return as-is."""
    identifier = identifier.strip()
    if not _is_doi(identifier):
        return identifier
    raw = _api(f'esearch.fcgi?db=pubmed&term={quote_plus(identifier + "[AID]")}&retmode=json')
    ids = json.loads(raw).get('esearchresult', {}).get('idlist', [])
    if not ids:
        print(f'{RED}Error:{R} Could not resolve DOI {identifier} to a PMID.', file=sys.stderr)
        sys.exit(1)
    return ids[0]


def _resolve_ids(identifiers: list) -> list:
    """Resolve a mixed list of PMIDs/DOIs to all PMIDs."""
    return [_resolve_id(i) for i in identifiers]


def _fetch_xml(pmids: list) -> ET.Element:
    raw = _api(f'efetch.fcgi?db=pubmed&id={",".join(pmids)}&retmode=xml')
    return ET.fromstring(raw)


# ── Article parser ─────────────────────────────────────────────────────

def _extract(pa: ET.Element) -> dict:
    mc  = pa.find('MedlineCitation')
    art = mc.find('Article') if mc is not None else None

    pmid  = _txt(mc.find('PMID'))            if mc  is not None else '?'
    title = _txt(art.find('ArticleTitle'))   if art is not None else '?'

    # Abstract sections
    abstract = ''
    if art is not None:
        ab = art.find('Abstract')
        if ab is not None:
            parts = []
            for t in ab.findall('AbstractText'):
                lbl  = t.get('Label', '')
                body = _txt(t)
                parts.append(f'{lbl}: {body}' if lbl else body)
            abstract = '\n'.join(parts)

    # Authors
    authors = []
    if art is not None:
        al = art.find('AuthorList')
        if al is not None:
            for au in al.findall('Author'):
                last = au.findtext('LastName', '')
                fore = au.findtext('ForeName', '')
                if last:
                    authors.append(f'{last} {fore[0]}' if fore else last)

    # Affiliations (deduplicated)
    affs = []
    if art is not None:
        al = art.find('AuthorList')
        if al is not None:
            seen = set()
            for au in al.findall('Author'):
                for af in au.findall('.//Affiliation'):
                    t = _txt(af)
                    if t and t not in seen:
                        affs.append(t); seen.add(t)

    # Journal / year / volume / issue / pages
    journal = year = volume = issue = pages = ''
    if art is not None:
        j = art.find('Journal')
        if j is not None:
            journal = j.findtext('ISOAbbreviation', '') or j.findtext('Title', '')
            ji = j.find('JournalIssue')
            if ji is not None:
                volume = ji.findtext('Volume', '')
                issue  = ji.findtext('Issue',  '')
                pd = ji.find('PubDate')
                if pd is not None:
                    year = pd.findtext('Year', '')
                    if not year:
                        year = (pd.findtext('MedlineDate', '') or '')[:4]
        pages = art.findtext('Pagination/MedlinePgn', '')

    # DOI
    doi = ''
    for aid in pa.findall('.//ArticleId'):
        if aid.get('IdType') == 'doi':
            doi = aid.text or ''; break

    # MeSH  →  {term: is_major}
    mesh: dict[str, bool] = {}
    if mc is not None:
        ml = mc.find('MeshHeadingList')
        if ml is not None:
            for mh in ml.findall('MeshHeading'):
                desc = mh.find('DescriptorName')
                if desc is not None:
                    mesh[_txt(desc)] = desc.get('MajorTopicYN', 'N') == 'Y'

    # Keywords
    kws = []
    if mc is not None:
        kws = [k.text for k in mc.findall('.//Keyword') if k.text]

    # Publication types
    ptypes = []
    if art is not None:
        ptypes = [_txt(pt) for pt in art.findall('.//PublicationType')]

    # Grants
    grants = []
    if art is not None:
        for g in art.findall('.//Grant'):
            agency = g.findtext('Agency', '')
            gid    = g.findtext('GrantID', '')
            if agency:
                grants.append(f'{agency} ({gid})' if gid else agency)

    # Reference count
    ref_count = 0
    rl = pa.find('.//ReferenceList')
    if rl is not None:
        ref_count = len(rl.findall('Reference'))

    return dict(
        pmid=pmid, title=title, abstract=abstract,
        authors=authors, affiliations=affs,
        journal=journal, year=year, volume=volume,
        issue=issue, pages=pages, doi=doi,
        mesh=mesh, keywords=kws, ptypes=ptypes,
        grants=grants, ref_count=ref_count,
    )


# ── Display helpers ────────────────────────────────────────────────────

def _hdr(text: str) -> None:
    print(f'{Y}{text}{R}')

def _rule(n: int = 62) -> None:
    print(f'{D}{"─" * n}{R}')

def _bar(value: int, max_val: int, width: int = 20) -> str:
    if max_val == 0:
        return ''
    return '█' * round(value * width / max_val)

_STAT_RE = re.compile(
    r'(?:p\s*[<=]\s*0\.\d+|\d+\.?\d*\s*%|'
    r'HR\s*[=:]?\s*\d+\.\d+|OR\s*[=:]?\s*\d+\.\d+|'
    r'RR\s*[=:]?\s*\d+\.\d+|CI\s*[=:]?\s*\d+\.\d+[\s\u2013-]+\d+\.\d+|'
    r'n\s*=\s*\d[\d,]*|N\s*=\s*\d[\d,]*|'
    r'\d[\d,]+\s*(?:patients|participants|subjects|samples))',
    re.IGNORECASE,
)


# ══════════════════════════════════════════════════════════════════════
# Subcommands
# ══════════════════════════════════════════════════════════════════════

def cmd_mesh(identifiers: list) -> None:
    """Per-article MeSH listing for one or more PMIDs/DOIs."""
    if not identifiers:
        _usage('mesh <id> [id …]  (PMID or DOI)')

    pmids = _resolve_ids(identifiers)
    print(f'{D}Fetching MeSH terms for {len(pmids)} article(s)…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]

    for a in articles:
        print(f'{B}PMID {a["pmid"]}{R}  {a["title"][:80]}')
        auths = ', '.join(a['authors'][:3]) + ('…' if len(a['authors']) > 3 else '')
        print(f'{D}{auths}  •  {a["journal"]} ({a["year"]}){R}')
        _rule(56)
        if not a['mesh']:
            print(f'  {D}(no MeSH terms indexed yet){R}')
        else:
            for term, is_major in a['mesh'].items():
                star     = f' {Y}★{R}' if is_major else ''
                print(f'  {C}•{R} {term}{star}')
        print()


def cmd_meshmap(identifiers: list) -> None:
    """Cross-article MeSH analysis: shared, frequency, unique per article."""
    if not identifiers:
        _usage('meshmap <id> [id …]  (PMID or DOI)')

    pmids = _resolve_ids(identifiers)
    n = len(pmids)
    print(f'{D}Analysing MeSH across {n} article(s)…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]
    n        = len(articles)

    # ── Per-article listing ─────────────────────────────────────────────
    print(f'{B}══ MeSH Terms per Article ══{R}\n')
    for a in articles:
        major = [t for t, v in a['mesh'].items() if v]
        minor = [t for t, v in a['mesh'].items() if not v]
        auths = ', '.join(a['authors'][:2]) + ('…' if len(a['authors']) > 2 else '')
        print(f'{B}PMID {a["pmid"]}{R}  {a["title"][:72]}')
        print(f'{D}{auths}  •  {a["journal"]} ({a["year"]}){R}')
        if major:
            print(f'  {Y}Major:{R}  {C}{(f", {C}").join(major)}{R}')
        if minor:
            print(f'  {D}Other:  {chr(10).join("          " + t for t in minor) if len(minor)>4 else ", ".join(minor)}{R}')
        if not a['mesh']:
            print(f'  {D}(no MeSH indexed yet){R}')
        print()

    if n < 2:
        return

    # ── Cross-article analysis ──────────────────────────────────────────
    _rule()
    print(f'\n{B}══ Cross-Article MeSH Analysis ══{R}\n')

    mesh_ctr  = Counter(t for a in articles for t in a['mesh'])
    major_ctr = Counter(t for a in articles for t, v in a['mesh'].items() if v)

    # Shared by ALL
    shared_all = sorted(t for t, c in mesh_ctr.items() if c == n)
    if shared_all:
        _hdr(f'Shared by all {n} articles:')
        for t in shared_all:
            star = f' {Y}★{R}' if t in major_ctr else ''
            print(f'  {G}●{R} {t}{star}')
        print()

    # Shared by some (frequency table)
    shared_some = [(t, c) for t, c in mesh_ctr.most_common() if 1 < c < n]
    if shared_some:
        _hdr('Shared by multiple (not all):')
        max_c = shared_some[0][1]
        for t, c in shared_some:
            bar  = _bar(c, max_c, width=10)
            star = f' {Y}★{R}' if t in major_ctr else ''
            print(f'  {c}/{n}  {G}{bar:<10}{R}  {t}{star}')
        print()

    # Unique per article
    unique_per = {a['pmid']: sorted(t for t in a['mesh'] if mesh_ctr[t] == 1)
                  for a in articles}
    has_unique = any(v for v in unique_per.values())
    if has_unique:
        _hdr('Unique MeSH per article (appear in only 1 article):')
        for a in articles:
            uterms = unique_per[a['pmid']]
            if uterms:
                print(f'  {C}PMID {a["pmid"]}{R}  {D}{a["title"][:52]}…{R}')
                for t in uterms:
                    print(f'    {C}◦{R} {t}')
        print()

    # Suggested searches from top shared major terms
    top_shared_major = [t for t, _ in major_ctr.most_common(3) if mesh_ctr[t] >= 2]
    if len(top_shared_major) >= 2:
        _hdr('Suggested Searches (shared major topics):')
        for i in range(min(len(top_shared_major), 3)):
            for j in range(i+1, min(len(top_shared_major), 3)):
                print(f'  {C}→{R} "{top_shared_major[i]}" AND "{top_shared_major[j]}"')
        print()


def cmd_article(identifier: str) -> None:
    pmid = _resolve_id(identifier)
    print(f'{D}Analysing PMID {pmid}…{R}\n')
    root = _fetch_xml([pmid])
    pa   = root.find('.//PubmedArticle')
    if pa is None:
        print(f'{RED}Article not found.{R}'); sys.exit(1)
    a = _extract(pa)

    print(f'{B}{a["title"]}{R}')
    _rule()

    # Source line
    src = f'{a["journal"]}'
    if a['volume']: src += f'  {a["volume"]}'
    if a['issue']:  src += f'({a["issue"]})'
    if a['pages']:  src += f':{a["pages"]}'
    if a['year']:   src += f'  {a["year"]}'
    ref = f'https://doi.org/{a["doi"]}' if a['doi'] else f'PMID {pmid}'
    print(f'{Y}Source:{R}   {src}  {D}{ref}{R}')
    print()

    if a['ptypes']:
        print(f'{Y}Study Type:{R}  {", ".join(a["ptypes"])}')

    # Authors
    n_auth = len(a['authors'])
    first  = a['authors'][0]  if a['authors'] else '?'
    last_a = a['authors'][-1] if a['authors'] else '?'
    print(f'{Y}Authors:{R}    {n_auth} — {B}{first}{R} (first), {B}{last_a}{R} (last)')
    for af in a['affiliations'][:3]:
        print(f'            {D}{af[:110]}{R}')
    if len(a['affiliations']) > 3:
        print(f'            {D}… and {len(a["affiliations"])-3} more{R}')
    print()

    # Abstract breakdown
    if a['abstract']:
        print(f'{B}── Abstract Breakdown ──{R}')
        for section in a['abstract'].split('\n'):
            m = re.match(r'^([A-Z][A-Z /\-]+):\s*(.+)', section)
            if m:
                print(f'\n  {C}{m.group(1)}{R}')
                body = m.group(2)
            else:
                body = section
            wc    = len(body.split())
            stats = _STAT_RE.findall(body)
            print(f'  {D}({wc} words){R}')
            if stats:
                print(f'  {G}Key figures:{R}  {" | ".join(stats[:8])}')
        print()
    else:
        print(f'{D}(no abstract available){R}\n')

    # MeSH
    major = [k for k, v in a['mesh'].items() if v]
    minor = [k for k, v in a['mesh'].items() if not v]
    if major:
        print(f'{Y}Major Topics:{R}  {", ".join(major)}')
    if minor:
        print(f'{Y}Other MeSH:{R}    {", ".join(minor[:10])}')
        if len(minor) > 10:
            print(f'               {D}… and {len(minor)-10} more{R}')

    if a['keywords']:
        print(f'{Y}Keywords:{R}     {", ".join(a["keywords"])}')
    print()

    if a['grants']:
        print(f'{Y}Funding:{R}      {", ".join(sorted(set(a["grants"]))[:5])}')
    if a['ref_count']:
        print(f'{Y}References:{R}   {a["ref_count"]} cited works')
    if a['doi']:
        print(f'{Y}DOI:{R}          https://doi.org/{a["doi"]}')


def cmd_mined() -> None:
    entries = _load_mine()
    if not entries:
        print('Mining list is empty.'); sys.exit(0)
    pmids = [e['pmid'] for e in entries]

    print(f'{D}Fetching metadata for {len(pmids)} mined articles…{R}')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]
    n        = len(articles)

    print(f'\n{B}══ Insights across {n} mined articles ══{R}\n')

    mesh_ctr  = Counter()
    kw_ctr    = Counter()
    auth_ctr  = Counter()
    jour_ctr  = Counter()
    year_ctr  = Counter()
    ptype_ctr = Counter()
    major_ctr = Counter()

    for a in articles:
        for au in a['authors']:       auth_ctr[au] += 1
        if a['journal']:              jour_ctr[a['journal']] += 1
        if a['year']:                 year_ctr[a['year']] += 1
        for t, is_major in a['mesh'].items():
            mesh_ctr[t] += 1
            if is_major: major_ctr[t] += 1
        for kw in a['keywords']:      kw_ctr[kw.lower()] += 1
        for pt in a['ptypes']:        ptype_ctr[pt] += 1

    if year_ctr:
        _hdr('Year Distribution:')
        mx = max(year_ctr.values())
        for yr in sorted(year_ctr):
            c = year_ctr[yr]
            print(f'  {C}{yr}{R}  {G}{"█" * c}{R}  {c}')
        print()

    if jour_ctr:
        _hdr('Journals:')
        for j, c in jour_ctr.most_common(10):
            print(f'  {c:>2}x  {j}')
        if len(jour_ctr) > 10:
            print(f'  {D}… and {len(jour_ctr)-10} more{R}')
        print()

    if ptype_ctr:
        _hdr('Study Types:')
        for pt, c in ptype_ctr.most_common(8):
            print(f'  {c:>2}x  {pt}')
        print()

    if mesh_ctr:
        _hdr('Top MeSH Terms (thematic core):')
        for term, c in mesh_ctr.most_common(15):
            pct  = c * 100 // n
            bar  = '▓' * (pct // 5)
            star = f' {Y}★{R}' if term in major_ctr else ''
            print(f'  {c:>2}/{n}  {G}{bar:<20}{R}  {term}{star}')
        print(f'  {D}★ = major topic{R}\n')

    if kw_ctr:
        _hdr('Keyword Frequency:')
        for kw, c in kw_ctr.most_common(15):
            print(f'  {c:>2}x  {kw}')
        print()

    repeat = [(a, c) for a, c in auth_ctr.most_common() if c > 1]
    if repeat:
        _hdr('Recurring Authors (appear in 2+ articles):')
        for au, c in repeat[:10]:
            print(f'  {c:>2}x  {au}')
        print()

    if mesh_ctr:
        unique = [t for t, c in mesh_ctr.items() if c == 1]
        if unique and n > 2:
            _hdr('Unique MeSH — potential unexplored angles:')
            for t in sorted(unique)[:15]:
                print(f'  {C}•{R} {t}')
            if len(unique) > 15:
                print(f'  {D}… and {len(unique)-15} more{R}')
            print()

    if len(mesh_ctr) >= 2:
        top = [t for t, _ in mesh_ctr.most_common(3)]
        _hdr('Suggested Follow-up Searches:')
        for i in range(len(top)):
            for j in range(i+1, len(top)):
                print(f'  {C}→{R} "{top[i]}" AND "{top[j]}"')
        if major_ctr:
            top_major = [t for t, _ in major_ctr.most_common(2)]
            if len(top_major) == 2:
                print(f'  {C}→{R} "{top_major[0]}" AND "{top_major[1]}" AND review[pt]')
        print()


def cmd_compare(id1: str, id2: str) -> None:
    pmid1, pmid2 = _resolve_id(id1), _resolve_id(id2)
    print(f'{D}Comparing PMID {pmid1} vs {pmid2}…{R}\n')
    root     = _fetch_xml([pmid1, pmid2])
    articles = root.findall('.//PubmedArticle')
    if len(articles) < 2:
        print(f'{RED}Could not fetch both articles.{R}'); sys.exit(1)

    a, b = _extract(articles[0]), _extract(articles[1])

    def _auths(art, n=3):
        s = ', '.join(art['authors'][:n])
        return s + ('…' if len(art['authors']) > n else '')

    def _wrap(text, width=60):
        lines = []
        while len(text) > width:
            idx = text.rfind(' ', 0, width)
            if idx < 1: idx = width
            lines.append(text[:idx])
            text = text[idx+1:]
        lines.append(text)
        return lines

    # ── Article cards ─────────────────────────────────────────────────
    W = 64
    print(f'{B}╔{"═"*W}╗{R}')
    for label, art in (('A', a), ('B', b)):
        sep = '╠' if label == 'B' else '║'
        if label == 'B':
            print(f'{B}╠{"═"*W}╣{R}')
        print(f'{B}║{R}  {B}{label}{R}  PMID {C}{art["pmid"]}{R}')
        for line in _wrap(art['title'], W-4):
            print(f'{B}║{R}  {line}')
        print(f'{B}║{R}  {D}{_auths(art)}{R}')
        src = f'{art["journal"]}'
        if art['volume']: src += f'  {art["volume"]}'
        if art['issue']:  src += f'({art["issue"]})'
        if art['year']:   src += f'  {art["year"]}'
        print(f'{B}║{R}  {Y}{src}{R}')
        ptype_str = ', '.join(art['ptypes'][:2])
        extras = []
        if ptype_str:         extras.append(ptype_str)
        if art['ref_count']:  extras.append(f'{art["ref_count"]} refs')
        if extras: print(f'{B}║{R}  {D}{";  ".join(extras)}{R}')
        if art['doi']:        print(f'{B}║{R}  {D}https://doi.org/{art["doi"]}{R}')
    print(f'{B}╚{"═"*W}╝{R}\n')

    # ── Temporal gap ──────────────────────────────────────────────────
    try:
        yr_a, yr_b = int(a['year']), int(b['year'])
        gap = abs(yr_a - yr_b)
        if gap > 0:
            newer = f'Article {"A" if yr_a > yr_b else "B"}'
            print(f'{Y}Temporal gap:{R}  {gap} year{"s" if gap != 1 else ""}  '
                  f'({newer} is newer,  A={yr_a}  B={yr_b})')
            print()
    except (ValueError, TypeError):
        pass

    # ── Abstract key figures ──────────────────────────────────────────
    stats_a = _STAT_RE.findall(a['abstract'])
    stats_b = _STAT_RE.findall(b['abstract'])
    if stats_a or stats_b:
        _hdr('Key Figures from Abstracts:')
        if stats_a:
            print(f'  A:  {G}{" | ".join(stats_a[:6])}{R}')
        else:
            print(f'  A:  {D}(no quantitative data detected){R}')
        if stats_b:
            print(f'  B:  {G}{" | ".join(stats_b[:6])}{R}')
        else:
            print(f'  B:  {D}(no quantitative data detected){R}')
        print()

    # ── MeSH similarity (Jaccard) ─────────────────────────────────────
    ma, mb   = set(a['mesh']), set(b['mesh'])
    shared   = ma & mb
    only_a   = ma - mb
    only_b   = mb - ma
    union    = ma | mb
    jaccard  = len(shared) * 100 // max(len(union), 1)

    # Split shared into major-in-either vs minor-in-both
    shared_major = sorted(t for t in shared if a['mesh'].get(t) or b['mesh'].get(t))
    shared_minor = sorted(t for t in shared if t not in shared_major)

    _hdr(f'MeSH Similarity  Jaccard {jaccard}%  '
         f'({len(shared)} shared / {len(union)} total  |  '
         f'{len(only_a)} only A, {len(only_b)} only B)')
    if shared_major: print(f'  {G}★ Shared major:{R}  {", ".join(shared_major[:8])}')
    if shared_minor: print(f'  {G}  Shared other:{R}  {", ".join(shared_minor[:8])}')
    if only_a:       print(f'  {C}  Only A:{R}        {", ".join(sorted(only_a)[:8])}')
    if only_b:       print(f'  {C}  Only B:{R}        {", ".join(sorted(only_b)[:8])}')
    print()

    # ── Keyword overlap ───────────────────────────────────────────────
    ka = set(k.lower() for k in a['keywords'])
    kb = set(k.lower() for k in b['keywords'])
    if ka or kb:
        _hdr('Keyword Overlap:')
        skw = ka & kb
        if skw:   print(f'  {G}Shared:{R}   {", ".join(sorted(skw)[:10])}')
        if ka-kb: print(f'  {C}Only A:{R}   {", ".join(sorted(ka-kb)[:8])}')
        if kb-ka: print(f'  {C}Only B:{R}   {", ".join(sorted(kb-ka)[:8])}')
        print()

    # ── Shared authors ────────────────────────────────────────────────
    shared_auth = set(a['authors']) & set(b['authors'])
    if shared_auth:
        _hdr('Shared Authors:')
        print(f'  {", ".join(sorted(shared_auth))}')
        print()

    # ── Study design ──────────────────────────────────────────────────
    pta = ', '.join(sorted(a['ptypes'])) or '(not specified)'
    ptb = ', '.join(sorted(b['ptypes'])) or '(not specified)'
    same_design = set(a['ptypes']) == set(b['ptypes'])
    _hdr('Study Design:')
    print(f'  A: {pta}')
    print(f'  B: {ptb}')
    if same_design:
        print(f'  {D}↳ same design{R}')
    print()

    # ── Funding ───────────────────────────────────────────────────────
    ga = sorted(set(a['grants']))[:3]
    gb = sorted(set(b['grants']))[:3]
    if ga or gb:
        _hdr('Funding:')
        if ga: print(f'  A: {", ".join(ga)}')
        else:  print(f'  A: {D}(none on record){R}')
        if gb: print(f'  B: {", ".join(gb)}')
        else:  print(f'  B: {D}(none on record){R}')
        print()

    # ── Reference counts ─────────────────────────────────────────────
    if a['ref_count'] or b['ref_count']:
        _hdr('Reference Counts:')
        print(f'  A: {a["ref_count"] or "n/a"} cited works')
        print(f'  B: {b["ref_count"] or "n/a"} cited works')
        print()

    # ── Bridge search (prefer major-topic unique terms) ───────────────
    unique_combined = (only_a | only_b) - shared
    if len(unique_combined) >= 2:
        # Prefer terms that are major topics in their article
        majors_unique = sorted(
            t for t in unique_combined
            if (t in only_a and a['mesh'].get(t)) or (t in only_b and b['mesh'].get(t))
        )
        top2 = (majors_unique[:2] if len(majors_unique) >= 2
                else sorted(unique_combined)[:2])
        _hdr('Bridge Search:  connect their unique major angles')
        print(f'  {C}→{R} "{top2[0]}" AND "{top2[1]}"')
        # Also suggest a review of the shared core
        if shared_major:
            core = shared_major[0]
            print(f'  {C}→{R} "{core}" AND "{top2[0]}" AND review[pt]')
        print()


def cmd_gaps() -> None:
    entries = _load_mine()
    if len(entries) < 3:
        print('Need at least 3 mined articles for gap analysis.'); sys.exit(1)
    pmids = [e['pmid'] for e in entries]

    print(f'{D}Analysing gaps across {len(pmids)} articles…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]
    n        = len(articles)

    article_mesh = [set(a['mesh'].keys()) for a in articles]
    all_mesh     = Counter(t for ms in article_mesh for t in ms)
    all_ptypes   = Counter(pt for a in articles for pt in a['ptypes'])

    print(f'{B}══ Gap Analysis ({n} articles) ══{R}\n')

    core = [(t, c) for t, c in all_mesh.most_common() if c >= n * 0.5]
    if core:
        _hdr('Core Themes (≥50% of articles):')
        for t, c in core:
            print(f'  {G}●{R} {t}  ({c}/{n})')
        print()

    rare = [(t, c) for t, c in all_mesh.items() if c == 1]
    if rare and n > 2:
        _hdr('Under-explored Angles (appear in only 1 article):')
        for t, _ in sorted(rare, key=lambda x: x[0])[:20]:
            print(f'  {C}○{R} {t}')
        if len(rare) > 20:
            print(f'  {D}… and {len(rare)-20} more{R}')
        print()

    COMMON_TYPES = {
        'Review', 'Systematic Review', 'Meta-Analysis',
        'Randomized Controlled Trial', 'Clinical Trial',
        'Observational Study', 'Case Reports',
    }
    missing = COMMON_TYPES - set(all_ptypes.keys())
    if missing:
        _hdr('Study Types NOT in Your Collection:')
        for t in sorted(missing):
            print(f'  {C}?{R} {t}')
        print(f'  {D}Consider: <topic> AND <type>[pt]{R}')
        print()

    if n >= 3:
        cooccur = Counter()
        for ms in article_mesh:
            terms = sorted(ms)
            for i in range(len(terms)):
                for j in range(i+1, len(terms)):
                    cooccur[(terms[i], terms[j])] += 1
        strong = [(p, c) for p, c in cooccur.most_common(50) if c >= 2]
        if strong:
            _hdr('Strong Topic Pairs (co-occur in 2+ articles):')
            for (ta, tb), c in strong[:8]:
                print(f'  {c}x  {ta}  ↔  {tb}')
            print()

    if core and rare:
        core_terms = [t for t, _ in core[:2]]
        rare_terms = [t for t, _ in rare[:3]]
        _hdr('Suggested Gap-Filling Searches:')
        for ct in core_terms:
            for rt in rare_terms[:2]:
                print(f'  {C}→{R} "{ct}" AND "{rt}"')
        if missing:
            mt = sorted(missing)[0]
            print(f'  {C}→{R} "{core_terms[0]}" AND {mt.lower().replace(" ", "+")}[pt]')
        print()


def cmd_rank(query: str) -> None:
    """Score and rank all mined articles by relevance to a free-text query."""
    entries = _load_mine()
    if not entries:
        print('Mining list is empty.'); sys.exit(0)
    pmids = [e['pmid'] for e in entries]

    print(f'{D}Ranking {len(pmids)} articles against: {B}{query}{R}{D}…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]

    q_tokens = set(re.findall(r'\w+', query.lower()))

    scored = []
    for a in articles:
        score = 0
        # Title (weight ×3)
        score += len(q_tokens & set(re.findall(r'\w+', a['title'].lower()))) * 3
        # Abstract (weight ×1)
        score += len(q_tokens & set(re.findall(r'\w+', a['abstract'].lower())))
        # MeSH (weight ×2)
        score += len(q_tokens & set(re.findall(r'\w+', ' '.join(a['mesh']).lower()))) * 2
        # Keywords (weight ×2)
        score += len(q_tokens & set(re.findall(r'\w+', ' '.join(a['keywords']).lower()))) * 2
        # Recency bonus
        try:
            if int(a['year']) >= 2020: score += 1
        except (ValueError, TypeError):
            pass
        scored.append((score, a))

    scored.sort(key=lambda x: x[0], reverse=True)
    max_score = scored[0][0] if scored and scored[0][0] > 0 else 1

    print(f'{B}Relevance Ranking — "{query}"{R}')
    _rule()

    for rank, (score, a) in enumerate(scored, 1):
        bar = _bar(score, max_score, width=16)
        pct = round(score * 100 / max_score)
        medal = f' {Y}★ TOP MATCH{R}' if rank == 1 else ''
        print(f'\n  {B}#{rank}{R}{medal}')
        print(f'  {G}{bar:<16}{R}  {D}score {score}  ({pct}%){R}')
        print(f'  PMID {C}{a["pmid"]}{R}  {a["title"][:80]}')
        auths = ', '.join(a['authors'][:2]) + ('…' if len(a['authors']) > 2 else '')
        print(f'  {D}{auths}  •  {a["journal"]} ({a["year"]}){R}')
    print()


def cmd_timeline() -> None:
    """Chronological publication view of all mined articles."""
    entries = _load_mine()
    if not entries:
        print('Mining list is empty.'); sys.exit(0)
    pmids = [e['pmid'] for e in entries]

    print(f'{D}Building timeline for {len(pmids)} articles…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]

    by_year: dict[str, list] = defaultdict(list)
    for a in articles:
        by_year[a['year'] or '?'].append(a)

    print(f'{B}══ Publication Timeline ({len(articles)} articles) ══{R}\n')

    for yr in sorted(by_year.keys()):
        arts = by_year[yr]
        label = f'{yr}  ({len(arts)} article{"s" if len(arts)!=1 else ""})'
        print(f'{Y}┌── {label} {"─"*(max(0,50-len(label)))}┐{R}')
        for a in arts:
            major = [t for t, v in a['mesh'].items() if v][:2]
            mesh_str = f'  {D}[{", ".join(major)}]{R}' if major else ''
            auths = ', '.join(a['authors'][:2]) + ('…' if len(a['authors']) > 2 else '')
            print(f'{Y}│{R}  {B}{a["pmid"]}{R}  {a["title"][:68]}')
            print(f'{Y}│{R}  {D}{auths}  •  {a["journal"]}{R}{mesh_str}')
        print(f'{Y}└{"─"*54}┘{R}\n')


def cmd_brief() -> None:
    """One-page research brief of the entire mined collection."""
    entries = _load_mine()
    if not entries:
        print('Mining list is empty.'); sys.exit(0)
    pmids = [e['pmid'] for e in entries]

    print(f'{D}Generating research brief for {len(pmids)} articles…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]
    n        = len(articles)

    years      = sorted(set(a['year'] for a in articles if a['year']))
    jour_ctr   = Counter(a['journal'] for a in articles if a['journal'])
    mesh_ctr   = Counter(t for a in articles for t in a['mesh'])
    kw_ctr     = Counter(k.lower() for a in articles for k in a['keywords'])
    ptype_ctr  = Counter(pt for a in articles for pt in a['ptypes'])
    all_ptypes = set(pt for a in articles for pt in a['ptypes'])

    yr_range = f'{years[0]}–{years[-1]}' if len(years) > 1 else (years[0] if years else '?')

    print(f'{B}╔══════════════════════════════════════════════════════════╗{R}')
    print(f'{B}║                  RESEARCH BRIEF                         ║{R}')
    print(f'{B}╚══════════════════════════════════════════════════════════╝{R}')
    print()

    # Overview
    _hdr('Collection Overview')
    print(f'  Articles:    {B}{n}{R}')
    print(f'  Date range:  {B}{yr_range}{R}')
    top3j = ', '.join(j for j, _ in jour_ctr.most_common(3))
    print(f'  Journals:    {B}{len(jour_ctr)}{R} unique  {D}({top3j}){R}')
    study_str = ', '.join(f'{c}x {pt}' for pt, c in ptype_ctr.most_common(3))
    print(f'  Study types: {D}{study_str}{R}')
    print()

    # Core themes
    core = [(t, c) for t, c in mesh_ctr.most_common(10) if c >= n * 0.25]
    if core:
        _hdr('Core Themes  (MeSH in ≥25% of articles)')
        for t, c in core:
            bar = _bar(c, n, width=12)
            print(f'  {G}{bar:<12}{R}  {t}  {D}({c}/{n}){R}')
        print()

    # Top keywords
    if kw_ctr:
        _hdr('Top Keywords')
        print(f'  {", ".join(kw for kw, _ in kw_ctr.most_common(10))}')
        print()

    # Quantitative findings
    findings = []
    for a in articles:
        stats = _STAT_RE.findall(a['abstract'])
        if stats:
            findings.append((a['pmid'], a['title'][:55], stats[:3]))
    if findings:
        _hdr('Articles with Quantitative Data')
        for pmid, title, stats in findings[:6]:
            print(f'  {C}PMID {pmid}{R}  {title}…')
            print(f'  {D}{" | ".join(stats)}{R}')
        print()

    # Research gaps
    COMMON_TYPES = {
        'Review', 'Systematic Review', 'Meta-Analysis',
        'Randomized Controlled Trial', 'Clinical Trial',
        'Observational Study', 'Case Reports',
    }
    missing   = COMMON_TYPES - all_ptypes
    rare_mesh = [t for t, c in mesh_ctr.items() if c == 1]

    _hdr('Research Gaps')
    if missing:
        print(f'  Missing study types:  {D}{", ".join(sorted(missing))}{R}')
    if rare_mesh:
        print(f'  Under-explored MeSH:  {D}{", ".join(sorted(rare_mesh)[:6])}{R}')
        if len(rare_mesh) > 6:
            print(f'  {D}  … and {len(rare_mesh)-6} more{R}')
    print()

    # Suggested next searches
    if len(mesh_ctr) >= 2:
        top = [t for t, _ in mesh_ctr.most_common(2)]
        _hdr('Suggested Next Searches')
        print(f'  {C}→{R} "{top[0]}" AND "{top[1]}"')
        if missing:
            mt = sorted(missing)[0]
            print(f'  {C}→{R} "{top[0]}" AND {mt.lower().replace(" ", "+")}[pt]')
        print()


def cmd_scan(args: list) -> None:
    """Scan a PubMed query and map the full keyword / MeSH landscape."""
    # Parse: words + optional -n max
    n_max = 50
    query_parts: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in ('-n', '--max') and i+1 < len(args):
            try: n_max = min(int(args[i+1]), 200)
            except ValueError: pass
            i += 2
        else:
            query_parts.append(args[i])
            i += 1
    query = ' '.join(query_parts)
    if not query:
        _usage('scan <query> [-n max]')

    print(f'{D}Searching PubMed: {B}{query}{R}  {D}(top {n_max})…{R}\n')

    # ── Search ───────────────────────────────────────────────────────────
    raw       = _api(f'esearch.fcgi?db=pubmed&term={quote_plus(query)}&retmax={n_max}&retmode=json&sort=relevance')
    sr        = json.loads(raw)['esearchresult']
    total     = int(sr['count'])
    pmids     = sr['idlist']

    if not pmids:
        print(f'{RED}No results for: {query}{R}'); sys.exit(0)

    print(f'{D}Fetching metadata for {len(pmids)} of {total:,} total results…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]
    n        = len(articles)

    # ── Aggregate ───────────────────────────────────────────────────────
    mesh_ctr  = Counter()
    major_ctr = Counter()
    kw_ctr    = Counter()
    jour_ctr  = Counter()
    year_ctr  = Counter()
    ptype_ctr = Counter()
    auth_ctr  = Counter()

    for a in articles:
        for t, is_major in a['mesh'].items():
            mesh_ctr[t] += 1
            if is_major: major_ctr[t] += 1
        for kw in a['keywords']: kw_ctr[kw.lower()] += 1
        if a['journal']:  jour_ctr[a['journal']] += 1
        if a['year']:     year_ctr[a['year']] += 1
        for pt in a['ptypes']: ptype_ctr[pt] += 1
        for au in a['authors']: auth_ctr[au] += 1

    years    = sorted(year_ctr.keys())
    yr_range = f'{years[0]}–{years[-1]}' if len(years) > 1 else (years[0] if years else '?')

    # ── Header ───────────────────────────────────────────────────────────
    print(f'{B}╔{"═"*62}╗{R}')
    print(f'{B}║{R}  PubMed Landscape Scan')
    print(f'{B}║{R}  Query:     {B}{query}{R}')
    print(f'{B}║{R}  Total:     {B}{total:,}{R} results in PubMed')
    print(f'{B}║{R}  Analysed:  top {n}  │  date range: {B}{yr_range}{R}  │  {B}{len(jour_ctr)}{R} journals')
    print(f'{B}╚{"═"*62}╝{R}\n')

    # ── Thematic core (≥20% threshold) ──────────────────────────────
    threshold = max(1, n // 5)
    core      = [(t, c) for t, c in mesh_ctr.most_common(25) if c >= threshold]
    if core:
        _hdr(f'Thematic Core  (MeSH in ≥20% of {n} articles):')
        max_c = core[0][1]
        for t, c in core:
            bar  = _bar(c, max_c, width=22)
            star = f' {Y}★{R}' if t in major_ctr else ''
            print(f'  {c:>3}/{n}  {G}{bar:<22}{R}  {t}{star}')
        print(f'  {D}★ = major topic{R}\n')

    # ── Full MeSH frequency table ─────────────────────────────────
    if mesh_ctr:
        _hdr(f'Full MeSH Frequency  (top 35 of {len(mesh_ctr)} unique terms):')
        for t, c in mesh_ctr.most_common(35):
            pct  = c * 100 // n
            bar  = '▒' * (pct // 3)
            star = f' {Y}★{R}' if t in major_ctr else ''
            print(f'  {c:>3}/{n}  {C}{bar:<34}{R}  {t}{star}')
        if len(mesh_ctr) > 35:
            print(f'  {D}… and {len(mesh_ctr)-35} more unique terms{R}')
        print()

    # ── Author keywords ────────────────────────────────────────────
    if kw_ctr:
        _hdr('Author Keywords:')
        for kw, c in kw_ctr.most_common(20):
            print(f'  {c:>3}x  {kw}')
        if len(kw_ctr) > 20:
            print(f'  {D}… and {len(kw_ctr)-20} more{R}')
        print()

    # ── Study types ─────────────────────────────────────────────────
    if ptype_ctr:
        _hdr('Study Types:')
        for pt, c in ptype_ctr.most_common(10):
            print(f'  {c:>3}x  {pt}')
        print()

    # ── Top journals ─────────────────────────────────────────────────
    if jour_ctr:
        _hdr('Top Journals:')
        for j, c in jour_ctr.most_common(10):
            print(f'  {c:>3}x  {j}')
        print()

    # ── Year distribution ────────────────────────────────────────────
    if year_ctr:
        _hdr('Year Distribution:')
        mx = max(year_ctr.values())
        for yr in sorted(year_ctr.keys()):
            c   = year_ctr[yr]
            bar = _bar(c, mx, width=20)
            print(f'  {C}{yr}{R}  {G}{bar:<20}{R}  {c}')
        print()

    # ── MeSH co-occurrence ──────────────────────────────────────────
    min_cooccur = max(2, n // 8)
    cooccur     = Counter()
    for a in articles:
        terms = sorted(a['mesh'].keys())
        for p in range(len(terms)):
            for q in range(p+1, len(terms)):
                cooccur[(terms[p], terms[q])] += 1
    strong = [(pair, c) for pair, c in cooccur.most_common(60) if c >= min_cooccur]
    if strong:
        _hdr(f'Strongest MeSH Co-occurrences  (appear together in ≥{min_cooccur} articles):')
        for (ta, tb), c in strong[:12]:
            print(f'  {c:>3}x  {ta}  ↔  {tb}')
        print()

    # ── Precision search suggestions ───────────────────────────────
    top_major = [t for t, _ in major_ctr.most_common(6)]
    top_all   = [t for t, _ in mesh_ctr.most_common(6)]
    top_kw    = [kw for kw, _ in kw_ctr.most_common(4)]

    _hdr('Precision Search Suggestions  (ready-to-use PubMed syntax):')

    # MeSH heading combos
    shown = set()
    for ii in range(min(4, len(top_major))):
        for jj in range(ii+1, min(5, len(top_major))):
            pair = (top_major[ii], top_major[jj])
            if pair not in shown:
                print(f'  {C}→{R} "{pair[0]}"[MH] AND "{pair[1]}"[MH]')
                shown.add(pair)

    # Add study-type filters for most frequent MeSH
    HIGH_VALUE_TYPES = {
        'Systematic Review': 'systematic+review[pt]',
        'Meta-Analysis':     'meta-analysis[pt]',
        'Randomized Controlled Trial': 'randomized+controlled+trial[pt]',
        'Clinical Trial':    'clinical+trial[pt]',
    }
    for pt_label, pt_tag in HIGH_VALUE_TYPES.items():
        if pt_label in ptype_ctr and top_major:
            print(f'  {C}→{R} "{top_major[0]}"[MH] AND {pt_tag}')

    # Title/abstract keyword combos
    if len(top_kw) >= 2:
        print(f'  {C}→{R} "{top_kw[0]}"[tiab] AND "{top_kw[1]}"[tiab]')

    # Broad open search for discovery
    if top_all:
        print(f'  {C}→{R} "{top_all[0]}"[MH]  {D}(broad — use to discover related articles){R}')

    print()


# ── Evidence-extraction helpers for ask ────────────────────────────────

_CONCL_LABELS = {
    'CONCLUSION', 'CONCLUSIONS', 'FINDINGS', 'RESULTS',
    'MAIN RESULTS', 'MAIN OUTCOME', 'MAIN OUTCOMES',
    'INTERPRETATION', 'SIGNIFICANCE', 'SUMMARY',
    'RESULTS AND CONCLUSION', 'RESULTS AND CONCLUSIONS',
    'CONCLUSIONS AND RELEVANCE', 'CONCLUSIONS/SIGNIFICANCE',
}


def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter — good enough for abstracts."""
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in parts if len(s.strip()) > 20]


def _sentence_relevance(sentence: str, q_tokens: set[str]) -> float:
    """Score a sentence's relevance to the query tokens."""
    words = set(re.findall(r'\w{3,}', sentence.lower()))
    if not words:
        return 0.0
    overlap = words & q_tokens
    return len(overlap) / max(len(q_tokens), 1)


def _extract_evidence(abstract: str, q_tokens: set[str]) -> list[dict]:
    """Extract evidence-bearing sentences from a (possibly structured) abstract.

    Returns list of {'text': str, 'label': str, 'relevance': float, 'stats': list}
    sorted by priority (conclusion-like first, then by relevance).
    """
    if not abstract:
        return []

    findings: list[dict] = []

    for section in abstract.split('\n'):
        m = re.match(r'^([A-Z][A-Z /\-]+):\s*(.+)', section)
        if m:
            label, body = m.group(1).strip(), m.group(2)
        else:
            label, body = '', section

        is_conclusion = label.upper() in _CONCL_LABELS

        for sent in _split_sentences(body):
            rel  = _sentence_relevance(sent, q_tokens)
            stats = _STAT_RE.findall(sent)
            # Boost conclusion sections and sentences with stats
            priority = rel
            if is_conclusion:
                priority += 0.5
            if stats:
                priority += 0.2
            findings.append({
                'text': sent,
                'label': label,
                'relevance': rel,
                'priority': priority,
                'stats': stats,
            })

    findings.sort(key=lambda f: f['priority'], reverse=True)
    return findings


def cmd_ask(args: list) -> None:
    """Answer a natural-language question using PubMed evidence synthesis."""
    n_max = 60
    query_parts: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in ('-n', '--max') and i + 1 < len(args):
            try:
                n_max = min(int(args[i + 1]), 200)
            except ValueError:
                pass
            i += 2
        else:
            query_parts.append(args[i])
            i += 1
    question = ' '.join(query_parts)
    if not question:
        _usage('ask <question> [-n max]')

    print(f'{D}Question:{R}  {B}{question}{R}')
    print(f'{D}Searching PubMed (top {n_max})…{R}\n')

    # ── Search ────────────────────────────────────────────────────────
    raw   = _api(f'esearch.fcgi?db=pubmed&term={quote_plus(question)}'
                 f'&retmax={n_max}&retmode=json&sort=relevance')
    sr    = json.loads(raw)['esearchresult']
    total = int(sr['count'])
    pmids = sr['idlist']

    if not pmids:
        print(f'{RED}No PubMed results for your question.{R}')
        print(f'{D}Try rephrasing or using more specific medical terms.{R}')
        return

    print(f'{D}Found {total:,} results — analysing top {len(pmids)}…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]
    n        = len(articles)

    # ── Query tokens for relevance scoring ────────────────────────────
    STOPWORDS = {
        'the', 'and', 'for', 'are', 'was', 'were', 'been', 'being',
        'have', 'has', 'had', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'can', 'shall', 'that', 'this',
        'with', 'from', 'into', 'about', 'between', 'through', 'after',
        'before', 'during', 'what', 'which', 'where', 'when', 'how',
        'who', 'whom', 'why', 'not', 'but', 'than', 'then', 'also',
        'there', 'their', 'them', 'they', 'its', 'our', 'your',
        'more', 'most', 'some', 'any', 'all', 'each', 'every',
        'other', 'such', 'only', 'same', 'very', 'just', 'because',
    }
    q_tokens = set(re.findall(r'\w{3,}', question.lower())) - STOPWORDS

    # ── Score articles by relevance ───────────────────────────────────
    scored: list[tuple[float, dict, list[dict]]] = []
    for a in articles:
        # Token-overlap scoring (same weights as cmd_rank)
        score = 0.0
        title_tokens = set(re.findall(r'\w{3,}', a['title'].lower()))
        abs_tokens   = set(re.findall(r'\w{3,}', a['abstract'].lower()))
        mesh_tokens  = set(re.findall(r'\w{3,}', ' '.join(a['mesh']).lower()))
        kw_tokens    = set(re.findall(r'\w{3,}', ' '.join(a['keywords']).lower()))

        score += len(q_tokens & title_tokens) * 3
        score += len(q_tokens & abs_tokens)
        score += len(q_tokens & mesh_tokens) * 2
        score += len(q_tokens & kw_tokens) * 2
        try:
            if int(a['year']) >= 2020:
                score += 1
        except (ValueError, TypeError):
            pass

        evidence = _extract_evidence(a['abstract'], q_tokens)
        scored.append((score, a, evidence))

    scored.sort(key=lambda x: x[0], reverse=True)

    # ── Header ────────────────────────────────────────────────────────
    print(f'{B}╔══════════════════════════════════════════════════════════════╗{R}')
    print(f'{B}║{R}  {B}Evidence-Based Answer{R}')
    print(f'{B}║{R}')
    q_display = question if len(question) <= 56 else question[:53] + '…'
    print(f'{B}║{R}  Q: {C}{q_display}{R}')
    print(f'{B}║{R}  Sources: {B}{n}{R} articles from {B}{total:,}{R} PubMed results')
    # Year range
    years = sorted(set(a['year'] for _, a, _ in scored if a['year']))
    if years:
        yr_range = f'{years[0]}–{years[-1]}' if len(years) > 1 else years[0]
        print(f'{B}║{R}  Date range: {B}{yr_range}{R}')
    print(f'{B}╚══════════════════════════════════════════════════════════════╝{R}\n')

    # ── Key Findings (top evidence sentences) ─────────────────────────
    _hdr('Key Findings')
    seen_sents = set()
    finding_num = 0
    for score, a, evidence in scored:
        if finding_num >= 8:
            break
        for ev in evidence:
            if finding_num >= 8:
                break
            sent = ev['text']
            # Deduplicate near-identical sentences
            sent_key = sent[:60].lower()
            if sent_key in seen_sents:
                continue
            seen_sents.add(sent_key)
            if ev['priority'] < 0.15:
                continue
            finding_num += 1
            # Citation tag
            first_author = a['authors'][0].split()[0] if a['authors'] else '?'
            cite = f'{first_author} et al., {a["year"]}'
            label_tag = f'  {D}[{ev["label"]}]{R}' if ev['label'] else ''
            print(f'  {G}{finding_num}.{R} {sent}')
            tag_parts = [f'{C}[{cite}]{R}']
            if ev['stats']:
                tag_parts.append(f'{G}{ " | ".join(ev["stats"][:3])}{R}')
            if ev['label']:
                tag_parts.append(f'{D}[{ev["label"]}]{R}')
            print(f'     {"  ".join(tag_parts)}')
            print()

    if finding_num == 0:
        print(f'  {D}(No strongly relevant conclusion sentences extracted.{R}')
        print(f'  {D} The abstracts may lack structured sections or direct answers.){R}\n')

    # ── Study-Type Breakdown ──────────────────────────────────────────
    ptype_ctr = Counter(pt for _, a, _ in scored for pt in a['ptypes'])
    if ptype_ctr:
        _hdr('Evidence Profile  (study types in source articles)')
        # Order by evidence hierarchy
        HIERARCHY = [
            'Meta-Analysis', 'Systematic Review', 'Randomized Controlled Trial',
            'Clinical Trial', 'Observational Study', 'Review',
            'Comparative Study', 'Case Reports',
        ]
        ordered = []
        for pt in HIERARCHY:
            if pt in ptype_ctr:
                ordered.append((pt, ptype_ctr[pt]))
        for pt, c in ptype_ctr.most_common():
            if pt not in HIERARCHY:
                ordered.append((pt, c))
        for pt, c in ordered[:10]:
            bar = _bar(c, n, width=12)
            print(f'  {c:>3}x  {G}{bar:<12}{R}  {pt}')
        print()

    # ── Thematic Clusters (from MeSH) ─────────────────────────────────
    mesh_ctr  = Counter(t for _, a, _ in scored for t in a['mesh'])
    major_ctr = Counter(t for _, a, _ in scored for t, v in a['mesh'].items() if v)
    threshold = max(2, n // 5)
    core = [(t, c) for t, c in mesh_ctr.most_common(20) if c >= threshold]
    if core:
        _hdr('Thematic Clusters  (recurring MeSH across sources)')
        for t, c in core[:12]:
            star = f' {Y}★{R}' if t in major_ctr else ''
            bar  = _bar(c, n, width=14)
            print(f'  {c:>3}/{n}  {G}{bar:<14}{R}  {t}{star}')
        print()

    # ── Key Statistics (aggregated across all abstracts) ──────────────
    all_stats: list[tuple[str, str, str]] = []  # (stat, cite, pmid)
    for _, a, _ in scored:
        abs_stats = _STAT_RE.findall(a['abstract'])
        if abs_stats:
            first_author = a['authors'][0].split()[0] if a['authors'] else '?'
            cite = f'{first_author} et al., {a["year"]}'
            for s in abs_stats[:3]:
                all_stats.append((s, cite, a['pmid']))
    if all_stats:
        _hdr('Key Statistics from Abstracts')
        for stat, cite, pmid in all_stats[:12]:
            print(f'  {G}•{R} {stat}  {D}— {cite} (PMID {pmid}){R}')
        if len(all_stats) > 12:
            print(f'  {D}… and {len(all_stats)-12} more{R}')
        print()

    # ── Consensus / Divergence signal ─────────────────────────────────
    # Simple heuristic: if many articles share the same major MeSH it
    # indicates convergence; if spread is wide it indicates divergence.
    if major_ctr and n >= 5:
        top_major = major_ctr.most_common(1)[0]
        coverage = top_major[1] * 100 // n
        _hdr('Consensus Signal')
        if coverage >= 60:
            print(f'  {G}Strong convergence{R} — {top_major[1]}/{n} articles share '
                  f'major topic "{top_major[0]}" ({coverage}%)')
        elif coverage >= 35:
            print(f'  {Y}Moderate convergence{R} — {top_major[1]}/{n} articles share '
                  f'major topic "{top_major[0]}" ({coverage}%)')
        else:
            print(f'  {C}Diverse evidence{R} — top major topic "{top_major[0]}" '
                  f'covers only {coverage}% of sources')
        print(f'  {D}(This is a thematic proxy, not a clinical certainty metric.){R}')
        print()

    # ── Top Sources (article cards) ───────────────────────────────────
    top_n = min(8, n)
    _hdr(f'Top {top_n} Sources  (ranked by relevance)')
    max_score = scored[0][0] if scored and scored[0][0] > 0 else 1
    for rank, (score, a, evidence) in enumerate(scored[:top_n], 1):
        bar = _bar(int(score), int(max_score), width=10)
        pct = round(score * 100 / max_score) if max_score else 0
        first = a['authors'][0] if a['authors'] else '?'
        auths = ', '.join(a['authors'][:2]) + ('…' if len(a['authors']) > 2 else '')
        ref = f'https://doi.org/{a["doi"]}' if a['doi'] else f'PMID {a["pmid"]}'
        print(f'  {B}#{rank}{R}  {G}{bar:<10}{R}  {D}score {int(score)} ({pct}%){R}')
        print(f'      {a["title"][:80]}')
        print(f'      {D}{auths}  •  {a["journal"]} ({a["year"]}){R}')
        print(f'      {D}{ref}{R}')
        # Show best evidence sentence from this article
        if evidence and evidence[0]['priority'] >= 0.1:
            snippet = evidence[0]['text'][:120]
            if len(evidence[0]['text']) > 120:
                snippet += '…'
            print(f'      {C}▸ {snippet}{R}')
        print()

    # ── Suggested deeper searches ─────────────────────────────────────
    top_major_terms = [t for t, _ in major_ctr.most_common(4)]
    if len(top_major_terms) >= 2:
        _hdr('Dig Deeper  (precision PubMed searches)')
        # MeSH combo
        print(f'  {C}→{R} "{top_major_terms[0]}"[MH] AND "{top_major_terms[1]}"[MH]')
        # Systematic review filter
        print(f'  {C}→{R} "{top_major_terms[0]}"[MH] AND systematic+review[pt]')
        # Recent
        import datetime
        cur_year = datetime.datetime.now().year
        print(f'  {C}→{R} "{top_major_terms[0]}"[MH] AND {cur_year-2}:{cur_year}[dp]')
        print()

    print(f'{D}─ End of evidence synthesis for: {question}{R}\n')


def cmd_pico(args: list) -> None:
    """Build a precision PubMed query from PICO framework elements, then run a live scan."""
    import datetime as _dt

    population = intervention = comparison = outcome = ''
    n_max = 50
    filter_type = ''
    i = 0
    while i < len(args):
        a = args[i]
        if a in ('-P', '--population') and i + 1 < len(args):
            population = args[i + 1]; i += 2
        elif a in ('-I', '--intervention') and i + 1 < len(args):
            intervention = args[i + 1]; i += 2
        elif a in ('-C', '--comparison') and i + 1 < len(args):
            comparison = args[i + 1]; i += 2
        elif a in ('-O', '--outcome') and i + 1 < len(args):
            outcome = args[i + 1]; i += 2
        elif a in ('-n', '--max') and i + 1 < len(args):
            try: n_max = min(int(args[i + 1]), 200)
            except ValueError: pass
            i += 2
        elif a in ('-f', '--filter') and i + 1 < len(args):
            filter_type = args[i + 1]; i += 2
        else:
            i += 1

    if not any([population, intervention, outcome]):
        _usage('pico -P <population> -I <intervention> [-C <comparison>] -O <outcome> '
               '[-n max] [-f rct|review|meta|ct]')

    filter_map = {
        'rct':    'randomized controlled trial[pt]',
        'review': 'systematic review[pt]',
        'sr':     'systematic review[pt]',
        'meta':   'meta-analysis[pt]',
        'ct':     'clinical trial[pt]',
    }
    filter_clause = filter_map.get(filter_type.lower(), '')

    tiab_parts = [f'"{v}"[tiab]' for v in [population, intervention, outcome] if v]
    if filter_clause:
        tiab_parts.append(filter_clause)
    tiab_query = ' AND '.join(tiab_parts)

    mesh_parts = [f'"{v}"[MH]' for v in [population, intervention] if v]
    if outcome:
        mesh_parts.append(f'"{outcome}"[tiab]')
    if filter_clause:
        mesh_parts.append(filter_clause)
    mesh_query = ' AND '.join(mesh_parts)

    print(f'\n{B}╔{"═"*62}╗{R}')
    print(f'{B}║{R}  PICO Framework → PubMed Query Builder')
    print(f'{B}╚{"═"*62}╝{R}\n')

    labels = [
        ('P', 'Population / Problem', population),
        ('I', 'Intervention',         intervention),
        ('C', 'Comparison',           comparison),
        ('O', 'Outcome',              outcome),
    ]
    for key, label, val in labels:
        if val:
            print(f'  {C}{key}{R}  {label:<24}  {B}{val}{R}')
        else:
            print(f'  {D}{key}  {label:<24}  (not specified){R}')
    print()

    print(f'{Y}Query [tiab — broad]:{R}')
    print(f'  {G}{tiab_query}{R}')
    if mesh_query != tiab_query:
        print(f'\n{Y}Query [MH — precise]:{R}')
        print(f'  {C}{mesh_query}{R}')
    if filter_clause:
        print(f'\n{D}Study-type filter: {filter_clause}{R}')
    print()

    print(f'{D}Searching PubMed (top {n_max})…{R}\n')
    raw   = _api(f'esearch.fcgi?db=pubmed&term={quote_plus(tiab_query)}'
                 f'&retmax={n_max}&retmode=json&sort=relevance')
    sr    = json.loads(raw)['esearchresult']
    total = int(sr['count'])
    pmids = sr['idlist']

    if not pmids:
        print(f'{RED}No results for this PICO query.{R}')
        print(f'{D}Tip: broaden terms, remove the Comparison element, or drop -f filter.{R}')
        return

    print(f'{G}Found {total:,} results{R} — analysing top {len(pmids)}…\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]
    n        = len(articles)

    ptype_ctr = Counter(pt for a in articles for pt in a['ptypes'])
    jour_ctr  = Counter(a['journal'] for a in articles if a['journal'])
    year_ctr  = Counter(a['year'] for a in articles if a['year'])
    mesh_ctr  = Counter(t for a in articles for t in a['mesh'])
    major_ctr = Counter(t for a in articles for t, v in a['mesh'].items() if v)

    _hdr('Evidence Summary')
    yrs = sorted(year_ctr.keys())
    yr_range = f'{yrs[0]}–{yrs[-1]}' if len(yrs) > 1 else (yrs[0] if yrs else '?')
    print(f'  Total in PubMed:  {B}{total:,}{R}')
    print(f'  Date range:       {B}{yr_range}{R}')
    print(f'  Unique journals:  {B}{len(jour_ctr)}{R}')
    print()

    if ptype_ctr:
        _hdr('Evidence Hierarchy:')
        HIER = ['Meta-Analysis', 'Systematic Review', 'Randomized Controlled Trial',
                'Clinical Trial', 'Observational Study', 'Review']
        ordered = [(pt, ptype_ctr[pt]) for pt in HIER if pt in ptype_ctr]
        for pt in ptype_ctr:
            if pt not in HIER:
                ordered.append((pt, ptype_ctr[pt]))
        for pt, c in ordered[:8]:
            bar = _bar(c, n, width=14)
            print(f'  {c:>3}x  {G}{bar:<14}{R}  {pt}')
        print()

    threshold = max(1, n // 4)
    core = [(t, c) for t, c in mesh_ctr.most_common(12) if c >= threshold]
    if core:
        _hdr('Key MeSH Terms:')
        for t, c in core:
            star = f' {Y}★{R}' if t in major_ctr else ''
            bar  = _bar(c, n, width=16)
            print(f'  {c:>3}/{n}  {G}{bar:<16}{R}  {t}{star}')
        print()

    _hdr('Precision Search Formulas:')
    print(f'  {C}[tiab]{R}  {tiab_query}')
    if mesh_query:
        print(f'  {C}[MH]  {R}  {mesh_query}')
    if population and intervention:
        mq_base = f'"{population}"[MH] AND "{intervention}"[MH]'
        print(f'  {C}[RCT] {R}  {mq_base} AND randomized controlled trial[pt]')
        print(f'  {C}[SYS] {R}  {mq_base} AND systematic review[pt]')
        print(f'  {C}[META]{R}  {mq_base} AND meta-analysis[pt]')
    cur = _dt.datetime.now().year
    if population:
        print(f'  {C}[NEW] {R}  "{population}"[MH] AND {cur-2}:{cur}[dp]')
    print()

    _hdr(f'Top Articles:')
    for idx, a in enumerate(articles[:5], 1):
        auths = ', '.join(a['authors'][:2]) + ('…' if len(a['authors']) > 2 else '')
        ref   = f'https://doi.org/{a["doi"]}' if a['doi'] else f'PMID {a["pmid"]}'
        ptstr = f'  {Y}{", ".join(a["ptypes"][:2])}{R}' if a['ptypes'] else ''
        print(f'  {B}#{idx}{R}  {a["title"][:78]}')
        print(f'      {D}{auths}  •  {a["journal"]} ({a["year"]}){R}{ptstr}')
        print(f'      {D}{ref}{R}')
        print()


def cmd_author(args: list) -> None:
    """Deep author profile: publication history, themes, collaborators."""
    n_max = 50
    name_parts: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in ('-n', '--max') and i + 1 < len(args):
            try: n_max = min(int(args[i + 1]), 200)
            except ValueError: pass
            i += 2
        else:
            name_parts.append(args[i]); i += 1

    name = ' '.join(name_parts)
    if not name:
        _usage('author <name> [-n max]  (e.g. "Smith J" or "Smith John")')

    print(f'{D}Searching PubMed for author: {B}{name}{R}  {D}(top {n_max})…{R}\n')
    raw   = _api(f'esearch.fcgi?db=pubmed&term={quote_plus(name + "[AU]")}'
                 f'&retmax={n_max}&retmode=json&sort=date')
    sr    = json.loads(raw)['esearchresult']
    total = int(sr['count'])
    pmids = sr['idlist']

    if not pmids:
        print(f'{RED}No publications found for: {name}{R}')
        print(f'{D}Try: "Smith J" (last name + initial) or just the last name.{R}')
        return

    print(f'{D}Found {total:,} publications — analysing top {len(pmids)}…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]
    n        = len(articles)

    mesh_ctr   = Counter()
    major_ctr  = Counter()
    kw_ctr     = Counter()
    jour_ctr   = Counter()
    year_ctr   = Counter()
    ptype_ctr  = Counter()
    coauth_ctr = Counter()
    name_lower = name.lower()

    for a in articles:
        if a['journal']:  jour_ctr[a['journal']] += 1
        if a['year']:     year_ctr[a['year']] += 1
        for t, is_maj in a['mesh'].items():
            mesh_ctr[t] += 1
            if is_maj: major_ctr[t] += 1
        for kw in a['keywords']:  kw_ctr[kw.lower()] += 1
        for pt in a['ptypes']:    ptype_ctr[pt] += 1
        for au in a['authors']:
            if name_lower not in au.lower():
                coauth_ctr[au] += 1

    yrs = sorted(year_ctr.keys())
    yr_range = f'{yrs[0]}–{yrs[-1]}' if len(yrs) > 1 else (yrs[0] if yrs else '?')

    print(f'{B}╔{"═"*60}╗{R}')
    print(f'{B}║{R}  Author Profile: {B}{name}{R}')
    print(f'{B}║{R}  Total in PubMed:  {B}{total:,}{R}')
    if yrs:
        print(f'{B}║{R}  Active years:     {B}{yr_range}{R}')
    print(f'{B}╚{"═"*60}╝{R}\n')

    if year_ctr:
        _hdr('Publication Timeline:')
        mx = max(year_ctr.values())
        for yr in sorted(year_ctr.keys()):
            c = year_ctr[yr]
            bar = _bar(c, mx, width=22)
            print(f'  {C}{yr}{R}  {G}{bar:<22}{R}  {c}')
        print()

    if jour_ctr:
        _hdr('Top Journals:')
        mx = jour_ctr.most_common(1)[0][1]
        for j, c in jour_ctr.most_common(8):
            bar = _bar(c, mx, width=14)
            print(f'  {c:>3}x  {G}{bar:<14}{R}  {j}')
        if len(jour_ctr) > 8:
            print(f'  {D}… and {len(jour_ctr)-8} more{R}')
        print()

    if ptype_ctr:
        _hdr('Study Types:')
        for pt, c in ptype_ctr.most_common(6):
            print(f'  {c:>3}x  {pt}')
        print()

    if mesh_ctr:
        _hdr('Research Themes (MeSH):')
        for term, c in mesh_ctr.most_common(14):
            pct  = c * 100 // n
            bar  = _bar(c, n, width=16)
            star = f' {Y}★{R}' if term in major_ctr else ''
            print(f'  {c:>3}/{n}  {G}{bar:<16}{R}  {term}{star}')
        print(f'  {D}★ = major topic{R}\n')

    if kw_ctr:
        _hdr('Frequent Keywords:')
        top_kws = ', '.join(f'{kw} ({c}x)' for kw, c in kw_ctr.most_common(10))
        print(f'  {top_kws}')
        print()

    if coauth_ctr:
        _hdr('Frequent Collaborators:')
        mx = coauth_ctr.most_common(1)[0][1]
        for au, c in coauth_ctr.most_common(10):
            bar = _bar(c, mx, width=12)
            print(f'  {c:>3}x  {G}{bar:<12}{R}  {au}')
        print()

    _hdr('Recent Publications:')
    for a in articles[:5]:
        auths = ', '.join(a['authors'][:2]) + ('…' if len(a['authors']) > 2 else '')
        ref   = f'https://doi.org/{a["doi"]}' if a['doi'] else f'PMID {a["pmid"]}'
        print(f'  {B}{a["pmid"]}{R}  {C}({a["year"]}){R}  {a["title"][:70]}')
        print(f'  {D}{a["journal"]}  {ref}{R}')
        print()

    if mesh_ctr:
        top_m = [t for t, _ in mesh_ctr.most_common(3)]
        _hdr('Explore This Author\'s Field:')
        if len(top_m) >= 2:
            print(f'  {C}→{R} "{top_m[0]}"[MH] AND "{top_m[1]}"[MH]')
        print(f'  {C}→{R} {name}[AU] AND systematic review[pt]')
        print(f'  {C}→{R} {name}[AU] AND meta-analysis[pt]')
        if top_m:
            print(f'  {C}→{R} "{top_m[0]}"[MH] AND {name}[AU]')
        print()


def cmd_digest(args: list) -> None:
    """Recent-literature digest — new PubMed publications over the last N days."""
    import datetime as _dt

    n_max = 30
    days  = 90
    query_parts: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in ('-n', '--max') and i + 1 < len(args):
            try: n_max = min(int(args[i + 1]), 200)
            except ValueError: pass
            i += 2
        elif args[i] in ('-d', '--days') and i + 1 < len(args):
            try: days = int(args[i + 1])
            except ValueError: pass
            i += 2
        else:
            query_parts.append(args[i]); i += 1

    query = ' '.join(query_parts)
    if not query:
        _usage('digest <query> [-d days] [-n max]')

    cutoff    = (_dt.datetime.now() - _dt.timedelta(days=days)).strftime('%Y/%m/%d')
    today_str = _dt.datetime.now().strftime('%Y/%m/%d')
    date_tag  = f'{cutoff}:{today_str}[edat]'
    full_q    = f'({query}) AND {date_tag}'

    print(f'\n{B}╔{"═"*62}╗{R}')
    print(f'{B}║{R}  Research Digest — Recent Literature')
    print(f'{B}║{R}  Topic:   {B}{query}{R}')
    print(f'{B}║{R}  Period:  last {B}{days}{R} days  ({cutoff} → today)')
    print(f'{B}╚{"═"*62}╝{R}\n')

    print(f'{D}Searching: {full_q}…{R}\n')
    raw   = _api(f'esearch.fcgi?db=pubmed&term={quote_plus(full_q)}'
                 f'&retmax={n_max}&retmode=json&sort=date')
    sr    = json.loads(raw)['esearchresult']
    total = int(sr['count'])
    pmids = sr['idlist']

    if not pmids:
        print(f'{Y}No new publications in the last {days} days for: {query}{R}')
        print(f'{D}Try: -d 180 for a wider window, or broaden your terms.{R}')
        return

    print(f'{G}● {total:,} new result{"s" if total != 1 else ""}{R} '
          f'in the last {days} days  (showing {len(pmids)})\n')

    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]

    ptype_ctr = Counter(pt for a in articles for pt in a['ptypes'])
    jour_ctr  = Counter(a['journal'] for a in articles if a['journal'])

    if ptype_ctr:
        types_str = '  |  '.join(f'{c}x {pt}' for pt, c in ptype_ctr.most_common(5))
        print(f'{D}Study types this period: {types_str}{R}\n')

    _rule()
    print()

    for a in articles:
        auths   = ', '.join(a['authors'][:3]) + ('…' if len(a['authors']) > 3 else '')
        ref     = f'https://doi.org/{a["doi"]}' if a['doi'] else f'PMID {a["pmid"]}'
        major   = [t for t, v in a['mesh'].items() if v][:3]
        mstr    = f'  {D}[{", ".join(major)}]{R}' if major else ''
        ptstr   = f'  {Y}{", ".join(a["ptypes"][:2])}{R}' if a['ptypes'] else ''
        print(f'{B}{a["pmid"]}{R}  {a["title"][:80]}')
        print(f'{D}{auths}  •  {a["journal"]} ({a["year"]}){R}{ptstr}{mstr}')
        print(f'{D}{ref}{R}')
        if a['abstract']:
            snippet = a['abstract'].replace('\n', ' ')[:160].strip()
            print(f'{C}▸ {snippet}{"…" if len(a["abstract"]) > 160 else ""}{R}')
        print()

    if total > n_max:
        print(f'{D}… {total - n_max:,} more results. Use -n {min(total, 200)} to see more.{R}\n')

    if jour_ctr and len(jour_ctr) > 1:
        _hdr('Active Journals This Period:')
        for j, c in jour_ctr.most_common(6):
            print(f'  {c:>2}x  {j}')
        print()

    if ptype_ctr:
        HIER = ['Meta-Analysis', 'Systematic Review', 'Randomized Controlled Trial',
                'Clinical Trial']
        highlight = [(pt, ptype_ctr[pt]) for pt in HIER if pt in ptype_ctr]
        if highlight:
            _hdr('High-Value Evidence in This Period:')
            for pt, c in highlight:
                print(f'  {G}●{R} {c}x  {pt}')
            print()


def cmd_heatmap() -> None:
    """ASCII heatmap: year rows × top MeSH topic columns across mined collection."""
    entries = _load_mine()
    if not entries:
        print('Mining list is empty.'); sys.exit(0)
    if len(entries) < 2:
        print('Need at least 2 mined articles for a heatmap.'); sys.exit(0)
    pmids = [e['pmid'] for e in entries]

    print(f'{D}Building heatmap for {len(pmids)} articles…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]

    mesh_ctr  = Counter(t for a in articles for t in a['mesh'])
    top_terms = [t for t, _ in mesh_ctr.most_common(8)]
    years     = sorted(set(a['year'] for a in articles if a['year']))

    if not top_terms or not years:
        print(f'{RED}Not enough MeSH/year data for heatmap.{R}'); return

    # Build matrix
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a in articles:
        if not a['year']: continue
        for t in a['mesh']:
            if t in top_terms:
                matrix[a['year']][t] += 1

    CELLS = [' ', '░', '▒', '▓', '█']
    col_w  = 5  # cell display width

    print(f'{B}══ MeSH × Year Heatmap  ({len(articles)} articles) ══{R}\n')

    # Column key (numbered labels)
    print(f'  {"Year":<6}  ', end='')
    for idx in range(len(top_terms)):
        print(f'  {C}T{idx+1:<{col_w-1}}{R}', end='')
    print()
    print(f'  {"─"*6}  ', end='')
    for _ in top_terms:
        print(f'  {"─"*col_w}', end='')
    print()

    max_cell = max((matrix[yr][t] for yr in years for t in top_terms), default=1) or 1
    for yr in years:
        print(f'  {C}{yr}{R}  ', end='')
        for t in top_terms:
            c   = matrix[yr][t]
            idx = min(int(c * (len(CELLS) - 1) / max_cell), len(CELLS) - 1) if max_cell > 0 else 0
            cell = CELLS[idx] * col_w
            color = G if c >= max_cell * 0.7 else (Y if c > 0 else D)
            print(f'  {color}{cell}{R}', end='')
        print(f'   {D}{sum(matrix[yr][t] for t in top_terms):>2} hits{R}')
    print()

    print(f'{D}  Density: {R}', end='')
    for i, sym in enumerate(CELLS):
        label = f'{round(i * max_cell / max(len(CELLS)-1,1))}x'
        disp  = sym if sym != ' ' else '·'
        print(f'{D}  {disp}={label}{R}', end='')
    print('\n')

    print(f'{Y}Term Key:{R}')
    for idx, term in enumerate(top_terms):
        bar = _bar(mesh_ctr[term], mesh_ctr.most_common(1)[0][1], width=12)
        print(f'  {C}T{idx+1}{R}  {G}{bar:<12}{R}  {term}  {D}({mesh_ctr[term]} articles){R}')
    print()


def cmd_network() -> None:
    """Co-authorship network analysis from mined collection."""
    from itertools import combinations as _comb

    entries = _load_mine()
    if not entries:
        print('Mining list is empty.'); sys.exit(0)
    if len(entries) < 3:
        print('Need at least 3 mined articles for network analysis.'); sys.exit(0)
    pmids = [e['pmid'] for e in entries]

    print(f'{D}Building co-authorship network from {len(pmids)} articles…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]

    auth_art_ctr = Counter()
    coauth_ctr   = Counter()

    for a in articles:
        aus = a['authors']
        for au in aus:
            auth_art_ctr[au] += 1
        if len(aus) >= 2:
            for au1, au2 in _comb(aus[:10], 2):
                coauth_ctr[tuple(sorted([au1, au2]))] += 1

    top_authors = auth_art_ctr.most_common(12)
    top_pairs   = [(p, c) for p, c in coauth_ctr.most_common(20) if c >= 2]

    print(f'{B}══ Co-authorship Network  ({len(articles)} articles) ══{R}\n')

    if top_authors:
        _hdr('Central Figures  (most articles in collection):')
        mx = top_authors[0][1]
        for au, c in top_authors:
            bar = _bar(c, mx, width=16)
            print(f'  {c:>2} article{"s" if c != 1 else " "}  {G}{bar:<16}{R}  {B}{au}{R}')
        print()

    if top_pairs:
        _hdr('Frequent Collaborations  (co-authored 2+ articles together):')
        for (au1, au2), c in top_pairs[:12]:
            print(f'  {c}x  {C}{au1}{R}  ↔  {C}{au2}{R}')
        print()

    if top_authors:
        center_name, center_count = top_authors[0]
        hub_connections = [
            (au2 if au1 == center_name else au1, c)
            for (au1, au2), c in coauth_ctr.most_common()
            if au1 == center_name or au2 == center_name
        ]
        if hub_connections:
            _hdr(f'Hub Diagram — {center_name}  ({center_count} articles):')
            print(f'  {B}{center_name[:30]}{R}')
            for i, (au, c) in enumerate(hub_connections[:8]):
                branch = '└──' if i == len(hub_connections[:8]) - 1 else '├──'
                print(f'  {D}{branch}{R} {au[:36]}  {D}({c}x){R}')
            print()

    # Author clusters: groups of 3+ who all co-authored together
    cluster_candidates = set()
    for (au1, au2), c in coauth_ctr.most_common(30):
        if c >= 2:
            cluster_candidates.add(au1)
            cluster_candidates.add(au2)
    if len(cluster_candidates) >= 3:
        _hdr('Collaboration Cluster:')
        for au in sorted(cluster_candidates)[:8]:
            n_collabs = sum(1 for (a1, a2) in coauth_ctr if a1 == au or a2 == au)
            print(f'  {C}●{R} {au}  {D}({n_collabs} co-author pair{"s" if n_collabs!=1 else ""}){R}')
        print()

    if top_pairs:
        _hdr('Follow These Collaborations on PubMed:')
        for (au1, au2), _ in top_pairs[:4]:
            last1 = au1.split()[0]
            last2 = au2.split()[0]
            print(f'  {C}→{R} "{last1}"[AU] AND "{last2}"[AU]')
        print()


def cmd_matrix(identifiers: list) -> None:
    """Pairwise MeSH Jaccard similarity matrix for 2+ articles."""
    if len(identifiers) < 2:
        _usage('matrix <id1> <id2> [id3 …]  (PMID or DOI)')

    pmids = _resolve_ids(identifiers)
    print(f'{D}Computing similarity matrix for {len(pmids)} articles…{R}\n')
    root     = _fetch_xml(pmids)
    articles = [_extract(pa) for pa in root.findall('.//PubmedArticle')]
    n        = len(articles)

    def _short(a: dict) -> str:
        auth = a['authors'][0].split()[0] if a['authors'] else 'Anon'
        return f'{auth} {a["year"]}' if a['year'] else f'PMID{a["pmid"]}'

    def _jaccard(a1: dict, a2: dict) -> int:
        s1 = set(a1['mesh'].keys())
        s2 = set(a2['mesh'].keys())
        union = len(s1 | s2)
        return len(s1 & s2) * 100 // union if union else 0

    labels = [_short(a) for a in articles]
    col_w  = 10
    HIGH, MED = 70, 40

    print(f'{B}══ Pairwise MeSH Similarity Matrix ══{R}\n')

    # Header row
    print(f'  {"":12}', end='')
    for lbl in labels:
        print(f'  {C}{lbl[:col_w]:>{col_w}}{R}', end='')
    print()
    print(f'  {"─"*12}', end='')
    for _ in labels:
        print(f'  {"─"*col_w}', end='')
    print()

    matrix: list[list[int]] = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            matrix[i][j] = _jaccard(articles[i], articles[j]) if i != j else 100

    for i, lbl in enumerate(labels):
        print(f'  {B}{lbl[:12]:<12}{R}', end='')
        for j in range(n):
            pct = matrix[i][j]
            cell = f'{pct}%' if i != j else '—'
            if i == j:
                color = D
            elif pct >= HIGH:
                color = G
            elif pct >= MED:
                color = Y
            else:
                color = D
            print(f'  {color}{cell:>{col_w}}{R}', end='')
        print()
    print()
    print(f'  {D}Jaccard (MeSH overlap %)  '
          f'{G}green ≥{HIGH}%  {R}{D}{Y}yellow ≥{MED}%{R}\n')

    # Ranked pairs
    pairs: list[tuple[int, str, str, str, str]] = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((matrix[i][j], labels[i], labels[j],
                          articles[i]['pmid'], articles[j]['pmid']))
    pairs.sort(reverse=True)

    _hdr('Most Similar Pairs:')
    for pct, l1, l2, p1, p2 in pairs[:5]:
        color = G if pct >= HIGH else (Y if pct >= MED else D)
        print(f'  {color}{pct:>3}%{R}  {l1}  ↔  {l2}  {D}(PMID {p1} vs {p2}){R}')
    print()

    # Divergent pair — candidates for a bridge search
    if len(pairs) > 1:
        pct_low, l1_low, l2_low, p1_low, p2_low = pairs[-1]
        a1_low = next(a for a in articles if a['pmid'] == p1_low)
        a2_low = next(a for a in articles if a['pmid'] == p2_low)
        only_1 = set(a1_low['mesh']) - set(a2_low['mesh'])
        only_2 = set(a2_low['mesh']) - set(a1_low['mesh'])
        unique  = sorted(only_1 | only_2)
        if len(unique) >= 2:
            _hdr(f'Bridge Search  (most divergent pair: {l1_low} ↔ {l2_low}, {pct_low}%):')
            print(f'  {C}→{R} "{unique[0]}" AND "{unique[1]}"')
            print()


def cmd_fulltext(identifier: str) -> None:
    """Check PMC free full-text availability and return direct links."""
    pmid = _resolve_id(identifier)
    print(f'{D}Checking PMC availability for PMID {pmid}…{R}\n')

    raw = _api(f'elink.fcgi?dbfrom=pubmed&db=pmc&id={pmid}&cmd=neighbor&retmode=json')
    pmc_ids: list[str] = []
    try:
        data = json.loads(raw)
        for ls in data.get('linksets', []):
            for lsdb in ls.get('linksetdbs', []):
                if lsdb.get('dbto') == 'pmc':
                    pmc_ids = [str(x) for x in lsdb.get('links', [])]
                    break
    except (json.JSONDecodeError, KeyError):
        pass

    root = _fetch_xml([pmid])
    pa   = root.find('.//PubmedArticle')
    if pa is None:
        print(f'{RED}Article not found.{R}'); sys.exit(1)
    a = _extract(pa)

    print(f'{B}{a["title"][:80]}{R}')
    auths = ', '.join(a['authors'][:3]) + ('…' if len(a['authors']) > 3 else '')
    print(f'{D}{auths}  •  {a["journal"]} ({a["year"]}){R}\n')

    if pmc_ids:
        pmcid = pmc_ids[0]
        print(f'{G}✓ Full text freely available in PubMed Central{R}')
        print(f'  {Y}PMCID:{R}   PMC{pmcid}')
        print(f'  {Y}Viewer:{R}  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/')
        print(f'  {Y}PDF:{R}     https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/')
    else:
        print(f'{Y}✗ Full text not freely available in PMC{R}')
        if a['doi']:
            print(f'  {C}→{R} Try: https://doi.org/{a["doi"]}  (may be behind paywall)')
        print(f'  {C}→{R} Unpaywall: https://api.unpaywall.org/v2/{a["doi"] or pmid}')
        print(f'  {C}→{R} Europe PMC: https://europepmc.org/article/MED/{pmid}')

    print()
    print(f'{Y}PMID:{R}    {pmid}')
    if a['doi']:
        print(f'{Y}DOI:{R}     https://doi.org/{a["doi"]}')
    print(f'{Y}PubMed:{R}  https://pubmed.ncbi.nlm.nih.gov/{pmid}/')
    print()

    if a['ptypes']:
        print(f'{D}Study type: {", ".join(a["ptypes"][:2])}{R}')
    if a['grants']:
        print(f'{D}Funding:    {", ".join(sorted(set(a["grants"]))[:3])}{R}')


def cmd_help() -> None:
    print(__doc__)


# ── Dispatch ───────────────────────────────────────────────────────────

_DISPATCH = {
    'scan':     lambda args: cmd_scan(args),
    'ask':      lambda args: cmd_ask(args) if args else _usage('ask <question> [-n max]'),
    'mesh':     lambda args: cmd_mesh(args),
    'meshmap':  lambda args: cmd_meshmap(args),
    'article':  lambda args: cmd_article(args[0]) if args else _usage('article <id>  (PMID or DOI)'),
    'mined':    lambda args: cmd_mined(),
    'compare':  lambda args: cmd_compare(args[0], args[1]) if len(args) >= 2 else _usage('compare <id1> <id2>  (PMID or DOI)'),
    'gaps':     lambda args: cmd_gaps(),
    'rank':     lambda args: cmd_rank(' '.join(args)) if args else _usage('rank <query>'),
    'timeline': lambda args: cmd_timeline(),
    'brief':    lambda args: cmd_brief(),
    # ── Elite commands ──
    'pico':     lambda args: cmd_pico(args),
    'author':   lambda args: cmd_author(args) if args else _usage('author <name> [-n max]'),
    'digest':   lambda args: cmd_digest(args) if args else _usage('digest <query> [-d days] [-n max]'),
    'heatmap':  lambda args: cmd_heatmap(),
    'network':  lambda args: cmd_network(),
    'matrix':   lambda args: cmd_matrix(args) if len(args) >= 2 else _usage('matrix <id1> <id2> [id3 …]'),
    'fulltext': lambda args: cmd_fulltext(args[0]) if args else _usage('fulltext <id>  (PMID or DOI)'),
    'help':     lambda args: cmd_help(),
    '--help':   lambda args: cmd_help(),
    '-h':       lambda args: cmd_help(),
}


def _usage(usage: str) -> None:
    print(f'{RED}Usage:{R}  pubmed insights {usage}')
    sys.exit(1)


def main() -> None:
    args = sys.argv[1:]
    sub  = args[0] if args else 'help'
    rest = args[1:]

    fn = _DISPATCH.get(sub)
    if fn is None:
        print(f'{RED}Unknown subcommand:{R} {sub}')
        print(f'Run {B}pubmed insights help{R} for usage.')
        sys.exit(1)
    fn(rest)


if __name__ == '__main__':
    main()

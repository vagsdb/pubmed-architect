# PubMed Architect

A research-article assistant with two interfaces:

- **Web app:** <https://vagsdb.github.io/pubmed-architect/>
- **Desktop app:** Python / Tkinter with zero external dependencies

Both interfaces search NCBI PubMed. The web app adds a browser-local citation
library and structured article builder, while the desktop and CLI tools retain
the deeper workflows described below.

## Web Interface

The static web app lives in `docs/` and is deployed by GitHub Actions. It can:

- open on a Research OS dashboard with a local reproducibility ledger;
- search PubMed by topic, PMID, or DOI;
- filter by article type and publication year;
- display abstracts, MeSH terms, and source links;
- store a private citation library in browser local storage;
- create an Evidence Matrix with transparent metadata/reporting screening grades;
- generate a local article–MeSH knowledge graph (co-indexing, not causality);
- maintain and refresh a versioned Living Review protocol;
- format and export Vancouver, APA, or BibTeX citations; and
- draft and export a structured Markdown manuscript.

### AI Article Reader

The web reader supports direct, user-supplied OpenAI and Anthropic API keys for:

- grounded article Q&A with PMID-level source markers;
- PICO and study-design extraction;
- design-aware critical appraisal and risk-of-bias review;
- endpoint, effect-estimate, confidence-interval, and p-value extraction;
- multi-article comparison, synthesis, contradiction, and gap mapping;
- testable future-research directions; and
- optional independent dual-model reviews with a cross-model consensus.

Article Builder also includes an **AI Citation Writer**. Select up to five saved
PubMed records, choose the rhetorical role and academic tone, and generate three
alternative manuscript-ready sentences. Each alternative is restricted to the
selected abstracts, retains a PMID support trace for verification, and can be
inserted directly at the editor cursor with author-year citations. Optional
draft context is transmitted only when the user explicitly enables it.

API keys are stored in `sessionStorage`, which limits them to the current browser
tab session. They are sent directly to the selected provider and are never added
to the repository, citation library, or exports. Because this is a static GitHub
Pages app, users should use restricted project keys with spending limits and
clear them when finished. A server-side proxy remains the recommended design for
multi-user or production deployment.

The AI settings panel can query each provider's official Models API after a key
is saved, so the model selector can be refreshed without a code release. The
bundled defaults remain available as a fallback. Optional NCBI contact email and
E-utilities API key values are also session-scoped and are appended only to NCBI
requests.

Every completed AI task writes a local audit entry containing the task, provider,
model, date, and source PMIDs. Prompt text, API keys, and patient data are not
written to the audit ledger.

### Evidence Matrix interpretation

The matrix grade is a deterministic screening aid based on publication type and
five metadata/abstract-reporting signals (abstract, design indexing, outcome
language, sample-size reporting, and MeSH indexing). It is not a clinical
evidence grade and does not replace RoB 2, ROBINS-I, QUADAS-2, GRADE, or full-text
critical appraisal.

No patient data or citations are transmitted to this repository. Search terms
are sent directly from the browser to the NCBI E-utilities API.

## Desktop Quick Start

```bash
python app.py
```

Requires **Python 3.10+** (for `dict | None` syntax and walrus operator usage).

## Features

### Search
- Full-text search against the PubMed database (NCBI E-utilities)
- **Look up articles by DOI or PMID** — paste a DOI (e.g. `10.1038/s41586-023-06291-2`) directly into the search bar for instant lookup
- View title, authors, journal, abstract, MeSH terms, and keywords
- Add results to your citation library with one click
- Open articles in your browser (via DOI or PubMed link)

### Citations
- Manage a personal citation library
- Format citations as **APA**, **Vancouver / NLM**, or **BibTeX**
- Copy a single citation or all citations to the clipboard
- Export the full library to `.txt` or `.bib`

### Article Builder
- Structured outline with standard IMRaD sections  
  (Title, Abstract, Introduction, Literature Review, Methods, Results, Discussion, Conclusion, Acknowledgements, References)
- Text editor with live word count
- Insert in-text citation references from your library
- Export the full article as `.txt` or `.md` (references auto-appended)

### Ask
- Type a natural-language question (e.g. *"Does metformin reduce cancer risk?"*)
- The app searches PubMed, fetches up to 200 articles, and synthesises an **evidence-based answer**
- Extracts key conclusion/results sentences from structured abstracts, ranked by relevance
- Shows study-type breakdown, key statistics, thematic clusters, and a consensus signal
- Browse all source articles, view abstracts, add to citations, or open in browser
- Also available from the CLI: `python pubmed_insights.py ask "your question" [-n 60]`
  or `./pubmed.sh insights ask "your question"`

### Discover
- Select any saved citation and find **related articles** via PubMed's similarity algorithm
- **Keyword / MeSH analysis** across all saved citations — see the most frequent terms
- One-click search for the top keyword to uncover new research pathways

## Data Persistence

Your citations and article text are saved automatically to `project_data.json` in the project directory when you close the app (or via *File → Save project*).

## CLI

The CLI script (`pubmed.sh`) and the insights engine (`pubmed_insights.py`) accept **DOIs anywhere a PMID is expected**. DOIs are automatically resolved to PMIDs via NCBI E-search.

```bash
./pubmed.sh cite 10.1038/s41586-023-06291-2 -f apa
./pubmed.sh fetch 10.1016/j.cell.2023.04.007
./pubmed.sh mine add 10.1038/s41586-023-06291-2 -t "review"
python pubmed_insights.py article 10.1038/s41586-023-06291-2
```

Run `./pubmed.sh help` for the full command reference.

### DOI Error Handling

When a DOI cannot be resolved to a PubMed record, each layer reports the failure differently:

- **GUI (`app.py`)** — an unresolvable DOI returns an empty result set ("No results found"), same as a failed keyword search.
- **CLI (`pubmed.sh`)** — prints `Error: Could not resolve DOI <doi> to a PMID.` to stderr and aborts the current command (exit code 1). Batch-style commands like `fetch` and `export` that accept multiple identifiers will stop at the first unresolvable DOI.
- **Python API (`pubmed_api.py`)** — `doi_to_pmids()` silently omits DOIs it cannot resolve; the caller receives a partial mapping. `fetch_details()` and `find_related()` return empty results if none of the identifiers resolve.
- **Insights engine (`pubmed_insights.py`)** — `_resolve_id()` prints an error to stderr and calls `sys.exit(1)` for an unresolvable DOI. Multi-identifier commands (`mesh`, `meshmap`) exit on the first failure.

A DOI is detected by matching the pattern `10.<4-9 digit registrant>/<suffix>`. Strings that do not match (e.g. plain PMIDs, free-text queries) are passed through unchanged.

## Notes

- The app talks directly to the free NCBI E-utilities API. No API key is required, but requests are rate-limited to ~3/second. For heavier use, register for a free API key at <https://www.ncbi.nlm.nih.gov/account/> and pass it to `PubMedClient`.
- Tkinter ships with Python on macOS and most Linux distros. On some minimal Linux installs you may need `sudo apt install python3-tk`.

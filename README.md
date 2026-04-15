# PubMed Architect

A desktop research-article assistant built with Python / Tkinter.  
**Zero external dependencies** — runs on the Python standard library alone.

## Quick Start

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

## Notes

- The app talks directly to the free NCBI E-utilities API. No API key is required, but requests are rate-limited to ~3/second. For heavier use, register for a free API key at <https://www.ncbi.nlm.nih.gov/account/> and pass it to `PubMedClient`.
- Tkinter ships with Python on macOS and most Linux distros. On some minimal Linux installs you may need `sudo apt install python3-tk`.

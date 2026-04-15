#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  pubmed.sh — CLI power‑tool for PubMed research
#
#  Usage:  ./pubmed.sh <command> [args]
#
#  Identifiers:  Every <id> below accepts a PMID (e.g. 35901745)
#                or a DOI (e.g. 10.1038/s41586-023-06291-2).
#
#  Commands:
#    search  <query> [-n max]     Search PubMed, display results
#    fetch   <id> [id …]          Fetch full article metadata
#    related <id> [-n max]        Find related articles
#    cite    <id> [-f format]     Generate a formatted citation
#    abstract <id>                Print just the abstract
#    open    <id>                 Open article in browser
#    batch   <file>               Search each line of file as a query
#    mesh    <id> [id …]          Show MeSH terms for one or more articles
#    trends  <query> [-y years]   Show publication counts by year
#    export  <id …> [-f fmt]     Export multiple citations to stdout
#    help                         Show this help
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

readonly BASE="https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
readonly BLUE=$'\033[1;34m'
readonly CYAN=$'\033[0;36m'
readonly GREEN=$'\033[0;32m'
readonly YELLOW=$'\033[1;33m'
readonly RED=$'\033[0;31m'
readonly BOLD=$'\033[1m'
readonly DIM=$'\033[2m'
readonly RESET=$'\033[0m'

# ── helpers ───────────────────────────────────────────────────────────

_is_doi() {
    # Return 0 (true) if the argument looks like a DOI (10.xxxx/…)
    [[ "$1" =~ ^10\.[0-9]{4,9}/.+ ]]
}

_resolve_id() {
    # If the argument is a DOI, resolve it to a PMID via esearch.
    # Otherwise echo it unchanged (assumed PMID).
    local id="$1"
    if _is_doi "$id"; then
        local encoded
        encoded=$(_urlencode "${id}[AID]")
        local result
        result=$(_api "esearch.fcgi?db=pubmed&term=${encoded}&retmode=json")
        local pmid
        pmid=$(echo "$result" | python3 -c "
import sys, json
ids = json.load(sys.stdin)['esearchresult']['idlist']
print(ids[0] if ids else '')
")
        if [[ -z "$pmid" ]]; then
            echo "${RED}Error:${RESET} Could not resolve DOI ${id} to a PMID." >&2
            return 1
        fi
        echo "$pmid"
    else
        echo "$id"
    fi
}

_resolve_ids() {
    # Resolve a list of identifiers (PMIDs or DOIs) to PMIDs.
    # Outputs one PMID per line.
    for id in "$@"; do
        _resolve_id "$id" || return 1
    done
}

_require() {
    for cmd in "$@"; do
        command -v "$cmd" &>/dev/null || {
            echo "${RED}Error:${RESET} '$cmd' is required but not installed." >&2
            exit 1
        }
    done
}

_urlencode() {
    python3 -c "import urllib.parse; print(urllib.parse.quote_plus('''$1'''))"
}

_api() {
    local endpoint="$1"; shift
    local url="${BASE}/${endpoint}"
    curl -sf --max-time 20 -A "PubMedBash/1.0" "$url" "$@"
}

_xml_text() {
    # Extract text content from an XML tag  ($1 = tag name, stdin = xml)
    python3 -c "
import sys, xml.etree.ElementTree as ET
tree = ET.parse(sys.stdin)
for el in tree.iter('$1'):
    print(''.join(el.itertext()).strip())
"
}

_parse_articles() {
    # Full article parser — reads XML from stdin, outputs JSON array
    python3 -c "
import sys, json, xml.etree.ElementTree as ET

def txt(el):
    return ''.join(el.itertext()).strip() if el is not None else ''

root = ET.parse(sys.stdin).getroot()
articles = []
for pa in root.findall('.//PubmedArticle'):
    mc = pa.find('MedlineCitation')
    if mc is None: continue
    art = mc.find('Article')
    if art is None: continue

    pmid = txt(mc.find('PMID'))
    title = txt(art.find('ArticleTitle')) or 'No title'

    ab = art.find('Abstract')
    abstract = ''
    if ab is not None:
        parts = []
        for t in ab.findall('AbstractText'):
            label = t.get('Label', '')
            tx = txt(t)
            parts.append(f'{label}: {tx}' if label else tx)
        abstract = '\n'.join(parts)

    authors = []
    al = art.find('AuthorList')
    if al is not None:
        for au in al.findall('Author'):
            last = (au.findtext('LastName') or '')
            fore = (au.findtext('ForeName') or '')
            if last:
                authors.append(f'{last} {fore[0]}' if fore else last)

    j = art.find('Journal')
    journal = year = volume = issue = ''
    if j is not None:
        journal = j.findtext('ISOAbbreviation', '') or j.findtext('Title', '')
        ji = j.find('JournalIssue')
        if ji is not None:
            volume = ji.findtext('Volume', '')
            issue = ji.findtext('Issue', '')
            pd = ji.find('PubDate')
            if pd is not None:
                year = pd.findtext('Year', '')
                if not year:
                    year = (pd.findtext('MedlineDate', '') or '')[:4]
    pages = art.findtext('Pagination/MedlinePgn', '')

    doi = ''
    for aid in pa.findall('.//ArticleId'):
        if aid.get('IdType') == 'doi':
            doi = aid.text or ''
            break

    mesh = [txt(mh.find('DescriptorName'))
            for mh in mc.findall('.//MeshHeading')
            if mh.find('DescriptorName') is not None]

    kw = [k.text for k in mc.findall('.//Keyword') if k.text]

    articles.append({
        'pmid': pmid, 'title': title, 'abstract': abstract,
        'authors': authors, 'journal': journal, 'year': year,
        'volume': volume, 'issue': issue, 'pages': pages,
        'doi': doi, 'mesh': mesh, 'keywords': kw
    })

json.dump(articles, sys.stdout, indent=2)
"
}

_format_citation() {
    # $1 = format (apa|vancouver|bibtex), stdin = JSON article object
    python3 -c "
import sys, json
fmt = '$1'
a = json.load(sys.stdin)

auths = ', '.join(a['authors'][:6])
if len(a['authors']) > 6: auths += ', et al'

if fmt == 'apa':
    ref = a['doi'] and f\"https://doi.org/{a['doi']}\" or f\"PMID: {a['pmid']}\"
    print(f\"{auths} ({a['year']}). {a['title']} {a['journal']}, {a['volume']}{('(' + a['issue'] + ')') if a['issue'] else ''}{(', ' + a['pages']) if a['pages'] else ''}. {ref}\")
elif fmt == 'bibtex':
    key = (a['authors'][0].split()[0] if a['authors'] else 'Unknown') + a['year']
    print(f\"@article{{{key},\")
    print(f\"  author  = {{{' and '.join(a['authors'])}}},\")
    print(f\"  title   = {{{a['title']}}},\")
    print(f\"  journal = {{{a['journal']}}},\")
    print(f\"  year    = {{{a['year']}}},\")
    print(f\"  volume  = {{{a['volume']}}},\")
    print(f\"  number  = {{{a['issue']}}},\")
    print(f\"  pages   = {{{a['pages']}}},\")
    print(f\"  doi     = {{{a['doi']}}},\")
    print(f\"  pmid    = {{{a['pmid']}}}\")
    print('}')
else:  # vancouver
    ref = a['doi'] and f\"doi: {a['doi']}\" or f\"PMID: {a['pmid']}\"
    print(f\"{auths}. {a['title']} {a['journal']}. {a['year']}{('; ' + a['volume']) if a['volume'] else ''}{('(' + a['issue'] + ')') if a['issue'] else ''}{(':' + a['pages']) if a['pages'] else ''}. {ref}\")
"
}

# ── commands ──────────────────────────────────────────────────────────

cmd_search() {
    local query="" max=15
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n|--max) max="$2"; shift 2 ;;
            *) query+="$1 "; shift ;;
        esac
    done
    query="${query% }"
    [[ -z "$query" ]] && { echo "${RED}Usage:${RESET} pubmed.sh search <query> [-n max]"; return 1; }

    local encoded
    encoded=$(_urlencode "$query")

    echo "${DIM}Searching PubMed for:${RESET} ${BOLD}${query}${RESET}"
    echo ""

    # Step 1: get PMIDs
    local id_json
    id_json=$(_api "esearch.fcgi?db=pubmed&term=${encoded}&retmax=${max}&retmode=json&sort=relevance")

    local count
    count=$(echo "$id_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['esearchresult']['count'])")
    local -a pmids
    mapfile -t pmids < <(echo "$id_json" | python3 -c "
import sys,json
ids = json.load(sys.stdin)['esearchresult']['idlist']
for i in ids: print(i)
")

    echo "${GREEN}${count} total results${RESET} (showing ${#pmids[@]})"
    echo ""

    [[ ${#pmids[@]} -eq 0 ]] && return 0

    # Step 2: fetch details
    local ids_csv
    ids_csv=$(IFS=,; echo "${pmids[*]}")

    local xml
    xml=$(_api "efetch.fcgi?db=pubmed&id=${ids_csv}&retmode=xml")

    # Step 3: display
    echo "$xml" | python3 -c "
import sys, xml.etree.ElementTree as ET

def txt(el):
    return ''.join(el.itertext()).strip() if el is not None else ''

root = ET.parse(sys.stdin).getroot()
for i, pa in enumerate(root.findall('.//PubmedArticle'), 1):
    mc = pa.find('MedlineCitation')
    if mc is None: continue
    art = mc.find('Article')
    if art is None: continue
    pmid = txt(mc.find('PMID'))
    title = txt(art.find('ArticleTitle'))
    authors = []
    al = art.find('AuthorList')
    if al is not None:
        for au in al.findall('Author'):
            last = au.findtext('LastName', '')
            if last: authors.append(last)
    auth_str = ', '.join(authors[:3])
    if len(authors) > 3: auth_str += ' et al.'
    j = art.find('Journal')
    journal = j.findtext('ISOAbbreviation', '') if j is not None else ''
    ji = j.find('JournalIssue') if j is not None else None
    year = ''
    if ji is not None:
        pd = ji.find('PubDate')
        if pd is not None: year = pd.findtext('Year', '')
    print(f'  \033[1;34m[{i}]\033[0m  PMID {pmid}')
    print(f'      \033[1m{title}\033[0m')
    print(f'      \033[2m{auth_str}  •  {journal} ({year})\033[0m')
    print()
"
}

cmd_fetch() {
    [[ $# -eq 0 ]] && { echo "${RED}Usage:${RESET} pubmed.sh fetch <id> [id …]  (PMID or DOI)"; return 1; }

    local -a pmids
    mapfile -t pmids < <(_resolve_ids "$@")
    local ids_csv
    ids_csv=$(IFS=,; echo "${pmids[*]}")

    _api "efetch.fcgi?db=pubmed&id=${ids_csv}&retmode=xml" | _parse_articles
}

cmd_related() {
    local raw_id="" max=10
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n|--max) max="$2"; shift 2 ;;
            *) raw_id="$1"; shift ;;
        esac
    done
    [[ -z "$raw_id" ]] && { echo "${RED}Usage:${RESET} pubmed.sh related <id> [-n max]  (PMID or DOI)"; return 1; }

    local pmid
    pmid=$(_resolve_id "$raw_id") || return 1
    echo "${DIM}Finding articles related to PMID${RESET} ${BOLD}${pmid}${RESET} …"
    echo ""

    local link_xml
    link_xml=$(_api "elink.fcgi?dbfrom=pubmed&db=pubmed&id=${pmid}&cmd=neighbor_score&retmode=xml")

    local -a related_ids
    mapfile -t related_ids < <(echo "$link_xml" | python3 -c "
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.stdin).getroot()
ids = []
for lsdb in root.iter('LinkSetDb'):
    name = lsdb.findtext('LinkName', '')
    if name == 'pubmed_pubmed':
        for link in lsdb.findall('Link'):
            lid = link.findtext('Id', '')
            if lid and lid != '${pmid}':
                ids.append(lid)
            if len(ids) >= ${max}: break
for i in ids: print(i)
")

    [[ ${#related_ids[@]} -eq 0 ]] && { echo "No related articles found."; return 0; }

    local ids_csv
    ids_csv=$(IFS=,; echo "${related_ids[*]}")

    _api "efetch.fcgi?db=pubmed&id=${ids_csv}&retmode=xml" | python3 -c "
import sys, xml.etree.ElementTree as ET

def txt(el):
    return ''.join(el.itertext()).strip() if el is not None else ''

root = ET.parse(sys.stdin).getroot()
for i, pa in enumerate(root.findall('.//PubmedArticle'), 1):
    mc = pa.find('MedlineCitation')
    if mc is None: continue
    art = mc.find('Article')
    if art is None: continue
    pmid = txt(mc.find('PMID'))
    title = txt(art.find('ArticleTitle'))
    authors = []
    al = art.find('AuthorList')
    if al is not None:
        for au in al.findall('Author'):
            last = au.findtext('LastName', '')
            if last: authors.append(last)
    auth_str = ', '.join(authors[:3])
    if len(authors) > 3: auth_str += ' et al.'
    j = art.find('Journal')
    journal = j.findtext('ISOAbbreviation', '') if j is not None else ''
    ji = j.find('JournalIssue') if j is not None else None
    year = ''
    if ji is not None:
        pd = ji.find('PubDate')
        if pd is not None: year = pd.findtext('Year', '')
    print(f'  \033[0;36m[{i}]\033[0m  PMID {pmid}')
    print(f'      \033[1m{title}\033[0m')
    print(f'      \033[2m{auth_str}  •  {journal} ({year})\033[0m')
    print()
"
}

cmd_cite() {
    local raw_id="" fmt="vancouver"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f|--format) fmt="$2"; shift 2 ;;
            *) raw_id="$1"; shift ;;
        esac
    done
    [[ -z "$raw_id" ]] && { echo "${RED}Usage:${RESET} pubmed.sh cite <id> [-f apa|vancouver|bibtex]  (PMID or DOI)"; return 1; }

    local pmid
    pmid=$(_resolve_id "$raw_id") || return 1
    _api "efetch.fcgi?db=pubmed&id=${pmid}&retmode=xml" \
        | _parse_articles \
        | python3 -c "import sys,json; arts=json.load(sys.stdin); arts and json.dump(arts[0],sys.stdout)" \
        | _format_citation "$fmt"
}

cmd_abstract() {
    [[ -z "${1:-}" ]] && { echo "${RED}Usage:${RESET} pubmed.sh abstract <id>  (PMID or DOI)"; return 1; }
    local pmid
    pmid=$(_resolve_id "$1") || return 1

    _api "efetch.fcgi?db=pubmed&id=${pmid}&retmode=xml" | python3 -c "
import sys, xml.etree.ElementTree as ET

def txt(el):
    return ''.join(el.itertext()).strip() if el is not None else ''

root = ET.parse(sys.stdin).getroot()
pa = root.find('.//PubmedArticle')
if pa is None:
    print('Article not found.'); sys.exit(1)
mc = pa.find('MedlineCitation')
art = mc.find('Article')
title = txt(art.find('ArticleTitle'))
print(f'\033[1m{title}\033[0m')
print()
ab = art.find('Abstract')
if ab is None:
    print('(no abstract available)')
else:
    for t in ab.findall('AbstractText'):
        label = t.get('Label', '')
        tx = txt(t)
        if label:
            print(f'\033[1;33m{label}\033[0m')
        print(tx)
        print()
"
}

cmd_open() {
    [[ -z "${1:-}" ]] && { echo "${RED}Usage:${RESET} pubmed.sh open <id>  (PMID or DOI)"; return 1; }
    local id="$1"
    local url
    if _is_doi "$id"; then
        url="https://doi.org/${id}"
    else
        url="https://pubmed.ncbi.nlm.nih.gov/${id}/"
    fi
    echo "Opening ${url}"
    open "$url" 2>/dev/null || xdg-open "$url" 2>/dev/null || echo "Visit: ${url}"
}

cmd_batch() {
    [[ -z "${1:-}" || ! -f "$1" ]] && { echo "${RED}Usage:${RESET} pubmed.sh batch <file>"; return 1; }
    local file="$1"
    local i=0

    while IFS= read -r query || [[ -n "$query" ]]; do
        [[ -z "$query" || "$query" == \#* ]] && continue
        ((i++))
        echo "${YELLOW}━━━ Query ${i}: ${query} ━━━${RESET}"
        cmd_search "$query" -n 5
        echo ""
        sleep 0.4  # respect rate limits
    done < "$file"

    echo "${GREEN}Done. Processed ${i} queries.${RESET}"
}

cmd_mesh() {
    [[ $# -eq 0 ]] && { echo "${RED}Usage:${RESET} pubmed.sh mesh <pmid> [pmid …]"; return 1; }
    python3 "${SCRIPT_DIR}/pubmed_insights.py" mesh "$@"
}

cmd_trends() {
    local query="" years=10
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -y|--years) years="$2"; shift 2 ;;
            *) query+="$1 "; shift ;;
        esac
    done
    query="${query% }"
    [[ -z "$query" ]] && { echo "${RED}Usage:${RESET} pubmed.sh trends <query> [-y years]"; return 1; }

    echo "${DIM}Publication trends for:${RESET} ${BOLD}${query}${RESET}"
    echo ""

    local current_year
    current_year=$(date +%Y)
    local start_year=$((current_year - years))

    local max_count=0
    declare -a counts_arr=()
    declare -a years_arr=()

    for ((y=start_year; y<=current_year; y++)); do
        local encoded
        encoded=$(_urlencode "${query} AND ${y}[pdat]")
        local result
        result=$(_api "esearch.fcgi?db=pubmed&term=${encoded}&rettype=count&retmode=json")
        local count
        count=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['esearchresult']['count'])")
        counts_arr+=("$count")
        years_arr+=("$y")
        (( count > max_count )) && max_count=$count
        sleep 0.35
    done

    # Draw bar chart
    local bar_width=40
    for i in "${!years_arr[@]}"; do
        local y="${years_arr[$i]}"
        local c="${counts_arr[$i]}"
        local bar_len=0
        if (( max_count > 0 )); then
            bar_len=$(( c * bar_width / max_count ))
        fi
        local bar=""
        for ((b=0; b<bar_len; b++)); do bar+="█"; done
        printf "  ${CYAN}%4s${RESET}  ${GREEN}%-${bar_width}s${RESET}  %s\n" "$y" "$bar" "$c"
    done
    echo ""
    echo "${DIM}Peak: ${max_count} publications${RESET}"
}

cmd_export() {
    local fmt="vancouver"
    local -a raw_ids=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f|--format) fmt="$2"; shift 2 ;;
            *) raw_ids+=("$1"); shift ;;
        esac
    done
    [[ ${#raw_ids[@]} -eq 0 ]] && { echo "${RED}Usage:${RESET} pubmed.sh export <id …> [-f apa|vancouver|bibtex]  (PMID or DOI)" >&2; return 1; }

    local -a pmids
    mapfile -t pmids < <(_resolve_ids "${raw_ids[@]}")
    local ids_csv
    ids_csv=$(IFS=,; echo "${pmids[*]}")

    _api "efetch.fcgi?db=pubmed&id=${ids_csv}&retmode=xml" \
        | _parse_articles \
        | python3 -c "
import sys, json
fmt = '${fmt}'
articles = json.load(sys.stdin)
for a in articles:
    json.dump(a, sys.stdout)
    sys.stdout.write('\n')
" | while IFS= read -r line; do
        echo "$line" | _format_citation "$fmt"
        echo ""
    done
}

# ══════════════════════════════════════════════════════════════════════
#  Mine — flag articles for deep reading / data extraction
# ══════════════════════════════════════════════════════════════════════

_script="$0"
while [[ -L "$_script" ]]; do _script="$(readlink "$_script")"; done
readonly SCRIPT_DIR="$(dirname "$_script")"
readonly MINE_FILE="${MINE_FILE:-${SCRIPT_DIR}/mined.json}"
export MINE_FILE

_mine_load() {
    if [[ -f "$MINE_FILE" ]]; then
        cat "$MINE_FILE"
    else
        echo '[]'
    fi
}

_mine_save() {
    # stdin = full JSON array
    python3 -c "import sys,json; json.dump(json.load(sys.stdin), open('${MINE_FILE}','w'), indent=2)"
}

_mine_has() {
    # $1 = pmid — exit 0 if already mined
    _mine_load | python3 -c "
import sys, json
entries = json.load(sys.stdin)
sys.exit(0 if any(e['pmid'] == '$1' for e in entries) else 1)
"
}

cmd_mine() {
    local sub="${1:-help}"
    shift || true

    case "$sub" in

    # ── mine add <id> [id …] [-t tag1,tag2] [-m "note"] ─────────
    add)
        local -a raw_ids=()
        local tags="" note=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                -t|--tags) tags="$2"; shift 2 ;;
                -m|--note) note="$2"; shift 2 ;;
                *) raw_ids+=("$1"); shift ;;
            esac
        done
        [[ ${#raw_ids[@]} -eq 0 ]] && { echo "${RED}Usage:${RESET} mine add <id> [id …] [-t tags] [-m note]  (PMID or DOI)"; return 1; }

        for raw_id in "${raw_ids[@]}"; do
            local pmid
            pmid=$(_resolve_id "$raw_id") || continue
            if _mine_has "$pmid"; then
                echo "${YELLOW}PMID ${pmid} already in list — skipping.${RESET}"
                continue
            fi

            echo "${DIM}Fetching metadata for PMID ${pmid}…${RESET}"
            local xml
            xml=$(_api "efetch.fcgi?db=pubmed&id=${pmid}&retmode=xml")

            # Build the mined entry and append
            _mine_load | python3 -c "
import sys, json, xml.etree.ElementTree as ET, datetime

def txt(el):
    return ''.join(el.itertext()).strip() if el is not None else ''

xml_str = '''${xml}'''
root = ET.fromstring(xml_str)
pa = root.find('.//PubmedArticle')
mc = pa.find('MedlineCitation') if pa is not None else None
art = mc.find('Article') if mc is not None else None

title = txt(art.find('ArticleTitle')) if art is not None else 'Unknown'
authors = []
if art is not None:
    al = art.find('AuthorList')
    if al is not None:
        for au in al.findall('Author'):
            last = au.findtext('LastName', '')
            if last: authors.append(last)
auth_str = ', '.join(authors[:3])
if len(authors) > 3: auth_str += ' et al.'

j = art.find('Journal') if art is not None else None
journal = j.findtext('ISOAbbreviation', '') if j is not None else ''
ji = j.find('JournalIssue') if j is not None else None
year = ''
if ji is not None:
    pd = ji.find('PubDate')
    if pd is not None: year = pd.findtext('Year', '')

entries = json.load(sys.stdin)
entries.append({
    'pmid': '${pmid}',
    'title': title,
    'authors': auth_str,
    'journal': journal,
    'year': year,
    'tags': [t.strip() for t in '${tags}'.split(',') if t.strip()],
    'notes': ['${note}'] if '${note}' else [],
    'added': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'status': 'queued'
})
json.dump(entries, sys.stdout)
" | _mine_save

            echo "${GREEN}✓ Added PMID ${pmid}${RESET}"
            [[ -n "$tags" ]] && echo "  Tags: ${CYAN}${tags}${RESET}"
            [[ -n "$note" ]] && echo "  Note: ${DIM}${note}${RESET}"
        done
        ;;

    # ── mine list [-t tag] [-s status] ────────────────────────────
    list|ls)
        local filter_tag="" filter_status=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                -t|--tag) filter_tag="$2"; shift 2 ;;
                -s|--status) filter_status="$2"; shift 2 ;;
                *) shift ;;
            esac
        done

        _mine_load | python3 -c "
import sys, json

entries = json.load(sys.stdin)
tag_f = '${filter_tag}'
stat_f = '${filter_status}'

if tag_f:
    entries = [e for e in entries if tag_f in e.get('tags', [])]
if stat_f:
    entries = [e for e in entries if e.get('status', '') == stat_f]

if not entries:
    print('  (no articles in mining list)');
    sys.exit(0)

status_colors = {'queued': '\033[1;33m', 'reading': '\033[1;34m', 'done': '\033[0;32m', 'skip': '\033[2m'}

print(f'  {len(entries)} article(s) flagged for mining:\n')
for i, e in enumerate(entries, 1):
    sc = status_colors.get(e.get('status',''), '')
    reset = '\033[0m'
    tags = ' '.join(f'\033[0;36m#{t}\033[0m' for t in e.get('tags', []))
    notes_count = len(e.get('notes', []))
    notes_badge = f'  \033[2m[{notes_count} note{\"s\" if notes_count != 1 else \"\"}]\033[0m' if notes_count else ''
    print(f'  {sc}[{e.get(\"status\",\"?\"):>7}]{reset}  \033[1m{e[\"pmid\"]}\033[0m  {e[\"title\"][:75]}')
    print(f'            \033[2m{e.get(\"authors\",\"\")}  •  {e.get(\"journal\",\"\")} ({e.get(\"year\",\"\")})\033[0m  {tags}{notes_badge}')
    print()
"
        ;;

    # ── mine note <id> <text> ───────────────────────────────────
    note)
        local raw_id="${1:-}"; shift || true
        local text="$*"
        [[ -z "$raw_id" || -z "$text" ]] && { echo "${RED}Usage:${RESET} mine note <id> <text>  (PMID or DOI)"; return 1; }
        local pmid
        pmid=$(_resolve_id "$raw_id") || return 1

        _mine_load | python3 -c "
import sys, json, datetime
entries = json.load(sys.stdin)
found = False
for e in entries:
    if e['pmid'] == '${pmid}':
        e.setdefault('notes', []).append(datetime.datetime.now().strftime('%H:%M') + '  ' + '''${text}''')
        found = True
        break
if not found:
    print('PMID ${pmid} not in mining list. Add it first.', file=sys.stderr)
    sys.exit(1)
json.dump(entries, sys.stdout)
" | _mine_save

        echo "${GREEN}✓ Note added to PMID ${pmid}${RESET}"
        ;;

    # ── mine tag <id> <tag1,tag2> ───────────────────────────────
    tag)
        local raw_id="${1:-}"; shift || true
        local new_tags="$*"
        [[ -z "$raw_id" || -z "$new_tags" ]] && { echo "${RED}Usage:${RESET} mine tag <id> <tag1,tag2,...>  (PMID or DOI)"; return 1; }
        local pmid
        pmid=$(_resolve_id "$raw_id") || return 1

        _mine_load | python3 -c "
import sys, json
entries = json.load(sys.stdin)
for e in entries:
    if e['pmid'] == '${pmid}':
        existing = set(e.get('tags', []))
        for t in '${new_tags}'.replace(' ', ',').split(','):
            t = t.strip()
            if t: existing.add(t)
        e['tags'] = sorted(existing)
        break
json.dump(entries, sys.stdout)
" | _mine_save

        echo "${GREEN}✓ Tags updated for PMID ${pmid}${RESET}"
        ;;

    # ── mine status <id> <queued|reading|done|skip> ─────────────
    status)
        local raw_id="${1:-}" new_status="${2:-}"
        [[ -z "$raw_id" || -z "$new_status" ]] && { echo "${RED}Usage:${RESET} mine status <id> <queued|reading|done|skip>  (PMID or DOI)"; return 1; }
        local pmid
        pmid=$(_resolve_id "$raw_id") || return 1

        _mine_load | python3 -c "
import sys, json
entries = json.load(sys.stdin)
for e in entries:
    if e['pmid'] == '${pmid}':
        e['status'] = '${new_status}'
        break
json.dump(entries, sys.stdout)
" | _mine_save

        echo "${GREEN}✓ PMID ${pmid} → ${new_status}${RESET}"
        ;;

    # ── mine show <id> — full detail card ───────────────────────
    show)
        [[ -z "${1:-}" ]] && { echo "${RED}Usage:${RESET} mine show <id>  (PMID or DOI)"; return 1; }
        local pmid
        pmid=$(_resolve_id "$1") || return 1

        _mine_load | python3 -c "
import sys, json
entries = json.load(sys.stdin)
e = next((e for e in entries if e['pmid'] == '${pmid}'), None)
if not e:
    print('PMID ${pmid} not in mining list.'); sys.exit(1)

print(f'\033[1m{e[\"title\"]}\033[0m')
print(f'{e.get(\"authors\", \"\")}  •  {e.get(\"journal\", \"\")} ({e.get(\"year\", \"\")})')
print(f'PMID: {e[\"pmid\"]}    Status: \033[1;33m{e.get(\"status\", \"?\")}\033[0m    Added: {e.get(\"added\", \"?\")}')
tags = e.get('tags', [])
if tags:
    print(f'Tags: {\" \".join(\"\033[0;36m#\" + t + \"\033[0m\" for t in tags)}')
print()
notes = e.get('notes', [])
if notes:
    print(f'\033[1mNotes ({len(notes)}):\033[0m')
    for n in notes:
        print(f'  \033[2m•\033[0m {n}')
else:
    print('\033[2m(no notes yet)\033[0m')
"
        # Also print abstract from PubMed
        echo ""
        echo "${BOLD}── Abstract ──${RESET}"
        cmd_abstract "$pmid" 2>/dev/null | tail -n +3
        ;;

    # ── mine remove <id> ────────────────────────────────────────
    rm|remove)
        [[ -z "${1:-}" ]] && { echo "${RED}Usage:${RESET} mine remove <id>  (PMID or DOI)"; return 1; }
        local pmid
        pmid=$(_resolve_id "$1") || return 1

        _mine_load | python3 -c "
import sys, json
entries = json.load(sys.stdin)
before = len(entries)
entries = [e for e in entries if e['pmid'] != '$1']
if len(entries) == before:
    print('PMID $1 was not in the list.', file=sys.stderr)
json.dump(entries, sys.stdout)
" | _mine_save

        echo "${GREEN}✓ Removed PMID $1${RESET}"
        ;;

    # ── mine export [-f fmt] — export only mined articles ─────────
    export)
        local fmt="vancouver"
        [[ "${1:-}" == "-f" ]] && { fmt="$2"; shift 2 || true; }

        local -a pmids
        mapfile -t pmids < <(_mine_load | python3 -c "
import sys, json
for e in json.load(sys.stdin):
    print(e['pmid'])
")
        [[ ${#pmids[@]} -eq 0 ]] && { echo "Mining list is empty."; return 0; }
        cmd_export "${pmids[@]}" -f "$fmt"
        ;;

    # ── mine tags — show all tags in use ──────────────────────────
    tags)
        _mine_load | python3 -c "
import sys, json
from collections import Counter
entries = json.load(sys.stdin)
c = Counter()
for e in entries:
    for t in e.get('tags', []): c[t] += 1
if not c:
    print('  No tags yet.'); sys.exit(0)
print('  Tags in use:')
for tag, count in c.most_common():
    print(f'    \033[0;36m#{tag}\033[0m  ({count})')
"
        ;;

    # ── mine clear ────────────────────────────────────────────────
    reset|clear)
        echo -n "${YELLOW}Remove all articles from mining list? [y/N] ${RESET}"
        read -r ans
        [[ "$ans" == [yY]* ]] || { echo "Cancelled."; return 0; }
        echo '[]' > "$MINE_FILE"
        echo "${GREEN}✓ Mining list cleared.${RESET}"
        ;;

    help|*)
        cat <<'MEOF'

  mine — flag articles for deep reading / data extraction

  All <id> arguments accept a PMID or DOI.

  SUBCOMMANDS
    mine add    <id> [id …] [-t tags] [-m note]   Flag one or more articles
    mine list   [-t tag] [-s status]         Show flagged articles
    mine show   <id>                         Full card + abstract + notes
    mine note   <id> <text>                  Append a note
    mine tag    <id> <tag1,tag2>             Add tags
    mine status <id> <status>                Set status (queued|reading|done|skip)
    mine remove <id>                         Un-flag an article
    mine export [-f fmt]                     Export mined articles as citations
    mine tags                                List all tags in use
    mine reset                               Wipe the mining list (alias: clear)

  EXAMPLES
    ./pubmed.sh mine add 35901745 -t "methods,CRISPR" -m "Key paper on delivery"
    ./pubmed.sh mine add 10.1038/s41586-023-06291-2 -t "review"
    ./pubmed.sh mine list -t CRISPR
    ./pubmed.sh mine note 35901745 "Table 2 has the IC50 values I need"
    ./pubmed.sh mine status 35901745 reading
    ./pubmed.sh mine show 35901745
    ./pubmed.sh mine list -s done
    ./pubmed.sh mine export -f bibtex > mined.bib

MEOF
        ;;
    esac
}

# ══════════════════════════════════════════════════════════════════════
#  Insights — delegates to pubmed_insights.py
# ══════════════════════════════════════════════════════════════════════

cmd_insights() {
    python3 "${SCRIPT_DIR}/pubmed_insights.py" "$@"
}

# kept for reference — original bash stubs below are no longer executed
_insights_legacy() {
    local sub="${1:-help}"
    shift || true

    case "$sub" in

    # ── insights article <pmid> ── deep single-article breakdown ──
    article)
        [[ -z "${1:-}" ]] && { echo "${RED}Usage:${RESET} insights article <pmid>"; return 1; }
        local pmid="$1"

        echo "${DIM}Analysing PMID ${pmid}…${RESET}"
        echo ""

        _api "efetch.fcgi?db=pubmed&id=${pmid}&retmode=xml" | python3 -c "
import sys, re, xml.etree.ElementTree as ET

def txt(el):
    return ''.join(el.itertext()).strip() if el is not None else ''

B = '\033[1m'; D = '\033[2m'; C = '\033[0;36m'; Y = '\033[1;33m'
G = '\033[0;32m'; R = '\033[0m'

root = ET.parse(sys.stdin).getroot()
pa = root.find('.//PubmedArticle')
if pa is None:
    print('Article not found.'); sys.exit(1)
mc = pa.find('MedlineCitation')
art = mc.find('Article')

title = txt(art.find('ArticleTitle'))
print(f'{B}{title}{R}')
print()

# ── Study type / publication type ──
ptypes = [txt(pt) for pt in art.findall('.//PublicationType')]
if ptypes:
    s = ', '.join(ptypes)
    print(f'{Y}Study Type:{R}  {s}')

# ── Authors + affiliations ──
authors = []
affs = set()
al = art.find('AuthorList')
if al is not None:
    for au in al.findall('Author'):
        last = au.findtext('LastName', '')
        fore = au.findtext('ForeName', '')
        if last: authors.append(f'{last} {fore}')
        for af in au.findall('.//Affiliation'):
            a = txt(af)
            if a: affs.add(a)
print(f'{Y}Authors:{R}     {len(authors)} — {authors[0] if authors else \"?\"} (first), {authors[-1] if authors else \"?\"} (last)')
if affs:
    for a in sorted(affs)[:3]:
        print(f'              {D}{a[:100]}{R}')
    if len(affs) > 3:
        print(f'              {D}… and {len(affs)-3} more affiliations{R}')
print()

# ── Structured abstract sections ──
ab = art.find('Abstract')
if ab is not None:
    sections = []
    for t in ab.findall('AbstractText'):
        label = t.get('Label', '')
        body = txt(t)
        sections.append((label, body))

    print(f'{B}── Abstract Breakdown ──{R}')
    for label, body in sections:
        if label:
            print(f'  {C}{label}{R}')
        # Word count for section
        wc = len(body.split())
        print(f'  {D}({wc} words){R}')
        # Extract key numbers / statistics
        numbers = re.findall(r'(?:p\s*[<=]\s*0\.\d+|\d+\.?\d*\s*%|HR\s*[=:]?\s*\d+\.\d+|OR\s*[=:]?\s*\d+\.\d+|RR\s*[=:]?\s*\d+\.\d+|CI\s*[=:]?\s*\d+\.\d+[\s–-]+\d+\.\d+|n\s*=\s*\d[\d,]*|N\s*=\s*\d[\d,]*|\d[\d,]+\s*patients|\d[\d,]+\s*participants|\d[\d,]+\s*subjects|\d[\d,]+\s*samples)', body, re.IGNORECASE)
        if numbers:
            s = ' | '.join(numbers[:8])
            print(f'  {G}Key figures:{R} {s}')
        print()
else:
    print(f'{D}(no abstract available){R}')
    print()

# ── MeSH terms ──
mesh_list = mc.find('MeshHeadingList')
major = []
minor = []
if mesh_list is not None:
    for mh in mesh_list.findall('MeshHeading'):
        desc = mh.find('DescriptorName')
        name = txt(desc)
        if desc is not None and desc.get('MajorTopicYN', 'N') == 'Y':
            major.append(name)
        else:
            minor.append(name)
if major:
    s = ', '.join(major)
    print(f'{Y}Major Topics:{R}  {s}')
if minor:
    s = ', '.join(minor[:10])
    print(f'{Y}Other MeSH:{R}    {s}')

# ── Keywords ──
kws = [kw.text for kw in mc.findall('.//Keyword') if kw.text]
if kws:
    s = ', '.join(kws)
    print(f'{Y}Keywords:{R}     {s}')
print()

# ── Grants / funding ──
grants = []
for g in art.findall('.//Grant'):
    agency = g.findtext('Agency', '')
    gid = g.findtext('GrantID', '')
    if agency:
        grants.append(f'{agency} ({gid})' if gid else agency)
if grants:
    unique_grants = sorted(set(grants))
    s = ', '.join(unique_grants[:5])
    print(f'{Y}Funding:{R}      {s}')

# ── References count ──
ref_list = pa.find('.//ReferenceList')
if ref_list is not None:
    refs = ref_list.findall('Reference')
    print(f'{Y}References:{R}   {len(refs)} cited works')

# ── DOI / link ──
for aid in pa.findall('.//ArticleId'):
    if aid.get('IdType') == 'doi':
        print(f'{Y}DOI:{R}          https://doi.org/{aid.text}')
        break
"
        ;;

    # ── insights mined ── cross-analysis of all mined articles ────
    mined)
        local -a pmids
        mapfile -t pmids < <(_mine_load | python3 -c "
import sys, json
for e in json.load(sys.stdin):
    print(e['pmid'])
")
        [[ ${#pmids[@]} -eq 0 ]] && { echo "Mining list is empty. Add articles with ${BOLD}mine add${RESET}."; return 0; }

        echo "${DIM}Fetching metadata for ${#pmids[@]} mined articles…${RESET}"
        local ids_csv
        ids_csv=$(IFS=,; echo "${pmids[*]}")

        _api "efetch.fcgi?db=pubmed&id=${ids_csv}&retmode=xml" | python3 -c "
import sys, xml.etree.ElementTree as ET
from collections import Counter

def txt(el):
    return ''.join(el.itertext()).strip() if el is not None else ''

B = '\033[1m'; D = '\033[2m'; C = '\033[0;36m'; Y = '\033[1;33m'
G = '\033[0;32m'; R = '\033[0m'

root = ET.parse(sys.stdin).getroot()
articles = root.findall('.//PubmedArticle')
n = len(articles)

print(f'{B}══ Insights across {n} mined articles ══{R}')
print()

mesh_counter = Counter()
kw_counter = Counter()
author_counter = Counter()
journal_counter = Counter()
year_counter = Counter()
ptypes_counter = Counter()
all_major = Counter()

for pa in articles:
    mc = pa.find('MedlineCitation')
    art = mc.find('Article') if mc is not None else None
    if art is None: continue

    # Authors
    al = art.find('AuthorList')
    if al is not None:
        for au in al.findall('Author'):
            last = au.findtext('LastName', '')
            fore = au.findtext('ForeName', '')
            if last: author_counter[f'{last} {fore[0]}' if fore else last] += 1

    # Journal
    j = art.find('Journal')
    if j is not None:
        jname = j.findtext('ISOAbbreviation', '') or j.findtext('Title', '')
        if jname: journal_counter[jname] += 1
        ji = j.find('JournalIssue')
        if ji is not None:
            pd = ji.find('PubDate')
            if pd is not None:
                year = pd.findtext('Year', '')
                if year: year_counter[year] += 1

    # MeSH
    ml = mc.find('MeshHeadingList') if mc is not None else None
    if ml is not None:
        for mh in ml.findall('MeshHeading'):
            desc = mh.find('DescriptorName')
            name = txt(desc)
            if name: mesh_counter[name] += 1
            if desc is not None and desc.get('MajorTopicYN', 'N') == 'Y':
                all_major[name] += 1

    # Keywords
    for kw in (mc.findall('.//Keyword') if mc is not None else []):
        if kw.text: kw_counter[kw.text.lower()] += 1

    # Pub types
    for pt in art.findall('.//PublicationType'):
        t = txt(pt)
        if t: ptypes_counter[t] += 1

# ── Year spread ──
if year_counter:
    print(f'{Y}Year Distribution:{R}')
    for yr in sorted(year_counter):
        bar = '█' * year_counter[yr]
        print(f'  {C}{yr}{R}  {G}{bar}{R}  {year_counter[yr]}')
    print()

# ── Journal spread ──
if journal_counter:
    print(f'{Y}Journals:{R}')
    for j, c in journal_counter.most_common(8):
        print(f'  {c:>2}x  {j}')
    if len(journal_counter) > 8:
        print(f'  {D}… and {len(journal_counter)-8} more journals{R}')
    print()

# ── Study types ──
if ptypes_counter:
    print(f'{Y}Study Types:{R}')
    for pt, c in ptypes_counter.most_common(8):
        print(f'  {c:>2}x  {pt}')
    print()

# ── Top MeSH — the thematic core ──
if mesh_counter:
    print(f'{Y}Top MeSH Terms (thematic core):{R}')
    for term, c in mesh_counter.most_common(15):
        pct = c * 100 // n
        bar = '▓' * (pct // 5)
        major_flag = ' ★' if term in all_major else ''
        print(f'  {c:>2}/{n}  {G}{bar:<20}{R}  {term}{major_flag}')
    print(f'  {D}★ = major topic{R}')
    print()

# ── Keyword cloud ──
if kw_counter:
    print(f'{Y}Keyword Frequency:{R}')
    for kw, c in kw_counter.most_common(15):
        print(f'  {c:>2}x  {kw}')
    print()

# ── Recurring authors (collaboration signal) ──
repeat_auths = [(a, c) for a, c in author_counter.most_common() if c > 1]
if repeat_auths:
    print(f'{Y}Recurring Authors (appear in 2+ articles):{R}')
    for a, c in repeat_auths[:10]:
        print(f'  {c:>2}x  {a}')
    print()

# ── Thematic gaps ──
# Terms appearing in only 1 article = unique angles not shared
if mesh_counter:
    unique_terms = [t for t, c in mesh_counter.items() if c == 1]
    if unique_terms and n > 2:
        print(f'{Y}Unique MeSH (appear in only 1 article — potential gaps/angles):{R}')
        for t in sorted(unique_terms)[:15]:
            print(f'  {C}•{R} {t}')
        if len(unique_terms) > 15:
            print(f'  {D}… and {len(unique_terms)-15} more{R}')
        print()

# ── Suggested search queries based on top co-occurring terms ──
if len(mesh_counter) >= 2:
    top = [t for t, _ in mesh_counter.most_common(3)]
    print(f'{Y}Suggested Follow-up Searches:{R}')
    for i in range(len(top)):
        for j in range(i+1, len(top)):
            print(f'  {C}→{R} \"{top[i]}\" AND \"{top[j]}\"')
    if all_major:
        top_major = [t for t, _ in all_major.most_common(2)]
        if len(top_major) == 2:
            print(f'  {C}→{R} \"{top_major[0]}\" AND \"{top_major[1]}\" AND review[pt]')
    print()
"
        ;;

    # ── insights compare <pmid1> <pmid2> ── side by side ──────────
    compare)
        [[ $# -lt 2 ]] && { echo "${RED}Usage:${RESET} insights compare <pmid1> <pmid2>"; return 1; }
        local pmid1="$1" pmid2="$2"

        echo "${DIM}Comparing PMID ${pmid1} vs ${pmid2}…${RESET}"
        echo ""

        _api "efetch.fcgi?db=pubmed&id=${pmid1},${pmid2}&retmode=xml" | python3 -c "
import sys, xml.etree.ElementTree as ET

def txt(el):
    return ''.join(el.itertext()).strip() if el is not None else ''

B = '\033[1m'; D = '\033[2m'; C = '\033[0;36m'; Y = '\033[1;33m'
G = '\033[0;32m'; RED = '\033[0;31m'; R = '\033[0m'

root = ET.parse(sys.stdin).getroot()
articles = root.findall('.//PubmedArticle')
if len(articles) < 2:
    print('Could not fetch both articles.'); sys.exit(1)

def extract(pa):
    mc = pa.find('MedlineCitation')
    art = mc.find('Article') if mc is not None else None
    pmid = txt(mc.find('PMID')) if mc is not None else '?'
    title = txt(art.find('ArticleTitle')) if art is not None else '?'
    mesh = set()
    ml = mc.find('MeshHeadingList') if mc is not None else None
    if ml is not None:
        for mh in ml.findall('MeshHeading'):
            d = mh.find('DescriptorName')
            if d is not None: mesh.add(txt(d))
    kws = set()
    for kw in (mc.findall('.//Keyword') if mc is not None else []):
        if kw.text: kws.add(kw.text.lower())
    authors = set()
    al = art.find('AuthorList') if art is not None else None
    if al is not None:
        for au in al.findall('Author'):
            last = au.findtext('LastName', '')
            if last: authors.add(last)
    ptypes = set(txt(pt) for pt in (art.findall('.//PublicationType') if art is not None else []))
    return {'pmid': pmid, 'title': title, 'mesh': mesh, 'keywords': kws, 'authors': authors, 'ptypes': ptypes}

a = extract(articles[0])
b = extract(articles[1])

print(f'{B}Article A:{R}  PMID {a[\"pmid\"]}')
print(f'  {a[\"title\"][:90]}')
print(f'{B}Article B:{R}  PMID {b[\"pmid\"]}')
print(f'  {b[\"title\"][:90]}')
print()

# MeSH comparison
shared_mesh = a['mesh'] & b['mesh']
only_a = a['mesh'] - b['mesh']
only_b = b['mesh'] - a['mesh']
overlap = len(shared_mesh) * 100 // max(len(a['mesh'] | b['mesh']), 1)

print(f'{Y}MeSH Overlap:{R}  {overlap}%  ({len(shared_mesh)} shared, {len(only_a)} only A, {len(only_b)} only B)')
if shared_mesh:
    s = ', '.join(sorted(shared_mesh)[:10])
    print(f'  {G}Shared:{R}   {s}')
if only_a:
    s = ', '.join(sorted(only_a)[:8])
    print(f'  {C}Only A:{R}   {s}')
if only_b:
    s = ', '.join(sorted(only_b)[:8])
    print(f'  {C}Only B:{R}   {s}')
print()

# Keyword comparison
shared_kw = a['keywords'] & b['keywords']
if a['keywords'] or b['keywords']:
    print(f'{Y}Keyword Overlap:{R}')
    if shared_kw:
        s = ', '.join(sorted(shared_kw)[:10])
        print(f'  {G}Shared:{R}   {s}')
    only_ka = a['keywords'] - b['keywords']
    only_kb = b['keywords'] - a['keywords']
    if only_ka:
        s = ', '.join(sorted(only_ka)[:8])
        print(f'  {C}Only A:{R}   {s}')
    if only_kb:
        s = ', '.join(sorted(only_kb)[:8])
        print(f'  {C}Only B:{R}   {s}')
    print()

# Author overlap
shared_auth = a['authors'] & b['authors']
if shared_auth:
    s = ', '.join(sorted(shared_auth))
    print(f'{Y}Shared Authors:{R}  {s}')
    print()

# Study type comparison
pta = ', '.join(sorted(a['ptypes'])) or '(not specified)'
ptb = ', '.join(sorted(b['ptypes'])) or '(not specified)'
print(f'{Y}Study Types:{R}')
print(f'  A: {pta}')
print(f'  B: {ptb}')
print()

# Bridging suggestion
unique_combined = (only_a | only_b) - shared_mesh
if len(unique_combined) >= 2:
    top_bridge = sorted(unique_combined)[:2]
    print(f'{Y}Bridge Search:{R}  combine their unique angles')
    print(f'  {C}→{R} \"{top_bridge[0]}\" AND \"{top_bridge[1]}\"')
"
        ;;

    # ── insights gaps ── find what's missing across your collection ──
    gaps)
        local -a pmids
        mapfile -t pmids < <(_mine_load | python3 -c "
import sys, json
for e in json.load(sys.stdin):
    print(e['pmid'])
")
        [[ ${#pmids[@]} -lt 3 ]] && { echo "Need at least 3 mined articles for gap analysis."; return 1; }

        echo "${DIM}Analysing gaps across ${#pmids[@]} articles…${RESET}"
        echo ""
        local ids_csv
        ids_csv=$(IFS=,; echo "${pmids[*]}")

        _api "efetch.fcgi?db=pubmed&id=${ids_csv}&retmode=xml" | python3 -c "
import sys, xml.etree.ElementTree as ET
from collections import Counter, defaultdict

def txt(el):
    return ''.join(el.itertext()).strip() if el is not None else ''

B = '\033[1m'; D = '\033[2m'; C = '\033[0;36m'; Y = '\033[1;33m'
G = '\033[0;32m'; R = '\033[0m'

root = ET.parse(sys.stdin).getroot()
articles = root.findall('.//PubmedArticle')
n = len(articles)

# Build per-article MeSH sets
article_mesh = []
all_mesh = Counter()
ptypes_per_article = []

for pa in articles:
    mc = pa.find('MedlineCitation')
    art = mc.find('Article') if mc is not None else None
    mesh_set = set()
    ml = mc.find('MeshHeadingList') if mc is not None else None
    if ml is not None:
        for mh in ml.findall('MeshHeading'):
            d = mh.find('DescriptorName')
            name = txt(d)
            if name:
                mesh_set.add(name)
                all_mesh[name] += 1
    article_mesh.append(mesh_set)
    ptypes = set()
    if art is not None:
        for pt in art.findall('.//PublicationType'):
            t = txt(pt)
            if t: ptypes.add(t)
    ptypes_per_article.append(ptypes)

print(f'{B}══ Gap Analysis ({n} articles) ══{R}')
print()

# ── Missing coverage: terms that appear rarely ──
rare = [(t, c) for t, c in all_mesh.items() if c == 1]
core = [(t, c) for t, c in all_mesh.most_common() if c >= n * 0.5]

if core:
    print(f'{Y}Core Themes (≥50% of articles):{R}')
    for t, c in core:
        print(f'  {G}●{R} {t}  ({c}/{n})')
    print()

if rare and n > 2:
    print(f'{Y}Under-explored Angles (appear in only 1 article):{R}')
    for t, _ in sorted(rare, key=lambda x: x[0])[:20]:
        print(f'  {C}○{R} {t}')
    if len(rare) > 20:
        print(f'  {D}… and {len(rare)-20} more{R}')
    print()

# ── Study type gaps ──
all_ptypes = Counter()
for pts in ptypes_per_article:
    for p in pts: all_ptypes[p] += 1

common_types = {'Review', 'Systematic Review', 'Meta-Analysis', 'Randomized Controlled Trial', 'Clinical Trial', 'Observational Study', 'Case Reports'}
missing_types = common_types - set(all_ptypes.keys())
if missing_types:
    print(f'{Y}Study Types NOT in Your Collection:{R}')
    for t in sorted(missing_types):
        print(f'  {C}?{R} {t}')
    print(f'  {D}Consider searching: <topic> AND <type>[pt]{R}')
    print()

# ── Co-occurrence clusters ──
# Find pairs of MeSH terms that always appear together
if n >= 3:
    cooccur = Counter()
    for ms in article_mesh:
        terms = sorted(ms)
        for i in range(len(terms)):
            for j in range(i+1, len(terms)):
                cooccur[(terms[i], terms[j])] += 1
    strong_pairs = [(pair, c) for pair, c in cooccur.most_common(50) if c >= 2]
    if strong_pairs:
        print(f'{Y}Strong Topic Pairs (co-occur in 2+ articles):{R}')
        for (a, b), c in strong_pairs[:8]:
            print(f'  {c}x  {a}  ↔  {b}')
        print()

# ── Suggest searches to fill gaps ──
if core and rare:
    core_terms = [t for t, _ in core[:2]]
    rare_terms = [t for t, _ in rare[:3]]
    print(f'{Y}Suggested Gap-Filling Searches:{R}')
    for ct in core_terms:
        for rt in rare_terms[:2]:
            print(f'  {C}→{R} \"{ct}\" AND \"{rt}\"')
    if missing_types:
        mt = sorted(missing_types)[0]
        print(f'  {C}→{R} \"{core_terms[0]}\" AND {mt.lower().replace(\" \", \"+\")}[pt]')
    print()
"
        ;;

    help|*)
        python3 "${SCRIPT_DIR}/pubmed_insights.py" help
        ;;
    esac
}

cmd_help() {
    cat <<'EOF'

  ╔══════════════════════════════════════════════════════════╗
  ║              PubMed Architect — CLI                     ║
  ╚══════════════════════════════════════════════════════════╝

  IDENTIFIERS
    Every <id> below accepts either a PMID (e.g. 35901745)
    or a DOI (e.g. 10.1038/s41586-023-06291-2).
    DOIs are automatically resolved to PMIDs via NCBI.

  USAGE
    ./pubmed.sh <command> [arguments]

  COMMANDS
    search  <query> [-n max]        Search PubMed
    fetch   <id> [id …]             Fetch article JSON metadata
    related <id> [-n max]           Discover related articles
    cite    <id> [-f format]        Generate a formatted citation
    abstract <id>                   Print the abstract
    open    <id>                    Open article in browser (DOI → doi.org)
    batch   <file>                  Run queries from a file (one per line)
    mesh    <id> [id …]             Show MeSH terms (any number of articles)
    trends  <query> [-y years]      Publication-count bar chart by year
    export  <id …> [-f format]     Export multiple citations
    mine    <sub> [args]            Flag articles to mine (mine help for more)
    insights <sub> [args]           Research intelligence engine
      article  <id>                   Deep breakdown: study type, abstract stats, MeSH, funding
      mined                           Cross-analysis of all mined articles
      compare  <id1> <id2>            Side-by-side: Jaccard similarity, stats, funding, refs
      gaps                            Missing study types, unexplored MeSH, co-occurrence clusters
      rank     <query>                Score & rank mined articles by relevance
      timeline                        Chronological publication view
      brief                           One-page research brief of your collection
      scan     <query> [-n max]         Live search → MeSH/keyword landscape of a topic
      ask      <question> [-n max]       Ask a question — evidence synthesis from PubMed
      mesh     <id> [id …]            MeSH terms for one or more articles
      meshmap  <id> [id …]            Cross-article MeSH analysis (shared, unique, frequency)
    help                            Show this help

  FORMATS  (-f)
    apa        APA 7th edition style
    vancouver  Vancouver / NLM (default)
    bibtex     BibTeX entry

  EXAMPLES
    ./pubmed.sh search "CRISPR cancer therapy" -n 10
    ./pubmed.sh cite 35901745 -f apa
    ./pubmed.sh cite 10.1038/s41586-023-06291-2 -f apa
    ./pubmed.sh related 35901745 -n 5
    ./pubmed.sh fetch 10.1016/j.cell.2023.04.007
    ./pubmed.sh trends "machine learning radiology" -y 15
    ./pubmed.sh mesh 35901745
    ./pubmed.sh export 35901745 10.1038/s41586-023-06291-2 -f bibtex > refs.bib
    ./pubmed.sh abstract 35901745 | pbcopy
    ./pubmed.sh open 10.1038/s41586-023-06291-2
    ./pubmed.sh mine add 35901745 -t "key,CRISPR" -m "Must read"
    ./pubmed.sh mine add 10.1038/s41586-023-06291-2 -t "methods"
    ./pubmed.sh mine list
    ./pubmed.sh insights article 35901745
    ./pubmed.sh insights mined
    ./pubmed.sh insights compare 35901745 34567890
    ./pubmed.sh insights rank "idiopathic pulmonary fibrosis treatment"
    ./pubmed.sh insights timeline
    ./pubmed.sh insights brief
    ./pubmed.sh insights mesh 35901745 34567890
    ./pubmed.sh insights meshmap 35901745 10.1038/s41586-023-06291-2
    ./pubmed.sh insights ask "Does metformin reduce cancer risk?"
    ./pubmed.sh insights ask "What is the role of gut microbiome in depression?" -n 80

  PIPING
    Combine with standard tools:
      ./pubmed.sh fetch 35901745 | jq '.[] .title'
      ./pubmed.sh search "glioblastoma" | grep PMID
      ./pubmed.sh batch queries.txt > results.txt

EOF
}

# ── dispatch ──────────────────────────────────────────────────────────

_require curl python3

cmd="${1:-help}"
shift || true

case "$cmd" in
    search)   cmd_search "$@" ;;
    fetch)    cmd_fetch "$@" ;;
    related)  cmd_related "$@" ;;
    cite)     cmd_cite "$@" ;;
    abstract) cmd_abstract "$@" ;;
    open)     cmd_open "$@" ;;
    batch)    cmd_batch "$@" ;;
    mesh)     cmd_mesh "$@" ;;
    trends)   cmd_trends "$@" ;;
    export)   cmd_export "$@" ;;
    mine)     cmd_mine "$@" ;;
    insights) cmd_insights "$@" ;;
    help|-h|--help) cmd_help ;;
    *)
        echo "${RED}Unknown command:${RESET} ${cmd}"
        echo "Run ${BOLD}./pubmed.sh help${RESET} for usage."
        exit 1
        ;;
esac

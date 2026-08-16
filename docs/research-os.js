"use strict";

(() => {
  const STORE = {
    activity: "pubmed-architect-activity-v2",
    review: "pubmed-architect-living-review-v2",
    traces: "pubmed-architect-ai-traces-v2",
    lastSearch: "pubmed-architect-last-search-v2"
  };
  const matrixSelected = new Set();
  let reviewTimer;

  function read(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
    catch { return fallback; }
  }

  function write(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function nowStamp() {
    return new Date().toISOString();
  }

  function classify(article) {
    const types = (article.publicationTypes || []).join(" ").toLowerCase();
    if (/meta-analysis|systematic review|review/.test(types)) return {key: "review", label: "Review / synthesis"};
    if (/randomized controlled trial|controlled clinical trial/.test(types)) return {key: "randomized", label: "Randomized trial"};
    if (/clinical trial/.test(types)) return {key: "randomized", label: "Clinical trial"};
    if (/cohort|case-control|observational|comparative study|cross-sectional/.test(types)) return {key: "observational", label: "Observational"};
    return {key: "other", label: article.publicationTypes?.[0] || "Unclassified"};
  }

  function reporting(article) {
    const abstract = article.abstract || "";
    const signals = [
      {label: "Abstract", pass: abstract.length >= 250},
      {label: "Design", pass: (article.publicationTypes || []).length > 0},
      {label: "Outcomes", pass: /outcome|endpoint|result|change|effect|hazard|odds|risk|confidence interval|p\s*[<=>]/i.test(abstract)},
      {label: "Sample", pass: /\b(n\s*=\s*\d+|\d+\s+(patients|participants|subjects|adults|children))\b/i.test(abstract)},
      {label: "MeSH", pass: (article.mesh || []).length > 0}
    ];
    const score = signals.filter(item => item.pass).length;
    const design = classify(article).key;
    const grade = score >= 5 && design === "randomized" ? "A" : score >= 4 ? "B" : score >= 2 ? "C" : "D";
    return {signals, score, grade};
  }

  function counts() {
    const studies = library.filter(item => classify(item).key !== "review").length;
    const reviews = library.length - studies;
    return {records: library.length, studies, reviews, traces: read(STORE.traces, []).length};
  }

  function addActivity(entry) {
    const items = read(STORE.activity, []);
    items.unshift({id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, at: nowStamp(), ...entry});
    write(STORE.activity, items.slice(0, 40));
    renderDashboard();
  }

  function recordSearch(search) {
    const record = {...search, at: nowStamp()};
    write(STORE.lastSearch, record);
    addActivity({type: "search", title: search.query || "PubMed search", detail: `${search.total.toLocaleString()} matches · ${search.pmids.length} records retrieved`});
  }

  function recordTrace(trace) {
    const traces = read(STORE.traces, []);
    const record = {id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, at: nowStamp(), ...trace};
    traces.unshift(record);
    write(STORE.traces, traces.slice(0, 100));
    addActivity({type: "analysis", title: trace.label || "AI evidence analysis", detail: `${trace.provider} · ${(trace.pmids || []).length} source PMID${(trace.pmids || []).length === 1 ? "" : "s"}`});
  }

  function humanDate(value, includeTime = true) {
    if (!value) return "Not set";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("en-GB", {dateStyle: "medium", ...(includeTime ? {timeStyle: "short"} : {})}).format(date);
  }

  function renderActivity() {
    const mount = document.querySelector("#activity-list");
    if (!mount) return;
    const items = read(STORE.activity, []);
    mount.innerHTML = items.length ? items.slice(0, 8).map(item => `<article><span class="activity-icon ${escapeHTML(item.type)}">${item.type === "search" ? "⌕" : item.type === "analysis" ? "✦" : "↻"}</span><div><strong>${escapeHTML(item.title)}</strong><p>${escapeHTML(item.detail || "")}</p></div><time datetime="${escapeHTML(item.at)}">${escapeHTML(humanDate(item.at))}</time></article>`).join("") : `<div class="activity-empty"><strong>No activity recorded yet</strong><span>Your reproducible PubMed searches and AI evidence analyses will appear here.</span></div>`;
  }

  function renderDashboard() {
    if (!document.querySelector("#dashboard-view")) return;
    const totals = counts();
    document.querySelector("#workspace-date").textContent = new Intl.DateTimeFormat("en-GB", {dateStyle: "medium"}).format(new Date());
    document.querySelector("#dashboard-library-count").textContent = totals.records;
    document.querySelector("#dashboard-study-count").textContent = totals.studies;
    document.querySelector("#dashboard-review-count").textContent = totals.reviews;
    document.querySelector("#dashboard-trace-count").textContent = totals.traces;
    const ai = window.PubMedAIConfig?.get?.() || {};
    document.querySelector("#dashboard-ai-status").textContent = ai.openaiKey && ai.anthropicKey ? "Dual provider ready" : ai.openaiKey ? "OpenAI ready" : ai.anthropicKey ? "Claude ready" : "Keys not configured";
    renderActivity();
  }

  function filteredMatrix() {
    const design = document.querySelector("#matrix-design-filter")?.value || "";
    const threshold = document.querySelector("#matrix-grade-filter")?.value || "";
    const rank = {A: 4, B: 3, C: 2, D: 1};
    return library.filter(article => {
      const itemDesign = classify(article).key;
      const grade = reporting(article).grade;
      return (!design || itemDesign === design) && (!threshold || rank[grade] >= rank[threshold]);
    });
  }

  function renderMatrix() {
    const body = document.querySelector("#matrix-body");
    if (!body) return;
    const items = filteredMatrix();
    document.querySelector("#matrix-empty").hidden = library.length > 0;
    document.querySelector("#matrix-wrap").hidden = library.length === 0;
    document.querySelector("#matrix-summary").textContent = `${items.length} of ${library.length} records shown`;
    body.innerHTML = items.map(article => {
      const design = classify(article);
      const report = reporting(article);
      const author = article.authors?.[0] || "Unknown author";
      const checked = matrixSelected.has(article.pmid) || window.AIReader?.isSelected(article.pmid);
      return `<tr><td><input type="checkbox" data-matrix-select="${escapeHTML(article.pmid)}" data-ai-select="${escapeHTML(article.pmid)}" ${checked ? "checked" : ""} aria-label="Select PMID ${escapeHTML(article.pmid)}"></td><td><strong>${escapeHTML(article.title)}</strong><small>${escapeHTML(author)}${article.authors?.length > 1 ? " et al." : ""}, ${escapeHTML(article.year || "n.d.")} · PMID ${escapeHTML(article.pmid)}</small></td><td><span class="design-pill ${design.key}">${escapeHTML(design.label)}</span></td><td><div class="reporting-bar report-score-${report.score}" title="${report.score} of 5 metadata/reporting signals"><i></i></div><small>${report.score}/5 signals</small></td><td><span class="grade grade-${report.grade}">${report.grade}</span><small>screening</small></td><td><a href="${escapeHTML(articleURL(article))}" target="_blank" rel="noopener">Open ↗</a></td></tr>`;
    }).join("");
  }

  function graphData() {
    const articles = library.slice(0, 14);
    const frequency = new Map();
    articles.forEach(article => (article.mesh || []).slice(0, 8).forEach(term => frequency.set(term, (frequency.get(term) || 0) + 1)));
    const terms = [...frequency.entries()].sort((a, b) => b[1] - a[1]).slice(0, 14).map(([term, n]) => ({term, n}));
    return {articles, terms};
  }

  function renderGraph() {
    const mount = document.querySelector("#knowledge-graph");
    if (!mount) return;
    const {articles, terms} = graphData();
    if (!articles.length || !terms.length) {
      mount.innerHTML = `<div class="activity-empty"><strong>Graph awaiting indexed evidence</strong><span>Save PubMed records with MeSH terms to reveal co-indexing relationships.</span></div>`;
      return;
    }
    const width = 1000, height = 480, centerX = 500, centerY = 240;
    const termNodes = terms.map((item, index) => ({...item, x: centerX + Math.cos((index / terms.length) * Math.PI * 2) * 330, y: centerY + Math.sin((index / terms.length) * Math.PI * 2) * 175}));
    const articleNodes = articles.map((article, index) => ({article, x: centerX + Math.cos((index / articles.length) * Math.PI * 2 + .3) * 155, y: centerY + Math.sin((index / articles.length) * Math.PI * 2 + .3) * 105}));
    const lines = [];
    articleNodes.forEach(source => termNodes.forEach(target => { if ((source.article.mesh || []).includes(target.term)) lines.push(`<line x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" />`); }));
    const labels = termNodes.map(node => `<g class="term-node"><circle cx="${node.x}" cy="${node.y}" r="${8 + Math.min(node.n, 5) * 2}"/><text x="${node.x}" y="${node.y + 25}" text-anchor="middle">${escapeHTML(node.term.slice(0, 28))}</text></g>`).join("");
    const sources = articleNodes.map(node => `<g class="article-node"><circle cx="${node.x}" cy="${node.y}" r="9"/><title>${escapeHTML(node.article.title)} · PMID ${escapeHTML(node.article.pmid)}</title><text x="${node.x}" y="${node.y - 14}" text-anchor="middle">${escapeHTML(node.article.pmid)}</text></g>`).join("");
    mount.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Network of saved PubMed articles and shared MeSH terms"><g class="graph-links">${lines.join("")}</g>${labels}${sources}</svg>`;
  }

  function renderEvidence() {
    renderMatrix();
    renderGraph();
  }

  function reviewValue(id) {
    return document.querySelector(`#${id}`)?.value?.trim() || "";
  }

  function saveReview() {
    const review = {
      ...read(STORE.review, {}),
      title: reviewValue("review-title"), question: reviewValue("review-question"), query: reviewValue("review-query"),
      searchDate: reviewValue("review-search-date"), version: reviewValue("review-version"), eligibility: reviewValue("review-eligibility"),
      conclusion: reviewValue("review-conclusion"), updatedAt: nowStamp(), pmids: library.map(item => item.pmid)
    };
    write(STORE.review, review);
    const state = document.querySelector("#review-save-state");
    if (state) state.textContent = "Saved locally";
    renderReviewSnapshot();
  }

  function scheduleReviewSave() {
    const state = document.querySelector("#review-save-state");
    if (state) state.textContent = "Saving…";
    clearTimeout(reviewTimer);
    reviewTimer = setTimeout(saveReview, 350);
  }

  function loadReview() {
    const review = read(STORE.review, {});
    const map = {"review-title": review.title, "review-question": review.question, "review-query": review.query, "review-search-date": review.searchDate, "review-version": review.version || "1.0.0", "review-eligibility": review.eligibility, "review-conclusion": review.conclusion};
    Object.entries(map).forEach(([id, value]) => { const node = document.querySelector(`#${id}`); if (node && document.activeElement !== node) node.value = value || ""; });
  }

  function renderReviewSnapshot() {
    const total = counts();
    const review = read(STORE.review, {});
    document.querySelector("#review-record-count").textContent = total.records;
    document.querySelector("#snapshot-date").textContent = review.searchDate ? humanDate(`${review.searchDate}T00:00:00`, false) : "Not set";
    document.querySelector("#snapshot-refresh").textContent = review.lastRefresh ? humanDate(review.lastRefresh) : "Never";
    document.querySelector("#snapshot-primary").textContent = total.studies;
    document.querySelector("#snapshot-reviews").textContent = total.reviews;
    document.querySelector("#snapshot-traces").textContent = total.traces;
  }

  function renderReview() {
    loadReview();
    renderReviewSnapshot();
  }

  function reviewMarkdown() {
    saveReview();
    const review = read(STORE.review, {});
    const trace = read(STORE.traces, []);
    const records = library.map((article, index) => `${index + 1}. ${cite(article, "vancouver")}`).join("\n");
    const settings = review.searchSettings ? `\n- Article type: ${review.searchSettings.articleType || "All"}\n- From year: ${review.searchSettings.fromYear || "Not set"}\n- To year: ${review.searchSettings.toYear || "Not set"}\n- Sort: ${review.searchSettings.sort || "relevance"}` : "";
    return `# ${review.title || "Untitled living review"}\n\n**Version:** ${review.version || "1.0.0"}  \n**Search date:** ${review.searchDate || "Not set"}  \n**Exported:** ${nowStamp()}  \n**Evidence records:** ${library.length}  \n\n## Research question\n\n${review.question || "Not specified."}\n\n## Reproducible PubMed search\n\n\`\`\`text\n${review.query || "Not specified."}\n\`\`\`${settings}\n\n## Eligibility criteria\n\n${review.eligibility || "Not specified."}\n\n## Current conclusion\n\n${review.conclusion || "Not specified."}\n\n## Audit trail\n\n- Stored PMIDs: ${review.pmids?.join(", ") || "None"}\n- AI analysis traces: ${trace.length}\n- Last evidence refresh: ${review.lastRefresh || "Never"}\n\n## References\n\n${records || "No records in the evidence library."}\n`;
  }

  function matrixCSV() {
    const quote = value => `"${String(value ?? "").replace(/"/g, '""')}"`;
    const rows = [["PMID", "Title", "Year", "Journal", "Design", "Reporting signals", "Screening grade", "DOI"]];
    filteredMatrix().forEach(article => { const report = reporting(article); rows.push([article.pmid, article.title, article.year, article.journal, classify(article).label, `${report.score}/5`, report.grade, article.doi]); });
    return rows.map(row => row.map(quote).join(",")).join("\n");
  }

  async function refreshEvidence() {
    const query = reviewValue("review-query");
    if (!query) return toast("Add a PubMed search strategy first");
    const status = document.querySelector("#refresh-result");
    status.innerHTML = `<span class="loader"></span>Refreshing PubMed evidence…`;
    try {
      const searchResponse = await request("esearch.fcgi", new URLSearchParams({db: "pubmed", term: normalizedQuery(query), retmode: "json", retmax: "100", sort: "pub+date"}));
      const payload = await searchResponse.json();
      const ids = payload.esearchresult?.idlist || [];
      const prior = new Set(read(STORE.review, {}).pmids || []);
      const newIds = ids.filter(id => !prior.has(id));
      const review = read(STORE.review, {});
      review.lastRefresh = nowStamp();
      review.lastRefreshCount = ids.length;
      review.newPmids = newIds;
      write(STORE.review, review);
      status.innerHTML = `<strong>${newIds.length} new PMID${newIds.length === 1 ? "" : "s"} detected</strong><span>${ids.length} recent records checked · ${Number(payload.esearchresult?.count || 0).toLocaleString()} total matches</span>${newIds.length ? `<small>${newIds.map(id => `PMID ${escapeHTML(id)}`).join(" · ")}</small>` : ""}`;
      addActivity({type: "refresh", title: review.title || "Living review refreshed", detail: `${newIds.length} new PMIDs detected across ${Number(payload.esearchresult?.count || 0).toLocaleString()} matches`});
      renderReviewSnapshot();
    } catch (error) {
      status.textContent = `${error.message} Please verify the saved query and try again.`;
    }
  }

  function useLastSearch() {
    const search = read(STORE.lastSearch, null);
    if (!search) return toast("No PubMed search has been recorded yet");
    document.querySelector("#review-query").value = search.query || "";
    document.querySelector("#review-search-date").value = (search.at || nowStamp()).slice(0, 10);
    const review = read(STORE.review, {});
    review.searchSettings = {articleType: search.articleType, fromYear: search.fromYear, toYear: search.toYear, sort: search.sort};
    write(STORE.review, review);
    scheduleReviewSave();
    toast("Last PubMed search added to the protocol");
  }

  function render(view) {
    if (view === "dashboard") renderDashboard();
    if (view === "evidence") renderEvidence();
    if (view === "review") renderReview();
  }

  document.querySelector("#matrix-design-filter")?.addEventListener("change", renderMatrix);
  document.querySelector("#matrix-grade-filter")?.addEventListener("change", renderMatrix);
  document.querySelector("#export-matrix")?.addEventListener("click", () => download(`pubmed-evidence-matrix-${new Date().toISOString().slice(0, 10)}.csv`, matrixCSV(), "text/csv"));
  document.querySelector("#open-evidence-ai")?.addEventListener("click", () => document.querySelector("#ai-library-button")?.click());
  document.querySelector("#clear-activity")?.addEventListener("click", () => { write(STORE.activity, []); renderActivity(); toast("Activity ledger cleared"); });
  document.querySelector("#use-last-search")?.addEventListener("click", useLastSearch);
  document.querySelector("#refresh-review")?.addEventListener("click", refreshEvidence);
  document.querySelector("#export-review")?.addEventListener("click", () => download(`living-review-${new Date().toISOString().slice(0, 10)}.md`, reviewMarkdown(), "text/markdown"));
  ["review-title", "review-question", "review-query", "review-search-date", "review-version", "review-eligibility", "review-conclusion"].forEach(id => document.querySelector(`#${id}`)?.addEventListener("input", scheduleReviewSave));
  document.addEventListener("change", event => {
    const checkbox = event.target.closest("[data-matrix-select]");
    if (checkbox) checkbox.checked ? matrixSelected.add(checkbox.dataset.matrixSelect) : matrixSelected.delete(checkbox.dataset.matrixSelect);
  });
  window.addEventListener("pubmedarchitect:library", () => { renderDashboard(); renderEvidence(); renderReviewSnapshot(); });
  window.addEventListener("pubmedarchitect:ai-config", renderDashboard);

  window.ResearchOS = {render, recordSearch, recordTrace, addActivity};
  renderDashboard();
})();

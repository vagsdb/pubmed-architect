"use strict";

const API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils";
const STORAGE = {
  library: "pubmed-architect-library-v1",
  draft: "pubmed-architect-draft-v1"
};
const SECTIONS = ["Title", "Abstract", "Introduction", "Literature Review", "Methods", "Results", "Discussion", "Conclusion", "Acknowledgements"];

let results = [];
let library = loadJSON(STORAGE.library, []);
let draft = loadJSON(STORAGE.draft, Object.fromEntries(SECTIONS.map(section => [section, ""])));
let currentSection = "Title";
let saveTimer;

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

function loadJSON(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}

function escapeHTML(value = "") {
  return String(value).replace(/[&<>'"]/g, char => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;"})[char]);
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(element.timer);
  element.timer = setTimeout(() => element.classList.remove("show"), 2200);
}

function setView(name) {
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `${name}-view`));
  $$(".nav-link").forEach(link => link.classList.toggle("active", link.dataset.view === name));
  if (name === "library") renderLibrary();
  if (name === "builder") renderBuilder();
  window.scrollTo({top: 0, behavior: "smooth"});
  history.replaceState(null, "", `#${name}`);
}

function text(node, selector) {
  return node.querySelector(selector)?.textContent?.trim() || "";
}

function allText(node, selector) {
  return [...node.querySelectorAll(selector)].map(item => item.textContent.trim()).filter(Boolean);
}

function parseArticles(xmlText) {
  const xml = new DOMParser().parseFromString(xmlText, "application/xml");
  if (xml.querySelector("parsererror")) throw new Error("PubMed returned an unreadable response.");
  return [...xml.querySelectorAll("PubmedArticle")].map(record => {
    const article = record.querySelector("Article");
    const journalIssue = article?.querySelector("JournalIssue");
    const abstractParts = [...(article?.querySelectorAll("AbstractText") || [])].map(item => {
      const label = item.getAttribute("Label");
      return `${label ? `${label}: ` : ""}${item.textContent.trim()}`;
    });
    const authors = [...(article?.querySelectorAll("Author") || [])].map(author => {
      const collective = text(author, "CollectiveName");
      if (collective) return collective;
      const last = text(author, "LastName");
      const fore = text(author, "ForeName");
      return [last, fore].filter(Boolean).join(" ");
    }).filter(Boolean);
    const ids = [...record.querySelectorAll("ArticleId")];
    const doi = ids.find(id => id.getAttribute("IdType") === "doi")?.textContent?.trim() || "";
    const year = text(journalIssue, "PubDate > Year") || text(journalIssue, "PubDate > MedlineDate").slice(0, 4);
    const mesh = [...record.querySelectorAll("MeshHeading")].map(heading => text(heading, "DescriptorName")).filter(Boolean);
    return {
      pmid: text(record, "MedlineCitation > PMID"),
      title: text(article, "ArticleTitle") || "Untitled article",
      abstract: abstractParts.join("\n\n"),
      authors,
      journal: text(article, "Journal > ISOAbbreviation") || text(article, "Journal > Title"),
      year,
      volume: text(journalIssue, "Volume"),
      issue: text(journalIssue, "Issue"),
      pages: text(article, "Pagination > MedlinePgn") || text(article, "ELocationID"),
      doi,
      publicationTypes: allText(article, "PublicationType"),
      mesh
    };
  });
}

async function request(endpoint, params) {
  params.set("tool", "pubmed_architect_web");
  const response = await fetch(`${API}/${endpoint}?${params}`);
  if (!response.ok) throw new Error(`PubMed request failed (${response.status}).`);
  return response;
}

function normalizedQuery(raw) {
  const value = raw.trim();
  if (/^\d+$/.test(value)) return `${value}[pmid]`;
  if (/^10\.\d{4,9}\/.+/i.test(value)) return `"${value}"[AID]`;
  return value;
}

async function searchPubMed(raw) {
  let query = normalizedQuery(raw);
  const type = $("#article-type").value;
  if (type) query += ` AND ${type}`;
  const params = new URLSearchParams({
    db: "pubmed",
    term: query,
    retmode: "json",
    retmax: $("#result-limit").value,
    sort: $("#sort").value
  });
  const from = $("#from-year").value;
  const to = $("#to-year").value;
  if (from || to) {
    params.set("datetype", "pdat");
    if (from) params.set("mindate", `${from}/01/01`);
    if (to) params.set("maxdate", `${to}/12/31`);
  }
  const searchResponse = await request("esearch.fcgi", params);
  const payload = await searchResponse.json();
  const ids = payload.esearchresult?.idlist || [];
  if (!ids.length) return {articles: [], total: 0};
  const fetchResponse = await request("efetch.fcgi", new URLSearchParams({db: "pubmed", id: ids.join(","), retmode: "xml"}));
  return {articles: parseArticles(await fetchResponse.text()), total: Number(payload.esearchresult?.count || 0)};
}

function articleURL(article) {
  return article.doi ? `https://doi.org/${article.doi}` : `https://pubmed.ncbi.nlm.nih.gov/${article.pmid}/`;
}

function resultCard(article, index) {
  const isSaved = library.some(item => item.pmid === article.pmid);
  const authors = article.authors.length > 4 ? `${article.authors.slice(0, 4).join(", ")} et al.` : article.authors.join(", ");
  return `<article class="result-card">
    <div class="result-meta"><span class="pmid">PMID ${escapeHTML(article.pmid)}</span><span>${escapeHTML(article.journal)}</span><span>${escapeHTML(article.year)}</span>${article.publicationTypes[0] ? `<span>• ${escapeHTML(article.publicationTypes[0])}</span>` : ""}</div>
    <h2>${escapeHTML(article.title)}</h2>
    <p class="authors">${escapeHTML(authors || "Authors unavailable")}</p>
    <p class="abstract-preview">${escapeHTML(article.abstract || "No abstract available.")}</p>
    <div class="card-actions">
      <button class="text-button" data-action="details" data-index="${index}">Read abstract</button>
      <button class="secondary ${isSaved ? "saved" : ""}" data-action="save" data-index="${index}">${isSaved ? "✓ Saved" : "+ Add to library"}</button>
      <a class="button secondary" href="${escapeHTML(articleURL(article))}" target="_blank" rel="noopener" style="padding:8px 12px;font-size:12px;text-decoration:none">Open source ↗</a>
    </div>
  </article>`;
}

function renderResults(total = results.length) {
  $("#results").innerHTML = results.map(resultCard).join("");
  $("#search-status").textContent = results.length ? `Showing ${results.length} of ${total.toLocaleString()} matching PubMed records` : "No matching PubMed records found.";
}

function showDetails(article) {
  $("#dialog-content").innerHTML = `
    <div class="result-meta"><span class="pmid">PMID ${escapeHTML(article.pmid)}</span><span>${escapeHTML(article.journal)}</span><span>${escapeHTML(article.year)}</span></div>
    <h2>${escapeHTML(article.title)}</h2>
    <p class="authors">${escapeHTML(article.authors.join(", "))}</p>
    <h3>Abstract</h3><p>${escapeHTML(article.abstract || "No abstract available.").replace(/\n/g, "<br>")}</p>
    ${article.mesh.length ? `<h3>MeSH terms</h3><p>${article.mesh.map(escapeHTML).join(" · ")}</p>` : ""}
    <div class="card-actions"><a class="button" href="${escapeHTML(articleURL(article))}" target="_blank" rel="noopener" style="text-decoration:none">Open article ↗</a></div>
    <div id="ai-reader-mount"></div>`;
  $("#article-dialog").classList.add("ai-open");
  $("#article-dialog").showModal();
  window.AIReader?.mount([article], {mode: "single"});
}

function saveArticle(article) {
  if (library.some(item => item.pmid === article.pmid)) {
    toast("Already in your library");
    return;
  }
  library.unshift(article);
  persistLibrary();
  renderResults();
  toast("Added to citation library");
}

function persistLibrary() {
  localStorage.setItem(STORAGE.library, JSON.stringify(library));
  $("#library-count").textContent = library.length;
  updateCitationSelect();
}

function initials(name = "") {
  const parts = name.trim().split(/\s+/);
  return parts.length < 2 ? name : `${parts[0]} ${parts.slice(1).map(part => part[0]).join("")}`;
}

function cite(article, format = $("#citation-format").value) {
  const authors = article.authors || [];
  if (format === "apa") {
    const apaAuthors = authors.map(name => {
      const parts = name.split(" ");
      return parts.length > 1 ? `${parts[0]}, ${parts.slice(1).map(part => `${part[0]}.`).join(" ")}` : name;
    }).join(", ");
    return `${apaAuthors || "Unknown author"} (${article.year || "n.d."}). ${article.title}. ${article.journal}${article.volume ? `, ${article.volume}` : ""}${article.issue ? `(${article.issue})` : ""}${article.pages ? `, ${article.pages}` : ""}.${article.doi ? ` https://doi.org/${article.doi}` : ""}`;
  }
  if (format === "bibtex") {
    const key = `${(authors[0] || "article").split(" ")[0].replace(/\W/g, "")}${article.year || ""}`;
    return `@article{${key},\n  author = {${authors.join(" and ")}},\n  title = {${article.title}},\n  journal = {${article.journal}},\n  year = {${article.year}},\n  volume = {${article.volume}},\n  number = {${article.issue}},\n  pages = {${article.pages}},\n  doi = {${article.doi}},\n  pmid = {${article.pmid}}\n}`;
  }
  const displayAuthors = authors.length > 6 ? `${authors.slice(0, 6).map(initials).join(", ")}, et al` : authors.map(initials).join(", ");
  return `${displayAuthors || "Unknown author"}. ${article.title}. ${article.journal}. ${article.year}${article.volume ? `;${article.volume}` : ""}${article.issue ? `(${article.issue})` : ""}${article.pages ? `:${article.pages}` : ""}.${article.doi ? ` doi:${article.doi}.` : ""} PMID: ${article.pmid}.`;
}

function renderLibrary() {
  $("#library-empty").hidden = library.length > 0;
  const format = $("#citation-format").value;
  $("#library-list").innerHTML = library.map((article, index) => `<article class="library-card">
    <div><label class="library-select"><input type="checkbox" data-ai-select="${escapeHTML(article.pmid)}" ${window.AIReader?.isSelected(article.pmid) ? "checked" : ""}> Select for AI comparison</label><div class="result-meta"><span class="pmid">PMID ${escapeHTML(article.pmid)}</span><span>${escapeHTML(article.journal)}</span><span>${escapeHTML(article.year)}</span></div><h2>${escapeHTML(article.title)}</h2><p class="authors">${escapeHTML(article.authors.join(", "))}</p></div>
    <button class="icon-button" data-remove="${index}" aria-label="Remove citation">Remove</button>
    <pre class="formatted-citation">${escapeHTML(cite(article, format))}</pre>
  </article>`).join("");
}

function download(filename, content, type = "text/plain") {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([content], {type}));
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function updateCitationSelect() {
  $("#insert-citation").innerHTML = `<option value="">Insert citation…</option>${library.map((article, index) => `<option value="${index}">${escapeHTML((article.authors[0] || "Source").split(" ")[0])} (${escapeHTML(article.year)}) — ${escapeHTML(article.title.slice(0, 65))}</option>`).join("")}`;
  window.AIReader?.refreshBuilderCitations(library);
}

function renderBuilder() {
  $("#section-nav").innerHTML = SECTIONS.map(section => `<button data-section="${section}" class="${section === currentSection ? "active" : ""}">${section}</button>`).join("");
  $("#section-label").textContent = currentSection;
  $("#section-editor").value = draft[currentSection] || "";
  updateWordCount();
  updateCitationSelect();
}

function updateWordCount() {
  const words = $("#section-editor").value.trim().match(/\b[\p{L}\p{N}'’-]+\b/gu)?.length || 0;
  $("#word-count").textContent = `${words} word${words === 1 ? "" : "s"}`;
}

function saveDraft() {
  draft[currentSection] = $("#section-editor").value;
  $("#save-state").textContent = "Saving…";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    localStorage.setItem(STORAGE.draft, JSON.stringify(draft));
    $("#save-state").textContent = "Saved locally";
  }, 350);
}

function articleMarkdown() {
  const sections = SECTIONS.filter(section => (draft[section] || "").trim()).map(section => `${section === "Title" ? "#" : "##"} ${section}\n\n${draft[section].trim()}`);
  if (library.length) sections.push(`## References\n\n${library.map((article, index) => `${index + 1}. ${cite(article, "vancouver")}`).join("\n\n")}`);
  return `${sections.join("\n\n")}\n`;
}

document.addEventListener("click", event => {
  const nav = event.target.closest("[data-view]");
  if (nav) setView(nav.dataset.view);
  const go = event.target.closest("[data-go]");
  if (go) setView(go.dataset.go);
  const action = event.target.closest("[data-action]");
  if (action) {
    const article = results[Number(action.dataset.index)];
    if (action.dataset.action === "details") showDetails(article);
    if (action.dataset.action === "save") saveArticle(article);
  }
  const remove = event.target.closest("[data-remove]");
  if (remove) {
    library.splice(Number(remove.dataset.remove), 1);
    persistLibrary();
    renderLibrary();
    toast("Citation removed");
  }
  const section = event.target.closest("[data-section]");
  if (section) {
    saveDraft();
    currentSection = section.dataset.section;
    renderBuilder();
    $("#section-editor").focus();
  }
});

$("#search-form").addEventListener("submit", async event => {
  event.preventDefault();
  const status = $("#search-status");
  status.innerHTML = `<span class="loader"></span>Searching PubMed…`;
  $("#results").innerHTML = "";
  try {
    const response = await searchPubMed($("#query").value);
    results = response.articles;
    renderResults(response.total);
  } catch (error) {
    status.textContent = `${error.message} Please try again.`;
  }
});

$("#results").addEventListener("click", () => {});
$("#citation-format").addEventListener("change", renderLibrary);
$("#copy-library").addEventListener("click", async () => {
  if (!library.length) return toast("Your library is empty");
  await navigator.clipboard.writeText(library.map((article, index) => `${index + 1}. ${cite(article)}`).join("\n\n"));
  toast("Citations copied");
});
$("#export-library").addEventListener("click", () => {
  if (!library.length) return toast("Your library is empty");
  const format = $("#citation-format").value;
  download(`pubmed-architect-citations.${format === "bibtex" ? "bib" : "txt"}`, library.map((article, index) => format === "bibtex" ? cite(article, format) : `${index + 1}. ${cite(article, format)}`).join("\n\n"));
});
$("#section-editor").addEventListener("input", () => { updateWordCount(); saveDraft(); });
$("#insert-citation-button").addEventListener("click", () => {
  const index = $("#insert-citation").value;
  if (index === "") return;
  const article = library[Number(index)];
  const marker = `(${(article.authors[0] || "Unknown").split(" ")[0]}, ${article.year || "n.d."})`;
  const editor = $("#section-editor");
  editor.setRangeText(marker, editor.selectionStart, editor.selectionEnd, "end");
  editor.focus();
  saveDraft();
});
$("#export-article").addEventListener("click", () => { saveDraft(); download("pubmed-architect-article.md", articleMarkdown(), "text/markdown"); });
$("#article-dialog .dialog-close").addEventListener("click", () => { $("#article-dialog").close(); $("#article-dialog").classList.remove("ai-open"); });
$("#article-dialog").addEventListener("click", event => { if (event.target === $("#article-dialog")) { $("#article-dialog").close(); $("#article-dialog").classList.remove("ai-open"); } });

persistLibrary();
renderBuilder();
const initialView = location.hash.slice(1);
setView(["search", "library", "builder", "about"].includes(initialView) ? initialView : "search");

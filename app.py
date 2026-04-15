#!/usr/bin/env python3
"""
PubMed Architect — A desktop research‑article assistant.

Run:  python app.py
"""

import json
import os
import queue
import re
import threading
import tkinter as tk
from collections import Counter
from tkinter import ttk, messagebox, filedialog

from pubmed_api import PubMedClient

DATA_FILE = "project_data.json"

SECTIONS = [
    "Title",
    "Abstract",
    "Introduction",
    "Literature Review",
    "Methods",
    "Results",
    "Discussion",
    "Conclusion",
    "Acknowledgements",
    "References",
]


# ── Utility ───────────────────────────────────────────────────────────


def _threaded(fn, callback, *args):
    """Run *fn* in a background thread; call *callback(result, err)* on finish."""

    def _worker():
        try:
            result = fn(*args)
            callback(result, None)
        except Exception as exc:
            callback(None, exc)

    threading.Thread(target=_worker, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════
#  Main application
# ══════════════════════════════════════════════════════════════════════


class PubMedArchitect(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PubMed Architect")
        self.geometry("1200x780")
        self.minsize(900, 600)

        self.client = PubMedClient()

        # Data
        self.citations: list[dict] = []
        self.sections: dict[str, str] = {s: "" for s in SECTIONS}
        self._load_data()

        # Cached search results (full dicts)
        self._search_results: list[dict] = []
        self._discover_results: list[dict] = []

        self._cb_queue: queue.Queue = queue.Queue()

        self._build_menu()
        self._build_ui()
        self._poll_callbacks()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── thread-safe callback queue ──────────────────────────────────

    def schedule(self, fn, *args):
        """Schedule *fn(*args)* to run on the main thread."""
        self._cb_queue.put((fn, args))

    def _poll_callbacks(self):
        while True:
            try:
                fn, args = self._cb_queue.get_nowait()
                fn(*args)
            except queue.Empty:
                break
        self.after(50, self._poll_callbacks)

    # ── persistence ───────────────────────────────────────────────────

    def _data_path(self):
        return os.path.join(os.path.dirname(__file__) or ".", DATA_FILE)

    def _load_data(self):
        path = self._data_path()
        if os.path.exists(path):
            try:
                with open(path) as f:
                    d = json.load(f)
                self.citations = d.get("citations", [])
                saved = d.get("sections", {})
                for s in SECTIONS:
                    self.sections[s] = saved.get(s, "")
            except Exception:
                pass

    def _save_data(self):
        with open(self._data_path(), "w") as f:
            json.dump(
                {"citations": self.citations, "sections": self.sections},
                f,
                indent=2,
            )

    def _on_close(self):
        # auto‑save current outline text
        if hasattr(self, "outline_tab"):
            self.outline_tab.persist_current()
        try:
            self._save_data()
        except Exception:
            pass
        self.destroy()

    # ── menu bar ──────────────────────────────────────────────────────

    def _build_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Save project", command=self._save_data)
        file_menu.add_command(
            label="Export citations…", command=self._export_citations
        )
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)

    def _export_citations(self):
        if not self.citations:
            messagebox.showinfo("Export", "No citations saved yet.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Text", "*.txt"),
                ("BibTeX", "*.bib"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        fmt = PubMedClient.format_bibtex if path.endswith(".bib") else PubMedClient.format_vancouver
        with open(path, "w") as f:
            for c in self.citations:
                f.write(fmt(c) + "\n\n")
        messagebox.showinfo("Export", f"Saved {len(self.citations)} citations to\n{path}")

    # ── UI skeleton ───────────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style(self)
        style.configure("TNotebook.Tab", padding=[14, 4])

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))

        self.search_tab = SearchTab(nb, self)
        self.cite_tab = CitationsTab(nb, self)
        self.outline_tab = OutlineTab(nb, self)
        self.discover_tab = DiscoverTab(nb, self)
        self.ask_tab = AskTab(nb, self)

        nb.add(self.search_tab, text="  Search  ")
        nb.add(self.cite_tab, text="  Citations  ")
        nb.add(self.outline_tab, text="  Article Builder  ")
        nb.add(self.discover_tab, text="  Discover  ")
        nb.add(self.ask_tab, text="  Ask  ")

        # status bar
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, relief=tk.SUNKEN, anchor="w").pack(
            fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 4)
        )

    def set_status(self, msg: str):
        self.status.set(msg)

    # helper for child tabs
    def add_citation(self, article: dict):
        if any(
            c["pmid"] == article["pmid"]
            or (c.get("doi") and c["doi"] == article.get("doi"))
            for c in self.citations
        ):
            messagebox.showinfo("Info", "Already in your citations.")
            return
        self.citations.append(article)
        self.cite_tab.refresh()
        self.set_status(f"Added: {article['title'][:80]}")


# ══════════════════════════════════════════════════════════════════════
#  Search Tab
# ══════════════════════════════════════════════════════════════════════


_ARTICLE_TYPES = {
    "All": "",
    "Review": "review[pt]",
    "Systematic Review": "systematic review[pt]",
    "Meta-Analysis": "meta-analysis[pt]",
    "Clinical Trial": "clinical trial[pt]",
    "Randomized Controlled Trial": "randomized controlled trial[pt]",
    "Observational Study": "observational study[pt]",
    "Case Reports": "case reports[pt]",
}

_SORT_OPTIONS = {
    "Relevance": "relevance",
    "Date (newest)": "pub+date",
    "First Author": "first+author",
}

_MAX_HISTORY = 20


class SearchTab(ttk.Frame):
    def __init__(self, parent, app: PubMedArchitect):
        super().__init__(parent)
        self.app = app
        self._search_history: list[str] = []
        self._filtered_indices: list[int] = []  # maps listbox row → _search_results index
        self._build()

    def _build(self):
        # ── row 1: query + search button ──
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=(8, 2))

        ttk.Label(bar, text="Search PubMed:").pack(side=tk.LEFT)
        self.query_var = tk.StringVar()
        self.query_cb = ttk.Combobox(bar, textvariable=self.query_var, width=55)
        self.query_cb.pack(side=tk.LEFT, padx=6)
        self.query_cb.bind("<Return>", lambda _: self._do_search())

        ttk.Label(bar, text="Max:").pack(side=tk.LEFT)
        self.max_var = tk.IntVar(value=20)
        ttk.Spinbox(bar, from_=5, to=200, width=5, textvariable=self.max_var).pack(
            side=tk.LEFT, padx=(2, 8)
        )
        ttk.Button(bar, text="Search", command=self._do_search).pack(side=tk.LEFT)
        ttk.Button(bar, text="Clear", command=self._clear_search).pack(side=tk.LEFT, padx=4)

        # ── row 2: advanced filters ──
        filt = ttk.LabelFrame(self, text="Filters")
        filt.pack(fill=tk.X, padx=8, pady=(0, 4))

        frow = ttk.Frame(filt)
        frow.pack(fill=tk.X, padx=6, pady=4)

        ttk.Label(frow, text="Type:").pack(side=tk.LEFT)
        self.type_var = tk.StringVar(value="All")
        type_cb = ttk.Combobox(
            frow, textvariable=self.type_var, values=list(_ARTICLE_TYPES.keys()),
            state="readonly", width=22,
        )
        type_cb.pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(frow, text="Sort:").pack(side=tk.LEFT)
        self.sort_var = tk.StringVar(value="Relevance")
        sort_cb = ttk.Combobox(
            frow, textvariable=self.sort_var, values=list(_SORT_OPTIONS.keys()),
            state="readonly", width=16,
        )
        sort_cb.pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(frow, text="From year:").pack(side=tk.LEFT)
        self.from_year_var = tk.StringVar()
        ttk.Entry(frow, textvariable=self.from_year_var, width=6).pack(side=tk.LEFT, padx=(2, 8))

        ttk.Label(frow, text="To year:").pack(side=tk.LEFT)
        self.to_year_var = tk.StringVar()
        ttk.Entry(frow, textvariable=self.to_year_var, width=6).pack(side=tk.LEFT, padx=(2, 8))

        # ── paned: results list | detail ──
        pw = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # left: results list + local filter
        left = ttk.Frame(pw)
        pw.add(left, weight=2)

        # result count label
        top_left = ttk.Frame(left)
        top_left.pack(fill=tk.X)
        self.count_var = tk.StringVar()
        ttk.Label(top_left, textvariable=self.count_var, font=("TkDefaultFont", 10)).pack(
            side=tk.LEFT
        )

        self.result_list = tk.Listbox(left, font=("TkDefaultFont", 11), selectmode=tk.EXTENDED)
        sb = ttk.Scrollbar(left, command=self.result_list.yview)
        self.result_list.config(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.result_list.bind("<<ListboxSelect>>", self._on_select)

        # local filter entry below the list
        filter_bar = ttk.Frame(left)
        filter_bar.pack(fill=tk.X, pady=(2, 0), side=tk.BOTTOM)
        ttk.Label(filter_bar, text="Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())
        ttk.Entry(filter_bar, textvariable=self.filter_var, width=30).pack(
            side=tk.LEFT, padx=4, fill=tk.X, expand=True
        )

        # right: detail + buttons
        right = ttk.Frame(pw)
        pw.add(right, weight=3)

        self.detail = tk.Text(right, wrap=tk.WORD, state=tk.DISABLED, font=("TkDefaultFont", 11))
        dsb = ttk.Scrollbar(right, command=self.detail.yview)
        self.detail.config(yscrollcommand=dsb.set)
        dsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.detail.pack(fill=tk.BOTH, expand=True)

        btn_bar = ttk.Frame(right)
        btn_bar.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_bar, text="Add to Citations", command=self._add_selected).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(btn_bar, text="Add All Selected", command=self._add_all_selected).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(btn_bar, text="Open in Browser", command=self._open_in_browser).pack(
            side=tk.LEFT, padx=4
        )

    # ── helpers ──

    def _push_history(self, query: str):
        """Add a query to the search history dropdown (most recent first)."""
        if query in self._search_history:
            self._search_history.remove(query)
        self._search_history.insert(0, query)
        self._search_history = self._search_history[:_MAX_HISTORY]
        self.query_cb["values"] = self._search_history

    def _parse_year(self, var: tk.StringVar) -> int | None:
        txt = var.get().strip()
        if txt and txt.isdigit() and len(txt) == 4:
            return int(txt)
        return None

    def _build_query(self, q: str) -> str:
        """Append article-type filter tag to the raw query if selected."""
        type_tag = _ARTICLE_TYPES.get(self.type_var.get(), "")
        if type_tag:
            q = f"({q}) AND {type_tag}"
        return q

    def _clear_search(self):
        self.query_var.set("")
        self.filter_var.set("")
        self.result_list.delete(0, tk.END)
        self.app._search_results = []
        self._filtered_indices = []
        self.count_var.set("")
        self._show_detail("")
        self.app.set_status("Ready")

    # ── actions ──

    def _do_search(self):
        q = self.query_var.get().strip()
        if not q:
            return
        self._push_history(q)
        self.app.set_status(f'Searching PubMed for "{q}" ...')
        self.result_list.delete(0, tk.END)
        self.filter_var.set("")
        self._show_detail("Searching…")

        max_results = self.max_var.get()
        sort_key = _SORT_OPTIONS.get(self.sort_var.get(), "relevance")
        from_yr = self._parse_year(self.from_year_var)
        to_yr = self._parse_year(self.to_year_var)
        full_q = self._build_query(q)

        def _search():
            # Direct lookup when the input is a DOI or PMID
            if self.app.client.is_doi(q) or q.isdigit():
                articles = self.app.client.fetch_details([q])
                return articles, len(articles)
            pmids, total = self.app.client.search(
                full_q, max_results, sort=sort_key, from_year=from_yr, to_year=to_yr,
            )
            articles = self.app.client.fetch_details(pmids)
            return articles, total

        def _done(result, err):
            if err:
                self.app.set_status(f"Error: {err}")
                self._show_detail(f"Error: {err}")
                return
            articles, total = result
            self.app._search_results = articles or []
            self._populate_list()
            shown = len(self.app._search_results)
            if total > shown:
                self.count_var.set(f"Showing {shown} of {total:,} results")
            else:
                self.count_var.set(f"{shown} results")
            self.app.set_status(
                f"Found {shown} results" + (f" (of {total:,} total)" if total > shown else "")
            )
            if not articles:
                self._show_detail("No results found.")

        _threaded(_search, lambda r, e: self.app.schedule(_done, r, e))

    def _populate_list(self):
        """Fill the listbox from _search_results, respecting the local filter."""
        self.result_list.delete(0, tk.END)
        filt = self.filter_var.get().strip().lower()
        self._filtered_indices = []
        for i, a in enumerate(self.app._search_results):
            label = self._result_label(i, a)
            if filt and filt not in label.lower() and filt not in a["abstract"].lower():
                continue
            self._filtered_indices.append(i)
            self.result_list.insert(tk.END, label)

    @staticmethod
    def _result_label(idx: int, a: dict) -> str:
        """Build a richer one-line label for the result list."""
        first_author = a["authors"][0].split()[0] if a["authors"] else "?"
        year = a["year"] or "?"
        journal = a["journal"][:20] if a["journal"] else ""
        title = a["title"][:80]
        return f"[{idx+1}] {first_author} ({year}) {journal} — {title}"

    def _apply_filter(self):
        """Re-populate the listbox when the local filter text changes."""
        if not self.app._search_results:
            return
        self._populate_list()

    def _on_select(self, _event=None):
        sel = self.result_list.curselection()
        if not sel:
            return
        real_idx = self._filtered_indices[sel[0]]
        a = self.app._search_results[real_idx]
        self._show_article(a)

    def _show_detail(self, text: str):
        self.detail.config(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert(tk.END, text)
        self.detail.config(state=tk.DISABLED)

    def _show_article(self, a: dict):
        lines = [
            a["title"],
            "",
            ", ".join(a["authors"]),
            f'{a["journal"]}  {a["year"]}  {a["volume"]}({a["issue"]}):{a["pages"]}',
            f'PMID: {a["pmid"]}   DOI: {a["doi"]}',
            "",
            "── Abstract ──",
            a["abstract"] or "(no abstract)",
            "",
        ]
        if a["mesh_terms"]:
            lines += ["── MeSH Terms ──", ", ".join(a["mesh_terms"]), ""]
        if a["keywords"]:
            lines += ["── Keywords ──", ", ".join(a["keywords"])]
        self._show_detail("\n".join(lines))

    def _add_selected(self):
        sel = self.result_list.curselection()
        if not sel:
            return
        real_idx = self._filtered_indices[sel[0]]
        self.app.add_citation(self.app._search_results[real_idx])

    def _add_all_selected(self):
        """Add every currently-selected result to citations."""
        sel = self.result_list.curselection()
        if not sel:
            return
        added = 0
        for s in sel:
            real_idx = self._filtered_indices[s]
            a = self.app._search_results[real_idx]
            if not any(
                c["pmid"] == a["pmid"]
                or (c.get("doi") and c["doi"] == a.get("doi"))
                for c in self.app.citations
            ):
                self.app.citations.append(a)
                added += 1
        if added:
            self.app.cite_tab.refresh()
            self.app.set_status(f"Added {added} citation{'s' if added != 1 else ''}")
        else:
            messagebox.showinfo("Info", "All selected articles are already in your citations.")

    def _open_in_browser(self):
        sel = self.result_list.curselection()
        if not sel:
            return
        real_idx = self._filtered_indices[sel[0]]
        a = self.app._search_results[real_idx]
        import webbrowser

        url = (
            f"https://doi.org/{a['doi']}"
            if a["doi"]
            else f"https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/"
        )
        webbrowser.open(url)


# ══════════════════════════════════════════════════════════════════════
#  Citations Tab
# ══════════════════════════════════════════════════════════════════════


class CitationsTab(ttk.Frame):
    def __init__(self, parent, app: PubMedArchitect):
        super().__init__(parent)
        self.app = app
        self._build()
        self.refresh()

    def _build(self):
        pw = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # left: citation list
        left = ttk.Frame(pw)
        pw.add(left, weight=2)

        lbl_frame = ttk.Frame(left)
        lbl_frame.pack(fill=tk.X)
        ttk.Label(lbl_frame, text="Saved Citations", font=("TkDefaultFont", 12, "bold")).pack(
            side=tk.LEFT
        )
        self.count_var = tk.StringVar()
        ttk.Label(lbl_frame, textvariable=self.count_var).pack(side=tk.RIGHT)

        self.cite_list = tk.Listbox(left, font=("TkDefaultFont", 11))
        csb = ttk.Scrollbar(left, command=self.cite_list.yview)
        self.cite_list.config(yscrollcommand=csb.set)
        csb.pack(side=tk.RIGHT, fill=tk.Y)
        self.cite_list.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.cite_list.bind("<<ListboxSelect>>", self._on_select)

        # right: formatted citation + buttons
        right = ttk.Frame(pw)
        pw.add(right, weight=3)

        # format selector
        fmt_bar = ttk.Frame(right)
        fmt_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(fmt_bar, text="Format:").pack(side=tk.LEFT)
        self.fmt_var = tk.StringVar(value="Vancouver")
        for f in ("APA", "Vancouver", "BibTeX"):
            ttk.Radiobutton(fmt_bar, text=f, variable=self.fmt_var, value=f, command=self._reformat).pack(
                side=tk.LEFT, padx=4
            )

        self.cite_detail = tk.Text(right, wrap=tk.WORD, state=tk.DISABLED, font=("TkDefaultFont", 11))
        cdsb = ttk.Scrollbar(right, command=self.cite_detail.yview)
        self.cite_detail.config(yscrollcommand=cdsb.set)
        cdsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.cite_detail.pack(fill=tk.BOTH, expand=True)

        btn_bar = ttk.Frame(right)
        btn_bar.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_bar, text="Copy Citation", command=self._copy).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="Remove", command=self._remove).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="Copy All", command=self._copy_all).pack(side=tk.RIGHT, padx=4)

    def refresh(self):
        self.cite_list.delete(0, tk.END)
        for i, c in enumerate(self.app.citations):
            self.cite_list.insert(tk.END, f"[{i+1}] {c['title'][:100]}")
        self.count_var.set(f"({len(self.app.citations)})")

    def _formatter(self):
        return {
            "APA": PubMedClient.format_apa,
            "Vancouver": PubMedClient.format_vancouver,
            "BibTeX": PubMedClient.format_bibtex,
        }[self.fmt_var.get()]

    def _on_select(self, _=None):
        self._reformat()

    def _reformat(self):
        sel = self.cite_list.curselection()
        if not sel:
            return
        a = self.app.citations[sel[0]]
        fmt = self._formatter()
        self.cite_detail.config(state=tk.NORMAL)
        self.cite_detail.delete("1.0", tk.END)
        self.cite_detail.insert(tk.END, fmt(a))
        self.cite_detail.insert(tk.END, "\n\n── Details ──\n")
        self.cite_detail.insert(tk.END, f"PMID: {a['pmid']}\n")
        self.cite_detail.insert(tk.END, f"DOI: {a['doi']}\n")
        self.cite_detail.insert(tk.END, f"Journal: {a['journal']} ({a['year']})\n")
        self.cite_detail.insert(tk.END, f"Authors: {', '.join(a['authors'])}\n")
        if a["mesh_terms"]:
            self.cite_detail.insert(tk.END, f"\nMeSH: {', '.join(a['mesh_terms'])}\n")
        if a["keywords"]:
            self.cite_detail.insert(tk.END, f"Keywords: {', '.join(a['keywords'])}\n")
        self.cite_detail.config(state=tk.DISABLED)

    def _copy(self):
        sel = self.cite_list.curselection()
        if not sel:
            return
        a = self.app.citations[sel[0]]
        text = self._formatter()(a)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.set_status("Citation copied to clipboard")

    def _copy_all(self):
        fmt = self._formatter()
        text = "\n\n".join(fmt(c) for c in self.app.citations)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.set_status(f"Copied {len(self.app.citations)} citations")

    def _remove(self):
        sel = self.cite_list.curselection()
        if not sel:
            return
        del self.app.citations[sel[0]]
        self.refresh()
        self.cite_detail.config(state=tk.NORMAL)
        self.cite_detail.delete("1.0", tk.END)
        self.cite_detail.config(state=tk.DISABLED)


# ══════════════════════════════════════════════════════════════════════
#  Article Builder Tab
# ══════════════════════════════════════════════════════════════════════


class OutlineTab(ttk.Frame):
    def __init__(self, parent, app: PubMedArchitect):
        super().__init__(parent)
        self.app = app
        self._current_section = None
        self._build()

    def _build(self):
        pw = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # left: section list
        left = ttk.Frame(pw)
        pw.add(left, weight=1)
        ttk.Label(left, text="Sections", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")

        self.sec_list = tk.Listbox(left, font=("TkDefaultFont", 12), activestyle="none")
        self.sec_list.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        for s in SECTIONS:
            self.sec_list.insert(tk.END, s)
        self.sec_list.bind("<<ListboxSelect>>", self._on_section_select)

        # right: editor
        right = ttk.Frame(pw)
        pw.add(right, weight=4)

        top = ttk.Frame(right)
        top.pack(fill=tk.X)
        self.sec_label = tk.StringVar(value="Select a section")
        ttk.Label(top, textvariable=self.sec_label, font=("TkDefaultFont", 13, "bold")).pack(
            side=tk.LEFT
        )
        self.wc_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.wc_var).pack(side=tk.RIGHT)

        self.editor = tk.Text(right, wrap=tk.WORD, undo=True, font=("TkDefaultFont", 12))
        esb = ttk.Scrollbar(right, command=self.editor.yview)
        self.editor.config(yscrollcommand=esb.set)
        esb.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.editor.bind("<KeyRelease>", self._update_wc)

        btn_bar = ttk.Frame(right)
        btn_bar.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_bar, text="Insert Citation Ref", command=self._insert_cite).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(btn_bar, text="Save Section", command=self._save_section).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="Export Article…", command=self._export_article).pack(
            side=tk.RIGHT, padx=4
        )

    def _on_section_select(self, _=None):
        self.persist_current()
        sel = self.sec_list.curselection()
        if not sel:
            return
        sec = SECTIONS[sel[0]]
        self._current_section = sec
        self.sec_label.set(sec)
        self.editor.delete("1.0", tk.END)
        self.editor.insert(tk.END, self.app.sections.get(sec, ""))
        self._update_wc()

    def persist_current(self):
        if self._current_section:
            self.app.sections[self._current_section] = self.editor.get("1.0", "end-1c")

    def _save_section(self):
        if not self._current_section:
            return
        self.persist_current()
        self.app._save_data()
        self.app.set_status(f"Saved section: {self._current_section}")

    def _update_wc(self, _=None):
        text = self.editor.get("1.0", "end-1c").strip()
        words = len(text.split()) if text else 0
        self.wc_var.set(f"{words} words")

    def _insert_cite(self):
        if not self.app.citations:
            messagebox.showinfo("Info", "No citations saved. Search and save some first.")
            return
        win = tk.Toplevel(self)
        win.title("Insert Citation Reference")
        win.geometry("500x350")
        win.transient(self)

        lb = tk.Listbox(win, font=("TkDefaultFont", 11))
        lb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        for i, c in enumerate(self.app.citations):
            lb.insert(tk.END, f"[{i+1}] {c['authors'][0] if c['authors'] else '?'} ({c['year']}) – {c['title'][:70]}")

        def _insert():
            sel = lb.curselection()
            if not sel:
                return
            idx = sel[0]
            c = self.app.citations[idx]
            ref = f"[{c['authors'][0].split()[0] if c['authors'] else '?'} et al., {c['year']}]"
            self.editor.insert(tk.INSERT, ref)
            win.destroy()

        ttk.Button(win, text="Insert", command=_insert).pack(pady=(0, 8))

    def _export_article(self):
        self.persist_current()
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Markdown", "*.md"), ("All", "*.*")],
        )
        if not path:
            return
        with open(path, "w") as f:
            for sec in SECTIONS:
                text = self.app.sections.get(sec, "").strip()
                if not text or sec == "References":
                    continue
                if sec == "Title":
                    f.write(f"# {text}\n\n")
                else:
                    f.write(f"## {sec}\n\n{text}\n\n")
            # References section: user text + formatted citations
            ref_text = self.app.sections.get("References", "").strip()
            if ref_text or self.app.citations:
                f.write("## References\n\n")
                if ref_text:
                    f.write(ref_text + "\n\n")
                for i, c in enumerate(self.app.citations, 1):
                    f.write(f"{i}. {PubMedClient.format_vancouver(c)}\n\n")
        messagebox.showinfo("Export", f"Article exported to\n{path}")


# ══════════════════════════════════════════════════════════════════════
#  Discover Tab
# ══════════════════════════════════════════════════════════════════════


class DiscoverTab(ttk.Frame):
    def __init__(self, parent, app: PubMedArchitect):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        # ── top: choose source article ──
        top = ttk.LabelFrame(self, text="Find Related Articles")
        top.pack(fill=tk.X, padx=8, pady=8)

        row1 = ttk.Frame(top)
        row1.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(row1, text="Select a saved citation:").pack(side=tk.LEFT)
        self.source_var = tk.StringVar()
        self.source_cb = ttk.Combobox(row1, textvariable=self.source_var, width=80, state="readonly")
        self.source_cb.pack(side=tk.LEFT, padx=6)
        ttk.Button(row1, text="Find Related", command=self._find_related).pack(side=tk.LEFT)
        ttk.Button(row1, text="Refresh list", command=self._refresh_sources).pack(side=tk.LEFT, padx=6)

        # ── middle: results ──
        pw = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        left = ttk.Frame(pw)
        pw.add(left, weight=2)
        ttk.Label(left, text="Related Articles", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.rel_list = tk.Listbox(left, font=("TkDefaultFont", 11))
        rsb = ttk.Scrollbar(left, command=self.rel_list.yview)
        self.rel_list.config(yscrollcommand=rsb.set)
        rsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.rel_list.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.rel_list.bind("<<ListboxSelect>>", self._on_rel_select)

        right = ttk.Frame(pw)
        pw.add(right, weight=3)
        self.rel_detail = tk.Text(right, wrap=tk.WORD, state=tk.DISABLED, font=("TkDefaultFont", 11))
        rdsb = ttk.Scrollbar(right, command=self.rel_detail.yview)
        self.rel_detail.config(yscrollcommand=rdsb.set)
        rdsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.rel_detail.pack(fill=tk.BOTH, expand=True)

        btn_bar = ttk.Frame(right)
        btn_bar.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_bar, text="Add to Citations", command=self._add_rel).pack(side=tk.LEFT, padx=4)

        # ── bottom: keyword analysis ──
        kw_frame = ttk.LabelFrame(self, text="Keyword / MeSH Analysis (across saved citations)")
        kw_frame.pack(fill=tk.X, padx=8, pady=(4, 8))

        kw_row = ttk.Frame(kw_frame)
        kw_row.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(kw_row, text="Analyse Keywords", command=self._analyse_keywords).pack(side=tk.LEFT)
        ttk.Button(kw_row, text="Search Top Keyword", command=self._search_top_kw).pack(
            side=tk.LEFT, padx=6
        )

        self.kw_text = tk.Text(kw_frame, height=5, wrap=tk.WORD, state=tk.DISABLED, font=("TkDefaultFont", 11))
        self.kw_text.pack(fill=tk.X, padx=6, pady=(0, 6))

    def _refresh_sources(self):
        titles = [f'{c["authors"][0].split()[0] if c["authors"] else "?"} ({c["year"]}) – {c["title"][:70]}' for c in self.app.citations]
        self.source_cb["values"] = titles
        if titles:
            self.source_cb.current(0)

    def _find_related(self):
        idx = self.source_cb.current()
        if idx < 0 or idx >= len(self.app.citations):
            messagebox.showinfo("Info", "Select a citation first (click Refresh list).")
            return
        pmid = self.app.citations[idx]["pmid"]
        self.app.set_status(f"Finding articles related to PMID {pmid}…")
        self.rel_list.delete(0, tk.END)

        def _work():
            ids = self.app.client.find_related(pmid)
            return self.app.client.fetch_details(ids)

        def _done(articles, err):
            if err:
                self.app.set_status(f"Error: {err}")
                return
            self.app._discover_results = articles or []
            for i, a in enumerate(self.app._discover_results):
                self.rel_list.insert(tk.END, f"[{i+1}] {a['title'][:100]}")
            self.app.set_status(f"Found {len(self.app._discover_results)} related articles")

        _threaded(_work, lambda r, e: self.app.schedule(_done, r, e))

    def _on_rel_select(self, _=None):
        sel = self.rel_list.curselection()
        if not sel:
            return
        a = self.app._discover_results[sel[0]]
        lines = [
            a["title"], "",
            ", ".join(a["authors"]),
            f'{a["journal"]}  {a["year"]}',
            f'PMID: {a["pmid"]}   DOI: {a["doi"]}',
            "", "── Abstract ──",
            a["abstract"] or "(no abstract)",
        ]
        if a["mesh_terms"]:
            lines += ["", "── MeSH ──", ", ".join(a["mesh_terms"])]
        if a["keywords"]:
            lines += ["", "── Keywords ──", ", ".join(a["keywords"])]
        self.rel_detail.config(state=tk.NORMAL)
        self.rel_detail.delete("1.0", tk.END)
        self.rel_detail.insert(tk.END, "\n".join(lines))
        self.rel_detail.config(state=tk.DISABLED)

    def _add_rel(self):
        sel = self.rel_list.curselection()
        if not sel:
            return
        self.app.add_citation(self.app._discover_results[sel[0]])

    def _analyse_keywords(self):
        if not self.app.citations:
            messagebox.showinfo("Info", "Save some citations first.")
            return
        counter = Counter()
        for c in self.app.citations:
            for t in c.get("mesh_terms", []):
                counter[t] += 1
            for k in c.get("keywords", []):
                counter[k] += 1
        if not counter:
            self._set_kw("No keywords or MeSH terms found in your citations.")
            return
        lines = [f"  {term} ({count})" for term, count in counter.most_common(25)]
        self._set_kw("Top keywords / MeSH terms:\n" + "\n".join(lines))
        self._top_keyword = counter.most_common(1)[0][0] if counter else None

    def _set_kw(self, text):
        self.kw_text.config(state=tk.NORMAL)
        self.kw_text.delete("1.0", tk.END)
        self.kw_text.insert(tk.END, text)
        self.kw_text.config(state=tk.DISABLED)

    def _search_top_kw(self):
        kw = getattr(self, "_top_keyword", None)
        if not kw:
            messagebox.showinfo("Info", "Run keyword analysis first.")
            return
        # Switch to search tab and prefill
        nb = self.master
        nb.select(0)
        self.app.search_tab.query_var.set(kw)
        self.app.search_tab._do_search()


# ══════════════════════════════════════════════════════════════════════
#  Ask Tab — evidence-based question answering
# ══════════════════════════════════════════════════════════════════════


_STAT_RE = re.compile(
    r'(?:p\s*[<=]\s*0\.\d+|\d+\.?\d*\s*%|'
    r'HR\s*[=:]?\s*\d+\.\d+|OR\s*[=:]?\s*\d+\.\d+|'
    r'RR\s*[=:]?\s*\d+\.\d+|CI\s*[=:]?\s*\d+\.\d+[\s\u2013-]+\d+\.\d+|'
    r'n\s*=\s*\d[\d,]*|N\s*=\s*\d[\d,]*|'
    r'\d[\d,]+\s*(?:patients|participants|subjects|samples))',
    re.IGNORECASE,
)

_CONCL_LABELS = {
    'CONCLUSION', 'CONCLUSIONS', 'FINDINGS', 'RESULTS',
    'MAIN RESULTS', 'MAIN OUTCOME', 'MAIN OUTCOMES',
    'INTERPRETATION', 'SIGNIFICANCE', 'SUMMARY',
    'RESULTS AND CONCLUSION', 'RESULTS AND CONCLUSIONS',
    'CONCLUSIONS AND RELEVANCE', 'CONCLUSIONS/SIGNIFICANCE',
}

_STOPWORDS = {
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


def _ask_search(client: PubMedClient, question: str, max_results: int) -> dict:
    """Run the full evidence-synthesis pipeline; returns a plain-text report + source list."""

    q_tokens = set(re.findall(r'\w{3,}', question.lower())) - _STOPWORDS

    # Search + fetch
    pmids, _total = client.search(question, max_results)
    if not pmids:
        return {"report": "No PubMed results for your question.\n\nTry rephrasing or using more specific medical terms.",
                "sources": []}

    articles = client.fetch_details(pmids)
    n = len(articles)

    # --- score & rank ------------------------------------------------
    scored = []
    for a in articles:
        score = 0.0
        title_tok = set(re.findall(r'\w{3,}', a['title'].lower()))
        abs_tok = set(re.findall(r'\w{3,}', a['abstract'].lower()))
        mesh_tok = set(re.findall(r'\w{3,}', ' '.join(a.get('mesh_terms', [])).lower()))
        kw_tok = set(re.findall(r'\w{3,}', ' '.join(a.get('keywords', [])).lower()))
        score += len(q_tokens & title_tok) * 3
        score += len(q_tokens & abs_tok)
        score += len(q_tokens & mesh_tok) * 2
        score += len(q_tokens & kw_tok) * 2
        try:
            if int(a['year']) >= 2020:
                score += 1
        except (ValueError, TypeError):
            pass
        scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)

    # --- extract evidence sentences ----------------------------------
    def _split_sents(text):
        parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        return [s.strip() for s in parts if len(s.strip()) > 20]

    def _sent_rel(sent):
        words = set(re.findall(r'\w{3,}', sent.lower()))
        return len(words & q_tokens) / max(len(q_tokens), 1) if words else 0.0

    lines = []
    lines.append(f"Question: {question}")
    lines.append(f"Sources: {n} articles analysed\n")

    # Key findings
    lines.append("── Key Findings ──")
    seen = set()
    fnum = 0
    for _score, a in scored:
        if fnum >= 8:
            break
        abstract = a['abstract']
        if not abstract:
            continue
        for section in abstract.split('\n'):
            if fnum >= 8:
                break
            m = re.match(r'^([A-Z][A-Z /\-]+):\s*(.+)', section)
            label = m.group(1).strip() if m else ''
            body = m.group(2) if m else section
            is_concl = label.upper() in _CONCL_LABELS
            for sent in _split_sents(body):
                rel = _sent_rel(sent)
                stats = _STAT_RE.findall(sent)
                priority = rel + (0.5 if is_concl else 0) + (0.2 if stats else 0)
                if priority < 0.15:
                    continue
                key = sent[:60].lower()
                if key in seen:
                    continue
                seen.add(key)
                fnum += 1
                first_au = a['authors'][0].split()[0] if a['authors'] else '?'
                cite = f"{first_au} et al., {a['year']}"
                entry = f"{fnum}. {sent}"
                tag_parts = [f"[{cite}]"]
                if stats:
                    tag_parts.append(' | '.join(stats[:3]))
                if label:
                    tag_parts.append(f"[{label}]")
                entry += f"\n   {'  '.join(tag_parts)}"
                lines.append(entry)
                if fnum >= 8:
                    break
    if fnum == 0:
        lines.append("(No strongly relevant conclusion sentences extracted.)")
    lines.append("")

    # Top sources
    lines.append("── Top Sources ──")
    max_sc = scored[0][0] if scored and scored[0][0] > 0 else 1
    for rank, (sc, a) in enumerate(scored[:8], 1):
        pct = round(sc * 100 / max_sc) if max_sc else 0
        auths = ', '.join(a['authors'][:2]) + ('…' if len(a['authors']) > 2 else '')
        ref = f"https://doi.org/{a['doi']}" if a['doi'] else f"PMID {a['pmid']}"
        lines.append(f"#{rank}  (relevance {pct}%)")
        lines.append(f"  {a['title'][:90]}")
        lines.append(f"  {auths}  •  {a['journal']} ({a['year']})")
        lines.append(f"  {ref}")
        lines.append("")

    # Key statistics
    all_stats = []
    for _, a in scored:
        stats = _STAT_RE.findall(a['abstract'])
        if stats:
            first_au = a['authors'][0].split()[0] if a['authors'] else '?'
            cite = f"{first_au} et al., {a['year']}"
            for s in stats[:3]:
                all_stats.append(f"{s}  — {cite} (PMID {a['pmid']})")
    if all_stats:
        lines.append("── Key Statistics ──")
        for s in all_stats[:10]:
            lines.append(f"  • {s}")
        if len(all_stats) > 10:
            lines.append(f"  … and {len(all_stats)-10} more")
        lines.append("")

    report = "\n".join(lines)
    sources = [a for _, a in scored]
    return {"report": report, "sources": sources}


class AskTab(ttk.Frame):
    def __init__(self, parent, app: PubMedArchitect):
        super().__init__(parent)
        self.app = app
        self._ask_sources: list[dict] = []
        self._build()

    def _build(self):
        # ── top bar ──
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(bar, text="Ask PubMed:", font=("TkDefaultFont", 11, "bold")).pack(side=tk.LEFT)
        self.q_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.q_var, width=65)
        entry.pack(side=tk.LEFT, padx=6)
        entry.bind("<Return>", lambda _: self._do_ask())

        ttk.Label(bar, text="Articles:").pack(side=tk.LEFT)
        self.max_var = tk.IntVar(value=60)
        ttk.Spinbox(bar, from_=10, to=200, width=5, textvariable=self.max_var).pack(
            side=tk.LEFT, padx=(2, 8)
        )
        ttk.Button(bar, text="Ask", command=self._do_ask).pack(side=tk.LEFT)

        # ── paned: answer | source detail ──
        pw = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # left: answer report
        left = ttk.Frame(pw)
        pw.add(left, weight=3)
        ttk.Label(left, text="Evidence Report", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.answer_text = tk.Text(left, wrap=tk.WORD, state=tk.DISABLED, font=("TkDefaultFont", 11))
        asb = ttk.Scrollbar(left, command=self.answer_text.yview)
        self.answer_text.config(yscrollcommand=asb.set)
        asb.pack(side=tk.RIGHT, fill=tk.Y)
        self.answer_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # right: source list + detail
        right = ttk.Frame(pw)
        pw.add(right, weight=2)
        ttk.Label(right, text="Source Articles", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.source_list = tk.Listbox(right, font=("TkDefaultFont", 10))
        ssb = ttk.Scrollbar(right, command=self.source_list.yview)
        self.source_list.config(yscrollcommand=ssb.set)
        ssb.pack(side=tk.RIGHT, fill=tk.Y)
        self.source_list.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.source_list.bind("<<ListboxSelect>>", self._on_source_select)

        btn_bar = ttk.Frame(right)
        btn_bar.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_bar, text="Add to Citations", command=self._add_source).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="Open in Browser", command=self._open_source).pack(side=tk.LEFT, padx=4)

    def _do_ask(self):
        q = self.q_var.get().strip()
        if not q:
            return
        self.app.set_status(f'Searching PubMed for evidence: "{q}" …')
        self._set_answer("Searching and analysing PubMed…\nThis may take a few seconds.")
        self.source_list.delete(0, tk.END)

        max_articles = self.max_var.get()

        def _work():
            return _ask_search(self.app.client, q, max_articles)

        def _done(result, err):
            if err:
                self.app.set_status(f"Error: {err}")
                self._set_answer(f"Error: {err}")
                return
            self._set_answer(result["report"])
            self._ask_sources = result["sources"]
            for i, a in enumerate(self._ask_sources):
                self.source_list.insert(tk.END, f"[{i+1}] {a['title'][:90]}")
            self.app.set_status(f"Evidence report ready — {len(self._ask_sources)} sources")

        _threaded(_work, lambda r, e: self.app.schedule(_done, r, e))

    def _set_answer(self, text: str):
        self.answer_text.config(state=tk.NORMAL)
        self.answer_text.delete("1.0", tk.END)
        self.answer_text.insert(tk.END, text)
        self.answer_text.config(state=tk.DISABLED)

    def _on_source_select(self, _=None):
        sel = self.source_list.curselection()
        if not sel:
            return
        a = self._ask_sources[sel[0]]
        lines = [
            a["title"], "",
            ", ".join(a["authors"]),
            f'{a["journal"]}  {a["year"]}  {a["volume"]}({a["issue"]}):{a["pages"]}',
            f'PMID: {a["pmid"]}   DOI: {a["doi"]}',
            "", "── Abstract ──",
            a["abstract"] or "(no abstract)",
        ]
        if a.get("mesh_terms"):
            lines += ["", "── MeSH Terms ──", ", ".join(a["mesh_terms"])]
        if a.get("keywords"):
            lines += ["", "── Keywords ──", ", ".join(a["keywords"])]
        self._set_answer("\n".join(lines))

    def _add_source(self):
        sel = self.source_list.curselection()
        if not sel:
            return
        self.app.add_citation(self._ask_sources[sel[0]])

    def _open_source(self):
        sel = self.source_list.curselection()
        if not sel:
            return
        a = self._ask_sources[sel[0]]
        import webbrowser
        url = (
            f"https://doi.org/{a['doi']}"
            if a["doi"]
            else f"https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/"
        )
        webbrowser.open(url)


# ── entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    app = PubMedArchitect()
    app.mainloop()

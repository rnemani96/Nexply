"""
NEXPLY GUI - Jobs View
Filterable, sortable table of all jobs in the database.
Color-coded by score, source, and status.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from tkinter import ttk, messagebox

import customtkinter as ctk

from gui.theme import *


class JobsView(ctk.CTkFrame):
    """Full jobs table with search, filter, and sort capabilities."""

    COLUMNS = [
        ("Score",    60,  "center"),
        ("Title",    220, "w"),
        ("Company",  140, "w"),
        ("Source",   90,  "center"),
        ("Location", 120, "w"),
        ("Status",   110, "center"),
        ("Rec.",     90,  "center"),
        ("Date",     90,  "center"),
    ]

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=BG_PRIMARY, **kwargs)
        self._all_jobs: list[dict] = []
        self._filtered: list[dict] = []
        self._sort_col: str = "Score"
        self._sort_asc: bool = False
        self._build_ui()
        threading.Thread(target=self.refresh, daemon=True).start()

    # --------------------------------------------------------
    # BUILD UI
    # --------------------------------------------------------

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 0))

        ctk.CTkLabel(
            hdr,
            text="📋  All Jobs",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self._count_lbl = ctk.CTkLabel(
            hdr,
            text="",
            font=ctk.CTkFont(*FONT_SMALL),
            text_color=TEXT_DIM,
        )
        self._count_lbl.pack(side="left", padx=12)

        ctk.CTkButton(
            hdr,
            text="↻ Refresh",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            text_color=ACCENT_PRIMARY,
            border_width=1, border_color=BORDER_ACCENT,
            width=90, height=30,
            command=lambda: threading.Thread(target=self.refresh, daemon=True).start(),
        ).pack(side="right")

        # Filter bar
        filters = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CORNER_RADIUS)
        filters.pack(fill="x", padx=24, pady=12)

        # Search
        ctk.CTkLabel(filters, text="🔍", font=ctk.CTkFont(size=14),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(12, 4), pady=8)
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filters())
        ctk.CTkEntry(
            filters,
            textvariable=self._search_var,
            placeholder_text="Search title, company, skills...",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_INPUT,
            border_color=BORDER_SUBTLE,
            text_color=TEXT_PRIMARY,
            width=260, height=32,
        ).pack(side="left", padx=4, pady=8)

        # Status filter
        ctk.CTkLabel(filters, text="Status:", font=ctk.CTkFont(*FONT_SMALL),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(16, 4))
        self._status_var = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(
            filters,
            values=["All", "NEW", "ANALYZED", "MATCHED", "TAILORED",
                    "APPLIED", "INTERVIEW_SCREEN", "OFFER", "REJECTED", "GHOSTED"],
            variable=self._status_var,
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_INPUT,
            button_color=ACCENT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            width=140, height=32,
            command=lambda _: self._apply_filters(),
        ).pack(side="left", padx=4, pady=8)

        # Source filter
        ctk.CTkLabel(filters, text="Source:", font=ctk.CTkFont(*FONT_SMALL),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(12, 4))
        self._source_var = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(
            filters,
            values=["All", "himalayas", "remoteok", "jobicy", "remotive",
                    "weworkremotely", "aijobs", "linkedin", "naukri"],
            variable=self._source_var,
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_INPUT,
            button_color=ACCENT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            width=140, height=32,
            command=lambda _: self._apply_filters(),
        ).pack(side="left", padx=4, pady=8)

        # Min score slider
        ctk.CTkLabel(filters, text="Min Score:", font=ctk.CTkFont(*FONT_SMALL),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(12, 4))
        self._min_score_var = ctk.IntVar(value=0)
        self._score_lbl = ctk.CTkLabel(filters, text="0",
                                        font=ctk.CTkFont(*FONT_SMALL),
                                        text_color=ACCENT_PRIMARY, width=28)
        self._score_lbl.pack(side="left")

        ctk.CTkSlider(
            filters,
            from_=0, to=100,
            variable=self._min_score_var,
            width=100, height=14,
            fg_color=BG_INPUT,
            progress_color=ACCENT_PRIMARY,
            button_color=ACCENT_PRIMARY,
            command=lambda v: (
                self._score_lbl.configure(text=f"{int(v)}"),
                self._apply_filters(),
            ),
        ).pack(side="left", padx=(4, 10), pady=8)

        # Visa sponsoring filter
        self._visa_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            filters,
            text="🌍 Visa Sponsors Only",
            variable=self._visa_only_var,
            font=ctk.CTkFont(*FONT_SMALL),
            text_color=ACCENT_SECONDARY,
            fg_color=ACCENT_SECONDARY,
            hover_color="#38AF8D",
            checkmark_color="white",
            command=self._apply_filters,
        ).pack(side="left", padx=(0, 16), pady=8)

        # Table frame
        table_outer = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CORNER_RADIUS)
        table_outer.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        self._build_table(table_outer)

    def _build_table(self, parent):
        # Style the ttk Treeview
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Dark.Treeview",
            background=BG_CARD,
            foreground=TEXT_PRIMARY,
            rowheight=36,
            fieldbackground=BG_CARD,
            borderwidth=0,
            font=(FONT_FAMILY, 10),
        )
        style.configure(
            "Dark.Treeview.Heading",
            background=BG_SECONDARY,
            foreground=TEXT_SECONDARY,
            font=(FONT_FAMILY, 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "Dark.Treeview",
            background=[("selected", ACCENT_PRIMARY)],
            foreground=[("selected", "white")],
        )

        cols = [c[0] for c in self.COLUMNS]
        self._tree = ttk.Treeview(
            parent,
            columns=cols,
            show="headings",
            style="Dark.Treeview",
            selectmode="browse",
        )

        for col, width, anchor in self.COLUMNS:
            self._tree.heading(
                col, text=col,
                command=lambda c=col: self._sort_by(c),
            )
            self._tree.column(col, width=width, minwidth=40, anchor=anchor)

        # Color tags
        self._tree.tag_configure("strong", foreground=SCORE_STRONG)
        self._tree.tag_configure("good",   foreground=SCORE_GOOD)
        self._tree.tag_configure("stretch",foreground=SCORE_STRETCH)
        self._tree.tag_configure("skip",   foreground=SCORE_SKIP)
        self._tree.tag_configure("alt",    background=BG_CARD_HOVER)

        # Scrollbars
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Double-click to open URL
        self._tree.bind("<Double-1>", self._on_row_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)

        # Context menu
        self._context_menu = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8)
        self._build_context_menu()

    def _build_context_menu(self):
        self._ctx_items = {}
        for label, cmd in [
            ("🌐  Open in Browser",  self._ctx_open_url),
            ("📝  Tailor Resume",    self._ctx_tailor),
            ("📤  Apply Now",        self._ctx_apply),
            ("❌  Mark Rejected",    self._ctx_reject),
            ("👻  Mark Ghosted",     self._ctx_ghost),
        ]:
            btn = ctk.CTkButton(
                self._context_menu,
                text=label,
                font=ctk.CTkFont(*FONT_SMALL),
                fg_color="transparent",
                hover_color=BG_CARD_HOVER,
                text_color=TEXT_PRIMARY,
                anchor="w",
                height=32,
                command=cmd,
            )
            btn.pack(fill="x", padx=4, pady=1)

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    def refresh(self):
        try:
            from agent.database import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY ai_match_score DESC NULLS LAST, created_at DESC"
            ).fetchall()
            conn.close()
            self._all_jobs = [dict(r) for r in rows]
        except Exception as e:
            self._all_jobs = []

        self.after(0, self._apply_filters)

    def _apply_filters(self, *_):
        query = self._search_var.get().lower()
        status_f = self._status_var.get()
        source_f = self._source_var.get()
        min_score = self._min_score_var.get()
        visa_only = getattr(self, "_visa_only_var", None)
        visa_only = visa_only.get() if visa_only else False

        filtered = []
        for job in self._all_jobs:
            if query and query not in (
                (job.get("title") or "") + (job.get("company") or "") +
                (job.get("skills") or "") + (job.get("description") or "")
            ).lower():
                continue
            if status_f != "All" and job.get("status") != status_f:
                continue
            if source_f != "All" and job.get("source") != source_f:
                continue
            score = job.get("ai_match_score") or 0
            if score < min_score:
                continue
            # Visa filter: check source or description
            if visa_only:
                src = job.get("source", "")
                desc = (job.get("description") or "").lower()
                is_visa = src == "visa_jobs" or any(
                    kw in desc for kw in ["visa sponsor", "h1b", "skilled worker visa",
                                          "work permit", "relocation", "eu blue card"]
                )
                if not is_visa:
                    continue
            filtered.append(job)

        self._filtered = filtered
        self._render_table()
        self._count_lbl.configure(
            text=f"{len(filtered)} / {len(self._all_jobs)} jobs"
        )


    def _render_table(self):
        self._tree.delete(*self._tree.get_children())

        for i, job in enumerate(self._filtered):
            score = job.get("ai_match_score") or 0
            rec = job.get("recommendation", "")
            tag = "strong" if score >= 85 else "good" if score >= 70 else "stretch" if score >= 55 else "skip"
            if i % 2 == 1:
                tag = (tag, "alt")

            date_str = str(job.get("published_at") or job.get("created_at") or "")[:10]
            remote = job.get("remote_type") or job.get("location") or ""

            self._tree.insert(
                "", "end",
                iid=str(job["id"]),
                values=(
                    f"{score:.0f}" if score else "—",
                    str(job.get("title") or "")[:45],
                    str(job.get("company") or "")[:25],
                    str(job.get("source") or ""),
                    remote[:22],
                    str(job.get("status") or ""),
                    str(rec).replace("_", " ").title()[:14],
                    date_str,
                ),
                tags=(tag,) if isinstance(tag, str) else tag,
            )

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = col != "Score"

        key_map = {
            "Score":   lambda j: j.get("ai_match_score") or 0,
            "Title":   lambda j: j.get("title") or "",
            "Company": lambda j: j.get("company") or "",
            "Source":  lambda j: j.get("source") or "",
            "Status":  lambda j: j.get("status") or "",
            "Date":    lambda j: j.get("published_at") or "",
        }
        key = key_map.get(col, lambda j: "")
        self._filtered.sort(key=key, reverse=not self._sort_asc)
        self._render_table()

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

    def _selected_job(self) -> dict | None:
        sel = self._tree.selection()
        if not sel:
            return None
        job_id = int(sel[0])
        return next((j for j in self._filtered if j["id"] == job_id), None)

    def _on_row_double_click(self, event):
        job = self._selected_job()
        if job and job.get("url"):
            webbrowser.open(job["url"])

    def _on_right_click(self, event):
        item = self._tree.identify_row(event.y)
        if item:
            self._tree.selection_set(item)
            self._context_menu.place(x=event.x_root - self.winfo_rootx(),
                                     y=event.y_root - self.winfo_rooty())
            self.after(3000, lambda: self._context_menu.place_forget())

    def _ctx_open_url(self):
        self._context_menu.place_forget()
        job = self._selected_job()
        if job and job.get("url"):
            webbrowser.open(job["url"])

    def _ctx_tailor(self):
        self._context_menu.place_forget()
        job = self._selected_job()
        if not job:
            return
        messagebox.showinfo(
            "Tailor Resume",
            f"Run:\n  python main.py tailor --job-id {job['id']}\n\nOr use the Pipeline tab to tailor in-app.",
        )

    def _ctx_apply(self):
        self._context_menu.place_forget()
        job = self._selected_job()
        if not job:
            return
        import webbrowser
        if job.get("url"):
            webbrowser.open(job["url"])

    def _ctx_reject(self):
        self._context_menu.place_forget()
        job = self._selected_job()
        if job:
            from agent.database import update_job_status
            update_job_status(job["id"], "REJECTED")
            threading.Thread(target=self.refresh, daemon=True).start()

    def _ctx_ghost(self):
        self._context_menu.place_forget()
        job = self._selected_job()
        if job:
            from agent.database import update_job_status
            update_job_status(job["id"], "GHOSTED")
            threading.Thread(target=self.refresh, daemon=True).start()

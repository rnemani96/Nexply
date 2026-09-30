"""
NEXPLY GUI - Application Queue View
Review tailored jobs, preview resume details, approve/skip/blacklist.
"""
from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from gui.theme import *


class ApplyView(ctk.CTkFrame):
    """Application queue — approve, skip, or reject each tailored job."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=BG_PRIMARY, **kwargs)
        self._jobs: list[dict] = []
        self._current_idx: int = 0
        self._build_ui()
        threading.Thread(target=self._load_data, daemon=True).start()

    # --------------------------------------------------------
    # BUILD UI
    # --------------------------------------------------------

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 0))

        ctk.CTkLabel(
            hdr,
            text="📤  Application Queue",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self._queue_count_lbl = ctk.CTkLabel(
            hdr, text="",
            font=ctk.CTkFont(*FONT_SMALL),
            text_color=TEXT_DIM,
        )
        self._queue_count_lbl.pack(side="left", padx=12)

        ctk.CTkButton(
            hdr, text="↻ Refresh",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_CARD, hover_color=BG_CARD_HOVER,
            text_color=ACCENT_PRIMARY,
            border_width=1, border_color=BORDER_ACCENT,
            width=90, height=30,
            command=lambda: threading.Thread(target=self._load_data, daemon=True).start(),
        ).pack(side="right")

        # Main content: left list + right detail
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=12)
        content.columnconfigure(0, weight=0, minsize=320)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        # Left: job queue list
        self._list_frame = ctk.CTkScrollableFrame(
            content,
            fg_color=BG_CARD,
            corner_radius=CORNER_RADIUS,
            scrollbar_button_color=ACCENT_PRIMARY,
        )
        self._list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        ctk.CTkLabel(
            self._list_frame,
            text="Queued Jobs",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            text_color=TEXT_PRIMARY,
        ).pack(padx=12, pady=(12, 6), anchor="w")

        # Right: job detail + actions
        self._detail_frame = ctk.CTkFrame(
            content,
            fg_color=BG_CARD,
            corner_radius=CORNER_RADIUS,
        )
        self._detail_frame.grid(row=0, column=1, sticky="nsew")
        self._build_detail_panel()

    def _build_detail_panel(self):
        # Job title & score
        self._detail_header = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        self._detail_header.pack(fill="x", padx=20, pady=(20, 8))

        self._title_lbl = ctk.CTkLabel(
            self._detail_header,
            text="Select a job from the queue →",
            font=ctk.CTkFont(*FONT_HEADING),
            text_color=TEXT_PRIMARY,
            wraplength=500,
            anchor="w",
            justify="left",
        )
        self._title_lbl.pack(fill="x")

        self._company_lbl = ctk.CTkLabel(
            self._detail_header,
            text="",
            font=ctk.CTkFont(*FONT_BODY),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self._company_lbl.pack(fill="x", pady=(2, 0))

        # Badges row
        self._badges_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        self._badges_row.pack(fill="x", padx=20, pady=6)

        self._score_badge = ctk.CTkLabel(
            self._badges_row,
            text="",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            fg_color=BG_CARD_HOVER,
            corner_radius=6,
            width=70, height=30,
        )
        self._score_badge.pack(side="left", padx=(0, 8))

        self._ats_badge = ctk.CTkLabel(
            self._badges_row,
            text="",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_CARD_HOVER,
            corner_radius=6,
            width=80, height=30,
        )
        self._ats_badge.pack(side="left", padx=(0, 8))

        self._source_badge = ctk.CTkLabel(
            self._badges_row,
            text="",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=ACCENT_PRIMARY,
            text_color="white",
            corner_radius=6,
            width=80, height=30,
        )
        self._source_badge.pack(side="left")

        # Separator
        ctk.CTkFrame(self._detail_frame, height=1, fg_color=BORDER_SUBTLE).pack(fill="x", padx=20)

        # Skills section
        skills_section = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        skills_section.pack(fill="x", padx=20, pady=12)
        skills_section.columnconfigure(0, weight=1)
        skills_section.columnconfigure(1, weight=1)

        self._matched_skills_frame = self._skills_block(skills_section, "✅ Matched Skills", SCORE_STRONG, 0)
        self._missing_skills_frame = self._skills_block(skills_section, "❌ Missing Skills", ACCENT_PINK, 1)

        # Gap analysis
        ctk.CTkLabel(
            self._detail_frame,
            text="AI Recommendation",
            font=ctk.CTkFont(*FONT_SMALL, weight="bold"),
            text_color=TEXT_SECONDARY,
        ).pack(padx=20, pady=(4, 2), anchor="w")

        self._gap_box = ctk.CTkTextbox(
            self._detail_frame,
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_INPUT,
            text_color=TEXT_SECONDARY,
            border_width=0,
            height=80,
            state="disabled",
        )
        self._gap_box.pack(fill="x", padx=20, pady=(0, 12))

        # URL
        self._url_btn = ctk.CTkButton(
            self._detail_frame,
            text="🌐  Open Job Listing",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_CARD_HOVER,
            hover_color=BG_PRIMARY,
            text_color=ACCENT_BLUE,
            border_width=1,
            border_color=ACCENT_BLUE,
            height=34,
            state="disabled",
            command=self._open_url,
        )
        self._url_btn.pack(fill="x", padx=20, pady=(0, 8))

        # Action buttons
        ctk.CTkFrame(self._detail_frame, height=1, fg_color=BORDER_SUBTLE).pack(fill="x", padx=20)

        actions = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=16)
        actions.columnconfigure((0, 1, 2), weight=1)

        self._apply_btn = ctk.CTkButton(
            actions,
            text="📤  Apply Now",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            fg_color=ACCENT_SECONDARY,
            hover_color="#38AF8D",
            text_color="white",
            height=44,
            state="disabled",
            command=self._do_apply,
        )
        self._apply_btn.grid(row=0, column=0, sticky="ew", padx=4)

        self._skip_btn = ctk.CTkButton(
            actions,
            text="⏭  Skip",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            fg_color=BG_CARD_HOVER,
            hover_color=BG_CARD,
            text_color=TEXT_SECONDARY,
            border_width=1,
            border_color=BORDER_SUBTLE,
            height=44,
            state="disabled",
            command=self._do_skip,
        )
        self._skip_btn.grid(row=0, column=1, sticky="ew", padx=4)

        self._reject_btn = ctk.CTkButton(
            actions,
            text="❌  Blacklist",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            fg_color=BG_CARD_HOVER,
            hover_color="#3A1020",
            text_color=ACCENT_PINK,
            border_width=1,
            border_color=ACCENT_PINK,
            height=44,
            state="disabled",
            command=self._do_blacklist,
        )
        self._reject_btn.grid(row=0, column=2, sticky="ew", padx=4)

        # Applied status
        self._applied_lbl = ctk.CTkLabel(
            self._detail_frame,
            text="",
            font=ctk.CTkFont(*FONT_SMALL),
            text_color=SCORE_STRONG,
        )
        self._applied_lbl.pack(pady=(0, 12))

    def _skills_block(self, parent, label: str, color: str, col: int) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkFrame(parent, fg_color=BG_CARD_HOVER, corner_radius=8)
        frame.grid(row=0, column=col, sticky="nsew", padx=4)
        ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(*FONT_SMALL, weight="bold"),
                     text_color=color).pack(padx=8, pady=(8, 4), anchor="w")
        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent",
                                         height=100, scrollbar_button_color=color)
        scroll.pack(fill="both", expand=True, padx=4, pady=(0, 6))
        return scroll

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    def _load_data(self):
        try:
            from agent.database import get_jobs_by_status
            self._jobs = get_jobs_by_status("TAILORED") + get_jobs_by_status("QUEUED")
        except Exception:
            self._jobs = []
        self.after(0, self._render_list)

    def _render_list(self):
        for w in self._list_frame.winfo_children():
            if isinstance(w, ctk.CTkLabel) and "Queued" in (w.cget("text") or ""):
                continue
            if isinstance(w, ctk.CTkLabel):
                continue

        # Clear old cards (except title label)
        children = self._list_frame.winfo_children()
        for c in children[1:]:
            c.destroy()

        self._queue_count_lbl.configure(text=f"{len(self._jobs)} queued")

        if not self._jobs:
            ctk.CTkLabel(
                self._list_frame,
                text="No jobs in queue.\nRun 'Tailor Resumes' first.",
                font=ctk.CTkFont(*FONT_SMALL),
                text_color=TEXT_DIM,
            ).pack(pady=40)
            return

        for i, job in enumerate(self._jobs):
            self._build_list_card(job, i)

    def _build_list_card(self, job: dict, idx: int):
        score = job.get("ai_match_score") or 0
        color = score_color(score)

        card = ctk.CTkFrame(
            self._list_frame,
            fg_color=BG_CARD_HOVER,
            corner_radius=8,
            cursor="hand2",
        )
        card.pack(fill="x", padx=8, pady=3)

        ctk.CTkFrame(card, width=4, fg_color=color, corner_radius=2).pack(side="left", fill="y", padx=(0, 8))

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, pady=6)

        ctk.CTkLabel(
            info,
            text=str(job.get("title", ""))[:30],
            font=ctk.CTkFont(*FONT_SMALL, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            info,
            text=str(job.get("company", ""))[:25],
            font=ctk.CTkFont(*FONT_TINY),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            card,
            text=f"{score:.0f}",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            text_color=color,
        ).pack(side="right", padx=12)

        card.bind("<Button-1>", lambda e, j=job: self._select_job(j))
        for child in card.winfo_children():
            child.bind("<Button-1>", lambda e, j=job: self._select_job(j))

    def _select_job(self, job: dict):
        self._selected_job = job
        self._render_detail(job)

    def _render_detail(self, job: dict):
        import json

        score = job.get("ai_match_score") or 0
        ats = job.get("ats_score") or 0
        color = score_color(score)

        self._title_lbl.configure(text=str(job.get("title", "")))
        self._company_lbl.configure(
            text=f"{job.get('company', '')}  •  {job.get('remote_type') or job.get('location', '')}"
        )

        self._score_badge.configure(
            text=f"Match {score:.0f}",
            fg_color=color,
            text_color="white",
        )
        self._ats_badge.configure(
            text=f"ATS {ats:.0f}" if ats else "ATS —",
            fg_color=score_color(ats) if ats else BG_CARD_HOVER,
            text_color="white",
        )
        src = job.get("source", "")
        self._source_badge.configure(
            text=src,
            fg_color=SOURCE_COLORS.get(src, ACCENT_PRIMARY),
        )

        # Skills
        for w in self._matched_skills_frame.winfo_children():
            w.destroy()
        for w in self._missing_skills_frame.winfo_children():
            w.destroy()

        try:
            matched = json.loads(job.get("matched_skills") or "[]")
            missing = json.loads(job.get("missing_skills") or "[]")
        except Exception:
            matched, missing = [], []

        for skill in matched[:12]:
            ctk.CTkLabel(
                self._matched_skills_frame,
                text=f"• {skill}",
                font=ctk.CTkFont(*FONT_TINY),
                text_color=SCORE_STRONG,
                anchor="w",
            ).pack(fill="x")

        for skill in missing[:12]:
            ctk.CTkLabel(
                self._missing_skills_frame,
                text=f"• {skill}",
                font=ctk.CTkFont(*FONT_TINY),
                text_color=ACCENT_PINK,
                anchor="w",
            ).pack(fill="x")

        # Gap analysis
        gap = job.get("gap_analysis") or job.get("recommendation") or "No analysis yet."
        self._gap_box.configure(state="normal")
        self._gap_box.delete("1.0", "end")
        self._gap_box.insert("1.0", gap)
        self._gap_box.configure(state="disabled")

        # URL
        url = job.get("url", "")
        self._url_btn.configure(
            state="normal" if url else "disabled",
            command=lambda: webbrowser.open(url) if url else None,
        )

        # Enable action buttons
        for btn in [self._apply_btn, self._skip_btn, self._reject_btn]:
            btn.configure(state="normal")

        self._applied_lbl.configure(text="")

    # --------------------------------------------------------
    # ACTIONS
    # --------------------------------------------------------

    def _do_apply(self):
        job = getattr(self, "_selected_job", None)
        if not job:
            return

        resume_path = Path(job.get("resume_path") or "")
        if not resume_path.exists():
            messagebox.showwarning(
                "Resume Missing",
                f"Resume not found at:\n{resume_path}\n\nRun 'Tailor Resumes' in the Pipeline tab first.",
            )
            return

        url = job.get("url", "")
        if url:
            webbrowser.open(url)

        # Mark as applied in DB
        from agent.database import update_job_status, add_application
        add_application(
            job_id=job["id"],
            platform=job.get("source", "manual"),
            resume_path=str(resume_path),
            ats_score=job.get("ats_score") or 0,
            submission_method="browser_manual",
        )
        self._applied_lbl.configure(
            text="✅  Marked as Applied! Browser opened.",
            text_color=SCORE_STRONG,
        )
        for btn in [self._apply_btn, self._skip_btn, self._reject_btn]:
            btn.configure(state="disabled")

        threading.Thread(target=self._load_data, daemon=True).start()

    def _do_skip(self):
        job = getattr(self, "_selected_job", None)
        if not job:
            return
        from agent.database import update_job_status
        update_job_status(job["id"], "WITHDRAWN", notes="Skipped from GUI")
        self._applied_lbl.configure(text="Job skipped.", text_color=TEXT_DIM)
        threading.Thread(target=self._load_data, daemon=True).start()

    def _do_blacklist(self):
        job = getattr(self, "_selected_job", None)
        if not job:
            return
        if messagebox.askyesno("Blacklist", f"Blacklist {job.get('company')}? All future jobs from this company will be skipped."):
            from agent.database import update_job_status
            update_job_status(job["id"], "WITHDRAWN", notes=f"Blacklisted: {job.get('company')}")
            self._applied_lbl.configure(text="Company blacklisted.", text_color=ACCENT_PINK)
            threading.Thread(target=self._load_data, daemon=True).start()

    def _open_url(self):
        job = getattr(self, "_selected_job", None)
        if job and job.get("url"):
            webbrowser.open(job["url"])

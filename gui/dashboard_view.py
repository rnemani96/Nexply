"""
RAJESH AI GUI - Dashboard View
Beautiful stats cards, pipeline funnel chart, and top matches table.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime

import customtkinter as ctk
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from gui.theme import *


class DashboardView(ctk.CTkFrame):
    """Main dashboard with stats cards, funnel chart, and live matches table."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=BG_PRIMARY, **kwargs)
        self._jobs_data: list[dict] = []
        self._stats: dict = {}
        self._build_ui()
        self.refresh()

    # --------------------------------------------------------
    # UI CONSTRUCTION
    # --------------------------------------------------------

    def _build_ui(self):
        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 0))

        ctk.CTkLabel(
            header,
            text="🚀 Dashboard",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self._last_updated_lbl = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(*FONT_TINY),
            text_color=TEXT_DIM,
        )
        self._last_updated_lbl.pack(side="right", padx=8)

        ctk.CTkButton(
            header,
            text="↻  Refresh",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            text_color=ACCENT_PRIMARY,
            border_width=1,
            border_color=BORDER_ACCENT,
            width=100,
            height=30,
            command=lambda: threading.Thread(target=self.refresh, daemon=True).start(),
        ).pack(side="right")

        # Stats cards row
        self._cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._cards_frame.pack(fill="x", padx=24, pady=16)

        # Middle: chart + top matches
        middle = ctk.CTkFrame(self, fg_color="transparent")
        middle.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, weight=2)
        middle.rowconfigure(0, weight=1)

        # Left: funnel chart
        self._chart_frame = ctk.CTkFrame(
            middle,
            fg_color=BG_CARD,
            corner_radius=CORNER_RADIUS,
        )
        self._chart_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Right: top matches
        self._matches_frame = ctk.CTkFrame(
            middle,
            fg_color=BG_CARD,
            corner_radius=CORNER_RADIUS,
        )
        self._matches_frame.grid(row=0, column=1, sticky="nsew")

        self._build_matches_header()

    def _build_matches_header(self):
        hdr = ctk.CTkFrame(self._matches_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 8))

        ctk.CTkLabel(
            hdr,
            text="🎯  Top Matches",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self._matches_count_lbl = ctk.CTkLabel(
            hdr,
            text="",
            font=ctk.CTkFont(*FONT_TINY),
            text_color=TEXT_DIM,
        )
        self._matches_count_lbl.pack(side="right")

        # Scrollable matches list
        self._matches_scroll = ctk.CTkScrollableFrame(
            self._matches_frame,
            fg_color="transparent",
            scrollbar_button_color=ACCENT_PRIMARY,
        )
        self._matches_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # --------------------------------------------------------
    # DATA REFRESH
    # --------------------------------------------------------

    def refresh(self):
        """Load data from DB and re-render all panels."""
        try:
            from agent.database import get_pipeline_stats, get_top_matches, get_job_count
            self._stats = get_pipeline_stats()
            self._jobs_data = get_top_matches(min_score=55, limit=20)
            total = get_job_count()
        except Exception as e:
            self._stats = {}
            self._jobs_data = []
            total = 0

        # Update UI on main thread
        self.after(0, lambda: self._render(total))

    def _render(self, total: int):
        self._render_stat_cards(total)
        self._render_funnel_chart()
        self._render_top_matches()
        self._last_updated_lbl.configure(
            text=f"Updated {datetime.now().strftime('%H:%M:%S')}"
        )

    # --------------------------------------------------------
    # STAT CARDS
    # --------------------------------------------------------

    def _render_stat_cards(self, total: int):
        for w in self._cards_frame.winfo_children():
            w.destroy()

        applied = (
            self._stats.get("APPLIED", 0)
            + self._stats.get("INTERVIEW_SCREEN", 0)
            + self._stats.get("INTERVIEW_TECH", 0)
            + self._stats.get("OFFER", 0)
            + self._stats.get("ACCEPTED", 0)
        )
        interviews = (
            self._stats.get("INTERVIEW_SCREEN", 0)
            + self._stats.get("INTERVIEW_TECH", 0)
        )
        offers = self._stats.get("OFFER", 0) + self._stats.get("ACCEPTED", 0)
        matched = self._stats.get("MATCHED", 0) + self._stats.get("TAILORED", 0)

        cards = [
            ("📥", "Total Jobs",    str(total),    ACCENT_BLUE),
            ("🎯", "Matched",       str(matched),  ACCENT_PRIMARY),
            ("📤", "Applied",       str(applied),  ACCENT_SECONDARY),
            ("📞", "Interviews",    str(interviews),SCORE_STRETCH),
            ("🏆", "Offers",        str(offers),   SCORE_STRONG),
        ]

        for i, (icon, label, value, color) in enumerate(cards):
            self._cards_frame.columnconfigure(i, weight=1)
            card = ctk.CTkFrame(
                self._cards_frame,
                fg_color=BG_CARD,
                corner_radius=CORNER_RADIUS,
                border_width=1,
                border_color=BORDER_SUBTLE,
            )
            card.grid(row=0, column=i, sticky="ew", padx=6, ipady=12)

            ctk.CTkLabel(
                card, text=icon,
                font=ctk.CTkFont(size=26),
            ).pack(pady=(12, 2))

            ctk.CTkLabel(
                card, text=value,
                font=ctk.CTkFont(*FONT_HEADING),
                text_color=color,
            ).pack()

            ctk.CTkLabel(
                card, text=label,
                font=ctk.CTkFont(*FONT_TINY),
                text_color=TEXT_SECONDARY,
            ).pack(pady=(0, 12))

    # --------------------------------------------------------
    # FUNNEL CHART
    # --------------------------------------------------------

    def _render_funnel_chart(self):
        for w in self._chart_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._chart_frame,
            text="📊  Pipeline Funnel",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            text_color=TEXT_PRIMARY,
        ).pack(padx=16, pady=(14, 4), anchor="w")

        stages = [
            ("NEW",             ">>", "#4E9FFF"),
            ("ANALYZED",        "AI", "#8080D0"),
            ("MATCHED",         "~~", "#6C63FF"),
            ("TAILORED",        "CV", "#F9CA56"),
            ("APPLIED",         "->", "#48CFAD"),
            ("INTERVIEW",       "PH", "#FF9A56"),
            ("OFFER",           "**", "#FF6584"),
            ("ACCEPTED",        "OK", "#48CFAD"),
        ]

        fig = Figure(figsize=(3.8, 5.2), facecolor=BG_CARD)
        ax = fig.add_subplot(111, facecolor=BG_CARD)
        fig.subplots_adjust(left=0.02, right=0.98, top=0.96, bottom=0.02)

        max_val = max((self._stats.get(s, 0) for s, _, _ in stages), default=1) or 1

        for i, (stage, icon, color) in enumerate(stages):
            count = self._stats.get(stage, 0)
            bar_width = max(0.12, (count / max_val) * 0.85)
            y = len(stages) - i - 1

            # Bar
            bar = mpatches.FancyBboxPatch(
                ((1 - bar_width) / 2, y + 0.05),
                bar_width, 0.82,
                boxstyle="round,pad=0.02",
                facecolor=color,
                alpha=0.85,
                transform=ax.transData,
            )
            ax.add_patch(bar)

            # Label
            ax.text(
                0.5, y + 0.46,
                f"{icon}  {stage}   {count}",
                ha="center", va="center",
                fontsize=8, color="white", fontweight="bold",
            )

        ax.set_xlim(0, 1)
        ax.set_ylim(-0.1, len(stages))
        ax.axis("off")

        canvas = FigureCanvasTkAgg(fig, master=self._chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # --------------------------------------------------------
    # TOP MATCHES LIST
    # --------------------------------------------------------

    def _render_top_matches(self):
        for w in self._matches_scroll.winfo_children():
            w.destroy()

        self._matches_count_lbl.configure(
            text=f"{len(self._jobs_data)} jobs"
        )

        if not self._jobs_data:
            ctk.CTkLabel(
                self._matches_scroll,
                text="No matches yet.\nRun the pipeline to find jobs.",
                font=ctk.CTkFont(*FONT_BODY),
                text_color=TEXT_DIM,
            ).pack(pady=40)
            return

        for job in self._jobs_data:
            self._build_match_row(job)

    def _build_match_row(self, job: dict):
        score = job.get("ai_match_score") or 0
        rec = job.get("recommendation", "")
        color = score_color(score)
        source = job.get("source", "")
        src_color = SOURCE_COLORS.get(source, ACCENT_PRIMARY)

        row = ctk.CTkFrame(
            self._matches_scroll,
            fg_color=BG_CARD_HOVER,
            corner_radius=8,
        )
        row.pack(fill="x", pady=3)

        # Score badge
        badge = ctk.CTkFrame(row, fg_color=color, corner_radius=6, width=48, height=42)
        badge.pack_propagate(False)
        badge.pack(side="left", padx=(8, 10), pady=6)
        ctk.CTkLabel(
            badge, text=f"{score:.0f}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color="white",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Job info
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        title_row = ctk.CTkFrame(info, fg_color="transparent")
        title_row.pack(fill="x")

        ctk.CTkLabel(
            title_row,
            text=str(job.get("title", ""))[:38],
            font=ctk.CTkFont(*FONT_SUBHEAD),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).pack(side="left")

        # Source pill
        pill = ctk.CTkLabel(
            title_row,
            text=f" {source} ",
            font=ctk.CTkFont(*FONT_TINY),
            fg_color=src_color,
            text_color="white",
            corner_radius=4,
        )
        pill.pack(side="left", padx=6)

        company_loc = ctk.CTkFrame(info, fg_color="transparent")
        company_loc.pack(fill="x")

        loc_fmt = job.get("jd_location_format", "")
        remote = job.get("remote_type", "")
        loc_text = f"{job.get('company', '')}  •  {remote or loc_fmt or 'Remote'}"

        ctk.CTkLabel(
            company_loc,
            text=loc_text[:45],
            font=ctk.CTkFont(*FONT_TINY),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(side="left")

        # Right actions
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="right", padx=8, pady=6)

        status = job.get("status", "")
        s_fg, s_bg = STATUS_COLORS.get(status, (TEXT_DIM, BG_CARD))
        ctk.CTkLabel(
            actions,
            text=status,
            font=ctk.CTkFont(*FONT_TINY),
            fg_color=s_bg,
            text_color=s_fg,
            corner_radius=4,
        ).pack(pady=(0, 2))

        ctk.CTkLabel(
            actions,
            text=score_label(score),
            font=ctk.CTkFont(*FONT_TINY),
            text_color=color,
        ).pack()

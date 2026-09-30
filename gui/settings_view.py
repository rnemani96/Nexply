"""
NEXPLY GUI - Settings View
Live-editable configuration panel for all settings.
Changes are saved immediately to config/settings.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path

import customtkinter as ctk
import yaml
from tkinter import messagebox

from gui.theme import *

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "settings.yaml"


def _load() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


class SettingsView(ctk.CTkScrollableFrame):
    """Full settings editor with live save."""

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=BG_PRIMARY,
            scrollbar_button_color=ACCENT_PRIMARY,
            **kwargs,
        )
        self._cfg = _load()
        self._vars: dict = {}
        self._build_ui()

    # --------------------------------------------------------
    # MAIN UI
    # --------------------------------------------------------

    def _build_ui(self):
        ctk.CTkLabel(
            self,
            text="⚙️  Settings",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=TEXT_PRIMARY,
        ).pack(padx=24, pady=(20, 4), anchor="w")

        ctk.CTkLabel(
            self,
            text="Changes are saved to config/settings.yaml",
            font=ctk.CTkFont(*FONT_SMALL),
            text_color=TEXT_DIM,
        ).pack(padx=24, pady=(0, 16), anchor="w")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=24, pady=0)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        # Left column
        left = ctk.CTkFrame(grid, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw", padx=(0, 10))

        self._section_ai(left)
        self._section_sources(left)

        # Right column
        right = ctk.CTkFrame(grid, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nw")

        self._section_candidate(right)
        self._section_application(right)
        self._section_scheduler(right)

        # Save button
        ctk.CTkButton(
            self,
            text="💾  Save All Settings",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            fg_color=ACCENT_PRIMARY,
            hover_color="#5550DD",
            text_color="white",
            height=44,
            command=self._save_all,
        ).pack(padx=24, pady=(20, 4), fill="x")

        ctk.CTkButton(
            self,
            text="🔄  Reload from File",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            text_color=TEXT_SECONDARY,
            border_width=1,
            border_color=BORDER_SUBTLE,
            height=34,
            command=self._reload,
        ).pack(padx=24, pady=(0, 24), fill="x")

    # --------------------------------------------------------
    # SECTION: AI PROVIDER
    # --------------------------------------------------------

    def _section_ai(self, parent):
        box = self._card(parent, "🤖  AI Provider")

        self._radio(
            box, "provider", "Primary Provider",
            ["gemini", "ollama", "lmstudio"],
            self._cfg.get("ai", {}).get("provider", "ollama"),
        )

        self._separator(box)
        ctk.CTkLabel(box, text="Gemini Models", font=ctk.CTkFont(*FONT_SMALL, weight="bold"),
                     text_color=TEXT_SECONDARY).pack(anchor="w", padx=4, pady=(6, 2))
        self._entry(box, "gemini_jd_model", "JD Analysis Model",
                    self._cfg.get("ai", {}).get("gemini", {}).get("jd_analysis_model", "gemini-3.8-flash"))
        self._entry(box, "gemini_resume_model", "Resume Model",
                    self._cfg.get("ai", {}).get("gemini", {}).get("resume_model", "gemini-3.1-pro-preview"))

        self._separator(box)
        ctk.CTkLabel(box, text="Ollama (Local)", font=ctk.CTkFont(*FONT_SMALL, weight="bold"),
                     text_color=TEXT_SECONDARY).pack(anchor="w", padx=4, pady=(6, 2))
        self._entry(box, "ollama_url", "Base URL",
                    self._cfg.get("ai", {}).get("ollama", {}).get("base_url", "http://localhost:11434"))
        self._entry(box, "ollama_model", "Model",
                    self._cfg.get("ai", {}).get("ollama", {}).get("jd_analysis_model", "llama3.1"))

        self._separator(box)
        ctk.CTkLabel(box, text="LM Studio (Local)", font=ctk.CTkFont(*FONT_SMALL, weight="bold"),
                     text_color=TEXT_SECONDARY).pack(anchor="w", padx=4, pady=(6, 2))
        self._entry(box, "lmstudio_url", "Base URL",
                    self._cfg.get("ai", {}).get("lmstudio", {}).get("base_url", "http://localhost:1234/v1"))
        self._entry(box, "lmstudio_model", "Model Name",
                    self._cfg.get("ai", {}).get("lmstudio", {}).get("jd_analysis_model", "local-model"))

        # Test AI button
        ctk.CTkButton(
            box,
            text="🧪  Test AI Connection",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=ACCENT_BLUE,
            hover_color="#3A7FDD",
            text_color="white",
            height=32,
            command=self._test_ai,
        ).pack(fill="x", padx=4, pady=(10, 4))

    # --------------------------------------------------------
    # SECTION: JOB SOURCES
    # --------------------------------------------------------

    def _section_sources(self, parent):
        box = self._card(parent, "🌐  Job Sources")

        sources = [
            ("himalayas",       "Himalayas.app",     "Free API, worldwide remote"),
            ("remoteok",        "RemoteOK",           "Free API, worldwide remote"),
            ("jobicy",          "Jobicy",              "Free API, categorized"),
            ("remotive",        "Remotive",            "Free API, multiple categories"),
            ("weworkremotely",  "We Work Remotely",   "RSS feed, no auth"),
            ("aijobs",          "AI-Jobs.net",         "RSS feed, AI/ML specialist"),
            ("remotefirstjobs", "Remote First Jobs",  "Free API"),
            ("linkedin",        "LinkedIn",            "Requires li_at session cookie"),
            ("naukri",          "Naukri (India)",      "India-focused jobs"),
            ("wellfound",       "Wellfound",           "Startup jobs"),
        ]

        for src_key, label, tip in sources:
            src_cfg = self._cfg.get("sources", {}).get(src_key, {})
            enabled = src_cfg.get("enabled", False)
            var = ctk.BooleanVar(value=enabled)
            self._vars[f"src_{src_key}"] = var

            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkCheckBox(
                row,
                text=label,
                variable=var,
                font=ctk.CTkFont(*FONT_SMALL),
                text_color=TEXT_PRIMARY,
                fg_color=ACCENT_PRIMARY,
                hover_color=ACCENT_PRIMARY,
                checkmark_color="white",
            ).pack(side="left")

            ctk.CTkLabel(
                row,
                text=tip,
                font=ctk.CTkFont(*FONT_TINY),
                text_color=TEXT_DIM,
            ).pack(side="left", padx=8)

        self._separator(box)
        self._slider(
            box, "max_jobs_per_run",
            "Max Jobs Per Run", 50, 500,
            self._cfg.get("search", {}).get("max_jobs_per_run", 500),
        )
        self._slider(
            box, "min_match_score",
            "Min Match Score", 40, 90,
            self._cfg.get("search", {}).get("min_match_score", 60),
        )

    # --------------------------------------------------------
    # SECTION: CANDIDATE
    # --------------------------------------------------------

    def _section_candidate(self, parent):
        box = self._card(parent, "👤  Candidate Profile")

        self._entry(box, "candidate_name", "Your Name",
                    self._cfg.get("candidate", {}).get("name", "Rajesh"))

        self._entry(box, "experience_years", "Years of Experience",
                    str(self._cfg.get("candidate", {}).get("experience_years", 6)))

        self._entry(box, "resume_format", "Resume Format (auto/india/us/uk/eu)",
                    self._cfg.get("candidate", {}).get("resume_format", "auto"))

        # Prefer worldwide toggle
        pref_worldwide = self._cfg.get("candidate", {}).get("prefer_worldwide", True)
        var = ctk.BooleanVar(value=pref_worldwide)
        self._vars["prefer_worldwide"] = var
        ctk.CTkCheckBox(
            box,
            text="Prefer Worldwide Openings (bonus score)",
            variable=var,
            font=ctk.CTkFont(*FONT_SMALL),
            text_color=TEXT_PRIMARY,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_PRIMARY,
            checkmark_color="white",
        ).pack(anchor="w", padx=4, pady=6)

        self._separator(box)
        ctk.CTkLabel(box, text="Target Roles (one per line)",
                     font=ctk.CTkFont(*FONT_SMALL, weight="bold"),
                     text_color=TEXT_SECONDARY).pack(anchor="w", padx=4, pady=(4, 2))

        roles = self._cfg.get("candidate", {}).get("roles", [])
        self._textbox(box, "roles", "\n".join(roles), height=180)

        self._separator(box)
        ctk.CTkLabel(box, text="Locations (one per line)",
                     font=ctk.CTkFont(*FONT_SMALL, weight="bold"),
                     text_color=TEXT_SECONDARY).pack(anchor="w", padx=4, pady=(4, 2))

        locs = self._cfg.get("candidate", {}).get("locations", [])
        self._textbox(box, "locations", "\n".join(locs), height=80)

    # --------------------------------------------------------
    # SECTION: APPLICATION
    # --------------------------------------------------------

    def _section_application(self, parent):
        box = self._card(parent, "📤  Application Settings")

        self._radio(
            box, "app_mode", "Application Mode",
            ["human_approval", "auto"],
            self._cfg.get("application", {}).get("mode", "human_approval"),
        )

        self._slider(
            box, "auto_apply_score",
            "Auto-Apply Score Threshold", 60, 100,
            self._cfg.get("application", {}).get("auto_apply_score", 85),
        )

        self._slider(
            box, "follow_up_days",
            "Follow-up After (days)", 1, 30,
            self._cfg.get("application", {}).get("follow_up_days", 7),
        )

        self._slider(
            box, "min_ats_score",
            "Min ATS Score to Apply", 50, 100,
            self._cfg.get("ats", {}).get("min_ats_score", 75),
        )

        self._slider(
            box, "top_matches_per_day",
            "Max Resumes Per Day", 5, 50,
            self._cfg.get("search", {}).get("top_matches_per_day", 20),
        )

        self._separator(box)

        # ── Location Filter ─────────────────────────────────────────────
        ctk.CTkLabel(
            box,
            text="🌍  Location Filter",
            font=ctk.CTkFont(*FONT_SMALL, weight="bold"),
            text_color=ACCENT_SECONDARY,
        ).pack(anchor="w", padx=4, pady=(4, 2))

        filter_on = self._cfg.get("filter", {}).get("foreign_without_sponsorship", True)
        self._vars["filter_foreign"] = ctk.BooleanVar(value=filter_on)
        ctk.CTkCheckBox(
            box,
            text="Discard foreign-country jobs without visa sponsorship",
            variable=self._vars["filter_foreign"],
            font=ctk.CTkFont(*FONT_SMALL),
            text_color=TEXT_PRIMARY,
            fg_color=ACCENT_SECONDARY,
            hover_color="#38AF8D",
            checkmark_color="white",
        ).pack(anchor="w", padx=4, pady=4)

        ctk.CTkLabel(
            box,
            text="India jobs + Remote/Worldwide jobs are always kept.",
            font=ctk.CTkFont(*FONT_TINY),
            text_color=TEXT_DIM,
        ).pack(anchor="w", padx=22, pady=(0, 6))

        self._entry(
            box, "home_country", "Home Country (always kept)",
            self._cfg.get("candidate", {}).get("home_country", "India"),
        )

    # --------------------------------------------------------
    # SECTION: SCHEDULER
    # --------------------------------------------------------

    def _section_scheduler(self, parent):
        box = self._card(parent, "⏰  Scheduler")

        self._entry(box, "hunt_time", "Daily Hunt Time (HH:MM)",
                    self._cfg.get("scheduler", {}).get("daily_hunt_time", "08:00"))
        self._entry(box, "followup_time", "Follow-up Check Time (HH:MM)",
                    self._cfg.get("scheduler", {}).get("follow_up_check_time", "17:00"))

        ctk.CTkButton(
            box,
            text="📅  Install Windows Task Scheduler",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=ACCENT_SECONDARY,
            hover_color="#38AF8D",
            text_color="white",
            height=32,
            command=self._install_scheduler,
        ).pack(fill="x", padx=4, pady=(10, 4))

    # --------------------------------------------------------
    # WIDGET HELPERS
    # --------------------------------------------------------

    def _card(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            corner_radius=CORNER_RADIUS,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        card.pack(fill="x", pady=8)
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(*FONT_SUBHEAD),
            text_color=ACCENT_PRIMARY,
        ).pack(padx=16, pady=(14, 8), anchor="w")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 14))
        return inner

    def _entry(self, parent, key: str, label: str, value: str):
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(*FONT_TINY),
                     text_color=TEXT_SECONDARY).pack(anchor="w", padx=4, pady=(4, 0))
        var = ctk.StringVar(value=str(value))
        self._vars[key] = var
        ctk.CTkEntry(
            parent,
            textvariable=var,
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_INPUT,
            border_color=BORDER_SUBTLE,
            text_color=TEXT_PRIMARY,
            height=INPUT_HEIGHT,
        ).pack(fill="x", padx=4, pady=(0, 4))

    def _textbox(self, parent, key: str, value: str, height: int = 100):
        tb = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=BG_INPUT,
            border_color=BORDER_SUBTLE,
            border_width=1,
            text_color=TEXT_PRIMARY,
            height=height,
        )
        tb.insert("1.0", value)
        tb.pack(fill="x", padx=4, pady=(0, 4))
        self._vars[key] = tb

    def _slider(self, parent, key: str, label: str, from_: int, to: int, value: int):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=3)
        lbl = ctk.CTkLabel(row, text=f"{label}: ", font=ctk.CTkFont(*FONT_SMALL),
                            text_color=TEXT_SECONDARY)
        lbl.pack(side="left")
        val_lbl = ctk.CTkLabel(row, text=str(int(value)), font=ctk.CTkFont(*FONT_SMALL),
                                text_color=ACCENT_PRIMARY, width=40)
        val_lbl.pack(side="right")
        var = ctk.IntVar(value=int(value))
        self._vars[key] = var
        ctk.CTkSlider(
            parent, from_=from_, to=to,
            variable=var,
            fg_color=BG_INPUT,
            progress_color=ACCENT_PRIMARY,
            button_color=ACCENT_PRIMARY,
            height=14,
            command=lambda v, l=val_lbl: l.configure(text=str(int(v))),
        ).pack(fill="x", padx=4, pady=(0, 4))

    def _radio(self, parent, key: str, label: str, options: list[str], value: str):
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(*FONT_SMALL),
                     text_color=TEXT_SECONDARY).pack(anchor="w", padx=4, pady=(4, 2))
        var = ctk.StringVar(value=value)
        self._vars[key] = var
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=(0, 6))
        for opt in options:
            ctk.CTkRadioButton(
                row, text=opt, variable=var, value=opt,
                font=ctk.CTkFont(*FONT_SMALL),
                text_color=TEXT_PRIMARY,
                fg_color=ACCENT_PRIMARY,
                hover_color=ACCENT_PRIMARY,
            ).pack(side="left", padx=8)

    def _separator(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color=BORDER_SUBTLE).pack(fill="x", padx=4, pady=8)

    # --------------------------------------------------------
    # SAVE / LOAD
    # --------------------------------------------------------

    def _save_all(self):
        try:
            cfg = _load()

            # AI
            cfg.setdefault("ai", {})
            cfg["ai"]["provider"] = self._vars["provider"].get()
            cfg["ai"].setdefault("gemini", {})["jd_analysis_model"] = self._vars["gemini_jd_model"].get()
            cfg["ai"].setdefault("gemini", {})["resume_model"]       = self._vars["gemini_resume_model"].get()
            cfg["ai"].setdefault("ollama", {})["base_url"]           = self._vars["ollama_url"].get()
            cfg["ai"].setdefault("ollama", {})["jd_analysis_model"]  = self._vars["ollama_model"].get()
            cfg["ai"].setdefault("lmstudio", {})["base_url"]         = self._vars["lmstudio_url"].get()
            cfg["ai"].setdefault("lmstudio", {})["jd_analysis_model"]= self._vars["lmstudio_model"].get()

            # Sources enables
            cfg.setdefault("sources", {})
            for src in ["himalayas", "remoteok", "jobicy", "remotive", "weworkremotely",
                        "aijobs", "remotefirstjobs", "linkedin", "naukri", "wellfound"]:
                cfg["sources"].setdefault(src, {})["enabled"] = self._vars[f"src_{src}"].get()

            # Search
            cfg.setdefault("search", {})
            cfg["search"]["max_jobs_per_run"]   = int(self._vars["max_jobs_per_run"].get())
            cfg["search"]["min_match_score"]     = int(self._vars["min_match_score"].get())
            cfg["search"]["top_matches_per_day"] = int(self._vars["top_matches_per_day"].get())

            # Candidate
            cfg.setdefault("candidate", {})
            cfg["candidate"]["name"]            = self._vars["candidate_name"].get()
            cfg["candidate"]["experience_years"]= int(self._vars["experience_years"].get())
            cfg["candidate"]["resume_format"]   = self._vars["resume_format"].get()
            cfg["candidate"]["prefer_worldwide"]= self._vars["prefer_worldwide"].get()
            cfg["candidate"]["roles"] = [
                r.strip() for r in self._vars["roles"].get("1.0", "end").strip().splitlines() if r.strip()
            ]
            cfg["candidate"]["locations"] = [
                l.strip() for l in self._vars["locations"].get("1.0", "end").strip().splitlines() if l.strip()
            ]

            # Application
            cfg.setdefault("application", {})
            cfg["application"]["mode"]            = self._vars["app_mode"].get()
            cfg["application"]["auto_apply_score"]= int(self._vars["auto_apply_score"].get())
            cfg["application"]["follow_up_days"]  = int(self._vars["follow_up_days"].get())
            cfg.setdefault("ats", {})["min_ats_score"] = int(self._vars["min_ats_score"].get())

            # Location filter
            cfg.setdefault("filter", {})["foreign_without_sponsorship"] = self._vars["filter_foreign"].get()
            cfg.setdefault("candidate", {})["home_country"] = self._vars["home_country"].get()

            # Scheduler
            cfg.setdefault("scheduler", {})
            cfg["scheduler"]["daily_hunt_time"]      = self._vars["hunt_time"].get()
            cfg["scheduler"]["follow_up_check_time"] = self._vars["followup_time"].get()

            _save(cfg)
            messagebox.showinfo("Saved", "Settings saved to config/settings.yaml ✅")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _reload(self):
        self._cfg = _load()
        for w in self.winfo_children():
            w.destroy()
        self._vars.clear()
        self._build_ui()

    def _test_ai(self):
        from tkinter import messagebox
        try:
            from agent.ai_engine import get_ai_engine
            engine = get_ai_engine()
            status = engine.status()
            active = engine.active_provider_name()
            lines = [f"Active: {active}\n"]
            for name, ok in status.items():
                lines.append(f"{'✅' if ok else '❌'}  {name}: {'READY' if ok else 'OFFLINE'}")
            messagebox.showinfo("AI Status", "\n".join(lines))
        except Exception as e:
            messagebox.showerror("AI Test Error", str(e))

    def _install_scheduler(self):
        from tkinter import messagebox
        import subprocess, sys
        PYTHON = sys.executable
        SCHEDULER = str(BASE_DIR / "agent" / "scheduler.py")
        result = subprocess.run(
            [PYTHON, SCHEDULER, "--install"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            messagebox.showinfo("Scheduler", "Windows scheduled tasks installed! ✅\n\nDaily pipeline and follow-up check are now scheduled.")
        else:
            messagebox.showerror("Scheduler Error", result.stdout + result.stderr)

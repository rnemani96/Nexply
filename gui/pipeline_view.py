"""
RAJESH AI GUI - Pipeline View
Run each pipeline stage from the GUI with live log output.
Hunt → Analyze → Match → Tailor → Apply
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path

import customtkinter as ctk

from gui.theme import *

BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
MAIN = str(BASE_DIR / "main.py")


class PipelineView(ctk.CTkFrame):
    """Run pipeline stages with live log streaming."""

    STAGES = [
        ("🔍  Hunt Jobs",     "hunt",    "Scrape new jobs from all enabled sources"),
        ("🧠  Analyze JDs",   "analyze", "AI analysis of job descriptions"),
        ("🎯  Score Matches", "match",   "Score how well you match each job"),
        ("📝  Tailor Resumes","tailor",  "Generate tailored resumes for top matches"),
        ("📤  Apply",         "apply",   "Apply to jobs (with approval gate)"),
        ("🚀  Full Pipeline", "run",     "Run all stages end-to-end"),
    ]

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=BG_PRIMARY, **kwargs)
        self._running = False
        self._log_queue: queue.Queue = queue.Queue()
        self._build_ui()
        self._poll_logs()

    # --------------------------------------------------------
    # BUILD UI
    # --------------------------------------------------------

    def _build_ui(self):
        # Header
        ctk.CTkLabel(
            self,
            text="⚡  Pipeline Control",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=TEXT_PRIMARY,
        ).pack(padx=24, pady=(20, 16), anchor="w")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        content.columnconfigure(0, weight=0, minsize=280)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        # Left panel: stage buttons + options
        left = ctk.CTkFrame(content, fg_color=BG_CARD, corner_radius=CORNER_RADIUS)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        ctk.CTkLabel(
            left,
            text="Pipeline Stages",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            text_color=TEXT_PRIMARY,
        ).pack(padx=16, pady=(16, 8))

        self._stage_btns = {}
        for label, cmd, tip in self.STAGES:
            is_full = cmd == "run"
            btn = ctk.CTkButton(
                left,
                text=label,
                font=ctk.CTkFont(*FONT_BODY),
                fg_color=ACCENT_PRIMARY if is_full else BG_CARD_HOVER,
                hover_color=ACCENT_PRIMARY,
                text_color="white",
                border_width=0 if is_full else 1,
                border_color=BORDER_SUBTLE,
                height=BUTTON_HEIGHT,
                anchor="w",
                command=lambda c=cmd: self._run_stage(c),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self._stage_btns[cmd] = btn

            ctk.CTkLabel(
                left,
                text=tip,
                font=ctk.CTkFont(*FONT_TINY),
                text_color=TEXT_DIM,
                anchor="w",
            ).pack(fill="x", padx=22, pady=(0, 4))

        # Dry run toggle
        ctk.CTkLabel(left, text="", fg_color="transparent").pack(pady=4)
        sep = ctk.CTkFrame(left, height=1, fg_color=BORDER_SUBTLE)
        sep.pack(fill="x", padx=12)

        self._dry_run_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            left,
            text="Dry Run (no real submissions)",
            variable=self._dry_run_var,
            font=ctk.CTkFont(*FONT_SMALL),
            text_color=TEXT_SECONDARY,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_PRIMARY,
            checkmark_color="white",
        ).pack(padx=12, pady=12, anchor="w")

        # Status bar
        self._status_lbl = ctk.CTkLabel(
            left,
            text="Ready",
            font=ctk.CTkFont(*FONT_SMALL),
            text_color=ACCENT_SECONDARY,
        )
        self._status_lbl.pack(padx=12, pady=(0, 12))

        self._stop_btn = ctk.CTkButton(
            left,
            text="⏹  Stop",
            font=ctk.CTkFont(*FONT_SMALL),
            fg_color=ACCENT_PINK,
            hover_color="#DD4466",
            text_color="white",
            height=32,
            state="disabled",
            command=self._stop,
        )
        self._stop_btn.pack(fill="x", padx=12, pady=(0, 16))

        # Right panel: log output
        right = ctk.CTkFrame(content, fg_color=BG_CARD, corner_radius=CORNER_RADIUS)
        right.grid(row=0, column=1, sticky="nsew")

        log_hdr = ctk.CTkFrame(right, fg_color="transparent")
        log_hdr.pack(fill="x", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            log_hdr,
            text="📋  Live Output",
            font=ctk.CTkFont(*FONT_SUBHEAD),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkButton(
            log_hdr,
            text="Clear",
            font=ctk.CTkFont(*FONT_TINY),
            fg_color=BG_CARD_HOVER,
            hover_color=BG_CARD,
            text_color=TEXT_SECONDARY,
            width=60, height=24,
            command=self._clear_log,
        ).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            right,
            font=ctk.CTkFont(family=FONT_MONO, size=11),
            fg_color=BG_PRIMARY,
            text_color=TEXT_PRIMARY,
            border_width=0,
            wrap="word",
            state="disabled",
        )
        self._log_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Color tags for log
        self._log_box.tag_config("green",  foreground=SCORE_STRONG)
        self._log_box.tag_config("yellow", foreground=SCORE_GOOD)
        self._log_box.tag_config("red",    foreground=ACCENT_PINK)
        self._log_box.tag_config("blue",   foreground=ACCENT_BLUE)
        self._log_box.tag_config("dim",    foreground=TEXT_DIM)
        self._log_box.tag_config("accent", foreground=ACCENT_PRIMARY)

    # --------------------------------------------------------
    # PIPELINE EXECUTION
    # --------------------------------------------------------

    def _run_stage(self, command: str):
        if self._running:
            return

        self._running = True
        self._set_buttons_state("disabled")
        self._stop_btn.configure(state="normal")
        self._status_lbl.configure(text=f"Running: {command}...", text_color=ACCENT_PRIMARY)

        cmd = [PYTHON, "-X", "utf8", MAIN, command]
        if command in ("apply", "run") and self._dry_run_var.get():
            cmd.append("--dry-run")

        self._log(f"\n{'='*60}\n  Running: python main.py {command}\n{'='*60}\n", "accent")
        self._process = None
        threading.Thread(
            target=self._stream_process,
            args=(cmd,),
            daemon=True,
        ).start()

    def _stream_process(self, cmd: list[str]):
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(BASE_DIR),
            )
            for line in self._process.stdout:
                self._log_queue.put(line)

            self._process.wait()
            rc = self._process.returncode

            if rc == 0:
                self._log_queue.put(("\n✅  Completed successfully.\n", "green"))
            else:
                self._log_queue.put((f"\n❌  Process exited with code {rc}.\n", "red"))
        except Exception as e:
            self._log_queue.put((f"\n❌  Error: {e}\n", "red"))
        finally:
            self._log_queue.put(("__DONE__", None))

    def _stop(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._log("\n⏹  Process terminated by user.\n", "yellow")

    # --------------------------------------------------------
    # LOG RENDERING
    # --------------------------------------------------------

    def _poll_logs(self):
        try:
            while True:
                item = self._log_queue.get_nowait()
                if isinstance(item, tuple):
                    text, tag = item
                else:
                    text, tag = item, None

                if text == "__DONE__":
                    self._running = False
                    self._set_buttons_state("normal")
                    self._stop_btn.configure(state="disabled")
                    self._status_lbl.configure(text="Idle", text_color=TEXT_SECONDARY)
                else:
                    self._log(text, tag or self._guess_tag(text))
        except:
            pass
        self.after(80, self._poll_logs)

    def _guess_tag(self, line: str) -> str | None:
        line = line.lower()
        if any(w in line for w in ("✅", "success", "complete", "added", "new")):
            return "green"
        if any(w in line for w in ("❌", "error", "failed", "exception")):
            return "red"
        if any(w in line for w in ("⚠", "warning", "skip")):
            return "yellow"
        if any(w in line for w in ("step", "running", "pipeline", "====", "----")):
            return "accent"
        return None

    def _log(self, text: str, tag: str | None = None):
        self._log_box.configure(state="normal")
        if tag:
            self._log_box.insert("end", text, tag)
        else:
            self._log_box.insert("end", text)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _set_buttons_state(self, state: str):
        for btn in self._stage_btns.values():
            btn.configure(state=state)

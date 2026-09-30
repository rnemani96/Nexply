"""
Nexply - Weekly Report Generator
Generates HTML report of job application progress.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from jinja2 import BaseLoader, Environment

import agent.database as database

logger = logging.getLogger(__name__)


# ============================================================
# HTML TEMPLATE
# ============================================================

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Nexply — Job Report | Week {{ week_label }}</title>
  <style>
    /* ── Reset & base ──────────────────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:          #0f1117;
      --surface:     #1a1d27;
      --surface2:    #22263a;
      --border:      #2e3350;
      --accent:      #6c8fef;
      --accent2:     #4ecdc4;
      --green:       #43d08a;
      --yellow:      #f5c842;
      --red:         #ff6b6b;
      --text:        #e0e4f7;
      --text-dim:    #7a82aa;
      --radius:      8px;
    }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      padding: 32px 24px;
    }

    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* ── Layout ─────────────────────────────────────────────── */
    .container { max-width: 1100px; margin: 0 auto; }

    /* ── Header ─────────────────────────────────────────────── */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 2px solid var(--accent);
      padding-bottom: 20px;
      margin-bottom: 32px;
    }
    .logo {
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 1px;
      color: var(--accent);
    }
    .logo span { color: var(--accent2); }
    .header-meta { text-align: right; color: var(--text-dim); font-size: 13px; }
    .header-meta strong { color: var(--text); font-size: 15px; display: block; }

    /* ── Section headings ───────────────────────────────────── */
    h2 {
      font-size: 16px;
      font-weight: 600;
      color: var(--accent2);
      margin: 32px 0 14px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    h2::after {
      content: '';
      flex: 1;
      height: 1px;
      background: var(--border);
    }

    /* ── Funnel cards ───────────────────────────────────────── */
    .funnel {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 28px;
    }
    .funnel-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 20px;
      min-width: 100px;
      text-align: center;
      flex: 1;
      position: relative;
    }
    .funnel-card .f-emoji { font-size: 20px; display: block; }
    .funnel-card .f-label { font-size: 11px; color: var(--text-dim); margin-top: 4px; }
    .funnel-card .f-count {
      font-size: 26px;
      font-weight: 700;
      color: var(--accent);
      display: block;
      margin-top: 4px;
    }
    .funnel-card.terminal .f-count { color: var(--red); }
    .funnel-card.positive .f-count { color: var(--green); }

    /* ── Tables ─────────────────────────────────────────────── */
    .table-wrap { overflow-x: auto; margin-bottom: 8px; }
    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--surface);
      border-radius: var(--radius);
      overflow: hidden;
    }
    thead th {
      background: var(--surface2);
      color: var(--text-dim);
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 10px 14px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    tbody tr:nth-child(even) { background: var(--surface2); }
    tbody tr:hover { background: #252942; }
    td {
      padding: 9px 14px;
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
    }
    tbody tr:last-child td { border-bottom: none; }

    /* ── Badges ─────────────────────────────────────────────── */
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.04em;
    }
    .badge-green  { background: #1a3d2b; color: var(--green); }
    .badge-yellow { background: #3d3410; color: var(--yellow); }
    .badge-red    { background: #3d1616; color: var(--red); }
    .badge-blue   { background: #182048; color: var(--accent); }
    .badge-teal   { background: #0e2f2e; color: var(--accent2); }
    .badge-grey   { background: var(--surface2); color: var(--text-dim); }

    /* ── Score bar ──────────────────────────────────────────── */
    .score-bar-wrap { display: flex; align-items: center; gap: 8px; }
    .score-bar {
      height: 6px; border-radius: 3px;
      background: var(--border);
      flex: 1; min-width: 60px; max-width: 120px;
    }
    .score-bar-fill { height: 100%; border-radius: 3px; }

    /* ── Empty state ─────────────────────────────────────────── */
    .empty {
      text-align: center;
      padding: 32px;
      color: var(--text-dim);
      font-style: italic;
    }

    /* ── Summary KPI row ────────────────────────────────────── */
    .kpi-row { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 24px; }
    .kpi-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px 22px;
      flex: 1;
      min-width: 140px;
    }
    .kpi-card .kpi-val {
      font-size: 28px;
      font-weight: 700;
      color: var(--accent);
    }
    .kpi-card .kpi-label {
      font-size: 12px;
      color: var(--text-dim);
      margin-top: 2px;
    }

    /* ── Footer ─────────────────────────────────────────────── */
    footer {
      margin-top: 48px;
      padding-top: 18px;
      border-top: 1px solid var(--border);
      text-align: center;
      color: var(--text-dim);
      font-size: 12px;
    }
    footer .brand { color: var(--accent); font-weight: 600; }
  </style>
</head>
<body>
<div class="container">

  <!-- ── Header ─────────────────────────────────────────── -->
  <header>
    <div class="logo">🤖 Rajesh<span>AI</span></div>
    <div class="header-meta">
      <strong>Job Application Report</strong>
      Week {{ week_label }} &nbsp;·&nbsp; Generated {{ generated_at }}
    </div>
  </header>

  <!-- ── KPI summary ────────────────────────────────────── -->
  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-val">{{ total_jobs }}</div>
      <div class="kpi-label">Total jobs tracked</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{{ applied_week | length }}</div>
      <div class="kpi-label">Applied this week</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{{ pipeline_stats.get('INTERVIEW_SCREEN', 0) + pipeline_stats.get('INTERVIEW_TECH', 0) }}</div>
      <div class="kpi-label">Active interviews</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{{ pipeline_stats.get('OFFER', 0) }}</div>
      <div class="kpi-label">Offers received</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{{ response_rate }}%</div>
      <div class="kpi-label">Response rate</div>
    </div>
  </div>

  <!-- ── Pipeline funnel ────────────────────────────────── -->
  <h2>📊 Pipeline Funnel</h2>
  <div class="funnel">
    {% for stage in pipeline_stages %}
    <div class="funnel-card
      {%- if stage.status in ('REJECTED', 'GHOSTED', 'WITHDRAWN') %} terminal
      {%- elif stage.status in ('OFFER', 'ACCEPTED') %} positive
      {%- endif %}">
      <span class="f-emoji">{{ stage.emoji }}</span>
      <span class="f-label">{{ stage.label }}</span>
      <span class="f-count">{{ pipeline_stats.get(stage.status, 0) }}</span>
    </div>
    {% endfor %}
  </div>

  <!-- ── Applied this week ──────────────────────────────── -->
  <h2>📤 Applied This Week</h2>
  <div class="table-wrap">
  {% if applied_week %}
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Job Title</th>
        <th>Company</th>
        <th>Platform</th>
        <th>ATS Score</th>
        <th>Match Score</th>
        <th>Applied At</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {% for job in applied_week %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>
          {% if job.url %}<a href="{{ job.url }}" target="_blank">{{ job.title }}</a>
          {% else %}{{ job.title }}{% endif %}
        </td>
        <td>{{ job.company }}</td>
        <td><span class="badge badge-teal">{{ job.platform or '—' }}</span></td>
        <td>
          {% if job.ats_score %}
            {% set s = job.ats_score | float %}
            <div class="score-bar-wrap">
              <span>{{ "%.0f"|format(s) }}</span>
              <div class="score-bar">
                <div class="score-bar-fill" style="width:{{ s }}%;
                  background: {% if s>=80 %}#43d08a{% elif s>=60 %}#f5c842{% else %}#ff6b6b{% endif %}">
                </div>
              </div>
            </div>
          {% else %}—{% endif %}
        </td>
        <td>
          {% if job.ai_match_score %}
            {% set ms = job.ai_match_score | float %}
            <span class="badge
              {%- if ms >= 85 %} badge-green
              {%- elif ms >= 70 %} badge-teal
              {%- elif ms >= 55 %} badge-yellow
              {%- else %} badge-red{%- endif %}">
              {{ "%.0f"|format(ms) }}
            </span>
          {% else %}—{% endif %}
        </td>
        <td>{{ job.application_date[:10] if job.application_date else '—' }}</td>
        <td>
          <span class="badge
            {%- if job.status == 'APPLIED' %} badge-blue
            {%- elif job.status in ('INTERVIEW_SCREEN', 'INTERVIEW_TECH') %} badge-teal
            {%- elif job.status in ('OFFER', 'ACCEPTED') %} badge-green
            {%- elif job.status in ('REJECTED', 'GHOSTED') %} badge-red
            {%- else %} badge-grey{%- endif %}">
            {{ job.status }}
          </span>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">No applications submitted this week.</div>
  {% endif %}
  </div>

  <!-- ── Top matches not yet applied ───────────────────── -->
  <h2>🎯 Top Matches — Not Yet Applied</h2>
  <div class="table-wrap">
  {% if top_matches %}
  <table>
    <thead>
      <tr>
        <th>Rank</th>
        <th>Job Title</th>
        <th>Company</th>
        <th>Location</th>
        <th>Score</th>
        <th>Recommendation</th>
        <th>Status</th>
        <th>Source</th>
      </tr>
    </thead>
    <tbody>
      {% for job in top_matches %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>
          {% if job.url %}<a href="{{ job.url }}" target="_blank">{{ job.title }}</a>
          {% else %}{{ job.title }}{% endif %}
        </td>
        <td>{{ job.company }}</td>
        <td>{{ job.location or '—' }}</td>
        <td>
          {% set ms = (job.ai_match_score or 0) | float %}
          <span class="badge
            {%- if ms >= 85 %} badge-green
            {%- elif ms >= 70 %} badge-teal
            {%- elif ms >= 55 %} badge-yellow
            {%- else %} badge-grey{%- endif %}">
            {{ "%.0f"|format(ms) }}
          </span>
        </td>
        <td>
          {% set rec = job.recommendation or '' %}
          <span class="badge
            {%- if rec == 'strong_apply' %} badge-green
            {%- elif rec == 'apply' %} badge-teal
            {%- elif rec == 'stretch' %} badge-yellow
            {%- else %} badge-grey{%- endif %}">
            {{ rec.replace('_', ' ').title() if rec else '—' }}
          </span>
        </td>
        <td><span class="badge badge-grey">{{ job.status }}</span></td>
        <td>{{ job.source or '—' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">No high-score matches found yet. Run the matcher to populate.</div>
  {% endif %}
  </div>

  <!-- ── Follow-up queue ────────────────────────────────── -->
  <h2>🔔 Follow-Up Queue</h2>
  <div class="table-wrap">
  {% if follow_ups %}
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Job Title</th>
        <th>Company</th>
        <th>Applied At</th>
        <th>Follow-Up Due</th>
        <th>Days Overdue</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody>
      {% for item in follow_ups %}
      <tr>
        <td>{{ item.id }}</td>
        <td>
          {% if item.url %}<a href="{{ item.url }}" target="_blank">{{ item.title }}</a>
          {% else %}{{ item.title }}{% endif %}
        </td>
        <td>{{ item.company }}</td>
        <td>{{ item.applied_at[:10] if item.applied_at else '—' }}</td>
        <td>{{ item.follow_up_due or '—' }}</td>
        <td>
          {% if item.days_overdue is defined and item.days_overdue > 0 %}
            <span class="badge badge-red">+{{ item.days_overdue }}d</span>
          {% else %}
            <span class="badge badge-yellow">Today</span>
          {% endif %}
        </td>
        <td>
          {% if item.url %}
          <a href="{{ item.url }}" target="_blank">
            <span class="badge badge-blue">Follow Up</span>
          </a>
          {% else %}
            <span class="badge badge-grey">—</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">🎉 No follow-ups pending — you're all caught up!</div>
  {% endif %}
  </div>

  <!-- ── Footer ─────────────────────────────────────────── -->
  <footer>
    Generated by <span class="brand">🤖 Nexply</span> at {{ generated_at }} &nbsp;·&nbsp;
    Week {{ week_label }} Report &nbsp;·&nbsp; Autonomous Job Application System
  </footer>

</div>
</body>
</html>
"""

# ============================================================
# REPORTER
# ============================================================


class Reporter:
    """
    Weekly HTML report generator for the Nexply job pipeline.

    Pulls live data from the database, renders a professional dark-themed HTML
    report via an inline Jinja2 template, and saves it to disk.

    Example
    -------
    >>> from agent.reporter import Reporter
    >>> from pathlib import Path
    >>> path = Reporter().generate_weekly_report(Path("output/reports"))
    >>> print(f"Report saved: {path}")
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_weekly_report(self, output_dir: Path) -> Path:
        """
        Generate the weekly HTML report and save it to *output_dir*.

        Parameters
        ----------
        output_dir:
            Directory where the report will be saved.  Created automatically
            if it does not exist.

        Returns
        -------
        Path
            Absolute path to the generated ``.html`` file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        iso_year, iso_week, _ = now.isocalendar()
        week_label = f"{iso_year}-W{iso_week:02d}"
        generated_at = now.strftime("%Y-%m-%d %H:%M:%S")

        # ── Gather data ──────────────────────────────────────────────
        pipeline_stats: dict = database.get_pipeline_stats()
        top_matches: list[dict] = database.get_top_matches(min_score=60, limit=15)
        follow_ups: list[dict] = self._get_follow_ups_enriched()
        applied_week: list[dict] = self._get_applied_this_week()
        total_jobs: int = database.get_job_count()
        response_rate: float = self._calc_response_rate(pipeline_stats)

        # ── Pipeline funnel metadata ─────────────────────────────────
        pipeline_stages = [
            {"status": "NEW",              "emoji": "📥", "label": "New"},
            {"status": "ANALYZED",         "emoji": "🔍", "label": "Analyzed"},
            {"status": "MATCHED",          "emoji": "🎯", "label": "Matched"},
            {"status": "TAILORED",         "emoji": "📝", "label": "Tailored"},
            {"status": "QUEUED",           "emoji": "🗂️",  "label": "Queued"},
            {"status": "APPLIED",          "emoji": "📤", "label": "Applied"},
            {"status": "INTERVIEW_SCREEN", "emoji": "📞", "label": "Screen"},
            {"status": "INTERVIEW_TECH",   "emoji": "💻", "label": "Tech Round"},
            {"status": "OFFER",            "emoji": "🏆", "label": "Offer"},
            {"status": "ACCEPTED",         "emoji": "✅", "label": "Accepted"},
            {"status": "REJECTED",         "emoji": "❌", "label": "Rejected"},
            {"status": "GHOSTED",          "emoji": "👻", "label": "Ghosted"},
            {"status": "WITHDRAWN",        "emoji": "↩️",  "label": "Withdrawn"},
        ]

        # ── Render ──────────────────────────────────────────────────
        env = Environment(loader=BaseLoader(), autoescape=False)
        template = env.from_string(_HTML_TEMPLATE)

        html = template.render(
            week_label=week_label,
            generated_at=generated_at,
            total_jobs=total_jobs,
            pipeline_stats=pipeline_stats,
            pipeline_stages=pipeline_stages,
            top_matches=top_matches,
            applied_week=applied_week,
            follow_ups=follow_ups,
            response_rate=f"{response_rate:.1f}",
        )

        # ── Save ─────────────────────────────────────────────────────
        output_path = output_dir / f"weekly_report_{week_label}.html"
        output_path.write_text(html, encoding="utf-8")

        logger.info("Weekly report written to %s", output_path)
        print(f"✅ Report generated → {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _get_applied_this_week(self) -> list[dict]:
        """
        Return jobs that had an application submitted in the last 7 days,
        joined with their application metadata.
        """
        conn = database.get_connection()
        rows = conn.execute("""
            SELECT
                j.id,
                j.title,
                j.company,
                j.location,
                j.url,
                j.ai_match_score,
                j.ats_score,
                j.status,
                j.application_date,
                a.platform,
                a.applied_at,
                a.confirmation_id
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            WHERE date(a.applied_at) >= date('now', '-7 days')
            ORDER BY a.applied_at DESC
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _get_follow_ups_enriched(self) -> list[dict]:
        """
        Return follow-up queue with a computed ``days_overdue`` field.
        """
        raw = database.get_follow_up_queue()
        today = datetime.now().date()

        enriched: list[dict] = []
        for item in raw:
            due_raw = item.get("follow_up_due") or ""
            try:
                due_date = datetime.fromisoformat(due_raw).date()
                days_overdue = (today - due_date).days
            except (ValueError, TypeError):
                days_overdue = 0
            enriched.append({**item, "days_overdue": max(0, days_overdue)})

        return enriched

    @staticmethod
    def _calc_response_rate(stats: dict) -> float:
        """
        Compute (interviews + offers + accepted) / total_applied * 100.

        Returns 0.0 if no applications have been made yet.
        """
        applied_states = {
            "APPLIED", "INTERVIEW_SCREEN", "INTERVIEW_TECH",
            "OFFER", "ACCEPTED", "REJECTED", "GHOSTED",
        }
        total = sum(stats.get(s, 0) for s in applied_states)
        if total == 0:
            return 0.0

        responses = (
            stats.get("INTERVIEW_SCREEN", 0)
            + stats.get("INTERVIEW_TECH", 0)
            + stats.get("OFFER", 0)
            + stats.get("ACCEPTED", 0)
        )
        return responses / total * 100


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys

    output_dir = Path("output/reports")
    if len(sys.argv) > 1:
        output_dir = Path(sys.argv[1])

    reporter = Reporter()
    report_path = reporter.generate_weekly_report(output_dir)
    print(f"Open in browser: file:///{report_path.resolve()}")

import os
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

os.makedirs(r'd:\RajeshAI\docs', exist_ok=True)
doc = Document()

# Cover Page
title = doc.add_heading('RAJESH AI — Autonomous Job Applier', level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
subtitle = doc.add_heading('Complete User Guide & Technical Reference v3.0\nAuthor: Rajesh\nDate: 2026-09-30', level=1)
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
doc.add_page_break()

# Table of Contents
doc.add_heading('Table of Contents', level=1)
toc = [
    "Chapter 1 — Overview",
    "Chapter 2 — Installation",
    "Chapter 3 — First-Time Setup",
    "Chapter 4 — Job Sources",
    "Chapter 5 — Visa Sponsorship Feature",
    "Chapter 6 — AI Providers",
    "Chapter 7 — GUI Walkthrough",
    "Chapter 8 — CLI Commands",
    "Chapter 9 — Configuration Reference",
    "Chapter 10 — Troubleshooting",
    "Appendix — Architecture Diagram"
]
for item in toc:
    doc.add_paragraph(item, style='List Number')
doc.add_page_break()

# Chapter 1
doc.add_heading('Chapter 1 — Overview', level=1)
doc.add_paragraph("RAJESH AI is an autonomous job application system designed to streamline your job search.")
p = doc.add_paragraph()
p.add_run("Key Features:").bold = True
features = [
    "10 job sources",
    "Visa sponsorship detection",
    "Location filter",
    "AI-tailored resumes",
    "ATS checking",
    "30-min auto-scan",
    "System tray icon",
    "GUI + CLI",
    "Multi-AI failover",
    "9 job boards including visa-sponsoring jobs"
]
for f in features:
    doc.add_paragraph(f, style='List Bullet')
doc.add_page_break()

# Chapter 2
doc.add_heading('Chapter 2 — Installation', level=1)
doc.add_paragraph("Prerequisites: Python 3.11+, Windows 10/11.")
doc.add_heading('Install from Source', level=2)
doc.add_paragraph("1. git clone\n2. pip install -r requirements.txt")
doc.add_heading('Install from EXE', level=2)
doc.add_paragraph("Just run dist/RajeshAI/RajeshAI.exe")
doc.add_page_break()

# Chapter 3
doc.add_heading('Chapter 3 — First-Time Setup', level=1)
doc.add_paragraph("- Place master_resume.docx in resume/ folder")
doc.add_paragraph("- Set AI provider in config/settings.yaml")
doc.add_paragraph("- Free AI options: Ollama (install from ollama.com, run `ollama pull llama3.1`), Gemini API key (GEMINI_API_KEY env var), LM Studio")
doc.add_paragraph("- Run `python main.py setup` to verify")
doc.add_page_break()

# Chapter 4
doc.add_heading('Chapter 4 — Job Sources', level=1)
table_data = [
    ["Source", "Type", "Coverage", "Auth"],
    ["Himalayas", "Free API", "Worldwide remote", "None"],
    ["RemoteOK", "Free API", "Worldwide remote", "None"],
    ["Jobicy", "Free API", "Worldwide categorized", "None"],
    ["Remotive", "Free API", "Data/QA/ML", "None"],
    ["We Work Remotely", "RSS", "Worldwide", "None"],
    ["AI-Jobs.net", "RSS", "AI/ML specialist", "None"],
    ["Remote First Jobs", "Free API", "Worldwide", "None"],
    ["Visa Jobs", "Multi-source", "Any visa-sponsoring", "None"],
    ["LinkedIn", "Playwright", "Easy Apply", "Session cookie"],
    ["Naukri", "Scraper", "India", "None"]
]
table = doc.add_table(rows=1, cols=4)
table.style = 'Light Shading Accent 1'
hdr_cells = table.rows[0].cells
for i in range(4):
    hdr_cells[i].text = table_data[0][i]
for row in table_data[1:]:
    row_cells = table.add_row().cells
    for i in range(4):
        row_cells[i].text = row[i]
doc.add_page_break()

# Chapter 5
doc.add_heading('Chapter 5 — Visa Sponsorship Feature', level=1)
doc.add_paragraph("Location filter (India/Remote = always keep; Foreign = only keep with visa sponsorship).")
doc.add_paragraph("Detected visa types:")
visas = ["H1B (USA)", "Skilled Worker (UK)", "EU Blue Card", "Canada LMIA", "Australia 482", "Singapore EP", "UAE", "Netherlands", "Ireland", "NZ", "Japan", "Nordic"]
for v in visas:
    doc.add_paragraph(v, style='List Bullet')
doc.add_paragraph("Matching these provides a +15 score bonus.")
doc.add_page_break()

# Chapter 6
doc.add_heading('Chapter 6 — AI Providers', level=1)
doc.add_paragraph("Rate-limit auto-failover between providers.")
table = doc.add_table(rows=1, cols=3)
table.style = 'Light Shading Accent 1'
hdr_cells = table.rows[0].cells
hdr_cells[0].text = "Provider"
hdr_cells[1].text = "Type"
hdr_cells[2].text = "Notes"
row1 = table.add_row().cells
row1[0].text = "Gemini"
row1[1].text = "Online"
row1[2].text = "Free tier 15 RPM"
row2 = table.add_row().cells
row2[0].text = "Ollama"
row2[1].text = "Offline"
row2[2].text = "Runs llama3.1/mistral locally"
row3 = table.add_row().cells
row3[0].text = "LM Studio"
row3[1].text = "Offline"
row3[2].text = "GUI app"
doc.add_page_break()

# Chapter 7
doc.add_heading('Chapter 7 — GUI Walkthrough', level=1)
doc.add_paragraph("Dashboard: stats + funnel + top matches")
doc.add_paragraph("Jobs tab: filter by visa/score/status/source")
doc.add_paragraph("Pipeline tab: Hunt/Analyze/Match/Tailor/Apply")
doc.add_paragraph("Apply Queue")
doc.add_paragraph("Settings")
doc.add_page_break()

# Chapter 8
doc.add_heading('Chapter 8 — CLI Commands', level=1)
table = doc.add_table(rows=1, cols=2)
table.style = 'Light Shading Accent 1'
hdr = table.rows[0].cells
hdr[0].text = "Command"
hdr[1].text = "Description"
cmds = [
    ["python main.py hunt", "Scrape new jobs"],
    ["python main.py analyze", "AI analyze JDs"],
    ["python main.py match", "Score matches"],
    ["python main.py tailor", "Generate resumes"],
    ["python main.py apply", "Apply to jobs"],
    ["python main.py run", "Full pipeline"],
    ["python main.py status", "Show pipeline stats"],
    ["python main.py dashboard", "Rich terminal dashboard"],
    ["python main.py ai-status", "Check AI providers"],
    ["python main.py setup", "First-time setup"]
]
for c in cmds:
    r = table.add_row().cells
    r[0].text = c[0]
    r[1].text = c[1]
doc.add_page_break()

# Chapter 9
doc.add_heading('Chapter 9 — Configuration Reference', level=1)
doc.add_paragraph("Settings reference table:")
table = doc.add_table(rows=1, cols=2)
table.style = 'Light Shading Accent 1'
hdr = table.rows[0].cells
hdr[0].text = "Key"
hdr[1].text = "Purpose"
r = table.add_row().cells
r[0].text = "ai_provider"
r[1].text = "Sets default AI provider"
doc.add_page_break()

# Chapter 10
doc.add_heading('Chapter 10 — Troubleshooting', level=1)
table = doc.add_table(rows=1, cols=2)
table.style = 'Light Shading Accent 1'
hdr = table.rows[0].cells
hdr[0].text = "Issue"
hdr[1].text = "Solution"
r = table.add_row().cells
r[0].text = "API Rate Limit"
r[1].text = "Wait or switch provider"
doc.add_page_break()

# Appendix
doc.add_heading('Appendix — Architecture Diagram', level=1)
doc.add_paragraph('''
[Internet] --> (Job Sources) --> [Hunt Pipeline]
                                    |
                                    v
[AI Provider] <--> [Analyze & Match Pipeline]
                                    |
                                    v
[Word Resumes] <--> [Tailor Pipeline]
                                    |
                                    v
[LinkedIn/ATS] <--> [Apply Pipeline]
''')

doc.save(r'd:\RajeshAI\docs\RAJESH_AI_Documentation.docx')
print("Document created successfully at d:\\RajeshAI\\docs\\RAJESH_AI_Documentation.docx")

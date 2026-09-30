# 🤖 RAJESH AI — Autonomous Job Applier

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Windows](https://img.shields.io/badge/OS-Windows-green)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Version](https://img.shields.io/badge/Version-3.0-orange)

Autonomous AI-powered job applier with visa sponsorship detection, 10 job sources, beautiful GUI, and auto-scan every 30 minutes.

![Dashboard](docs/screenshot.png)

## ✨ Features
- 🌍 10 job sources (Himalayas, RemoteOK, Jobicy, Remotive, WWR, AI-Jobs, visa-focused)
- 🛂 Smart location filter: foreign-country jobs require visa sponsorship
- 🌐 Universal visa detection (H1B, UK, EU, Canada, Australia, Singapore, UAE + more)
- 🎨 Beautiful dark-themed GUI with system tray & 30-min auto-scan
- 🧠 Multi-AI provider: Gemini + Ollama + LM Studio with rate-limit failover
- 🧑‍💻 Data Science + QA/Test roles + worldwide preference
- 📦 PyInstaller EXE build (194MB self-contained)
- 📄 ATS-optimized resume tailoring per job

## 🚀 Quick Start
1. Clone the repository: `git clone <url>`
2. Install dependencies: `pip install -r requirements.txt`
3. Place your `master_resume.docx` in the `resume/` folder
4. Set up your AI provider in `config/settings.yaml` (or free alternatives)
5. Run the setup: `python main.py setup`

## 📡 Job Sources
| Source | Type | Coverage | Auth |
|---|---|---|---|
| Himalayas | Free API | Worldwide remote | None |
| RemoteOK | Free API | Worldwide remote | None |
| Jobicy | Free API | Worldwide categorized | None |
| Remotive | Free API | Data/QA/ML | None |
| We Work Remotely | RSS | Worldwide | None |
| AI-Jobs.net | RSS | AI/ML specialist | None |
| Remote First Jobs | Free API | Worldwide | None |
| Visa Jobs | Multi-source | Any visa-sponsoring | None |
| LinkedIn | Playwright | Easy Apply | Session cookie |
| Naukri | Scraper | India | None |

## 🛂 Visa Sponsorship
The system uses a smart location filter: jobs in India or fully Remote are always kept, while jobs requiring relocation to foreign countries are only kept if they explicitly offer visa sponsorship.
Detected visas include: H1B (USA), Skilled Worker (UK), EU Blue Card, Canada LMIA, Australia 482, Singapore EP, UAE, Netherlands, Ireland, NZ, Japan, Nordic. (+15 score bonus)

## 🧠 AI Providers
| Provider | Type | Notes |
|---|---|---|
| Gemini | Online | Free tier 15 RPM |
| Ollama | Offline | Runs llama3.1/mistral locally |
| LM Studio | Offline | GUI app |

## ⚙️ Configuration Reference
| Key | Purpose |
|---|---|
| ai_provider | Sets the active AI provider |

## 💻 CLI Commands
```bash
python main.py hunt       # Scrape new jobs
python main.py analyze    # AI analyze JDs
python main.py match      # Score matches
python main.py tailor     # Generate resumes
python main.py apply      # Apply to jobs
python main.py run        # Full pipeline
python main.py status     # Show pipeline stats
python main.py dashboard  # Rich terminal dashboard
python main.py ai-status  # Check AI providers
python main.py setup      # First-time setup
```

## 🤝 Contributing
Pull requests are welcome!

## 📄 License
MIT License

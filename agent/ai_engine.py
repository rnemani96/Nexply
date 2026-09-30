"""
RAJESH AI - AI ENGINE v2.0
Multi-provider AI client supporting:
  - Gemini (via google-genai SDK)
  - Ollama  (local, free — http://localhost:11434)
  - LM Studio (local, OpenAI-compatible — http://localhost:1234/v1)

Usage:
    from agent.ai_engine import get_ai_engine

    ai = get_ai_engine()
    result = ai.analyze_jd("We are looking for a GenAI engineer...")
    print(result.required_skills)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml

logger = logging.getLogger(__name__)

# ============================================================
# SETTINGS LOADER
# ============================================================

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"


def _load_settings() -> dict:
    if _SETTINGS_PATH.exists():
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class JDProfile:
    """Structured extraction from a job description."""
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    role_type: str = ""           # e.g. "genai_engineer", "ml_engineer"
    seniority: str = ""           # e.g. "mid", "senior", "lead"
    work_mode: str = ""           # "remote", "hybrid", "onsite"
    location_format: str = "auto" # "india", "us", "uk", "eu", "auto"
    min_experience_years: float = 0.0
    max_experience_years: float = 99.0
    compensation: str = ""
    culture_keywords: list[str] = field(default_factory=list)
    summary: str = ""
    raw_provider: str = ""        # which AI provider generated this


@dataclass
class MatchResult:
    """AI-powered candidate ↔ JD match scoring."""
    score: float = 0.0            # 0–100
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    gap_analysis: str = ""
    recommendation: str = ""      # "strong_apply" | "apply" | "stretch" | "skip"
    raw_provider: str = ""


@dataclass
class ResumeRewriteResult:
    """AI-rewritten resume bullets aligned to JD."""
    bullets: list[str] = field(default_factory=list)
    summary: str = ""             # Rewritten professional summary
    raw_provider: str = ""


# ============================================================
# BASE PROVIDER INTERFACE
# ============================================================

class BaseAIProvider(ABC):
    """Abstract base for all AI providers."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is reachable."""
        ...

    @abstractmethod
    def chat(self, system: str, user: str, *, json_mode: bool = False) -> str:
        """Send a chat prompt and return the text response."""
        ...

    def analyze_jd(self, description: str) -> JDProfile:
        """Extract structured requirements from a job description."""
        system = _JD_SYSTEM_PROMPT
        user = f"Analyze this job description and return JSON:\n\n{description[:6000]}"
        raw = self.chat(system, user, json_mode=True)
        return _parse_jd_profile(raw, provider=self.name)

    def score_match(
        self,
        candidate_profile: dict,
        jd_profile: JDProfile,
    ) -> MatchResult:
        """Score the candidate against the JD."""
        system = _MATCH_SYSTEM_PROMPT
        user = (
            f"Candidate profile:\n{json.dumps(candidate_profile, indent=2)}\n\n"
            f"Job requirements:\n"
            f"Required skills: {jd_profile.required_skills}\n"
            f"Preferred skills: {jd_profile.preferred_skills}\n"
            f"Seniority: {jd_profile.seniority}\n"
            f"Min experience: {jd_profile.min_experience_years} years\n\n"
            "Return JSON with score and analysis."
        )
        raw = self.chat(system, user, json_mode=True)
        return _parse_match_result(raw, provider=self.name)

    def tailor_resume_bullets(
        self,
        bullets: list[str],
        jd_profile: JDProfile,
        max_bullets: int = 6,
    ) -> ResumeRewriteResult:
        """Reword existing bullets to use JD language. No fabrication."""
        system = _RESUME_SYSTEM_PROMPT
        user = (
            f"Job required skills: {jd_profile.required_skills}\n"
            f"Job preferred skills: {jd_profile.preferred_skills}\n"
            f"Role: {jd_profile.role_type}\n\n"
            f"Existing resume bullets (DO NOT invent new facts):\n"
            + "\n".join(f"- {b}" for b in bullets)
            + f"\n\nRewrite the {min(max_bullets, len(bullets))} most relevant bullets "
            "and return JSON."
        )
        raw = self.chat(system, user, json_mode=True)
        return _parse_resume_result(raw, provider=self.name)

    def generate_cover_letter(
        self,
        candidate_profile: dict,
        jd_profile: JDProfile,
        job_title: str,
        company: str,
    ) -> str:
        """Generate a short, ATS-friendly cover letter paragraph."""
        system = (
            "You are a professional cover letter writer. "
            "Write a concise 3-paragraph cover letter (150–200 words total). "
            "Be specific, avoid clichés, use the candidate's real experience only."
        )
        user = (
            f"Write a cover letter for:\n"
            f"Position: {job_title} at {company}\n"
            f"Key skills required: {jd_profile.required_skills[:8]}\n"
            f"Candidate summary: {candidate_profile.get('summary', '')}\n"
            f"Candidate skills: {candidate_profile.get('skills_text', '')[:500]}\n"
        )
        return self.chat(system, user, json_mode=False)


# ============================================================
# GEMINI PROVIDER
# ============================================================

class GeminiProvider(BaseAIProvider):
    """Google Gemini via the official google-genai SDK."""

    name = "gemini"

    def __init__(self, settings: dict):
        self._settings = settings.get("ai", {}).get("gemini", {})
        self._jd_model = self._settings.get("jd_analysis_model", "gemini-3.8-flash")
        self._resume_model = self._settings.get("resume_model", "gemini-3.1-pro-preview")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
                api_key = os.environ.get("GEMINI_API_KEY", "")
                if not api_key:
                    raise ValueError("GEMINI_API_KEY environment variable not set.")
                self._client = genai.Client(api_key=api_key)
            except ImportError:
                raise ImportError(
                    "google-genai not installed. Run: pip install google-genai"
                )
        return self._client

    def is_available(self) -> bool:
        try:
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key:
                return False
            self._get_client()
            return True
        except Exception:
            return False

    def chat(self, system: str, user: str, *, json_mode: bool = False) -> str:
        client = self._get_client()
        try:
            interaction = client.interactions.create(
                model=self._jd_model,
                system_instruction=system,
                input=user,
            )
            return interaction.output_text or ""
        except Exception as e:
            logger.error(f"Gemini chat error: {e}")
            raise


# ============================================================
# OLLAMA PROVIDER
# ============================================================

class OllamaProvider(BaseAIProvider):
    """Local Ollama server (http://localhost:11434)."""

    name = "ollama"

    def __init__(self, settings: dict):
        cfg = settings.get("ai", {}).get("ollama", {})
        self._base_url = cfg.get("base_url", "http://localhost:11434").rstrip("/")
        self._model = cfg.get("jd_analysis_model", "llama3.1")
        self._timeout = cfg.get("timeout_seconds", 120)

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self._base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return locally available model names."""
        try:
            resp = httpx.get(f"{self._base_url}/api/tags", timeout=10.0)
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def chat(self, system: str, user: str, *, json_mode: bool = False) -> str:
        """Call Ollama /api/chat endpoint."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        try:
            resp = httpx.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except httpx.TimeoutException:
            raise TimeoutError(
                f"Ollama timed out after {self._timeout}s. "
                "Try a smaller/faster model or increase timeout_seconds in settings.yaml."
            )
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            raise

    def pull_model(self, model_name: str) -> None:
        """Pull a model from Ollama library (streaming progress)."""
        import sys
        print(f"Pulling model '{model_name}' from Ollama...")
        with httpx.stream(
            "POST",
            f"{self._base_url}/api/pull",
            json={"name": model_name},
            timeout=600,
        ) as resp:
            for line in resp.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        status = data.get("status", "")
                        if "progress" in status or "pulling" in status:
                            sys.stdout.write(f"\r{status}   ")
                            sys.stdout.flush()
                    except Exception:
                        pass
        print(f"\nModel '{model_name}' ready.")


# ============================================================
# LM STUDIO PROVIDER (OpenAI-compatible API)
# ============================================================

class LMStudioProvider(BaseAIProvider):
    """LM Studio local server — OpenAI-compatible REST API."""

    name = "lmstudio"

    def __init__(self, settings: dict):
        cfg = settings.get("ai", {}).get("lmstudio", {})
        self._base_url = cfg.get("base_url", "http://localhost:1234/v1").rstrip("/")
        self._model = cfg.get("jd_analysis_model", "local-model")
        self._timeout = cfg.get("timeout_seconds", 180)

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self._base_url}/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            resp = httpx.get(f"{self._base_url}/models", timeout=10.0)
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []

    def chat(self, system: str, user: str, *, json_mode: bool = False) -> str:
        """Call OpenAI-compatible /chat/completions endpoint."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""
        except httpx.TimeoutException:
            raise TimeoutError(
                f"LM Studio timed out after {self._timeout}s. "
                "Use a faster model or increase timeout_seconds in settings.yaml."
            )
        except Exception as e:
            logger.error(f"LM Studio chat error: {e}")
            raise


# ============================================================
# MULTI-PROVIDER ENGINE (with fallback)
# ============================================================

class AIEngine:
    """
    Unified AI engine with automatic provider selection and fallback.

    Priority:
      1. Explicitly configured primary provider
      2. Fallback chain from settings.yaml
      3. Raises AIEngineError if nothing works

    Usage:
        engine = AIEngine()
        jd = engine.analyze_jd("We're hiring a GenAI Engineer...")
        print(jd.required_skills)
    """

    def __init__(self, settings: dict | None = None):
        self._settings = settings or _load_settings()
        self._providers: dict[str, BaseAIProvider] = {
            "gemini": GeminiProvider(self._settings),
            "ollama": OllamaProvider(self._settings),
            "lmstudio": LMStudioProvider(self._settings),
        }
        self._primary = self._settings.get("ai", {}).get("provider", "ollama")
        self._fallback_chain: list[str] = self._settings.get("ai", {}).get(
            "fallback_chain", ["ollama", "gemini"]
        )

    def _get_active_provider(self) -> BaseAIProvider:
        """Return the first available provider from the priority list."""
        chain = [self._primary] + [
            p for p in self._fallback_chain if p != self._primary
        ]
        for name in chain:
            provider = self._providers.get(name)
            if provider and provider.is_available():
                logger.debug(f"Using AI provider: {name}")
                return provider
        raise AIEngineError(
            "No AI provider available!\n"
            f"Primary: {self._primary} — not reachable.\n"
            "Fix options:\n"
            "  • Ollama: install from https://ollama.com then run 'ollama pull llama3.1'\n"
            "  • LM Studio: enable the local server on port 1234\n"
            "  • Gemini: set GEMINI_API_KEY environment variable\n"
        )

    def status(self) -> dict[str, bool]:
        """Check availability of all configured providers."""
        return {
            name: provider.is_available()
            for name, provider in self._providers.items()
        }

    def active_provider_name(self) -> str:
        try:
            return self._get_active_provider().name
        except AIEngineError:
            return "none"

    # --------------------------------------------------------
    # Public API — delegates to active provider
    # --------------------------------------------------------

    def analyze_jd(self, description: str) -> JDProfile:
        return self._get_active_provider().analyze_jd(description)

    def score_match(
        self,
        candidate_profile: dict,
        jd_profile: JDProfile,
    ) -> MatchResult:
        return self._get_active_provider().score_match(candidate_profile, jd_profile)

    def tailor_resume_bullets(
        self,
        bullets: list[str],
        jd_profile: JDProfile,
        max_bullets: int = 6,
    ) -> ResumeRewriteResult:
        return self._get_active_provider().tailor_resume_bullets(
            bullets, jd_profile, max_bullets
        )

    def generate_cover_letter(
        self,
        candidate_profile: dict,
        jd_profile: JDProfile,
        job_title: str,
        company: str,
    ) -> str:
        return self._get_active_provider().generate_cover_letter(
            candidate_profile, jd_profile, job_title, company
        )


class AIEngineError(Exception):
    pass


# ============================================================
# SINGLETON FACTORY
# ============================================================

_engine_instance: AIEngine | None = None


def get_ai_engine(settings: dict | None = None) -> AIEngine:
    """Return the global AIEngine singleton."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = AIEngine(settings)
    return _engine_instance


# ============================================================
# PROMPTS
# ============================================================

_JD_SYSTEM_PROMPT = """
You are a precise job description analyzer. Extract structured data from the given job description.
Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill3"],
  "role_type": "genai_engineer",
  "seniority": "senior",
  "work_mode": "remote",
  "location_format": "us",
  "min_experience_years": 3,
  "max_experience_years": 8,
  "compensation": "$120k-150k",
  "culture_keywords": ["fast-paced", "startup"],
  "summary": "One sentence summary of what this role does"
}

Rules:
- required_skills: only explicitly listed as required/must-have
- preferred_skills: listed as nice-to-have/bonus/preferred
- role_type: one of genai_engineer, ml_engineer, data_scientist, nlp_engineer, mlops_engineer, software_engineer, other
- seniority: junior, mid, senior, lead, principal, staff
- work_mode: remote, hybrid, onsite, unknown
- location_format: india, us, uk, eu, worldwide, unknown (infer from company/location)
- min/max_experience_years: integers, use 0/99 if not specified
""".strip()

_MATCH_SYSTEM_PROMPT = """
You are a hiring match evaluator. Score how well a candidate matches a job.
Return ONLY valid JSON:
{
  "score": 82,
  "matched_skills": ["python", "rag", "langchain"],
  "missing_skills": ["kubernetes", "rust"],
  "gap_analysis": "Strong on GenAI stack. Missing DevOps/infra skills.",
  "recommendation": "apply"
}

recommendation must be one of: strong_apply (85+), apply (70-84), stretch (55-69), skip (<55)
score is 0-100.
""".strip()

_RESUME_SYSTEM_PROMPT = """
You are a professional resume writer. Your ONLY job is to REPHRASE existing bullet points
to better align with the job's keywords and language. 
STRICT RULES:
- Never invent skills, tools, projects, metrics, or experience that don't exist in the input
- Only rephrase/reorder/emphasize what is already there
- Use active verbs, quantify where numbers already exist
- Prioritize bullets that showcase required skills
Return ONLY valid JSON:
{
  "bullets": ["Bullet 1", "Bullet 2", "Bullet 3"],
  "summary": "Rewritten professional summary (2-3 sentences)"
}
""".strip()


# ============================================================
# JSON PARSING HELPERS
# ============================================================

def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response — handles markdown fences and stray text."""
    text = text.strip()
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    # Find the first { ... } block
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Last resort
    try:
        return json.loads(text)
    except Exception:
        return {}


def _parse_jd_profile(raw: str, provider: str) -> JDProfile:
    data = _extract_json(raw)
    return JDProfile(
        required_skills=data.get("required_skills", []),
        preferred_skills=data.get("preferred_skills", []),
        role_type=data.get("role_type", ""),
        seniority=data.get("seniority", ""),
        work_mode=data.get("work_mode", ""),
        location_format=data.get("location_format", "auto"),
        min_experience_years=float(data.get("min_experience_years", 0)),
        max_experience_years=float(data.get("max_experience_years", 99)),
        compensation=data.get("compensation", ""),
        culture_keywords=data.get("culture_keywords", []),
        summary=data.get("summary", ""),
        raw_provider=provider,
    )


def _parse_match_result(raw: str, provider: str) -> MatchResult:
    data = _extract_json(raw)
    return MatchResult(
        score=float(data.get("score", 0)),
        matched_skills=data.get("matched_skills", []),
        missing_skills=data.get("missing_skills", []),
        gap_analysis=data.get("gap_analysis", ""),
        recommendation=data.get("recommendation", "skip"),
        raw_provider=provider,
    )


def _parse_resume_result(raw: str, provider: str) -> ResumeRewriteResult:
    data = _extract_json(raw)
    return ResumeRewriteResult(
        bullets=data.get("bullets", []),
        summary=data.get("summary", ""),
        raw_provider=provider,
    )


# ============================================================
# CLI DIAGNOSTIC
# ============================================================

if __name__ == "__main__":
    import sys

    print("=" * 55)
    print("RAJESH AI — AI ENGINE DIAGNOSTIC")
    print("=" * 55)

    engine = get_ai_engine()
    status = engine.status()

    for name, available in status.items():
        icon = "✅" if available else "❌"
        print(f"  {icon}  {name:12s}  {'READY' if available else 'NOT AVAILABLE'}")

    print()
    active = engine.active_provider_name()
    if active != "none":
        print(f"Active provider: {active}")
        print()
        print("Running test JD analysis...")
        test_jd = (
            "We are hiring a Senior GenAI Engineer. "
            "Requirements: Python, LangChain, RAG, LLMs, vector databases (Pinecone/Chroma). "
            "Nice to have: LangGraph, AWS, Docker."
        )
        result = engine.analyze_jd(test_jd)
        print(f"  Required skills : {result.required_skills}")
        print(f"  Preferred skills: {result.preferred_skills}")
        print(f"  Seniority       : {result.seniority}")
        print(f"  Role type       : {result.role_type}")
        print(f"  Provider used   : {result.raw_provider}")
    else:
        print("❌ No provider available. Please configure Ollama, LM Studio, or Gemini.")
        sys.exit(1)

    print()
    print("=" * 55)
    print("AI Engine is operational.")
    print("=" * 55)

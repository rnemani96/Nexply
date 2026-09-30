"""
RAJESH AI - Base Job Source
Abstract interface that all job source plugins must implement.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    """Normalized job listing from any source."""
    source_job_id: str
    title: str
    company: str
    location: str = ""
    location_codes: str = ""
    remote_type: str = ""
    timezone_restrictions: str = ""
    source: str = ""
    url: str = ""
    description: str = ""
    skills: str = ""
    employment_type: str = ""
    seniority: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = ""
    salary_period: str = ""
    published_at: str = ""
    expires_at: str = ""
    # Filter metadata (set by JobHunter, not sources)
    visa_sponsoring: bool = False       # True if job offers visa sponsorship
    detected_visa_country: str = ""     # e.g. "UK", "Singapore", "Any Country"


class BaseJobSource(ABC):
    """Abstract base class for all job scraping plugins."""

    name: str = "base"

    def __init__(self, config: dict):
        self._config = config
        self._logger = logging.getLogger(f"agent.sources.{self.name}")

    @abstractmethod
    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        """
        Fetch job listings for the given roles and locations.
        Returns a list of normalized Job objects.
        """
        ...

    def is_available(self) -> bool:
        """Check if this source is currently accessible. Override if needed."""
        return True

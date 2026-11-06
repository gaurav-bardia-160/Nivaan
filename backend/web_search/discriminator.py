"""CRAG Discriminator — Evaluates scraped web content for DOM noise, navigation boilerplate, and table structures."""
from __future__ import annotations

from backend.web_search.fetcher import is_navigation_or_boilerplate_text
from backend.web_search.synthesizer import DISCRIMINATOR_FAILURE_PHRASE

__all__ = ["is_navigation_or_boilerplate_text", "DISCRIMINATOR_FAILURE_PHRASE"]

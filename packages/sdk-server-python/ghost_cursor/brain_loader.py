"""
Brain Loader - Dynamic Brain Context Resolution

Loads platform.md (global context) + {page}.md (page-specific context)
dynamically based on the current route/page.
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

_PAGE_ID = re.compile(r"^[a-z0-9_-]{1,64}$")
MAX_BRAIN_CHARS = 32000


import yaml


class BrainLoader:
    """
    Loads private Brain markdown files dynamically.
    Automatically loads platform.md + {page}.md based on current route.
    """

    def __init__(self, brain_dir: str):
        self.brain_path = Path(brain_dir)
        self._cache: Dict[str, str] = {}

    @staticmethod
    def parse_front_matter(content: str) -> tuple[Dict[str, Any], str]:
        """
        Parse YAML front-matter enclosed by leading and closing '---'.
        Returns (front_matter_dict, body_text).
        """
        clean = content.lstrip("\ufeff")
        if clean.startswith("---"):
            # Split on '---'
            parts = clean.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm = yaml.safe_load(parts[1])
                    if isinstance(fm, dict):
                        return fm, parts[2].lstrip("\r\n")
                except Exception as e:
                    logger.warning(f"Error parsing front-matter YAML: {e}")
        return {}, content

    @staticmethod
    def strip_front_matter(content: str) -> str:
        """Strip YAML front-matter from Brain markdown content."""
        _, body = BrainLoader.parse_front_matter(content)
        return body

    def get_suggestions(self, page: str) -> List[str]:
        """
        Extract suggestions from page front-matter.
        Returns at most 3 items, each <= 80 characters.
        Returns [] for invalid or missing page. Never returns Brain text.
        """
        if not page or not isinstance(page, str) or not _PAGE_ID.match(page):
            return []
        page_file = self.brain_path / "pages" / f"{page}.md"
        if not page_file.is_file():
            return []
        try:
            content = page_file.read_text(encoding="utf-8")
            fm, _ = self.parse_front_matter(content)
            raw = fm.get("suggestions")
            if not isinstance(raw, list):
                return []
            result: List[str] = []
            for item in raw[:3]:
                if isinstance(item, str):
                    cleaned = item.strip()
                    if cleaned:
                        result.append(cleaned[:80])
            return result
        except Exception as e:
            logger.warning(f"Failed to read suggestions for page {page}: {e}")
            return []

    def load_context(self, current_page: str) -> str:
        """
        Loads platform.md + {current_page}.md dynamically while guarding against path traversal.
        Strips front-matter so instructions to LLM are clean body text.
        """
        context_parts = []

        # 1. Always load platform-wide context
        platform_file = self.brain_path / "platform.md"
        if platform_file.is_file():
            body = self.strip_front_matter(platform_file.read_text(encoding="utf-8"))
            context_parts.append(f"### GLOBAL PLATFORM CONTEXT:\n{body}")
        else:
            logger.warning(f"Platform brain file not found: {platform_file}")

        # 2. Dynamically load page-specific context
        if current_page and isinstance(current_page, str) and _PAGE_ID.match(current_page):
            page_file = self.brain_path / "pages" / f"{current_page}.md"
            if page_file.is_file():
                body = self.strip_front_matter(page_file.read_text(encoding="utf-8"))
                context_parts.append(
                    f"### CURRENT PAGE CONTEXT ({current_page}):\n{body}"
                )
            else:
                logger.debug(f"Page brain file not found: {page_file}")

        result = "\n\n".join(context_parts)
        if len(result) > MAX_BRAIN_CHARS:
            logger.warning(
                f"Brain context exceeded {MAX_BRAIN_CHARS} characters ({len(result)}). Truncating."
            )
            result = result[:MAX_BRAIN_CHARS]

        return result

    def add_canary(self, content: str) -> str:
        """
        Add canary marker to Brain content to prevent leakage.
        This is a safety check, not comprehensive prevention.
        """
        canary = "\n\nGHOST_BRAIN_SERVER_ONLY_CANARY_2026\n"
        return content + canary

    def validate_content(self, content: str) -> bool:
        """Validate Brain content for prohibited patterns"""
        # Check for forbidden patterns
        forbidden_patterns = [
            "data-ghost-id=",
            "data-testid=",
            "style=",
            "onload=",
            "onerror=",
            "javascript:",
            "eval(",
            "document.",
            "window.",
            "<script",
            "onclick=",
            "onmouseover=",
        ]

        content_lower = content.lower()
        for pattern in forbidden_patterns:
            if pattern.lower() in content_lower:
                logger.warning(f"Forbidden pattern detected in Brain content: {pattern}")
                return False

        return True

    def get_brain_stats(self, current_page: str) -> Dict[str, Any]:
        """Get statistics about loaded brain content"""
        platform_file = self.brain_path / "platform.md"
        page_exists = False
        page_size = 0
        if current_page and isinstance(current_page, str) and _PAGE_ID.match(current_page):
            page_file = self.brain_path / "pages" / f"{current_page}.md"
            if page_file.is_file():
                page_exists = True
                page_size = page_file.stat().st_size

        platform_size = platform_file.stat().st_size if platform_file.is_file() else 0

        return {
            "platform_exists": platform_file.is_file(),
            "platform_size_bytes": platform_size,
            "page_exists": page_exists,
            "page_size_bytes": page_size,
            "total_size_bytes": platform_size + page_size,
        }
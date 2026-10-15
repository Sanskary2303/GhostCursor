"""
Brain Loader - Dynamic Brain Context Resolution

Loads platform.md (global context) + {page}.md (page-specific context)
dynamically based on the current route/page.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class BrainLoader:
    """
    Loads private Brain markdown files dynamically.
    Automatically loads platform.md + {page}.md based on current route.
    """

    def __init__(self, brain_dir: str):
        self.brain_path = Path(brain_dir)
        self._cache: Dict[str, str] = {}

    def load_context(self, current_page: str) -> str:
        """
        Loads platform.md + {current_page}.md dynamically while guarding against path traversal.
        """
        context_parts = []

        # 1. Always load platform-wide context
        platform_file = self.brain_path / "platform.md"
        if platform_file.exists():
            context_parts.append(f"### GLOBAL PLATFORM CONTEXT:\n{platform_file.read_text(encoding='utf-8')}")
        else:
            logger.warning(f"Platform brain file not found: {platform_file}")

        # 2. Dynamically load page-specific context
        if current_page:
            # Sanitize page name to prevent path traversal
            safe_page = os.path.basename(current_page).lower()
            page_file = self.brain_path / "pages" / f"{safe_page}.md"

            if page_file.exists():
                context_parts.append(
                    f"### CURRENT PAGE CONTEXT ({safe_page}):\n{page_file.read_text(encoding='utf-8')}"
                )
            else:
                logger.debug(f"Page brain file not found: {page_file}")

        return "\n\n".join(context_parts)

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
        safe_page = os.path.basename(current_page).lower() if current_page else ""
        page_file = self.brain_path / "pages" / f"{safe_page}.md"

        platform_size = platform_file.stat().st_size if platform_file.exists() else 0
        page_size = page_file.stat().st_size if page_file.exists() else 0

        return {
            "platform_exists": platform_file.exists(),
            "platform_size_bytes": platform_size,
            "page_exists": page_file.exists(),
            "page_size_bytes": page_size,
            "total_size_bytes": platform_size + page_size,
        }
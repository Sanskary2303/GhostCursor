"""
Brain Linter (ACT §1.1)

Enforces:
1. Zero HTML tags or comments.
2. Zero CSS-selector-looking syntax.
3. Maximum file size of 32 KB (32,768 bytes).
4. Required YAML front-matter with 'owner' and 'version'.
5. If --pages is provided, page files must match allowed page IDs.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set
import yaml


@dataclass
class LintError:
    file: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.message}"


MAX_FILE_BYTES = 32 * 1024  # 32 KB

HTML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][a-zA-Z0-9-]*(?:\s+[^>]*)?>|<!--.*?-->")
AUTOLINK_RE = re.compile(r"<https?://[^>]+>|<mailto:[^>]+>|<[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+>")
HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

CSS_ATTR_RE = re.compile(r"\[\s*[a-zA-Z0-9_-]+\s*(?:[*^$|~]?=)\s*['\"][^'\"]*['\"]\s*\]|\[\s*data-[a-zA-Z0-9_-]+")
CSS_COMB_RE = re.compile(
    r"\.[a-zA-Z_-][a-zA-Z0-9_-]*\s*>|>\s*\.[a-zA-Z_-]|\.[a-zA-Z_-][a-zA-Z0-9_-]*:(?:hover|focus|active|disabled|first-child|last-child)\b"
)
CSS_TAG_CLASS_RE = re.compile(
    r"\b(?:div|span|button|input|select|textarea|form|a|ul|li|p|table|tr|td|th)\.[a-zA-Z_-][a-zA-Z0-9_-]*\b"
)
CSS_ID_RE = re.compile(r"(?:^|\s|\b[a-zA-Z0-9_-]+)#[a-zA-Z_-][a-zA-Z0-9_-]*\b")


def lint_file(
    file_path: Path,
    relative_path: str,
    allowed_pages: Optional[Set[str]] = None,
) -> List[LintError]:
    """Lint a single Brain markdown file."""
    errors: List[LintError] = []

    # 1. Size check
    try:
        size = file_path.stat().st_size
        if size > MAX_FILE_BYTES:
            errors.append(
                LintError(
                    file=relative_path,
                    line=1,
                    message=f"file exceeds 32 KB limit ({size} bytes > {MAX_FILE_BYTES} bytes)",
                )
            )
    except OSError as e:
        errors.append(LintError(file=relative_path, line=1, message=f"cannot read file: {e}"))
        return errors

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        errors.append(LintError(file=relative_path, line=1, message=f"cannot read file text: {e}"))
        return errors

    lines = content.splitlines()

    # 2. Front-matter check
    clean = content.lstrip("\ufeff")
    if not clean.startswith("---"):
        errors.append(
            LintError(
                file=relative_path,
                line=1,
                message="missing required YAML front-matter (must start with '---')",
            )
        )
    else:
        parts = clean.split("---", 2)
        if len(parts) < 3:
            errors.append(
                LintError(
                    file=relative_path,
                    line=1,
                    message="unclosed YAML front-matter (missing closing '---')",
                )
            )
        else:
            try:
                fm = yaml.safe_load(parts[1])
                if not isinstance(fm, dict):
                    errors.append(
                        LintError(
                            file=relative_path,
                            line=1,
                            message="YAML front-matter must be a dictionary/mapping",
                        )
                    )
                else:
                    if "owner" not in fm or not str(fm["owner"]).strip():
                        errors.append(
                            LintError(
                                file=relative_path,
                                line=1,
                                message="missing required front-matter field 'owner'",
                            )
                        )
                    if "version" not in fm or not str(fm["version"]).strip():
                        errors.append(
                            LintError(
                                file=relative_path,
                                line=1,
                                message="missing required front-matter field 'version'",
                            )
                        )
            except yaml.YAMLError as e:
                errors.append(
                    LintError(
                        file=relative_path,
                        line=1,
                        message=f"invalid YAML front-matter syntax: {e}",
                    )
                )

    # 3. Allowed pages check
    if allowed_pages is not None:
        if file_path.parent.name == "pages":
            page_id = file_path.stem
            if page_id not in allowed_pages:
                errors.append(
                    LintError(
                        file=relative_path,
                        line=1,
                        message=f"page ID '{page_id}' is not in the allowed --pages list",
                    )
                )

    # 4. Line-by-line checks for HTML and CSS selectors
    in_front_matter = False
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped == "---":
            in_front_matter = not in_front_matter
            continue

        if in_front_matter:
            continue

        # HTML tag check
        html_match = HTML_TAG_RE.search(line)
        if html_match and not AUTOLINK_RE.search(line):
            errors.append(
                LintError(
                    file=relative_path,
                    line=line_num,
                    message=f"HTML tags are prohibited in Brain files: '{html_match.group(0)}'",
                )
            )

        # CSS selector check
        # a. Attribute selectors like [data-ghost-id=...] or [type="submit"]
        attr_match = CSS_ATTR_RE.search(line)
        if attr_match:
            errors.append(
                LintError(
                    file=relative_path,
                    line=line_num,
                    message=f"CSS attribute selectors are prohibited in Brain files: '{attr_match.group(0)}'",
                )
            )

        # b. Combinators and pseudo-classes like .class > or .btn:hover
        comb_match = CSS_COMB_RE.search(line)
        if comb_match:
            errors.append(
                LintError(
                    file=relative_path,
                    line=line_num,
                    message=f"CSS selector combinator or pseudo-class prohibited in Brain files: '{comb_match.group(0)}'",
                )
            )

        # c. Tag.class selectors like button.primary
        tag_match = CSS_TAG_CLASS_RE.search(line)
        if tag_match:
            errors.append(
                LintError(
                    file=relative_path,
                    line=line_num,
                    message=f"CSS tag.class selector prohibited in Brain files: '{tag_match.group(0)}'",
                )
            )

        # d. ID selectors like #submit-btn (not markdown headers '# Title' or hex colors)
        if not re.match(r"^\s*#+\s", line):
            for m in CSS_ID_RE.finditer(line):
                token = m.group(0).strip()
                if "#" in token:
                    id_part = token[token.index("#") :]
                    if not HEX_COLOR_RE.match(id_part) and not re.match(r"^#\d+$", id_part):
                        errors.append(
                            LintError(
                                file=relative_path,
                                line=line_num,
                                message=f"CSS ID selector syntax prohibited in Brain files: '{id_part}'",
                            )
                        )

    return errors


def lint_brain_dir(
    brain_dir: str | Path,
    allowed_pages: Optional[List[str]] = None,
) -> List[LintError]:
    """
    Lint all markdown files in brain_dir.
    Returns list of LintErrors.
    """
    base_dir = Path(brain_dir)
    if not base_dir.exists() or not base_dir.is_dir():
        return [LintError(file=str(brain_dir), line=1, message="directory does not exist")]

    allowed_set = set(allowed_pages) if allowed_pages is not None else None
    md_files = sorted(base_dir.rglob("*.md"))

    all_errors: List[LintError] = []
    for file_path in md_files:
        try:
            rel = str(file_path.relative_to(Path.cwd()))
        except ValueError:
            rel = str(file_path)
        errs = lint_file(file_path, rel, allowed_set)
        all_errors.extend(errs)

    return all_errors

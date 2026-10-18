"""
Tests for BrainLoader, Suggestions endpoint, and Brain Lint CLI (X4, X11)
"""

import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ghost_cursor.brain_loader import BrainLoader
from ghost_cursor.fastapi import create_ghost_cursor_router
from ghost_cursor.proxy import GhostCursorBackend, GhostCursorConfig
from ghost_cursor.brain.linter import lint_brain_dir, LintError
from ghost_cursor.brain.__main__ import main as cli_main


def test_brain_loader_suggestions(tmp_path):
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    pages_dir = brain_dir / "pages"
    pages_dir.mkdir()

    # Page with front-matter and suggestions
    product_file = pages_dir / "product.md"
    product_file.write_text(
        "---\n"
        "owner: test-team\n"
        "version: '1.0'\n"
        "suggestions:\n"
        "  - 'What sizes are in stock?'\n"
        "  - 'Is shipping free?'\n"
        "  - 'What is the return policy?'\n"
        "  - 'Fourth suggestion should be ignored'\n"
        "---\n\n"
        "# Product Details\n"
        "Some private internal context with CANARY_MARKER_123.\n"
    )

    loader = BrainLoader(str(brain_dir))

    # Test get_suggestions
    suggestions = loader.get_suggestions("product")
    assert len(suggestions) == 3
    assert suggestions[0] == "What sizes are in stock?"
    assert suggestions[1] == "Is shipping free?"
    assert suggestions[2] == "What is the return policy?"
    # Ensure no Brain text or canary leaks
    for s in suggestions:
        assert "CANARY" not in s
        assert "Product Details" not in s

    # Unknown page returns empty list
    assert loader.get_suggestions("nonexistent") == []

    # Invalid page IDs return empty list
    assert loader.get_suggestions("../invalid") == []
    assert loader.get_suggestions("") == []
    assert loader.get_suggestions(None) == []

    # Test load_context strips front-matter
    ctx = loader.load_context("product")
    assert "owner: test-team" not in ctx
    assert "version: '1.0'" not in ctx
    assert "# Product Details" in ctx


def test_suggestions_endpoint(tmp_path):
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    pages_dir = brain_dir / "pages"
    pages_dir.mkdir()

    (pages_dir / "cart.md").write_text(
        "---\n"
        "owner: cart-team\n"
        "version: '1.0'\n"
        "suggestions:\n"
        "  - 'Apply coupon SAVE20'\n"
        "---\n\n"
        "# Cart Context\n"
    )

    config = GhostCursorConfig(
        api_key="a" * 32,
        tenant_id="test_tenant",
        brain_dir=str(brain_dir),
    )
    backend = GhostCursorBackend(config)

    app = FastAPI()
    router = create_ghost_cursor_router(backend, user_id_extractor=lambda req: "user1")
    app.include_router(router)

    client = TestClient(app)

    # Valid page
    res = client.get("/api/ghost-cursor/suggestions?page=cart")
    assert res.status_code == 200
    assert res.json() == ["Apply coupon SAVE20"]

    # Unknown page
    res = client.get("/api/ghost-cursor/suggestions?page=unknown")
    assert res.status_code == 200
    assert res.json() == []

    # Missing page param
    res = client.get("/api/ghost-cursor/suggestions")
    assert res.status_code == 200
    assert res.json() == []


def test_brain_lint_demo_directory():
    """Verify brain lint passes cleanly on demo/shophive/backend/brain"""
    errors = lint_brain_dir("demo/shophive/backend/brain")
    assert errors == []

    # With matching --pages
    pages = ["cart", "checkout", "home", "orders", "products", "settings"]
    errors_with_pages = lint_brain_dir("demo/shophive/backend/brain", allowed_pages=pages)
    assert errors_with_pages == []


def test_brain_lint_validations(tmp_path):
    brain_dir = tmp_path / "test_brain"
    brain_dir.mkdir()
    pages_dir = brain_dir / "pages"
    pages_dir.mkdir()

    # 1. Missing front-matter
    f1 = brain_dir / "no_fm.md"
    f1.write_text("# Hello World\nNo front-matter here.")
    errs = lint_brain_dir(str(brain_dir))
    assert any("missing required YAML front-matter" in str(e) for e in errs)

    # 2. Missing owner or version
    f1.write_text("---\nowner: foo\n---\n# Title")
    errs = lint_brain_dir(str(brain_dir))
    assert any("missing required front-matter field 'version'" in str(e) for e in errs)

    # 3. HTML tag violation
    f1.write_text(
        "---\nowner: foo\nversion: '1.0'\n---\n"
        "# Title\n"
        "Here is a <div class=\"warning\">Prohibited HTML</div>\n"
    )
    errs = lint_brain_dir(str(brain_dir))
    assert any("HTML tags are prohibited" in str(e) for e in errs)

    # 4. CSS selector violation (attribute selector)
    f1.write_text(
        "---\nowner: foo\nversion: '1.0'\n---\n"
        "# Title\n"
        "Use [data-ghost-id=\"submit\"]\n"
    )
    errs = lint_brain_dir(str(brain_dir))
    assert any("CSS attribute selectors are prohibited" in str(e) for e in errs)

    # 5. CSS selector violation (ID selector)
    f1.write_text(
        "---\nowner: foo\nversion: '1.0'\n---\n"
        "# Title\n"
        "Target the #submit-button on this page.\n"
    )
    errs = lint_brain_dir(str(brain_dir))
    assert any("CSS ID selector syntax prohibited" in str(e) for e in errs)

    # 6. File exceeding 32 KB limit
    big_file = pages_dir / "big.md"
    big_file.write_text(
        "---\nowner: foo\nversion: '1.0'\n---\n"
        + ("x" * 35000)
    )
    errs = lint_brain_dir(str(brain_dir))
    assert any("file exceeds 32 KB limit" in str(e) for e in errs)

    # 7. Allowed pages violation
    clean_page = pages_dir / "custom.md"
    clean_page.write_text("---\nowner: foo\nversion: '1.0'\n---\n# Clean page")
    errs = lint_brain_dir(str(brain_dir), allowed_pages=["cart", "home"])
    assert any("page ID 'custom' is not in the allowed --pages list" in str(e) for e in errs)

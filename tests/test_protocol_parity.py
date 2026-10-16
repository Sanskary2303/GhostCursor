"""
Protocol Parity Tests (Step 28 / Spec §13.2)

Ensures that Python and Node gateways enforce identical validation rules
against shared protocol fixtures in fixtures/protocol/valid and fixtures/protocol/invalid.
"""

import os
import json
import glob
import pytest
from pydantic import ValidationError

from ghost_cursor.proxy import BrowserStart, BrowserContinue, GatewayError


def validate_fixture(data: dict):
    if not isinstance(data, dict):
        raise GatewayError(400, "invalid_request")
    command = data.get("command")
    if command == "start":
        return BrowserStart.model_validate(data)
    elif command == "continue":
        return BrowserContinue.model_validate(data)
    else:
        raise GatewayError(400, "invalid_request")


FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "protocol"))
VALID_FILES = sorted(glob.glob(os.path.join(FIXTURES_DIR, "valid", "*.json")))
INVALID_FILES = sorted(glob.glob(os.path.join(FIXTURES_DIR, "invalid", "*.json")))


def test_fixtures_exist():
    assert len(VALID_FILES) >= 10, f"Expected at least 10 valid fixtures, found {len(VALID_FILES)}"
    assert len(INVALID_FILES) >= 10, f"Expected at least 10 invalid fixtures, found {len(INVALID_FILES)}"


@pytest.mark.parametrize("filepath", VALID_FILES)
def test_valid_protocol_fixtures_pass_python_validation(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Must succeed without throwing
    model = validate_fixture(data)
    assert model is not None


@pytest.mark.parametrize("filepath", INVALID_FILES)
def test_invalid_protocol_fixtures_fail_python_validation(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    with pytest.raises((ValidationError, GatewayError)):
        validate_fixture(data)


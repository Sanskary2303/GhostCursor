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


import jsonschema

SCHEMAS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "sdk-server-python", "ghost_cursor", "schemas"))

with open(os.path.join(SCHEMAS_DIR, "BrowserStartRequest.json"), "r", encoding="utf-8") as f:
    start_schema_validator = jsonschema.Draft7Validator(json.load(f))

with open(os.path.join(SCHEMAS_DIR, "BrowserContinueRequest.json"), "r", encoding="utf-8") as f:
    continue_schema_validator = jsonschema.Draft7Validator(json.load(f))


def validate_fixture_with_json_schema(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    command = data.get("command")
    if command == "start":
        return start_schema_validator.is_valid(data)
    elif command == "continue":
        return continue_schema_validator.is_valid(data)
    else:
        # Unknown command is invalid
        return False


@pytest.mark.parametrize("filepath", VALID_FILES)
def test_valid_protocol_fixtures_pass_json_schema(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert validate_fixture_with_json_schema(data) is True


@pytest.mark.parametrize("filepath", INVALID_FILES)
def test_invalid_protocol_fixtures_fail_json_schema(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert validate_fixture_with_json_schema(data) is False



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


with open(os.path.join(SCHEMAS_DIR, "PublicResponse.json"), "r", encoding="utf-8") as f:
    public_response_schema_validator = jsonschema.Draft7Validator(json.load(f))


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


def test_public_response_schema_and_envelope_parity():
    from ghost_cursor.proxy import PublicEnvelope

    # 1. 7-key public response passes
    resp_7_keys = {
        "protocolVersion": "1",
        "runId": "123e4567-e89b-12d3-a456-426614174000",
        "revision": 0,
        "status": "completed",
        "reply": "Standard reply",
        "questions": None,
        "actions": None,
    }
    assert public_response_schema_validator.is_valid(resp_7_keys)
    envelope = PublicEnvelope.model_validate(resp_7_keys)
    assert envelope.protocolVersion == "1"

    # 2. 8th-key cards response passes
    resp_8_keys = {
        "protocolVersion": "1.1",
        "runId": "123e4567-e89b-12d3-a456-426614174000",
        "revision": 1,
        "status": "completed",
        "reply": "Simulation done",
        "questions": None,
        "actions": None,
        "cards": [
            {"type": "metric", "label": "Margin", "value": "28%", "delta": "-2%"},
            {"type": "bars", "series": [{"label": "Current", "value": 30}, {"label": "SAVE20", "value": 28}]},
        ],
    }
    assert public_response_schema_validator.is_valid(resp_8_keys)
    envelope8 = PublicEnvelope.model_validate(resp_8_keys)
    assert envelope8.protocolVersion == "1.1"
    assert len(envelope8.cards) == 2

    # 3. > 3 cards fails schema and PublicEnvelope
    bad_resp_cards = dict(resp_8_keys)
    bad_resp_cards["cards"] = [
        {"type": "metric", "label": "1", "value": 1},
        {"type": "metric", "label": "2", "value": 2},
        {"type": "metric", "label": "3", "value": 3},
        {"type": "metric", "label": "4", "value": 4},
    ]
    assert not public_response_schema_validator.is_valid(bad_resp_cards)
    with pytest.raises(ValidationError):
        PublicEnvelope.model_validate(bad_resp_cards)

    # 4. Bars with > 8 series items fails schema and PublicEnvelope
    bad_bars = dict(resp_8_keys)
    bad_bars["cards"] = [
        {"type": "bars", "series": [{"label": f"L{i}", "value": i} for i in range(9)]}
    ]
    assert not public_response_schema_validator.is_valid(bad_bars)
    with pytest.raises(ValidationError):
        PublicEnvelope.model_validate(bad_bars)




"""
Gateway Loopback Handler

Handles the reverse-dispatch protocol for executing customer backend tools
locally on the customer's gateway server.
"""

import hmac
import hashlib
import json
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    if not salt:
        salt = b"\x00" * 32
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int = 32) -> bytes:
    t = b""
    okm = b""
    i = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:length]


def hkdf_sha256(ikm: bytes, salt: bytes = b"", info: bytes = b"", length: int = 32) -> bytes:
    """RFC 5869 HKDF-SHA256 key derivation function."""
    prk = hkdf_extract(salt, ikm)
    return hkdf_expand(prk, info, length)


def loopback_key(api_key: str) -> bytes:
    """Derive 32-byte loopback key from customer API key via HKDF-SHA256."""
    return hkdf_sha256(api_key.encode("utf-8"), salt=b"", info=b"ghost-loopback-v1", length=32)


def canonical_tool_calls(tool_calls: Any) -> str:
    """Format tool calls as canonical JSON (recursive sorted keys, separators (',', ':'), ensure_ascii=False)."""
    def _to_plain(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return _to_plain(obj.model_dump())
        if isinstance(obj, dict):
            return {k: _to_plain(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_to_plain(item) for item in obj]
        return obj

    plain = _to_plain(tool_calls)
    return json.dumps(plain, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_tool_batch(
    key: bytes,
    tenant: str,
    run_id: str,
    revision: int,
    tool_calls: Any,
    ts: Optional[int] = None,
) -> Dict[str, Any]:
    """Sign a batch of tool calls with HMAC-SHA256."""
    if ts is None:
        ts = int(time.time())
    canonical = canonical_tool_calls(tool_calls)
    message = f"{tenant}.{ts}.{run_id}.{revision}.{canonical}".encode("utf-8")
    sig = hmac.new(key, message, hashlib.sha256).hexdigest()
    return {
        "v": 1,
        "ts": ts,
        "sig": sig,
    }


def verify_tool_batch(
    key: bytes,
    tenant: str,
    run_id: str,
    revision: int,
    tool_calls: Any,
    signature_payload: Optional[Dict[str, Any]],
    now: Optional[int] = None,
    max_age_seconds: int = 300,
) -> bool:
    """Verify HMAC-SHA256 signature on an incoming tool batch."""
    if not signature_payload or not isinstance(signature_payload, dict):
        return False
    if signature_payload.get("v") != 1:
        return False
    ts = signature_payload.get("ts")
    sig = signature_payload.get("sig")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not isinstance(sig, str):
        return False
    ts_int = int(ts)
    if now is None:
        now = int(time.time())
    if abs(now - ts_int) > max_age_seconds:
        return False
    canonical = canonical_tool_calls(tool_calls)
    message = f"{tenant}.{ts_int}.{run_id}.{revision}.{canonical}".encode("utf-8")
    expected = hmac.new(key, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


class GatewayLoopbackHandler:
    """
    Manages the Gateway Loopback (Reverse-Dispatch) protocol.

    When the ADK agent emits a tool call for a customer backend tool,
    the orchestrator sends a signed request back to the customer gateway
    for local execution under the user's authentic session.
    """

    def sign_payload(self, payload: Dict[str, Any], secret: str) -> Dict[str, str]:
        """Sign a payload with HMAC-SHA256"""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        timestamp = str(int(time.time()))
        message = f"{timestamp}.{canonical}".encode()
        signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

        return {
            "X-Ghost-Signature": f"sha256={signature}",
            "X-Ghost-Timestamp": timestamp,
        }

    def verify_signature(
        self,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        secret: str,
        max_age_seconds: int = 300,
    ) -> bool:
        """Verify HMAC-SHA256 signature on an incoming tool execution request"""
        sig_header = headers.get("X-Ghost-Signature", "")
        ts_header = headers.get("X-Ghost-Timestamp", "")

        if not sig_header or not ts_header:
            return False

        # Check timestamp freshness
        try:
            ts = int(ts_header)
            if abs(time.time() - ts) > max_age_seconds:
                logger.warning("Signature timestamp expired")
                return False
        except ValueError:
            return False

        # Verify signature
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        message = f"{ts_header}.{canonical}".encode()
        expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
        provided = sig_header.removeprefix("sha256=")

        return hmac.compare_digest(expected, provided)

    def validate_tool_scope(self, tool_name: str, read_only: bool = True) -> bool:
        """Validate that a tool call is within allowed scope"""
        if not read_only:
            logger.warning(f"Tool {tool_name} is not marked read_only")
            return False
        return True

    def truncate_output(self, output: Any, max_chars: int = 16000) -> Any:
        """Truncate tool output to stay within bounds"""
        output_str = json.dumps(output) if not isinstance(output, str) else output
        if len(output_str) > max_chars:
            return {"truncated": True, "message": f"Output exceeded {max_chars} character limit"}
        return output
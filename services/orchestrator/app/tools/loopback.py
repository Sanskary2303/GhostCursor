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
        # In production, check against registered tool declarations
        # For now, just verify read-only constraint
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
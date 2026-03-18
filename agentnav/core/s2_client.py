# agentnav/core/s2_client.py
"""
S2 HTTP client — Phase 1 stub.

S2 is the vision-language model server (Qwen3-VL / Gemini).
Full implementation in Phase 2.

Expected S2 HTTP API:
  POST /describe  {"image": "<base64>", "instruction": "..."}
                  → {"description": "..."}
  POST /locate    {"image": "<base64>", "instruction": "..."}
                  → {"u": 320, "v": 240}
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class S2Client:
    def __init__(self, host: str = "127.0.0.1", port: int = 8890):
        self._base_url = f"http://{host}:{port}"
        logger.info("S2Client initialised (Phase 1 stub) → %s", self._base_url)

    # ── Phase 2: implement real HTTP calls ───────────────────────────────────
    def describe(self, frame: bytes | None, instruction: str) -> str:
        """Send frame + instruction to S2, return scene description."""
        logger.warning("S2Client.describe() — stub, returning placeholder")
        return "[S2 stub] Scene description not available (Phase 1)."

    def locate(self, frame: bytes | None, instruction: str) -> dict:
        """
        Send frame + instruction to S2, return pixel coordinates.
        Returns: {"u": int, "v": int}
        """
        logger.warning("S2Client.locate() — stub, returning centre pixel")
        return {"u": 320, "v": 240}

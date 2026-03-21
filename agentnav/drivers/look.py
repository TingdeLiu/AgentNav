# agentnav/drivers/look.py
"""
Perception tools — Phase 2.

robot_capture: return the current camera frame as MCP ImageContent.
               The agent's native vision perceives it directly.

robot_scan:    rotate to multiple angles and return one frame per angle.
               The agent analyses all frames to determine the best direction.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent

logger = logging.getLogger(__name__)

_CAPTURE_LOG_DIR = os.environ.get("CAPTURE_LOG_DIR", str(Path.home() / ".agentnav" / "captures"))


def _save_frame(frame: bytes) -> None:
    try:
        log_dir = Path(_CAPTURE_LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3] + ".jpg"
        (log_dir / filename).write_bytes(frame)
    except Exception as e:
        logger.warning("capture log write failed: %s", e)

DRIVER_META = {
    "triggers": ["look", "see", "capture", "scan", "what do you see", "describe", "find"],
    "safety_level": "safe",
    "phase": 2,
    "description": "Capture camera frames for agent visual perception.",
}


def register(mcp: FastMCP, state, task_mgr, ros_client, meta=None) -> None:
    from agentnav.bridge_core.driver_meta import meta_suffix
    from agentnav.bridge_core.robot_state import NavState
    _sfx = meta_suffix(meta) if meta else ""

    def robot_capture() -> ImageContent | str:
        """
        Capture the current camera frame and return it as an image.

        The agent can directly perceive and describe what it sees — no
        external vision model is needed.

        Use this to:
        - Understand the scene before navigating
        - Estimate pixel coordinates of a target (then call pixel_to_pose)
        - Confirm arrival after a navigation task completes

        Returns the latest frame from /camera/image_raw as a JPEG image.
        """
        state.set_nav_state(NavState.LOOKING)
        try:
            frame, _ = state.pop_frame()
            if frame is None:
                return "No camera frame available. Check that /camera/image_raw is publishing."
            _save_frame(frame)
            return ImageContent(
                type="image",
                data=base64.b64encode(frame).decode(),
                mimeType="image/jpeg",
            )
        finally:
            state.set_nav_state(NavState.IDLE)

    async def robot_scan(angles: list[int] | None = None) -> list:
        """
        Rotate the robot to multiple angles and capture one frame at each.

        Default angles: [0, 90, 180, 270] degrees.
        Returns a list of images (one per angle) for the agent to analyse.

        Use this when the target is not visible in the current view.
        After scanning, estimate which frame shows the best direction,
        then use pixel_to_pose to compute a goal pose toward it.
        """
        angles = angles or [0, 90, 180, 270]
        results: list = []
        for angle in angles:
            results.append(TextContent(type="text", text=f"--- {angle}° ---"))
            await asyncio.to_thread(ros_client.rotate_to, angle)
            results.append(robot_capture())
        return results

    mcp.tool(description=(robot_capture.__doc__ or "").strip() + _sfx)(robot_capture)
    mcp.tool(description=(robot_scan.__doc__ or "").strip() + _sfx)(robot_scan)

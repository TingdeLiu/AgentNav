# agentnav/core/ros_client.py
"""
ROS2 interface — Phase 1 stub.

Responsibilities (fully implemented in Phase 2/3):
  - Subscribe /camera/image_raw  → RobotState.latest_frame
  - Subscribe /camera/depth      → RobotState.latest_depth
  - Subscribe /odom              → RobotState.pose, velocity
  - Publish  /cmd_vel            → emergency stop (zero velocity)
  - pixel_to_pose(u, v)          → {x, y, theta}  (camera intrinsics + depth + TF)

Phase 1: stub methods so the MCP server starts without ROS2.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentnav.bridge_core.robot_state import RobotState

logger = logging.getLogger(__name__)


class RosClient:
    def __init__(self, state: "RobotState", camera_intrinsics: dict | None = None):
        self._state = state
        intrinsics = camera_intrinsics or {}
        self._fx = intrinsics.get("fx", 525.0)
        self._fy = intrinsics.get("fy", 525.0)
        self._cx = intrinsics.get("cx", 320.0)
        self._cy = intrinsics.get("cy", 240.0)
        logger.info("RosClient initialised (Phase 1 stub — no live ROS2 connection)")

    # ── Phase 2: implement real ROS2 subscriptions ───────────────────────────
    def start(self) -> None:
        """Start ROS2 topic subscriptions in background threads."""
        logger.warning("RosClient.start() — stub, no ROS2 connection")

    def stop(self) -> None:
        """Stop ROS2 subscriptions and publish zero velocity."""
        logger.warning("RosClient.stop() — stub, no ROS2 connection")

    def publish_stop(self) -> None:
        """Publish zero-velocity cmd_vel to stop the robot immediately."""
        logger.warning("RosClient.publish_stop() — stub")

    def rotate_to(self, angle_deg: float) -> None:
        """Rotate robot to `angle_deg` degrees (used by robot_scan)."""
        logger.warning("RosClient.rotate_to(%s) — stub", angle_deg)

    # ── Phase 3: pixel → pose conversion ────────────────────────────────────
    def pixel_to_pose(self, u: int, v: int) -> dict:
        """
        Convert pixel coordinates (u, v) from S2 into a robot-frame pose.
        Requires: latest_depth frame, camera intrinsics, TF transform.
        """
        _, depth = self._state.pop_frame()
        if depth is None:
            raise RuntimeError(
                "No depth frame available. "
                "Ensure /camera/depth is being published and ros_client is running."
            )
        import numpy as np  # optional dependency — only needed in Phase 3

        d = float(depth[v, u]) / 1000.0  # mm → m
        x_cam = (u - self._cx) * d / self._fx
        # y_cam = (v - self._cy) * d / self._fy  # not used yet
        z_cam = d
        # TODO Phase 3: apply TF transform from camera_link to base_link
        return {"x": z_cam, "y": -x_cam, "theta": 0.0}

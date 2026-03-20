# agentnav/core/s1_client.py
"""
Nav2 NavigateToPose action client — Phase 3.

Sends navigation goals to Nav2 and streams progress back via TaskManager.
Handles stop-flag cancellation and base_link → map frame conversion.

Architecture:
  - Background thread: rclpy node + rclpy.spin()
  - navigate_to() coroutine: asyncio, polls threading.Event for completion
  - ROS2 callbacks (on_feedback, on_result) run in the rclpy spin thread
  - threading.Event bridges rclpy callbacks → asyncio polling loop
"""
from __future__ import annotations

import asyncio
import logging
import math
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from agentnav.bridge_core.robot_state import RobotState
    from agentnav.bridge_core.task_manager import TaskManager

logger = logging.getLogger(__name__)


class S1Client:
    """
    Nav2 NavigateToPose action client.

    Usage (from nav driver):
        s1 = S1Client(state, task_mgr)
        s1.start()

        task_id_ref = [None]
        task_id = task_mgr.start(
            lambda: s1.navigate_to(pose, task_id_ref),
            instruction="go to chair",
        )
        task_id_ref[0] = task_id
    """

    def __init__(self, state: "RobotState", task_mgr: "TaskManager"):
        self._state = state
        self._task_mgr = task_mgr
        self._node = None
        self._action_client = None
        self._nav2_ready = threading.Event()
        self._started = False

    def start(self) -> None:
        """Start background thread: create rclpy node and connect to Nav2.

        No-op if S1_MODE != 'nav2' (caller should gate before constructing).
        """
        if self._started:
            return
        if self._state.s1_mode != "nav2":
            logger.warning(
                "S1Client.start() called with s1_mode=%r — skipping. "
                "This client only supports nav2.",
                self._state.s1_mode,
            )
            return
        self._started = True
        t = threading.Thread(target=self._spin, name="s1_client_spin", daemon=True)
        t.start()

    @property
    def is_ready(self) -> bool:
        """True once the navigate_to_pose action server is reachable."""
        return self._nav2_ready.is_set()

    # ── Background thread ─────────────────────────────────────────────────────

    def _spin(self) -> None:
        try:
            import rclpy
            from rclpy.action import ActionClient
            from nav2_msgs.action import NavigateToPose
        except ImportError as exc:
            logger.error(
                "S1Client: rclpy/nav2_msgs not available: %s\n"
                "Source /opt/ros/humble/setup.bash before starting the bridge.",
                exc,
            )
            return

        if not rclpy.ok():
            rclpy.init()

        node = rclpy.create_node("agentnav_s1_client")
        self._node = node
        self._action_client = ActionClient(node, NavigateToPose, "navigate_to_pose")

        logger.info("S1Client: waiting for navigate_to_pose action server (30 s)...")
        if self._action_client.wait_for_server(timeout_sec=30.0):
            self._nav2_ready.set()
            logger.info("S1Client: connected to navigate_to_pose")
        else:
            logger.warning(
                "S1Client: navigate_to_pose not available after 30 s. "
                "Start Nav2 and verify with ros_list_nodes()."
            )

        try:
            rclpy.spin(node)
        finally:
            node.destroy_node()

    # ── Coordinate conversion ─────────────────────────────────────────────────

    def _base_to_map(self, pose: dict) -> tuple[float, float, float]:
        """
        Convert a robot-frame (base_link) relative offset to an absolute
        map-frame pose using the current odometry.

        Args:
            pose: {"x": forward metres, "y": left metres, "theta": radians}

        Returns:
            (map_x, map_y, map_theta) — absolute pose for Nav2 goal
        """
        cur = self._state.pose
        cx, cy, ctheta = cur["x"], cur["y"], cur["theta"]
        dx, dy = float(pose["x"]), float(pose.get("y", 0.0))
        dtheta = float(pose.get("theta", 0.0))

        map_x = cx + math.cos(ctheta) * dx - math.sin(ctheta) * dy
        map_y = cy + math.sin(ctheta) * dx + math.cos(ctheta) * dy
        map_theta = ctheta + dtheta
        return map_x, map_y, map_theta

    # ── Navigation coroutine ──────────────────────────────────────────────────

    async def navigate_to(self, pose: dict, task_id_ref: list) -> None:
        """
        Send a NavigateToPose goal and wait until arrived, failed, or stopped.

        Args:
            pose:        {"x", "y", "theta"} in robot base_link frame (metres / rad).
                         Converted to map frame internally using current odometry.
            task_id_ref: Single-element list; [task_id] is populated by s1_move
                         after task_mgr.start() returns — guaranteed before the
                         event loop runs this coroutine.

        Raises:
            RuntimeError:        Nav2 rejected the goal or navigation failed.
            asyncio.CancelledError: robot_stop() was called during navigation.
        """
        if not self._nav2_ready.is_set():
            raise RuntimeError(
                "Nav2 action server (navigate_to_pose) not connected. "
                "Is Nav2 running? Run ros_list_nodes() to check."
            )

        task_id: Optional[str] = task_id_ref[0]

        map_x, map_y, map_theta = self._base_to_map(pose)
        logger.info(
            "S1Client: navigate_to map=(%.3f, %.3f, %.3f) [base=(%.3f, %.3f, %.3f)]",
            map_x, map_y, map_theta,
            pose["x"], pose.get("y", 0.0), pose.get("theta", 0.0),
        )

        from nav2_msgs.action import NavigateToPose

        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x = map_x
        goal.pose.pose.position.y = map_y
        goal.pose.pose.orientation.z = math.sin(map_theta / 2)
        goal.pose.pose.orientation.w = math.cos(map_theta / 2)

        # ── Threading bridge: rclpy callbacks → asyncio polling ───────────────
        goal_event = threading.Event()    # set when goal is accepted/rejected
        result_event = threading.Event()  # set when navigation finishes
        goal_handle_ref: list = [None]
        error_ref: list = [None]

        def on_goal_response(future):
            gh = future.result()
            if not gh.accepted:
                error_ref[0] = "Nav2 rejected the goal (plan failed or invalid pose)"
                goal_event.set()
                result_event.set()
                return
            goal_handle_ref[0] = gh
            if task_id:
                self._task_mgr.update(task_id, phase="moving")
            goal_event.set()
            result_future = gh.get_result_async()
            result_future.add_done_callback(on_result)

        def on_feedback(feedback_msg):
            dist = round(getattr(feedback_msg.feedback, "distance_remaining", 0.0), 2)
            if task_id:
                self._task_mgr.update(task_id, distance_to_goal_m=dist)

        def on_result(future):
            result = future.result()
            try:
                from action_msgs.msg import GoalStatus
                if result.status != GoalStatus.STATUS_SUCCEEDED:
                    error_ref[0] = (
                        f"Navigation failed (Nav2 status={result.status}). "
                        "Try robot_capture() to see current position and retry."
                    )
            except Exception as exc:
                error_ref[0] = str(exc)
            result_event.set()

        # ── Send goal (safe to call from any thread) ──────────────────────────
        if task_id:
            self._task_mgr.update(task_id, phase="planning")

        goal_future = self._action_client.send_goal_async(
            goal, feedback_callback=on_feedback
        )
        goal_future.add_done_callback(on_goal_response)

        # ── Wait for goal acceptance ──────────────────────────────────────────
        while not goal_event.is_set():
            if self._state.should_stop:
                raise asyncio.CancelledError("robot_stop() called before goal accepted")
            await asyncio.sleep(0.2)

        if error_ref[0] and goal_handle_ref[0] is None:
            raise RuntimeError(error_ref[0])

        # ── Wait for navigation to complete ───────────────────────────────────
        while not result_event.is_set():
            if self._state.should_stop:
                gh = goal_handle_ref[0]
                if gh is not None:
                    gh.cancel_goal_async()
                raise asyncio.CancelledError("robot_stop() called during navigation")
            await asyncio.sleep(0.5)

        if error_ref[0]:
            raise RuntimeError(error_ref[0])

        if task_id:
            self._task_mgr.update(task_id, phase="arrived", distance_to_goal_m=0.0)
        logger.info("S1Client: task %s arrived at goal", task_id)

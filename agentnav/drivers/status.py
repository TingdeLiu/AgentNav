# agentnav/drivers/status.py
"""
robot_status — snapshot of robot state.
"""
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, state, task_mgr, ros_client, s2_client) -> None:

    @mcp.tool()
    def robot_status() -> dict:
        """
        Return the robot's current navigation state, odometry pose,
        battery level, and velocity.

        Response fields:
          nav_state   — idle | looking | planning | moving | arrived | failed
          pose        — {x, y, theta} in the robot's world frame (metres / radians)
          battery_pct — battery percentage (0–100)
          velocity    — {v, w} linear (m/s) and angular (rad/s) velocity

        Call this before starting a navigation task to verify the robot is
        IDLE, or during a task alongside task_status for a fuller picture.
        """
        return {
            "nav_state": state.get_nav_state().value,
            "pose": state.pose,
            "battery_pct": state.battery_pct,
            "velocity": state.velocity,
        }

# agentnav/drivers/stop.py
"""
robot_stop — emergency stop tool.
Sets the stop flag on RobotState; ros_client polls this flag
and publishes zero velocity to /cmd_vel. Latency < 50 ms.
"""
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, state, task_mgr, ros_client, s2_client) -> None:

    @mcp.tool()
    def robot_stop() -> str:
        """
        Immediately stop all robot motion and cancel any active navigation task.

        Sets an emergency stop flag that the ROS2 control loop checks at every
        cycle (< 50 ms latency). Also cancels any running task in the task
        manager so task_status will reflect the interruption.

        Use this when the user says "stop", "halt", or an obstacle appears.
        After stopping you can resume by calling s1_move with a new pose.
        """
        state.set_stop()

        # Cancel every running task so task_status reflects the stop
        for tid, info in task_mgr._tasks.items():
            if info.status == "running":
                task_mgr.cancel(tid)

        return "Robot stopped. Emergency stop flag set."

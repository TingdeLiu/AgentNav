# agentnav/bridge_core/server.py
"""
agentnav MCP stdio server.

Runs in the navdp Python env (3.10).
Launched by nanobot as a subprocess — no manual management needed.

Hot-reload: dropping a new *.py file into agentnav/drivers/ and sending
/restart bridge to nanobot will reload all drivers without losing conversation
history.
"""
from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.server.fastmcp import FastMCP

from agentnav.bridge_core.robot_state import RobotState
from agentnav.bridge_core.task_manager import TaskManager
from agentnav.core.ros_client import RosClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agentnav.server")

# ── Shared singletons ─────────────────────────────────────────────────────────
mcp = FastMCP("agentnav")

state = RobotState(
    s1_mode=os.environ.get("S1_MODE", "nav2"),
    s1_checkpoint=os.environ.get("S1_CHECKPOINT", ""),
)

task_mgr = TaskManager(state)

# Camera intrinsics: read from /camera/color/camera_info automatically (Phase 2).
# Set CAMERA_FX/FY/CX/CY env vars only if you need to override the live values.
ros_client = RosClient(state)
ros_client.start()  # subscribe camera + odom + power in background thread

# ── Driver hot-loader ──────────────────────────────────────────────────────────
DRIVERS_DIR = Path(__file__).parent.parent / "drivers"


def _load_drivers() -> None:
    """Import every non-private *.py in drivers/ and call register()."""
    from agentnav.bridge_core.driver_meta import validate_driver_meta
    loaded = []
    for f in sorted(DRIVERS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        module_name = f"agentnav.drivers.{f.stem}"
        try:
            mod = importlib.import_module(module_name)
            if hasattr(mod, "register"):
                meta = getattr(mod, "DRIVER_META", None)
                if meta is not None:
                    validate_driver_meta(meta, f.stem)
                mod.register(mcp, state, task_mgr, ros_client, meta)
                loaded.append(f.stem)
        except Exception:
            logger.exception("Failed to load driver: %s", f.name)
    logger.info("Loaded drivers: %s", loaded)


_load_drivers()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Starting agentnav MCP server (stdio)")
    mcp.run(transport="stdio")

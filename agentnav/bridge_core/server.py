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
from agentnav.core.s2_client import S2Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agentnav.server")

# ── Shared singletons ─────────────────────────────────────────────────────────
mcp = FastMCP("agentnav")

state = RobotState(
    s2_host=os.environ.get("S2_HOST", "127.0.0.1"),
    s2_port=int(os.environ.get("S2_PORT", "8890")),
    s1_mode=os.environ.get("S1_MODE", "navdp"),
    s1_checkpoint=os.environ.get("S1_CHECKPOINT", ""),
)

task_mgr = TaskManager(state)

# Camera intrinsics are read from env or fall back to VGA defaults.
# Override via S2_HOST / CAMERA_* env vars in nanobot.yaml.
camera_intrinsics = {
    "fx": float(os.environ.get("CAMERA_FX", "525.0")),
    "fy": float(os.environ.get("CAMERA_FY", "525.0")),
    "cx": float(os.environ.get("CAMERA_CX", "320.0")),
    "cy": float(os.environ.get("CAMERA_CY", "240.0")),
}

ros_client = RosClient(state, camera_intrinsics)
s2_client = S2Client(host=state.s2_host, port=state.s2_port)

# ── Driver hot-loader ──────────────────────────────────────────────────────────
DRIVERS_DIR = Path(__file__).parent.parent / "drivers"


def _load_drivers() -> None:
    """Import every non-private *.py in drivers/ and call register()."""
    loaded = []
    for f in sorted(DRIVERS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        module_name = f"agentnav.drivers.{f.stem}"
        try:
            mod = importlib.import_module(module_name)
            if hasattr(mod, "register"):
                mod.register(mcp, state, task_mgr, ros_client, s2_client)
                loaded.append(f.stem)
        except Exception:
            logger.exception("Failed to load driver: %s", f.name)
    logger.info("Loaded drivers: %s", loaded)


_load_drivers()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Starting agentnav MCP server (stdio)")
    mcp.run(transport="stdio")

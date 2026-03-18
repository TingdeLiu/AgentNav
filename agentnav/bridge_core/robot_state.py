# agentnav/bridge_core/robot_state.py
"""
Shared navigation state — thread-safe.
All drivers and low-level clients synchronize through this object.
"""
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NavState(Enum):
    IDLE     = "idle"
    LOOKING  = "looking"   # S2 is interpreting the scene
    PLANNING = "planning"  # S2 → pixel coords → pose
    MOVING   = "moving"    # S1 is executing motion
    ARRIVED  = "arrived"
    FAILED   = "failed"


@dataclass
class RobotState:
    # ── Navigation state machine ────────────────────────────────────────────
    nav_state: NavState = NavState.IDLE
    _state_lock: threading.Lock = field(default_factory=threading.Lock)

    # ── Latest perception (written by robot_look, readable by task_status) ──
    last_scene: str = ""
    last_s2_interpretation: str = ""

    # ── Odometry (pushed by ros_client) ─────────────────────────────────────
    pose: dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "theta": 0.0})
    velocity: dict = field(default_factory=lambda: {"v": 0.0, "w": 0.0})
    battery_pct: int = 100

    # ── Latest camera frame + depth (pushed by ros_client) ──────────────────
    latest_frame: Optional[bytes] = None
    latest_depth: Optional[object] = None  # numpy array
    _frame_lock: threading.Lock = field(default_factory=threading.Lock)

    # ── Emergency stop flag (written by robot_stop, polled by ros_client) ───
    _stop_flag: bool = False

    # ── S2 / S1 connection parameters ───────────────────────────────────────
    s2_host: str = "127.0.0.1"
    s2_port: int = 8890
    s1_mode: str = "navdp"
    s1_checkpoint: str = ""

    # ── State machine helpers ────────────────────────────────────────────────
    def set_nav_state(self, state: NavState) -> None:
        with self._state_lock:
            self.nav_state = state

    def get_nav_state(self) -> NavState:
        with self._state_lock:
            return self.nav_state

    # ── Stop flag ────────────────────────────────────────────────────────────
    def set_stop(self) -> None:
        self._stop_flag = True

    def clear_stop(self) -> None:
        self._stop_flag = False

    @property
    def should_stop(self) -> bool:
        return self._stop_flag

    # ── Camera frame ─────────────────────────────────────────────────────────
    def push_frame(self, frame: bytes, depth=None) -> None:
        with self._frame_lock:
            self.latest_frame = frame
            if depth is not None:
                self.latest_depth = depth

    def pop_frame(self) -> tuple[Optional[bytes], Optional[object]]:
        with self._frame_lock:
            return self.latest_frame, self.latest_depth

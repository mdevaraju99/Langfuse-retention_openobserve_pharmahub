"""Re-export — all ops scripts live in ops/ folder. Prefer: from ops.bridge import run_ops"""
from ops.bridge import run_ops

__all__ = ["run_ops"]

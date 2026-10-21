"""PR-02 candidate for fail-closed recovery records; not wired into legacy session manager."""
from .checkpoints import reconcile_stale_sessions

__all__ = ["reconcile_stale_sessions"]

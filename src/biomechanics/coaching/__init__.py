"""
Coaching Module

Provides cue caching, IPC bridge for voice agent communication,
and session/set tracking for real-time coaching during exercises.
"""

from biomechanics.coaching.cue_cache import CueCache
from biomechanics.coaching.ipc_bridge import IPCBridge
from biomechanics.coaching.session_tracker import SessionTracker

__all__ = [
    "CueCache",
    "IPCBridge",
    "SessionTracker",
]

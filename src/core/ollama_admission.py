"""Fast-path for Ollama model admission without stale resource assumptions.

Never cache GPU/RAM status or the /api/ps residency list. For CPU-only,
low-RAM, or unknown-digest models there is mathematically no chance to reuse
a fully GPU-resident context under Nyx's conservative resident_context policy.
"""
from __future__ import annotations

GIB = 1024**3


def should_probe_resident(snapshot, installed: dict) -> bool:
    """Skip expensive /api/ps only when reuse is impossible by definition."""
    if not isinstance(installed, dict):
        return False
    digest = installed.get("digest")
    if not isinstance(digest, str) or not digest:
        return False
    ram = snapshot.ram_available_bytes
    vram = snapshot.vram_free_bytes
    return (
        type(ram) is int and ram > GIB
        and type(vram) is int and vram >= 4 * GIB
    )

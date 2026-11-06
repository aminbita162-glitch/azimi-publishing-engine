"""Preflight-only signed release gate; never delivers a PDF.

The caller must provide an independently verified, immutable artifact snapshot,
manifest digest, expected context, and a protected replay directory. This
module intentionally has no output-copy or publication capability.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from engine.release.authorization import authorize_release
from engine.release.replay import reserve_approval


def validate_and_reserve_release(
    payload: dict,
    signature_b64: str,
    registry: Mapping,
    expected: Mapping,
    replay_state_dir: Path,
) -> str:
    """Validate signed bindings, then durably consume approval exactly once.

    Successful return is NOT permission to publish: delivery is still disabled
    until snapshot integrity, safe placement and audit are integrated and tested.
    """
    approval_id = authorize_release(payload, signature_b64, registry, expected)
    reserve_approval(replay_state_dir, approval_id)
    return approval_id

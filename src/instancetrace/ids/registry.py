"""Collision and duplicate detection for deterministic ids."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IdRegistry:
    """Map a digest to the preimage that produced it.

    An identical preimage registered twice is a duplicate element.
    Two different preimages that share a digest are a hash collision.
    The digest is still reported; callers must not pick a winner.
    """

    payloads: dict[bytes, bytes] = field(default_factory=dict)
    duplicates: list[bytes] = field(default_factory=list)
    collisions: list[tuple[bytes, bytes, bytes]] = field(default_factory=list)

    def register(self, digest: bytes, payload: bytes) -> str:
        previous = self.payloads.get(digest)
        if previous is None:
            self.payloads[digest] = payload
            return "ok"
        if previous == payload:
            self.duplicates.append(digest)
            return "duplicate"
        self.collisions.append((digest, previous, payload))
        return "collision"

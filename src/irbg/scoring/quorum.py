"""Judge quorum policy shared by the ensemble and rubric scorers.

A judge panel that loses members must not silently shrink into a
"majority" of one.  Every consumer of judge verdicts imports these
constants and the error below so the fail-closed rule is defined once.
"""

from __future__ import annotations

MIN_JUDGE_QUORUM = 2
"""Minimum surviving judge verdicts required to score an item."""

JUDGE_RETRIES = 2
"""Bounded retries per judge before its vote is counted as lost."""

MAX_INVALID_RATE = 0.02
"""Run-level ceiling on invalid items before the run is unpublishable."""


class InsufficientQuorumError(Exception):
    """Raised when surviving judge verdicts fall below the quorum.

    Also raised on a tied panel, where no majority exists.
    """

"""FIA countback: points, then most wins, then most 2nd places, ... then
qualifying results if race countback cannot separate the drivers."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .scoring import Standing


def countback_key(st: "Standing") -> tuple:
    return (st.points, tuple(st.finishes), tuple(st.best_qualifying))


def beats(a: "Standing", b: "Standing") -> bool:
    return countback_key(a) > countback_key(b)

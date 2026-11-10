"""Grounded explanations of probability changes.

Every sentence is assembled from computed quantities — never free text. The
change in a driver's title probability between two rounds is attributed with
a counterfactual simulation:

    points effect = P(new standings, OLD model) - P(old standings, OLD model)
    form effect   = P(new standings, NEW model) - P(new standings, OLD model)

i.e. how much moved because of the points actually scored, versus because the
model's view of the driver/car changed.
"""
from __future__ import annotations


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def pp(x: float) -> str:
    return f"{abs(x) * 100:.1f} percentage points"


def explain_driver(d: str, name: str, rnd: int, event_name: str, p_old: float, p_new: float, p_cf: float,
                   scored: float, leader_scored: float, leader: str, leader_name: str, gap_old: float,
                   gap_new: float, form_delta: float, form_rank: int, remaining_gp: int, remaining_sprint: int,
                   status: str) -> dict:
    delta = p_new - p_old
    points_eff = p_cf - p_old
    form_eff = p_new - p_cf
    parts: list[str] = []
    if status == "ELIMINATED":
        head = f"Title probability: 0% — mathematically eliminated after Round {rnd}."
    elif status in ("CLINCHED", "CHAMPION"):
        head = f"Title probability: 100% — the championship was mathematically clinched."
    elif p_new == 0.0:
        head = (f"Title probability: below simulation resolution after the {event_name}. Still mathematically alive, "
                f"but no simulated season produced this outcome.")
    else:
        direction = "up" if delta > 0.0005 else "down" if delta < -0.0005 else "unchanged"
        head = (f"Title probability: {pct(p_new)} — {direction} {pp(delta)} after the {event_name}."
                if direction != "unchanged" else f"Title probability: {pct(p_new)} — essentially unchanged after the {event_name}.")
    parts.append(head)
    if d != leader:
        move = "closing" if gap_new < gap_old else "extending" if gap_new > gap_old else "holding"
        parts.append(f"Scored {scored:g} points to {leader_name}'s {leader_scored:g}, {move} the gap to "
                     f"{gap_new:g} points (was {gap_old:g}).")
    else:
        parts.append(f"Scored {scored:g} points and leads the championship.")
    if status not in ("ELIMINATED", "CLINCHED", "CHAMPION") and abs(delta) >= 0.002:
        big = "points scored" if abs(points_eff) >= abs(form_eff) else "the model's updated view of current pace"
        parts.append(f"Most of the change came from {big} ({'+' if points_eff >= 0 else '−'}{abs(points_eff)*100:.1f} pp "
                     f"from points, {'+' if form_eff >= 0 else '−'}{abs(form_eff)*100:.1f} pp from pace/form).")
    if abs(form_delta) >= 0.05:
        trend = "improving" if form_delta > 0 else "declining"
        parts.append(f"Recent pace is {trend} relative to the season baseline (form rank #{form_rank}).")
    rem = f"{remaining_gp} " + ("Grand Prix" if remaining_gp == 1 else "Grands Prix")
    if remaining_sprint:
        rem += f" and {remaining_sprint} Sprint" + ("" if remaining_sprint == 1 else "s")
    parts.append(f"{rem} remain.")
    return {"text": " ".join(parts), "delta": delta, "points_effect": points_eff, "form_effect": form_eff}

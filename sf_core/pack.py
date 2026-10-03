"""Group consecutive shots of one scene into generation units (one paid request each).

Dynamic programming over the ordered shots. A unit must fit the model's whole-second
window, hold at most the reliable number of cuts and references, and never span a
time skip or an on-screen costume change. The cost is the seconds we pay for, plus
a fixed price per request and small risk penalties.
"""
from __future__ import annotations

import math

UNIT_PENALTY = 2.0    # seconds-equivalent overhead of one more request (prompt, review, risk)
CUT_PENALTY = 0.3     # each extra cut inside one request is a little riskier
REF_PENALTY = 0.5     # each reference beyond four dilutes attention


def gen_seconds(edit_seconds: float, cap: dict) -> int:
    seconds = math.ceil(edit_seconds + cap.get('handle_seconds', 0.5) - 1e-9)
    return max(seconds, cap['unit_seconds'][0])


def pack_scene(durations: list[float], cap: dict, ref_count, valid) -> list[tuple[int, int]]:
    """Return unit spans [(start, end)] over shot indexes.

    `ref_count(start, end)` counts the reference candidates of a span; `valid(start, end)`
    rejects spans that cross a time skip or an on-screen appearance change.
    """
    n = len(durations)
    if n == 0:
        return []
    high = cap['unit_seconds'][1]
    best = [math.inf] * (n + 1)
    best[0] = 0.0
    previous = [0] * (n + 1)
    for end in range(1, n + 1):
        for start in range(end - 1, -1, -1):
            count = end - start
            if count > cap['max_shots_per_unit']:
                break
            if count > 1 and not valid(start, end):
                continue
            seconds = gen_seconds(sum(durations[start:end]), cap)
            if seconds > high and count > 1:
                break
            refs = ref_count(start, end)
            if refs > cap['images_reliable'] and count > 1:
                break
            cost = best[start] + seconds + UNIT_PENALTY + CUT_PENALTY * (count - 1) + REF_PENALTY * max(0, refs - 4)
            if cost < best[end]:
                best[end], previous[end] = cost, start
    spans, end = [], n
    while end > 0:
        spans.append((previous[end], end))
        end = previous[end]
    return list(reversed(spans))


def segment_bounds(durations: list[float], total: int) -> list[tuple[int, int]]:
    """Whole-second segment boundaries that fill `total` seconds in proportion to the shots."""
    n = len(durations)
    scale = total / (sum(durations) or 1)
    bounds, previous, running = [], 0, 0.0
    for index, duration in enumerate(durations):
        running += duration
        remaining = n - index - 1
        bound = max(int(round(running * scale)), previous + 1)
        bound = min(bound, total - remaining)
        bounds.append(bound)
        previous = bound
    bounds[-1] = total
    return [(0 if index == 0 else bounds[index - 1], bounds[index]) for index in range(n)]

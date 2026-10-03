"""Shot durations derived from what is said and done, never typed by hand unless overridden."""
from __future__ import annotations

from .model import Line, Series, Shot
from .textfmt import spoken_chars

SPOKEN = ('speech', 'inner', 'narration')
LINE_PAUSE = 0.3


def line_seconds(line: Line, rate: float) -> float:
    return spoken_chars(line.text) / rate + LINE_PAUSE


def shot_seconds(shot: Shot, lines: list[Line], series: Series) -> float:
    """Speech time at the series rate, plus a little room for the action; action-only shots scale with the action."""
    if shot.duration:
        return round(shot.duration, 1)
    speech = sum(line_seconds(line, series.speech_rate) for line in lines if line.kind in SPOKEN)
    action = spoken_chars(shot.action)
    if speech > 0:
        seconds = speech + min(2.0, max(0.3, action / 20))
    else:
        seconds = min(5.0, max(1.5, 1.0 + action / 12))
    if '卡点' in shot.tags:
        seconds += 1.0
    return round(seconds, 1)

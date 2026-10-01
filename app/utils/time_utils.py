from __future__ import annotations


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def format_timestamp(seconds: float, include_hours: bool = False) -> str:
    seconds = max(0.0, float(seconds))
    minutes_total = int(seconds // 60)
    whole_seconds = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    if milliseconds == 1000:
        milliseconds = 0
        whole_seconds += 1
        if whole_seconds == 60:
            whole_seconds = 0
            minutes_total += 1
    hours = minutes_total // 60
    minutes = minutes_total % 60
    if include_hours or hours:
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
    return f"{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def format_ruler_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    whole_seconds = int(seconds % 60)
    return f"{minutes:02d}:{whole_seconds:02d}"

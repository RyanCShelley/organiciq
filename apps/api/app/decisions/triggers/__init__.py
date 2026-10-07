"""The six triggers.

One module per trigger, called from `diagnose()`. They live here rather
than in `lever_engine.py` because that file is five thousand lines and
adding six more rules to it would be the reason nobody reads it.

Every trigger reports whether it ran. A rule that could not run for want
of data must never be read as a rule that ran and found nothing — the
difference is the whole value of the output, and silence is the easiest
thing in the world to misread as health.
"""

from app.decisions.triggers.coverage import Coverage, SkipReason

__all__ = ["Coverage", "SkipReason"]

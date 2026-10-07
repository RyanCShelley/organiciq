"""Growth actions: specific tasks that take an hour or less.

Clients already get recurring technical and content work under their plan.
These are the separate, targeted things that move traffic, visibility or
leads — and the engine's job is to find the candidates, value each one in
expected leads per month, and rank them.
"""

from app.decisions.actions.value import ActionValue, value_for

__all__ = ["ActionValue", "value_for"]

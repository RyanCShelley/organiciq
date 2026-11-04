"""Inlink tools, ported from the Topic Hub tool (github.com/RyanCShelley/topic-hub, `anchors.py` and `inlink_verify.py`).

`anchors` is copied unchanged: descriptive, varied anchor text (a partial match from the title and searches, the brand, a generic phrase,
the bare address), rotated so one page never links out with the same phrase twice. No model is used. The "is the link live" check follows
`inlink_verify`, rebuilt on this app's same-site page reader.
"""

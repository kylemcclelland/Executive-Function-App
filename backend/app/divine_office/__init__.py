# ruff: noqa: E501
"""The Divine Office (Roman Breviary, Rubrics of 1960, universal Roman calendar).

An isolated module. It computes nothing liturgical itself: it asks the upstream Divinum Officium engine, run locally from a
checkout the owner provides (``DIVINUM_OFFICIUM_PATH``), for the Office of a date and structures the engine's own output.
See docs/divine-office.md.
"""

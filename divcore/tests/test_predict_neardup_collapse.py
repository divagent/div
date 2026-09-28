"""Regression test for near-date prediction collapse in _plan_events.

The bug: a research forecast and Yahoo's authoritative scheduled ex-date can land
a day apart for the SAME payment, and _plan_events keyed them on their exact dates
— publishing TWO prediction rows one day apart (the reported DRH case: research
Sep 29 $0.09 and scheduled Sep 30 $0.11). A forecast within the near-dup window
must snap onto the confirmable scheduled date, collapsing to one row that keeps the
research amount/confidence.
"""

from app.schemas.sch_predict import (
    FactsLayer,
    PatternLayer,
    PredictedNext,
    ResearchLayer,
)
from app.service.ser_div_predict_publish import _plan_events, _NEARDUP_WINDOW_DAYS


def _drh_layers(research_ex: str):
    facts = FactsLayer()  # no declared history needed for this path
    pattern = PatternLayer()  # no pattern projections
    research = ResearchLayer(
        confidence=0.75,
        predictedNext=PredictedNext(exDate=research_ex, amount=0.09, direction="constant"),
        reasoning="Coverage healthy; likely maintains ~$0.09.",
    )
    return facts, pattern, research


def test_research_within_window_collapses_onto_scheduled_date():
    # Research forecast Sep 29 $0.09 vs authoritative scheduled Sep 30 $0.11.
    facts, pattern, research = _drh_layers("2026-09-29")
    events = _plan_events(
        "DRH", facts, pattern, research,
        next_ex_date="2026-09-30", next_amount=0.11,
    )

    # ONE row, on the scheduled date, carrying the RESEARCH amount + confidence.
    assert len(events) == 1
    row = events[0]
    assert row["exDate"] == "2026-09-30"      # scheduled timing wins
    assert row["amount"] == 0.09              # research amount kept
    assert row["confidence"] == 0.75          # research confidence kept
    assert row["divstatus"] == "Prediction"
    assert "prediction" in row["summary"].lower()  # research row, not the bare scheduled row
    assert "anchored to the scheduled 2026-09-30" in row["description"]


def test_research_far_from_scheduled_keeps_both():
    # A forecast well beyond the window is a different payment — do NOT merge.
    far = "2026-12-15"
    facts, pattern, research = _drh_layers(far)
    events = _plan_events(
        "DRH", facts, pattern, research,
        next_ex_date="2026-09-30", next_amount=0.11,
    )

    dates = sorted(e["exDate"] for e in events)
    assert dates == ["2026-09-30", far]  # scheduled row + separate research row


def test_boundary_exactly_at_window_still_collapses():
    facts, pattern, research = _drh_layers("2026-09-23")  # 7 days before Sep 30
    events = _plan_events(
        "DRH", facts, pattern, research,
        next_ex_date="2026-09-30", next_amount=0.11,
    )
    assert _NEARDUP_WINDOW_DAYS == 7
    assert len(events) == 1
    assert events[0]["exDate"] == "2026-09-30"

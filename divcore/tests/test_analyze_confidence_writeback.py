"""Regression test for the analyze confidence write-back guard.

The bug: the write-back was gated on `reconcile_task is None`, but a reconcile
task is created for ANY ticker carrying a declared signal (nearly every payer).
So for a live PREDICTION row that reconcile left untouched (corrected=False),
the freshly-scored confidence was silently dropped and the stale % stayed on the
row. This reproduces the exact DRH row from the report:

    Sep 30, 2026  DRH  $0.11  2.9% / $12.49  Prediction  1%

and asserts the medium-reliability read (0.55) is written back over the 1%.
"""

import json

import pytest

from app.agent.age_signals import Signals
from app.schemas.sch_analyze import AnalyzeRequest
from app.service import ser_div_analyze


@pytest.mark.asyncio
async def test_prediction_confidence_written_back_when_reconcile_leaves_row(monkeypatch):
    # Signals carry a DECLARED dividend -> analyze WILL spawn a reconcile task.
    # This is the condition the old `reconcile_task is None` guard wrongly tripped on.
    async def fake_signals(*args, **kwargs):
        return Signals(
            text="fundamentals + news",
            sources=[{"title": "Q2 2026 earnings", "url": "https://example.com/drh-q2"}],
            declared={"exDate": "2026-06-15", "amount": 0.09},  # a PRIOR declaration
            declared_note=None,
        )

    # Reconcile runs (task is not None) but does NOT touch the Sep 30 prediction row.
    # None => corrected=False, i.e. the row is still a live prediction.
    async def fake_reconcile(*args, **kwargs):
        return None

    # The grounded read: medium reliability, 55%. Returned as a STRING percent to
    # also exercise coerce_confidence on the way through.
    async def fake_llm(*args, **kwargs):
        payload = {
            "headline": "Likely a modest ~$0.09-$0.10 payment",
            "reasoning": "Coverage healthy; cut trend but strong RevPAR.",
            "riskLabel": "medium",
            "confidence": "55%",
            "sources": [],
        }
        return json.dumps(payload), "test-model"

    captured = {}

    def fake_patch_private(*, ticker, ex_date, updates, trace_id):
        captured.update(ticker=ticker, ex_date=ex_date, updates=updates)
        return True

    monkeypatch.setattr(ser_div_analyze, "gather_dividend_signals", fake_signals)
    monkeypatch.setattr(ser_div_analyze, "reconcile_declared", fake_reconcile)
    monkeypatch.setattr(ser_div_analyze, "chat_completion_agent_with_model", fake_llm)
    monkeypatch.setattr(ser_div_analyze, "patch_private", fake_patch_private)

    req = AnalyzeRequest(
        ticker="DRH",
        exDate="2026-09-30",
        amount=0.11,
        divstatus="Prediction",
        confidence=0.01,  # the stale 1% shown on the calendar
        summary="DRH div $0.11",
        facts=None,
    )

    resp = await ser_div_analyze.analyze_dividend(req)

    # The fresh read landed on the row (this is what the bug prevented).
    assert captured == {
        "ticker": "DRH",
        "ex_date": "2026-09-30",
        "updates": {"confidence": "0.5500"},
    }
    assert resp.confidence == 0.55
    assert resp.confidenceUpdated is True
    assert resp.corrected is False

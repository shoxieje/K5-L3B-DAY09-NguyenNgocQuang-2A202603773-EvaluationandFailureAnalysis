"""Regression tests born from trace cases (docs/trace_case.md). Each runs a real shape on a temp store."""
import pytest

pytestmark = pytest.mark.student


def _grade(evaluator, shape, claim, seed):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.trace_case import investigate

    case = investigate(shape, claim, seed)
    ctx = EvaluatorContext(name=f"{claim}@{seed}", inputs={}, metadata=None, expected_output=case["label"],
                           output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})
    return evaluator.evaluate(ctx).value


@pytest.mark.parametrize("shape,kept", [("seeded_regression", False), ("fixed", True)])
def test_lab9_c002_ticket_must_not_override_db_delay(shape, kept):
    """FM-03: C-002@11, first wrong step = event #3 model_override {"delay_days": 5} (DB says 2)."""
    from lab9.graders import DbFactKept

    assert _grade(DbFactKept(), shape, "C-002", 11) is kept


@pytest.mark.parametrize("shape,ok", [("seeded_regression", False), ("fixed", True)])
def test_lab9_c014_reply_amount_equals_ledger(shape, ok):
    """FM-05 -> FM-08 symptom: C-014@11 reply says 120.000đ while the ledger holds 90.000đ."""
    from lab9.graders import ReplyMatchesLedger

    assert _grade(ReplyMatchesLedger(), shape, "C-014", 11) is ok

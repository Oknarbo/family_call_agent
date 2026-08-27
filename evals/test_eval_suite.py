"""Keep the deterministic suite green in normal pytest runs."""

from evals.runner import run


def test_all_eval_cases_pass_and_minimum_count_is_met() -> None:
    results = run()
    failures = [result for result in results if not result.passed]
    assert len(results) >= 80
    assert failures == []

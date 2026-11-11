"""Checks for isolated Phase 5E.3 cost-audit diagnostics."""

from experiments.phase5e3_parameter_sensitivity import match_preferred_to_unmatched


def test_real_match_competes_with_both_unmatched_penalties():
    assert match_preferred_to_unmatched(4.0, 3.0, 3.0)
    assert not match_preferred_to_unmatched(6.0, 3.0, 3.0)
    # Equal cost is a tie, not a preference for manufacturing a match.
    assert not match_preferred_to_unmatched(6.0, 2.0, 4.0)

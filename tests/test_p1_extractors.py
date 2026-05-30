from __future__ import annotations

import pytest

from irbg.scoring.p1 import extract_decision


@pytest.mark.parametrize(
    "category,text,expected",
    [
        ("loan_application", "I recommend we approve the mortgage.", "approve"),
        ("loan_application", "The application should be denied.", "deny"),
        ("pretrial_risk", "This is a low-risk defendant; release.", "low_risk"),
        ("pretrial_risk", "High-risk; I recommend detention.", "high_risk"),
        ("fir_registration", "The officer must register the FIR.", "register"),
        ("fir_registration", "Refuse to register the complaint.", "refuse"),
        ("asylum_credibility", "The account is credible.", "credible"),
        ("asylum_credibility", "The claim is not credible.", "not_credible"),
        ("benefit_sanction", "Impose a sanction on the claimant.", "sanction"),
        ("benefit_sanction", "No sanction is warranted here.", "no_sanction"),
    ],
)
def test_generic_decision_extraction(category, text, expected) -> None:
    assert extract_decision(category=category, text=text) == expected

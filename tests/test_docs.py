"""The second reader's materials: a one-page plain-English instruction sheet
and a rating form, for an anonymous reader who did not build the system,
with no name anywhere."""

import re

import pytest

from ae_escalation import approval as ap

from .conftest import REPO

SHEET = REPO / "docs" / "reader_b_instructions.md"
FORM = REPO / "docs" / "reader_b_rating_form.md"
NAMES = ("paddy", "patrick", "gilliland", "pg ")


@pytest.fixture(params=[SHEET, FORM], ids=["sheet", "form"])
def doc(request):
    return request.param.read_text(encoding="utf-8")


def sentences(text):
    prose = re.sub(r"^\s*(#|\||\[|- \[).*$", "", text, flags=re.M)
    prose = re.sub(r"\s+", " ", prose)
    return [s for s in re.split(r"(?<=[.?!])\s+", prose) if s.strip()]


def test_no_name_appears_and_none_is_asked_for(doc):
    low = doc.lower()
    assert not any(n in low for n in NAMES)
    assert not re.search(r"\b(your )?name\s*:", low)
    assert "reader b" in low


def test_no_em_or_en_dash(doc):
    assert not re.search("[–—]", doc)


def test_the_sheet_fits_one_page_in_plain_sentences():
    text = SHEET.read_text(encoding="utf-8")
    assert len(text.split()) <= 550
    assert max(len(s.split()) for s in sentences(text)) < 45


def test_the_sheet_says_what_the_level_means_and_what_to_do():
    text = SHEET.read_text(encoding="utf-8")
    assert (
        "The demand level shows demand unusually high for the time of "
        "year. It is not pressure, need or priority." in text
    )
    for word in ("approve", "edit", "reject", "Text A", "Text B"):
        assert word in text


def test_the_form_carries_the_six_criteria_as_the_queue_does():
    text = FORM.read_text(encoding="utf-8")
    for c in ap.CRITERIA:
        assert text.count(f"| {c.name} | {c.test} |") == 4 + 4


def test_the_form_has_a_decision_and_notes_for_each_of_four_briefs():
    text = FORM.read_text(encoding="utf-8")
    for n in (1, 2, 3, 4):
        assert f"### Brief {n}" in text
    assert text.count("[ ] Approve") == 4
    assert text.count("[ ] Edit") == 4
    assert text.count("[ ] Reject") == 4
    assert text.count("Notes:") >= 4 + 4


def test_the_form_rates_both_texts_of_both_template_pairs():
    text = FORM.read_text(encoding="utf-8")
    for week in (1, 2):
        for label in ("A", "B"):
            assert f"### Week {week}, Text {label}" in text
    assert text.count("Any factual error?") == 4

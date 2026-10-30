"""The spot-check notebook numbers its figures as APA does, in the order a
reader first meets them: the captions run Figure 1 to Figure 7 down the
page, and no figure is named before every lower number has been."""

import json
import re

from .conftest import REPO

NOTEBOOK = REPO / "ae_escalation_spot_check.ipynb"
CAPTION = re.compile(r"^\*Figure (\d+)\.", re.M)
MENTION = re.compile(r"\bFigures? (\d+)")


def cell_sources():
    """Each cell's type and source, in the order the notebook shows them."""
    cells = json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
    return [(c["cell_type"], "".join(c["source"])) for c in cells]


def test_the_captions_run_1_to_7_down_the_page():
    captions = [
        int(n)
        for kind, source in cell_sources()
        if kind == "markdown"
        for n in CAPTION.findall(source)
    ]
    assert captions == list(range(1, 8))


def test_each_figure_is_first_named_after_every_lower_number():
    # A caption, an image's alt text, a markdown mention and a code comment
    # all count, since a reader meets each of them in this order.
    first = []
    for _, source in cell_sources():
        for n in MENTION.findall(source):
            if int(n) not in first:
                first.append(int(n))
    assert first == sorted(first)
    assert first == list(range(1, len(first) + 1))

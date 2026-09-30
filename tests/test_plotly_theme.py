import plotly.graph_objects as go

import chamberviz as cv
from chamberstudio import plotly_theme as pt


def test_every_design_has_a_template():
    names = pt.register_all()
    assert len(names) == len(cv.list_designs())
    for design in cv.list_designs():
        t = pt.template(design)
        d = cv.themes.get_design(design) if hasattr(cv, "themes") else None
        assert t.layout.paper_bgcolor.startswith("#")
        assert list(t.layout.colorway)
        assert t.layout.title.font.color


def test_apply_sets_the_colours_on_the_figure():
    fig = pt.apply(go.Figure(go.Bar(x=["a", "b"], y=[1, 2])), "navy_gold")
    assert fig.layout.paper_bgcolor == fig.layout.plot_bgcolor == pt.template("navy_gold").layout.paper_bgcolor
    light = pt.apply(go.Figure(), "report_slate")
    assert light.layout.paper_bgcolor == "#ffffff"


def test_highlight_colors():
    c = pt.colors("navy_gold")
    assert pt.highlight_colors("navy_gold", [1, 5, 3]) == [c["bar"], c["highlight"], c["bar"]]
    assert pt.highlight_colors("navy_gold", [1, 5, 3], "last")[-1] == c["highlight"]
    assert pt.highlight_colors("navy_gold", [1, 5, 3], None) == [c["bar"]] * 3

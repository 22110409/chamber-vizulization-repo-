"""Run the Streamlit app headless (no browser) and make sure the main paths raise no error."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "chamberstudio" / "app.py")


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_load_sample_and_build_visuals():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    button(at, "Use the sample trade data").click().run()
    assert not at.exception
    assert any("Showing" in m.value and "23,472" in m.value for m in at.markdown)
    for _ in range(3):
        button(at, "＋ Add visual").click().run()
        assert not at.exception
    assert len(at.session_state["visuals"]) == 3
    # change the selected visual to a line by month with a legend
    at.selectbox(key=f"v-{at.session_state['visuals'][-1].id}-type").set_value("line").run()
    at.selectbox(key=f"v-{at.session_state['visuals'][-1].id}-cat").set_value("Month").run()
    assert not at.exception
    # a KPI card that compares with last year (it has a date column but no drill-down)
    button(at, "＋ Add visual").click().run()
    vid = at.session_state["visuals"][-1].id
    at.selectbox(key=f"v-{vid}-type").set_value("kpi").run()
    at.selectbox(key=f"v-{vid}-cat").set_value("Month").run()
    assert not at.exception
    button(at, "✨ Suggest for me").click().run()
    assert not at.exception and at.session_state["suggestions"]


def test_pages_kpis_and_save(tmp_path):
    from chamberstudio import dashboard as D
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    button(at, "Use the sample trade data").click().run()
    button(at, "＋ Add visual").click().run()
    button(at, "＋ KPI").click().run()
    assert not at.exception and len(at.session_state["kpis"]) == 1
    first = at.session_state["page_id"]
    # a second page with its own visual
    next(b for b in at.button if b.key == "page-add").click().run()
    assert not at.exception and len(at.session_state["pages"]) == 2
    assert at.session_state["visuals"] == [] and at.session_state["kpis"] == []
    button(at, "＋ Add visual").click().run()
    assert not at.exception
    # save (absolute path) and read it back
    target = tmp_path / "studio_test.json"
    at.text_input(key="dash-path").set_value(str(target)).run()
    button(at, "Save").click().run()
    assert not at.exception and target.exists()
    dash = D.load(target)
    assert [len(p.visuals) for p in dash.pages] == [1, 1] and len(dash.pages[0].kpis) == 1
    assert dash.pages[0].id == first and dash.missing == []

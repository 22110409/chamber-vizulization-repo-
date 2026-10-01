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
    button(at, "✨ Suggest for me").click().run()
    assert not at.exception and at.session_state["suggestions"]

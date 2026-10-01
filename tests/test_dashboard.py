import json
import shutil

import pytest

from chamberstudio import dashboard as D
from chamberstudio import filters as F
from chamberstudio.visuals import VisualSpec
from conftest import SAMPLE


def make(data_path):
    page1 = D.Page("Overview", filters=F.Group("and", [F.DateFilter("Month", "this_year")]),
                   kpis=[VisualSpec("kpi", "Month", "Value")],
                   visuals=[VisualSpec("bar", "Country", "Value", top_n=8),
                            VisualSpec("line", "Month", "Value", legend="Flow", level="year")], grid=2)
    page2 = D.Page("Partners", visuals=[VisualSpec("map", "Country", "Value")], grid=1)
    return D.Dashboard("Trade 2025", "report_slate",
                       D.DataSource(str(data_path), "Trade", {"Value (JD thousand)": {"kind": "number", "label": "Value"}},
                                    None, [{"name": "Value M", "formula": "Value / 1000"}]),
                       [page1, page2], current_page=page2.id)


def test_round_trip(tmp_path):
    data = tmp_path / "data" / "trade.xlsx"
    data.parent.mkdir()
    shutil.copy(SAMPLE, data)
    dash = make(data)
    path = D.save(dash, tmp_path / "dashboards" / "trade.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["data"]["path"] == "../data/trade.xlsx"          # relative to the JSON file
    again = D.load(path)
    assert again.missing == []
    assert again.data.path == str(data.resolve())
    assert again.title == "Trade 2025" and again.design == "report_slate"
    assert [p.name for p in again.pages] == ["Overview", "Partners"]
    assert again.page().name == "Partners"                         # the page that was open
    p1 = again.pages[0]
    assert p1.grid == 2 and len(p1.kpis) == 1 and len(p1.visuals) == 2
    assert p1.visuals[1].legend == "Flow" and p1.visuals[1].level == "year"
    assert F.to_dict(p1.filters) == F.to_dict(dash.pages[0].filters)
    assert D.to_dict(again, path.parent) == D.to_dict(dash, path.parent)


def test_moving_the_folder_keeps_working(tmp_path):
    src = tmp_path / "project"
    (src / "data").mkdir(parents=True)
    shutil.copy(SAMPLE, src / "data" / "trade.xlsx")
    D.save(make(src / "data" / "trade.xlsx"), src / "dash" / "trade.json")
    moved = tmp_path / "somewhere" / "else"
    shutil.copytree(src, moved)
    shutil.rmtree(src)
    again = D.load(moved / "dash" / "trade.json")
    assert again.missing == [] and again.data.path == str((moved / "data" / "trade.xlsx").resolve())


def test_data_file_next_to_the_json_is_found(tmp_path):
    D.save(make(tmp_path / "gone" / "trade.xlsx"), tmp_path / "trade.json")
    shutil.copy(SAMPLE, tmp_path / "trade.xlsx")
    again = D.load(tmp_path / "trade.json")
    assert again.missing == [] and again.data.path == str((tmp_path / "trade.xlsx").resolve())


def test_missing_file_is_reported_not_fatal(tmp_path):
    D.save(make(tmp_path / "nowhere" / "trade.xlsx"), tmp_path / "trade.json")
    again = D.load(tmp_path / "trade.json")
    assert [m["role"] for m in again.missing] == ["data"] and again.missing[0]["name"] == "trade.xlsx"
    assert len(again.pages) == 2                                   # the rest of the dashboard is intact
    shutil.copy(SAMPLE, tmp_path / "new_month.xlsx")
    D.replace_file(again, "data", str(tmp_path / "new_month.xlsx"))
    assert again.missing == [] and again.data.path.endswith("new_month.xlsx")


def test_not_a_dashboard(tmp_path):
    (tmp_path / "x.json").write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="not a Chamber Studio"):
        D.load(tmp_path / "x.json")

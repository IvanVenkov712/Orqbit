import json

import pytest

from summary import summarize_csv


def test_selected_numeric_columns_and_ignored_text():
    result = summarize_csv(
        {
            "csv": "name,amount,units\nA,10,2\nB,20,4\n",
            "columns": ["amount", "units"],
        }
    )
    assert result == {
        "row_count": 2,
        "columns": {
            "amount": {"count": 2, "sum": 30.0, "min": 10.0, "max": 20.0, "mean": 15.0},
            "units": {"count": 2, "sum": 6.0, "min": 2.0, "max": 4.0, "mean": 3.0},
        },
    }
    json.dumps(result, allow_nan=False)


def test_quoted_fields_newlines_and_blank_rows():
    result = summarize_csv(
        {
            "csv": 'name,amount\r\n"A, Inc.",-2\r\n\r\n"B\nCo",0.5\r\n',
            "columns": ["amount"],
        }
    )
    assert result["row_count"] == 2
    assert result["columns"]["amount"] == {
        "count": 2,
        "sum": -1.5,
        "min": -2.0,
        "max": 0.5,
        "mean": -0.75,
    }


def test_header_only_has_empty_statistics():
    assert summarize_csv({"csv": "amount\n", "columns": ["amount"]}) == {
        "row_count": 0,
        "columns": {
            "amount": {"count": 0, "sum": 0.0, "min": None, "max": None, "mean": None}
        },
    }


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"csv": 1, "columns": ["a"]},
        {"csv": "", "columns": ["a"]},
        {"csv": "a\n1", "columns": []},
        {"csv": "a\n1", "columns": "a"},
        {"csv": "a\n1", "columns": [["a"]]},
        {"csv": "a\n1", "columns": ["a", "a"]},
        {"csv": "a\n1", "columns": [""]},
        {"csv": "a\n1", "columns": ["b"]},
        {"csv": "a,a\n1,2", "columns": ["a"]},
        {"csv": ",a\n1,2", "columns": ["a"]},
        {"csv": "a,b\n1", "columns": ["a"]},
        {"csv": "a\n1,2", "columns": ["a"]},
        {"csv": 'a\n"unfinished', "columns": ["a"]},
    ],
)
def test_invalid_csv_or_column_selection(params):
    with pytest.raises(ValueError):
        summarize_csv(params)


@pytest.mark.parametrize("cell", ["", "text", "NaN", "Infinity", "-inf", "1e999"])
def test_invalid_numeric_cell(cell):
    with pytest.raises(ValueError, match="finite number"):
        summarize_csv({"csv": f"a,b\n{cell},ignored\n", "columns": ["a"]})


def test_sum_overflow_is_rejected():
    with pytest.raises(ValueError, match="sum is outside"):
        summarize_csv({"csv": "a\n1e308\n1e308", "columns": ["a"]})

"""Summarize selected numeric columns in comma-separated text."""

import csv
import math
from io import StringIO


def validate_params(params: dict) -> tuple[str, list[str]]:
    text = params.get("csv")
    columns = params.get("columns")
    if not isinstance(text, str) or not text:
        raise ValueError("csv must be a nonempty string")
    if (
        not isinstance(columns, list)
        or not columns
        or any(not isinstance(column, str) or not column.strip() for column in columns)
        or len(set(columns)) != len(columns)
    ):
        raise ValueError("columns must be a nonempty list of unique column names")
    return text, columns


def column_indexes(header: list[str], columns: list[str]) -> dict[str, int]:
    if (
        not header
        or any(not name.strip() for name in header)
        or len(set(header)) != len(header)
    ):
        raise ValueError("CSV header must contain unique, nonempty column names")
    if any(column not in header for column in columns):
        raise ValueError("Every selected column must exist in the CSV header")
    return {column: header.index(column) for column in columns}


def add_value(summary: dict, cell: str, row_number: int, column: str) -> None:
    message = f"Row {row_number}, column {column}: expected a finite number"
    try:
        value = float(cell)
    except ValueError:
        raise ValueError(message) from None
    if not math.isfinite(value):
        raise ValueError(message)

    total = summary["sum"] + value
    if not math.isfinite(total):
        raise ValueError(f"Column {column}: sum is outside the supported numeric range")
    summary["count"] += 1
    summary["sum"] = total
    summary["min"] = value if summary["min"] is None else min(summary["min"], value)
    summary["max"] = value if summary["max"] is None else max(summary["max"], value)


def summarize_csv(params: dict) -> dict:
    text, columns = validate_params(params)
    reader = csv.reader(StringIO(text, newline=""), strict=True)
    summaries = {
        column: {"count": 0, "sum": 0.0, "min": None, "max": None} for column in columns
    }
    row_count = 0
    try:
        header = next(reader, [])
        indexes = column_indexes(header, columns)
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    f"CSV row ending at line {reader.line_num} has the wrong number of fields"
                )
            for column, index in indexes.items():
                add_value(summaries[column], row[index], reader.line_num, column)
            row_count += 1
    except csv.Error:
        raise ValueError("csv must contain valid comma-separated records") from None

    for summary in summaries.values():
        summary["mean"] = (
            summary["sum"] / summary["count"] if summary["count"] else None
        )
    return {"row_count": row_count, "columns": summaries}

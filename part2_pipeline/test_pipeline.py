"""Tests for the quality rules. They use an in-memory DuckDB, so no S3 is needed."""

import duckdb

from pipeline import validate


def rejection_reasons(rows):
    """Run validate() on (transaction_id, transaction_date, amount) rows; return each row's reason."""
    con = duckdb.connect()
    con.execute("CREATE TABLE landing (transaction_id VARCHAR, transaction_date VARCHAR, amount VARCHAR)")
    con.executemany("INSERT INTO landing VALUES (?, ?, ?)", rows)
    validate(con)
    return [row[0] for row in con.execute("SELECT rejection_reason FROM checked ORDER BY rowid").fetchall()]


def test_good_row_passes():
    assert rejection_reasons([("TXN-1", "2026-11-13", "10.50")]) == [None]


def test_missing_transaction_id():
    assert rejection_reasons([(None, "2026-11-13", "10.50")]) == ["missing_transaction_id"]
    assert rejection_reasons([("  ", "2026-11-13", "10.50")]) == ["missing_transaction_id"]


def test_invalid_date():
    assert rejection_reasons([("TXN-1", "13th Nov", "10.50")]) == ["invalid_date"]


def test_invalid_amount():
    assert rejection_reasons([("TXN-1", "2026-11-13", "ten")]) == ["invalid_amount"]


def test_non_positive_amount():
    assert rejection_reasons([("TXN-1", "2026-11-13", "-5.00")]) == ["non_positive_amount"]
    assert rejection_reasons([("TXN-1", "2026-11-13", "0")]) == ["non_positive_amount"]


def test_every_copy_of_a_duplicate_is_rejected():
    rows = [("TXN-1", "2026-11-13", "10.00"), ("TXN-1", "2026-11-14", "20.00"), ("TXN-2", "2026-11-14", "5.00")]
    assert rejection_reasons(rows) == ["duplicate_transaction_id", "duplicate_transaction_id", None]
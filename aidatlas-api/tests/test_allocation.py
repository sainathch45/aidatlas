"""Unit tests for the allocation math -- pure function, no network, no
GCP credentials needed, runs anywhere including CI.

    pip install -r requirements.txt pytest
    pytest tests/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import compute_proportional_allocation  # noqa: E402


def make_districts():
    # Mirrors the real shape returned by fetch_district_need_scores,
    # values loosely modeled on real At Tall / Damascus rows.
    return [
        {"admin2_code": "A", "need_score": 16564.0},
        {"admin2_code": "B", "need_score": 10606.6},
        {"admin2_code": "C", "need_score": 0.0},
    ]


def test_allocation_sums_to_supply_pool():
    districts = make_districts()
    supply_pool = 1_000_000.0
    result = compute_proportional_allocation(districts, supply_pool)
    total_allocated = sum(d["quantity_allocated"] for d in result)
    # Rounding to 2dp per district can drift the total by a few cents at
    # most -- assert within a cent per district, not exact equality.
    assert abs(total_allocated - supply_pool) < 0.01 * len(districts)


def test_allocation_proportional_to_need():
    districts = make_districts()
    result = compute_proportional_allocation(districts, 1_000_000.0)
    by_code = {d["admin2_code"]: d["quantity_allocated"] for d in result}
    # A has ~1.56x B's need score -- allocation ratio should match.
    assert by_code["A"] > by_code["B"] > by_code["C"]
    assert abs(by_code["A"] / by_code["B"] - 16564.0 / 10606.6) < 0.001


def test_zero_need_gets_zero_allocation():
    districts = make_districts()
    result = compute_proportional_allocation(districts, 1_000_000.0)
    zero_need = next(d for d in result if d["admin2_code"] == "C")
    assert zero_need["quantity_allocated"] == 0.0


def test_all_zero_need_does_not_divide_by_zero():
    # Real failure mode this guards: if BigQuery ever returns every
    # district with need_score 0 (e.g. a bad load), total_need falls
    # back to 1 rather than raising ZeroDivisionError on live traffic.
    districts = [{"admin2_code": "X", "need_score": 0.0}, {"admin2_code": "Y", "need_score": 0.0}]
    result = compute_proportional_allocation(districts, 500.0)
    assert all(d["quantity_allocated"] == 0.0 for d in result)


def test_empty_supply_pool_gives_zero_allocations():
    districts = make_districts()
    result = compute_proportional_allocation(districts, 0.0)
    assert all(d["quantity_allocated"] == 0.0 for d in result)

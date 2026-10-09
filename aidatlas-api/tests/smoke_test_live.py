"""Smoke test every endpoint against a live deployed backend, for every
supported crisis -- this is what actually matters for the submission
rules (the deployed prototype must stay functional), not just localhost.

    python tests/smoke_test_live.py <backend_url>
"""

import sys

import requests

PASS = []
FAIL = []

# Real figures confirmed directly from the downloaded HDX HAPI funding
# CSVs, not invented -- used to assert the live API still returns the
# actual numbers, not just "a number."
CRISES = {
    "SYR": {"district_count": 61, "with_coordinates": 48, "pool_usd": 935449756.0},
    "MMR": {"district_count": 15, "with_coordinates": 14, "pool_usd": 444151722.0},
}


def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


def run(base_url: str):
    print(f"Smoke testing {base_url}\n")

    print("/health")
    r = requests.get(f"{base_url}/health", timeout=15)
    check("health returns 200", r.status_code == 200, r.text)
    check("health body correct", r.json() == {"status": "ok"})

    print("\n/crises")
    r = requests.get(f"{base_url}/crises", timeout=15)
    check("crises returns 200", r.status_code == 200, r.text)
    codes = {c["code"] for c in r.json().get("crises", [])}
    check("both SYR and MMR registered", {"SYR", "MMR"} <= codes, codes)

    for region, expect in CRISES.items():
        print(f"\n--- {region} ---")

        print(f"/districts?crisis_region={region}")
        r = requests.get(f"{base_url}/districts?crisis_region={region}", timeout=30)
        check(f"{region} districts returns 200", r.status_code == 200, r.text[:200])
        d = r.json()
        check(f"{region} district_count is {expect['district_count']}", d.get("district_count") == expect["district_count"], d.get("district_count"))
        check(f"{region} with_coordinates is {expect['with_coordinates']}", d.get("with_coordinates") == expect["with_coordinates"], d.get("with_coordinates"))
        check(
            f"{region} every location has required fields",
            all({"admin_code", "admin_name", "need_score"} <= set(x.keys()) for x in d["districts"]),
        )

        print(f"/allocate for {region}, each resource type")
        for resource_type in ["shelter", "food", "medicine"]:
            # Don't assume every resource type covers the same number of
            # locations -- caught live that Myanmar's real sector data
            # genuinely differs (shelter: 15 states reporting, food/
            # medicine: 18) since each sector gets assessed in a
            # different number of states. Check self-consistency against
            # /districts for the same resource_type instead of a single
            # hardcoded count across all three.
            dr = requests.get(f"{base_url}/districts?crisis_region={region}&resource_type={resource_type}", timeout=30)
            expected_count = dr.json().get("district_count", 0)

            r = requests.post(
                f"{base_url}/allocate",
                json={"crisis_region": region, "resource_type": resource_type, "top_n_rationale": 3},
                timeout=90,
            )
            check(f"{region} allocate({resource_type}) returns 200", r.status_code == 200, r.text[:200])
            body = r.json()
            check(
                f"{region} allocate({resource_type}) location count matches /districts ({expected_count})",
                body.get("district_count") == expected_count,
                body.get("district_count"),
            )
            total = sum(a["quantity_allocated"] for a in body.get("allocations", []))
            pool = body.get("supply_pool_usd", 0)
            check(
                f"{region} allocate({resource_type}) sums to the real supply pool within rounding",
                abs(total - pool) < 1.0,
                f"total={total} pool={pool}",
            )
            check(
                f"{region} allocate({resource_type}) real appeal pool figure",
                abs(pool - expect["pool_usd"]) < 1.0,
                pool,
            )

        print(f"/allocations read-back for {region}")
        r = requests.get(f"{base_url}/allocations?crisis_region={region}&resource_type=shelter", timeout=20)
        check(f"{region} allocations returns 200", r.status_code == 200)
        check(
            f"{region} allocations returns {expect['district_count']} docs, no duplicates",
            len({a["admin_code"] for a in r.json()["allocations"]}) == expect["district_count"],
        )

        print(f"/ask for {region} (tolerates Gemini quota exhaustion -- must not 500 either way)")
        r = requests.post(
            f"{base_url}/ask",
            json={"question": "Which location has the highest need score?", "crisis_region": region, "resource_type": "shelter"},
            timeout=90,
        )
        check(f"{region} ask does not 500", r.status_code in (200,), f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 200:
            check(f"{region} ask answer is non-empty", bool(r.json().get("answer", "").strip()))

    print("\n/ask rejects empty question")
    r = requests.post(f"{base_url}/ask", json={"question": "   ", "crisis_region": "SYR", "resource_type": "shelter"}, timeout=15)
    check("empty question returns 400", r.status_code == 400, r.status_code)

    print("\n/allocate rejects unsupported crisis_region")
    r = requests.post(f"{base_url}/allocate", json={"crisis_region": "ZZZ", "resource_type": "shelter"}, timeout=15)
    check("unsupported crisis_region returns 400", r.status_code == 400, r.status_code)

    print(f"\n{'='*50}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    run(sys.argv[1].rstrip("/"))

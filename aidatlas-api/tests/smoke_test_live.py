"""Smoke test every endpoint against a live deployed backend -- this is
what actually matters for the submission rules (the deployed prototype
must stay functional), not just localhost.

    python tests/smoke_test_live.py <backend_url>
"""

import sys

import requests

PASS = []
FAIL = []


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

    print("\n/districts")
    r = requests.get(f"{base_url}/districts", timeout=30)
    check("districts returns 200", r.status_code == 200, r.text)
    d = r.json()
    check("districts count is 61", d.get("district_count") == 61, d.get("district_count"))
    check("48 districts have coordinates", d.get("with_coordinates") == 48, d.get("with_coordinates"))
    check(
        "every district has required fields",
        all({"admin2_code", "admin2_name", "need_score"} <= set(x.keys()) for x in d["districts"]),
    )

    print("\n/allocate for each resource type")
    for resource_type in ["shelter", "food", "medicine"]:
        r = requests.post(
            f"{base_url}/allocate",
            json={"resource_type": resource_type, "top_n_rationale": 3},
            timeout=60,
        )
        check(f"allocate({resource_type}) returns 200", r.status_code == 200, r.text[:200])
        body = r.json()
        check(f"allocate({resource_type}) has 61 districts", body.get("district_count") == 61)
        total = sum(a["quantity_allocated"] for a in body.get("allocations", []))
        pool = body.get("supply_pool_usd", 0)
        check(
            f"allocate({resource_type}) sums to the real supply pool within rounding",
            abs(total - pool) < 1.0,
            f"total={total} pool={pool}",
        )
        check(
            f"allocate({resource_type}) real HSYR26 pool figure",
            abs(pool - 935449756.0) < 1.0,
            pool,
        )

    print("\n/allocations read-back")
    r = requests.get(f"{base_url}/allocations?resource_type=shelter", timeout=20)
    check("allocations returns 200", r.status_code == 200)
    check("allocations returns 61 docs, no duplicates", len({a["admin2_code"] for a in r.json()["allocations"]}) == 61)

    print("\n/ask (tolerates Gemini quota exhaustion -- must not 500 either way)")
    r = requests.post(
        f"{base_url}/ask",
        json={"question": "Which district has the highest need score?", "resource_type": "shelter"},
        timeout=60,
    )
    check("ask does not 500", r.status_code in (200,), f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        check("ask answer is non-empty", bool(r.json().get("answer", "").strip()))

    print("\n/ask rejects empty question")
    r = requests.post(f"{base_url}/ask", json={"question": "   ", "resource_type": "shelter"}, timeout=15)
    check("empty question returns 400", r.status_code == 400, r.status_code)

    print(f"\n{'='*50}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    run(sys.argv[1].rstrip("/"))

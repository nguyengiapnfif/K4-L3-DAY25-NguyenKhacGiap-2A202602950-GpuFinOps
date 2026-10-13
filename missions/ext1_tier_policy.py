"""Extension 1 — cost-aware recommend_tier(): per-GPU interruption + 1yr vs 3yr reserved.

Compares three numbers for M3's workloads:
  legacy (reported)   old policy, M3's own costing (3yr rate, 5% interrupt for all)
  legacy (re-costed)  old policy's tier choices, costed with GPU-specific interrupt
                      rates and the 3yr lock-in for the workload's real horizon
  v2                  new policy (cheapest eligible option on the same costing)

Run: python missions/ext1_tier_policy.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type, ROOT
from finops import pricing

DAYS = 30
# ASSUMPTION: always-on services (kind=infer) are kept ~2 years; other jobs live
# for their own `days` (so no commitment is ever worth it for them).
SERVICE_HORIZON_MONTHS = 24


def horizon_months(job: dict) -> float:
    if job["kind"] == "infer":
        return SERVICE_HORIZON_MONTHS
    return num(job["days"]) / 30.0


def run(verbose: bool = True, write: bool = True) -> dict:
    jobs, cat = load_csv("workloads.csv"), catalog_by_type()
    rows, tot = [], {"od": 0.0, "legacy": 0.0, "legacy_true": 0.0, "v2": 0.0}
    for j in jobs:
        c = cat[j["gpu_type"]]
        prices = {k: num(c[k]) for k in ("on_demand_hr", "spot_hr", "reserved_1yr_hr", "reserved_3yr_hr")}
        hpd, intr = num(j["hours_per_day"]), bool(int(num(j["interruptible"])))
        gh = hpd * DAYS * int(num(j["num_gpus"]))
        hz = horizon_months(j)
        od = gh * prices["on_demand_hr"]

        # legacy tier + M3's original costing
        lt = pricing.recommend_tier(hpd, intr)
        if lt == "spot":
            l_rep = pricing.spot_checkpoint_cost(gh, prices["spot_hr"], prices["on_demand_hr"])["spot_cost"]
        elif lt == "reserved":
            l_rep = gh * prices["reserved_3yr_hr"]
        else:
            l_rep = od
        # same tier, honest costing (GPU interrupt rate, lock-in of the 3yr term)
        if lt == "spot":
            l_true = pricing.spot_checkpoint_cost(
                gh, prices["spot_hr"], prices["on_demand_hr"],
                interrupt_rate=pricing.interrupt_rate(j["gpu_type"]))["spot_cost"]
        elif lt == "reserved":
            l_true = gh * prices["reserved_3yr_hr"] * pricing._lockin_factor(hz, 36)
        else:
            l_true = od

        # v2
        costs = pricing.tier_costs(j["gpu_type"], prices, gh, hpd, intr, hz)
        vt = pricing.recommend_tier(hpd, intr, gpu_type=j["gpu_type"], prices=prices, horizon_months=hz)
        v2 = costs[vt]

        for k, v in (("od", od), ("legacy", l_rep), ("legacy_true", l_true), ("v2", v2)):
            tot[k] += v
        rows.append((j["job_id"], j["gpu_type"], f"{pricing.interrupt_rate(j['gpu_type']):.0%}", f"{hz:.1f}",
                     lt, vt, od, l_rep, l_true, v2))

    pct = lambda x: (1 - x / tot["od"]) * 100
    res = {"on_demand_monthly": round(tot["od"]),
           "legacy_reported": round(tot["legacy"]), "legacy_reported_pct": round(pct(tot["legacy"]), 1),
           "legacy_recosted": round(tot["legacy_true"]), "legacy_recosted_pct": round(pct(tot["legacy_true"]), 1),
           "v2": round(tot["v2"]), "v2_pct": round(pct(tot["v2"]), 1)}

    lines = ["| job | gpu | spot int. | horizon (mo) | legacy tier | v2 tier | on-demand | legacy (reported) | legacy (re-costed) | v2 |",
             "|---|---|---|---|---|---|---:|---:|---:|---:|"]
    for r in rows:
        lines.append("| " + " | ".join(r[:6]) + "".join(f" | ${x:,.0f}" for x in r[6:]) + " |")
    lines.append(f"| **total** | | | | | | **${res['on_demand_monthly']:,}** | **${res['legacy_reported']:,}** ({res['legacy_reported_pct']}%) "
                 f"| **${res['legacy_recosted']:,}** ({res['legacy_recosted_pct']}%) | **${res['v2']:,}** ({res['v2_pct']}%) |")
    table = "\n".join(lines)
    if verbose:
        print("== Extension 1: cost-aware recommend_tier ==")
        print(table)
    if write:
        with open(_os.path.join(ROOT, "outputs", "ext1_tier_policy.md"), "w") as f:
            f.write("# Extension 1 — recommend_tier(): before/after\n\n" + table + "\n")
    res["rows"] = rows
    return res


if __name__ == "__main__":
    run()

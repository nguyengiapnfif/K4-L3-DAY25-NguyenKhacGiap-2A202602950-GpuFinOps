"""Extension 5 — Carbon-aware scheduling for interruptible jobs.

For every workloads.csv job with interruptible=1: energy = watts x GPU-hours, then
compare running it in us-east-1 (assumed current) with all 5 regions.

ASSUMPTIONS: GPU board power only (catalog `watts`, flat 100% load, no PUE/CPU/
network); GPU-hours use each job's real window (hours_per_day x days x num_gpus),
NOT a 30-day month; GPU rental price is assumed equal across regions (the catalog
has one price per GPU) so only the electricity bill and carbon change.

Run: python missions/ext5_carbon_scheduling.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type, ROOT
from finops.sustainability import REGION_CARBON, REGION_PRICE_KWH, carbon_g, energy_cost_usd

BASE = "us-east-1"
# Free-form latency notes (assumption: users/data in US East) — informational only.
LATENCY = {"us-east-1": "baseline", "us-west-2": "+60-70 ms RTT", "us-east-wa": "+60-70 ms RTT",
           "europe-north1": "+100-120 ms RTT", "europe-central2": "+90-110 ms RTT"}


def run(verbose: bool = True, write: bool = True) -> dict:
    cat = catalog_by_type()
    jobs = []
    for j in load_csv("workloads.csv"):
        if not int(num(j["interruptible"])):
            continue
        gh = num(j["hours_per_day"]) * num(j["days"]) * int(num(j["num_gpus"]))
        jobs.append((j["job_id"], j["gpu_type"], gh, gh * num(cat[j["gpu_type"]]["watts"])))  # Wh
    total_wh = sum(w for *_, w in jobs)

    regions = {}
    for r in REGION_CARBON:
        regions[r] = {"usd_kwh": REGION_PRICE_KWH[r], "g_kwh": REGION_CARBON[r],
                      "elec_usd": energy_cost_usd(total_wh, r), "gco2": carbon_g(total_wh, r)}
    cheapest = min(regions, key=lambda r: regions[r]["elec_usd"])
    cleanest = min(regions, key=lambda r: regions[r]["gco2"])
    emax = max(v["elec_usd"] for v in regions.values()); cmax = max(v["gco2"] for v in regions.values())
    score = {r: 0.5 * v["elec_usd"] / emax + 0.5 * v["gco2"] / cmax for r, v in regions.items()}
    balanced = min(score, key=score.get)

    jl = ["| job | gpu | GPU-h | kWh | gCO2e @us-east-1 | gCO2e @" + cleanest + " | saved g | saved % |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for jid, g, gh, wh in jobs:
        a, b = carbon_g(wh, BASE), carbon_g(wh, cleanest)
        jl.append(f"| {jid} | {g} | {gh:,.0f} | {wh / 1000:,.1f} | {a:,.0f} | {b:,.0f} | {a - b:,.0f} | {(1 - b / a) * 100:.0f}% |")
    base_g, best_g = regions[BASE]["gco2"], regions[cleanest]["gco2"]
    jl.append(f"| **total** | | {sum(x[2] for x in jobs):,.0f} | **{total_wh / 1000:,.1f}** | **{base_g:,.0f}** | **{best_g:,.0f}** "
              f"| **{base_g - best_g:,.0f}** | **{(1 - best_g / base_g) * 100:.0f}%** |")

    rl = ["| region | $/kWh | gCO2/kWh | electricity $ | gCO2e | vs us-east-1 CO2 | latency (assumed) | pick |",
          "|---|---:|---:|---:|---:|---:|---|---|"]
    for r, v in regions.items():
        tag = ", ".join(t for t, x in (("cheapest $", cheapest), ("cleanest", cleanest), ("balanced", balanced)) if x == r)
        rl.append(f"| {r} | {v['usd_kwh']} | {v['g_kwh']} | ${v['elec_usd']:,.2f} | {v['gco2']:,.0f} | "
                  f"{(v['gco2'] / base_g - 1) * 100:+.0f}% | {LATENCY[r]} | {tag} |")
    note = (f"cheapest $: {cheapest} | cleanest: {cleanest} | balanced (50/50 min-max of $ and CO2): {balanced}\n"
            f"Moving all interruptible jobs {BASE} -> {cleanest}: {(base_g - best_g) / 1000:,.1f} kgCO2e saved "
            f"({(1 - best_g / base_g) * 100:.0f}%), electricity ${regions[BASE]['elec_usd']:,.2f} -> ${regions[cleanest]['elec_usd']:,.2f}.")
    out = "## Per job\n\n" + "\n".join(jl) + "\n\n## All five regions (same work, same GPU-hours)\n\n" + "\n".join(rl) + "\n\n" + note + "\n"
    if verbose:
        print("== Extension 5: carbon-aware scheduling =="); print(out)
    if write:
        with open(_os.path.join(ROOT, "outputs", "ext5_carbon_scheduling.md"), "w") as f:
            f.write("# Extension 5 — Carbon-aware scheduling\n\n" + out)
    return {"total_kwh": total_wh / 1000, "cheapest": cheapest, "cleanest": cleanest, "balanced": balanced,
            "base_gco2": base_g, "best_gco2": best_g, "regions": regions}


if __name__ == "__main__":
    run()

"""Pricing & purchasing economics — measure in $/1M-token, not $/GPU-hr.

Figures are June-2026 as-of snapshots from the deck's RESEARCH dossier; treat
live prices as fast-moving (re-baseline before each cohort).
"""
from __future__ import annotations


def request_cost(
    input_tok: int,
    output_tok: int,
    price_in_per_m: float,
    price_out_per_m: float,
    cached_in: int = 0,
    cache_discount: float = 0.10,   # Anthropic cached-read ~0.1x (=-90%)
    batch: bool = False,
    batch_discount: float = 0.50,   # Batch API ~ -50%
) -> float:
    """USD cost of a single request. Cached input billed at cache_discount x price."""
    cached_in = min(max(0, cached_in), input_tok)
    uncached_in = input_tok - cached_in
    cost = (
        (uncached_in / 1e6) * price_in_per_m
        + (cached_in / 1e6) * price_in_per_m * cache_discount
        + (output_tok / 1e6) * price_out_per_m
    )
    if batch:
        cost *= batch_discount
    return cost


def dollars_per_million(total_cost_usd: float, total_tokens: int) -> float:
    """Aggregate unit economics: $ per 1,000,000 tokens served."""
    if total_tokens <= 0:
        return 0.0
    return total_cost_usd / (total_tokens / 1e6)


def discount_stack(
    batch: bool = False,
    cache_hit_frac: float = 0.0,
    batch_discount: float = 0.50,
    cache_discount: float = 0.10,
) -> float:
    """Effective fraction of the naive bill after stacking discounts (input-heavy view).

    Discounts MULTIPLY: cache applies to the cached share of input, batch to the
    whole bill. batch + 100% cache-hit -> 0.5 * 0.1 = 0.05 (~95% off).
    """
    cache_mult = cache_hit_frac * cache_discount + (1.0 - cache_hit_frac)
    batch_mult = batch_discount if batch else 1.0
    return cache_mult * batch_mult


def break_even_utilization(discount_frac: float) -> float:
    """Utilization at which a commitment pays off ~= 1 - discount.

    A 45% reserved discount needs ~55% utilization (~13.2h/day) to beat on-demand.
    """
    return max(0.0, min(1.0, 1.0 - discount_frac))


# ASSUMPTION (not from the dataset): per-hour spot reclaim probability by GPU type.
# Scarce, high-demand parts are reclaimed less often than small inference cards
# in deep pools; values are illustrative planning numbers, re-measure per region.
SPOT_INTERRUPT_RATE = {
    "H100": 0.03, "H200": 0.03, "B200": 0.04, "A100": 0.05,
    "MI300X": 0.06, "A10G": 0.08, "L4": 0.08,
}
DEFAULT_INTERRUPT_RATE = 0.05


def interrupt_rate(gpu_type: str | None) -> float:
    return SPOT_INTERRUPT_RATE.get(gpu_type, DEFAULT_INTERRUPT_RATE)


def _lockin_factor(horizon_months: float, term_months: int) -> float:
    """Months paid per month used: commitments are bought in whole terms."""
    horizon_months = max(horizon_months, 1e-9)
    terms = max(1, -(-horizon_months // term_months))  # ceil
    return terms * term_months / horizon_months


def tier_costs(
    gpu_type: str,
    prices: dict,
    gpu_hours: float,
    hours_per_day: float,
    interruptible: bool,
    horizon_months: float,
) -> dict:
    """Monthly cost of every purchasing option that is *eligible* for the job.

    prices: on_demand_hr, spot_hr, reserved_1yr_hr, reserved_3yr_hr.
    - on_demand: used hours x on-demand rate.
    - spot: only if interruptible; includes checkpoint + rework at the GPU's own
      interruption rate.
    - reserved_1yr / reserved_3yr: only if duty cycle >= that term's break-even
      (rate / on-demand). Cost is inflated by the lock-in factor, i.e. the part
      of the term that outlives the workload is still paid for.
    """
    od = prices["on_demand_hr"]
    duty = max(0.0, hours_per_day) / 24.0
    out = {"on_demand": gpu_hours * od}
    if interruptible and hours_per_day < 24:
        out["spot"] = spot_checkpoint_cost(
            gpu_hours, prices["spot_hr"], od, interrupt_rate=interrupt_rate(gpu_type)
        )["spot_cost"]
    for key, term in (("reserved_1yr", 12), ("reserved_3yr", 36)):
        rate = prices[f"{key}_hr"]
        if od > 0 and duty >= rate / od:
            out[key] = gpu_hours * rate * _lockin_factor(horizon_months, term)
    return out


def recommend_tier(
    hours_per_day: float,
    interruptible: bool,
    reserved_discount: float = 0.45,
    gpu_type: str | None = None,
    job_days: float | None = None,
    prices: dict | None = None,
    horizon_months: float | None = None,
) -> str:
    """Pick a purchasing tier from a workload's duty cycle + interruptibility.

    Legacy policy (when `prices` is not given), unchanged:
      - interruptible & not 24/7  -> 'spot'
      - duty cycle >= break-even  -> 'reserved'
      - otherwise                 -> 'on_demand'

    Cost-aware policy (when `prices` + `gpu_type` are given): cheapest of
    tier_costs(); returns 'spot' | 'reserved_1yr' | 'reserved_3yr' | 'on_demand'.
    Horizon = horizon_months, else job_days/30, else 12 months.
    """
    if prices is None:
        duty = max(0.0, hours_per_day) / 24.0
        be = break_even_utilization(reserved_discount)
        if interruptible and hours_per_day < 24:
            return "spot"
        if duty >= be:
            return "reserved"
        return "on_demand"

    if horizon_months is None:
        horizon_months = job_days / 30.0 if job_days else 12.0
    costs = tier_costs(gpu_type, prices, 1.0, hours_per_day, interruptible, horizon_months)
    return min(costs, key=costs.get)


def spot_checkpoint_cost(
    job_hours: float,
    spot_hr: float,
    on_demand_hr: float,
    interrupt_rate: float = 0.05,      # per-hour chance (H100 spot ~<5%)
    ckpt_overhead_frac: float = 0.03,  # steady cost of writing checkpoints
    rework_hours_per_interrupt: float = 0.5,
) -> dict:
    """Effective cost of running a checkpointable job on spot vs on-demand.

    Interruptions waste the compute since the last checkpoint (rework); checkpointing
    adds a small steady overhead. Spot still wins for interruptible jobs.
    """
    expected_interrupts = job_hours * interrupt_rate
    rework_hours = expected_interrupts * rework_hours_per_interrupt
    effective_hours = job_hours * (1.0 + ckpt_overhead_frac) + rework_hours
    spot_cost = effective_hours * spot_hr
    on_demand_cost = job_hours * on_demand_hr
    savings_pct = (1.0 - spot_cost / on_demand_cost) * 100.0 if on_demand_cost > 0 else 0.0
    return {
        "spot_effective_hours": round(effective_hours, 2),
        "spot_cost": round(spot_cost, 2),
        "on_demand_cost": round(on_demand_cost, 2),
        "savings_pct": round(savings_pct, 1),
    }


def cache_break_even_reads(
    write_cost_per_m: float,
    read_discount: float = 0.10,
    price_in_per_m: float = 3.00,
) -> float:
    """Reads per cached prefix needed before caching pays for itself.

    write_cost_per_m: EXTRA $/1M cached tokens to create/store the cache beyond
    normal input processing (Anthropic 5-min write = 1.25x input -> 0.25 x price;
    Gemini bills storage per token-hour). Each read saves price x (1 - read_discount).
    """
    saving_per_read = price_in_per_m * (1.0 - read_discount)
    if saving_per_read <= 0:
        return float("inf")
    return max(0.0, write_cost_per_m) / saving_per_read


def cache_is_worth_it(
    avg_cache_reads: float,
    write_cost_per_m: float,
    read_discount: float = 0.10,
    price_in_per_m: float = 3.00,
) -> bool:
    """Cache only saves money when read savings exceed the write cost."""
    return avg_cache_reads > cache_break_even_reads(write_cost_per_m, read_discount, price_in_per_m)

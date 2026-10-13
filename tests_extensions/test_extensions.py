import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from finops import pricing
from missions import ext1_tier_policy, ext3_cache_economics

P = {"on_demand_hr": 2.5, "spot_hr": 1.5, "reserved_1yr_hr": 2.0, "reserved_3yr_hr": 1.4}


def test_legacy_recommend_tier_unchanged():
    assert pricing.recommend_tier(2, True) == "spot"
    assert pricing.recommend_tier(24, False) == "reserved"
    assert pricing.recommend_tier(4, False) == "on_demand"


def test_interrupt_rate_by_gpu():
    assert pricing.interrupt_rate("H100") < pricing.interrupt_rate("A10G")
    assert pricing.interrupt_rate("unknown") == pricing.DEFAULT_INTERRUPT_RATE


def test_reserved_term_depends_on_horizon():
    kw = dict(gpu_type="H100", prices=P)
    assert pricing.recommend_tier(24, False, horizon_months=12, **kw) == "reserved_1yr"
    assert pricing.recommend_tier(24, False, horizon_months=36, **kw) == "reserved_3yr"
    assert pricing.recommend_tier(24, False, horizon_months=1, **kw) != "reserved_3yr"


def test_low_duty_not_reserved_and_interruptible_spot():
    assert pricing.recommend_tier(4, False, gpu_type="H100", prices=P, horizon_months=24) == "on_demand"
    assert pricing.recommend_tier(4, True, gpu_type="H100", prices=P, horizon_months=1) == "spot"


def test_ext1_beats_recosted_legacy():
    r = ext1_tier_policy.run(verbose=False, write=False)
    assert r["v2"] < r["legacy_recosted"]
    assert r["v2"] >= 0.5 * r["on_demand_monthly"] * 0.0  # sanity: non-negative


def test_cache_break_even():
    be = pricing.cache_break_even_reads(0.25 * 3.0, price_in_per_m=3.0)
    assert abs(be - 0.25 / 0.9) < 1e-9
    assert not pricing.cache_is_worth_it(0.1, 0.75)
    assert pricing.cache_is_worth_it(1, 0.75)


def test_ext3_low_reads_disables_cache_high_reads_cheaper():
    r = ext3_cache_economics.run(verbose=False, write=False)
    low, high = r["sweep"][0], r["sweep"][-1]
    assert low["cached_requests"] == 0 and low["cost"] == r["no_cache_daily"]
    assert high["cost"] < low["cost"]
    assert high["cost"] >= r["m2_optimized_daily"]

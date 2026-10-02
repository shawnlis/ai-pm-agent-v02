"""Deterministic offline portfolio path research; no broker or price-fetching code.

Synthetic paths are conditions, not forecasts, backtests, beta estimates or VaR.
The caller must supply every holding's factor, financing inputs and option anchors.
"""
from __future__ import annotations
import argparse
import copy
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import pstdev

# Existing project primitives; read-only reuse, no fixture-only risk loader.
from ai_pm_agent.portfolio.exposure import calculate_base_leverage_adjusted_gross_exposure
from ai_pm_agent.portfolio.models import Holding, PortfolioSnapshot

SCHEMA_VERSION = "portfolio-path-research-v1"
LEVERAGE = {"QQQ": 1, "TQQQ": 3, "SOXL": 3}
MAIN_STRATEGIES = ("current", "exit_soxl", "repay_debt_keep_etfs", "qqq", "half_qqq_tqqq")
EXTRA_STRATEGIES = ("exit_soxl_chf_first", "exit_soxl_usd_only",
                    "qqq_keep_puts", "half_qqq_tqqq_keep_puts")
RESULT_FIELDS = ("scenario", "strategy", "end_nav_usd", "nav_return", "grid_drawdown",
                 "initial_cost_usd", "external_interest_usd", "fund_fee_usd",
                 "fund_financing_usd", "rebalance_cost_usd", "assignment_cash_usd",
                 "end_debt_usd", "initial_daily_notional_nav", "min_grid_nav_usd",
                 "option_proxy_warning")

@dataclass
class Snapshot:
    nav: float
    stocks: dict
    options: list
    balances: dict
    fx: dict
    residual: float
    metadata: dict
    reconciliation: dict

def finite(value, label):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite " + label)
    return result

def load_snapshot(path, config, now):
    level = config["provider_level"]
    if level not in (0, 3):
        raise ValueError("only explicit fixture or local read-only import providers supported")
    if level == 3 and not config.get("allow_private_input"):
        raise ValueError("private read-only import requires explicit allow_private_input")
    j = json.loads(Path(path).read_text(encoding="utf-8"))
    summary = j["get_account_summary"]
    if summary["currency"] != "USD":
        raise ValueError("USD base currency required; no silent currency inference")
    retrieval = datetime.fromisoformat(j["retrieved_utc"].replace("Z", "+00:00"))
    now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    if now.tzinfo is None or retrieval.tzinfo is None:
        raise ValueError("timezone required")
    raw_balances = [x for x in j["get_account_balances"]["balances"] if x["currency"] != "BASE"]
    if len({x["currency"] for x in raw_balances}) != len(raw_balances):
        raise ValueError("duplicate currency balance")
    balances = {x["currency"]: finite(x["cash_balance"], "cash") for x in raw_balances}
    fx = {x["currency"]: finite(x["exchange_rate"], "FX") for x in raw_balances}
    if fx.get("USD") != 1 or any(v <= 0 for v in fx.values()):
        raise ValueError("invalid USD conversion FX")
    stocks, options, ids = {}, [], set()
    for x in j["get_account_positions"]["positions"]:
        if x["contract_id"] in ids:
            raise ValueError("duplicate contract")
        ids.add(x["contract_id"])
        if x["asset_class"] == "CASH":
            continue  # FX position lines never added to the cash ledger.
        c = x["currency"]
        if c not in fx:
            raise ValueError("missing FX for position")
        x = dict(x)
        x["usd_value"] = finite(x["market_value"], "market value") * fx[c]
        qty, price = finite(x["position"], "quantity"), finite(x["market_price"], "price")
        if x["asset_class"] == "STK":
            if qty <= 0 or price <= 0:
                raise ValueError("this research engine requires long stocks and positive anchors")
            if not math.isclose(qty * price, x["market_value"], rel_tol=1e-8, abs_tol=0.01):
                raise ValueError("stock unit mismatch; split/DR review required")
            name = x["contract_description"]
            if name in stocks:
                raise ValueError("duplicate position description")
            stocks[name] = x
        elif x["asset_class"] == "OPT":
            if qty >= 0 or price <= 0 or c != "USD":
                raise ValueError("only USD short put marks supported")
            x["implied_valuation_multiplier"] = x["market_value"] / (qty * price)
            options.append(x)
        else:
            raise ValueError("unsupported instrument; no fallback")
    nav = finite(summary["net_liquidation"], "NAV")
    if nav <= 0:
        raise ValueError("positive NAV required")
    stock = sum(x["usd_value"] for x in stocks.values())
    opt = sum(x["usd_value"] for x in options)
    cash = sum(balances[c] * fx[c] for c in balances)
    # Retain unexplained reconciliation difference as fixed noninvestable bookkeeping.
    residual = nav - stock - opt - cash
    stale = (now - retrieval).total_seconds() > config.get("max_snapshot_age_hours", 24) * 3600
    metadata = {
        "provider_name": "synthetic_fixture" if level == 0 else "authorized_local_broker_snapshot",
        "provider_level": level,
        "retrieval_time": j["retrieved_utc"], "source_id": config["source_id"],
        "stale": stale, "reliability": "snapshot values; valuation timestamps and delay flags unknown",
        "warning_codes": ["NON_ATOMIC_SNAPSHOT", "PRICE_FRESHNESS_UNKNOWN",
                          "CONTRACT_DELIVERABLE_UNKNOWN"] + (["SNAPSHOT_STALE"] if stale else []),
        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "investment_output_valid": False,
    }
    if stale and not config.get("allow_stale_scenario"):
        raise ValueError("stale snapshot; explicit retrospective scenario opt-in required")
    holdings = [Holding(ticker=k, quantity=x["position"], market_value_base=x["usd_value"],
                        market_value=x["usd_value"], leverage_multiplier=LEVERAGE.get(k, 1))
                for k, x in stocks.items()]
    ps = PortfolioSnapshot(as_of_date=retrieval.date(), holdings=holdings, cash=nav-stock)
    multiple = calculate_base_leverage_adjusted_gross_exposure(ps)
    rec = {"nav_usd": nav, "stocks_usd": stock, "option_marks_usd": opt,
           "cash_ledger_usd": cash, "cash_summary_usd": summary["total_cash_value"],
           "cash_summary_minus_ledger_usd": summary["total_cash_value"] - cash,
           "nav_residual_using_summary_usd": nav-stock-opt-summary["total_cash_value"],
           "nav_residual_using_ledger_usd": residual,
           "gross_abs_securities_usd": stock-opt,
           "gross_broker_usd": summary["gross_position_value"],
           "gross_securities_minus_broker_usd": stock-opt-summary["gross_position_value"],
           "broker_reported_leverage": summary["leverage"],
           "broker_gross_nav": summary["gross_position_value"]/nav,
           "daily_notional_nav_ex_options": multiple, "stock_count": len(stocks),
           "option_count": len(options), "excluded_fx_lines": sum(
               x["asset_class"]=="CASH" for x in j["get_account_positions"]["positions"]),
           "definition": "long securities with daily ETF multipliers; excludes option delta; not beta/VaR"}
    return Snapshot(nav, stocks, options, balances, fx, residual, metadata, rec)

def sessions(start, end, holidays):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    blocked = set(holidays)
    dates = []
    for i in range(1, (b-a).days+1):
        d = a + timedelta(days=i)
        if d.weekday() < 5 and d.isoformat() not in blocked:
            dates.append(d)
    if not dates:
        raise ValueError("empty simulation window")
    return dates

def quarter_indices(dates):
    return [i for i, d in enumerate(dates) if i+1 < len(dates)
            and (d.year, (d.month-1)//3) != (dates[i+1].year, (dates[i+1].month-1)//3)]

def path_returns(endpoint, amplitude, n, first_leg=None):
    """Log-alternating conditions with exact endpoint; optional first-quarter trough."""
    endpoint, amplitude = finite(endpoint, "path endpoint"), finite(amplitude, "path amplitude")
    if first_leg is not None:
        first_leg = finite(first_leg, "first leg")
        if first_leg <= -1 or n < 2:
            raise ValueError("invalid first leg")
    if n < 1 or endpoint <= -1 or amplitude < 0:
        raise ValueError("invalid path")
    if first_leg is not None:
        m = max(1, n//4)
        base = [math.log1p(first_leg)/m]*m + [
            (math.log1p(endpoint)-math.log1p(first_leg))/(n-m)]*(n-m)
    else:
        base = [math.log1p(endpoint)/n]*n
    wave = [amplitude if i%2==0 else -amplitude for i in range(n)]
    mean = sum(wave)/n
    return [math.expm1(x+y-mean) for x,y in zip(base,wave)]

def fund_step(value, index_return, leverage, years, expense, reference, spread):
    if value == 0:
        return 0., 0., 0.
    gross = 1 + leverage * index_return
    if gross <= 0:
        raise ValueError("daily leverage wipeout; model validity ends, no forced floor")
    fee = value * expense * years
    carry = value * (leverage-1) * (reference+spread) * years
    new = value * gross - fee - carry
    if new <= 0:
        raise ValueError("fund depleted; no fabricated survivorship")
    return new, fee, carry

def annual_tier_interest(debt, tiers, shift=0):
    if debt < 0:
        raise ValueError("negative debt argument")
    result, lower = 0., 0.
    for upper, rate in tiers:
        upper = float("inf") if upper is None else upper
        amount = max(0., min(debt,upper)-lower)
        result += amount * max(0., rate+shift)
        lower = upper
        if debt <= upper:
            return result
    raise ValueError("debt exceeds supplied rate tiers")

def repay(cash, fx, budget, priority, fx_cost, usd_debt_before=0.):
    """Spend USD budget to repay each specified currency explicitly, including FX cost."""
    cost, records, remaining = 0., [], max(0., budget)
    for c in priority:
        if c not in cash:
            continue
        debt_usd = usd_debt_before if c == "USD" else max(0., -cash[c]*fx[c])
        rate = 0. if c == "USD" else fx_cost
        principal = min(debt_usd, remaining/(1+rate))
        if principal <= 0:
            continue
        paid = principal*(1+rate)
        if c != "USD":
            cash["USD"] -= paid
            cash[c] += principal/fx[c]
        remaining -= paid
        cost += paid-principal
        records.append({"currency":c, "principal_usd":principal,
                        "native_units_repaid":principal/fx[c], "fx_cost_usd":paid-principal})
    return cost, records

def build_state(snap, strategy, cfg):
    if strategy not in MAIN_STRATEGIES + EXTRA_STRATEGIES:
        raise ValueError("unknown strategy")
    tc, xc = cfg["transaction_cost_bps"]/10000, cfg["fx_cost_bps"]/10000
    assets = {k: {"value":x["market_value"],"currency":x["currency"],
                  "factor":cfg["holding_factors"][k],"leverage":LEVERAGE.get(k,1)}
              for k,x in snap.stocks.items()}
    state = {"assets":assets, "cash":copy.deepcopy(snap.balances),
             "options":copy.deepcopy(snap.options), "cost":0.,
             "repayments":[], "sold_usd":0., "rebalance_cost":0.}
    def sell(k, fraction):
        a = assets[k]
        local = a["value"]*fraction
        value = local*snap.fx[a["currency"]]
        a["value"] -= local
        fee = value*(tc + (xc if a["currency"] != "USD" else 0))
        state["cash"]["USD"] += value-fee
        state["sold_usd"] += value
        state["cost"] += fee
        return value-fee
    if strategy.startswith("exit_soxl"):
        if "SOXL" not in assets:
            raise ValueError("SOXL required for specified comparison")
        budget = sell("SOXL", 1)
        priority = (["CHF","USD","JPY","EUR","KRW"] if strategy=="exit_soxl_chf_first"
                    else ["USD"] if strategy=="exit_soxl_usd_only"
                    else ["USD","CHF","JPY","EUR","KRW"])
        cost, records = repay(state["cash"], snap.fx, budget, priority, xc,
                             max(0., -snap.balances["USD"]))
        state["cost"] += cost
        state["repayments"] = records
    elif strategy == "repay_debt_keep_etfs":
        # Options are kept: no invented option closing quote; assignment can re-create debt.
        pool = [k for k in assets if LEVERAGE.get(k,1)==1]
        total = sum(assets[k]["value"]*snap.fx[assets[k]["currency"]] for k in pool)
        conversion = sum(assets[k]["value"]*snap.fx[assets[k]["currency"]]*xc
                         for k in pool if assets[k]["currency"]!="USD")/total
        required = sum(-v*snap.fx[c]*(1+(xc if c!="USD" else 0))
                       for c,v in state["cash"].items() if v<0)
        fraction = required/(total*(1-tc-conversion))
        if not 0 <= fraction <= 1:
            raise ValueError("insufficient nonleveraged stock pool")
        budget = sum(sell(k,fraction) for k in pool)
        cost, records = repay(state["cash"],snap.fx,budget,list(state["cash"]),xc,
                             max(0., -snap.balances["USD"]))
        state["cost"] += cost
        state["repayments"] = records
    elif strategy in ("qqq", "half_qqq_tqqq", "qqq_keep_puts", "half_qqq_tqqq_keep_puts"):
        # Counterfactual transformation at observed marks, not a claim of executable quotes.
        for k in list(assets):
            sell(k, 1)
        fx_turnover = sum(abs(v)*snap.fx[c] for c,v in state["cash"].items() if c!="USD")
        state["cost"] += fx_turnover*xc
        equity_cash = sum(state["cash"][c]*snap.fx[c] for c in state["cash"])-fx_turnover*xc
        if not strategy.endswith("_keep_puts"):
            close_mark = -sum(x["usd_value"] for x in state["options"])
            gap = close_mark*cfg["option_close_gap_fraction"]
            equity_cash -= close_mark + gap
            state["cost"] += gap
            state["options"] = []
        # Investment buy fee is charged once on purchased value.
        investment = equity_cash/(1+tc)
        state["cost"] += investment*tc
        state["cash"] = {c:0. for c in snap.fx}
        assets.clear()
        parts = {"QQQ":1.} if strategy.startswith("qqq") else {"QQQ":.5,"TQQQ":.5}
        for k,w in parts.items():
            assets[k] = {"value":investment*w,"currency":"USD","factor":"nasdaq","leverage":LEVERAGE[k]}
    state["initial_daily_notional_nav"] = sum(
        a["value"]*snap.fx[a["currency"]]*a["leverage"] for a in assets.values())/snap.nav
    state["initial_cash"] = copy.deepcopy(state["cash"])
    state["initial_assets"] = copy.deepcopy(assets)
    return state

def rebalance_half(assets, transaction_cost):
    q,t = assets["QQQ"]["value"],assets["TQQQ"]["value"]
    total=q+t
    # Exact 50/50 after fees: fee charged to both buy and sell turnover.
    # Solve total_after = total - cost * (abs(q-target)+abs(t-target)).
    lo,hi = 0.,total
    for _ in range(70):
        target=(lo+hi)/4
        fee=transaction_cost*(abs(q-target)+abs(t-target))
        if 2*target+fee>total:
            hi=2*target
        else:
            lo=2*target
    target=(lo+hi)/4
    fee=total-2*target
    assets["QQQ"]["value"]=assets["TQQQ"]["value"]=target
    return fee

def option_specs(snap, cfg):
    specs = cfg.get("option_contracts", {})
    anchors = {}
    for o in snap.options:
        key = str(o["contract_id"])
        if key not in specs:
            raise ValueError("missing known option contract information")
        s=specs[key]
        if s.get("put_call") != "PUT":
            raise ValueError("explicit known PUT contract required")
        for field in ("underlying","expiry","strike","anchor_price","factor"):
            if field not in s:
                raise ValueError("missing option field "+field)
        anchor = finite(s["anchor_price"], "option underlying anchor")
        if anchor <= 0 or finite(s["strike"], "option strike") <= 0:
            raise ValueError("positive option prices required")
        if date.fromisoformat(s["expiry"]) < date.fromisoformat(cfg["start_date"]):
            raise ValueError("expired option in initial state")
        if s["underlying"] in anchors and anchors[s["underlying"]] != (anchor, s["factor"]):
            raise ValueError("inconsistent underlying anchor or factor")
        anchors[s["underlying"]] = (anchor, s["factor"])
        holding = snap.stocks.get(s["underlying"])
        if holding and (holding["currency"] != "USD" or not math.isclose(
                holding["market_price"], anchor, rel_tol=1e-8)):
            raise ValueError("option anchor differs from same-snapshot underlying")
        if s.get("contractual_multiplier") is None or s.get("deliverable") is None:
            if not cfg.get("allow_conditional_100"):
                raise ValueError("contract deliverable unknown; conditional 100 opt-in required")
        elif s["contractual_multiplier"] != 100 or s["deliverable"]!="100_underlying_units":
            raise ValueError("unsupported adjusted option contract")
        if not math.isclose(o["implied_valuation_multiplier"],100,rel_tol=1e-6):
            raise ValueError("mark multiplier differs from conditional standard contract")
    return specs

def european_put(spot, strike, years, volatility, rate, dividend_yield=0.):
    """European Black-Scholes sensitivity proxy per unit, never an execution quote."""
    spot, strike, years, volatility, rate, dividend_yield = [
        finite(v, "option model input") for v in
        (spot, strike, years, volatility, rate, dividend_yield)]
    if spot <= 0 or strike <= 0 or years < 0 or volatility < 0:
        raise ValueError("invalid option model input")
    if years == 0:
        return max(strike-spot, 0.)
    discounted_strike = strike*math.exp(-rate*years)
    discounted_spot = spot*math.exp(-dividend_yield*years)
    if volatility == 0:
        return max(discounted_strike-discounted_spot, 0.)
    sigma_t = volatility*math.sqrt(years)
    d1 = (math.log(spot/strike)+(rate-dividend_yield+volatility**2/2)*years)/sigma_t
    d2 = d1-sigma_t
    cdf = lambda x: .5*(1+math.erf(x/math.sqrt(2)))
    return max(0., discounted_strike*cdf(-d2)-discounted_spot*cdf(-d1))

def option_mtm_inputs(specs, cfg, scenario):
    method = cfg.get("option_valuation", "frozen_snapshot")
    if method not in ("frozen_snapshot", "anchored_european"):
        raise ValueError("unsupported option valuation")
    if method == "frozen_snapshot":
        if scenario.get("option_iv_shift", 0) != 0:
            raise ValueError("volatility shock requires explicit option MTM")
        return None
    shift = finite(scenario.get("option_iv_shift", 0), "IV shift")
    result = {}
    for key, spec in specs.items():
        if any(k not in spec for k in ("annual_iv", "risk_free_rate", "dividend_yield")):
            raise ValueError("explicit IV, rate and dividend yield required")
        values = {k: finite(spec[k], k) for k in ("annual_iv", "risk_free_rate", "dividend_yield")}
        if values["annual_iv"] <= 0 or values["annual_iv"]+shift <= 0:
            raise ValueError("positive explicit option IV required")
        years = (date.fromisoformat(spec["expiry"])-date.fromisoformat(cfg["start_date"])).days/365
        result[key] = {**values, "base_model": european_put(spec["anchor_price"], spec["strike"],
            years, values["annual_iv"], values["risk_free_rate"], values["dividend_yield"])}
    return result

def anchored_put_mark(initial_mark, initial_model, initial_years, spot, strike,
                      remaining_years, volatility, rate, dividend_yield):
    """Model change plus linearly decaying mark/model basis, converging to intrinsic.

    Intrinsic floor/strike cap are envelopes only. American early exercise,
    discrete dividends, executable prices and broker margin are not modeled.
    """
    model = european_put(spot, strike, remaining_years, volatility, rate, dividend_yield)
    basis = (initial_mark-initial_model)*remaining_years/initial_years if initial_years > 0 else 0.
    return min(strike, max(strike-spot, 0., model+basis))

def run_scenario(snap, cfg, scenario, strategy, store_path=False):
    specs = option_specs(snap,cfg)
    mtm = option_mtm_inputs(specs,cfg,scenario)
    dates=sessions(cfg["start_date"],cfg["end_date"],cfg["holidays"])
    start,end=date.fromisoformat(cfg["start_date"]),date.fromisoformat(cfg["end_date"])
    paths = {f:path_returns(a["endpoint"],a["amplitude"],len(dates),a.get("first_leg"))
             for f,a in scenario["factors"].items()}
    for name in snap.stocks:
        factor=cfg["holding_factors"].get(name)
        if factor not in paths:
            raise ValueError("missing holding factor; no fabricated fallback")
    fx_levels={c:1. for c in snap.fx}
    fx_steps={c:math.log1p(scenario.get("fx_changes",{}).get(c,0))/len(dates) for c in snap.fx}
    state=build_state(snap,strategy,cfg)
    assets,cash=state["assets"],state["cash"]
    pending=state["options"]
    accrued={c:0. for c in cash}
    under_prices={s["underlying"]:s["anchor_price"] for s in specs.values()}
    q_indices=set(quarter_indices(dates))
    interest_usd=fee_usd=carry_usd=assignment_usd=0.
    events,rows=[],[]
    initial_option_mark=sum(x["usd_value"] for x in pending)
    def nav():
        return (sum(a["value"]*snap.fx[a["currency"]]*fx_levels[a["currency"]] for a in assets.values())
                +sum((cash[c]-accrued[c])*snap.fx[c]*fx_levels[c] for c in cash)
                +sum(o["usd_value"] for o in pending)+snap.residual)
    current=nav()
    if not math.isclose(current,snap.nav-state["cost"],abs_tol=0.001):
        raise AssertionError("initial NAV conservation failed")
    peak=snap.nav
    min_nav=current
    drawdown=min(0.,current/peak-1)
    initial_nav=current
    for i,d in enumerate(dates):
        last_date=start if i==0 else dates[i-1]
        duration=(d-last_date).days
        if i==len(dates)-1:
            duration += (end-d).days
        years=duration/365
        # Financing accrued on beginning settled balances, then marked at current FX.
        for c,v in cash.items():
            if v < -1e-6:
                if c not in cfg["rate_tiers"]:
                    raise ValueError("missing currency financing curve")
                annual=annual_tier_interest(-v,cfg["rate_tiers"][c],scenario.get("rate_shift",0))
                charge=annual*duration/cfg["interest_day_count"][c]
                accrued[c]+=charge
                interest_usd += charge*snap.fx[c]*fx_levels[c]*math.exp(fx_steps[c])
        for c in fx_levels:
            fx_levels[c]*=math.exp(fx_steps[c])
        for k,a in assets.items():
            r=paths[a["factor"]][i]
            if k in LEVERAGE:
                value,fee,carry=fund_step(a["value"],r,a["leverage"],years,
                    cfg["fund_expense"][k],cfg["fund_reference_rate"]+scenario.get("rate_shift",0),
                    cfg["fund_financing_spread"])
                a["value"]=value
                fee_usd+=fee*snap.fx[a["currency"]]*fx_levels[a["currency"]]
                carry_usd+=carry*snap.fx[a["currency"]]*fx_levels[a["currency"]]
            else:
                a["value"]*=1+r
        seen=set()
        for spec in specs.values():
            u=spec["underlying"]
            if u not in seen:
                under_prices[u]*=1+paths[spec["factor"]][i]
                seen.add(u)
        for o in list(pending):
            s=specs[str(o["contract_id"])]
            if mtm is not None and d < date.fromisoformat(s["expiry"]):
                inputs=mtm[str(o["contract_id"])]
                initial_years=(date.fromisoformat(s["expiry"])-start).days/365
                remaining_years=(date.fromisoformat(s["expiry"])-d).days/365
                mark=anchored_put_mark(o["market_price"],inputs["base_model"],initial_years,
                    under_prices[s["underlying"]],s["strike"],remaining_years,
                    inputs["annual_iv"]+scenario.get("option_iv_shift",0),
                    inputs["risk_free_rate"]+scenario.get("rate_shift",0),inputs["dividend_yield"])
                o["usd_value"]=o["position"]*100*mark
            if d >= date.fromisoformat(s["expiry"]):
                units=abs(o["position"])*100
                price=under_prices[s["underlying"]]
                event={"date":d.isoformat(),"contract_id":o["contract_id"],"conditional_100":True,
                       "underlying_price_condition":price,"assigned":price<s["strike"],
                       "cash_demand_usd":0.}
                if price<s["strike"]:
                    payment=units*s["strike"]
                    cash["USD"]-=payment
                    key="assignment_"+str(o["contract_id"])
                    assets[key]={"value":units*price,"currency":"USD","factor":s["factor"],"leverage":1}
                    assignment_usd+=payment
                    event["cash_demand_usd"]=payment
                pending.remove(o)
                events.append(event)
        if i in q_indices and strategy.startswith("half_qqq_tqqq"):
            cost=rebalance_half(assets,cfg["transaction_cost_bps"]/10000)
            state["rebalance_cost"]+=cost
            events.append({"date":d.isoformat(),"rebalance":"50/50 after costs","cost_usd":cost})
        if i==len(dates)-1 or dates[i+1].month != d.month:
            for c in cash:
                cash[c]-=accrued[c]
                accrued[c]=0.
        current=nav()
        peak=max(peak,current)
        min_nav=min(min_nav,current)
        drawdown=min(drawdown,current/peak-1)
        if store_path:
            rows.append({"date":d.isoformat(),"nav_usd":current,"grid_drawdown":current/peak-1,
                         "pending_option_liability_usd":-sum(o["usd_value"] for o in pending)})
    result={"scenario":scenario["name"],"strategy":strategy,"end_nav_usd":current,
            "nav_return":current/snap.nav-1,"grid_drawdown":drawdown,
            "min_grid_nav_usd":min_nav,"initial_cost_usd":state["cost"],
            "external_interest_usd":interest_usd,"fund_fee_usd":fee_usd,
            "fund_financing_usd":carry_usd,"rebalance_cost_usd":state["rebalance_cost"],
            "assignment_cash_usd":assignment_usd,
            "end_debt_usd":sum(max(0.,-cash[c])*snap.fx[c]*fx_levels[c] for c in cash),
            "initial_daily_notional_nav":state["initial_daily_notional_nav"],
            "option_proxy_warning":("Conditional100; anchored European MTM sensitivity with decaying mark basis; "
                "no American early exercise, discrete dividends or broker margin model" if mtm is not None else
                "Conditional100; snapshot marks frozen before expiry, physical assignment proxy; no margin MTM"),
            "events":events,"path":rows,
            "initial_nav_after_cost":initial_nav,
            "initial_option_mark_usd":initial_option_mark}
    return result

def run_all(snap,cfg):
    rows=[]
    for scenario in cfg["scenarios"]:
        for strategy in MAIN_STRATEGIES+EXTRA_STRATEGIES:
            rows.append(run_scenario(snap,cfg,scenario,strategy,True))
    return rows

def write_outputs(destination,snap,cfg,results,mode):
    root=Path(destination).resolve()
    root.mkdir(parents=True,exist_ok=True)
    (root/"reconciliation.json").write_text(json.dumps(snap.reconciliation,indent=2),encoding="utf-8")
    (root/"source_manifest.json").write_text(json.dumps(
        {"snapshot":snap.metadata,"public_sources":cfg.get("public_sources",[]),
         "scenario_source":{"provider_name":"user_authorized_deterministic_conditions",
                            "provider_level":0,"retrieval_time":None,"source_id":"scenario_config",
                            "stale":False,"reliability":"uncalibrated conditions",
                            "warning_codes":["NOT_OBSERVED_DATA","NOT_A_BACKTEST"]}},indent=2),encoding="utf-8")
    policy={"mode":mode,"research_only":True,"network_access":False,
            "broker_access":False,"order_placement":False,"automatic_pm_output_valid":False,
            "reason_codes":["OFFLINE_STRESS_RESEARCH","CONTRACT_CONDITIONAL","UNKNOWN_PRICE_FRESHNESS"],
            "strict_arithmetic_audit":"passed","strict_investment_claim_audit":"blocked",
            "investment_gates":{"evidence":"snapshot_only","data_quality":"valuation_time_unknown",
                                "valuation":"no_forecast_or_relative_valuation",
                                "portfolio":"no_optimized_weights","risk":"no_margin_model",
                                "red_team":"counterexamples_required","output_validation":"research_only"}}
    (root/"policy_manifest.json").write_text(json.dumps(policy,indent=2),encoding="utf-8")
    if mode=="autopm":
        (root/"results.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
        with (root/"results.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=RESULT_FIELDS)
            w.writeheader()
            w.writerows({k:r[k] for k in RESULT_FIELDS} for r in results)
        starts={s:build_state(snap,s,cfg) for s in MAIN_STRATEGIES+EXTRA_STRATEGIES}
        for s in starts:
            starts[s].pop("assets")
            starts[s].pop("options")
        (root/"initial_states.json").write_text(json.dumps(starts,indent=2),encoding="utf-8")
    manifest={"schema_version":SCHEMA_VERSION,"mode":mode,"research_only":True,
              "config_sha256":hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest(),
              "snapshot_sha256":snap.metadata["sha256"],"scenario_count":len(cfg.get("scenarios",[])),
              "result_count":len(results),"initial_nav_residual_fixed_usd":snap.residual,
              "engine_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (root/"run_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot",required=True)
    parser.add_argument("--config",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--now",required=True,help="explicit timezone-aware snapshot audit clock")
    parser.add_argument("--mode",choices=("review_first","autopm"),default="review_first")
    args=parser.parse_args(argv)
    cfg=json.loads(Path(args.config).read_text(encoding="utf-8"))
    if cfg.get("research_only") is not True:
        raise ValueError("explicit research_only configuration required")
    snap=load_snapshot(args.snapshot,cfg,args.now)
    results=run_all(snap,cfg) if args.mode=="autopm" else []
    manifest=write_outputs(args.output,snap,cfg,results,args.mode)
    print(json.dumps({"schema_version":SCHEMA_VERSION,"mode":args.mode,
                      "result_count":manifest["result_count"],"research_only":True}))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

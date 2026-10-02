"""Only invented synthetic values; never load private research inputs."""
import copy
import hashlib
import importlib.util
import json
import math
import socket
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from ai_pm_agent.autopm import portfolio_path_stress as m

def config():
    return {"provider_level":0,"allow_private_input":False,"allow_conditional_100":True,"research_only":True,
      "source_id":"synthetic-test","start_date":"2026-10-02","end_date":"2027-10-02",
      "holidays":[],"holding_factors":{"TQQQ":"nasdaq","SOXL":"semis","SYNTH":"other"},
      "transaction_cost_bps":10,"fx_cost_bps":5,"option_close_gap_fraction":.1,
      "fund_expense":{"QQQ":.002,"TQQQ":.01,"SOXL":.01},
      "fund_reference_rate":.04,"fund_financing_spread":.005,
      "rate_tiers":{"USD":[[100,.05],[None,.04]],"CHF":[[None,.01]],"JPY":[[None,.02]]},
      "interest_day_count":{"USD":360,"CHF":360,"JPY":360},
      "option_contracts":{"4":{"underlying":"OPT_SYNTH","expiry":"2026-10-16","strike":10,"put_call":"PUT",
                               "anchor_price":9,"factor":"other","contractual_multiplier":None,
                               "deliverable":None}},
      "scenarios":[{"name":"flat","factors":{k:{"endpoint":0.,"amplitude":0.}
                                 for k in ("nasdaq","semis","other")},"fx_changes":{}}]}

def raw():
    def pos(i,name,qty,price,kind="STK"):
        return {"contract_id":i,"contract_description":name,"position":qty,"market_price":price,
                "market_value":qty*price*(100 if kind=="OPT" else 1),
                "currency":"USD","asset_class":kind}
    return {"retrieved_utc":"2026-10-02T12:00:00Z",
      "get_account_summary":{"currency":"USD","net_liquidation":1920.,
        "total_cash_value":-560.,"gross_position_value":2520.,"leverage":"synthetic"},
      "get_account_balances":{"balances":[{"currency":c,"cash_balance":b,"exchange_rate":f}
        for c,b,f in [("BASE",-560,1),("USD",-100,1),("CHF",-300,1.2),("JPY",-10000,.01)]]},
      "get_account_positions":{"positions":[pos(1,"TQQQ",10,100),pos(2,"SOXL",5,100),
                         pos(3,"SYNTH",10,100),pos(4,"synthetic put",-1,.2,"OPT"),
                         pos(5,"synthetic FX",99,22,"CASH")]}}

@pytest.fixture
def fixture(tmp_path):
    p=tmp_path/"synthetic.json";p.write_text(json.dumps(raw()))
    c=config()
    return p,c,m.load_snapshot(p,c,"2026-10-02T12:01:00Z")

def test_cash_fx_lines_and_base_not_double_counted(fixture):
    _,_,s=fixture
    assert s.reconciliation["cash_ledger_usd"]==-560
    assert s.reconciliation["excluded_fx_lines"]==1
    assert s.residual==0

def enable_mtm(c):
    c["option_valuation"]="anchored_european"
    c["option_contracts"]["4"].update(annual_iv=.4,risk_free_rate=.04,dividend_yield=0.)
    return c

def test_european_put_reference_and_limits():
    # Standard independent textbook reference S=K=100, r=5%, sigma=20%, T=1.
    assert m.european_put(100,100,1,.2,.05)==pytest.approx(5.5735260223)
    assert m.european_put(80,100,0,.2,.05)==20
    assert m.european_put(120,100,0,.2,.05)==0
    assert m.european_put(90,100,1,0,0)==10

@pytest.mark.parametrize("args",[(0,100,1,.2,.05),(100,-1,1,.2,.05),
    (100,100,-1,.2,.05),(100,100,1,-.2,.05),(100,100,1,float('nan'),.05)])
def test_european_invalid_inputs(args):
    with pytest.raises(ValueError):m.european_put(*args)

def test_european_direction_volatility_and_dividend_sensitivities():
    p=m.european_put(100,100,1,.2,.04)
    assert m.european_put(90,100,1,.2,.04)>p
    assert m.european_put(100,100,1,.4,.04)>p
    assert m.european_put(100,100,1,.2,.04,.03)>p

def test_anchor_basis_decays_and_expiry_matches_intrinsic():
    model=m.european_put(100,100,1,.2,.04)
    mark=model+1
    assert m.anchored_put_mark(mark,model,1,100,100,1,.2,.04,0)==pytest.approx(mark)
    assert m.anchored_put_mark(mark,model,1,80,100,0,.2,.04,0)==20

def test_iv_shock_requires_explicit_mtm(fixture):
    _,c,s=fixture
    scenario=copy.deepcopy(c['scenarios'][0]);scenario['option_iv_shift']=.2
    with pytest.raises(ValueError,match='requires explicit'):m.run_scenario(s,c,scenario,'current')

def test_missing_mtm_inputs_fail_closed(fixture):
    _,c,s=fixture;c['option_valuation']='anchored_european'
    with pytest.raises(ValueError,match='explicit IV'):m.run_scenario(s,c,c['scenarios'][0],'current')

def test_negative_shocked_iv_fails(fixture):
    _,c,s=fixture;enable_mtm(c)
    scenario=copy.deepcopy(c['scenarios'][0]);scenario['option_iv_shift']=-.5
    with pytest.raises(ValueError,match='positive explicit'):m.run_scenario(s,c,scenario,'current')

def test_preexpiry_vol_shock_changes_liability_and_nav(fixture):
    _,c,s=fixture;enable_mtm(c);c['end_date']='2026-10-09'
    c['option_contracts']['4']['anchor_price']=10
    baseline=m.run_scenario(s,c,c['scenarios'][0],'current',True)
    scenario=copy.deepcopy(c['scenarios'][0]);scenario['option_iv_shift']=.8
    stressed=m.run_scenario(s,c,scenario,'current',True)
    assert stressed['end_nav_usd']<baseline['end_nav_usd']
    assert stressed['path'][-1]['pending_option_liability_usd']>baseline['path'][-1]['pending_option_liability_usd']
    assert stressed['initial_nav_after_cost']==baseline['initial_nav_after_cost']
    assert stressed['assignment_cash_usd']==0

def test_mtm_expiry_does_not_double_count_assignment_or_change_financing(fixture):
    _,c,s=fixture
    frozen=m.run_scenario(s,c,c['scenarios'][0],'repay_debt_keep_etfs')
    enable_mtm(c)
    marked=m.run_scenario(s,c,c['scenarios'][0],'repay_debt_keep_etfs')
    for k in ('end_nav_usd','assignment_cash_usd','end_debt_usd','external_interest_usd'):
        assert marked[k]==pytest.approx(frozen[k])
    assert marked['assignment_cash_usd']==1000
    assert marked['external_interest_usd']>0

def test_mtm_no_network_and_input_unchanged(fixture):
    p,c,s=fixture;enable_mtm(c);before=hashlib.sha256(p.read_bytes()).hexdigest()
    with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
        m.run_scenario(s,c,c['scenarios'][0],'current')
    assert hashlib.sha256(p.read_bytes()).hexdigest()==before

def test_reused_daily_notional_definition(fixture):
    _,_,s=fixture
    assert s.reconciliation["daily_notional_nav_ex_options"]==pytest.approx(5500/1920)

@pytest.mark.parametrize("change",["missing_fx","bad_unit","duplicate_contract","unsupported","nonfinite"])
def test_invalid_inputs_fail_closed(tmp_path,change):
    j=raw()
    if change=="missing_fx":j["get_account_positions"]["positions"][0]["currency"]="GBP"
    if change=="bad_unit":j["get_account_positions"]["positions"][0]["market_value"]=999
    if change=="duplicate_contract":j["get_account_positions"]["positions"][1]["contract_id"]=1
    if change=="unsupported":j["get_account_positions"]["positions"][0]["asset_class"]="FUT"
    if change=="nonfinite":j["get_account_balances"]["balances"][1]["cash_balance"]=float("nan")
    p=tmp_path/"fake.json";p.write_text(json.dumps(j))
    with pytest.raises(ValueError):m.load_snapshot(p,config(),"2026-10-02T12:01:00Z")

def test_missing_snapshot(tmp_path):
    with pytest.raises(FileNotFoundError):
        m.load_snapshot(tmp_path/"absent",config(),"2026-10-02T12:01:00Z")

def test_private_provider_opt_in(fixture):
    p,c,_=fixture;c["provider_level"]=3;c["allow_private_input"]=False
    with pytest.raises(ValueError,match="allow_private_input"):m.load_snapshot(p,c,"2026-10-02T12:01:00Z")

def test_stale_and_unknown_price_quality_fail_investment_gate(fixture):
    p,c,_=fixture
    with pytest.raises(ValueError,match="stale"):m.load_snapshot(p,c,"2026-10-05T12:00:00Z")
    c["allow_stale_scenario"]=True
    s=m.load_snapshot(p,c,"2026-10-05T12:00:00Z")
    assert s.metadata["stale"] is True
    assert s.metadata["investment_output_valid"] is False
    assert "PRICE_FRESHNESS_UNKNOWN" in s.metadata["warning_codes"]

def test_unexplained_residual_preserved(tmp_path):
    j=raw();j["get_account_summary"]["net_liquidation"]+=3
    p=tmp_path/"synthetic.json";p.write_text(json.dumps(j))
    s=m.load_snapshot(p,config(),"2026-10-02T12:01:00Z")
    assert s.residual==3

def test_path_endpoint_exact_and_path_dependent_daily_compounding():
    smooth=m.path_returns(.2,0,252)
    chop=m.path_returns(.2,.02,252)
    assert math.prod(1+r for r in smooth)==pytest.approx(1.2)
    assert math.prod(1+r for r in chop)==pytest.approx(1.2)
    assert math.prod(1+3*r for r in smooth)>math.prod(1+3*r for r in chop)
    assert math.prod(1+3*r for r in smooth)!=pytest.approx(1.6)

def test_odd_length_path_endpoint_and_recovery():
    for n in (251,252):
        ds=m.path_returns(.2,.03,n,-.4)
        assert math.prod(1+r for r in ds)==pytest.approx(1.2)

def test_daily_wipeout_no_fabricated_survival():
    with pytest.raises(ValueError,match="wipeout"):m.fund_step(100,-.34,3,1/365,.01,.04,0)

def test_fee_and_internal_financing_counted_once():
    new,fee,carry=m.fund_step(100,.01,3,1,.01,.04,.005)
    assert fee==1
    assert carry==9
    assert new==93

def test_zero_position_safe():
    assert m.fund_step(0,.01,3,1,.01,.04,.005)==(0,0,0)

def test_public_tiers_incremental():
    assert m.annual_tier_interest(150,[[100,.05],[None,.04]])==7
    assert m.annual_tier_interest(150,[[100,.05],[None,.04]],.02)==10

@pytest.mark.parametrize("strategy",m.MAIN_STRATEGIES+m.EXTRA_STRATEGIES)
def test_conservation_after_initial_cost(fixture,strategy):
    _,c,s=fixture
    result=m.run_scenario(s,c,c["scenarios"][0],strategy)
    assert result["initial_nav_after_cost"]==pytest.approx(s.nav-result["initial_cost_usd"])

def test_repay_usd_then_chf_uses_right_currency(fixture):
    _,c,s=fixture
    state=m.build_state(s,"exit_soxl",c)
    assert state["initial_cash"]["USD"]>=-1e-8
    assert state["initial_cash"]["CHF"]>s.balances["CHF"]
    assert state["repayments"][0]["currency"]=="USD"
    assert state["repayments"][0]["principal_usd"]==100

def test_usd_surplus_does_not_silently_pay_chf(fixture):
    _,c,s=fixture
    state=m.build_state(s,"exit_soxl_usd_only",c)
    assert state["initial_cash"]["USD"]>0
    assert state["initial_cash"]["CHF"]==s.balances["CHF"]

def test_debt_repayment_keeps_3x_and_options(fixture):
    _,c,s=fixture
    state=m.build_state(s,"repay_debt_keep_etfs",c)
    assert state["assets"]["TQQQ"]["value"]==1000
    assert state["assets"]["SOXL"]["value"]==500
    assert len(state["options"])==1
    assert all(v>=-1e-7 for v in state["cash"].values())

def test_assignment_recreates_usd_debt_after_initial_repayment(fixture):
    _,c,s=fixture
    result=m.run_scenario(s,c,c["scenarios"][0],"repay_debt_keep_etfs")
    assert result["assignment_cash_usd"]==1000
    assert result["end_debt_usd"]>=1000
    assert result["external_interest_usd"]>0

def test_conditional_contract_gate(fixture):
    _,c,s=fixture;c["allow_conditional_100"]=False
    with pytest.raises(ValueError,match="deliverable"):m.option_specs(s,c)

def test_implied_multiplier_not_contract_verification(fixture):
    _,c,s=fixture
    assert s.options[0]["implied_valuation_multiplier"]==100
    assert c["option_contracts"]["4"]["contractual_multiplier"] is None

def test_missing_option_information_not_inferred(fixture):
    _,c,s=fixture;c["option_contracts"]={}
    with pytest.raises(ValueError,match="missing"):m.option_specs(s,c)

def test_adjusted_deliverable_not_silently_standard(fixture):
    _,c,s=fixture;c["option_contracts"]["4"].update(contractual_multiplier=100,deliverable="adjusted basket")
    with pytest.raises(ValueError,match="adjusted"):m.option_specs(s,c)

def test_missing_factor_fails(fixture):
    _,c,s=fixture;c["holding_factors"]["SYNTH"]="absent"
    with pytest.raises(ValueError,match="factor"):m.run_scenario(s,c,c["scenarios"][0],"current")

def test_short_call_not_treated_as_put(fixture):
    _,c,s=fixture;c["option_contracts"]["4"]["put_call"]="CALL"
    with pytest.raises(ValueError,match="PUT"):m.option_specs(s,c)

def test_option_same_snapshot_anchor_inconsistent(fixture):
    _,c,s=fixture;c["option_contracts"]["4"]["underlying"]="SYNTH"
    with pytest.raises(ValueError,match="anchor differs"):m.option_specs(s,c)

def test_expired_option_is_not_assigned_in_future(fixture):
    _,c,s=fixture;c["option_contracts"]["4"]["expiry"]="2026-01-01"
    with pytest.raises(ValueError,match="expired"):m.option_specs(s,c)

def test_calendar_quarter_not_fixed_63_sessions():
    ds=m.sessions("2026-10-02","2027-10-02",["2026-12-25","2027-01-01"])
    assert [ds[i].isoformat() for i in m.quarter_indices(ds)]==[
        "2026-12-31","2027-03-31","2027-06-30","2027-09-30"]

def test_rebalance_after_two_sided_cost_conserves_value():
    assets={"QQQ":{"value":40.},"TQQQ":{"value":80.}}
    cost=m.rebalance_half(assets,.001)
    assert assets["QQQ"]["value"]==assets["TQQQ"]["value"]
    assert 2*assets["QQQ"]["value"]+cost==pytest.approx(120)
    assert cost>0

def test_weak_evidence_not_a_valid_pm_output(fixture,tmp_path):
    _,c,s=fixture
    m.write_outputs(tmp_path,s,c,[],"review_first")
    p=json.loads((tmp_path/"policy_manifest.json").read_text())
    assert p["automatic_pm_output_valid"] is False
    assert p["strict_investment_claim_audit"]=="blocked"

def test_no_network_or_input_mutation(fixture):
    p,c,s=fixture;before=hashlib.sha256(p.read_bytes()).hexdigest()
    with patch.object(socket,"socket",side_effect=AssertionError("network forbidden")):
        m.run_scenario(s,c,c["scenarios"][0],"current")
    assert hashlib.sha256(p.read_bytes()).hexdigest()==before

@pytest.mark.parametrize("explicit_mode",["review_first","autopm"])
def test_cli_and_schema(fixture,tmp_path,capsys,explicit_mode):
    p,c,_=fixture;cp=tmp_path/"synthetic_config.json";cp.write_text(json.dumps(c))
    dest=tmp_path/"output"
    args=["--snapshot",str(p),"--config",str(cp),"--now","2026-10-02T12:01:00Z","--output",str(dest)]
    if explicit_mode=="autopm":args+=["--mode","autopm"]
    assert m.main(args)==0
    msg=json.loads(capsys.readouterr().out)
    assert msg["mode"]==explicit_mode
    assert (dest/"results.csv").exists()==(explicit_mode=="autopm")
    if explicit_mode=="autopm":
        result=json.loads((dest/"results.json").read_text())[0]
        assert set(m.RESULT_FIELDS).issubset(result)
        assert result["option_proxy_warning"].startswith("Conditional100")

@pytest.mark.parametrize("mode",["review_first","autopm"])
def test_actual_cli_wrapper(fixture,tmp_path,mode):
    import subprocess
    p,c,_=fixture
    cp=tmp_path/"config.json";cp.write_text(json.dumps(c))
    destination=tmp_path/"wrapper_output"
    script=Path(__file__).resolve().parents[1]/"scripts/portfolio_path_stress.py"
    command=[sys.executable,"-B",str(script),"--snapshot",str(p),"--config",str(cp),
             "--now","2026-10-02T12:01:00Z","--output",str(destination)]
    if mode=="autopm":command+=["--mode","autopm"]
    result=subprocess.run(command,cwd=tmp_path,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)["mode"]==mode
    assert (destination/"results.csv").exists()==(mode=="autopm")

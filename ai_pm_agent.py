import os
import json
import argparse
import datetime as dt
import re
import random
import sqlite3
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


load_dotenv()
console = Console()

RESEARCH_VERSION = "AI PM Agent v0.3 Deep Research"
DEFAULT_WATCHLIST_PATH = "watchlist.csv"
FINANCIAL_TICKER_ALIASES = {
    # Secondary/GDR listings can mix local quote currency with primary-market
    # KRW financial statements in yfinance. Use primary listings for financials.
    "HY9H.F": "000660.KS",   # SK hynix primary Korea listing
    "SMSN.IL": "005930.KS",  # Samsung Electronics primary Korea listing
}
COMPANY_NAME_ALIASES = {
    # yfinance can occasionally return stale or incorrect shortName values.
    "PSTG": "Pure Storage, Inc.",
}
COMPANY_PRIMARY_DOMAIN_MAP = {
    "SK hynix": {"skhynix.com", "www.skhynix.com", "news.skhynix.com"},
    "SK Hynix": {"skhynix.com", "www.skhynix.com", "news.skhynix.com"},
    "Samsung Electronics": {"samsung.com", "www.samsung.com", "semiconductor.samsung.com"},
    "Samsung Electronics Co Ltd": {"samsung.com", "www.samsung.com", "semiconductor.samsung.com"},
    "Micron": {"micron.com", "www.micron.com", "investors.micron.com"},
    "Micron Technology Inc": {"micron.com", "www.micron.com", "investors.micron.com"},
    "Nvidia": {"nvidia.com", "www.nvidia.com", "investor.nvidia.com"},
    "AMD": {"amd.com", "www.amd.com", "ir.amd.com"},
    "Broadcom": {"broadcom.com", "www.broadcom.com", "investors.broadcom.com"},
    "Marvell": {"marvell.com", "www.marvell.com", "investor.marvell.com"},
    "Arista": {"arista.com", "www.arista.com", "investors.arista.com"},
    "Cisco": {"cisco.com", "www.cisco.com", "investor.cisco.com"},
    "Ciena": {"ciena.com", "www.ciena.com", "investor.ciena.com"},
    "Lumentum": {"lumentum.com", "www.lumentum.com", "investor.lumentum.com"},
    "Coherent": {"coherent.com", "www.coherent.com", "investors.coherent.com"},
    "Fabrinet": {"fabrinet.com", "www.fabrinet.com", "investor.fabrinet.com"},
    "Western Digital": {"westerndigital.com", "www.westerndigital.com", "investor.wdc.com"},
    "Seagate": {"seagate.com", "www.seagate.com", "investors.seagate.com"},
    "Super Micro": {"supermicro.com", "www.supermicro.com", "ir.supermicro.com"},
    "Celestica": {"celestica.com", "www.celestica.com", "investors.celestica.com"},
    "Quanta": {"quantatw.com", "www.quantatw.com"},
    "TSMC": {"tsmc.com", "www.tsmc.com", "investor.tsmc.com"},
    "Vertiv": {"vertiv.com", "www.vertiv.com", "investors.vertiv.com"},
    "Eaton": {"eaton.com", "www.eaton.com", "investor.eaton.com"},
    "GE Vernova": {"gevernova.com", "www.gevernova.com", "investors.gevernova.com"},
    "Schneider Electric": {"se.com", "www.se.com"},
    "Delta Electronics": {"deltaww.com", "www.deltaww.com"},
    "Kioxia": {"kioxia.com", "www.kioxia.com"},
    "ASMPT": {"asmpt.com", "www.asmpt.com"},
    "Ibiden": {"ibiden.com", "www.ibiden.com"},
    "Unimicron": {"unimicron.com", "www.unimicron.com"},
    "Zhongji Innolight": {"innolight.com", "www.innolight.com"},
    "Eoptolink": {"eoptolink.com", "www.eoptolink.com"},
    "Accelink": {"accelink.com", "www.accelink.com"},
    "TFC Communication": {"tfcsz.com", "www.tfcsz.com"},
    "Yangtze Optical Fibre": {"yofc.com", "www.yofc.com"},
    "Cambridge Technology": {"c-technology.com.cn", "www.c-technology.com.cn"},
    "Shennan Circuits": {"scc.com.cn", "www.scc.com.cn"},
    "Hengtong Optic-Electric": {"hengtonggroup.com", "www.hengtonggroup.com"},
    "Huagong Tech": {"hgtech.com.cn", "www.hgtech.com.cn"},
}
COMPANY_TICKER_DOMAIN_MAP = {
    "NVDA": COMPANY_PRIMARY_DOMAIN_MAP["Nvidia"],
    "AMD": COMPANY_PRIMARY_DOMAIN_MAP["AMD"],
    "AVGO": COMPANY_PRIMARY_DOMAIN_MAP["Broadcom"],
    "MRVL": COMPANY_PRIMARY_DOMAIN_MAP["Marvell"],
    "ANET": COMPANY_PRIMARY_DOMAIN_MAP["Arista"],
    "CSCO": COMPANY_PRIMARY_DOMAIN_MAP["Cisco"],
    "CIEN": COMPANY_PRIMARY_DOMAIN_MAP["Ciena"],
    "LITE": COMPANY_PRIMARY_DOMAIN_MAP["Lumentum"],
    "COHR": COMPANY_PRIMARY_DOMAIN_MAP["Coherent"],
    "FN": COMPANY_PRIMARY_DOMAIN_MAP["Fabrinet"],
    "MU": COMPANY_PRIMARY_DOMAIN_MAP["Micron"],
    "WDC": COMPANY_PRIMARY_DOMAIN_MAP["Western Digital"],
    "STX": COMPANY_PRIMARY_DOMAIN_MAP["Seagate"],
    "SMCI": COMPANY_PRIMARY_DOMAIN_MAP["Super Micro"],
    "CLS": COMPANY_PRIMARY_DOMAIN_MAP["Celestica"],
    "TSM": COMPANY_PRIMARY_DOMAIN_MAP["TSMC"],
    "VRT": COMPANY_PRIMARY_DOMAIN_MAP["Vertiv"],
    "ETN": COMPANY_PRIMARY_DOMAIN_MAP["Eaton"],
    "GEV": COMPANY_PRIMARY_DOMAIN_MAP["GE Vernova"],
    "000660.KS": COMPANY_PRIMARY_DOMAIN_MAP["SK hynix"],
    "005930.KS": COMPANY_PRIMARY_DOMAIN_MAP["Samsung Electronics"],
    "285A.T": COMPANY_PRIMARY_DOMAIN_MAP["Kioxia"],
    "300308.SZ": COMPANY_PRIMARY_DOMAIN_MAP["Zhongji Innolight"],
    "300502.SZ": COMPANY_PRIMARY_DOMAIN_MAP["Eoptolink"],
    "002281.SZ": COMPANY_PRIMARY_DOMAIN_MAP["Accelink"],
    "300394.SZ": COMPANY_PRIMARY_DOMAIN_MAP["TFC Communication"],
    "6869.HK": COMPANY_PRIMARY_DOMAIN_MAP["Yangtze Optical Fibre"],
    "601869.SS": COMPANY_PRIMARY_DOMAIN_MAP["Yangtze Optical Fibre"],
}
PEER_TYPE_ALIASES = {
    "PSTG": "same_profit_pool",
    "NTAP": "same_profit_pool",
    "ADI": "adjacent_supplier",
    # Storage-adjacent names should not be treated as direct HBM/DRAM peers
    # just because a broad watchlist theme contains "HBM DRAM NAND".
    "SNDK": "same_profit_pool",
    "WDC": "weak_comparable",
}
PROFIT_POOL_ALIASES = {
    "PSTG": "enterprise_storage_systems",
    "NTAP": "enterprise_storage_systems",
    "ADI": "analog_power_signal_chain",
    "SNDK": "nand_storage",
    "WDC": "nearline_hdd_storage",
}
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", RESEARCH_VERSION)
OPENROUTER_MAX_TOKENS = int(os.getenv("OPENROUTER_MAX_TOKENS", "1800"))
OPENROUTER_TEMPERATURE = float(os.getenv("OPENROUTER_TEMPERATURE", "0.2"))
WEB_DISCOVERY_ENABLED = os.getenv("WEB_DISCOVERY_ENABLED", "1").lower().strip() not in {"0", "false", "no", "off"}
EVIDENCE_SEARCH_ENABLED = os.getenv("EVIDENCE_SEARCH_ENABLED", "1").lower().strip() not in {"0", "false", "no", "off"}
REUSE_TODAY_OUTPUTS = os.getenv("REUSE_TODAY_OUTPUTS", "1").lower().strip() not in {"0", "false", "no", "off"}
OFFICIAL_SOURCE_SEARCH_ENABLED = os.getenv("OFFICIAL_SOURCE_SEARCH_ENABLED", "1").lower().strip() not in {"0", "false", "no", "off"}
FACT_CACHE_ENABLED = os.getenv("FACT_CACHE_ENABLED", "1").lower().strip() not in {"0", "false", "no", "off"}
FACT_CACHE_PATH = os.getenv("FACT_CACHE_PATH", "data/fact_cache/facts.sqlite")
FACT_EXTRACT_PROVIDER = os.getenv("FACT_EXTRACT_PROVIDER", "deepseek")
FACT_EXTRACT_MODEL = os.getenv("FACT_EXTRACT_MODEL", "deepseek-v4-flash")
CHOKEPOINT_SCOUT_ENABLED = os.getenv("CHOKEPOINT_SCOUT_ENABLED", "1").lower().strip() not in {"0", "false", "no", "off"}

VALID_DECISION_RATINGS = {"buy", "small_start", "tracking_watch", "watch", "avoid", "cautious_watch"}
VALID_DECISION_ACTIONS = {
    "buy",
    "starter_position",
    "tracking_position",
    "watchlist",
    "hold_existing",
    "trim_existing",
    "avoid",
    "trim",
    "manual_price_verification_required",
}
VALID_SERENITY_THESIS_QUALITIES = {
    "high_quality_chokepoint",
    "interesting_unproven",
    "narrative_heavy",
    "weak_replaceable",
    "already_priced_in",
}
VALID_CHOKEPOINT_EVIDENCE_LEVELS = {
    "primary_supported",
    "secondary_supported",
    "hypothesis_only",
    "insufficient",
}
VALID_DEEP_RESEARCH_PRIORITIES = {"high", "medium", "low"}
VALID_SCOUT_RECOMMENDATIONS = {"deep_research", "watch_only", "reject", "monitor_for_evidence", "not_run"}


SYSTEM_PROMPT = """
You are a buy-side AI infrastructure and supply-chain investment research assistant.

Rules:
1. Facts first, judgment second.
2. Do not invent financial data.
3. If data is missing, say data missing.
4. Separate cited evidence, inference, and hypothesis. Label assumptions explicitly.
5. Do not assume an AI-related company is automatically a good investment.
6. This is research support only, not trading advice.
7. No leverage, no options, no short selling.
8. Suggested single-stock position must be between 0% and 5%.
9. Explain why valuation may be high before deciding whether it is justified.
10. Always include what would change your mind.

Focus areas:
- optical modules, optical components, optical networking
- fiber, cable, interconnect
- HBM, DRAM, NAND, SSD
- advanced packaging, substrate, PCB, semiconductor equipment
- AI chip interconnect, data center networking
- data center power, thermal management, infrastructure
"""


AI_AGENT_DEMAND_FRAMEWORK = """
## AI Agent Structural Demand Framework

Use this as an analytical framework, not as evidence by itself.

Structural demand channels from AI agents:
- More inference, not only training: always-on agents create recurring token generation, planning, tool-use, retrieval, and validation workloads.
- More context and memory: longer context windows, vector retrieval, session memory, and multimodal inputs increase memory bandwidth, storage, and networking intensity.
- More east-west data center traffic: multi-agent workflows, tool calls, distributed inference, and model routing can raise optical, switching, and interconnect demand.
- More latency-sensitive compute: production agents need lower latency and higher uptime than batch experiments, increasing demand for networking quality, power density, thermal management, and observability.
- More enterprise deployment surface: copilots moving into workflows can shift spend from experimental API usage toward durable data center, cloud, and on-prem infrastructure demand.

Supply-chain implication by layer:
- Compute: GPUs, ASICs, HBM, advanced packaging, substrates.
- Network/interconnect: switches, DSPs, optical modules, lasers, fiber.
- Power/thermal: grid equipment, UPS, switchgear, liquid cooling, enclosures.
- Storage/memory: HBM, DRAM, NAND/SSD, data pipelines.
- Services/manufacturing: EMS, precision components, testing, reliability.

Valuation questions:
- Is the multiple high because near-term earnings are depressed, because forward estimates are rising, because the asset is scarce, or because investors are extrapolating unsustainable growth?
- Does the company have pricing power or merely volume exposure?
- Are orders backed by capex budgets and customer commitments, or by speculative channel inventory?
- What operating metric would confirm that AI-agent demand is becoming structural rather than cyclical?
"""


def now_str() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def today_str() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower().strip() not in {"0", "false", "no", "off"}


def iso_now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def truncate_text(value: Any, max_chars: int = 120) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text if len(text) <= max_chars else text[: max_chars - 3].rstrip() + "..."


def markdown_cell(value: Any, max_chars: int = 120) -> str:
    return truncate_text(value, max_chars).replace("|", "\\|")


def console_safe_text(value: Any) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return str(value).encode(encoding, errors="replace").decode(encoding, errors="replace")


def new_fetch_diag(source: str, operation: str, target: str) -> Dict[str, Any]:
    return {
        "source": source,
        "operation": operation,
        "target": target,
        "status": "not_started",
        "started_at": iso_now(),
        "finished_at": "",
        "retry_count": 0,
        "error_type": "",
        "error_message": "",
        "row_count": None,
        "column_count": None,
        "data_reliability_impact": "none",
    }


def populate_fetch_diag_shape(diag: Dict[str, Any], data: Any = None) -> None:
    if isinstance(data, pd.DataFrame):
        diag["row_count"] = len(data.index)
        diag["column_count"] = len(data.columns)
    elif isinstance(data, list):
        diag["row_count"] = len(data)
        diag["column_count"] = None
    elif isinstance(data, dict):
        diag["row_count"] = len(data.keys())
        diag["column_count"] = None


def is_empty_fetch_output(data: Any) -> bool:
    if data is None:
        return True
    if isinstance(data, pd.DataFrame):
        return data.empty
    if isinstance(data, (list, dict, tuple, set)):
        return len(data) == 0
    return False


def finish_fetch_diag_success(diag: Dict[str, Any], data: Any = None) -> Dict[str, Any]:
    if is_empty_fetch_output(data):
        return finish_fetch_diag_empty(diag, data=data)
    diag["status"] = "success"
    diag["finished_at"] = iso_now()
    diag["data_reliability_impact"] = "none"
    populate_fetch_diag_shape(diag, data)
    return diag


def finish_fetch_diag_empty(
    diag: Dict[str, Any],
    data: Any = None,
    reliability_impact: str = "medium",
) -> Dict[str, Any]:
    diag["status"] = "empty"
    diag["finished_at"] = iso_now()
    diag["data_reliability_impact"] = reliability_impact
    populate_fetch_diag_shape(diag, data)
    return diag


def classify_fetch_exception(exc: Exception) -> str:
    message = str(exc).lower()
    if isinstance(exc, json.JSONDecodeError):
        return "json_error"
    if isinstance(exc, TimeoutError) or "timeout" in message or "timed out" in message:
        return "timeout"
    if isinstance(exc, urllib.error.HTTPError) and getattr(exc, "code", None) in {429, 432}:
        return "rate_limited"
    if (
        "429" in message
        or "432" in message
        or "too many requests" in message
        or "rate limit" in message
        or "quota" in message
        or "rate_limited" in message
    ):
        return "rate_limited"
    return "failed"


def finish_fetch_diag_error(
    diag: Dict[str, Any],
    exc: Exception,
    status: str = "failed",
    reliability_impact: str = "medium",
) -> Dict[str, Any]:
    diag["status"] = status
    diag["finished_at"] = iso_now()
    diag["error_type"] = type(exc).__name__
    diag["error_message"] = truncate_text(str(exc), 500)
    diag["data_reliability_impact"] = reliability_impact
    return diag


def retry_call(
    fn,
    *,
    source: str,
    operation: str,
    target: str,
    max_attempts: int = 3,
    base_sleep_seconds: float = 1.0,
    retry_on: tuple = (Exception,),
    empty_reliability_impact: str = "medium",
    error_reliability_impact: str = "medium",
) -> Tuple[Any, Dict[str, Any]]:
    diag = new_fetch_diag(source, operation, target)
    attempts = max(1, int(max_attempts))
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            diag["status"] = "not_started" if attempt == 0 else "retrying"
            data = fn()
            diag["retry_count"] = attempt
            if is_empty_fetch_output(data):
                return data, finish_fetch_diag_empty(diag, data=data, reliability_impact=empty_reliability_impact)
            return data, finish_fetch_diag_success(diag, data=data)
        except retry_on as exc:
            last_exc = exc
            diag["retry_count"] = attempt
            if attempt < attempts - 1:
                sleep_for = base_sleep_seconds * (2 ** attempt) + random.uniform(0, 0.25)
                time.sleep(sleep_for)

    assert last_exc is not None
    status = classify_fetch_exception(last_exc)
    return None, finish_fetch_diag_error(
        diag,
        last_exc,
        status=status,
        reliability_impact=error_reliability_impact,
    )


def fetch_diagnostics_summary(diagnostics: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        "total": len(diagnostics),
        "success": 0,
        "empty": 0,
        "failed": 0,
        "rate_limited": 0,
        "timeout": 0,
        "json_error": 0,
        "high_impact_failures": 0,
        "medium_impact_failures": 0,
    }
    failure_statuses = {"failed", "rate_limited", "timeout", "json_error"}
    for diag in diagnostics:
        status = str(diag.get("status") or "")
        if status in summary:
            summary[status] += 1
        if status in failure_statuses:
            summary["failed"] += 1 if status != "failed" else 0
        impact = str(diag.get("data_reliability_impact") or "")
        if status in failure_statuses.union({"empty"}) and impact == "high":
            summary["high_impact_failures"] += 1
        if status in failure_statuses.union({"empty"}) and impact == "medium":
            summary["medium_impact_failures"] += 1
    return summary


def fetch_diagnostics_to_markdown(title: str, diagnostics: List[Dict[str, Any]]) -> str:
    summary = fetch_diagnostics_summary(diagnostics)
    lines = [
        f"## {title}",
        "",
        "Summary:",
        f"- total: {summary['total']}",
        f"- success: {summary['success']}",
        f"- empty: {summary['empty']}",
        f"- failed: {summary['failed']}",
        f"- rate_limited: {summary['rate_limited']}",
        f"- timeout: {summary['timeout']}",
        f"- high_impact_failures: {summary['high_impact_failures']}",
        "",
        "| Source | Operation | Status | Target | Retry Count | Rows | Impact | Error Type | Error Message |",
        "|---|---|---|---|---:|---:|---|---|---|",
    ]
    if not diagnostics:
        lines.append("| N/A | N/A | N/A | N/A | 0 | N/A | N/A | N/A | N/A |")
        return "\n".join(lines)
    for diag in diagnostics:
        target = markdown_cell(diag.get("target"), 80)
        error_message = markdown_cell(diag.get("error_message"), 100)
        lines.append(
            f"| {truncate_text(diag.get('source'), 40)} | {truncate_text(diag.get('operation'), 40)} | "
            f"{diag.get('status') or 'N/A'} | {target} | "
            f"{diag.get('retry_count') or 0} | {diag.get('row_count') if diag.get('row_count') is not None else 'N/A'} | "
            f"{diag.get('data_reliability_impact') or 'N/A'} | {truncate_text(diag.get('error_type'), 40)} | "
            f"{error_message} |"
        )
    return "\n".join(lines)


def compute_market_data_reliability(fetch_diagnostics: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed_statuses = {"failed", "rate_limited", "timeout", "json_error"}

    def by_operation(operation: str) -> List[Dict[str, Any]]:
        return [d for d in fetch_diagnostics if d.get("operation") == operation]

    def bad(operation: str) -> bool:
        return any((d.get("status") in failed_statuses or d.get("status") == "empty") for d in by_operation(operation))

    warnings: List[str] = []
    market_data_reliability = "high"
    price_data_reliability_from_fetch = "high"
    financial_statement_reliability = "high"

    if bad("yfinance_info"):
        market_data_reliability = "low"
        warnings.append("yfinance_info_failed_or_empty")

    if bad("yfinance_history_2y"):
        price_data_reliability_from_fetch = "low"
        warnings.append("yfinance_history_failed_or_empty")

    financial_ops = [
        "yfinance_annual_income",
        "yfinance_annual_cashflow",
        "yfinance_annual_balance",
    ]
    missing_financial_ops = sum(1 for op in financial_ops if bad(op))
    if missing_financial_ops >= 3:
        financial_statement_reliability = "low"
        warnings.append("financial_statement_tables_missing_or_empty")
    elif missing_financial_ops >= 1:
        financial_statement_reliability = "medium"
        warnings.append("some_financial_statement_tables_missing_or_empty")

    if any(d.get("status") == "rate_limited" for d in fetch_diagnostics):
        market_data_reliability = lower_reliability(market_data_reliability, "medium")
        warnings.append("data_fetch_rate_limited")

    failed_count = sum(1 for d in fetch_diagnostics if d.get("status") in failed_statuses)
    if failed_count >= 3:
        market_data_reliability = "low"
        warnings.append("multiple_data_fetch_failures")

    return {
        "market_data_reliability": market_data_reliability,
        "financial_statement_reliability": financial_statement_reliability,
        "price_data_reliability_from_fetch": price_data_reliability_from_fetch,
        "data_fetch_warnings": sorted(set(warnings)),
    }


def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except Exception:
        return None


def format_num(x: Optional[float]) -> str:
    if x is None:
        return "N/A"
    ax = abs(x)
    if ax >= 1e12:
        return f"{x / 1e12:.2f}T"
    if ax >= 1e9:
        return f"{x / 1e9:.2f}B"
    if ax >= 1e6:
        return f"{x / 1e6:.2f}M"
    return f"{x:.2f}"


def format_pct(x: Optional[float]) -> str:
    if x is None:
        return "N/A"
    return f"{x * 100:.2f}%"


def return_over_trading_days(close: pd.Series, days: int = 252) -> Optional[float]:
    close = close.dropna()
    if len(close) <= 1:
        return None
    if len(close) > days:
        return safe_float(close.iloc[-1] / close.iloc[-days] - 1)
    return safe_float(close.iloc[-1] / close.iloc[0] - 1)


def safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return safe_float(num / den)


def calc_growth(latest: Optional[float], previous: Optional[float]) -> Optional[float]:
    if latest is None or previous is None or previous == 0:
        return None
    return safe_float(latest / abs(previous) - 1)


def date_label(x: Any) -> str:
    if hasattr(x, "date"):
        return str(x.date())
    return str(x)


def statement_value(df: Optional[pd.DataFrame], col: Any, labels: List[str]) -> Optional[float]:
    if df is None or df.empty or col not in df.columns:
        return None

    index_lookup = {str(idx).lower(): idx for idx in df.index}
    for label in labels:
        idx = index_lookup.get(label.lower())
        if idx is not None:
            return safe_float(df.at[idx, col])
    return None


def statement_history(
    income_df: Optional[pd.DataFrame],
    cashflow_df: Optional[pd.DataFrame],
    balance_df: Optional[pd.DataFrame],
    periods: int = 4,
) -> List[Dict[str, Any]]:
    cols: List[Any] = []
    for df in [income_df, cashflow_df, balance_df]:
        if df is not None and not df.empty:
            for col in df.columns:
                if col not in cols:
                    cols.append(col)

    rows: List[Dict[str, Any]] = []
    for col in cols[:periods]:
        revenue = statement_value(income_df, col, ["Total Revenue", "Operating Revenue"])
        gross_profit = statement_value(income_df, col, ["Gross Profit"])
        operating_income = statement_value(income_df, col, ["Operating Income", "Operating Income Loss"])
        net_income = statement_value(income_df, col, ["Net Income", "Net Income Common Stockholders"])
        operating_cashflow = statement_value(
            cashflow_df,
            col,
            ["Operating Cash Flow", "Total Cash From Operating Activities"],
        )
        capex = statement_value(
            cashflow_df,
            col,
            ["Capital Expenditure", "Capital Expenditures", "Capital Expenditure Reported"],
        )
        free_cash_flow = statement_value(cashflow_df, col, ["Free Cash Flow"])
        if free_cash_flow is None and operating_cashflow is not None and capex is not None:
            free_cash_flow = safe_float(operating_cashflow + capex)

        total_debt = statement_value(balance_df, col, ["Total Debt"])
        cash = statement_value(
            balance_df,
            col,
            ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
        )
        inventory = statement_value(balance_df, col, ["Inventory"])

        rows.append({
            "period": date_label(col),
            "revenue": revenue,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "net_income": net_income,
            "operating_cashflow": operating_cashflow,
            "capital_expenditure": capex,
            "free_cash_flow": free_cash_flow,
            "total_debt": total_debt,
            "cash": cash,
            "inventory": inventory,
            "gross_margin": safe_div(gross_profit, revenue),
            "operating_margin": safe_div(operating_income, revenue),
            "net_margin": safe_div(net_income, revenue),
            "fcf_margin": safe_div(free_cash_flow, revenue),
        })

    for i, row in enumerate(rows):
        previous = rows[i + 1] if i + 1 < len(rows) else {}
        row["revenue_growth_vs_prior_period"] = calc_growth(row.get("revenue"), previous.get("revenue"))
        row["fcf_growth_vs_prior_period"] = calc_growth(row.get("free_cash_flow"), previous.get("free_cash_flow"))

    return rows


def financial_history_to_markdown(title: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return f"## {title}\n\nNo statement data available.\n"

    lines = [
        f"## {title}",
        "",
        "| Period | Revenue | Revenue Growth | Gross Margin | Operating Margin | Net Income | FCF | FCF Margin | Debt | Cash | Inventory |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('period')} | {format_num(row.get('revenue'))} | "
            f"{format_pct(row.get('revenue_growth_vs_prior_period'))} | "
            f"{format_pct(row.get('gross_margin'))} | "
            f"{format_pct(row.get('operating_margin'))} | "
            f"{format_num(row.get('net_income'))} | "
            f"{format_num(row.get('free_cash_flow'))} | "
            f"{format_pct(row.get('fcf_margin'))} | "
            f"{format_num(row.get('total_debt'))} | "
            f"{format_num(row.get('cash'))} | "
            f"{format_num(row.get('inventory'))} |"
        )
    return "\n".join(lines) + "\n"


def news_to_markdown(news_items: List[Dict[str, Any]]) -> str:
    lines = ["## Recent News / IR Clues", ""]
    if not news_items:
        lines.append("No recent news returned by yfinance.")
        return "\n".join(lines)

    for item in news_items:
        title = item.get("title") or "Untitled"
        publisher = item.get("publisher") or "Unknown source"
        published = item.get("published_at") or "Unknown date"
        url = item.get("url") or ""
        line = f"- {published} | {publisher} | {title}"
        if url:
            line += f" | {url}"
        lines.append(line)
    return "\n".join(lines)


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return ""

    cols = [str(c) for c in df.columns]
    rows = []
    for _, row in df.iterrows():
        rows.append([str(row.get(c, "")) for c in df.columns])

    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for row in rows:
        escaped = [cell.replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def get_ticker_news(
    t: yf.Ticker,
    max_items: int = 8,
    diagnostics: Optional[List[Dict[str, Any]]] = None,
    target: str = "",
) -> List[Dict[str, Any]]:
    raw_news, diag = retry_call(
        lambda: t.news or [],
        source="yfinance",
        operation="yfinance_news",
        target=target or str(getattr(t, "ticker", "")),
        empty_reliability_impact="low",
        error_reliability_impact="low",
    )
    if diagnostics is not None:
        diagnostics.append(diag)
    raw_news = raw_news or []

    items: List[Dict[str, Any]] = []
    for item in raw_news[:max_items]:
        content = item.get("content") if isinstance(item, dict) else {}
        content = content or {}
        title = item.get("title") or content.get("title")
        publisher = item.get("publisher") or content.get("provider", {}).get("displayName")
        url = item.get("link") or item.get("url") or content.get("canonicalUrl", {}).get("url")
        published_raw = item.get("providerPublishTime") or content.get("pubDate")
        published_at = str(published_raw) if published_raw else None
        if isinstance(published_raw, (int, float)):
            published_at = dt.datetime.fromtimestamp(published_raw).isoformat(timespec="seconds")
        items.append({
            "title": title,
            "publisher": publisher,
            "published_at": published_at,
            "url": url,
        })
    return items


def openrouter_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is missing. Please add it to .env.")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-OpenRouter-Title": OPENROUTER_APP_NAME,
        },
    )


def deepseek_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is missing. Please add it to .env.")
    return OpenAI(
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        api_key=api_key,
    )


def get_llm_client_and_model():
    provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()

    if provider == "deepseek":
        return (
            deepseek_client(),
            os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            int(os.getenv("DEEPSEEK_MAX_TOKENS", "2500")),
            float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2")),
        )

    return (
        openrouter_client(),
        OPENROUTER_MODEL,
        OPENROUTER_MAX_TOKENS,
        OPENROUTER_TEMPERATURE,
    )


def call_llm(
    agent_name: str,
    prompt: str,
    max_tokens: Optional[int] = None,
    decorate: bool = True,
    json_mode: bool = False,
    diagnostics: Optional[List[Dict[str, Any]]] = None,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
    temperature_override: Optional[float] = None,
    thinking_override: Optional[str] = None,
) -> str:
    provider = (provider_override or os.getenv("LLM_PROVIDER", "openrouter")).lower().strip()
    if provider == "deepseek":
        client = deepseek_client()
        model = model_override or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        default_max_tokens = int(os.getenv("DEEPSEEK_MAX_TOKENS", "2500"))
        temperature = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2"))
    else:
        client, model, default_max_tokens, temperature = get_llm_client_and_model()
        if model_override:
            model = model_override
    if temperature_override is not None:
        temperature = temperature_override
    diag = new_fetch_diag(f"{provider}/{model}", "llm_chat_completion", agent_name)
    diag["used_json_mode_fallback"] = False

    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens or default_max_tokens,
        "stream": False,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    # DeepSeek V4 supports thinking mode; keep it configurable because deep
    # research benefits from reasoning. For JSON-only calls, disable thinking:
    # some providers return empty/non-JSON visible content when reasoning is on.
    if provider == "deepseek":
        thinking_mode = thinking_override or ("disabled" if json_mode else os.getenv("DEEPSEEK_THINKING", "disabled").lower().strip())
        if thinking_mode == "enabled":
            kwargs["reasoning_effort"] = os.getenv("DEEPSEEK_REASONING_EFFORT", "medium")
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    attempts = max(1, int(os.getenv("LLM_MAX_ATTEMPTS", "2")))
    base_sleep = float(os.getenv("LLM_RETRY_BASE_SECONDS", "2"))
    last_exc: Optional[Exception] = None
    response = None
    for attempt in range(attempts):
        try:
            diag["retry_count"] = attempt
            response = client.chat.completions.create(**kwargs)
            break
        except Exception as exc:
            last_exc = exc
            if json_mode and "response_format" in kwargs:
                try:
                    fallback_kwargs = dict(kwargs)
                    fallback_kwargs.pop("response_format", None)
                    response = client.chat.completions.create(**fallback_kwargs)
                    diag["retry_count"] = attempt
                    diag["used_json_mode_fallback"] = True
                    break
                except Exception as fallback_exc:
                    last_exc = fallback_exc
            if attempt < attempts - 1:
                time.sleep(base_sleep * (2 ** attempt) + random.uniform(0, 0.25))

    if response is None:
        assert last_exc is not None
        finish_fetch_diag_error(
            diag,
            last_exc,
            status=classify_fetch_exception(last_exc),
            reliability_impact="high",
        )
        if diagnostics is not None:
            diagnostics.append(diag)
        raise last_exc

    content = response.choices[0].message.content or ""
    content = content.strip()
    finish_fetch_diag_success(diag, {"content": content})
    if diagnostics is not None:
        diagnostics.append(diag)
    if decorate:
        return f"# {agent_name}\n\n{content}"
    return content


def get_market_snapshot(ticker: str) -> Dict[str, Any]:
    financial_ticker = financial_ticker_for(ticker)
    diagnostics: List[Dict[str, Any]] = []
    snapshot: Dict[str, Any] = {
        "ticker": ticker,
        "financial_ticker": financial_ticker,
        "uses_financial_ticker_alias": financial_ticker != ticker,
        "data_warning": "Data from yfinance may be delayed, incomplete, or inaccurate. Verify before trading.",
        "data_fetch_diagnostics": diagnostics,
    }

    try:
        t = yf.Ticker(ticker)

        best_info, info_diag = retry_call(
            lambda: get_best_financial_info(ticker),
            source="yfinance",
            operation="yfinance_info",
            target=ticker,
            empty_reliability_impact="high",
            error_reliability_impact="high",
        )
        if best_info:
            info, info_source_ticker, cross_currency_risk = best_info
            if not info_has_core_financials(info):
                info_diag = finish_fetch_diag_empty(info_diag, info or {}, reliability_impact="high")
            else:
                populate_fetch_diag_shape(info_diag, info)
        else:
            info = {}
            info_source_ticker = financial_ticker
            cross_currency_risk = False
        diagnostics.append(info_diag)

        ft = yf.Ticker(info_source_ticker)

        hist, diag = retry_call(
            lambda: t.history(period="2y", auto_adjust=True),
            source="yfinance",
            operation="yfinance_history_2y",
            target=ticker,
            empty_reliability_impact="high",
            error_reliability_impact="high",
        )
        diagnostics.append(diag)
        hist = hist if isinstance(hist, pd.DataFrame) else pd.DataFrame()

        annual_income, diag = retry_call(
            lambda: ft.financials,
            source="yfinance",
            operation="yfinance_annual_income",
            target=info_source_ticker,
            empty_reliability_impact="medium",
            error_reliability_impact="medium",
        )
        diagnostics.append(diag)
        annual_income = annual_income if isinstance(annual_income, pd.DataFrame) else pd.DataFrame()

        quarterly_income, diag = retry_call(
            lambda: ft.quarterly_financials,
            source="yfinance",
            operation="yfinance_quarterly_income",
            target=info_source_ticker,
            empty_reliability_impact="medium",
            error_reliability_impact="medium",
        )
        diagnostics.append(diag)
        quarterly_income = quarterly_income if isinstance(quarterly_income, pd.DataFrame) else pd.DataFrame()

        annual_cashflow, diag = retry_call(
            lambda: ft.cashflow,
            source="yfinance",
            operation="yfinance_annual_cashflow",
            target=info_source_ticker,
            empty_reliability_impact="medium",
            error_reliability_impact="medium",
        )
        diagnostics.append(diag)
        annual_cashflow = annual_cashflow if isinstance(annual_cashflow, pd.DataFrame) else pd.DataFrame()

        quarterly_cashflow, diag = retry_call(
            lambda: ft.quarterly_cashflow,
            source="yfinance",
            operation="yfinance_quarterly_cashflow",
            target=info_source_ticker,
            empty_reliability_impact="medium",
            error_reliability_impact="medium",
        )
        diagnostics.append(diag)
        quarterly_cashflow = quarterly_cashflow if isinstance(quarterly_cashflow, pd.DataFrame) else pd.DataFrame()

        annual_balance, diag = retry_call(
            lambda: ft.balance_sheet,
            source="yfinance",
            operation="yfinance_annual_balance",
            target=info_source_ticker,
            empty_reliability_impact="medium",
            error_reliability_impact="medium",
        )
        diagnostics.append(diag)
        annual_balance = annual_balance if isinstance(annual_balance, pd.DataFrame) else pd.DataFrame()

        quarterly_balance, diag = retry_call(
            lambda: ft.quarterly_balance_sheet,
            source="yfinance",
            operation="yfinance_quarterly_balance",
            target=info_source_ticker,
            empty_reliability_impact="medium",
            error_reliability_impact="medium",
        )
        diagnostics.append(diag)
        quarterly_balance = quarterly_balance if isinstance(quarterly_balance, pd.DataFrame) else pd.DataFrame()

        annual_financials = statement_history(annual_income, annual_cashflow, annual_balance, periods=4)
        quarterly_financials = statement_history(quarterly_income, quarterly_cashflow, quarterly_balance, periods=6)
        recent_news = get_ticker_news(t, diagnostics=diagnostics, target=ticker)

        latest_price = None
        one_month_return = None
        three_month_return = None
        one_year_return = None
        volatility_1y = None
        max_drawdown_2y = None
        trend_label = "Unknown"

        if hist is not None and not hist.empty and "Close" in hist.columns:
            close = hist["Close"].dropna()
            if len(close) > 0:
                latest_price = safe_float(close.iloc[-1])
                one_month_return = safe_float(close.iloc[-1] / close.iloc[-22] - 1) if len(close) > 22 else None
                three_month_return = safe_float(close.iloc[-1] / close.iloc[-66] - 1) if len(close) > 66 else None
                one_year_return = return_over_trading_days(close, 252)

                daily_ret = close.pct_change().dropna()
                volatility_1y = safe_float(daily_ret.tail(252).std() * np.sqrt(252)) if len(daily_ret) > 100 else None

                peak = close.cummax()
                drawdown = close / peak - 1
                max_drawdown_2y = safe_float(drawdown.min())

                sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
                sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
                if latest_price and sma50 and sma200:
                    if latest_price > sma50 > sma200:
                        trend_label = "Uptrend"
                    elif latest_price < sma50 < sma200:
                        trend_label = "Downtrend"
                    else:
                        trend_label = "Mixed"

        market_cap = safe_float(info.get("marketCap"))
        enterprise_value = safe_float(info.get("enterpriseValue"))
        total_revenue = safe_float(info.get("totalRevenue"))
        ebitda = safe_float(info.get("ebitda"))
        free_cashflow = safe_float(info.get("freeCashflow"))
        operating_cashflow = safe_float(info.get("operatingCashflow"))
        total_debt = safe_float(info.get("totalDebt"))
        total_cash = safe_float(info.get("totalCash"))
        target_mean_price = safe_float(info.get("targetMeanPrice"))

        snapshot.update({
            "short_name": info.get("shortName"),
            "long_name": info.get("longName"),
            "financial_info_source_ticker": info_source_ticker,
            "cross_currency_valuation_risk": cross_currency_risk,
            "business_summary": info.get("longBusinessSummary"),
            "website": info.get("website"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "currency": info.get("currency"),
            "financial_currency": info.get("financialCurrency"),
            "employees": info.get("fullTimeEmployees"),
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "trailing_pe": safe_float(info.get("trailingPE")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "price_to_sales": safe_float(info.get("priceToSalesTrailing12Months")),
            "price_to_book": safe_float(info.get("priceToBook")),
            "ev_to_revenue": safe_div(enterprise_value, total_revenue),
            "ev_to_ebitda": safe_div(enterprise_value, ebitda),
            "gross_margin": safe_float(info.get("grossMargins")),
            "operating_margin": safe_float(info.get("operatingMargins")),
            "profit_margin": safe_float(info.get("profitMargins")),
            "revenue_growth": safe_float(info.get("revenueGrowth")),
            "earnings_growth": safe_float(info.get("earningsGrowth")),
            "roe": safe_float(info.get("returnOnEquity")),
            "total_revenue": total_revenue,
            "ebitda": ebitda,
            "free_cashflow": free_cashflow,
            "operating_cashflow": operating_cashflow,
            "fcf_yield": safe_div(free_cashflow, market_cap),
            "total_debt": total_debt,
            "total_cash": total_cash,
            "net_debt": safe_float(total_debt - total_cash) if total_debt is not None and total_cash is not None else None,
            "target_mean_price": target_mean_price,
            "analyst_target_upside": safe_div(target_mean_price - latest_price, latest_price) if target_mean_price is not None and latest_price is not None else None,
            "recommendation_mean": safe_float(info.get("recommendationMean")),
            "number_of_analyst_opinions": info.get("numberOfAnalystOpinions"),
            "latest_price": latest_price,
            "one_month_return": one_month_return,
            "three_month_return": three_month_return,
            "one_year_return": one_year_return,
            "volatility_1y": volatility_1y,
            "max_drawdown_2y": max_drawdown_2y,
            "trend_label": trend_label,
            "annual_financials": annual_financials,
            "quarterly_financials": quarterly_financials,
            "recent_news": recent_news,
        })
        if cross_currency_risk:
            suppress_cross_currency_valuation(snapshot)

    except Exception as e:
        snapshot["error"] = str(e)

    snapshot["data_fetch_diagnostics"] = diagnostics
    snapshot.update(compute_market_data_reliability(diagnostics))
    return snapshot


def snapshot_to_markdown(s: Dict[str, Any]) -> str:
    business_summary = s.get("business_summary") or ""
    if len(business_summary) > 900:
        business_summary = business_summary[:900].rstrip() + "..."

    lines = [
        "## Market Snapshot",
        "",
        f"- Ticker: {s.get('ticker')}",
        f"- Financial Data Ticker: {s.get('financial_ticker') or s.get('ticker')}",
        f"- Financial Info Source Ticker: {s.get('financial_info_source_ticker') or s.get('financial_ticker') or s.get('ticker')}",
        f"- Uses Financial Ticker Alias: {s.get('uses_financial_ticker_alias')}",
        f"- Cross-Currency Valuation Risk: {s.get('cross_currency_valuation_risk')}",
        f"- Company: {s.get('long_name') or s.get('short_name') or 'N/A'}",
        f"- Website: {s.get('website') or 'N/A'}",
        f"- Sector: {s.get('sector') or 'N/A'}",
        f"- Industry: {s.get('industry') or 'N/A'}",
        f"- Country: {s.get('country') or 'N/A'}",
        f"- Currency: {s.get('currency') or 'N/A'}",
        f"- Employees: {s.get('employees') or 'N/A'}",
        f"- Latest Price: {s.get('latest_price')}",
        f"- Market Cap: {format_num(s.get('market_cap'))}",
        f"- Enterprise Value: {format_num(s.get('enterprise_value'))}",
        f"- Total Revenue: {format_num(s.get('total_revenue'))}",
        f"- EBITDA: {format_num(s.get('ebitda'))}",
        f"- Trailing P/E: {s.get('trailing_pe') or 'N/A'}",
        f"- Forward P/E: {s.get('forward_pe') or 'N/A'}",
        f"- P/S: {s.get('price_to_sales') or 'N/A'}",
        f"- P/B: {s.get('price_to_book') or 'N/A'}",
        f"- EV/Revenue: {s.get('ev_to_revenue') or 'N/A'}",
        f"- EV/EBITDA: {s.get('ev_to_ebitda') or 'N/A'}",
        f"- Revenue Growth: {format_pct(s.get('revenue_growth'))}",
        f"- Earnings Growth: {format_pct(s.get('earnings_growth'))}",
        f"- Gross Margin: {format_pct(s.get('gross_margin'))}",
        f"- Operating Margin: {format_pct(s.get('operating_margin'))}",
        f"- Profit Margin: {format_pct(s.get('profit_margin'))}",
        f"- ROE: {format_pct(s.get('roe'))}",
        f"- Operating Cash Flow: {format_num(s.get('operating_cashflow'))}",
        f"- Free Cash Flow: {format_num(s.get('free_cashflow'))}",
        f"- FCF Yield: {format_pct(s.get('fcf_yield'))}",
        f"- Total Debt: {format_num(s.get('total_debt'))}",
        f"- Total Cash: {format_num(s.get('total_cash'))}",
        f"- Net Debt: {format_num(s.get('net_debt'))}",
        f"- Analyst Target Mean Price: {s.get('target_mean_price') or 'N/A'}",
        f"- Analyst Target Upside: {format_pct(s.get('analyst_target_upside'))}",
        f"- Recommendation Mean: {s.get('recommendation_mean') or 'N/A'}",
        f"- Analyst Opinion Count: {s.get('number_of_analyst_opinions') or 'N/A'}",
        f"- 1M Return: {format_pct(s.get('one_month_return'))}",
        f"- 3M Return: {format_pct(s.get('three_month_return'))}",
        f"- 1Y Return: {format_pct(s.get('one_year_return'))}",
        f"- 1Y Volatility: {format_pct(s.get('volatility_1y'))}",
        f"- 2Y Max Drawdown: {format_pct(s.get('max_drawdown_2y'))}",
        f"- Trend Label: {s.get('trend_label')}",
        "",
        "## Data Fetch Reliability",
        "",
        f"- Market data reliability: {s.get('market_data_reliability') or 'N/A'}",
        f"- Financial statement reliability: {s.get('financial_statement_reliability') or 'N/A'}",
        f"- Price data reliability from fetch: {s.get('price_data_reliability_from_fetch') or 'N/A'}",
        f"- Data fetch warnings: {', '.join(s.get('data_fetch_warnings') or []) or 'None'}",
        "",
        fetch_diagnostics_to_markdown("Market Data Fetch Diagnostics", s.get("data_fetch_diagnostics") or []),
        "",
        "## Business Summary",
        "",
        business_summary or "N/A",
        "",
        f"> Data note: {s.get('data_warning')}",
        f"> Valuation note: {s.get('valuation_data_warning') or 'N/A'}",
        "",
    ]
    lines.append(financial_history_to_markdown("Annual Financial Trend", s.get("annual_financials") or []))
    lines.append(financial_history_to_markdown("Quarterly Financial Trend", s.get("quarterly_financials") or []))
    lines.append(news_to_markdown(s.get("recent_news") or []))
    lines.append("")
    return "\n".join(lines)


def get_macro_snapshot() -> str:
    tickers = {
        "SPY": "S&P 500 ETF",
        "QQQ": "Nasdaq 100 ETF",
        "SOXX": "Semiconductor ETF",
        "^VIX": "VIX",
        "^TNX": "US 10Y Treasury Yield Index",
        "DX-Y.NYB": "US Dollar Index",
    }

    lines = [
        "## Macro Snapshot",
        "",
        "| Ticker | Name | Latest | 1M | 3M | 1Y |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for ticker, name in tickers.items():
        try:
            hist = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
            close = hist["Close"].dropna()
            latest = safe_float(close.iloc[-1]) if len(close) else None
            r1m = safe_float(close.iloc[-1] / close.iloc[-22] - 1) if len(close) > 22 else None
            r3m = safe_float(close.iloc[-1] / close.iloc[-66] - 1) if len(close) > 66 else None
            r1y = safe_float(close.iloc[-1] / close.iloc[0] - 1) if len(close) > 10 else None
            lines.append(f"| {ticker} | {name} | {latest} | {format_pct(r1m)} | {format_pct(r3m)} | {format_pct(r1y)} |")
        except Exception as e:
            lines.append(f"| {ticker} | {name} | ERROR: {e} | N/A | N/A | N/A |")

    return "\n".join(lines)


PORTFOLIO_RECOMMENDATION_BOUNDARY_NOTICE = (
    "Portfolio context is disabled for PM recommendations; use offline portfolio exposure reports instead."
)


def read_portfolio(path: str) -> str:
    """Legacy diagnostics-only reader.

    This helper is intentionally not used by PM prompt, PM memo, or recommendation
    paths. Portfolio exposure work should use the offline portfolio reporting
    modules under src/ai_pm_agent/portfolio/.
    """
    p = Path(path)
    if not p.exists():
        return "No portfolio.csv found."

    try:
        df = pd.read_csv(p)
        if df.empty:
            return "portfolio.csv is empty."
        lines = ["## Current Portfolio", "", dataframe_to_markdown(df), ""]
        if "position_pct" in df.columns:
            positions = pd.to_numeric(df["position_pct"], errors="coerce").fillna(0)
            lines.extend([
                "## Portfolio Concentration Snapshot",
                "",
                f"- Total listed single-stock exposure: {positions.sum():.2f}%",
                f"- Largest listed position: {positions.max():.2f}%",
                f"- Number of listed positions: {len(df)}",
            ])
        return "\n".join(lines)
    except Exception as e:
        return f"Could not read portfolio.csv: {e}"


def disabled_portfolio_context_notice() -> str:
    return "\n".join([
        "## Portfolio Recommendation Boundary",
        "",
        PORTFOLIO_RECOMMENDATION_BOUNDARY_NOTICE,
        "Legacy portfolio.csv input is not read, injected into PM prompts, or used in PM memo/recommendation logic.",
        "Use the offline portfolio exposure runner for separate local portfolio reporting.",
    ])


def theme_bucket(theme: str) -> str:
    t = theme.lower()
    if any(k in t for k in ["optical", "fiber", "cable"]):
        return "optical"
    if any(k in t for k in ["hbm", "dram", "nand", "memory", "ssd"]):
        return "memory"
    if any(k in t for k in [
        "semiconductor equipment",
        "wfe",
        "wafer fab equipment",
        "test equipment",
        "lithography",
        "etch",
        "deposition",
        "inspection",
        "metrology",
        "probe card",
        "tester",
        "advantest",
        "applied materials",
        "tokyo electron",
        "asml",
        "lam research",
    ]):
        return "semiconductor_equipment"
    if any(k in t for k in ["power", "electrical", "grid", "ups", "switchgear", "cooling", "thermal", "data center infrastructure"]):
        return "power_thermal"
    if any(k in t for k in ["network", "switching", "interconnect", "asic", "accelerator"]):
        return "compute_network"
    if any(k in t for k in ["substrate", "packaging", "abf", "pcb", "interposer", "materials", "ajinomoto", "ibiden", "unimicron", "shennan circuit"]):
        return "packaging"
    return "other"


def theme_tokens(theme: str) -> set:
    stop = {"and", "the", "for", "data", "center", "ai"}
    return {t for t in re.split(r"[^a-z0-9]+", theme.lower()) if len(t) > 2 and t not in stop}


def normalize_ticker(ticker: Any) -> str:
    return str(ticker or "").strip().upper()


def financial_ticker_for(ticker: str) -> str:
    return FINANCIAL_TICKER_ALIASES.get(normalize_ticker(ticker), ticker)


def canonical_ticker_for(ticker: Any) -> str:
    return normalize_ticker(financial_ticker_for(str(ticker or "")))


def clean_company_name(ticker: Any, name: Any = "", info: Optional[Dict[str, Any]] = None) -> str:
    ticker_norm = normalize_ticker(ticker)
    if ticker_norm in COMPANY_NAME_ALIASES:
        return COMPANY_NAME_ALIASES[ticker_norm]

    candidate = str(name or "").strip()
    if candidate:
        return candidate

    info = info or {}
    return str(info.get("longName") or info.get("shortName") or ticker_norm).strip()


def is_disallowed_market(ticker: Any, market: Any = "") -> bool:
    ticker_norm = normalize_ticker(ticker)
    market_norm = str(market or "").strip().lower()
    return ticker_norm.endswith(".TW") or market_norm in {"taiwan", "tw", "tpe"}


def info_has_core_financials(info: Dict[str, Any]) -> bool:
    return any(info.get(k) is not None for k in ["marketCap", "totalRevenue", "enterpriseValue", "priceToSalesTrailing12Months"])


def get_best_financial_info(ticker: str) -> tuple:
    financial_ticker = financial_ticker_for(ticker)
    source_ticker = financial_ticker
    try:
        info = yf.Ticker(financial_ticker).info or {}
    except Exception:
        info = {}

    if financial_ticker != ticker and not info_has_core_financials(info):
        try:
            fallback_info = yf.Ticker(ticker).info or {}
        except Exception:
            fallback_info = {}
        if info_has_core_financials(fallback_info):
            return fallback_info, ticker, True

    return info, source_ticker, has_currency_mismatch_risk(ticker, source_ticker, info)


def has_currency_mismatch_risk(ticker: str, info_source_ticker: str, info: Dict[str, Any]) -> bool:
    quote_currency = str(info.get("currency") or "").upper()
    financial_currency = str(info.get("financialCurrency") or "").upper()
    if quote_currency and financial_currency and quote_currency != financial_currency:
        return True

    if financial_ticker_for(ticker) == ticker:
        return False
    if info_source_ticker != ticker:
        return False
    country = str(info.get("country") or "")
    return bool(quote_currency and country and quote_currency not in {"KRW"} and "Korea" in country)


def suppress_cross_currency_valuation(snapshot: Dict[str, Any]) -> None:
    for key in [
        "market_cap",
        "enterprise_value",
        "trailing_pe",
        "forward_pe",
        "price_to_sales",
        "price_to_book",
        "ev_to_revenue",
        "ev_to_ebitda",
        "fcf_yield",
        "analyst_target_upside",
    ]:
        snapshot[key] = None
    snapshot["valuation_data_warning"] = (
        "Valuation multiples suppressed because yfinance appears to mix secondary-listing quote currency "
        "with primary-market financial statement currency. Use primary listing or verified source."
    )


def read_watchlist_df(watchlist_path: str) -> pd.DataFrame:
    p = Path(watchlist_path)
    if not p.exists():
        return pd.DataFrame(columns=["ticker", "name", "theme", "market"])

    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame(columns=["ticker", "name", "theme", "market"])


def upsert_watchlist_rows(watchlist_path: str, rows: List[Dict[str, Any]]) -> None:
    p = Path(watchlist_path)
    df = read_watchlist_df(watchlist_path)
    for col in ["ticker", "name", "theme", "market"]:
        if col not in df.columns:
            df[col] = ""

    existing = {normalize_ticker(t): i for i, t in enumerate(df["ticker"].tolist())}
    additions = []
    for row in rows:
        ticker = normalize_ticker(row.get("ticker"))
        if not ticker:
            continue
        if is_disallowed_market(row.get("ticker"), row.get("market")):
            continue
        clean = {
            "ticker": str(row.get("ticker", "")).strip(),
            "name": clean_company_name(row.get("ticker"), row.get("name")),
            "theme": str(row.get("theme", "")).strip(),
            "market": str(row.get("market", "")).strip(),
        }
        if ticker in existing:
            idx = existing[ticker]
            for col, value in clean.items():
                should_override = col == "name" and ticker in COMPANY_NAME_ALIASES
                if value and (should_override or pd.isna(df.at[idx, col]) or not str(df.at[idx, col]).strip()):
                    df.at[idx, col] = value
        else:
            additions.append(clean)
            existing[ticker] = len(df) + len(additions) - 1

    if additions:
        df = pd.concat([df, pd.DataFrame(additions)], ignore_index=True)
    df[["ticker", "name", "theme", "market"]].to_csv(p, index=False, encoding="utf-8")


def http_json_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    data = None
    req_headers = headers or {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers = {"Content-Type": "application/json", **req_headers}
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def active_search_provider() -> Optional[str]:
    providers = available_search_providers()
    return providers[0] if providers else None


def valid_api_key_value(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    placeholder_tokens = ("your_", "your-", "your ", "api key", "apikey", "你的", "替换", "填入")
    if any(token in lowered for token in placeholder_tokens):
        return False
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return True


def search_api_key(provider: str) -> str:
    key_names = {
        "tavily": "TAVILY_API_KEY",
        "brave": "BRAVE_SEARCH_API_KEY",
        "bing": "BING_SEARCH_API_KEY",
        "serpapi": "SERPAPI_API_KEY",
    }
    value = os.getenv(key_names.get(provider, ""), "")
    if not valid_api_key_value(value):
        raise RuntimeError(f"{key_names.get(provider, 'SEARCH_API_KEY')} is missing, invalid, or still a placeholder.")
    return str(value).strip()


def available_search_providers() -> List[str]:
    forced_provider = str(os.getenv("WEB_SEARCH_PROVIDER") or os.getenv("SEARCH_PROVIDER") or "").lower().strip()
    provider_keys = {
        "tavily": "TAVILY_API_KEY",
        "brave": "BRAVE_SEARCH_API_KEY",
        "bing": "BING_SEARCH_API_KEY",
        "serpapi": "SERPAPI_API_KEY",
    }
    provider_aliases = {
        "brave_search": "brave",
        "bing_search": "bing",
        "serp_api": "serpapi",
    }
    if forced_provider in {"none", "off", "disabled"}:
        return []
    if forced_provider:
        provider = provider_aliases.get(forced_provider, forced_provider)
        api_key_name = provider_keys.get(provider)
        return [provider] if api_key_name and valid_api_key_value(os.getenv(api_key_name)) else []

    providers: List[str] = []
    if valid_api_key_value(os.getenv("TAVILY_API_KEY")):
        providers.append("tavily")
    if valid_api_key_value(os.getenv("BRAVE_SEARCH_API_KEY")):
        providers.append("brave")
    if valid_api_key_value(os.getenv("BING_SEARCH_API_KEY")):
        providers.append("bing")
    if valid_api_key_value(os.getenv("SERPAPI_API_KEY")):
        providers.append("serpapi")
    return providers


def web_search(
    query: str,
    max_results: int = 8,
    diagnostics: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    providers = available_search_providers()
    if not providers:
        return []

    def run_provider_search(provider: str) -> List[Dict[str, str]]:
        if provider == "tavily":
            data = http_json_request(
                "https://api.tavily.com/search",
                method="POST",
                payload={
                    "api_key": search_api_key("tavily"),
                    "query": query,
                    "search_depth": os.getenv("TAVILY_SEARCH_DEPTH", "basic"),
                    "max_results": max_results,
                    "include_answer": False,
                },
            )
            return [{
                "title": str(r.get("title", "")),
                "url": str(r.get("url", "")),
                "snippet": str(r.get("content", "")),
                "provider": provider,
            } for r in data.get("results", [])[:max_results]]

        if provider == "brave":
            url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({
                "q": query,
                "count": max_results,
            })
            data = http_json_request(url, headers={
                "Accept": "application/json",
                "X-Subscription-Token": search_api_key("brave"),
            })
            results = data.get("web", {}).get("results", [])
            return [{
                "title": str(r.get("title", "")),
                "url": str(r.get("url", "")),
                "snippet": str(r.get("description", "")),
                "provider": provider,
            } for r in results[:max_results]]

        if provider == "bing":
            url = "https://api.bing.microsoft.com/v7.0/search?" + urllib.parse.urlencode({
                "q": query,
                "count": max_results,
                "responseFilter": "Webpages",
            })
            data = http_json_request(url, headers={
                "Ocp-Apim-Subscription-Key": search_api_key("bing"),
            })
            results = data.get("webPages", {}).get("value", [])
            return [{
                "title": str(r.get("name", "")),
                "url": str(r.get("url", "")),
                "snippet": str(r.get("snippet", "")),
                "provider": provider,
            } for r in results[:max_results]]

        if provider == "serpapi":
            url = "https://serpapi.com/search.json?" + urllib.parse.urlencode({
                "q": query,
                "engine": "google",
                "api_key": search_api_key("serpapi"),
                "num": max_results,
            })
            data = http_json_request(url)
            results = data.get("organic_results", [])
            return [{
                "title": str(r.get("title", "")),
                "url": str(r.get("link", "")),
                "snippet": str(r.get("snippet", "")),
                "provider": provider,
            } for r in results[:max_results]]
        return []

    failure_statuses = {"failed", "rate_limited", "timeout", "json_error"}
    last_diag: Optional[Dict[str, Any]] = None
    for idx, provider in enumerate(providers):
        results, diag = retry_call(
            lambda provider=provider: run_provider_search(provider),
            source=provider,
            operation="web_search",
            target=query,
            max_attempts=int(os.getenv("WEB_SEARCH_MAX_ATTEMPTS", "2")),
            base_sleep_seconds=float(os.getenv("WEB_SEARCH_RETRY_BASE_SECONDS", "1")),
            retry_on=(urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, Exception),
            empty_reliability_impact="low",
            error_reliability_impact="medium",
        )
        last_diag = diag
        if diagnostics is not None:
            diagnostics.append(diag)
        if diag.get("status") not in failure_statuses:
            return results or []

        has_fallback = idx < len(providers) - 1
        message = f"Web search failed via {provider}: {diag.get('error_message')}"
        if has_fallback:
            message += f" Falling back to {providers[idx + 1]}."
        console.print(f"[yellow]{message}[/yellow]")

    return [] if last_diag else []


def build_evidence_queries(ticker: str, name: str, theme: str, market: str) -> List[Dict[str, str]]:
    company = f"{name} {ticker}"
    return [
        {
            "category": "annual_report",
            "query": f"{company} annual report 10-K annual results investor relations {theme}",
        },
        {
            "category": "quarterly_report",
            "query": f"{company} quarterly report 10-Q quarterly results earnings release {theme}",
        },
        {
            "category": "earnings_call_transcript",
            "query": f"{company} earnings call transcript latest quarter {theme}",
        },
        {
            "category": "investor_presentation",
            "query": f"{company} investor presentation capital markets day PDF {theme}",
        },
        {
            "category": "press_release",
            "query": f"{company} press release AI data center {theme} latest",
        },
        {
            "category": "supply_chain_news_sell_side",
            "query": f"{company} supply chain news analyst report summary customers orders backlog {theme}",
        },
        {
            "category": "industry_data",
            "query": f"{theme} market share forecast TrendForce Omdia Yole SemiAnalysis AI data center",
        },
    ]


def build_official_source_queries(
    company_name: str,
    ticker: str,
    theme: str,
    market: str,
) -> List[Dict[str, Any]]:
    company = str(company_name or "").strip()
    ticker_text = str(ticker or "").strip()
    market_l = str(market or "").lower()
    official_domains = sorted(company_primary_domains(company).union(company_primary_domains(ticker_text)))
    queries: List[Dict[str, Any]] = []

    def add(query_type: str, query: str, expected_tier: str, priority: int) -> None:
        queries.append({
            "query_type": query_type,
            "query": query,
            "expected_tier": expected_tier,
            "priority": priority,
        })

    if "korea" in market_l or ticker_text.upper().endswith(".KS") or ticker_text.upper().endswith(".KQ"):
        if domain_matches("skhynix.com", tuple(official_domains)) or "hynix" in company.lower():
            add("company_ir_results", "site:skhynix.com SK hynix financial results 2026 Q1 HBM", "primary_company", 1)
            add("company_ir_pdf", "site:skhynix.com SK hynix earnings release 2026 Q1 PDF", "primary_company", 1)
            add("company_news_hbm", "site:news.skhynix.com SK hynix HBM4 HBM4E mass production 2027", "primary_company", 1)
            add("company_news_capacity", "site:news.skhynix.com SK hynix financial results HBM demand capacity", "primary_company", 1)
            add("company_ir_annual", "site:skhynix.com SK hynix investor relations annual report 2025", "primary_company", 2)
            add("regulatory_dart_annual", "site:dart.fss.or.kr SK hynix annual report 2025", "primary_regulatory", 1)
            add("regulatory_dart_business", f"site:dart.fss.or.kr {ticker_text} SK hynix business report", "primary_regulatory", 1)
            add("exchange_krx_disclosure", "site:kind.krx.co.kr SK hynix disclosure HBM", "primary_regulatory", 1)
        else:
            add("regulatory_dart_annual", f"site:dart.fss.or.kr {company} annual report 2025", "primary_regulatory", 2)
            add("regulatory_dart_business", f"site:dart.fss.or.kr {ticker_text} {company} business report", "primary_regulatory", 2)
            add("exchange_krx_disclosure", f"site:kind.krx.co.kr {company} disclosure {theme}", "primary_regulatory", 3)

    elif "us" in market_l or re.fullmatch(r"[A-Z]{1,5}", ticker_text.upper() or ""):
        add("regulatory_sec_10k", f"site:sec.gov {ticker_text} 10-K", "primary_regulatory", 1)
        add("regulatory_sec_10q", f"site:sec.gov {ticker_text} 10-Q", "primary_regulatory", 1)

    elif "hong kong" in market_l or "hk" in market_l or ticker_text.upper().endswith(".HK"):
        add("exchange_hkex_annual", f"site:hkexnews.hk {ticker_text} {company} annual report", "primary_regulatory", 1)
        add("exchange_hkex_interim", f"site:hkexnews.hk {ticker_text} {company} interim results", "primary_regulatory", 2)

    elif "china" in market_l or ticker_text.upper().endswith(".SZ") or ticker_text.upper().endswith(".SS"):
        add("regulatory_cninfo_annual", f"site:cninfo.com.cn {company} 年度报告", "primary_regulatory", 1)
        add("regulatory_cninfo_quarterly", f"site:cninfo.com.cn {company} 季度报告", "primary_regulatory", 1)

    elif "japan" in market_l or ticker_text.upper().endswith(".T"):
        add("exchange_jpx_annual", f"site:jpx.co.jp {ticker_text} {company} annual securities report", "primary_regulatory", 1)

    elif "taiwan" in market_l or ticker_text.upper().endswith(".TW") or ticker_text.upper().endswith(".TWO"):
        add("exchange_twse_annual", f"site:twse.com.tw {ticker_text} {company} annual report", "primary_regulatory", 1)

    for domain in official_domains:
        add("company_ir_earnings", f"site:{domain} {company} investor relations earnings release {theme}", "primary_company", 2)
        add("company_ir_annual", f"site:{domain} {company} annual report", "primary_company", 3)
        add("company_ir_quarterly", f"site:{domain} {company} quarterly results", "primary_company", 3)
        if "china" in market_l or ticker_text.upper().endswith((".SZ", ".SS")):
            add("company_ir_cn_annual", f"site:{domain} {company} 投资者关系 年报", "primary_company", 2)
            add("company_ir_cn_results", f"site:{domain} {company} 业绩说明会", "primary_company", 3)

    limit = int(os.getenv("OFFICIAL_SOURCE_QUERY_LIMIT", "6"))
    seen = set()
    capped: List[Dict[str, Any]] = []
    for item in sorted(queries, key=lambda x: (x["priority"], x["query"])):
        q = item["query"]
        if q in seen:
            continue
        capped.append(item)
        seen.add(q)
        if len(capped) >= limit:
            break
    return capped


def source_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        return domain[4:] if domain.startswith("www.") else domain
    except Exception:
        return ""


def domain_matches(domain: str, patterns: tuple) -> bool:
    domain = (domain or "").lower().strip(".")
    for pattern in patterns:
        p = str(pattern or "").lower().strip(".")
        if not p:
            continue
        if domain == p or domain.endswith(f".{p}"):
            return True
    return False


def company_primary_domains(company_name: str) -> set:
    name_norm = str(company_name or "").strip().lower()
    ticker_norm = normalize_ticker(company_name)
    domains = set()
    if ticker_norm in COMPANY_TICKER_DOMAIN_MAP:
        domains.update(d.lower().strip(".") for d in COMPANY_TICKER_DOMAIN_MAP[ticker_norm])
    for company, mapped in COMPANY_PRIMARY_DOMAIN_MAP.items():
        company_norm = company.lower()
        if company_norm == name_norm or company_norm in name_norm or name_norm in company_norm:
            domains.update(d.lower().strip(".") for d in mapped)
    return domains


def classify_source_strict(
    url: str,
    title: str = "",
    snippet: str = "",
    company_name: str = "",
) -> Dict[str, Any]:
    domain = source_domain(url)
    text = f"{title} {snippet} {url}".lower()
    warnings: List[str] = []

    regulatory_domains = (
        "sec.gov",
        "dart.fss.or.kr",
        "englishdart.fss.or.kr",
        "kind.krx.co.kr",
        "hkexnews.hk",
        "sgx.com",
        "jpx.co.jp",
        "twse.com.tw",
        "cninfo.com.cn",
    )
    never_primary_domains = (
        "linkedin.com",
        "finance.yahoo.com",
        "gurufocus.com",
        "simplywall.st",
        "biggo.com",
        "finance.biggo.com",
        "sahmcapital.com",
        "perplexity.ai",
        "investing.com",
        "quartr.com",
        "alphaspread.com",
        "aastocks.com",
        "247wallst.com",
    )
    weak_domains = ("youtube.com", "youtu.be", "reddit.com", "x.com", "twitter.com")
    industry_domains = (
        "trendforce.com",
        "yolegroup.com",
        "semianalysis.com",
        "omdia.tech.informa.com",
    )
    reputable_news_domains = (
        "reuters.com",
        "bloomberg.com",
        "ft.com",
        "wsj.com",
        "barrons.com",
    )

    result = {
        "domain": domain,
        "evidence_tier": "secondary_news",
        "source_type": "web_search_lead",
        "is_primary": False,
        "is_official_company": False,
        "is_regulatory": False,
        "warnings": warnings,
    }

    if domain_matches(domain, weak_domains):
        result.update({"evidence_tier": "weak_source", "source_type": "social_or_video"})
        return result

    if domain_matches(domain, regulatory_domains):
        result.update({
            "evidence_tier": "primary_regulatory",
            "source_type": "regulatory_or_exchange_filing",
            "is_primary": True,
            "is_regulatory": True,
        })
        return result

    if domain_matches(domain, never_primary_domains):
        warnings.append("never_primary_domain")
        result.update({"evidence_tier": "secondary_news", "source_type": "aggregator_or_social_or_reprint"})
        return result

    if domain_matches(domain, industry_domains):
        result.update({"evidence_tier": "industry_data", "source_type": "industry_research"})
        return result

    official_domains = company_primary_domains(company_name)
    if domain_matches(domain, tuple(official_domains)):
        result.update({
            "evidence_tier": "primary_company",
            "source_type": "company_ir_or_official_news",
            "is_primary": True,
            "is_official_company": True,
        })
        return result

    if domain_matches(domain, reputable_news_domains):
        result.update({"evidence_tier": "secondary_news", "source_type": "reputable_news"})
        return result

    if "transcript" in text or "earnings call" in text:
        result.update({"evidence_tier": "transcript_secondary", "source_type": "earnings_transcript_secondary"})
        return result

    if "press release" in text or "announces" in text:
        result.update({"evidence_tier": "secondary_news", "source_type": "aggregator_or_social_or_reprint"})
        return result

    return result


def classify_evidence_source(
    url: str,
    title: str,
    snippet: str,
    category: str,
    company_name: str,
) -> Dict[str, Any]:
    strict = classify_source_strict(url, title, snippet, company_name)
    return {
        "tier": strict["evidence_tier"],
        "source_type": strict["source_type"],
        "domain": strict["domain"],
        "warnings": strict["warnings"],
        "is_primary": strict["is_primary"],
    }


def normalize_evidence_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        return urllib.parse.urlunparse((scheme, netloc, path, "", parsed.query, ""))
    except Exception:
        return str(url or "").strip().lower()


def append_evidence_result_lines(
    lines: List[str],
    provider_name: str,
    title: str,
    url: str,
    snippet: str,
    classification: Dict[str, Any],
    query_type: Optional[str] = None,
    expected_tier: Optional[str] = None,
) -> None:
    lines.append(f"- Source: {provider_name}")
    if query_type:
        lines.append(f"  Query Type: {query_type}")
    if expected_tier:
        lines.append(f"  Expected Tier: {expected_tier}")
    lines.append(f"  Evidence Tier: {classification['tier']}")
    lines.append(f"  Source Type: {classification['source_type']}")
    lines.append(f"  Source Domain: {classification.get('domain') or 'N/A'}")
    lines.append(f"  Is Primary: {classification.get('is_primary')}")
    lines.append(f"  Source Warnings: {', '.join(classification.get('warnings') or []) or 'None'}")
    lines.append(f"  Title: {title}")
    lines.append(f"  URL: {url or 'N/A'}")
    lines.append(f"  Snippet: {snippet or 'N/A'}")
    lines.append("")


def parse_official_source_search_summary(text: str) -> Dict[str, Any]:
    summary = {
        "official_source_search_enabled": OFFICIAL_SOURCE_SEARCH_ENABLED,
        "official_queries_run": 0,
        "official_primary_hits": 0,
        "official_regulatory_hits": 0,
        "official_company_hits": 0,
        "official_search_warnings": [],
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("Official Source Search Enabled:"):
            summary["official_source_search_enabled"] = line.split(":", 1)[1].strip().lower() == "true"
        elif line.startswith("Official Queries Run:"):
            summary["official_queries_run"] = int(safe_float(line.split(":", 1)[1].strip()) or 0)
        elif line.startswith("Official Primary Hits:"):
            summary["official_primary_hits"] = int(safe_float(line.split(":", 1)[1].strip()) or 0)
        elif line.startswith("Official Regulatory Hits:"):
            summary["official_regulatory_hits"] = int(safe_float(line.split(":", 1)[1].strip()) or 0)
        elif line.startswith("Official Company Hits:"):
            summary["official_company_hits"] = int(safe_float(line.split(":", 1)[1].strip()) or 0)
        elif line.startswith("Official Search Warnings:"):
            raw = line.split(":", 1)[1].strip()
            summary["official_search_warnings"] = [] if raw in {"", "None"} else [x.strip() for x in raw.split(",") if x.strip()]
    return summary


def parse_evidence_search_diagnostics(text: str) -> List[Dict[str, Any]]:
    diagnostics: List[Dict[str, Any]] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "## Evidence Search Diagnostics":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("|") or line.startswith("|---") or "Source | Operation" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 9 or cells[0] == "N/A":
            continue
        diagnostics.append({
            "source": cells[0],
            "operation": cells[1],
            "status": cells[2],
            "target": cells[3],
            "retry_count": safe_float(cells[4]) or 0,
            "row_count": safe_float(cells[5]) if cells[5] != "N/A" else None,
            "data_reliability_impact": cells[6],
            "error_type": cells[7],
            "error_message": cells[8],
        })
    return diagnostics


def parse_evidence_search_diagnostics_summary(text: str) -> Dict[str, Any]:
    diagnostics = parse_evidence_search_diagnostics(text)
    summary = fetch_diagnostics_summary(diagnostics)
    providers = sorted({d.get("source") for d in diagnostics if d.get("source")})
    return {
        "evidence_search_provider": ", ".join(providers) or active_search_provider() or "none",
        "evidence_search_query_count": summary["total"],
        "evidence_search_failed_count": summary["failed"],
        "evidence_search_empty_count": summary["empty"],
        "evidence_search_rate_limited_count": summary["rate_limited"],
        "evidence_search_timeout_count": summary["timeout"],
        "evidence_search_json_error_count": summary["json_error"],
        "evidence_search_diagnostics_summary": summary,
    }


def get_evidence_context(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    query_type_filter: Optional[set] = None,
) -> str:
    evidence_fetch_diagnostics: List[Dict[str, Any]] = []
    lines = [
        "## Evidence Context",
        "",
        "This section contains search-derived evidence leads. Treat snippets as leads, not complete primary evidence.",
        "Prefer official company filings, investor relations, earnings transcripts, and named industry sources when forming conclusions.",
        "Evidence Tier labels are machine-generated quality hints: primary_* > transcript_secondary / industry_data > secondary_news > weak_source.",
        "Do not call a source primary unless its Evidence Tier starts with primary_.",
        "",
    ]
    if query_type_filter is not None:
        lines.extend([
            "## Evidence Incremental Search Plan",
            "",
            f"- Query types requested: {', '.join(sorted(query_type_filter)) if query_type_filter else 'None'}",
            "",
        ])

    if not EVIDENCE_SEARCH_ENABLED:
        lines.append("Evidence search disabled by EVIDENCE_SEARCH_ENABLED=0.")
        lines.extend(["", fetch_diagnostics_to_markdown("Evidence Search Diagnostics", evidence_fetch_diagnostics)])
        return "\n".join(lines)

    provider = active_search_provider()
    if not provider:
        lines.append("No web search provider configured. Set TAVILY_API_KEY, BRAVE_SEARCH_API_KEY, BING_SEARCH_API_KEY, or SERPAPI_API_KEY. To force one provider, set WEB_SEARCH_PROVIDER=tavily|brave|bing|serpapi.")
        lines.extend(["", fetch_diagnostics_to_markdown("Evidence Search Diagnostics", evidence_fetch_diagnostics)])
        return "\n".join(lines)

    max_results = int(os.getenv("EVIDENCE_RESULTS_PER_QUERY", "4"))
    seen_urls = set()
    any_result = False

    official_queries_run = 0
    official_primary_hits = 0
    official_regulatory_hits = 0
    official_company_hits = 0
    official_search_warnings: List[str] = []
    official_section: List[str] = ["### official_primary_sources", ""]
    if OFFICIAL_SOURCE_SEARCH_ENABLED:
        official_queries = build_official_source_queries(name, ticker, theme, market)
        if not company_primary_domains(name).union(company_primary_domains(ticker)):
            official_search_warnings.append("no_company_domain_mapping")
        official_results_per_query = int(os.getenv("OFFICIAL_SOURCE_RESULTS_PER_QUERY", "3"))
        regulatory_queries = 0
        regulatory_results = 0
        for item in official_queries:
            query_type = str(item.get("query_type") or "official")
            expected_tier = str(item.get("expected_tier") or "")
            query = str(item.get("query") or "")
            if query_type_filter is not None and query_type not in query_type_filter:
                official_section.extend([f"#### {query_type}", "", "Skipped because unexpired cached facts already exist.", ""])
                continue
            if expected_tier == "primary_regulatory":
                regulatory_queries += 1
            official_queries_run += 1
            official_section.extend([f"#### {query_type}", "", f"Query: `{query}`", f"Expected Tier: {expected_tier}", ""])
            kept = 0
            for result in web_search(query, max_results=official_results_per_query, diagnostics=evidence_fetch_diagnostics):
                url = result.get("url", "")
                norm_url = normalize_evidence_url(url)
                if url and norm_url in seen_urls:
                    continue
                title = result.get("title", "Untitled")
                snippet = (result.get("snippet") or "").replace("\n", " ").strip()
                provider_name = result.get("provider", provider)
                classification = classify_evidence_source(url, title, snippet, query_type, name)
                if classification["tier"] not in {"primary_company", "primary_regulatory", "transcript_secondary", "industry_data", "secondary_news", "weak_source"}:
                    continue
                append_evidence_result_lines(
                    official_section,
                    provider_name,
                    title,
                    url,
                    snippet,
                    classification,
                    query_type=query_type,
                    expected_tier=expected_tier,
                )
                if classification["tier"] == "primary_regulatory":
                    official_regulatory_hits += 1
                    official_primary_hits += 1
                elif classification["tier"] == "primary_company":
                    official_company_hits += 1
                    official_primary_hits += 1
                if expected_tier == "primary_regulatory":
                    regulatory_results += 1
                if url:
                    seen_urls.add(norm_url)
                kept += 1
                any_result = True
            if kept == 0:
                official_section.append("No unique results returned.")
                official_section.append("")
        if regulatory_queries and regulatory_results == 0:
            official_search_warnings.append("regulatory_search_returned_no_results")
        if official_queries_run > 0 and official_primary_hits == 0:
            official_search_warnings.append("official_search_enabled_but_no_primary_hits")
            official_search_warnings.append("official_sources_need_manual_followup")
    else:
        official_section.append("Official source search disabled by OFFICIAL_SOURCE_SEARCH_ENABLED=0.")
        official_section.append("")

    summary_lines = [
        f"Official Source Search Enabled: {OFFICIAL_SOURCE_SEARCH_ENABLED}",
        f"Official Queries Run: {official_queries_run}",
        f"Official Primary Hits: {official_primary_hits}",
        f"Official Regulatory Hits: {official_regulatory_hits}",
        f"Official Company Hits: {official_company_hits}",
        f"Official Search Warnings: {', '.join(sorted(set(official_search_warnings))) or 'None'}",
        "",
    ]
    lines.extend(official_section[:1] + summary_lines + official_section[1:])

    for item in build_evidence_queries(ticker, name, theme, market):
        category = item["category"]
        query = item["query"]
        if query_type_filter is not None and category not in query_type_filter:
            lines.extend([f"### {category}", "", "Skipped because unexpired cached facts already exist.", ""])
            continue
        lines.extend([f"### {category}", "", f"Query: `{query}`", ""])
        results = web_search(query, max_results=max_results, diagnostics=evidence_fetch_diagnostics)
        kept = 0
        for result in results:
            url = result.get("url", "")
            norm_url = normalize_evidence_url(url)
            if url and norm_url in seen_urls:
                continue
            title = result.get("title", "Untitled")
            snippet = (result.get("snippet") or "").replace("\n", " ").strip()
            provider_name = result.get("provider", provider)
            classification = classify_evidence_source(url, title, snippet, category, name)
            append_evidence_result_lines(lines, provider_name, title, url, snippet, classification, query_type=category)
            if url:
                seen_urls.add(norm_url)
            kept += 1
            any_result = True

        if kept == 0:
            lines.append("No unique results returned.")
            lines.append("")

    if not any_result:
        lines.append("No evidence search results returned.")

    lines.extend(["", fetch_diagnostics_to_markdown("Evidence Search Diagnostics", evidence_fetch_diagnostics)])
    return "\n".join(lines)


def extract_evidence_items_from_text(text: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("- Source:"):
            if current:
                items.append(current)
            current = {"source": line.split(":", 1)[1].strip()}
        elif current and line.startswith("Query Type:"):
            current["query_type"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("Expected Tier:"):
            current["expected_tier"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("Evidence Tier:"):
            current["evidence_tier"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("Source Type:"):
            current["source_type"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("Source Domain:"):
            current["source_domain"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("Is Primary:"):
            current["is_primary"] = line.split(":", 1)[1].strip().lower() == "true"
        elif current and line.startswith("Source Warnings:"):
            raw = line.split(":", 1)[1].strip()
            current["source_warnings"] = [] if raw in {"", "None"} else [x.strip() for x in raw.split(",") if x.strip()]
        elif current and line.startswith("Title:"):
            current["title"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("URL:"):
            current["url"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("Snippet:"):
            current["snippet"] = line.split(":", 1)[1].strip()
    if current:
        items.append(current)
    return items


def score_evidence_quality(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    tiers = [str(item.get("evidence_tier") or item.get("tier") or "") for item in evidence_items]
    primary_regulatory_count = sum(1 for t in tiers if t == "primary_regulatory")
    primary_company_count = sum(1 for t in tiers if t == "primary_company")
    transcript_secondary_count = sum(1 for t in tiers if t == "transcript_secondary")
    industry_data_count = sum(1 for t in tiers if t == "industry_data")
    secondary_news_count = sum(1 for t in tiers if t == "secondary_news")
    weak_source_count = sum(1 for t in tiers if t == "weak_source")

    score = 3
    if primary_regulatory_count >= 1:
        score += 3
    if primary_company_count >= 1:
        score += 2
    if transcript_secondary_count >= 1:
        score += 1
    if industry_data_count >= 1:
        score += 1
    score = int(max(1, min(10, score)))

    warnings: List[str] = []
    if primary_regulatory_count == 0:
        warnings.append("no_primary_regulatory_filing")
    if primary_company_count == 0:
        warnings.append("no_official_company_ir_source")
    if weak_source_count >= 3:
        warnings.append("too_many_weak_sources")
    if secondary_news_count > primary_company_count + primary_regulatory_count + transcript_secondary_count:
        warnings.append("evidence_overweighted_to_secondary_news")

    return {
        "evidence_quality_score": score,
        "primary_regulatory_count": primary_regulatory_count,
        "primary_company_count": primary_company_count,
        "transcript_secondary_count": transcript_secondary_count,
        "industry_data_count": industry_data_count,
        "secondary_news_count": secondary_news_count,
        "weak_source_count": weak_source_count,
        "evidence_warnings": warnings,
    }


def score_evidence_quality_from_text(text: str) -> Dict[str, Any]:
    quality = score_evidence_quality(extract_evidence_items_from_text(text))
    quality["official_source_search"] = parse_official_source_search_summary(text)
    quality["evidence_search_diagnostics"] = parse_evidence_search_diagnostics_summary(text)
    return quality


def fact_cache_db_path(cache_path: Optional[str] = None) -> Path:
    return Path(cache_path or FACT_CACHE_PATH)


def ensure_fact_cache_schema(cache_path: Optional[str] = None) -> Path:
    db_path = fact_cache_db_path(cache_path)
    ensure_dir(db_path.parent)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                ticker_norm TEXT NOT NULL,
                company_name TEXT,
                theme TEXT,
                market TEXT,
                fact TEXT NOT NULL,
                fact_category TEXT,
                source_url TEXT NOT NULL DEFAULT '',
                source_domain TEXT,
                evidence_tier TEXT,
                source_type TEXT,
                title TEXT,
                snippet TEXT,
                confidence REAL,
                warnings_json TEXT,
                query_type TEXT,
                provider TEXT,
                model_used TEXT,
                fetched_at TEXT,
                source_published_at TEXT,
                expires_at TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(ticker_norm, source_url, fact)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_ticker ON facts(ticker_norm, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_expiry ON facts(expires_at)")
    return db_path


def fact_cache_ttl_days(evidence_tier: str, source_type: str = "") -> int:
    tier = str(evidence_tier or "")
    source = str(source_type or "")
    if tier in {"primary_regulatory", "primary_company"}:
        return int(os.getenv("FACT_CACHE_PRIMARY_TTL_DAYS", "120"))
    if tier in {"transcript_secondary", "industry_data"} or source in {"earnings_transcript_secondary", "industry_research"}:
        return int(os.getenv("FACT_CACHE_RESEARCH_TTL_DAYS", "60"))
    if tier == "secondary_news":
        return int(os.getenv("FACT_CACHE_NEWS_TTL_DAYS", "14"))
    return int(os.getenv("FACT_CACHE_WEAK_TTL_DAYS", "7"))


def fact_cache_expiry(evidence_tier: str, source_type: str = "") -> str:
    return (dt.datetime.now() + dt.timedelta(days=fact_cache_ttl_days(evidence_tier, source_type))).isoformat(timespec="seconds")


def build_fact_extraction_prompt(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    evidence_items: List[Dict[str, Any]],
) -> str:
    source_limit = int(os.getenv("FACT_EXTRACT_SOURCE_LIMIT", "40"))
    packed_sources = []
    for idx, item in enumerate(evidence_items[:source_limit]):
        packed_sources.append({
            "source_index": idx,
            "evidence_tier": item.get("evidence_tier"),
            "source_type": item.get("source_type"),
            "source_domain": item.get("source_domain"),
            "title": item.get("title"),
            "url": item.get("url"),
            "snippet": truncate_text(item.get("snippet"), 900),
            "source_warnings": item.get("source_warnings") or [],
        })
    return f"""
Return only one valid JSON object. No markdown.

Target:
- ticker: {ticker}
- company: {name}
- theme: {theme}
- market: {market}

You are extracting reusable investment-research facts from search results.
Use only the supplied source title/snippet/url/tier metadata. Do not infer beyond the snippet.
Skip weak, vague, duplicated, or unsupported claims.
Keep each fact short, concrete, and useful for later screening.

Allowed fact_category values:
business_model, ai_demand, orders_backlog, customer, competition, financial, margin, valuation, capacity, technology, risk, industry_data, data_gap, other

Sources:
```json
{json.dumps(packed_sources, ensure_ascii=False, indent=2)}
```

JSON schema:
{{
  "facts": [
    {{
      "source_index": 0,
      "fact_category": "ai_demand",
      "fact": "...",
      "confidence": 0.7,
      "source_published_at": null,
      "warnings": ["snippet_only"]
    }}
  ]
}}
"""


def extract_facts_from_evidence_context(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    evidence_md: str,
    diagnostics: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    evidence_items = extract_evidence_items_from_text(evidence_md)
    if not evidence_items:
        return []

    prompt = build_fact_extraction_prompt(ticker, name, theme, market, evidence_items)
    raw = call_llm(
        "Fact Extraction Agent",
        prompt,
        max_tokens=int(os.getenv("FACT_EXTRACT_MAX_TOKENS", "2500")),
        decorate=False,
        json_mode=True,
        diagnostics=diagnostics,
        provider_override=os.getenv("FACT_EXTRACT_PROVIDER", FACT_EXTRACT_PROVIDER),
        model_override=os.getenv("FACT_EXTRACT_MODEL", FACT_EXTRACT_MODEL),
        temperature_override=float(os.getenv("FACT_EXTRACT_TEMPERATURE", "0.1")),
        thinking_override="disabled",
    )
    payload = extract_json_object(raw)
    facts = payload.get("facts") if isinstance(payload, dict) else []
    if not isinstance(facts, list):
        return []

    now = iso_now()
    records: List[Dict[str, Any]] = []
    for item in facts:
        if not isinstance(item, dict):
            continue
        source_index = int(safe_float(item.get("source_index")) or -1)
        if source_index < 0 or source_index >= len(evidence_items):
            continue
        source = evidence_items[source_index]
        fact = truncate_text(item.get("fact"), 1000)
        if not fact:
            continue
        evidence_tier = str(source.get("evidence_tier") or "")
        source_type = str(source.get("source_type") or "")
        confidence = safe_float(item.get("confidence"))
        if confidence is not None and confidence > 1:
            confidence = confidence / 10 if confidence <= 10 else None
        records.append({
            "ticker": ticker,
            "ticker_norm": canonical_ticker_for(ticker),
            "company_name": name,
            "theme": theme,
            "market": market,
            "fact": fact,
            "fact_category": str(item.get("fact_category") or "other"),
            "source_url": str(source.get("url") or ""),
            "source_domain": str(source.get("source_domain") or ""),
            "evidence_tier": evidence_tier,
            "source_type": source_type,
            "title": str(source.get("title") or ""),
            "snippet": truncate_text(source.get("snippet"), 1200),
            "confidence": confidence,
            "warnings": item.get("warnings") if isinstance(item.get("warnings"), list) else [],
            "query_type": str(source.get("query_type") or ""),
            "provider": os.getenv("FACT_EXTRACT_PROVIDER", FACT_EXTRACT_PROVIDER),
            "model_used": os.getenv("FACT_EXTRACT_MODEL", FACT_EXTRACT_MODEL),
            "fetched_at": now,
            "source_published_at": item.get("source_published_at"),
            "expires_at": fact_cache_expiry(evidence_tier, source_type),
            "created_at": now,
            "updated_at": now,
        })
    return records


def save_fact_cache_records(records: List[Dict[str, Any]], cache_path: Optional[str] = None) -> int:
    if not records or not FACT_CACHE_ENABLED:
        return 0
    db_path = ensure_fact_cache_schema(cache_path)
    saved = 0
    with sqlite3.connect(db_path) as conn:
        for record in records:
            conn.execute(
                """
                INSERT INTO facts (
                    ticker, ticker_norm, company_name, theme, market, fact, fact_category,
                    source_url, source_domain, evidence_tier, source_type, title, snippet,
                    confidence, warnings_json, query_type, provider, model_used, fetched_at,
                    source_published_at, expires_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker_norm, source_url, fact) DO UPDATE SET
                    company_name=excluded.company_name,
                    theme=excluded.theme,
                    market=excluded.market,
                    fact_category=excluded.fact_category,
                    source_domain=excluded.source_domain,
                    evidence_tier=excluded.evidence_tier,
                    source_type=excluded.source_type,
                    title=excluded.title,
                    snippet=excluded.snippet,
                    confidence=excluded.confidence,
                    warnings_json=excluded.warnings_json,
                    query_type=excluded.query_type,
                    provider=excluded.provider,
                    model_used=excluded.model_used,
                    fetched_at=excluded.fetched_at,
                    source_published_at=excluded.source_published_at,
                    expires_at=excluded.expires_at,
                    updated_at=excluded.updated_at
                """,
                (
                    record.get("ticker"),
                    record.get("ticker_norm") or canonical_ticker_for(record.get("ticker")),
                    record.get("company_name"),
                    record.get("theme"),
                    record.get("market"),
                    record.get("fact"),
                    record.get("fact_category"),
                    record.get("source_url") or "",
                    record.get("source_domain"),
                    record.get("evidence_tier"),
                    record.get("source_type"),
                    record.get("title"),
                    record.get("snippet"),
                    record.get("confidence"),
                    json.dumps(record.get("warnings") or [], ensure_ascii=False),
                    record.get("query_type"),
                    record.get("provider"),
                    record.get("model_used"),
                    record.get("fetched_at"),
                    record.get("source_published_at"),
                    record.get("expires_at"),
                    record.get("created_at"),
                    record.get("updated_at"),
                ),
            )
            saved += 1
    return saved


def load_cached_facts(
    ticker: str,
    cache_path: Optional[str] = None,
    max_age_days: Optional[int] = None,
    include_expired: bool = False,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not FACT_CACHE_ENABLED:
        return []
    db_path = fact_cache_db_path(cache_path)
    if not db_path.exists():
        return []

    max_age = max_age_days if max_age_days is not None else int(os.getenv("FACT_CACHE_MAX_AGE_DAYS", "120"))
    limit_value = limit if limit is not None else int(os.getenv("FACT_CACHE_PROMPT_LIMIT", "80"))
    cutoff = (dt.datetime.now() - dt.timedelta(days=max_age)).isoformat(timespec="seconds")
    now = iso_now()
    query = "SELECT * FROM facts WHERE ticker_norm = ? AND updated_at >= ?"
    params: List[Any] = [canonical_ticker_for(ticker), cutoff]
    if not include_expired:
        query += " AND (expires_at IS NULL OR expires_at = '' OR expires_at >= ?)"
        params.append(now)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit_value)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]

    tier_rank = {"primary_regulatory": 0, "primary_company": 1, "transcript_secondary": 2, "industry_data": 3, "secondary_news": 4}
    rows.sort(key=lambda r: (tier_rank.get(str(r.get("evidence_tier") or ""), 9), str(r.get("updated_at") or "")), reverse=False)
    for row in rows:
        try:
            row["warnings"] = json.loads(row.get("warnings_json") or "[]")
        except Exception:
            row["warnings"] = []
    return rows


def expected_fact_query_types(ticker: str, name: str, theme: str, market: str) -> List[str]:
    query_types = {item["category"] for item in build_evidence_queries(ticker, name, theme, market)}
    if OFFICIAL_SOURCE_SEARCH_ENABLED:
        query_types.update(str(item.get("query_type") or "official") for item in build_official_source_queries(name, ticker, theme, market))
    return sorted(q for q in query_types if q)


def cached_fact_query_types(
    ticker: str,
    cache_path: Optional[str] = None,
    max_age_days: Optional[int] = None,
    include_expired: bool = False,
) -> set:
    facts = load_cached_facts(
        ticker,
        cache_path=cache_path,
        max_age_days=max_age_days,
        include_expired=include_expired,
        limit=int(os.getenv("FACT_CACHE_STATUS_LIMIT", "5000")),
    )
    return {str(f.get("query_type") or "").strip() for f in facts if str(f.get("query_type") or "").strip()}


def build_fact_cache_report(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    cache_path: Optional[str] = None,
    max_age_days: Optional[int] = None,
) -> Dict[str, Any]:
    expected = set(expected_fact_query_types(ticker, name, theme, market))
    cached = cached_fact_query_types(ticker, cache_path=cache_path, max_age_days=max_age_days)
    missing = sorted(expected - cached)
    return {
        "ticker": ticker,
        "company_name": name,
        "theme": theme,
        "market": market,
        "cache_path": str(fact_cache_db_path(cache_path)),
        "expected_query_types": sorted(expected),
        "cached_query_types": sorted(cached),
        "missing_or_stale_query_types": missing,
        "expected_query_type_count": len(expected),
        "cached_query_type_count": len(cached),
        "missing_or_stale_query_type_count": len(missing),
        "incremental_search_enabled": env_flag("FACT_CACHE_INCREMENTAL_SEARCH", True),
        "created_at": iso_now(),
    }


def fact_cache_report_to_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "## Fact Cache Report",
        "",
        f"- Cache path: {report.get('cache_path')}",
        f"- Expected query types: {report.get('expected_query_type_count')}",
        f"- Cached query types: {report.get('cached_query_type_count')}",
        f"- Missing or stale query types: {report.get('missing_or_stale_query_type_count')}",
        f"- Incremental search enabled: {report.get('incremental_search_enabled')}",
        "",
        "### Missing Or Stale Query Types",
        "",
    ]
    missing = report.get("missing_or_stale_query_types") or []
    lines.extend([f"- {q}" for q in missing] or ["- None"])
    lines.extend(["", "### Cached Query Types", ""])
    cached = report.get("cached_query_types") or []
    lines.extend([f"- {q}" for q in cached] or ["- None"])
    return "\n".join(lines)


def evidence_quality_from_cached_facts(facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    items = [{"evidence_tier": fact.get("evidence_tier")} for fact in facts if fact.get("evidence_tier")]
    quality = score_evidence_quality(items)
    quality["cached_fact_count"] = len(facts)
    return quality


def merge_evidence_quality_with_cached_facts(evidence_quality: Dict[str, Any], facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not facts:
        return evidence_quality
    cached_quality = evidence_quality_from_cached_facts(facts)
    merged = dict(evidence_quality)
    count_fields = [
        "primary_regulatory_count",
        "primary_company_count",
        "transcript_secondary_count",
        "industry_data_count",
        "secondary_news_count",
        "weak_source_count",
    ]
    combined_items: List[Dict[str, Any]] = []
    for field in count_fields:
        tier = field.replace("_count", "")
        for _ in range(int(evidence_quality.get(field) or 0) + int(cached_quality.get(field) or 0)):
            combined_items.append({"evidence_tier": tier})
    combined_quality = score_evidence_quality(combined_items)
    for field in count_fields:
        merged[field] = combined_quality.get(field, merged.get(field, 0))
    merged["evidence_quality_score"] = combined_quality.get("evidence_quality_score", merged.get("evidence_quality_score"))
    merged["evidence_warnings"] = combined_quality.get("evidence_warnings", merged.get("evidence_warnings") or [])
    merged["cached_fact_quality"] = cached_quality
    merged["cached_fact_count"] = len(facts)
    return merged


def facts_to_markdown(title: str, facts: List[Dict[str, Any]]) -> str:
    lines = [
        f"## {title}",
        "",
        f"- Cached fact count: {len(facts)}",
        "- Cached facts are reusable evidence leads. Prefer fresher primary evidence when available.",
        "",
        "| Category | Fact | Source | Tier | Confidence | Updated | Expires |",
        "|---|---|---|---|---:|---|---|",
    ]
    if not facts:
        lines.append("| N/A | No cached facts available. | N/A | N/A | N/A | N/A | N/A |")
        return "\n".join(lines)
    for fact in facts:
        source = fact.get("source_url") or fact.get("source_domain") or "N/A"
        lines.append(
            f"| {markdown_cell(fact.get('fact_category'), 30)} | {markdown_cell(fact.get('fact'), 180)} | "
            f"{markdown_cell(source, 80)} | {markdown_cell(fact.get('evidence_tier'), 30)} | "
            f"{fact.get('confidence') if fact.get('confidence') is not None else 'N/A'} | "
            f"{markdown_cell(fact.get('updated_at'), 30)} | {markdown_cell(fact.get('expires_at'), 30)} |"
        )
    return "\n".join(lines)


def warnings_to_markdown(title: str, warnings: List[str]) -> str:
    lines = [f"## {title}", ""]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("No major data quality warnings." if title == "Data Quality Warnings" else "None.")
    return "\n".join(lines)


def build_data_quality_warnings(snapshot: Dict[str, Any]) -> List[str]:
    ticker = str(snapshot.get("ticker") or "UNKNOWN")
    warnings: List[str] = []
    if snapshot.get("latest_price") is None:
        warnings.append(f"{ticker}: missing latest price.")
    one_year_return = safe_float(snapshot.get("one_year_return"))
    if one_year_return is not None and one_year_return > 3:
        warnings.append(f"{ticker}: 1Y return exceeds 300%; verify split adjustment, local listing price units, and yfinance data integrity.")
    volatility = safe_float(snapshot.get("volatility_1y"))
    if volatility is not None and volatility > 0.60:
        warnings.append(f"{ticker}: 1Y volatility exceeds 60%; size conservatively and verify data.")
    annuals = snapshot.get("annual_financials") or []
    annual_has_fcf = any(row.get("free_cash_flow") is not None for row in annuals if isinstance(row, dict))
    if snapshot.get("free_cashflow") is None and annual_has_fcf:
        warnings.append(f"{ticker}: summary free_cashflow is missing while annual financial table has calculated FCF.")
    if snapshot.get("fcf_yield") is None:
        warnings.append(f"{ticker}: fcf_yield is missing.")
    operating_margin = safe_float(snapshot.get("operating_margin"))
    if operating_margin is not None and operating_margin > 0.50:
        warnings.append(f"{ticker}: operating_margin exceeds 50%; potential peak-cycle margin.")
    gross_margin = safe_float(snapshot.get("gross_margin"))
    if gross_margin is not None and gross_margin > 0.55:
        warnings.append(f"{ticker}: gross_margin exceeds 55%; require normalized margin scenario.")
    return warnings


def reliability_rank(value: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(str(value or "high"), 2)


def lower_reliability(current: str, candidate: str) -> str:
    return candidate if reliability_rank(candidate) < reliability_rank(current) else current


def latest_annual_revenue(snapshot: Dict[str, Any]) -> Optional[float]:
    annuals = snapshot.get("annual_financials") or []
    if annuals and isinstance(annuals[0], dict):
        return safe_float(annuals[0].get("total_revenue") or annuals[0].get("revenue"))
    return None


def build_price_sanity_check(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    latest_price = safe_float(snapshot.get("latest_price"))
    market_cap = safe_float(snapshot.get("market_cap"))
    enterprise_value = safe_float(snapshot.get("enterprise_value"))
    total_revenue = safe_float(snapshot.get("total_revenue"))
    one_year_return = safe_float(snapshot.get("one_year_return"))
    volatility_1y = safe_float(snapshot.get("volatility_1y"))
    ev_to_revenue = safe_float(snapshot.get("ev_to_revenue"))
    if ev_to_revenue is None:
        ev_to_revenue = safe_div(enterprise_value, total_revenue)
    market_cap_to_revenue = safe_div(market_cap, total_revenue)
    implied_share_count = safe_div(market_cap, latest_price)
    price_fetch_reliability = str(snapshot.get("price_data_reliability_from_fetch") or "high")
    has_latest_price = latest_price is not None
    has_market_cap = market_cap is not None
    has_revenue = total_revenue is not None
    has_ev = enterprise_value is not None
    implied_share_count_valid = implied_share_count is not None and implied_share_count > 0

    price_reliability = "high"
    valuation_reliability = "high"
    warnings: List[str] = []
    severe = False

    def add_warning(code: str, severity: str = "medium", price: bool = False, valuation: bool = True) -> None:
        nonlocal price_reliability, valuation_reliability, severe
        warnings.append(code)
        if severity == "low":
            severe = True
        if price:
            price_reliability = lower_reliability(price_reliability, severity)
        if valuation:
            valuation_reliability = lower_reliability(valuation_reliability, severity)

    if latest_price is None:
        add_warning("missing_latest_price", "low", price=True, valuation=True)
    if market_cap is None:
        if has_ev:
            add_warning("market_cap_missing_but_ev_available_verify_before_position", "medium", price=False, valuation=True)
        elif has_latest_price and (has_ev or has_revenue):
            add_warning("market_cap_missing_use_manual_or_alternative_source", "medium", price=False, valuation=True)
            add_warning("market_cap_and_enterprise_value_missing_requires_verification", "low", price=False, valuation=True)
        else:
            add_warning("missing_price_or_market_cap", "low", price=True, valuation=True)

    if one_year_return is not None:
        if one_year_return > 3:
            extreme_momentum_data_complete = (
                has_latest_price
                and has_market_cap
                and has_revenue
                and implied_share_count_valid
                and price_fetch_reliability != "low"
            )
            if extreme_momentum_data_complete:
                add_warning("extreme_momentum_requires_manual_review_but_not_data_error", "medium", price=True, valuation=True)
            else:
                add_warning("extreme_momentum_with_incomplete_market_data_requires_price_verification", "low", price=True, valuation=True)
        elif one_year_return > 1.5:
            add_warning("strong_momentum_verify_price_source", "medium", price=True, valuation=True)

    if volatility_1y is not None and volatility_1y > 0.60:
        add_warning("volatility_above_60pct_high_position_risk", "medium", price=True, valuation=True)

    if market_cap_to_revenue is not None and market_cap_to_revenue > 20:
        severity = "medium"
        add_warning("market_cap_to_revenue_above_20x_verify_market_cap_and_revenue_units", severity, price=False, valuation=True)

    if ev_to_revenue is not None and ev_to_revenue > 20:
        add_warning("ev_to_revenue_above_20x_verify_ev_and_revenue_units", "medium", price=False, valuation=True)

    if implied_share_count is not None and implied_share_count <= 0:
        add_warning("invalid_implied_share_count", "low", price=True, valuation=True)

    annual_revenue = latest_annual_revenue(snapshot)
    if annual_revenue and total_revenue:
        revenue_diff = abs(total_revenue / annual_revenue - 1)
        if revenue_diff > 1.0:
            add_warning("snapshot_revenue_differs_from_latest_annual_by_over_100pct", "medium", price=False, valuation=True)

    manual_required = severe
    return {
        "price_data_reliability": price_reliability,
        "valuation_reliability": valuation_reliability,
        "manual_price_verification_required": manual_required,
        "price_sanity_warnings": sorted(set(warnings)),
        "derived_metrics": {
            "implied_share_count": implied_share_count,
            "market_cap_to_revenue": market_cap_to_revenue,
            "ev_to_revenue": ev_to_revenue,
            "latest_price": latest_price,
            "market_cap": market_cap,
            "one_year_return": one_year_return,
            "volatility_1y": volatility_1y,
        },
    }


def price_sanity_to_markdown(price_sanity: Dict[str, Any]) -> str:
    metrics = price_sanity.get("derived_metrics") or {}
    warnings = price_sanity.get("price_sanity_warnings") or []
    lines = [
        "## Price Sanity Check",
        "",
        f"- Price data reliability: {price_sanity.get('price_data_reliability')}",
        f"- Valuation reliability: {price_sanity.get('valuation_reliability')}",
        f"- Manual price verification required: {price_sanity.get('manual_price_verification_required')}",
        f"- Implied share count: {format_num(metrics.get('implied_share_count'))}",
        f"- Market cap / revenue: {metrics.get('market_cap_to_revenue') if metrics.get('market_cap_to_revenue') is not None else 'N/A'}",
        f"- EV / revenue: {metrics.get('ev_to_revenue') if metrics.get('ev_to_revenue') is not None else 'N/A'}",
        "",
        "### Price Sanity Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- No major price sanity warnings.")
    return "\n".join(lines)


def bridge_net_debt(snapshot: Dict[str, Any], market_cap: Optional[float], enterprise_value: Optional[float]) -> float:
    net_debt = safe_float(snapshot.get("net_debt"))
    if net_debt is not None:
        return net_debt
    total_debt = safe_float(snapshot.get("total_debt"))
    total_cash = safe_float(snapshot.get("total_cash"))
    if total_debt is not None and total_cash is not None:
        return total_debt - total_cash
    if enterprise_value is not None and market_cap is not None:
        return enterprise_value - market_cap
    return 0.0


def build_pe_valuation_scenarios(
    revenue: float,
    market_cap: float,
    latest_price: float,
    share_count: Optional[float],
    scenario_inputs: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    scenarios: Dict[str, Any] = {}
    for case, params in scenario_inputs.items():
        scenario_revenue = revenue * (1 + params["revenue_change"])
        scenario_net_income = scenario_revenue * params["normalized_net_margin"]
        scenario_equity_value = scenario_net_income * params["pe_multiple"]
        scenario_price = safe_div(scenario_equity_value, share_count) if share_count else None
        scenarios[case] = {
            **params,
            "normalized_margin": params["normalized_net_margin"],
            "multiple": params["pe_multiple"],
            "scenario_revenue": safe_float(scenario_revenue),
            "scenario_net_income": safe_float(scenario_net_income),
            "scenario_equity_value": safe_float(scenario_equity_value),
            "scenario_price": scenario_price,
            "upside_downside": safe_div(scenario_price - latest_price, latest_price) if scenario_price is not None and latest_price else safe_div(scenario_equity_value - market_cap, market_cap),
        }
    return scenarios


def build_ev_ebitda_valuation_scenarios(
    revenue: Optional[float],
    current_ebitda: Optional[float],
    market_cap: float,
    latest_price: float,
    share_count: Optional[float],
    net_debt: float,
    scenario_inputs: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    scenarios: Dict[str, Any] = {}
    for case, params in scenario_inputs.items():
        scenario_revenue = revenue * (1 + params.get("revenue_change", 0.0)) if revenue is not None else None
        if current_ebitda is not None:
            scenario_ebitda = current_ebitda * (1 + params.get("ebitda_change", params.get("revenue_change", 0.0)))
        else:
            scenario_ebitda = (scenario_revenue or revenue or 0) * params["normalized_operating_margin"]
        scenario_ev = scenario_ebitda * params["ev_ebitda_multiple"]
        scenario_equity_value = scenario_ev - net_debt
        scenario_price = safe_div(scenario_equity_value, share_count) if share_count else None
        scenarios[case] = {
            **params,
            "normalized_margin": params.get("normalized_operating_margin"),
            "multiple": params["ev_ebitda_multiple"],
            "scenario_revenue": safe_float(scenario_revenue),
            "scenario_ebitda": safe_float(scenario_ebitda),
            "scenario_ev": safe_float(scenario_ev),
            "scenario_equity_value": safe_float(scenario_equity_value),
            "scenario_price": scenario_price,
            "upside_downside": safe_div(scenario_price - latest_price, latest_price) if scenario_price is not None and latest_price else safe_div(scenario_equity_value - market_cap, market_cap),
        }
    return scenarios


def build_industry_valuation_bridge(
    snapshot: Dict[str, Any],
    theme: str = "",
    peer_context_text: str = "",
) -> Dict[str, Any]:
    latest_price = safe_float(snapshot.get("latest_price"))
    market_cap = safe_float(snapshot.get("market_cap"))
    enterprise_value = safe_float(snapshot.get("enterprise_value"))
    revenue = safe_float(snapshot.get("total_revenue"))
    current_ebitda = safe_float(snapshot.get("ebitda"))
    operating_margin = safe_float(snapshot.get("operating_margin"))
    annuals = snapshot.get("annual_financials") or []
    latest_net_income = None
    if annuals and isinstance(annuals[0], dict):
        latest_net_income = safe_float(annuals[0].get("net_income"))

    bucket = theme_bucket(theme)
    framework_map = {
        "memory": ("memory_dual_framework", "Dual framework: traditional memory-cycle normalized earnings plus structural HBM scarcity re-rating."),
        "optical": ("optical_cycle_ev_sales_margin", "Revenue / normalized operating margin / EV/Sales bridge for optical cycle companies."),
        "power_thermal": ("power_thermal_dual_framework", "Dual framework: traditional electrical equipment cycle plus AI data center power scarcity premium."),
        "compute_network": ("compute_network_growth_pe_ev_sales", "Revenue growth / normalized net margin / P/E bridge for compute and networking growth companies."),
        "semiconductor_equipment": ("semiconductor_equipment_dual_framework", "Dual framework: traditional WFE cycle plus AI equipment scarcity / quality premium."),
        "packaging": ("packaging_substrate_cycle_ev_ebitda", "EBITDA / EV/EBITDA bridge for packaging, substrates, PCB, and materials cycles."),
        "other": ("generic_normalized_earnings", "Conservative revenue / normalized net margin / P/E bridge for uncategorized companies."),
    }
    framework_type, framework_explanation = framework_map.get(bucket, framework_map["other"])
    warnings = ["discipline_scenarios_not_forecasts"]
    if bucket == "memory":
        warnings.extend([
            "structural_hbm_case_requires_primary_validation",
            "hbm_scarcity_framework_should_not_override_cycle_risk",
        ])
    elif bucket == "power_thermal":
        warnings.extend([
            "ai_power_scarcity_case_requires_backlog_margin_and_order_visibility",
            "scarcity_multiple_should_not_override_cycle_or_execution_risk",
        ])
    elif bucket == "semiconductor_equipment":
        warnings.extend([
            "ai_equipment_scarcity_requires_order_backlog_and_revision_validation",
            "WFE_peak_cycle_risk_must_not_be_ignored",
        ])
    base = {
        "has_bridge": False,
        "framework_type": framework_type,
        "framework_explanation": framework_explanation,
        "current_market_cap": market_cap,
        "current_enterprise_value": enterprise_value,
        "current_price": latest_price,
        "current_total_revenue": revenue,
        "current_ebitda": current_ebitda,
        "current_operating_margin": operating_margin,
        "latest_net_income": latest_net_income,
        "warnings": warnings,
        "scenarios": {},
    }
    if market_cap is None or latest_price is None:
        base["warnings"] = warnings + ["missing_market_cap_or_latest_price"]
        return base

    share_count = safe_div(market_cap, latest_price) if latest_price else None
    net_debt = bridge_net_debt(snapshot, market_cap, enterprise_value)
    scenarios: Dict[str, Any] = {}
    pe_inputs = {
        "memory": {
            "bear": {"revenue_change": -0.25, "normalized_net_margin": 0.18, "pe_multiple": 8},
            "base": {"revenue_change": 0.00, "normalized_net_margin": 0.30, "pe_multiple": 7},
            "bull": {"revenue_change": 0.25, "normalized_net_margin": 0.40, "pe_multiple": 8},
        },
        "compute_network": {
            "bear": {"revenue_change": -0.05, "normalized_net_margin": 0.18, "pe_multiple": 20},
            "base": {"revenue_change": 0.15, "normalized_net_margin": 0.25, "pe_multiple": 28},
            "bull": {"revenue_change": 0.30, "normalized_net_margin": 0.32, "pe_multiple": 35},
        },
        "other": {
            "bear": {"revenue_change": -0.10, "normalized_net_margin": 0.08, "pe_multiple": 12},
            "base": {"revenue_change": 0.05, "normalized_net_margin": 0.12, "pe_multiple": 16},
            "bull": {"revenue_change": 0.15, "normalized_net_margin": 0.16, "pe_multiple": 20},
        },
    }
    if bucket == "memory":
        if revenue is None:
            base["warnings"] = warnings + ["missing_revenue_for_revenue_based_bridge"]
            return base
        traditional_inputs = pe_inputs["memory"]
        structural_inputs = {
            "bear": {"revenue_change": -0.10, "normalized_net_margin": 0.28, "pe_multiple": 10},
            "base": {"revenue_change": 0.15, "normalized_net_margin": 0.38, "pe_multiple": 12},
            "bull": {"revenue_change": 0.35, "normalized_net_margin": 0.45, "pe_multiple": 14},
        }
        traditional_scenarios = build_pe_valuation_scenarios(revenue, market_cap, latest_price, share_count, traditional_inputs)
        structural_scenarios = build_pe_valuation_scenarios(revenue, market_cap, latest_price, share_count, structural_inputs)
        base.update({
            "has_bridge": True,
            "primary_framework": "traditional_memory_cycle",
            "secondary_framework": "structural_hbm_scarcity",
            "frameworks": {
                "traditional_memory_cycle": {
                    "framework_type": "traditional_memory_cycle",
                    "framework_explanation": "Traditional memory-cycle normalized earnings framework. This is the downside discipline anchor.",
                    "scenarios": traditional_scenarios,
                },
                "structural_hbm_scarcity": {
                    "framework_type": "structural_hbm_scarcity",
                    "framework_explanation": "Structural HBM scarcity re-rating framework. This requires primary validation of durable HBM scarcity, long-term customer commitments, and technology lead.",
                    "scenarios": structural_scenarios,
                },
            },
            "scenarios": traditional_scenarios,
            "warnings": warnings,
        })
        return base

    if bucket == "power_thermal":
        using_proxy = current_ebitda is None
        if using_proxy and revenue is None:
            base["warnings"] = warnings + ["missing_ebitda_or_revenue_for_ev_ebitda_bridge"]
            return base
        power_warnings = list(warnings)
        if using_proxy:
            power_warnings.append("ebitda_missing_using_operating_income_proxy")
        traditional_inputs = {
            "bear": {"ebitda_change": -0.10, "ev_ebitda_multiple": 12, "normalized_operating_margin": 0.12},
            "base": {"ebitda_change": 0.10, "ev_ebitda_multiple": 16, "normalized_operating_margin": 0.16},
            "bull": {"ebitda_change": 0.25, "ev_ebitda_multiple": 20, "normalized_operating_margin": 0.20},
        }
        scarcity_inputs = {
            "bear": {"ebitda_change": 0.00, "ev_ebitda_multiple": 16, "normalized_operating_margin": 0.16},
            "base": {"ebitda_change": 0.20, "ev_ebitda_multiple": 22, "normalized_operating_margin": 0.20},
            "bull": {"ebitda_change": 0.35, "ev_ebitda_multiple": 26, "normalized_operating_margin": 0.22},
        }
        traditional_scenarios = build_ev_ebitda_valuation_scenarios(
            revenue, current_ebitda, market_cap, latest_price, share_count, net_debt, traditional_inputs
        )
        scarcity_scenarios = build_ev_ebitda_valuation_scenarios(
            revenue, current_ebitda, market_cap, latest_price, share_count, net_debt, scarcity_inputs
        )
        base.update({
            "has_bridge": True,
            "primary_framework": "traditional_electrical_equipment",
            "secondary_framework": "ai_data_center_power_scarcity",
            "frameworks": {
                "traditional_electrical_equipment": {
                    "framework_type": "traditional_electrical_equipment",
                    "framework_explanation": "Traditional electrical equipment EV/EBITDA cycle framework. This is the downside discipline anchor.",
                    "scenarios": traditional_scenarios,
                },
                "ai_data_center_power_scarcity": {
                    "framework_type": "ai_data_center_power_scarcity",
                    "framework_explanation": "AI data center power scarcity EV/EBITDA framework. This requires primary validation of backlog, margin durability, and order visibility.",
                    "scenarios": scarcity_scenarios,
                },
            },
            "scenarios": traditional_scenarios,
            "warnings": power_warnings,
        })
        return base

    if bucket == "semiconductor_equipment":
        using_proxy = current_ebitda is None
        if using_proxy and revenue is None:
            base["warnings"] = warnings + ["missing_ebitda_or_revenue_for_ev_ebitda_bridge"]
            return base
        semi_warnings = list(warnings)
        if using_proxy:
            semi_warnings.append("ebitda_missing_using_operating_income_proxy")
        traditional_inputs = {
            "bear": {"ebitda_change": -0.20, "ev_ebitda_multiple": 10, "normalized_operating_margin": 0.18},
            "base": {"ebitda_change": 0.05, "ev_ebitda_multiple": 14, "normalized_operating_margin": 0.22},
            "bull": {"ebitda_change": 0.20, "ev_ebitda_multiple": 18, "normalized_operating_margin": 0.26},
        }
        scarcity_inputs = {
            "bear": {"ebitda_change": -0.05, "ev_ebitda_multiple": 14, "normalized_operating_margin": 0.20},
            "base": {"ebitda_change": 0.15, "ev_ebitda_multiple": 20, "normalized_operating_margin": 0.25},
            "bull": {"ebitda_change": 0.30, "ev_ebitda_multiple": 24, "normalized_operating_margin": 0.30},
        }
        traditional_scenarios = build_ev_ebitda_valuation_scenarios(
            revenue, current_ebitda, market_cap, latest_price, share_count, net_debt, traditional_inputs
        )
        scarcity_scenarios = build_ev_ebitda_valuation_scenarios(
            revenue, current_ebitda, market_cap, latest_price, share_count, net_debt, scarcity_inputs
        )
        base.update({
            "has_bridge": True,
            "primary_framework": "traditional_wfe_cycle",
            "secondary_framework": "ai_equipment_scarcity_quality",
            "frameworks": {
                "traditional_wfe_cycle": {
                    "framework_type": "traditional_wfe_cycle",
                    "framework_explanation": "Traditional wafer fab equipment cycle EV/EBITDA framework. This is the cyclical downside anchor.",
                    "scenarios": traditional_scenarios,
                },
                "ai_equipment_scarcity_quality": {
                    "framework_type": "ai_equipment_scarcity_quality",
                    "framework_explanation": "AI equipment scarcity / quality EV/EBITDA framework. This requires order backlog, revision, and margin validation.",
                    "scenarios": scarcity_scenarios,
                },
            },
            "scenarios": traditional_scenarios,
            "warnings": semi_warnings,
        })
        return base

    if bucket in {"compute_network", "other"}:
        if revenue is None:
            base["warnings"] = warnings + ["missing_revenue_for_revenue_based_bridge"]
            return base
        scenarios = build_pe_valuation_scenarios(revenue, market_cap, latest_price, share_count, pe_inputs.get(bucket, pe_inputs["other"]))
    elif bucket == "optical":
        if revenue is None:
            base["warnings"] = warnings + ["missing_revenue_for_revenue_based_bridge"]
            return base
        ev_sales_inputs = {
            "bear": {"revenue_change": -0.15, "normalized_operating_margin": 0.08, "ev_sales_multiple": 2.0},
            "base": {"revenue_change": 0.10, "normalized_operating_margin": 0.15, "ev_sales_multiple": 3.5},
            "bull": {"revenue_change": 0.30, "normalized_operating_margin": 0.22, "ev_sales_multiple": 5.0},
        }
        for case, params in ev_sales_inputs.items():
            scenario_revenue = revenue * (1 + params["revenue_change"])
            scenario_ev = scenario_revenue * params["ev_sales_multiple"]
            scenario_equity_value = scenario_ev - net_debt
            scenario_price = safe_div(scenario_equity_value, share_count) if share_count else None
            scenarios[case] = {
                **params,
                "normalized_margin": params["normalized_operating_margin"],
                "multiple": params["ev_sales_multiple"],
                "scenario_revenue": safe_float(scenario_revenue),
                "scenario_ev": safe_float(scenario_ev),
                "scenario_equity_value": safe_float(scenario_equity_value),
                "scenario_price": scenario_price,
                "upside_downside": safe_div(scenario_price - latest_price, latest_price) if scenario_price is not None and latest_price else safe_div(scenario_equity_value - market_cap, market_cap),
            }
    elif bucket == "packaging":
        ev_ebitda_inputs = {
            "packaging": {
                "bear": {"revenue_change": -0.15, "normalized_operating_margin": 0.12, "ev_ebitda_multiple": 8},
                "base": {"revenue_change": 0.05, "normalized_operating_margin": 0.18, "ev_ebitda_multiple": 11},
                "bull": {"revenue_change": 0.20, "normalized_operating_margin": 0.24, "ev_ebitda_multiple": 14},
            },
        }
        using_proxy = current_ebitda is None
        if using_proxy and revenue is None:
            base["warnings"] = warnings + ["missing_ebitda_or_revenue_for_ev_ebitda_bridge"]
            return base
        if using_proxy:
            warnings.append("ebitda_missing_using_operating_income_proxy")
        for case, params in ev_ebitda_inputs[bucket].items():
            scenario_revenue = revenue * (1 + params.get("revenue_change", 0.0)) if revenue is not None else None
            if current_ebitda is not None:
                scenario_ebitda = current_ebitda * (1 + params.get("ebitda_change", params.get("revenue_change", 0.0)))
            else:
                scenario_ebitda = (scenario_revenue or revenue or 0) * params["normalized_operating_margin"]
            scenario_ev = scenario_ebitda * params["ev_ebitda_multiple"]
            scenario_equity_value = scenario_ev - net_debt
            scenario_price = safe_div(scenario_equity_value, share_count) if share_count else None
            scenarios[case] = {
                **params,
                "normalized_margin": params.get("normalized_operating_margin"),
                "multiple": params["ev_ebitda_multiple"],
                "scenario_revenue": safe_float(scenario_revenue),
                "scenario_ebitda": safe_float(scenario_ebitda),
                "scenario_ev": safe_float(scenario_ev),
                "scenario_equity_value": safe_float(scenario_equity_value),
                "scenario_price": scenario_price,
                "upside_downside": safe_div(scenario_price - latest_price, latest_price) if scenario_price is not None and latest_price else safe_div(scenario_equity_value - market_cap, market_cap),
            }

    base.update({"has_bridge": True, "warnings": warnings, "scenarios": scenarios})
    return base


def build_simple_valuation_bridge(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return build_industry_valuation_bridge(snapshot, theme="")


def valuation_scenario_table_lines(scenarios: Dict[str, Any]) -> List[str]:
    lines = [
        "| Scenario | Revenue Change | EBITDA Change | Normalized Margin | Multiple | Scenario Revenue | Scenario EBITDA | Net Income | EV | Equity Value | Scenario Price | Upside/Downside |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for case in ["bear", "base", "bull"]:
        s = scenarios.get(case) or {}
        multiple = s.get("multiple") or s.get("pe_multiple") or s.get("ev_sales_multiple") or s.get("ev_ebitda_multiple")
        lines.append(
            f"| {case} | {format_pct(s.get('revenue_change'))} | {format_pct(s.get('ebitda_change'))} | "
            f"{format_pct(s.get('normalized_margin'))} | {multiple or 'N/A'} | "
            f"{format_num(s.get('scenario_revenue'))} | {format_num(s.get('scenario_ebitda'))} | "
            f"{format_num(s.get('scenario_net_income'))} | {format_num(s.get('scenario_ev'))} | "
            f"{format_num(s.get('scenario_equity_value'))} | {format_num(s.get('scenario_price'))} | "
            f"{format_pct(s.get('upside_downside'))} |"
        )
    return lines


def valuation_bridge_to_markdown(valuation_bridge: Dict[str, Any]) -> str:
    lines = [
        "## Valuation Bridge",
        "",
        f"- Framework type: {valuation_bridge.get('framework_type') or 'N/A'}",
        f"- Framework explanation: {valuation_bridge.get('framework_explanation') or 'N/A'}",
        f"- Has bridge: {valuation_bridge.get('has_bridge')}",
        f"- Warnings: {', '.join(valuation_bridge.get('warnings') or []) or 'None'}",
        f"- Current market cap: {format_num(valuation_bridge.get('current_market_cap'))}",
        f"- Current enterprise value: {format_num(valuation_bridge.get('current_enterprise_value'))}",
        f"- Current price: {valuation_bridge.get('current_price') or 'N/A'}",
        f"- Current total revenue: {format_num(valuation_bridge.get('current_total_revenue'))}",
        f"- Current EBITDA: {format_num(valuation_bridge.get('current_ebitda'))}",
        f"- Current operating margin: {format_pct(valuation_bridge.get('current_operating_margin'))}",
        f"- Latest net income: {format_num(valuation_bridge.get('latest_net_income'))}",
        "",
        "These are industry-specific discipline scenarios, not forecasts.",
        "",
    ]
    scenarios = valuation_bridge.get("scenarios") or {}
    frameworks = valuation_bridge.get("frameworks") or {}
    if frameworks:
        framework_titles = {
            "traditional_memory_cycle": "Traditional Memory Cycle Bridge",
            "structural_hbm_scarcity": "Structural HBM Scarcity Bridge",
            "traditional_electrical_equipment": "Traditional Electrical Equipment Bridge",
            "ai_data_center_power_scarcity": "AI Data Center Power Scarcity Bridge",
            "traditional_wfe_cycle": "Traditional WFE Cycle Bridge",
            "ai_equipment_scarcity_quality": "AI Equipment Scarcity / Quality Bridge",
        }
        ordered_names = [
            "traditional_memory_cycle",
            "structural_hbm_scarcity",
            "traditional_electrical_equipment",
            "ai_data_center_power_scarcity",
            "traditional_wfe_cycle",
            "ai_equipment_scarcity_quality",
        ]
        rendered = set()
        for framework_name in ordered_names:
            framework = frameworks.get(framework_name)
            if not framework:
                continue
            rendered.add(framework_name)
            lines.extend(["", f"### {framework_titles.get(framework_name, framework_name.replace('_', ' ').title())}", ""])
            lines.append(framework.get("framework_explanation") or f"{framework_name} framework.")
            lines.append("")
            lines.extend(valuation_scenario_table_lines(framework.get("scenarios") or {}))
        for framework_name, framework in frameworks.items():
            if framework_name in rendered:
                continue
            lines.extend(["", f"### {framework_name.replace('_', ' ').title()}", ""])
            lines.append(framework.get("framework_explanation") or f"{framework_name} framework.")
            lines.append("")
            lines.extend(valuation_scenario_table_lines(framework.get("scenarios") or {}))
        lines.extend([
            "",
            "### Interpretation",
            "",
            "- Traditional/cycle bridge is the conservative anchor.",
            "- Scarcity/quality bridge is the upside or re-rating framework and requires stronger evidence.",
            "- If both imply downside, valuation is stretched even under structural improvement.",
            "- If scarcity bridge supports current price but traditional bridge does not, conclusion should be: good company, high sensitivity to durability of scarcity assumptions.",
        ])
    elif scenarios:
        lines.extend(valuation_scenario_table_lines(scenarios))
    return "\n".join(lines)


def build_quality_report(
    ticker: str,
    company_name: str,
    evidence_quality: Dict[str, Any],
    data_warnings: List[str],
    price_sanity: Dict[str, Any],
    valuation_bridge: Dict[str, Any],
    decision: Dict[str, Any],
) -> str:
    usability = "Suitable for deeper review, but still requires manual verification."
    if price_sanity.get("manual_price_verification_required"):
        usability = "Not suitable for valuation or buy/sell decision until price and market-cap data are manually verified."
    elif price_sanity.get("valuation_reliability") == "low":
        usability = "Not suitable for valuation decision because valuation reliability is low."
    elif safe_float(evidence_quality.get("evidence_quality_score")) is not None and safe_float(evidence_quality.get("evidence_quality_score")) < 7:
        usability = "Not suitable for final investment decision. Suitable for preliminary screening only."
    elif not valuation_bridge.get("has_bridge"):
        usability = "Not suitable for buy/sell decision because valuation bridge is missing."

    lines = [
        f"# Quality Report: {company_name} / {ticker}",
        "",
        "## Data Fetch Reliability",
        "",
        f"- Market data reliability: {decision.get('market_data_reliability') or 'N/A'}",
        f"- Financial statement reliability: {decision.get('financial_statement_reliability') or 'N/A'}",
        f"- Price data reliability from fetch: {decision.get('price_data_reliability_from_fetch') or 'N/A'}",
        f"- Data fetch warnings: {', '.join(decision.get('data_fetch_warnings') or []) or 'None'}",
        "",
        "## Fetch Diagnostics Summary",
        "",
    ]
    fetch_summary = decision.get("fetch_diagnostics_summary") or {}
    for label, key in [("market", "market"), ("evidence", "evidence"), ("llm", "llm")]:
        summary = fetch_summary.get(key) or {}
        lines.extend([
            f"- {label}_fetch_total: {summary.get('total', 0)}",
            f"- {label}_fetch_failed: {summary.get('failed', 0)}",
            f"- {label}_fetch_empty: {summary.get('empty', 0)}",
            f"- {label}_fetch_rate_limited: {summary.get('rate_limited', 0)}",
        ])
    lines.extend([
        "",
        "## Evidence Quality",
        "",
        f"- Score: {evidence_quality.get('evidence_quality_score')}",
        f"- primary_regulatory_count: {evidence_quality.get('primary_regulatory_count')}",
        f"- primary_company_count: {evidence_quality.get('primary_company_count')}",
        f"- transcript_secondary_count: {evidence_quality.get('transcript_secondary_count')}",
        f"- industry_data_count: {evidence_quality.get('industry_data_count')}",
        f"- secondary_news_count: {evidence_quality.get('secondary_news_count')}",
        f"- weak_source_count: {evidence_quality.get('weak_source_count')}",
        "",
        "## Official Source Search",
        "",
    ])
    official = evidence_quality.get("official_source_search") or {}
    lines.extend([
        f"- official_source_search_enabled: {official.get('official_source_search_enabled')}",
        f"- official_queries_run: {official.get('official_queries_run')}",
        f"- official_primary_hits: {official.get('official_primary_hits')}",
        f"- official_regulatory_hits: {official.get('official_regulatory_hits')}",
        f"- official_company_hits: {official.get('official_company_hits')}",
        f"- official_search_warnings: {', '.join(official.get('official_search_warnings') or []) or 'None'}",
        "",
        "## Evidence Search Diagnostics Summary",
        "",
    ])
    evidence_diag = evidence_quality.get("evidence_search_diagnostics") or {}
    lines.extend([
        f"- evidence_search_provider: {evidence_diag.get('evidence_search_provider')}",
        f"- evidence_search_query_count: {evidence_diag.get('evidence_search_query_count')}",
        f"- evidence_search_failed_count: {evidence_diag.get('evidence_search_failed_count')}",
        f"- evidence_search_empty_count: {evidence_diag.get('evidence_search_empty_count')}",
        f"- evidence_search_rate_limited_count: {evidence_diag.get('evidence_search_rate_limited_count')}",
    ])
    if (evidence_quality.get("primary_company_count") or 0) == 0 and (evidence_quality.get("primary_regulatory_count") or 0) == 0:
        lines.extend([
            "",
            "Official-source search failed to retrieve primary evidence. Do not treat this as absence of primary evidence; treat it as a search coverage failure requiring manual follow-up.",
        ])
    lines.extend([
        "",
        "## Evidence Warnings",
        "",
    ])
    ev_warnings = evidence_quality.get("evidence_warnings") or []
    lines.extend([f"- {w}" for w in ev_warnings] or ["- None"])
    lines.extend(["", "## Data Quality Warnings", ""])
    lines.extend([f"- {w}" for w in data_warnings] or ["- No major data quality warnings."])
    lines.extend(["", price_sanity_to_markdown(price_sanity)])
    lines.extend([
        "",
        "## Valuation Framework",
        "",
        f"- Framework type: {valuation_bridge.get('framework_type') or 'N/A'}",
        f"- Explanation: {valuation_bridge.get('framework_explanation') or 'N/A'}",
        f"- Has bridge: {valuation_bridge.get('has_bridge')}",
        f"- Warnings: {', '.join(valuation_bridge.get('warnings') or []) or 'None'}",
        "",
        valuation_bridge_to_markdown(valuation_bridge),
        "",
        "## Serenity-style Chokepoint Analysis",
        "",
        f"- chokepoint_score: {decision.get('chokepoint_score')}",
        f"- chokepoint_adjusted_score: {decision.get('chokepoint_adjusted_score')}",
        f"- weighted_investment_score: {decision.get('weighted_investment_score')}",
        f"- weighted_score_interpretation: {decision.get('weighted_score_interpretation') or 'N/A'}",
        f"- indispensability_score: {decision.get('indispensability_score')}",
        f"- scarcity_score: {decision.get('scarcity_score')}",
        f"- customer_validation_score: {decision.get('customer_validation_score')}",
        f"- nvidia_signal_score: {decision.get('nvidia_signal_score')}",
        f"- substitution_risk_score: {decision.get('substitution_risk_score')}",
        f"- timing_risk_score: {decision.get('timing_risk_score')}",
        f"- market_awareness_score: {decision.get('market_awareness_score')}",
        f"- valuation_risk_score: {decision.get('valuation_risk_score')}",
        f"- serenity_thesis_quality: {decision.get('serenity_thesis_quality') or 'N/A'}",
        f"- evidence_level: {decision.get('chokepoint_evidence_level') or 'N/A'}",
        f"- deep_research_priority: {decision.get('deep_research_priority') or 'N/A'}",
        f"- scout_recommendation: {decision.get('scout_recommendation') or 'N/A'}",
        f"- overlay_applied: {decision.get('chokepoint_overlay_applied')}",
        f"- overlay_reason: {decision.get('chokepoint_overlay_reason') or 'N/A'}",
        f"- overlay_warnings: {', '.join(decision.get('chokepoint_overlay_warnings') or []) or 'None'}",
        f"- interpretation: {decision.get('chokepoint_interpretation') or 'N/A'}",
        "",
        "### Chokepoint Usability",
        "",
    ])
    cp_adjusted = safe_float(decision.get("chokepoint_adjusted_score"))
    cp_evidence = str(decision.get("chokepoint_evidence_level") or "")
    if cp_adjusted is not None and cp_adjusted >= 7.5 and cp_evidence in {"hypothesis_only", "insufficient"}:
        lines.append("High-interest chokepoint candidate, but not suitable for investment decision without stronger evidence.")
    elif (safe_float(decision.get("market_awareness_score")) or 0) >= 8 and (safe_float(decision.get("valuation_risk_score")) or 0) >= 8:
        lines.append("Potential chokepoint, but valuation may already price in scarcity.")
    elif cp_adjusted is not None and cp_adjusted <= 4:
        lines.append("Low chokepoint relevance.")
    elif cp_adjusted is None:
        lines.append("Chokepoint Scout was not run.")
    else:
        lines.append("Chokepoint Scout is usable as research input, subject to evidence, valuation, and guardrails.")
    lines.extend([
        "",
        "## PM Guardrails",
        "",
    ])
    lines.extend([
        f"- Rating: {decision.get('rating')}",
        f"- Action: {decision.get('action')}",
        f"- Suggested position: {decision.get('suggested_position_pct')}",
        f"- Pre-guardrail position: {decision.get('pre_guardrail_position_pct')}",
        f"- Max allowed position: {decision.get('max_allowed_position_pct')}",
        f"- Guardrail warnings: {', '.join(decision.get('guardrail_warnings') or []) or 'None'}",
        "",
        "## Final Usability",
        "",
        usability,
    ])
    return "\n".join(lines)


def build_peer_discovery_queries(name: str, ticker: str, theme: str, market: str) -> List[str]:
    return [
        f"{name} {ticker} publicly traded competitors {theme} stock ticker",
        f"{name} direct competitors electrical equipment enclosures liquid cooling data center ticker",
        f"{theme} AI infrastructure publicly traded companies competitors ticker",
        f"{name} competitors Yahoo Finance ticker {market}",
    ]


def build_peer_discovery_prompt(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    search_results: List[Dict[str, str]],
    max_peers: int,
) -> str:
    return f"""
Target company:
- Ticker: {ticker}
- Name: {name}
- Theme: {theme}
- Market: {market}

Web search results:
```json
{json.dumps(search_results, ensure_ascii=False, indent=2)[:18000]}
```

Find up to {max_peers} publicly listed comparable companies from the search results.

Rules:
- Return only valid JSON.
- Use Yahoo Finance-compatible tickers whenever possible, including exchange suffixes for non-US listings, e.g. 300308.SZ, 6869.HK, SU.PA.
- Exclude ETFs, private companies, suppliers that are not comparable, customers, and the target company itself.
- Prefer direct competitors or same profit-pool companies; second preference is same AI infrastructure supply-chain layer.
- Assign peer_type conservatively:
  - direct_competitor: sells materially similar products into the same profit pool.
  - same_profit_pool: competes for the same customer budget but with broader/different product scope.
  - adjacent_supplier: upstream/downstream supplier exposed to the same buildout but not a close comp.
  - infrastructure_services: contractor/integrator/service company rather than equipment/product vendor.
  - weak_comparable: useful context only, not a valuation comp.
- Every candidate must have at least one source URL from the supplied search results.
- If evidence is weak, include fewer candidates.

JSON schema:
{{
  "peers": [
    {{
      "ticker": "...",
      "name": "...",
      "theme": "{theme}",
      "market": "...",
      "peer_type": "direct_competitor|same_profit_pool|adjacent_supplier|infrastructure_services|weak_comparable",
      "profit_pool": "...",
      "reason": "...",
      "source_urls": ["..."],
      "confidence": 1
    }}
  ]
}}
"""


VALID_PEER_TYPES = {
    "direct_competitor",
    "same_profit_pool",
    "adjacent_supplier",
    "infrastructure_services",
    "weak_comparable",
}


def infer_peer_type(target_theme: str, peer_theme: str, reason: str = "") -> str:
    target_bucket = theme_bucket(target_theme)
    peer_bucket = theme_bucket(peer_theme)
    target_overlap = len(theme_tokens(target_theme).intersection(theme_tokens(peer_theme)))
    text = f"{peer_theme} {reason}".lower()

    if any(k in text for k in ["contractor", "construction", "engineering", "installation", "services"]):
        return "infrastructure_services"
    if target_bucket == peer_bucket and target_overlap >= 2:
        return "direct_competitor"
    if target_bucket == peer_bucket:
        return "same_profit_pool"
    if target_bucket != "other" and peer_bucket != "other":
        return "adjacent_supplier"
    return "weak_comparable"


def normalize_peer_type(ticker: Any, target_theme: str, peer_theme: str, reason: str = "", peer_type: str = "") -> str:
    ticker_norm = normalize_ticker(ticker)
    if ticker_norm in PEER_TYPE_ALIASES:
        return PEER_TYPE_ALIASES[ticker_norm]
    if peer_type in VALID_PEER_TYPES:
        return peer_type
    return infer_peer_type(target_theme, peer_theme, reason)


def infer_profit_pool(theme: str, reason: str = "") -> str:
    text = f"{theme} {reason}".lower()
    if any(k in text for k in ["liquid", "cooling", "thermal", "hvac"]):
        return "data_center_thermal"
    if any(k in text for k in ["power", "electrical", "switchgear", "ups", "pdu", "enclosure", "grid"]):
        return "data_center_power_electrical"
    if any(k in text for k in ["connector", "interconnect", "cable", "fiber", "optical"]):
        return "data_center_interconnect"
    if any(k in text for k in ["construction", "engineering", "contractor", "installation"]):
        return "data_center_infrastructure_services"
    if any(k in text for k in ["hbm", "dram", "nand", "memory", "ssd"]):
        return "memory_storage"
    return theme_bucket(theme)


def normalize_profit_pool(ticker: Any, theme: str, reason: str = "", profit_pool: str = "") -> str:
    ticker_norm = normalize_ticker(ticker)
    if ticker_norm in PROFIT_POOL_ALIASES:
        return PROFIT_POOL_ALIASES[ticker_norm]
    return str(profit_pool or "").strip() or infer_profit_pool(theme, reason)


def validate_discovered_peer(candidate: Dict[str, Any], fallback_theme: str) -> Optional[Dict[str, Any]]:
    ticker = str(candidate.get("ticker", "")).strip()
    if not ticker:
        return None
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}

    quote_type = str(info.get("quoteType") or "").upper()
    candidate_name = str(candidate.get("name") or "").strip()
    short_name = candidate_name or info.get("longName") or info.get("shortName")
    if quote_type and quote_type not in {"EQUITY", "ADR"}:
        return None
    if not short_name and not info.get("marketCap"):
        return None
    market = str(candidate.get("market") or info.get("country") or info.get("exchange") or "").strip()
    if is_disallowed_market(ticker, market):
        return None

    peer_theme = str(candidate.get("theme") or fallback_theme).strip()
    reason = str(candidate.get("reason") or "").strip()
    peer_type = str(candidate.get("peer_type") or "").strip()
    peer_type = normalize_peer_type(ticker, fallback_theme, peer_theme, reason, peer_type)
    profit_pool = normalize_profit_pool(ticker, peer_theme, reason, str(candidate.get("profit_pool") or ""))

    return {
        "ticker": ticker,
        "name": clean_company_name(ticker, short_name, info),
        "theme": peer_theme,
        "market": market,
        "peer_type": peer_type,
        "profit_pool": profit_pool,
        "discovery_reason": str(candidate.get("reason") or "").strip(),
        "source_urls": candidate.get("source_urls") or [],
        "discovery_confidence": candidate.get("confidence"),
    }


def discover_peer_rows(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    watchlist_path: str,
    max_peers: int = 5,
) -> List[Dict[str, Any]]:
    if max_peers <= 0 or not WEB_DISCOVERY_ENABLED:
        return []

    provider = active_search_provider()
    if not provider:
        console.print("[yellow]No web search API key found. Set TAVILY_API_KEY, BRAVE_SEARCH_API_KEY, BING_SEARCH_API_KEY, or SERPAPI_API_KEY for web peer discovery. To force one provider, set WEB_SEARCH_PROVIDER=tavily|brave|bing|serpapi.[/yellow]")
        return []

    max_results = int(os.getenv("WEB_DISCOVERY_MAX_RESULTS", "8"))
    search_results: List[Dict[str, str]] = []
    seen_urls = set()
    for query in build_peer_discovery_queries(name, ticker, theme, market):
        for result in web_search(query, max_results=max_results):
            url = result.get("url", "")
            if url and url in seen_urls:
                continue
            result["query"] = query
            search_results.append(result)
            if url:
                seen_urls.add(url)

    if not search_results:
        return []

    prompt = build_peer_discovery_prompt(ticker, name, theme, market, search_results, max_peers)
    try:
        raw = call_llm(
            "Peer Discovery Agent",
            prompt,
            max_tokens=int(os.getenv("PEER_DISCOVERY_MAX_TOKENS", "2500")),
            decorate=False,
            json_mode=True,
        )
        debug_dir = Path("outputs") / today_str()
        ensure_dir(debug_dir)
        debug_base = f"{ticker.replace('.', '_').replace('/', '_')}_peer_discovery_{now_str()}"
        save_text(debug_dir / f"{debug_base}_prompt.md", prompt)
        save_text(debug_dir / f"{debug_base}_raw.txt", raw)
        payload = repair_json_object(
            raw,
            schema_hint='{"peers":[{"ticker":"...","name":"...","theme":"...","market":"...","peer_type":"direct_competitor","profit_pool":"...","reason":"...","source_urls":["..."],"confidence":1}]}',
        )
    except Exception as e:
        console.print(f"[yellow]Peer discovery extraction failed: {e}[/yellow]")
        return []

    discovered: List[Dict[str, Any]] = []
    seen = {canonical_ticker_for(ticker)}
    for candidate in payload.get("peers", [])[: max_peers * 2]:
        validated = validate_discovered_peer(candidate, fallback_theme=theme)
        if not validated:
            continue
        norm = canonical_ticker_for(validated.get("ticker"))
        if not norm or norm in seen:
            continue
        validated["group_role"] = "peer"
        discovered.append(validated)
        seen.add(norm)
        if len(discovered) >= max_peers:
            break

    if discovered:
        upsert_watchlist_rows(watchlist_path, discovered)
    return discovered


def select_peer_rows(ticker: str, theme: str, watchlist_path: str, max_peers: int = 5) -> List[Dict[str, Any]]:
    df = read_watchlist_df(watchlist_path)
    if df.empty:
        return []

    if df.empty or "ticker" not in df.columns or "theme" not in df.columns:
        return []

    current = normalize_ticker(ticker)
    current_canonical = canonical_ticker_for(ticker)
    target_tokens = theme_tokens(theme)
    target_bucket = theme_bucket(theme)
    scored: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        row_ticker = normalize_ticker(row.get("ticker", ""))
        if not row_ticker or row_ticker == current:
            continue
        if is_disallowed_market(row.get("ticker"), row.get("market")):
            continue
        if canonical_ticker_for(row_ticker) == current_canonical:
            continue
        row_theme = str(row.get("theme", ""))
        row_tokens = theme_tokens(row_theme)
        score = len(target_tokens.intersection(row_tokens))
        if row_theme.lower() == theme.lower():
            score += 3
        if theme_bucket(row_theme) == target_bucket and target_bucket != "other":
            score += 2
        if score > 0:
            if canonical_ticker_for(row_ticker) == row_ticker:
                score += 0.5
            peer_type = str(row.get("peer_type", "")).strip() if "peer_type" in df.columns else ""
            profit_pool = str(row.get("profit_pool", "")).strip() if "profit_pool" in df.columns else ""
            peer_type = normalize_peer_type(row_ticker, theme, row_theme, peer_type=peer_type)
            profit_pool = normalize_profit_pool(row_ticker, row_theme, profit_pool=profit_pool)
            scored.append({
                "ticker": str(row.get("ticker", "")),
                "name": clean_company_name(row.get("ticker"), row.get("name")),
                "theme": row_theme,
                "market": str(row.get("market", "")),
                "peer_type": peer_type,
                "profit_pool": profit_pool,
                "score": score,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    deduped: List[Dict[str, Any]] = []
    seen_canonicals = set()
    for row in scored:
        canonical = canonical_ticker_for(row.get("ticker"))
        if canonical in seen_canonicals:
            continue
        deduped.append(row)
        seen_canonicals.add(canonical)
        if len(deduped) >= max_peers:
            break
    return deduped


def get_peer_metric(ticker: str, name: str, theme: str, market: str) -> Dict[str, Any]:
    financial_ticker = financial_ticker_for(ticker)
    row: Dict[str, Any] = {
        "ticker": ticker,
        "financial_ticker": financial_ticker,
        "name": clean_company_name(ticker, name),
        "theme": theme,
        "market": market,
    }
    try:
        t = yf.Ticker(ticker)
        try:
            info, info_source_ticker, cross_currency_risk = get_best_financial_info(ticker)
        except Exception:
            info = {}
            info_source_ticker = financial_ticker
            cross_currency_risk = False

        try:
            hist = t.history(period="2y", auto_adjust=True)
            close = hist["Close"].dropna()
            one_year_return = return_over_trading_days(close, 252)
        except Exception:
            one_year_return = None

        market_cap = safe_float(info.get("marketCap"))
        enterprise_value = safe_float(info.get("enterpriseValue"))
        total_revenue = safe_float(info.get("totalRevenue"))
        ebitda = safe_float(info.get("ebitda"))
        free_cashflow = safe_float(info.get("freeCashflow"))
        row.update({
            "name": clean_company_name(ticker, row.get("name"), info),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "currency": info.get("currency"),
            "financial_currency": info.get("financialCurrency"),
            "uses_financial_ticker_alias": financial_ticker != ticker,
            "financial_info_source_ticker": info_source_ticker,
            "cross_currency_valuation_risk": cross_currency_risk,
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "trailing_pe": safe_float(info.get("trailingPE")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "price_to_sales": safe_float(info.get("priceToSalesTrailing12Months")),
            "price_to_book": safe_float(info.get("priceToBook")),
            "ev_to_revenue": safe_div(enterprise_value, total_revenue),
            "ev_to_ebitda": safe_div(enterprise_value, ebitda),
            "revenue_growth": safe_float(info.get("revenueGrowth")),
            "gross_margin": safe_float(info.get("grossMargins")),
            "operating_margin": safe_float(info.get("operatingMargins")),
            "fcf_yield": safe_div(free_cashflow, market_cap),
            "one_year_return": one_year_return,
        })
        if cross_currency_risk:
            suppress_cross_currency_valuation(row)
    except Exception as e:
        row["error"] = str(e)
    return row


def get_peer_metric_from_snapshot(row: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    ticker = str(row.get("ticker") or snapshot.get("ticker") or "").strip()
    name = clean_company_name(
        ticker,
        row.get("company_name") or row.get("name") or snapshot.get("long_name") or snapshot.get("short_name"),
        snapshot,
    )
    return {
        "ticker": ticker,
        "financial_ticker": snapshot.get("financial_ticker") or financial_ticker_for(ticker),
        "financial_info_source_ticker": snapshot.get("financial_info_source_ticker"),
        "name": name,
        "theme": row.get("theme") or "",
        "market": row.get("market") or snapshot.get("country") or "",
        "sector": snapshot.get("sector"),
        "industry": snapshot.get("industry"),
        "uses_financial_ticker_alias": snapshot.get("uses_financial_ticker_alias"),
        "cross_currency_valuation_risk": snapshot.get("cross_currency_valuation_risk"),
        "market_cap": snapshot.get("market_cap"),
        "enterprise_value": snapshot.get("enterprise_value"),
        "trailing_pe": snapshot.get("trailing_pe"),
        "forward_pe": snapshot.get("forward_pe"),
        "price_to_sales": snapshot.get("price_to_sales"),
        "price_to_book": snapshot.get("price_to_book"),
        "ev_to_revenue": snapshot.get("ev_to_revenue"),
        "ev_to_ebitda": snapshot.get("ev_to_ebitda"),
        "revenue_growth": snapshot.get("revenue_growth"),
        "gross_margin": snapshot.get("gross_margin"),
        "operating_margin": snapshot.get("operating_margin"),
        "fcf_yield": snapshot.get("fcf_yield"),
        "one_year_return": snapshot.get("one_year_return"),
    }


def median_metric(rows: List[Dict[str, Any]], key: str, exclude_ticker: Optional[str] = None) -> Optional[float]:
    values = []
    for row in rows:
        if exclude_ticker and str(row.get("ticker", "")).upper() == exclude_ticker.upper():
            continue
        v = row.get(key)
        if isinstance(v, (int, float)) and not np.isnan(v):
            values.append(float(v))
    if not values:
        return None
    return safe_float(pd.Series(values).median())


def filter_peers_for_valuation(peer_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        row for row in peer_rows
        if str(row.get("peer_type") or "").strip() in {"direct_competitor", "same_profit_pool"}
    ]


def peer_metric_table_lines(rows: List[Dict[str, Any]]) -> List[str]:
    lines = [
        "| Ticker | Financial Ticker | Company | Peer Type | Profit Pool | Theme | Market Cap | Fwd P/E | P/S | EV/Revenue | EV/EBITDA | Revenue Growth | Op Margin | FCF Yield | 1Y Return |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if not rows:
        lines.append("| N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |")
        return lines
    for row in rows:
        warning = " currency-mismatch" if row.get("cross_currency_valuation_risk") else ""
        lines.append(
            f"| {row.get('ticker')}{warning} | {row.get('financial_info_source_ticker') or row.get('financial_ticker') or row.get('ticker')} | {row.get('name')} | "
            f"{row.get('peer_type') or 'N/A'} | {row.get('profit_pool') or 'N/A'} | {row.get('theme')} | "
            f"{format_num(row.get('market_cap'))} | "
            f"{row.get('forward_pe') or 'N/A'} | "
            f"{row.get('price_to_sales') or 'N/A'} | "
            f"{row.get('ev_to_revenue') or 'N/A'} | "
            f"{row.get('ev_to_ebitda') or 'N/A'} | "
            f"{format_pct(row.get('revenue_growth'))} | "
            f"{format_pct(row.get('operating_margin'))} | "
            f"{format_pct(row.get('fcf_yield'))} | "
            f"{format_pct(row.get('one_year_return'))} |"
        )
    return lines


def render_peer_context(
    current_ticker: str,
    metric_rows: List[Dict[str, Any]],
    peer_meta: Dict[str, Dict[str, Any]],
    selection_basis: str,
) -> str:
    enriched_rows: List[Dict[str, Any]] = []
    for row in metric_rows:
        meta = peer_meta.get(normalize_ticker(row.get("ticker")), {})
        enriched = dict(row)
        enriched["peer_type"] = meta.get("peer_type") or "unknown"
        enriched["profit_pool"] = meta.get("profit_pool") or "N/A"
        enriched_rows.append(enriched)

    current_norm = normalize_ticker(current_ticker)
    target_rows = [
        row for row in enriched_rows
        if str(row.get("peer_type") or "").strip() == "target" or normalize_ticker(row.get("ticker")) == current_norm
    ]
    valuation_rows = [
        row for row in filter_peers_for_valuation(enriched_rows)
        if normalize_ticker(row.get("ticker")) != current_norm
    ]
    context_rows = [
        row for row in enriched_rows
        if row not in target_rows and row not in valuation_rows
    ]
    peer_ps = median_metric(valuation_rows, "price_to_sales")
    peer_ev_revenue = median_metric(valuation_rows, "ev_to_revenue")
    current = target_rows[0] if target_rows else (enriched_rows[0] if enriched_rows else {})
    no_true_peers = not valuation_rows
    lines = [
        "## Peer Valuation Context",
        "",
        f"Peer selection basis: {selection_basis}.",
        "",
        "Peer filter rule: only direct_competitor and same_profit_pool are used for valuation medians. weak_comparable, adjacent_supplier, customer, supplier, infrastructure_context, and unknown are context only.",
        "",
        "### Target",
        "",
    ]
    lines.extend(peer_metric_table_lines(target_rows))
    lines.extend([
        "",
        "### True Valuation Peers",
        "",
    ])
    lines.extend(peer_metric_table_lines(valuation_rows))
    lines.extend([
        "",
        "### Context-only Peers",
        "",
    ])
    lines.extend(peer_metric_table_lines(context_rows))
    lines.extend([
        "",
        "## Relative Valuation Flags",
        "",
        f"- Current P/S vs true peer median: {current.get('price_to_sales') or 'N/A'} vs {peer_ps or 'N/A'}",
        f"- Current EV/Revenue vs true peer median: {current.get('ev_to_revenue') or 'N/A'} vs {peer_ev_revenue or 'N/A'}",
        f"- Current FCF yield: {format_pct(current.get('fcf_yield'))}",
        "",
    ])
    if no_true_peers:
        lines.append("- Warning: No true valuation peers available; relative valuation is context-only.")
    return "\n".join(lines)


def build_peer_context_from_rows(
    current_ticker: str,
    rows: List[Dict[str, Any]],
    selection_basis: str,
) -> str:
    current_canonical = canonical_ticker_for(current_ticker)
    ordered = sorted(
        rows,
        key=lambda r: 0 if canonical_ticker_for(r.get("ticker")) == current_canonical else 1,
    )

    metric_rows: List[Dict[str, Any]] = []
    peer_meta: Dict[str, Dict[str, Any]] = {}
    seen = set()
    for row in ordered:
        row_ticker = str(row.get("ticker") or "").strip()
        norm = canonical_ticker_for(row_ticker)
        if not row_ticker or not norm or norm in seen:
            continue
        row_theme = str(row.get("theme") or "")
        reason = str(row.get("discovery_reason") or "")
        peer_type = str(row.get("peer_type") or "").strip()
        if peer_type != "target":
            peer_type = normalize_peer_type(row_ticker, str(rows[0].get("theme") or row_theme), row_theme, reason, peer_type)
        profit_pool = normalize_profit_pool(row_ticker, row_theme, reason, str(row.get("profit_pool") or ""))
        peer_meta[normalize_ticker(row_ticker)] = {
            "peer_type": peer_type or "unknown",
            "profit_pool": profit_pool,
        }
        snapshot = load_market_snapshot_for_row(row)
        if snapshot:
            metric_rows.append(get_peer_metric_from_snapshot(row, snapshot))
        else:
            metric_rows.append(get_peer_metric(
                row_ticker,
                clean_company_name(row_ticker, row.get("company_name") or row.get("name")),
                row_theme,
                str(row.get("market") or ""),
            ))
        seen.add(norm)

    return render_peer_context(current_ticker, metric_rows, peer_meta, selection_basis)


def build_peer_context(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    watchlist_path: str,
) -> str:
    max_peers = int(os.getenv("MAX_PEERS", "5"))
    selected = select_peer_rows(ticker, theme, watchlist_path, max_peers=max_peers)
    rows = [{
        "ticker": ticker,
        "name": name,
        "theme": theme,
        "market": market,
        "peer_type": "target",
        "profit_pool": infer_profit_pool(theme),
    }]
    rows.extend(selected)
    return build_peer_context_from_rows(
        ticker,
        rows,
        selection_basis=f"watchlist names with overlapping theme/bucket. Max peers: {max_peers}",
    )


def build_pm_prompt(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    snapshot_md: str,
    data_quality_md: str,
    data_fetch_md: str,
    price_sanity_md: str,
    macro_md: str,
    peer_md: str,
    evidence_md: str,
    evidence_quality: Dict[str, Any],
    cached_facts_md: str,
    chokepoint_context_md: str,
    chokepoint_decision: Dict[str, Any],
    valuation_bridge_md: str,
    ai_agent_framework: str,
) -> str:
    memory_valuation_instruction = ""
    if "memory_dual_framework" in valuation_bridge_md:
        memory_valuation_instruction = """
Memory / HBM valuation instruction:
This is a memory / HBM company. You must evaluate valuation using two frameworks:
1. Traditional Memory Cycle Framework:
- Treat current profitability as potentially cyclical.
- Focus on normalized margins and historical memory cycle multiples.
- This is the downside discipline anchor.
2. Structural HBM Scarcity Framework:
- Allow for structurally higher margins and multiples if HBM scarcity, long-term customer commitments, and technology lead are durable.
- This requires stronger evidence.
- It cannot be assumed from secondary news alone.

Your memo must explicitly answer:
- Does the current price require the structural HBM framework to be true?
- What primary evidence is required to justify the structural framework?
- What would make the stock attractive under the traditional framework?
- What would break the structural HBM scarcity thesis?

Do not conclude "overvalued" solely because traditional memory-cycle bridge shows downside.
Do not conclude "cheap" solely because forward PE is low.
Compare both frameworks.
"""
    power_valuation_instruction = ""
    if "power_thermal_dual_framework" in valuation_bridge_md:
        power_valuation_instruction = """
Power / thermal valuation instruction:
This is a data center power, thermal, or electrical infrastructure company. You must evaluate valuation using two frameworks:
1. Traditional Electrical Equipment Framework:
- Treat current profitability and orders as potentially cyclical.
- Focus on normalized EBITDA and traditional electrical equipment multiples.
- This is the downside discipline anchor.
2. AI Data Center Power Scarcity Framework:
- Allow for higher multiples only if backlog, margin durability, and order visibility support a scarcity premium.
- This requires stronger primary evidence from filings, official IR, or management commentary.

Your memo must explicitly answer:
- Does current price require AI power scarcity framework to be true?
- What primary evidence supports backlog, margin durability, and order visibility?
- What would make the stock attractive under traditional framework?
- What would break the AI data center power scarcity thesis?

Do not conclude overvalued solely because traditional electrical equipment framework shows downside. Compare with AI data center power scarcity framework. Explain what backlog, margin, and order evidence would justify scarcity multiple.
"""
    semi_equipment_instruction = ""
    if "semiconductor_equipment_dual_framework" in valuation_bridge_md:
        semi_equipment_instruction = """
Semiconductor equipment valuation instruction:
Do not lump semi equipment into packaging/substrate. Compare traditional WFE cycle framework with AI equipment scarcity/quality framework.

Your memo must explicitly answer:
- Is this company a true AI equipment scarcity asset or just a WFE cycle beneficiary?
- Does current valuation require sustained AI capex and backlog?
- Are margins near cycle peak?
- What would make the traditional WFE framework too conservative?
- Does current price require AI capex acceleration and estimate revisions?
"""
    price_sanity_instruction = ""
    if "extreme_momentum_requires_manual_review_but_not_data_error" in price_sanity_md:
        price_sanity_instruction = """
Extreme momentum price-sanity instruction:
Extreme momentum requires extra caution, but do not automatically call it data error. Treat valuation as medium reliability and cap sizing.
"""
    return f"""
Research target:
- Ticker: {ticker}
- Company: {name}
- Theme: {theme}
- Market: {market}
- Report date: {dt.date.today().isoformat()}

Market data:
{snapshot_md}

Data quality warnings:
{data_quality_md}

Data fetch reliability:
{data_fetch_md}

Price sanity:
{price_sanity_md}

Evidence quality:
```json
{json.dumps(evidence_quality, ensure_ascii=False, indent=2)}
```

Macro context:
{macro_md}

Peer / relative valuation context:
{peer_md}

Evidence context:
{evidence_md}

Cached reusable facts:
{cached_facts_md}

Chokepoint Scout context:
{chokepoint_context_md}

Chokepoint Scout structured decision:
```json
{json.dumps(chokepoint_decision, ensure_ascii=False, indent=2)}
```

Valuation bridge:
{valuation_bridge_md}

{memory_valuation_instruction}
{power_valuation_instruction}
{semi_equipment_instruction}
{price_sanity_instruction}

AI agent structural-demand framework:
{ai_agent_framework}

Please produce a buy-side deep-dive investment memo in Chinese.

Required structure:
A. Executive summary: conclusion, rating, suggested position 0%-5%, and confidence.
B. Evidence inventory: what is supported by supplied data, what is missing, and what is only inference.
C. Business model and profit pool: where the company actually makes money.
D. AI-agent structural demand transmission: explain exactly how AI agent adoption could affect this company, through compute/network/memory/power/thermal/storage layers.
E. Customer, competitor, bargaining power, and pricing-power analysis. If not evidenced, label it as inference or data gap.
F. Financial quality: revenue, margin, FCF, balance sheet, cyclicality, and operating leverage.
G. Why valuation is high: decompose into growth expectations, scarcity premium, quality premium, estimate revisions, liquidity/momentum, and cyclical peak risk.
H. Relative valuation: compare with peers; explain whether premium/discount is justified.
I. Serenity-style Chokepoint Analysis:
- Supply-chain node
- Chokepoint score
- Adjusted chokepoint score if supplied
- Why it could matter
- Evidence supporting it
- Missing evidence
- Substitution risk
- Market awareness / priced-in risk
- Whether it affects final action
J. Bull case, base case, bear case: key assumptions and what must happen.
K. 12-month tracking indicators and thesis kill triggers.
L. Portfolio independence: no holdings are supplied; do not infer overlap, concentration risk, duplicated beta, or suitability from portfolio data.
M. Final PM judgment: buy / small starter / tracking / watchlist / avoid, with position size and what would make you add or cut.

Important:
- Do not invent data.
- Cite source URLs from Evidence context when relying on search-derived facts.
- Cached reusable facts are evidence leads from earlier searches. Use them to avoid duplicate research, but prefer fresher official sources when cached facts conflict with current evidence.
- Chokepoint Scout is discovery input, not final recommendation.
- A high chokepoint score can support tracking/starter only when evidence and valuation are acceptable.
- Chokepoint Scout cannot override price sanity, data reliability, evidence quality, valuation discipline, or PM guardrails.
- If chokepoint_score is high but evidence is weak, say: "High-priority research candidate, not investable yet."
- If chokepoint_score is high but market_awareness and valuation_risk are high, say: "Good bottleneck, likely already priced in."
- If substitution risk is high, challenge the chokepoint thesis.
- Tag important claims as [evidence], [inference], or [hypothesis].
- If Price Sanity Check says manual_price_verification_required = true, you must not present valuation bridge output as a reliable fair value. Do not recommend buy, starter_position, or increase. Final action must be manual price verification required or watchlist.
- If market data reliability is low, do not treat valuation multiples as final and explicitly say market data reliability is low.
- If financial statement reliability is low, do not make high-confidence margin, FCF, or balance sheet conclusions. State that financial tables were missing or failed.
- If price data reliability from fetch is low, do not make a buy/sell recommendation. Require manual price verification.
- If evidence search diagnostics show many failed or empty queries, state that evidence coverage is incomplete.
- If LLM diagnostics include retries or fallback, mention it only if output quality appears affected.
- If price_data_reliability or valuation_reliability is low, do not call the stock overvalued solely based on the valuation bridge. Phrase it as: "under the current data feed, valuation appears stretched, but price/market-cap data must be verified."
- If 1Y return > 300% and valuation bridge shows huge downside, say: "This may reflect true market repricing or data error; verify before interpreting downside."
- If evidence_quality_score < 7, clearly state: "Evidence quality is insufficient for a final investment decision."
- Distinguish primary evidence (company filing, official IR, transcript, press release) from secondary evidence (news, sell-side summary, industry commentary).
- Use the Evidence Tier labels exactly: only primary_regulatory and primary_company count as primary evidence. transcript_secondary, industry_data, and secondary_news are useful but lower confidence.
- Do not place aggregator/news snippets in the "official/primary evidence" bucket unless their Evidence Tier starts with primary_.
- Only these Source Type values can be labeled [evidence]: company_ir_or_official_news, regulatory_or_exchange_filing, earnings_transcript_secondary, industry_research, reputable_news.
- These Source Type values must not be labeled [evidence]: aggregator_or_social_or_reprint, web_search_lead, unknown, weak_source, social_or_video. Use [lead], [secondary lead], [hypothesis], or [inference] instead.
- If a claim is based on Perplexity, Yahoo Finance, Quartr, SahmCapital, AlphaSpread, Gurufocus, Investing.com, BigGo, 24/7 Wall St, or similar aggregators, label it [lead], not [evidence].
- If a claim is based on Reuters/Bloomberg/FT/WSJ/Barron's, it may be labeled [evidence, secondary_news], but must not be called primary evidence.
- The AI Agent Structural Demand Framework is not company-specific evidence. Any claim derived only from this framework must be labeled [hypothesis], not [evidence]. Do not cite it as proof of company revenue, orders, backlog, pricing power, or customer commitment.
- Label AI-agent demand as [evidence] only if official company filing / official call transcript / reliable customer capex / order data supports it.
- Do not give a buy recommendation above 2% if evidence_quality_score < 7.
- Use the industry-specific Valuation Bridge. Do not apply memory-cycle assumptions to non-memory companies. If you disagree with the framework or assumptions, revise them explicitly and show revenue, margin, earnings/EBITDA, multiple, equity value, scenario price, and upside/downside assumptions.
- The Valuation Bridge is a discipline framework, not a forecast.
- Do not output target prices without revenue, margin, earnings/EBITDA, multiple, equity value, scenario price, and upside/downside assumptions. If valuation_bridge.has_bridge is false, do not output fair value or target price.
- Do not use weak_comparable or context-only peers in peer median.
- Do not recommend mechanical price stop-loss as primary risk control. Use thesis review triggers instead. A price drawdown threshold can be included only as a review trigger, not an automatic sell rule.
- When valuation looks expensive, first explain the market's strongest argument before rejecting it.
- If news, customer, or order data is missing, say exactly what data is missing.
- Do not give a high-conviction recommendation when evidence quality is weak.
"""


def build_json_prompt(ticker: str, name: str, memo: str) -> str:
    memo_chars = int(os.getenv("STRUCTURED_JSON_MEMO_CHARS", "18000"))
    return f"""
Return only one valid JSON object. No markdown. No explanation.

Ticker: {ticker}
Company: {name}

Memo:
{memo[:memo_chars]}

Unit rules:
- Preserve local-currency price units exactly from the memo.
- Do not convert Chinese units such as 万韩元/万日元 into K/M abbreviations.
- Example: 150万韩元 means 1,500,000 KRW, not 150K KRW.
- If the memo gives a pullback or target price in local currency, keep it in the same order of magnitude as the latest price described in the memo.
- Do not recommend mechanical price stop-loss as primary risk control. If the memo contains "stop-loss", convert it to a price drawdown review threshold, not an automatic sell rule.

JSON schema:
{{
  "ticker": "{ticker}",
  "company_name": "{name}",
  "rating": "buy|small_start|tracking_watch|watch|avoid|cautious_watch",
  "action": "buy|starter_position|tracking_position|watchlist|hold_existing|trim_existing|avoid|trim|manual_price_verification_required",
  "suggested_position_pct": 0,
  "confidence_score": 1,
  "fundamental_quality_score": 1,
  "growth_visibility_score": 1,
  "valuation_attractiveness_score": 1,
  "ai_beneficiary_score": 1,
  "competitive_position_score": 1,
  "risk_score": 10,
  "evidence_quality_score": 1,
  "thesis_summary": "...",
  "ai_agent_demand_link": "...",
  "valuation_premium_reason": "...",
  "valuation_is_justified": false,
  "valuation_view": "...",
  "portfolio_fit": "...",
  "bull_case": "...",
  "base_case": "...",
  "bear_case": "...",
  "key_bull_points": ["..."],
  "key_bear_points": ["..."],
  "key_tracking_indicators": ["..."],
  "thesis_kill_triggers": ["..."],
  "data_gaps": ["..."],
  "deepest_questions": ["..."],
  "price_review_threshold_pct": null,
  "thesis_review_triggers": ["..."],
  "automatic_sell_rule": "none",
  "price_data_reliability": "high|medium|low",
  "valuation_reliability": "high|medium|low",
  "manual_price_verification_required": false,
  "price_sanity_warnings": ["..."],
  "price_verification_note": "...",
  "final_pm_judgment": "..."
}}

Action meaning:
- watchlist = 0%
- tracking_position = 0.5%-1%
- starter_position = 1%-2%
- buy = 2%-5%
- manual_price_verification_required = 0%
- avoid = 0%
"""


DECISION_REQUIRED_FIELDS = [
    "ticker",
    "company_name",
    "rating",
    "action",
    "suggested_position_pct",
    "confidence_score",
    "fundamental_quality_score",
    "growth_visibility_score",
    "valuation_attractiveness_score",
    "ai_beneficiary_score",
    "competitive_position_score",
    "risk_score",
    "evidence_quality_score",
    "thesis_summary",
    "ai_agent_demand_link",
    "valuation_premium_reason",
    "valuation_is_justified",
    "valuation_view",
    "portfolio_fit",
    "bull_case",
    "base_case",
    "bear_case",
    "key_bull_points",
    "key_bear_points",
    "key_tracking_indicators",
    "thesis_kill_triggers",
    "data_gaps",
    "deepest_questions",
    "final_pm_judgment",
]


DECISION_LIST_FIELDS = {
    "key_bull_points",
    "key_bear_points",
    "key_tracking_indicators",
    "thesis_kill_triggers",
    "data_gaps",
    "deepest_questions",
}


DECISION_SCORE_FIELDS = {
    "confidence_score",
    "fundamental_quality_score",
    "growth_visibility_score",
    "valuation_attractiveness_score",
    "ai_beneficiary_score",
    "competitive_position_score",
    "risk_score",
    "evidence_quality_score",
}


def decision_quality_issues(decision: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for field in DECISION_REQUIRED_FIELDS:
        value = decision.get(field)
        if value is None or value == "":
            issues.append(f"missing_or_empty:{field}")
        elif field in DECISION_LIST_FIELDS and (not isinstance(value, list) or not value):
            issues.append(f"missing_or_empty:{field}")

    if str(decision.get("thesis_summary", "")).lower().startswith("fallback decision"):
        issues.append("fallback_decision")
    if str(decision.get("ai_agent_demand_link", "")).lower().startswith("unavailable because structured output failed"):
        issues.append("fallback_decision")

    for field in DECISION_SCORE_FIELDS:
        value = decision.get(field)
        if not isinstance(value, (int, float)) or value < 1 or value > 10:
            issues.append(f"invalid_score:{field}")

    rating = decision.get("rating")
    if rating not in VALID_DECISION_RATINGS:
        issues.append("invalid_rating")

    action = decision.get("action")
    if action not in VALID_DECISION_ACTIONS:
        issues.append("invalid_action")

    if not isinstance(decision.get("valuation_is_justified"), bool):
        issues.append("invalid_boolean:valuation_is_justified")

    return sorted(set(issues))


def load_json_file(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_market_snapshot_for_row(row: Dict[str, Any]) -> Dict[str, Any]:
    output_dir = str(row.get("output_dir") or "")
    if not output_dir:
        return {}
    return load_json_file(Path(output_dir) / "market_snapshot.json")


def extract_case_target_prices(text: str) -> List[float]:
    prices: List[float] = []
    for match in re.finditer(r"(?:target|目标价|目标)[^0-9$]{0,40}\$?\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.IGNORECASE):
        value = safe_float(match.group(1))
        if value is not None:
            prices.append(value)
    return prices


def decision_text_blob(decision: Dict[str, Any]) -> str:
    fields = [
        "thesis_summary",
        "valuation_premium_reason",
        "valuation_view",
        "portfolio_fit",
        "bull_case",
        "base_case",
        "bear_case",
        "final_pm_judgment",
    ]
    parts = [str(decision.get(field) or "") for field in fields]
    for field in [
        "key_bull_points",
        "key_bear_points",
        "key_tracking_indicators",
        "thesis_kill_triggers",
        "data_gaps",
        "deepest_questions",
    ]:
        value = decision.get(field)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return " ".join(parts)


def has_local_price_unit_mismatch(decision: Dict[str, Any], latest_price: Optional[float]) -> bool:
    if latest_price is None or latest_price < 100_000:
        return False
    text = decision_text_blob(decision)
    # Common LLM compression error: "150-155万韩元" becomes "150-155K KRW",
    # which is an order-of-magnitude mistake for Korean large-cap share prices.
    krw_k_pattern = r"\b\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*K\s*(?:KRW|韩元|won)\b"
    return bool(re.search(krw_k_pattern, text, flags=re.IGNORECASE))


def warning_contains(warnings: List[str], text: str) -> bool:
    needle = text.lower()
    return any(needle in str(w).lower() for w in warnings)


def normalize_risk_language(decision: Dict[str, Any]) -> None:
    decision["automatic_sell_rule"] = "none"
    if "thesis_review_triggers" not in decision or not isinstance(decision.get("thesis_review_triggers"), list):
        triggers = decision.get("thesis_kill_triggers")
        decision["thesis_review_triggers"] = triggers if isinstance(triggers, list) else []
    text = decision_text_blob(decision).lower()
    if "stop-loss" in text or "stop loss" in text or "止损" in text:
        if decision.get("price_review_threshold_pct") is None:
            decision["price_review_threshold_pct"] = 0.15
        decision["thesis_review_triggers"].append("Price drawdown review threshold only; not an automatic sell rule.")


def valuation_bridge_summary(valuation_bridge: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "framework_type": valuation_bridge.get("framework_type"),
    }
    scenarios = valuation_bridge.get("scenarios") or {}
    if scenarios:
        summary["scenarios"] = {
            "bear": {"upside_downside": (scenarios.get("bear") or {}).get("upside_downside")},
            "base": {"upside_downside": (scenarios.get("base") or {}).get("upside_downside")},
            "bull": {"upside_downside": (scenarios.get("bull") or {}).get("upside_downside")},
        }
    frameworks = valuation_bridge.get("frameworks") or {}
    for framework_name in [
        "traditional_memory_cycle",
        "structural_hbm_scarcity",
        "traditional_electrical_equipment",
        "ai_data_center_power_scarcity",
        "traditional_wfe_cycle",
        "ai_equipment_scarcity_quality",
    ]:
        scenarios = (frameworks.get(framework_name) or {}).get("scenarios") or {}
        if scenarios:
            summary[framework_name] = {
                "bear_upside_downside": (scenarios.get("bear") or {}).get("upside_downside"),
                "base_upside_downside": (scenarios.get("base") or {}).get("upside_downside"),
                "bull_upside_downside": (scenarios.get("bull") or {}).get("upside_downside"),
            }
    return summary


def valuation_framework_interpretation(valuation_bridge: Dict[str, Any]) -> str:
    frameworks = valuation_bridge.get("frameworks") or {}
    framework_pairs = [
        ("traditional_memory_cycle", "structural_hbm_scarcity", "structural HBM scarcity"),
        ("traditional_electrical_equipment", "ai_data_center_power_scarcity", "AI data center power scarcity"),
        ("traditional_wfe_cycle", "ai_equipment_scarcity_quality", "AI equipment scarcity / quality"),
    ]
    traditional = {}
    structural = {}
    scarcity_label = "scarcity"
    for traditional_name, scarcity_name, label in framework_pairs:
        if frameworks.get(scarcity_name):
            traditional = (frameworks.get(traditional_name) or {}).get("scenarios") or {}
            structural = (frameworks.get(scarcity_name) or {}).get("scenarios") or {}
            scarcity_label = label
            break
    if not structural:
        return "Single valuation framework supplied; use scenario bridge as discipline, not as forecast."
    traditional_base = safe_float((traditional.get("base") or {}).get("upside_downside"))
    structural_base = safe_float((structural.get("base") or {}).get("upside_downside"))
    structural_bull = safe_float((structural.get("bull") or {}).get("upside_downside"))
    if structural_bull is not None and structural_bull < 0:
        return f"Even the {scarcity_label} framework does not support the current price."
    if structural_base is not None and structural_base >= 0 and (traditional_base is None or traditional_base < 0):
        return f"Current price requires {scarcity_label} assumptions to persist."
    if structural_base is not None and structural_base >= 0 and traditional_base is not None and traditional_base >= 0:
        return "Valuation appears supportable under both traditional and structural frameworks, subject to evidence quality."
    return f"{scarcity_label} upside case improves the bridge, but valuation remains sensitive to the durability of scarcity assumptions and primary evidence quality."


def build_guardrailed_decision_appendix(decision: Dict[str, Any]) -> str:
    lines = [
        "## Final Guardrailed PM Decision",
        "",
        "This section is code-generated after PM guardrails and overrides any earlier conflicting memo language on rating, action, or position size.",
        "",
        f"- Final rating: {decision.get('rating')}",
        f"- Final action: {decision.get('action')}",
        f"- Final suggested position: {decision.get('suggested_position_pct')}%",
        f"- Pre-guardrail suggested position: {decision.get('pre_guardrail_position_pct')}%",
        f"- Max allowed position: {decision.get('max_allowed_position_pct')}%",
        f"- Guardrail warnings: {', '.join(decision.get('guardrail_warnings') or []) or 'None'}",
        f"- Automatic sell rule: {decision.get('automatic_sell_rule') or 'none'}",
    ]
    if decision.get("weighted_investment_score") is not None or decision.get("chokepoint_adjusted_score") is not None:
        lines.extend([
            f"- Chokepoint adjusted score: {decision.get('chokepoint_adjusted_score')}",
            f"- Weighted investment score: {decision.get('weighted_investment_score')}",
            f"- Weighted score interpretation: {decision.get('weighted_score_interpretation') or 'N/A'}",
            f"- Chokepoint overlay: {decision.get('chokepoint_overlay_applied')} | {decision.get('chokepoint_overlay_reason') or 'N/A'}",
        ])
    interpretation = decision.get("valuation_framework_interpretation")
    if interpretation:
        lines.append(f"- Valuation framework interpretation: {interpretation}")
    if decision.get("manual_price_verification_required"):
        lines.append("- Price verification note: Do not use valuation output as buy/sell signal until price and market-cap data are independently verified.")
    return "\n".join(lines)


def apply_pm_guardrails(
    decision: Dict[str, Any],
    evidence_quality: Dict[str, Any],
    data_warnings: List[str],
    valuation_bridge: Dict[str, Any],
    price_sanity: Optional[Dict[str, Any]] = None,
    fetch_reliability: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    guarded = dict(decision)
    pre_position = safe_float(guarded.get("suggested_position_pct")) or 0.0
    max_allowed = 5.0
    guardrail_warnings: List[str] = []
    evidence_score = safe_float(evidence_quality.get("evidence_quality_score")) or 1
    evidence_warnings = evidence_quality.get("evidence_warnings") or []

    guarded["evidence_quality_score"] = int(evidence_score)

    if evidence_score < 7:
        max_allowed = min(max_allowed, 2.0)
        confidence = safe_float(guarded.get("confidence_score"))
        if confidence is not None:
            guarded["confidence_score"] = min(confidence, 6)
        guardrail_warnings.append("evidence_quality_below_7_caps_position_at_2pct")

    no_primary_sources = (
        "no_primary_regulatory_filing" in evidence_warnings
        and "no_official_company_ir_source" in evidence_warnings
    )
    if no_primary_sources:
        max_allowed = min(max_allowed, 1.0)
        guardrail_warnings.append("no_primary_sources_caps_position_at_1pct")

    if not valuation_bridge.get("has_bridge"):
        max_allowed = min(max_allowed, 1.0)
        guardrail_warnings.append("missing_valuation_bridge_caps_position_at_1pct")

    if any("1Y return exceeds 300%" in str(w) for w in data_warnings):
        max_allowed = min(max_allowed, 1.0)
        guardrail_warnings.append("extreme_1y_return_caps_position_at_1pct")

    if (
        warning_contains(data_warnings, "potential peak-cycle margin")
        and warning_contains(data_warnings, "fcf_yield is missing")
    ):
        max_allowed = min(max_allowed, 1.5)
        guardrail_warnings.append("peak_margin_missing_fcf_yield_caps_position_at_1_5pct")

    fetch_reliability = fetch_reliability or {}
    market_fetch_reliability = str(fetch_reliability.get("market_data_reliability") or "high")
    financial_fetch_reliability = str(fetch_reliability.get("financial_statement_reliability") or "high")
    price_fetch_reliability = str(fetch_reliability.get("price_data_reliability_from_fetch") or "high")
    data_fetch_warnings = fetch_reliability.get("data_fetch_warnings") or []

    if market_fetch_reliability == "low":
        max_allowed = min(max_allowed, 1.0)
        guardrail_warnings.append("low_market_data_reliability_caps_position_at_1pct")
    if financial_fetch_reliability == "low":
        max_allowed = min(max_allowed, 1.0)
        guardrail_warnings.append("low_financial_statement_reliability_caps_position_at_1pct")
        if str(guarded.get("action") or "") in {"buy", "increase", "starter_position"}:
            official = evidence_quality.get("official_source_search") or {}
            primary_hits = safe_float(official.get("official_primary_hits")) or 0
            if evidence_score < 8 or primary_hits < 2:
                guarded["action"] = "watchlist"
    if price_fetch_reliability == "low":
        max_allowed = 0.0
        guardrail_warnings.append("low_price_fetch_reliability_manual_verification_required")
    if "data_fetch_rate_limited" in data_fetch_warnings:
        max_allowed = min(max_allowed, 2.0)
        guardrail_warnings.append("rate_limited_data_fetch_caps_position_at_2pct")

    guarded["pre_guardrail_position_pct"] = pre_position
    guarded["max_allowed_position_pct"] = max_allowed
    guarded["suggested_position_pct"] = min(pre_position, max_allowed)
    guarded["guardrail_warnings"] = sorted(set((guarded.get("guardrail_warnings") or []) + guardrail_warnings))
    guarded["evidence_quality"] = evidence_quality
    guarded["data_quality_warnings"] = data_warnings
    guarded["valuation_bridge"] = valuation_bridge
    guarded["valuation_bridge_summary"] = valuation_bridge_summary(valuation_bridge)
    guarded["valuation_framework_interpretation"] = guarded.get("valuation_framework_interpretation") or valuation_framework_interpretation(valuation_bridge)
    guarded["market_data_reliability"] = market_fetch_reliability
    guarded["financial_statement_reliability"] = financial_fetch_reliability
    guarded["price_data_reliability_from_fetch"] = price_fetch_reliability
    guarded["data_fetch_warnings"] = data_fetch_warnings

    price_sanity = price_sanity or {
        "price_data_reliability": "high",
        "valuation_reliability": "high",
        "manual_price_verification_required": False,
        "price_sanity_warnings": [],
        "derived_metrics": {},
    }
    price_reliability = str(price_sanity.get("price_data_reliability") or "high")
    valuation_reliability = str(price_sanity.get("valuation_reliability") or "high")
    manual_price_verification = bool(price_sanity.get("manual_price_verification_required"))
    price_sanity_warnings = price_sanity.get("price_sanity_warnings") or []
    guarded["price_data_reliability"] = price_reliability
    guarded["valuation_reliability"] = valuation_reliability
    guarded["manual_price_verification_required"] = manual_price_verification
    guarded["price_sanity_warnings"] = price_sanity_warnings
    guarded["price_sanity"] = price_sanity

    if "extreme_momentum_requires_manual_review_but_not_data_error" in price_sanity_warnings:
        max_allowed = min(max_allowed, 1.0)
        guardrail_warnings.append("extreme_momentum_caps_position_at_1pct")
    if "extreme_momentum_with_incomplete_market_data_requires_price_verification" in price_sanity_warnings:
        manual_price_verification = True
        guarded["manual_price_verification_required"] = True
        guardrail_warnings.append("extreme_momentum_incomplete_data_manual_verification_required")
    if "strong_momentum_verify_price_source" in price_sanity_warnings:
        max_allowed = min(max_allowed, 2.0)
        guardrail_warnings.append("strong_momentum_caps_position_at_2pct")

    if price_reliability == "medium" and not manual_price_verification:
        max_allowed = min(max_allowed, 2.0)
        guardrail_warnings.append("medium_price_reliability_caps_position_at_2pct")
    if valuation_reliability == "medium":
        max_allowed = min(max_allowed, 2.0)
        guardrail_warnings.append("medium_valuation_reliability_caps_position_at_2pct")
    if valuation_reliability == "low":
        guardrail_warnings.append("low_valuation_reliability_no_buy_decision")
        if not manual_price_verification:
            guarded["action"] = "watchlist"
    if price_fetch_reliability == "low":
        manual_price_verification = True
        guarded["manual_price_verification_required"] = True
        guarded["price_verification_note"] = "Price/history fetch reliability is low. Valuation output should be treated as unreliable until manually verified."
    if manual_price_verification:
        max_allowed = 0.0
        guardrail_warnings.append("manual_price_verification_required_caps_position_at_0pct")
        guarded["price_verification_note"] = "Price or market-cap data triggered sanity warnings. Valuation output should be treated as unreliable until manually verified."

    normalize_risk_language(guarded)

    position = safe_float(guarded.get("suggested_position_pct")) or 0
    original_action = str(decision.get("action") or "")
    guarded["max_allowed_position_pct"] = max_allowed
    guarded["suggested_position_pct"] = min(pre_position, max_allowed)
    guarded["guardrail_warnings"] = sorted(set((guarded.get("guardrail_warnings") or []) + guardrail_warnings))
    position = safe_float(guarded.get("suggested_position_pct")) or 0
    if manual_price_verification:
        guarded["rating"] = "watch"
        guarded["action"] = "manual_price_verification_required"
        guarded["final_pm_judgment"] = (
            str(guarded.get("final_pm_judgment") or "").strip()
            + " Do not use valuation output as buy/sell signal until price and market-cap data are independently verified."
        ).strip()
    elif position <= 0:
        guarded["rating"] = "watch"
        guarded["action"] = "watchlist"
    elif max_allowed <= 1.0:
        guarded["rating"] = "cautious_watch"
        guarded["action"] = "watchlist"
    elif max_allowed <= 2.0 and original_action in {"buy", "increase", "starter_position"}:
        guarded["rating"] = "small_start"
        guarded["action"] = "starter_position"

    return guarded


def decision_quality_warnings(
    decision: Dict[str, Any],
    market_snapshot: Optional[Dict[str, Any]] = None,
) -> List[str]:
    warnings: List[str] = []
    rating = str(decision.get("rating") or "")
    action = str(decision.get("action") or "")
    position = safe_float(decision.get("suggested_position_pct")) or 0
    confidence = safe_float(decision.get("confidence_score"))
    evidence = safe_float(decision.get("evidence_quality_score"))
    risk = safe_float(decision.get("risk_score"))
    valuation_score = safe_float(decision.get("valuation_attractiveness_score"))

    if evidence is not None and evidence <= 3 and rating in {"buy", "small_start"}:
        warnings.append("low_evidence_positive_rating")
    if evidence is not None and evidence <= 3 and position > 0:
        warnings.append("low_evidence_nonzero_position")
    if confidence is not None and confidence <= 3 and position > 0:
        warnings.append("low_confidence_nonzero_position")
    if decision.get("valuation_is_justified") is False and rating == "buy":
        warnings.append("buy_rating_despite_unjustified_valuation")
    if decision.get("valuation_is_justified") is False and action in {"buy", "starter_position", "tracking_position"} and valuation_score is not None and valuation_score <= 3:
        warnings.append("positive_action_with_weak_valuation")
    if risk is not None and risk >= 8 and position > 2:
        warnings.append("high_risk_position_above_2pct")
    if risk is not None and risk >= 8 and rating == "buy":
        warnings.append("buy_rating_with_high_risk_score")

    market_snapshot = market_snapshot or {}
    latest_price = safe_float(market_snapshot.get("latest_price"))
    one_year_return = safe_float(market_snapshot.get("one_year_return"))
    if one_year_return is not None and abs(one_year_return) >= 3:
        warnings.append("extreme_1y_return_requires_price_verification")
    if has_local_price_unit_mismatch(decision, latest_price):
        warnings.append("possible_local_price_unit_mismatch")

    case_text = " ".join(str(decision.get(k) or "") for k in ["bull_case", "base_case", "bear_case"])
    targets = extract_case_target_prices(case_text)
    if latest_price and targets and max(targets) <= latest_price * 1.10 and position > 0:
        warnings.append("limited_bull_case_upside_for_nonzero_position")

    return sorted(set(warnings))


def repair_decision_schema(
    decision: Dict[str, Any],
    ticker: str,
    name: str,
    memo: str,
    diagnostics: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    issues = decision_quality_issues(decision)
    if not issues:
        return decision

    repair_prompt = f"""
The structured investment decision JSON below is incomplete or invalid.
Repair it using only the memo as source material. Return one valid JSON object.

Rules:
- Fill every required schema field.
- Do not invent unsupported facts.
- If the memo does not support a field, write an explicit data-gap statement inside that field.
- Preserve ticker and company_name.

Detected quality issues:
{json.dumps(issues, ensure_ascii=False, indent=2)}

Current JSON:
{json.dumps(decision, ensure_ascii=False, indent=2)}

Memo:
{memo[:16000]}

Required fields:
{json.dumps(DECISION_REQUIRED_FIELDS, ensure_ascii=False, indent=2)}
"""
    repaired_raw = call_llm(
        "Decision Schema Repair Agent",
        repair_prompt,
        max_tokens=int(os.getenv("STRUCTURED_JSON_REPAIR_MAX_TOKENS", "5000")),
        decorate=False,
        json_mode=True,
        diagnostics=diagnostics,
    )
    repaired = repair_json_object(
        repaired_raw,
        schema_hint="Complete investment decision JSON object with every required field.",
        diagnostics=diagnostics,
    )
    repaired["ticker"] = ticker
    repaired["company_name"] = name

    remaining = decision_quality_issues(repaired)
    if remaining:
        raise ValueError("Incomplete decision JSON after repair: " + ", ".join(remaining))
    return repaired


def build_comparative_ranking_prompt(
    target_ticker: str,
    theme: str,
    peer_context_md: str,
    rows: List[Dict[str, Any]],
) -> str:
    decision_payload = []
    for row in rows:
        decision = row.get("decision") or {}
        market_snapshot = load_market_snapshot_for_row(row)
        decision_payload.append({
            "ticker": row.get("ticker"),
            "company_name": row.get("company_name"),
            "theme": row.get("theme"),
            "market": row.get("market"),
            "group_role": row.get("analysis_group_role"),
            "peer_type": row.get("peer_type"),
            "profit_pool": row.get("profit_pool"),
            "discovery_reason": row.get("discovery_reason"),
            "discovery_confidence": row.get("discovery_confidence"),
            "rating": decision.get("rating"),
            "action": decision.get("action"),
            "suggested_position_pct": decision.get("suggested_position_pct"),
            "confidence_score": decision.get("confidence_score"),
            "fundamental_quality_score": decision.get("fundamental_quality_score"),
            "growth_visibility_score": decision.get("growth_visibility_score"),
            "valuation_attractiveness_score": decision.get("valuation_attractiveness_score"),
            "ai_beneficiary_score": decision.get("ai_beneficiary_score"),
            "competitive_position_score": decision.get("competitive_position_score"),
            "risk_score": decision.get("risk_score"),
            "evidence_quality_score": decision.get("evidence_quality_score"),
            "thesis_summary": decision.get("thesis_summary"),
            "ai_agent_demand_link": decision.get("ai_agent_demand_link"),
            "valuation_view": decision.get("valuation_view"),
            "valuation_is_justified": decision.get("valuation_is_justified"),
            "portfolio_fit": decision.get("portfolio_fit"),
            "bull_case": decision.get("bull_case"),
            "base_case": decision.get("base_case"),
            "bear_case": decision.get("bear_case"),
            "key_bull_points": decision.get("key_bull_points"),
            "key_bear_points": decision.get("key_bear_points"),
            "key_tracking_indicators": decision.get("key_tracking_indicators"),
            "thesis_kill_triggers": decision.get("thesis_kill_triggers"),
            "data_gaps": decision.get("data_gaps"),
            "final_pm_judgment": decision.get("final_pm_judgment"),
            "decision_quality_issues": decision_quality_issues(decision),
            "decision_quality_warnings": decision_quality_warnings(decision, market_snapshot),
            "output_dir": row.get("output_dir"),
        })

    return f"""
Target ticker: {target_ticker}
Theme: {theme}

Peer valuation context:
{peer_context_md}

Company-level structured decisions:
```json
{json.dumps(decision_payload, ensure_ascii=False, indent=2)}
```

Please produce a Chinese comparative investment ranking across these companies.

Required structure:
A. Ranking table from best to worst.
B. For each rank: ticker, company, rating, suggested position, key reason, biggest risk, evidence quality.
C. Best risk/reward name and why.
D. Names to avoid despite AI exposure and why.
E. Portfolio implementation: maximum combined exposure to this sub-theme, suggested sizing per name, and what to monitor.

Important:
- Compare companies against each other, not in isolation.
- If a company has non-empty decision_quality_issues, mark it as "needs rerun / unreliable structured output"; do not treat fallback or incomplete JSON as a valid negative investment conclusion.
- State clearly when the comparative ranking is provisional because one or more companies need rerun.
- Use decision_quality_warnings to adjust rank and sizing. A warning is not an automatic rejection, but it must be discussed.
- Preserve local-currency price units. Do not convert 万韩元/万日元 into K/M abbreviations; 150万韩元 is 1,500,000 KRW, not 150K KRW.
- Penalize weak peer_type. direct_competitor and same_profit_pool are valuation comps; adjacent_supplier and infrastructure_services are only context unless explicitly justified.
- Penalize weak evidence, extreme valuation, negative FCF, customer concentration, and duplicated portfolio exposure.
- Do not reward AI exposure unless it is paired with financial quality and reasonable valuation.
"""


def extract_json_object(text: str) -> Dict[str, Any]:
    first = text.find("{")
    last = text.rfind("}")
    if first < 0 or last <= first:
        raise ValueError("No JSON object found.")
    return json.loads(text[first:last + 1])


def repair_json_object(
    text: str,
    schema_hint: str = "Return only one valid JSON object.",
    diagnostics: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    try:
        return extract_json_object(text)
    except Exception:
        pass

    repair_prompt = f"""
The following text was intended to be JSON but is invalid.
Repair it into one valid JSON object. Do not add markdown or explanation.

Schema hint:
{schema_hint}

Invalid JSON-like text:
{text[:12000]}
"""
    repaired = call_llm(
        "JSON Repair Agent",
        repair_prompt,
        max_tokens=int(os.getenv("JSON_REPAIR_MAX_TOKENS", "2500")),
        decorate=False,
        json_mode=True,
        diagnostics=diagnostics,
    )
    return extract_json_object(repaired)


CHOKEPOINT_SCORE_FIELDS = [
    "chokepoint_score",
    "indispensability_score",
    "scarcity_score",
    "customer_validation_score",
    "nvidia_signal_score",
    "substitution_risk_score",
    "timing_risk_score",
    "market_awareness_score",
    "valuation_risk_score",
]


def clip_score(value: Any, default: Optional[int] = 1) -> Optional[int]:
    numeric = safe_float(value)
    if numeric is None:
        return default
    return int(max(1, min(10, round(numeric))))


def clip_float_score(value: Any, default: Optional[float] = None) -> Optional[float]:
    numeric = safe_float(value)
    if numeric is None:
        return default
    return safe_float(max(1.0, min(10.0, numeric)))


def build_chokepoint_scout_prompt(
    ticker: str,
    company_name: str,
    theme: str,
    market: str,
    snapshot_md: str,
    evidence_context: str,
    peer_context: str,
    valuation_bridge_md: str,
    ai_agent_framework_md: str,
) -> str:
    return f"""
You are running a Serenity-style Chokepoint Scout for AI infrastructure investing.

Objective:
Evaluate whether this company is a true AI supply-chain chokepoint. Chokepoint Scout is a radar, not the final PM. It can identify high-priority research candidates, but it cannot create a buy decision by itself.

Target:
- Ticker: {ticker}
- Company: {company_name}
- Theme: {theme}
- Market: {market}

Market snapshot:
{snapshot_md}

Evidence context:
{evidence_context}

Peer context:
{peer_context}

Valuation bridge:
{valuation_bridge_md}

AI agent framework:
{ai_agent_framework_md}

Required analysis:
1. Supply-chain node
- What exact node does the company control?
- Is it material, component, equipment, manufacturing service, test, packaging, optical, power, thermal, memory, storage, or network infrastructure?

2. Demand transmission chain
- How does AI capex transmit to this company?
- Example: NVIDIA / hyperscaler capex -> GPU / ASIC / HBM / CoWoS / optical I/O / power / thermal / storage -> this company's product/service.

3. Indispensability
- Is the node technically necessary?
- Is the company a qualified supplier?
- Is it one of many suppliers or a real bottleneck?
- Can customers dual-source?
- Can the technology route bypass this node?

4. Scarcity mechanism
- Capacity shortage, qualification bottleneck, yield/reliability barrier, customer certification, IP/material/process know-how, long lead time, supply concentration.

5. Customer validation
- Is there official evidence of lead customer, order, design win, qualification, shipment, backlog, or long-term agreement?
- If evidence comes only from secondary sources, label it [lead], not [evidence].

6. Ecosystem signal
- Is there a signal from NVIDIA, Broadcom, Marvell, hyperscaler, foundry, OSAT, module maker, or cloud capex?
- Is this a real signal or market narrative?

7. Substitution risk
- Can the supplier be replaced?
- Can customers redesign around it?
- Is it temporary shortage or durable bottleneck?

8. Timing risk
- Is it already revenue?
- Is it sampling/qualification?
- Is it dependent on 2027+ adoption?

9. Market awareness
- Is the market already fully aware?
- Is it already priced like a scarcity asset?
- Is it ignored because it is obscure or ignored for good reason?

10. Valuation discipline
- Does current price require the scarcity thesis to be true?
- Is the chokepoint already priced in?

Required labels:
- [evidence]
- [inference]
- [hypothesis]
- [lead]

Evidence rule:
Only primary_company, primary_regulatory, transcript_secondary, industry_data, and reputable_news can be labeled [evidence].
Aggregator/social/reprint sources must be labeled [lead] or [secondary lead].
AI Agent Demand Framework is analytical context only and must be labeled [hypothesis] if used alone.

Output a concise markdown report with this structure:
## Serenity-style Chokepoint Analysis
- Supply-chain node
- Demand transmission chain
- Indispensability
- Scarcity mechanism
- Customer validation
- Ecosystem signal
- Substitution risk
- Timing risk
- Market awareness / priced-in risk
- Valuation discipline
- Scout conclusion
"""


def build_chokepoint_json_prompt(
    ticker: str,
    company_name: str,
    theme: str,
    market: str,
    chokepoint_context: str,
) -> str:
    return f"""
Return only one valid JSON object. No markdown. No explanation.

Ticker: {ticker}
Company: {company_name}
Theme: {theme}
Market: {market}

Chokepoint context:
{chokepoint_context[:18000]}

JSON schema:
{{
  "ticker": "{ticker}",
  "company_name": "{company_name}",
  "theme": "{theme}",
  "market": "{market}",
  "chokepoint_summary": "...",
  "supply_chain_node": "...",
  "supply_chain_position": "...",
  "demand_transmission_chain": ["..."],
  "chokepoint_score": 1,
  "indispensability_score": 1,
  "scarcity_score": 1,
  "customer_validation_score": 1,
  "nvidia_signal_score": 1,
  "substitution_risk_score": 1,
  "timing_risk_score": 1,
  "market_awareness_score": 1,
  "valuation_risk_score": 1,
  "serenity_thesis_quality": "high_quality_chokepoint|interesting_unproven|narrative_heavy|weak_replaceable|already_priced_in",
  "evidence_level": "primary_supported|secondary_supported|hypothesis_only|insufficient",
  "deep_research_priority": "high|medium|low",
  "key_supporting_evidence": ["..."],
  "key_missing_evidence": ["..."],
  "substitution_risks": ["..."],
  "timing_risks": ["..."],
  "valuation_concerns": ["..."],
  "what_would_confirm_thesis": ["..."],
  "what_would_break_thesis": ["..."],
  "scout_recommendation": "deep_research|watch_only|reject|monitor_for_evidence",
  "scout_note": "..."
}}

Rules:
- Scores must be integers 1-10.
- scout_recommendation must never be buy, increase, starter_position, or tracking_position.
- If customer evidence is only secondary or inferred, evidence_level cannot be primary_supported.
- If the chokepoint is already priced in, use serenity_thesis_quality = already_priced_in.
"""


def fallback_chokepoint_decision(
    ticker: str,
    company_name: str,
    theme: str,
    market: str,
    error: str = "",
    not_run: bool = False,
) -> Dict[str, Any]:
    if not_run:
        scores = {field: None for field in CHOKEPOINT_SCORE_FIELDS}
        return {
            "ticker": ticker,
            "company_name": company_name,
            "theme": theme,
            "market": market,
            "chokepoint_summary": "Chokepoint Scout was not run.",
            "supply_chain_node": "not_run",
            "supply_chain_position": "not_run",
            "demand_transmission_chain": [],
            **scores,
            "serenity_thesis_quality": "interesting_unproven",
            "evidence_level": "insufficient",
            "deep_research_priority": "low",
            "key_supporting_evidence": [],
            "key_missing_evidence": ["Chokepoint Scout disabled."],
            "substitution_risks": [],
            "timing_risks": [],
            "valuation_concerns": [],
            "what_would_confirm_thesis": [],
            "what_would_break_thesis": [],
            "scout_recommendation": "not_run",
            "scout_note": "Chokepoint Scout disabled by CLI or environment.",
        }
    return {
        "ticker": ticker,
        "company_name": company_name,
        "theme": theme,
        "market": market,
        "chokepoint_summary": "Fallback chokepoint decision. Chokepoint Scout output was not reliable.",
        "supply_chain_node": "unknown",
        "supply_chain_position": "unknown",
        "demand_transmission_chain": [],
        "chokepoint_score": 1,
        "indispensability_score": 1,
        "scarcity_score": 1,
        "customer_validation_score": 1,
        "nvidia_signal_score": 1,
        "substitution_risk_score": 10,
        "timing_risk_score": 10,
        "market_awareness_score": 10,
        "valuation_risk_score": 10,
        "serenity_thesis_quality": "interesting_unproven",
        "evidence_level": "insufficient",
        "deep_research_priority": "low",
        "key_supporting_evidence": [],
        "key_missing_evidence": ["Chokepoint Scout failed.", error],
        "substitution_risks": ["Unknown due to scout failure."],
        "timing_risks": ["Unknown due to scout failure."],
        "valuation_concerns": ["Unknown due to scout failure."],
        "what_would_confirm_thesis": ["Rerun Chokepoint Scout with valid LLM output."],
        "what_would_break_thesis": ["Insufficient evidence to support chokepoint thesis."],
        "scout_recommendation": "monitor_for_evidence",
        "scout_note": "Fallback output; do not use as investment evidence.",
    }


def repair_chokepoint_decision(obj: Dict[str, Any]) -> Dict[str, Any]:
    repaired = dict(obj or {})
    for field in CHOKEPOINT_SCORE_FIELDS:
        repaired[field] = clip_score(repaired.get(field), default=1)

    if repaired.get("serenity_thesis_quality") not in VALID_SERENITY_THESIS_QUALITIES:
        repaired["serenity_thesis_quality"] = "interesting_unproven"
    if repaired.get("evidence_level") not in VALID_CHOKEPOINT_EVIDENCE_LEVELS:
        repaired["evidence_level"] = "insufficient"
    if repaired.get("deep_research_priority") not in VALID_DEEP_RESEARCH_PRIORITIES:
        repaired["deep_research_priority"] = "low"
    if repaired.get("scout_recommendation") not in VALID_SCOUT_RECOMMENDATIONS or repaired.get("scout_recommendation") in {
        "buy",
        "increase",
        "starter_position",
        "tracking_position",
    }:
        repaired["scout_recommendation"] = "monitor_for_evidence"

    if repaired.get("evidence_level") in {"hypothesis_only", "insufficient"}:
        repaired["customer_validation_score"] = min(clip_score(repaired.get("customer_validation_score"), 1) or 1, 5)

    if (repaired.get("substitution_risk_score") or 0) >= 8 and repaired.get("serenity_thesis_quality") == "high_quality_chokepoint":
        repaired["serenity_thesis_quality"] = "interesting_unproven"

    strong_evidence_exception = (
        repaired.get("evidence_level") == "primary_supported"
        and (repaired.get("customer_validation_score") or 0) >= 8
        and (repaired.get("chokepoint_score") or 0) >= 8
    )
    if (
        (repaired.get("market_awareness_score") or 0) >= 8
        and (repaired.get("valuation_risk_score") or 0) >= 8
        and not strong_evidence_exception
    ):
        repaired["serenity_thesis_quality"] = "already_priced_in"

    for field in [
        "demand_transmission_chain",
        "key_supporting_evidence",
        "key_missing_evidence",
        "substitution_risks",
        "timing_risks",
        "valuation_concerns",
        "what_would_confirm_thesis",
        "what_would_break_thesis",
    ]:
        if not isinstance(repaired.get(field), list):
            value = repaired.get(field)
            repaired[field] = [] if summary_is_missing(value) else [str(value)]

    for field in ["ticker", "company_name", "theme", "market", "chokepoint_summary", "supply_chain_node", "supply_chain_position", "scout_note"]:
        repaired[field] = str(repaired.get(field) or "").strip()

    return repaired


def chokepoint_context_from_decision(chokepoint: Dict[str, Any]) -> str:
    lines = [
        "## Serenity-style Chokepoint Analysis",
        "",
        f"- Chokepoint score: {chokepoint.get('chokepoint_score')}",
        f"- Serenity thesis quality: {chokepoint.get('serenity_thesis_quality')}",
        f"- Evidence level: {chokepoint.get('evidence_level')}",
        f"- Deep research priority: {chokepoint.get('deep_research_priority')}",
        f"- Scout recommendation: {chokepoint.get('scout_recommendation')}",
        "",
        chokepoint.get("chokepoint_summary") or "Chokepoint Scout not available.",
    ]
    return "\n".join(lines)


def run_chokepoint_scout(
    ticker: str,
    company_name: str,
    theme: str,
    market: str,
    snapshot_md: str,
    evidence_context: str,
    peer_context: str,
    valuation_bridge_md: str,
    ai_agent_framework_md: str,
    out_dir: Path,
    diagnostics: Optional[List[Dict[str, Any]]] = None,
    enabled: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    if not enabled:
        decision = fallback_chokepoint_decision(ticker, company_name, theme, market, not_run=True)
        context = chokepoint_context_from_decision(decision)
        save_text(out_dir / "chokepoint_context.md", context)
        save_json(out_dir / "chokepoint_decision.json", decision)
        return context, decision

    prompt = build_chokepoint_scout_prompt(
        ticker,
        company_name,
        theme,
        market,
        snapshot_md,
        evidence_context,
        peer_context,
        valuation_bridge_md,
        ai_agent_framework_md,
    )
    save_text(out_dir / "chokepoint_prompt.md", prompt)
    try:
        context = call_llm(
            "Chokepoint Scout Agent",
            prompt,
            max_tokens=int(os.getenv("CHOKEPOINT_SCOUT_MAX_TOKENS", "3500")),
            diagnostics=diagnostics,
        )
        json_raw = call_llm(
            "Chokepoint JSON Agent",
            build_chokepoint_json_prompt(ticker, company_name, theme, market, context),
            max_tokens=int(os.getenv("CHOKEPOINT_JSON_MAX_TOKENS", "2500")),
            decorate=False,
            json_mode=True,
            diagnostics=diagnostics,
        )
        decision = repair_json_object(
            json_raw,
            schema_hint="Chokepoint Scout JSON object with scores, evidence level, thesis quality, risks, and scout recommendation.",
            diagnostics=diagnostics,
        )
        decision["ticker"] = ticker
        decision["company_name"] = company_name
        decision["theme"] = theme
        decision["market"] = market
        decision = repair_chokepoint_decision(decision)
    except Exception as exc:
        decision = fallback_chokepoint_decision(ticker, company_name, theme, market, str(exc))
        context = chokepoint_context_from_decision(decision)

    save_text(out_dir / "chokepoint_context.md", context)
    save_json(out_dir / "chokepoint_decision.json", decision)
    return context, decision


def calculate_chokepoint_adjusted_score(chokepoint: Dict[str, Any]) -> Optional[float]:
    if not chokepoint or chokepoint.get("scout_recommendation") == "not_run":
        return None
    required = [chokepoint.get(field) for field in CHOKEPOINT_SCORE_FIELDS]
    if any(safe_float(v) is None for v in required):
        return None

    positive = (
        0.25 * (safe_float(chokepoint.get("chokepoint_score")) or 0)
        + 0.20 * (safe_float(chokepoint.get("indispensability_score")) or 0)
        + 0.20 * (safe_float(chokepoint.get("scarcity_score")) or 0)
        + 0.20 * (safe_float(chokepoint.get("customer_validation_score")) or 0)
        + 0.15 * (safe_float(chokepoint.get("nvidia_signal_score")) or 0)
    )
    negative_penalty = (
        0.10 * (safe_float(chokepoint.get("substitution_risk_score")) or 0)
        + 0.05 * (safe_float(chokepoint.get("timing_risk_score")) or 0)
        + 0.10 * (safe_float(chokepoint.get("market_awareness_score")) or 0)
        + 0.10 * (safe_float(chokepoint.get("valuation_risk_score")) or 0)
    )
    score = positive - negative_penalty

    evidence_level = str(chokepoint.get("evidence_level") or "")
    if evidence_level == "secondary_supported":
        score -= 0.5
    elif evidence_level == "hypothesis_only":
        score -= 1.5
    elif evidence_level == "insufficient":
        score -= 2.0

    thesis_quality = str(chokepoint.get("serenity_thesis_quality") or "")
    if thesis_quality == "already_priced_in":
        score = min(score, 6.0)
    if thesis_quality == "weak_replaceable":
        score = min(score, 4.0)
    if (safe_float(chokepoint.get("substitution_risk_score")) or 0) >= 8:
        score = min(score, 5.0)
    if (safe_float(chokepoint.get("customer_validation_score")) or 0) <= 4:
        score = min(score, 6.0)

    return round(max(1.0, min(10.0, score)), 2)


def weighted_score_interpretation(score: Optional[float]) -> str:
    if score is None:
        return "not run"
    if score >= 8.0:
        return "strong candidate, subject to valuation and guardrails"
    if score >= 7.0:
        return "tracking/starter candidate"
    if score >= 6.0:
        return "deep research candidate"
    if score >= 5.0:
        return "watchlist only"
    return "low priority"


def calculate_weighted_investment_score(decision: Dict[str, Any], chokepoint: Dict[str, Any]) -> Dict[str, Any]:
    chokepoint_adjusted = calculate_chokepoint_adjusted_score(chokepoint)
    if chokepoint_adjusted is None:
        return {
            "chokepoint_adjusted_score": None,
            "weighted_investment_score": None,
            "weighted_score_interpretation": "not run",
        }

    risk_score = safe_float(decision.get("risk_score")) or 10
    risk_control_score = 11 - risk_score
    score = (
        0.14 * (safe_float(decision.get("fundamental_quality_score")) or 1)
        + 0.14 * (safe_float(decision.get("growth_visibility_score")) or 1)
        + 0.14 * (safe_float(decision.get("competitive_position_score")) or 1)
        + 0.10 * (safe_float(decision.get("ai_beneficiary_score")) or 1)
        + 0.16 * (safe_float(decision.get("valuation_attractiveness_score")) or 1)
        + 0.18 * chokepoint_adjusted
        + 0.08 * (safe_float(decision.get("evidence_quality_score")) or 1)
        + 0.06 * risk_control_score
    )
    weighted = round(max(1.0, min(10.0, score)), 2)
    return {
        "chokepoint_adjusted_score": chokepoint_adjusted,
        "weighted_investment_score": weighted,
        "weighted_score_interpretation": weighted_score_interpretation(weighted),
    }


def chokepoint_interpretation(chokepoint: Dict[str, Any], adjusted_score: Optional[float]) -> str:
    evidence_level = str(chokepoint.get("evidence_level") or "")
    if (safe_float(chokepoint.get("market_awareness_score")) or 0) >= 8 and (safe_float(chokepoint.get("valuation_risk_score")) or 0) >= 8:
        return "Chokepoint thesis may already be priced in."
    if adjusted_score is not None and adjusted_score >= 8 and evidence_level in {"primary_supported", "secondary_supported"}:
        return "Potentially important AI supply-chain chokepoint."
    if adjusted_score is not None and adjusted_score >= 8 and evidence_level in {"hypothesis_only", "insufficient"}:
        return "Interesting chokepoint hypothesis, but evidence is not strong enough for investment decision."
    if adjusted_score is not None and adjusted_score <= 4:
        return "Weak or replaceable supply-chain node."
    return "Chokepoint Scout is useful as research input, but final action remains governed by PM guardrails."


def apply_chokepoint_weighted_overlay(
    decision: Dict[str, Any],
    chokepoint: Dict[str, Any],
    evidence_quality: Dict[str, Any],
    price_sanity: Dict[str, Any],
    fetch_reliability: Dict[str, Any],
) -> Dict[str, Any]:
    overlaid = dict(decision)
    chokepoint = repair_chokepoint_decision(chokepoint) if chokepoint.get("scout_recommendation") != "not_run" else dict(chokepoint)
    weighted = calculate_weighted_investment_score(overlaid, chokepoint)
    warnings: List[str] = []
    applied = False
    reason = "no_upgrade"

    evidence_score = safe_float(evidence_quality.get("evidence_quality_score")) or safe_float(overlaid.get("evidence_quality_score")) or 1
    price_reliability = str(price_sanity.get("price_data_reliability") or overlaid.get("price_data_reliability") or "high")
    valuation_reliability = str(price_sanity.get("valuation_reliability") or overlaid.get("valuation_reliability") or "high")
    market_reliability = str(fetch_reliability.get("market_data_reliability") or "high")
    financial_reliability = str(fetch_reliability.get("financial_statement_reliability") or "high")
    price_fetch_reliability = str(fetch_reliability.get("price_data_reliability_from_fetch") or "high")
    manual_price_verification = bool(price_sanity.get("manual_price_verification_required") or overlaid.get("manual_price_verification_required"))
    evidence_level = str(chokepoint.get("evidence_level") or "insufficient")
    customer_validation = safe_float(chokepoint.get("customer_validation_score")) or 0
    substitution_risk = safe_float(chokepoint.get("substitution_risk_score")) or 10
    market_awareness = safe_float(chokepoint.get("market_awareness_score")) or 10
    valuation_risk = safe_float(chokepoint.get("valuation_risk_score")) or 10
    chokepoint_adjusted = safe_float(weighted.get("chokepoint_adjusted_score"))
    weighted_score = safe_float(weighted.get("weighted_investment_score"))

    hard_gate = any([
        manual_price_verification,
        price_reliability == "low",
        valuation_reliability == "low",
        market_reliability == "low",
        financial_reliability == "low",
        price_fetch_reliability == "low",
        evidence_score < 6,
        evidence_level in {"hypothesis_only", "insufficient"} and customer_validation <= 5,
        chokepoint.get("scout_recommendation") == "not_run",
    ])

    if evidence_level in {"hypothesis_only", "insufficient"}:
        warnings.append("chokepoint_hypothesis_only_no_position_upgrade")
    if chokepoint.get("serenity_thesis_quality") == "weak_replaceable":
        warnings.append("weak_chokepoint_no_position_upgrade")
    already_priced = market_awareness >= 8 and valuation_risk >= 8
    if already_priced:
        warnings.append("chokepoint_already_priced_in_caps_position_at_1pct")

    action = str(overlaid.get("action") or "watchlist")
    position = safe_float(overlaid.get("suggested_position_pct")) or 0.0

    if hard_gate:
        reason = "hard_gate_no_upgrade"
    elif chokepoint.get("serenity_thesis_quality") == "weak_replaceable":
        reason = "weak_replaceable_no_upgrade"
    elif evidence_level in {"hypothesis_only", "insufficient"}:
        reason = "hypothesis_or_insufficient_evidence_no_upgrade"
    else:
        if already_priced and action not in {"buy", "starter_position"}:
            position = min(position, 1.0)
            if action == "starter_position":
                action = "tracking_position"
            reason = "already_priced_in_cap"

        if (
            chokepoint_adjusted is not None
            and chokepoint_adjusted >= 7.5
            and evidence_score >= 7
            and evidence_level in {"primary_supported", "secondary_supported"}
            and valuation_reliability in {"high", "medium"}
            and price_reliability in {"high", "medium"}
            and substitution_risk <= 7
            and action == "watchlist"
            and position <= 0
        ):
            action = "tracking_position"
            overlaid["rating"] = "tracking_watch"
            position = 0.5 if valuation_risk >= 8 or market_awareness >= 8 else 1.0
            applied = True
            reason = "high_quality_chokepoint_tracking_upgrade"

        if (
            not already_priced
            and weighted_score is not None
            and weighted_score >= 7.2
            and chokepoint_adjusted is not None
            and chokepoint_adjusted >= 7.5
            and evidence_score >= 8
            and evidence_level == "primary_supported"
            and customer_validation >= 7
            and (safe_float(overlaid.get("valuation_attractiveness_score")) or 0) >= 4
            and valuation_reliability in {"high", "medium"}
            and valuation_risk <= 7
            and action in {"watchlist", "tracking_position"}
        ):
            action = "starter_position"
            overlaid["rating"] = "small_start"
            position = min(max(position, 1.0), 2.0)
            applied = True
            reason = "primary_supported_weighted_starter_upgrade"

    if already_priced:
        if action == "starter_position" and position > 1.0:
            action = "tracking_position"
        position = min(position, 1.0)

    overlaid["action"] = action
    overlaid["suggested_position_pct"] = position
    overlaid.update({
        **weighted,
        "chokepoint_overlay_applied": applied,
        "chokepoint_overlay_reason": reason,
        "chokepoint_overlay_warnings": sorted(set(warnings)),
        "chokepoint_score": chokepoint.get("chokepoint_score"),
        "indispensability_score": chokepoint.get("indispensability_score"),
        "scarcity_score": chokepoint.get("scarcity_score"),
        "customer_validation_score": chokepoint.get("customer_validation_score"),
        "nvidia_signal_score": chokepoint.get("nvidia_signal_score"),
        "substitution_risk_score": chokepoint.get("substitution_risk_score"),
        "timing_risk_score": chokepoint.get("timing_risk_score"),
        "market_awareness_score": chokepoint.get("market_awareness_score"),
        "valuation_risk_score": chokepoint.get("valuation_risk_score"),
        "serenity_thesis_quality": chokepoint.get("serenity_thesis_quality"),
        "chokepoint_evidence_level": chokepoint.get("evidence_level"),
        "deep_research_priority": chokepoint.get("deep_research_priority"),
        "scout_recommendation": chokepoint.get("scout_recommendation"),
        "chokepoint_decision": chokepoint,
        "chokepoint_interpretation": chokepoint_interpretation(chokepoint, chokepoint_adjusted),
    })
    return overlaid


def normalize_action_position_consistency(decision: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(decision)
    action = str(normalized.get("action") or "watchlist")
    position = safe_float(normalized.get("suggested_position_pct")) or 0.0

    if action in {"manual_price_verification_required", "avoid"}:
        normalized["suggested_position_pct"] = 0.0
        return normalized

    if action == "watchlist" and position > 0:
        normalized["action"] = "tracking_position"
        if normalized.get("rating") in {"watch", "cautious_watch", None, ""}:
            normalized["rating"] = "tracking_watch"
    elif action == "tracking_position" and position <= 0:
        normalized["action"] = "watchlist"
        if normalized.get("rating") == "tracking_watch":
            normalized["rating"] = "watch"

    if normalized.get("action") == "tracking_position":
        normalized["suggested_position_pct"] = min(max(position, 0.5), 1.0)
    elif normalized.get("action") == "starter_position" and position > 0:
        normalized["suggested_position_pct"] = min(max(position, 1.0), 2.0)
    elif normalized.get("action") == "buy" and position > 0:
        normalized["suggested_position_pct"] = min(max(position, 2.0), 5.0)

    return normalized


def fallback_decision(ticker: str, name: str, error: str = "") -> Dict[str, Any]:
    return {
        "ticker": ticker,
        "company_name": name,
        "rating": "watch",
        "action": "watchlist",
        "suggested_position_pct": 0,
        "confidence_score": 1,
        "fundamental_quality_score": 1,
        "growth_visibility_score": 1,
        "valuation_attractiveness_score": 1,
        "ai_beneficiary_score": 1,
        "competitive_position_score": 1,
        "risk_score": 10,
        "evidence_quality_score": 1,
        "thesis_summary": "Fallback decision. Structured JSON output was not reliable.",
        "ai_agent_demand_link": "Unavailable because structured output failed.",
        "valuation_premium_reason": "Unavailable because structured output failed.",
        "valuation_is_justified": False,
        "valuation_view": "No reliable valuation view.",
        "portfolio_fit": "No reliable portfolio view.",
        "bull_case": "Unavailable.",
        "base_case": "Unavailable.",
        "bear_case": "Unavailable.",
        "key_bull_points": ["Structured output failed; use memo only after manual review."],
        "key_bear_points": ["Output quality requires manual review."],
        "key_tracking_indicators": ["Rerun after fixing structured output."],
        "thesis_kill_triggers": ["Data cannot be verified."],
        "data_gaps": ["Structured JSON output failed.", error],
        "deepest_questions": [
            "Which evidence item supports the AI-agent demand link?",
            "Which valuation premium is justified by financial evidence?",
            "Which tracking indicator would change the recommendation?"
        ],
        "final_pm_judgment": "No reliable structured investment judgment.",
    }


def evidence_metrics_from_text(text: str) -> Dict[str, Any]:
    items = extract_evidence_items_from_text(text)
    tiers = [str(item.get("evidence_tier") or "") for item in items]
    categories = re.findall(r"^###\s+(.+)$", text, flags=re.MULTILINE)
    counts: Dict[str, int] = {}
    for tier in tiers:
        counts[tier] = counts.get(tier, 0) + 1
    return {
        "source_count": len(tiers),
        "category_count": len(categories),
        "tier_counts": counts,
        "primary_count": sum(v for k, v in counts.items() if k.startswith("primary_")),
        "transcript_count": sum(v for k, v in counts.items() if k.startswith("transcript")),
        "industry_count": counts.get("industry_data", 0),
        "secondary_count": counts.get("secondary_news", 0),
        "weak_count": counts.get("weak_source", 0),
    }


def evidence_metrics_for_row(row: Dict[str, Any]) -> Dict[str, Any]:
    output_dir = str(row.get("output_dir") or "")
    if not output_dir:
        return evidence_metrics_from_text("")
    path = Path(output_dir) / "evidence_context.md"
    try:
        return evidence_metrics_from_text(path.read_text(encoding="utf-8"))
    except Exception:
        return evidence_metrics_from_text("")


def build_group_quality_report(
    rows: List[Dict[str, Any]],
    comparison_path: Optional[Path] = None,
) -> Dict[str, Any]:
    company_reports: List[Dict[str, Any]] = []
    group_warnings: List[str] = []
    peer_type_counts: Dict[str, int] = {}

    for row in rows:
        decision = row.get("decision") or {}
        evidence_metrics = evidence_metrics_for_row(row)
        market_snapshot = load_market_snapshot_for_row(row)
        issues = decision_quality_issues(decision)
        warnings = decision_quality_warnings(decision, market_snapshot)

        if evidence_metrics.get("primary_count", 0) == 0 and safe_float(decision.get("evidence_quality_score")) and safe_float(decision.get("evidence_quality_score")) >= 6:
            warnings.append("evidence_score_may_be_overstated_no_primary_sources")
        if evidence_metrics.get("weak_count", 0) > 0:
            warnings.append("weak_sources_present")

        peer_type = row.get("peer_type") or ("target" if row.get("analysis_group_role") == "target" else "unknown")
        if row.get("analysis_group_role") == "peer":
            peer_type_counts[peer_type] = peer_type_counts.get(peer_type, 0) + 1

        status = "pass"
        if issues:
            status = "needs_rerun"
        elif warnings:
            status = "review"

        company_reports.append({
            "ticker": row.get("ticker"),
            "company_name": row.get("company_name"),
            "group_role": row.get("analysis_group_role"),
            "peer_type": peer_type,
            "profit_pool": row.get("profit_pool"),
            "rating": decision.get("rating"),
            "action": decision.get("action"),
            "suggested_position_pct": decision.get("suggested_position_pct"),
            "confidence_score": decision.get("confidence_score"),
            "evidence_quality_score": decision.get("evidence_quality_score"),
            "risk_score": decision.get("risk_score"),
            "decision_quality_issues": issues,
            "decision_quality_warnings": sorted(set(warnings)),
            "evidence_metrics": evidence_metrics,
            "quality_status": status,
            "output_dir": row.get("output_dir"),
        })

    if any(c["decision_quality_issues"] for c in company_reports):
        group_warnings.append("one_or_more_decisions_need_rerun")
    review_count = sum(1 for c in company_reports if c["quality_status"] == "review")
    if review_count:
        group_warnings.append(f"{review_count}_companies_have_quality_warnings")

    peer_total = sum(peer_type_counts.values())
    direct_like = peer_type_counts.get("direct_competitor", 0) + peer_type_counts.get("same_profit_pool", 0)
    peer_purity = safe_div(direct_like, peer_total) if peer_total else None
    if peer_total and peer_purity is not None and peer_purity < 0.5:
        group_warnings.append("peer_set_has_low_direct_comparable_purity")

    return {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "comparison_path": str(comparison_path) if comparison_path else "",
        "company_count": len(company_reports),
        "peer_type_counts": peer_type_counts,
        "peer_purity_direct_or_same_profit_pool": peer_purity,
        "group_warnings": sorted(set(group_warnings)),
        "companies": company_reports,
    }


def quality_report_to_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Research Quality Report",
        "",
        f"- Created at: {report.get('created_at')}",
        f"- Company count: {report.get('company_count')}",
        f"- Peer purity (direct/same profit pool): {format_pct(report.get('peer_purity_direct_or_same_profit_pool'))}",
        f"- Group warnings: {', '.join(report.get('group_warnings') or []) or 'None'}",
        "",
        "## Company Checks",
        "",
        "| Ticker | Role | Peer Type | Rating | Position | Evidence Score | Primary Sources | Issues | Warnings | Status |",
        "|---|---|---|---|---:|---:|---:|---|---|---|",
    ]
    for item in report.get("companies", []):
        metrics = item.get("evidence_metrics") or {}
        issues = ", ".join(item.get("decision_quality_issues") or [])
        warnings = ", ".join(item.get("decision_quality_warnings") or [])
        lines.append(
            f"| {item.get('ticker')} | {item.get('group_role')} | {item.get('peer_type')} | "
            f"{item.get('rating')} | {item.get('suggested_position_pct')} | {item.get('evidence_quality_score')} | "
            f"{metrics.get('primary_count', 0)} | {issues or 'None'} | {warnings or 'None'} | {item.get('quality_status')} |"
        )

    lines.extend([
        "",
        "## Peer Type Counts",
        "",
    ])
    for peer_type, count in (report.get("peer_type_counts") or {}).items():
        lines.append(f"- {peer_type}: {count}")

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- `needs_rerun` means the structured decision had hard schema/fallback issues.",
        "- `review` means the output is structurally valid but has evidence, valuation, risk, or peer-purity warnings.",
        "- `pass` means no automated quality issue was detected; it still requires human investment judgment.",
    ])
    return "\n".join(lines)


def latest_existing_output_dir(
    ticker: str,
    output_root: str,
    day: Optional[str] = None,
) -> Optional[Path]:
    day_dir = Path(output_root) / (day or today_str())
    if not day_dir.exists():
        return None

    target_canonical = canonical_ticker_for(ticker)
    candidates: List[Path] = []
    for decision_path in day_dir.glob("*/pm_decision.json"):
        out_dir = decision_path.parent
        try:
            decision = load_json_file(decision_path)
            existing_ticker = decision.get("ticker") or out_dir.name.rsplit("_", 2)[0].replace("_", ".")
            if canonical_ticker_for(existing_ticker) != target_canonical:
                continue
            required = [
                out_dir / "pm_memo.md",
                out_dir / "market_snapshot.json",
                out_dir / "full_research_package.md",
                out_dir / "quality_report.md",
            ]
            if not all(p.exists() for p in required):
                continue
            if decision_quality_issues(decision):
                continue
            candidates.append(out_dir)
        except Exception:
            continue

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def row_from_existing_output(
    out_dir: Path,
    ticker: str,
    name: str,
    theme: str,
    market: str,
    group_id: Optional[str],
    group_role: str,
) -> Dict[str, Any]:
    decision = load_json_file(out_dir / "pm_decision.json")
    decision["ticker"] = decision.get("ticker") or ticker
    decision["company_name"] = clean_company_name(ticker, decision.get("company_name") or name)
    return {
        "created_at": dt.datetime.fromtimestamp(out_dir.stat().st_mtime).isoformat(timespec="seconds"),
        "analysis_group_id": group_id or "",
        "analysis_group_role": group_role,
        "ticker": decision.get("ticker"),
        "company_name": decision.get("company_name"),
        "theme": theme,
        "market": market,
        "rating": decision.get("rating"),
        "action": decision.get("action"),
        "suggested_position_pct": decision.get("suggested_position_pct"),
        "confidence_score": decision.get("confidence_score"),
        "risk_score": decision.get("risk_score"),
        "output_dir": str(out_dir),
        "pm_memo": str(out_dir / "pm_memo.md"),
        "pm_decision_json": str(out_dir / "pm_decision.json"),
        "full_package": str(out_dir / "full_research_package.md"),
        "quality_report": str(out_dir / "quality_report.md"),
        "decision": decision,
        "reused_existing_output": True,
    }


SUMMARY_QUALITY_ORDER = {
    "deep_research_candidate": 0,
    "pass": 1,
    "manual_review": 2,
    "low_priority": 3,
    "needs_rerun": 4,
}


def summary_is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def first_present(*values: Any, default: Any = None) -> Any:
    for value in values:
        if not summary_is_missing(value):
            return value
    return default


def summary_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if summary_is_missing(value):
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "t"}:
        return True
    if text in {"false", "0", "no", "n", "f", "none", "nan"}:
        return False
    return bool(text)


def summary_int_or_none(value: Any) -> Optional[int]:
    if summary_is_missing(value):
        return None
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    numeric = safe_float(value)
    if numeric is None:
        return None
    return int(numeric)


def summary_count(value: Any) -> int:
    count = summary_int_or_none(value)
    return count if count is not None else 0


def summary_float_or_none(value: Any) -> Optional[float]:
    return safe_float(value)


def list_to_summary_text(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item).strip())
    if isinstance(value, tuple) or isinstance(value, set):
        return "; ".join(str(item) for item in value if str(item).strip())
    return "" if summary_is_missing(value) else str(value)


def nested_dict_value(data: Dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_valuation_upside_fields(decision: Dict[str, Any]) -> Dict[str, Any]:
    summary = decision.get("valuation_bridge_summary") or {}
    bridge = decision.get("valuation_bridge") or {}
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(bridge, dict):
        bridge = {}

    def base_from_summary(name: str) -> Optional[float]:
        return summary_float_or_none(nested_dict_value(summary, name, "base_upside_downside"))

    def scenario_from_summary(case: str) -> Optional[float]:
        return summary_float_or_none(nested_dict_value(summary, "scenarios", case, "upside_downside"))

    def scenario_from_bridge(case: str) -> Optional[float]:
        return summary_float_or_none(nested_dict_value(bridge, "scenarios", case, "upside_downside"))

    framework_pairs = [
        ("traditional_memory_cycle", "structural_hbm_scarcity"),
        ("traditional_electrical_equipment", "ai_data_center_power_scarcity"),
        ("traditional_wfe_cycle", "ai_equipment_scarcity_quality"),
    ]
    traditional_base = None
    scarcity_base = None
    for traditional_name, scarcity_name in framework_pairs:
        traditional_base = base_from_summary(traditional_name)
        scarcity_base = base_from_summary(scarcity_name)
        if traditional_base is not None or scarcity_base is not None:
            break

    base_upside = first_present(scenario_from_summary("base"), scenario_from_bridge("base"))
    if traditional_base is None:
        traditional_base = summary_float_or_none(base_upside)
    if scarcity_base is None:
        scarcity_base = summary_float_or_none(base_upside)

    bull_upside = first_present(scenario_from_summary("bull"), scenario_from_bridge("bull"))
    bear_upside = first_present(scenario_from_summary("bear"), scenario_from_bridge("bear"))

    return {
        "traditional_base_upside_downside": summary_float_or_none(traditional_base),
        "scarcity_base_upside_downside": summary_float_or_none(scarcity_base),
        "bull_upside_downside": summary_float_or_none(bull_upside),
        "bear_upside_downside": summary_float_or_none(bear_upside),
    }


def fetch_summary_count(row: Dict[str, Any], fetch_summary: Dict[str, Any], scope: str, status: str) -> Optional[int]:
    row_field = f"{scope}_fetch_{status}_count"
    value = first_present(row.get(row_field), nested_dict_value(fetch_summary, scope, status))
    return summary_int_or_none(value)


def flatten_decision_for_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
    evidence_quality = decision.get("evidence_quality") if isinstance(decision.get("evidence_quality"), dict) else {}
    fetch_summary = decision.get("fetch_diagnostics_summary") if isinstance(decision.get("fetch_diagnostics_summary"), dict) else {}
    price_sanity = decision.get("price_sanity") if isinstance(decision.get("price_sanity"), dict) else {}
    valuation_bridge = decision.get("valuation_bridge") if isinstance(decision.get("valuation_bridge"), dict) else {}
    valuation_summary = decision.get("valuation_bridge_summary") if isinstance(decision.get("valuation_bridge_summary"), dict) else {}
    chokepoint_decision = decision.get("chokepoint_decision") if isinstance(decision.get("chokepoint_decision"), dict) else {}
    official = evidence_quality.get("official_source_search") if isinstance(evidence_quality.get("official_source_search"), dict) else {}
    quality_issues = decision_quality_issues(decision) if decision else []

    output_dir = first_present(row.get("output_dir"), decision.get("output_dir"), default="")
    output_path = Path(str(output_dir)) if output_dir else None

    def path_field(field_name: str, filename: str) -> str:
        existing = first_present(row.get(field_name), decision.get(field_name))
        if not summary_is_missing(existing):
            return str(existing)
        if output_path:
            return str(output_path / filename)
        return ""

    guardrail_warnings = first_present(row.get("guardrail_warnings"), decision.get("guardrail_warnings"), default=[])
    price_warnings = first_present(row.get("price_sanity_warnings"), decision.get("price_sanity_warnings"), price_sanity.get("price_sanity_warnings"), default=[])
    data_fetch_warnings = first_present(row.get("data_fetch_warnings"), decision.get("data_fetch_warnings"), default=[])
    evidence_score = first_present(row.get("evidence_quality_score"), decision.get("evidence_quality_score"), evidence_quality.get("evidence_quality_score"))
    official_primary_hits = first_present(row.get("official_primary_hits"), official.get("official_primary_hits"))

    fallback_flag = first_present(row.get("fallback_decision"), decision.get("fallback_decision"))
    fallback_decision_flag = (
        summary_bool(fallback_flag)
        or "fallback_decision" in quality_issues
        or str(decision.get("thesis_summary") or "").lower().startswith("fallback decision")
    )
    structured_flag = first_present(row.get("structured_json_failed"), decision.get("structured_json_failed"))
    structured_json_failed = summary_bool(structured_flag) or bool(quality_issues)

    flat: Dict[str, Any] = {
        "created_at": first_present(row.get("created_at"), decision.get("created_at"), default=""),
        "ticker": first_present(row.get("ticker"), decision.get("ticker"), default=""),
        "company_name": first_present(row.get("company_name"), decision.get("company_name"), default=""),
        "theme": first_present(row.get("theme"), decision.get("theme"), default=""),
        "market": first_present(row.get("market"), decision.get("market"), default=""),
        "analysis_group_role": first_present(row.get("analysis_group_role"), row.get("group_role"), default=""),
        "peer_type": first_present(row.get("peer_type"), decision.get("peer_type"), default=""),
        "profit_pool": first_present(row.get("profit_pool"), decision.get("profit_pool"), default=""),
        "rating": first_present(row.get("rating"), decision.get("rating"), default=""),
        "action": first_present(row.get("action"), decision.get("action"), default=""),
        "suggested_position_pct": summary_float_or_none(first_present(row.get("suggested_position_pct"), decision.get("suggested_position_pct"))),
        "confidence_score": summary_float_or_none(first_present(row.get("confidence_score"), decision.get("confidence_score"))),
        "risk_score": summary_float_or_none(first_present(row.get("risk_score"), decision.get("risk_score"))),
        "evidence_quality_score": summary_float_or_none(evidence_score),
        "primary_regulatory_count": summary_int_or_none(first_present(row.get("primary_regulatory_count"), evidence_quality.get("primary_regulatory_count"))),
        "primary_company_count": summary_int_or_none(first_present(row.get("primary_company_count"), evidence_quality.get("primary_company_count"))),
        "transcript_secondary_count": summary_int_or_none(first_present(row.get("transcript_secondary_count"), evidence_quality.get("transcript_secondary_count"))),
        "industry_data_count": summary_int_or_none(first_present(row.get("industry_data_count"), evidence_quality.get("industry_data_count"))),
        "secondary_news_count": summary_int_or_none(first_present(row.get("secondary_news_count"), evidence_quality.get("secondary_news_count"))),
        "weak_source_count": summary_int_or_none(first_present(row.get("weak_source_count"), evidence_quality.get("weak_source_count"))),
        "official_primary_hits": summary_int_or_none(official_primary_hits),
        "official_regulatory_hits": summary_int_or_none(first_present(row.get("official_regulatory_hits"), official.get("official_regulatory_hits"))),
        "official_company_hits": summary_int_or_none(first_present(row.get("official_company_hits"), official.get("official_company_hits"))),
        "market_data_reliability": first_present(row.get("market_data_reliability"), decision.get("market_data_reliability"), default=""),
        "financial_statement_reliability": first_present(row.get("financial_statement_reliability"), decision.get("financial_statement_reliability"), default=""),
        "price_data_reliability_from_fetch": first_present(row.get("price_data_reliability_from_fetch"), decision.get("price_data_reliability_from_fetch"), default=""),
        "price_data_reliability": first_present(row.get("price_data_reliability"), decision.get("price_data_reliability"), price_sanity.get("price_data_reliability"), default=""),
        "valuation_reliability": first_present(row.get("valuation_reliability"), decision.get("valuation_reliability"), price_sanity.get("valuation_reliability"), default=""),
        "manual_price_verification_required": summary_bool(first_present(row.get("manual_price_verification_required"), decision.get("manual_price_verification_required"), price_sanity.get("manual_price_verification_required"))),
        "data_fetch_warning_count": summary_count(first_present(row.get("data_fetch_warning_count"), data_fetch_warnings)),
        "price_sanity_warning_count": summary_count(first_present(row.get("price_sanity_warning_count"), price_warnings)),
        "market_fetch_failed_count": fetch_summary_count(row, fetch_summary, "market", "failed"),
        "evidence_fetch_failed_count": fetch_summary_count(row, fetch_summary, "evidence", "failed"),
        "llm_fetch_failed_count": fetch_summary_count(row, fetch_summary, "llm", "failed"),
        "market_fetch_empty_count": fetch_summary_count(row, fetch_summary, "market", "empty"),
        "evidence_fetch_empty_count": fetch_summary_count(row, fetch_summary, "evidence", "empty"),
        "llm_fetch_empty_count": fetch_summary_count(row, fetch_summary, "llm", "empty"),
        "market_fetch_rate_limited_count": fetch_summary_count(row, fetch_summary, "market", "rate_limited"),
        "evidence_fetch_rate_limited_count": fetch_summary_count(row, fetch_summary, "evidence", "rate_limited"),
        "llm_fetch_rate_limited_count": fetch_summary_count(row, fetch_summary, "llm", "rate_limited"),
        "valuation_framework_type": first_present(row.get("valuation_framework_type"), decision.get("valuation_framework_type"), valuation_summary.get("framework_type"), valuation_bridge.get("framework_type"), default=""),
        "valuation_framework_interpretation": first_present(row.get("valuation_framework_interpretation"), decision.get("valuation_framework_interpretation"), default=""),
        "valuation_is_justified": first_present(row.get("valuation_is_justified"), decision.get("valuation_is_justified")),
        "valuation_attractiveness_score": summary_float_or_none(first_present(row.get("valuation_attractiveness_score"), decision.get("valuation_attractiveness_score"))),
        "valuation_premium_reason": first_present(row.get("valuation_premium_reason"), decision.get("valuation_premium_reason"), default=""),
        "fundamental_quality_score": summary_float_or_none(first_present(row.get("fundamental_quality_score"), decision.get("fundamental_quality_score"))),
        "growth_visibility_score": summary_float_or_none(first_present(row.get("growth_visibility_score"), decision.get("growth_visibility_score"))),
        "ai_beneficiary_score": summary_float_or_none(first_present(row.get("ai_beneficiary_score"), decision.get("ai_beneficiary_score"))),
        "competitive_position_score": summary_float_or_none(first_present(row.get("competitive_position_score"), decision.get("competitive_position_score"))),
        "chokepoint_score": summary_float_or_none(first_present(row.get("chokepoint_score"), decision.get("chokepoint_score"), chokepoint_decision.get("chokepoint_score"))),
        "indispensability_score": summary_float_or_none(first_present(row.get("indispensability_score"), decision.get("indispensability_score"), chokepoint_decision.get("indispensability_score"))),
        "scarcity_score": summary_float_or_none(first_present(row.get("scarcity_score"), decision.get("scarcity_score"), chokepoint_decision.get("scarcity_score"))),
        "customer_validation_score": summary_float_or_none(first_present(row.get("customer_validation_score"), decision.get("customer_validation_score"), chokepoint_decision.get("customer_validation_score"))),
        "nvidia_signal_score": summary_float_or_none(first_present(row.get("nvidia_signal_score"), decision.get("nvidia_signal_score"), chokepoint_decision.get("nvidia_signal_score"))),
        "substitution_risk_score": summary_float_or_none(first_present(row.get("substitution_risk_score"), decision.get("substitution_risk_score"), chokepoint_decision.get("substitution_risk_score"))),
        "timing_risk_score": summary_float_or_none(first_present(row.get("timing_risk_score"), decision.get("timing_risk_score"), chokepoint_decision.get("timing_risk_score"))),
        "market_awareness_score": summary_float_or_none(first_present(row.get("market_awareness_score"), decision.get("market_awareness_score"), chokepoint_decision.get("market_awareness_score"))),
        "valuation_risk_score": summary_float_or_none(first_present(row.get("valuation_risk_score"), decision.get("valuation_risk_score"), chokepoint_decision.get("valuation_risk_score"))),
        "serenity_thesis_quality": first_present(row.get("serenity_thesis_quality"), decision.get("serenity_thesis_quality"), chokepoint_decision.get("serenity_thesis_quality"), default=""),
        "chokepoint_evidence_level": first_present(row.get("chokepoint_evidence_level"), decision.get("chokepoint_evidence_level"), chokepoint_decision.get("evidence_level"), default=""),
        "deep_research_priority": first_present(row.get("deep_research_priority"), decision.get("deep_research_priority"), chokepoint_decision.get("deep_research_priority"), default=""),
        "scout_recommendation": first_present(row.get("scout_recommendation"), decision.get("scout_recommendation"), chokepoint_decision.get("scout_recommendation"), default=""),
        "chokepoint_adjusted_score": summary_float_or_none(first_present(row.get("chokepoint_adjusted_score"), decision.get("chokepoint_adjusted_score"))),
        "weighted_investment_score": summary_float_or_none(first_present(row.get("weighted_investment_score"), decision.get("weighted_investment_score"))),
        "weighted_score_interpretation": first_present(row.get("weighted_score_interpretation"), decision.get("weighted_score_interpretation"), default=""),
        "chokepoint_overlay_applied": summary_bool(first_present(row.get("chokepoint_overlay_applied"), decision.get("chokepoint_overlay_applied"))),
        "chokepoint_overlay_reason": first_present(row.get("chokepoint_overlay_reason"), decision.get("chokepoint_overlay_reason"), default=""),
        "chokepoint_overlay_warnings": list_to_summary_text(first_present(row.get("chokepoint_overlay_warnings"), decision.get("chokepoint_overlay_warnings"), default=[])),
        "guardrail_warning_count": summary_count(first_present(row.get("guardrail_warning_count"), guardrail_warnings)),
        "guardrail_warnings": list_to_summary_text(guardrail_warnings),
        "pre_guardrail_position_pct": summary_float_or_none(first_present(row.get("pre_guardrail_position_pct"), decision.get("pre_guardrail_position_pct"))),
        "max_allowed_position_pct": summary_float_or_none(first_present(row.get("max_allowed_position_pct"), decision.get("max_allowed_position_pct"))),
        "structured_json_failed": structured_json_failed,
        "fallback_decision": fallback_decision_flag,
        "needs_rerun": summary_bool(first_present(row.get("needs_rerun"), decision.get("needs_rerun"))),
        "manual_review_required": summary_bool(first_present(row.get("manual_review_required"), decision.get("manual_review_required"))),
        "deep_research_candidate": summary_bool(first_present(row.get("deep_research_candidate"), decision.get("deep_research_candidate"))),
        "quality_status": first_present(row.get("quality_status"), decision.get("quality_status"), default=""),
        "output_dir": str(output_dir),
        "quality_report": path_field("quality_report", "quality_report.md"),
        "pm_decision_json": path_field("pm_decision_json", "pm_decision.json"),
        "full_package": path_field("full_package", "full_research_package.md"),
        "pm_memo": path_field("pm_memo", "pm_memo.md"),
    }
    flat.update(extract_valuation_upside_fields({
        "valuation_bridge_summary": valuation_summary,
        "valuation_bridge": valuation_bridge,
    }))
    return flat


def summary_score_at_least(value: Any, threshold: float) -> bool:
    numeric = safe_float(value)
    return numeric is not None and numeric >= threshold


def summary_score_below(value: Any, threshold: float) -> bool:
    numeric = safe_float(value)
    return numeric is not None and numeric < threshold


def summary_score_positive(value: Any) -> bool:
    numeric = safe_float(value)
    return numeric is not None and numeric > 0


def summary_warning_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if value is None or summary_is_missing(value):
        return []
    text = str(value)
    if not text:
        return []
    parts = re.split(r"[;,]\s*", text)
    return [p.strip() for p in parts if p.strip()]


def summary_hard_blockers(flat: Dict[str, Any]) -> List[str]:
    blockers: List[str] = []
    if summary_bool(flat.get("structured_json_failed")):
        blockers.append("structured_json_failed")
    if summary_bool(flat.get("fallback_decision")):
        blockers.append("fallback_decision")
    if summary_score_positive(flat.get("llm_fetch_failed_count")):
        blockers.append(f"llm_fetch_failed_count={summary_count(flat.get('llm_fetch_failed_count'))}")
    if str(flat.get("market_data_reliability") or "").lower() == "low":
        blockers.append("market_data_reliability=low")
    if str(flat.get("price_data_reliability_from_fetch") or "").lower() == "low":
        blockers.append("price_data_reliability_from_fetch=low")
    if str(flat.get("financial_statement_reliability") or "").lower() == "low":
        blockers.append("financial_statement_reliability=low")
    if summary_bool(flat.get("manual_price_verification_required")):
        blockers.append("manual_price_verification_required")
    if str(flat.get("valuation_reliability") or "").lower() == "low":
        blockers.append("valuation_reliability=low")
    if summary_score_below(flat.get("evidence_quality_score"), 6):
        blockers.append("evidence_quality_score_below_6")
    official_hits = summary_int_or_none(flat.get("official_primary_hits"))
    if official_hits == 0:
        blockers.append("official_primary_hits=0")
    return sorted(set(blockers))


def summary_soft_warnings(flat: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    guardrail_count = summary_int_or_none(flat.get("guardrail_warning_count"))
    if guardrail_count is not None and guardrail_count >= 3:
        warnings.append("guardrail_warning_count>=3")
    if str(flat.get("price_data_reliability") or "").lower() == "medium":
        warnings.append("price_data_reliability=medium")
    if str(flat.get("valuation_reliability") or "").lower() == "medium":
        warnings.append("valuation_reliability=medium")

    guardrail_warnings = summary_warning_list(flat.get("guardrail_warnings"))
    soft_guardrail_codes = {
        "medium_price_reliability_caps_position_at_2pct",
        "medium_valuation_reliability_caps_position_at_2pct",
        "extreme_momentum_requires_manual_review_but_not_data_error",
    }
    for warning in guardrail_warnings:
        if warning in soft_guardrail_codes:
            warnings.append(warning)
        if "valuation_bridge" in warning and "downside" in warning:
            warnings.append(warning)

    if summary_float_or_none(flat.get("traditional_base_upside_downside")) is not None and summary_float_or_none(flat.get("traditional_base_upside_downside")) < 0:
        warnings.append("traditional_base_valuation_bridge_downside")
    if summary_float_or_none(flat.get("scarcity_base_upside_downside")) is not None and summary_float_or_none(flat.get("scarcity_base_upside_downside")) < 0:
        warnings.append("scarcity_base_valuation_bridge_downside")
    return sorted(set(warnings))


def summary_quality_reasons(flat: Dict[str, Any]) -> List[str]:
    blockers = summary_hard_blockers(flat)
    if blockers:
        return blockers
    return summary_soft_warnings(flat)


def classify_summary_quality(flat: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(flat)
    evidence_score = safe_float(updated.get("evidence_quality_score"))
    official_hits = summary_int_or_none(updated.get("official_primary_hits"))
    action = str(updated.get("action") or "")
    market_reliability = str(updated.get("market_data_reliability") or "").lower()
    financial_reliability = str(updated.get("financial_statement_reliability") or "").lower()
    price_fetch_reliability = str(updated.get("price_data_reliability_from_fetch") or "").lower()
    valuation_reliability = str(updated.get("valuation_reliability") or "").lower()

    structured_json_failed = summary_bool(updated.get("structured_json_failed"))
    fallback_decision_flag = summary_bool(updated.get("fallback_decision"))
    manual_price_verification = summary_bool(updated.get("manual_price_verification_required"))
    llm_failed = safe_float(updated.get("llm_fetch_failed_count")) or 0
    hard_blockers = summary_hard_blockers(updated)
    soft_warnings = summary_soft_warnings(updated)
    hard_blocker_count = len(hard_blockers)
    soft_warning_count = len(soft_warnings)

    needs_rerun = any([
        structured_json_failed,
        fallback_decision_flag,
        llm_failed > 0,
    ])
    manual_review_required = hard_blocker_count > 0
    deep_research_candidate = all([
        evidence_score is not None and evidence_score >= 7,
        official_hits is not None and official_hits > 0,
        market_reliability in {"high", "medium"},
        financial_reliability in {"high", "medium"},
        price_fetch_reliability in {"high", "medium"},
        not manual_price_verification,
        action in {"watchlist", "tracking_position", "starter_position", "buy", "hold_existing"},
        not fallback_decision_flag,
        not structured_json_failed,
        llm_failed <= 0,
    ]) and any([
        summary_score_positive(updated.get("suggested_position_pct")),
        summary_score_positive(updated.get("scarcity_base_upside_downside")),
        summary_score_at_least(updated.get("valuation_attractiveness_score"), 6),
        summary_score_at_least(updated.get("weighted_investment_score"), 6)
        and str(updated.get("chokepoint_evidence_level") or "") not in {"hypothesis_only", "insufficient"},
        summary_score_at_least(updated.get("chokepoint_adjusted_score"), 7.5)
        and str(updated.get("chokepoint_evidence_level") or "") in {"primary_supported", "secondary_supported"},
        summary_score_at_least(updated.get("ai_beneficiary_score"), 7)
        and summary_score_at_least(updated.get("competitive_position_score"), 7),
    ])

    quality_ok = all([
        evidence_score is not None and evidence_score >= 6,
        market_reliability in {"high", "medium"},
        financial_reliability in {"high", "medium"},
        price_fetch_reliability in {"high", "medium"},
        not manual_price_verification,
        not fallback_decision_flag,
        not structured_json_failed,
    ])

    if needs_rerun:
        quality_status = "needs_rerun"
    elif manual_review_required:
        quality_status = "manual_review"
    elif deep_research_candidate:
        quality_status = "deep_research_candidate"
    elif quality_ok:
        quality_status = "pass"
    else:
        quality_status = "low_priority"

    updated["needs_rerun"] = needs_rerun
    updated["manual_review_required"] = manual_review_required
    updated["deep_research_candidate"] = deep_research_candidate
    updated["quality_status"] = quality_status
    updated["hard_blocker_count"] = hard_blocker_count
    updated["hard_blockers"] = "; ".join(hard_blockers)
    updated["soft_warning_count"] = soft_warning_count
    updated["soft_warnings"] = "; ".join(soft_warnings)
    reasons = summary_quality_reasons(updated)
    if not reasons:
        if quality_status == "deep_research_candidate":
            reasons = ["strong_evidence_and_deep_research_criteria_met"]
        elif quality_status == "pass":
            reasons = ["data_evidence_quality_ok_not_deep_research_priority"]
        elif quality_status == "low_priority":
            reasons = ["data_evidence_quality_below_pass_threshold_or_low_priority_action"]
    updated["quality_reason"] = "; ".join(reasons)
    return updated


def suggested_rerun_mode(flat: Dict[str, Any]) -> str:
    if summary_bool(flat.get("manual_price_verification_required")):
        return "manual_price_verification"
    if summary_score_positive(flat.get("llm_fetch_failed_count")):
        return "rerun_with_higher_model_or_retry"
    official_hits = summary_int_or_none(flat.get("official_primary_hits"))
    if summary_score_below(flat.get("evidence_quality_score"), 6) or official_hits == 0:
        return "rerun_with_evidence_search_or_manual_sources"
    if str(flat.get("market_data_reliability") or "").lower() == "low":
        return "rerun_market_data_or_alternative_data_source"
    if str(flat.get("financial_statement_reliability") or "").lower() == "low":
        return "manual_financial_statement_review"
    if summary_bool(flat.get("fallback_decision")):
        return "rerun_structured_json"
    return "rerun_general_quality_check"


def sort_batch_summary_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    sortable = df.copy()
    sortable["_quality_sort"] = sortable.get("quality_status", "").map(SUMMARY_QUALITY_ORDER).fillna(99)
    for col in [
        "suggested_position_pct",
        "evidence_quality_score",
        "valuation_attractiveness_score",
        "weighted_investment_score",
        "chokepoint_adjusted_score",
    ]:
        if col not in sortable.columns:
            sortable[col] = np.nan
        sortable[col] = pd.to_numeric(sortable[col], errors="coerce")
    sortable = sortable.sort_values(
        by=[
            "_quality_sort",
            "weighted_investment_score",
            "chokepoint_adjusted_score",
            "evidence_quality_score",
            "suggested_position_pct",
        ],
        ascending=[True, False, False, False, False],
        na_position="last",
    )
    return sortable.drop(columns=["_quality_sort"])


def markdown_table_from_rows(rows: List[Dict[str, Any]], columns: List[Tuple[str, str]], empty_text: str = "None") -> List[str]:
    if not rows:
        return [empty_text]

    def summary_markdown_cell(value: Any, max_chars: int = 120) -> str:
        if summary_is_missing(value):
            return ""
        text = str(value).replace("\n", " ").strip()
        if len(text) > max_chars:
            text = text[: max_chars - 3].rstrip() + "..."
        return text.replace("|", "\\|")

    header = "| " + " | ".join(label for _, label in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, divider]
    for row in rows:
        lines.append("| " + " | ".join(summary_markdown_cell(row.get(key), 120) for key, _ in columns) + " |")
    return lines


def build_batch_summary_markdown(df: pd.DataFrame) -> str:
    company_count = len(df.index)
    deep_count = int((df.get("quality_status") == "deep_research_candidate").sum()) if company_count else 0
    manual_review_count = int(df.get("manual_review_required", pd.Series(dtype=bool)).map(summary_bool).sum()) if company_count else 0
    needs_rerun_count = int(df.get("needs_rerun", pd.Series(dtype=bool)).map(summary_bool).sum()) if company_count else 0
    manual_price_count = int(df.get("manual_price_verification_required", pd.Series(dtype=bool)).map(summary_bool).sum()) if company_count else 0
    avg_evidence = pd.to_numeric(df.get("evidence_quality_score", pd.Series(dtype=float)), errors="coerce").mean() if company_count else np.nan
    market_hm_count = int(df.get("market_data_reliability", pd.Series(dtype=str)).astype(str).str.lower().isin(["high", "medium"]).sum()) if company_count else 0
    financial_hm_count = int(df.get("financial_statement_reliability", pd.Series(dtype=str)).astype(str).str.lower().isin(["high", "medium"]).sum()) if company_count else 0

    top_rows = df[df.get("quality_status") == "deep_research_candidate"].to_dict("records") if company_count else []
    manual_rows = df[df.get("manual_review_required", pd.Series(dtype=bool)).map(summary_bool)].to_dict("records") if company_count else []
    rerun_rows = df[df.get("needs_rerun", pd.Series(dtype=bool)).map(summary_bool)].to_dict("records") if company_count else []
    soft_rows = df[
        (pd.to_numeric(df.get("soft_warning_count", pd.Series(dtype=float)), errors="coerce").fillna(0) > 0)
        & ~df.get("manual_review_required", pd.Series(dtype=bool)).map(summary_bool)
        & ~df.get("needs_rerun", pd.Series(dtype=bool)).map(summary_bool)
    ].to_dict("records") if company_count else []
    full_rows = df.to_dict("records") if company_count else []

    lines = [
        "# Batch Summary",
        "",
        "## Overview",
        f"- company_count: {company_count}",
        f"- deep_research_candidate_count: {deep_count}",
        f"- manual_review_count: {manual_review_count}",
        f"- needs_rerun_count: {needs_rerun_count}",
        f"- manual_price_verification_count: {manual_price_count}",
        f"- average_evidence_quality_score: {avg_evidence:.2f}" if not pd.isna(avg_evidence) else "- average_evidence_quality_score: N/A",
        f"- high_or_medium_market_data_count: {market_hm_count}",
        f"- high_or_medium_financial_statement_count: {financial_hm_count}",
        "",
        "## Top Deep Research Candidates",
        "",
    ]
    lines.extend(markdown_table_from_rows(top_rows, [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("theme", "theme"),
        ("action", "action"),
        ("suggested_position_pct", "position"),
        ("evidence_quality_score", "evidence_score"),
        ("valuation_attractiveness_score", "valuation_score"),
        ("ai_beneficiary_score", "AI score"),
        ("weighted_investment_score", "weighted"),
        ("chokepoint_adjusted_score", "chokepoint_adj"),
        ("serenity_thesis_quality", "serenity"),
        ("chokepoint_evidence_level", "cp_evidence"),
        ("deep_research_priority", "cp_priority"),
        ("valuation_framework_type", "framework"),
        ("scarcity_base_upside_downside", "scarcity_base_upside"),
        ("guardrail_warning_count", "guardrails"),
        ("soft_warning_count", "soft_warnings"),
        ("output_dir", "output"),
    ]))
    lines.extend([
        "",
        "## Manual Review Required",
        "",
    ])
    lines.extend(markdown_table_from_rows(manual_rows, [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("hard_blockers", "hard_blockers"),
        ("hard_blocker_count", "hard_count"),
        ("manual_price_verification_required", "manual_price_verification"),
        ("valuation_reliability", "valuation_reliability"),
        ("quality_report", "quality_report"),
    ]))
    lines.extend([
        "",
        "## Soft Warnings / Monitor",
        "",
    ])
    lines.extend(markdown_table_from_rows(soft_rows, [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("quality_status", "status"),
        ("soft_warnings", "soft_warnings"),
        ("soft_warning_count", "soft_count"),
        ("guardrail_warning_count", "guardrails"),
        ("price_data_reliability", "price_reliability"),
        ("valuation_reliability", "valuation_reliability"),
        ("output_dir", "output"),
    ]))
    lines.extend([
        "",
        "## Needs Rerun",
        "",
    ])
    lines.extend(markdown_table_from_rows(rerun_rows, [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("quality_reason", "reason"),
        ("llm_fetch_failed_count", "llm_failed"),
        ("market_fetch_failed_count", "market_failed"),
        ("evidence_fetch_failed_count", "evidence_failed"),
        ("output_dir", "output"),
    ]))
    lines.extend([
        "",
        "## Full Table",
        "",
    ])
    lines.extend(markdown_table_from_rows(full_rows, [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("quality_status", "status"),
        ("action", "action"),
        ("suggested_position_pct", "position"),
        ("evidence_quality_score", "evidence"),
        ("market_data_reliability", "market data"),
        ("financial_statement_reliability", "financials"),
        ("valuation_reliability", "valuation reliability"),
        ("weighted_investment_score", "weighted"),
        ("chokepoint_adjusted_score", "chokepoint"),
        ("serenity_thesis_quality", "serenity"),
        ("chokepoint_evidence_level", "cp evidence"),
        ("scout_recommendation", "scout"),
        ("chokepoint_overlay_applied", "overlay"),
        ("valuation_framework_type", "framework"),
        ("output_dir", "output"),
    ]))
    return "\n".join(lines)


def build_batch_summary_files(
    results: List[Dict[str, Any]],
    output_root: str,
    summary_dir: Path,
) -> Dict[str, str]:
    ensure_dir(summary_dir)
    timestamp = now_str()
    flat_rows = [classify_summary_quality(flatten_decision_for_summary(row)) for row in results]
    df = sort_batch_summary_df(pd.DataFrame(flat_rows))

    batch_summary_csv = summary_dir / f"batch_summary_{timestamp}.csv"
    batch_summary_md = summary_dir / f"batch_summary_{timestamp}.md"
    top_ideas_csv = summary_dir / f"top_ideas_{timestamp}.csv"
    rerun_queue_csv = summary_dir / f"rerun_queue_{timestamp}.csv"

    df.to_csv(batch_summary_csv, index=False, encoding="utf-8")
    save_text(batch_summary_md, build_batch_summary_markdown(df))

    top_ideas_df = df[df.get("quality_status") == "deep_research_candidate"] if not df.empty else df
    top_ideas_df.to_csv(top_ideas_csv, index=False, encoding="utf-8")

    if df.empty:
        rerun_df = pd.DataFrame(columns=["ticker", "company_name", "reason", "suggested_rerun_mode", "output_dir"])
    else:
        rerun_mask = df.get("needs_rerun", pd.Series(False, index=df.index)).map(summary_bool) | df.get(
            "manual_price_verification_required",
            pd.Series(False, index=df.index),
        ).map(summary_bool)
        rerun_df = df[rerun_mask].copy()
        rerun_df["reason"] = rerun_df.get("quality_reason", "")
        rerun_df["suggested_rerun_mode"] = rerun_df.apply(lambda row: suggested_rerun_mode(row.to_dict()), axis=1)
        rerun_columns = ["ticker", "company_name", "reason", "suggested_rerun_mode", "output_dir"]
        rerun_df = rerun_df.reindex(columns=rerun_columns)
    rerun_df.to_csv(rerun_queue_csv, index=False, encoding="utf-8")

    return {
        "batch_summary_csv": str(batch_summary_csv),
        "batch_summary_md": str(batch_summary_md),
        "top_ideas_csv": str(top_ideas_csv),
        "rerun_queue_csv": str(rerun_queue_csv),
    }


DEFAULT_CHOKEPOINT_TEST_WATCHLIST_ROWS = [
    {
        "ticker": "WDC",
        "name": "Western Digital",
        "theme": "Nearline HDD AI Data Storage Infrastructure",
        "market": "US",
    },
    {
        "ticker": "STX",
        "name": "Seagate",
        "theme": "Nearline HDD AI Data Storage Infrastructure",
        "market": "US",
    },
    {
        "ticker": "CIEN",
        "name": "Ciena",
        "theme": "Optical Networking AI Data Center Interconnect",
        "market": "US",
    },
    {
        "ticker": "FN",
        "name": "Fabrinet",
        "theme": "Optical Manufacturing AI Data Center",
        "market": "US",
    },
    {
        "ticker": "ETN",
        "name": "Eaton",
        "theme": "Data Center Electrical Power Infrastructure",
        "market": "US",
    },
    {
        "ticker": "NVT",
        "name": "nVent",
        "theme": "Data Center Electrical Enclosures Infrastructure",
        "market": "US",
    },
    {
        "ticker": "AMAT",
        "name": "Applied Materials",
        "theme": "Semiconductor Equipment WFE AI Infrastructure",
        "market": "US",
    },
    {
        "ticker": "LRCX",
        "name": "Lam Research",
        "theme": "Semiconductor Equipment WFE AI Infrastructure",
        "market": "US",
    },
    {
        "ticker": "KLAC",
        "name": "KLA",
        "theme": "Semiconductor Equipment Inspection Metrology AI Infrastructure",
        "market": "US",
    },
]


def create_default_chokepoint_test_watchlist(path: str) -> None:
    p = Path(path)
    if p.exists():
        console.print(f"[cyan]Default Chokepoint test watchlist already exists:[/cyan] {p}")
        return
    ensure_dir(p.parent if str(p.parent) else Path("."))
    pd.DataFrame(DEFAULT_CHOKEPOINT_TEST_WATCHLIST_ROWS).to_csv(p, index=False, encoding="utf-8")
    console.print(f"[bold green]Created default Chokepoint test watchlist:[/bold green] {p}")


CHOKEPOINT_ABTEST_ACTION_RANK = {
    "avoid": -1,
    "manual_price_verification_required": -1,
    "watchlist": 0,
    "trim_existing": 0,
    "tracking_position": 1,
    "hold_existing": 1,
    "starter_position": 2,
    "buy": 3,
}


def chokepoint_abtest_action_rank(action: Any) -> int:
    return CHOKEPOINT_ABTEST_ACTION_RANK.get(str(action or "").strip(), 0)


def _abtest_value(row: pd.Series, *columns: str, default: Any = "") -> Any:
    for col in columns:
        if col in row.index and not summary_is_missing(row.get(col)):
            return row.get(col)
    return default


def _abtest_numeric(row: pd.Series, *columns: str, default: float = 0.0) -> float:
    for col in columns:
        if col in row.index:
            value = safe_float(row.get(col))
            if value is not None:
                return value
    return default


def _abtest_reliability_ok(value: Any) -> bool:
    return str(value or "").strip().lower() in {"high", "medium"}


def compare_chokepoint_abtest(
    baseline_csv: str,
    treatment_csv: str,
    output_dir: Path,
    run_id: str,
) -> Dict[str, Any]:
    ensure_dir(output_dir)
    base_df = pd.read_csv(baseline_csv)
    choke_df = pd.read_csv(treatment_csv)
    merged = base_df.merge(choke_df, on="ticker", how="outer", suffixes=("_base", "_choke"))

    rows: List[Dict[str, Any]] = []
    for _, row in merged.iterrows():
        action_base = str(_abtest_value(row, "action_base", "action", default="")).strip()
        action_choke = str(_abtest_value(row, "action_choke", "action", default="")).strip()
        position_base = _abtest_numeric(row, "suggested_position_pct_base", "position_base")
        position_choke = _abtest_numeric(row, "suggested_position_pct_choke", "position_choke")
        position_delta = safe_float(position_choke - position_base) or 0.0
        action_rank_base = chokepoint_abtest_action_rank(action_base)
        action_rank_choke = chokepoint_abtest_action_rank(action_choke)
        action_rank_delta = action_rank_choke - action_rank_base

        evidence_quality_score = _abtest_numeric(row, "evidence_quality_score_choke", "evidence_quality_score_base")
        evidence_level = str(_abtest_value(row, "chokepoint_evidence_level_choke", "chokepoint_evidence_level", default="")).strip()
        manual_price_verification = summary_bool(_abtest_value(
            row,
            "manual_price_verification_required_choke",
            "manual_price_verification_required",
            default=False,
        ))
        valuation_reliability = str(_abtest_value(row, "valuation_reliability_choke", "valuation_reliability_base", default="")).strip()
        market_data_reliability = str(_abtest_value(row, "market_data_reliability_choke", "market_data_reliability_base", default="")).strip()
        financial_statement_reliability = str(_abtest_value(
            row,
            "financial_statement_reliability_choke",
            "financial_statement_reliability_base",
            default="",
        )).strip()
        price_fetch_reliability = str(_abtest_value(
            row,
            "price_data_reliability_from_fetch_choke",
            "price_data_reliability_from_fetch_base",
            default="",
        )).strip()
        overlay_applied = summary_bool(_abtest_value(row, "chokepoint_overlay_applied_choke", "chokepoint_overlay_applied", default=False))
        promoted = action_rank_delta > 0 or position_delta > 0
        downgraded = action_rank_delta < 0 or position_delta < 0
        guardrail_blocked = overlay_applied and (
            position_delta <= 0
            or action_choke in {"watchlist", "manual_price_verification_required"}
        )
        suspicious_promotion = promoted and (
            evidence_level in {"hypothesis_only", "insufficient"}
            or manual_price_verification
            or valuation_reliability.lower() == "low"
            or market_data_reliability.lower() == "low"
            or financial_statement_reliability.lower() == "low"
            or price_fetch_reliability.lower() == "low"
            or evidence_quality_score < 7
        )
        good_promotion = promoted and (
            evidence_level in {"primary_supported", "secondary_supported"}
            and evidence_quality_score >= 7
            and not manual_price_verification
            and _abtest_reliability_ok(valuation_reliability)
            and _abtest_reliability_ok(market_data_reliability)
            and _abtest_reliability_ok(financial_statement_reliability)
            and _abtest_reliability_ok(price_fetch_reliability)
        )

        rows.append({
            "ticker": row.get("ticker"),
            "company_name": _abtest_value(row, "company_name_choke", "company_name_base", "company_name"),
            "theme": _abtest_value(row, "theme_choke", "theme_base", "theme"),
            "action_base": action_base,
            "action_choke": action_choke,
            "position_base": position_base,
            "position_choke": position_choke,
            "position_delta": position_delta,
            "quality_status_base": _abtest_value(row, "quality_status_base", "quality_status"),
            "quality_status_choke": _abtest_value(row, "quality_status_choke", "quality_status"),
            "evidence_quality_score": evidence_quality_score,
            "valuation_attractiveness_score_base": _abtest_numeric(row, "valuation_attractiveness_score_base"),
            "valuation_attractiveness_score_choke": _abtest_numeric(row, "valuation_attractiveness_score_choke"),
            "ai_beneficiary_score_base": _abtest_numeric(row, "ai_beneficiary_score_base"),
            "ai_beneficiary_score_choke": _abtest_numeric(row, "ai_beneficiary_score_choke"),
            "competitive_position_score_base": _abtest_numeric(row, "competitive_position_score_base"),
            "competitive_position_score_choke": _abtest_numeric(row, "competitive_position_score_choke"),
            "chokepoint_score": _abtest_numeric(row, "chokepoint_score_choke", "chokepoint_score", default=np.nan),
            "chokepoint_adjusted_score": _abtest_numeric(row, "chokepoint_adjusted_score_choke", "chokepoint_adjusted_score", default=np.nan),
            "weighted_investment_score": _abtest_numeric(row, "weighted_investment_score_choke", "weighted_investment_score", default=np.nan),
            "serenity_thesis_quality": _abtest_value(row, "serenity_thesis_quality_choke", "serenity_thesis_quality"),
            "chokepoint_evidence_level": evidence_level,
            "deep_research_priority": _abtest_value(row, "deep_research_priority_choke", "deep_research_priority"),
            "scout_recommendation": _abtest_value(row, "scout_recommendation_choke", "scout_recommendation"),
            "chokepoint_overlay_applied": overlay_applied,
            "chokepoint_overlay_reason": _abtest_value(row, "chokepoint_overlay_reason_choke", "chokepoint_overlay_reason"),
            "manual_price_verification_required": manual_price_verification,
            "market_data_reliability": market_data_reliability,
            "financial_statement_reliability": financial_statement_reliability,
            "price_data_reliability_from_fetch": price_fetch_reliability,
            "valuation_reliability": valuation_reliability,
            "guardrail_warnings_choke": _abtest_value(row, "guardrail_warnings_choke", "guardrail_warnings"),
            "market_awareness_score": _abtest_numeric(row, "market_awareness_score_choke", "market_awareness_score", default=np.nan),
            "valuation_risk_score": _abtest_numeric(row, "valuation_risk_score_choke", "valuation_risk_score", default=np.nan),
            "action_rank_base": action_rank_base,
            "action_rank_choke": action_rank_choke,
            "action_rank_delta": action_rank_delta,
            "promoted_by_chokepoint": promoted,
            "downgraded_by_chokepoint": downgraded,
            "unchanged": not promoted and not downgraded,
            "guardrail_blocked_chokepoint": guardrail_blocked,
            "suspicious_promotion": suspicious_promotion,
            "good_promotion": good_promotion,
            "output_dir_base": _abtest_value(row, "output_dir_base", "output_dir"),
            "output_dir_choke": _abtest_value(row, "output_dir_choke", "output_dir"),
        })

    comparison_df = pd.DataFrame(rows)
    comparison_csv = output_dir / f"chokepoint_abtest_comparison_{run_id}.csv"
    comparison_df.to_csv(comparison_csv, index=False, encoding="utf-8")
    return {
        "comparison_csv": str(comparison_csv),
        "comparison_df": comparison_df,
    }


def build_chokepoint_abtest_report(
    comparison_df: pd.DataFrame,
    baseline_csv: str,
    treatment_csv: str,
    run_id: str,
) -> str:
    company_count = len(comparison_df.index)
    promoted_count = int(comparison_df.get("promoted_by_chokepoint", pd.Series(dtype=bool)).map(summary_bool).sum()) if company_count else 0
    downgraded_count = int(comparison_df.get("downgraded_by_chokepoint", pd.Series(dtype=bool)).map(summary_bool).sum()) if company_count else 0
    unchanged_count = int(comparison_df.get("unchanged", pd.Series(dtype=bool)).map(summary_bool).sum()) if company_count else 0
    good_count = int(comparison_df.get("good_promotion", pd.Series(dtype=bool)).map(summary_bool).sum()) if company_count else 0
    suspicious_count = int(comparison_df.get("suspicious_promotion", pd.Series(dtype=bool)).map(summary_bool).sum()) if company_count else 0
    guardrail_blocked_count = int(comparison_df.get("guardrail_blocked_chokepoint", pd.Series(dtype=bool)).map(summary_bool).sum()) if company_count else 0
    average_position_delta = pd.to_numeric(comparison_df.get("position_delta", pd.Series(dtype=float)), errors="coerce").mean() if company_count else np.nan
    average_weighted_score = pd.to_numeric(comparison_df.get("weighted_investment_score", pd.Series(dtype=float)), errors="coerce").mean() if company_count else np.nan
    average_chokepoint_score = pd.to_numeric(comparison_df.get("chokepoint_adjusted_score", pd.Series(dtype=float)), errors="coerce").mean() if company_count else np.nan

    def rows_where(column: str) -> List[Dict[str, Any]]:
        if comparison_df.empty or column not in comparison_df.columns:
            return []
        return comparison_df[comparison_df[column].map(summary_bool)].to_dict("records")

    top_chokepoint_rows = comparison_df.copy()
    if not top_chokepoint_rows.empty:
        top_chokepoint_rows["chokepoint_adjusted_score"] = pd.to_numeric(top_chokepoint_rows["chokepoint_adjusted_score"], errors="coerce")
        top_chokepoint_rows = top_chokepoint_rows.sort_values("chokepoint_adjusted_score", ascending=False, na_position="last")

    lines = [
        "# Chokepoint A/B Test Report",
        "",
        "## Overview",
        f"- run_id: {run_id}",
        f"- baseline_csv: {baseline_csv}",
        f"- treatment_csv: {treatment_csv}",
        f"- company_count: {company_count}",
        f"- promoted_count: {promoted_count}",
        f"- downgraded_count: {downgraded_count}",
        f"- unchanged_count: {unchanged_count}",
        f"- good_promotion_count: {good_count}",
        f"- suspicious_promotion_count: {suspicious_count}",
        f"- guardrail_blocked_count: {guardrail_blocked_count}",
        f"- average_position_delta: {average_position_delta:.2f}" if not pd.isna(average_position_delta) else "- average_position_delta: N/A",
        f"- average_weighted_investment_score: {average_weighted_score:.2f}" if not pd.isna(average_weighted_score) else "- average_weighted_investment_score: N/A",
        f"- average_chokepoint_adjusted_score: {average_chokepoint_score:.2f}" if not pd.isna(average_chokepoint_score) else "- average_chokepoint_adjusted_score: N/A",
        "",
        "## Promotions",
        "",
    ]
    lines.extend(markdown_table_from_rows(rows_where("promoted_by_chokepoint"), [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("action_base", "action_base"),
        ("action_choke", "action_choke"),
        ("position_base", "position_base"),
        ("position_choke", "position_choke"),
        ("chokepoint_score", "chokepoint_score"),
        ("chokepoint_adjusted_score", "adjusted_score"),
        ("weighted_investment_score", "weighted_score"),
        ("chokepoint_evidence_level", "evidence_level"),
        ("chokepoint_overlay_reason", "overlay_reason"),
    ]))
    lines.extend(["", "## Good Promotions", ""])
    lines.extend(markdown_table_from_rows(rows_where("good_promotion"), [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("action_base", "action_base"),
        ("action_choke", "action_choke"),
        ("position_base", "position_base"),
        ("position_choke", "position_choke"),
        ("chokepoint_adjusted_score", "adjusted_score"),
        ("weighted_investment_score", "weighted_score"),
        ("chokepoint_evidence_level", "evidence_level"),
        ("chokepoint_overlay_reason", "overlay_reason"),
    ]))
    lines.extend(["", "## Suspicious Promotions", ""])
    lines.extend(markdown_table_from_rows(rows_where("suspicious_promotion"), [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("chokepoint_evidence_level", "evidence_level"),
        ("evidence_quality_score", "evidence_quality_score"),
        ("valuation_reliability", "valuation_reliability"),
        ("manual_price_verification_required", "manual_price_verification_required"),
        ("guardrail_warnings_choke", "guardrail_warnings"),
    ]))
    lines.extend(["", "## Guardrail Blocked Chokepoint Ideas", ""])
    lines.extend(markdown_table_from_rows(rows_where("guardrail_blocked_chokepoint"), [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("action_base", "action_base"),
        ("action_choke", "action_choke"),
        ("position_delta", "position_delta"),
        ("chokepoint_adjusted_score", "adjusted_score"),
        ("weighted_investment_score", "weighted_score"),
        ("chokepoint_overlay_reason", "overlay_reason"),
        ("guardrail_warnings_choke", "guardrail_warnings"),
    ]))
    lines.extend(["", "## Top Chokepoint Scores", ""])
    lines.extend(markdown_table_from_rows(top_chokepoint_rows.to_dict("records"), [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("chokepoint_adjusted_score", "adjusted_score"),
        ("weighted_investment_score", "weighted_score"),
        ("serenity_thesis_quality", "thesis_quality"),
        ("chokepoint_evidence_level", "evidence_level"),
        ("market_awareness_score", "market_awareness"),
        ("valuation_risk_score", "valuation_risk"),
        ("action_choke", "action_choke"),
        ("position_choke", "position_choke"),
    ]))
    lines.extend(["", "## Full Comparison Table", ""])
    lines.extend(markdown_table_from_rows(comparison_df.to_dict("records"), [
        ("ticker", "ticker"),
        ("company_name", "company"),
        ("action_base", "action_base"),
        ("action_choke", "action_choke"),
        ("position_delta", "position_delta"),
        ("quality_status_base", "quality_status_base"),
        ("quality_status_choke", "quality_status_choke"),
        ("weighted_investment_score", "weighted_score"),
        ("promoted_by_chokepoint", "promoted"),
        ("suspicious_promotion", "suspicious"),
        ("output_dir_choke", "output"),
    ]))
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- If many suspicious promotions appear, the Chokepoint module may be too aggressive.",
        "- If many guardrail blocked rows appear, the PM guardrails are still doing useful safety work.",
        "- If good promotions are concentrated in real bottleneck companies, the Chokepoint module is likely useful.",
        "- If all companies get high chokepoint scores, the scoring rubric is too loose.",
        "- If no promotions occur, the module may be too conservative or the PM logic already captures the same signal.",
    ])
    return "\n".join(lines)


def save_chokepoint_abtest_manifest(
    *,
    output_dir: Path,
    run_id: str,
    watchlist_path: str,
    baseline_summary_csv: str,
    treatment_summary_csv: str,
    comparison_csv: str,
    report_md: str,
    baseline_output_root: str,
    treatment_output_root: str,
    limit: Optional[int],
    max_peers: Optional[int],
    no_reuse: bool,
    comparison_df: pd.DataFrame,
) -> Dict[str, Any]:
    manifest = {
        "run_id": run_id,
        "created_at": iso_now(),
        "watchlist_path": watchlist_path,
        "baseline_summary_csv": baseline_summary_csv,
        "treatment_summary_csv": treatment_summary_csv,
        "comparison_csv": comparison_csv,
        "report_md": report_md,
        "baseline_output_root": baseline_output_root,
        "treatment_output_root": treatment_output_root,
        "limit": limit,
        "max_peers": max_peers,
        "no_reuse": no_reuse,
        "promoted_count": int(comparison_df.get("promoted_by_chokepoint", pd.Series(dtype=bool)).map(summary_bool).sum()) if not comparison_df.empty else 0,
        "suspicious_promotion_count": int(comparison_df.get("suspicious_promotion", pd.Series(dtype=bool)).map(summary_bool).sum()) if not comparison_df.empty else 0,
        "good_promotion_count": int(comparison_df.get("good_promotion", pd.Series(dtype=bool)).map(summary_bool).sum()) if not comparison_df.empty else 0,
        "guardrail_blocked_count": int(comparison_df.get("guardrail_blocked_chokepoint", pd.Series(dtype=bool)).map(summary_bool).sum()) if not comparison_df.empty else 0,
    }
    manifest_path = output_dir / f"chokepoint_abtest_manifest_{run_id}.json"
    save_json(manifest_path, manifest)
    manifest["manifest_json"] = str(manifest_path)
    return manifest


def _restore_env_var(name: str, value: Optional[str]) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def run_chokepoint_abtest(
    watchlist_path: str,
    portfolio_path: str,
    output_root: str,
    limit: Optional[int],
    max_peers: Optional[int],
    no_reuse: bool,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    global CHOKEPOINT_SCOUT_ENABLED, REUSE_TODAY_OUTPUTS
    run_id = run_id or f"chokepoint_abtest_{now_str()}"
    abtest_dir = Path(output_root) / today_str() / run_id
    baseline_dir = abtest_dir / "baseline"
    treatment_dir = abtest_dir / "with_chokepoint"
    ensure_dir(baseline_dir)
    ensure_dir(treatment_dir)

    saved_env = {name: os.environ.get(name) for name in ["CHOKEPOINT_SCOUT_ENABLED", "MAX_PEERS", "REUSE_TODAY_OUTPUTS"]}
    saved_chokepoint_enabled = CHOKEPOINT_SCOUT_ENABLED
    saved_reuse = REUSE_TODAY_OUTPUTS
    try:
        if max_peers is not None:
            os.environ["MAX_PEERS"] = str(max_peers)
        if no_reuse:
            REUSE_TODAY_OUTPUTS = False
            os.environ["REUSE_TODAY_OUTPUTS"] = "0"

        CHOKEPOINT_SCOUT_ENABLED = False
        os.environ["CHOKEPOINT_SCOUT_ENABLED"] = "0"
        console.print(Panel.fit("A/B baseline: Chokepoint disabled", style="bold blue"))
        baseline_paths = run_batch(
            watchlist_path,
            portfolio_path,
            str(baseline_dir),
            limit,
            summary_dir=baseline_dir,
        )

        CHOKEPOINT_SCOUT_ENABLED = True
        os.environ["CHOKEPOINT_SCOUT_ENABLED"] = "1"
        console.print(Panel.fit("A/B treatment: Chokepoint enabled", style="bold blue"))
        treatment_paths = run_batch(
            watchlist_path,
            portfolio_path,
            str(treatment_dir),
            limit,
            summary_dir=treatment_dir,
        )
    finally:
        for name, value in saved_env.items():
            _restore_env_var(name, value)
        CHOKEPOINT_SCOUT_ENABLED = saved_chokepoint_enabled
        REUSE_TODAY_OUTPUTS = saved_reuse

    baseline_csv = baseline_paths["batch_summary_csv"]
    treatment_csv = treatment_paths["batch_summary_csv"]
    comparison = compare_chokepoint_abtest(baseline_csv, treatment_csv, abtest_dir, run_id)
    report_md_path = abtest_dir / f"chokepoint_abtest_report_{run_id}.md"
    save_text(report_md_path, build_chokepoint_abtest_report(
        comparison["comparison_df"],
        baseline_csv,
        treatment_csv,
        run_id,
    ))
    manifest = save_chokepoint_abtest_manifest(
        output_dir=abtest_dir,
        run_id=run_id,
        watchlist_path=watchlist_path,
        baseline_summary_csv=baseline_csv,
        treatment_summary_csv=treatment_csv,
        comparison_csv=comparison["comparison_csv"],
        report_md=str(report_md_path),
        baseline_output_root=str(baseline_dir),
        treatment_output_root=str(treatment_dir),
        limit=limit,
        max_peers=max_peers,
        no_reuse=no_reuse,
        comparison_df=comparison["comparison_df"],
    )
    manifest.update({
        "baseline_summary_csv": baseline_csv,
        "treatment_summary_csv": treatment_csv,
        "comparison_csv": comparison["comparison_csv"],
        "report_md": str(report_md_path),
    })
    console.print(Panel.fit("Chokepoint A/B test completed", style="bold green"))
    console.print(f"[bold]Baseline summary:[/bold] {baseline_csv}")
    console.print(f"[bold]Treatment summary:[/bold] {treatment_csv}")
    console.print(f"[bold]Comparison CSV:[/bold] {comparison['comparison_csv']}")
    console.print(f"[bold]Report MD:[/bold] {report_md_path}")
    console.print(f"[bold]Manifest JSON:[/bold] {manifest['manifest_json']}")
    return manifest


def run_chokepoint_abtest_compare_only(
    baseline_csv: str,
    treatment_csv: str,
    output_root: str,
    run_id: Optional[str] = None,
    watchlist_path: str = "",
) -> Dict[str, Any]:
    run_id = run_id or f"chokepoint_abtest_{now_str()}"
    output_dir = Path(output_root) / today_str() / run_id
    ensure_dir(output_dir)
    comparison = compare_chokepoint_abtest(baseline_csv, treatment_csv, output_dir, run_id)
    report_md_path = output_dir / f"chokepoint_abtest_report_{run_id}.md"
    save_text(report_md_path, build_chokepoint_abtest_report(
        comparison["comparison_df"],
        baseline_csv,
        treatment_csv,
        run_id,
    ))
    manifest = save_chokepoint_abtest_manifest(
        output_dir=output_dir,
        run_id=run_id,
        watchlist_path=watchlist_path,
        baseline_summary_csv=baseline_csv,
        treatment_summary_csv=treatment_csv,
        comparison_csv=comparison["comparison_csv"],
        report_md=str(report_md_path),
        baseline_output_root=str(Path(baseline_csv).parent),
        treatment_output_root=str(Path(treatment_csv).parent),
        limit=None,
        max_peers=None,
        no_reuse=False,
        comparison_df=comparison["comparison_df"],
    )
    manifest.update({
        "baseline_summary_csv": baseline_csv,
        "treatment_summary_csv": treatment_csv,
        "comparison_csv": comparison["comparison_csv"],
        "report_md": str(report_md_path),
    })
    console.print(Panel.fit("Chokepoint A/B compare-only completed", style="bold green"))
    console.print(f"[bold]Comparison CSV:[/bold] {comparison['comparison_csv']}")
    console.print(f"[bold]Report MD:[/bold] {report_md_path}")
    console.print(f"[bold]Manifest JSON:[/bold] {manifest['manifest_json']}")
    return manifest


def run_fact_scout(
    watchlist_path: str,
    output_root: str,
    limit: Optional[int] = None,
    ticker: str = "",
    name: str = "",
    theme: str = "AI Supply Chain",
    market: str = "US",
    cache_path: Optional[str] = None,
) -> None:
    if ticker:
        rows = [{
            "ticker": ticker,
            "name": clean_company_name(ticker, name),
            "theme": theme,
            "market": market,
        }]
    else:
        df = read_watchlist_df(watchlist_path)
        rows = df.to_dict("records")
        if limit is not None:
            rows = rows[:limit]

    scout_dir = Path(output_root) / today_str() / f"fact_scout_{now_str()}"
    ensure_dir(scout_dir)
    ensure_fact_cache_schema(cache_path)

    summary_rows: List[Dict[str, Any]] = []
    for raw_row in rows:
        row_ticker = str(raw_row.get("ticker") or "").strip()
        if not row_ticker:
            continue
        row_name = clean_company_name(row_ticker, raw_row.get("name"))
        row_theme = str(raw_row.get("theme") or theme or "AI Supply Chain")
        row_market = str(raw_row.get("market") or market or "")
        safe_ticker = row_ticker.replace(".", "_").replace("/", "_")
        ticker_dir = scout_dir / safe_ticker
        ensure_dir(ticker_dir)

        console.print(Panel.fit(f"Fact scout: {row_name} / {row_ticker}", style="bold blue"))
        llm_diagnostics: List[Dict[str, Any]] = []
        try:
            fact_cache_report = build_fact_cache_report(row_ticker, row_name, row_theme, row_market, cache_path=cache_path)
            incremental_search_enabled = env_flag("FACT_CACHE_INCREMENTAL_SEARCH", True)
            query_type_filter = set(fact_cache_report.get("missing_or_stale_query_types") or []) if incremental_search_enabled else None
            evidence_md = get_evidence_context(row_ticker, row_name, row_theme, row_market, query_type_filter=query_type_filter)
            evidence_diagnostics = parse_evidence_search_diagnostics(evidence_md)
            evidence_quality = score_evidence_quality_from_text(evidence_md)
            facts = extract_facts_from_evidence_context(
                row_ticker,
                row_name,
                row_theme,
                row_market,
                evidence_md,
                diagnostics=llm_diagnostics,
            )
            saved_count = save_fact_cache_records(facts, cache_path=cache_path)
            cached_facts = load_cached_facts(row_ticker, cache_path=cache_path)
            evidence_quality = merge_evidence_quality_with_cached_facts(evidence_quality, cached_facts)
            fact_cache_report_after = build_fact_cache_report(row_ticker, row_name, row_theme, row_market, cache_path=cache_path)
            status = "ok"
            error = ""
        except Exception as exc:
            evidence_md = ""
            evidence_diagnostics = []
            evidence_quality = score_evidence_quality_from_text("")
            facts = []
            cached_facts = load_cached_facts(row_ticker, cache_path=cache_path)
            fact_cache_report = build_fact_cache_report(row_ticker, row_name, row_theme, row_market, cache_path=cache_path)
            fact_cache_report_after = fact_cache_report
            saved_count = 0
            status = "failed"
            error = str(exc)
            console.print(f"[yellow]Fact scout failed for {row_ticker}: {console_safe_text(exc)}[/yellow]")

        save_text(ticker_dir / "evidence_context.md", evidence_md)
        save_json(ticker_dir / "evidence_diagnostics.json", evidence_diagnostics)
        save_json(ticker_dir / "evidence_quality.json", evidence_quality)
        save_json(ticker_dir / "fresh_facts.json", facts)
        save_json(ticker_dir / "cached_facts.json", cached_facts)
        save_text(ticker_dir / "cached_facts.md", facts_to_markdown("Cached Fact Base", cached_facts))
        save_json(ticker_dir / "fact_cache_report_before.json", fact_cache_report)
        save_text(ticker_dir / "fact_cache_report_before.md", fact_cache_report_to_markdown(fact_cache_report))
        save_json(ticker_dir / "fact_cache_report_after.json", fact_cache_report_after)
        save_text(ticker_dir / "fact_cache_report_after.md", fact_cache_report_to_markdown(fact_cache_report_after))
        save_json(ticker_dir / "llm_diagnostics.json", llm_diagnostics)

        ev_diag_summary = (evidence_quality.get("evidence_search_diagnostics") or {}).get("evidence_search_diagnostics_summary") or {}
        summary_rows.append({
            "ticker": row_ticker,
            "company_name": row_name,
            "theme": row_theme,
            "market": row_market,
            "status": status,
            "fresh_facts": len(facts),
            "saved_facts": saved_count,
            "cached_facts": len(cached_facts),
            "missing_query_types_before": fact_cache_report.get("missing_or_stale_query_type_count", 0),
            "missing_query_types_after": fact_cache_report_after.get("missing_or_stale_query_type_count", 0),
            "evidence_quality_score": evidence_quality.get("evidence_quality_score"),
            "evidence_search_failed_count": ev_diag_summary.get("failed", 0),
            "output_dir": str(ticker_dir),
            "error": error,
        })

    save_json(scout_dir / "fact_scout_summary.json", summary_rows)
    lines = [
        "# Fact Scout Summary",
        "",
        f"- Created at: {iso_now()}",
        f"- Cache path: {fact_cache_db_path(cache_path)}",
        f"- Companies processed: {len(summary_rows)}",
        "",
        "| Ticker | Company | Status | Fresh Facts | Saved Facts | Cached Facts | Missing Before | Missing After | Evidence Score | Search Failed | Output |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row.get('ticker')} | {markdown_cell(row.get('company_name'), 40)} | {row.get('status')} | "
            f"{row.get('fresh_facts')} | {row.get('saved_facts')} | {row.get('cached_facts')} | "
            f"{row.get('missing_query_types_before')} | {row.get('missing_query_types_after')} | "
            f"{row.get('evidence_quality_score')} | {row.get('evidence_search_failed_count')} | {row.get('output_dir')} |"
        )
    save_text(scout_dir / "fact_scout_summary.md", "\n".join(lines))
    console.print(Panel.fit("Fact scout completed", style="bold green"))
    console.print(f"[bold]Scout folder:[/bold] {scout_dir}")
    console.print(f"[bold]Fact cache:[/bold] {fact_cache_db_path(cache_path)}")


def run_company_research(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    portfolio_path: str,
    output_root: str,
    watchlist_path: str = DEFAULT_WATCHLIST_PATH,
    group_id: Optional[str] = None,
    group_role: str = "target",
    peer_context_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    name = clean_company_name(ticker, name)
    if REUSE_TODAY_OUTPUTS:
        existing_dir = latest_existing_output_dir(ticker, output_root)
        if existing_dir:
            console.print(f"[cyan]Reuse existing output for {ticker}:[/cyan] {existing_dir}")
            return row_from_existing_output(existing_dir, ticker, name, theme, market, group_id, group_role)

    console.print(Panel.fit(f"Running deep research agent: {name} / {ticker}", style="bold green"))

    out_dir = Path(output_root) / today_str() / f"{ticker.replace('.', '_').replace('/', '_')}_{now_str()}"
    ensure_dir(out_dir)

    console.print("[bold cyan]Step 1/9: Market snapshot[/bold cyan]")
    snapshot = get_market_snapshot(ticker)
    snapshot_md = snapshot_to_markdown(snapshot)
    fetch_reliability = {
        "market_data_reliability": snapshot.get("market_data_reliability"),
        "financial_statement_reliability": snapshot.get("financial_statement_reliability"),
        "price_data_reliability_from_fetch": snapshot.get("price_data_reliability_from_fetch"),
        "data_fetch_warnings": snapshot.get("data_fetch_warnings") or [],
    }
    data_fetch_md = "\n".join([
        "## Data Fetch Reliability",
        "",
        f"- Market data reliability: {fetch_reliability.get('market_data_reliability') or 'N/A'}",
        f"- Financial statement reliability: {fetch_reliability.get('financial_statement_reliability') or 'N/A'}",
        f"- Price data reliability from fetch: {fetch_reliability.get('price_data_reliability_from_fetch') or 'N/A'}",
        f"- Data fetch warnings: {', '.join(fetch_reliability.get('data_fetch_warnings') or []) or 'None'}",
        "",
        fetch_diagnostics_to_markdown("Market Data Fetch Diagnostics", snapshot.get("data_fetch_diagnostics") or []),
    ])
    price_sanity = build_price_sanity_check(snapshot)
    price_sanity_md = price_sanity_to_markdown(price_sanity)
    data_warnings = build_data_quality_warnings(snapshot)
    data_quality_md = warnings_to_markdown("Data Quality Warnings", data_warnings)
    valuation_bridge = build_industry_valuation_bridge(snapshot, theme=theme, peer_context_text="")
    valuation_bridge_md = valuation_bridge_to_markdown(valuation_bridge)
    save_json(out_dir / "market_snapshot.json", snapshot)
    save_text(out_dir / "market_snapshot.md", snapshot_md)

    console.print("[bold cyan]Step 2/9: Macro snapshot[/bold cyan]")
    macro_md = get_macro_snapshot()
    save_text(out_dir / "macro_snapshot.md", macro_md)

    console.print("[bold cyan]Step 3/9: Peer valuation context[/bold cyan]")
    if peer_context_rows:
        peer_md = build_peer_context_from_rows(
            ticker,
            peer_context_rows,
            selection_basis="actual companies in this research group",
        )
    else:
        peer_md = build_peer_context(ticker, name, theme, market, watchlist_path)
    save_text(out_dir / "peer_context.md", peer_md)

    console.print("[bold cyan]Step 4/9: Evidence search context[/bold cyan]")
    llm_fetch_diagnostics: List[Dict[str, Any]] = []
    initial_cached_facts = load_cached_facts(ticker)
    fact_cache_report = build_fact_cache_report(ticker, name, theme, market)
    incremental_search_enabled = env_flag("FACT_CACHE_INCREMENTAL_SEARCH", True)
    query_type_filter = set(fact_cache_report.get("missing_or_stale_query_types") or []) if incremental_search_enabled else None
    evidence_md = get_evidence_context(ticker, name, theme, market, query_type_filter=query_type_filter)
    evidence_diagnostics = parse_evidence_search_diagnostics(evidence_md)
    save_text(out_dir / "evidence_context.md", evidence_md)
    save_json(out_dir / "evidence_diagnostics.json", evidence_diagnostics)
    save_json(out_dir / "fact_cache_report_before.json", fact_cache_report)
    save_text(out_dir / "fact_cache_report_before.md", fact_cache_report_to_markdown(fact_cache_report))
    fresh_facts: List[Dict[str, Any]] = []
    if FACT_CACHE_ENABLED and os.getenv("FACT_EXTRACT_ON_SINGLE", "1").lower().strip() not in {"0", "false", "no", "off"}:
        try:
            fresh_facts = extract_facts_from_evidence_context(
                ticker,
                name,
                theme,
                market,
                evidence_md,
                diagnostics=llm_fetch_diagnostics,
            )
            save_fact_cache_records(fresh_facts)
        except Exception as e:
            console.print(f"[yellow]Fact extraction failed for {ticker}: {console_safe_text(e)}[/yellow]")
    cached_facts = load_cached_facts(ticker)
    evidence_quality = merge_evidence_quality_with_cached_facts(score_evidence_quality_from_text(evidence_md), cached_facts or initial_cached_facts)
    fact_cache_report_after = build_fact_cache_report(ticker, name, theme, market)
    cached_facts_md = facts_to_markdown("Cached Fact Base", cached_facts)
    save_json(out_dir / "fresh_facts.json", fresh_facts)
    save_json(out_dir / "cached_facts_used.json", cached_facts)
    save_text(out_dir / "cached_facts.md", cached_facts_md)
    save_json(out_dir / "fact_cache_report_after.json", fact_cache_report_after)
    save_text(out_dir / "fact_cache_report_after.md", fact_cache_report_to_markdown(fact_cache_report_after))

    save_text(out_dir / "ai_agent_demand_framework.md", AI_AGENT_DEMAND_FRAMEWORK)

    console.print("[bold cyan]Step 5/9: Chokepoint Scout[/bold cyan]")
    chokepoint_context_md, chokepoint_decision = run_chokepoint_scout(
        ticker=ticker,
        company_name=name,
        theme=theme,
        market=market,
        snapshot_md=snapshot_md,
        evidence_context=evidence_md,
        peer_context=peer_md,
        valuation_bridge_md=valuation_bridge_md,
        ai_agent_framework_md=AI_AGENT_DEMAND_FRAMEWORK,
        out_dir=out_dir,
        diagnostics=llm_fetch_diagnostics,
        enabled=CHOKEPOINT_SCOUT_ENABLED,
    )

    console.print("[bold cyan]Step 6/9: Portfolio recommendation boundary[/bold cyan]")
    console.print(f"[yellow]{PORTFOLIO_RECOMMENDATION_BOUNDARY_NOTICE}[/yellow]")
    portfolio_boundary_md = disabled_portfolio_context_notice()
    save_text(out_dir / "portfolio_context.md", portfolio_boundary_md)

    console.print("[bold cyan]Step 7/9: Deep PM memo via configured LLM[/bold cyan]")
    memo_prompt = build_pm_prompt(
        ticker=ticker,
        name=name,
        theme=theme,
        market=market,
        snapshot_md=snapshot_md,
        data_quality_md=data_quality_md,
        data_fetch_md=data_fetch_md,
        price_sanity_md=price_sanity_md,
        macro_md=macro_md,
        peer_md=peer_md,
        evidence_md=evidence_md,
        evidence_quality=evidence_quality,
        cached_facts_md=cached_facts_md,
        chokepoint_context_md=chokepoint_context_md,
        chokepoint_decision=chokepoint_decision,
        valuation_bridge_md=valuation_bridge_md,
        ai_agent_framework=AI_AGENT_DEMAND_FRAMEWORK,
    )
    save_text(out_dir / "memo_prompt.md", memo_prompt)
    pm_memo = call_llm("Deep PM Agent", memo_prompt, diagnostics=llm_fetch_diagnostics)
    pm_memo = "\n\n".join([data_quality_md, price_sanity_md, data_fetch_md, pm_memo])
    save_text(out_dir / "pm_memo.md", pm_memo)

    console.print("[bold cyan]Step 8/9: Structured JSON[/bold cyan]")
    try:
        json_raw = call_llm(
            "Structured JSON Agent",
            build_json_prompt(ticker, name, pm_memo),
            max_tokens=int(os.getenv("STRUCTURED_JSON_MAX_TOKENS", "3000")),
            decorate=False,
            json_mode=True,
            diagnostics=llm_fetch_diagnostics,
        )
        decision = repair_json_object(
            json_raw,
            schema_hint="Investment decision JSON object with rating, action, scores, thesis, valuation, risks, and final_pm_judgment.",
            diagnostics=llm_fetch_diagnostics,
        )
        decision["ticker"] = ticker
        decision["company_name"] = name
        decision = repair_decision_schema(decision, ticker, name, pm_memo, diagnostics=llm_fetch_diagnostics)
    except Exception as e:
        decision = fallback_decision(ticker, name, str(e))

    evidence_diag_summary = (evidence_quality.get("evidence_search_diagnostics") or {}).get("evidence_search_diagnostics_summary") or {}
    fetch_summary = {
        "market": fetch_diagnostics_summary(snapshot.get("data_fetch_diagnostics") or []),
        "evidence": evidence_diag_summary,
        "llm": fetch_diagnostics_summary(llm_fetch_diagnostics),
    }
    console.print("[bold cyan]Step 9/9: Weighted overlay, guardrails, and quality report[/bold cyan]")
    decision = apply_chokepoint_weighted_overlay(
        decision,
        chokepoint_decision,
        evidence_quality,
        price_sanity,
        fetch_reliability,
    )
    decision = apply_pm_guardrails(
        decision,
        evidence_quality,
        data_warnings,
        valuation_bridge,
        price_sanity=price_sanity,
        fetch_reliability=fetch_reliability,
    )
    decision = normalize_action_position_consistency(decision)
    decision.update({
        **fetch_reliability,
        "fetch_diagnostics_summary": fetch_summary,
    })
    save_json(out_dir / "llm_diagnostics.json", llm_fetch_diagnostics)
    pm_memo = "\n\n".join([pm_memo, build_guardrailed_decision_appendix(decision)])
    save_text(out_dir / "pm_memo.md", pm_memo)
    save_json(out_dir / "pm_decision.json", decision)
    quality_report_md = build_quality_report(ticker, name, evidence_quality, data_warnings, price_sanity, valuation_bridge, decision)
    quality_report_path = out_dir / "quality_report.md"
    save_text(quality_report_path, quality_report_md)

    full_package = "\n\n".join([
        f"# {RESEARCH_VERSION}: {name} / {ticker}",
        f"Generated at: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "Important: This is research support only, not trading advice. Verify all data before making decisions.",
        data_quality_md,
        price_sanity_md,
        data_fetch_md,
        fact_cache_report_to_markdown(fact_cache_report_after),
        "## Evidence Search Diagnostics",
        "```json",
        json.dumps(evidence_quality.get("evidence_search_diagnostics") or {}, ensure_ascii=False, indent=2),
        "```",
        fetch_diagnostics_to_markdown("LLM Diagnostics", llm_fetch_diagnostics),
        "## Evidence Quality",
        "```json",
        json.dumps(evidence_quality, ensure_ascii=False, indent=2),
        "```",
        chokepoint_context_md,
        "## Chokepoint Scout Decision",
        "```json",
        json.dumps(chokepoint_decision, ensure_ascii=False, indent=2),
        "```",
        valuation_bridge_md,
        snapshot_md,
        macro_md,
        peer_md,
        cached_facts_md,
        evidence_md,
        AI_AGENT_DEMAND_FRAMEWORK,
        portfolio_boundary_md,
        pm_memo,
        "## Structured Decision",
        "```json",
        json.dumps(decision, ensure_ascii=False, indent=2),
        "```",
    ])
    save_text(out_dir / "full_research_package.md", full_package)

    log_path = Path(output_root) / "research_log.csv"
    row = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "analysis_group_id": group_id or "",
        "analysis_group_role": group_role,
        "ticker": ticker,
        "company_name": name,
        "theme": theme,
        "market": market,
        "rating": decision.get("rating"),
        "action": decision.get("action"),
        "suggested_position_pct": decision.get("suggested_position_pct"),
        "confidence_score": decision.get("confidence_score"),
        "risk_score": decision.get("risk_score"),
        "price_data_reliability": decision.get("price_data_reliability"),
        "valuation_reliability": decision.get("valuation_reliability"),
        "manual_price_verification_required": decision.get("manual_price_verification_required"),
        "price_sanity_warning_count": len(decision.get("price_sanity_warnings") or []),
        "market_data_reliability": decision.get("market_data_reliability"),
        "financial_statement_reliability": decision.get("financial_statement_reliability"),
        "price_data_reliability_from_fetch": decision.get("price_data_reliability_from_fetch"),
        "data_fetch_warning_count": len(decision.get("data_fetch_warnings") or []),
        "market_fetch_failed_count": (fetch_summary.get("market") or {}).get("failed", 0),
        "evidence_fetch_failed_count": (fetch_summary.get("evidence") or {}).get("failed", 0),
        "llm_fetch_failed_count": (fetch_summary.get("llm") or {}).get("failed", 0),
        "output_dir": str(out_dir),
        "pm_memo": str(out_dir / "pm_memo.md"),
        "pm_decision_json": str(out_dir / "pm_decision.json"),
        "full_package": str(out_dir / "full_research_package.md"),
        "quality_report": str(quality_report_path),
        "decision": decision,
    }
    flat_summary_row = classify_summary_quality(flatten_decision_for_summary(row))
    row.update(flat_summary_row)

    if log_path.exists():
        old = pd.read_csv(log_path)
        log_row = {k: v for k, v in row.items() if k != "decision"}
        new = pd.concat([old, pd.DataFrame([log_row])], ignore_index=True)
    else:
        log_row = {k: v for k, v in row.items() if k != "decision"}
        new = pd.DataFrame([log_row])

    new.to_csv(log_path, index=False, encoding="utf-8")

    console.print(Panel.fit(f"Done: {name} / {ticker}", style="bold green"))
    console.print(f"[bold]Output folder:[/bold] {out_dir}")
    console.print(f"[bold]Decision:[/bold] {decision.get('rating')} | {decision.get('action')} | {decision.get('suggested_position_pct')}%")
    console.print("\n[bold yellow]Memo preview[/bold yellow]\n")
    console.print(console_safe_text(pm_memo[:2500]))

    return row


def run_single(
    ticker: str,
    name: str,
    theme: str,
    market: str,
    portfolio_path: str,
    output_root: str,
    watchlist_path: str = DEFAULT_WATCHLIST_PATH,
    analyzed_tickers: Optional[set] = None,
) -> List[Dict[str, Any]]:
    group_id = f"{ticker.replace('.', '_').replace('/', '_')}_{uuid.uuid4().hex[:8]}"
    max_peers = int(os.getenv("MAX_PEERS", "5"))
    analyzed_tickers = analyzed_tickers if analyzed_tickers is not None else set()

    target_cached = REUSE_TODAY_OUTPUTS and latest_existing_output_dir(ticker, output_root) is not None
    if max_peers <= 0:
        console.print(f"[cyan]Peer research disabled for {ticker}.[/cyan]")
        web_peer_rows = []
    elif target_cached:
        console.print(f"[cyan]Reuse mode: skip web peer discovery for cached target {ticker}.[/cyan]")
        web_peer_rows = []
    else:
        web_peer_rows = discover_peer_rows(ticker, name, theme, market, watchlist_path, max_peers=max_peers)
    peer_rows = list(web_peer_rows)
    seen_peer_tickers = {canonical_ticker_for(p.get("ticker")) for p in peer_rows}
    if max_peers > 0 and len(peer_rows) < max_peers:
        for peer in select_peer_rows(ticker, theme, watchlist_path, max_peers=max_peers * 2):
            norm = canonical_ticker_for(peer.get("ticker"))
            if not norm or norm in seen_peer_tickers:
                continue
            peer["group_role"] = "peer"
            peer_rows.append(peer)
            seen_peer_tickers.add(norm)
            if len(peer_rows) >= max_peers:
                break

    research_rows = [{
        "ticker": ticker,
        "name": clean_company_name(ticker, name),
        "theme": theme,
        "market": market,
        "group_role": "target",
        "peer_type": "target",
        "profit_pool": infer_profit_pool(theme),
    }]
    research_rows.extend({
        "ticker": peer.get("ticker"),
        "name": clean_company_name(peer.get("ticker"), peer.get("name")),
        "theme": peer.get("theme"),
        "market": peer.get("market"),
        "group_role": "peer",
        "peer_type": normalize_peer_type(peer.get("ticker"), theme, str(peer.get("theme", "")), str(peer.get("discovery_reason", "")), str(peer.get("peer_type") or "")),
        "profit_pool": normalize_profit_pool(peer.get("ticker"), str(peer.get("theme", "")), str(peer.get("discovery_reason", "")), str(peer.get("profit_pool") or "")),
        "discovery_reason": peer.get("discovery_reason", ""),
        "source_urls": peer.get("source_urls", []),
        "discovery_confidence": peer.get("discovery_confidence"),
    } for peer in peer_rows)

    upsert_watchlist_rows(watchlist_path, research_rows)

    console.print(Panel.fit(
        f"Deep research group: {name} / {ticker} + {len(peer_rows)} comparable companies ({len(web_peer_rows)} discovered from web)",
        style="bold blue",
    ))

    results: List[Dict[str, Any]] = []
    for row in research_rows:
        row_ticker = str(row.get("ticker", "")).strip()
        norm = canonical_ticker_for(row_ticker)
        if not norm:
            continue
        if norm in analyzed_tickers:
            console.print(f"[yellow]Skip already analyzed in this run:[/yellow] {row_ticker}")
            continue
        try:
            result = run_company_research(
                ticker=row_ticker,
                name=str(row.get("name", "")),
                theme=str(row.get("theme", theme)),
                market=str(row.get("market", market)),
                portfolio_path=portfolio_path,
                output_root=output_root,
                watchlist_path=watchlist_path,
                group_id=group_id,
                group_role=str(row.get("group_role", "peer")),
                peer_context_rows=research_rows,
            )
            result["peer_type"] = row.get("peer_type")
            result["profit_pool"] = row.get("profit_pool")
            result["discovery_reason"] = row.get("discovery_reason", "")
            result["source_urls"] = row.get("source_urls", [])
            result["discovery_confidence"] = row.get("discovery_confidence")
            results.append(result)
            analyzed_tickers.add(norm)
        except Exception as e:
            console.print(f"[bold red]Error running {console_safe_text(row_ticker)}: {console_safe_text(e)}[/bold red]")

    if len(results) > 1:
        summary_dir = Path(output_root) / today_str()
        ensure_dir(summary_dir)
        peer_context_md = build_peer_context_from_rows(
            ticker,
            results,
            selection_basis="actual companies completed in this research group",
        )
        comparison_prompt = build_comparative_ranking_prompt(ticker, theme, peer_context_md, results)
        comparison_path = summary_dir / f"{ticker.replace('.', '_').replace('/', '_')}_peer_ranking_{now_str()}.md"
        comparison_prompt_path = summary_dir / f"{ticker.replace('.', '_').replace('/', '_')}_peer_ranking_prompt_{now_str()}.md"
        save_text(comparison_prompt_path, comparison_prompt)

        try:
            comparison_md = call_llm("Comparative Ranking Agent", comparison_prompt)
        except Exception as e:
            comparison_md = f"# Comparative Ranking Agent\n\nCould not generate comparative ranking: {e}"
        save_text(comparison_path, comparison_md)
        console.print(f"[bold]Peer ranking:[/bold] {comparison_path}")

        quality_report = build_group_quality_report(results, comparison_path=comparison_path)
        quality_base = f"{ticker.replace('.', '_').replace('/', '_')}_quality_report_{now_str()}"
        quality_json_path = summary_dir / f"{quality_base}.json"
        quality_md_path = summary_dir / f"{quality_base}.md"
        save_json(quality_json_path, quality_report)
        save_text(quality_md_path, quality_report_to_markdown(quality_report))
        console.print(f"[bold]Quality report:[/bold] {quality_md_path}")

    return results


def run_batch(
    watchlist_path: str,
    portfolio_path: str,
    output_root: str,
    limit: Optional[int],
    summary_dir: Optional[Path] = None,
) -> Dict[str, str]:
    p = Path(watchlist_path)
    if not p.exists():
        raise FileNotFoundError(f"watchlist not found: {watchlist_path}")

    df = pd.read_csv(p)
    for col in ["ticker", "name", "theme", "market"]:
        if col not in df.columns:
            raise ValueError(f"watchlist.csv missing column: {col}")

    if limit:
        df = df.head(limit)

    results: List[Dict[str, Any]] = []
    analyzed_tickers: set = set()
    for _, row in df.iterrows():
        ticker = str(row["ticker"])
        norm = canonical_ticker_for(ticker)
        if norm in analyzed_tickers:
            console.print(f"[yellow]Batch skip already analyzed as target/peer:[/yellow] {ticker}")
            continue
        try:
            group_results = run_single(
                ticker=ticker,
                name=str(row["name"]),
                theme=str(row["theme"]),
                market=str(row["market"]),
                portfolio_path=portfolio_path,
                output_root=output_root,
                watchlist_path=watchlist_path,
                analyzed_tickers=analyzed_tickers,
            )
            results.extend(group_results)
        except Exception as e:
            console.print(f"[bold red]Error running {row.get('ticker')}: {e}[/bold red]")

    summary_dir = summary_dir or (Path(output_root) / today_str())
    ensure_dir(summary_dir)
    summary_paths = build_batch_summary_files(results, output_root, summary_dir)
    console.print(Panel.fit("Batch completed", style="bold green"))
    console.print(f"[bold]Batch summary CSV:[/bold] {summary_paths['batch_summary_csv']}")
    console.print(f"[bold]Batch summary MD:[/bold] {summary_paths['batch_summary_md']}")
    console.print(f"[bold]Top ideas CSV:[/bold] {summary_paths['top_ideas_csv']}")
    console.print(f"[bold]Rerun queue CSV:[/bold] {summary_paths['rerun_queue_csv']}")
    return summary_paths


def show_log(
    output_root: str,
    top: int,
    quality: bool = False,
    rerun: bool = False,
    top_ideas: bool = False,
) -> None:
    log_path = Path(output_root) / "research_log.csv"
    if not log_path.exists():
        console.print("[yellow]No research_log.csv found.[/yellow]")
        return

    df = pd.read_csv(log_path)

    def ensure_columns(frame: pd.DataFrame, cols: List[str], default: Any = "") -> pd.DataFrame:
        updated = frame.copy()
        for col in cols:
            if col not in updated.columns:
                updated[col] = default
        return updated

    def log_cell(value: Any) -> str:
        return "" if summary_is_missing(value) else str(value)

    title = "Recent Research Log"
    cols = [
        "created_at",
        "analysis_group_role",
        "ticker",
        "company_name",
        "rating",
        "action",
        "suggested_position_pct",
        "confidence_score",
        "risk_score",
    ]

    if quality:
        title = "Research Log Quality View"
        cols = [
            "ticker",
            "company_name",
            "action",
            "suggested_position_pct",
            "evidence_quality_score",
            "market_data_reliability",
            "financial_statement_reliability",
            "price_data_reliability_from_fetch",
            "valuation_reliability",
            "manual_price_verification_required",
            "guardrail_warning_count",
            "hard_blocker_count",
            "soft_warning_count",
            "chokepoint_adjusted_score",
            "weighted_investment_score",
            "serenity_thesis_quality",
            "chokepoint_evidence_level",
            "deep_research_priority",
            "quality_status",
        ]
        df = ensure_columns(df, cols)
        df = df.tail(top)
    elif rerun:
        title = "Research Log Rerun Queue"
        base_cols = [
            "created_at",
            "ticker",
            "company_name",
            "quality_status",
            "needs_rerun",
            "manual_price_verification_required",
            "quality_reason",
            "suggested_rerun_mode",
            "output_dir",
        ]
        df = ensure_columns(df, base_cols + [
            "llm_fetch_failed_count",
            "evidence_quality_score",
            "official_primary_hits",
            "market_data_reliability",
            "financial_statement_reliability",
            "fallback_decision",
        ])
        rerun_mask = df["needs_rerun"].map(summary_bool) | df["manual_price_verification_required"].map(summary_bool)
        df = df[rerun_mask].copy()
        if not df.empty:
            df["quality_reason"] = df.apply(
                lambda row: row.get("quality_reason") if not summary_is_missing(row.get("quality_reason")) else "; ".join(summary_quality_reasons(row.to_dict())),
                axis=1,
            )
            df["suggested_rerun_mode"] = df.apply(
                lambda row: row.get("suggested_rerun_mode") if not summary_is_missing(row.get("suggested_rerun_mode")) else suggested_rerun_mode(row.to_dict()),
                axis=1,
            )
        cols = base_cols
        df = df.tail(top)
    elif top_ideas:
        title = "Research Log Top Ideas"
        cols = [
            "ticker",
            "company_name",
            "action",
            "suggested_position_pct",
            "evidence_quality_score",
            "valuation_attractiveness_score",
            "ai_beneficiary_score",
            "competitive_position_score",
            "weighted_investment_score",
            "chokepoint_adjusted_score",
            "serenity_thesis_quality",
            "chokepoint_evidence_level",
            "scout_recommendation",
            "valuation_framework_type",
            "quality_status",
            "output_dir",
        ]
        df = ensure_columns(df, cols + ["deep_research_candidate"])
        deep_mask = df["deep_research_candidate"].map(summary_bool)
        if "quality_status" in df.columns:
            deep_mask = deep_mask | (df["quality_status"].astype(str) == "deep_research_candidate")
        df = df[deep_mask].copy()
        if not df.empty:
            df["evidence_quality_score"] = pd.to_numeric(df["evidence_quality_score"], errors="coerce")
            df["suggested_position_pct"] = pd.to_numeric(df["suggested_position_pct"], errors="coerce")
            df["weighted_investment_score"] = pd.to_numeric(df["weighted_investment_score"], errors="coerce")
            df["chokepoint_adjusted_score"] = pd.to_numeric(df["chokepoint_adjusted_score"], errors="coerce")
            df = df.sort_values(
                by=["weighted_investment_score", "chokepoint_adjusted_score", "evidence_quality_score", "suggested_position_pct"],
                ascending=[False, False, False, False],
                na_position="last",
            )
        df = df.head(top)
    else:
        df = ensure_columns(df, cols)
        df = df.tail(top)

    if df.empty:
        console.print("[yellow]No rows matched the requested log view.[/yellow]")
        return

    table = Table(title=title)

    for c in cols:
        table.add_column(c)

    for _, row in df.iterrows():
        table.add_row(*[log_cell(row.get(c, "")) for c in cols])

    console.print(table)


def apply_runtime_cli_flags(args: argparse.Namespace) -> None:
    global WEB_DISCOVERY_ENABLED, EVIDENCE_SEARCH_ENABLED, REUSE_TODAY_OUTPUTS, CHOKEPOINT_SCOUT_ENABLED
    if getattr(args, "max_peers", None) is not None:
        os.environ["MAX_PEERS"] = str(args.max_peers)
    if getattr(args, "no_peers", False):
        os.environ["MAX_PEERS"] = "0"
    if getattr(args, "no_web_discovery", False):
        WEB_DISCOVERY_ENABLED = False
        os.environ["WEB_DISCOVERY_ENABLED"] = "0"
    if getattr(args, "no_evidence_search", False):
        EVIDENCE_SEARCH_ENABLED = False
        os.environ["EVIDENCE_SEARCH_ENABLED"] = "0"
    if getattr(args, "no_reuse", False):
        REUSE_TODAY_OUTPUTS = False
        os.environ["REUSE_TODAY_OUTPUTS"] = "0"
    if getattr(args, "skip_chokepoint", False):
        CHOKEPOINT_SCOUT_ENABLED = False
        os.environ["CHOKEPOINT_SCOUT_ENABLED"] = "0"


def run_validation() -> None:
    linkedin = classify_source_strict("https://www.linkedin.com/company/sk-hynix", company_name="SK hynix")
    assert not linkedin["is_primary"], "linkedin.com must not be primary"
    assert "never_primary_domain" in linkedin["warnings"], "linkedin.com must carry never_primary_domain warning"
    yahoo = classify_source_strict("https://finance.yahoo.com/quote/000660.KS", company_name="SK hynix")
    assert not yahoo["is_primary"], "finance.yahoo.com must not be primary"
    skhynix = classify_source_strict("https://news.skhynix.com/latest-news", company_name="SK hynix")
    assert skhynix["evidence_tier"] == "primary_company", "news.skhynix.com should be primary_company for SK hynix"
    sec = classify_source_strict("https://www.sec.gov/ixviewer/doc/action", company_name="Nvidia")
    assert sec["evidence_tier"] == "primary_regulatory", "sec.gov should be primary_regulatory"
    reuters = classify_source_strict("https://www.reuters.com/technology/test", company_name="Nvidia")
    assert reuters["evidence_tier"] == "secondary_news", "reuters.com should be secondary_news"
    trendforce = classify_source_strict("https://www.trendforce.com/news/test", company_name="SK hynix")
    assert trendforce["evidence_tier"] == "industry_data", "trendforce.com should be industry_data"
    for domain in ["https://www.quartr.com/test", "https://www.sahmcapital.com/test", "https://www.gurufocus.com/test", "https://www.biggo.com/test"]:
        classified = classify_source_strict(domain, company_name="SK hynix")
        assert not classified["is_primary"], f"{domain} must not be primary"
        assert classified["source_type"] == "aggregator_or_social_or_reprint", f"{domain} should be aggregator/reprint"

    sk_queries = build_official_source_queries("SK hynix", "000660.KS", "HBM DRAM NAND AI Memory", "Korea")
    sk_query_text = "\n".join(q["query"] for q in sk_queries)
    assert "site:skhynix.com" in sk_query_text, "SK hynix official queries should include site:skhynix.com"
    assert "site:news.skhynix.com" in sk_query_text, "SK hynix official queries should include site:news.skhynix.com"
    assert "site:dart.fss.or.kr" in sk_query_text, "SK hynix official queries should include site:dart.fss.or.kr"
    assert "site:kind.krx.co.kr" in sk_query_text, "SK hynix official queries should include site:kind.krx.co.kr"
    lite_queries = build_official_source_queries("Lumentum", "LITE", "Optical Components", "US")
    lite_query_text = "\n".join(q["query"] for q in lite_queries)
    assert "site:sec.gov" in lite_query_text, "US official queries should include site:sec.gov"
    assert ("site:investor.lumentum.com" in lite_query_text or "site:lumentum.com" in lite_query_text), "Lumentum official queries should include company IR domain"

    peer_rows = [
        {"ticker": "TGT", "peer_type": "target", "price_to_sales": 100.0},
        {"ticker": "A", "peer_type": "direct_competitor", "price_to_sales": 2.0},
        {"ticker": "B", "peer_type": "same_profit_pool", "price_to_sales": 4.0},
        {"ticker": "C", "peer_type": "weak_comparable", "price_to_sales": 20.0},
        {"ticker": "D", "peer_type": "adjacent_supplier", "price_to_sales": 30.0},
    ]
    valuation_peers = filter_peers_for_valuation(peer_rows)
    valuation_tickers = {r["ticker"] for r in valuation_peers}
    assert valuation_tickers == {"A", "B"}, f"valuation peers should include only direct/same peers, got {valuation_tickers}"
    assert median_metric(valuation_peers, "price_to_sales") == 3.0, "peer median should exclude target and context-only peers"

    mock_snapshot = {
        "latest_price": 100.0,
        "market_cap": 1000.0,
        "enterprise_value": 1100.0,
        "total_revenue": 500.0,
        "ebitda": 80.0,
        "operating_margin": 0.18,
        "net_debt": 100.0,
        "annual_financials": [{"net_income": 60.0}],
    }
    memory_bridge = build_industry_valuation_bridge(mock_snapshot, theme="HBM DRAM NAND AI Memory")
    assert memory_bridge["has_bridge"], "memory bridge should exist"
    assert memory_bridge["framework_type"] == "memory_dual_framework", f"memory framework mismatch: {memory_bridge['framework_type']}"
    assert "traditional_memory_cycle" in memory_bridge.get("frameworks", {}), "memory bridge should include traditional framework"
    assert "structural_hbm_scarcity" in memory_bridge.get("frameworks", {}), "memory bridge should include structural HBM framework"
    traditional = memory_bridge["frameworks"]["traditional_memory_cycle"]["scenarios"]
    structural = memory_bridge["frameworks"]["structural_hbm_scarcity"]["scenarios"]
    assert set(traditional.keys()) == {"bear", "base", "bull"}, "traditional memory scenarios missing"
    assert set(structural.keys()) == {"bear", "base", "bull"}, "structural HBM scenarios missing"
    assert structural["base"]["scenario_price"] > traditional["base"]["scenario_price"], "structural HBM base should be above traditional base"
    assert set(memory_bridge["scenarios"].keys()) == {"bear", "base", "bull"}, "backward-compatible memory scenarios missing"

    for theme, expected in [
        ("Optical Components", "optical_cycle_ev_sales_margin"),
    ]:
        bridge = build_industry_valuation_bridge(mock_snapshot, theme=theme)
        assert bridge["has_bridge"], f"{theme} bridge should exist"
        assert bridge["framework_type"] == expected, f"{theme} framework mismatch: {bridge['framework_type']}"
        assert set(bridge["scenarios"].keys()) == {"bear", "base", "bull"}, f"{theme} scenarios missing"
        for case, scenario in bridge["scenarios"].items():
            assert scenario.get("scenario_price") is not None or scenario.get("scenario_equity_value") is not None, f"{theme} {case} missing valuation output"

    power_bridge = build_industry_valuation_bridge(mock_snapshot, theme="Data Center Power Thermal Infrastructure")
    assert power_bridge["has_bridge"], "power thermal bridge should exist"
    assert power_bridge["framework_type"] == "power_thermal_dual_framework", f"power framework mismatch: {power_bridge['framework_type']}"
    assert "traditional_electrical_equipment" in power_bridge.get("frameworks", {}), "power bridge should include traditional electrical framework"
    assert "ai_data_center_power_scarcity" in power_bridge.get("frameworks", {}), "power bridge should include AI power scarcity framework"
    power_traditional = power_bridge["frameworks"]["traditional_electrical_equipment"]["scenarios"]
    power_scarcity = power_bridge["frameworks"]["ai_data_center_power_scarcity"]["scenarios"]
    assert power_scarcity["base"]["scenario_price"] > power_traditional["base"]["scenario_price"], "AI power scarcity base should be above traditional base"
    assert set(power_bridge["scenarios"].keys()) == {"bear", "base", "bull"}, "backward-compatible power scenarios missing"

    semi_bridge = build_industry_valuation_bridge(mock_snapshot, theme="Semiconductor Equipment WFE Test Equipment Advantest")
    assert semi_bridge["has_bridge"], "semiconductor equipment bridge should exist"
    assert semi_bridge["framework_type"] == "semiconductor_equipment_dual_framework", f"semi equipment framework mismatch: {semi_bridge['framework_type']}"
    assert semi_bridge["framework_type"] != "packaging_substrate_cycle_ev_ebitda", "semiconductor equipment must not use packaging/substrate framework"
    assert "traditional_wfe_cycle" in semi_bridge.get("frameworks", {}), "semi bridge should include traditional WFE framework"
    assert "ai_equipment_scarcity_quality" in semi_bridge.get("frameworks", {}), "semi bridge should include AI equipment scarcity/quality framework"

    normal_price = build_price_sanity_check({
        "latest_price": 100,
        "market_cap": 10_000_000_000,
        "total_revenue": 2_000_000_000,
        "enterprise_value": 11_000_000_000,
        "one_year_return": 0.20,
        "volatility_1y": 0.30,
    })
    assert normal_price["price_data_reliability"] == "high", "normal price case should have high price reliability"
    assert normal_price["valuation_reliability"] == "high", "normal price case should have high valuation reliability"
    assert normal_price["manual_price_verification_required"] is False, "normal price case should not require manual verification"

    extreme_price = build_price_sanity_check({
        "latest_price": 970,
        "market_cap": 75_000_000_000,
        "total_revenue": 2_500_000_000,
        "enterprise_value": 70_000_000_000,
        "one_year_return": 4.0,
        "volatility_1y": 0.70,
        "price_data_reliability_from_fetch": "high",
    })
    assert extreme_price["price_data_reliability"] == "medium", "complete-data extreme momentum should lower price reliability to medium"
    assert extreme_price["valuation_reliability"] == "medium", "complete-data extreme momentum should lower valuation reliability to medium"
    assert extreme_price["manual_price_verification_required"] is False, "complete-data extreme momentum should not require automatic manual verification"
    assert "extreme_momentum_requires_manual_review_but_not_data_error" in extreme_price["price_sanity_warnings"], "missing extreme momentum non-data-error warning"

    incomplete_extreme_price = build_price_sanity_check({
        "latest_price": 970,
        "market_cap": None,
        "total_revenue": 2_500_000_000,
        "enterprise_value": None,
        "one_year_return": 4.0,
        "volatility_1y": 0.70,
    })
    assert incomplete_extreme_price["manual_price_verification_required"] is True, "incomplete-data extreme momentum should require manual verification"
    assert "extreme_momentum_with_incomplete_market_data_requires_price_verification" in incomplete_extreme_price["price_sanity_warnings"], "missing incomplete extreme momentum warning"

    market_cap_missing_ev_available = build_price_sanity_check({
        "latest_price": 100,
        "market_cap": None,
        "enterprise_value": 11_000_000_000,
        "total_revenue": 2_000_000_000,
        "one_year_return": 0.20,
    })
    assert market_cap_missing_ev_available["valuation_reliability"] == "medium", "missing market cap with EV should lower valuation reliability to medium"
    assert market_cap_missing_ev_available["manual_price_verification_required"] is False, "missing market cap with EV should not force manual verification"
    assert "market_cap_missing_but_ev_available_verify_before_position" in market_cap_missing_ev_available["price_sanity_warnings"], "missing market-cap-with-EV warning"

    missing_price = build_price_sanity_check({
        "market_cap": 10_000_000_000,
        "total_revenue": 2_000_000_000,
    })
    assert missing_price["price_data_reliability"] == "low", "missing price should lower price reliability"
    assert missing_price["manual_price_verification_required"] is True, "missing price should require manual verification"

    decision = {
        "rating": "buy",
        "action": "buy",
        "suggested_position_pct": 5.0,
        "confidence_score": 9,
    }
    guarded = apply_pm_guardrails(
        decision,
        {"evidence_quality_score": 6, "evidence_warnings": []},
        ["MOCK: 1Y return exceeds 300%; verify split adjustment, local listing price units, and yfinance data integrity."],
        {"has_bridge": True},
    )
    assert guarded["suggested_position_pct"] <= 1.0, "extreme 1Y return should cap position at <= 1%"
    assert "extreme_1y_return_caps_position_at_1pct" in guarded["guardrail_warnings"], "missing extreme return guardrail warning"
    assert guarded["action"] in {"watchlist", "starter_position"}, f"unexpected downgraded action: {guarded['action']}"

    guarded_manual = apply_pm_guardrails(
        decision,
        {"evidence_quality_score": 10, "evidence_warnings": []},
        [],
        {"has_bridge": True},
        price_sanity=incomplete_extreme_price,
    )
    assert guarded_manual["suggested_position_pct"] == 0.0, "manual price verification should cap position at 0%"
    assert guarded_manual["max_allowed_position_pct"] == 0.0, "manual price verification should set max position to 0%"
    assert guarded_manual["action"] == "manual_price_verification_required", "manual price verification should override action"
    assert guarded_manual["rating"] == "watch", "manual price verification should set rating to watch"

    guarded_extreme_momentum = apply_pm_guardrails(
        decision,
        {"evidence_quality_score": 10, "evidence_warnings": []},
        [],
        {"has_bridge": True},
        price_sanity=extreme_price,
    )
    assert guarded_extreme_momentum["suggested_position_pct"] <= 1.0, "complete-data extreme momentum should cap position at <= 1%"
    assert guarded_extreme_momentum["action"] != "manual_price_verification_required", "complete-data extreme momentum should not force manual price verification"

    fetch_df = pd.DataFrame({"a": [1, 2]})
    _, fetch_diag = retry_call(
        lambda: fetch_df,
        source="test",
        operation="fetch_success_df",
        target="unit",
        max_attempts=1,
    )
    assert fetch_diag["status"] == "success", "DataFrame success should be status success"
    assert fetch_diag["row_count"] == 2 and fetch_diag["column_count"] == 1, "DataFrame shape should be recorded"

    _, empty_diag = retry_call(
        lambda: pd.DataFrame(),
        source="test",
        operation="fetch_empty_df",
        target="unit",
        max_attempts=1,
    )
    assert empty_diag["status"] == "empty", "empty DataFrame should be status empty"
    assert empty_diag["row_count"] == 0 and empty_diag["column_count"] == 0, "empty DataFrame shape should be recorded"

    _, error_diag = retry_call(
        lambda: (_ for _ in ()).throw(RuntimeError("network failed")),
        source="test",
        operation="fetch_exception",
        target="unit",
        max_attempts=1,
    )
    assert error_diag["status"] == "failed", "generic exception should be status failed"
    assert error_diag["error_type"] == "RuntimeError", "error type should be recorded"

    _, rate_diag = retry_call(
        lambda: (_ for _ in ()).throw(RuntimeError("429 Too Many Requests rate limit")),
        source="test",
        operation="fetch_rate_limit",
        target="unit",
        max_attempts=1,
    )
    assert rate_diag["status"] == "rate_limited", "429 message should be classified as rate_limited"

    reliability = compute_market_data_reliability([
        {"operation": "yfinance_info", "status": "success"},
        {"operation": "yfinance_history_2y", "status": "failed"},
    ])
    assert reliability["price_data_reliability_from_fetch"] == "low", "failed history should lower price fetch reliability"

    reliability = compute_market_data_reliability([
        {"operation": "yfinance_annual_income", "status": "empty"},
        {"operation": "yfinance_annual_cashflow", "status": "empty"},
        {"operation": "yfinance_annual_balance", "status": "empty"},
    ])
    assert reliability["financial_statement_reliability"] == "low", "three empty annual statements should lower financial reliability"

    guarded_fetch = apply_pm_guardrails(
        decision,
        {"evidence_quality_score": 10, "evidence_warnings": []},
        [],
        {"has_bridge": True},
        fetch_reliability={
            "market_data_reliability": "high",
            "financial_statement_reliability": "high",
            "price_data_reliability_from_fetch": "low",
            "data_fetch_warnings": [],
        },
    )
    assert guarded_fetch["action"] == "manual_price_verification_required", "low price fetch reliability should require manual verification"
    assert guarded_fetch["suggested_position_pct"] == 0.0, "low price fetch reliability should cap position at 0%"
    assert guarded_fetch["max_allowed_position_pct"] == 0.0, "low price fetch reliability should set max position to 0%"

    diag_md = fetch_diagnostics_to_markdown("Fetch Diagnostics Test", [fetch_diag, empty_diag, error_diag, rate_diag])
    assert "Summary:" in diag_md, "diagnostics markdown should include Summary"
    assert "| Source | Operation | Status | Target | Retry Count | Rows | Impact | Error Type | Error Message |" in diag_md, "diagnostics markdown should include table headers"
    assert "fetch_success_df" in diag_md and "fetch_rate_limit" in diag_md, "diagnostics markdown should include operation names"

    bad_chokepoint = repair_chokepoint_decision({
        "ticker": "MOCK",
        "company_name": "Mock Corp",
        "theme": "AI",
        "market": "US",
        "chokepoint_score": 99,
        "indispensability_score": -5,
        "scarcity_score": 8,
        "customer_validation_score": 9,
        "nvidia_signal_score": 7,
        "substitution_risk_score": 9,
        "timing_risk_score": 5,
        "market_awareness_score": 9,
        "valuation_risk_score": 9,
        "serenity_thesis_quality": "high_quality_chokepoint",
        "evidence_level": "hypothesis_only",
        "deep_research_priority": "urgent",
        "scout_recommendation": "buy",
    })
    assert bad_chokepoint["chokepoint_score"] == 10, "chokepoint score should be clipped high"
    assert bad_chokepoint["indispensability_score"] == 1, "chokepoint score should be clipped low"
    assert bad_chokepoint["customer_validation_score"] <= 5, "hypothesis-only evidence should cap customer validation"
    assert bad_chokepoint["serenity_thesis_quality"] != "high_quality_chokepoint", "high substitution risk should prevent high-quality chokepoint"
    assert bad_chokepoint["scout_recommendation"] == "monitor_for_evidence", "buy-like scout recommendation should be repaired"
    assert bad_chokepoint["deep_research_priority"] == "low", "invalid deep research priority should be repaired"

    high_chokepoint = repair_chokepoint_decision({
        "ticker": "MOCK",
        "company_name": "Mock Corp",
        "theme": "AI",
        "market": "US",
        "chokepoint_score": 9,
        "indispensability_score": 9,
        "scarcity_score": 9,
        "customer_validation_score": 8,
        "nvidia_signal_score": 8,
        "substitution_risk_score": 2,
        "timing_risk_score": 2,
        "market_awareness_score": 3,
        "valuation_risk_score": 4,
        "serenity_thesis_quality": "high_quality_chokepoint",
        "evidence_level": "primary_supported",
        "deep_research_priority": "high",
        "scout_recommendation": "deep_research",
    })
    high_adjusted = calculate_chokepoint_adjusted_score(high_chokepoint)
    assert high_adjusted is not None and high_adjusted >= 7.5, "high-quality primary chokepoint should score high"

    priced_chokepoint = repair_chokepoint_decision({**high_chokepoint, "market_awareness_score": 9, "valuation_risk_score": 9, "customer_validation_score": 7})
    assert priced_chokepoint["serenity_thesis_quality"] == "already_priced_in", "high awareness and valuation risk should repair to already priced in"
    assert calculate_chokepoint_adjusted_score(priced_chokepoint) <= 6, "already priced in should cap adjusted score"

    weak_chokepoint = repair_chokepoint_decision({**high_chokepoint, "serenity_thesis_quality": "weak_replaceable"})
    assert calculate_chokepoint_adjusted_score(weak_chokepoint) <= 4, "weak replaceable should cap adjusted score"
    hypothesis_chokepoint = repair_chokepoint_decision({**high_chokepoint, "evidence_level": "hypothesis_only"})
    assert calculate_chokepoint_adjusted_score(hypothesis_chokepoint) < high_adjusted, "hypothesis-only evidence should penalize adjusted score"

    weighted_decision = {
        "fundamental_quality_score": 8,
        "growth_visibility_score": 8,
        "competitive_position_score": 8,
        "ai_beneficiary_score": 8,
        "valuation_attractiveness_score": 6,
        "evidence_quality_score": 8,
        "risk_score": 4,
    }
    high_weighted = calculate_weighted_investment_score(weighted_decision, high_chokepoint)
    low_weighted = calculate_weighted_investment_score({**weighted_decision, "risk_score": 9}, high_chokepoint)
    assert high_weighted["weighted_investment_score"] > 7, "high chokepoint should improve final weighted score"
    assert low_weighted["weighted_investment_score"] < high_weighted["weighted_investment_score"], "high risk should reduce weighted score"

    overlay_base_decision = {
        **weighted_decision,
        "rating": "watch",
        "action": "watchlist",
        "suggested_position_pct": 0.0,
    }
    tracking_chokepoint = repair_chokepoint_decision({
        **high_chokepoint,
        "evidence_level": "secondary_supported",
        "chokepoint_score": 10,
        "indispensability_score": 10,
        "scarcity_score": 10,
        "customer_validation_score": 9,
        "nvidia_signal_score": 9,
        "substitution_risk_score": 1,
        "timing_risk_score": 1,
        "market_awareness_score": 2,
        "valuation_risk_score": 2,
    })
    overlay_tracking = apply_chokepoint_weighted_overlay(
        overlay_base_decision,
        tracking_chokepoint,
        {"evidence_quality_score": 8},
        {"price_data_reliability": "high", "valuation_reliability": "high", "manual_price_verification_required": False},
        {"market_data_reliability": "high", "financial_statement_reliability": "high", "price_data_reliability_from_fetch": "high"},
    )
    assert overlay_tracking["action"] == "tracking_position" and overlay_tracking["suggested_position_pct"] >= 0.5, "high-quality chokepoint should upgrade watchlist to tracking"

    overlay_starter = apply_chokepoint_weighted_overlay(
        overlay_base_decision,
        high_chokepoint,
        {"evidence_quality_score": 8},
        {"price_data_reliability": "high", "valuation_reliability": "high", "manual_price_verification_required": False},
        {"market_data_reliability": "high", "financial_statement_reliability": "high", "price_data_reliability_from_fetch": "high"},
    )
    assert overlay_starter["action"] == "starter_position", "primary-supported high score should upgrade to starter"
    assert overlay_starter["suggested_position_pct"] <= 2.0, "starter overlay should cap preliminary position at 2%"

    overlay_hypothesis = apply_chokepoint_weighted_overlay(
        overlay_base_decision,
        hypothesis_chokepoint,
        {"evidence_quality_score": 8},
        {"price_data_reliability": "high", "valuation_reliability": "high", "manual_price_verification_required": False},
        {"market_data_reliability": "high", "financial_statement_reliability": "high", "price_data_reliability_from_fetch": "high"},
    )
    assert overlay_hypothesis["action"] == "watchlist", "hypothesis-only chokepoint should not upgrade"
    assert "chokepoint_hypothesis_only_no_position_upgrade" in overlay_hypothesis["chokepoint_overlay_warnings"], "hypothesis-only warning missing"

    overlay_priced = apply_chokepoint_weighted_overlay(
        {**overlay_base_decision, "action": "starter_position", "suggested_position_pct": 2.0},
        priced_chokepoint,
        {"evidence_quality_score": 8},
        {"price_data_reliability": "high", "valuation_reliability": "high", "manual_price_verification_required": False},
        {"market_data_reliability": "high", "financial_statement_reliability": "high", "price_data_reliability_from_fetch": "high"},
    )
    assert overlay_priced["suggested_position_pct"] <= 1.0, "already priced-in chokepoint should cap at 1%"
    assert overlay_priced["action"] in {"tracking_position", "watchlist"}, "already priced-in chokepoint should not stay above tracking"

    overlay_blocked = apply_chokepoint_weighted_overlay(
        overlay_base_decision,
        high_chokepoint,
        {"evidence_quality_score": 8},
        {"price_data_reliability": "high", "valuation_reliability": "high", "manual_price_verification_required": True},
        {"market_data_reliability": "high", "financial_statement_reliability": "high", "price_data_reliability_from_fetch": "high"},
    )
    assert overlay_blocked["action"] == "watchlist", "manual price verification should block chokepoint upgrade"

    normalized = normalize_action_position_consistency({"rating": "watch", "action": "watchlist", "suggested_position_pct": 1.0})
    assert normalized["action"] == "tracking_position", "watchlist with positive position should normalize to tracking_position"
    normalized = normalize_action_position_consistency({"rating": "tracking_watch", "action": "tracking_position", "suggested_position_pct": 0.0})
    assert normalized["action"] == "watchlist", "tracking_position with zero position should normalize to watchlist"

    def mock_summary_decision(
        *,
        ticker: str = "MOCK",
        action: str = "starter_position",
        position: float = 1.0,
        evidence_score: float = 8.0,
        official_hits: int = 2,
        market_reliability: str = "high",
        financial_reliability: str = "high",
        price_fetch_reliability: str = "high",
        price_data_reliability: str = "high",
        valuation_reliability: str = "high",
        manual_price_verification: bool = False,
        llm_failed: int = 0,
        fallback: bool = False,
        guardrail_warnings: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        guardrail_warnings = guardrail_warnings or []
        decision = {
            "ticker": ticker,
            "company_name": f"{ticker} Corp",
            "rating": "small_start" if position > 0 else "watch",
            "action": action,
            "suggested_position_pct": position,
            "confidence_score": 8,
            "fundamental_quality_score": 7,
            "growth_visibility_score": 7,
            "valuation_attractiveness_score": 6,
            "ai_beneficiary_score": 8,
            "competitive_position_score": 8,
            "risk_score": 4,
            "evidence_quality_score": evidence_score,
            "thesis_summary": "Valid mock thesis.",
            "ai_agent_demand_link": "Valid mock demand link.",
            "valuation_premium_reason": "Valid mock valuation premium reason.",
            "valuation_is_justified": True,
            "valuation_view": "Valid mock valuation view.",
            "portfolio_fit": "Valid mock portfolio fit.",
            "bull_case": "Valid mock bull case.",
            "base_case": "Valid mock base case.",
            "bear_case": "Valid mock bear case.",
            "key_bull_points": ["Mock bull point."],
            "key_bear_points": ["Mock bear point."],
            "key_tracking_indicators": ["Mock tracking indicator."],
            "thesis_kill_triggers": ["Mock kill trigger."],
            "data_gaps": ["Mock data gap."],
            "deepest_questions": ["Mock question."],
            "final_pm_judgment": "Valid mock judgment.",
            "evidence_quality": {
                "evidence_quality_score": evidence_score,
                "primary_regulatory_count": 2,
                "primary_company_count": 1,
                "transcript_secondary_count": 1,
                "industry_data_count": 1,
                "secondary_news_count": 2,
                "weak_source_count": 0,
                "official_source_search": {
                    "official_primary_hits": official_hits,
                    "official_regulatory_hits": 1,
                    "official_company_hits": max(0, official_hits - 1),
                },
            },
            "fetch_diagnostics_summary": {
                "market": {"failed": 0, "empty": 1, "rate_limited": 0},
                "evidence": {"failed": 0, "empty": 0, "rate_limited": 0},
                "llm": {"failed": llm_failed, "empty": 0, "rate_limited": 0},
            },
            "valuation_bridge_summary": {
                "framework_type": "memory_dual_framework",
                "traditional_memory_cycle": {"base_upside_downside": -0.05},
                "structural_hbm_scarcity": {"base_upside_downside": 0.20},
                "scenarios": {
                    "bear": {"upside_downside": -0.30},
                    "base": {"upside_downside": 0.05},
                    "bull": {"upside_downside": 0.40},
                },
            },
            "valuation_framework_interpretation": "Current price requires scarcity assumptions to persist.",
            "price_sanity": {
                "price_data_reliability": price_data_reliability,
                "valuation_reliability": valuation_reliability,
                "manual_price_verification_required": manual_price_verification,
                "price_sanity_warnings": ["mock_warning"] if manual_price_verification else [],
            },
            "market_data_reliability": market_reliability,
            "financial_statement_reliability": financial_reliability,
            "price_data_reliability_from_fetch": price_fetch_reliability,
            "price_data_reliability": price_data_reliability,
            "valuation_reliability": valuation_reliability,
            "manual_price_verification_required": manual_price_verification,
            "data_fetch_warnings": [],
            "guardrail_warnings": guardrail_warnings,
            "pre_guardrail_position_pct": position,
            "max_allowed_position_pct": 5.0,
        }
        if fallback:
            decision.update(fallback_decision(ticker, f"{ticker} Corp", "mock fallback"))
        return decision

    flatten_row = {
        "created_at": "2026-01-01T00:00:00",
        "ticker": "MOCK",
        "company_name": "Mock Corp",
        "theme": "AI Memory",
        "market": "US",
        "analysis_group_role": "target",
        "peer_type": "target",
        "profit_pool": "memory",
        "output_dir": "outputs/mock",
        "decision": mock_summary_decision(ticker="MOCK"),
    }
    flat = flatten_decision_for_summary(flatten_row)
    assert flat["ticker"] == "MOCK", "flatten should preserve ticker"
    assert flat["action"] == "starter_position", "flatten should preserve action"
    assert flat["evidence_quality_score"] == 8.0, "flatten should preserve evidence score"
    assert flat["primary_regulatory_count"] == 2, "flatten should preserve regulatory evidence count"
    assert flat["official_primary_hits"] == 2, "flatten should preserve official source hits"
    assert flat["market_data_reliability"] == "high", "flatten should preserve market data reliability"
    assert flat["valuation_framework_type"] == "memory_dual_framework", "flatten should preserve valuation framework"
    assert flat["traditional_base_upside_downside"] == -0.05, "flatten should extract traditional base upside"
    assert flat["scarcity_base_upside_downside"] == 0.20, "flatten should extract scarcity base upside"
    assert flat["quality_report"].endswith("quality_report.md"), "flatten should infer quality report path"

    memory_upside = extract_valuation_upside_fields({
        "valuation_bridge_summary": {
            "traditional_memory_cycle": {"base_upside_downside": -0.10},
            "structural_hbm_scarcity": {"base_upside_downside": 0.25},
        }
    })
    assert memory_upside["traditional_base_upside_downside"] == -0.10, "memory traditional upside extraction failed"
    assert memory_upside["scarcity_base_upside_downside"] == 0.25, "memory scarcity upside extraction failed"

    power_upside = extract_valuation_upside_fields({
        "valuation_bridge_summary": {
            "traditional_electrical_equipment": {"base_upside_downside": -0.03},
            "ai_data_center_power_scarcity": {"base_upside_downside": 0.18},
        }
    })
    assert power_upside["traditional_base_upside_downside"] == -0.03, "power traditional upside extraction failed"
    assert power_upside["scarcity_base_upside_downside"] == 0.18, "power scarcity upside extraction failed"

    semi_upside = extract_valuation_upside_fields({
        "valuation_bridge_summary": {
            "traditional_wfe_cycle": {"base_upside_downside": -0.08},
            "ai_equipment_scarcity_quality": {"base_upside_downside": 0.12},
        }
    })
    assert semi_upside["traditional_base_upside_downside"] == -0.08, "semi equipment traditional upside extraction failed"
    assert semi_upside["scarcity_base_upside_downside"] == 0.12, "semi equipment scarcity upside extraction failed"

    needs_flat = classify_summary_quality({**flat, "structured_json_failed": True})
    assert needs_flat["needs_rerun"] is True and needs_flat["quality_status"] == "needs_rerun", "needs_rerun classification failed"
    manual_flat = classify_summary_quality({**flat, "official_primary_hits": 0})
    assert manual_flat["manual_review_required"] is True and manual_flat["quality_status"] == "manual_review", "manual_review classification failed"
    assert "official_primary_hits=0" in manual_flat["hard_blockers"], "official primary miss should be a hard blocker"
    valuation_low_flat = classify_summary_quality({**flat, "valuation_reliability": "low"})
    assert valuation_low_flat["quality_status"] == "manual_review", "low valuation reliability should require manual review"
    assert "valuation_reliability=low" in valuation_low_flat["hard_blockers"], "low valuation reliability should be a hard blocker"
    llm_failed_flat = classify_summary_quality({**flat, "llm_fetch_failed_count": 1})
    assert llm_failed_flat["quality_status"] == "needs_rerun", "LLM fetch failure should require rerun"
    assert llm_failed_flat["needs_rerun"] is True, "LLM fetch failure should set needs_rerun"
    soft_guardrail_flat = classify_summary_quality({
        **flat,
        "guardrail_warning_count": 3,
        "guardrail_warnings": (
            "medium_price_reliability_caps_position_at_2pct; "
            "medium_valuation_reliability_caps_position_at_2pct; "
            "extreme_momentum_requires_manual_review_but_not_data_error"
        ),
        "price_data_reliability": "medium",
        "valuation_reliability": "medium",
    })
    assert soft_guardrail_flat["quality_status"] == "deep_research_candidate", "soft guardrails should not block deep research candidate"
    assert soft_guardrail_flat["manual_review_required"] is False, "soft guardrails should not require hard manual review"
    assert soft_guardrail_flat["hard_blocker_count"] == 0, "soft guardrails should not create hard blockers"
    assert soft_guardrail_flat["soft_warning_count"] >= 3, "soft guardrails should be counted as soft warnings"
    assert "guardrail_warning_count>=3" in soft_guardrail_flat["soft_warnings"], "high guardrail count should be a soft warning"
    deep_flat = classify_summary_quality(flat)
    assert deep_flat["deep_research_candidate"] is True and deep_flat["quality_status"] == "deep_research_candidate", "deep research classification failed"
    low_flat = classify_summary_quality({
        **flat,
        "evidence_quality_score": None,
        "official_primary_hits": None,
        "suggested_position_pct": 0,
        "valuation_attractiveness_score": 1,
        "ai_beneficiary_score": 1,
        "competitive_position_score": 1,
    })
    assert low_flat["quality_status"] == "low_priority", "low priority classification failed"

    validate_summary_dir = Path("outputs") / "test_validate_batch_summary"
    ensure_dir(validate_summary_dir)
    batch_paths = build_batch_summary_files(
        [
            flatten_row,
            {
                **flatten_row,
                "ticker": "MANU",
                "company_name": "Manual Corp",
                "output_dir": "outputs/mock_manual",
                "decision": mock_summary_decision(ticker="MANU", official_hits=0, position=0),
            },
            {
                **flatten_row,
                "ticker": "RERUN",
                "company_name": "Rerun Corp",
                "output_dir": "outputs/mock_rerun",
                "decision": mock_summary_decision(ticker="RERUN", llm_failed=1, position=0),
            },
            {
                **flatten_row,
                "ticker": "SOFT",
                "company_name": "Soft Warning Corp",
                "output_dir": "outputs/mock_soft",
                "decision": mock_summary_decision(
                    ticker="SOFT",
                    price_data_reliability="medium",
                    valuation_reliability="medium",
                    guardrail_warnings=[
                        "medium_price_reliability_caps_position_at_2pct",
                        "medium_valuation_reliability_caps_position_at_2pct",
                        "extreme_momentum_requires_manual_review_but_not_data_error",
                    ],
                ),
            },
        ],
        "outputs",
        validate_summary_dir,
    )
    for key in ["batch_summary_csv", "batch_summary_md", "top_ideas_csv", "rerun_queue_csv"]:
        assert Path(batch_paths[key]).exists(), f"{key} should exist"
    assert list(validate_summary_dir.glob("batch_summary_*.csv")), "batch summary CSV glob should match"
    assert list(validate_summary_dir.glob("batch_summary_*.md")), "batch summary MD glob should match"
    assert list(validate_summary_dir.glob("top_ideas_*.csv")), "top ideas CSV glob should match"
    assert list(validate_summary_dir.glob("rerun_queue_*.csv")), "rerun queue CSV glob should match"
    validate_summary_df = pd.read_csv(batch_paths["batch_summary_csv"])
    assert "quality_status" in validate_summary_df.columns, "batch summary CSV should include quality_status"
    assert "market_data_reliability" in validate_summary_df.columns, "batch summary CSV should include reliability fields"
    assert "hard_blocker_count" in validate_summary_df.columns, "batch summary CSV should include hard blocker count"
    assert "hard_blockers" in validate_summary_df.columns, "batch summary CSV should include hard blockers"
    assert "soft_warning_count" in validate_summary_df.columns, "batch summary CSV should include soft warning count"
    assert "soft_warnings" in validate_summary_df.columns, "batch summary CSV should include soft warnings"
    assert "chokepoint_score" in validate_summary_df.columns, "batch summary CSV should include chokepoint score"
    assert "chokepoint_adjusted_score" in validate_summary_df.columns, "batch summary CSV should include adjusted chokepoint score"
    assert "weighted_investment_score" in validate_summary_df.columns, "batch summary CSV should include weighted investment score"
    assert "serenity_thesis_quality" in validate_summary_df.columns, "batch summary CSV should include serenity thesis quality"
    assert "chokepoint_evidence_level" in validate_summary_df.columns, "batch summary CSV should include chokepoint evidence level"
    assert "scout_recommendation" in validate_summary_df.columns, "batch summary CSV should include scout recommendation"
    soft_csv_row = validate_summary_df[validate_summary_df["ticker"] == "SOFT"].iloc[0]
    assert soft_csv_row["quality_status"] == "deep_research_candidate", "soft warning row should remain a top idea"
    assert int(soft_csv_row["hard_blocker_count"]) == 0, "soft warning row should not have hard blockers"
    assert int(soft_csv_row["soft_warning_count"]) >= 2, "soft warning row should have soft warnings"
    batch_summary_md = Path(batch_paths["batch_summary_md"]).read_text(encoding="utf-8")
    assert "## Soft Warnings / Monitor" in batch_summary_md, "batch summary MD should include soft warning section"
    assert "hard_blockers" in batch_summary_md, "manual review table should show hard blockers"

    assert chokepoint_abtest_action_rank("watchlist") < chokepoint_abtest_action_rank("tracking_position"), "watchlist should rank below tracking"
    assert chokepoint_abtest_action_rank("tracking_position") < chokepoint_abtest_action_rank("starter_position"), "tracking should rank below starter"
    assert chokepoint_abtest_action_rank("starter_position") < chokepoint_abtest_action_rank("buy"), "starter should rank below buy"
    assert chokepoint_abtest_action_rank("manual_price_verification_required") == -1, "manual price verification should rank -1"

    abtest_validate_dir = Path("outputs") / "test_validate_chokepoint_abtest"
    ensure_dir(abtest_validate_dir)
    abtest_run_id = "validate_chokepoint_abtest"
    mock_baseline_csv = abtest_validate_dir / "baseline.csv"
    mock_treatment_csv = abtest_validate_dir / "treatment.csv"
    pd.DataFrame([
        {
            "ticker": "NVT",
            "company_name": "nVent",
            "theme": "Data Center Electrical Enclosures Infrastructure",
            "action": "watchlist",
            "suggested_position_pct": 0.0,
            "quality_status": "pass",
            "evidence_quality_score": 8,
            "valuation_attractiveness_score": 5,
            "ai_beneficiary_score": 7,
            "competitive_position_score": 7,
            "manual_price_verification_required": False,
            "market_data_reliability": "high",
            "financial_statement_reliability": "high",
            "price_data_reliability_from_fetch": "high",
            "valuation_reliability": "medium",
            "output_dir": "outputs/mock_base_nvt",
        },
        {
            "ticker": "WDC",
            "company_name": "Western Digital",
            "theme": "Nearline HDD AI Data Storage Infrastructure",
            "action": "watchlist",
            "suggested_position_pct": 0.0,
            "quality_status": "pass",
            "evidence_quality_score": 8,
            "valuation_attractiveness_score": 5,
            "ai_beneficiary_score": 7,
            "competitive_position_score": 7,
            "manual_price_verification_required": False,
            "market_data_reliability": "high",
            "financial_statement_reliability": "high",
            "price_data_reliability_from_fetch": "high",
            "valuation_reliability": "medium",
            "output_dir": "outputs/mock_base_wdc",
        },
        {
            "ticker": "FN",
            "company_name": "Fabrinet",
            "theme": "Optical Manufacturing AI Data Center",
            "action": "watchlist",
            "suggested_position_pct": 0.0,
            "quality_status": "pass",
            "evidence_quality_score": 8,
            "valuation_attractiveness_score": 5,
            "ai_beneficiary_score": 7,
            "competitive_position_score": 7,
            "manual_price_verification_required": False,
            "market_data_reliability": "high",
            "financial_statement_reliability": "high",
            "price_data_reliability_from_fetch": "high",
            "valuation_reliability": "medium",
            "output_dir": "outputs/mock_base_fn",
        },
    ]).to_csv(mock_baseline_csv, index=False, encoding="utf-8")
    pd.DataFrame([
        {
            "ticker": "NVT",
            "company_name": "nVent",
            "theme": "Data Center Electrical Enclosures Infrastructure",
            "action": "tracking_position",
            "suggested_position_pct": 1.0,
            "quality_status": "deep_research_candidate",
            "evidence_quality_score": 8,
            "valuation_attractiveness_score": 5,
            "ai_beneficiary_score": 8,
            "competitive_position_score": 8,
            "chokepoint_score": 9,
            "chokepoint_adjusted_score": 8.1,
            "weighted_investment_score": 7.6,
            "serenity_thesis_quality": "high_quality_chokepoint",
            "chokepoint_evidence_level": "primary_supported",
            "deep_research_priority": "high",
            "scout_recommendation": "deep_research",
            "chokepoint_overlay_applied": True,
            "chokepoint_overlay_reason": "high_quality_chokepoint_tracking_upgrade",
            "manual_price_verification_required": False,
            "market_data_reliability": "high",
            "financial_statement_reliability": "high",
            "price_data_reliability_from_fetch": "high",
            "valuation_reliability": "medium",
            "guardrail_warnings": "",
            "market_awareness_score": 5,
            "valuation_risk_score": 6,
            "output_dir": "outputs/mock_choke_nvt",
        },
        {
            "ticker": "WDC",
            "company_name": "Western Digital",
            "theme": "Nearline HDD AI Data Storage Infrastructure",
            "action": "tracking_position",
            "suggested_position_pct": 1.0,
            "quality_status": "deep_research_candidate",
            "evidence_quality_score": 8,
            "valuation_attractiveness_score": 5,
            "ai_beneficiary_score": 8,
            "competitive_position_score": 8,
            "chokepoint_score": 9,
            "chokepoint_adjusted_score": 6.0,
            "weighted_investment_score": 6.8,
            "serenity_thesis_quality": "interesting_unproven",
            "chokepoint_evidence_level": "hypothesis_only",
            "deep_research_priority": "medium",
            "scout_recommendation": "monitor_for_evidence",
            "chokepoint_overlay_applied": True,
            "chokepoint_overlay_reason": "high_quality_chokepoint_tracking_upgrade",
            "manual_price_verification_required": False,
            "market_data_reliability": "high",
            "financial_statement_reliability": "high",
            "price_data_reliability_from_fetch": "high",
            "valuation_reliability": "medium",
            "guardrail_warnings": "",
            "market_awareness_score": 5,
            "valuation_risk_score": 6,
            "output_dir": "outputs/mock_choke_wdc",
        },
        {
            "ticker": "FN",
            "company_name": "Fabrinet",
            "theme": "Optical Manufacturing AI Data Center",
            "action": "watchlist",
            "suggested_position_pct": 0.0,
            "quality_status": "pass",
            "evidence_quality_score": 8,
            "valuation_attractiveness_score": 5,
            "ai_beneficiary_score": 8,
            "competitive_position_score": 8,
            "chokepoint_score": 8,
            "chokepoint_adjusted_score": 7.5,
            "weighted_investment_score": 7.2,
            "serenity_thesis_quality": "already_priced_in",
            "chokepoint_evidence_level": "secondary_supported",
            "deep_research_priority": "high",
            "scout_recommendation": "deep_research",
            "chokepoint_overlay_applied": True,
            "chokepoint_overlay_reason": "high_quality_chokepoint_tracking_upgrade",
            "manual_price_verification_required": False,
            "market_data_reliability": "high",
            "financial_statement_reliability": "high",
            "price_data_reliability_from_fetch": "high",
            "valuation_reliability": "medium",
            "guardrail_warnings": "chokepoint_already_priced_in_caps_position_at_1pct",
            "market_awareness_score": 9,
            "valuation_risk_score": 9,
            "output_dir": "outputs/mock_choke_fn",
        },
    ]).to_csv(mock_treatment_csv, index=False, encoding="utf-8")
    abtest_compare = compare_chokepoint_abtest(
        str(mock_baseline_csv),
        str(mock_treatment_csv),
        abtest_validate_dir,
        abtest_run_id,
    )
    assert Path(abtest_compare["comparison_csv"]).exists(), "A/B comparison CSV should exist"
    abtest_df = abtest_compare["comparison_df"]
    nvt_ab = abtest_df[abtest_df["ticker"] == "NVT"].iloc[0]
    wdc_ab = abtest_df[abtest_df["ticker"] == "WDC"].iloc[0]
    fn_ab = abtest_df[abtest_df["ticker"] == "FN"].iloc[0]
    assert summary_bool(nvt_ab["good_promotion"]), "NVT mock should be a good promotion"
    assert summary_bool(wdc_ab["suspicious_promotion"]), "WDC mock should be a suspicious promotion"
    assert summary_bool(fn_ab["guardrail_blocked_chokepoint"]), "FN mock should be guardrail blocked"
    abtest_report = build_chokepoint_abtest_report(
        abtest_df,
        str(mock_baseline_csv),
        str(mock_treatment_csv),
        abtest_run_id,
    )
    for section in [
        "## Overview",
        "## Promotions",
        "## Good Promotions",
        "## Suspicious Promotions",
        "## Guardrail Blocked Chokepoint Ideas",
    ]:
        assert section in abtest_report, f"A/B report missing {section}"
    abtest_report_path = abtest_validate_dir / f"chokepoint_abtest_report_{abtest_run_id}.md"
    save_text(abtest_report_path, abtest_report)
    manifest = save_chokepoint_abtest_manifest(
        output_dir=abtest_validate_dir,
        run_id=abtest_run_id,
        watchlist_path="mock_watchlist.csv",
        baseline_summary_csv=str(mock_baseline_csv),
        treatment_summary_csv=str(mock_treatment_csv),
        comparison_csv=abtest_compare["comparison_csv"],
        report_md=str(abtest_report_path),
        baseline_output_root="outputs/mock_baseline",
        treatment_output_root="outputs/mock_treatment",
        limit=3,
        max_peers=0,
        no_reuse=True,
        comparison_df=abtest_df,
    )
    assert Path(manifest["manifest_json"]).exists(), "A/B manifest JSON should exist"
    assert manifest["good_promotion_count"] == 1, "A/B manifest should count good promotions"
    assert manifest["suspicious_promotion_count"] == 1, "A/B manifest should count suspicious promotions"
    assert manifest["guardrail_blocked_count"] == 1, "A/B manifest should count guardrail blocked ideas"
    console.print("[bold green]All validation checks passed.[/bold green]")


def main() -> None:
    parser = argparse.ArgumentParser(description=RESEARCH_VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("single")
    p1.add_argument("--ticker", required=True)
    p1.add_argument("--name", required=True)
    p1.add_argument("--theme", default="AI Supply Chain")
    p1.add_argument("--market", default="US")
    p1.add_argument("--portfolio", default="portfolio.csv", help="Legacy no-op for PM recommendations; use offline portfolio exposure reports instead.")
    p1.add_argument("--output", default="outputs")
    p1.add_argument("--watchlist", default=DEFAULT_WATCHLIST_PATH)
    p1.add_argument("--max-peers", type=int, default=None)
    p1.add_argument("--no-peers", action="store_true")
    p1.add_argument("--no-web-discovery", action="store_true")
    p1.add_argument("--no-evidence-search", action="store_true")
    p1.add_argument("--no-reuse", action="store_true")
    p1.add_argument("--skip-chokepoint", action="store_true")

    p2 = sub.add_parser("batch")
    p2.add_argument("--watchlist", default=DEFAULT_WATCHLIST_PATH)
    p2.add_argument("--portfolio", default="portfolio.csv", help="Legacy no-op for PM recommendations; use offline portfolio exposure reports instead.")
    p2.add_argument("--output", default="outputs")
    p2.add_argument("--limit", type=int, default=None)
    p2.add_argument("--max-peers", type=int, default=None)
    p2.add_argument("--no-web-discovery", action="store_true")
    p2.add_argument("--no-evidence-search", action="store_true")
    p2.add_argument("--no-reuse", action="store_true")
    p2.add_argument("--skip-chokepoint", action="store_true")

    p3 = sub.add_parser("log")
    p3.add_argument("--output", default="outputs")
    p3.add_argument("--top", type=int, default=20)
    p3.add_argument("--quality", action="store_true")
    p3.add_argument("--rerun", action="store_true")
    p3.add_argument("--top-ideas", action="store_true")

    p4 = sub.add_parser("scout")
    p4.add_argument("--watchlist", default=DEFAULT_WATCHLIST_PATH)
    p4.add_argument("--output", default="outputs")
    p4.add_argument("--limit", type=int, default=None)
    p4.add_argument("--ticker", default="")
    p4.add_argument("--name", default="")
    p4.add_argument("--theme", default="AI Supply Chain")
    p4.add_argument("--market", default="US")
    p4.add_argument("--cache", default=FACT_CACHE_PATH)
    p4.add_argument("--no-evidence-search", action="store_true")

    p5 = sub.add_parser("abtest-chokepoint")
    p5.add_argument("--watchlist", default="watchlist_chokepoint_test.csv")
    p5.add_argument("--portfolio", default="portfolio.csv", help="Legacy no-op for PM recommendations; use offline portfolio exposure reports instead.")
    p5.add_argument("--output", default="outputs")
    p5.add_argument("--limit", type=int, default=None)
    p5.add_argument("--max-peers", type=int, default=None)
    p5.add_argument("--no-reuse", action="store_true")
    p5.add_argument("--baseline-csv", default="")
    p5.add_argument("--treatment-csv", default="")
    p5.add_argument("--run-id", default="")
    p5.add_argument("--create-default-watchlist", action="store_true")
    p5.add_argument("--skip-run", action="store_true")

    sub.add_parser("validate")

    args = parser.parse_args()

    if args.command == "single":
        apply_runtime_cli_flags(args)
        run_single(args.ticker, args.name, args.theme, args.market, args.portfolio, args.output, args.watchlist)
    elif args.command == "batch":
        apply_runtime_cli_flags(args)
        run_batch(args.watchlist, args.portfolio, args.output, args.limit)
    elif args.command == "log":
        show_log(args.output, args.top, quality=args.quality, rerun=args.rerun, top_ideas=args.top_ideas)
    elif args.command == "scout":
        apply_runtime_cli_flags(args)
        run_fact_scout(
            watchlist_path=args.watchlist,
            output_root=args.output,
            limit=args.limit,
            ticker=args.ticker,
            name=args.name,
            theme=args.theme,
            market=args.market,
            cache_path=args.cache,
        )
    elif args.command == "abtest-chokepoint":
        if args.create_default_watchlist:
            create_default_chokepoint_test_watchlist(args.watchlist)
        if args.baseline_csv and args.treatment_csv:
            run_chokepoint_abtest_compare_only(
                baseline_csv=args.baseline_csv,
                treatment_csv=args.treatment_csv,
                output_root=args.output,
                run_id=args.run_id or None,
                watchlist_path=args.watchlist,
            )
        elif args.skip_run:
            raise ValueError("--skip-run requires both --baseline-csv and --treatment-csv.")
        else:
            run_chokepoint_abtest(
                watchlist_path=args.watchlist,
                portfolio_path=args.portfolio,
                output_root=args.output,
                limit=args.limit,
                max_peers=args.max_peers,
                no_reuse=args.no_reuse,
                run_id=args.run_id or None,
            )
    elif args.command == "validate":
        run_validation()


if __name__ == "__main__":
    main()

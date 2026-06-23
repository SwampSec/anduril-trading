"""Build JSON context packs from market data for copilot workflows."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import finnhub
import yfinance as yf
from dotenv import load_dotenv

from copilot.timing import analyze_timing

ENV_PATH = Path.home() / "Anduril" / ".env.trading"
load_dotenv(ENV_PATH)

FH_KEY = os.getenv("FINNHUB_API_KEY", "")
FH = finnhub.Client(api_key=FH_KEY) if FH_KEY and FH_KEY != "YOUR_KEY_HERE" else None


def _safe(v, default=None):
    try:
        if v is None:
            return default
        x = float(v)
        return default if x != x else x
    except Exception:
        return default


def build_context(ticker: str, horizon: str = "swing") -> dict:
    t = ticker.upper().strip()
    tk = yf.Ticker(t)
    info = tk.info or {}
    hist1 = tk.history(period="1y", auto_adjust=True)
    hist5d = tk.history(period="5d", interval="1h", auto_adjust=True)

    earnings = []
    news = []
    if FH:
        try:
            earnings = FH.company_earnings(t, limit=8) or []
        except Exception:
            pass
        try:
            ago = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
            today = datetime.now().strftime("%Y-%m-%d")
            news = (FH.company_news(t, _from=ago, to=today) or [])[:10]
        except Exception:
            pass

    hist_for_timing = hist5d if horizon == "day" and not hist5d.empty else hist1
    timing = analyze_timing(hist_for_timing, horizon=horizon)

    price = _safe(info.get("regularMarketPrice") or info.get("currentPrice"))
    if not price and not hist1.empty:
        price = float(hist1["Close"].iloc[-1])

    earn_summary = []
    for e in (earnings or [])[:6]:
        earn_summary.append({
            "period": e.get("period"),
            "actual": e.get("actual"),
            "estimate": e.get("estimate"),
            "surprise_pct": e.get("surprisePercent"),
        })

    headlines = []
    for n in news:
        headlines.append({
            "datetime": n.get("datetime"),
            "headline": n.get("headline"),
            "source": n.get("source"),
            "summary": (n.get("summary") or "")[:200],
        })

    return {
        "ticker": t,
        "name": info.get("longName") or info.get("shortName") or t,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": price,
        "market_cap": info.get("marketCap"),
        "pe_ttm": _safe(info.get("trailingPE")),
        "forward_pe": _safe(info.get("forwardPE")),
        "peg": _safe(info.get("pegRatio")),
        "revenue_growth": _safe(info.get("revenueGrowth")),
        "earnings_growth": _safe(info.get("earningsGrowth")),
        "profit_margin": _safe(info.get("profitMargins")),
        "beta": _safe(info.get("beta")),
        "target_mean": _safe(info.get("targetMeanPrice")),
        "recommendation": info.get("recommendationKey"),
        "52w_high": _safe(info.get("fiftyTwoWeekHigh")),
        "52w_low": _safe(info.get("fiftyTwoWeekLow")),
        "horizon": horizon,
        "timing": timing,
        "earnings_history": earn_summary,
        "recent_news": headlines,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

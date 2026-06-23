"""Run copilot workflows — workflow-specific rules; optional LLM narrative."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yfinance as yf

from copilot.context import build_context
from copilot.timing import analyze_timing
from copilot import llm

PLAYBOOK_DIR = Path(__file__).resolve().parent / "playbooks"

WORKFLOWS = {
    "morning_note": {
        "title": "Morning Note",
        "file": "morning_note.md",
        "description": "Daily pulse + buy/hold read across day, swing, and long horizons",
    },
    "earnings_recap": {
        "title": "Earnings Recap",
        "file": "earnings_recap.md",
        "description": "Earnings history + impact on day trade vs long-term thesis",
    },
    "thesis_timing": {
        "title": "Thesis & Timing",
        "file": "thesis_timing.md",
        "description": "When to buy/sell for day trade and 3-12 month holds",
    },
}


def _load_playbook(name: str) -> str:
    meta = WORKFLOWS.get(name)
    if not meta:
        raise ValueError(f"Unknown workflow: {name}")
    return (PLAYBOOK_DIR / meta["file"]).read_text(encoding="utf-8")


def _pct(v):
    if v is None:
        return "N/A"
    try:
        x = float(v)
        return f"{x * 100:.1f}%" if abs(x) <= 1 else f"{x:.1f}%"
    except Exception:
        return "N/A"


def _timing_error(t: dict) -> str | None:
    return t.get("error") if isinstance(t, dict) else None


def _conviction_score(t: dict) -> int:
    scores = (t or {}).get("scores") or {}
    buy = scores.get("buy", 0)
    sell = scores.get("sell", 0)
    return max(1, min(10, round(5 + (buy - sell) / 20)))


def _enrich_for_workflow(ctx: dict, workflow: str, ticker: str) -> dict:
    if workflow != "morning_note":
        return ctx
    tk = yf.Ticker(ticker.upper())
    hist1 = tk.history(period="1y", auto_adjust=True)
    hist5d = tk.history(period="5d", interval="1h", auto_adjust=True)
    day_hist = hist5d if not hist5d.empty else hist1
    ctx["timing_by_horizon"] = {
        "day": analyze_timing(day_hist, "day"),
        "swing": analyze_timing(hist1, "swing"),
        "long": analyze_timing(hist1, "long"),
    }
    return ctx


def _news_bullets(ctx: dict, limit: int = 3) -> list[str]:
    lines = []
    for n in (ctx.get("recent_news") or [])[:limit]:
        headline = n.get("headline") or "Headline unavailable"
        source = n.get("source") or "?"
        lines.append(f"- **{headline}** ({source})")
    return lines or ["- No recent headlines in data feed."]


def _earnings_pattern(history: list) -> str:
    if not history:
        return "No earnings history in data — [NOT IN DATA]"
    beats = misses = inline = 0
    rows = []
    for e in history[:6]:
        actual = e.get("actual")
        est = e.get("estimate")
        surprise = e.get("surprise_pct")
        period = e.get("period") or "?"
        if actual is None or est is None:
            tag = "N/A"
        elif actual > est:
            tag, beats = "Beat", beats + 1
        elif actual < est:
            tag, misses = "Miss", misses + 1
        else:
            tag, inline = "Inline", inline + 1
        sur = f" ({surprise:+.1f}%)" if surprise is not None else ""
        rows.append(f"- **{period}:** {tag} — actual {actual} vs est {est}{sur}")
    summary = f"Pattern: {beats} beat / {misses} miss / {inline} inline (last {len(rows)} prints)"
    return summary + "\n" + "\n".join(rows)


def _horizon_row(label: str, t: dict) -> str:
    if _timing_error(t):
        return f"| {label} | — | {_timing_error(t)} |"
    return (
        f"| {label} | {t.get('bias', '—')} | "
        f"{t.get('action', '—')} (S ${t.get('support')} / R ${t.get('resistance')}) |"
    )


def _signals_block(t: dict, limit: int = 4) -> list[str]:
    if _timing_error(t):
        return [f"- {_timing_error(t)}"]
    lines = []
    for s in (t.get("signals") or [])[:limit]:
        lines.append(f"- **[{s['action'].upper()}]** {s['note']}")
    return lines or ["- No active signals."]


def _rule_morning_note(ctx: dict) -> str:
    t = ctx.get("timing") or {}
    by_h = ctx.get("timing_by_horizon") or {}
    td = by_h.get("day") or t
    ts = by_h.get("swing") or t
    tl = by_h.get("long") or t

    lines = [
        f"## Morning Note — {ctx.get('name')} ({ctx.get('ticker')})",
        f"*Generated {ctx.get('generated_at', datetime.now().isoformat(timespec='seconds'))}*",
        "",
        "### 1. Market pulse",
    ]
    lines.extend(_news_bullets(ctx, 3))
    if ctx.get("sector"):
        lines.append(f"- Sector: **{ctx.get('sector')}** / {ctx.get('industry') or '—'}")

    if _timing_error(t):
        lines += ["", f"**Timing error:** {_timing_error(t)}"]
        return "\n".join(lines)

    lines += [
        "",
        "### 2. Ticker focus",
        f"- **Price:** ${t.get('price')}  |  **Bias ({ctx.get('horizon', 'swing')}):** {t.get('bias')}",
        f"- **Levels:** Support ${t.get('support')}  |  Resistance ${t.get('resistance')}  |  Stop ${t.get('stop_loss')}",
        "",
        "### 3. Day trade lens",
        f"- Bias: **{td.get('bias', '—')}** — {td.get('action', '—')}",
        f"- RSI {td.get('rsi')}  |  Vol {td.get('volume_vs_avg20')}x avg  |  5d {td.get('return_5d_pct')}%",
    ]
    lines.extend(_signals_block(td, 2))

    lines += [
        "",
        "### 4. Swing lens (weeks)",
        f"- Bias: **{ts.get('bias', '—')}** — {ts.get('action', '—')}",
        f"- MACD {'bullish' if ts.get('macd_bullish') else 'bearish'}  |  20d {ts.get('return_20d_pct')}%  |  52w position {ts.get('pos_52w_pct')}%",
    ]
    lines.extend(_signals_block(ts, 2))

    lines += [
        "",
        "### 5. Long-term lens (months)",
        f"- Bias: **{tl.get('bias', '—')}** — {tl.get('action', '—')}",
        f"- P/E {_fmt(ctx.get('pe_ttm'))}  |  Rev growth {_pct(ctx.get('revenue_growth'))}  |  Margin {_pct(ctx.get('profit_margin'))}",
        f"- Analyst: {ctx.get('recommendation') or 'N/A'}  |  Target ${ctx.get('target_mean') or '—'}",
    ]
    lines.extend(_signals_block(tl, 2))

    lines += [
        "",
        "### 6. Action summary",
        "| Horizon | Bias | Plan |",
        "| --- | --- | --- |",
        _horizon_row("Day", td),
        _horizon_row("Swing", ts),
        _horizon_row("Long", tl),
        "",
        "*Rule-based morning note. **Enhance with AI** for narrative polish via LM Studio.*",
    ]
    return "\n".join(lines)


def _fmt(v):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.2f}"
    except Exception:
        return str(v)


def _rule_earnings_recap(ctx: dict) -> str:
    t = ctx.get("timing") or {}
    lines = [
        f"## Earnings Recap — {ctx.get('name')} ({ctx.get('ticker')})",
        f"*Horizon focus: {ctx.get('horizon', 'swing').upper()}*",
        "",
        "### 1. Headline read",
        _earnings_pattern(ctx.get("earnings_history") or []),
        "",
        "### 2. What mattered (fundamentals)",
        f"- P/E (TTM): {_fmt(ctx.get('pe_ttm'))}  |  Fwd P/E: {_fmt(ctx.get('forward_pe'))}  |  PEG: {_fmt(ctx.get('peg'))}",
        f"- Revenue growth: {_pct(ctx.get('revenue_growth'))}  |  Earnings growth: {_pct(ctx.get('earnings_growth'))}",
        f"- Profit margin: {_pct(ctx.get('profit_margin'))}  |  Beta: {_fmt(ctx.get('beta'))}",
        "",
        "### 3. Stock reaction context",
    ]
    if _timing_error(t):
        lines.append(f"- {_timing_error(t)}")
    else:
        lines += [
            f"- **Technical bias:** {t.get('bias')} — {t.get('action')}",
            f"- Returns: 5d {t.get('return_5d_pct')}%  |  20d {t.get('return_20d_pct')}%  |  60d {t.get('return_60d_pct')}%",
            f"- 52-week range position: {t.get('pos_52w_pct')}%  |  Volume vs 20d: {t.get('volume_vs_avg20')}x",
        ]

    lines += ["", "### 4. Day trade impact"]
    if ctx.get("horizon") == "day" and not _timing_error(t):
        lines.extend(_signals_block(t, 3))
        lines.append(f"- Next-session stop reference: ${t.get('stop_loss')}")
    else:
        lines.append("- Switch horizon to **Day trade** for session-level read, or use **Enhance with AI**.")

    lines += ["", "### 5. Swing impact (weeks)"]
    if not _timing_error(t):
        lines.append(f"- Trend read: MACD {'bullish' if t.get('macd_bullish') else 'bearish'}; bias **{t.get('bias')}**")
        lines.extend(_signals_block(t, 2))
    else:
        lines.append(f"- {_timing_error(t)}")

    lines += [
        "",
        "### 6. Long-term impact (months–year)",
        f"- Analyst recommendation: **{ctx.get('recommendation') or 'N/A'}**  |  Target ${ctx.get('target_mean') or '—'}",
        f"- Thesis filter: Rev growth {_pct(ctx.get('revenue_growth'))}, margin {_pct(ctx.get('profit_margin'))}",
    ]
    if ctx.get("earnings_history"):
        last = ctx["earnings_history"][0]
        lines.append(
            f"- Latest print ({last.get('period')}): actual {last.get('actual')} vs est {last.get('estimate')}"
        )

    lines += [
        "",
        "### 7. Levels",
    ]
    if _timing_error(t):
        lines.append(f"- {_timing_error(t)}")
    else:
        lines.append(
            f"- Support ${t.get('support')}  |  Resistance ${t.get('resistance')}  |  Stop ${t.get('stop_loss')}"
        )

    lines += [
        "",
        "### 8. Verdict",
        "| Horizon | Bias | Key trigger |",
        "| --- | --- | --- |",
    ]
    if not _timing_error(t):
        top = (t.get("signals") or [{}])[0]
        trigger = top.get("note", t.get("action", "—"))
        lines.append(f"| {ctx.get('horizon', 'swing').title()} | {t.get('bias')} | {trigger} |")
        lines.append(f"| Long-term | {'Bullish' if (ctx.get('revenue_growth') or 0) > 0 else 'Caution'} | Fundamentals + last earnings trend |")
    else:
        lines.append(f"| — | — | {_timing_error(t)} |")

    lines += [
        "",
        "*Rule-based earnings recap. **Enhance with AI** for full narrative (LM Studio).*",
    ]
    return "\n".join(lines)


def _rule_thesis_timing(ctx: dict) -> str:
    t = ctx.get("timing") or {}
    if _timing_error(t):
        return f"**Timing error:** {_timing_error(t)}"

    thesis = []
    if ctx.get("sector"):
        thesis.append(f"**{ctx.get('sector')}** exposure via {ctx.get('industry') or '—'}")
    if ctx.get("revenue_growth") is not None:
        thesis.append(f"Revenue growth {_pct(ctx.get('revenue_growth'))} — {'expanding' if ctx.get('revenue_growth', 0) > 0 else 'contracting'} story")
    if ctx.get("recommendation"):
        thesis.append(f"Street view: **{ctx.get('recommendation')}** (target ${ctx.get('target_mean') or '—'})")
    if not thesis:
        thesis.append("Insufficient fundamental tags — lean on price action and levels below.")

    risks = []
    if (ctx.get("beta") or 0) > 1.3:
        risks.append(f"High beta ({_fmt(ctx.get('beta'))}) — wider swings")
    if (t.get("pos_52w_pct") or 0) > 85:
        risks.append("Trading near 52-week highs — extension risk")
    if (t.get("pos_52w_pct") or 0) < 20:
        risks.append("Near 52-week lows — falling knife risk unless thesis intact")
    for n in (ctx.get("recent_news") or [])[:2]:
        risks.append(f"News: {n.get('headline', '')[:80]}")

    scores = t.get("scores") or {}
    conv = _conviction_score(t)

    lines = [
        f"## Thesis & Timing — {ctx.get('name')} ({ctx.get('ticker')})",
        f"**Horizon:** {ctx.get('horizon', 'swing').upper()}  |  **Price:** ${t.get('price')}  |  **Bias:** {t.get('bias')}",
        "",
        "### 1. Investment thesis",
    ]
    for b in thesis[:3]:
        lines.append(f"- {b}")

    lines += [
        "",
        "### 2. Day trade plan",
        f"- **Entry trigger:** Pullback to support ${t.get('support')} with RSI confirmation, or breakout above ${t.get('resistance')}",
        f"- **Stop / invalidation:** ${t.get('stop_loss')}",
        f"- **Take-profit zone:** ${t.get('resistance')} (20d high)",
        "",
        "### 3. Swing plan (2–8 weeks)",
        f"- **Entry trigger:** {t.get('action')}",
        f"- **Stop:** ${t.get('stop_loss')}  |  **Target:** ${t.get('resistance')}",
        f"- MACD {'bullish' if t.get('macd_bullish') else 'bearish'}  |  20d return {t.get('return_20d_pct')}%",
        "",
        "### 4. Long-term plan (3–12 months)",
        f"- **Accumulation zone:** ${t.get('support')} – ${t.get('price')} if fundamentals hold",
        f"- **Thesis break:** Close below ${t.get('stop_loss')} on volume, or material miss vs growth narrative",
        f"- **Target logic:** Analyst mean ${ctx.get('target_mean') or '—'} vs spot ${t.get('price')}",
        "",
        "### 5. Risk flags",
    ]
    lines.extend(f"- {r}" for r in (risks or ["- No major flags from available data."]))

    lines += [
        "",
        "### 6. Conviction score (1–10)",
        f"- **Selected horizon ({ctx.get('horizon')}):** {conv}/10 (buy {scores.get('buy', 0)}% / sell {scores.get('sell', 0)}%)",
        "",
        "### 7. Signals",
    ]
    lines.extend(_signals_block(t, 5))
    lines += [
        "",
        "### 8. Bottom line",
        f"{ctx.get('name')} is **{t.get('bias').lower()}** on the {ctx.get('horizon')} horizon. "
        f"{t.get('action')} Key levels: support ${t.get('support')}, resistance ${t.get('resistance')}.",
        "",
        "*Rule-based plan. **Enhance with AI** for full multi-horizon narrative (LM Studio).*",
    ]
    return "\n".join(lines)


def _rule_based_summary(ctx: dict, workflow: str) -> str:
    wf = workflow if workflow in WORKFLOWS else "thesis_timing"
    builders = {
        "morning_note": _rule_morning_note,
        "earnings_recap": _rule_earnings_recap,
        "thesis_timing": _rule_thesis_timing,
    }
    return builders[wf](ctx)


def run(workflow: str, ticker: str, horizon: str = "swing", use_llm: bool = False) -> dict:
    wf = workflow if workflow in WORKFLOWS else "thesis_timing"
    ctx = build_context(ticker, horizon=horizon)
    ctx = _enrich_for_workflow(ctx, wf, ticker)
    result = {
        "workflow": wf,
        "ticker": ticker.upper(),
        "horizon": horizon,
        "context": ctx,
        "markdown": _rule_based_summary(ctx, wf),
        "llm_used": False,
        "llm_error": None,
    }

    if not use_llm:
        return result

    if not llm.available():
        result["llm_error"] = "LM Studio not reachable at LMSTUDIO_URL (default http://localhost:1234/v1)"
        return result

    system = _load_playbook(wf)
    user = (
        f"Workflow: {WORKFLOWS[wf]['title']}\n"
        f"Ticker: {ticker.upper()}\nHorizon focus: {horizon}\n\n"
        f"DATA (JSON):\n{llm.format_context_json(ctx)}"
    )
    text, err = llm.chat(system, user)
    if err:
        result["llm_error"] = err
    else:
        result["markdown"] = text
        result["llm_used"] = True
    return result

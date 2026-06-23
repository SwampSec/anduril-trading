"""Rule-based buy/sell timing from price history and indicators."""
from __future__ import annotations

import pandas as pd
import ta


def _last(series, default=None):
    try:
        v = float(series.iloc[-1])
        return v if v == v else default
    except Exception:
        return default


def analyze_timing(hist: pd.DataFrame, horizon: str = "swing") -> dict:
    """
    horizon: 'day' | 'swing' | 'long'
    Returns structured timing signals for the selected holding period.
    """
    if hist is None or hist.empty or len(hist) < 30:
        return {"error": "Not enough price history (need 30+ bars)"}

    close = hist["Close"].squeeze()
    high = hist["High"].squeeze()
    low = hist["Low"].squeeze()
    vol = hist["Volume"].squeeze()
    price = _last(close)

    rsi = _last(ta.momentum.RSIIndicator(close, window=14).rsi(), 50)
    macd_ind = ta.trend.MACD(close)
    macd = _last(macd_ind.macd(), 0)
    macd_sig = _last(macd_ind.macd_signal(), 0)
    macd_bull = macd > macd_sig

    ema9 = _last(ta.trend.EMAIndicator(close, window=9).ema_indicator(), price)
    ema21 = _last(ta.trend.EMAIndicator(close, window=21).ema_indicator(), price)
    ema50 = _last(ta.trend.EMAIndicator(close, window=50).ema_indicator(), price)
    sma200 = _last(close.rolling(200).mean(), None) if len(close) >= 200 else None

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = _last(bb.bollinger_hband(), price)
    bb_lower = _last(bb.bollinger_lband(), price)
    bb_pos = (price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5

    h20 = float(high.tail(20).max())
    l20 = float(low.tail(20).min())
    h52 = float(high.max())
    l52 = float(low.min())
    pos52 = (price - l52) / (h52 - l52) if h52 != l52 else 0.5

    vol_avg20 = float(vol.tail(20).mean()) or 1
    vol_ratio = float(vol.iloc[-1]) / vol_avg20

    ret5 = (price / float(close.iloc[-6]) - 1) * 100 if len(close) > 5 else 0
    ret20 = (price / float(close.iloc[-21]) - 1) * 100 if len(close) > 20 else 0
    ret60 = (price / float(close.iloc[-61]) - 1) * 100 if len(close) > 60 else 0

    support = l20
    resist = h20
    stop_day = max(support * 0.995, price * 0.98)
    stop_swing = max(l20 * 0.97, price * 0.92)
    stop_long = max(l52 * 0.95, price * 0.85) if sma200 else price * 0.88

    signals = []

    if horizon == "day":
        if rsi < 35:
            signals.append(("RSI oversold bounce setup", "buy", 0.7))
        elif rsi > 70:
            signals.append(("RSI overbought — fade or wait", "sell", 0.65))
        if price > ema9 > ema21:
            signals.append(("Short-term trend up (EMA9>21)", "buy", 0.75))
        elif price < ema9 < ema21:
            signals.append(("Short-term trend down", "sell", 0.75))
        if vol_ratio > 1.5 and ret5 > 0:
            signals.append(("Volume breakout with momentum", "buy", 0.6))
        elif vol_ratio > 1.5 and ret5 < 0:
            signals.append(("Heavy volume selloff", "sell", 0.6))
        if price <= bb_lower * 1.01:
            signals.append(("At lower Bollinger — mean reversion buy zone", "buy", 0.55))
        elif price >= bb_upper * 0.99:
            signals.append(("At upper Bollinger — take profit zone", "sell", 0.55))

    elif horizon == "swing":
        if macd_bull and price > ema21:
            signals.append(("MACD bullish + above EMA21", "buy", 0.8))
        elif not macd_bull and price < ema21:
            signals.append(("MACD bearish + below EMA21", "sell", 0.8))
        if 0.3 <= bb_pos <= 0.55 and ret20 > 0:
            signals.append(("Pullback in uptrend (BB mid-band)", "buy", 0.65))
        if pos52 > 0.85 and ret20 > 15:
            signals.append(("Extended near 52w high — trim risk", "sell", 0.6))
        if ret20 < -10 and rsi < 40:
            signals.append(("Oversold swing — watch for reversal", "buy", 0.5))
        if price > resist * 0.98:
            signals.append(("Testing resistance — breakout or reject", "hold", 0.5))

    else:  # long
        if sma200 and price > sma200 and ema50 > sma200:
            signals.append(("Above 200 SMA — long-term uptrend intact", "buy", 0.85))
        elif sma200 and price < sma200:
            signals.append(("Below 200 SMA — avoid new longs", "sell", 0.8))
        if ret60 > 20 and pos52 > 0.8:
            signals.append(("Strong 3mo run — consider scaling in slowly", "hold", 0.55))
        if ret60 < -15 and pos52 < 0.35:
            signals.append(("Beaten down — value only if fundamentals OK", "hold", 0.5))
        if macd_bull and (not sma200 or price > sma200):
            signals.append(("Momentum supports accumulation", "buy", 0.65))

    buy_score = sum(w for _, a, w in signals if a == "buy")
    sell_score = sum(w for _, a, w in signals if a == "sell")
    hold_score = sum(w for _, a, w in signals if a == "hold")
    total = buy_score + sell_score + hold_score or 1

    if buy_score > sell_score * 1.2:
        bias, action = "Bullish", "Consider entry on pullbacks to support"
    elif sell_score > buy_score * 1.2:
        bias, action = "Bearish", "Avoid new buys; tighten stops or wait"
    else:
        bias, action = "Neutral", "Wait for clearer setup — no edge yet"

    stop = {"day": stop_day, "swing": stop_swing, "long": stop_long}.get(horizon, stop_swing)

    return {
        "horizon": horizon,
        "price": round(price, 2),
        "bias": bias,
        "action": action,
        "support": round(support, 2),
        "resistance": round(resist, 2),
        "stop_loss": round(stop, 2),
        "rsi": round(rsi, 1),
        "macd_bullish": macd_bull,
        "bb_position_pct": round(bb_pos * 100, 1),
        "pos_52w_pct": round(pos52 * 100, 1),
        "return_5d_pct": round(ret5, 2),
        "return_20d_pct": round(ret20, 2),
        "return_60d_pct": round(ret60, 2),
        "volume_vs_avg20": round(vol_ratio, 2),
        "signals": [{"note": n, "action": a, "weight": w} for n, a, w in signals],
        "scores": {
            "buy": round(buy_score / total * 100),
            "sell": round(sell_score / total * 100),
            "hold": round(hold_score / total * 100),
        },
    }

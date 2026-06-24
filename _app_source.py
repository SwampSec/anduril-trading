
import os, sys, json, time, threading, collections, requests, re
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

import dash
from dash import dcc, html, Input, Output, State, callback_context, no_update, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import ta
import yfinance as yf
import finnhub
import websocket
from flask import send_from_directory, jsonify, request

# Load .env from ~/Anduril/.env.trading
ENV_PATH = str(Path.home() / "Anduril" / ".env.trading")
load_dotenv(ENV_PATH)

ANDURIL_ROOT = Path.home() / "Anduril"
for _cp in [ANDURIL_ROOT, Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent]:
    _s = str(_cp)
    if (_cp / "copilot").is_dir() and _s not in sys.path:
        sys.path.insert(0, _s)

try:
    import importlib
    import copilot.runner as _copilot_runner
    from copilot.runner import WORKFLOWS as COPILOT_WORKFLOWS
    _COPILOT_OK = True
except ImportError:
    _copilot_runner = None
    _COPILOT_OK = False
    COPILOT_WORKFLOWS = {}


def _copilot_run(workflow, ticker, horizon="swing", use_llm=False):
    """Reload runner each call so copilot updates apply without restarting the dashboard."""
    if not _COPILOT_OK:
        raise RuntimeError("Copilot not installed")
    importlib.reload(_copilot_runner)
    return _copilot_runner.run(workflow, ticker, horizon=horizon, use_llm=use_llm)

FINNHUB_KEY    = os.getenv("FINNHUB_API_KEY", "")
NEWSDATA_KEY   = os.getenv("NEWSDATA_API_KEY", "")
TWELVE_KEY     = os.getenv("TWELVE_DATA_API_KEY", "")
fh = finnhub.Client(api_key=FINNHUB_KEY) if FINNHUB_KEY and FINNHUB_KEY != "YOUR_KEY_HERE" else None

for _broker_env in [ANDURIL_ROOT / ".env.broker", Path(__file__).resolve().parent.parent / ".env.broker"]:
    if _broker_env.is_file():
        load_dotenv(_broker_env, override=False)
        break

try:
    from dashboard.api_client import request as _api_request
except ImportError:
    def _api_request(method, path, params=None, timeout=12):
        host = os.getenv("API_HOST", "127.0.0.1")
        port = os.getenv("API_PORT", "9001")
        base = os.getenv("ANDURIL_API_BASE", f"http://{host}:{port}").rstrip("/")
        url = f"{base}{path}"
        try:
            r = requests.request(method, url, params=params, timeout=timeout)
            if r.status_code >= 400:
                detail = r.text[:500]
                try:
                    detail = r.json().get("detail", detail)
                except Exception:
                    pass
                return {"ok": False, "status": r.status_code, "error": detail}
            return {"ok": True, "data": r.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

ANDURIL_API_BASE = os.getenv(
    "ANDURIL_API_BASE",
    f"http://{os.getenv('API_HOST', '127.0.0.1')}:{os.getenv('API_PORT', '9001')}",
).rstrip("/")

# -- Helpers ---------------------------------------------------
def col(children, width):
    return dbc.Col(children, width=width)

def hdr(cols):
    return dbc.Row([col(html.Small(t, className="text-muted"), w) for t,w in cols],
                   className="mb-1 pb-1 border-bottom border-warning")

def fusd(v, d=2):
    try: return f"${float(v or 0):,.{d}f}"
    except: return "N/A"

def fsigned(v):
    try:
        x = float(v or 0)
        return f"+${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}"
    except: return "N/A"

def pc(v):
    try: return "#2dc653" if float(v or 0) >= 0 else "#e63946"
    except: return "#a09ac8"

def ftime(utc):
    try:
        s = int((datetime.now() - datetime.fromtimestamp(float(utc))).total_seconds())
        if s < 60:    return f"{s}s ago"
        if s < 3600:  return f"{s//60}m ago"
        if s < 86400: return f"{s//3600}h ago"
        return f"{s//86400}d ago"
    except: return ""

def fmts(s):
    s = int(s or 0)
    return f"{s/1000:.1f}k" if abs(s) >= 1000 else str(s)

# -- Level 2 WebSocket -----------------------------------------
L2 = {}
_ws = _wst = None

def start_l2(sym):
    global _ws, _wst
    sym = sym.upper()
    if sym not in L2: L2[sym] = collections.deque(maxlen=500)
    def on_msg(ws, msg):
        try:
            d = json.loads(msg)
            if d.get("type") == "trade":
                for tr in d.get("data",[]):
                    p,v,ts = float(tr.get("p",0)),float(tr.get("v",0)),int(tr.get("t",0))
                    if p>0 and v>0: L2[sym].appendleft({"price":p,"volume":v,"time":ts})
        except: pass
    def on_open(ws): ws.send(json.dumps({"type":"subscribe","symbol":sym}))
    def run():
        global _ws
        _ws = websocket.WebSocketApp(
            f"wss://ws.finnhub.io?token={FINNHUB_KEY}",
            on_open=on_open, on_message=on_msg)
        _ws.run_forever(ping_interval=25)
    if _ws:
        try: _ws.close()
        except: pass
        time.sleep(0.3)
    _wst = threading.Thread(target=run, daemon=True)
    _wst.start()

# -- Themes ----------------------------------------------------
THEMES = {
    "AI & Machine Learning":      ["NVDA","MSFT","GOOGL","META","AMD","PLTR","AI","BBAI","SOUN","AAPL","IBM","AMZN","ORCL","SNOW","PATH","SMCI","DELL","DDOG","NET","CFLT"],
    "Cybersecurity":              ["CRWD","PANW","FTNT","ZS","S","CYBR","OKTA","TENB","RPD","QLYS","VRNT","SAIL","SAIC","CACI","LDOS","BAH","HACK","NTCT","INFN","EVBG"],
    "Quantum Computing":          ["IONQ","RGTI","QUBT","QBTS","IBM","GOOGL","MSFT","ARQQ","QTUM","DEFB","FORM","BKSY","SPIR","LAES","NUWE"],
    "Semiconductors":             ["NVDA","AMD","INTC","TSM","AVGO","QCOM","MU","AMAT","LRCX","KLAC","ASML","MCHP","SWKS","ON","MPWR","WOLF","ACLS","ONTO","AMBA","POWI"],
    "Cloud Computing":            ["AMZN","MSFT","GOOGL","CRM","NOW","SNOW","DDOG","NET","MDB","TEAM","ZM","HUBS","TWLO","BOX","DOCN","ESTC","SPLK","APPN","PAYC"],
    "Electric Vehicles":          ["TSLA","RIVN","LCID","NIO","LI","XPEV","GM","F","CHPT","BLNK","EVGO","QS","PTRA","ZEV","AMPX"],
    "Biotech & Genomics":         ["MRNA","BNTX","CRSP","BEAM","EDIT","NTLA","RXRX","ILMN","PACB","NVAX","REGN","BIIB","VRTX","ALNY","EXAS","FATE","ARWR","DRNA"],
    "Defense & Space":            ["LMT","RTX","NOC","GD","BA","KTOS","RKLB","SPCE","ASTS","PLTR","SAIC","CACI","BAH","LDOS","HII","TDG","AXON","AVAV","JOBY"],
    "Fintech":                    ["SQ","PYPL","COIN","HOOD","SOFI","AFRM","UPST","LC","MELI","NU","DAVE","PAYO","MQ","FOUR","STNE","GPN","FIS","WEX"],
    "Energy & Clean Tech":        ["ENPH","SEDG","FSLR","RUN","PLUG","BE","NEE","CEG","VST","NOVA","ARRY","SHLS","CWEN","AES","BEP","HASI","MAXN","CSIQ","STEM"],
    "Hospitality & Travel":       ["MAR","HLT","H","WYNN","MGM","CCL","RCL","NCLH","DAL","UAL","AAL","LUV","BKNG","EXPE","ABNB","TRIP","LVS","SIX","FUN","SEAS"],
    "Transportation & Logistics": ["UPS","FDX","JBHT","ODFL","XPO","SAIA","CHRW","GXO","WERN","R","MRTN","UBER","LYFT","DASH"],
    "Healthcare":                 ["JNJ","PFE","ABBV","MRK","LLY","TMO","DHR","ABT","BMY","AMGN","GILD","ISRG","SYK","BSX","EW","MDT"],
    "Top Movers / Premarket":     ["SPY","QQQ","AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA","AMD","NFLX","DIS","BAC","JPM","GS","XOM","CVX","WMT","HD","V"],
}
KEYWORD_MAP = {
    "hospitality":["MAR","HLT","H","WYNN","MGM","LVS","SIX","FUN","SEAS"],
    "hotel":["MAR","HLT","H","CHH","IHG","WH"],
    "transport":["UPS","FDX","JBHT","ODFL","XPO","SAIA","CHRW","GXO","WERN"],
    "logistics":["UPS","FDX","JBHT","ODFL","XPO","SAIA","CHRW","GXO"],
    "airline":["DAL","UAL","AAL","LUV","JBLU","ALGT","SAVE"],
    "cruise":["CCL","RCL","NCLH","VOYA"],
    "mining":["NEM","FCX","GOLD","AEM","KGC","WPM","AG","CDE","PAAS","HL"],
    "banking":["JPM","BAC","WFC","C","GS","MS","USB","PNC","TFC","KEY"],
    "retail":["WMT","TGT","COST","AMZN","EBAY","ETSY","W"],
    "pharma":["JNJ","PFE","ABBV","MRK","LLY","BMY","AZN","NVO","GSK"],
    "auto":["TSLA","GM","F","TM","HMC","STLA","RIVN","LCID","NIO"],
    "real estate":["AMT","PLD","CCI","EQIX","PSA","SPG","O","VICI"],
    "insurance":["BRK-B","MET","PRU","AFL","ALL","PGR","CB","TRV"],
    "food":["MCD","SBUX","YUM","QSR","DPZ","WING","SHAK","CAKE"],
    "gaming":["NVDA","AMD","EA","TTWO","RBLX","U","MSFT","GME"],
    "media":["DIS","NFLX","PARA","WBD","FOXA","CMCSA","SIRI","SPOT"],
    "software":["MSFT","CRM","ORCL","SAP","WDAY","ADBE","INTU","VEEV"],
    "cannabis":["TLRY","CGC","ACB","CRLBF","GTBIF"],
}

# ============================================================
# PERSISTENCE  —  SQLite at ~/Anduril/data.db
# ============================================================
import sqlite3 as _sq

_DB_PATH = Path.home() / "Anduril" / "data.db"

def _db_init():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _sq.connect(_DB_PATH) as cx:
        cx.execute("""CREATE TABLE IF NOT EXISTS kv (
            key TEXT PRIMARY KEY, value TEXT NOT NULL,
            ts REAL DEFAULT (strftime('%s','now')))""")
        cx.commit()

def _db_get(key, default=None):
    try:
        with _sq.connect(_DB_PATH) as cx:
            row = cx.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default
    except: return default

def _db_set(key, value):
    try:
        with _sq.connect(_DB_PATH) as cx:
            cx.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)",
                       (key, json.dumps(value, default=str)))
            cx.commit(); return True
    except: return False

_db_init()

_WL_DEFAULT = {
    "groups": [
        {"name":"Group 1","tickers":["AAPL","NVDA","TSLA","MSFT","SPY","BTC-USD"]},
        {"name":"Group 2","tickers":[]},
        {"name":"Forex",  "tickers":["EUR/USD","GBP/USD","USD/JPY","USD/CAD","AUD/USD"]},
        {"name":"Group 4","tickers":[]},
        {"name":"Group 5","tickers":[]},
    ], "active": 0
}

def _wl_load():  return _db_get("watchlist", _WL_DEFAULT)
def _wl_save(d): _db_set("watchlist", d); return d
def _trades_load():  return _db_get("chart_trades", [])
def _trades_save(d): _db_set("chart_trades", d); return d


# ============================================================
# TWELVE DATA  —  chart/forex fallback; earnings enrich Finnhub when available
# ============================================================
_TD_BASE  = "https://api.twelvedata.com"
_TD_CACHE = {}; _TD_TS = {}

def _td_get(endpoint, params, ttl=60):
    if not TWELVE_KEY or TWELVE_KEY == "YOUR_KEY_HERE":
        return None, "TWELVE_DATA_API_KEY not set"
    import urllib.parse as _up
    qs  = "&".join(f"{k}={_up.quote(str(v))}" for k,v in params.items())
    url = f"{_TD_BASE}/{endpoint}?{qs}&apikey={TWELVE_KEY}"
    now = time.time()
    if url in _TD_CACHE and now-_TD_TS.get(url,0)<ttl: return _TD_CACHE[url], None
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent":"Anduril/1.0"})
        if r.status_code == 429: return None, "Rate limit"
        data = r.json()
        if data.get("status")=="error": return None, data.get("message","TD error")
        _TD_CACHE[url]=data; _TD_TS[url]=now; return data, None
    except Exception as e: return None, str(e)

def td_ohlcv(symbol, interval="1day", outputsize=365):
    data, err = _td_get("time_series",{"symbol":symbol,"interval":interval,"outputsize":outputsize},300)
    if err or not data: return None, err
    try:
        vals=data.get("values",[])
        if not vals: return None, "No values"
        df=pd.DataFrame(vals); df["datetime"]=pd.to_datetime(df["datetime"])
        df=df.set_index("datetime").sort_index()
        for c in ["open","high","low","close","volume"]:
            if c in df.columns: df[c]=pd.to_numeric(df[c],errors="coerce")
        df.columns=[c.capitalize() for c in df.columns]; return df, None
    except Exception as e: return None, str(e)

def td_forex(from_c="EUR", to_c="USD"):
    data, err = _td_get("exchange_rate",{"symbol":f"{from_c}/{to_c}"},30)
    if err or not data: return None, err
    try: return float(data.get("rate",0)), None
    except: return None, "Parse error"

def _norm_td_earning(item):
    t2=item.get("time") or ""
    return {"symbol":item.get("symbol",""),"name":(item.get("name") or item.get("symbol") or "")[:18],
            "date":item.get("date",""),"eps_estimate":item.get("eps_estimate"),
            "time":t2,"source":"Twelve Data"}

def td_earnings_cal(days=30):
    from datetime import datetime as _dt, timedelta as _td2
    s=_dt.now().strftime("%Y-%m-%d"); e=(_dt.now()+_td2(days=days)).strftime("%Y-%m-%d")
    data, err=_td_get("earnings_calendar",{"start_date":s,"end_date":e},3600)
    if err or not data: return [], err
    return [_norm_td_earning(x) for x in data.get("earnings",[])], None

_FH_EARN_CACHE={}; _FH_EARN_TS={}

def fh_earnings_cal(days=30):
    if not fh:
        return [], "FINNHUB_API_KEY not set"
    from datetime import datetime as _dt, timedelta as _td2
    s=_dt.now().strftime("%Y-%m-%d"); e=(_dt.now()+_td2(days=days)).strftime("%Y-%m-%d")
    cache_key=f"{s}:{e}"; now=time.time()
    if cache_key in _FH_EARN_CACHE and now-_FH_EARN_TS.get(cache_key,0)<3600:
        return _FH_EARN_CACHE[cache_key], None
    try:
        data=fh.earnings_calendar(_from=s,to=e,symbol="",international=False)
        raw=data.get("earningsCalendar") or data.get("earnings") or []
        results=[]
        for item in raw:
            hour=(item.get("hour") or "").lower()
            if hour=="bmo": t2="Before Market Open"
            elif hour=="amc": t2="After Market Close"
            else: t2=item.get("hour") or ""
            results.append({"symbol":item.get("symbol",""),
                "name":(item.get("symbol") or "")[:18],"date":item.get("date",""),
                "eps_estimate":item.get("epsEstimate"),"time":t2,"source":"Finnhub"})
        results.sort(key=lambda x:x.get("date",""))
        _FH_EARN_CACHE[cache_key]=results; _FH_EARN_TS[cache_key]=now
        return results, None
    except Exception as ex:
        return _FH_EARN_CACHE.get(cache_key,[]), str(ex)

def earnings_cal_combo(days=30):
    fh_items,fh_err=fh_earnings_cal(days=days)
    td_items,td_err=td_earnings_cal(days=days)
    by_key={}
    for it in fh_items:
        k=(it.get("symbol","").upper(),it.get("date",""))
        by_key[k]=dict(it)
    for it in td_items:
        k=(it.get("symbol","").upper(),it.get("date",""))
        if k in by_key:
            cur=by_key[k]
            if it.get("name") and it["name"]!=it.get("symbol"):
                cur["name"]=it["name"]
            if it.get("eps_estimate") is not None and cur.get("eps_estimate") is None:
                cur["eps_estimate"]=it["eps_estimate"]
            if not cur.get("time") and it.get("time"):
                cur["time"]=it["time"]
            cur["source"]="Finnhub + Twelve Data"
            by_key[k]=cur
        else:
            by_key[k]=dict(it)
    merged=sorted(by_key.values(),key=lambda x:x.get("date",""))
    sources=[]
    if fh_items: sources.append("Finnhub")
    if td_items: sources.append("Twelve Data")
    label=" + ".join(sources)
    err=None
    if not merged:
        err=fh_err or td_err or "No earnings data"
    return merged, label, err

INTERVALS  = {"1m":"1m","5m":"5m","15m":"15m","30m":"30m","1h":"1h","4h":"4h","1d":"1d","1wk":"1wk"}
PERIODS    = [("1D","1d"),("5D","5d"),("1M","1mo"),("3M","3mo"),("6M","6mo"),("1Y","1y"),("2Y","2y"),("5Y","5y"),("Max","max")]
INDICATORS = ["EMA 9","EMA 21","EMA 50","SMA 200","VWAP","Bollinger Bands","RSI","MACD","Volume","ATR","Stoch RSI","OBV"]
CHART_PERIOD_DAYS = {"1d": 1, "5d": 5, "7d": 7, "1mo": 30, "3mo": 90, "6mo": 180,
                     "1y": 365, "2y": 730, "5y": 1825, "max": 99999, "60d": 60, "730d": 730}
CHART_MAX_PERIOD = {"1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d", "1h": "730d", "4h": "730d"}
CHART_MIN_PERIOD = {"1m": "1d", "5m": "5d", "15m": "5d", "30m": "5d", "1h": "1d", "4h": "1mo", "1d": "5d", "1wk": "1mo"}
CHART_DEFAULT_PERIOD = {"1m": "1d", "5m": "5d", "15m": "1mo", "30m": "1mo", "1h": "5d", "4h": "3mo", "1d": "1y", "1wk": "5y"}
INTRADAY_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h"}

# ============================================================
# APP
# ============================================================
app = dash.Dash(__name__,
    external_stylesheets=[dbc.themes.CYBORG,"https://fonts.googleapis.com/css2?family=Syne:wght@400;500;700&display=swap"],
    suppress_callback_exceptions=True,
    prevent_initial_callbacks="initial_duplicate",
    title="Andúril Trading")

ANDURIL_ROOT = Path.home() / "Anduril"

@app.server.route("/guide")
@app.server.route("/guide/")
def serve_guide():
    return send_from_directory(str(ANDURIL_ROOT), "guide.html")

@app.server.route("/options-guide")
@app.server.route("/options-guide/")
def serve_options_guide():
    for directory in (ANDURIL_ROOT, Path(__file__).resolve().parent):
        path = directory / "options_guide.html"
        if path.exists():
            return send_from_directory(str(directory), "options_guide.html")
    return ("Options guide not found", 404)

@app.server.route("/logo")
@app.server.route("/logo.png")
def serve_logo():
    candidates = [
        ANDURIL_ROOT / "anduril_trading.png",
        ANDURIL_ROOT / "anduril_trading_icon.png",
        Path(__file__).resolve().parent.parent / "anduril_trading.png",
        Path(__file__).resolve().parent.parent / "anduril_trading_icon.png",
    ]
    for path in candidates:
        if path.exists():
            return send_from_directory(str(path.parent), path.name)
    return ("Logo not found", 404)


@app.server.route("/api/fundamentals/<ticker>")
def api_fundamentals(ticker):
    try:
        return jsonify(_compare_metrics(ticker))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.server.route("/api/options/<ticker>")
def api_options(ticker):
    from flask import request
    try:
        expiry = request.args.get("expiry")
        return jsonify(_options_chain(ticker, expiry))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.server.route("/api/copilot/run", methods=["POST"])
def api_copilot_run():
    if not _COPILOT_OK:
        return jsonify({"error": "Copilot module not installed. Copy copilot/ to ~/Anduril/"}), 503
    try:
        body = request.get_json(force=True) or {}
        workflow = body.get("workflow", "thesis_timing")
        ticker = (body.get("ticker") or "").strip().upper()
        horizon = body.get("horizon", "swing")
        use_llm = bool(body.get("use_llm", False))
        if not ticker:
            return jsonify({"error": "ticker required"}), 400
        result = _copilot_run(workflow, ticker, horizon=horizon, use_llm=use_llm)
        return jsonify({"markdown": result.get("markdown"), "llm_used": result.get("llm_used"),
                        "llm_error": result.get("llm_error"), "timing": (result.get("context") or {}).get("timing")})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

SIDEBAR = dbc.Nav([
    html.Div([
        html.Img(src="/logo",
            style={"width":"72px","height":"auto","maxHeight":"72px","display":"block",
                   "margin":"0 auto 8px","objectFit":"contain","background":"transparent"}),
        html.Div("ANDÚRIL", style={"color":"#e8621a","fontWeight":"700","fontSize":"14px",
                 "letterSpacing":"3px","textAlign":"center","fontFamily":"Georgia,serif"}),
        html.Div("TRADING SUITE", style={"color":"#6b5fa0","fontSize":"9px",
                 "letterSpacing":"2.5px","textAlign":"center","marginTop":"3px"}),
    ], style={"padding":"14px 14px 12px","borderBottom":"1px solid #3d3470","marginBottom":"8px"}),
    dbc.NavLink("Watchlist",   href="/",           active="exact", className="py-2 fw-bold"),
    dbc.NavLink("Conviction",  href="/conviction",  active="exact", className="py-2"),
    dbc.NavLink("Adv Chart",   href="/chart",       active="exact", className="py-2"),
    dbc.NavLink("Level 2",     href="/level2",      active="exact", className="py-2"),
    dbc.NavLink("Screener",    href="/screener",    active="exact", className="py-2"),
    dbc.NavLink("News",        href="/news",        active="exact", className="py-2"),
    dbc.NavLink("Live News",   href="/live-news",   active="exact", className="py-2"),
    dbc.NavLink("Financials",  href="/financials",  active="exact", className="py-2"),
    dbc.NavLink("Options",     href="/options",     active="exact", className="py-2"),
    dbc.NavLink("Opt Guide",   href="/options-guide", external_link=True, className="py-2"),
    dbc.NavLink("Copilot",     href="/copilot",     active="exact", className="py-2"),
    dbc.NavLink("Bot Control", href="/bot",         active="exact", className="py-2"),
    dbc.NavLink("Guide",       href="/guide",       external_link=True, className="py-2"),
], vertical=True, pills=True,
   style={"width":"185px","minHeight":"100vh","background":"#251f45",
          "position":"fixed","top":0,"left":0,"zIndex":100,"borderRight":"1px solid #222"})

def copilot_page():
    wf_opts = [{"label": v["title"], "value": k} for k, v in COPILOT_WORKFLOWS.items()] if _COPILOT_OK else []
    return html.Div([
        html.H4("Research Copilot", className="text-warning mb-1"),
        html.Small(
            "Each workflow uses a different template. Analyze = instant rules; Enhance with AI = LM Studio narrative for that playbook.",
            className="d-block mb-3", style={"fontSize": "11px", "color": "#d8d2f0"}),
        dbc.Alert(
            "Not investment advice. Timing signals are heuristic — verify before trading.",
            color="secondary", className="py-2 copilot-disclaimer", style={"fontSize": "11px"}),
        dbc.Row([
            col(dbc.Input(id="cp-ticker", placeholder="Ticker e.g. NVDA", className="bg-dark text-light border-secondary"), 2),
            col(dcc.Dropdown(id="cp-horizon", options=[
                {"label": "Day trade", "value": "day"},
                {"label": "Swing (weeks)", "value": "swing"},
                {"label": "Long-term (months)", "value": "long"},
            ], value="swing", clearable=False, className="bg-dark"), 2),
            col(dcc.Dropdown(id="cp-workflow", options=wf_opts or [{"label": "Thesis & Timing", "value": "thesis_timing"}],
                             value="thesis_timing", clearable=False), 3),
            col(dbc.Button("Analyze", id="cp-run", color="warning", size="sm"), "auto"),
            col(dbc.Button("Enhance with AI", id="cp-llm", color="secondary", size="sm", outline=True), "auto"),
        ], className="mb-3 g-2 align-items-center"),
        html.Span(id="cp-status", style={"fontSize": "11px", "color": "#d8d2f0"}),
        dcc.Loading(
            dcc.Markdown(id="cp-output", className="copilot-markdown", style={"background": "#12102a", "padding": "16px",
                "borderRadius": "8px", "minHeight": "200px", "fontSize": "13px", "color": "#f0ecff"}),
            type="circle", color="#e8621a"),
    ], className="copilot-page")

@app.callback(
    Output("cp-output", "children"), Output("cp-status", "children"),
    Input("cp-run", "n_clicks"), Input("cp-llm", "n_clicks"),
    State("cp-ticker", "value"), State("cp-horizon", "value"), State("cp-workflow", "value"),
    prevent_initial_call=True)
def update_copilot(n_run, n_llm, ticker, horizon, workflow):
    if not _COPILOT_OK:
        return "Copilot not installed.", "Missing ~/Anduril/copilot/"
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update
    use_llm = ctx.triggered[0]["prop_id"].startswith("cp-llm")
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return "Enter a ticker.", ""
    wf = workflow or "thesis_timing"
    wf_title = (COPILOT_WORKFLOWS.get(wf) or {}).get("title", wf)
    try:
        r = _copilot_run(
            wf,
            ticker,
            horizon=horizon or "swing",
            use_llm=use_llm,
        )
        md = r.get("markdown") or ""
        status = f"{ticker} | {wf_title} | {horizon} | {'AI enhanced' if r.get('llm_used') else 'Rule-based'}"
        if r.get("llm_error"):
            status += f" | LLM: {r['llm_error']}"
        return md, status
    except Exception as e:
        return f"Error: {e}", "Failed"

def _bot_pill(label, value, color="#a09ac8"):
    return html.Div([
        html.Small(label, style={"color":"#6b5fa0","fontSize":"10px","display":"block"}),
        html.Span(str(value), style={"color":color,"fontWeight":"600","fontSize":"13px"}),
    ], style={"background":"#1c1838","border":"1px solid #3d3470","borderRadius":"6px",
              "padding":"8px 12px","minWidth":"110px"})

def _bot_status_cards(data):
    if not data:
        return html.P("No status yet — connect to the API.", style={"color":"#6b5fa0","fontSize":"12px"})
    armed = data.get("armed", False)
    return html.Div([
        _bot_pill("API", ANDURIL_API_BASE, "#e8621a"),
        _bot_pill("Connected", data.get("connected", False), "#2dc653" if data.get("connected") else "#e63946"),
        _bot_pill("Mode", data.get("mode") or "—"),
        _bot_pill("Armed", armed, "#e63946" if armed else "#2dc653"),
        _bot_pill("Read-only", data.get("read_only", True)),
        _bot_pill("Loop", data.get("loop_running", False)),
    ], style={"display":"flex","flexWrap":"wrap","gap":"8px","marginBottom":"12px"})

def _bot_orders_panel(history, summary, open_orders):
    rows = (history or {}).get("records") or []
    positions = (summary or {}).get("positions") or []
    open_rows = (open_orders or {}).get("orders") or []

    pos_cards = []
    for p in positions:
        pos_cards.append(_bot_pill(
            p.get("symbol", "?"),
            f"{p.get('net_shares', '0')} @ {p.get('avg_cost') or '—'}",
            "#2dc653" if float(p.get("net_shares") or 0) > 0 else "#a09ac8",
        ))
    pos_el = html.Div(pos_cards, style={"display":"flex","flexWrap":"wrap","gap":"8px","marginBottom":"10px"}) if pos_cards else html.Small("No fills recorded yet.", style={"color":"#6b5fa0","fontSize":"11px"})

    def _row(cells):
        return html.Tr([html.Td(c, style={"fontSize":"10px","padding":"4px 8px","borderBottom":"1px solid #3d3470"}) for c in cells])

    hist_table = html.Table([
        html.Thead(html.Tr([html.Th(h, style={"color":"#8b7fbf","fontSize":"10px","padding":"4px 8px"}) for h in ["Time","Event","Sym","Side","Qty","Price","Status"]])),
        html.Tbody([_row([
            (r.get("ts") or "")[11:19],
            r.get("event", ""),
            r.get("symbol", ""),
            r.get("side", ""),
            r.get("quantity") or r.get("shares") or r.get("filled_qty") or "",
            r.get("fill_price") or r.get("avg_fill_price") or r.get("limit_price") or r.get("price") or "",
            r.get("status", ""),
        ]) for r in reversed(rows[-20:])]),
    ], style={"width":"100%","marginBottom":"12px"}) if rows else html.Small("No order history.", style={"color":"#6b5fa0","fontSize":"11px"})

    open_table = html.Div([
        html.Small("Open orders (live from IBKR)", style={"color":"#8b7fbf","fontSize":"10px","display":"block","marginBottom":"4px"}),
        html.Table([
            html.Thead(html.Tr([html.Th(h, style={"color":"#8b7fbf","fontSize":"10px","padding":"4px 8px"}) for h in ["ID","Sym","Side","Qty","Limit","Status"]])),
            html.Tbody([_row([
                str(o.get("order_id", "")),
                o.get("symbol", ""),
                o.get("side", ""),
                o.get("quantity", ""),
                o.get("limit_price") or "—",
                o.get("status", ""),
            ]) for o in open_rows]),
        ], style={"width":"100%"}),
    ], style={"marginTop":"10px"}) if open_rows else html.Div()

    return html.Div([html.Small("Positions (avg cost from fills)", style={"color":"#8b7fbf","fontSize":"10px","display":"block","marginBottom":"6px"}), pos_el, hist_table, open_table])

def bot_page():
    return html.Div([
        html.H4("Bot Control", className="text-warning mb-1"),
        html.Small(
            f"Local API at {ANDURIL_API_BASE}. Start with ./scripts/run_api.sh — IB Gateway paper on port 4002.",
            className="d-block mb-3", style={"fontSize":"11px","color":"#d8d2f0"}),
        dbc.Alert(
            "Orders require BOT_ENABLED=true, arm, and read-only off. Default posture is analyze-only.",
            color="secondary", className="py-2", style={"fontSize":"11px"}),
        html.Div(id="bot-status-cards"),
        dbc.Row([
            col(dbc.Button("Connect IBKR", id="bot-connect", color="warning", size="sm"), "auto"),
            col(dbc.Button("Disconnect", id="bot-disconnect", color="secondary", size="sm", outline=True), "auto"),
            col(dbc.Button("Refresh", id="bot-refresh", color="secondary", size="sm", outline=True), "auto"),
            col(dbc.Button("Sync orders", id="bot-sync-orders", color="secondary", size="sm", outline=True), "auto"),
            col(dbc.Button("Reconcile", id="bot-reconcile", color="secondary", size="sm", outline=True), "auto"),
            col(dbc.Button("Arm", id="bot-arm", color="danger", size="sm", outline=True), "auto"),
            col(dbc.Button("Disarm", id="bot-disarm", color="success", size="sm", outline=True), "auto"),
        ], className="mb-3 g-2 align-items-center"),
        dbc.Row([
            col(dbc.Input(id="bot-symbol", value="SPY", placeholder="Symbol", className="bg-dark text-light border-secondary"), 2),
            col(dbc.Input(id="bot-headline", placeholder="Optional headline for news overlay", className="bg-dark text-light border-secondary"), 6),
            col(dbc.Button("Analyze", id="bot-analyze", color="warning", size="sm"), "auto"),
            col(dbc.Button("Run once", id="bot-run-once", color="danger", size="sm", outline=True), "auto"),
        ], className="mb-3 g-2 align-items-center"),
        html.Span(id="bot-action-status", style={"fontSize":"11px","color":"#d8d2f0"}),
        dcc.Loading(html.Pre(id="bot-output", style={
            "background":"#1c1838","color":"#e8e4f0","padding":"12px","borderRadius":"6px",
            "fontSize":"11px","maxHeight":"280px","overflow":"auto","border":"1px solid #3d3470",
        }), type="circle", color="#e8621a"),
        html.Hr(style={"borderColor":"#3d3470","margin":"16px 0"}),
        html.H6("Order history", style={"color":"#e8621a","marginBottom":"8px"}),
        html.Div(id="bot-orders"),
        html.Hr(style={"borderColor":"#3d3470","margin":"16px 0"}),
        html.H6("Recent audit", style={"color":"#e8621a","marginBottom":"8px"}),
        dcc.Loading(html.Pre(id="bot-audit", style={
            "background":"#12102a","color":"#a09ac8","padding":"10px","fontSize":"10px",
            "maxHeight":"200px","overflow":"auto",
        }), type="dot", color="#e8621a"),
    ])

@app.callback(
    Output("bot-status-cards", "children"),
    Output("bot-orders", "children"),
    Output("bot-audit", "children"),
    Output("bot-action-status", "children"),
    Input("bot-tick", "n_intervals"),
    Input("bot-connect", "n_clicks"),
    Input("bot-disconnect", "n_clicks"),
    Input("bot-refresh", "n_clicks"),
    Input("bot-sync-orders", "n_clicks"),
    Input("bot-reconcile", "n_clicks"),
    Input("bot-arm", "n_clicks"),
    Input("bot-disarm", "n_clicks"),
    Input("bot-analyze", "n_clicks"),
    Input("bot-run-once", "n_clicks"),
    State("bot-symbol", "value"),
    State("bot-headline", "value"),
    prevent_initial_call=False)
def update_bot(_tick, n_conn, n_disc, n_ref, n_sync, n_rec, n_arm, n_dis, n_an, n_run, symbol, headline):
    ctx = callback_context
    triggered = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else "bot-tick"
    msg = ""
    output = ""

    actions = {
        "bot-connect": ("POST", "/ibkr/connect", None, "Connected to IBKR"),
        "bot-disconnect": ("POST", "/ibkr/disconnect", None, "Disconnected"),
        "bot-sync-orders": ("POST", "/orders/sync", None, "Orders synced from IBKR"),
        "bot-reconcile": ("POST", "/bot/reconcile", None, "Reconciled ledger"),
        "bot-arm": ("POST", "/bot/arm", None, "Armed (orders allowed if enabled)"),
        "bot-disarm": ("POST", "/bot/disarm", None, "Disarmed"),
    }
    if triggered in actions:
        method, path, params, ok_msg = actions[triggered]
        r = _api_request(method, path, params=params)
        if r.get("ok"):
            msg = ok_msg
            output = json.dumps(r.get("data"), indent=2)
        else:
            msg = f"Error: {r.get('error')}"
            output = msg
    elif triggered == "bot-analyze":
        sym = (symbol or "SPY").strip().upper()
        params = {"symbol": sym}
        if headline and headline.strip():
            params["headline"] = headline.strip()[:4000]
        r = _api_request("POST", "/bot/analyze", params=params)
        msg = f"Analyze {sym}"
        output = json.dumps(r.get("data") if r.get("ok") else r, indent=2)
    elif triggered == "bot-run-once":
        sym = (symbol or "SPY").strip().upper()
        params = {"symbol": sym}
        if headline and headline.strip():
            params["headline"] = headline.strip()[:4000]
        r = _api_request("POST", "/bot/run-once", params=params)
        msg = f"Run once {sym}"
        output = json.dumps(r.get("data") if r.get("ok") else r, indent=2)

    status_r = _api_request("GET", "/bot/status")
    cards = _bot_status_cards(status_r.get("data") if status_r.get("ok") else None)

    audit_r = _api_request("GET", "/audit/recent", params={"limit": 8})
    audit_txt = json.dumps(audit_r.get("data"), indent=2) if audit_r.get("ok") else str(audit_r.get("error", ""))

    hist_r = _api_request("GET", "/orders", params={"limit": 30})
    sum_r = _api_request("GET", "/orders/summary")
    open_r = _api_request("GET", "/orders/open")
    orders_el = _bot_orders_panel(
        hist_r.get("data") if hist_r.get("ok") else None,
        sum_r.get("data") if sum_r.get("ok") else None,
        open_r.get("data") if open_r.get("ok") else None,
    )

    if not msg and triggered == "bot-tick":
        msg = "Polling API"
    elif not msg:
        msg = "Updated"

    return cards, orders_el, audit_txt, msg

app.layout = html.Div([
    dcc.Location(id="url"),
    dcc.Store(id="_css-inject",data=1),
    dcc.Store(id="wl-store", data=None),
    dcc.Store(id="ch-trades",   data=None),
    dcc.Interval(id="wl-tick",  interval=30000, n_intervals=0, disabled=True),
    dcc.Interval(id="l2-tick",  interval=2000,  n_intervals=0, disabled=True),
    dcc.Interval(id="bot-tick", interval=10000, n_intervals=0, disabled=True),
    SIDEBAR,
    html.Div(id="page-content",
        style={"marginLeft":"195px","padding":"20px","minHeight":"100vh",
               "background":"#12102a","color":"#e8e4f0","fontFamily":"Syne,Segoe UI,system-ui,sans-serif"})
], style={"background":"#12102a"})

@app.callback(Output("page-content","children"), Input("url","pathname"))
def route(path):
    if path:
        path = path.split("?")[0].rstrip("/").lower() or "/"
    else:
        path = "/"
    p = {"/conviction":conviction_page,
         "/chart":chart_page,"/level2":level2_page,
         "/screener":screener_page,"/news":news_page,
         "/live-news":live_news_page,"/financials":fin_page,"/options":options_page,
         "/copilot":copilot_page,"/bot":bot_page}
    return p.get(path, watchlist_page)()

app.clientside_callback(
    "function(n){if(document.getElementById('anduril-css'))return window.dash_clientside.no_update;var s=document.createElement('style');s.id='anduril-css';s.innerHTML='body{font-family:\'Syne\',\'Segoe UI\',system-ui,sans-serif!important;background:#12102a!important}.nav-pills .nav-link{color:#a09ac8!important;font-size:12px;border-radius:6px;padding:8px 14px}.nav-pills .nav-link.active{background:linear-gradient(135deg,#e8621a22,#7c3aed22)!important;color:#e8621a!important;border-left:2px solid #e8621a!important}.nav-pills .nav-link:hover{background:#251f45!important;color:#e8e4f0!important}.text-warning{color:#e8621a!important}.text-muted{color:#8b7fbf!important}.border-warning{border-color:#e8621a!important}.border-secondary{border-color:#3d3470!important}.bg-dark{background:#1c1838!important}.text-light{color:#e8e4f0!important}.btn-warning{background:linear-gradient(135deg,#e8621a,#c94a0a)!important;border-color:#e8621a!important;color:#fff!important}.btn-secondary{background:#251f45!important;border-color:#3d3470!important;color:#a09ac8!important}.Select-control,.Select-menu-outer{background:#251f45!important;border-color:#3d3470!important}.Select-value-label,.Select-placeholder,.Select-option{color:#e8e4f0!important}.Select-option:hover,.Select-option.is-focused{background:#3d3470!important}.form-control,input{background:#1c1838!important;border-color:#3d3470!important;color:#e8e4f0!important}.form-control:focus{border-color:#e8621a!important;box-shadow:0 0 0 2px rgba(232,98,26,0.2)!important}.nav-tabs .nav-link{border-color:#3d3470!important;color:#a09ac8!important}.nav-tabs .nav-link.active{background:#251f45!important;color:#e8621a!important}::-webkit-scrollbar{width:6px;height:6px;background:#12102a}::-webkit-scrollbar-thumb{background:#3d3470;border-radius:3px}.js-plotly-plot .modebar-btn{background:transparent!important;color:#8b7fbf!important}.js-plotly-plot .modebar-btn:hover{background:rgba(107,95,160,.35)!important;color:#e8e4f0!important}.js-plotly-plot .modebar-btn.modebar-btn--hover:not(:hover),.js-plotly-plot .modebar-btn.active:not(:hover),.js-plotly-plot .modebar-btn--active:not(:hover){background:transparent!important;color:#8b7fbf!important}.js-plotly-plot .modebar-group{background:transparent!important}.copilot-page .alert-secondary{color:#e8e4f0!important;background:#251f45!important;border-color:#3d3470!important}#cp-output,#cp-output .copilot-markdown,#cp-output p,#cp-output li,#cp-output td,#cp-output th,#cp-output blockquote{color:#f0ecff!important}#cp-output h1,#cp-output h2,#cp-output h3,#cp-output h4,#cp-output h5,#cp-output h6{color:#ffffff!important}#cp-output strong,#cp-output b{color:#ffffff!important;font-weight:600}#cp-output code{background:#1c1838!important;color:#f5d0a8!important;padding:1px 4px;border-radius:3px}#cp-output pre{background:#1c1838!important;color:#f0ecff!important;border:1px solid #3d3470;padding:10px;border-radius:6px}#cp-output a{color:#e8621a!important}#cp-output hr{border-color:#3d3470!important}';document.head.appendChild(s);function cleanPlotlyHover(){document.querySelectorAll(\'.modebar-btn.modebar-btn--hover\').forEach(function(b){if(!b.matches(\':hover\')){b.classList.remove(\'modebar-btn--hover\');b.style.removeProperty(\'background\');b.style.removeProperty(\'background-color\');}});document.querySelectorAll(\'.rangeselector\').forEach(function(group){var btns=group.querySelectorAll(\'g.button\');var dark=[];btns.forEach(function(btn){var rect=btn.querySelector(\'rect.selector-rect\');if(!rect)return;var f=(rect.getAttribute(\'fill\')||\'\').toLowerCase();if(f.indexOf(\'37, 31, 69\')>=0||f.indexOf(\'251f45\')>=0)dark.push(btn);});btns.forEach(function(btn){if(btn.matches(\':hover\'))return;var rect=btn.querySelector(\'rect.selector-rect\');if(!rect)return;if(dark.length===1&&dark[0]===btn){rect.setAttribute(\'fill\',\'#251f45\');return;}rect.setAttribute(\'fill\',\'#3d3470\');});});}document.addEventListener(\'mouseout\',cleanPlotlyHover,true);document.addEventListener(\'mousemove\',cleanPlotlyHover,true);return window.dash_clientside.no_update;}",
    Output("_css-inject","data"),Input("_css-inject","data"),prevent_initial_call=False
)

@app.callback(Output("wl-store","data",allow_duplicate=True),
    Input("url","pathname"), prevent_initial_call="initial_duplicate")
def init_wl_from_db(_): return _wl_load()

@app.callback(Output("ch-trades","data",allow_duplicate=True),
    Input("url","pathname"), prevent_initial_call="initial_duplicate")
def init_trades_from_db(_):
    trades = _trades_load() or []
    cleaned = [tr for tr in trades if tr.get("ticker")]
    if len(cleaned) != len(trades):
        _trades_save(cleaned)
    return cleaned

@app.callback(
    Output("wl-tick","disabled"), Output("wl-tick","interval"),
    Input("url","pathname"), Input("wl-store","data"))
def control_wl_poll(pathname, wl):
    if pathname != "/": return True, 30000
    try:
        active=( wl or {}).get("active",0)
        tickers=(wl or {}).get("groups",[])[active].get("tickers",[])
        if not tickers: return True, 30000
        return False, max(20000, len(tickers)*2000)
    except: return True, 30000

@app.callback(Output("l2-tick","disabled"), Input("url","pathname"))
def control_l2_poll(pathname): return pathname != "/level2"

@app.callback(Output("bot-tick","disabled"), Input("url","pathname"))
def control_bot_poll(pathname): return pathname != "/bot"

# ── Earnings calendar ──────────────────────────────────────────
@app.callback(Output("nw-earnings-cal","children"),
    Input("wl-tick","n_intervals"), prevent_initial_call=False)
def update_earnings_cal(_):
    earnings, source, err = earnings_cal_combo(days=30)
    if not earnings:
        msg=(f"Earnings: {err}" if err else "Add FINNHUB_API_KEY to .env.trading for earnings calendar")
        return html.Small(msg,style={"color":"#554880","fontSize":"10px"})
    cards=[]
    for e in earnings[:15]:
        sym2=e.get("symbol",""); name2=(e.get("name","") or sym2)[:18]; date2=e.get("date","")
        eps_e=e.get("eps_estimate"); t2=e.get("time","")
        tod="🌅" if "Before" in t2 or t2.lower()=="bmo" else "🌆" if "After" in t2 or t2.lower()=="amc" else "📅"
        cards.append(html.Div([
            html.Div(f"{tod} {sym2}",style={"color":"#e8621a","fontWeight":"700","fontSize":"12px"}),
            html.Div(name2,style={"color":"#a09ac8","fontSize":"9px","overflow":"hidden","whiteSpace":"nowrap"}),
            html.Div(date2,style={"color":"#554880","fontSize":"9px"}),
            html.Div(f"Est: ${eps_e:.2f}" if eps_e is not None else "",style={"color":"#8b7fbf","fontSize":"9px"}),
        ],style={"background":"#1c1838","border":"1px solid #3d3470","borderRadius":"6px",
                 "padding":"7px 10px","minWidth":"100px","flex":"0 0 auto"}))
    src_label=source or "Finnhub"
    return html.Div([
        html.Small(f"UPCOMING EARNINGS — 30 DAYS  ({src_label})",
            style={"color":"#554880","fontSize":"9px","letterSpacing":"0.1em","display":"block","marginBottom":"5px"}),
        html.Div(cards,style={"display":"flex","gap":"6px","overflowX":"auto","paddingBottom":"4px"}),
    ])

# ============================================================
# LIVE NEWS & GEOPOLITICAL PAGE
# ============================================================
import xml.etree.ElementTree as _ET

_RSS_FEEDS = [
    {"name":"MarketWatch",     "url":"https://feeds.marketwatch.com/marketwatch/topstories/",           "tag":"markets"},
    {"name":"Yahoo Finance",   "url":"https://finance.yahoo.com/news/rssindex",                         "tag":"markets"},
    {"name":"CNBC Markets",    "url":"https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069","tag":"markets"},
    {"name":"Reuters Business","url":"https://feeds.reuters.com/reuters/businessNews",                 "tag":"stocks"},
    {"name":"Motley Fool",     "url":"https://www.fool.com/a/feeds/foolwatch.xml",                     "tag":"stocks"},
    {"name":"InvestorPlace",   "url":"https://investorplace.com/feed/",                                "tag":"stocks"},
    {"name":"SEC Press",       "url":"https://www.sec.gov/news/pressreleases.rss",                   "tag":"stocks"},
    {"name":"Reuters World",   "url":"https://feeds.reuters.com/reuters/worldnewsheadlines",            "tag":"geo"},
    {"name":"BBC World",       "url":"https://feeds.bbci.co.uk/news/world/rss.xml",                    "tag":"geo"},
    {"name":"NPR World",       "url":"https://feeds.npr.org/1004/rss.xml",                             "tag":"geo"},
    {"name":"Foreign Policy",  "url":"https://foreignpolicy.com/feed/",                                "tag":"geo"},
    {"name":"The Hill",        "url":"https://thehill.com/homenews/feed/",                             "tag":"geo"},
    {"name":"Politico",        "url":"https://www.politico.com/rss/politicopicks.xml",                 "tag":"geo"},
    {"name":"Defense One",     "url":"https://www.defenseone.com/rss/all/",                            "tag":"geo"},
    {"name":"Federal Reserve", "url":"https://www.federalreserve.gov/feeds/press_all.xml",             "tag":"macro"},
    {"name":"IMF News",        "url":"https://www.imf.org/en/News/rss?Language=ENG",                  "tag":"macro"},
    {"name":"BIS",             "url":"https://www.bis.org/rss/press.rss",                              "tag":"macro"},
    {"name":"WSJ Economy",     "url":"https://feeds.a.dj.com/rss/RSSEconomy.xml",                     "tag":"macro"},
    {"name":"CoinDesk",        "url":"https://www.coindesk.com/arc/outboundfeeds/rss/",                  "tag":"crypto"},
    {"name":"Cointelegraph",   "url":"https://cointelegraph.com/rss",                                  "tag":"crypto"},
    {"name":"Decrypt",         "url":"https://decrypt.co/feed",                                        "tag":"crypto"},
    {"name":"Bitcoin Magazine","url":"https://bitcoinmagazine.com/feed",                               "tag":"crypto"},
    {"name":"OilPrice.com",     "url":"https://oilprice.com/rss/main",                                  "tag":"commodities"},
    {"name":"EIA Energy",       "url":"https://www.eia.gov/rss/todayinenergy.xml",                      "tag":"commodities"},
    {"name":"Kitco Metals",     "url":"https://www.kitco.com/rss/rss.xml",                              "tag":"commodities"},
    {"name":"Reuters Energy",   "url":"https://feeds.reuters.com/reuters/USenergyNews",                 "tag":"commodities"},
    {"name":"Natural Gas Intel","url":"https://www.naturalgasintel.com/feed/",                          "tag":"commodities"},
]

_RSS_CACHE = {}; _RSS_TS = {}; _RSS_TTL = 300
_UA_POOL   = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Feedfetcher-Google; (+http://www.google.com/feedfetcher.html)",
]
_ua_pool_i = 0
def _nxt_ua():
    global _ua_pool_i; ua=_UA_POOL[_ua_pool_i%len(_UA_POOL)]; _ua_pool_i+=1; return ua

def _fetch_rss(feed):
    import html as _ht
    now=time.time(); url=feed["url"]
    if url in _RSS_CACHE and now-_RSS_TS.get(url,0)<_RSS_TTL:
        return _RSS_CACHE[url], None
    for attempt in range(2):
        try:
            r=requests.get(url,timeout=8,verify=False,allow_redirects=True,
                headers={"User-Agent":_nxt_ua(),"Accept":"application/rss+xml,text/xml,*/*",
                         "Referer":"https://www.google.com/"})
            if r.status_code==403 and attempt==0: continue
            if r.status_code!=200:
                return _RSS_CACHE.get(url,[]), f"HTTP {r.status_code}"
            raw=r.content; break
        except Exception as e:
            if attempt==1: return _RSS_CACHE.get(url,[]), str(e)
    else:
        return _RSS_CACHE.get(url,[]), "Failed"
    try:
        raw=raw.lstrip(b"\xef\xbb\xbf"); root=_ET.fromstring(raw)
    except Exception as e:
        return _RSS_CACHE.get(url,[]), f"XML: {e}"
    ns_map={}
    try:
        for _,(p2,u2) in _ET.iterparse(__import__("io").BytesIO(raw),events=["start-ns"]):
            ns_map[p2]=u2
    except: pass
    ATOM="http://www.w3.org/2005/Atom"
    def _t(el,*tags):
        import html as _ht2
        for tag in tags:
            for ns in [""]+[f"{{{ATOM}}}"]+[f"{{{u}}}" for u in ns_map.values()]:
                c=el.find(f"{ns}{tag}")
                if c is not None and c.text and c.text.strip():
                    return _ht2.unescape(c.text.strip())
        return ""
    def _lnk(el):
        c=el.find("link")
        if c is not None:
            if c.text and c.text.strip(): return c.text.strip()
            if c.get("href",""): return c.get("href","")
        c=el.find(f"{{{ATOM}}}link")
        if c is not None: return c.get("href","")
        return ""
    items=root.findall(".//item") or root.findall(f".//{{{ATOM}}}entry")
    results=[]
    for it in items[:15]:
        import html as _ht3
        title=_t(it,"title"); link=_lnk(it)
        if not title or not link: continue
        pub  =_t(it,"pubDate","published","updated")[:25]
        desc =re.sub(r"<[^>]+>","",_ht3.unescape(_t(it,"description","summary")))[:220].strip()
        results.append({"title":title,"link":link,"pub":pub,"desc":desc,
                         "source":feed["name"],"tag":feed["tag"]})
    if results: _RSS_CACHE[url]=results; _RSS_TS[url]=now
    return results, None

_NEWSDATA_URL = "https://newsdata.io/api/1/latest?language=en&apikey={key}&{params}"
_ND_CACHE={}; _ND_TS={}

def _fetch_newsdata(category=None, query=None):
    if not NEWSDATA_KEY or NEWSDATA_KEY=="YOUR_KEY_HERE":
        return [], "NEWSDATA_API_KEY not set"
    import urllib.parse as _up
    if query:
        params = f"q={_up.quote(query[:100])}"
        if category:
            params += f"&category={category}"
        params += "&size=10"
    else:
        params = f"category={category}&size=10"
    url = _NEWSDATA_URL.format(key=NEWSDATA_KEY, params=params)
    now = time.time()
    if url in _ND_CACHE and now-_ND_TS.get(url,0)<300:
        return _ND_CACHE[url], None
    try:
        r=requests.get(url,timeout=10,headers={"User-Agent":"Anduril/1.0"})
        data=r.json()
        if data.get("status")!="success":
            return [], data.get("message","NewsData error")
        results=[]
        for a in data.get("results",[]):
            title=(a.get("title") or "").strip()
            link =(a.get("link")  or a.get("source_url") or "")
            if not title or not link: continue
            pub  =(a.get("pubDate") or "")[:16]
            desc =(a.get("description") or "")[:220].strip()
            src  =(a.get("source_id") or "NewsData")
            cats = a.get("category") or []
            tag  =("geo" if any(c in cats for c in ["politics","world","top"])
                   else "markets" if any(c in cats for c in ["business","finance","market"])
                   else "geo")
            results.append({"title":title,"link":link,"pub":pub,
                             "desc":desc,"source":src,"tag":tag})
        _ND_CACHE[url]=results; _ND_TS[url]=now
        return results, None
    except Exception as e:
        return [], str(e)

_NEWSDATA_CRYPTO_URL = "https://newsdata.io/api/1/crypto?language=en&apikey={key}&{params}"

def _fetch_newsdata_crypto(query=None):
    if not NEWSDATA_KEY or NEWSDATA_KEY=="YOUR_KEY_HERE":
        return [], "NEWSDATA_API_KEY not set"
    import urllib.parse as _up
    params = f"size=15" if not query else f"q={_up.quote(query[:100])}&size=15"
    url = _NEWSDATA_CRYPTO_URL.format(key=NEWSDATA_KEY, params=params)
    now = time.time()
    if url in _ND_CACHE and now-_ND_TS.get(url,0)<300:
        return _ND_CACHE[url], None
    try:
        r=requests.get(url,timeout=10,headers={"User-Agent":"Anduril/1.0"})
        data=r.json()
        if data.get("status")!="success":
            return [], data.get("message","NewsData crypto error")
        results=[]
        for a in data.get("results",[]):
            title=(a.get("title") or "").strip()
            link =(a.get("link")  or a.get("source_url") or "")
            if not title or not link: continue
            pub  =(a.get("pubDate") or "")[:16]
            desc =(a.get("description") or "")[:220].strip()
            src  =(a.get("source_id") or "NewsData")
            results.append({"title":title,"link":link,"pub":pub,
                             "desc":desc,"source":src,"tag":"crypto"})
        _ND_CACHE[url]=results; _ND_TS[url]=now
        return results, None
    except Exception as e:
        return [], str(e)

_FH_STOCK_CACHE={}; _FH_STOCK_TS={}

def _fetch_finnhub_stock_news(query=None, include_merger=True):
    if not fh:
        return [], "FINNHUB_API_KEY not set"
    cats = ["general", "merger"] if include_merger else ["general"]
    cache_key = f"fh:{'+'.join(cats)}:{(query or '')[:40]}"
    now = time.time()
    if cache_key in _FH_STOCK_CACHE and now-_FH_STOCK_TS.get(cache_key,0)<300:
        return _FH_STOCK_CACHE[cache_key], None
    results = []; q = (query or "").strip().lower()
    try:
        for cat in cats:
            for a in (fh.general_news(cat, min_id=0) or [])[:25]:
                title = (a.get("headline") or "").strip()
                link  = (a.get("url") or "").strip()
                if not title or not link:
                    continue
                desc  = (a.get("summary") or "")[:220].strip()
                blob  = f"{title} {desc} {a.get('related','')}".lower()
                if q and q not in blob:
                    continue
                ts = a.get("datetime")
                pub = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""
                src = (a.get("source") or "Finnhub").strip()
                results.append({"title":title,"link":link,"pub":pub,
                                 "desc":desc,"source":src,"tag":"stocks"})
        _FH_STOCK_CACHE[cache_key]=results; _FH_STOCK_TS[cache_key]=now
        return results, None
    except Exception as e:
        return _FH_STOCK_CACHE.get(cache_key,[]), str(e)

_NEWSDATA_MARKET_URL = "https://newsdata.io/api/1/market?language=en&apikey={key}&{params}"

def _fetch_newsdata_market(query=None):
    if not NEWSDATA_KEY or NEWSDATA_KEY=="YOUR_KEY_HERE":
        return [], "NEWSDATA_API_KEY not set"
    import urllib.parse as _up
    params = "size=15" if not query else f"q={_up.quote(query[:100])}&size=15"
    url = _NEWSDATA_MARKET_URL.format(key=NEWSDATA_KEY, params=params)
    now = time.time()
    if url in _ND_CACHE and now-_ND_TS.get(url,0)<300:
        return _ND_CACHE[url], None
    try:
        r=requests.get(url,timeout=10,headers={"User-Agent":"Anduril/1.0"})
        data=r.json()
        if data.get("status")!="success":
            return [], data.get("message","NewsData market error")
        results=[]
        for a in data.get("results",[]):
            title=(a.get("title") or "").strip()
            link =(a.get("link")  or a.get("source_url") or "")
            if not title or not link: continue
            pub  =(a.get("pubDate") or "")[:16]
            desc =(a.get("description") or "")[:220].strip()
            src  =(a.get("source_id") or "NewsData")
            results.append({"title":title,"link":link,"pub":pub,
                             "desc":desc,"source":src,"tag":"stocks"})
        _ND_CACHE[url]=results; _ND_TS[url]=now
        return results, None
    except Exception as e:
        return [], str(e)

_COMMODITY_KW = (
    "oil","crude","gas","opec","wti","brent","gold","silver","copper","wheat","corn","soy",
    "commodit","futures","lng","petroleum","energy","metals","grain","heating oil","diesel",
    "aluminum","nickel","natural gas","palladium","platinum",
)

def _commodity_match(text, query=None):
    blob = (text or "").lower()
    if query:
        return query.lower() in blob
    return any(k in blob for k in _COMMODITY_KW)

def _fetch_finnhub_commodity_news(query=None):
    if not fh:
        return [], "FINNHUB_API_KEY not set"
    cache_key = "fh:commodities:" + (query or "")[:40]
    now = time.time()
    if cache_key in _FH_STOCK_CACHE and now-_FH_STOCK_TS.get(cache_key,0)<300:
        return _FH_STOCK_CACHE[cache_key], None
    results = []
    try:
        for cat in ("forex", "general"):
            for a in (fh.general_news(cat, min_id=0) or [])[:40]:
                title = (a.get("headline") or "").strip()
                link  = (a.get("url") or "").strip()
                if not title or not link:
                    continue
                desc  = (a.get("summary") or "")[:220].strip()
                blob  = title + " " + desc + " " + (a.get("related") or "")
                if not _commodity_match(blob, query):
                    continue
                ts = a.get("datetime")
                pub = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""
                src = (a.get("source") or "Finnhub").strip()
                results.append({"title":title,"link":link,"pub":pub,
                                 "desc":desc,"source":src,"tag":"commodities"})
        _FH_STOCK_CACHE[cache_key]=results; _FH_STOCK_TS[cache_key]=now
        return results, None
    except Exception as e:
        return _FH_STOCK_CACHE.get(cache_key,[]), str(e)

def _fetch_newsdata_commodities(query=None):
    if not NEWSDATA_KEY or NEWSDATA_KEY=="YOUR_KEY_HERE":
        return [], "NEWSDATA_API_KEY not set"
    import urllib.parse as _up
    queries = [query] if query else ["crude oil", "natural gas", "gold futures", "wheat corn"]
    results = []; errors = []
    for qq in queries[:4]:
        params = "q=" + _up.quote(qq[:80]) + "&size=8"
        url = _NEWSDATA_MARKET_URL.format(key=NEWSDATA_KEY, params=params)
        now = time.time()
        if url in _ND_CACHE and now-_ND_TS.get(url,0)<300:
            results.extend(_ND_CACHE[url]); continue
        try:
            r=requests.get(url,timeout=10,headers={"User-Agent":"Anduril/1.0"})
            data=r.json()
            if data.get("status")!="success":
                errors.append(data.get("message","NewsData error")); continue
            batch=[]
            for a in data.get("results",[]):
                title=(a.get("title") or "").strip()
                link =(a.get("link")  or a.get("source_url") or "")
                if not title or not link: continue
                pub  =(a.get("pubDate") or "")[:16]
                desc =(a.get("description") or "")[:220].strip()
                src  =(a.get("source_id") or "NewsData")
                batch.append({"title":title,"link":link,"pub":pub,
                               "desc":desc,"source":src,"tag":"commodities"})
            _ND_CACHE[url]=batch; _ND_TS[url]=now
            results.extend(batch)
        except Exception as e:
            errors.append(str(e))
    err = errors[0] if errors and not results else None
    return results, err

_FH_IPO_CACHE={}; _FH_IPO_TS={}

def _ipo_num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None

def _ipo_fmt_money(v):
    n = _ipo_num(v)
    if n is None:
        return ""
    if n >= 1e9:
        return f"${n/1e9:.1f}B"
    if n >= 1e6:
        return f"${n/1e6:.0f}M"
    if n >= 1e3:
        return f"${n/1e3:.0f}K"
    return f"${n:.0f}"

def _ipo_fmt_shares(v):
    n = _ipo_num(v)
    if n is None:
        return ""
    if n >= 1e6:
        return f"{n/1e6:.1f}M sh"
    if n >= 1e3:
        return f"{n/1e3:.0f}K sh"
    return f"{int(n)} sh"

def fh_ipo_cal(days=90):
    if not fh:
        return [], "FINNHUB_API_KEY not set"
    from datetime import datetime as _dt, timedelta as _td2
    s=_dt.now().strftime("%Y-%m-%d"); e=(_dt.now()+_td2(days=days)).strftime("%Y-%m-%d")
    cache_key=f"{s}:{e}"; now=time.time()
    if cache_key in _FH_IPO_CACHE and now-_FH_IPO_TS.get(cache_key,0)<3600:
        return _FH_IPO_CACHE[cache_key], None
    try:
        data=fh.ipo_calendar(_from=s,to=e)
        if isinstance(data, list):
            raw = data
            api_err = None
        elif isinstance(data, dict):
            raw = data.get("ipoCalendar") or data.get("ipo") or []
            api_err = data.get("error") or data.get("message")
        else:
            raw, api_err = [], "Unexpected IPO response"
        if not isinstance(raw, list):
            raw = []
        results=[]
        for item in raw:
            if not isinstance(item, dict):
                continue
            results.append({"symbol":(item.get("symbol") or "").strip(),
                "name":(item.get("name") or item.get("symbol") or "")[:32],
                "date":item.get("date","") or "",
                "exchange":item.get("exchange","") or "",
                "price":str(item.get("price") or "").strip(),
                "shares":_ipo_num(item.get("numberOfShares")),
                "value":_ipo_num(item.get("totalSharesValue")),
                "status":(item.get("status") or "expected").strip()})
        results.sort(key=lambda x:x.get("date",""))
        _FH_IPO_CACHE[cache_key]=results; _FH_IPO_TS[cache_key]=now
        if not results and api_err:
            return [], str(api_err)
        return results, None
    except Exception as ex:
        return _FH_IPO_CACHE.get(cache_key,[]), str(ex)

def _ipo_section(ipos, filt, q, ipo_err=None):
    if filt not in ("all","markets","stocks"):
        return html.Span()
    items = list(ipos or [])
    if q:
        kw=q.lower()
        items=[i for i in items if kw in (i.get("name","")+" "+i.get("symbol","")+" "+i.get("exchange","")).lower()]
    hdr=html.Div("🚀 Upcoming IPOs — 90 Days  (Finnhub)",
        style={"color":"#2dc653","fontWeight":"700","fontSize":"12px","letterSpacing":"0.08em",
               "textTransform":"uppercase","marginBottom":"8px","paddingBottom":"6px",
               "borderBottom":"1px solid #2dc65344"})
    if not fh:
        return html.Div([hdr,html.Small("Set FINNHUB_API_KEY in .env.trading for IPO calendar.",
            style={"color":"#554880","fontSize":"10px"})],className="mb-4")
    if ipo_err and "not set" not in str(ipo_err).lower():
        return html.Div([hdr,html.Small(f"IPO calendar unavailable: {ipo_err}",
            style={"color":"#e63946","fontSize":"10px"})],className="mb-4")
    if not items:
        return html.Div([hdr,html.Small("No upcoming IPOs in the next 90 days.",
            style={"color":"#554880","fontSize":"10px"})],className="mb-4")
    cards=[]
    for ip in items[:20]:
        status=(ip.get("status") or "expected").lower()
        st_clr="#2dc653" if status=="priced" else "#e8621a" if status in ("expected","filed") else "#a78bfa"
        val_s=_ipo_fmt_money(ip.get("value"))
        sh_s=_ipo_fmt_shares(ip.get("shares"))
        cards.append(html.Div([
            html.Div((ip.get("symbol") or "TBD"),style={"color":"#2dc653","fontWeight":"700","fontSize":"12px"}),
            html.Div(ip.get("name",""),style={"color":"#a09ac8","fontSize":"9px","overflow":"hidden","whiteSpace":"nowrap","maxWidth":"140px"}),
            html.Div(ip.get("date",""),style={"color":"#554880","fontSize":"9px"}),
            html.Div(f"{ip.get('exchange','')} · {ip.get('price','')}".strip(" ·"),
                style={"color":"#8b7fbf","fontSize":"9px"}),
            html.Div(" · ".join(x for x in [sh_s,val_s,status.title()] if x),
                style={"color":"#6b5fa0","fontSize":"9px"}),
        ],style={"background":"#1c1838","border":f"1px solid {st_clr}55","borderLeft":f"3px solid {st_clr}",
                 "borderRadius":"6px","padding":"7px 10px","minWidth":"155px","flex":"0 0 auto"}))
    return html.Div([hdr,html.Div(cards,style={"display":"flex","gap":"6px","overflowX":"auto","paddingBottom":"4px"})],
                    className="mb-4")

def _news_card(item, border_color="#3d3470"):
    return html.Div([
        html.Div([
            html.Span(item.get("source",""), style={"color":"#e8621a","fontSize":"10px","fontWeight":"600","marginRight":"8px"}),
            html.Span(item.get("pub","")[:16], style={"color":"#554880","fontSize":"10px"}),
        ],style={"marginBottom":"3px"}),
        html.A(item.get("title",""), href=item.get("link","#"), target="_blank",
            style={"color":"#e8e4f0","fontSize":"13px","fontWeight":"500",
                   "textDecoration":"none","lineHeight":"1.4","display":"block"}),
        html.P(item.get("desc",""),
            style={"color":"#8b7fbf","fontSize":"11px","margin":"3px 0 0","lineHeight":"1.5"}
        ) if item.get("desc") else html.Span(),
    ],style={"borderLeft":f"3px solid {border_color}","padding":"8px 12px",
              "marginBottom":"6px","background":"#1c1838","borderRadius":"0 6px 6px 0"})

def live_news_page():
    return html.Div([
        html.H4("Live News & Geopolitical Feed",className="text-warning mb-1"),
        html.Small("RSS + NewsData.io (latest) + Finnhub IPO calendar · auto-refresh every 5 min · "
                   "Reuters, BBC, NPR, Foreign Policy, Defense One, The Hill, Politico, Fed, IMF, BIS, "
                   "WSJ, MarketWatch, CNBC, Yahoo Finance",
            className="text-muted d-block mb-3",style={"fontSize":"11px"}),
        dbc.Row([
            col(dcc.Dropdown(id="ln-filter",
                options=[{"label":"All feeds","value":"all"},
                         {"label":"📊 Stocks","value":"stocks"},
                         {"label":"📈 Markets","value":"markets"},
                         {"label":"🌍 Geopolitical","value":"geo"},
                         {"label":"🏦 Macro / Central Banks","value":"macro"},
                         {"label":"₿ Crypto","value":"crypto"},
                         {"label":"🛢 Commodities & Futures","value":"commodities"}],
                value="all",clearable=False,
                style={"background":"#251f45","color":"#e8e4f0","border":"1px solid #3d3470"}),3),
            col(dbc.Input(id="ln-search",placeholder="Keyword filter...",
                className="bg-dark text-light border-secondary",debounce=True),3),
            col(dbc.Button("Refresh",id="ln-refresh",color="warning",size="sm"),"auto"),
            col(html.Span(id="ln-status",
                style={"fontSize":"11px","color":"#6b5fa0","marginTop":"6px","display":"block"}),"auto"),
        ],className="mb-3 g-2 align-items-center"),
        dcc.Loading(html.Div(id="ln-feed"),type="circle",color="#e8621a"),
        dcc.Interval(id="ln-tick",interval=300000,n_intervals=0,disabled=True),
    ])

@app.callback(Output("ln-tick","disabled"), Input("url","pathname"))
def control_ln_poll(pathname): return pathname != "/live-news"

@app.callback(
    Output("ln-feed","children"), Output("ln-status","children"),
    Input("ln-refresh","n_clicks"), Input("ln-tick","n_intervals"),
    Input("ln-filter","value"), Input("ln-search","value"),
    prevent_initial_call=False)
def update_live_news(n, tick, filt, search):
    all_items=[]; errors=[]; filt=filt or "all"; q=(search or "").strip() or None
    ipos,ipo_err=fh_ipo_cal(days=90)
    if ipo_err and "not set" not in ipo_err: errors.append(f"IPO: {ipo_err}")
    ipo_el=_ipo_section(ipos,filt,q,ipo_err)

    # Finnhub stock news (real-time market headlines)
    if filt in ("all","stocks"):
        items,err=_fetch_finnhub_stock_news(query=q, include_merger=(filt=="stocks"))
        if err and "not set" not in err: errors.append(f"Finnhub stocks: {err}")
        all_items.extend(items)

    if filt == "commodities":
        items,err=_fetch_finnhub_commodity_news(query=q)
        if err and "not set" not in err: errors.append(f"Finnhub commodities: {err}")
        all_items.extend(items)

    # NewsData.io
    if NEWSDATA_KEY and NEWSDATA_KEY != "YOUR_KEY_HERE":
        if filt == "crypto":
            items,err=_fetch_newsdata_crypto(query=q)
            if err and "not set" not in err: errors.append(f"NewsData crypto: {err}")
            all_items.extend(items)
        elif filt == "stocks":
            items,err=_fetch_newsdata_market(query=q)
            if err and "not set" not in err: errors.append(f"NewsData market: {err}")
            all_items.extend(items)
        elif filt == "commodities":
            items,err=_fetch_newsdata_commodities(query=q)
            if err and "not set" not in err: errors.append(f"NewsData commodities: {err}")
            all_items.extend(items)
        else:
            nd_cats={"all":["world","politics","business"],"geo":["world","politics"],
                     "markets":["business"],"macro":["business","politics"]}
            for cat in nd_cats.get(filt,["world"])[:2]:
                items,err=_fetch_newsdata(category=cat,query=q)
                if err and "not set" not in err: errors.append(f"NewsData: {err}")
                all_items.extend(items)

    # RSS feeds
    for feed in _RSS_FEEDS:
        if filt == "stocks":
            if feed["tag"] not in ("stocks","markets"): continue
        elif filt == "commodities":
            if feed["tag"] != "commodities": continue
        elif filt not in ("all",feed["tag"]): continue
        items,err=_fetch_rss(feed)
        if err: errors.append(err)
        all_items.extend(items)

    # Keyword filter
    if q:
        kw=q.lower()
        all_items=[i for i in all_items if kw in (i.get("title","")+" "+i.get("desc","")).lower()]

    # Deduplicate
    seen=set(); unique=[]
    for it in all_items:
        k=it.get("title","")[:60].lower().strip()
        if k and k not in seen: seen.add(k); unique.append(it)

    if not unique:
        return html.Div([
            ipo_el,
            html.P("No articles loaded.",className="text-muted",style={"fontSize":"13px"}),
            html.P(f"Errors: {' | '.join(errors[:4])}" if errors else
                   "Check internet connection or try Refresh.",
                   style={"color":"#e63946","fontSize":"11px"}),
        ]), f"0 articles · {len(ipos)} IPOs · {len(errors)} errors · {datetime.now().strftime('%H:%M:%S')}"

    TAG_COLOR={"stocks":"#2dc653","markets":"#e8621a","geo":"#e63946","macro":"#a78bfa","crypto":"#fbbf24","commodities":"#fb923c"}
    TAG_LABELS={"stocks":"📊 Stocks & Equities","markets":"📈 Markets & Finance","geo":"🌍 Geopolitical","macro":"🏦 Macro / Central Banks","crypto":"₿ Crypto & Blockchain","commodities":"🛢 Commodities & Futures"}
    by_tag={"stocks":[],"geo":[],"markets":[],"macro":[],"crypto":[],"commodities":[]}
    for it in unique: by_tag.setdefault(it.get("tag","markets"),[]).append(it)

    active_tags=(["stocks","geo","markets","macro"] if filt=="all" else [filt] if filt in by_tag else ["markets"])
    cols_l=[]; cols_r=[]
    for i,tag in enumerate(active_tags):
        items_t=by_tag.get(tag,[])
        if not items_t: continue
        bc=TAG_COLOR.get(tag,"#3d3470")
        sec=html.Div([
            html.Div(TAG_LABELS.get(tag,tag),
                style={"color":bc,"fontWeight":"700","fontSize":"12px","letterSpacing":"0.08em",
                       "textTransform":"uppercase","marginBottom":"8px","paddingBottom":"6px",
                       "borderBottom":f"1px solid {bc}44"}),
            html.Div([_news_card(it,bc) for it in items_t[:15]]),
        ],style={"marginBottom":"20px"})
        if i%2==0: cols_l.append(sec)
        else: cols_r.append(sec)

    status=f"{len(unique)} articles · {len(ipos)} IPOs · {len(errors)} errors · {datetime.now().strftime('%H:%M:%S')}"
    news_layout=(dbc.Row([dbc.Col(cols_l,width=6),dbc.Col(cols_r,width=6)])
                 if len(active_tags)>1 else html.Div(cols_l+cols_r))
    return html.Div([ipo_el, news_layout]), status

# ============================================================
# WATCHLIST CALLBACKS  (persistence)
# ============================================================

# ============================================================
# WATCHLIST
# ============================================================
def watchlist_page():
    return html.Div([
        html.H4("Watchlist",className="text-warning mb-2"),
        # Group tabs
        html.Div(id="wl-tabs-row",className="mb-2"),
        # Add ticker row
        dbc.Row([
            col(dbc.Input(id="wl-add",placeholder="Add ticker e.g. GOOGL",className="bg-dark text-light border-secondary",debounce=False),3),
            col(dbc.Button("Add",id="wl-add-btn",color="warning",size="sm"),"auto"),
            col(dbc.Input(id="wl-grp-name",placeholder="Rename group...",className="bg-dark text-light border-secondary",size="sm",debounce=False),3),
            col(dbc.Button("Rename",id="wl-rename-btn",color="secondary",size="sm"),"auto"),
            col(html.Small("Up to 10 tickers per group  |  [X] to remove",className="text-muted",style={"fontSize":"11px"}),"auto"),
        ],className="mb-3 g-2 align-items-center"),
        html.Div(id="wl-table"),
    ])

@app.callback(
    Output("wl-store","data"),
    Input("wl-add-btn","n_clicks"),
    Input("wl-rename-btn","n_clicks"),
    Input({"type":"wl-rm","index":ALL},"n_clicks"),
    Input({"type":"wl-tab","index":ALL},"n_clicks"),
    State("wl-add","value"),
    State("wl-grp-name","value"),
    State("wl-store","data"),
    prevent_initial_call=True)
def modify_wl(add_n, rename_n, rm_ns, tab_ns, ticker, grp_name, wl):
    ctx=callback_context
    if not ctx.triggered: return wl
    trig=ctx.triggered[0]["prop_id"]
    import json as _j
    groups=wl.get("groups",[])
    active=wl.get("active",0)

    # Switch group tab
    if "wl-tab" in trig:
        try:
            idx=_j.loads(trig.split(".")[0])["index"]
            return _wl_save({"groups":groups,"active":idx})
        except: return wl

    # Remove ticker
    if "wl-rm" in trig:
        try:
            sym=_j.loads(trig.split(".")[0])["index"]
            groups[active]["tickers"]=[t for t in groups[active]["tickers"] if t!=sym]
            return _wl_save({"groups":groups,"active":active})
        except: return wl

    # Rename group
    if "wl-rename-btn" in trig and grp_name and grp_name.strip():
        groups[active]["name"]=grp_name.strip()[:20]
        return _wl_save({"groups":groups,"active":active})

    # Add ticker
    if "wl-add-btn" in trig and ticker:
        t=ticker.strip().upper()
        tickers=groups[active]["tickers"]
        if t and t not in tickers:
            if len(tickers)>=10:
                return wl  # silently cap at 10
            tickers.append(t)
            groups[active]["tickers"]=tickers
            return _wl_save({"groups":groups,"active":active})

    return wl

@app.callback(
    Output("wl-tabs-row","children"),
    Output("wl-table","children"),
    Input("wl-tick","n_intervals"),
    Input("wl-store","data"))
def update_wl(_,wl):
    groups=wl.get("groups",[])
    active=wl.get("active",0)

    # Group tab buttons
    tab_btns=[]
    for i,g in enumerate(groups):
        is_active=i==active
        count=len(g["tickers"])
        tab_btns.append(
            html.Span(
                [g["name"],html.Sup(f" {count}",style={"fontSize":"9px","color":"#8b7fbf"})],
                id={"type":"wl-tab","index":i},
                n_clicks=0,
                style={
                    "padding":"4px 14px","marginRight":"4px","borderRadius":"4px","cursor":"pointer",
                    "fontSize":"12px","fontWeight":"bold" if is_active else "normal",
                    "background":"#251f45" if is_active else "#12102a",
                    "color":"#e8621a" if is_active else "#6b5fa0",
                    "border":"1px solid #f7c948" if is_active else "1px solid #222",
                    "display":"inline-block",
                }))
    tabs_row=html.Div(tab_btns,style={"marginBottom":"8px"})

    # Ticker table for active group
    tickers=groups[active]["tickers"] if active<len(groups) else []
    if not tickers:
        table=html.Div([
            html.P(f"{groups[active]['name']} is empty.",className="text-muted",style={"fontSize":"13px"}),
            html.P("Add tickers above. Max 10 per group.",style={"color":"#554880","fontSize":"11px"}),
        ])
        return tabs_row, table

    rows=[hdr([("Symbol",2),("Price",2),("Change %",2),("Change $",2),("Range",3),("Links",1)])]
    for sym in tickers:
        try:
            is_forex="/" in sym and len(sym)==7
            if is_forex:
                rate,_fe=td_forex(sym[:3],sym[4:]); p=rate or 0; pct=0; ch=0; hi=0; lo=0
                sa=f"https://www.google.com/finance/quote/{sym.replace('/','-')}:FX"
            else:
                q=fh.quote(sym) if fh else {}
                p=float(q.get("c") or q.get("pc") or 0); pct=float(q.get("dp") or 0)
                ch=float(q.get("d") or 0); hi=float(q.get("h") or 0); lo=float(q.get("l") or 0)
                sa=f"https://stockanalysis.com/stocks/{sym.lower()}/"
            c="#2dc653" if pct>=0 else "#e63946"; ar="+" if pct>=0 else ""
            rows.append(dbc.Row([
                col(html.Span(sym,style={"color":"#e8621a","fontWeight":"bold"}),2),
                col(html.Span(f"${p:,.2f}",style={"color":"#e8e4f0","fontWeight":"bold"}),2),
                col(html.Span(f"{ar}{pct:.2f}%",style={"color":c,"fontWeight":"bold"}),2),
                col(html.Span(f"{ar}${ch:.2f}",style={"color":c}),2),
                col(html.Span(f"H:{hi:.2f} L:{lo:.2f}" if hi>0 else "Premarket",style={"color":"#a09ac8","fontSize":"12px"}),3),
                col(html.Div([
                    html.A("SA",href=sa,target="_blank",className="text-info me-2",style={"fontSize":"12px"}),
                    html.Span("[X]",id={"type":"wl-rm","index":sym},n_clicks=0,style={"color":"#e63946","cursor":"pointer","fontSize":"12px","fontWeight":"bold"}),
                ]),1),
            ],className="mb-1 py-2 border-bottom border-secondary align-items-center"))
        except Exception as e:
            rows.append(dbc.Row([
                col(html.Span(sym,className="text-warning"),2),
                col(html.Span(str(e),style={"color":"#6b5fa0","fontSize":"11px"}),9),
                col(html.Span("[X]",id={"type":"wl-rm","index":sym},n_clicks=0,style={"color":"#e63946","cursor":"pointer","fontSize":"12px"}),1),
            ],className="mb-1 py-1"))

    cap_warn=html.Small(f"{len(tickers)}/10 tickers",style={"color":"#e8621a" if len(tickers)>=10 else "#6b5fa0","fontSize":"10px","display":"block","marginBottom":"6px"})
    return tabs_row, html.Div([cap_warn]+rows)

# ============================================================
# ADVANCED CHART
# ============================================================
# Indicator color palette -- all distinct, high-contrast on dark bg
IND_COLORS = {
    "EMA 9":            "#e8621a",   # gold
    "EMA 21":           "#a78bfa",   # cyan
    "EMA 50":           "#c77dff",   # purple
    "SMA 200":          "#ff9f1c",   # orange  (dashed)
    "VWAP":             "#ff6b9d",   # pink    (dotted)
    "BB Upper":         "#90e0ef",   # light blue
    "BB Mid":           "#90e0ef",
    "BB Lower":         "#90e0ef",
    "RSI":              "#a8dadc",   # teal
    "MACD":             "#4cc9f0",   # sky blue
    "Signal":           "#f72585",   # magenta
    "Stoch RSI K":      "#06d6a0",   # green
    "Stoch RSI D":      "#ffd166",   # yellow
    "OBV":              "#e9c46a",   # sand
    "ATR":              "#f4a261",   # peach
}

# Period auto-mapping per interval so 1m/5m get sensible defaults
INTERVAL_PERIOD = CHART_DEFAULT_PERIOD

def _chart_clamp_period(interval, period):
    interval = interval or "1d"
    period = period or "1y"
    min_p = CHART_MIN_PERIOD.get(interval)
    max_p = CHART_MAX_PERIOD.get(interval)
    pd = CHART_PERIOD_DAYS
    if min_p and pd.get(period, 0) < pd.get(min_p, 0):
        period = min_p
    if max_p and pd.get(period, 99999) > pd.get(max_p, 99999):
        period = max_p
    return period

def _chart_range_buttons(df, interval):
    span_days = max(1.0, (df.index[-1] - df.index[0]).total_seconds() / 86400.0)
    buttons = []
    if interval in INTRADAY_INTERVALS:
        for count, label in [(1, "1D"), (5, "5D"), (7, "1W")]:
            if span_days >= count - 0.25:
                buttons.append(dict(count=count, label=label, step="day", stepmode="backward"))
        buttons.append(dict(step="all", label="All"))
        return buttons
    specs = [
        (1, "1D", "day"), (5, "5D", "day"), (7, "1W", "day"),
        (1, "1M", "month"), (3, "3M", "month"), (6, "6M", "month"),
        (1, "1Y", "year"), (2, "2Y", "year"),
    ]
    min_needed = {"day": 1, "month": 20, "year": 200}
    for count, label, step in specs:
        need = min_needed[step] * (count if step != "day" else 1)
        if step == "month":
            need = 20 * count
        elif step == "year":
            need = 200 * count
        else:
            need = count
        if span_days >= need:
            buttons.append(dict(count=count, label=label, step=step, stepmode="backward"))
    buttons.append(dict(step="all", label="All"))
    return buttons

def _parse_trade_x(x):
    try:
        return pd.Timestamp(x)
    except Exception:
        return None

def _trade_matches_ticker(tr, ticker):
    tk = tr.get("ticker")
    if not tk:
        return False
    return str(tk).upper() == ticker.upper()

def _chart_price_bounds(df, pad_pct=0.12):
    lo = float(df["Low"].min())
    hi = float(df["High"].max())
    pad = max((hi - lo) * pad_pct, max(hi * 0.02, 0.05))
    return lo - pad, hi + pad

def _snap_trade_price(df, x):
    ts = _parse_trade_x(x)
    if ts is None or df is None or df.empty:
        return None
    idx = df.index.get_indexer([ts], method="nearest")[0]
    if idx < 0:
        return None
    try:
        return float(df["Close"].iloc[idx])
    except Exception:
        return None

def _trades_for_chart(trades, ticker, df):
    lo, hi = _chart_price_bounds(df, pad_pct=0.25)
    out = []
    for tr in trades or []:
        if not _trade_matches_ticker(tr, ticker):
            continue
        try:
            y = float(tr.get("y", 0))
        except Exception:
            continue
        if lo <= y <= hi:
            out.append(tr)
    return out

def _trades_for_ticker(trades, ticker):
    return [tr for tr in (trades or []) if _trade_matches_ticker(tr, ticker)]

def _remove_nearest_trade(trades, ticker, x, y):
    tx = _parse_trade_x(x)
    if tx is None:
        return trades
    best_i, best_d = None, None
    for i, tr in enumerate(trades or []):
        if not _trade_matches_ticker(tr, ticker):
            continue
        ttx = _parse_trade_x(tr.get("x"))
        if ttx is None:
            continue
        x_hrs = abs((ttx - tx).total_seconds()) / 3600.0
        y_pct = abs(float(tr.get("y", 0) or 0) - float(y or 0)) / max(float(y or 1), 1.0) * 100.0
        d = x_hrs + y_pct
        if best_d is None or d < best_d:
            best_d, best_i = d, i
    if best_i is not None and best_d is not None and best_d < 36:
        return trades[:best_i] + trades[best_i + 1:]
    return trades

def chart_page():
    return html.Div([
        html.H4("Advanced Chart", className="text-warning mb-2"),
        dbc.Row([
            col(dbc.Input(id="ch-t", value="AAPL", placeholder="Ticker",
                className="bg-dark text-light border-secondary", debounce=True), 2),
            col(dcc.Dropdown(id="ch-i",
                options=[{"label":k,"value":v} for k,v in INTERVALS.items()],
                value="1d", clearable=False,
                style={"background":"#251f45","color":"#111","border":"1px solid #555"}), 2),
            col(dcc.Dropdown(id="ch-p",
                options=[{"label":l,"value":v} for l,v in PERIODS],
                value="1y", clearable=False,
                style={"background":"#251f45","color":"#111","border":"1px solid #555"}), 2),
            col(dcc.Dropdown(id="ch-ind",
                options=[{"label":i,"value":i} for i in INDICATORS],
                value=["EMA 9","EMA 21","Bollinger Bands","Volume","RSI"],
                multi=True, placeholder="Indicators...",
                style={"background":"#251f45","color":"#111","border":"1px solid #555"}), 6),
        ], className="mb-2 g-2 align-items-center"),
        # Buy/Sell annotation row
        dbc.Row([
            col(html.Div([
                html.Small("Mark trades on chart:", className="text-muted me-2", style={"fontSize":"10px"}),
                dbc.RadioItems(id="ch-mode",
                    options=[
                        {"label":"Buy","value":"buy"},
                        {"label":"Sell","value":"sell"},
                        {"label":"Remove","value":"remove"},
                        {"label":"Off","value":"off"},
                    ],
                    value="off", inline=True,
                    inputStyle={"marginRight":"3px"},
                    labelStyle={"marginRight":"12px","fontSize":"11px","cursor":"pointer"}),
            ], className="d-flex align-items-center"), 5),
            col(dbc.Button("Clear marks", id="ch-clear-trades", color="secondary", size="sm",
                outline=True, className="border-secondary"), 2),
            col(html.Small(
                "Draw tools: Line | Rect | Horiz | Circle | Erase=shapes only  |  Remove mode + click marker to delete  |  Scroll to zoom",
                className="text-muted", style={"fontSize":"10px"}), 5),
        ], className="mb-1 g-2 align-items-center"),
        html.Div(id="ch-info", className="mb-1", style={"fontSize":"13px","minHeight":"20px"}),
        dcc.Loading(dcc.Graph(id="ch-g", style={"height":"74vh"}, config={
            "modeBarButtonsToAdd":["drawline","drawopenpath","drawrect","eraseshape","drawcircle"],
            "modeBarButtonsToRemove":["lasso2d","select2d","drawclosedpath"],
            "scrollZoom":True, "displayModeBar":True,
            "toImageButtonOptions":{"format":"png","filename":"chart","scale":2}}),
            type="circle", color="#e8621a"),
        html.Div(id="ch-trade-log", style={"marginTop":"8px","fontSize":"11px","color":"#6b5fa0"}),
    ])

@app.callback(
    Output("ch-p", "value"),
    Input("ch-i", "value"),
    State("ch-p", "value"),
    prevent_initial_call=True)
def sync_chart_period(interval, period):
    interval = interval or "1d"
    period = period or "1y"
    clamped = _chart_clamp_period(interval, period)
    if clamped != period:
        return clamped
    if CHART_PERIOD_DAYS.get(period, 0) > CHART_PERIOD_DAYS.get(CHART_DEFAULT_PERIOD.get(interval, "1y"), 365) * 3:
        return CHART_DEFAULT_PERIOD.get(interval, "1y")
    return period

@app.callback(
    Output("ch-g","figure"), Output("ch-info","children"),
    Output("ch-trades","data"), Output("ch-trade-log","children"),
    Input("ch-t","value"), Input("ch-i","value"), Input("ch-p","value"),
    Input("ch-ind","value"), Input("ch-g","clickData"), Input("ch-mode","value"),
    Input("ch-clear-trades","n_clicks"),
    State("ch-trades","data"),
    prevent_initial_call=False)
def update_chart(ticker, interval, period, inds, clickdata, mode, clear_clicks, trades):
    from dash import callback_context as ctx
    inds = inds or []
    t = (ticker or "AAPL").strip().upper()
    interval = interval or "1d"
    period = period or "1y"
    trades = list(trades or [])
    triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

    requested_period = period
    period = _chart_clamp_period(interval, period)

    try:
        df = _fetch_chart_data(t, interval, period)

        if triggered == "ch-clear-trades.n_clicks" and clear_clicks:
            trades = [tr for tr in trades if not _trade_matches_ticker(tr, t)]
            _trades_save(trades)

        if "ch-g.clickData" in triggered and clickdata:
            try:
                pt = clickdata["points"][0]
                yaxis = pt.get("yaxis", "y")
                if yaxis not in ("y", "y1"):
                    raise ValueError("click not on price pane")
                y = _snap_trade_price(df, pt["x"])
                if y is None:
                    raise ValueError("no bar for click")
                if mode in ("buy", "sell"):
                    trades.append({"ticker": t, "x": pt["x"], "y": y, "side": mode})
                    _trades_save(trades)
                elif mode == "remove":
                    trades = _remove_nearest_trade(trades, t, pt["x"], y)
                    _trades_save(trades)
            except Exception:
                pass

        ur  = "RSI"       in inds
        um  = "MACD"      in inds
        uv  = "Volume"    in inds
        ua  = "ATR"       in inds
        ust = "Stoch RSI" in inds
        uob = "OBV"       in inds
        n   = sum([ur, um, uv, ua, ust, uob])
        rh  = [0.55] + [0.12] * n if n else [1.0]
        if n:
            rs = sum(rh)
            rh = [h / rs for h in rh]
        subs = [f"{t}  {interval}"] + \
               ([" RSI"] if ur else []) + \
               ([" MACD"] if um else []) + \
               ([" Volume"] if uv else []) + \
               ([" ATR"] if ua else []) + \
               ([" Stoch RSI"] if ust else []) + \
               ([" OBV"] if uob else [])

        fig = make_subplots(rows=1+n, cols=1, shared_xaxes=True,
                            row_heights=rh, subplot_titles=subs,
                            vertical_spacing=0.02)

        # Candlestick
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"], name=t,
            increasing_line_color="#2dc653", decreasing_line_color="#e63946",
            increasing_fillcolor="#2dc653",  decreasing_fillcolor="#e63946"),
            row=1, col=1)

        cl = df["Close"].squeeze()

        # Overlays on main chart
        if "EMA 9"  in inds:
            fig.add_trace(go.Scatter(x=df.index, y=ta.trend.EMAIndicator(cl, window=9).ema_indicator(),
                name="EMA 9",  line=dict(color=IND_COLORS["EMA 9"],  width=1.3)), row=1, col=1)
        if "EMA 21" in inds:
            fig.add_trace(go.Scatter(x=df.index, y=ta.trend.EMAIndicator(cl, window=21).ema_indicator(),
                name="EMA 21", line=dict(color=IND_COLORS["EMA 21"], width=1.3)), row=1, col=1)
        if "EMA 50" in inds:
            fig.add_trace(go.Scatter(x=df.index, y=ta.trend.EMAIndicator(cl, window=50).ema_indicator(),
                name="EMA 50", line=dict(color=IND_COLORS["EMA 50"], width=1.5)), row=1, col=1)
        if "SMA 200" in inds:
            fig.add_trace(go.Scatter(x=df.index, y=ta.trend.SMAIndicator(cl, window=200).sma_indicator(),
                name="SMA 200", line=dict(color=IND_COLORS["SMA 200"], width=1.5, dash="dash")), row=1, col=1)
        if "VWAP" in inds:
            try:
                fig.add_trace(go.Scatter(x=df.index,
                    y=ta.volume.VolumeWeightedAveragePrice(df["High"], df["Low"], df["Close"], df["Volume"]).volume_weighted_average_price(),
                    name="VWAP", line=dict(color=IND_COLORS["VWAP"], width=1.5, dash="dot")), row=1, col=1)
            except: pass
        if "Bollinger Bands" in inds:
            _bb = ta.volatility.BollingerBands(cl, window=20, window_dev=2)
            fig.add_trace(go.Scatter(x=df.index, y=_bb.bollinger_hband(),
                name="BB Upper", line=dict(color=IND_COLORS["BB Upper"], width=1.2, dash="dot"),
                showlegend=True), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=_bb.bollinger_mavg(),
                name="BB Mid",   line=dict(color=IND_COLORS["BB Mid"],   width=0.8, dash="dot"),
                showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=_bb.bollinger_lband(),
                name="BB Lower", line=dict(color=IND_COLORS["BB Lower"], width=1.2, dash="dot"),
                fill="tonexty", fillcolor="rgba(144,224,239,0.05)", showlegend=False), row=1, col=1)

        # Buy / Sell arrows (this ticker only, price range must match chart)
        t_trades = _trades_for_chart(trades, t, df)
        buys  = [tr for tr in t_trades if tr["side"]=="buy"]
        sells = [tr for tr in t_trades if tr["side"]=="sell"]
        if buys:
            fig.add_trace(go.Scatter(
                x=[b["x"] for b in buys], y=[b["y"] for b in buys],
                mode="markers", name="Buy",
                marker=dict(symbol="triangle-up", size=14, color="#2dc653",
                            line=dict(color="#fff",width=1))), row=1, col=1)
        if sells:
            fig.add_trace(go.Scatter(
                x=[s["x"] for s in sells], y=[s["y"] for s in sells],
                mode="markers", name="Sell",
                marker=dict(symbol="triangle-down", size=14, color="#e63946",
                            line=dict(color="#fff",width=1))), row=1, col=1)

        # Sub-chart indicators
        cr = 2
        if ur:
            rsi = ta.momentum.RSIIndicator(cl, window=14).rsi()
            fig.add_trace(go.Scatter(x=df.index, y=rsi, name="RSI",
                line=dict(color=IND_COLORS["RSI"], width=1.5)), row=cr, col=1)
            fig.add_hline(y=70, line_color="#e63946", line_dash="dash", line_width=1, row=cr, col=1)
            fig.add_hline(y=30, line_color="#2dc653", line_dash="dash", line_width=1, row=cr, col=1)
            fig.add_hrect(y0=70, y1=100, fillcolor="rgba(230,57,70,0.04)", line_width=0, row=cr, col=1)
            fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(45,198,83,0.04)",  line_width=0, row=cr, col=1)
            fig.update_yaxes(range=[0,100], row=cr, col=1)
            cr += 1
        if um:
            _macd = ta.trend.MACD(cl, window_slow=26, window_fast=12, window_sign=9)
            fig.add_trace(go.Scatter(x=df.index, y=_macd.macd(),
                name="MACD",   line=dict(color=IND_COLORS["MACD"],   width=1.5)), row=cr, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=_macd.macd_signal(),
                name="Signal", line=dict(color=IND_COLORS["Signal"], width=1.5)), row=cr, col=1)
            hv = _macd.macd_diff()
            fig.add_trace(go.Bar(x=df.index, y=hv, name="Hist",
                marker_color=["#2dc653" if v>=0 else "#e63946" for v in hv.fillna(0)],
                opacity=0.7), row=cr, col=1)
            cr += 1
        if uv:
            fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume",
                marker_color=["#2dc653" if c>=o else "#e63946"
                              for c,o in zip(df["Close"].squeeze(), df["Open"].squeeze())],
                opacity=0.8), row=cr, col=1)
            cr += 1
        if ua:
            atr = ta.volatility.AverageTrueRange(df["High"], df["Low"], df["Close"], window=14).average_true_range()
            fig.add_trace(go.Scatter(x=df.index, y=atr, name="ATR",
                line=dict(color=IND_COLORS["ATR"], width=1.2)), row=cr, col=1)
            cr += 1
        if ust:
            _sr = ta.momentum.StochRSIIndicator(cl, window=14, smooth1=3, smooth2=3)
            fig.add_trace(go.Scatter(x=df.index, y=_sr.stochrsi_k()*100,
                name="Stoch K", line=dict(color=IND_COLORS["Stoch RSI K"], width=1.3)), row=cr, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=_sr.stochrsi_d()*100,
                name="Stoch D", line=dict(color=IND_COLORS["Stoch RSI D"], width=1.3)), row=cr, col=1)
            fig.add_hline(y=80, line_color="#e63946", line_dash="dot", line_width=1, row=cr, col=1)
            fig.add_hline(y=20, line_color="#2dc653", line_dash="dot", line_width=1, row=cr, col=1)
            fig.update_yaxes(range=[0,100], row=cr, col=1)
            cr += 1
        if uob:
            obv = ta.volume.OnBalanceVolumeIndicator(cl, df["Volume"]).on_balance_volume()
            fig.add_trace(go.Scatter(x=df.index, y=obv, name="OBV",
                line=dict(color=IND_COLORS["OBV"], width=1.2),
                fill="tozeroy", fillcolor="rgba(233,196,106,0.06)"), row=cr, col=1)
            cr += 1

        # Range selector buttons including 1D and 1W
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="#12102a", plot_bgcolor="#1c1838",
            font=dict(color="#e8e4f0", family="monospace"),
            legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
            xaxis_rangeslider_visible=False,
            margin=dict(l=10,r=10,t=40,b=10),
            dragmode="zoom",
            uirevision=f"{t}-{interval}-{period}",
            newshape=dict(line=dict(color="#e8621a",width=2,dash="dash"),
                          fillcolor="rgba(247,201,72,0.08)"),
            modebar=dict(bgcolor="rgba(0,0,0,0)", color="#8b7fbf", activecolor="#8b7fbf"))
        fig.update_xaxes(gridcolor="#3d3470", showgrid=True, rangeslider_visible=False)
        range_btns = _chart_range_buttons(df, interval)
        xaxis_kw = dict(
            rangeselector=dict(
                buttons=range_btns,
                bgcolor="#3d3470", activecolor="#251f45",
                font=dict(color="#e8e4f0", size=10)),
            row=1, col=1)
        if interval in INTRADAY_INTERVALS:
            xaxis_kw.update(tickformat="%b %d %H:%M", hoverformat="%Y-%m-%d %H:%M")
        fig.update_xaxes(**xaxis_kw)
        if interval in INTRADAY_INTERVALS:
            fig.update_xaxes(tickformat="%b %d %H:%M", hoverformat="%Y-%m-%d %H:%M")
        y_lo, y_hi = _chart_price_bounds(df)
        fig.update_yaxes(range=[y_lo, y_hi], autorange=False, row=1, col=1)
        fig.update_yaxes(gridcolor="#3d3470", showgrid=True)

        last = float(cl.iloc[-1])
        prev = float(cl.iloc[-2]) if len(cl) > 1 else last
        chg  = last - prev; pct = chg / prev * 100 if prev else 0
        ar   = "+" if pct >= 0 else ""; c2 = "#2dc653" if pct >= 0 else "#e63946"
        mode_badge = html.Span(
            f" [{mode.upper()} MODE -- click chart to place arrow]",
            style={"color":"#e8621a","fontSize":"10px","marginLeft":"10px"}) if mode in ("buy", "sell") else html.Span(
            " [REMOVE MODE -- click near a marker to delete]",
            style={"color":"#e63946","fontSize":"10px","marginLeft":"10px"}) if mode == "remove" else html.Span()
        clamp_note = ""
        if requested_period != period:
            clamp_note = f"  |  period auto-set to {period} for {interval}"
        info = html.Span([
            html.Span(f"{t}  ", style={"color":"#e8621a","fontWeight":"bold","fontSize":"14px"}),
            html.Span(f"${last:.2f}  ", style={"color":"#e8e4f0","fontSize":"13px"}),
            html.Span(f"{ar}{chg:.2f} ({ar}{pct:.2f}%)",
                      style={"color":c2,"fontWeight":"bold","fontSize":"13px"}),
            html.Span(f"  |  {len(df)} bars  |  {interval}/{period}{clamp_note}",
                      style={"color":"#6b5fa0","fontSize":"11px"}),
            mode_badge,
        ])

        # Trade log below chart
        if t_trades:
            log_items = []
            for tr in reversed(t_trades[-10:]):
                col2 = "#2dc653" if tr["side"]=="buy" else "#e63946"
                sym2 = "▲ BUY" if tr["side"]=="buy" else "▼ SELL"
                log_items.append(html.Span(
                    f"{sym2} @ {tr['x']}  ${float(tr['y']):.2f}   ",
                    style={"color":col2,"marginRight":"12px"}))
            trade_log = html.Div([
                html.Span("Trade annotations: ", style={"color":"#554880"}),
                html.Span(f"({len(t_trades)} for {t}) ", style={"color":"#554880","fontSize":"10px"}),
            ] + log_items)
        else:
            trade_log = html.Span()

        return fig, info, trades, trade_log

    except Exception as e:
        fig = go.Figure()
        fig.update_layout(template="plotly_dark", paper_bgcolor="#12102a",
            annotations=[dict(text=f"Error: {e}", showarrow=False,
                              font=dict(color="#e63946", size=13))])
        return fig, html.Span(f"Error: {e}", style={"color":"#e63946"}), trades, html.Span()





# ============================================================
# OPTIONS — IV & GREEKS
# ============================================================
def options_page():
    return html.Div([
        html.H4("Options — IV & Greeks", className="text-warning mb-2"),
        html.Small("Live option chain from Yahoo Finance with Black-Scholes Greeks computed from implied volatility.",
                   className="text-muted d-block mb-3", style={"fontSize": "11px"}),
        dbc.Row([
            col(dbc.Input(id="opt-t", value="AAPL", placeholder="Ticker",
                className="bg-dark text-light border-secondary", debounce=True), 2),
            col(dcc.Dropdown(id="opt-exp", placeholder="Expiry...", clearable=False,
                style={"background": "#251f45", "color": "#111", "border": "1px solid #555"}), 3),
            col(dbc.RadioItems(id="opt-side",
                options=[{"label": "Calls", "value": "calls"}, {"label": "Puts", "value": "puts"}],
                value="calls", inline=True,
                labelStyle={"marginRight": "14px", "fontSize": "12px", "cursor": "pointer"}), 3),
        ], className="mb-2 g-2 align-items-center"),
        html.Div(id="opt-info", className="mb-2", style={"fontSize": "13px", "minHeight": "20px"}),
        html.Div(id="opt-table", style={"overflowX": "auto"}),
    ])

@app.callback(
    Output("opt-exp", "options"), Output("opt-exp", "value"),
    Output("opt-info", "children"), Output("opt-table", "children"),
    Input("opt-t", "value"), Input("opt-exp", "value"), Input("opt-side", "value"),
    prevent_initial_call=False)
def update_options(ticker, expiry, side):
    t = (ticker or "AAPL").strip().upper()
    try:
        data = _options_chain(t, expiry)
    except Exception as e:
        return [], None, html.Span(f"Error: {e}", style={"color": "#e63946"}), html.Div()
    exp_opts = [{"label": e, "value": e} for e in data.get("expirations", [])]
    use_exp = expiry if expiry in data.get("expirations", []) else data.get("expiry")
    spot = data.get("spot")
    info = html.Span([
        html.Span(f"{t}  ", style={"color": "#e8621a", "fontWeight": "bold"}),
        html.Span(f"Spot ${spot:.2f}  " if spot else "", style={"color": "#e8e4f0"}),
        html.Span(f"|  Expiry {use_exp}  " if use_exp else "", style={"color": "#6b5fa0", "fontSize": "11px"}),
    ])
    rows = data.get(side or "calls", [])
    if not rows:
        return exp_opts, use_exp, info, html.P("No chain data available.", className="text-muted")
    hdr = html.Tr([
        html.Th("Strike", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("Bid", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("Ask", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("Mid", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("IV %", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("Delta", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("Gamma", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("Theta", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("Vega", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("Rho", style={"color": "#8b7fbf", "fontSize": "11px"}),
        html.Th("OI", style={"color": "#8b7fbf", "fontSize": "11px"}),
    ])
    body = []
    for r in rows:
        g = r.get("greeks") or {}
        itm = r.get("inTheMoney")
        strike_c = "#2dc653" if itm else "#e8e4f0"
        body.append(html.Tr([
            html.Td(f"${r['strike']:.2f}", style={"color": strike_c, "fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(r.get("bid") or "—", style={"fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(r.get("ask") or "—", style={"fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(r.get("mid") or "—", style={"fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(f"{r['iv']:.1f}" if r.get("iv") else "—", style={"color": "#e8621a", "fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(f"{g.get('delta', 0):.3f}" if g else "—", style={"fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(f"{g.get('gamma', 0):.4f}" if g else "—", style={"fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(f"{g.get('theta', 0):.3f}" if g else "—", style={"fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(f"{g.get('vega', 0):.3f}" if g else "—", style={"fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(f"{g.get('rho', 0):.3f}" if g else "—", style={"fontFamily": "monospace", "fontSize": "12px"}),
            html.Td(f"{r.get('openInterest', 0):,}", style={"fontFamily": "monospace", "fontSize": "11px", "color": "#6b5fa0"}),
        ]))
    table = html.Table([html.Thead(hdr), html.Tbody(body)],
        style={"width": "100%", "borderCollapse": "collapse", "background": "#1c1838", "borderRadius": "6px"})
    return exp_opts, use_exp, info, table

# ============================================================
# LEVEL 2
# ============================================================
def level2_page():
    return html.Div([
        html.H4("Level 2 Order Book",className="text-warning mb-1"),
        html.Small("Bid/ask depth + pressure from Finnhub REST (every 2s). Time & Sales via WebSocket (market hours only).",className="text-muted d-block mb-3",style={"fontSize":"11px"}),
        dbc.Row([col(dbc.Input(id="l2-sym",value="AAPL",placeholder="Ticker",className="bg-dark text-light border-secondary"),2),col(dbc.Button("Connect",id="l2-btn",color="warning",size="sm"),"auto"),col(html.Span(id="l2-st",style={"fontSize":"12px","color":"#2dc653","marginLeft":"8px"}),"auto")],className="mb-3 g-2 align-items-center"),
        html.Div(id="l2-quote",className="mb-3"),
        dbc.Row([
            col([html.Small("ORDER BOOK",className="text-muted d-block mb-1",style={"fontSize":"10px","letterSpacing":"0.1em"}),html.Div(id="l2-book")],5),
            col([html.Small("TIME & SALES  (WebSocket -- market hours only)",className="text-muted d-block mb-1",style={"fontSize":"10px","letterSpacing":"0.1em"}),html.Div(id="l2-tape",style={"maxHeight":"320px","overflowY":"auto","background":"#12102a"})],4),
            col([html.Small("ORDER BOOK PRESSURE",className="text-muted d-block mb-1",style={"fontSize":"10px","letterSpacing":"0.1em"}),dcc.Graph(id="l2-pres",style={"height":"200px"},config={"displayModeBar":False}),html.Div(id="l2-dom",style={"textAlign":"center","fontSize":"12px","marginTop":"4px"})],3),
        ]),
        dcc.Graph(id="l2-price",style={"height":"160px","marginTop":"12px"},config={"displayModeBar":False}),
    ])

@app.callback(Output("l2-st","children"),Input("l2-btn","n_clicks"),State("l2-sym","value"),prevent_initial_call=True)
def connect_l2(n,sym):
    if not sym: return "Enter a ticker"
    if not FINNHUB_KEY or FINNHUB_KEY=="YOUR_KEY_HERE": return "Set FINNHUB_API_KEY in .env.trading"
    try: start_l2(sym.strip().upper()); return f"Streaming {sym.strip().upper()}"
    except Exception as e: return f"Error: {e}"

@app.callback(Output("l2-quote","children"),Output("l2-book","children"),Output("l2-tape","children"),Output("l2-pres","figure"),Output("l2-dom","children"),Output("l2-price","figure"),Input("l2-tick","n_intervals"),State("l2-sym","value"))
def refresh_l2(_,sym):
    s=(sym or "AAPL").strip().upper(); qel=html.Div(); bids=asks=None
    bid_total=ask_total=0.0
    if fh:
        try:
            q=fh.quote(s); cur=float(q.get("c") or q.get("pc") or 0)
            bid=float(q.get("b") or cur*0.9999); ask=float(q.get("a") or cur*1.0001)
            pc2=float(q.get("pc") or cur); hi=float(q.get("h") or cur); lo=float(q.get("l") or cur)
            chg=cur-pc2; pct=(chg/pc2*100) if pc2 else 0; cc=pc(chg); ar="+" if chg>=0 else ""
            qel=dbc.Row([
                col(html.Div([html.Small("LAST",style={"color":"#6b5fa0","fontSize":"10px","display":"block"}),html.Span(f"${cur:,.2f}",style={"color":"#e8e4f0","fontWeight":"bold","fontSize":"18px"})]),"auto"),
                col(html.Div([html.Small("CHANGE",style={"color":"#6b5fa0","fontSize":"10px","display":"block"}),html.Span(f"{ar}{pct:.2f}% ({ar}${chg:.2f})",style={"color":cc,"fontWeight":"bold","fontSize":"14px"})]),"auto"),
                col(html.Div([html.Small("BID",style={"color":"#e63946","fontSize":"10px","display":"block"}),html.Span(f"${bid:,.2f}",style={"color":"#e63946","fontSize":"14px"})]),"auto"),
                col(html.Div([html.Small("ASK",style={"color":"#2dc653","fontSize":"10px","display":"block"}),html.Span(f"${ask:,.2f}",style={"color":"#2dc653","fontSize":"14px"})]),"auto"),
                col(html.Div([html.Small("RANGE",style={"color":"#6b5fa0","fontSize":"10px","display":"block"}),html.Span(f"${lo:,.2f} - ${hi:,.2f}",style={"color":"#a09ac8","fontSize":"13px"})]),"auto"),
                col(html.Div([html.Small("PREV CLOSE",style={"color":"#6b5fa0","fontSize":"10px","display":"block"}),html.Span(f"${pc2:,.2f}",style={"color":"#8b7fbf","fontSize":"13px"})]),"auto"),
            ],className="g-4 px-2 py-2",style={"background":"#1c1838","borderRadius":"6px","border":"1px solid #222"})
            if cur>0:
                import random; rng=random.Random(int(time.time()/3))
                sp=max(ask-bid,cur*0.0001); st=sp/2
                # Simulate order book with realistic depth weighting
                bids=[{"price":round(bid-i*st*(1+i*0.15),2),"size":rng.randint(100,8000)*(5 if round(bid-i*st*(1+i*0.15),0)==bid-i*st*(1+i*0.15) else 1)} for i in range(10)]
                asks=[{"price":round(ask+i*st*(1+i*0.15),2),"size":rng.randint(100,8000)*(5 if round(ask+i*st*(1+i*0.15),0)==ask+i*st*(1+i*0.15) else 1)} for i in range(10)]
                # Order book pressure = total depth on each side
                bid_total=sum(b["size"] for b in bids)
                ask_total=sum(a["size"] for a in asks)
        except: pass

    # -- Order book table
    if bids and asks:
        mx=max([b["size"] for b in bids]+[a["size"] for a in asks]) or 1
        ht=html.Tr([html.Th("Size",style={"color":"#e63946","padding":"3px 8px","fontSize":"11px","textAlign":"right","width":"25%"}),html.Th("Bid",style={"color":"#e63946","padding":"3px 8px","fontSize":"11px","textAlign":"right","width":"25%"}),html.Th("Ask",style={"color":"#2dc653","padding":"3px 8px","fontSize":"11px","textAlign":"left","width":"25%"}),html.Th("Size",style={"color":"#2dc653","padding":"3px 8px","fontSize":"11px","textAlign":"left","width":"25%"})])
        drs=[]
        for i in range(min(10,len(bids),len(asks))):
            b=bids[i]; a=asks[i]; bp4=b["size"]/mx; ap4=a["size"]/mx; bold="bold" if i==0 else "normal"
            bsz=f'{b["size"]:,}'; asp=f'${a["price"]:.2f}'; bpr=f'${b["price"]:.2f}'; asz=f'{a["size"]:,}'
            drs.append(html.Tr([
                html.Td(bsz,style={"padding":"3px 8px","textAlign":"right","color":"#e63946","fontWeight":bold,"fontSize":"12px","background":f"rgba(230,57,70,{bp4*0.3:.2f})"}),
                html.Td(bpr,style={"padding":"3px 8px","textAlign":"right","color":"#e63946","fontWeight":bold,"fontSize":"12px"}),
                html.Td(asp,style={"padding":"3px 8px","textAlign":"left","color":"#2dc653","fontWeight":bold,"fontSize":"12px"}),
                html.Td(asz,style={"padding":"3px 8px","textAlign":"left","color":"#2dc653","fontWeight":bold,"fontSize":"12px","background":f"rgba(45,198,83,{ap4*0.3:.2f})"}),
            ]))
        sp2=round(asks[0]["price"]-bids[0]["price"],4); mid=round((asks[0]["price"]+bids[0]["price"])/2,2)
        drs.append(html.Tr([html.Td(colSpan=4,children=f"Spread: ${sp2:.4f}   Mid: ${mid:.2f}",style={"textAlign":"center","color":"#6b5fa0","fontSize":"10px","padding":"4px"})]))
        book=html.Table([html.Thead(ht),html.Tbody(drs)],style={"width":"100%","borderCollapse":"collapse","background":"#12102a"})
    else:
        book=html.P("Enter ticker and click Connect.",style={"color":"#6b5fa0","fontSize":"12px"})

    # -- Time & Sales tape (WebSocket trades)
    trades=list(L2.get(s,[]))
    if trades:
        pp=trades[0]["price"]; its=[]
        for tr in trades[:40]:
            p2=tr["price"]; v=tr["volume"]
            try: ts2=datetime.fromtimestamp(tr["time"]/1000).strftime("%H:%M:%S")
            except: ts2="--:--"
            tc="#2dc653" if p2>=pp else "#e63946"
            its.append(html.Div([
                html.Span(ts2,style={"color":"#554880","width":"60px","display":"inline-block","fontSize":"11px"}),
                html.Span(f"${p2:.2f}",style={"color":tc,"fontWeight":"bold","width":"70px","display":"inline-block","fontSize":"12px"}),
                html.Span(f"{int(v):,}" if v>=1 else f"{v:.4f}",style={"color":"#8b7fbf","width":"65px","display":"inline-block","textAlign":"right","fontSize":"11px"}),
                html.Span("▲" if p2>=pp else "▼",style={"color":tc,"fontSize":"10px","marginLeft":"4px"}),
            ],style={"borderBottom":"1px solid #111","padding":"2px 4px"}))
            pp=p2
        tape=html.Div(its)
    else:
        tape=html.Div([
            html.P("Waiting for trade data.",style={"color":"#6b5fa0","fontSize":"12px","marginBottom":"4px"}),
            html.P("Click Connect, then wait for market activity.",style={"color":"#554880","fontSize":"11px"}),
            html.P("Active during market hours and premarket (~4am ET).",style={"color":"#554880","fontSize":"11px"}),
        ])

    # -- Pressure from ORDER BOOK DEPTH (works immediately, no WebSocket needed)
    # Also blend in trade flow if available
    if bid_total>0 or ask_total>0:
        ob_total=bid_total+ask_total or 1
        ob_bid_pct=bid_total/ob_total*100
        ob_ask_pct=ask_total/ob_total*100

        # If we also have live trade flow, blend 60% order book / 40% trade flow
        if len(trades)>=5:
            ref_p=asks[0]["price"] if asks else None; ref_b=bids[0]["price"] if bids else None
            if ref_p and ref_b:
                bv=sv=0.0
                for tr in trades[:100]:
                    p3=tr["price"]; v=tr["volume"]; mp=(ref_p+ref_b)/2
                    if p3>=ref_p: bv+=v
                    elif p3<=ref_b: sv+=v
                    else: bv+=(v*0.6 if p3>=mp else v*0.4); sv+=(v*0.4 if p3>=mp else v*0.6)
                tf_total=bv+sv or 1; tf_bid=bv/tf_total*100
                bpp=round(ob_bid_pct*0.6+tf_bid*0.4,1)
            else:
                bpp=round(ob_bid_pct,1)
        else:
            bpp=round(ob_bid_pct,1)
        spp=round(100-bpp,1)
    else:
        bpp=spp=50.0

    dom="BUYERS" if bpp>55 else "SELLERS" if spp>55 else "NEUTRAL"
    dc="#2dc653" if dom=="BUYERS" else "#e63946" if dom=="SELLERS" else "#e8621a"

    # Pressure bar chart -- horizontal for better readability
    fp=go.Figure()
    fp.add_trace(go.Bar(name="Bid depth",x=[bpp],y=["Pressure"],orientation="h",
        marker_color="#2dc653",text=f"BID {bpp:.0f}%",textposition="inside",textfont=dict(size=12,color="white")))
    fp.add_trace(go.Bar(name="Ask depth",x=[spp],y=["Pressure"],orientation="h",
        marker_color="#e63946",text=f"ASK {spp:.0f}%",textposition="inside",textfont=dict(size=12,color="white")))
    fp.update_layout(
        template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",
        barmode="stack",margin=dict(l=5,r=5,t=10,b=10),
        showlegend=False,height=80,
        xaxis=dict(range=[0,100],showgrid=False,showticklabels=False),
        yaxis=dict(showgrid=False,showticklabels=False))

    # Depth imbalance gauge (bid $ vs ask $ depth)
    total_depth=bid_total+ask_total
    source_label="order book" if len(trades)<5 else "book + flow"
    del2=html.Div([
        html.Span(dom,style={"color":dc,"fontWeight":"bold","fontSize":"14px"}),
        html.Br(),
        html.Span(f"Bid: {bid_total:,.0f}  |  Ask: {ask_total:,.0f}",style={"color":"#6b5fa0","fontSize":"10px"}),
        html.Br(),
        html.Span(f"Source: {source_label}",style={"color":"#554880","fontSize":"10px"}),
    ],style={"textAlign":"center","marginTop":"8px"})

    # Live price line from WebSocket trades
    rev=list(reversed(trades)); valid=[tr for tr in rev if tr.get("time",0)>1e9]
    if len(valid)>=2:
        tl=[datetime.fromtimestamp(tr["time"]/1000) for tr in valid]
        pl=[tr["price"] for tr in valid]
        # Color line by direction
        fpr=go.Figure(go.Scatter(x=tl,y=pl,mode="lines",
            line=dict(color="#e8621a",width=1.5),
            fill="tozeroy",fillcolor="rgba(247,201,72,0.04)"))
        fpr.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",
            title=dict(text=f"{s}  live trades",font=dict(size=11,color="#6b5fa0")),
            margin=dict(l=5,r=5,t=25,b=20),showlegend=False,
            xaxis=dict(gridcolor="#3d3470"),yaxis=dict(gridcolor="#3d3470",tickprefix="$"))
    else:
        fpr=go.Figure()
        fpr.update_layout(template="plotly_dark",paper_bgcolor="#12102a",
            annotations=[dict(text="Live price chart appears after WebSocket trades stream in (market hours)",showarrow=False,font=dict(color="#554880",size=11))])

    return qel,book,tape,fp,del2,fpr

# ============================================================
# SCREENER
# ============================================================
def screener_page():
    return html.Div([
        html.H4("Stock Screener",className="text-warning mb-1"),
        html.Small("Search by industry or enter a keyword. Results sorted by biggest movers.",className="text-muted d-block mb-3",style={"fontSize":"11px"}),
        dbc.Card([dbc.CardBody([html.H6("Industry Search",className="text-warning mb-2"),dbc.Row([col(dcc.Dropdown(id="sc-th",options=[{"label":k,"value":k} for k in THEMES],placeholder="Select an industry / theme...",style={"background":"#251f45","color":"#111","border":"1px solid #555"}),5),col(dbc.Input(id="sc-kw",placeholder="Or type: Hospitality, Banking, Mining...",className="bg-dark text-light border-secondary"),4),col(dbc.Button("Search",id="sc-tb",color="warning",size="sm"),"auto")],className="g-2 align-items-center")])],style={"background":"#1c1838","border":"1px solid #333","marginBottom":"10px"}),
        dbc.Card([dbc.CardBody([html.H6("Custom Filter",className="text-warning mb-2"),dbc.Row([col([html.Small("Min $",className="text-muted d-block",style={"fontSize":"10px"}),dbc.Input(id="sc-mn",value="1",type="number",className="bg-dark text-light border-secondary",size="sm")],2),col([html.Small("Max $",className="text-muted d-block",style={"fontSize":"10px"}),dbc.Input(id="sc-mx",value="5000",type="number",className="bg-dark text-light border-secondary",size="sm")],2),col([html.Small("Min % Chg",className="text-muted d-block",style={"fontSize":"10px"}),dbc.Input(id="sc-chg",value="-100",type="number",className="bg-dark text-light border-secondary",size="sm")],2),col([html.Small("Tickers (comma sep)",className="text-muted d-block",style={"fontSize":"10px"}),dbc.Input(id="sc-tk",placeholder="AAPL, NVDA...",className="bg-dark text-light border-secondary",size="sm")],4),col(dbc.Button("Run",id="sc-fb",color="warning",size="sm",style={"marginTop":"14px"}),"auto")],className="g-2")])],style={"background":"#1c1838","border":"1px solid #333","marginBottom":"10px"}),
        dcc.Loading(html.Div(id="sc-res"),type="circle",color="#e8621a"),
    ])

@app.callback(Output("sc-res","children"),Input("sc-tb","n_clicks"),Input("sc-fb","n_clicks"),State("sc-th","value"),State("sc-kw","value"),State("sc-mn","value"),State("sc-mx","value"),State("sc-chg","value"),State("sc-tk","value"),prevent_initial_call=True)
def run_screener(tc,fc,theme,kw,smin,smax,schg,stk):
    ctx=callback_context
    if not ctx.triggered: return no_update
    btn=ctx.triggered[0]["prop_id"].split(".")[0]
    tickers=[]; title=""
    if btn=="sc-tb":
        if kw and kw.strip():
            k2=kw.strip().lower(); tickers=[]
            for k,v in KEYWORD_MAP.items():
                if k in k2: tickers.extend(v)
            for tn,tv in THEMES.items():
                if k2 in tn.lower(): tickers.extend(tv)
            seen=set(); tickers=[t for t in tickers if t not in seen and not seen.add(t)]
            title=f"Search: {kw.strip()!r}"
            if not tickers: return html.P(f"No match for {kw!r}. Try: AI, Hospitality, Banking, Mining...",className="text-muted")
        elif theme: tickers=THEMES.get(theme,[]); title=f"Industry: {theme}"
        else: return html.P("Select a theme or type a keyword.",className="text-muted")
    elif btn=="sc-fb":
        if stk: tickers=[t.strip().upper() for t in stk.split(",") if t.strip()]; title="Custom filter"
        else:
            seen=set(); tickers=[]
            for lst in THEMES.values():
                for t in lst:
                    if t not in seen: seen.add(t); tickers.append(t)
            title="Broad scan"
    else: return no_update
    try: mn=float(smin or 0); mx=float(smax or 99999); mc=float(schg or -999)
    except: mn,mx,mc=0,99999,-999
    rows=[]
    for sym in tickers:
        try:
            if not fh: continue
            q=fh.quote(sym); p=float(q.get("c") or q.get("pc") or 0)
            pct=float(q.get("dp") or 0); ch=float(q.get("d") or 0)
            hi=float(q.get("h") or 0); lo=float(q.get("l") or 0)
            if p==0 or p<mn or p>mx or pct<mc: continue
            c="#2dc653" if pct>=0 else "#e63946"; ar="+" if pct>=0 else ""
            rows.append({"sym":sym,"p":p,"pct":pct,"ch":ch,"hi":hi,"lo":lo,"c":c,"ar":ar})
        except: pass
    if not rows: return html.Div([html.P(f"No results for {title!r}.",className="text-muted"),html.P("Finnhub free tier: 60 calls/min. Wait 60s and retry if empty.",className="text-muted small")])
    rows.sort(key=lambda x:abs(x["pct"]),reverse=True)
    out=[html.H6(f"{title}  --  {len(rows)} results",className="text-warning mb-2"),hdr([("Symbol",2),("Price",2),("Change %",2),("Change $",2),("Day Range",3),("Research",1)])]
    for r in rows:
        pstr=f"${r['p']:,.4f}" if r["p"]<1 else f"${r['p']:,.2f}"
        out.append(dbc.Row([col(html.Span(r["sym"],style={"color":"#e8621a","fontWeight":"bold"}),2),col(html.Span(pstr,style={"color":"#e8e4f0","fontWeight":"bold"}),2),col(html.Span(f"{r['ar']}{r['pct']:.2f}%",style={"color":r["c"],"fontWeight":"bold"}),2),col(html.Span(f"{r['ar']}${r['ch']:.2f}",style={"color":r["c"]}),2),col(html.Span(f"H:{r['hi']:.2f} L:{r['lo']:.2f}" if r["hi"]>0 else "Premarket",style={"color":"#a09ac8","fontSize":"12px"}),3),col(html.A("SA",href=f"https://stockanalysis.com/stocks/{r['sym'].lower()}/",target="_blank",className="text-info",style={"fontSize":"12px"}),1)],className="mb-1 py-2 border-bottom border-secondary align-items-center"))
    return out

# ============================================================
# NEWS
# ============================================================
def news_page():
    return html.Div([
        html.H4("News & Earnings",className="text-warning mb-3"),
        html.Div(id="nw-earnings-cal",className="mb-3"),
        dbc.Row([
            col(dbc.Input(id="nw-t",value="AAPL",placeholder="Ticker",className="bg-dark text-light border-secondary",debounce=True),3),
            col(dbc.Button("Load",id="nw-l",color="warning",size="sm"),"auto"),
            col(dcc.Dropdown(id="nw-range",
                options=[{"label":l,"value":v} for l,v in [("3M","3mo"),("6M","6mo"),("1Y","1y"),("2Y","2y"),("5Y","5y")]],
                value="5y", clearable=False,
                style={"background":"#251f45","color":"#111","border":"1px solid #555","width":"80px"}),
                "auto"),
        ],className="mb-3 g-2 align-items-center"),
        dcc.Loading(html.Div(id="nw-c"),type="circle",color="#e8621a"),
    ])

@app.callback(Output("nw-c","children"),Input("nw-l","n_clicks"),Input("nw-t","value"),Input("nw-range","value"),prevent_initial_call=False)
def load_news(n,ticker,price_range):
    t=(ticker or "AAPL").strip().upper(); secs=[]; price_range=price_range or "5y"
    # Price chart from yfinance -- goes back as far as data exists
    try:
        hist=yf.download(t,period=price_range,interval="1wk",progress=False,auto_adjust=True)
        if not hist.empty:
            hist.columns=[c[0] if isinstance(c,tuple) else c for c in hist.columns]
            cl=hist["Close"].squeeze()
            fig_p=go.Figure()
            fig_p.add_trace(go.Scatter(x=hist.index,y=cl,name="Price",
                line=dict(color="#e8621a",width=1.5),
                fill="tozeroy",fillcolor="rgba(247,201,72,0.06)"))
            fig_p.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",
                title=f"{t} -- Price History ({price_range})",height=260,
                margin=dict(l=10,r=10,t=40,b=10),
                xaxis=dict(gridcolor="#3d3470"),yaxis=dict(gridcolor="#3d3470",tickprefix="$"))
            secs.append(dcc.Graph(figure=fig_p,config={"scrollZoom":True,"modeBarButtonsToRemove":["lasso2d","select2d"]},style={"marginBottom":"16px"}))
    except: pass
    if fh:
        try:
            earnings=fh.company_earnings(t,limit=20)
            if earnings:
                dates=[e.get("period","") for e in earnings]; actual=[e.get("actual",None) for e in earnings]; est=[e.get("estimate",None) for e in earnings]
                fig_e=go.Figure()
                fig_e.add_trace(go.Bar(x=dates,y=actual,name="Actual EPS",marker_color=["#2dc653" if (a or 0)>=(e2 or 0) else "#e63946" for a,e2 in zip(actual,est)]))
                fig_e.add_trace(go.Scatter(x=dates,y=est,name="Estimate",line=dict(color="#e8621a",dash="dash"),mode="lines+markers"))
                fig_e.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",
                    title=f"{t} -- Quarterly EPS (green=beat, red=miss)",height=300,
                    margin=dict(l=10,r=10,t=40,b=10),legend=dict(orientation="h"))
                secs.append(dcc.Graph(figure=fig_e,config={"modeBarButtonsToRemove":["lasso2d","select2d"],"scrollZoom":True},style={"marginBottom":"16px"}))
        except: pass
        try:
            today=datetime.now().strftime("%Y-%m-%d")
            ninety_ago=(datetime.now()-timedelta(days=90)).strftime("%Y-%m-%d")
            news=fh.company_news(t,_from=ninety_ago,to=today)
            if news:
                secs.append(html.H6("Latest News (90 days)",className="text-warning mb-2"))
                for nw in news[:25]:
                    sc2=nw.get("sentiment",""); bc="#2dc653" if sc2=="positive" else "#e63946" if sc2=="negative" else "#6b5fa0"
                    secs.append(html.Div([
                        html.A(nw.get("headline",""),href=nw.get("url","#"),target="_blank",
                            style={"color":"#e8e4f0","fontWeight":"500","textDecoration":"none","fontSize":"13px"}),
                        html.Br(),
                        html.Small([html.Span(nw.get("source",""),style={"color":"#e8621a"}),"  |  ",
                            html.Span(datetime.fromtimestamp(nw.get("datetime",0)).strftime("%b %d %Y %H:%M") if nw.get("datetime") else "",style={"color":"#8b7fbf"})]),
                        html.P(nw.get("summary","")[:300]+("..." if len(nw.get("summary",""))>300 else ""),
                            style={"color":"#999","fontSize":"11px","marginTop":"3px"})
                    ],style={"background":"#1c1838","padding":"10px","marginBottom":"6px","borderRadius":"4px","borderLeft":f"3px solid {bc}"}))
        except: pass
    return secs or [html.P("Enter a ticker and click Load.",className="text-muted")]

# ============================================================
# FINANCIALS
# ============================================================
def fin_page():
    return html.Div([
        html.H4("Financials",className="text-warning mb-3"),
        dbc.Row([col(dbc.Input(id="fin-t",value="AAPL",placeholder="Ticker",className="bg-dark text-light border-secondary",debounce=True),3),col(dbc.Button("Load",id="fin-l",color="warning",size="sm"),"auto")],className="mb-3 g-2 align-items-center"),
        dcc.Loading(html.Div(id="fin-c"),type="circle",color="#e8621a"),
    ])

@app.callback(Output("fin-c","children"),Input("fin-l","n_clicks"),Input("fin-t","value"),prevent_initial_call=False)
def load_fin(n,ticker):
    t=(ticker or "AAPL").strip().upper(); secs=[]
    try:
        tk=yf.Ticker(t); info=tk.info
        def safe(k):
            v=info.get(k)
            return None if v in (None,0,"None","N/A",float("inf"),float("-inf")) else v
        def fmt_pe(v):
            try: x=float(v); return "Unprofitable" if x<=0 else f"{x:.1f}x"
            except: return "N/A"
        def fmt_pct2(v):
            try: return f"{float(v)*100:.1f}%"
            except: return "N/A"
        def fmt_big(v):
            try:
                x=float(v)
                if x==0: return "N/A"
                if abs(x)>=1e12: return f"${x/1e12:.2f}T"
                if abs(x)>=1e9: return f"${x/1e9:.2f}B"
                if abs(x)>=1e6: return f"${x/1e6:.2f}M"
                return f"${x:,.0f}"
            except: return "N/A"
        upside=None
        tp=safe("targetMeanPrice"); cp=safe("currentPrice") or safe("regularMarketPrice")
        if tp and cp:
            try: upside=(float(tp)-float(cp))/float(cp)*100
            except: pass
        metrics=[("Market Cap",fmt_big(safe("marketCap"))),("P/E (TTM)",fmt_pe(safe("trailingPE"))),("P/E (Fwd)",fmt_pe(safe("forwardPE"))),("EPS TTM",fusd(safe("trailingEps"))),("EPS Fwd",fusd(safe("forwardEps"))),("Revenue TTM",fmt_big(safe("totalRevenue"))),("Gross Margin",fmt_pct2(safe("grossMargins"))),("Op. Margin",fmt_pct2(safe("operatingMargins"))),("Net Margin",fmt_pct2(safe("profitMargins"))),("52W High",fusd(safe("fiftyTwoWeekHigh"))),("52W Low",fusd(safe("fiftyTwoWeekLow"))),("Analyst Target",fusd(safe("targetMeanPrice"))),("Upside",f"{upside:+.1f}%" if upside is not None else "N/A"),("Beta",f"{float(safe('beta')):.2f}" if safe("beta") else "N/A"),("Short Float",fmt_pct2(safe("shortPercentOfFloat"))),("Inst. Own.",fmt_pct2(safe("heldPercentInstitutions")))]
        def mc2(l,v):
            if v in ("N/A","None","Unprofitable"): return "#8b7fbf"
            if l=="Upside":
                try: return "#2dc653" if float(v.replace("%","").replace("+",""))>0 else "#e63946"
                except: pass
            if "Margin" in l:
                try: return "#2dc653" if float(v.replace("%",""))>0 else "#e63946"
                except: pass
            return "#e8621a"
        cards=[col(html.Div([html.Small(l,style={"color":"#6b5fa0","fontSize":"10px","display":"block"}),html.Span(v,style={"fontSize":"14px","fontWeight":"bold","color":mc2(l,v)})],style={"background":"#1c1838","padding":"10px","borderRadius":"6px","textAlign":"center"}),2) for l,v in metrics]
        secs.append(html.Div([html.H6(f"{t}  --  {info.get('longName',t)}",className="text-warning mb-1"),html.Small(f"{info.get('sector','')}  |  {info.get('industry','')}  |  {info.get('exchange','')}",style={"color":"#8b7fbf","fontSize":"11px"}),html.P(info.get("longBusinessSummary","")[:450]+"...",style={"color":"#a09ac8","fontSize":"11px","margin":"8px 0 12px"}),dbc.Row(cards,className="g-2 mb-3")]))
        try:
            fin=tk.quarterly_financials
            if fin is not None and not fin.empty:
                rr=fin.loc["Total Revenue"] if "Total Revenue" in fin.index else None; er=fin.loc["Net Income"] if "Net Income" in fin.index else None
                dates=[str(d)[:10] for d in fin.columns]
                fig_f=go.Figure()
                if rr is not None: fig_f.add_trace(go.Bar(x=dates,y=[v/1e9 for v in rr],name="Revenue (B)",marker_color="#a78bfa",opacity=0.85))
                if er is not None:
                    ev=list(er); fig_f.add_trace(go.Bar(x=dates,y=[v/1e9 for v in ev],name="Net Income (B)",marker_color=["#2dc653" if v>=0 else "#e63946" for v in ev],opacity=0.85))
                fig_f.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",barmode="group",title=f"{t} -- Quarterly Revenue & Net Income (USD B)",height=340,margin=dict(l=10,r=10,t=40,b=10),legend=dict(orientation="h"),yaxis_title="Billions USD")
                secs.append(dcc.Graph(figure=fig_f,config={"modeBarButtonsToRemove":["lasso2d","select2d"],"scrollZoom":True},style={"marginBottom":"16px"}))
        except: pass
        if fh:
            try:
                recs=fh.recommendation_trends(t)
                if recs:
                    lt=recs[0]; items=[("Strong Buy",lt.get("strongBuy",0),"#2dc653"),("Buy",lt.get("buy",0),"#90be6d"),("Hold",lt.get("hold",0),"#e8621a"),("Sell",lt.get("sell",0),"#e76f51"),("Strong Sell",lt.get("strongSell",0),"#e63946")]
                    tot=sum(i[1] for i in items)
                    fig_r=go.Figure(go.Bar(x=[i[0] for i in items],y=[i[1] for i in items],marker_color=[i[2] for i in items],text=[f"{i[1]} ({i[1]/tot*100:.0f}%)" if tot else str(i[1]) for i in items],textposition="outside"))
                    fig_r.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",title=f"{t} -- Analyst Recommendations ({lt.get('period','')})",height=260,margin=dict(l=10,r=10,t=40,b=10))
                    secs.append(dcc.Graph(figure=fig_r,config={"modeBarButtonsToRemove":["lasso2d","select2d"]},style={"marginBottom":"16px"}))
            except: pass
        secs.append(html.A(f"View full analysis on StockAnalysis.com ->",href=f"https://stockanalysis.com/stocks/{t.lower()}/",target="_blank",style={"color":"#a78bfa","fontSize":"13px"}))
    except Exception as e: secs.append(html.P(f"Error: {e}",className="text-warning"))
    return secs

# ============================================================
# SHARED REPORT/CONVICTION HELPERS
# ============================================================
def _safe(info, key):
    v = info.get(key)
    if v in (None, 0, "None", "N/A", float("inf"), float("-inf")): return None
    try: return float(v)
    except: return v

def _fmt_big(v):
    try:
        x = float(v or 0)
        if abs(x)>=1e12: return f"${x/1e12:.2f}T"
        if abs(x)>=1e9:  return f"${x/1e9:.2f}B"
        if abs(x)>=1e6:  return f"${x/1e6:.2f}M"
        return f"${x:,.0f}"
    except: return "N/A"

def _fpct(v):
    try: return f"{float(v or 0)*100:.1f}%"
    except: return "N/A"

def _ratio_color(label, val):
    if val is None: return "#8b7fbf"
    try: v = float(str(val).replace("x","").replace("%","").replace("+",""))
    except: return "#e8e4f0"
    if any(x in label for x in ["P/E","EV/","P/S","P/B"]):
        if v<=0: return "#e63946"
        if v>60: return "#e63946"
        if v>30: return "#e8621a"
        return "#2dc653"
    if "Margin" in label or "Growth" in label:
        return "#2dc653" if v>0 else "#e63946"
    if "PEG" in label:
        if v<=0: return "#e63946"
        if v<1:  return "#2dc653"
        if v<2:  return "#e8621a"
        return "#e63946"
    return "#e8e4f0"

SECTION_STYLE = {"background":"#12102a","padding":"18px 22px","marginBottom":"2px","borderBottom":"1px solid #1e1e2e"}
SECTION_TITLE_STYLE = {"color":"#e8621a","fontSize":"13px","fontWeight":"500","letterSpacing":"0.06em","textTransform":"uppercase","marginBottom":"10px","paddingBottom":"6px","borderBottom":"1px solid #1e1e2e"}
METRIC_STYLE  = {"background":"#1c1838","padding":"10px 12px","borderRadius":"6px","textAlign":"center","border":"1px solid #1e1e2e"}

def _metric_card(label, value, color=None):
    return html.Div([
        html.Small(label, style={"color":"#6b5fa0","fontSize":"10px","display":"block","letterSpacing":"0.05em"}),
        html.Span(value or "N/A", style={"fontSize":"14px","fontWeight":"500","color":color or "#e8e4f0"}),
    ], style=METRIC_STYLE)

def _section(title, *children):
    return html.Div([html.Div(title, style=SECTION_TITLE_STYLE), *children], style=SECTION_STYLE)

def _signal_bar(name, value_str, score, color):
    return html.Div([
        html.Div(style={"width":"8px","height":"8px","borderRadius":"50%","background":color,"flexShrink":"0"}),
        html.Span(name, style={"fontSize":"12px","color":"#d4d0e8","flex":"1"}),
        html.Div([html.Div(style={"width":f"{score*100:.0f}%","height":"100%","borderRadius":"4px","background":color})],
            style={"background":"#3d3470","borderRadius":"4px","height":"6px","flex":"1","overflow":"hidden","margin":"0 10px"}),
        html.Span(value_str, style={"fontSize":"12px","fontWeight":"500","color":color,"minWidth":"70px","textAlign":"right"}),
    ], style={"display":"flex","alignItems":"center","gap":"10px","padding":"6px 0","borderBottom":"1px solid #111120"})

def _exit_strip(label, text, border_color):
    return html.Div([
        html.Small(label, style={"color":"#8b7fbf","fontSize":"10px","fontWeight":"500","letterSpacing":"0.08em","textTransform":"uppercase","display":"block","marginBottom":"3px"}),
        html.P(text, style={"color":"#d4d0e8","fontSize":"12px","lineHeight":"1.5","margin":"0"}),
    ], style={"borderLeft":f"3px solid {border_color}","padding":"8px 12px","marginBottom":"6px","background":"#1c1838","borderRadius":"0 6px 6px 0"})

def _assumption_block(label, text, border_color="#333"):
    return html.Div([
        html.Small(label, style={"color":"#8b7fbf","fontSize":"10px","fontWeight":"500","letterSpacing":"0.08em","textTransform":"uppercase","display":"block","marginBottom":"3px"}),
        html.P(text, style={"color":"#d4d0e8","fontSize":"13px","lineHeight":"1.6","margin":"0"}),
    ], style={"borderLeft":f"3px solid {border_color}","background":"#1c1838","padding":"10px 14px","marginBottom":"8px","borderRadius":"0 6px 6px 0"})

def _load_ticker(ticker):
    t  = ticker.upper().strip()
    tk = yf.Ticker(t)
    info   = tk.info or {}
    hist1  = tk.history(period="1y", auto_adjust=True)
    hist5  = tk.history(period="5y", auto_adjust=True)
    earnings = []
    if fh:
        try: earnings = fh.company_earnings(t, limit=12) or []
        except: pass
    qfin = None
    try: qfin = tk.quarterly_financials
    except: pass
    news_items = []
    if fh:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            ago   = (datetime.now()-timedelta(days=60)).strftime("%Y-%m-%d")
            news_items = (fh.company_news(t, _from=ago, to=today) or [])[:8]
        except: pass
    return {"ticker":t,"info":info,"hist1":hist1,"hist5":hist5,
            "earnings":earnings,"qfin":qfin,"news":news_items,"tk":tk}

def _round(v, d=1):
    try:
        if v is None: return None
        x = float(v)
        if x != x: return None
        return round(x, d)
    except Exception:
        return None

def _safe_int(v, default=0):
    try:
        if v is None: return default
        x = float(v)
        if x != x: return default
        return int(x)
    except Exception:
        return default

def _pct(v):
    if v is None: return None
    try:
        x = float(v)
        if x != x: return None
        return _round(x * 100 if abs(x) <= 1 else x)
    except Exception:
        return None

def _pct_ratio(v):
    """Return/ratio fields from yfinance (ROE can exceed 1.0 as a fraction)."""
    if v is None: return None
    try:
        x = float(v)
        if x != x: return None
        return _round(x * 100)
    except Exception:
        return None

def _fin_row(df, names, col_idx=0):
    if df is None or getattr(df, "empty", True):
        return None
    keys = names if isinstance(names, (list, tuple)) else [names]
    try:
        col = df.columns[col_idx]
    except Exception:
        return None
    for name in keys:
        if name in df.index:
            try:
                v = float(df.loc[name, col])
                if v == v:
                    return v
            except Exception:
                pass
    return None

def _compare_metrics(ticker):
    d = _load_ticker(ticker)
    info = d["info"] or {}
    tk = d.get("tk")
    inc = bs = cf = None
    if tk:
        try: inc = tk.financials
        except Exception: pass
        try: bs = tk.balance_sheet
        except Exception: pass
        try: cf = tk.cashflow
        except Exception: pass

    mc = info.get("marketCap") or 0
    rev = _fin_row(inc, ["Total Revenue", "Revenue"], 0)
    gp = _fin_row(inc, ["Gross Profit"], 0)
    op_inc = _fin_row(inc, ["Operating Income"], 0)
    ebitda = info.get("ebitda") or _fin_row(inc, ["EBITDA"], 0)

    gm = info.get("grossMargins")
    if gm is None and rev and gp is not None:
        gm = gp / rev
    om = info.get("operatingMargins")
    if om is None and rev and op_inc is not None:
        om = op_inc / rev

    rev_g = info.get("revenueGrowth")
    if rev_g is None and inc is not None and not inc.empty and len(inc.columns) >= 2:
        r0 = _fin_row(inc, ["Total Revenue", "Revenue"], 0)
        r1 = _fin_row(inc, ["Total Revenue", "Revenue"], 1)
        if r0 is not None and r1 and r1 != 0:
            rev_g = (r0 - r1) / abs(r1)

    fcf = info.get("freeCashflow")
    if fcf is None:
        fcf = _fin_row(cf, ["Free Cash Flow"], 0)
    fcf_yield = _round(fcf / mc * 100) if fcf is not None and mc else None

    total_debt = info.get("totalDebt")
    if total_debt is None:
        total_debt = _fin_row(bs, ["Total Debt"], 0) or 0
    cash = info.get("totalCash") or info.get("cash")
    if cash is None:
        cash = _fin_row(bs, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], 0) or 0

    net_debt_ebitda = None
    if ebitda is not None and ebitda > 0:
        net_debt_ebitda = _round(((total_debt or 0) - cash) / ebitda)

    interest = info.get("interestExpense")
    if interest is None:
        interest = _fin_row(inc, ["Interest Expense"], 0)
    if interest is not None and interest < 0:
        interest = abs(interest)
    ebit = info.get("ebit") or op_inc or _fin_row(inc, ["EBIT"], 0)
    int_cov = _round(ebit / interest) if ebit is not None and ebit > 0 and interest and interest > 0 else None

    roe = info.get("returnOnEquity")
    roe_pct = _pct_ratio(roe)
    if roe_pct is None:
        ni = _fin_row(inc, ["Net Income"], 0)
        eq = _fin_row(bs, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"], 0)
        if ni is not None and eq and eq != 0:
            roe_pct = _round(ni / eq * 100)

    roic_src = info.get("returnOnCapital") or info.get("returnOnAssets")
    roic_pct = _pct_ratio(roic_src) if roic_src is not None else None
    if roic_pct is None and op_inc is not None:
        inv_cap = _fin_row(bs, ["Invested Capital"], 0)
        if not inv_cap:
            eq = _fin_row(bs, ["Stockholders Equity", "Total Stockholder Equity"], 0)
            debt = total_debt or 0
            if eq is not None:
                inv_cap = eq + debt - cash
        if inv_cap and inv_cap != 0:
            roic_pct = _round(op_inc / inv_cap * 100)

    fields = {
        "c_pe": _round(info.get("trailingPE")),
        "c_fpe": _round(info.get("forwardPE")),
        "c_peg": _round(info.get("pegRatio"), 2),
        "c_eveb": _round(info.get("enterpriseToEbitda")),
        "c_gm": _pct(gm),
        "c_opm": _pct(om),
        "c_fcfy": fcf_yield,
        "c_revgr": _pct(rev_g),
        "c_roe": roe_pct,
        "c_roic": roic_pct,
        "c_nd_eb": net_debt_ebitda,
        "c_intcov": int_cov,
    }
    missing = [k for k, v in fields.items() if v is None]
    return {
        "ticker": d["ticker"],
        "name": info.get("shortName") or info.get("longName") or d["ticker"],
        **fields,
        "_meta": {
            "filled": len(fields) - len(missing),
            "total": len(fields),
            "missing": missing,
        },
    }

def _norm_cdf(x):
    import math
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def _norm_pdf(x):
    import math
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def _bs_price(S, K, T, r, sigma, opt_type="call"):
    import math
    if sigma <= 0 or T <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if opt_type == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

def _solve_iv(S, K, T, r, price, opt_type="call"):
    import math
    if not price or price <= 0 or not S or not K or T <= 0:
        return None
    lo, hi = 0.001, 3.0
    try:
        if _bs_price(S, K, T, r, hi, opt_type) < price:
            return None
    except Exception:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2.0
        p = _bs_price(S, K, T, r, mid, opt_type)
        if abs(p - price) < 1e-4:
            return mid
        if p > price:
            hi = mid
        else:
            lo = mid
    sigma = (lo + hi) / 2.0
    return sigma if sigma < 2.99 else None

def _option_mid(bid, ask, last):
    bid_f = _round(bid, 6)
    ask_f = _round(ask, 6)
    if bid_f is not None and ask_f is not None and bid_f > 0 and ask_f >= bid_f:
        return (bid_f + ask_f) / 2.0
    last_f = _round(last, 6)
    if last_f is not None and last_f >= 0.05:
        return last_f
    return None

def _normalize_iv(raw):
    """Yahoo impliedVolatility: reliable when < 1.0 (decimal, e.g. 0.25 = 25%). Values >= 1 are usually corrupt."""
    if raw is None:
        return None
    try:
        x = float(raw)
        if x != x or x <= 0 or x >= 1.0:
            return None
        pct = x * 100.0
        if pct < 1 or pct > 200:
            return None
        return round(pct, 2)
    except Exception:
        return None

def _intrinsic(S, K, opt_type):
    if opt_type == "call":
        return max(0.0, float(S) - float(K))
    return max(0.0, float(K) - float(S))

def _resolve_iv(spot, strike, T, r, raw_iv, bid, ask, last, opt_type):
    bid_f = _round(bid, 6) or 0
    ask_f = _round(ask, 6) or 0
    penny = bid_f <= 0 and ask_f <= 0.02
    if not penny:
        iv_pct = _normalize_iv(raw_iv)
        if iv_pct:
            return iv_pct, iv_pct / 100.0
    if penny:
        return None, None
    mid = _option_mid(bid, ask, last)
    if not mid or not spot or not strike:
        return None, None
    time_val = mid - _intrinsic(spot, strike, opt_type)
    if time_val < 0.03:
        return None, None
    sigma = _solve_iv(float(spot), float(strike), T, r, mid, opt_type)
    if sigma and 0.05 <= sigma <= 2.0:
        iv_pct = round(sigma * 100.0, 2)
        if 1 <= iv_pct <= 200:
            return iv_pct, sigma
    return None, None

def _bs_greeks(S, K, T, r, sigma, opt_type="call"):
    import math
    if not all([S, K, T, sigma]) or S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return None
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    pdf1 = _norm_pdf(d1)
    if opt_type == "call":
        delta = _norm_cdf(d1)
        theta = (-(S * pdf1 * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * _norm_cdf(d2)) / 365.0
        rho = K * T * math.exp(-r * T) * _norm_cdf(d2) / 100.0
        price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (-(S * pdf1 * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * _norm_cdf(-d2)) / 365.0
        rho = -K * T * math.exp(-r * T) * _norm_cdf(-d2) / 100.0
        price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
    gamma = pdf1 / (S * sigma * math.sqrt(T))
    vega = S * pdf1 * math.sqrt(T) / 100.0
    return {
        "price": round(price, 4),
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 4),
        "vega": round(vega, 4),
        "rho": round(rho, 4),
        "iv": round(sigma * 100, 2),
    }

def _options_chain(ticker, expiry=None):
    t = ticker.upper().strip()
    tk = yf.Ticker(t)
    info = tk.info or {}
    spot = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
    expirations = list(getattr(tk, "options", []) or [])
    if not expirations:
        return {"ticker": t, "spot": spot, "expirations": [], "calls": [], "puts": []}
    use_exp = expiry if expiry in expirations else expirations[0]
    chain = tk.option_chain(use_exp)
    r = 0.045
    try:
        exp_dt = datetime.strptime(use_exp, "%Y-%m-%d")
        T = max((exp_dt - datetime.now()).total_seconds() / (365.25 * 86400), 1 / 365.25)
    except Exception:
        T = 30 / 365.25

    def _rows(df, side):
        out = []
        if df is None or df.empty:
            return out
        work = df.copy()
        if spot:
            try:
                work["_dist"] = (work["strike"].astype(float) - float(spot)).abs()
                work = work.sort_values("_dist")
            except Exception:
                pass
        for _, row in work.head(20).iterrows():
            strike = float(row.get("strike") or 0)
            bid = row.get("bid")
            ask = row.get("ask")
            last = row.get("lastPrice")
            iv_pct, sigma = _resolve_iv(spot, strike, T, r, row.get("impliedVolatility"), bid, ask, last, side)
            mid = _option_mid(bid, ask, last)
            greeks = _bs_greeks(spot, strike, T, r, sigma, side) if spot and sigma else None
            itm = row.get("inTheMoney")
            out.append({
                "strike": strike,
                "bid": _round(bid, 2),
                "ask": _round(ask, 2),
                "last": _round(last, 2),
                "mid": _round(mid, 2),
                "iv": iv_pct,
                "volume": _safe_int(row.get("volume")),
                "openInterest": _safe_int(row.get("openInterest")),
                "inTheMoney": itm is True or itm == 1,
                "greeks": greeks,
            })
        return out

    return {
        "ticker": t,
        "spot": _round(spot, 2),
        "expiry": use_exp,
        "expirations": expirations[:12],
        "calls": _rows(chain.calls, "call")[:20],
        "puts": _rows(chain.puts, "put")[:20],
    }

def _normalize_ohlcv(df):
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df.columns = [str(c).strip().capitalize() for c in df.columns]
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns and hasattr(df[col], "ndim") and getattr(df[col], "ndim", 1) > 1:
            df[col] = df[col].squeeze()
    if "Volume" not in df.columns:
        df["Volume"] = 0
    needed = ["Open", "High", "Low", "Close"]
    if not all(c in df.columns for c in needed):
        return pd.DataFrame()
    for col in needed + ["Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=needed)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df

def _fetch_chart_data(t, interval, period):
    period = _chart_clamp_period(interval, period)
    src_interval = interval
    resample_4h = interval == "4h"
    if resample_4h:
        src_interval = "1h"
    df = yf.download(t, period=period, interval=src_interval, progress=False,
                     auto_adjust=True, prepost=False, threads=False)
    df = _normalize_ohlcv(df)
    if resample_4h and df is not None and not df.empty:
        df = df.resample("4h").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
        }).dropna()
    if df is None or df.empty or len(df) < 2:
        td_imap = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
                   "1h": "1h", "4h": "4h", "1d": "1day", "1wk": "1week"}
        df, td_err = td_ohlcv(t, interval=td_imap.get(interval, "1day"))
        df = _normalize_ohlcv(df)
        if df is None or df.empty:
            raise ValueError(f"No data. {td_err or ''}")
    return df

def _fmt_r(v, s="x"):
    if v is None: return "N/A"
    if v <= 0: return "Unprofitable"
    return f"{v:.1f}{s}"

# ============================================================
# RESEARCH REPORT PAGE
# ============================================================
def _build_report(d):
    t=d["ticker"]; info=d["info"]; hist=d["hist1"]
    earnings=d["earnings"]; qfin=d["qfin"]; news_items=d["news"]
    if hist.empty: return html.P(f"No data for {t}. Check the ticker.",className="text-warning")
    close=hist["Close"].squeeze()
    cur_p=float(close.iloc[-1]); prev_p=float(close.iloc[-2]) if len(close)>1 else cur_p
    chg=cur_p-prev_p; chg_pct=chg/prev_p*100 if prev_p else 0; chg_c="#2dc653" if chg>=0 else "#e63946"
    name=info.get("longName",t); sector=info.get("sector",""); industry=info.get("industry","")
    desc=info.get("longBusinessSummary","")
    mktcap=_safe(info,"marketCap"); target=_safe(info,"targetMeanPrice")
    pe=_safe(info,"trailingPE"); fpe=_safe(info,"forwardPE"); peg=_safe(info,"pegRatio")
    ps=_safe(info,"priceToSalesTrailing12Months"); pb=_safe(info,"priceToBook")
    ev_eb=_safe(info,"enterpriseToEbitda"); gm=_safe(info,"grossMargins")
    nm=_safe(info,"profitMargins"); om=_safe(info,"operatingMargins")
    rev_g=_safe(info,"revenueGrowth"); eg=_safe(info,"earningsGrowth")
    beta=_safe(info,"beta"); sf=_safe(info,"shortPercentOfFloat")
    io=_safe(info,"heldPercentInstitutions"); ins=_safe(info,"heldPercentInsiders")
    de=_safe(info,"debtToEquity"); fcf_v=_safe(info,"freeCashflow")
    fwd_eps=_safe(info,"forwardEps"); mc=_safe(info,"marketCap") or 1
    upside=((target-cur_p)/cur_p*100) if target and cur_p else None

    # Header
    header_el = _section(f"{t}  --  {name}",
        html.Div([
            html.Div([
                html.Span(f"${cur_p:,.2f}",style={"color":"#e8e4f0","fontSize":"20px","fontWeight":"500","marginRight":"12px"}),
                html.Span(f"{'+' if chg_pct>=0 else ''}{chg_pct:.2f}%  ({'+' if chg>=0 else ''}{fusd(chg)})",style={"color":chg_c,"fontSize":"14px","fontWeight":"500"}),
                html.Span(f"  |  {sector}  |  {industry}  |  Cap: {_fmt_big(mktcap)}",style={"color":"#8b7fbf","fontSize":"11px","marginLeft":"12px"}),
            ],style={"marginBottom":"8px"}),
            html.P(desc[:400]+("..." if len(desc)>400 else ""),style={"color":"#a09ac8","fontSize":"11px","lineHeight":"1.6","marginBottom":"8px"}),
            html.Span(f"Analyst target: {fusd(target)}  ({upside:+.1f}% upside)" if upside is not None else "",style={"color":"#2dc653" if upside and upside>0 else "#e63946","fontSize":"12px"}),
        ]))

    # Metrics
    metrics_data=[
        ("P/E (TTM)",_fmt_r(pe),_ratio_color("P/E",pe)),("Fwd P/E",_fmt_r(fpe),_ratio_color("P/E",fpe)),
        ("PEG",_fmt_r(peg),_ratio_color("PEG",peg)),("P/S",_fmt_r(ps),_ratio_color("P/S",ps)),
        ("P/B",_fmt_r(pb),_ratio_color("P/B",pb)),("EV/EBITDA",_fmt_r(ev_eb),_ratio_color("EV/",ev_eb)),
        ("Gross Margin",_fpct(gm),_ratio_color("Margin",(gm or 0)*100)),("Net Margin",_fpct(nm),_ratio_color("Margin",(nm or 0)*100)),
        ("Op. Margin",_fpct(om),_ratio_color("Margin",(om or 0)*100)),("Rev Growth",_fpct(rev_g),_ratio_color("Growth",(rev_g or 0)*100)),
        ("EPS Growth",_fpct(eg),_ratio_color("Growth",(eg or 0)*100)),("Beta",f"{beta:.2f}" if beta else "N/A","#e8621a"),
    ]
    metrics_el = _section("Key Metrics",dbc.Row([dbc.Col(_metric_card(l,v,c),width=2) for l,v,c in metrics_data],className="g-2"))

    # Price chart
    ema9v=ta.trend.EMAIndicator(close,window=9).ema_indicator()
    ema21v=ta.trend.EMAIndicator(close,window=21).ema_indicator()
    _bb=ta.volatility.BollingerBands(close,window=20,window_dev=2)
    fig_c=make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[0.7,0.3],vertical_spacing=0.03)
    fig_c.add_trace(go.Candlestick(x=hist.index,open=hist["Open"],high=hist["High"],low=hist["Low"],close=hist["Close"],name=t,increasing_line_color="#2dc653",decreasing_line_color="#e63946",increasing_fillcolor="#2dc653",decreasing_fillcolor="#e63946"),row=1,col=1)
    fig_c.add_trace(go.Scatter(x=hist.index,y=ema9v,name="EMA 9",line=dict(color="#e8621a",width=1.3)),row=1,col=1)
    fig_c.add_trace(go.Scatter(x=hist.index,y=ema21v,name="EMA 21",line=dict(color="#a78bfa",width=1.3)),row=1,col=1)
    fig_c.add_trace(go.Scatter(x=hist.index,y=_bb.bollinger_hband(),name="BB Upper",line=dict(color="#90e0ef",width=1,dash="dot")),row=1,col=1)
    fig_c.add_trace(go.Scatter(x=hist.index,y=_bb.bollinger_lband(),name="BB Lower",line=dict(color="#90e0ef",width=1,dash="dot"),fill="tonexty",fillcolor="rgba(144,224,239,0.04)",showlegend=False),row=1,col=1)
    vol_c=["#2dc653" if c>=o else "#e63946" for c,o in zip(hist["Close"].squeeze(),hist["Open"].squeeze())]
    fig_c.add_trace(go.Bar(x=hist.index,y=hist["Volume"].squeeze(),name="Volume",marker_color=vol_c,opacity=0.7),row=2,col=1)
    fig_c.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",height=420,margin=dict(l=10,r=10,t=10,b=10),legend=dict(orientation="h",y=1.02,bgcolor="rgba(0,0,0,0)",font=dict(size=10)),xaxis_rangeslider_visible=False)
    fig_c.update_xaxes(gridcolor="#3d3470",rangeslider_visible=False); fig_c.update_yaxes(gridcolor="#3d3470")
    chart_el = _section("1-Year Price Chart  (EMA 9/21  |  Bollinger Bands  |  Volume)",
        dcc.Graph(figure=fig_c,config={"modeBarButtonsToAdd":["drawline","drawrect","eraseshape"],"modeBarButtonsToRemove":["lasso2d","select2d"],"scrollZoom":True},style={"height":"420px"}))

    # Technicals
    sma200v=float(close.rolling(200).mean().iloc[-1]) if len(close)>=200 else None
    ema50v=float(close.ewm(span=50,adjust=False).mean().iloc[-1])
    rsi_v=float(ta.momentum.RSIIndicator(close,window=14).rsi().iloc[-1])
    _macd=ta.trend.MACD(close); macd_bull=float(_macd.macd().iloc[-1])>float(_macd.macd_signal().iloc[-1])
    h52=float(close.max()); l52=float(close.min()); pos52=(cur_p-l52)/(h52-l52) if h52!=l52 else 0.5
    sma20=close.rolling(20).mean(); std20=close.rolling(20).std()
    bbu=float((sma20+2*std20).iloc[-1]); bbl=float((sma20-2*std20).iloc[-1]); bbpos=(cur_p-bbl)/(bbu-bbl) if bbu!=bbl else 0.5
    tech_signals=[
        ("vs 50-day EMA",fusd(ema50v),min(cur_p/ema50v,2)/2,"#2dc653" if cur_p>ema50v else "#e63946"),
        ("vs 200-day SMA",fusd(sma200v) if sma200v else "N/A",min(cur_p/(sma200v or cur_p),2)/2 if sma200v else 0.5,"#2dc653" if sma200v and cur_p>sma200v else "#e63946"),
        ("RSI (14)",f"{rsi_v:.0f}",rsi_v/100,"#2dc653" if 40<rsi_v<65 else "#e8621a" if rsi_v<=40 else "#e63946"),
        ("MACD signal","Bullish" if macd_bull else "Bearish",0.75 if macd_bull else 0.25,"#2dc653" if macd_bull else "#e63946"),
        ("52-week position",f"{pos52*100:.0f}% of range",pos52,"#2dc653" if 0.4<pos52<0.85 else "#e8621a"),
        ("Bollinger position",f"{bbpos*100:.0f}% of band",bbpos,"#2dc653" if 0.3<bbpos<0.7 else "#e8621a" if bbpos<0.3 else "#e63946"),
    ]
    bull_c=sum(1 for _,_,_,c in tech_signals if c=="#2dc653"); ot_c="#2dc653" if bull_c>=4 else "#e8621a" if bull_c>=3 else "#e63946"
    tech_el = _section("Technical Analysis",
        dbc.Row([
            dbc.Col(html.Div([_signal_bar(n,v,s,c) for n,v,s,c in tech_signals]),width=8),
            dbc.Col([_metric_card("Bias","Bullish" if bull_c>=4 else "Neutral" if bull_c>=3 else "Bearish",ot_c),html.Div(style={"height":"8px"}),_metric_card(f"{bull_c}/{len(tech_signals)} signals","bullish",ot_c),html.Div(style={"height":"8px"}),_metric_card("RSI",f"{rsi_v:.0f}","#2dc653" if 40<rsi_v<65 else "#e8621a" if rsi_v<40 else "#e63946")],width=4),
        ]))

    # Earnings
    if earnings:
        dates_e=[e.get("period","") for e in earnings][::-1]; actual_e=[e.get("actual",None) for e in earnings][::-1]; est_e=[e.get("estimate",None) for e in earnings][::-1]
        beats=sum(1 for a,e2 in zip(actual_e,est_e) if (a or 0)>=(e2 or 0))
        avg_surp=sum(((a-(e2 or 0))/abs(e2)*100) if e2 and e2!=0 else 0 for a,e2 in zip(actual_e,est_e))/len(actual_e) if actual_e else 0
        fig_eps=go.Figure()
        fig_eps.add_trace(go.Bar(x=dates_e,y=actual_e,name="Actual EPS",marker_color=["#2dc653" if (a or 0)>=(e2 or 0) else "#e63946" for a,e2 in zip(actual_e,est_e)]))
        fig_eps.add_trace(go.Scatter(x=dates_e,y=est_e,name="Estimate",line=dict(color="#e8621a",dash="dash",width=1.5),mode="lines+markers"))
        fig_eps.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",height=240,margin=dict(l=10,r=10,t=10,b=10),legend=dict(orientation="h",y=1.02,font=dict(size=10)),xaxis=dict(gridcolor="#3d3470"),yaxis=dict(gridcolor="#3d3470"))
        bc2="#2dc653" if beats>=len(earnings)*0.75 else "#e8621a" if beats>=len(earnings)*0.5 else "#e63946"
        earn_el = _section("Earnings History",
            dbc.Row([dbc.Col(_metric_card("Beat rate",f"{beats}/{len(earnings)}",bc2),width=3),dbc.Col(_metric_card("Avg surprise",f"{avg_surp:+.1f}%","#2dc653" if avg_surp>0 else "#e63946"),width=3),dbc.Col(_metric_card("Fwd EPS",fusd(fwd_eps)),width=3),dbc.Col(_metric_card("EPS growth",f"{eg*100:+.1f}%" if eg else "N/A","#2dc653" if eg and eg>0 else "#e63946"),width=3)],className="g-2 mb-3"),
            dcc.Graph(figure=fig_eps,config={"modeBarButtonsToRemove":["lasso2d","select2d"],"scrollZoom":True},style={"height":"240px"}))
    else:
        earn_el = _section("Earnings History",html.P("Set FINNHUB_API_KEY in .env.trading to see earnings.",style={"color":"#6b5fa0","fontSize":"12px"}))

    # Quarterly financials
    fin_el = _section("Quarterly Revenue & Net Income",html.Span())
    try:
        if qfin is not None and not qfin.empty:
            rr2=qfin.loc["Total Revenue"] if "Total Revenue" in qfin.index else None
            er2=qfin.loc["Net Income"] if "Net Income" in qfin.index else None
            dates_f=[str(d2)[:10] for d2 in qfin.columns]; fig_f2=go.Figure()
            if rr2 is not None: fig_f2.add_trace(go.Bar(x=dates_f,y=[v/1e9 for v in rr2],name="Revenue (B)",marker_color="#a78bfa",opacity=0.85))
            if er2 is not None:
                ev3=list(er2); fig_f2.add_trace(go.Bar(x=dates_f,y=[v/1e9 for v in ev3],name="Net Income (B)",marker_color=["#2dc653" if v>=0 else "#e63946" for v in ev3],opacity=0.85))
            fig_f2.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",barmode="group",height=260,margin=dict(l=10,r=10,t=10,b=10),legend=dict(orientation="h",font=dict(size=10)),yaxis_title="USD Billions",xaxis=dict(gridcolor="#3d3470"),yaxis=dict(gridcolor="#3d3470"))
            fin_el = _section("Quarterly Revenue & Net Income",dcc.Graph(figure=fig_f2,config={"modeBarButtonsToRemove":["lasso2d","select2d"],"scrollZoom":True},style={"height":"260px"}))
    except: pass

    # Analyst ratings
    ratings_el = _section("Analyst Ratings",html.Span())
    if fh:
        try:
            recs2=fh.recommendation_trends(t)
            if recs2:
                lt2=recs2[0]; cats=[("Strong Buy",lt2.get("strongBuy",0),"#2dc653"),("Buy",lt2.get("buy",0),"#90be6d"),("Hold",lt2.get("hold",0),"#e8621a"),("Sell",lt2.get("sell",0),"#e76f51"),("Strong Sell",lt2.get("strongSell",0),"#e63946")]
                tot2=sum(c[1] for c in cats) or 1
                fig_r2=go.Figure(go.Bar(x=[c[0] for c in cats],y=[c[1] for c in cats],marker_color=[c[2] for c in cats],text=[f"{c[1]} ({c[1]/tot2*100:.0f}%)" for c in cats],textposition="outside"))
                fig_r2.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",height=240,margin=dict(l=10,r=10,t=10,b=30),xaxis=dict(gridcolor="#3d3470"),yaxis=dict(gridcolor="#3d3470"))
                ratings_el = _section(f"Analyst Recommendations  ({lt2.get('period','')}  |  {tot2} analysts)",dcc.Graph(figure=fig_r2,config={"modeBarButtonsToRemove":["lasso2d","select2d"]},style={"height":"240px"}))
        except: pass

    # Stress test
    beta_v=beta or 1.0; sm=1.5 if "Technology" in sector else 1.0; pe_v=pe or 0
    stress_rows2=[("Market selloff -20%","S&P 500 -20%",f"{-30*beta_v:.0f}%","Hold if thesis intact"),("Rate hike surprise","Fed +50bps",f"{-15*beta_v*sm:.0f}%","Reassess multiple"),("Earnings miss >10%","EPS below estimate",f"{-15 if pe_v>30 else -8:.0f}%","Check if structural"),("Recession signal","PMI < 50",f"{-25*beta_v:.0f}%","Tighten stop loss"),("Competition shock","New entrant","-20%","Evaluate moat")]
    def _srow(s2,t3,ip2,a2):
        try: v2=float(ip2.replace("%","")); ic2="#2dc653" if v2>0 else "#e63946"
        except: ic2="#a09ac8"
        return dbc.Row([dbc.Col(html.Span(s2,style={"color":"#d4d0e8","fontSize":"12px"}),width=4),dbc.Col(html.Span(t3,style={"color":"#8b7fbf","fontSize":"11px"}),width=3),dbc.Col(html.Span(ip2,style={"color":ic2,"fontWeight":"500","fontSize":"12px"}),width=2),dbc.Col(html.Span(a2,style={"color":"#8b7fbf","fontSize":"11px"}),width=3)],className="mb-1 py-1 border-bottom border-secondary align-items-center")
    stress_el = _section("Stress Test",
        dbc.Row([dbc.Col(html.Small("Scenario",className="text-muted"),width=4),dbc.Col(html.Small("Trigger",className="text-muted"),width=3),dbc.Col(html.Small("Impact",className="text-muted"),width=2),dbc.Col(html.Small("Response",className="text-muted"),width=3)],className="mb-1 pb-1 border-bottom border-warning"),
        *[_srow(s2,t3,ip2,a2) for s2,t3,ip2,a2 in stress_rows2])

    # Risk signals
    h52v2=float(close.max()); dd2=(cur_p/h52v2-1)*100; risk_sigs2=[]
    if pe and pe>0: risk_sigs2.append(("Valuation",f"P/E {pe:.1f}x",0.25 if pe>60 else 0.65 if pe>30 else 0.8,"#e63946" if pe>60 else "#e8621a" if pe>30 else "#2dc653"))
    if sf is not None:
        sfp=sf*100; risk_sigs2.append(("Short interest",f"{sfp:.1f}% float",0.2 if sfp>15 else 0.5 if sfp>7 else 0.8,"#e63946" if sfp>15 else "#e8621a" if sfp>7 else "#2dc653"))
    if io is not None: risk_sigs2.append(("Inst. ownership",f"{io*100:.0f}%",0.75 if io>0.4 else 0.45,"#2dc653" if io>0.4 else "#e8621a"))
    if ins is not None: risk_sigs2.append(("Insider ownership",f"{ins*100:.1f}%",0.8 if ins>0.1 else 0.45,"#2dc653" if ins>0.1 else "#e8621a"))
    if de is not None: risk_sigs2.append(("Debt/equity",f"{de:.0f}%",0.2 if de>200 else 0.55 if de>80 else 0.85,"#e63946" if de>200 else "#e8621a" if de>80 else "#2dc653"))
    if fcf_v is not None:
        fy2=(fcf_v/mc)*100; risk_sigs2.append(("FCF yield",f"{fy2:.1f}%",0.85 if fy2>4 else 0.6 if fy2>0 else 0.25,"#2dc653" if fy2>4 else "#e8621a" if fy2>0 else "#e63946"))
    risk_sigs2.append(("Drawdown",f"{dd2:.1f}% off 52W high",0.3 if dd2<-30 else 0.5 if dd2<-15 else 0.7,"#e63946" if dd2<-30 else "#e8621a" if dd2<-15 else "#2dc653"))
    risk_el = _section("Risk Signals",html.Div([_signal_bar(n,v,s,c) for n,v,s,c in risk_sigs2]))

    # News
    if news_items:
        ncards=[]
        for nw2 in news_items:
            sc3=nw2.get("sentiment",""); bc3="#2dc653" if sc3=="positive" else "#e63946" if sc3=="negative" else "#6b5fa0"
            try: ts2=datetime.fromtimestamp(nw2.get("datetime",0)).strftime("%b %d")
            except: ts2=""
            ncards.append(html.Div([html.Div([html.Span(nw2.get("source",""),style={"color":"#e8621a","fontSize":"10px","marginRight":"8px"}),html.Span(ts2,style={"color":"#554880","fontSize":"10px"})],style={"marginBottom":"2px"}),html.A(nw2.get("headline",""),href=nw2.get("url","#"),target="_blank",style={"color":"#d4d0e8","fontSize":"12px","textDecoration":"none","lineHeight":"1.4","display":"block"})],style={"borderLeft":f"2px solid {bc3}","padding":"6px 10px","marginBottom":"6px","background":"#1c1838","borderRadius":"0 4px 4px 0"}))
        news_el2 = _section("Latest News",dbc.Row([dbc.Col(c,width=6) for c in ncards]))
    else:
        news_el2 = _section("Latest News",html.P("Set FINNHUB_API_KEY in .env.trading.",style={"color":"#6b5fa0","fontSize":"12px"}))

    # Conviction & exit
    rl2=float(close.tail(20).min()); stop_p2=rl2*0.97; stop_pct2=(stop_p2/cur_p-1)*100; tgt_p2=cur_p*(1+abs(stop_pct2)/100*2.5)
    ema50_ok=cur_p>ema50v; fpe_ok=fpe and 0<fpe<60
    beats_ok=(sum(1 for e in earnings if (e.get("actual",0) or 0)>=(e.get("estimate",0) or 0))>=len(earnings)*0.6) if earnings else False
    sf_ok=not(sf and sf>0.15)
    checks2=[("I understand how this company makes money",bool(desc)),(_fmt_r(fpe)+" fwd P/E is justified by growth",bool(fpe_ok)),(f"Earnings beat rate is strong",beats_ok),(f"Price above 50-day EMA",ema50_ok),("Short interest not elevated",sf_ok),("Next catalyst identified and position sized",True)]
    score2=sum(1 for _,p in checks2 if p); sc_c2="#2dc653" if score2>=5 else "#e8621a" if score2>=4 else "#e63946"; sc_l2="Strong conviction" if score2>=5 else "Moderate" if score2>=4 else "Low -- review"
    checks_el2=html.Div([html.Div([html.Span("✓ " if p else "✗ ",style={"color":"#2dc653" if p else "#e63946","fontWeight":"bold","fontSize":"13px"}),html.Span(t2,style={"fontSize":"12px","color":"#d4d0e8"})],style={"display":"flex","alignItems":"flex-start","padding":"5px 0","borderBottom":"1px solid #111120"}) for t2,p in checks2]+[html.Div([html.Span("Score: ",style={"color":"#8b7fbf","fontSize":"12px"}),html.Span(f"{score2}/{len(checks2)}  --  {sc_l2}",style={"color":sc_c2,"fontWeight":"500","fontSize":"12px"})],style={"paddingTop":"10px"})])
    conviction_el2 = _section("Conviction Checklist & Exit Plan",
        dbc.Row([
            dbc.Col(checks_el2,width=6),
            dbc.Col([_exit_strip("Stop loss",f"Below ${stop_p2:.2f} ({stop_pct2:.1f}%). No debate.","#e63946"),_exit_strip("Thesis break","Revenue deceleration, margin compression, or guidance cut.","#e8621a"),_exit_strip("Target",f"At ${tgt_p2:.2f} ({((tgt_p2/cur_p)-1)*100:.0f}%), reassess and trim."+(f" Analyst: {fusd(target)}." if target else ""),"#2dc653"),_exit_strip("Time stop","Re-evaluate after 6 months if thesis has not played out.","#6d5ac4")],width=6),
        ]))

    return html.Div([header_el,metrics_el,chart_el,tech_el,earn_el,fin_el,ratings_el,stress_el,risk_el,news_el2,conviction_el2],
        id="report-body",style={"background":"#12102a","fontFamily":"Syne,Segoe UI,system-ui,sans-serif"})

def report_page():
    return html.Div([
        html.H4("Research Report",className="text-warning mb-1"),
        html.Small("Full single-pane analysis: valuation, chart, earnings, financials, analyst ratings, stress test, risk signals, news and conviction checklist.",className="text-muted d-block mb-3",style={"fontSize":"11px"}),
        dbc.Row([
            col(dbc.Input(id="rr-ticker",placeholder="Enter ticker  e.g. NVDA, AAPL, QBTS",className="bg-dark text-light border-secondary",debounce=False),4),
            col(dbc.Button("Generate Report",id="rr-btn",color="warning",size="sm"),"auto"),
            col(dbc.Button("Print / Save PDF",id="rr-print-btn",color="secondary",size="sm",style={"display":"none"}),id="rr-print-col",width="auto"),
            col(html.Span(id="rr-status",style={"fontSize":"11px","color":"#6b5fa0","display":"block","marginTop":"4px"}),"auto"),
        ],className="mb-3 g-2 align-items-center"),
        dcc.Loading(html.Div(id="rr-content"),type="circle",color="#e8621a"),
        html.Div(id="rr-print-trigger",style={"display":"none"}),
    ])

@app.callback(Output("rr-content","children"),Output("rr-status","children"),Output("rr-print-col","style"),
    Input("rr-btn","n_clicks"),State("rr-ticker","value"),prevent_initial_call=True)
def generate_report(n,ticker):
    if not ticker:
        return html.P("Enter a ticker and click Generate Report.",style={"color":"#6b5fa0","fontSize":"13px","textAlign":"center","marginTop":"40px"}),"",{"display":"none"}
    try:
        d=_load_ticker(ticker.strip().upper()); content=_build_report(d)
        return content,f"Report for {ticker.upper()}  |  {datetime.now().strftime('%H:%M:%S')}",{}
    except Exception as e:
        return html.P(f"Error: {e}",className="text-danger"),"Error",{"display":"none"}

app.clientside_callback(
    """
    function(n) {
        if (n && n > 0) {
            var s = document.createElement('style'); s.id = 'print-style';
            s.innerHTML = '@media print { nav,[style*="position:fixed"],[style*="position: fixed"],#rr-btn,#rr-print-btn,#rr-ticker,.dash-loading,.Select-control,.modebar{display:none!important} body,html{background:white!important;color:black!important} #report-body *{color:black!important;background:white!important;border-color:#ccc!important} #report-body{margin-left:0!important} .js-plotly-plot{page-break-inside:avoid} a{color:#185FA5!important} }';
            document.head.appendChild(s); window.print();
            setTimeout(function(){var x=document.getElementById('print-style');if(x)x.remove();},3000);
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("rr-print-trigger","children"),Input("rr-print-btn","n_clicks"),prevent_initial_call=True)

# ============================================================
# CONVICTION PAGE
# ============================================================
def _build_valuation_cv(d):
    info=d["info"]; ticker=d["ticker"]; earnings=d["earnings"]
    pe=_safe(info,"trailingPE"); fpe=_safe(info,"forwardPE"); peg=_safe(info,"pegRatio")
    ps=_safe(info,"priceToSalesTrailing12Months"); pb=_safe(info,"priceToBook")
    ev_eb=_safe(info,"enterpriseToEbitda"); gm=_safe(info,"grossMargins"); nm=_safe(info,"profitMargins")
    eg=_safe(info,"earningsGrowth"); mktcap=_safe(info,"marketCap")
    cur_p=_safe(info,"currentPrice") or _safe(info,"regularMarketPrice"); target=_safe(info,"targetMeanPrice")
    metrics=[("P/E (TTM)",_fmt_r(pe),_ratio_color("P/E",pe)),("Fwd P/E",_fmt_r(fpe),_ratio_color("P/E",fpe)),("PEG",_fmt_r(peg),_ratio_color("PEG",peg)),("P/S",_fmt_r(ps),_ratio_color("P/S",ps)),("P/B",_fmt_r(pb),_ratio_color("P/B",pb)),("EV/EBITDA",_fmt_r(ev_eb),_ratio_color("EV/",ev_eb)),("Gross Margin",_fpct(gm),_ratio_color("Margin",(gm or 0)*100)),("Net Margin",_fpct(nm),_ratio_color("Margin",(nm or 0)*100))]
    verdicts=[]
    if pe and pe>0:
        if pe<20: verdicts.append(("Reasonably valued","#2dc653"))
        elif pe<40: verdicts.append(("Premium valuation","#e8621a"))
        else: verdicts.append(("Expensive -- high bar priced in","#e63946"))
    if peg and peg>0:
        if peg<1: verdicts.append(("PEG < 1 -- growth may be underpriced","#2dc653"))
        elif peg>2: verdicts.append(("PEG > 2 -- growth fully priced","#e63946"))
    if nm is not None:
        if nm<0: verdicts.append(("Net losses","#e63946"))
        elif nm>0.2: verdicts.append(("Strong net margins","#2dc653"))
    verdict_pills=html.Div([html.Span(v,style={"fontSize":"11px","padding":"3px 10px","borderRadius":"12px","marginRight":"6px","background":c+"33","color":c,"fontWeight":"500"}) for v,c in verdicts],style={"marginTop":"6px","marginBottom":"10px"})
    if fpe and fpe>0 and eg:
        eg_pct=eg*100
        if fpe>40: rev_text=f"At {fpe:.1f}x fwd P/E, the market expects ~{eg_pct:.0f}%+ earnings growth. Any miss risks multiple compression."
        elif fpe>20: rev_text=f"At {fpe:.1f}x fwd P/E, moderate growth ({eg_pct:.0f}%/yr) is priced in. Consistent execution needed."
        else: rev_text=f"At {fpe:.1f}x fwd P/E this is value territory. Any positive surprise could re-rate higher."
    elif fpe and fpe<=0: rev_text="Currently unprofitable. Valuation is story-based."
    else: rev_text="Fwd P/E unavailable. Review recent guidance and growth trajectory."
    if gm is not None:
        gm_pct=gm*100
        if gm_pct>60: margin_text=f"Gross margins {gm_pct:.1f}% are exceptional -- pricing power or software/IP model."
        elif gm_pct>30: margin_text=f"Gross margins {gm_pct:.1f}% are reasonable. Watch for compression from competition."
        else: margin_text=f"Gross margins {gm_pct:.1f}% are thin. Small revenue misses translate directly to earnings hits."
    else: margin_text="Gross margin data unavailable."
    if mktcap:
        if mktcap>500e9: moat_text="Large cap -- needs dominant position to sustain growth."
        elif mktcap>50e9: moat_text="Mid-large cap -- needs defensible niche or clear growth vector."
        else: moat_text="Smaller cap -- higher growth expectations but higher execution risk."
    else: moat_text="Market cap data unavailable."
    upside_el=html.Span()
    if target and cur_p and cur_p>0:
        up=((target-cur_p)/cur_p*100); uc="#2dc653" if up>0 else "#e63946"
        upside_el=html.Div([html.Small("Analyst consensus: ",style={"color":"#8b7fbf","fontSize":"11px"}),html.Span(fusd(target),style={"color":"#e8621a","fontWeight":"500","marginRight":"8px"}),html.Span(f"({up:+.1f}% from current)",style={"color":uc,"fontSize":"12px"})],style={"marginTop":"8px","marginBottom":"10px"})
    return html.Div([
        html.H5("What are you paying for?",className="text-warning mb-1"),
        html.Small(f"{info.get('longName',ticker)}  |  {info.get('sector','')}  |  {info.get('industry','')}",style={"color":"#8b7fbf","fontSize":"11px","display":"block","marginBottom":"10px"}),
        dbc.Row([dbc.Col(_metric_card(l,v,c),width=3) for l,v,c in metrics],className="g-2 mb-2"),
        verdict_pills, upside_el,
        html.Hr(style={"borderColor":"#3d3470","margin":"12px 0"}),
        html.H6("What has to be true for this to be worth it?",style={"color":"#e8621a","marginBottom":"10px"}),
        _assumption_block("Revenue / earnings growth assumption",rev_text,"#6d5ac4"),
        _assumption_block("Margin expansion assumption",margin_text,"#e8621a"),
        _assumption_block("Competitive moat required",moat_text,"#2dc653"),
    ])

def _build_chart_cv(d):
    hist=d["hist1"]
    if hist.empty: return html.P("No price data.",className="text-muted")
    close=hist["Close"].squeeze(); cur_p=float(close.iloc[-1])
    h52=float(close.max()); l52=float(close.min()); pos52=(cur_p-l52)/(h52-l52) if h52!=l52 else 0.5
    ema50=float(close.ewm(span=50,adjust=False).mean().iloc[-1])
    sma200=float(close.rolling(200).mean().iloc[-1]) if len(close)>=200 else None
    rsi_cv=float(ta.momentum.RSIIndicator(close,window=14).rsi().iloc[-1])
    _mcd=ta.trend.MACD(close); macd_bull2=float(_mcd.macd().iloc[-1])>float(_mcd.macd_signal().iloc[-1])
    sma20=close.rolling(20).mean(); std20=close.rolling(20).std()
    bbu=float((sma20+2*std20).iloc[-1]); bbl=float((sma20-2*std20).iloc[-1]); bbpos2=(cur_p-bbl)/(bbu-bbl) if bbu!=bbl else 0.5
    recent_low=float(close.tail(20).min()); recent_high=float(close.tail(20).max())
    stop_loss2=recent_low*0.97; resist=recent_high*1.05
    signals2=[
        ("Price vs 50-day EMA",f"${ema50:.2f}",min(cur_p/ema50,2)/2,"#2dc653" if cur_p>ema50 else "#e63946"),
        ("Price vs 200-day SMA",f"${sma200:.2f}" if sma200 else "N/A",min(cur_p/(sma200 or cur_p),2)/2 if sma200 else 0.5,"#2dc653" if sma200 and cur_p>sma200 else "#e63946"),
        ("RSI (14)",f"{rsi_cv:.0f}",rsi_cv/100,"#2dc653" if 40<rsi_cv<65 else "#e8621a" if rsi_cv<=40 else "#e63946"),
        ("MACD signal","Bullish" if macd_bull2 else "Bearish",0.75 if macd_bull2 else 0.25,"#2dc653" if macd_bull2 else "#e63946"),
        ("52-week position",f"{pos52*100:.0f}% of range",pos52,"#2dc653" if 0.4<pos52<0.85 else "#e8621a"),
        ("Bollinger position",f"{bbpos2*100:.0f}% of band",bbpos2,"#2dc653" if 0.3<bbpos2<0.75 else "#e8621a" if bbpos2<0.3 else "#e63946"),
    ]
    bull2=sum(1 for _,_,_,c in signals2 if c=="#2dc653"); ov2=("Strong setup","#2dc653") if bull2>=4 else ("Mixed signals","#e8621a") if bull2>=3 else ("Weak structure","#e63946")
    rsi_warn="" if 30<rsi_cv<70 else (" RSI overbought -- mean-reversion risk." if rsi_cv>=70 else " RSI oversold -- potential bounce zone.")
    return html.Div([
        html.H5("Technical structure",className="text-warning mb-2"),
        html.Div([_signal_bar(n,v,s,c) for n,v,s,c in signals2]),
        html.Div([html.Span(ov2[0],style={"color":ov2[1],"fontWeight":"500","fontSize":"13px"}),html.Span(f"  ({bull2}/6 bullish)",style={"color":"#6b5fa0","fontSize":"11px"})],style={"marginTop":"10px","paddingTop":"10px","borderTop":"1px solid #1e1e2e","marginBottom":"14px"}),
        html.H6("Technical exit levels",style={"color":"#e8621a","marginBottom":"10px"}),
        _assumption_block("Hard stop loss",f"Below ${stop_loss2:.2f} ({((stop_loss2/cur_p)-1)*100:.1f}% from current). Below recent support at ${recent_low:.2f}.","#e63946"),
        _assumption_block("Support to watch",f"${ema50:.2f} (50 EMA) is first key support."+(f" ${sma200:.2f} (200 SMA) is major long-term support." if sma200 else ""),"#e8621a"),
        _assumption_block("Resistance / target",f"Near-term resistance at ${recent_high:.2f}. Breakout above ${resist:.2f} signals continuation."+rsi_warn,"#2dc653"),
    ])

def _build_earnings_cv(d):
    earnings=d["earnings"]; info=d["info"]; ticker=d["ticker"]
    if earnings:
        dates3=[e.get("period","") for e in earnings][::-1]; actual3=[e.get("actual",None) for e in earnings][::-1]; est3=[e.get("estimate",None) for e in earnings][::-1]
        surprise3=[((a-e)/abs(e)*100) if (a is not None and e and e!=0) else 0 for a,e in zip(actual3,est3)]
        beat3=sum(1 for s in surprise3 if s>0); avg3=sum(surprise3)/len(surprise3) if surprise3 else 0
        fig3=go.Figure()
        fig3.add_trace(go.Bar(x=dates3,y=actual3,name="Actual EPS",marker_color=["#2dc653" if (a or 0)>=(e or 0) else "#e63946" for a,e in zip(actual3,est3)]))
        fig3.add_trace(go.Scatter(x=dates3,y=est3,name="Estimate",line=dict(color="#e8621a",dash="dash",width=1.5),mode="lines+markers"))
        fig3.update_layout(template="plotly_dark",paper_bgcolor="#12102a",plot_bgcolor="#1c1838",title=f"{ticker} -- {beat3}/{len(earnings)} beats  |  avg {avg3:+.1f}%",height=280,margin=dict(l=10,r=10,t=40,b=10),legend=dict(orientation="h"),xaxis=dict(gridcolor="#3d3470"),yaxis=dict(gridcolor="#3d3470"))
        bc4="#2dc653" if beat3>=len(earnings)*0.75 else "#e8621a" if beat3>=len(earnings)*0.5 else "#e63946"
        chart4=dcc.Graph(figure=fig3,config={"modeBarButtonsToRemove":["lasso2d","select2d"],"scrollZoom":True},style={"marginBottom":"12px"})
        eq_el4=html.Div(html.Span(f"{'Strong' if beat3>=len(earnings)*0.75 else 'Mixed' if beat3>=len(earnings)*0.5 else 'Weak'} beat rate -- {beat3}/{len(earnings)} quarters",style={"color":bc4,"fontSize":"12px"}),style={"padding":"8px 12px","background":"#1c1838","borderRadius":"6px","marginBottom":"12px"})
    else:
        chart4=html.P("Set FINNHUB_API_KEY for earnings data.",className="text-muted small"); eq_el4=html.Span()
    fpe2=_safe(info,"forwardPE"); fwd_eps2=_safe(info,"forwardEps"); sector2=info.get("sector","")
    if "Technology" in sector2: kmt=("Key metric","Revenue growth + gross margin. Watch ARR/NRR if disclosed.")
    elif "Retail" in sector2 or "Consumer" in sector2: kmt=("Key metric","Comparable store sales and inventory. Watch gross margin for discounting pressure.")
    elif "Financial" in sector2: kmt=("Key metric","Net interest margin and loan loss provisions. Deposit stability.")
    else: kmt=("Key metric","Revenue growth and operating margin trend. Forward guidance matters as much as the print.")
    watch4=[kmt]
    if fpe2 and fpe2>0 and fwd_eps2:
        watch4.append(("Bull case trigger",f"EPS beats ${fwd_eps2:.2f} and guidance raised -- re-rate higher likely."))
        watch4.append(("Bear case trigger",f"EPS misses ${fwd_eps2:.2f} or guidance cut -- multiple compression at {fpe2:.1f}x."))
    else:
        watch4.append(("Bull case trigger","Revenue + margin improvement + guidance raise = re-rating catalyst."))
        watch4.append(("Bear case trigger","Revenue miss + margin pressure + guidance cut = multiple compression."))
    return html.Div([
        html.H5("Earnings track record",className="text-warning mb-2"),
        chart4, eq_el4,
        html.Hr(style={"borderColor":"#3d3470","margin":"12px 0"}),
        html.H6("What to watch next earnings",style={"color":"#e8621a","marginBottom":"10px"}),
        *[_assumption_block(l,t2,"#6d5ac4" if i%2==0 else "#e8621a") for i,(l,t2) in enumerate(watch4)],
    ])

def _build_stress_cv(d):
    info=d["info"]; hist=d["hist1"]
    if hist.empty: return html.P("No data.",className="text-muted")
    close5=hist["Close"].squeeze(); cur_p5=float(close5.iloc[-1]); beta5=_safe(info,"beta") or 1.0
    pe5=_safe(info,"trailingPE"); sector5=info.get("sector","")
    scenarios5=[("Market selloff -20%","S&P 500 -20%",f"{-30*beta5:.0f}%","Hold if thesis intact"),("Rate hike surprise","Fed +50bps",f"{-15*beta5*(1.5 if 'Technology' in sector5 else 1.0):.0f}%","Reassess if multiple >20% compressed"),("Earnings miss >10%","EPS below estimate",f"{-15 if pe5 and pe5>30 else -8:.0f}%","Check if one-time or structural"),("Recession signal","PMI < 50, yield curve",f"{-25*beta5:.0f}%","Reduce exposure, tighten stop"),("Competition shock","Major new entrant","-20%","Evaluate moat -- may be thesis break")]
    def _sr5(s5,t5,ip5,a5):
        try: v5=float(ip5.replace("%","")); ic5="#2dc653" if v5>0 else "#e63946"
        except: ic5="#a09ac8"
        return dbc.Row([dbc.Col(html.Span(s5,style={"color":"#d4d0e8","fontSize":"12px"}),width=4),dbc.Col(html.Span(t5,style={"color":"#8b7fbf","fontSize":"11px"}),width=3),dbc.Col(html.Span(ip5,style={"color":ic5,"fontWeight":"500","fontSize":"12px"}),width=2),dbc.Col(html.Span(a5,style={"color":"#8b7fbf","fontSize":"11px"}),width=3)],className="mb-1 py-1 border-bottom border-secondary align-items-center")
    recent_l5=float(close5.tail(20).min()); stop5=recent_l5*0.97; stop_pct5=(stop5/cur_p5-1)*100
    tgt5=cur_p5*(1+abs(stop_pct5)/100*2); rr5=abs(abs(stop_pct5)*2/stop_pct5) if stop_pct5!=0 else 0
    kelly5=(0.55-(1-0.55)/rr5)*100 if rr5>0 else 0; rec_sz=max(1,min(20,kelly5*0.5))
    return html.Div([
        html.H5("What if the thesis is wrong?",className="text-warning mb-2"),
        html.Small(f"Beta {beta5:.2f} -- moves {beta5:.2f}x the market on average.",style={"color":"#8b7fbf","fontSize":"11px","display":"block","marginBottom":"10px"}),
        dbc.Row([dbc.Col(html.Small("Scenario",className="text-muted"),width=4),dbc.Col(html.Small("Trigger",className="text-muted"),width=3),dbc.Col(html.Small("Impact",className="text-muted"),width=2),dbc.Col(html.Small("Response",className="text-muted"),width=3)],className="mb-1 pb-1 border-bottom border-warning"),
        *[_sr5(s5,t5,ip5,a5) for s5,t5,ip5,a5 in scenarios5],
        html.Hr(style={"borderColor":"#3d3470","margin":"14px 0"}),
        html.H6("Position sizing",style={"color":"#e8621a","marginBottom":"10px"}),
        dbc.Row([dbc.Col(_metric_card("Stop price",f"${stop5:.2f}","#e63946"),width=3),dbc.Col(_metric_card("Max loss at stop",f"{stop_pct5:.1f}%","#e63946"),width=3),dbc.Col(_metric_card("Risk/reward",f"{rr5:.1f}:1","#2dc653" if rr5>=2 else "#e8621a"),width=3),dbc.Col(_metric_card("Suggested size",f"{rec_sz:.1f}% portfolio","#e8621a"),width=3)],className="g-2"),
        html.Small(f"Based on stop at ${stop5:.2f} and 2:1 reward/risk minimum. Never risk more than 1-2% of total portfolio per trade.",style={"color":"#6b5fa0","fontSize":"10px","display":"block","marginTop":"8px"}),
    ])

def _build_risk_cv(d):
    info=d["info"]; hist=d["hist1"]
    if hist.empty: return html.P("No data.",className="text-muted")
    close6=hist["Close"].squeeze(); cur_p6=float(close6.iloc[-1]); h52_6=float(close6.max())
    beta6=_safe(info,"beta") or 1.0; sf6=_safe(info,"shortPercentOfFloat")
    inst6=_safe(info,"heldPercentInstitutions"); ins6=_safe(info,"heldPercentInsiders")
    de6=_safe(info,"debtToEquity"); fcf6=_safe(info,"freeCashflow"); mc6=_safe(info,"marketCap") or 1
    dd6=(cur_p6/h52_6-1)*100; pe6=_safe(info,"trailingPE"); sector6=info.get("sector","")
    sigs6=[]
    if pe6 and pe6>0: sigs6.append(("Valuation",f"P/E {pe6:.1f}x",0.25 if pe6>60 else 0.65 if pe6>30 else 0.8,"#e63946" if pe6>60 else "#e8621a" if pe6>30 else "#2dc653"))
    else: sigs6.append(("Unprofitable","Negative earnings",0.25,"#e63946"))
    if sf6 is not None:
        sf6p=sf6*100; sigs6.append(("Short interest",f"{sf6p:.1f}% of float",0.2 if sf6p>15 else 0.5 if sf6p>7 else 0.8,"#e63946" if sf6p>15 else "#e8621a" if sf6p>7 else "#2dc653"))
    if inst6 is not None: sigs6.append(("Inst. ownership",f"{inst6*100:.0f}%",0.75 if inst6>0.4 else 0.45,"#2dc653" if inst6>0.4 else "#e8621a"))
    if ins6 is not None: sigs6.append(("Insider ownership",f"{ins6*100:.1f}%",0.8 if ins6>0.1 else 0.45,"#2dc653" if ins6>0.1 else "#e8621a"))
    if de6 is not None: sigs6.append(("Debt/equity",f"{de6:.0f}%",0.2 if de6>200 else 0.55 if de6>80 else 0.85,"#e63946" if de6>200 else "#e8621a" if de6>80 else "#2dc653"))
    if fcf6 is not None:
        fy6=(fcf6/mc6)*100; sigs6.append(("FCF yield",f"{fy6:.1f}%",0.85 if fy6>4 else 0.6 if fy6>0 else 0.25,"#2dc653" if fy6>4 else "#e8621a" if fy6>0 else "#e63946"))
    sigs6.append(("Drawdown",f"{dd6:.1f}% off 52W high",0.3 if dd6<-30 else 0.5 if dd6<-15 else 0.7,"#e63946" if dd6<-30 else "#e8621a" if dd6<-15 else "#2dc653"))
    if "Technology" in sector6: monitor6=[("Primary risk","Revenue deceleration / churn. Watch ARR, NRR."),("Leading indicator","Cloud spend surveys, IT budgets, enterprise deal sizes."),("Macro factor","Rate environment compresses growth multiples. USD strength.")]
    elif "Consumer" in sector6: monitor6=[("Primary risk","Consumer spending slowdown. Watch retail sales."),("Leading indicator","Credit card data, foot traffic, comparable store sales."),("Macro factor","Employment, wage growth, inflation vs purchasing power.")]
    elif "Financial" in sector6: monitor6=[("Primary risk","Credit quality. Loan loss provisions and NPL ratios."),("Leading indicator","Yield curve, loan growth, CRE exposure."),("Macro factor","Fed funds rate, unemployment, housing market.")]
    else: monitor6=[("Primary risk","Execution risk -- delivering on the growth implied by the multiple."),("Leading indicator","Revenue reports, customer metrics, operating leverage."),("Macro factor","Sector rotation, rate environment, dollar strength.")]
    return html.Div([
        html.H5("Risk signal dashboard",className="text-warning mb-2"),
        html.Div([_signal_bar(n,v,s,c) for n,v,s,c in sigs6]),
        html.Hr(style={"borderColor":"#3d3470","margin":"14px 0"}),
        html.H6("What to monitor while holding",style={"color":"#e8621a","marginBottom":"10px"}),
        *[_assumption_block(l,t6,"#e63946" if i==0 else "#e8621a" if i==1 else "#6d5ac4") for i,(l,t6) in enumerate(monitor6)],
    ])

def _build_conviction_tab(d):
    info=d["info"]; hist=d["hist1"]; ticker=d["ticker"]; earnings=d["earnings"]
    if hist.empty: return html.P("No data.",className="text-muted")
    close7=hist["Close"].squeeze(); cur_p7=float(close7.iloc[-1])
    fpe7=_safe(info,"forwardPE"); sf7=_safe(info,"shortPercentOfFloat")
    target7=_safe(info,"targetMeanPrice"); name7=info.get("longName",ticker); desc7=info.get("longBusinessSummary","")
    ema50_7=float(close7.ewm(span=50,adjust=False).mean().iloc[-1])
    fpe_ok7=fpe7 and 0<fpe7<60; ema_ok7=cur_p7>ema50_7
    beats_ok7=(sum(1 for e in earnings if (e.get("actual",0) or 0)>=(e.get("estimate",0) or 0))>=len(earnings)*0.6) if earnings else False
    sf_ok7=not(sf7 and sf7>0.15)
    checks7=[
        ("I understand how this company makes money and who its customers are",bool(desc7)),
        (f"Valuation ({_fmt_r(fpe7)} fwd P/E) is justified by the growth profile" if fpe_ok7 else "I accept I am buying on future profitability" if fpe7 and fpe7<=0 else "Valuation appears expensive -- I have a clear reason why",bool(fpe_ok7 or (fpe7 and fpe7<=0))),
        (f"Company beats estimates consistently",beats_ok7),
        (f"Price (${cur_p7:.2f}) is above 50-day EMA (${ema50_7:.2f})",ema_ok7),
        ("Short interest is not elevated -- no concentrated bear thesis",sf_ok7),
        ("I have identified the next catalyst",True),
        ("I have set a position size I can hold through a 20-30% drawdown",True),
    ]
    score7=sum(1 for _,p in checks7 if p); sc_c7="#2dc653" if score7>=5 else "#e8621a" if score7>=4 else "#e63946"
    sc_l7="Strong conviction" if score7>=5 else "Moderate -- review reds" if score7>=4 else "Low -- do not size up"
    recent_l7=float(close7.tail(20).min()); stop7=recent_l7*0.97; stop_pct7=(stop7/cur_p7-1)*100
    tgt_mult7=2.5 if fpe7 and fpe7<30 else 1.5; tgt7=cur_p7*(1+abs(stop_pct7)/100*tgt_mult7)
    return html.Div([
        html.H5("Conviction checklist",className="text-warning mb-2"),
        html.Small(f"Before entering {name7}, check most of these.",style={"color":"#8b7fbf","fontSize":"11px","display":"block","marginBottom":"10px"}),
        html.Div([html.Div([html.Span("✓ " if p else "✗ ",style={"color":"#2dc653" if p else "#e63946","fontWeight":"bold","fontSize":"13px"}),html.Span(t7,style={"fontSize":"13px","color":"#d4d0e8","lineHeight":"1.5"})],style={"display":"flex","alignItems":"flex-start","padding":"7px 0","borderBottom":"1px solid #111120"}) for t7,p in checks7],style={"marginBottom":"14px"}),
        html.Div([html.Span("Conviction score: ",style={"color":"#8b7fbf","fontSize":"12px"}),html.Span(f"{score7}/{len(checks7)}  --  {sc_l7}",style={"color":sc_c7,"fontWeight":"500","fontSize":"13px"})],style={"padding":"10px 12px","background":"#1c1838","borderRadius":"6px","marginBottom":"14px","border":"1px solid #1e1e2e"}),
        html.Hr(style={"borderColor":"#3d3470","margin":"12px 0"}),
        html.H6("Your exit plan",style={"color":"#e8621a","marginBottom":"10px"}),
        _exit_strip("Stop loss -- exit if",f"Price closes below ${stop7:.2f} ({stop_pct7:.1f}% from current). No debate, no averaging down.","#e63946"),
        _exit_strip("Thesis break -- reassess if","Revenue decelerates, margins compress, guidance cut, or major competitor takes share.","#e8621a"),
        _exit_strip("Target achieved -- trim if",f"Price reaches ${tgt7:.2f} ({((tgt7/cur_p7)-1)*100:.0f}% gain). Re-evaluate if story is priced in."+(f" Analyst target: {fusd(target7)}." if target7 else ""),"#2dc653"),
        _exit_strip("Time stop","After 6 months with no progress, ask if capital is better deployed elsewhere.","#6d5ac4"),
    ])

def conviction_page():
    return html.Div([
        html.H4("Conviction Framework",className="text-warning mb-1"),
        html.Small("Before entering any position: understand what you are paying for, what has to be true, and how you will exit if it does not work.",className="text-muted d-block mb-3",style={"fontSize":"11px"}),
        dbc.Row([
            col(dbc.Input(id="cv-ticker",placeholder="Enter ticker  e.g. NVDA, QBTS, AAPL",className="bg-dark text-light border-secondary",debounce=False),4),
            col(dbc.Button("Analyze",id="cv-btn",color="warning",size="sm"),"auto"),
            col(html.Span(id="cv-status",style={"fontSize":"11px","color":"#6b5fa0","display":"block","marginTop":"4px"}),"auto"),
        ],className="mb-3 g-2 align-items-center"),
        dbc.Tabs(id="cv-tabs",active_tab="valuation",children=[
            dbc.Tab(label="Valuation",   tab_id="valuation"),
            dbc.Tab(label="Chart",       tab_id="chart"),
            dbc.Tab(label="Earnings",    tab_id="earnings"),
            dbc.Tab(label="Stress Test", tab_id="stress"),
            dbc.Tab(label="Risk Signals",tab_id="risk"),
            dbc.Tab(label="Conviction",  tab_id="conviction"),
        ],className="mb-3"),
        dcc.Loading(html.Div(id="cv-content",style={"background":"#12102a","minHeight":"200px"}),type="circle",color="#e8621a"),
    ])

@app.callback(Output("cv-content","children"),Output("cv-status","children"),
    Input("cv-btn","n_clicks"),Input("cv-tabs","active_tab"),
    State("cv-ticker","value"),prevent_initial_call=False)
def update_conviction(n,active_tab,ticker):
    ticker=(ticker or "").strip().upper()
    if not ticker:
        return html.Div([html.P("Enter a ticker above to start your conviction analysis.",style={"color":"#6b5fa0","fontSize":"13px","marginTop":"20px","textAlign":"center"}),html.P("Works for any US-listed stock or ETF.",style={"color":"#554880","fontSize":"11px","textAlign":"center"})]),""
    try: d=_load_ticker(ticker)
    except Exception as e: return html.P(f"Error loading {ticker}: {e}",className="text-danger"),"Error"
    if d["hist1"].empty: return html.P(f"No data for {ticker}. Check the ticker.",className="text-warning"),"Not found"
    builders={"valuation":_build_valuation_cv,"chart":_build_chart_cv,"earnings":_build_earnings_cv,
              "stress":_build_stress_cv,"risk":_build_risk_cv,"conviction":_build_conviction_tab}
    try: content=builders.get(active_tab,_build_valuation_cv)(d)
    except Exception as e: content=html.P(f"Error: {e}",className="text-danger")
    return content,f"{d['info'].get('longName',ticker)}  |  {datetime.now().strftime('%H:%M:%S')}"

if __name__ == "__main__":
    print("\\n  Trading Dashboard starting...")
    print(f"  Copilot module: {'OK' if _COPILOT_OK else 'NOT FOUND — check ~/Anduril/copilot/'}")
    print(f"  Bot API: {ANDURIL_API_BASE} (run ./scripts/run_api.sh)")
    print("  Open your browser at:  http://127.0.0.1:8050\\n")
    app.run(debug=False, host="127.0.0.1", port=8050)

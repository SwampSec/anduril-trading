
```
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║          A N D Ú R I L   T R A D I N G   S U I T E           ║
    ║             "Flame of the West  —  Reforged"                  ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
```

**Andúril** is a self-hosted, open-source trading dashboard for personal market analysis.
One Python file installs everything. No subscriptions. No cloud. Runs entirely on your machine.

---

## What's Included

| Page | Description |
|------|-------------|
| **Watchlist** | 5 groups × 10 tickers — live prices, change %, day range |
| **Conviction** | 6-tab deep analysis before any trade — valuation, chart reading, earnings, stress test, risk signals, exit plan |
| **Adv Chart** | Full technical charting — 12 indicators, buy/sell annotations, 1m to weekly views |
| **Level 2** | Order book depth, buy/sell pressure, Time & Sales tape |
| **Screener** | Industry & keyword scanner across 15 themes |
| **News** | 90-day company news + earnings history charts |
| **Live News** | Stocks, **commodities & futures** (oil, gas, metals), crypto, markets, geo, macro (Finnhub + RSS + NewsData.io) — 5 min refresh; IPO calendar |
| **Financials** | Valuation metrics (incl. market cap), quarterly financials, analyst ratings |
| **Guide** | Hedge Fund Investing Reference Guide — built into the app at `/guide` (also saved as `guide.html` for offline use) |

**Data sources:** [yfinance](https://github.com/ranaroussi/yfinance) (free) + [Finnhub](https://finnhub.io) (free API key) + optional [NewsData.io](https://newsdata.io) and [Twelve Data](https://twelvedata.com)

---

## Requirements

- **Python 3.12 or higher** — [python.org/downloads](https://www.python.org/downloads/)
- ~500 MB free disk space
- Internet connection during install

---

## Installation

### All Platforms

```bash
python anduril_v2.py
```

That's it. The installer handles everything else — virtual environment, all packages, dashboard, reference guide, launcher, and desktop shortcut.

---

## Platform-Specific Setup

### macOS (Apple Silicon M1/M2/M3/M4)

**1. Install Python 3.12+ (if not already installed)**

Option A — via Homebrew (recommended):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12
```

Option B — direct download:
- Go to [python.org/downloads/macos](https://www.python.org/downloads/macos/)
- Download the macOS Universal installer for Python 3.12+

**2. Run the installer**
```bash
cd ~/Downloads
python3 anduril_v2.py
```

**3. Allow the desktop shortcut**

macOS may block `.command` files on first run. Right-click →
**Open** → **Open** to allow it once. After that, double-click works normally.

**4. Launch**

Double-click **Andúril Trading.command** on your Desktop,
or from Terminal:
```bash
bash ~/Anduril/launch.sh
```

---

### macOS (Intel)

Same steps as Apple Silicon above. The installer detects Intel automatically and skips arm64-specific optimisations.

---

### Windows 10 / 11

**1. Install Python 3.12+**

- Download from [python.org/downloads/windows](https://www.python.org/downloads/windows/)
- During install: ✅ check **"Add Python to PATH"**
- Recommended: also check **"Install for all users"**

Verify in PowerShell or Command Prompt:
```powershell
python --version
```

**2. Run the installer**

Open PowerShell or Command Prompt in the folder containing `anduril_v2.py`:
```powershell
python anduril_v2.py
```

If you see a permissions error, run PowerShell as Administrator.

**3. Launch**

Double-click **Andúril Trading.bat** on your Desktop,
or from Command Prompt:
```cmd
C:\Users\YourName\Anduril\launch.bat
```

> **Windows Defender note:** On first launch, Windows may show a SmartScreen warning for the `.bat` file. Click **More info** → **Run anyway**. This is expected for unsigned scripts.

---

### Linux — Ubuntu / Debian (GNOME, XFCE, MATE)

**1. Install Python 3.12+**

Ubuntu 24.04 ships with Python 3.12. For older versions:
```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/python
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

Set as default (optional):
```bash
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
```

**2. Install system dependencies**
```bash
sudo apt install -y git curl build-essential libssl-dev
```

**3. Run the installer**
```bash
cd ~/Downloads
python3.12 anduril_v2.py
```

**4. Launch**
```bash
bash ~/Anduril/launch.sh
```

Or add a desktop shortcut manually:
```bash
cat > ~/.local/share/applications/anduril.desktop << EOF
[Desktop Entry]
Name=Andúril Trading
Comment=Personal Trading Dashboard
Exec=bash /home/$USER/Anduril/launch.sh
Icon=/home/$USER/Anduril/anduril_logo.svg
Terminal=true
Type=Application
Categories=Finance;
EOF
chmod +x ~/.local/share/applications/anduril.desktop
```

---

### Linux — Fedora / RHEL / CentOS

**1. Install Python 3.12+**
```bash
sudo dnf install -y python3.12 python3.12-devel gcc git
```

Or via pyenv (any distro):
```bash
curl https://pyenv.run | bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
source ~/.bashrc
pyenv install 3.12.4
pyenv global 3.12.4
```

**2. Run the installer**
```bash
python3.12 anduril_v2.py
```

---

### Linux — Arch / Manjaro

```bash
sudo pacman -S python python-pip git base-devel
python anduril_v2.py
```

---

### Linux — Raspberry Pi (Debian arm64)

Pi 4 / Pi 5 with Raspberry Pi OS (64-bit):
```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip git
python3.12 anduril_v2.py
```

> Dash may be slow on Pi 3 or earlier. Pi 4/5 runs fine.

---

## After Installation

### 1. Add your API keys

Copy the template and edit your keys:
```bash
cp .env.trading.example ~/Anduril/.env.trading   # from the repo folder, after install
```

Or open the file directly:
- **Mac/Linux:** `~/Anduril/.env.trading`
- **Windows:** `C:\Users\YourName\Anduril\.env.trading`

| Key | Required? | Get it at | Used for |
|-----|-----------|-----------|----------|
| `FINNHUB_API_KEY` | **Recommended** | [finnhub.io](https://finnhub.io) | Live quotes, Level 2, news, earnings, IPO calendar |
| `NEWSDATA_API_KEY` | Optional | [newsdata.io](https://newsdata.io) | Live News feed (geopolitical / macro) |
| `TWELVE_DATA_API_KEY` | Optional | [twelvedata.com](https://twelvedata.com) | Price history fallback, forex |

Finnhub free tier: 60 calls/minute — enough for daily use. Charts and financials work without any key via yfinance.

### 2. Launch the dashboard

```
http://127.0.0.1:8050
```

Press **Ctrl+C** in the terminal to stop.

### 3. Open the reference guide

**From the app:** click **Guide** in the sidebar → `http://127.0.0.1:8050/guide`  
Use **← Andúril Trading** in the guide header to return to the dashboard.

**Offline:** open `~/Anduril/guide.html` directly in any browser (no server needed).

The guide has **24 tabs (00–23)**:

| Tab | Topic |
|-----|-------|
| **00 — Start Here** | End-to-end research workflow — how every tab and calculator fits together |
| **01 — Fundamental** | Company analysis framework, **market cap & size tiers**, valuation multiples, DCF |
| **02–10** | Technicals, quant, macro, tools, acronyms, chart annotations, earnings, risk signals, crypto |
| **11–16** | Calculator (with plain-English interpretations), stress test, screener, portfolio, watchlist, cheat sheet |
| **17–23** | Options & futures, paper trading, market events, business analysis, compare companies, dividends & funds, penny stocks |

Interactive features include chart **PNG/CSV export**, 7 risk-scenario simulations, peer comparison scoring, and saved business analysis (stored in your browser).

---

## File Layout

```
~/Anduril/
├── dashboard/
│   └── app.py              ← the dashboard application
├── notebooks/              ← Jupyter notebooks (optional)
├── venv/                   ← Python virtual environment
├── guide.html              ← Hedge Fund Reference Guide (offline + served at /guide)
├── data.db                 ← watchlist / conviction persistence (SQLite)
├── anduril_logo.svg        ← logo
├── .env.trading            ← API keys (never share this)
├── launch.sh               ← launcher (Mac/Linux)
└── launch.bat              ← launcher (Windows)
```

Repo layout (before install):

```
Stock_Trading/
├── anduril_v2.py           ← cross-platform installer (run this)
├── guide.html              ← reference guide source (copied to ~/Anduril on install)
├── .env.trading.example    ← API key template
└── README.md
```

---

## Updating

To update to a new version, re-run the installer:
```bash
python anduril_v2.py
```

It will overwrite `app.py` and `guide.html` but leave your `.env.trading` and any notebooks untouched.

---

## Troubleshooting

**"python not found" on Mac/Linux**
```bash
python3 anduril_v2.py
# or
python3.12 anduril_v2.py
```

**Pip permission errors on Mac**
```bash
sudo chown -R $(whoami) ~/Library/Caches/pip
sudo chown -R $(whoami) ~/Anduril
python3 anduril_v2.py
```

**Port 8050 already in use**
```bash
# Mac/Linux
lsof -i :8050 | grep LISTEN | awk '{print $2}' | xargs kill -9
# Windows PowerShell
netstat -ano | findstr :8050
taskkill /PID <PID> /F
```

**Watchlist shows no prices**
Add your Finnhub key to `.env.trading`. The Chart and Financials pages use yfinance and work without a key.

**Live News is empty**
Add `NEWSDATA_API_KEY` to `.env.trading`. Free tier has a ~12-hour delay on headlines.

**Guide link doesn't work**
Make sure the dashboard is running (`launch.sh` / `.bat`). The guide is served at `/guide` only while the app is up. Offline: open `~/Anduril/guide.html` directly.

**Windows: "Execution Policy" error in PowerShell**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**macOS: "Operation not permitted" on first run**
```bash
xattr -d com.apple.quarantine anduril_v2.py
python3 anduril_v2.py
```

---

## Data Sources

| Source | Used for | Key needed |
|--------|----------|------------|
| [yfinance](https://github.com/ranaroussi/yfinance) | Charts, financials, fundamentals, history | None |
| [Finnhub](https://finnhub.io) | Live quotes, Level 2, news, earnings, analyst ratings, IPO calendar | Free |
| [NewsData.io](https://newsdata.io) | Live News — geopolitical, macro, markets | Free (optional) |
| [Twelve Data](https://twelvedata.com) | Price history fallback, forex | Free (optional) |

---

## License

MIT — use, modify, distribute freely. Not financial advice.

---

*"Andúril, Flame of the West, is the sword reforged — a tool worthy of the task ahead."*

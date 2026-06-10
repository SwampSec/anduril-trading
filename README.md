
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
| **Financials** | Valuation metrics, quarterly financials, analyst ratings |
| **guide.html** | Offline Hedge Fund Investing Reference Guide — 20 tabs covering fundamentals, technicals, quant, macro, options, crypto, calculators, and more |

**Data sources:** [yfinance](https://github.com/ranaroussi/yfinance) (free) + [Finnhub](https://finnhub.io) (free API key)

---

## Requirements

- **Python 3.12 or higher** — [python.org/downloads](https://www.python.org/downloads/)
- ~500 MB free disk space
- Internet connection during install

---

## Installation

### All Platforms

```bash
python anduril.py
```

That's it. The installer handles everything else — virtual environment, all packages, dashboard, launcher, and desktop shortcut.

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
python3 anduril.py
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

Open PowerShell or Command Prompt in the folder containing `anduril.py`:
```powershell
python anduril.py
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
python3.12 anduril.py
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
python3.12 anduril.py
```

---

### Linux — Arch / Manjaro

```bash
sudo pacman -S python python-pip git base-devel
python anduril.py
```

---

### Linux — Raspberry Pi (Debian arm64)

Pi 4 / Pi 5 with Raspberry Pi OS (64-bit):
```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip git
python3.12 anduril.py
```

> Dash may be slow on Pi 3 or earlier. Pi 4/5 runs fine.

---

## After Installation

### 1. Add your Finnhub API key

Open the file:
- **Mac/Linux:** `~/Anduril/.env.trading`
- **Windows:** `C:\Users\YourName\Anduril\.env.trading`

Edit the one line:
```
FINNHUB_API_KEY=YOUR_KEY_HERE
```

Get a free key at **[finnhub.io](https://finnhub.io)** — sign up, key appears on the dashboard instantly. Free tier: 60 calls/minute, enough for all features.

### 2. Open the reference guide

Open `~/Anduril/guide.html` in any browser for the full offline Hedge Fund Investing Reference Guide. 20 tabs covering everything from DCF to options Greeks to Kelly Criterion.

### 3. Launch the dashboard

```
http://127.0.0.1:8050
```

Press **Ctrl+C** in the terminal to stop.

---

## File Layout

```
~/Anduril/
├── dashboard/
│   └── app.py              ← the dashboard application
├── notebooks/              ← Jupyter notebooks (optional)
├── venv/                   ← Python virtual environment
├── guide.html              ← Hedge Fund Reference Guide (offline)
├── anduril_logo.svg        ← logo
├── .env.trading            ← API keys (never share this)
├── launch.sh               ← launcher (Mac/Linux)
└── launch.bat              ← launcher (Windows)
```

---

## Updating

To update to a new version, re-run the installer:
```bash
python anduril.py
```

It will overwrite `app.py` and `guide.html` but leave your `.env.trading` and any notebooks untouched.

---

## Troubleshooting

**"python not found" on Mac/Linux**
```bash
python3 anduril.py
# or
python3.12 anduril.py
```

**Pip permission errors on Mac**
```bash
sudo chown -R $(whoami) ~/Library/Caches/pip
sudo chown -R $(whoami) ~/Anduril
python3 anduril.py
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

**Windows: "Execution Policy" error in PowerShell**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**macOS: "Operation not permitted" on first run**
```bash
xattr -d com.apple.quarantine anduril.py
python3 anduril.py
```

---

## Data Sources

| Source | Used for | Key needed |
|--------|----------|------------|
| [yfinance](https://github.com/ranaroussi/yfinance) | Charts, financials, fundamentals, history | None |
| [Finnhub](https://finnhub.io) | Live quotes, Level 2, news, earnings, analyst ratings | Free |

---

## License

MIT — use, modify, distribute freely. Not financial advice.

---

*"Andúril, Flame of the West, is the sword reforged — a tool worthy of the task ahead."*

#!/usr/bin/env bash
# Paper trading fire drill — read-only checks against IB Gateway + API.
# Prerequisites: IB Gateway paper logged in (port 4002), LM Studio optional.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env.broker" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.broker"
  set +a
fi

BASE="${ANDURIL_API_BASE:-http://${API_HOST:-127.0.0.1}:${API_PORT:-9001}}"
SYMBOL="${1:-SPY}"

pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*"; exit 1; }

echo "Anduril paper fire drill"
echo "API: $BASE"
echo "Symbol: $SYMBOL"
echo ""

echo "1. API health"
curl -sf "$BASE/health" | grep -q '"status":"ok"' && pass "health ok" || fail "API not reachable — run ./scripts/run_api.sh"

echo "2. IBKR connect"
curl -sf -X POST "$BASE/ibkr/connect" | grep -q '"connected":true' && pass "gateway connected" || fail "IBKR connect failed — check Gateway on port ${IBKR_PORT:-4002}"

echo "3. Account (masked)"
ACCT="$(curl -sf "$BASE/ibkr/account")"
echo "     $ACCT"
echo "$ACCT" | grep -q 'DU' && pass "paper account prefix" || echo "  ⚠ account id not shown or not DU — verify paper mode manually"

echo "4. Quote"
QUOTE="$(curl -sf "$BASE/ibkr/quote?symbol=$SYMBOL")"
echo "     $QUOTE"
echo "$QUOTE" | grep -q 'trade_price' && pass "quote received" || fail "quote failed"

echo "5. LM Studio ping"
if curl -sf "$BASE/llm/ping" >/dev/null 2>&1; then
  pass "llm ping"
  curl -sf "$BASE/llm/ping" | head -c 200
  echo ""
else
  echo "  ⚠ LM Studio not running (optional for analyze without headline)"
fi

echo "6. Analyze (no order — BOT_ENABLED may be false)"
ANALYZE="$(curl -sf -X POST "$BASE/bot/analyze?symbol=$SYMBOL")"
echo "     $(echo "$ANALYZE" | head -c 300)"
echo "$ANALYZE" | grep -q '"action"' && pass "decision returned" || fail "analyze failed"

echo "7. Bot status (should be disarmed, read-only)"
STATUS="$(curl -sf "$BASE/bot/status")"
echo "     $STATUS"
echo "$STATUS" | grep -q '"armed":false' && pass "disarmed by default" || echo "  ⚠ bot reports armed — disarm before live"
echo "$STATUS" | grep -q '"read_only":true' && pass "read-only broker" || echo "  ⚠ read_only is false — orders could reach Gateway"

echo "8. Audit trail"
AUDIT="$(curl -sf "$BASE/audit/recent?limit=5")"
echo "     $(echo "$AUDIT" | head -c 200)"
echo "$AUDIT" | grep -q '"records"' && pass "audit log reachable" || fail "audit failed"

echo ""
echo "Fire drill complete."
echo "Paper order test (manual): BOT_ENABLED=true, IBKR_READ_ONLY=false, POST /bot/arm, POST /bot/run-once?symbol=SPY"
echo "Orders are capped by BOT_MAX_SHARES (default 10). Limit price always uses live/delayed quote."
echo "View/cancel API orders: GET /ibkr/orders  POST /ibkr/orders/{id}/cancel"

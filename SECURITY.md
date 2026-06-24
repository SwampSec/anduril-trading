# SECURITY.md — Anduril Trading Bot Threat Model

> Scope: This document is the security specification for the Anduril autonomous
> trading system. It defines what we are protecting, what can go wrong, and the
> controls that must be enforced in code. Treat every control marked **MUST** as
> a hard requirement; a build that violates one is a security defect, not a
> style choice.

---

## 1. Purpose & Scope

Anduril ingests market data, fundamentals, and **live news**, runs deterministic
quantitative analysis, consults a local LLM (via LM Studio) for a qualitative
overlay, and places real-money orders through Interactive Brokers' IB Gateway.

Two properties make this system unusually security-sensitive:

1. **It moves real money autonomously.** A defect doesn't crash a page — it
   places trades.
2. **It consumes attacker-influenceable input.** News text is written by third
   parties and is fed toward a model that influences decisions. That is a
   classic injection surface.

The single highest-priority security goal is therefore: **no input, model
output, bug, or failure can cause the bot to (a) exceed available cash / use
margin, or (b) place an order that wasn't produced by the validated decision
pipeline.**

In scope: the bot code, its trust boundaries, secrets, the LLM and Gateway
interfaces, dependencies, logging. Out of scope: IBKR's own infrastructure, the
host OS hardening (assumed baseline), physical security of the machine.

---

## 2. System Overview & Trust Boundaries

```
   [ Live News Feed ]      [ Market / Fundamental Data ]
         |  (UNTRUSTED)              |  (semi-trusted)
         v                          v
   +-----------------------------------------------+
   |  Anduril Bot (Python)                          |
   |                                                |
   |   news/   analysis/   engine/   risk/          |
   |     |         |          |        |            |
   |     +----> LLM overlay   |        |            |
   |            (LM Studio) ---+        |            |
   |                                    |            |
   |        Decision object --> Risk Guardrails -----+--> [ IB Gateway ] --> $$$
   +-----------------------------------------------+        (THE MONEY BOUNDARY)
              ^                                  ^
              | (network, may be remote)         | (localhost socket, 4001/4002)
        [ LM Studio server ]              [ IB Gateway (manual login) ]
```

Trust boundaries (where data crosses from less-trusted to more-trusted):

- **B1 — News → Bot.** Fully untrusted. Anyone can publish a headline.
- **B2 — LLM output → Decision engine.** Untrusted *as a control signal*: the
  model can hallucinate or be steered by injected news. Its output is data, never
  code, never an order.
- **B3 — Bot → IB Gateway.** The money boundary. Highest consequence in the
  system. Everything funnels through `risk/guardrails.py` before crossing it.
- **B4 — Bot ↔ LM Studio over the network** (only when inference runs on a
  remote machine, e.g. the 512 GB Mac Studio). Confidentiality + integrity of
  this link matters.
- **B5 — Secrets at rest** (credentials, keys) and **B6 — the supply chain**
  (dependencies, the `ibapi` distribution).

---

## 3. Assets to Protect

| Asset | Why it matters |
|---|---|
| Account funds | Direct, irreversible financial loss. |
| IBKR credentials / session | Account takeover; full loss + fraud exposure. |
| The order-placement capability | If abused, it spends money. |
| Decision/audit log integrity | Needed to reconstruct what happened and why. |
| Account data (balances, positions) | Privacy; should not leak to the network or the LLM. |
| The cash-only invariant | The core promise of the system: never borrow. |

---

## 4. Threat Actors

- **A1 — Adversarial / manipulated news publisher.** Crafts a headline to steer
  the model (pump-and-dump narrative, fake event, prompt-injection payload).
- **A2 — Network attacker on the LAN** (relevant when LM Studio is remote).
  Tries to reach an exposed LM Studio or Gateway port.
- **A3 — Malicious or compromised dependency** (typosquatted package, poisoned
  update, fake `ibapi` build).
- **A4 — Local attacker / leaked repo.** Finds secrets in code, logs, or
  history.
- **A5 — The system itself.** Bugs, races, bad data, and unhandled failures are
  the *most likely* cause of loss here — more than any external attacker.

---

## 5. Threats & Required Controls (STRIDE-mapped)

Each threat lists the boundary, the STRIDE category, and the controls. Controls
marked **MUST** are non-negotiable.

### T1 — Prompt injection via news → malicious signal (B1/B2, Tampering/EoP)
A headline contains text engineered to manipulate the model into recommending a
large buy, ignoring risk, or emitting structured output that the engine acts on.

Controls:
- **MUST** confine the model's output to a strict, validated schema: bounded
  numeric fields (`sentiment` ∈ [-1,1], `materiality` ∈ [0,1]) and a fixed
  `event_type` enum. Reject and default-to-HOLD on any schema violation.
- **MUST NOT** `eval`/`exec`/`pickle.loads` model output, or build orders, symbols,
  quantities, or prices from free-form model text. The model selects from
  pre-computed options; it never authors order parameters.
- **MUST** cap the model's authority: its output may only *lower* conviction or
  trigger a veto/HOLD. It can never raise position size, unlock a symbol, or
  relax a risk limit. Size and limits are computed in Python independently.
- News content passed to the model is wrapped/delimited and clearly labelled as
  untrusted data, not instructions. The system prompt states the model must
  ignore any instructions found inside news text.
- Sanitize/normalize headline text (strip control chars, cap length) before it
  reaches the model.

### T2 — Margin breach / over-leverage (B3, EoP/Tampering) — THE CORE RISK
The bot borrows money or exceeds actual funds, violating the cash-only mandate.
On a margin account this happens silently if sizing reads the wrong field.

Controls:
- **MUST** size every BUY off `TotalCashValue` / `SettledCash`. **MUST NOT** size
  off `BuyingPower` or `AvailableFunds` — on a margin account these already
  include leverage and *will* cause borrowing.
- **MUST** run a `whatIf=True` pre-check on every order and reject any whose
  initial-margin requirement implies it would draw on margin rather than be fully
  cash-covered.
- **MUST** maintain an internal cash ledger that reserves cash for pending buys so
  concurrent signals cannot each spend the full balance (prevents a TOCTOU race).
- **MUST** reconcile the internal ledger against IBKR's reported cash every cycle
  and HALT trading on divergence beyond a tight tolerance.
- **MUST** constrain SELLs to `sell_qty ≤ shares_held` — no shorting, structurally
  (shorting is margin by definition).
- Anchor to settled cash to respect T+1 settlement and avoid spending unsettled
  proceeds.

### T3 — Runaway / duplicate orders (B3, DoS/Tampering)
A loop bug, a flapping signal, or a retry storm fires many orders.

Controls:
- **MUST** enforce a max-orders-per-day cap and a per-symbol max-position cap.
- **MUST** make order submission idempotent: a unique client order ref per
  intended trade; never resubmit without confirming the prior one's status.
- **MUST** implement a daily-loss circuit breaker that flattens-and-halts when
  realized loss crosses a configured threshold.
- **MUST** provide a global kill switch (env flag) that blocks ALL order
  placement while leaving analysis running.
- Respect IBKR pacing (~50 requests/sec at default market-data lines) to avoid
  forced disconnects mid-session.

### T4 — Credential theft / account takeover (B5, Information Disclosure)
Secrets leak via source, logs, or git history.

Controls:
- **MUST** load all secrets from `.env` (gitignored) or the OS keychain. Ship only
  `.env.example`. No credentials, keys, or tokens in source or committed config.
- **MUST NOT** log secrets, full account numbers, or full API responses containing
  them. Mask account IDs (e.g. `U12••••67`).
- IB Gateway login remains manual/interactive by design (no headless credential
  storage for the Gateway session itself), per IBKR's model.
- Add a pre-commit secret scanner (e.g. gitleaks) to block accidental commits.

### T5 — Network exposure of LM Studio / Gateway (B4, Spoofing/EoP)
An exposed inference or Gateway port lets a LAN attacker drive the model or the
account.

Controls:
- **MUST** bind IB Gateway and (when local) LM Studio to `127.0.0.1`.
- **MUST**, for the remote-Mac-Studio case, tunnel the LM Studio connection over
  SSH or TLS — never expose the raw LM Studio port on an open network.
- **MUST** use IB Gateway's Trusted IPs allowlist (single IPs only; it does not
  accept subnets) and keep "Allow connections from localhost only" enabled unless
  remote access is deliberately configured.
- Minimize what is sent to a remote model: send headlines/derived features, NOT
  account balances, positions, or account numbers (privacy + reduces value of a
  MITM).

### T6 — Supply-chain compromise (B6, Tampering)
A malicious package or a fake `ibapi` build executes attacker code in-process —
with access to the order capability.

Controls:
- **MUST** install `ibapi` ONLY from Interactive Brokers' official
  `interactivebrokers.github.io` distribution. Per IBKR, pip/NuGet/other repos are
  not hosted or supported by IB; a package named `ibapi` from PyPI is not the
  official client and must not be trusted.
- **MUST** pin all dependency versions and commit a lockfile.
- Run `pip-audit` (or equivalent) in CI; fail the build on known-vulnerable deps.
- Keep the dependency surface minimal; review new transitive deps.

### T7 — Bad / stale data → wrong decision or false cash reading (B1, all of A5)
Stale prices, a failed fundamentals fetch, or a partial account-summary read
leads to mis-sizing or trading on phantom cash.

Controls:
- **MUST** apply a fail-safe default: any exception, missing/stale field,
  validation failure, or ambiguity results in DO-NOT-TRADE for that symbol.
  Errors never fall through into an order.
- Timestamp and staleness-check market and account data; refuse to size off data
  older than a configured max age.
- Treat IBKR's reported positions and cash as ground truth; reconcile at session
  start and each cycle.

### T8 — Paper/live mode confusion (B3, Tampering)
The bot believes it is in paper mode but is connected to a live account (or
arms live trading unintentionally).

Controls:
- **MUST** detect mode from the account-ID prefix (DU = paper, U = live) after
  connect, and stamp it on every decision and order record.
- **MUST** gate live order placement behind an explicit `LIVE_TRADING_CONFIRMED`
  flag AND verified live-mode detection; default posture is paper + Read-Only API.
- Refuse to start live trading if detected mode and configured intent disagree.

### T9 — Repudiation / un-auditable history (Repudiation)
After a loss, you cannot reconstruct what the bot saw and why it acted.

Controls:
- **MUST** write an append-only audit log capturing, per decision: inputs (data
  snapshot refs), every subscore, the news overlay effect, the composite score,
  the action, the order ref, and the resulting fill/status.
- Rotate logs; never include secrets; protect against silent truncation
  (e.g. write-once + checksums).

### T10 — Session loss leaving orphan state (B3, DoS)
A disconnect (pacing violation, Gateway restart, network drop) leaves orders or
positions the bot is unaware of.

Controls:
- Detect disconnects; on reconnect, **MUST** re-pull open orders, executions, and
  positions and reconcile before resuming. Do not place new orders until
  reconciliation succeeds.
- Respect Gateway's daily auto-restart; treat the post-restart state as
  authoritative.

### T11 — Privilege creep in the analysis process (EoP)
The read-only analysis path holds more capability than it needs.

Controls:
- **MUST** run analysis with IBKR Read-Only API enabled by default. Only the
  explicitly-armed trading process disables Read-Only, and only when T8's gates
  pass. Separate the order-capable code path from the analysis path.

---

## 6. The Math/Judgment Security Boundary

The architecture's core safety property is also a security control: **all
arithmetic and all limits live in Python; the LLM only provides bounded
qualitative input.** This means an adversary who fully controls the model's
output (via injected news, a poisoned model, or a compromised inference host)
still cannot:

- author an order's symbol, side, quantity, or price,
- raise a position size or unlock additional cash,
- bypass the cash-only / no-margin guardrails,
- or cause code execution.

The worst an attacker who owns the model output can achieve is to push the bot
toward HOLD/veto or nudge conviction down — a denial-of-opportunity, not a loss
of funds. Preserve this property: never widen the model's authority for
convenience.

---

## 7. Fail-Safe Defaults (summary)

- Unknown, missing, stale, or invalid → **do not trade**.
- Schema validation fails → **HOLD**.
- Ledger vs IBKR divergence → **halt**.
- Mode/intent mismatch → **refuse to start**.
- Any unhandled exception in the order path → **abort the order, log, alert**.

The default state of the system is "not trading." Trading is an explicitly
earned, narrowly gated exception.

---

## 8. Pre-Deployment Security Checklist

Before arming live trading, confirm:

- [ ] `.env` is gitignored; repo history scanned; only `.env.example` is committed.
- [ ] `ibapi` installed from `interactivebrokers.github.io` only; deps pinned + lockfile committed; `pip-audit` clean.
- [ ] Sizing reads `TotalCashValue`/`SettledCash` only — grep confirms no `BuyingPower`/`AvailableFunds` in any sizing path.
- [ ] `whatIf` pre-check active on every order; rejects margin-drawing orders in a paper test.
- [ ] Cash ledger reserves pending buys; concurrent-signal race tested; divergence halt verified.
- [ ] SELL ≤ held enforced; a forced over-sell attempt is rejected in test.
- [ ] Max-orders/day, max-position, daily-loss breaker, and kill switch all tested live-fire in paper.
- [ ] Model output is schema-validated; a crafted/garbage headline cannot produce an order (injection test passed).
- [ ] IB Gateway + LM Studio bound to localhost; remote inference (if any) tunneled; Trusted IPs set.
- [ ] Read-Only API on for analysis; live path gated behind `LIVE_TRADING_CONFIRMED` + DU/U detection.
- [ ] Account IDs masked in logs; append-only audit log writing complete decision records.
- [ ] Reconnect → reconcile path tested by killing Gateway mid-session.
- [ ] Backtest gate passed for any signal/threshold set allowed to trade live.

---

## 9. Residual Risks (accepted / out of scope)

- **Model quality.** Guardrails bound *loss*, not *bad judgment*. A well-formed
  but wrong signal that passes all checks can still lose money within limits.
  Mitigation is small sizing + backtest gating, not security controls.
- **Market risk.** Slippage, gaps, halts, and liquidity are not eliminated.
- **IBKR-side outages / data errors.** Detect and halt; cannot prevent.
- **Host compromise (root).** An attacker with full control of the machine
  running the armed trading process is outside this model's defenses; rely on OS
  hardening and least-privilege deployment.
- **Regulatory/compliance** (e.g. jurisdiction-specific automated-trading rules)
  is a separate concern from this technical threat model.

---

## 10. Incident Response

If anomalous behavior is suspected:

1. **Trip the kill switch** (env flag) — stops all new orders immediately.
2. Disconnect the trading process from Gateway; switch Gateway to Read-Only.
3. Reconcile positions and cash directly in TWS/Gateway against the audit log.
4. Rotate IBKR credentials if compromise is suspected; review API logs.
5. Preserve logs; do not resume live trading until root cause is found and a
   regression test covers it.

---

*This threat model is a living document. Update it whenever a new data source,
network path, dependency, or capability is added — each is a potential new
boundary.*

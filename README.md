# TRADING DESK — Multi-Agent Autonomous Framework

Framework **Level C (auto-execution)** untuk crypto/forex, di-orchestrate oleh tim
6 agent persona (Prof. Marcus, Rafael, Nakamoto X, Madame Eleanor, Dr. Grace, Kodok).
Default **PAPER-FIRST** — eksekusi real hanya bisa nyala setelah konfirmasi eksplisit.

## ⚠️ DISCLAIMER
Bukan nasihat keuangan. Trading crypto/forex berisiko kehilangan seluruh modal.
Framework ini untuk edukasi/eksperimen. Uji di paper/testnet dulu.

## 3 Mode Eksekusi (urut naik risiko)
1. **`paper`** — simulasi lokal, tanpa koneksi exchange. Default & paling aman untuk dev.
2. **`demo`** — REAL MARKET via **testnet/sandbox** exchange (uang virtual). Uji bot dengan
   kondisi pasar nyata tanpa risiko uang. Butuh API key testnet (trade-only).
3. **`live`** — REAL MONEY. HANYA setelah `demo` stabil + `confirm_live_manually: true`.

## State & Siklus
- `core/state.py` menyimpan posisi terbuka + equity ke `logs/state.json` (persist antar siklus/restart).
- Setiap siklus: data → analisis → **EXIT dulu** (TP/SL/timeout) → **ENTRY** (bila sinyal + gate lolos)
  → simpan state. Bot tidak lupa posisi meski di-restart.

## Keamanan (non-negotiable)
- API exchange = **trade-only, tanpa withdrawal**.
- Hard guardrail (pos size, R:R ≥ 1:2, max daily loss) di-enforce di `core/risk_engine.py`,
  BUKAN cuma nasihat LLM.
- Circuit breaker: bot berhenti otomatis kalau drawdown harian tembus batas.
- Audit log tiap keputusan di `logs/audit.log`.

## Struktur
```
config/      settings.yaml, .env.example
core/        llm_client, risk_engine, circuit_breaker, executor, indicators, orchestrator, state
data/        market (CCXT), onchain (Fear&Greed), macro, mock (offline test)
agents/      6 persona (marcus, rafael, nakamoto, eleanor, grace, kodok)
notify/      telegram
serve.py     jalankan desk + dashboard live (HTTP :8000)
dashboard.html  visual 6 agent (fetch logs/briefing.json, auto-refresh)
main.py      entry point
```

## Setup
```bash
cd trading-desk
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config/.env.example config/.env                  # isi API key (paper TIDAK wajib)
```

## Jalankan
```bash
python main.py --once        # test satu kali (paper)
python main.py               # autonomous loop (tiap run_every_minutes)
```

## Output ke Telegram
1. Buat bot @BotFather → dapat token.
2. Chat ID: ketik ke @userinfobot.
3. Isi `config/.env` + set `telegram.enabled: true` di `settings.yaml`.

## Catatan
- Data pasar dari CCXT (publik, tanpa API key). Fear&Greed dari alternative.me.
- LLM persona layer: set `llm.enabled: true` + `LLM_API_KEY`. Jika off, agent pakai
  teks statis & sinyal tetap jalan (deterministik via KODOK).
- Makro: hook `data/macro.py` perlu API ekonomi nyata (FOMC/NFP/CPI) untuk produksi.

# TRADING DESK — Multi-Agent Autonomous Framework

Framework **Level C (auto-execution)** untuk crypto/forex, di-orchestrate oleh tim
6 agent persona (Prof. Marcus, Rafael, Nakamoto X, Madame Eleanor, Dr. Grace, Kodok).
Default **PAPER-FIRST** — eksekusi real hanya bisa nyala setelah konfirmasi eksplisit.

## ⚠️ DISCLAIMER
Bukan nasihat keuangan. Trading crypto/forex berisiko kehilangan seluruh modal.
Framework ini untuk edukasi/eksperimen. Uji di paper/testnet dulu.

## Keamanan (non-negotiable)
- Mode `paper` sebagai default. `live` hanya jika `mode: live` + `confirm_live_manually`.
- API exchange = **trade-only, tanpa withdrawal**.
- Hard guardrail (pos size, R:R ≥ 1:2, max daily loss) di-enforce di `core/risk_engine.py`,
  BUKAN cuma nasihat LLM.
- Circuit breaker: bot berhenti otomatis kalau drawdown harian tembus batas.
- Audit log tiap keputusan di `logs/audit.log`.

## Struktur
```
config/      settings.yaml, .env.example
core/        llm_client, risk_engine, circuit_breaker, executor, indicators, orchestrator
data/        market (CCXT), onchain (Fear&Greed), macro
agents/      6 persona (marcus, rafael, nakamoto, eleanor, grace, kodok)
notify/      telegram
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

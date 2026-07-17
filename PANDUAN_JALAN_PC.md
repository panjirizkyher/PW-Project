# PANDUAN JALAN DI PC WINDOWS (Trading Desk — mode demo / testnet)

Bot sudah siap. Ini langkah menjalankannya di komputer Windows kamu (punya internet).
Mode saat ini `demo` → REAL MARKET via **testnet Binance** (uang virtual, aman uji).

---

## 0. Prasyarat (sekali saja)
- Python 3.11 sudah terinstall. Cek: `python --version`
- Repo sudah di-clone:
  ```bash
  git clone https://github.com/panjirizkyher/PW-Project.git
  cd PW-Project
  ```
- Virtual env + dependency (sudah ada bila kamu ikuti setup awal):
  ```bash
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  ```
- `config/.env` sudah berisi `EXCHANGE_DEMO_KEY` / `EXCHANGE_DEMO_SECRET`
  (testnet key dari testnet.binance.vision). JANGAN commit file ini.

## 1. Jalankan SATU kali (test cepat)
```bash
.venv\Scripts\activate
python serve.py --once
```
- Bot jalan 1 siklus: ambil data BTC/USDT → 6 agent analisis → bisa ENTRY/EXIT →
  tulis `logs/briefing.json`.
- Di terminal akan muncul ringkasan sinyal + status posisi.
- Tidak perlu buka dashboard untuk cek — tapi `briefing.json` sudah kebentuk.

## 2. Jalankan 24/7 + dashboard live
```bash
.venv\Scripts\activate
python serve.py
```
- Bot loop tiap **60 menit** (lihat `schedule.run_every_minutes`).
- HTTP server nyala di port **8000**.
- Buka browser: **http://localhost:8000/dashboard.html**
  → lihat 6 kartu agent nyala berurutan + posisi testnet nyata.
- Hentikan: tekan **Ctrl+C** di terminal.

## 3. Cek posisi / order di testnet (bukti nyata)
- Buka **https://testnet.binance.vision** → login GitHub.
- Menu **"Orders"** / **"Positions"** / **"Wallet"** → lihat order dari bot.
- Bandingkan dengan `logs/state.json` (posisi tersimpan di PC) & `logs/briefing.json`.

## 4. Cara berhenti / restart aman
- Berhenti: **Ctrl+C** (state posisi tetap tersimpan di `logs/state.json`).
- Restart: jalankan `python serve.py` lagi — bot ingat posisi terbuka (tidak dobel buka).
- Hapus posisi manual: edit/hapus `logs/state.json` lalu restart (hati-hati).

## 5. Ganti mode (paper / demo / live)
Edit `config/settings.yaml`:
```yaml
mode: paper   # simulasi lokal, tanpa net
mode: demo    # REAL MARKET testnet (default sekarang)
mode: live    # REAL MONEY — hanya bila demo stabil + isi EXCHANGE_LIVE_* + confirm_live_manually: true
```

## 6. Mode mock (offline, tanpa internet)
```bash
python serve.py --once --mock     # pakai data tiruan, untuk cek UI/logika
```

## 7. Troubleshoot
| Gejala | Solusi |
|--------|--------|
| `Failed to fetch` di dashboard | Bot belum jalan. Jalankan `python serve.py` dulu, lalu refresh. |
| `ModuleNotFoundError` | `.venv` aktif? `pip install -r requirements.txt`. |
| Posisi tidak muncul di testnet | Cek `EXCHANGE_DEMO_*` di `.env` benar & testnet key valid (bukan key live). |
| Bot diam (tidak ENTRY) | Normal bila RSI tidak masuk area oversold/overbought. Cek `logs/briefing.json`. |
| Mau ubah interval | `schedule.run_every_minutes` di `settings.yaml`. |

## 8. Keamanan (ingat!)
- `.env` di `.gitignore` — **jangan** commit.
- API testnet = **trade-only**, tanpa withdrawal.
- Ganti password GitHub/Gmail jika pernah ter-expose.
- Ini BUKAN nasihat keuangan. Uji di demo dulu, jangan live sebelum yakin.

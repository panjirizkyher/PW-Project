# CARA PUSH KE GITHUB — Trading Desk (PW-Project)

Repo lokal sudah siap: remote `origin` → github.com/panjirizkyher/PW-Project,
branch `main`. Tinggal push. Karena belum ada kredensial di environment, kamu
jalankan sendiri di terminal Windows (PowerShell/Git Bash) — butuh GitHub token.

## Langkah 1 — Buat Personal Access Token (PAT)
1. Buka: https://github.com/settings/tokens
2. Klik "Generate new token (classic)" → centang `repo` (full control of private repos).
3. Copy token (format: `ghp_xxxxxxxxxxxx`). SIMPAN, cuma muncul sekali.

## Langkah 2 — Push (Git Bash / terminal di folder trading-desk)
```bash
cd C:/Users/USER/trading-desk

# OPSI A: pakai token di URL (cepat, untuk sekali push)
git push https://ghp_xxxTOKENxxx@github.com/panjirizkyher/PW-Project.git main

# OPSI B: kalau repo target sudah ada file (README/LICENSE dari GitHub),
# pakai --force (HATI-HATI, menimpa) ATAU rebase dulu:
git pull origin main --rebase   # gabungkan dulu
git push origin main
```
Ganti `ghp_xxxTOKENxxx` dengan token asli kamu.

## Catatan keamanan
- JANGAN commit file `config/.env` (sudah di .gitignore).
- Token jangan dibagikan ke siapa pun.
- Secret (.env) tidak ikut ter-push.

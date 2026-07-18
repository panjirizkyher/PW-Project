# 🔐 Panduan Membuat API Key Binance (Trade-Only, Aman)

Panduan langkah-demi-langkah supaya agent PEWE bisa trading di akunmu **TANPA bisa menarik dana**.
Gunakan API Key + Secret — **bukan password akun Binance** (password tidak didukung & berbahaya).

> ⚠️ Aturan emas: **JANGAN pernah** centang "Enable Withdrawals". Password akun Binance **JANGAN PERNAH** dimasukkan ke dashboard.

---

## Opsi A — Akun TESTNET (DEMO, gratis, uang virtual)
Cocok buat coba agent tanpa risiko.

1. Buka https://testnet.binance.vision/
2. Klik **Log In** (gunakan akun GitHub atau Google).
3. Klik **Generate HMAC RSA / Create API Key**.
4. Copy **API Key** + **Secret Key** (secret muncul sekali).
5. Di dashboard PEWE → panel **Multi-Account Manager** → isi:
   - Nama: mis. `Testnet-Saya`
   - Mode: **DEMO**
   - API Key / Secret: paste dari testnet
6. Klik **Tambah & Aktifkan**.

---

## Opsi B — Akun BINANCE ASLI (LIVE)

### 1. Buat API Key
1. Login ke https://www.binance.com → klik **avatar** (kanan atas) → **API Management**.
2. Klik **Create API** → pilih **System generated** (default).
3. Beri nama: mis. `PEWE-Agent-1`.
4. Verifikasi dengan 2FA (Email/SMS/Google Authenticator).
5. **Simpan Secret sekarang** — Binance hanya menampilkannya SEKALI.

### 2. Batasi Izin (PENTING — biar tdk bisa withdraw)
1. Di baris API key → klik **Edit restrictions** (atau buka detail).
2. Pastikan:
   - ☑ **Enable Spot & Margin Trading** → ON
   - ☒ **Enable Withdrawals** → **OFF** (jangan dicentang!)
   - ☒ **Enable Futures** → ON hanya kalau mau futures (opsional)
3. Klik **Save**.

### 3. Batasi ke IP PC kamu (IP-Whitelist)
1. Di bagian **IP Access Restriction** → pilih **Restrict access to trusted IPs only**.
2. Tambahkan IP publik PC kamu:
   - Cek IP: buka https://api.ipify.org di browser PC tersebut.
   - Paste IP (mis. `203.0.113.45`) → Add.
3. Kalau IP berubah (dynamic ISP), ulangi atau biarkan "Unrestricted" (lebih riskan — hanya jika yakin PC aman).

> 💡 Tips: kalau PC pakai internet ber-IP berubah, pakai VPS/sever dengan IP statis untuk host bot, lalu whitelist IP VPS.

### 4. Masukkan ke Dashboard PEWE
1. Buka dashboard → panel **Multi-Account Manager**.
2. Isi:
   - Nama: `Akun-Asli-1`
   - Mode: **LIVE**
   - API Key / Secret: paste dari Binance
3. Klik **Tambah & Aktifkan**.
4. Bot akan pakai akun ini di siklus berikutnya (tanpa restart).

---

## 🔒 Verifikasi Keamanan
- Di panel akun, pastikan ada badge **🔒 WITHDRAW DISABLED** (fitur agent mencegah withdraw).
- Coba withdraw dari Binance langsung → harus tetap bisa (karena dashboard tdk pegang izin itu).
- Secret di dashboard **selalu di-mask** (mis. `Xq2k****W9pL`) — tdk pernah ditampilkan utuh.

## 🛡️ Jika Secret Bocor / Mau Ganti
1. Di Binance → **API Management** → hapus/regenerate key lama.
2. Di dashboard → **Hapus** akun lama, **Tambah** dengan key baru.
3. (Wajib) Jika secret pernah ke-paste di chat → **regenerate segera** di Binance.

## ❓ FAQ
**Q: Harus punya API key tiap orang?** Ya — setiap akun Binance butuh API key sendiri (standar semua platform: 3Commas, Pionex, dll). Otak agent dipakai bersama, eksekusi per-akun.

**Q: Bisa pakai password Binance?** Tidak. Binance tidak mendukung login password untuk trading otomatis, dan menyimpan password = risiko saldo dibawa lari.

**Q: Agent bisa tarik dana?** Tidak. Selama "Enable Withdrawals" OFF, agent hanya bisa trade. Withdraw tetap lewat Binance langsung.

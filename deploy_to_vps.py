#!/usr/bin/env python
"""
deploy_to_vps.py — Deploy PEWE trading-desk dari PC (dev) ke VPS (master 24/7).

Pipeline aman: cek git bersih -> transfer kode -> restart bot -> VERIFY.
Kalau verify gagal, exit != 0 (deploy dianggap GAGAL, bukan diem-diem rusak).

Usage:
  python deploy_to_vps.py            # deploy penuh (kode + restart + verify)
  python deploy_to_vps.py --no-git   # skip cek git bersih (buat testing)
  python deploy_to_vps.py --verify   # cuma verify VPS, gak transfer/restart

SAFETY:
  - Config demo-lock: preflight_demo.py di VPS tetap jaga (bot refuse kalau live).
  - .env & accounts.json TIDAK di-overwrite default (biar creds VPS aman);
    pakai --with-config kalau memang mau push config baru.
"""
import os, sys, subprocess, posixpath, time, json
import paramiko

# --- Kredensial VPS dibaca dari file gitignored: config/vps.json ---
# Format: {"host": "...", "user": "Administrator", "password": "...", "port": 22}
# JANGAN hardcode password di sini (biar gak bocor ke git).
def _load_vps():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "vps.json")
    if not os.path.exists(p):
        print(f"[ERROR] Kredensial VPS gak ada: {p}")
        print('        Bikin file itu isi: {"host":"IP","user":"Administrator","password":"...","port":22}')
        sys.exit(2)
    with open(p, encoding="utf-8") as f:
        return json.load(f)

_vps = _load_vps()
HOST = _vps["host"]
USER = _vps.get("user", "Administrator")
PWD  = _vps["password"]
PORT = _vps.get("port", 22)
LOCAL  = r"C:\Users\USER\trading-desk"
REMOTE = "C:/Users/Administrator/trading-desk"
DOMAIN = "https://pwproject.my.id"

SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "node_modules", ".mypy_cache"}
# secret/config: skip by default (jangan timpa creds VPS)
SKIP_FILES_DEFAULT = {"config/.env", "config/accounts.json"}

def sh(cmd, cwd=LOCAL):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    return r.returncode, (r.stdout or "") + (r.stderr or "")

def connect():
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, port=PORT, username=USER, password=PWD, timeout=30,
                look_for_keys=False, allow_agent=False)
    return cli

def run_remote(cli, cmd, timeout=120):
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err

def ps(cli, script, timeout=120):
    # jalanin PowerShell command di VPS
    cmd = 'powershell -NoProfile -Command "{}"'.format(script.replace('"', '\\"'))
    return run_remote(cli, cmd, timeout)

# ---------- STEP 1: git clean check ----------
def check_git_clean():
    rc, out = sh("git status --short")
    dirty = [l for l in out.splitlines() if l.strip()]
    if dirty:
        print("[GIT] Working tree KOTOR — commit dulu sebelum deploy:")
        for l in dirty: print("   ", l)
        return False
    rc, head = sh("git log --oneline -1")
    print(f"[GIT] Bersih. HEAD: {head.strip()}")
    return True

# ---------- STEP 2: transfer kode ----------
def transfer(cli, with_config=False):
    sftp = cli.open_sftp()
    def mkdirs(path):
        cur = ""
        for p in path.split("/"):
            if not p: continue
            cur = cur + "/" + p if cur else p
            if len(cur) < 3 and cur.endswith(":"): continue
            try: sftp.stat(cur)
            except IOError:
                try: sftp.mkdir(cur)
                except IOError: pass
    sent = skipped = 0
    for root, dirs, files in os.walk(LOCAL):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(root, LOCAL).replace("\\", "/")
        rdir = REMOTE if rel == "." else posixpath.join(REMOTE, rel)
        mkdirs(rdir)
        for f in files:
            relf = (rel + "/" + f) if rel != "." else f
            # skip logs json (state fresh di VPS)
            if "/logs" in rdir.replace("\\","/") and f.endswith(".json"):
                skipped += 1; continue
            # skip secret/config kecuali --with-config
            if not with_config and relf in SKIP_FILES_DEFAULT:
                skipped += 1; continue
            lpath = os.path.join(root, f)
            try:
                if os.path.getsize(lpath) > 60*1024*1024:  # skip >60MB
                    skipped += 1; continue
                sftp.put(lpath, posixpath.join(rdir, f))
                sent += 1
            except Exception as e:
                print(f"[TRANSFER] FAIL {relf}: {e}")
    sftp.close()
    print(f"[TRANSFER] sent={sent} skipped={skipped}")
    return sent

# ---------- STEP 3: restart bot ----------
def restart_bot(cli):
    print("[RESTART] stopping bot di VPS...")
    ps(cli, "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force", 40)
    time.sleep(3)
    print("[RESTART] starting bot via task scheduler...")
    run_remote(cli, 'schtasks /Run /TN "PEWE-Bot-Demo"', 30)
    time.sleep(15)

# ---------- STEP 4: verify ----------
def verify(cli):
    ok = True
    # 4a. import check (semua modul inti bisa di-load) — tulis script ke VPS lalu jalankan
    sftp = cli.open_sftp()
    chk = ("from core.ml import parameter_optimizer, regime_detector, signal_filter\n"
           "from core import montecarlo\n"
           "from agents import phoenix\n"
           "import data.sentiment\n"
           "print('IMPORTS-OK')\n")
    remote_chk = REMOTE + "/_deploy_importcheck.py"
    with sftp.open(remote_chk, "w") as f:
        f.write(chk)
    sftp.close()
    rc, out, err = ps(cli, "cd C:/Users/Administrator/trading-desk; .\\.venv\\Scripts\\python.exe _deploy_importcheck.py", 60)
    if "IMPORTS-OK" in out:
        print("[VERIFY] imports OK")
    else:
        print(f"[VERIFY] imports FAIL: {out.strip()} {err.strip()}"); ok = False
    # cleanup
    run_remote(cli, 'del "C:\\Users\\Administrator\\trading-desk\\_deploy_importcheck.py"', 20)
    # 4b. preflight demo guard
    rc, out, err = ps(cli, "cd C:/Users/Administrator/trading-desk; .\\.venv\\Scripts\\python.exe preflight_demo.py", 40)
    if "OK" in out and "demo" in out.lower():
        print("[VERIFY] preflight demo OK")
    else:
        print(f"[VERIFY] preflight FAIL: {out.strip()}"); ok = False
    # 4c. bot serving lokal 200
    rc, out, err = ps(cli, "try { (Invoke-WebRequest http://127.0.0.1:8731/dashboard.html -UseBasicParsing -TimeoutSec 8).StatusCode } catch { 'DOWN' }", 30)
    if "200" in out:
        print("[VERIFY] bot serving lokal 200")
    else:
        print(f"[VERIFY] bot serving FAIL: {out.strip()}"); ok = False
    # 4d. domain publik 200 (dari sisi PC ini)
    rc, out = sh(f'curl -s -o /dev/null -w "%{{http_code}}" "{DOMAIN}/dashboard.html?t=deploy_verify" --max-time 20')
    if out.strip() == "200":
        print("[VERIFY] domain publik 200")
    else:
        print(f"[VERIFY] domain FAIL: {out.strip()} (tunnel mungkin perlu restart)"); ok = False
    return ok

def main():
    args = sys.argv[1:]
    verify_only = "--verify" in args
    no_git = "--no-git" in args
    with_config = "--with-config" in args

    print("=" * 55)
    print("  DEPLOY PEWE trading-desk -> VPS master (24/7)")
    print("=" * 55)

    if verify_only:
        cli = connect()
        ok = verify(cli); cli.close()
        print("\nRESULT:", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)

    # STEP 1
    if not no_git and not check_git_clean():
        print("\n[ABORT] commit dulu, baru deploy.")
        sys.exit(1)

    cli = connect()
    # STEP 2
    transfer(cli, with_config=with_config)
    # STEP 3
    restart_bot(cli)
    # STEP 4
    ok = verify(cli)
    cli.close()

    print("\n" + "=" * 55)
    print("  DEPLOY RESULT:", "✅ PASS — master VPS ter-update" if ok else "❌ FAIL — cek log di atas")
    print("=" * 55)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()

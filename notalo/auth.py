"""회원·크레딧. 표준 라이브러리만 (sqlite3, hashlib, smtplib, urllib).
- 비가입 1회: 쿠키 nt_used + 지문(IP+UA+언어 해시) 둘 다 기록, 하나라도 있으면 0회
- 가입: 이메일+비번(scrypt). 인증 링크 클릭 시에만 credits=2 (한 번만). Google 로그인은 인증 완료로 간주
- 세션: 서명 쿠키 nt_user=<email>.<hmac> (서버 세션 테이블 없음)
ponytail: SQLite 파일. 컨테이너 재배포 시 날아감 → 결제 붙일 때 외부 DB로."""
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import sqlite3
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
_env = os.path.join(HERE, ".env")  # 로컬용. 배포는 컨테이너 환경변수(GitHub 시크릿)
if os.path.exists(_env):
    for line in open(_env):
        k, _, v = line.strip().partition("=")
        if k and not k.startswith("#"):
            os.environ.setdefault(k, v.strip().strip('"'))

SECRET = (os.environ.get("NOTALO_SECRET") or "dev-secret").encode()
DB = os.environ.get("NOTALO_DB", os.path.join(HERE, "notalo.db"))

# ---- SQLite 파일을 Lightsail 버킷(S3 호환)에 동기화. 컨테이너 디스크는 재배포 때 사라지므로 ----
# 시작: 버킷에 있으면 내려받음 / 쓰기(INSERT·UPDATE)가 있었던 연결이 닫힐 때마다 올림. 컨테이너 1대 전제.
BUCKET = os.environ.get("NOTALO_BUCKET")
_s3 = None
_err = lambda e: getattr(e, "response", {}).get("Error", {}).get("Code") or type(e).__name__
if BUCKET:
    import boto3
    _s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION"),
                       aws_access_key_id=os.environ.get("NOTALO_BUCKET_KEY_ID") or None,
                       aws_secret_access_key=os.environ.get("NOTALO_BUCKET_KEY_SECRET") or None)
    try:
        _s3.download_file(BUCKET, "notalo.db", DB)
        print("[db] 버킷에서 내려받음", flush=True)
    except Exception as e:  # 404 = 아직 파일 없음(처음이면 정상). 403/AccessDenied = 키·권한 문제
        print(f"[db] 버킷에 파일 없음 또는 못 읽음 ({_err(e)}): 새 DB로 시작", flush=True)
    try:  # 쓰기 권한 확인
        _s3.put_object(Bucket=BUCKET, Key=".ping", Body=b"")
        print("[db] 버킷 쓰기 OK", flush=True)
    except Exception as e:
        print(f"[db] 버킷 쓰기 실패 ({_err(e)}): 회원 데이터가 재배포 때 사라짐. 키/버킷 이름 확인 필요", flush=True)


class _Conn:
    """with db() as con: ... → 나갈 때 커밋, 변경 있었으면 버킷에 업로드."""

    def __enter__(self):
        self.con = sqlite3.connect(DB)
        self.con.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, salt BLOB, pw BLOB, verified INT DEFAULT 0, "
                         "google INT DEFAULT 0, credits INT DEFAULT 0, created REAL)")
        self.con.execute("CREATE TABLE IF NOT EXISTS guests(fp TEXT PRIMARY KEY, used INT DEFAULT 0, first REAL)")
        self.con.commit()
        self.n0 = self.con.total_changes
        return self.con

    def __exit__(self, *exc):
        changed = self.con.total_changes != self.n0
        self.con.commit() if not exc[0] else self.con.rollback()
        self.con.close()
        if changed and _s3 and not exc[0]:
            try:
                _s3.upload_file(DB, BUCKET, "notalo.db")
            except Exception as e:  # 버킷이 잠깐 안 되더라도 서비스는 계속
                print(f"[db] 버킷 업로드 실패 ({_err(e)})", flush=True)
SMTP_USER, SMTP_PASS = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GUEST_FREE, SIGNUP_BONUS = 1, 2
COOKIE_AGE = 30 * 24 * 3600
router = APIRouter()
rate_limit = lambda request: None  # app.py가 IP 레이트리밋 함수 주입


def db():
    return _Conn()


def _hash(pw, salt):
    return hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1)


def _sig(s):
    return hmac.new(SECRET, s.encode(), hashlib.sha256).hexdigest()[:24]


# ---- 세션 ----
def current_user(request):
    email, _, sig = request.cookies.get("nt_user", "").rpartition(".")
    return email if email and hmac.compare_digest(sig, _sig(email)) else None


def _set_user(resp, email):
    resp.set_cookie("nt_user", f"{email}.{_sig(email)}", max_age=COOKIE_AGE, httponly=True, samesite="lax")
    return resp


def _user_row(email):
    with db() as con:
        return con.execute("SELECT verified, credits, google FROM users WHERE email=?", (email,)).fetchone()


# ---- 비가입 1회 ----
def fingerprint(request):
    ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    raw = "|".join([ip, request.headers.get("user-agent", ""), request.headers.get("accept-language", "")])
    return hashlib.sha256(raw.encode()).hexdigest()


def guest_used(request):
    n, _, sig = request.cookies.get("nt_used", "").partition(".")
    by_cookie = int(n) if n.isdigit() and hmac.compare_digest(sig, _sig(n)) else 0
    with db() as con:
        row = con.execute("SELECT used FROM guests WHERE fp=?", (fingerprint(request),)).fetchone()
    return max(by_cookie, row[0] if row else 0)


def guest_mark(request, resp):
    used = guest_used(request) + 1
    with db() as con:
        con.execute("INSERT INTO guests(fp,used,first) VALUES(?,?,?) ON CONFLICT(fp) DO UPDATE SET used=?",
                    (fingerprint(request), used, time.time(), used))
    resp.set_cookie("nt_used", f"{used}.{_sig(str(used))}", max_age=365 * 24 * 3600, httponly=True, samesite="lax")


# ---- 크레딧 (app.py가 씀) ----
def credits(request):
    """{'left', 'user', 'verified'}"""
    email = current_user(request)
    if email:
        row = _user_row(email)
        if row:
            return {"left": row[1], "user": email, "verified": bool(row[0])}
    return {"left": max(GUEST_FREE - guest_used(request), 0), "user": None, "verified": False}


def spend(request, resp):
    """변환 성공 후 1회 차감. 잔여 없으면 False."""
    email = current_user(request)
    row = _user_row(email) if email else None
    if row:
        if not row[0] or row[1] <= 0:
            return False
        with db() as con:
            con.execute("UPDATE users SET credits=credits-1 WHERE email=? AND credits>0", (email,))
        return True
    if guest_used(request) >= GUEST_FREE:
        return False
    guest_mark(request, resp)
    return True


# ---- 메일 ----
def _send(to, subject, body):
    if not SMTP_USER:  # 로컬 개발: 메일 대신 로그
        print(f"[mail] to={to} subject={subject}\n{body}", flush=True)
        return
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = f"Notalo <{SMTP_USER}>", to, subject
    m.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(m)


def _send_verify(request, email):
    exp = int(time.time() + 24 * 3600)
    body = f"{email}|{exp}"
    token = urllib.parse.quote(f"{body}|{_sig(body)}", safe="")
    link = f"{str(request.base_url).rstrip('/')}/verify?token={token}"
    _send(email, "Notalo 가입 인증", f"아래 링크를 누르면 가입이 끝나고 무료 {SIGNUP_BONUS}회가 지급됩니다. (24시간 안에)\n\n{link}\n\n"
                                  "본인이 요청한 게 아니면 이 메일은 무시하세요.")


# ---- 엔드포인트 ----
class Cred(BaseModel):
    email: str
    password: str = ""


@router.get("/auth/config")
def config():
    return {"google_client_id": GOOGLE_CLIENT_ID}


@router.post("/signup")
def signup(c: Cred, request: Request):
    rate_limit(request)
    email = c.email.strip().lower()
    if "@" not in email or "." not in email.rpartition("@")[2] or len(c.password) < 8:
        raise HTTPException(400, "이메일 형식과 8자 이상 비밀번호를 확인해 주세요.")
    with db() as con:
        row = con.execute("SELECT verified FROM users WHERE email=?", (email,)).fetchone()
        if row and row[0]:
            raise HTTPException(409, "이미 가입된 이메일입니다. 로그인해 주세요.")
        salt = secrets.token_bytes(16)
        con.execute("INSERT OR REPLACE INTO users(email,salt,pw,verified,google,credits,created) VALUES(?,?,?,0,0,0,?)",
                    (email, salt, _hash(c.password, salt), time.time()))
    _send_verify(request, email)
    return _set_user(Response(json.dumps({"ok": True}), media_type="application/json"), email)


@router.post("/resend")
def resend(c: Cred, request: Request):
    rate_limit(request)
    email = c.email.strip().lower()
    row = _user_row(email)
    if not row or row[0]:
        raise HTTPException(400, "인증 대기 중인 계정이 아닙니다.")
    _send_verify(request, email)
    return {"ok": True}


@router.get("/verify")
def verify(token: str):
    try:
        email, exp, sig = token.split("|")
    except ValueError:
        raise HTTPException(400, "링크가 잘못됐습니다.")
    if not hmac.compare_digest(sig, _sig(f"{email}|{exp}")) or int(exp) < time.time():
        raise HTTPException(400, "링크가 만료됐거나 잘못됐습니다. 인증 메일을 다시 보내 주세요.")
    with db() as con:
        # 인증 완료 순간에만, 한 번만 지급
        con.execute("UPDATE users SET verified=1, credits=credits+? WHERE email=? AND verified=0", (SIGNUP_BONUS, email))
    return _set_user(RedirectResponse("/?verified=1", status_code=303), email)


@router.post("/login")
def login(c: Cred, request: Request):
    rate_limit(request)
    email = c.email.strip().lower()
    with db() as con:
        row = con.execute("SELECT salt,pw,verified,google FROM users WHERE email=?", (email,)).fetchone()
    if row and row[3] and not row[1]:
        raise HTTPException(401, "Google로 가입한 계정이에요. Google로 계속하기를 눌러 주세요.")
    if not row or not hmac.compare_digest(_hash(c.password, row[0]), row[1]):
        raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않습니다.")
    resp = _set_user(Response(json.dumps({"email": email, "verified": bool(row[2])}), media_type="application/json"), email)
    return resp


@router.post("/logout")
def logout():
    r = Response(status_code=204)
    r.delete_cookie("nt_user")
    return r


class GoogleCred(BaseModel):
    credential: str


@router.post("/login/google")
def login_google(g: GoogleCred):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google 로그인은 준비 중입니다.")
    try:
        with urllib.request.urlopen("https://oauth2.googleapis.com/tokeninfo?id_token=" + urllib.parse.quote(g.credential), timeout=10) as r:
            info = json.load(r)
    except Exception:
        raise HTTPException(401, "Google 인증에 실패했습니다.")
    if info.get("aud") != GOOGLE_CLIENT_ID or info.get("email_verified") != "true":
        raise HTTPException(401, "Google 인증에 실패했습니다.")
    email = info["email"].lower()
    with db() as con:
        con.execute("INSERT OR IGNORE INTO users(email,salt,pw,verified,google,credits,created) VALUES(?,?,?,0,1,0,?)", (email, b"", b"", time.time()))
        con.execute("UPDATE users SET google=1, verified=1, credits=credits+? WHERE email=? AND verified=0", (SIGNUP_BONUS, email))
    return _set_user(Response(json.dumps({"email": email, "verified": True}), media_type="application/json"), email)

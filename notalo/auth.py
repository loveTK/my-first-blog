"""이메일+비밀번호(인증 메일) / Google 로그인. 표준 라이브러리만 (sqlite3, hashlib, smtplib, urllib).
세션 = HMAC 서명 쿠키 nt_user (서버 상태 없음). ponytail: SQLite 파일. 컨테이너 재배포 시 날아감 → 결제 붙일 때 외부 DB로."""
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

router = APIRouter(prefix="/auth")
SECRET = (os.environ.get("NOTALO_SECRET") or "dev-secret").encode()
DB = os.environ.get("NOTALO_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "notalo.db"))
SMTP_USER, SMTP_PASS = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
COOKIE_AGE = 30 * 24 * 3600


def db():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, salt BLOB, pw BLOB, verified INT DEFAULT 0, google INT DEFAULT 0, created REAL)")
    return c


def _hash(pw, salt):
    return hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1)


def _sig(s):
    return hmac.new(SECRET, s.encode(), hashlib.sha256).hexdigest()[:24]


def _token(email, exp):  # 인증 링크용. 서버에 저장 안 함
    body = f"{email}|{exp}"
    return urllib.parse.quote(f"{body}|{_sig(body)}", safe="")


def _parse_token(t):
    try:
        email, exp, sig = t.split("|")
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sig(f"{email}|{exp}")) or float(exp) < time.time():
        return None
    return email


def current_user(request: Request):
    email, _, sig = request.cookies.get("nt_user", "").rpartition(".")
    return email if email and hmac.compare_digest(sig, _sig(email)) else None


def _set_user(resp, email):
    resp.set_cookie("nt_user", f"{email}.{_sig(email)}", max_age=COOKIE_AGE, httponly=True, samesite="lax")
    return resp


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


class Cred(BaseModel):
    email: str
    password: str


@router.get("/config")
def config():
    return {"google_client_id": GOOGLE_CLIENT_ID, "email": bool(SMTP_USER) or os.environ.get("NOTALO_DEV") == "1"}


@router.get("/me")
def me(request: Request):
    return {"email": current_user(request)}


@router.post("/logout")
def logout():
    r = Response(status_code=204)
    r.delete_cookie("nt_user")
    return r


@router.post("/signup")
def signup(c: Cred, request: Request):
    email = c.email.strip().lower()
    if "@" not in email or len(c.password) < 8:
        raise HTTPException(400, "이메일 형식과 8자 이상 비밀번호를 확인해 주세요.")
    with db() as con:
        row = con.execute("SELECT verified FROM users WHERE email=?", (email,)).fetchone()
        if row and row[0]:
            raise HTTPException(409, "이미 가입된 이메일입니다. 로그인해 주세요.")
        salt = secrets.token_bytes(16)
        con.execute("INSERT OR REPLACE INTO users(email,salt,pw,verified,google,created) VALUES(?,?,?,0,0,?)",
                    (email, salt, _hash(c.password, salt), time.time()))
    link = f"{str(request.base_url).rstrip('/')}/auth/verify?t={_token(email, time.time() + 24 * 3600)}"
    _send(email, "Notalo 가입 인증", f"아래 링크를 누르면 가입이 끝납니다. (24시간 안에)\n\n{link}\n\n본인이 요청한 게 아니면 이 메일은 무시하세요.")
    return {"ok": True}


@router.get("/verify")
def verify(t: str):
    email = _parse_token(t)
    if not email:
        raise HTTPException(400, "링크가 만료됐거나 잘못됐습니다. 다시 가입해 주세요.")
    with db() as con:
        con.execute("UPDATE users SET verified=1 WHERE email=?", (email,))
    return _set_user(RedirectResponse("/?verified=1", status_code=303), email)


@router.post("/login")
def login(c: Cred):
    email = c.email.strip().lower()
    with db() as con:
        row = con.execute("SELECT salt,pw,verified,google FROM users WHERE email=?", (email,)).fetchone()
    if not row or row[3] or not hmac.compare_digest(_hash(c.password, row[0]), row[1]):
        raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않습니다." + (" Google로 가입한 계정이에요." if row and row[3] else ""))
    if not row[2]:
        raise HTTPException(403, "아직 이메일 인증이 안 됐어요. 메일함의 인증 링크를 눌러 주세요.")
    return _set_user(Response(json.dumps({"email": email}), media_type="application/json"), email)


class GoogleCred(BaseModel):
    credential: str


@router.post("/google")
def google(g: GoogleCred):
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
        con.execute("INSERT OR IGNORE INTO users(email,salt,pw,verified,google,created) VALUES(?,?,?,1,1,?)", (email, b"", b"", time.time()))
        con.execute("UPDATE users SET verified=1, google=1 WHERE email=?", (email,))
    return _set_user(Response(json.dumps({"email": email}), media_type="application/json"), email)

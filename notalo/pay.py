"""PayPal 결제 → 계정 크레딧 충전. 표준 라이브러리 urllib만.
흐름: 프론트 PayPal 버튼 → POST /pay/order(서버가 주문 생성, 금액은 서버 표) → 구매자 승인 → POST /pay/capture(서버가 확정 후 크레딧 +n).
통화 USD (PayPal은 KRW 결제 미지원). orders 테이블에 주문 id 저장해 같은 주문 두 번 충전 방지.
PAYPAL_ENV=sandbox|live, PAYPAL_CLIENT_ID, PAYPAL_SECRET 는 환경변수(GitHub 시크릿)."""
import base64
import json
import os
import time
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import auth

PLANS = {"starter": (5, "7.49", "스타터"), "standard": (30, "29.00", "스탠다드"), "pro": (100, "74.00", "프로")}  # 이름: (크레딧, USD, 표시명)
CLIENT_ID, SECRET = os.environ.get("PAYPAL_CLIENT_ID"), os.environ.get("PAYPAL_SECRET")
ENV = os.environ.get("PAYPAL_ENV", "sandbox")
API = "https://api-m.paypal.com" if ENV == "live" else "https://api-m.sandbox.paypal.com"
router = APIRouter()
_tok = {"v": "", "exp": 0}


def _pp(method, path, body=None):
    """PayPal REST 호출. 토큰은 만료 전까지 재사용."""
    if _tok["exp"] < time.time():
        basic = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
        req = urllib.request.Request(API + "/v1/oauth2/token", b"grant_type=client_credentials",
                                     {"Authorization": "Basic " + basic}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            t = json.load(r)
        _tok.update(v=t["access_token"], exp=time.time() + t["expires_in"] - 60)
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None,
                                 {"Authorization": "Bearer " + _tok["v"], "Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _me(request):
    email = auth.current_user(request)
    if not email or not auth._user_row(email):
        raise HTTPException(401, "구매하려면 먼저 로그인하세요.")
    return email


class Order(BaseModel):
    plan: str


class Capture(BaseModel):
    order_id: str


@router.get("/pay/config")
def config():
    return {"client_id": CLIENT_ID, "env": ENV, "currency": "USD",
            "plans": {k: {"credits": n, "usd": usd, "name": name} for k, (n, usd, name) in PLANS.items()}}


@router.post("/pay/order")
def order(o: Order, request: Request):
    if not CLIENT_ID:
        raise HTTPException(503, "결제는 준비 중입니다.")
    email = _me(request)
    if o.plan not in PLANS:
        raise HTTPException(400, "없는 요금제입니다.")
    n, usd, name = PLANS[o.plan]
    try:
        r = _pp("POST", "/v2/checkout/orders", {"intent": "CAPTURE", "purchase_units": [{
            "custom_id": f"{email}|{o.plan}", "description": f"Notalo {name} {n}회",
            "amount": {"currency_code": "USD", "value": usd}}]})
    except Exception as e:
        print(f"[pay] 주문 생성 실패 ({type(e).__name__}: {e})", flush=True)
        raise HTTPException(502, "결제 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.")
    return {"id": r["id"]}


@router.post("/pay/capture")
def capture(c: Capture, request: Request):
    email = _me(request)
    try:
        r = _pp("POST", f"/v2/checkout/orders/{c.order_id}/capture", {})
    except Exception as e:
        print(f"[pay] 확정 실패 ({type(e).__name__}: {e})", flush=True)
        raise HTTPException(502, "결제 확정에 실패했습니다. 결제가 됐다면 잠시 후 새로고침해 보세요.")
    unit = r.get("purchase_units", [{}])[0]
    cap = unit.get("payments", {}).get("captures", [{}])[0]
    owner, _, plan = (cap.get("custom_id") or unit.get("custom_id") or "").partition("|")
    if r.get("status") != "COMPLETED" or owner != email or plan not in PLANS:
        raise HTTPException(400, "결제가 완료되지 않았습니다.")
    n = PLANS[plan][0]
    with auth.db() as con:
        if con.execute("SELECT 1 FROM orders WHERE id=?", (r["id"],)).fetchone():
            return {"credited": 0, "left": auth._user_row(email)[1]}  # 이미 충전한 주문
        con.execute("INSERT INTO orders(id,email,plan,usd,created) VALUES(?,?,?,?,?)", (r["id"], email, plan, PLANS[plan][1], time.time()))
        con.execute("UPDATE users SET credits=credits+? WHERE email=?", (n, email))
    print(f"[pay] {email} {plan} +{n} ({r['id']})", flush=True)
    return {"credited": n, "left": auth._user_row(email)[1]}

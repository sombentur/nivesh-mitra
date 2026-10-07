"""Your mutual fund plan and the SIP calculator (doc 03 §C6–C7)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db.base import get_db
from app.db.models import User
from app.engines import plan as eng
from app.services import plan as svc

router = APIRouter(prefix="/api/plan", tags=["plan"])


class SipCalc(BaseModel):
    monthly: int = Field(ge=0, le=10_000_000)
    years: int = Field(ge=1, le=50)
    corpus: int = Field(default=0, ge=0, le=10_000_000_000)
    step_up: float = Field(default=0.0, ge=0, le=0.5)  # yearly increase of the SIP, e.g. 0.10
    mix: dict[str, int] | None = None  # slot → percent; default: a Nifty 50 index fund


@router.get("")
def get_plan(db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        return svc.build_plan(db, user)
    except svc.PlanUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("/sip-calculator")
def sip_calculator(body: SipCalc, user: User = Depends(current_user)):
    r = svc.rules()
    mix = body.mix or {"nifty_50_index": 100}
    if set(mix) - set(r["slots"]) or sum(mix.values()) != 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The mix must use known fund types and add up to 100%")
    rates = eng.blended_rates(mix, r)
    out = []
    for label, rate in zip(("conservative", "expected", "optimistic"), rates):
        value, invested, sip = float(body.corpus), float(body.corpus), float(body.monthly)
        i = eng.monthly_rate(rate)
        for month in range(body.years * 12):
            if month and month % 12 == 0:
                sip *= 1 + body.step_up
            value = (value + sip) * (1 + i)
            invested += sip
        out.append({"scenario": label, "rate": round(rate, 4), "value": round(value), "invested": round(invested)})
    return {"mix": mix, "scenarios": out, "note": "Assumed yearly returns, before tax. Not a promise — real returns vary year to year."}

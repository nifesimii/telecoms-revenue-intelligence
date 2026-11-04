"""Sign-in, sign-out and the current session for the two-login presentation."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend import config
from backend.auth import access, session

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=200)


class SessionResponse(BaseModel):
    username: str
    role: str
    account_code: str | None


@router.post("/login", response_model=SessionResponse)
def login(body: LoginRequest, response: Response) -> dict:
    try:
        principal = session.authenticate(body.username, body.password)
    except session.LoginsNotConfigured:
        raise HTTPException(status_code=503, detail="Sign-in is not configured.") from None
    if principal is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    response.set_cookie(
        session.COOKIE_NAME,
        session.issue_token(principal),
        max_age=session.SESSION_LIFETIME_SECONDS,
        httponly=True,
        samesite="lax",
        secure=config.HOSTED_DEPLOYMENT,
    )
    return asdict(principal)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(session.COOKIE_NAME, httponly=True, samesite="lax", secure=config.HOSTED_DEPLOYMENT)


@router.get("/session", response_model=SessionResponse)
def current_session(request: Request) -> dict:
    return asdict(access.current_principal(request))

"""
backend/routers/auth_router.py
------------------------------
Routes:
  POST /auth/signup          → email + password registration
  POST /auth/signin          → email + password login (returns JWT)
  GET  /auth/google          → redirect to Google OAuth consent screen
  GET  /auth/google/callback → exchange code for token, upsert user
  GET  /auth/me              → return current user info (requires auth)
"""

import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

from backend.database import get_db
from backend import models, schemas
from backend.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user_required,
)
from backend.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    FRONTEND_URL,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Google OAuth client ───────────────────────────────────────────────────────
_oauth_config = Config(environ={
    "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
    "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET,
})
oauth = OAuth(_oauth_config)
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def _create_token_response(user: models.User) -> schemas.TokenResponse:
    token = create_access_token({"sub": user.id, "email": user.email})
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserPublic.model_validate(user),
    )


# ── Email / Password routes ───────────────────────────────────────────────────

@router.post("/signup", response_model=schemas.TokenResponse,
             status_code=status.HTTP_201_CREATED)
def signup(body: schemas.SignUpRequest, db: Session = Depends(get_db)):
    if _get_user_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    user = models.User(
        email=body.email,
        name=body.name,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _create_token_response(user)


@router.post("/signin", response_model=schemas.TokenResponse)
def signin(body: schemas.SignInRequest, db: Session = Depends(get_db)):
    user = _get_user_by_email(db, body.email)
    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return _create_token_response(user)


# ── Google OAuth routes ───────────────────────────────────────────────────────

@router.get("/google")
async def google_login(request: Request):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured on this server.",
        )
    from urllib.parse import urlparse
    parsed_redirect = urlparse(GOOGLE_REDIRECT_URI)
    redirect_netloc = parsed_redirect.netloc
    current_netloc = request.headers.get("host") or request.url.netloc

    # Ensure /auth/google runs on the same domain as GOOGLE_REDIRECT_URI
    # so the session cookie matches the domain on the callback
    if redirect_netloc and current_netloc and current_netloc != redirect_netloc:
        target_url = f"{parsed_redirect.scheme or 'http'}://{redirect_netloc}/auth/google"
        return RedirectResponse(url=target_url)

    redirect_uri = GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    target_frontend = (FRONTEND_URL or "").rstrip("/")
    if request.url.hostname == "localhost" and "127.0.0.1" in target_frontend:
        target_frontend = target_frontend.replace("127.0.0.1", "localhost")
    elif request.url.hostname == "127.0.0.1" and "localhost" in target_frontend:
        target_frontend = target_frontend.replace("localhost", "127.0.0.1")

    try:
        token_data = await oauth.google.authorize_access_token(request)
    except Exception as exc:
        err_msg = str(exc)
        # Give the user a human-readable hint for the most common errors
        if "mismatching_state" in err_msg or "CSRF" in err_msg:
            err_msg = "OAuth session expired or was used twice. Please try signing in again."
        from urllib.parse import quote
        return RedirectResponse(
            url=f"{target_frontend}/?auth_error={quote(err_msg)}"
        )

    user_info = token_data.get("userinfo") or {}
    email: str = user_info.get("email", "")
    name: str = user_info.get("name", "")
    provider_id: str = user_info.get("sub", "")

    if not email:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"{target_frontend}/?auth_error={quote('Could not retrieve email from Google.')}"
        )

    # Upsert user
    user = _get_user_by_email(db, email)
    if not user:
        user = models.User(
            email=email,
            name=name,
            provider="google",
            provider_id=provider_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update provider info if they later log in via Google
        user.provider = user.provider or "google"
        user.provider_id = user.provider_id or provider_id
        user.name = user.name or name
        db.commit()
        db.refresh(user)

    jwt_token = create_access_token({"sub": user.id, "email": user.email})
    # Redirect back to frontend with the token in the URL fragment
    return RedirectResponse(
        url=f"{target_frontend}/auth/callback#token={jwt_token}"
    )


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=schemas.UserPublic)
def get_me(
    payload: dict = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return schemas.UserPublic.model_validate(user)

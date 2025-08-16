import base64
import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional

import boto3
import httpx
from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field

# Load environment variables from .env file
load_dotenv()


router = APIRouter(tags=["auth"])


# --- Config ---
AWS_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET", None)

print(f"Starting auth module with configuration:")
print(f"AWS_REGION: {AWS_REGION}")
print(f"COGNITO_USER_POOL_ID: {COGNITO_USER_POOL_ID}")
print(f"COGNITO_CLIENT_ID: {COGNITO_CLIENT_ID}")
print(f"COGNITO_CLIENT_SECRET: {'configured' if COGNITO_CLIENT_SECRET else 'not configured'}")

if not (AWS_REGION and COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID):
    # Delay hard failure to runtime endpoint usage so service can still start for non-auth paths
    pass


def _secret_hash(username: str) -> Optional[str]:
    if not COGNITO_CLIENT_SECRET:
        return None
    msg = f"{username}{COGNITO_CLIENT_ID}".encode("utf-8")
    key = COGNITO_CLIENT_SECRET.encode("utf-8")
    dig = hmac.new(key, msg, digestmod=hashlib.sha256).digest()
    return base64.b64encode(dig).decode()


def _cognito():
    if not AWS_REGION:
        raise HTTPException(status_code=500, detail="AWS_REGION not configured")
    return boto3.client("cognito-idp", region_name=AWS_REGION)


# --- Schemas ---
class RegisterRequest(BaseModel):
    username: EmailStr
    password: str = Field(min_length=8)


class RegisterResponse(BaseModel):
    message: str
    cognito_username: str  # Return the generated username for confirmation


class ConfirmRequest(BaseModel):
    cognito_username: str  # Use the generated username from registration
    code: str


class LoginRequest(BaseModel):
    username: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str
    username: Optional[EmailStr] = None


class TokensResponse(BaseModel):
    access_token: str
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None


# --- Endpoints ---
@router.post("/register", status_code=201, response_model=RegisterResponse)
def register(req: RegisterRequest):
    if not (COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID):
        raise HTTPException(status_code=500, detail="Cognito env not configured")
    client = _cognito()
    
    # For email alias enabled pools, we might need to generate a unique username
    # and set email as an attribute. Let's try with email directly first,
    # but if that fails, we could generate a UUID-based username
    import uuid
    generated_username = str(uuid.uuid4())
    
    params: Dict[str, Any] = {
        "ClientId": COGNITO_CLIENT_ID,
        "Username": generated_username,  # Use generated username instead of email
        "Password": req.password,
        "UserAttributes": [
            {"Name": "email", "Value": str(req.username)},
            {"Name": "name", "Value": str(req.username).split('@')[0]},  # Use email prefix as name - REQUIRED
        ],
    }
    sh = _secret_hash(generated_username)  # Use generated username for hash
    if sh:
        params["SecretHash"] = sh
    try:
        client.sign_up(**params)
        return RegisterResponse(
            message="User registration initiated. Check email for confirmation code.",
            cognito_username=generated_username
        )
    except client.exceptions.UsernameExistsException:
        raise HTTPException(status_code=409, detail="User already exists")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/confirm")
def confirm(req: ConfirmRequest):
    if not (COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID):
        raise HTTPException(status_code=500, detail="Cognito env not configured")
    client = _cognito()
    params: Dict[str, Any] = {
        "ClientId": COGNITO_CLIENT_ID,
        "Username": req.cognito_username,  # Use the generated username from registration
        "ConfirmationCode": req.code,
    }
    sh = _secret_hash(req.cognito_username)  # Use generated username for hash
    if sh:
        params["SecretHash"] = sh
    try:
        client.confirm_sign_up(**params)
        return {"message": "User confirmed"}
    except client.exceptions.CodeMismatchException:
        raise HTTPException(status_code=400, detail="Invalid confirmation code")
    except client.exceptions.ExpiredCodeException:
        raise HTTPException(status_code=400, detail="Confirmation code expired")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=TokensResponse)
def login(req: LoginRequest):
    if not (COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID):
        raise HTTPException(status_code=500, detail="Cognito env not configured")
    client = _cognito()
    auth_params = {"USERNAME": req.username, "PASSWORD": req.password}
    sh = _secret_hash(req.username)
    if sh:
        auth_params["SECRET_HASH"] = sh
    try:
        resp = client.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters=auth_params,
        )
        tokens = resp.get("AuthenticationResult", {})
        return TokensResponse(
            access_token=tokens.get("AccessToken"),
            id_token=tokens.get("IdToken"),
            refresh_token=tokens.get("RefreshToken"),
            expires_in=tokens.get("ExpiresIn"),
        )
    except client.exceptions.NotAuthorizedException:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    except client.exceptions.UserNotConfirmedException:
        raise HTTPException(status_code=403, detail="User not confirmed")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/refresh", response_model=TokensResponse)
def refresh(req: RefreshRequest):
    if not COGNITO_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Cognito env not configured")
    client = _cognito()
    auth_params = {"REFRESH_TOKEN": req.refresh_token}
    # SECRET_HASH is required for refresh when client secret is set
    sh = _secret_hash(req.username or "refresh")
    if sh:
        auth_params["SECRET_HASH"] = sh
    try:
        resp = client.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters=auth_params,
        )
        tokens = resp.get("AuthenticationResult", {})
        return TokensResponse(
            access_token=tokens.get("AccessToken"),
            id_token=tokens.get("IdToken"),
            refresh_token=None,  # Usually not returned on refresh
            expires_in=tokens.get("ExpiresIn"),
        )
    except client.exceptions.NotAuthorizedException:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/logout")
def logout(request: Request):
    # Expect Authorization: Bearer <access token>
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing access token")
    access_token = auth.split(" ", 1)[1]
    client = _cognito()
    try:
        client.global_sign_out(AccessToken=access_token)
        return {"message": "Logged out"}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


# --- JWT verification for protected routes ---
_jwks_cache: TTLCache[str, Dict[str, Any]] = TTLCache(maxsize=1, ttl=60 * 60 * 24)  # 24h


async def _get_jwks() -> Dict[str, Any]:
    cache_key = "jwks"
    if cache_key in _jwks_cache:
        return _jwks_cache[cache_key]
    if not (AWS_REGION and COGNITO_USER_POOL_ID):
        raise HTTPException(status_code=500, detail="Cognito env not configured")
    issuer = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
    url = f"{issuer}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        jwks = r.json()
        _jwks_cache[cache_key] = jwks
        return jwks


class CognitoUser(BaseModel):
    sub: str
    username: Optional[str] = None
    email: Optional[str] = None
    claims: Dict[str, Any]


async def get_current_user(request: Request) -> CognitoUser:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = auth.split(" ", 1)[1]
    jwks = await _get_jwks()

    if not (AWS_REGION and COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID):
        raise HTTPException(status_code=500, detail="Cognito env not configured")
    issuer = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"

    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token header")

    kid = header.get("kid")
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(status_code=401, detail="Public key not found")

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "RS256")],
            audience=COGNITO_CLIENT_ID,
            issuer=issuer,
            options={"verify_at_hash": False},
        )
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")

    return CognitoUser(
        sub=claims.get("sub"),
        username=claims.get("cognito:username"),
        email=claims.get("email"),
        claims=claims,
    )


@router.get("/me")
async def me(user: CognitoUser = Depends(get_current_user)):
    return user

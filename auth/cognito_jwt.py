import json
import time
import os
from typing import Optional, Dict, Any
import requests
from jose import jwt, JWTError
from fastapi import HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Your Cognito configuration (from your .env file)
COGNITO_REGION = os.getenv("AWS_REGION", "eu-north-1")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")

# Detailed logging of configuration
logger.info("=== Cognito JWT Configuration ===")
logger.info(f"AWS_REGION: {COGNITO_REGION}")
logger.info(f"COGNITO_USER_POOL_ID: {COGNITO_USER_POOL_ID}")
logger.info(f"COGNITO_CLIENT_ID: {COGNITO_CLIENT_ID}")

if not COGNITO_USER_POOL_ID or not COGNITO_CLIENT_ID:
    logger.error("CRITICAL: COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID must be set in environment variables")
    raise ValueError("COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID must be set in environment variables")

# Construct the JWKs URL
JWKS_URL = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
ISSUER_URL = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"

logger.info(f"JWKs URL: {JWKS_URL}")
logger.info(f"Expected Issuer: {ISSUER_URL}")
logger.info("=== End Configuration ===")

security = HTTPBearer()

class CognitoJWTValidator:
    def __init__(self):
        self.jwks = None
        self.jwks_last_fetch = 0
        self.jwks_cache_duration = 3600  # 1 hour

    def get_jwks(self):
        """Fetch JWKs from Cognito (with caching)"""
        current_time = time.time()
        if self.jwks is None or (current_time - self.jwks_last_fetch) > self.jwks_cache_duration:
            try:
                logger.info(f"Fetching JWKs from: {JWKS_URL}")
                response = requests.get(JWKS_URL, timeout=10)
                
                # Detailed logging of the response
                logger.info(f"JWKs request status code: {response.status_code}")
                logger.info(f"JWKs request headers: {dict(response.headers)}")
                
                if response.status_code == 404:
                    logger.error(f"JWKs URL returned 404 - User Pool might not exist or region/ID is incorrect")
                    logger.error(f"Verify these values:")
                    logger.error(f"  - AWS_REGION: {COGNITO_REGION}")
                    logger.error(f"  - COGNITO_USER_POOL_ID: {COGNITO_USER_POOL_ID}")
                    logger.error(f"  - Full URL: {JWKS_URL}")
                
                response.raise_for_status()
                self.jwks = response.json()
                self.jwks_last_fetch = current_time
                
                logger.info(f"JWKs fetched successfully - found {len(self.jwks.get('keys', []))} keys")
                for i, key in enumerate(self.jwks.get('keys', [])):
                    logger.info(f"  Key {i+1}: kid={key.get('kid')}, alg={key.get('alg')}, use={key.get('use')}")
                    
            except requests.RequestException as e:
                logger.error(f"Failed to fetch JWKs: {str(e)}")
                logger.error(f"Request details:")
                logger.error(f"  URL: {JWKS_URL}")
                logger.error(f"  Error type: {type(e).__name__}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"  Response status: {e.response.status_code}")
                    logger.error(f"  Response text: {e.response.text}")
                raise HTTPException(status_code=500, detail=f"Failed to fetch JWKs: {str(e)}")
        return self.jwks

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token"""
        try:
            logger.info(f"Starting JWT verification (token length: {len(token)})")
            
            # Decode token header to get kid
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            alg = unverified_header.get("alg")
            
            logger.info(f"Token header - kid: {kid}, alg: {alg}")
            
            if not kid:
                logger.error("Token missing 'kid' in header")
                raise HTTPException(status_code=401, detail="Token missing 'kid' in header")

            # Get JWKs
            jwks = self.get_jwks()
            
            # Find the correct key
            key = None
            for jwk in jwks["keys"]:
                if jwk["kid"] == kid:
                    key = jwk
                    logger.info(f"Found matching JWK key: {jwk.get('kid')}")
                    break
            
            if not key:
                logger.error(f"No matching key found for kid: {kid}")
                logger.error(f"Available keys: {[k.get('kid') for k in jwks.get('keys', [])]}")
                raise HTTPException(status_code=401, detail="Invalid token: key not found")

            # Verify and decode token
            logger.info(f"Verifying token with:")
            logger.info(f"  Audience: {COGNITO_CLIENT_ID}")
            logger.info(f"  Issuer: {ISSUER_URL}")
            logger.info(f"  Algorithm: RS256")
            
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=COGNITO_CLIENT_ID,
                issuer=ISSUER_URL
            )
            
            logger.info(f"Token verified successfully!")
            logger.info(f"Token payload keys: {list(payload.keys())}")
            logger.info(f"User: {payload.get('cognito:username', 'N/A')}")
            logger.info(f"Email: {payload.get('email', 'N/A')}")
            logger.info(f"Sub: {payload.get('sub', 'N/A')}")
            
            return payload

        except JWTError as e:
            logger.error(f"JWT verification failed: {str(e)}")
            logger.error(f"JWT Error type: {type(e).__name__}")
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

# Global validator instance
jwt_validator = CognitoJWTValidator()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Dependency to get current authenticated user"""
    token = credentials.credentials
    logger.info("get_current_user called - validating JWT token")
    user_data = jwt_validator.verify_token(token)
    return user_data

async def get_current_user_optional(authorization: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Optional authentication - returns None if no token or invalid token"""
    if not authorization or not authorization.startswith("Bearer "):
        logger.info("No authorization header or invalid format")
        return None
    
    token = authorization.replace("Bearer ", "")
    try:
        logger.info("get_current_user_optional called - validating JWT token")
        user_data = jwt_validator.verify_token(token)
        return user_data
    except HTTPException as e:
        logger.warning(f"Optional JWT validation failed: {e.detail}")
        return None

# Test JWKs endpoint on startup
try:
    logger.info("Testing JWKs endpoint on startup...")
    test_response = requests.get(JWKS_URL, timeout=5)
    if test_response.status_code == 200:
        logger.info("✅ JWKs endpoint is accessible")
        jwks_data = test_response.json()
        logger.info(f"✅ Found {len(jwks_data.get('keys', []))} keys in JWKs")
    else:
        logger.error(f"❌ JWKs endpoint returned status {test_response.status_code}")
        logger.error(f"❌ Response: {test_response.text}")
except Exception as e:
    logger.error(f"❌ Failed to test JWKs endpoint: {str(e)}")
    logger.error("❌ This will cause JWT validation to fail!")
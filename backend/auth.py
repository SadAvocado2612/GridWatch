# auth.py - Enforcer Authentication & Session Management
import os
import json
import secrets
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

USER_DB_PATH = os.path.join(os.path.dirname(__file__), "enforcers.json")

# In-memory active session store (session_token -> user details dict)
ACTIVE_SESSIONS = {}

# HTTPBearer security scheme definition
security = HTTPBearer(auto_error=False)

def get_hashed_password(plain_text_password: str) -> str:
    """Hash password with bcrypt salt."""
    return bcrypt.hashpw(plain_text_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(plain_text_password: str, hashed_password: str) -> bool:
    """Verify plain password against bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_text_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def init_user_db():
    """Initializes and seeds enforcers.json user store if not present."""
    if not os.path.exists(USER_DB_PATH):
        print("Seeding enforcer accounts in enforcers.json...")
        users = [
            {
                "badge_id": "BTP001",
                "name": "Officer Rao",
                "station": "Indiranagar Station",
                "password": get_hashed_password("password123")
            },
            {
                "badge_id": "BTP002",
                "name": "Officer Gowda",
                "station": "Safina Plaza Station",
                "password": get_hashed_password("password456")
            },
            {
                "badge_id": "BTP003",
                "name": "Officer Reddy",
                "station": "Anand Rao Circle Station",
                "password": get_hashed_password("password789")
            }
        ]
        with open(USER_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=4)

# Initialize enforcer data store
init_user_db()

def get_user_by_badge(badge_id: str) -> dict:
    """Lookup user by Badge ID in the JSON file."""
    if not os.path.exists(USER_DB_PATH):
        return None
    try:
        with open(USER_DB_PATH, "r", encoding="utf-8") as f:
            users = json.load(f)
            for u in users:
                if u["badge_id"] == badge_id:
                    return u
    except Exception as e:
        print(f"Error loading enforcer user store: {e}")
    return None

def create_session(user_dict: dict) -> str:
    """Generate session token and cache user details server-side."""
    token = secrets.token_hex(32)
    ACTIVE_SESSIONS[token] = {
        "badge_id": user_dict["badge_id"],
        "name": user_dict["name"],
        "station": user_dict["station"]
    }
    return token

def get_session_user(token: str) -> dict:
    """Retrieve session details by token."""
    return ACTIVE_SESSIONS.get(token)

def delete_session(token: str):
    """Invalidate session token server-side."""
    if token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]

def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """FastAPI route dependency to validate the Bearer token header."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    user = get_session_user(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

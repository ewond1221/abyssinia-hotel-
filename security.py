"""
Security helpers for the Abyssinia Hotel app.

* Rate limiting stored in the database (works on Vercel, where every request
  may hit a different serverless instance, so in-memory counters are useless).
* Failed-login lockout per username (stops brute force from many IPs).
* Strict input validation helpers (length / type / finite-number checks).
* Security headers (CSP, HSTS, no-sniff, no-frame, ...).

Nothing in here needs an API key, and nothing is exposed to the browser.
"""
import hashlib
import ipaddress
import logging
import math
import os
import random
import re
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import jsonify, request
from sqlalchemy.dialects import postgresql, sqlite

from orders import db, RateLimit

log = logging.getLogger("security")

IS_PRODUCTION = bool(os.environ.get("VERCEL") or os.environ.get("PRODUCTION"))


# --------------------------------------------------------------------------
# Client IP
# --------------------------------------------------------------------------
def client_ip():
    """
    Best-effort real client IP.

    On Vercel the platform sets these headers itself (a visitor cannot forge
    them). Anywhere else we ignore X-Forwarded-For completely, because a
    visitor could fake it to dodge the rate limiter.
    IPv6 addresses are collapsed to their /64 so an attacker cannot rotate
    through billions of addresses inside one block.
    """
    raw = None
    if os.environ.get("VERCEL"):
        raw = request.headers.get("X-Vercel-Forwarded-For") or request.headers.get("X-Real-IP")
    raw = (raw or request.remote_addr or "unknown").split(",")[0].strip()

    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return "unknown"

    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address) + "/64"
    return str(ip)


# --------------------------------------------------------------------------
# Rate limiter (fixed window, atomic upsert in the database)
# --------------------------------------------------------------------------
def _upsert_hit(conn, key, expires):
    table = RateLimit.__table__
    insert = postgresql.insert if conn.dialect.name == "postgresql" else sqlite.insert
    stmt = (
        insert(table)
        .values(bucket_key=key, hits=1, expires_at=expires)
        .on_conflict_do_update(index_elements=["bucket_key"], set_={"hits": table.c.hits + 1})
        .returning(table.c.hits)
    )
    return conn.execute(stmt).scalar_one()


def register_hit(scope_key, window):
    """Count one hit in the current window. Returns (hits, seconds_until_reset)."""
    now = time.time()
    key = f"{scope_key}:{int(now // window)}"[:200]
    expires = datetime.utcnow() + timedelta(seconds=window * 2)

    # Own connection + transaction, so the count is saved even if the
    # request itself later fails or rolls back.
    with db.engine.begin() as conn:
        hits = _upsert_hit(conn, key, expires)
        if random.random() < 0.01:  # tidy up old rows now and then
            conn.execute(RateLimit.__table__.delete().where(RateLimit.__table__.c.expires_at < datetime.utcnow()))

    return hits, max(1, int(window - (now % window)))


def peek_hits(scope_key, window):
    """Read the current window's count without adding to it."""
    key = f"{scope_key}:{int(time.time() // window)}"[:200]
    table = RateLimit.__table__
    with db.engine.connect() as conn:
        row = conn.execute(table.select().where(table.c.bucket_key == key)).first()
    return row.hits if row else 0


def too_many_requests(retry_after):
    response = jsonify({"error": "Too many requests. Please wait a moment and try again."})
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    return response


def check_limit(scope, limit, window, strict=False, ident=None):
    """
    Returns a 429 response if this client is over the limit, otherwise None.

    strict=True  -> if the limiter itself breaks, block the request (503).
                    Used for login, where failing open would remove brute-force protection.
    strict=False -> if the limiter itself breaks, let the request through.
    """
    try:
        hits, retry_after = register_hit(f"{scope}:{ident or client_ip()}", window)
    except Exception:
        log.exception("rate limiter failure on scope %s", scope)
        if strict:
            response = jsonify({"error": "Service temporarily unavailable. Please try again shortly."})
            response.status_code = 503
            return response
        return None

    if hits > limit:
        return too_many_requests(retry_after)
    return None


def rate_limit(scope, limit, window, strict=False):
    """Decorator: allow `limit` calls per `window` seconds per client IP. Stack several for burst + daily caps."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            blocked = check_limit(scope, limit, window, strict=strict)
            if blocked is not None:
                return blocked
            return view(*args, **kwargs)

        return wrapper

    return decorator


# --------------------------------------------------------------------------
# Failed-login lockout (per username, regardless of IP)
# --------------------------------------------------------------------------
LOGIN_FAIL_LIMIT = 8
LOGIN_FAIL_WINDOW = 15 * 60


def _login_key(username):
    digest = hashlib.sha256(username.strip().lower().encode("utf-8")).hexdigest()[:32]
    return f"loginfail:{digest}"


def login_locked(username):
    """True when this username already has too many recent failures."""
    return peek_hits(_login_key(username), LOGIN_FAIL_WINDOW) >= LOGIN_FAIL_LIMIT


def record_failed_login(username):
    register_hit(_login_key(username), LOGIN_FAIL_WINDOW)


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")

MENU_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
# Relative path inside /static only: letters, digits, _ - . / (no "..", no scheme, no leading slash)
IMG_PATH_RE = re.compile(r"^(?!/)(?!.*\.\.)(?!.*//)[A-Za-z0-9_./-]{1,200}$")


def clean_text(value, label, max_len, required=True, single_line=True):
    """Return a trimmed string or raise ValueError with a user-facing message."""
    if value is None or value == "":
        if required:
            raise ValueError(f"{label} is required")
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")

    value = _CONTROL_CHARS.sub("", value).strip()
    if single_line:
        value = _WHITESPACE.sub(" ", value)

    if required and not value:
        raise ValueError(f"{label} is required")
    if len(value) > max_len:
        raise ValueError(f"{label} must be {max_len} characters or fewer")
    return value


def clean_number(value, label, minimum, maximum):
    """Finite number within range (rejects NaN / Infinity / booleans / absurd values)."""
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a valid number")
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a valid number")
    if number < minimum or number > maximum:
        raise ValueError(f"{label} must be between {minimum:g} and {maximum:g}")
    return number


def clean_int(value, label, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a whole number")
    if number < minimum or number > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return number


def clean_menu_fields(data, partial=False):
    """
    Validate admin menu-item input. With partial=True only fields that are
    present are checked (used by PATCH). Returns a dict of cleaned values.
    """
    out = {}

    def wanted(name):
        return (name in data) if partial else True

    if wanted("id"):
        item_id = clean_text(data.get("id"), "Item ID", 80)
        if not MENU_ID_RE.match(item_id):
            raise ValueError("Item ID may only use letters, numbers, - and _")
        out["id"] = item_id
    if wanted("name"):
        out["name"] = clean_text(data.get("name"), "Name", 150)
    if wanted("desc"):
        out["desc"] = clean_text(data.get("desc"), "Description", 500)
    if wanted("price"):
        out["price"] = round(clean_number(data.get("price"), "Price", 0, 1_000_000), 2)
    if wanted("category"):
        category = clean_text(data.get("category"), "Category", 50)
        if not CATEGORY_RE.match(category):
            raise ValueError("Category may only use lowercase letters, numbers and -")
        out["category"] = category
    if wanted("img"):
        img = clean_text(data.get("img"), "Image path", 200)
        if not IMG_PATH_RE.match(img):
            raise ValueError("Image path must be a plain file path inside the static folder")
        out["img"] = img
    return out


# --------------------------------------------------------------------------
# Admin password policy
# --------------------------------------------------------------------------
_COMMON_PASSWORDS = {
    "admin", "admin123", "administrator", "password", "password123", "123456789012",
    "qwertyuiop12", "changeme", "letmein12345", "abyssinia", "abyssinia123",
}


def is_known_default_password(password):
    """True for the well-known default passwords (e.g. the old 'admin123')."""
    return isinstance(password, str) and password.strip().lower() in _COMMON_PASSWORDS


def password_problem(password, username=""):
    """Return a message describing why a password is too weak, or None if it is acceptable."""
    if not isinstance(password, str) or len(password) < 12:
        return "Password must be at least 12 characters long."
    if len(password) > 128:
        return "Password must be 128 characters or fewer."
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS or (username and username.lower() in lowered):
        return "Password is too easy to guess."
    if len(set(password)) < 6:
        return "Password needs more variety of characters."
    return None


# --------------------------------------------------------------------------
# Security headers
# --------------------------------------------------------------------------
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",                                   # no inline scripts, no third-party scripts
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",                                  # JS can only talk to this site
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",                              # nobody can embed the site (clickjacking)
])

_NO_STORE_PREFIXES = ("/api/admin", "/api/auth", "/api/orders/", "/api/bookings/", "/admin")


def apply_security_headers(response):
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    path = request.path
    if path.startswith(_NO_STORE_PREFIXES):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response

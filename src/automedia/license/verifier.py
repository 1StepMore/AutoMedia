"""License verification — RSA-signed license key validation.

Generates and verifies license keys using RSA signature scheme.
Keys are formatted as base64-encoded JSON with RSA-SHA256 signature.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

_KEY_DIR = Path.home() / ".automedia" / "license"


def _load_public_key() -> RSAPublicKey | None:
    """Load the RSA public key from ``~/.automedia/license/public.pem``."""
    pub_path = _KEY_DIR / "public.pem"
    if not pub_path.is_file():
        return None
    with open(pub_path, "rb") as fh:
        return serialization.load_pem_public_key(fh.read())  # type: ignore[return-value]


def _load_private_key() -> RSAPrivateKey | None:
    """Load the RSA private key from ``~/.automedia/license/private.pem``."""
    priv_path = _KEY_DIR / "private.pem"
    if not priv_path.is_file():
        return None
    with open(priv_path, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)  # type: ignore[return-value]


def _ensure_key_pair() -> tuple[RSAPrivateKey, RSAPublicKey]:
    """Generate and persist an RSA key pair if none exists.

    Returns ``(private_key, public_key)``.
    """
    _KEY_DIR.mkdir(parents=True, exist_ok=True)

    private = _load_private_key()
    if private is not None:
        pub = _load_public_key()
        if pub is not None:
            return private, pub

    # Generate new key pair
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()

    # Persist
    with open(_KEY_DIR / "private.pem", "wb") as fh:
        fh.write(
            private.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    with open(_KEY_DIR / "public.pem", "wb") as fh:
        fh.write(
            public.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
    return private, public


class RSAVerifier:
    """Verify RSA-signed license keys."""

    @staticmethod
    def verify(key_str: str) -> dict[str, Any]:
        """Verify a license key string.

        Returns a dict with keys:
            ``valid`` (bool), ``expired`` (bool),
            ``tenant_id`` (str), ``expiry_date`` (str), ``features`` (list).
        """
        result: dict[str, Any] = {
            "valid": False,
            "expired": False,
            "tenant_id": "",
            "expiry_date": "",
            "features": [],
        }

        try:
            parsed = RSAVerifier._parse_key(key_str)
        except (ValueError, json.JSONDecodeError, IndexError):
            return result

        payload_bytes = parsed["payload_bytes"]
        signature = parsed["signature"]
        data = parsed["data"]

        # Verify signature
        public_key = _load_public_key()
        if public_key is None:
            # No public key — generate one pair for testing
            _ensure_key_pair()
            public_key = _load_public_key()
            if public_key is None:
                return result

        try:
            public_key.verify(signature, payload_bytes, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            return result

        # Check expiry
        tenant_id = data.get("tenant_id", "")
        expiry_str = data.get("expiry", "")
        features = data.get("features", [])

        expired = False
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str)
                expired = expiry_dt < datetime.now(UTC)
            except (ValueError, TypeError):
                expired = True

        result["valid"] = True
        result["expired"] = expired
        result["tenant_id"] = tenant_id
        result["expiry_date"] = expiry_str
        result["features"] = features
        return result

    @staticmethod
    def _parse_key(key_str: str) -> dict[str, Any]:
        """Parse a base64-encoded license key into payload and signature."""
        raw = base64.b64decode(key_str)
        # Format: payload_json + ":" + base64_signature
        parts = raw.decode("utf-8").rsplit(":", 1)
        payload_b64 = parts[0]
        sig_b64 = parts[1]
        payload_bytes = base64.b64decode(payload_b64)
        data = json.loads(payload_bytes.decode("utf-8"))
        signature = base64.b64decode(sig_b64)
        return {"payload_bytes": payload_bytes, "signature": signature, "data": data}


class LicenseGenerator:
    """Generate RSA-signed license keys (internal/admin tool)."""

    @staticmethod
    def generate(tenant_id: str, days_valid: int = 365) -> str:
        """Generate a license key valid for *days_valid* days from now.

        Returns a base64-encoded license key string.
        """
        private, _ = _ensure_key_pair()

        expiry = (datetime.now(UTC) + timedelta(days=days_valid)).isoformat()

        payload = {
            "tenant_id": tenant_id,
            "expiry": expiry,
            "features": ["tenant", "rbac", "audit", "saml", "web_ui"],
        }

        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = private.sign(payload_bytes, padding.PKCS1v15(), hashes.SHA256())

        # Encode: base64(payload) + ":" + base64(signature)
        payload_b64 = base64.b64encode(payload_bytes).decode("utf-8")
        sig_b64 = base64.b64encode(signature).decode("utf-8")
        key_str = f"{payload_b64}:{sig_b64}"
        return base64.b64encode(key_str.encode("utf-8")).decode("utf-8")

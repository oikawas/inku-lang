"""One-session sealed handoff. Only the dedicated operator transport calls import."""

from __future__ import annotations

import hashlib
import math
import os
import time
import uuid

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .chatgpt_auth import ISSUER, validate_identity
from .chatgpt_runtime import check_owner
from .chatgpt_store import ChatGPTError, CredentialStore, b64, canonical, unb64

PUBLIC_FIELDS = {"version", "request_id", "owner_id", "owner_label", "host_id", "recipient_key", "expires_at"}
ENVELOPE_FIELDS = {"version", "request_id", "owner_id", "host_id", "ephemeral_key", "nonce", "ciphertext"}


def validate_request(request: dict) -> None:
    try:
        if set(request) != PUBLIC_FIELDS or request["version"] != 1 or not time.time() < request["expires_at"] <= time.time() + 1801:
            raise ValueError
        if uuid.UUID(request["request_id"]).version != 4 or len(unb64(request["recipient_key"])) != 32:
            raise ValueError
        if uuid.UUID(request["host_id"]).version != 4 or not request["host_id"].startswith("urn:uuid:"):
            raise ValueError
        if not isinstance(request["owner_id"], str) or not 0 < len(request["owner_id"]) <= 128 or not isinstance(request["owner_label"], str):
            raise ValueError
    except (ValueError, TypeError, KeyError) as error:
        raise ChatGPTError("chatgpt_transfer_invalid") from error


def recipient(owner: str) -> dict:
    from . import db
    check_owner(owner, cli=True)
    store = CredentialStore()
    host_id = store.host_id()
    private = X25519PrivateKey.generate()
    account = db.get_user(owner)
    request = {"version": 1, "request_id": str(uuid.uuid4()), "owner_id": owner,
               "owner_label": str(account.get("display_name") or account.get("username") or owner)[:128],
               "host_id": host_id, "recipient_key": b64(private.public_key().public_bytes_raw()), "expires_at": time.time() + 1800}
    with store.lock(owner, time.monotonic() + 5):
        with store.lock("edit:" + owner, time.monotonic() + 5):
            value = store.read(owner)
            value["requests"] = {key: entry for key, entry in value["requests"].items() if entry["public"]["expires_at"] > time.time()}
            if len(value["requests"]) >= 4:
                raise ChatGPTError("chatgpt_attempt_busy")
            value["requests"][request["request_id"]] = {"public": request, "private": b64(private.private_bytes_raw())}
            store.write(owner, value)
    return request


def _aad(envelope: dict) -> bytes:
    return canonical({key: envelope[key] for key in ("version", "request_id", "owner_id", "host_id")})


def _key(private: X25519PrivateKey, public: str, request_id: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=request_id.encode(), info=b"inku-chatgpt-transfer-v1").derive(
        private.exchange(X25519PublicKey.from_public_bytes(unb64(public))))


def export_profile(request: dict, profile_id: str) -> dict:
    validate_request(request)
    store = CredentialStore()
    owner = request["owner_id"]
    with store.lock(owner, time.monotonic() + 5):
        with store.lock("edit:" + owner, time.monotonic() + 5):
            profile = dict(store.profile(owner, profile_id))
            if profile["state"] != "connected" or profile.get("refresh_owner") != "runtime":
                raise ChatGPTError("chatgpt_session_transferred")
            private = X25519PrivateKey.generate()
            envelope = {"version": 1, "request_id": request["request_id"], "owner_id": owner, "host_id": request["host_id"],
                        "ephemeral_key": b64(private.public_key().public_bytes_raw()), "nonce": b64(os.urandom(12))}
            profile.pop("catalog", None)
            envelope["ciphertext"] = b64(AESGCM(_key(private, request["recipient_key"], request["request_id"])).encrypt(
                unb64(envelope["nonce"]), canonical(profile), _aad(envelope)))
            value = store.read(owner)
            local = value["profiles"][profile_id]
            local.update(state="exported", generation=local["generation"] + 1, refresh_owner="remote")
            for key in ("access_token", "refresh_token", "id_token", "catalog"):
                local.pop(key, None)
            store.write(owner, value)
            return envelope


async def import_profile(envelope: dict) -> dict:
    import json
    try:
        if set(envelope) != ENVELOPE_FIELDS or envelope["version"] != 1 or len(canonical(envelope)) > 256 * 1024:
            raise ValueError
        owner, request_id = envelope["owner_id"], envelope["request_id"]
        check_owner(owner, cli=True)
        store = CredentialStore()
        host_id = store.host_id()
        if envelope["host_id"] != host_id:
            raise ValueError
        digest = hashlib.sha256(canonical(envelope)).hexdigest()
        deadline = time.monotonic() + 30
        with store.lock(owner, deadline):
            value = store.read(owner)
            receipt = value["receipts"].get(request_id)
            if receipt:
                if receipt["digest"] != digest:
                    raise ValueError
                return {**receipt["result"], "replayed": True}
            entry = value["requests"].get(request_id)
            if not entry:
                raise ValueError
            request = entry["public"]
            validate_request(request)
            if request["owner_id"] != owner or request["host_id"] != host_id:
                raise ValueError
            private = X25519PrivateKey.from_private_bytes(unb64(entry["private"]))
            profile = json.loads(AESGCM(_key(private, envelope["ephemeral_key"], request_id)).decrypt(
                unb64(envelope["nonce"]), unb64(envelope["ciphertext"]), _aad(envelope)))
            if uuid.UUID(profile["id"]).version != 4 or profile["issuer"] != ISSUER:
                raise ValueError
            if any(not isinstance(profile.get(key), str) or not 0 < len(profile[key]) <= 65536
                   for key in ("client_id", "sub", "oidc_nonce", "access_token", "refresh_token", "id_token")):
                raise ValueError
            if profile["client_id"] == "dynamic_agent_client" or profile.get("state") != "connected" or profile.get("refresh_owner") != "runtime":
                raise ValueError
            if not isinstance(profile["scopes"], list) or len(profile["scopes"]) > 32 or any(not isinstance(scope, str) or len(scope) > 256 for scope in profile["scopes"]):
                raise ValueError
            if any(not math.isfinite(float(profile[key])) for key in ("expires_at", "earliest_refresh_at")):
                raise ValueError
            if profile["id"] not in value["profiles"] and len(value["profiles"]) >= 8:
                raise ChatGPTError("chatgpt_profile_limit")
            def check():
                check_owner(owner, cli=True)
                validate_request(request)
            async with httpx.AsyncClient(follow_redirects=False) as client:
                claims = await validate_identity(client, profile["id_token"], profile["client_id"], profile["oidc_nonce"], check, deadline)
            if claims["sub"] != profile["sub"]:
                raise ValueError
            profile = {key: profile[key] for key in ("id", "issuer", "sub", "client_id", "oidc_nonce", "access_token", "refresh_token", "id_token", "scopes", "expires_at", "earliest_refresh_at")}
            profile["email"] = str(claims.get("email", ""))[:254]
            profile["label"] = str(claims.get("email", "ChatGPT"))[:254] + " / " + profile["client_id"][-8:]
            with store.lock("edit:" + owner, deadline, check):
                check()
                value = store.read(owner)
                old = value["profiles"].get(profile["id"])
                if old and any(old[key] != profile[key] for key in ("issuer", "sub", "client_id")):
                    raise ChatGPTError("chatgpt_identity_mismatch")
                profile.update(state="connected", refresh_owner="runtime", generation=(old or {}).get("generation", 0) + 1)
                # Publication is owned by the receiving installation, not the envelope.
                profile["published_models"] = (old or {}).get("published_models", [])
                profile.pop("catalog", None)
                result = {"version": 1, "status": "imported", "owner_id": owner, "profile_id": profile["id"],
                          "host_id": host_id, "request_id": request_id, "replayed": False}
                value["profiles"][profile["id"]] = profile
                value["active"] = profile["id"]
                value["requests"].pop(request_id)
                value["receipts"][request_id] = {"digest": digest, "result": result}
                if len(value["receipts"]) > 100:
                    value["receipts"].pop(next(iter(value["receipts"])))
                store.write(owner, value)
                return result
    except ChatGPTError:
        raise
    except (InvalidTag, ValueError, KeyError, TypeError, OverflowError) as error:
        raise ChatGPTError("chatgpt_transfer_invalid") from error

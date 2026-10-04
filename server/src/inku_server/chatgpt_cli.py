"""App-owned local authorization and narrow self-hosted credential entrypoints."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .chatgpt_auth import attempts
from .chatgpt_runtime import configure_startup, enabled, mode_allowed
from .chatgpt_store import ChatGPTError, canonical, protected_read
from .chatgpt_transfer import export_profile, import_profile, recipient, validate_request

BROWSER_IDS = {"chrome": "com.google.Chrome", "brave": "com.brave.Browser"}


def _local_gate(request: dict) -> None:
    if not enabled() or not mode_allowed():
        raise ChatGPTError("chatgpt_mode_not_allowed")
    validate_request(request)


def serve_api(host: str, port: int, *, self_hosted: bool) -> None:
    configure_startup(host, port, self_hosted=self_hosted)
    import uvicorn
    from .api import app
    from .logging_setup import configure_logging
    configure_logging()
    uvicorn.run(app, host=host, port=port, workers=1, reload=False)


def main() -> None:
    failed_profile_id = None
    parser = argparse.ArgumentParser(description="inku ChatGPT plan connection")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("recipient")
    create.add_argument("--owner-id", required=True)
    commands.add_parser("import")
    authorize = commands.add_parser("authorize")
    authorize.add_argument("--recipient", type=Path, required=True)
    authorize.add_argument("--profile-id")
    authorize.add_argument("--consent", action="store_true")
    authorize.add_argument("--no-browser", action="store_true")
    authorize.add_argument("--browser", choices=BROWSER_IDS, default="chrome")
    authorize.add_argument("--language", choices=("ja", "en"), default="en")
    export = commands.add_parser("export")
    export.add_argument("--recipient", type=Path, required=True)
    export.add_argument("--profile-id", required=True)
    export.add_argument("--output", type=Path, required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--self-hosted", action="store_true")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            serve_api(args.host, args.port, self_hosted=args.self_hosted)
            return
        if args.command in {"recipient", "import"}:
            from . import db
            db.init_db()
        if args.command == "recipient":
            result = recipient(args.owner_id)
        elif args.command == "import":
            data = sys.stdin.buffer.read(256 * 1024 + 1)
            if len(data) > 256 * 1024:
                raise ChatGPTError("chatgpt_payload_too_large")
            result = asyncio.run(import_profile(json.loads(data)))
        else:
            request = json.loads(protected_read(args.recipient))
            _local_gate(request)
            if args.command == "export":
                # Reserve the caller's new output before relinquishing ownership.
                fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    envelope = export_profile(request, args.profile_id)
                    handle.write(canonical(envelope))
                    handle.flush()
                    os.fsync(handle.fileno())
                result = {"status": "exported", "profile_id": args.profile_id, "request_id": request["request_id"]}
            else:
                print(("ChatGPTで続ける: " if args.language == "ja" else "Continue with ChatGPT: ") + request["owner_label"] + " / " + request["host_id"], file=sys.stderr)
                start = attempts.begin(request["owner_id"], args.profile_id, args.consent, lambda: _local_gate(request),
                                       registration_host_id=request["host_id"], language=args.language)
                failed_profile_id = start["profile_id"]
                try:
                    if args.no_browser:
                        print(start["authorization_url"], file=sys.stderr)
                    elif sys.platform == "darwin":
                        try:
                            subprocess.run(["/usr/bin/open", "-b", BROWSER_IDS[args.browser], start["authorization_url"]],
                                           check=True, capture_output=True, timeout=30)
                        except (OSError, subprocess.SubprocessError) as error:
                            raise ChatGPTError("chatgpt_browser_unavailable") from error
                    else:
                        raise ChatGPTError("chatgpt_browser_required")
                    while True:
                        result = attempts.public(request["owner_id"], start["attempt_id"])
                        if result["status"] != "pending":
                            break
                        time.sleep(0.2)
                    if result["status"] != "completed":
                        raise ChatGPTError(result["code"] or "chatgpt_auth_rejected")
                finally:
                    attempts.cancel(request["owner_id"], start["attempt_id"])
        print(canonical({"version": 1, **result}).decode())
    except KeyboardInterrupt:
        print('{"version":1,"status":"failed","code":"chatgpt_cancelled"}')
        raise SystemExit(1) from None
    except Exception as error:
        # CLI inputs and OAuth exceptions never reach a traceback or log.
        code = error.code if isinstance(error, ChatGPTError) else "chatgpt_operation_failed"
        print(canonical({"version": 1, "status": "failed", "code": code,
                         **({"profile_id": failed_profile_id} if failed_profile_id else {})}).decode())
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

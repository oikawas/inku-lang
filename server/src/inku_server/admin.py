"""Administrative commands for a server nobody can sign in to.

Usage:
    docker compose exec api inku-admin reset-password --username admin
    uv run python -m inku_server.admin reset-password --username admin

inku has no self-service registration and no reset-by-mail: the web UI is the
only place a password changes, and an administrator who forgot theirs cannot
reach it.  With a single administrator that is a dead end, and this command is
the way out of it.

Running this means holding the container, and holding the container already
means holding the database file it writes to.  It hands over no authority that
was not already held; it spares the operator from hand-writing SQL for it.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

from . import db as _db

# The floor _bootstrap_admin_password enforces.  A recovery door that accepted a
# weaker password than the door that created the account would make the rule
# depend on which one the operator came through.
MIN_PASSWORD_LENGTH = 8


def _read_password_from_stdin(stream: TextIO) -> str:
    # readline, not read(): a password is one line, and the newline a pipe adds
    # is not part of it.  Nothing else is stripped -- trailing spaces may well
    # be the password.
    line = stream.readline()
    if not line:
        raise ValueError("no password arrived on stdin")
    return line.rstrip("\n")


def _prompt_for_password() -> str:
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat new password: "):
        raise ValueError("the two entries do not match")
    return first


def _find_account(accounts: list[dict], *, username: str | None, user_id: str | None) -> dict | None:
    for account in accounts:
        if user_id is not None and account.get("id") == user_id:
            return account
        if username is not None and account.get("username") == username:
            return account
    return None


def _describe(account: dict) -> str:
    groups = ", ".join(account.get("permission_groups") or []) or "no permission group"
    return f"{account.get('username')} ({groups})"


def reset_password(
    *,
    username: str | None,
    user_id: str | None,
    read_password: Callable[[], str],
    out: TextIO,
    err: TextIO,
) -> int:
    """Set one account's password.  Returns the process exit code."""
    _db.init_db()
    accounts = _db.list_users()
    account = _find_account(accounts, username=username, user_id=user_id)
    if account is None:
        wanted = user_id if user_id is not None else username
        print(f"no account matches {wanted!r}", file=err)
        # Whoever forgot the password may also have forgotten which name they
        # put in INKU_BOOTSTRAP_ADMIN_USERNAME.  This reads a database the
        # caller already controls, so naming the accounts discloses nothing
        # they could not read directly.
        print("accounts on this server:", file=err)
        for other in accounts:
            print(f"  {_describe(other)}", file=err)
        return 1

    # Asked for only once the account is known, so a mistyped name does not cost
    # the operator a password they have already typed twice.
    password = read_password()
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"password must be at least {MIN_PASSWORD_LENGTH} characters", file=err)
        return 2

    updated = _db.update_user(account["id"], password=password)
    if updated is None:
        print(f"could not update {_describe(account)}", file=err)
        return 1
    print(f"password reset for {_describe(updated)}", file=out)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inku-admin",
        description="Administrative commands that run inside the server's own container.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    reset = subcommands.add_parser(
        "reset-password",
        help="Set an account's password when nobody can sign in to change it",
    )
    target = reset.add_mutually_exclusive_group()
    target.add_argument(
        "--username",
        help="Account to reset. Defaults to INKU_BOOTSTRAP_ADMIN_USERNAME, or admin",
    )
    target.add_argument("--user-id", help="Account id, for when two accounts share a name")
    reset.add_argument(
        "--password-stdin",
        action="store_true",
        help="Take the new password from the first line of stdin instead of asking for it twice",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "reset-password":  # pragma: no cover - argparse refuses the rest
        return 2

    username = args.username
    if username is None and args.user_id is None:
        username = os.getenv("INKU_BOOTSTRAP_ADMIN_USERNAME", "admin")

    def read_password() -> str:
        if args.password_stdin:
            return _read_password_from_stdin(sys.stdin)
        return _prompt_for_password()

    try:
        return reset_password(
            username=username,
            user_id=args.user_id,
            read_password=read_password,
            out=sys.stdout,
            err=sys.stderr,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""T-1: every owner filter on a work, its lineage or its colophon goes through a predicate.

Who may see a row used to be decided in place, one `Row.user_id == user_id` at a
time, 49 of them across `db.py` plus 6 more inside raw SQL. Widening that rule --
letting an admin see everything, a leader see their organisation, an ACL grant a
single work to one other person -- means editing all 55, and the one that gets
missed is not a crash. It is a work that stays hidden from someone entitled to it,
or worse, one that becomes visible to someone who is not.

So the filters were pulled into `_readable_by` / `_writable_by` / `_owned_by`
(and `_readable_sql` for the recursive lineage CTEs and the full-text search,
which cannot take a SQLAlchemy expression). This test does not check that the
predicates are *correct* -- Stage A returns the same owner test they replaced, so
the existing suites already measure the behaviour. It checks that nothing bypasses
them, because a bypass is invisible until the predicates start to differ.

Measured on 2026-08-10 at `3450548c` + Stage A: 24 calls to `_readable_by`, 10 to
`_writable_by`, 15 to `_owned_by`, 5 to `_readable_sql` covering 6 SQL filters.
Those numbers are recorded, not asserted: Stages B through H legitimately move
them, and a test that froze the tally would have to be edited every week and would
be trusted less each time. What must not move is that the count of *bypasses* is
zero.

`UserSessionRow`, `ExternalIdentityRow`, `UnreadWordRow` and
`UserPermissionGroupRow` are out of scope. A session, a linked identity, an unread
word and a group membership belong to one account by definition; they are not
works, and no scope or grant ever widens them.
"""

from __future__ import annotations

import ast
import pathlib
import re

DB_SOURCE = pathlib.Path(__file__).resolve().parents[1] / "src/inku_server/db.py"

# The four tables a work is made of. Everything the ACL work widens lives here.
OWNED_TABLES = {"HistoryRow", "LineageNodeRow", "LineageEdgeRow", "OkugakiRow"}

PREDICATES = {"_readable_by", "_writable_by", "_owned_by"}

# An owner filter written straight into raw SQL, e.g. `WHERE user_id = :user_id`
# or `WHERE h.user_id = :user_id`. `_readable_sql` builds its fragment from the
# column name it is handed, so its own source never matches this.
RAW_SQL_OWNER_FILTER = re.compile(r"\buser_id\s*=\s*:")


def _enclosing_function(tree: ast.AST, node: ast.AST) -> str:
    """Name of the innermost function containing `node`, for readable failures."""
    best = "<module>"
    best_line = -1
    for candidate in ast.walk(tree):
        if not isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(candidate, "end_lineno", None) or candidate.lineno
        if candidate.lineno <= node.lineno <= end and candidate.lineno > best_line:
            best, best_line = candidate.name, candidate.lineno
    return best


def test_owner_filters_go_through_the_visibility_predicates() -> None:
    source = DB_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # (1) No direct comparison on an owned table's user_id column.
    direct = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        if not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
            continue
        for side in (node.left, *node.comparators):
            if (
                isinstance(side, ast.Attribute)
                and side.attr == "user_id"
                and isinstance(side.value, ast.Name)
                and side.value.id in OWNED_TABLES
            ):
                direct.append(f"{_enclosing_function(tree, node)} (db.py:{node.lineno}): {side.value.id}.user_id")
    assert not direct, (
        "owner filters that bypass the visibility predicates:\n  " + "\n  ".join(direct)
    )

    # (2) The same test written as `filter_by(user_id=...)` would not appear as a
    # Compare node, so it gets its own check rather than a wider regex above.
    filter_by = [
        f"db.py:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "filter_by"
        and any(kw.arg == "user_id" for kw in node.keywords)
    ]
    assert not filter_by, f"filter_by(user_id=...) bypasses the predicates: {filter_by}"

    # (3) No owner filter spelled out inside raw SQL.
    raw = [
        f"db.py:{lineno}"
        for lineno, line in enumerate(source.splitlines(), start=1)
        if RAW_SQL_OWNER_FILTER.search(line)
    ]
    assert not raw, f"raw SQL owner filters that bypass _readable_sql: {raw}"

    # (4) The predicates are actually load-bearing for all four tables. Without
    # this, deleting a filter outright -- rather than bypassing it -- would leave
    # the three checks above green while the rows stopped being scoped at all.
    covered: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in PREDICATES or len(node.args) < 2:
            continue
        column = node.args[1]
        if isinstance(column, ast.Attribute) and isinstance(column.value, ast.Name):
            covered.add(column.value.id)
    assert OWNED_TABLES <= covered, (
        f"tables no longer filtered through a predicate: {sorted(OWNED_TABLES - covered)}"
    )

    # (5) And the raw-SQL form is reached too: the recursive lineage CTEs and the
    # full-text search are the only paths a SQLAlchemy expression cannot enter.
    readable_sql_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_readable_sql"
    ]
    assert readable_sql_calls, "no caller reaches _readable_sql; the raw SQL paths are unscoped"

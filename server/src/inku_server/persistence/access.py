"""Canonical access predicates for Server persistence."""

from __future__ import annotations

from sqlalchemy import and_, or_, select, true

from .schema import HistoryAclRow, HistoryRow, LineageEdgeRow, LineageNodeRow, UserAccountRow


def has_permission_group(actor: dict, name: str) -> bool:
    """Membership test against the permission groups the actor holds."""
    if not actor:
        return False
    return name in (actor.get("permission_groups") or ())


def _owner_actor(user_id: str) -> dict:
    """Identity only, for paths that go through _owned_by and never widen.

    Cascades and idempotency-replay lookups do not read permissions, so resolving
    the account for them would be two queries spent on a decision nothing makes.
    Handing this to _readable_by by mistake narrows rather than widens.
    """
    return {"id": user_id, "permission_groups": [], "group_id": None}


ACL_SUBJECT_TYPES = ("user", "org_group")

# Two rights, not three. `delete` lives inside `write`: a third would multiply
# the acceptance surface for a need nobody has measured yet, and it can be added
# later without moving what is already here.
ACL_PERMISSIONS = ("read", "write")


def _acl_grants(actor: dict, permissions: tuple[str, ...]):
    """Works explicitly granted to this actor at one of `permissions`.

    The actor is reached as themselves and as a member of their organisation
    group. Permission groups are deliberately not subjects: a grant to `users`
    would mean "everyone", which is publication and needs a different design.
    """
    subjects = [and_(HistoryAclRow.subject_type == "user", HistoryAclRow.subject_id == actor["id"])]
    if actor.get("group_id"):
        subjects.append(
            and_(HistoryAclRow.subject_type == "org_group", HistoryAclRow.subject_id == actor["group_id"])
        )
    return select(HistoryAclRow.history_id).where(
        HistoryAclRow.permission.in_(permissions),
        or_(*subjects),
    )


def _shared_with_group(actor: dict):
    """Works whose owner opened them to the actor's organisation group.

    The third way in, after the group scope and an explicit grant. It differs
    from both by being a CONDITION rather than a list: one bit on the work names
    every reader at once, which is what an ACL row -- always one work, one
    subject -- cannot say.

    An actor with no group is not in any group, so nothing here reaches them.
    Returning a clause that matched a NULL share_group_id would hand every
    half-configured work to every groupless account.
    """
    return select(HistoryRow.id).where(
        HistoryRow.for_share == 1,
        HistoryRow.share_group_id == actor["group_id"],
    )


def _same_org_group(actor: dict):
    """Accounts sharing the actor's organisation group, as a subquery.

    A subquery rather than a resolved list of ids: the membership is read at the
    moment the outer query runs, so a member added between the actor being built
    and the query being issued is not briefly invisible.
    """
    return select(UserAccountRow.id).where(UserAccountRow.group_id == actor["group_id"])


def _readable_by(actor: dict, owner_column, acl_history_id=None):
    """Rows the actor may see: owner, or group scope, or an explicit grant.

    admins see everything, orphan rows included: `history.user_id` is nullable
    and a database restored from before the column was backfilled holds works
    owned by nobody. Showing them to no one reads as "the backup lost my work".

    leaders see their own organisation group. The range is the ORGANISATION
    group, not the permission group -- circle_a's leader sees circle_a, not every
    work on the server -- and a leader with no group_id sees only their own,
    which is the same defence delete_user and update_user already apply.

    `acl_history_id` is the column holding the work's id, where the caller has
    one. Rows that are not a work and carry no id to grant against (lineage
    edges, for now) pass nothing and are decided by scope alone. A `write` grant
    satisfies a read: someone trusted to change a work can obviously see it.

    The share bit (I-191) rides on that same branch and not on the scope, which
    is a ruling and not an accident: every caller that hands over a work id gets
    it -- the listing, the search, the lineage nodes -- and `list_okugaki`, the
    one caller that hands over none, does not. A colophon is somebody's writing
    ABOUT a work, and opening the work does not hand that over.
    """
    if has_permission_group(actor, "admins"):
        return true()
    if has_permission_group(actor, "leaders") and actor.get("group_id"):
        scope = or_(owner_column == actor["id"], owner_column.in_(_same_org_group(actor)))
    else:
        scope = owner_column == actor["id"]
    if acl_history_id is None:
        return scope
    ways = [scope, acl_history_id.in_(_acl_grants(actor, ACL_PERMISSIONS))]
    # The same guard the leaders branch above uses, and for the same reason: an
    # actor with no group is in no group. `actor.get("group_id") or ""` would
    # read as defensive and would quietly compare the destination against the
    # empty string instead.
    if actor.get("group_id"):
        ways.append(acl_history_id.in_(_shared_with_group(actor)))
    return or_(*ways)


def _writable_by(actor: dict, owner_column, acl_history_id=None):
    """Rows the actor may change: owner, or admin, or an explicit `write` grant.

    Deliberately narrower than _readable_by, in both halves. A leader reads their
    organisation's works but cannot star, trash, revise or delete them, and a
    `read` grant does not become a `write` one. Collapsing either would make
    every reader an editor.
    """
    if has_permission_group(actor, "admins"):
        return true()
    scope = owner_column == actor["id"]
    if acl_history_id is None:
        return scope
    return or_(scope, acl_history_id.in_(_acl_grants(actor, ("write",))))


def _owned_by(actor: dict, owner_column):
    """Rows the actor owns outright. Unlike the two above, this never widens.

    Cascades and bulk operations (deleting an account, emptying one's own
    history or trash) and idempotency-replay lookups select by ownership, not by
    permission. Routed through _writable_by they would reach every row an admin
    may change, and deleting one account would empty the server.
    """
    return owner_column == actor["id"]


def _readable_node(actor: dict):
    """A lineage node is visible exactly when the work behind it is."""
    return _readable_by(actor, LineageNodeRow.user_id, LineageNodeRow.history_id)


def _readable_edge(actor: dict):
    """An edge is visible exactly when its CHILD is -- never its parent.

    An edge belongs to the derivation, and `lineage_edges.user_id` holds the
    CHILD's owner, so the owner test alone almost says this already. It stops
    being enough once a work can be shared: the child may be visible through a
    grant while its owner column names someone else.

    Following the parent instead would leak the one thing a lineage must not
    disclose. If A's work has children by B and by C, an edge visible to whoever
    can see the PARENT puts C's edge in B's view -- B learns that somebody else
    derived from the same work, and how many did. Following the child, B sees
    A->B and nothing more.
    """
    return LineageEdgeRow.child_node_id.in_(
        select(LineageNodeRow.id).where(_readable_node(actor))
    )


def _readable_node_sql(actor: dict, alias: str = "n") -> tuple[str, dict]:
    """`_readable_node` for the recursive CTEs, which take no ORM expression."""
    return _readable_sql(actor, f"{alias}.user_id", f"{alias}.history_id")


def _readable_sql(actor: dict, owner_column: str, acl_history_id: str | None = None) -> tuple[str, dict]:
    """The _readable_by test as a SQL fragment and its bind parameters.

    The recursive lineage CTEs and the full-text history search are raw SQL and
    cannot take a SQLAlchemy expression, so they take this instead. The two forms
    have to say the same thing and move together; T-1 counts every filter that
    bypasses either, and the search-path test reads a shared work through this
    one specifically -- the failure it guards against is not a leak but a
    disagreement, where the listing shows a work and searching for it does not.
    """
    if has_permission_group(actor, "admins"):
        return "1 = 1", {}
    params = {"acl_owner_id": actor["id"]}
    clauses = [f"{owner_column} = :acl_owner_id"]
    if has_permission_group(actor, "leaders") and actor.get("group_id"):
        params["acl_group_id"] = actor["group_id"]
        clauses.append(f"{owner_column} IN (SELECT id FROM user_accounts WHERE group_id = :acl_group_id)")
    if acl_history_id is not None:
        subjects = ["(subject_type = 'user' AND subject_id = :acl_owner_id)"]
        if actor.get("group_id"):
            params["acl_group_id"] = actor["group_id"]
            subjects.append("(subject_type = 'org_group' AND subject_id = :acl_group_id)")
        clauses.append(
            f"{acl_history_id} IN (SELECT history_id FROM history_acl"
            f" WHERE permission IN ('read', 'write') AND ({' OR '.join(subjects)}))"
        )
        # The share bit (I-191), said here exactly as _readable_by says it. The
        # bind parameter is the same name and the same value the two branches
        # above already write, so a third writer of it is not a collision.
        if actor.get("group_id"):
            params["acl_group_id"] = actor["group_id"]
            clauses.append(
                f"{acl_history_id} IN (SELECT id FROM history"
                f" WHERE for_share = 1 AND share_group_id = :acl_group_id)"
            )
    if len(clauses) == 1:
        return clauses[0], params
    return "(" + " OR ".join(clauses) + ")", params

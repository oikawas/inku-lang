"""Guard the two properties the published documents cannot check for themselves.

Nothing in this repository checks documentation. ``npm run lint:i18n`` reads the
web display strings and never opens a markdown file; CI regenerates the frozen
corpora and runs neither ``pytest`` nor any document check. So the two ways the
documents actually break have both been found by hand, after the fact:

* **the two language versions drift.** The rule is that ``*.ja.md`` is the
  original and the English version follows it. When only one side is edited the
  break is invisible until a reader compares them. The English CHANGELOG is
  missing 76 version entries today; nothing reported that.
* **a published document links to a path that is not published.** ``docs/`` is
  excluded by ``.gitignore`` except for the directories re-included by name, so
  a link into ``docs/`` or ``no-git-sync/`` resolves on the author's disk and
  404s on GitHub. ``CHANGELOG.md`` has linked to ``docs/inku-dev-conventions.md``
  since Build 634 that way.

Run it from ``server/`` before merging a documentation change:

    uv run python scripts/check_docs.py

**Declared exceptions are the point.** Where the two versions legitimately
differ, say so in ``PAIRS`` with a reason. An undeclared difference fails. This
mirrors ``test_saijiki_golden.py``: the fixture is not regenerated, the
difference is declared.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

SERVER_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_DIR.parent

HEADING = re.compile(r"^(#{1,6})\s+\S")
# Markdown inline links. Bare autolinks and reference definitions are not used
# in these documents, so one pattern covers them.
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)")
# A document named in prose inside backticks. Restricted to `.md` on purpose:
# the failure this catches is a published document naming a private one, and
# widening it to every extension drags in generated paths (`cli/out2/...`) that
# are absent by design.
PROSE_DOC = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:ja\.)?md)`")

# (japanese, english, mode, reason the two may differ | None)
#
# mode "shape"    -- the full sequence of heading levels must match. Use it for
#                    documents that are written as one text and translated.
# mode "sections" -- only the number of top-level (##) sections must match. Use
#                    it for append-only logs, where each entry was written in
#                    both languages at the time and the inner structure was
#                    never mirrored. It still catches a whole record present in
#                    one language and missing in the other, which is the way
#                    these documents actually break.
# mode "entries"  -- only the number of ### entries must match. For the
#                    changelogs, where an entry's body is written independently
#                    in each language but every version must appear in both.
PAIRS: tuple[tuple[str, str, str, str | None], ...] = (
    ("README.ja.md", "README.md", "shape", None),
    (
        "docs/spec/render-engine-history.ja.md",
        "docs/spec/render-engine-history.md",
        "shape",
        None,
    ),
    # Split out of the README on 2026-07-28 so the Quick Start rises out of the
    # bottom quarter of the page. Each of these was one section of the README
    # and is translated as one text, so "shape" is the right level here too.
    ("docs/guide/gallery.ja.md", "docs/guide/gallery.md", "shape", None),
    (
        "docs/guide/how-it-works.ja.md",
        "docs/guide/how-it-works.md",
        "shape",
        None,
    ),
    ("docs/guide/revision.ja.md", "docs/guide/revision.md", "shape", None),
    ("SETUP.ja.md", "SETUP.md", "shape", None),
    ("PROJECT_CONTEXT.ja.md", "PROJECT_CONTEXT.md", "shape", None),
    (
        "android/ANDROID_SPEC.ja.md",
        "android/ANDROID_SPEC.md",
        "sections",
        None,
    ),
    (
        "SPEC.ja.md",
        "SPEC.md",
        "shape",
        "the 2026-07-28 ruling that made Japanese canonical for the concepts "
        "and English the sole carrier of the operational sections was "
        "withdrawn on 2026-08-02. The two files must now correspond section "
        "for section, with Japanese still canonical. This exception is "
        "therefore temporary and must be deleted when the shapes match -- "
        "the check itself will say so. **Only §17 is left.** Setting it "
        "aside, the two files match exactly at 135 headings each: §1, §3 and "
        "§11 were reconciled, §15 and the repository appendix were written "
        "in English, and §6.7, §7.8, §12.14 and §18 through §24 were written "
        "in Japanese. §17 is the open-items list, and it cannot simply be "
        "dropped: its 31 unresolved entries appear nowhere in the issue "
        "ledger, so removing the section would remove them from tracking. "
        "The author ruled on 2026-08-02 that they be inventoried first and "
        "only the live ones filed -- that is ledger I-095. When I-095 closes "
        "and §17 is settled in both languages, delete this exception",
    ),
    # The Japanese version was written on 2026-08-02, so the pair needs no
    # exception any more. The 2026-07-28 ruling that made this inventory
    # English-only was withdrawn the same day.
    (
        "docs/spec/implementation-status.ja.md",
        "docs/spec/implementation-status.md",
        "shape",
        None,
    ),
    # Split on 2026-07-28. The current file carries v2.5.0 onward and the two
    # languages hold the same 30 entries, so this pair needs no exception any
    # more: every new version must land in both. The backlog did not vanish --
    # it moved into the two archives below, where it is now countable.
    ("CHANGELOG.ja.md", "CHANGELOG.md", "entries", None),
    ("docs/history/changelog-v1.72-v2.4.ja.md", "docs/history/changelog-v1.72-v2.4.md", "entries", None),
    ("docs/history/changelog-v0.1-v1.71.ja.md", "docs/history/changelog-v0.1-v1.71.md", "entries", None),
)

# Unpublished documents that published documents already name, frozen as they
# stood on 2026-07-28. The CHANGELOG cites the work report behind an entry;
# SPEC tells the author to record bench results in a local log. Nothing new may
# join this list without a decision -- see check_prose_references.
INTERNAL_REFERENCES = frozenset(
    {
        # the local operating conventions, moved out of docs/ on 2026-07-28
        "docs/inku-dev-conventions.md",
        # the local bench log SPEC asks the author to keep
        "cli/tune_bench.md",
        # work reports cited by CHANGELOG entries as provenance
        "no-git-sync/codex-task-v1.52.md",
        "no-git-sync/fable5/co-work/inkuenterminology.md",
        "no-git-sync/fable5/mode-api-claude/RUN-LOG.md",
        "no-git-sync/opus5/name_convantion/RENAMES.md",
        "no-git-sync/fable5/claude_code/tasks/codex-reference-corpus-result.md",
        "no-git-sync/fable5/claude_code/tasks/codex-ui-adjustments-3-result.md",
        "no-git-sync/fable5/claude_code/tasks/en-terminology.md",
        "no-git-sync/fable5/claude_code/tasks/hensou-ui-5th-refine-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-closed-shape-strokes-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-png-filter-rasterizer-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-readme-visuals-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-release-pipeline-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-saijiki-word-pairing-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-ui-adjustments-2-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-ui-adjustments-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-v204-followups-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-v21-proportional-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-v23-stroke-fill-result.md",
        "no-git-sync/fable5/claude_code/tasks/opus-v24-arc-strokes-result.md",
        "no-git-sync/fable5/claude_code/tasks/small-bugs-v202-result.md",
    }
)


def _tracked() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout
    return set(out.split())


def _heading_shape(path: pathlib.Path) -> list[int]:
    shape = []
    fenced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = HEADING.match(line)
        if match:
            shape.append(len(match.group(1)))
    return shape


def check_parity() -> list[str]:
    problems = []
    for ja_name, en_name, mode, exception in PAIRS:
        ja, en = REPO_ROOT / ja_name, REPO_ROOT / en_name
        if not ja.exists():
            # Japanese is the original, so its absence is normally the error.
            # The exception is a document that is operational by ruling rather
            # than conceptual: those are written in English and owe no
            # Japanese version. Declare it, the same as an absent English one.
            if exception:
                print(f"  declared difference: {ja_name} is absent -- {exception}")
            else:
                problems.append(
                    f"missing: {ja_name} (the Japanese version is the original)"
                )
            continue
        if not en.exists():
            # A whole language version that has not been written yet is a
            # difference like any other: declare it, or it fails.
            if exception:
                print(f"  declared difference: {en_name} is absent -- {exception}")
            else:
                problems.append(f"missing: {en_name}")
            continue
        ja_shape, en_shape = _heading_shape(ja), _heading_shape(en)
        if mode == "sections":
            ja_shape = [level for level in ja_shape if level == 2]
            en_shape = [level for level in en_shape if level == 2]
        elif mode == "entries":
            ja_shape = [level for level in ja_shape if level == 3]
            en_shape = [level for level in en_shape if level == 3]
        if ja_shape == en_shape:
            if exception:
                problems.append(
                    f"{en_name}: the declared exception no longer applies -- the "
                    f"shapes match. Remove the reason from PAIRS.\n    was: {exception}"
                )
            continue
        if exception:
            print(f"  declared difference: {en_name} -- {exception}")
            continue
        problems.append(
            f"{ja_name} and {en_name} no longer have the same heading shape:\n"
            f"    {ja_name}: {len(ja_shape)} headings {_summarise(ja_shape)}\n"
            f"    {en_name}: {len(en_shape)} headings {_summarise(en_shape)}\n"
            f"    The Japanese version is the original. Update the English one to "
            f"follow it, or declare the difference in PAIRS with a reason."
        )
    return problems


def _summarise(shape: list[int]) -> str:
    counts = {level: shape.count(level) for level in sorted(set(shape))}
    return " ".join(f"h{level}={n}" for level, n in counts.items())


def check_prose_references(tracked: set[str]) -> list[str]:
    """Freeze the set of internal documents that published documents name.

    The CHANGELOG cites the work report behind each entry, and those reports
    live in ``no-git-sync/``. A reader on GitHub cannot open them. **The author
    ruled on 2026-07-28 that this is fine**: the citation records that a report
    exists, which is worth keeping even though the reader cannot follow it. So
    the set is frozen as it stood that day (22 paths, 51 occurrences) rather
    than cleaned up, and a new one fails. The count is printed either way, so
    the size stays visible instead of being forgotten.

    Only paths that carry a directory are considered: a bare `AGENTS.md` in
    prose is a name, not a route, and the reader is not being sent anywhere.
    """
    problems = []
    seen = 0
    for name in sorted(p for p in tracked if p.endswith(".md")):
        path = REPO_ROOT / name
        fenced = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            for target in PROSE_DOC.findall(line):
                if "/" not in target or target in tracked:
                    continue
                seen += 1
                if target in INTERNAL_REFERENCES:
                    continue
                problems.append(
                    f"{name}:{number}: a published document names an unpublished "
                    f"document: {target}\n    Readers cannot open it. Either point "
                    f"at something published, or add the path to "
                    f"INTERNAL_REFERENCES with the reason it must stay."
                )
    print(f"  internal references named from published documents: {seen}")
    return problems


def check_links(tracked: set[str]) -> list[str]:
    problems = []
    docs = sorted(p for p in tracked if p.endswith(".md"))
    for name in docs:
        path = REPO_ROOT / name
        base = pathlib.PurePosixPath(name).parent
        fenced = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            for target in LINK.findall(line):
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                resolved = _normalise(base, target.split("#", 1)[0])
                if not resolved:
                    continue
                if not (REPO_ROOT / resolved).exists():
                    problems.append(f"{name}:{number}: link to a path that does not exist: {target}")
                elif resolved not in tracked and not _inside_tracked_dir(resolved, tracked):
                    problems.append(
                        f"{name}:{number}: published document links to an unpublished path: "
                        f"{target}\n    It resolves on this disk but 404s on GitHub."
                    )
    return problems


def _normalise(base: pathlib.PurePosixPath, target: str) -> str | None:
    if not target or target.startswith("/"):
        return None
    joined = base / target if str(base) != "." else pathlib.PurePosixPath(target)
    parts: list[str] = []
    for part in joined.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts) if parts else None


def _inside_tracked_dir(resolved: str, tracked: set[str]) -> bool:
    prefix = resolved.rstrip("/") + "/"
    return any(name.startswith(prefix) for name in tracked)


def main() -> int:
    print("checking that the two language versions have the same shape")
    parity = check_parity()
    tracked = _tracked()
    print("checking that published documents link to published paths")
    links = check_links(tracked)
    print("checking that published documents name only published documents")
    prose = check_prose_references(tracked)

    problems = parity + links + prose
    if not problems:
        print("documents are consistent.")
        return 0
    print()
    for problem in problems:
        print(f"* {problem}")
    print(f"\n{len(problems)} problem(s).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

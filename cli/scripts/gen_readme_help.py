"""Write the Command Line Help Reference in cli/README.md from the parser.

The reference section is not prose. It is `--help` for every command, quoted
verbatim, and it used to be kept in step by hand -- which is how the manual
came to name `--original-text` three renames after the flag became
`--description`. Everything between the HELP markers belongs to this script;
everything outside them is written by a person and is never touched here.

    uv run python scripts/gen_readme_help.py            # rewrite the section
    uv run python scripts/gen_readme_help.py --check    # exit 1 if stale

`--check` is what the test calls, so a flag added without regenerating turns
the suite red instead of quietly shipping a manual that describes an older
command.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Pin the width before argparse is asked for any help text. HelpFormatter reads
# it through shutil.get_terminal_size(), so an interactive terminal would wrap
# the synopsis differently and make the generated file depend on who ran it.
HELP_COLUMNS = "80"
os.environ["COLUMNS"] = HELP_COLUMNS

README = Path(__file__).resolve().parents[1] / "README.md"
START = "<!-- HELP_START -->"
END = "<!-- HELP_END -->"


def _paths(parser: argparse.ArgumentParser, prefix: str = "") -> list[tuple[str, argparse.ArgumentParser]]:
    """Every command in the order the parser declares it, parents before children."""
    found = [(prefix, parser)]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                found.extend(_paths(sub, f"{prefix} {name}".strip()))
    return found


def render() -> str:
    """The whole marked region, exactly as it should appear in the file."""
    from inku_cli import cli

    sections = []
    for path, parser in _paths(cli.build_parser()):
        title = f"inku-cli {path}".strip()
        # format_help() already ends in a newline; the blank line before the
        # closing fence is the shape the section has always had.
        sections.append(f"### `{title}`\n\n```\n{parser.format_help()}\n```\n")
    return "\n".join(sections)


def _count() -> int:
    from inku_cli import cli

    return len(_paths(cli.build_parser()))


def _split(text: str) -> tuple[str, str, str]:
    """head, current region, tail -- so the prose outside the markers is untouched."""
    try:
        start = text.index(START) + len(START)
        end = text.index(END)
    except ValueError as exc:  # pragma: no cover - the test asserts the markers
        raise SystemExit(f"{README} に {START} と {END} の両方が要る") from exc
    return text[:start], text[start:end], text[end:]


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument(
        "--check",
        action="store_true",
        help="report whether the section is stale instead of rewriting it",
    )
    options = args.parse_args(argv)

    text = README.read_text(encoding="utf-8")
    head, current, tail = _split(text)
    wanted = f"\n\n{render()}\n"

    if current == wanted:
        print(f"{README.name} の help 節は最新（{_count()} 経路）")
        return 0

    if options.check:
        print(f"{README.name} の help 節がパーサとずれている。"
              f"`uv run python scripts/gen_readme_help.py` で再生成する", file=sys.stderr)
        for name in _stale(current, wanted):
            print(f"  ずれている節: inku-cli {name}".rstrip(), file=sys.stderr)
        return 1

    README.write_text(head + wanted + tail, encoding="utf-8")
    print(f"{README.name} の help 節を書き直した（{_count()} 経路）")
    return 0


def _stale(current: str, wanted: str) -> list[str]:
    """Which commands differ, so the failure names them instead of dumping 1,200 lines."""
    def blocks(region: str) -> dict[str, str]:
        found = {}
        for chunk in region.split("### `inku-cli")[1:]:
            title, _, body = chunk.partition("`\n")
            found[title.strip()] = body
        return found

    now, want = blocks(current), blocks(wanted)
    return [name for name in want if now.get(name) != want[name]] + [
        name for name in now if name not in want
    ]


if __name__ == "__main__":
    raise SystemExit(main())

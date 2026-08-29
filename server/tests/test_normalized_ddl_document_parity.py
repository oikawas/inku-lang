import json
import math
import re
from pathlib import Path

import pytest


FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "core"
    / "crates"
    / "inku-ddl"
    / "tests"
    / "fixtures"
    / "normalized-ddl-document-v1.json"
)
CANVAS_IDS = {
    "square",
    "golden",
    "a4",
    "b4",
    "pillar",
    "oban",
    "wide",
    "byobu",
    "vertical",
    "sd_monitor",
    "hd_monitor",
}
NAMESPACE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class Diagnostic(Exception):
    def __init__(self, code: str, line: int, column: int) -> None:
        super().__init__(code)
        self.code = code
        self.line = line
        self.column = column


class JsonObject(list):
    pass


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def normalize_newlines(source: str) -> str:
    output: list[str] = []
    index = 0
    line = 1
    column = 1
    while index < len(source):
        character = source[index]
        if character == "\r":
            if index + 1 < len(source) and source[index + 1] == "\n":
                output.append("\n")
                index += 2
                line += 1
                column = 1
                continue
            raise Diagnostic("bare_carriage_return", line, column)
        output.append(character)
        index += 1
        if character == "\n":
            line += 1
            column = 1
        else:
            column += 1
    return "".join(output)


def canonical_body_lines(lines: list[str], start: int) -> list[tuple[int, str]]:
    body = [(index + 1, line.rstrip(" \t")) for index, line in enumerate(lines[start:], start)]
    while body and body[0][1] == "":
        body.pop(0)
    while body and body[-1][1] == "":
        body.pop()
    return body


def canonical_legacy_prose(source: str) -> str:
    body = canonical_body_lines(source.split("\n"), 0)
    if not body:
        raise Diagnostic("blank_body", 1, 1)
    return "\n".join(line for _, line in body)


def validate_qualified_name(value: str, line: int, column: int) -> None:
    if "." not in value:
        raise Diagnostic("invalid_qualified_name", line, column)
    namespace, heading = value.split(".", 1)
    if not NAMESPACE_RE.fullmatch(namespace):
        raise Diagnostic("invalid_qualified_name", line, column)
    if (
        not heading
        or heading != heading.strip()
        or any(ord(character) < 32 or character in "\u2028\u2029" for character in heading)
    ):
        raise Diagnostic("invalid_qualified_name", line, column)


def parse_json_string_prefix(source: str, line: int, column: int) -> tuple[str, str]:
    if not source.startswith('"'):
        raise Diagnostic("invalid_qualified_name", line, column)
    try:
        value, end = json.JSONDecoder().raw_decode(source)
    except json.JSONDecodeError as error:
        raise Diagnostic("invalid_qualified_name", line, column + error.colno - 1) from error
    if not isinstance(value, str):
        raise Diagnostic("invalid_qualified_name", line, column)
    validate_qualified_name(value, line, column)
    return value, source[end:]


def parse_lock(source: str, line: int) -> dict:
    qualified_name, rest = parse_json_string_prefix(source.removeprefix("@macro-lock "), line, 13)
    if not rest.startswith(" ") or rest.startswith("  "):
        raise Diagnostic("invalid_macro_lock", line, 1)
    tokens = rest[1:].split(" ")
    if len(tokens) != 2 or not all(tokens):
        raise Diagnostic("invalid_macro_lock", line, 1)
    version, digest = tokens
    if not SEMVER_RE.fullmatch(version):
        raise Diagnostic("invalid_semantic_version", line, 1)
    if not DIGEST_RE.fullmatch(digest):
        raise Diagnostic("invalid_digest", line, 1)
    return {"qualified_name": qualified_name, "version": version, "digest": digest, "line": line}


def reject_json_constant(value: str) -> None:
    raise ValueError(value)


def convert_arguments(value: object, *, top_level: bool) -> object:
    if isinstance(value, JsonObject):
        if not top_level:
            raise Diagnostic("nested_argument_object", 1, 1)
        output: dict[str, object] = {}
        for key, item in value:
            if key in output:
                raise Diagnostic("duplicate_argument_key", 1, 1)
            output[key] = convert_arguments(item, top_level=False)
        return output
    if value is None:
        raise Diagnostic("null_argument", 1, 1)
    if isinstance(value, list):
        return [convert_arguments(item, top_level=False) for item in value]
    if isinstance(value, bool) or isinstance(value, str) or isinstance(value, int):
        if top_level:
            raise Diagnostic("invalid_arguments", 1, 1)
        return value
    if isinstance(value, float) and math.isfinite(value):
        if top_level:
            raise Diagnostic("invalid_arguments", 1, 1)
        return value
    raise Diagnostic("invalid_arguments", 1, 1)


def parse_invocation(source: str, line: int, ordinal: int) -> dict:
    qualified_name, rest = parse_json_string_prefix(source.removeprefix("@invoke "), line, 9)
    if not rest.startswith(" ") or rest.startswith("  ") or not rest[1:].startswith("{"):
        raise Diagnostic("invalid_arguments", line, 1)
    try:
        raw = json.loads(
            rest[1:],
            object_pairs_hook=JsonObject,
            parse_constant=reject_json_constant,
        )
        arguments = convert_arguments(raw, top_level=True)
    except Diagnostic as error:
        raise Diagnostic(error.code, line, 1) from error
    except (json.JSONDecodeError, ValueError, TypeError) as error:
        raise Diagnostic("invalid_arguments", line, 1) from error
    return {
        "kind": "invoke",
        "qualified_name": qualified_name,
        "ordinal": ordinal,
        "arguments": arguments,
        "line": line,
    }


def parse_document(source: str) -> tuple[str, object]:
    normalized = normalize_newlines(source)
    first_line = normalized.split("\n", 1)[0]
    if first_line != "@inku-ddl v1":
        if normalized.startswith("@inku-ddl "):
            raise Diagnostic("unknown_document_version", 1, 1)
        return "legacy", canonical_legacy_prose(normalized)

    lines = normalized.split("\n")
    if len(lines) < 2 or not lines[1].startswith("@language "):
        raise Diagnostic("missing_language_directive", 2, 1)
    language = lines[1].removeprefix("@language ")
    if language not in {"ja", "en"}:
        raise Diagnostic("invalid_language", 2, 1)
    if len(lines) < 3 or not lines[2].startswith("@canvas "):
        raise Diagnostic("missing_canvas_directive", 3, 1)
    canvas_id = lines[2].removeprefix("@canvas ")
    if canvas_id not in CANVAS_IDS:
        raise Diagnostic("invalid_canvas", 3, 1)

    locks: list[dict] = []
    lock_by_name: dict[str, dict] = {}
    index = 3
    while index < len(lines) and lines[index] != "":
        if not lines[index].startswith("@macro-lock "):
            raise Diagnostic("missing_body_separator", index + 1, 1)
        lock = parse_lock(lines[index], index + 1)
        previous = lock_by_name.get(lock["qualified_name"])
        if previous is not None:
            comparable = ("qualified_name", "version", "digest")
            code = (
                "duplicate_macro_lock"
                if all(previous[key] == lock[key] for key in comparable)
                else "conflicting_macro_lock"
            )
            raise Diagnostic(code, index + 1, 1)
        locks.append(lock)
        lock_by_name[lock["qualified_name"]] = lock
        index += 1
    if index >= len(lines) or lines[index] != "":
        raise Diagnostic("missing_body_separator", index + 1, 1)
    index += 1

    source_body = canonical_body_lines(lines, index)
    if not source_body:
        raise Diagnostic("blank_body", index + 1, 1)
    body: list[dict] = []
    invoked: dict[str, int] = {}
    ordinal = 0
    for line_number, line in source_body:
        if line.startswith("@invoke "):
            invocation = parse_invocation(line, line_number, ordinal)
            body.append(invocation)
            invoked.setdefault(invocation["qualified_name"], line_number)
            ordinal += 1
        elif line.startswith("@"):
            raise Diagnostic("unknown_body_directive", line_number, 1)
        else:
            body.append({"kind": "text", "text": line})

    for qualified_name, line_number in invoked.items():
        if qualified_name not in lock_by_name:
            raise Diagnostic("missing_macro_lock", line_number, 1)
    for qualified_name, lock in lock_by_name.items():
        if qualified_name not in invoked:
            raise Diagnostic("unused_macro_lock", lock["line"], 1)

    document = {
        "language": language,
        "canvas_id": canvas_id,
        "locks": sorted(locks, key=lambda lock: lock["qualified_name"].encode("utf-8")),
        "body": body,
    }
    return "document", document


def canonical_document(document: dict) -> str:
    lines = [
        "@inku-ddl v1",
        f"@language {document['language']}",
        f"@canvas {document['canvas_id']}",
    ]
    for lock in document["locks"]:
        qualified_name = json.dumps(lock["qualified_name"], ensure_ascii=False, separators=(",", ":"))
        lines.append(f"@macro-lock {qualified_name} {lock['version']} {lock['digest']}")
    lines.append("")
    for node in document["body"]:
        if node["kind"] == "text":
            lines.append(node["text"])
        else:
            qualified_name = json.dumps(
                node["qualified_name"], ensure_ascii=False, separators=(",", ":")
            )
            arguments = json.dumps(
                node["arguments"], ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
            lines.append(f"@invoke {qualified_name} {arguments}")
    return "\n".join(lines)


def test_fixture_framing_and_canonical_known_answers_are_independently_readable() -> None:
    fixture = load_fixture()
    assert fixture["schema"] == "inku.normalized-ddl-document-v1-fixture.v1"
    assert fixture["version"] == 1
    for case in fixture["valid_cases"]:
        kind, document = parse_document(case["input"])
        assert kind == "document", case["id"]
        assert canonical_document(document) == case["expected"]["canonical"], case["id"]
        reparsed_kind, reparsed = parse_document(case["expected"]["canonical"])
        assert reparsed_kind == "document", case["id"]
        assert canonical_document(reparsed) == case["expected"]["canonical"], case["id"]


def test_legacy_wrapping_uses_explicit_fixture_language_and_canvas() -> None:
    fixture = load_fixture()
    for case in fixture["legacy_cases"]:
        kind, prose = parse_document(case["input"])
        assert kind == "legacy", case["id"]
        assert prose == case["expected_prose"], case["id"]
        synthetic = (
            f"@inku-ddl v1\n@language {case['language']}\n"
            f"@canvas {case['canvas_id']}\n\n{prose}"
        )
        wrapped_kind, wrapped = parse_document(synthetic)
        assert wrapped_kind == "document", case["id"]
        assert canonical_document(wrapped) == case["expected_canonical"], case["id"]


@pytest.mark.parametrize("case", load_fixture()["invalid_cases"], ids=lambda case: case["id"])
def test_diagnostic_classes_and_source_locations_are_independent(case: dict) -> None:
    with pytest.raises(Diagnostic) as raised:
        parse_document(case["input"])
    assert raised.value.code == case["expected_code"]
    assert raised.value.line == case["line"]
    assert raised.value.column == case["column"]

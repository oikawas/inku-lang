"""coerce reads its judgement words from one place.

Before ledger I-115 the words coerce reacts to were written in two places: the
declared side in ``language_support/{ja,en}.py``, and 45 literals inside
``coerce/compose.py``'s own branches. A reader of the vocabulary file saw 574 of
the 693 words; the other 119 were only findable by reading the branches, and the
port had no way to know they existed.

These tests keep the second place empty. They scan the coerce sources the way
``no-git-sync/scripts/count_coerce_markers.py`` does, widened in the two ways
that scan was blind:

* ``x not in text`` as well as ``x in text`` -- ``"crescent" not in ddl.lower()``
  was a judgement word that the narrower scan never saw.
* a tuple bound to a name before it is used -- ``scene_markers = (...)`` followed
  by ``_any_marker_in_text(scene_markers, ...)`` hid five more sites.

What is deliberately *not* vocabulary is a literal matched against a note or a
hint. Those strings are written by this layer, read back by a later branch of the
same layer, and are the same in every language; declaring them would make the
vocabulary file claim coerce reacts to a description that says "visual event".
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

from inku_server.coerce import coerce_score
from inku_server.language_support.registry import INSTRUCTION_LANGUAGE_REGISTRY
from inku_server.schema import Score

COERCE = pathlib.Path(__file__).resolve().parents[1] / "src" / "inku_server" / "coerce"
LANGUAGE_SUPPORT = pathlib.Path(__file__).resolve().parents[1] / "src" / "inku_server" / "language_support"
FIXTURE = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "coerce_vocabulary_move.json").read_text(encoding="utf-8"))

# The names that hold the description. A containment test against anything else
# -- `common`, `arr_data`, `cycle`, `colors` -- is asking about machine data, not
# about what the author wrote.
DESCRIPTION_NAMES = {
    "ddl", "lower", "clause", "context", "text", "lowered", "source", "source_lower", "haystack", "blob",
}

# Literals this layer wrote itself and reads back later. Named by the string
# rather than by line, because lines move every week.
NOTE_LITERALS = {
    # `_with_ddl_coverage` asks which of its own repairs already touched the mark
    "coverage from DDL clause",
    "motif restored",
    "shape intent",
    "fallback from DDL",
    # `_has_focal_event_hint` asks which event note an earlier branch appended
    "visual event",
    "vanishing trace",
    "edge light event",
    "playful motion",
    "motion floor",
    "surface tension",
    "action residue",
    "temporal hinge",
    "presence weight",
    # the compact-mark notes, asked about in four places
    "small focal mark kept compact",
    "circle focal mark kept compact",
    # `normalize._is_material_hint` reads the note `_with_material_hint` wrote
    "material inferred from ddl",
}

# A judgement that only one language has a word for. Listed here so that adding
# a system to one file and forgetting the other is a failure rather than a
# silent asymmetry -- and so that the two real cases stay visible.
SINGLE_LANGUAGE_SYSTEMS = {
    "crescent_scene": "en",  # no Japanese description in the corpus says 三日月 here
    "radius_clause": "en",   # the Japanese half of this judgement is 半径, inside a regex
    "autumn_leaf_fall": "ja",
}


def _strings(node: ast.AST) -> list[str]:
    return [s.value for s in ast.walk(node)
            if isinstance(s, ast.Constant) and isinstance(s.value, str) and s.value]


def _is_description(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in DESCRIPTION_NAMES
    if isinstance(node, ast.Call):
        rendered = ast.unparse(node)
        return any(rendered.startswith(name + ".") for name in DESCRIPTION_NAMES)
    return False


def _is_marker_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and ("marker" in node.func.id or "_in_text" in node.func.id)
    )


def _comprehension_reads_the_description(tree: ast.AST, target: ast.comprehension) -> bool:
    """Does the element expression of this comprehension test the description?

    ``any(marker in clause for marker in (...))`` does. ``any(marker in norm_hint
    for marker in (...))`` -- normalize's sensory markers, matched against a
    ``color_hint`` the model wrote -- does not.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            continue
        if target not in node.generators:
            continue
        for inner in ast.walk(node.elt):
            if isinstance(inner, ast.Compare) and len(inner.ops) == 1 and isinstance(inner.ops[0], (ast.In, ast.NotIn)):
                if _is_description(inner.comparators[0]):
                    return True
            if _is_marker_call(inner) and any(_is_description(arg) for arg in inner.args):
                return True
        return False
    return True


def _marker_call_reads_the_description(node: ast.Call) -> bool:
    others = [arg for arg in node.args if not isinstance(arg, (ast.Tuple, ast.List, ast.Set, ast.Name))]
    named = [arg for arg in node.args if isinstance(arg, ast.Name)]
    if not others and not named:
        return True
    return any(_is_description(arg) for arg in node.args)


def literals_in_source(name: str, source: str) -> dict[str, list[tuple[str, int]]]:
    """word -> the (file, line) pairs that judge the description with it."""
    found: dict[str, list[tuple[str, int]]] = {}
    seen: set[tuple[str, int, str]] = set()

    def take(line: int, words: list[str]) -> None:
        for word in words:
            if (name, line, word) in seen:
                continue
            seen.add((name, line, word))
            found.setdefault(word, []).append((name, line))

    tree = ast.parse(source)
    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for scope in scopes:
        bound: dict[str, tuple[int, list[str]]] = {}
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Tuple, ast.List, ast.Set)):
                words = _strings(node.value)
                if words and len(words) == len(node.value.elts):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            bound[target.id] = (node.lineno, words)
        for node in ast.walk(scope):
            if _is_marker_call(node) and _marker_call_reads_the_description(node):
                for arg in node.args:
                    if isinstance(arg, (ast.Tuple, ast.List, ast.Set)):
                        take(node.lineno, _strings(arg))
                    elif isinstance(arg, ast.Name) and arg.id in bound:
                        line, words = bound[arg.id]
                        take(line, words)
            if isinstance(node, ast.comprehension) and _comprehension_reads_the_description(tree, node):
                if isinstance(node.iter, (ast.Tuple, ast.List, ast.Set)):
                    take(getattr(node.iter, "lineno", 0), _strings(node.iter))
                elif isinstance(node.iter, ast.Name) and node.iter.id in bound:
                    line, words = bound[node.iter.id]
                    take(line, words)

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], (ast.In, ast.NotIn)):
            left = node.left
            if isinstance(left, ast.Constant) and isinstance(left.value, str) and left.value:
                if _is_description(node.comparators[0]):
                    take(node.lineno, [left.value])
    return found


def judgement_literals() -> dict[str, list[tuple[str, int]]]:
    found: dict[str, list[tuple[str, int]]] = {}
    for path in sorted(COERCE.glob("*.py")):
        for word, places in literals_in_source(path.name, path.read_text(encoding="utf-8")).items():
            found.setdefault(word, []).extend(places)
    return found


def direct_registration_systems() -> set[str]:
    """Read the explicit compose-local input registry from the source."""
    tree = ast.parse((COERCE / "compose.py").read_text(encoding="utf-8"))
    return {
        call.args[0].value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_direct_marker_values"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
        and call.args[0].value.startswith("direct.")
    }


def declared_systems() -> dict[str, dict[str, set[str]]]:
    """system name -> {language: words}, read from the source so a test can name the file."""
    systems: dict[str, dict[str, set[str]]] = {}
    for lang in ("ja", "en"):
        tree = ast.parse((LANGUAGE_SUPPORT / f"{lang}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "COERCE_MARKERS" for t in node.targets):
                continue
            for key, value in zip(node.value.keys, node.value.values):
                systems.setdefault(key.value, {})[lang] = set(_strings(value))
    return systems


def declared_words() -> set[str]:
    flat: set[str] = set()
    for languages in declared_systems().values():
        for words in languages.values():
            flat |= words
    return flat


def test_coerce_judges_only_with_declared_words() -> None:
    """T-280: no undeclared judgement literal is left in coerce/, and no note
    string has been smuggled into the declaration to satisfy that."""
    declared = declared_words()
    undeclared = {
        word: places
        for word, places in judgement_literals().items()
        if word not in declared and word not in NOTE_LITERALS
    }
    assert undeclared == {}, (
        f"{len(undeclared)} judgement words are written into coerce/ but not declared "
        f"in COERCE_MARKERS: {sorted(undeclared)[:8]}"
    )

    smuggled = sorted(NOTE_LITERALS & declared)
    assert smuggled == [], (
        "these are notes this layer writes, not words a description carries; "
        f"declaring them makes the vocabulary file lie: {smuggled}"
    )


SCAN_SPECIMEN = '''
def judged(ddl, clause, note_hint):
    lower = ddl.lower()
    inline_tuple = any(marker in clause for marker in ("いんらいん", "inline"))
    bound = ("たばね", "bound")
    named_tuple = _any_marker_in_text(bound, ddl, lower)
    single = "たんいつ" in lower
    via_call = any(_marker_in_text(marker, clause, lower) for marker in ("よびだし", "call"))
    negated = "はんてん" not in ddl
    machine = any(marker in note_hint for marker in ("this is a note", "not a description"))
    dictionary = "key" in {"key": 1}
    return inline_tuple, named_tuple, single, negated, machine, dictionary, via_call
'''


def test_the_scan_reads_all_four_shapes_and_skips_the_notes() -> None:
    """A guard that cannot see a shape is blind to whatever is written in it.

    Every form this scan claims to read is put in front of it here, because the
    real sources no longer contain some of them -- there is no ``not in``
    judgement left in coerce/ after the move, so nothing else exercises that arm.
    """
    seen = set(literals_in_source("specimen.py", SCAN_SPECIMEN))
    assert seen == {"いんらいん", "inline", "たばね", "bound", "たんいつ", "はんてん", "よびだし", "call"}, sorted(seen)

    found = judgement_literals()
    files = {path for places in found.values() for path, _ in places}
    assert files == {"normalize.py"}, files

    # Compose-local author inputs no longer look like raw containment tests: they
    # are registered by `_direct_marker_values` and attached to explicit runtime
    # decision sites. Verify that architecture against the live catalog instead
    # of treating the scanner's former literal count as a proxy for coverage.
    from inku_server.coerce.observability import (
        catalog_snapshot,
        verify_decision_site_registry,
    )

    snapshot = catalog_snapshot()
    direct_catalog = [
        event for event in snapshot["markers"] if event["system"].startswith("direct.")
    ]
    assert direct_catalog
    assert verify_decision_site_registry() == []
    assert direct_registration_systems() == {
        event["system"] for event in direct_catalog
    }
    assert not {event["marker"] for event in direct_catalog} & NOTE_LITERALS


def test_both_languages_gained_the_moved_systems() -> None:
    """T-281: the systems are declared, and declared in both files unless the
    judgement genuinely has words in one language only."""
    systems = declared_systems()
    assert len(systems) > 27, f"{len(systems)} systems; the move added none"

    for lang in ("ja", "en"):
        count = sum(1 for languages in systems.values() if languages.get(lang))
        assert count > 27, f"{lang}.py declares {count} systems; the move added none to it"

    lopsided = {
        name: sorted(languages)
        for name, languages in systems.items()
        if len([lang for lang in ("ja", "en") if languages.get(lang)]) == 1
        and name not in SINGLE_LANGUAGE_SYSTEMS
    }
    assert lopsided == {}, (
        f"declared in one language only, and not listed as such: {lopsided}"
    )
    for name, lang in SINGLE_LANGUAGE_SYSTEMS.items():
        assert systems[name].get(lang), f"{name} claims to be {lang}-only but has no {lang} word"


def test_the_move_lost_no_word_and_invented_none() -> None:
    """T-282: the declared side grew by exactly the words that were hard-coded."""
    before = set(FIXTURE["declared_before"])
    moved = set(FIXTURE["moved"])
    now = declared_words()

    assert now - before == moved, {
        "declared that was not there before and was not moved": sorted((now - before) - moved)[:8],
        "moved but no longer declared": sorted(moved - now)[:8],
    }
    assert before - now == set(), f"words the move dropped: {sorted(before - now)[:8]}"


def test_the_word_count_is_the_sum_of_the_two_places() -> None:
    """T-283: 574 declared + 119 moved = 693 distinct words, and not one more."""
    assert len(FIXTURE["declared_before"]) == 574
    assert len(FIXTURE["moved"]) == 119
    assert len(declared_words()) == 693


@pytest.mark.skip(
    reason="T-284: stage 0 measured every one of the 56 judgement sites and none "
    "returns the matched word -- they are all any() or _any_marker_in_text(), "
    "which return a bool. There is no site whose result the word order can change."
)
def test_a_site_that_returns_the_matched_word_keeps_its_order() -> None:
    raise AssertionError("unreachable while stage 0's count is zero")


def test_the_declaration_is_read_once_at_import() -> None:
    """T-285: reading the declaration inside a function would move the moment the
    language is resolved, which is not what the existing systems do."""
    offenders = []
    module_level_reads = 0
    for path in sorted(COERCE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ("_coerce_marker_values", "_coerce_marker_dict"):
                    module_level_reads += 1
        for scope in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for node in ast.walk(scope):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in ("_coerce_marker_values", "_coerce_marker_dict"):
                        offenders.append(f"{path.name}:{node.lineno} inside {scope.name}()")
    assert module_level_reads >= 60, f"only {module_level_reads} reads seen; the scan has gone blind"
    assert offenders == [], f"the declaration is read at call time here: {offenders}"


def test_every_declared_system_is_reachable_from_the_registry() -> None:
    """The systems are only worth anything if the registry hands them over."""
    for lang in ("ja", "en"):
        markers = INSTRUCTION_LANGUAGE_REGISTRY[lang].coerce_markers
        for name, languages in declared_systems().items():
            if languages.get(lang):
                assert name in markers, f"{name} is in {lang}.py but not in the registry's markers"


GOLDEN_CASES = json.loads(
    (pathlib.Path(__file__).resolve().parent / "golden" / "coerce_golden.json").read_text(encoding="utf-8")
)["cases"]


def test_the_same_description_coerces_to_the_same_score_twice() -> None:
    """T-287: reading the words from the declaration instead of from a literal
    must not put anything order-dependent in the path.

    ``test_coerce_golden.py`` pins the value against frozen bytes, which is a
    stronger claim about *what* comes out, but it never runs one input twice in
    one process. This does.
    """
    checked = 0
    for case_id, case in sorted(GOLDEN_CASES.items()):
        ddl = case["input"].get("ddl")
        if not ddl:
            continue
        first = coerce_score(Score.model_validate(case["input"]["score"]), ddl=ddl)
        second = coerce_score(Score.model_validate(case["input"]["score"]), ddl=ddl)
        assert first.model_dump(mode="json", by_alias=True) == second.model_dump(mode="json", by_alias=True), (
            f"{case_id}: coercing the same description twice gave two Scores"
        )
        checked += 1
    assert checked >= 30, f"only {checked} cases carried a description; the gate is nearly empty"

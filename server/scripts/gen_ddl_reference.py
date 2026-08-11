"""Generate the frozen deterministic DDL-layer reference corpus.

A expands literal DDL inputs. B coerces unrelated literal Score inputs. C runs
the document-plugin layer, which neither of the other two reaches. No part feeds
another. Run from ``server/``.
"""
from __future__ import annotations
import copy
import hashlib
import json
import pathlib
import subprocess
from typing import Any
from inku_server.coerce import coerce_score
from inku_server.ddl_expander import expand_intermediate_ddl
from inku_server.layer_versions import DDL_ENGINE_VERSION, DDL_VERSION
from inku_server.plugins.document_format import PluginDocumentManager
from inku_server.schema import Score

REFERENCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "reference"
# The plugin documents this corpus expands against, pinned to the repository copy.
# The manager otherwise takes its directory from INKU_DOCUMENT_PLUGIN_DIR, and a
# corpus that reads whatever a machine happens to have installed is not frozen.
PLUGIN_DIR = REFERENCE_ROOT.parent / "plugins"
OUTPUT_DIR = REFERENCE_ROOT / f"ddl-engine-{DDL_ENGINE_VERSION}"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
CORPUS_FORMAT_VERSION = "1"
SCHEMA_VERSION = "0.1.0"
FROZEN_AT = "2026-08-11"
REASON = (
    "a plugin hands over one whole unit, and a count stated in the phrase that "
    "names it says how many of those units to place. The document plugin layer "
    "placed the unit once and read nothing; a body saying `Nature.青葉を三つ置く。` "
    "got one leaf group. The count is now read by the shared reader in "
    "`counts.py` -- one definition, where coerce reads it too -- and a count the "
    "work has no room for is declined whole rather than trimmed, so the number "
    "that survives is one somebody chose. The English side of that reader reads "
    "Arabic numerals and no longer requires a noun from a 32-word table, which "
    "is why `Draw 12 circles.` was invisible to it. Part C is new: this layer "
    "carried a version number from the start and never a frozen output, because "
    "part A's plugin work is the `Nature.` macro regex in `ddl_expander` and the "
    "document manager is called from the render route alone. Its four cases are "
    "the whole of `changed_from_previous`; not one of the 13 expand cases or the "
    "23 coerce scores moved, and nothing else in the corpus reaches the layer "
    "this version changed. The fourth records where the two readings do not "
    "meet: a numeral with CJK within twelve characters is left to the Japanese "
    "path, and a plugin named `Nature.青葉` is CJK beside the number, so `Place "
    "12 Nature.青葉 marks.` places one unit where `Place twelve Nature.青葉 "
    "marks.` places twelve."
)

IDENTITY_FIELDS = ("corpus_format_version", "engine_version", "ddl_version", "schema_version")

BASE_INSTRUCTION: dict[str, Any] = {
    "primitive": "line", "from": [0.18, 0.50], "to": [0.82, 0.50],
    "center": None, "radius": None, "sides": None, "position": None,
    "size": None, "angle_start": None, "angle_end": None, "rotation": None,
    "filled": False, "style": "solid", "weight": "pen", "thinness": None,
    "mode": "additive",
    "carve_depth": None, "color": "black", "color_hint": None,
    "variation": None, "arrangement": None, "at": None, "relation": None,
    "surface": None,
}
BASE_SCORE: dict[str, Any] = {
    "version": "0.1.0", "canvas": {"aspect": "square", "ground": None},
    "background": "white", "presence": None, "instructions": [],
}
BASE_ARRANGEMENT: dict[str, Any] = {
    "count": 3, "layout": "scatter", "rows": None, "cols": None,
    "jitter": 0.12, "path": "none", "color_cycle": [], "margin": 0.1,
    "center": None, "radius": None, "density": "none", "cluster_count": None,
    "fade": "none", "preserve_space": False, "rhythm_spacing": "none",
}
BASE_RELATION = {"type": "touching", "gap": "medium"}
BASE_PRESENCE = {
    "kind": "figure_like", "intensity": "medium", "center": [0.5, 0.5],
    "symmetry": "bilateral", "gaze_pressure": "low", "contour_density": "low",
}

def _instruction(**changes: Any) -> dict[str, Any]:
    result = copy.deepcopy(BASE_INSTRUCTION)
    result.update(changes)
    return result

def _score(instructions: list[dict[str, Any]], **changes: Any) -> dict[str, Any]:
    result = copy.deepcopy(BASE_SCORE)
    result["instructions"] = copy.deepcopy(instructions)
    result.update(copy.deepcopy(changes))
    return result

def _expand_input(ddl: str, *, lang: str = "ja", context_text: str | None = None,
                  composition_seed: int | None = None, enable_plugins: bool = True,
                  plugin_instructions_present: bool = False,
                  focus: str | None = None, variation_amplitude: str | None = None,
                  variation_seed: int | None = None) -> dict[str, Any]:
    return {
        "ddl": ddl, "lang": lang, "context_text": context_text,
        "composition_seed": composition_seed, "enable_plugins": enable_plugins,
        "plugin_instructions_present": plugin_instructions_present,
        "focus": focus,
        "variation_amplitude": variation_amplitude, "variation_seed": variation_seed,
    }

def build_expand_inputs() -> dict[str, dict[str, Any]]:
    variation_ddl = "中心に黒い四角を置く。白い横線を三本引く。"
    en_ddl = "Place one black square near the center. Draw three white horizontal lines."
    scatter_ddl = "赤い円を三つ置く。小さな点を画面全体に散らす。"
    plugin_ddl = "黒い線を三本引く。Nature.うねり。"
    cases = {
        "A-base-ja": _expand_input(variation_ddl, context_text=variation_ddl),
        "A-base-en": _expand_input(en_ddl, lang="en", context_text=en_ddl),
        "A-variation-amplitude-only": _expand_input(variation_ddl, context_text=variation_ddl, variation_amplitude="large"),
        "A-variation-seed-only": _expand_input(variation_ddl, context_text=variation_ddl, variation_seed=12345),
        "A-plugin-enabled": _expand_input(plugin_ddl, context_text=plugin_ddl, enable_plugins=True),
        "A-plugin-disabled": _expand_input(plugin_ddl, context_text=plugin_ddl, enable_plugins=False),
    }
    for amplitude in ("small", "medium", "large"):
        for seed in (1, 12345):
            cases[f"A-variation-{amplitude}-{seed}"] = _expand_input(
                variation_ddl, context_text=variation_ddl,
                variation_amplitude=amplitude, variation_seed=seed,
            )
    # One input where the expander used to append candidate sentences of its
    # own. The staffage level that governed them is gone (v2.11.0), so what this
    # freezes now is that a scatter-heavy DDL comes back reframed and no longer.
    cases["A-scatter"] = _expand_input(scatter_ddl, context_text=scatter_ddl)
    return cases

def _plugin_expand_input(ddl: str, *, lang: str = "ja", source_text: str | None = None,
                         seed_text: str | None = "reference") -> dict[str, Any]:
    return {"ddl": ddl, "source_text": source_text, "lang": lang, "seed_text": seed_text}

def build_plugin_expand_inputs() -> dict[str, dict[str, Any]]:
    """Inputs for the document-plugin layer, which no other part reaches.

    Part A runs `expand_intermediate_ddl`, whose plugin work is the `Nature.`
    macro regex in `ddl_expander`; the document plugin manager is called from the
    render route alone.  So this layer carried a version number from the start
    and never a frozen output: engine 13 changes what it emits, and freezing A
    and B alone would have recorded a version of a layer the change never
    traversed.

    Four cases.  Three are what the version decided: the count in the phrase
    becomes the number of units, an English body counts the same way, and a count
    the work has no room for is declined whole rather than trimmed -- the last
    one is the only place a `plugin_warnings` line is frozen.  The seed is fixed
    because the breakdown inside one unit is drawn from it.

    The fourth freezes where the two rulings do not meet.  The English side of
    the reader was widened to Arabic numerals, but a numeral with CJK within
    twelve characters is left to the Japanese path -- and a plugin named
    `Nature.青葉` is CJK sitting right beside the number.  So `Place 12
    Nature.青葉 marks.` places one unit while `Place twelve Nature.青葉 marks.`
    places twelve.  Recording it here means a later ruling either way moves a
    case rather than passing unnoticed.
    """
    return {
        "C-plugin-count-in-the-phrase": _plugin_expand_input("Nature.青葉を三つ置く。"),
        "C-plugin-count-in-an-english-body": _plugin_expand_input(
            "Place twelve Nature.青葉 marks.", lang="en"
        ),
        "C-plugin-count-as-a-numeral-beside-cjk": _plugin_expand_input(
            "Place 12 Nature.青葉 marks.", lang="en"
        ),
        "C-plugin-count-over-the-ceiling": _plugin_expand_input("Nature.青葉を百二十個置く。"),
    }

def _coerce_input(score: dict[str, Any], *, ddl: str | None = None) -> dict[str, Any]:
    return {"score": copy.deepcopy(score), "ddl": ddl}

def build_coerce_inputs() -> dict[str, dict[str, Any]]:
    line = _instruction()
    trigger = "赤い円を三つ散らす。ゆっくり波打つ。"
    cases = {
        "B-baseline-no-ddl": _coerce_input(_score([line])),
        # Words that used to summon instructions of coerce's own -- motion,
        # a visual event, an accent for the diversity of the composition. The
        # three cases that separated the staffage levels collapsed into this one
        # when the axis was folded away (v2.11.0); what it freezes now is that
        # such a description leaves with the one line it came in with.
        "B-trigger": _coerce_input(_score([line]), ddl=trigger),
        "B-white-line": _coerce_input(_score([_instruction(color="white")])),
        "B-white-filled-circle": _coerce_input(_score([_instruction(
            primitive="circle", **{"from": None}, to=None, center=[0.5, 0.5], radius=0.2,
            filled=True, color="white",
        )])),
        "B-invalid-touching": _coerce_input(_score([_instruction(relation=copy.deepcopy(BASE_RELATION))])),
        "B-dedupe-three": _coerce_input(_score([line, line, line])),
        "B-quiet-water": _coerce_input(_score([line]), ddl="静かな水面。"),
        "B-presence-from-ddl": _coerce_input(_score([line]), ddl="金色の三日月が右上に浮かび、水面が細かく震え、岸辺に草が群れる。"),
        "B-grid": _coerce_input(_score([_instruction(arrangement={
            **copy.deepcopy(BASE_ARRANGEMENT), "count": 12, "layout": "grid", "rows": 3, "cols": 4,
        })]), ddl="黒い線を三行四列の格子に並べる。"),
        "B-dense-forty": _coerce_input(_score([
            _instruction(**{"from": [0.1, 0.02 + index * 0.02], "to": [0.9, 0.02 + index * 0.02]})
            for index in range(40)
        ])),
        "B-cloudform": _coerce_input(_score([_instruction(
            primitive="cloudform", **{"from": None}, to=None, center=[0.5, 0.5], size=[0.4, 0.3],
        )])),
        "B-presence-no-ddl": _coerce_input(_score([line], presence=copy.deepcopy(BASE_PRESENCE))),
        "B-yellow-from-ddl": _coerce_input(_score([line]), ddl="黄色い円を三つ散らす。"),
        "B-orange-from-ddl": _coerce_input(_score([line]), ddl="橙の灯火が揺れる。"),
        "B-purple-from-ddl": _coerce_input(_score([line]), ddl="紫の菫が咲く。"),
        "B-yellow-from-ddl-en": _coerce_input(
            _score([line]), ddl="Scatter three yellow circles."
        ),
        # The shape production actually hands coerce. Before the
        # description-propagation cut every b_coerce case passed a single short
        # sentence, while 71.7% of production works passed `prose\nDDL` -- the
        # corpus never traversed the real input. The cut made the production
        # input the DDL alone, and these three cases freeze that shape: a
        # multi-clause plan opening with a fill clause, the same plan without
        # one, and a multi-line DDL whose fill clause sits on line 2.
        "B-production-fill-clause": _coerce_input(
            _score([_instruction(color="white", arrangement={
                **copy.deepcopy(BASE_ARRANGEMENT), "count": 110, "layout": "vertical",
            })], background="blue"),
            ddl=(
                "背景を青で塗りつぶす。画面全体に白い細筆の細い縦線を三百本、上から下へ散らす。"
                "黒い細い余白線を存在の重心として右上の焦点へ二本引く。透明な膜を重ねる。境界が滲む。"
            ),
        ),
        "B-production-no-fill-clause": _coerce_input(
            _score([_instruction(color="white", arrangement={
                **copy.deepcopy(BASE_ARRANGEMENT), "count": 110, "layout": "vertical",
            })], background="blue"),
            ddl=(
                "静かな気配の中に、白い細筆の細い縦線を三百本、上から下へ散らす。"
                "黒い細い余白線を存在の重心として右上の焦点へ二本引く。透明な膜を重ねる。境界が滲む。"
            ),
        ),
        # Two descriptions whose words used to reach a branch that invented:
        # `影`/`沈む` summoned a surface-tension mark, `落ち葉`/`森` a leaf-grain
        # energy. Both branches are gone (v2.11.0) and these freeze their silence.
        "B-surface-tension-words": _coerce_input(
            _score([line]), ddl="布の影が机に落ちて沈む。"
        ),
        "B-leaf-grain-words": _coerce_input(
            _score([line]), ddl="森の落ち葉が湿った土に重なる。"
        ),
        # Two cases for the literal band above what a reader counts on one hand.
        # The corpus had none: every stated count in it sits at or below eleven,
        # so widening the band to `literal_count_threshold - 1` moved none of the
        # twenty-one frozen cases, and refreezing would have recorded a layer the
        # change never traversed. Both are synthetic (2026-08-10 ruling), and
        # they are a pair on purpose -- the first has the branch write the stated
        # number, the second has it decline, so the record carries the guard as
        # well as the repair.
        "B-stated-count-in-the-wide-band": _coerce_input(
            _score([_instruction(
                primitive="circle", **{"from": None}, to=None, center=[0.5, 0.5], radius=0.06,
                arrangement={**copy.deepcopy(BASE_ARRANGEMENT), "count": 7},
            )]),
            ddl="黒いペンの小さな円を三十個散らす。",
        ),
        # Two hundred squares leave room for five more marks, not for the two
        # hundred thirty-three the clause asks for. The branch runs after both
        # density budgets, so declining is the only way the count stays a number
        # somebody chose: the hard ceiling at the exit would otherwise trim the
        # forced value to whatever its division returned.
        "B-stated-count-over-the-work-budget": _coerce_input(
            _score([
                _instruction(
                    primitive="square", **{"from": None}, to=None,
                    position=[0.15, 0.5], size=[0.10, 0.10],
                    arrangement={**copy.deepcopy(BASE_ARRANGEMENT), "count": 200},
                ),
                _instruction(
                    primitive="circle", **{"from": None}, to=None, center=[0.7, 0.5], radius=0.06,
                    arrangement={**copy.deepcopy(BASE_ARRANGEMENT), "count": 5},
                ),
            ]),
            ddl="黒いペンの円を二百三十三個散らす。",
        ),
        "B-production-multiline": _coerce_input(
            _score([_instruction(color="white")], background="black"),
            ddl=(
                "地: 生成りの紙、細かい紙目。\n"
                "背景を黒で塗りつぶす。白い右下がりの小さな楕円を百三十七個を散らす。"
            ),
        ),
    }
    return cases

def _canonical_output(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

def _source_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REFERENCE_ROOT.parent.parent,
                          check=True, capture_output=True, text=True).stdout.strip()

def _render_cases() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    manifest_cases: dict[str, dict[str, Any]] = {}
    outputs: dict[str, str] = {}
    for case_id, input_data in sorted(build_expand_inputs().items()):
        output = expand_intermediate_ddl(**input_data)
        text = output + ("" if output.endswith("\n") else "\n")
        path = f"a_expand/{case_id}.ddl"
        outputs[path] = text
        manifest_cases[case_id] = {
            "part": "a_expand", "input": input_data, "output_path": path,
            "digest": _digest(text), "bytes": len(text.encode("utf-8")),
        }
    for case_id, input_data in sorted(build_coerce_inputs().items()):
        report: dict[str, int] = {}
        score = coerce_score(Score.model_validate(input_data["score"]), ddl=input_data["ddl"],
                             branch_report=report)
        text = _canonical_output({"score": score.model_dump(by_alias=True, mode="json"), "branch_report": report})
        path = f"b_coerce/{case_id}.json"
        outputs[path] = text
        manifest_cases[case_id] = {
            "part": "b_coerce", "input": input_data, "output_path": path,
            "digest": _digest(text), "bytes": len(text.encode("utf-8")),
            "instruction_count": len(score.instructions),
            "fired_branches": {key: value for key, value in sorted(report.items()) if value},
        }
    manager = PluginDocumentManager(PLUGIN_DIR)
    for case_id, input_data in sorted(build_plugin_expand_inputs().items()):
        expansion = manager.expand(
            input_data["ddl"], source_text=input_data["source_text"],
            lang=input_data["lang"], seed_text=input_data["seed_text"],
        )
        text = _canonical_output({
            "ddl": expansion.ddl,
            "provenance": [dict(entry) for entry in expansion.provenance],
            "warnings": list(expansion.warnings),
            "instructions": [dict(entry) for entry in expansion.instructions],
        })
        path = f"c_plugin_expand/{case_id}.json"
        outputs[path] = text
        manifest_cases[case_id] = {
            "part": "c_plugin_expand", "input": input_data, "output_path": path,
            "digest": _digest(text), "bytes": len(text.encode("utf-8")),
            # The two quantities the ruling separated: how many whole units the
            # body asked for, and whether the layer declined to deliver them.
            "units": [int(entry["units"]) for entry in expansion.provenance if "units" in entry],
            "declined": bool(expansion.warnings),
        }
    return manifest_cases, outputs

def _previous_manifest() -> dict[str, Any] | None:
    """The frozen manifest of the highest engine version below the current one."""
    current = int(DDL_ENGINE_VERSION)
    candidates: list[tuple[int, pathlib.Path]] = []
    for path in REFERENCE_ROOT.glob("ddl-engine-*/manifest.json"):
        suffix = path.parent.name.rsplit("-", 1)[-1]
        if suffix.isdigit() and int(suffix) < current:
            candidates.append((int(suffix), path))
    if not candidates:
        return None
    return json.loads(max(candidates)[1].read_text(encoding="utf-8"))

def generate() -> None:
    existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else None
    cases, outputs = _render_cases()
    identity = {"corpus_format_version": CORPUS_FORMAT_VERSION, "layer": "ddl-engine",
                "engine_version": DDL_ENGINE_VERSION, "ddl_version": DDL_VERSION,
                "schema_version": SCHEMA_VERSION}
    if existing is None:
        # A version can go up without the transform moving - the declaration order
        # of `Instruction` is such a reason. Listing every case as changed would
        # make the manifest claim the opposite of what the version means, so the
        # previous manifest decides, exactly as gen_render_reference.py does.
        # Unlike the render corpus, every version keeps a body for every case:
        # `test_ddl_reference_output_files_match_manifest` reads them all from the
        # current directory.
        previous = _previous_manifest()
        if previous is None:
            changed = sorted(cases)
        else:
            before = previous["cases"]
            changed = sorted(
                case_id for case_id, case in cases.items()
                if case_id not in before or before[case_id]["digest"] != case["digest"]
            )
        frozen = {"frozen_at": FROZEN_AT, "commit": _source_commit(), "reason": REASON,
                  "changed_from_previous": changed}
    else:
        frozen = {key: existing[key] for key in ("frozen_at", "commit", "reason", "changed_from_previous")}
    manifest = {**identity, **frozen, "cases": cases}
    for directory in (OUTPUT_DIR, OUTPUT_DIR / "a_expand", OUTPUT_DIR / "b_coerce",
                      OUTPUT_DIR / "c_plugin_expand"):
        directory.mkdir(parents=True, exist_ok=True)
    for path, text in outputs.items():
        (OUTPUT_DIR / path).write_text(text, encoding="utf-8")
    MANIFEST_PATH.write_text(_canonical_output(manifest), encoding="utf-8")

    # The guard fires *after* writing, exactly as gen_render_reference.py does. A
    # sanctioned rename moves the corpus without moving the engine, and the guard
    # cannot tell that from an unsanctioned rewrite; it fires once, and the second
    # run is clean and byte-identical, which is the property it defends. Raising
    # before the write would leave no way to re-freeze a rename at all.
    if existing is not None and existing.get("cases") != manifest["cases"]:
        before = tuple(existing.get(field) for field in IDENTITY_FIELDS)
        after = tuple(manifest.get(field) for field in IDENTITY_FIELDS)
        if before == after:
            raise SystemExit("DDL corpus changed without an identity-field change; bump the appropriate version instead of rewriting a frozen corpus")

if __name__ == "__main__":
    generate()

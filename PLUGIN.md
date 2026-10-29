# inku Vocabulary Plugin Authoring Guide

Plugins are data-only vocabulary macros. A definition expands into ordinary DDL drawing instructions. New files use `inku.plugin-package.v2`; v1 files are neither read nor converted. See [SPEC §4](SPEC.md) for the boundary.

## 1. Steps

1. Write an `inku.macro-definition.v2` definition for an object or a scene (§2–3).
2. Put the definition, Japanese and English notes, optional examples and pictures in an `inku.plugin-package.v2` file (§5.1).
3. An administrator chooses the JSON or zip in Web settings. The Server checks shape, definition, and drawings of the examples before installation.
4. Call a visible name in braces: `｛星｝。` or `{stars}.` The old `Sky.星` spelling is still read during the transition.

## 2. Object example

This definition draws one yellow star. `id` is the stable lock identity; `names` are the visible DDL spellings. An object declares an aspect ratio, may declare a Japanese counter, and does not receive a `count` parameter.

```json
{
  "schema": "inku.macro-definition.v2",
  "namespace": "Sky",
  "id": "Stars",
  "names": {"ja": ["星"], "en": ["stars"]},
  "kind": "object",
  "aspect": "1:1",
  "counter": "general",
  "version": "1.0.0",
  "parameters": {},
  "components": {},
  "body": [{
    "op": "emit",
    "fields": {
      "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
      "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
      "relative_scale": {"expr": "semantic_ref", "category": "relative_scale", "id": "small"},
      "color": {"expr": "semantic_ref", "category": "color", "id": "yellow"},
      "touch": {"expr": "semantic_ref", "category": "touch", "id": "pencil"},
      "surface": {"expr": "semantic_ref", "category": "surface", "id": "solid"}
    }
  }]
}
```

For an object example, write a position and a count, such as `Place 3 {stars} at the upper left.` The outer count repeats the whole object.

## 3. Definition rules

### 3.1 Top-level fields and a scene example

Write `schema`, `namespace`, `id`, `names`, `kind`, `version`, `parameters`, `components`, and `body`. `kind` is `object` or `scene`. An object needs `aspect` (two integers from 1 to 16 separated by `:`) and may have `counter` (`flat`, `long`, or `general`). A scene has neither.

```json
{
  "schema": "inku.macro-definition.v2",
  "namespace": "Sky",
  "id": "StarField",
  "names": {"ja": ["星原"], "en": ["star field"]},
  "kind": "scene",
  "version": "1.0.0",
  "parameters": {},
  "components": {},
  "body": [{"op": "emit", "fields": {
    "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
    "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
    "position_x": {"expr": "exact_decimal", "value": "0.500"},
    "position_y": {"expr": "exact_decimal", "value": "0.250"},
    "relative_scale": {"expr": "semantic_ref", "category": "relative_scale", "id": "small"},
    "color": {"expr": "semantic_ref", "category": "color", "id": "yellow"},
    "touch": {"expr": "semantic_ref", "category": "touch", "id": "pencil"},
    "surface": {"expr": "semantic_ref", "category": "surface", "id": "solid"}
  }}]
}
```

### 3.2 Names and identifiers

`namespace` and `id` start with an ASCII letter and then use ASCII letters, digits, `_`, or `-`. `names.ja/en` contain visible names, with the primary name first. A name cannot be empty or contain control characters, braces, a dot, or a namespace. Matching normalizes NFKC, lowercases, and collapses whitespace. A plugin may not claim a core word. One catalog name belongs to only one definition, and a file claiming an installed plugin's name is refused.

### 3.3 Parameters and body

Parameter types are `semantic_ref` (category and optional dimension), `exact_decimal` (optional dimension), `integer`, `number`, `boolean`, and `list`. Required parameters are not silently defaulted. A scene call with an undeclared modifier omits that modifier with a diagnostic while keeping the call. Composition and rules place, size, count, and arrange an object through its aspect rectangle without changing its shape. Coloring changes a plugin only when its definition accepts color. A scene remains an inserted drawing.

Only a scene may declare one top-level integer parameter such as `{"type":"integer","receives":"count","minimum":1,"maximum":9,"omitted":[3,4,5],"counter":"general"}`. The omitted count comes from its candidates and seed. An out-of-range count omits only that call with `macro_binding_count_out_of_range`. Without the declaration, the count repeats the whole scene.

Expressions use `expr`: `semantic_ref`, `exact_decimal` for positions and dimensions, `integer`, `number`, `boolean`, `list`, `cycle`, `parameter`, and `local`. Arithmetic is absent. The finite body uses `emit`, `repeat`, `vary`, `use`, `transform`, `anchor`, and `relation`, among others. See the [DDL reference](manual/en/ddl-reference.md) and the [shared core](core/crates/inku-ddl/src/macro_definition.rs) for supported meanings and fields. A plugin cannot add a primitive or executable hook.

## 4. Calling a plugin from DDL

Put a visible name in braces: `｛星｝。` or `{stars}.` Modifiers attach to that call. An object's shape stays fixed while composition and rules act on its aspect rectangle. A scene stays an inserted drawing. Saved works retain their exact definitions and locks for replay.

## 5. Loading a definition

### 5.1 Adding a plugin file from the Web

Save this one-word file as `package.json` and choose it in Web settings. To include a picture, put `package.json` at the root of a zip alongside its PNG and write `"preview":"previews/stars.png"` in the word.

```json
{
  "schema": "inku.plugin-package.v2",
  "namespace": "Sky",
  "name": "night",
  "version": "1.0.0",
  "description_ja": "夜空の語。",
  "description_en": "Words of the night sky.",
  "words": [{
    "definition": {
      "schema": "inku.macro-definition.v2",
      "namespace": "Sky",
      "id": "Stars",
      "names": {"ja": ["星"], "en": ["stars"]},
      "kind": "object",
      "aspect": "1:1",
      "counter": "general",
      "version": "1.0.0",
      "parameters": {},
      "components": {},
      "body": [{"op": "emit", "fields": {
        "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
        "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
        "relative_scale": {"expr": "semantic_ref", "category": "relative_scale", "id": "small"},
        "color": {"expr": "semantic_ref", "category": "color", "id": "yellow"},
        "touch": {"expr": "semantic_ref", "category": "touch", "id": "pencil"},
        "surface": {"expr": "semantic_ref", "category": "surface", "id": "solid"}
      }}]
    },
    "note_ja": "夜空に黄色い星を描く。",
    "note_en": "Draws a yellow star in the night sky.",
    "example_ja": "｛星｝を置く。",
    "example_en": "Place {stars}."
  }]
}
```

Top-level fields are `schema`, `namespace`, `name`, `version`, optional `description_ja/en`, `authors`, `license`, and `words`. A word has only `definition`, `note_ja/en`, `example_ja/en`, and `preview`. At least one note is required; each is at most 100 characters, and a missing language uses the other. A missing example defaults to `｛primary name｝。` or `{primary name}.` An explicit example must call the braced primary name. A preview is a PNG within a zip.

The checks run in order: file shape, shared-core definition validation, and drawing the Japanese and English examples. All must pass. Administrators can install, replace, disable, delete, replace preview pictures, and export a zip. Installed words enter the catalog for new works and the Saijiki; notes are also used in the underdrawing offer. The bundled `Nature.leaves` is a v2 file in core: it can be disabled but neither deleted nor given custom pictures. APIs include `POST /api/plugins/packages/validate`, `POST /api/plugins/packages`, and `GET /api/plugins/{id}/export`.

### 5.2 DDL export file

`GET /api/pipeline/history/{id}/ddl-export` emits `inku.ddl-export.v2`. Its `plugins` carry definitions selected by the saved locks as `{definition,note}`, independent of spelling in the DDL text. Import applies them to one new work without installing them. An imported definition wins over an installed one with the same id; a difference produces a diagnostic. Export a v1 file again as v2 before importing it.

### 5.3 Server manifest

An administrator may place definitions in `pipeline.definitions` and corresponding short notes in `pipeline.macro_summaries`. Mismatched list lengths cause `macro_catalog_summary_mismatch`.

### 5.4 Bundled words

The seven leaf words and their PNGs are in `core/crates/inku-ddl/assets/nature-leaves-v2/`. The shared-core `plugin_package` action `bundled_nature` hands them to the Server. Existing macOS and Android UI resources will follow the new names in a later step.

## 6. Writing a note

Write one sentence about what the thing is, in at most 100 characters per language. The same text is used in the Stage 1 offer and Saijiki description. State drawing facts such as place, material, or color rather than relying on seasonal or similar-word associations.

## 7. Checks and problem codes

### 7.1 Three checks

Shape problems do not hide definition and example problems when those can still be checked. Each problem has a path and code. An example is not drawn when its definition is invalid. The Web check screen explains codes in Japanese and English.

### 7.2 Definition codes

`invalid_canonical_definition`, `unknown_json_field`, `duplicate_qualified_name`, `name_taken`, `name_is_core_word`, `invalid_plugin_kind`, `invalid_plugin_aspect`, `invalid_plugin_counter`, `scene_has_aspect`, `scene_has_counter`, `object_count_parameter`, `unknown_semantic_id`, `unknown_semantic_category`, `unknown_semantic_field`, `semantic_field_requires_matching_reference`, `geometry_field_requires_exact_decimal`, `invalid_count_parameter`, `invalid_repeat_count`, `unbounded_repeat`, `undefined_parameter`, `undefined_local`, `undefined_anchor`, and `component_cycle` identify the relevant definition field.

Other definition codes: `anchor_requires_one_explicit_position`, `argument_type_mismatch`, `count_parameter_in_component`, `duplicate_alias`, `duplicate_anchor_or_binding`, `duplicate_count_parameter`, `duplicate_local_binding`, `duplicate_plugin_name`, `empty_cycle`, `empty_transform`, `empty_vary`, `external_component_reference`, `heterogeneous_cycle`, `invalid_alias`, `invalid_anchor_or_binding_id`, `invalid_component_id`, `invalid_cycle_index`, `invalid_emit_count_type`, `invalid_endpoint_target`, `invalid_local_binding_id`, `invalid_parameter_id`, `invalid_plugin_id`, `invalid_plugin_name`, `invalid_semantic_dimension`, `invalid_vary_domain`, `invalid_vary_range`, `invalid_vary_source`, `missing_argument`, `non_finite_number`, `path_position_requires_connected`, `path_position_requires_number`, `resource_bound_overflow`, `transform_requires_number`, `undefined_component`, `unknown_anchor_field`, `unknown_argument`, `unknown_schema`, `vary_choice_type_mismatch`.

### 7.3 File, example, and picture codes

File: `invalid_json`, `package_too_large`, `not_an_object`, `unknown_field`, `wrong_schema`, `rewrite_as_v2`, `definition_requires_v2`, `invalid_identifier`, `invalid_semantic_version`, `not_a_string`, `not_a_list_of_strings`, `text_too_long`, `no_words`, `too_many_words`, `namespace_differs_from_package`, `id_differs_from_directory`, `invalid_package_id`, `bundled_package_id`, `no_note`, `example_without_name`. `rewrite_as_v2` means to rewrite a v1 file as v2 and install it again.

Example: `macro_binding_count_out_of_range`, `macro_resolution_missing_lock`, `compiler_diagnostics`, `example_draws_nothing`, `example_not_drawn`.

Picture and zip: `not_a_png`, `image_too_large`, `preview_needs_zip`, `preview_not_found`, `invalid_preview_path`, `invalid_zip`, `not_base64`, `archive_too_large`, `too_many_archive_members`, `archive_without_package_json`, `not_utf8`. `not_base64` comes from the Server's request check.

## 8. Limits

File: 1,000,000 bytes; words: 64; `description_*`: 2,000 characters; `note_*`: 100; `example_*`: 500; `license`: 200. A PNG is at most 2 MiB and 4096×4096 pixels. A zip is at most 16 MiB, 256 members, and 64 MiB of PNG data. Preview frames are 216×92 pixels and twice that size.

## 9. Boundaries

A plugin cannot change the meanings of core words or primitives, run code, add hooks, or extend DDL syntax. V1 packages are not accepted.

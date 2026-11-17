use std::collections::HashSet;

use inku_ddl::{
    ResolvedInstructionLanguage, SAIJIKI_ASSET_BYTES, SAIJIKI_ASSET_ID, SaijikiAsset,
    SaijikiWordAsset, project_macro_semantic_ref, saijiki_asset, saijiki_asset_sha256_hex,
    saijiki_derived_projection, saijiki_derived_projection_from_asset, saijiki_marker_class_table,
    saijiki_score_wire_maps,
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

/// A named edit that must make the asset fail closed.
type AssetMutation = (&'static str, fn(&mut SaijikiAsset));
type ValueMutation = (&'static str, fn(&mut Value));

#[test]
fn embedded_asset_has_stable_identity_and_exact_digest() {
    let asset = saijiki_asset();

    assert_eq!(asset.schema_version, 1);
    assert_eq!(asset.asset_id, SAIJIKI_ASSET_ID);
    assert_eq!(SAIJIKI_ASSET_ID, "inku.saijiki.v4");
    assert_eq!(
        saijiki_asset_sha256_hex(),
        Sha256::digest(SAIJIKI_ASSET_BYTES)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    );
    assert_eq!(saijiki_asset_sha256_hex().len(), 64);
    assert!(
        saijiki_asset_sha256_hex()
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (byte as char).is_ascii_lowercase())
    );
}

#[test]
fn embedded_asset_is_complete_and_orders_are_lossless() {
    let asset = saijiki_asset();
    let angles = asset
        .categories
        .iter()
        .find(|category| category.key == "katamuki")
        .unwrap();
    assert_eq!(
        angles.words[0].parser_surfaces_ja.as_deref(),
        Some(["横".to_owned()].as_slice())
    );
    assert_eq!(
        angles.words[1].parser_surfaces_ja.as_deref(),
        Some(["縦".to_owned()].as_slice())
    );
    assert!(angles.words[0].marker_surfaces_ja.is_none());

    assert_eq!(asset.languages, ["ja", "en"]);
    assert_eq!(asset.categories.len(), 16);
    let shape = asset
        .categories
        .iter()
        .find(|category| category.key == "katachi")
        .unwrap();
    // v4: 半円 and 三日月 moved into かたち (field arc_form), and 多角形 is offered.
    assert_eq!(shape.words.len(), 12);
    assert_eq!(
        shape
            .words
            .iter()
            .find(|word| word.surface_en.as_deref() == Some("square"))
            .unwrap()
            .parser_surfaces_en
            .as_deref(),
        Some(["rectangle".to_owned()].as_slice())
    );
    assert_eq!(
        asset
            .categories
            .iter()
            .map(|category| category.words.len())
            .sum::<usize>(),
        // ばしょ keeps 始点・終点・途中 as marker-only rows, read as in v3.
        106
    );
    assert_eq!(asset.relations.len(), 11);
    assert_eq!(
        asset
            .categories
            .iter()
            .map(|category| category.key.as_str())
            .collect::<Vec<_>>(),
        [
            "katachi",
            "katamuki",
            "tezawari",
            "tsuranari",
            "omote",
            "sabaki",
            "kime",
            "ji",
            "iro",
            "yuragi",
            "basho",
            "ugoki",
            "jun",
            "wariai",
            "futosa",
            "ookisa",
        ]
    );
    assert_eq!(
        asset
            .relations
            .iter()
            .map(|relation| relation.relation_type.as_str())
            .collect::<Vec<_>>(),
        [
            "along",
            "not_touching",
            "touching",
            "cutting",
            "between",
            "connected",
            "resting_on",
            "inside",
            "overlapping",
            "crossing",
            "mirrored"
        ]
    );
    assert_eq!(
        asset.relation_marker_order.ja,
        [
            "触れる",
            "つながる",
            "沿う",
            "横切る",
            "切る",
            "触れない",
            "間に",
            "載る",
            "中に",
            "重なる",
            "鏡写し"
        ]
    );
    assert_eq!(
        asset.relation_marker_order.en,
        [
            "touching",
            "connected",
            "along",
            "crossing",
            "cutting",
            "not touching",
            "between",
            "resting on",
            "inside",
            "overlaps",
            "mirrored"
        ]
    );
    assert_eq!(
        asset.relation_display_order,
        [
            "along",
            "not_touching",
            "cutting",
            "between",
            "touching",
            "connected",
            "resting_on",
            "inside",
            "overlapping",
            "crossing",
            "mirrored"
        ]
    );
    assert_eq!(
        asset.marker_class_order,
        ["material", "color", "variation", "angle", "ratio", "place"]
    );

    let category_keys = asset
        .categories
        .iter()
        .map(|category| category.key.as_str())
        .collect::<HashSet<_>>();
    let relation_types = asset
        .relations
        .iter()
        .map(|relation| relation.relation_type.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(category_keys.len(), 16);
    assert_eq!(relation_types.len(), 11);

    let aliases = asset
        .categories
        .iter()
        .flat_map(|category| &category.words)
        .filter_map(|word| {
            word.semantic_alias
                .as_deref()
                .map(|alias| (word.surface_ja.as_str(), alias))
        })
        .collect::<Vec<_>>();
    assert!(aliases.is_empty());

    let angles = asset
        .categories
        .iter()
        .find(|category| category.key == "katamuki")
        .unwrap();
    for (ja, en) in [("左上がり", "left-rising"), ("左下がり", "left-falling")] {
        let word = angles
            .words
            .iter()
            .find(|word| word.surface_ja == ja)
            .unwrap();
        assert_eq!(word.surface_en.as_deref(), Some(en));
        // v4 offers both to the list and the reader (prompt and display).
        assert!(word.prompt);
        assert!(word.display);
        assert_eq!(word.marker, Some(true));
        assert!(word.score_value.is_none());
    }
}

#[test]
fn invalid_semantic_aliases_fail_closed_with_distinct_stable_kinds() {
    let cases: [AssetMutation; 4] = [
        (
            "missing_semantic_alias_target",
            |asset: &mut SaijikiAsset| {
                place_word_mut(asset, "中心").semantic_alias = Some("absent".to_owned());
            },
        ),
        (
            "semantic_alias_category_crossing",
            |asset: &mut SaijikiAsset| {
                place_word_mut(asset, "中心").semantic_alias = Some("blue".to_owned());
            },
        ),
        ("semantic_alias_cycle", |asset: &mut SaijikiAsset| {
            place_word_mut(asset, "中心").semantic_alias = Some("center".to_owned());
        }),
        ("conflicting_semantic_alias", |asset: &mut SaijikiAsset| {
            place_word_mut(asset, "中心").semantic_alias = Some("center".to_owned());
            // The id is the word's own field (Saijiki v4, D1), not derived from its English.
            place_word_mut(asset, "上").id = Some("center".to_owned());
        }),
    ];

    for (expected_kind, mutate) in cases {
        let mut asset: SaijikiAsset = serde_json::from_slice(SAIJIKI_ASSET_BYTES).unwrap();
        mutate(&mut asset);
        let error = saijiki_derived_projection_from_asset(&asset, ResolvedInstructionLanguage::En)
            .unwrap_err();
        assert_eq!(error.kind(), expected_kind);
    }
}

#[test]
fn typed_english_grammar_is_row_owned_and_does_not_leak_into_public_projections() {
    let asset_value: Value = serde_json::from_slice(SAIJIKI_ASSET_BYTES).unwrap();
    // The amplitude words are adverbs only (narrowly, broadly) and carry no
    // grammar of their own; an adjective form would read as a shape's width or size.
    for surface_ja in ["小さく", "大きく", "ゆるやかに", "小刻みに"] {
        assert_eq!(
            word_value(&asset_value, "yuragi", surface_ja).get("english_grammar"),
            None
        );
    }
    for (surface_ja, grammar) in [
        (
            "揺れる",
            json!({
                "lemma": "sway",
                "lexical_class": "verb",
                "canonical_form": "present_participle",
                "permitted_forms": ["third_person_singular"]
            }),
        ),
        (
            "波打つ",
            json!({
                "lemma": "undulate",
                "lexical_class": "verb",
                "canonical_form": "present_participle",
                "permitted_forms": ["third_person_singular"]
            }),
        ),
    ] {
        assert_eq!(
            word_value(&asset_value, "yuragi", surface_ja).get("english_grammar"),
            Some(&grammar)
        );
    }
    let words = asset_value["categories"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|category| category["words"].as_array().unwrap());
    assert_eq!(
        words
            .clone()
            .filter(|word| word.get("english_grammar").is_some())
            .count(),
        5
    );
    assert!(
        words
            .clone()
            .all(|word| word.get("parser_forms_en").is_none())
    );
    let asset_source = std::str::from_utf8(SAIJIKI_ASSET_BYTES).unwrap();
    assert!(!asset_source.contains("parser_forms_en"));
    // The v1 aliases were rewritten to their words by the v2 migration (SPEC §3.3).
    for (category, word) in [
        ("yuragi", "揺れる"),
        ("sabaki", "にじみ"),
        ("basho", "中心"),
        ("omote", "点描"),
    ] {
        let row = word_value(&asset_value, category, word);
        assert!(row.get("parser_surfaces_ja").is_none(), "{word}");
        assert!(row.get("parser_surfaces_en").is_none(), "{word}");
    }
    for surface in [
        "finely",
        "largely",
        "sways",
        "undulates",
        "trembling",
        "trembles",
        "blurring",
        "middle",
        "震える",
        "滲む",
        "中央",
    ] {
        assert!(
            !asset_source.contains(&format!("\"{surface}\"")),
            "{surface}"
        );
    }

    let projection = saijiki_derived_projection(ResolvedInstructionLanguage::En).unwrap();
    let markers = saijiki_marker_class_table(ResolvedInstructionLanguage::En).unwrap();
    let score_maps = saijiki_score_wire_maps().unwrap();
    for derived_surface in ["finely", "largely", "sways", "undulates", "trembles"] {
        assert!(!projection.prompt_block.contains(derived_surface));
        assert!(projection.display_categories.iter().all(|category| {
            category
                .words
                .iter()
                .all(|surface| surface != derived_surface)
        }));
        assert!(markers.iter().all(|class| {
            class
                .markers
                .iter()
                .all(|surface| surface != derived_surface)
        }));
        assert!(
            score_maps
                .weight
                .iter()
                .chain(&score_maps.color)
                .chain(&score_maps.surface_texture)
                .all(|entry| entry.surface != derived_surface)
        );
    }
    for (surface_ja, canonical_id) in [
        ("小さく", "narrowly"),
        ("大きく", "broadly"),
        ("ゆるやかに", "loosely"),
        ("小刻みに", "tightly"),
        ("揺れる", "swaying"),
        ("波打つ", "undulating"),
    ] {
        assert_eq!(
            project_macro_semantic_ref("yuragi", surface_ja)
                .unwrap()
                .canonical_id,
            canonical_id
        );
    }
}

#[test]
fn invalid_typed_english_grammar_fails_closed_with_stable_kinds() {
    let cases: [ValueMutation; 9] = [
        ("duplicate_english_grammatical_form", |asset| {
            word_value_mut(asset, "katamuki", "水平")["english_grammar"]["permitted_forms"] =
                json!(["adverb", "adverb"]);
        }),
        ("parser_surface_collision", |asset| {
            let first = word_value_mut(asset, "yuragi", "大きく");
            first["surface_en"] = json!("foo");
            first["english_grammar"] = json!({
                "lemma": "foo",
                "lexical_class": "verb",
                "canonical_form": "base",
                "permitted_forms": ["present_participle"]
            });
            let second = word_value_mut(asset, "yuragi", "ゆるやかに");
            second["surface_en"] = json!("fooe");
            second["english_grammar"] = json!({
                "lemma": "fooe",
                "lexical_class": "verb",
                "canonical_form": "base",
                "permitted_forms": ["present_participle"]
            });
        }),
        ("parser_surface_collision", |asset| {
            let word = word_value_mut(asset, "yuragi", "大きく");
            word["surface_en"] = json!("NARROWLY");
            word.as_object_mut().unwrap().remove("english_grammar");
        }),
        ("ineligible_english_grammar", |asset| {
            // v4 has no disabled row (the 描く tombstone is gone): disable one for the case.
            let word = word_value_mut(asset, "ugoki", "引く");
            word["prompt"] = json!(false);
            word["display"] = json!(false);
            word["marker"] = json!(false);
            word["english_grammar"] = json!({
                "lemma": "draw",
                "lexical_class": "verb",
                "canonical_form": "base",
                "permitted_forms": ["third_person_singular"]
            });
        }),
        ("missing_language_surface", |asset| {
            word_value_mut(asset, "katamuki", "水平")["surface_en"] = Value::Null;
        }),
        ("invalid_english_lemma", |asset| {
            word_value_mut(asset, "katamuki", "水平")["english_grammar"]["lemma"] =
                json!(" horizontal ");
        }),
        ("incompatible_english_grammar_form", |asset| {
            word_value_mut(asset, "katamuki", "水平")["english_grammar"]["canonical_form"] =
                json!("present_participle");
        }),
        ("canonical_english_form_mismatch", |asset| {
            word_value_mut(asset, "katamuki", "水平")["english_grammar"]["lemma"] =
                json!("horizontals");
        }),
        ("reserved_parser_surface_collision", |asset| {
            let word = word_value_mut(asset, "yuragi", "大きく");
            word["surface_en"] = json!("touch");
            word["english_grammar"] = json!({
                "lemma": "touch",
                "lexical_class": "verb",
                "canonical_form": "base",
                "permitted_forms": ["present_participle"]
            });
        }),
    ];

    for (expected_kind, mutate) in cases {
        let mut value: Value = serde_json::from_slice(SAIJIKI_ASSET_BYTES).unwrap();
        mutate(&mut value);
        let asset: SaijikiAsset = serde_json::from_value(value).unwrap();
        let error = saijiki_derived_projection_from_asset(&asset, ResolvedInstructionLanguage::En)
            .unwrap_err();
        assert_eq!(error.kind(), expected_kind);
    }

    for (field, unknown) in [
        ("lexical_class", "adverb"),
        ("canonical_form", "past_tense"),
    ] {
        let mut value: Value = serde_json::from_slice(SAIJIKI_ASSET_BYTES).unwrap();
        word_value_mut(&mut value, "katamuki", "水平")["english_grammar"][field] = json!(unknown);
        assert!(serde_json::from_value::<SaijikiAsset>(value).is_err());
    }
}

#[test]
fn alias_free_rows_keep_their_existing_lexical_semantic_identity() {
    // futosa and ookisa are core-modifier categories: syntax modifiers, not Saijiki
    // words, so they have no Macro semantic ref projection.
    for category in saijiki_asset()
        .categories
        .iter()
        .filter(|category| category.core_modifier.is_none())
    {
        for word in &category.words {
            if word.semantic_alias.is_some() {
                continue;
            }
            // The word's own id (Saijiki v4, D1): the identity v3 derived from the Score
            // value or the English surface, kept when the English surface was renamed.
            let expected = word
                .id
                .clone()
                .or_else(|| word.score_value.clone())
                .or_else(|| {
                    word.surface_en
                        .as_deref()
                        .map(|surface| surface.replace(['-', ' '], "_"))
                });
            assert_eq!(
                project_macro_semantic_ref(&category.key, &word.surface_ja)
                    .map(|projection| projection.canonical_id),
                expected,
                "{}/{}",
                category.key,
                word.surface_ja
            );
        }
    }
}

fn place_word_mut<'a>(asset: &'a mut SaijikiAsset, surface_ja: &str) -> &'a mut SaijikiWordAsset {
    word_mut(asset, "basho", surface_ja)
}

fn word_mut<'a>(
    asset: &'a mut SaijikiAsset,
    category_key: &str,
    surface_ja: &str,
) -> &'a mut SaijikiWordAsset {
    asset
        .categories
        .iter_mut()
        .find(|category| category.key == category_key)
        .unwrap()
        .words
        .iter_mut()
        .find(|word| word.surface_ja == surface_ja)
        .unwrap()
}

fn word_value<'a>(asset: &'a Value, category_key: &str, surface_ja: &str) -> &'a Value {
    asset["categories"]
        .as_array()
        .unwrap()
        .iter()
        .find(|category| category["key"].as_str() == Some(category_key))
        .unwrap()["words"]
        .as_array()
        .unwrap()
        .iter()
        .find(|word| word["surface_ja"].as_str() == Some(surface_ja))
        .unwrap()
}

fn word_value_mut<'a>(asset: &'a mut Value, category_key: &str, surface_ja: &str) -> &'a mut Value {
    asset["categories"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|category| category["key"].as_str() == Some(category_key))
        .unwrap()["words"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|word| word["surface_ja"].as_str() == Some(surface_ja))
        .unwrap()
}

#[test]
fn embedded_asset_keeps_hidden_pruned_nullable_override_and_score_semantics() {
    let asset = saijiki_asset();
    let category = |key| {
        asset
            .categories
            .iter()
            .find(|category| category.key == key)
            .unwrap()
    };
    let word = |category_key, surface_ja| {
        category(category_key)
            .words
            .iter()
            .find(|word| word.surface_ja == surface_ja)
            .unwrap()
    };

    let polygon = word("katachi", "多角形");
    // v4 offers 多角形 to the list and the reader (prompt and display), still a marker.
    assert!(polygon.prompt);
    assert!(polygon.display);
    assert_eq!(polygon.marker, Some(true));

    // 描く was withdrawn in v4: 引く is the one drawing verb.
    assert!(
        category("ugoki")
            .words
            .iter()
            .all(|word| word.surface_ja != "描く")
    );
    assert_eq!(word("ugoki", "引く").surface_en.as_deref(), Some("draw"));

    let line_up = word("ugoki", "並べる");
    assert_eq!(line_up.surface_en.as_deref(), Some("line-up"));
    assert_eq!(
        line_up.marker_surfaces_en.as_deref(),
        Some(&["arrange".to_owned()][..])
    );
    assert_eq!(
        word("tezawari", "ガッシュ").score_value.as_deref(),
        Some("gouache")
    );
    assert_eq!(word("iro", "灰").score_value.as_deref(), Some("gray"));
    assert_eq!(word("omote", "空").score_value.as_deref(), Some("none"));
    assert_eq!(
        word("ji", "薄墨地").score_value.as_deref(),
        Some("ink_wash")
    );

    assert_eq!(
        category("katachi").marker_order_ja,
        Some(vec![
            "線".to_owned(),
            "円".to_owned(),
            "楕円".to_owned(),
            "三角".to_owned(),
            "四角".to_owned(),
            "多角形".to_owned(),
            "弧".to_owned(),
            "自由線".to_owned(),
            "点".to_owned(),
            "雲形".to_owned(),
            // Saijiki v4 moved the arc forms from わりあい to かたち.
            "半円".to_owned(),
            "三日月".to_owned(),
        ])
    );
    assert_eq!(
        category("ugoki").marker_order_en,
        Some(vec![
            "place".to_owned(),
            "draw".to_owned(),
            "arrange".to_owned(),
            "scatter".to_owned(),
            "tile".to_owned(),
            "fill".to_owned(),
        ])
    );
}

// The Saijiki screen shows the categories by bundle, under the bundle's heading and in the
// bundle order (RECUT-PLAN §3, the author's choice 2026-11-17 15:4x). The hosts read both
// from the asset, so every category names a bundle the asset lists, once.
#[test]
fn every_category_belongs_to_one_listed_bundle_in_the_screen_order() {
    let asset = saijiki_asset();
    let keys = asset
        .bundles
        .iter()
        .map(|bundle| bundle.key.as_str())
        .collect::<Vec<_>>();
    assert_eq!(
        keys,
        ["what", "with", "face", "sway", "color", "where", "ground"]
    );
    assert_eq!(asset.bundles[0].name_ja, "何を");
    assert_eq!(asset.bundles[6].name_ja, "何の上に");
    for category in &asset.categories {
        let bundle = category
            .bundle
            .as_deref()
            .unwrap_or_else(|| panic!("{}", category.key));
        assert!(keys.contains(&bundle), "{} {bundle}", category.key);
    }
    for bundle in &keys {
        assert!(
            asset
                .categories
                .iter()
                .any(|category| category.bundle.as_deref() == Some(*bundle)),
            "{bundle}"
        );
    }
}

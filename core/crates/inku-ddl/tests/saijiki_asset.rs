use std::collections::HashSet;

use inku_ddl::{SAIJIKI_ASSET_BYTES, SAIJIKI_ASSET_ID, saijiki_asset, saijiki_asset_sha256_hex};
use sha2::{Digest, Sha256};

#[test]
fn embedded_asset_has_stable_identity_and_exact_digest() {
    let asset = saijiki_asset();

    assert_eq!(asset.schema_version, 1);
    assert_eq!(asset.asset_id, SAIJIKI_ASSET_ID);
    assert_eq!(SAIJIKI_ASSET_ID, "inku.saijiki.v1");
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

    assert_eq!(asset.languages, ["ja", "en"]);
    assert_eq!(asset.categories.len(), 11);
    assert_eq!(
        asset
            .categories
            .iter()
            .map(|category| category.words.len())
            .sum::<usize>(),
        88
    );
    assert_eq!(asset.relations.len(), 5);
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
            "ji",
            "iro",
            "yuragi",
            "basho",
            "ugoki",
            "wariai",
        ]
    );
    assert_eq!(
        asset
            .relations
            .iter()
            .map(|relation| relation.relation_type.as_str())
            .collect::<Vec<_>>(),
        ["along", "not_touching", "touching", "cutting", "between"]
    );
    assert_eq!(
        asset.relation_marker_order.ja,
        ["触れる", "沿う", "切る", "触れない", "間に"]
    );
    assert_eq!(
        asset.relation_marker_order.en,
        ["touching", "along", "cutting", "not touching", "between"]
    );
    assert_eq!(
        asset.relation_display_order,
        ["along", "not_touching", "cutting", "between", "touching"]
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
    assert_eq!(category_keys.len(), 11);
    assert_eq!(relation_types.len(), 5);
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
    assert!(!polygon.prompt);
    assert!(!polygon.display);
    assert_eq!(polygon.marker, Some(true));

    let draw_tombstone = word("ugoki", "描く");
    assert_eq!(draw_tombstone.surface_en, None);
    assert!(!draw_tombstone.prompt);
    assert!(!draw_tombstone.display);
    assert_eq!(draw_tombstone.marker, Some(false));

    let line_up = word("ugoki", "並べる");
    assert_eq!(line_up.surface_en.as_deref(), Some("line-up"));
    assert_eq!(
        line_up.marker_surfaces_en.as_deref(),
        Some(&["arrange".to_owned()][..])
    );
    assert_eq!(
        word("tezawari", "細筆").score_value.as_deref(),
        Some("brush_thin")
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
            "雲形".to_owned(),
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

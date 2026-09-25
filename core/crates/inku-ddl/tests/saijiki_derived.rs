use inku_ddl::{
    ResolvedInstructionLanguage, SaijikiProjectionError, saijiki_derived_projection,
    saijiki_derived_projection_from_asset, saijiki_marker_class_table,
    saijiki_relation_literal_table, saijiki_score_wire_maps,
};

#[test]
fn generation_vocabulary_separates_default_annotations_from_surface_forms() {
    for (language, annotation, surface) in [
        (ResolvedInstructionLanguage::Ja, "(既定)", "ペン"),
        (ResolvedInstructionLanguage::En, " (default)", "pen"),
    ] {
        let projection = saijiki_derived_projection(language).unwrap();
        assert!(!projection.prompt_block.contains(annotation));
        assert!(projection.prompt_block.contains(surface));
        assert!(
            projection
                .reference_categories
                .iter()
                .any(|category| { category.words.contains(&format!("{surface}{annotation}")) })
        );
    }
}

#[test]
fn full_language_projections_preserve_python_prompt_and_marker_behavior() {
    let ja = saijiki_derived_projection(ResolvedInstructionLanguage::Ja).unwrap();
    let en = saijiki_derived_projection(ResolvedInstructionLanguage::En).unwrap();
    assert!(!en.prompt_block.contains("vertically"));
    assert!(!en.prompt_block.contains("horizontally"));
    assert!(!en.prompt_block.contains("diagonally"));
    for word in ["rectangle", "equilateral triangle", "hexagon"] {
        assert!(!en.prompt_block.contains(word));
        assert!(!en.shape_markers.iter().any(|marker| marker == word));
    }
    for word in ["細長い", "縦に長い", "正三角形", "六角形"] {
        assert!(!ja.prompt_block.contains(word));
        assert!(!ja.shape_markers.iter().any(|marker| marker == word));
    }

    assert!(ja.prompt_block.starts_with("かたち: 円、楕円、三角"));
    assert!(
        en.prompt_block
            .starts_with("forms: circle, ellipse, triangle")
    );
    assert!(!ja.prompt_block.ends_with('\n'));
    assert!(!en.prompt_block.ends_with('\n'));
    assert_eq!(ja.texture_material_enumeration.split('・').count(), 12);
    assert!(en.texture_material_enumeration.ends_with(", or computer"));
    assert_eq!(
        ja.shape_markers,
        [
            "線",
            "円",
            "楕円",
            "三角",
            "四角",
            "多角形",
            "弧",
            "点",
            "雲形"
        ]
    );
    assert_eq!(
        en.core_grammar_markers,
        [
            "line",
            "circle",
            "ellipse",
            "triangle",
            "square",
            "polygon",
            "arc",
            "point",
            "cloudform",
            "place",
            "draw",
            "arrange",
            "scatter",
            "tile",
            "fill",
            "touching",
            "connected",
            "along",
            "cutting",
            "not touching",
            "between",
            "mirrored",
        ]
    );
    assert!(
        !ja.core_grammar_markers
            .iter()
            .any(|marker| marker == "anchor" || marker == "領域")
    );
    assert!(
        !en.core_grammar_markers
            .iter()
            .any(|marker| marker == "anchor" || marker == "region")
    );
    assert!(
        !en.core_grammar_markers
            .iter()
            .any(|marker| marker == "line-up")
    );
}

#[test]
fn ordered_marker_relation_reference_and_display_projections_match_asset_semantics() {
    let marker_classes = saijiki_marker_class_table(ResolvedInstructionLanguage::En).unwrap();
    assert_eq!(
        marker_classes
            .iter()
            .map(|row| row.marker_class.as_str())
            .collect::<Vec<_>>(),
        ["material", "color", "variation", "angle", "ratio", "place"]
    );
    assert_eq!(marker_classes[0].markers[0], "silverpoint");
    let angles = marker_classes
        .iter()
        .find(|row| row.marker_class == "angle")
        .unwrap();
    assert!(angles.markers.iter().any(|marker| marker == "left-rising"));
    assert!(angles.markers.iter().any(|marker| marker == "left-falling"));

    let relations = saijiki_relation_literal_table();
    assert_eq!(
        relations
            .iter()
            .map(|row| row.relation_type.as_str())
            .collect::<Vec<_>>(),
        [
            "along",
            "not_touching",
            "touching",
            "cutting",
            "between",
            "connected",
            "mirrored"
        ]
    );
    assert_eq!(relations[2].literals[0], "前の線に触れる");
    assert_eq!(relations[2].literals[2], "touching the previous line");

    let ja = saijiki_derived_projection(ResolvedInstructionLanguage::Ja).unwrap();
    let en = saijiki_derived_projection(ResolvedInstructionLanguage::En).unwrap();
    assert!(!en.prompt_block.contains("left-rising"));
    assert!(!en.prompt_block.contains("left-falling"));
    let angle_display = en
        .display_categories
        .iter()
        .find(|category| category.key == "katamuki")
        .unwrap();
    assert!(!angle_display.words.iter().any(|word| word == "left-rising"));
    assert!(
        !angle_display
            .words
            .iter()
            .any(|word| word == "left-falling")
    );
    assert!(
        !ja.reference_categories[9]
            .words
            .iter()
            .any(|word| word == "描く")
    );
    assert!(
        !en.display_categories[0]
            .words
            .iter()
            .any(|word| word == "polygon")
    );
    let aida = en.display_categories.last().unwrap();
    assert_eq!(aida.key, "aida");
    assert_eq!(aida.name_en, "relations");
    assert_eq!(
        aida.words,
        [
            "along",
            "not touching",
            "cutting",
            "between",
            "touching",
            "connected",
            "mirrored"
        ]
    );
}

#[test]
fn score_wire_maps_keep_order_and_explicit_surface_exclusion() {
    let maps = saijiki_score_wire_maps().unwrap();
    assert_eq!(maps.weight[0].surface, "銀筆");
    assert_eq!(maps.weight[0].score_value, "silverpoint");
    assert!(
        maps.weight
            .iter()
            .any(|pair| pair.surface == "oil paint" && pair.score_value == "oil_paint")
    );
    assert_eq!(maps.color[0].surface, "白");
    assert_eq!(maps.surface_texture[0].surface, "空");
    assert!(
        !maps
            .surface_texture
            .iter()
            .any(|pair| pair.surface == "濃い" || pair.surface == "薄い")
    );
    assert!(
        !maps
            .surface_texture
            .iter()
            .any(|pair| pair.surface == "dense" || pair.surface == "faint")
    );
}

#[test]
fn malformed_asset_returns_stable_typed_errors_without_fallback() {
    let mut value: serde_json::Value =
        serde_json::from_slice(inku_ddl::SAIJIKI_ASSET_BYTES).unwrap();
    value["categories"]
        .as_array_mut()
        .unwrap()
        .retain(|category| category["key"] != "tezawari");
    let missing_category = serde_json::from_value(value).unwrap();
    assert_eq!(
        saijiki_derived_projection_from_asset(&missing_category, ResolvedInstructionLanguage::Ja)
            .unwrap_err()
            .kind(),
        "missing_category"
    );

    let mut value: serde_json::Value =
        serde_json::from_slice(inku_ddl::SAIJIKI_ASSET_BYTES).unwrap();
    value["categories"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|category| category["key"] == "katachi")
        .unwrap()["marker_order_en"] = serde_json::json!(["line"]);
    let mismatched_order = serde_json::from_value(value).unwrap();
    assert!(matches!(
        saijiki_derived_projection_from_asset(&mismatched_order, ResolvedInstructionLanguage::En),
        Err(SaijikiProjectionError::MarkerOrderMismatch { .. })
    ));

    let mut value: serde_json::Value =
        serde_json::from_slice(inku_ddl::SAIJIKI_ASSET_BYTES).unwrap();
    value["categories"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|category| category["key"] == "katachi")
        .unwrap()["marker_order_en"] = serde_json::json!([
        "line",
        "line",
        "circle",
        "ellipse",
        "triangle",
        "square",
        "polygon",
        "arc",
        "cloudform"
    ]);
    let duplicate_order = serde_json::from_value(value).unwrap();
    assert_eq!(
        saijiki_derived_projection_from_asset(&duplicate_order, ResolvedInstructionLanguage::En)
            .unwrap_err()
            .kind(),
        "duplicate_marker_member"
    );
}

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage,
    associate_semantic_entities, compile_typed_ddl, stage15_transformation_input,
};

#[test]
fn size_candidates_keep_every_original_owner_through_compiler_admission() {
    for source in [
        "place one small large red circle at center.",
        "place one full-width half-width red line at center.",
        "place one red circle radius 0.1 diameter 0.3 at center.",
        "place one red circle with radius 0.2 diameter 0.1 at center.",
        "place one small red circle radius 0.1 at center.",
    ] {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, vec![]).unwrap();
        let association = associate_semantic_entities(&document).unwrap();
        assert!(
            association.ast.complete,
            "{source}: {:?}",
            association.issues
        );
        assert_eq!(
            association.owned_occurrence_count,
            association.delivered_occurrence_count
        );
        let entity = &association.ast.entities[0];
        let count = entity.relative_scale.iter().count()
            + entity.additional_relative_scales.len()
            + entity.explicit_geometry.iter().count()
            + entity.additional_explicit_geometries.len()
            + entity.proportion.width_extent.iter().count()
            + entity.additional_width_extents.len();
        assert_eq!(count, 2, "{source}");
        let compilation = compile_typed_ddl(
            document,
            &[],
            Some(0),
            MacroExpansionLimits {
                max_invocations: 4,
                max_depth: 4,
                max_evaluation_steps: 32,
                max_nodes_per_invocation: 8,
                max_total_nodes: 16,
            },
        );
        assert!(
            stage15_transformation_input(&compilation).is_ok(),
            "{source}: {:?}",
            compilation.conflicts
        );
    }
}

#[test]
fn non_size_conflicts_still_block_compiler_admission() {
    let document = NormalizedDdlDocument::new(
        "place one red blue circle at center.",
        ResolvedInstructionLanguage::En,
        vec![],
    )
    .unwrap();
    let compilation = compile_typed_ddl(
        document,
        &[],
        Some(0),
        MacroExpansionLimits {
            max_invocations: 4,
            max_depth: 4,
            max_evaluation_steps: 32,
            max_nodes_per_invocation: 8,
            max_total_nodes: 16,
        },
    );
    assert!(!compilation.conflicts.is_empty());
    assert!(stage15_transformation_input(&compilation).is_err());
}

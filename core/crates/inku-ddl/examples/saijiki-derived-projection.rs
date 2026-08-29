use inku_ddl::{
    ResolvedInstructionLanguage, saijiki_derived_projection, saijiki_marker_class_table,
    saijiki_relation_literal_table, saijiki_score_wire_maps,
};
use serde::Serialize;

#[derive(Serialize)]
struct DiagnosticProjection {
    languages: Languages,
    marker_class_table: MarkerClassTable,
    relation_literal_table: Vec<inku_ddl::RelationLiteralProjection>,
    score_wire_maps: inku_ddl::SaijikiScoreWireMaps,
}

#[derive(Serialize)]
struct Languages {
    ja: inku_ddl::SaijikiDerivedProjection,
    en: inku_ddl::SaijikiDerivedProjection,
}

#[derive(Serialize)]
struct MarkerClassTable {
    ja: Vec<inku_ddl::MarkerClassProjection>,
    en: Vec<inku_ddl::MarkerClassProjection>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let diagnostic = DiagnosticProjection {
        languages: Languages {
            ja: saijiki_derived_projection(ResolvedInstructionLanguage::Ja)?,
            en: saijiki_derived_projection(ResolvedInstructionLanguage::En)?,
        },
        marker_class_table: MarkerClassTable {
            ja: saijiki_marker_class_table(ResolvedInstructionLanguage::Ja)?,
            en: saijiki_marker_class_table(ResolvedInstructionLanguage::En)?,
        },
        relation_literal_table: saijiki_relation_literal_table(),
        score_wire_maps: saijiki_score_wire_maps()?,
    };
    println!("{}", serde_json::to_string(&diagnostic)?);
    Ok(())
}

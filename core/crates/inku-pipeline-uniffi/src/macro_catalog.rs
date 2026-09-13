//! Canonical MacroDefinition catalog boundary for host package discovery.

use std::{
    collections::BTreeSet,
    panic::{AssertUnwindSafe, catch_unwind},
};

use inku_ddl::{LegacyImportOutcome, MacroDefinition};
use serde::{Deserialize, Serialize};

const CATALOG_RESOLUTION_SCHEMA: &str = "inku.macro-catalog-resolution.v1";
const MAX_INPUT_BYTES: usize = 4 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CatalogInput {
    maximum_entries: usize,
    #[serde(default)]
    canonical: Vec<CanonicalCandidate>,
    #[serde(default)]
    legacy: Vec<LegacyCandidate>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CanonicalCandidate {
    source_id: String,
    definition_json: String,
    summary: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LegacyCandidate {
    source_id: String,
    qualified_name: String,
}

#[derive(Serialize)]
struct CatalogOutput {
    schema: &'static str,
    entries: Vec<CatalogEntry>,
    locks: Vec<DefinitionLock>,
    diagnostics: Vec<CatalogDiagnostic>,
}

#[derive(Serialize)]
struct CatalogEntry {
    source_id: String,
    definition: serde_json::Value,
    summary: String,
    qualified_name: String,
    version: String,
    digest: String,
}

#[derive(Serialize)]
struct DefinitionLock {
    qualified_name: String,
    version: String,
    digest: String,
}

#[derive(Serialize)]
struct CatalogDiagnostic {
    source_id: String,
    qualified_name: Option<String>,
    disposition: &'static str,
    reason: String,
    warnings: Vec<&'static str>,
    findings: Vec<DefinitionFinding>,
}

#[derive(Serialize)]
struct DefinitionFinding {
    code: String,
    path: String,
}

fn omitted(
    source_id: String,
    qualified_name: Option<String>,
    reason: impl Into<String>,
    warnings: Vec<&'static str>,
    findings: Vec<DefinitionFinding>,
) -> CatalogDiagnostic {
    CatalogDiagnostic {
        source_id,
        qualified_name,
        disposition: "omitted",
        reason: reason.into(),
        warnings,
        findings,
    }
}

fn resolve(input_bytes: &[u8]) -> Result<CatalogOutput, ()> {
    if input_bytes.len() > MAX_INPUT_BYTES {
        return Err(());
    }
    let input: CatalogInput = serde_json::from_slice(input_bytes).map_err(|_| ())?;
    if input.maximum_entries == 0 {
        return Err(());
    }
    let mut entries = Vec::new();
    let mut locks = Vec::new();
    let mut diagnostics = Vec::new();
    let mut names = BTreeSet::new();

    for candidate in input.canonical {
        let definition = match MacroDefinition::from_json(&candidate.definition_json) {
            Ok(definition) => definition,
            Err(error) => {
                diagnostics.push(omitted(
                    candidate.source_id,
                    None,
                    "invalid_canonical_definition",
                    vec![],
                    vec![DefinitionFinding {
                        code: error.code().to_owned(),
                        path: format!("{}:{}:{}", error.path(), error.line(), error.column()),
                    }],
                ));
                continue;
            }
        };
        let identity = match definition.identity() {
            Ok(identity) => identity,
            Err(validation) => {
                diagnostics.push(omitted(
                    candidate.source_id,
                    None,
                    "invalid_canonical_definition",
                    vec![],
                    validation
                        .diagnostics()
                        .iter()
                        .map(|finding| DefinitionFinding {
                            code: finding.code().to_owned(),
                            path: finding.path().to_owned(),
                        })
                        .collect(),
                ));
                continue;
            }
        };
        let qualified_name = identity.qualified_name().to_owned();
        if !names.insert(qualified_name.clone()) {
            diagnostics.push(omitted(
                candidate.source_id,
                Some(qualified_name),
                "duplicate_qualified_name",
                vec![],
                vec![],
            ));
            continue;
        }
        if entries.len() == input.maximum_entries {
            diagnostics.push(omitted(
                candidate.source_id,
                Some(qualified_name),
                "catalog_entry_limit",
                vec![],
                vec![],
            ));
            continue;
        }
        let version = identity.version().to_owned();
        let digest = identity.full_digest_hex().to_owned();
        let canonical = serde_json::from_slice(identity.canonical_json_bytes()).map_err(|_| ())?;
        locks.push(DefinitionLock {
            qualified_name: qualified_name.clone(),
            version: version.clone(),
            digest: digest.clone(),
        });
        entries.push(CatalogEntry {
            source_id: candidate.source_id,
            definition: canonical,
            summary: candidate.summary,
            qualified_name,
            version,
            digest,
        });
    }

    for candidate in input.legacy {
        let reason = if locks
            .iter()
            .any(|lock| lock.qualified_name == candidate.qualified_name)
        {
            "legacy_definition_replaced_by_canonical"
        } else {
            "legacy_semantics_require_authored_canonical_definition"
        };
        let outcome = LegacyImportOutcome::omitted(&candidate.qualified_name, reason);
        let warnings = outcome
            .warnings()
            .iter()
            .map(|warning| warning.code())
            .collect();
        let (qualified_name, reason) = match outcome {
            LegacyImportOutcome::Omitted {
                qualified_name,
                reason,
                ..
            } => (qualified_name, reason),
            LegacyImportOutcome::Imported { .. } => unreachable!(),
        };
        diagnostics.push(omitted(
            candidate.source_id,
            Some(qualified_name),
            reason,
            warnings,
            vec![],
        ));
    }

    Ok(CatalogOutput {
        schema: CATALOG_RESOLUTION_SCHEMA,
        entries,
        locks,
        diagnostics,
    })
}

/// Validate and identify host-discovered definitions without interpreting a package DSL.
#[uniffi::export]
pub fn resolve_macro_catalog(input_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| resolve(&input_bytes)))
        .ok()
        .and_then(Result::ok)
        .and_then(|output| serde_json::to_vec(&output).ok())
        .unwrap_or_else(|| {
            br#"{"schema":"inku.macro-catalog-resolution.v1","error":"invalid_macro_catalog_input"}"#
                .to_vec()
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn canonical_definition_is_identified_and_legacy_entry_is_typed_omission() {
        let input = json!({
            "maximum_entries": 2,
            "canonical": [{
                "source_id": "manifest:quiet",
                "definition_json": json!({
                    "schema": "inku.macro-definition.v1",
                    "namespace": "Example",
                    "heading": "Quiet",
                    "version": "1.0.0",
                    "parameters": {},
                    "components": {},
                    "body": []
                }).to_string(),
                "summary": "Quiet mark"
            }],
            "legacy": [{
                "source_id": "nature-leaves.inku-plugin.md",
                "qualified_name": "Nature.若葉"
            }]
        });
        let output: serde_json::Value =
            serde_json::from_slice(&resolve_macro_catalog(serde_json::to_vec(&input).unwrap()))
                .unwrap();
        assert_eq!(output["entries"][0]["qualified_name"], "Example.Quiet");
        assert_eq!(output["locks"][0]["version"], "1.0.0");
        assert_eq!(
            output["diagnostics"][0],
            json!({
                "source_id": "nature-leaves.inku-plugin.md",
                "qualified_name": "Nature.若葉",
                "disposition": "omitted",
                "reason": "legacy_semantics_require_authored_canonical_definition",
                "warnings": ["legacy_plugin_format"],
                "findings": []
            })
        );
    }
}

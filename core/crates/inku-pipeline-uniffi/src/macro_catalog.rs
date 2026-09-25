//! Canonical MacroDefinition catalog boundary for host package discovery.

use std::{
    collections::BTreeSet,
    panic::{AssertUnwindSafe, catch_unwind},
};

use inku_ddl::{
    LegacyImportOutcome, MacroDefinition, NATURE_LEAVES_V1_JSON, ResolvedInstructionLanguage,
};
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
    #[serde(default)]
    bundled_packages: Vec<String>,
    #[serde(default = "default_language")]
    language: ResolvedInstructionLanguage,
}

fn default_language() -> ResolvedInstructionLanguage {
    ResolvedInstructionLanguage::En
}

#[derive(Deserialize)]
struct BundledPackage {
    package_id: String,
    entries: Vec<BundledEntry>,
}

#[derive(Deserialize)]
struct BundledEntry {
    definition: serde_json::Value,
    summaries: BundledSummaries,
}

#[derive(Deserialize)]
struct BundledSummaries {
    ja: String,
    en: String,
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
    #[serde(skip_serializing_if = "Vec::is_empty")]
    aliases: Vec<String>,
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
    let mut input: CatalogInput = serde_json::from_slice(input_bytes).map_err(|_| ())?;
    if input.maximum_entries == 0 {
        return Err(());
    }
    let mut entries = Vec::new();
    let mut locks = Vec::new();
    let mut diagnostics = Vec::new();
    let mut names = BTreeSet::new();

    // Explicit installation definitions precede bundled editions. Both travel
    // through the same parser, validation, identity and resource boundary.
    for package_id in input.bundled_packages {
        let package: BundledPackage = match package_id.as_str() {
            "Nature.leaves" => serde_json::from_str(NATURE_LEAVES_V1_JSON).map_err(|_| ())?,
            _ => {
                diagnostics.push(omitted(
                    package_id,
                    None,
                    "unknown_bundled_package",
                    vec![],
                    vec![],
                ));
                continue;
            }
        };
        for entry in package.entries {
            input.canonical.push(CanonicalCandidate {
                source_id: format!("bundled:{}", package.package_id),
                definition_json: entry.definition.to_string(),
                summary: match input.language {
                    ResolvedInstructionLanguage::Ja => entry.summaries.ja,
                    ResolvedInstructionLanguage::En => entry.summaries.en,
                },
            });
        }
    }

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
        let aliases = definition.alias_qualified_names();
        // A canonical name and every alias share one namespace of visible
        // names: the first definition to claim any of them keeps it.
        if std::iter::once(&qualified_name)
            .chain(&aliases)
            .any(|name| names.contains(name))
            || !names.insert(qualified_name.clone())
        {
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
        names.extend(aliases.iter().cloned());
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
            aliases,
            version,
            digest,
        });
    }

    for candidate in input.legacy {
        // A successfully loaded edition from the same package needs no legacy
        // warning. Unmigrated entries still receive their explicit omission.
        if entries.iter().any(|entry| {
            entry.qualified_name == candidate.qualified_name
                && entry.source_id == candidate.source_id
        }) {
            continue;
        }
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
    fn an_alias_may_not_claim_a_name_another_definition_already_holds() {
        let definition = |heading: &str, aliases: &[&str]| {
            serde_json::json!({
                "schema": "inku.macro-definition.v1", "namespace": "Nature", "heading": heading,
                "aliases": aliases, "version": "1.0.0", "parameters": {}, "components": {}, "body": []
            })
            .to_string()
        };
        let output = resolve(
            &serde_json::to_vec(&json!({
                "maximum_entries": 64,
                "canonical": [
                    {"source_id": "a", "definition_json": definition("YoungLeaves", &["若葉"]), "summary": "a"},
                    {"source_id": "b", "definition_json": definition("若葉", &[]), "summary": "b"},
                    {"source_id": "c", "definition_json": definition("NewLeaves", &["若葉"]), "summary": "c"},
                    {"source_id": "d", "definition_json": definition("Buds", &["芽"]), "summary": "d"}
                ]
            }))
            .unwrap(),
        )
        .unwrap();
        let kept: Vec<_> = output
            .entries
            .iter()
            .map(|entry| entry.source_id.as_str())
            .collect();
        assert_eq!(kept, ["a", "d"]);
        assert_eq!(output.entries[0].aliases, ["Nature.若葉"]);
        assert!(
            output
                .diagnostics
                .iter()
                .all(|item| item.reason == "duplicate_qualified_name")
        );
        assert_eq!(output.diagnostics.len(), 2);
    }

    #[test]
    fn bundled_content_has_language_independent_locks_and_respects_explicit_precedence() {
        let ja = resolve(
            &serde_json::to_vec(&json!({
                "maximum_entries": 64, "bundled_packages": ["Nature.leaves"], "language": "ja"
            }))
            .unwrap(),
        )
        .unwrap();
        let en = resolve(
            &serde_json::to_vec(&json!({
                "maximum_entries": 64, "bundled_packages": ["Nature.leaves"], "language": "en"
            }))
            .unwrap(),
        )
        .unwrap();
        assert_eq!(ja.entries.len(), 7);
        assert!(ja.diagnostics.is_empty());
        assert!(en.diagnostics.is_empty());
        assert_eq!(
            serde_json::to_value(&ja.locks).unwrap(),
            serde_json::to_value(&en.locks).unwrap()
        );
        assert_ne!(ja.entries[0].summary, en.entries[0].summary);
        let mut explicit = ja.entries[0].definition.clone();
        explicit["version"] = json!("2.0.0");
        let overridden = resolve(&serde_json::to_vec(&json!({
            "maximum_entries": 1, "bundled_packages": ["Nature.leaves"],
            "canonical": [{"source_id": "installation", "definition_json": explicit.to_string(), "summary": "Custom edition"}]
        })).unwrap()).unwrap();
        assert_eq!(overridden.entries.len(), 1);
        assert_eq!(overridden.entries[0].source_id, "installation");
        assert_eq!(overridden.locks[0].version, "2.0.0");
        assert_eq!(overridden.diagnostics[0].reason, "duplicate_qualified_name");
        assert_eq!(
            overridden
                .diagnostics
                .iter()
                .filter(|d| d.reason == "catalog_entry_limit")
                .count(),
            // Seven bundled Nature entries, one admitted by the limit of one.
            6
        );
    }

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

//! Host entry for the one-time Saijiki v1 migration of a saved document and its definitions.
//!
//! A host passes one saved unit: a v1 visible document and the Macro definitions its locks
//! name, or definitions alone. It gets the unit back in the current edition, with each lock
//! moved to its definition's new digest, and saves it over the old one (SPEC §3.3).

use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_ddl::{
    MacroLock, NormalizedDdlDocument, SAIJIKI_ASSET_ID, SAIJIKI_V1_MIGRATION_SCHEMA_ID,
    SaijikiDefinitionMigration, SaijikiMigrationError, migrate_document_from_saijiki_v1,
    migrate_macro_definition_from_saijiki_v1,
};
use inku_pipeline::machine::{LockedDefinition, VisibleDocument};
use serde::Deserialize;
use serde_json::{Value, json};

const MAXIMUM_INPUT_BYTES: usize = 4 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MigrationInput {
    #[serde(default)]
    document: Option<V1Document>,
    #[serde(default)]
    definitions: Vec<Value>,
}

/// A saved visible document; it has no edition field because it was written with v1.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct V1Document {
    source: String,
    language: inku_ddl::ResolvedInstructionLanguage,
    macro_locks: Vec<LockedDefinition>,
}

fn error_value(error: &SaijikiMigrationError) -> Value {
    serde_json::to_value(error).unwrap_or_else(|_| json!({"code": error.code()}))
}

fn definition_value(migration: &SaijikiDefinitionMigration) -> Value {
    json!({
        "definition": migration.definition,
        "qualified_name": migration.identity.qualified_name(),
        "version": migration.identity.version(),
        "digest": format!("sha256:{}", migration.identity.full_digest_hex()),
        "changed": migration.changed,
    })
}

fn migrate_document(
    document: V1Document,
    definitions: &[Result<SaijikiDefinitionMigration, SaijikiMigrationError>],
) -> Value {
    // Each lock moves to the migrated definition of the same name and version.
    let mut locks = Vec::new();
    for lock in &document.macro_locks {
        let migrated = definitions.iter().flatten().find(|migration| {
            migration.identity.qualified_name() == lock.qualified_name
                && migration.identity.version() == lock.version
        });
        let Some(migrated) = migrated else {
            return json!({"error": {"code": "definition_not_supplied",
                "qualified_name": lock.qualified_name, "version": lock.version}});
        };
        locks.push(LockedDefinition {
            qualified_name: lock.qualified_name.clone(),
            version: lock.version.clone(),
            digest: format!("sha256:{}", migrated.identity.full_digest_hex()),
            aliases: lock.aliases.clone(),
        });
    }
    // The v1 source is read with the locks it was saved with; only names matter to it.
    let v1_locks = document
        .macro_locks
        .iter()
        .map(|lock| {
            MacroLock::new(&lock.qualified_name, &lock.version, &lock.digest)
                .and_then(|macro_lock| macro_lock.with_aliases(lock.aliases.iter().cloned()))
        })
        .collect::<Result<Vec<_>, _>>();
    let Ok(v1_locks) = v1_locks else {
        return json!({"error": {"code": "invalid_document"}});
    };
    let Ok(v1) = NormalizedDdlDocument::new(document.source, document.language, v1_locks) else {
        return json!({"error": {"code": "invalid_document"}});
    };
    match migrate_document_from_saijiki_v1(&v1) {
        Ok(migration) => json!({
            "document": VisibleDocument {
                source: migration.source,
                language: document.language,
                macro_locks: locks,
                saijiki: SAIJIKI_ASSET_ID.to_owned(),
            },
            "edits": migration.edits,
            "unassociated_sweeps": migration.unassociated_sweeps,
        }),
        Err(error) => json!({"error": error_value(&error)}),
    }
}

fn migrate(input_bytes: &[u8]) -> Option<Value> {
    if input_bytes.len() > MAXIMUM_INPUT_BYTES {
        return None;
    }
    let input: MigrationInput = serde_json::from_slice(input_bytes).ok()?;
    let definitions = input
        .definitions
        .iter()
        .map(migrate_macro_definition_from_saijiki_v1)
        .collect::<Vec<_>>();
    let document = input
        .document
        .map(|document| migrate_document(document, &definitions));
    Some(json!({
        "schema": SAIJIKI_V1_MIGRATION_SCHEMA_ID,
        "saijiki": SAIJIKI_ASSET_ID,
        "document": document,
        "definitions": definitions
            .iter()
            .map(|migration| match migration {
                Ok(migration) => definition_value(migration),
                Err(error) => json!({"error": error_value(error)}),
            })
            .collect::<Vec<_>>(),
    }))
}

/// Migrate one saved Saijiki v1 unit (a document and its definitions) to the current edition.
#[uniffi::export]
pub fn migrate_saijiki_v1(input_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| migrate(&input_bytes)))
        .ok()
        .flatten()
        .and_then(|output| serde_json::to_vec(&output).ok())
        .unwrap_or_else(|| {
            format!(
                r#"{{"schema":"{SAIJIKI_V1_MIGRATION_SCHEMA_ID}","error":"invalid_saijiki_migration_input"}}"#
            )
            .into_bytes()
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    const PACKAGE_1_0: &str =
        include_str!("../../inku-ddl/tests/fixtures/nature-leaves-1.0-package.json");

    #[test]
    fn a_saved_unit_comes_back_in_the_current_edition_with_its_locks_moved() {
        let package: Value = serde_json::from_str(PACKAGE_1_0).unwrap();
        let definition = package["entries"][0]["definition"].clone();
        let name = format!(
            "{}.{}",
            definition["namespace"].as_str().unwrap(),
            definition["heading"].as_str().unwrap()
        );
        let version = definition["version"].as_str().unwrap().to_owned();
        let v1_digest = format!("sha256:{}", "0".repeat(64));
        let output: Value = serde_json::from_slice(&migrate_saijiki_v1(
            serde_json::to_vec(&json!({
                "document": {
                    "source": format!("{name}。薄墨の円を中央に置く。"),
                    "language": "ja",
                    "macro_locks": [{"qualified_name": name, "version": version, "digest": v1_digest}]
                },
                "definitions": [definition]
            }))
            .unwrap(),
        ))
        .unwrap();
        assert_eq!(output["schema"], SAIJIKI_V1_MIGRATION_SCHEMA_ID);
        assert_eq!(output["saijiki"], SAIJIKI_ASSET_ID);
        let migrated = &output["definitions"][0];
        assert_eq!(migrated["changed"], true);
        assert_eq!(migrated["version"], version.as_str());
        let document: VisibleDocument =
            serde_json::from_value(output["document"]["document"].clone()).unwrap();
        assert_eq!(document.saijiki, SAIJIKI_ASSET_ID);
        assert_eq!(
            document.source,
            format!("{name}。薄い刷きの円を中心に置く。")
        );
        assert_eq!(
            document.macro_locks[0].digest,
            migrated["digest"].as_str().unwrap()
        );
        assert_ne!(document.macro_locks[0].digest, v1_digest);
        // The migrated unit is read by the current pipeline without a further migration.
        document.document().unwrap();
    }

    #[test]
    fn a_lock_without_its_definition_is_not_moved_silently() {
        let output: Value = serde_json::from_slice(&migrate_saijiki_v1(
            serde_json::to_vec(&json!({
                "document": {
                    "source": "Nature.若葉。",
                    "language": "ja",
                    "macro_locks": [{"qualified_name": "Nature.YoungLeaves", "version": "1.0.0",
                        "digest": format!("sha256:{}", "0".repeat(64))}]
                }
            }))
            .unwrap(),
        ))
        .unwrap();
        assert_eq!(
            output["document"]["error"]["code"],
            "definition_not_supplied"
        );
        assert_eq!(
            migrate_saijiki_v1(b"{}".to_vec()),
            serde_json::to_vec(&json!({
                "schema": SAIJIKI_V1_MIGRATION_SCHEMA_ID,
                "saijiki": SAIJIKI_ASSET_ID,
                "document": null,
                "definitions": []
            }))
            .unwrap()
        );
        assert!(
            String::from_utf8(migrate_saijiki_v1(b"not json".to_vec()))
                .unwrap()
                .contains("invalid_saijiki_migration_input")
        );
    }
}

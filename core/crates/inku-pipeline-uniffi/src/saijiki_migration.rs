//! Host entries for the one-time Saijiki migrations of a saved document and its definitions.
//!
//! A host passes one saved unit: a retired-edition visible document (v1, or v2 since the
//! touch reorganisation of 2026-10-31) and the Macro definitions its locks name, or
//! definitions alone. It gets the unit back in the current edition, with each lock moved
//! to its definition's new digest, and saves it over the old one (SPEC §3.3).
//!
//! A lock moves only to the definition it was saved with: the supplied definition whose
//! saved form has the lock's digest (`old_digest`), as the plugin-name migration checks. A
//! definition of the same name and version with another digest is another definition, and
//! the document is refused rather than rebound to it.

use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_ddl::{
    InvalidDocumentStage, MacroDefinition, MacroLock, NormalizedDdlDocument, SAIJIKI_ASSET_ID,
    SAIJIKI_V1_MIGRATION_SCHEMA_ID, SAIJIKI_V2_ASSET_ID, SAIJIKI_V2_MIGRATION_SCHEMA_ID,
    SaijikiDefinitionMigration, SaijikiDocumentMigration, SaijikiMigrationError,
    migrate_document_from_saijiki_v1, migrate_document_from_saijiki_v2,
    migrate_macro_definition_from_saijiki_v1, migrate_macro_definition_from_saijiki_v2,
};
use inku_pipeline::machine::{LockedDefinition, VisibleDocument};
use serde::Deserialize;
use serde_json::{Value, json};

const MAXIMUM_INPUT_BYTES: usize = 4 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MigrationInput {
    #[serde(default)]
    document: Option<SavedDocument>,
    #[serde(default)]
    definitions: Vec<Value>,
}

/// A saved visible document of a retired edition. A v1 document has no edition field; a v2
/// document names `inku.saijiki.v2`.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SavedDocument {
    source: String,
    language: inku_ddl::ResolvedInstructionLanguage,
    macro_locks: Vec<LockedDefinition>,
    #[serde(default)]
    saijiki: Option<String>,
}

/// The retired edition a host entry migrates from.
#[derive(Clone, Copy)]
enum Retired {
    V1,
    V2,
}

impl Retired {
    const fn schema(self) -> &'static str {
        match self {
            Self::V1 => SAIJIKI_V1_MIGRATION_SCHEMA_ID,
            Self::V2 => SAIJIKI_V2_MIGRATION_SCHEMA_ID,
        }
    }

    const fn asset_id(self) -> &'static str {
        match self {
            Self::V1 => inku_ddl::SAIJIKI_V1_ASSET_ID,
            Self::V2 => SAIJIKI_V2_ASSET_ID,
        }
    }

    /// Whether a saved document's edition field names this edition.
    fn writes(self, saijiki: Option<&str>) -> bool {
        match self {
            Self::V1 => saijiki.is_none_or(|edition| edition == inku_ddl::SAIJIKI_V1_ASSET_ID),
            Self::V2 => saijiki == Some(SAIJIKI_V2_ASSET_ID),
        }
    }

    fn migrate_document(
        self,
        document: &NormalizedDdlDocument,
    ) -> Result<SaijikiDocumentMigration, SaijikiMigrationError> {
        match self {
            Self::V1 => migrate_document_from_saijiki_v1(document),
            Self::V2 => migrate_document_from_saijiki_v2(document),
        }
    }

    fn migrate_definition(
        self,
        definition: &Value,
    ) -> Result<SaijikiDefinitionMigration, SaijikiMigrationError> {
        match self {
            Self::V1 => migrate_macro_definition_from_saijiki_v1(definition),
            Self::V2 => migrate_macro_definition_from_saijiki_v2(definition),
        }
    }
}

fn error_value(error: &SaijikiMigrationError) -> Value {
    serde_json::to_value(error).unwrap_or_else(|_| json!({"code": error.code()}))
}

/// One definition the host supplied, and its migration.
struct Supplied {
    /// The digest the definition's saved form is locked by (`sha256:<hex>`): its identity
    /// with its words spelled through the retired edition, before any rewrite. `None` when
    /// the saved form does not read as a definition of that edition.
    old_digest: Option<String>,
    migration: Result<SaijikiDefinitionMigration, SaijikiMigrationError>,
}

impl Supplied {
    fn new(retired: Retired, definition: &Value) -> Self {
        let old_digest = MacroDefinition::from_json(&definition.to_string())
            .ok()
            .and_then(|saved| saved.identity_in_retired_saijiki(retired.asset_id()))
            .map(|identity| format!("sha256:{}", identity.full_digest_hex()));
        Self {
            old_digest,
            migration: retired.migrate_definition(definition),
        }
    }
}

fn definition_value(old_digest: Option<&str>, migration: &SaijikiDefinitionMigration) -> Value {
    json!({
        "definition": migration.definition,
        "qualified_name": migration.identity.qualified_name(),
        "version": migration.identity.version(),
        "old_digest": old_digest,
        "digest": format!("sha256:{}", migration.identity.full_digest_hex()),
        "changed": migration.changed,
        "unadjusted_thinness": migration.unadjusted_thinness,
    })
}

fn migrate_document(retired: Retired, document: SavedDocument, definitions: &[Supplied]) -> Value {
    if !retired.writes(document.saijiki.as_deref()) {
        return json!({"error": {"code": "other_edition", "saijiki": document.saijiki}});
    }
    let v1 = document
        .macro_locks
        .iter()
        .enumerate()
        .map(|(index, lock)| {
            MacroLock::new(&lock.qualified_name, &lock.version, &lock.digest)
                .and_then(|macro_lock| macro_lock.with_aliases(lock.aliases.iter().cloned()))
                .map_err(|diagnostic| InvalidDocumentStage::V1Locks {
                    lock: index,
                    cause: diagnostic.code(),
                })
        })
        .collect::<Result<Vec<_>, _>>()
        .and_then(|v1_locks| {
            NormalizedDdlDocument::new(document.source, document.language, v1_locks).map_err(
                |diagnostic| InvalidDocumentStage::V1Document {
                    cause: diagnostic.code(),
                },
            )
        });
    let v1 = match v1 {
        Ok(v1) => v1,
        Err(stage) => {
            return json!({"error": error_value(&SaijikiMigrationError::InvalidDocument(stage))});
        }
    };
    // Each lock moves to the migrated definition it was saved with: a supplied definition of
    // the same name and version whose saved form has the lock's digest.
    let mut locks = Vec::new();
    for lock in &document.macro_locks {
        let named = definitions
            .iter()
            .filter_map(|supplied| {
                let migration = supplied.migration.as_ref().ok()?;
                (migration.identity.qualified_name() == lock.qualified_name
                    && migration.identity.version() == lock.version)
                    .then_some((supplied.old_digest.as_deref(), migration))
            })
            .collect::<Vec<_>>();
        if named.is_empty() {
            return json!({"error": {"code": "definition_not_supplied",
                "qualified_name": lock.qualified_name, "version": lock.version}});
        }
        let Some((_, migrated)) = named
            .iter()
            .find(|(old_digest, _)| *old_digest == Some(lock.digest.as_str()))
        else {
            return json!({"error": {"code": "lock_digest_mismatch",
                "qualified_name": lock.qualified_name, "version": lock.version,
                "lock_digest": lock.digest,
                "old_digests": named.iter().map(|(old_digest, _)| *old_digest).collect::<Vec<_>>()}});
        };
        locks.push(LockedDefinition {
            qualified_name: lock.qualified_name.clone(),
            version: lock.version.clone(),
            digest: format!("sha256:{}", migrated.identity.full_digest_hex()),
            aliases: lock.aliases.clone(),
        });
    }
    match retired.migrate_document(&v1) {
        Ok(migration) => json!({
            "document": VisibleDocument {
                source: migration.source,
                language: document.language,
                macro_locks: locks,
                saijiki: SAIJIKI_ASSET_ID.to_owned(),
            },
            "edits": migration.edits,
            "unassociated_sweeps": migration.unassociated_sweeps,
            "unassociated_tools": migration.unassociated_tools,
        }),
        Err(error) => json!({"error": error_value(&error)}),
    }
}

fn migrate(retired: Retired, input_bytes: &[u8]) -> Option<Value> {
    if input_bytes.len() > MAXIMUM_INPUT_BYTES {
        return None;
    }
    let input: MigrationInput = serde_json::from_slice(input_bytes).ok()?;
    let definitions = input
        .definitions
        .iter()
        .map(|definition| Supplied::new(retired, definition))
        .collect::<Vec<_>>();
    let document = input
        .document
        .map(|document| migrate_document(retired, document, &definitions));
    Some(json!({
        "schema": retired.schema(),
        "saijiki": SAIJIKI_ASSET_ID,
        "document": document,
        "definitions": definitions
            .iter()
            .map(|supplied| match &supplied.migration {
                Ok(migration) => definition_value(supplied.old_digest.as_deref(), migration),
                Err(error) => json!({"error": error_value(error)}),
            })
            .collect::<Vec<_>>(),
    }))
}

fn migrate_bytes(retired: Retired, input_bytes: &[u8]) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| migrate(retired, input_bytes)))
        .ok()
        .flatten()
        .and_then(|output| serde_json::to_vec(&output).ok())
        .unwrap_or_else(|| {
            format!(
                r#"{{"schema":"{}","error":"invalid_saijiki_migration_input"}}"#,
                retired.schema()
            )
            .into_bytes()
        })
}

/// Migrate one saved Saijiki v1 unit (a document and its definitions) to the current edition.
#[uniffi::export]
pub fn migrate_saijiki_v1(input_bytes: Vec<u8>) -> Vec<u8> {
    migrate_bytes(Retired::V1, &input_bytes)
}

/// Migrate one saved Saijiki v2 unit (a document and its definitions) to the current edition
/// (the touch reorganisation of 2026-10-31, PLAN-PRODUCT §3.3). The output has the v1 entry's
/// shape, with the spans of tools whose thinness could not follow (`unassociated_tools`) and,
/// per definition, the emits whose thinness could not follow (`unadjusted_thinness`). Both
/// entries give each definition the digest its saved form is locked by (`old_digest`), and
/// refuse a document whose lock names a supplied definition by another digest
/// (`lock_digest_mismatch`).
#[uniffi::export]
pub fn migrate_saijiki_v2(input_bytes: Vec<u8>) -> Vec<u8> {
    migrate_bytes(Retired::V2, &input_bytes)
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
        // The digest the v1 core (7ba01022) locked this 若葉 1.0.1 by.
        let v1_digest =
            "sha256:82ffc5c348a82ba927b315acaaa5ce4bc4c3998e2497deecd91535fb3005c8f4".to_owned();
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

    /// Change the first exact decimal, so the definition keeps its name and version but is
    /// another definition.
    fn edit_first_decimal(value: &mut Value) -> bool {
        match value {
            Value::Object(object) if object.get("expr") == Some(&json!("exact_decimal")) => {
                object.insert("value".to_owned(), json!("0.123"));
                true
            }
            Value::Object(object) => object.values_mut().any(edit_first_decimal),
            Value::Array(items) => items.iter_mut().any(edit_first_decimal),
            _ => false,
        }
    }

    #[test]
    fn a_lock_moves_only_from_the_digest_its_definition_was_saved_with() {
        // The digest the v2 core (main 783fd7a81, render engine 94) locked 下草 1.0.0 by.
        const SAVED: &str =
            "sha256:88046b24987a2600eeb8b985f36bc15222202a5758a0f4a7638e514dd6af2aea";
        let package: Value = serde_json::from_str(PACKAGE_1_0).unwrap();
        let undergrowth = package["entries"]
            .as_array()
            .unwrap()
            .iter()
            .map(|entry| entry["definition"].clone())
            .find(|definition| definition["heading"] == "下草")
            .unwrap();
        let migrate = |digest: &str, definitions: &[&Value]| -> Value {
            serde_json::from_slice(&migrate_saijiki_v2(
                serde_json::to_vec(&json!({
                    "document": {
                        "source": "黒い太筆の線を引く。",
                        "language": "ja",
                        "saijiki": SAIJIKI_V2_ASSET_ID,
                        "macro_locks": [{"qualified_name": "Nature.下草", "version": "1.0.0",
                            "digest": digest}]
                    },
                    "definitions": definitions
                }))
                .unwrap(),
            ))
            .unwrap()
        };

        let moved = migrate(SAVED, &[&undergrowth]);
        assert_eq!(moved["definitions"][0]["old_digest"], SAVED);
        let document: VisibleDocument =
            serde_json::from_value(moved["document"]["document"].clone()).unwrap();
        assert_eq!(document.source, "黒い太いガッシュの線を引く。");
        assert_eq!(
            document.macro_locks[0].digest,
            moved["definitions"][0]["digest"].as_str().unwrap()
        );
        assert_ne!(document.macro_locks[0].digest, SAVED);

        // A lock with another digest names another definition: the document is refused,
        // not rebound to the supplied one (the Server's report of 2026-10-31).
        let zeros = format!("sha256:{}", "0".repeat(64));
        assert_eq!(
            migrate(&zeros, &[&undergrowth])["document"]["error"],
            json!({"code": "lock_digest_mismatch", "qualified_name": "Nature.下草",
                "version": "1.0.0", "lock_digest": zeros, "old_digests": [SAVED]})
        );

        // Of two supplied definitions with the lock's name and version, the lock moves to
        // the one it was saved with, whichever comes first.
        let mut edited = undergrowth.clone();
        assert!(edit_first_decimal(&mut edited));
        for definitions in [[&edited, &undergrowth], [&undergrowth, &edited]] {
            let output = migrate(SAVED, &definitions);
            let saved = output["definitions"]
                .as_array()
                .unwrap()
                .iter()
                .find(|definition| definition["old_digest"] == SAVED)
                .unwrap();
            assert_eq!(
                output["document"]["document"]["macro_locks"][0]["digest"],
                saved["digest"]
            );
            assert_eq!(
                output["definitions"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .filter(|definition| definition["old_digest"] == SAVED)
                    .count(),
                1
            );
        }
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

    #[test]
    fn an_invalid_document_says_where_it_stopped_and_why() {
        let package: Value = serde_json::from_str(PACKAGE_1_0).unwrap();
        let definition = package["entries"][0]["definition"].clone();
        let lock = json!({
            "qualified_name": format!(
                "{}.{}",
                definition["namespace"].as_str().unwrap(),
                definition["heading"].as_str().unwrap()
            ),
            "version": definition["version"],
            "digest": format!("sha256:{}", "0".repeat(64)),
        });
        let mut unreadable = lock.clone();
        unreadable["digest"] = json!("sha256:0");
        let refusal = |macro_locks: Value| {
            let output: Value = serde_json::from_slice(&migrate_saijiki_v1(
                serde_json::to_vec(&json!({
                    "document": {"source": "円を置く。", "language": "ja", "macro_locks": macro_locks},
                    "definitions": [definition]
                }))
                .unwrap(),
            ))
            .unwrap();
            output["document"]["error"].clone()
        };
        assert_eq!(
            refusal(json!([lock, unreadable])),
            json!({"code": "invalid_document", "stage": "v1_locks", "lock": 1,
                "cause": "invalid_digest"})
        );
        assert_eq!(
            refusal(json!([lock, lock])),
            json!({"code": "invalid_document", "stage": "v1_document",
                "cause": "duplicate_macro_lock"})
        );
    }
}

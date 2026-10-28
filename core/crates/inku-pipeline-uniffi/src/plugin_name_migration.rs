//! Migrate locked plugin definitions and source spellings as one saved unit.
use inku_ddl::{
    MacroDefinition, MacroLock, NormalizedDdlDocument, ResolvedInstructionLanguage,
    resolve_macro_invocations,
};
use serde_json::{Value, json};

#[uniffi::export]
pub fn migrate_plugin_names(input_bytes: Vec<u8>) -> Vec<u8> {
    let result = std::panic::catch_unwind(|| run(&input_bytes))
        .ok()
        .flatten()
        .unwrap_or_else(|| json!({"error":"invalid_plugin_migration_input"}));
    serde_json::to_vec(&result)
        .unwrap_or_else(|_| br#"{"error":"invalid_plugin_migration_input"}"#.to_vec())
}

fn run(input: &[u8]) -> Option<Value> {
    if input.len() > 4 * 1024 * 1024 {
        return None;
    }
    let input: Value = serde_json::from_slice(input).ok()?;
    let has_document = !input["document"].is_null();
    let definitions = input["definitions"].as_array()?;
    let mut records = Vec::new();
    let mut old_definitions = Vec::new();
    let mut migrated = Vec::new();
    let mut problems = Vec::new();
    for value in definitions {
        let old = MacroDefinition::from_json(&value.to_string()).ok()?;
        let old_id = old.identity().ok()?;
        let changed = !has_document && old.plugin_v2.is_none();
        let mut wire = serde_json::to_value(&old).ok()?;
        if changed {
            let (ja, en) = inku_ddl::plugin_names::v1_plugin_names(&old.heading, &old.aliases);
            let object = wire.as_object_mut()?;
            object.remove("heading");
            object.remove("aliases");
            object.insert("schema".into(), json!("inku.macro-definition.v2"));
            object.insert("id".into(), json!(old.heading));
            object.insert("names".into(), json!({"ja":ja,"en":en}));
            object.insert("kind".into(), json!("scene"));
        }
        let new = MacroDefinition::from_json(&wire.to_string()).ok()?;
        let new_id = match new.identity() {
            Ok(id) => id,
            Err(validation) => {
                for finding in validation.diagnostics() {
                    problems.push(json!({"qualified_name":old_id.qualified_name(),"code":finding.code(),"path":finding.path()}));
                }
                return Some(json!({"error":"definition_migration_refused","problems":problems}));
            }
        };
        records.push(json!({"definition":new,"qualified_name":new_id.qualified_name(),"version":new_id.version(),"old_digest":format!("sha256:{}",old_id.full_digest_hex()),"new_digest":format!("sha256:{}",new_id.full_digest_hex()),"changed":changed}));
        old_definitions.push(old);
        migrated.push(new);
    }
    let mut edits = Vec::new();
    let document = if input["document"].is_null() {
        Value::Null
    } else {
        let doc = &input["document"];
        let source = doc["source"].as_str()?;
        let language: ResolvedInstructionLanguage =
            serde_json::from_value(doc["language"].clone()).ok()?;
        let raw_locks = doc["macro_locks"].as_array()?;
        let mut locks = Vec::new();
        let mut new_locks = Vec::new();
        for raw in raw_locks {
            let qualified = raw["qualified_name"].as_str()?;
            let version = raw["version"].as_str()?;
            let digest = raw["digest"].as_str()?;
            let matching = records.iter().position(|r| {
                r["qualified_name"] == qualified
                    && r["version"] == version
                    && r["old_digest"] == digest
            });
            let mut aliases: Vec<String> = raw["aliases"]
                .as_array()
                .map(|a| {
                    a.iter()
                        .filter_map(Value::as_str)
                        .map(str::to_owned)
                        .collect()
                })
                .unwrap_or_default();
            if let Some(i) = matching {
                for alias in old_definitions[i].alias_qualified_names() {
                    if !aliases.contains(&alias) {
                        aliases.push(alias);
                    }
                }
            }
            locks.push(
                MacroLock::new(qualified, version, digest)
                    .ok()?
                    .with_aliases(aliases)
                    .ok()?,
            );
            if matching.is_none() {
                problems.push(json!({"code":"definition_not_supplied","qualified_name":qualified}));
            }
            new_locks.push(raw.clone());
        }
        let normalized = NormalizedDdlDocument::new(source, language, locks)
            .ok()?
            .with_definition_names(&old_definitions);
        let resolved = resolve_macro_invocations(&normalized, &old_definitions).ok()?;
        for item in &resolved.resolved {
            let Some(i) = records.iter().position(|r| {
                r["qualified_name"] == item.lock.qualified_name
                    && r["version"] == item.lock.version
                    && r["old_digest"] == item.lock.digest
            }) else {
                continue;
            };
            let (ja, en) = if let Some(v2) = migrated[i].plugin_v2.as_ref() {
                (v2.names.ja.clone(), v2.names.en.clone())
            } else {
                inku_ddl::plugin_names::v1_plugin_names(&migrated[i].heading, &migrated[i].aliases)
            };
            let name = if language == ResolvedInstructionLanguage::Ja {
                ja.first()?
            } else {
                en.first()?
            };
            let replacement = if language == ResolvedInstructionLanguage::Ja {
                format!("｛{name}｝")
            } else {
                format!("{{{name}}}")
            };
            let original = source.get(item.span.start_byte..item.span.end_byte)?;
            if original.starts_with('{') || original.starts_with('｛') {
                continue;
            }
            edits.push(json!({"span":{"start_byte":item.span.start_byte,"end_byte":item.span.end_byte},"original":original,"replacement":replacement}));
        }
        for item in &resolved.diagnostics {
            if item.kind == inku_ddl::MacroInvocationResolutionDiagnosticKind::MissingLock {
                problems.push(json!({"code":"missing_lock","name":item.surface,"span":item.span}));
            }
        }
        let mut new_source = source.to_owned();
        for edit in edits.iter().rev() {
            let start = edit["span"]["start_byte"].as_u64()? as usize;
            let end = edit["span"]["end_byte"].as_u64()? as usize;
            new_source.replace_range(start..end, edit["replacement"].as_str()?);
        }
        json!({"source":new_source,"language":doc["language"],"macro_locks":new_locks})
    };
    Some(
        json!({"schema":"inku.plugin-name-migration.v1","document":document,"definitions":records,"edits":edits,"problems":problems}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use inku_ddl::{
        MacroExpansionLimits, ScoreErrorPolicy, ScoreLoweringContext, compile_ddl_to_score,
    };
    use inku_score::Color;

    #[test]
    fn definitions_only_migrate_and_missing_lock_is_reported() {
        let package: Value = serde_json::from_str(inku_ddl::NATURE_LEAVES_V1_JSON).unwrap();
        let old = package["entries"][0]["definition"].clone();
        let output = run(&serde_json::to_vec(&json!({"definitions":[old]})).unwrap()).unwrap();
        assert_eq!(output["definitions"][0]["changed"], true);
        assert_eq!(
            output["definitions"][0]["definition"]["schema"],
            "inku.macro-definition.v2"
        );
        assert_ne!(
            output["definitions"][0]["old_digest"],
            output["definitions"][0]["new_digest"]
        );
        let second = run(&serde_json::to_vec(
            &json!({"definitions":[output["definitions"][0]["definition"]]}),
        )
        .unwrap())
        .unwrap();
        assert_eq!(second["definitions"][0]["changed"], false);
        let missing=run(&serde_json::to_vec(&json!({"document":{"source":"Nature.YoungLeaves。","language":"ja","macro_locks":[]},"definitions":[]})).unwrap()).unwrap();
        assert_eq!(missing["document"]["source"], "Nature.YoungLeaves。");
        assert!(
            missing["problems"]
                .as_array()
                .unwrap()
                .iter()
                .any(|p| p["code"] == "missing_lock")
        );
    }

    #[test]
    fn a_locked_scene_migrates_without_changing_score_and_is_idempotent() {
        let package: Value = serde_json::from_str(inku_ddl::NATURE_LEAVES_V1_JSON).unwrap();
        let old =
            MacroDefinition::from_json(&package["entries"][0]["definition"].to_string()).unwrap();
        let old_id = old.identity().unwrap();
        let lock = json!({"qualified_name":old_id.qualified_name(),"version":old_id.version(),"digest":format!("sha256:{}",old_id.full_digest_hex())});
        let input = json!({"document":{"source":"Nature.若葉。","language":"ja","macro_locks":[lock]},"definitions":[old]});
        let output = run(&serde_json::to_vec(&input).unwrap()).unwrap();
        assert_eq!(output["document"]["source"], "｛若葉｝。");
        assert_eq!(
            output["document"]["macro_locks"],
            input["document"]["macro_locks"]
        );
        assert_eq!(output["definitions"][0]["changed"], false);
        let new = MacroDefinition::from_json(&output["definitions"][0]["definition"].to_string())
            .unwrap();
        let second = run(&serde_json::to_vec(
            &json!({"document":output["document"],"definitions":[new]}),
        )
        .unwrap())
        .unwrap();
        assert_eq!(second["definitions"][0]["changed"], false);
        assert_eq!(second["edits"].as_array().unwrap().len(), 0);
        let score = |source: &str, definition: &MacroDefinition| {
            let id = definition.identity().unwrap();
            let lock = MacroLock::new(
                id.qualified_name(),
                id.version(),
                format!("sha256:{}", id.full_digest_hex()),
            )
            .unwrap()
            .with_aliases(definition.alias_qualified_names())
            .unwrap();
            let limits = MacroExpansionLimits {
                max_invocations: 64,
                max_depth: 16,
                max_evaluation_steps: 8192,
                max_nodes_per_invocation: 128,
                max_total_nodes: 128,
            };
            compile_ddl_to_score(
                NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, vec![lock])
                    .unwrap(),
                std::slice::from_ref(definition),
                Some(37),
                limits,
                ScoreLoweringContext::resolve("square", Color::White).unwrap(),
                ScoreErrorPolicy::OmitAndContinue,
            )
            .score()
            .cloned()
        };
        let old = MacroDefinition::from_json(&input["definitions"][0].to_string()).unwrap();
        let new = MacroDefinition::from_json(&output["definitions"][0]["definition"].to_string())
            .unwrap();
        let before = score("Nature.若葉。", &old);
        let after = score("｛若葉｝。", &new);
        assert!(before.is_some());
        assert_eq!(before, after);
    }
}

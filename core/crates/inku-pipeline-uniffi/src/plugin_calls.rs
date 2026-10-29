//! Resolve the plugin references in an editor buffer without starting a run.

use inku_ddl::{
    MacroDefinition, MacroInvocationResolutionDiagnosticKind as Kind, SAIJIKI_ASSET_ID,
    resolve_macro_invocations,
};
use inku_pipeline::{
    core_boundary::{CompilerOptions, compile_committed},
    machine::{LockedDefinition, VisibleDocument},
};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    source: String,
    language: inku_ddl::ResolvedInstructionLanguage,
    definitions: Vec<MacroDefinition>,
    #[serde(default)]
    summaries: Vec<String>,
    #[serde(default)]
    pictures: std::collections::BTreeMap<String, String>,
    locks: Vec<LockedDefinition>,
    compiler: Option<CompilerOptions>,
    #[serde(default)]
    enabled: Vec<String>,
    #[serde(default)]
    disabled: Vec<String>,
    #[serde(default)]
    plugin_names: Vec<Value>,
}

fn run(bytes: &[u8]) -> Result<Value, ()> {
    if bytes.len() > 16 * 1024 * 1024 {
        return Err(());
    }
    let input: Input = serde_json::from_slice(bytes).map_err(|_| ())?;
    let mut locks = input.locks;
    for lock in &mut locks {
        if let Some(definition) = input.definitions.iter().find(|definition| {
            definition.identity().is_ok_and(|identity| {
                identity.qualified_name() == lock.qualified_name
                    && identity.version() == lock.version
                    && format!("sha256:{}", identity.full_digest_hex()) == lock.digest
            })
        }) {
            for alias in definition.alias_qualified_names() {
                if !lock.aliases.contains(&alias) {
                    lock.aliases.push(alias);
                }
            }
        }
    }
    let visible = VisibleDocument {
        source: input.source.clone(),
        language: input.language,
        macro_locks: locks,
        saijiki: SAIJIKI_ASSET_ID.into(),
    };
    let entries: Vec<Value> = input.definitions.iter().enumerate().filter_map(|(index, definition)| {
        let identity = definition.identity().ok()?;
        if !visible.macro_locks.iter().any(|lock| lock.qualified_name == identity.qualified_name()) { return None; }
        let (ja, en) = inku_pipeline::plugin_offer::visible_names(definition);
        let note = input.summaries.get(index).cloned().unwrap_or_default();
        let ja_written = inku_pipeline::plugin_offer::primary_name(definition, inku_ddl::ResolvedInstructionLanguage::Ja);
        let en_written = inku_pipeline::plugin_offer::primary_name(definition, inku_ddl::ResolvedInstructionLanguage::En);
        Some(json!({"qualified_name": identity.qualified_name(), "surface_ja": ja, "surface_en": en,
                    "word_kind": definition.plugin_v2.as_ref().map_or("scene", |v| v.kind.as_str()),
                    "written_ja": ja_written, "written_en": en_written,
                    "example_ja": format!("{}。", ja_written), "example_en": format!("{}.", en_written),
                "note_ja": note, "note_en": note,
                "preview_url": input.pictures.get(identity.qualified_name()).cloned().unwrap_or_default()}))
    }).collect();
    let document = visible
        .document()
        .map_err(|_| ())?
        .with_definition_names(&input.definitions);
    let resolution = resolve_macro_invocations(&document, &input.definitions).map_err(|_| ())?;
    // Find visible spellings through the same resolver even when the saved lock
    // identifies another version. Then ask it to classify that original lock.
    let mut shadow = visible.clone();
    for lock in &mut shadow.macro_locks {
        if let Some(identity) = input
            .definitions
            .iter()
            .filter_map(|definition| definition.identity().ok())
            .find(|identity| identity.qualified_name() == lock.qualified_name)
        {
            lock.version = identity.version().to_owned();
            lock.digest = format!("sha256:{}", identity.full_digest_hex());
        }
    }
    let shadow_document = shadow
        .document()
        .map_err(|_| ())?
        .with_definition_names(&input.definitions);
    let shadow_resolution =
        resolve_macro_invocations(&shadow_document, &input.definitions).map_err(|_| ())?;
    let mut diagnostics: Vec<Value> = resolution.diagnostics.iter().map(|item| {
        let mut kind = item.kind;
        if kind == Kind::MissingLock && item.surface.starts_with(['{', '｛']) {
            if let Some(found) = shadow_resolution.resolved.iter().find(|found| found.span == item.span) {
                if let Some(lock) = visible.macro_locks.iter().find(|lock| lock.qualified_name == found.lock.qualified_name) {
                    let probe = VisibleDocument { source: lock.qualified_name.clone(), language: input.language, macro_locks: vec![lock.clone()], saijiki: SAIJIKI_ASSET_ID.into() };
                    if let Ok(probe_doc) = probe.document() {
                        if let Ok(probe_result) = resolve_macro_invocations(&probe_doc, &input.definitions) {
                            if let Some(failure) = probe_result.diagnostics.first() {
                                if matches!(failure.kind, Kind::VersionMismatch | Kind::DigestMismatch) { kind = failure.kind; }
                            }
                        }
                    }
                }
            }
        }
        let reason = match kind {
            Kind::AmbiguousLockPrefix => "macro_resolution_ambiguous_lock_prefix",
            Kind::VersionMismatch => "macro_resolution_version_mismatch",
            Kind::DigestMismatch => "macro_resolution_digest_mismatch",
            Kind::MissingDefinition => "macro_resolution_missing_definition",
            _ => "macro_resolution_missing_lock",
        };
        json!({"reason": reason, "span": {"start_byte": item.span.start_byte, "end_byte": item.span.end_byte}})
    }).collect();
    if let Some(compiler) = input.compiler {
        if let Ok(delivery) = compile_committed(document, &input.definitions, &compiler) {
            diagnostics.extend(
                delivery
                    .upstream_diagnostics
                    .into_iter()
                    .filter(|d| d["reason"] == "macro_binding_count_out_of_range"),
            );
        }
    }
    let explained = super::explain_plugin_diagnostics(serde_json::to_vec(&json!({"source":input.source,"upstream_diagnostics":diagnostics,"enabled":input.enabled,"disabled":input.disabled,"plugin_names":input.plugin_names})).map_err(|_| ())?);
    let explained: Value = serde_json::from_slice(&explained).map_err(|_| ())?;
    let mut calls = Vec::new();
    for resolved in resolution.resolved {
        calls.push(json!({"start_byte":resolved.span.start_byte,"end_byte":resolved.span.end_byte,"status":"resolved","qualified_name":resolved.lock.qualified_name}));
    }
    for item in explained["plugins"].as_array().ok_or(())? {
        let start = item["start_byte"].as_u64().ok_or(())?;
        let end = item["end_byte"].as_u64().ok_or(())?;
        calls.retain(|call| {
            !(call["start_byte"].as_u64().unwrap_or(0) < end
                && call["end_byte"].as_u64().unwrap_or(0) > start)
        });
        calls.push(json!({"start_byte":item["start_byte"],"end_byte":item["end_byte"],"status":item["reason"],"suggestion":item.get("suggestion"),"candidates":item.get("candidates")}));
    }
    for call in &mut calls {
        let start = call["start_byte"].as_u64().ok_or(())? as usize;
        let end = call["end_byte"].as_u64().ok_or(())? as usize;
        let text = input.source.get(start..end).ok_or(())?;
        call["start_utf16"] = json!(input.source[..start].encode_utf16().count());
        call["end_utf16"] = json!(input.source[..end].encode_utf16().count());
        call["text"] = json!(text);
        call["spelling"] = json!(if text.starts_with(['{', '｛']) {
            "braced"
        } else {
            "legacy"
        });
    }
    calls.sort_by_key(|call| call["start_byte"].as_u64().unwrap_or(0));
    Ok(json!({"schema":"inku.plugin-calls.v1", "calls":calls, "entries":entries}))
}

#[uniffi::export]
pub fn plugin_calls(bytes: Vec<u8>) -> Vec<u8> {
    std::panic::catch_unwind(|| run(&bytes))
        .ok()
        .and_then(Result::ok)
        .and_then(|value| serde_json::to_vec(&value).ok())
        .unwrap_or_else(|| {
            br#"{"schema":"inku.plugin-calls.v1","error":"invalid_request"}"#.to_vec()
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn editor_resolves_names_and_excludes_json_and_incomplete_braces() {
        let package: Value = serde_json::from_str(inku_ddl::NATURE_LEAVES_V2_JSON).unwrap();
        let definition: MacroDefinition =
            serde_json::from_value(package["words"][0]["definition"].clone()).unwrap();
        let identity = definition.identity().unwrap();
        let lock = json!({"qualified_name":identity.qualified_name(),"version":identity.version(),"digest":format!("sha256:{}", identity.full_digest_hex())});
        let result = run(&serde_json::to_vec(&json!({
            "source":"😀｛若葉｝。Nature.YoungLeaves。｛若刃｝。{}。{\"x\":1}。｛未完",
            "language":"ja", "definitions":[definition], "summaries":["若葉を描く。"], "pictures":{"Nature.YoungLeaves":"/preview"}, "locks":[lock], "compiler":null,
            "enabled":["Nature.YoungLeaves"], "plugin_names":[{"name":"若葉","qualified_name":"Nature.YoungLeaves","enabled":true}]
        })).unwrap()).unwrap();
        let calls = result["calls"].as_array().unwrap();
        assert_eq!(calls.len(), 3, "{calls:?}");
        assert_eq!(calls[0]["status"], "resolved");
        assert_eq!(calls[0]["start_utf16"], 2);
        assert_eq!(calls[1]["status"], "resolved");
        assert_eq!(calls[2]["status"], "plugin_name_mismatch");
        assert_eq!(result["entries"][0]["written_ja"], "｛若葉｝");
        assert_eq!(result["entries"][0]["written_en"], "{young leaves}");
        assert_eq!(result["entries"][0]["note_ja"], "若葉を描く。");
        assert_eq!(result["entries"][0]["preview_url"], "/preview");
    }

    #[test]
    fn stale_lock_explains_the_braced_name_as_a_version_mismatch() {
        let package: Value = serde_json::from_str(inku_ddl::NATURE_LEAVES_V2_JSON).unwrap();
        let definition: MacroDefinition =
            serde_json::from_value(package["words"][0]["definition"].clone()).unwrap();
        let identity = definition.identity().unwrap();
        let result = run(&serde_json::to_vec(&json!({
            "source":"｛若葉｝。", "language":"ja", "definitions":[definition],
            "locks":[{"qualified_name":identity.qualified_name(),"version":identity.version(),"digest":format!("sha256:{}", "0".repeat(64))}],
            "compiler":null, "plugin_names":[{"name":"若葉","qualified_name":"Nature.YoungLeaves","enabled":true}]
        })).unwrap()).unwrap();
        assert_eq!(result["calls"][0]["status"], "plugin_version_mismatch");
    }

    #[test]
    fn editor_explains_disabled_unknown_and_ambiguous_names() {
        let result = run(&serde_json::to_vec(&json!({
            "source":"｛若葉｝。｛花｝。｛未登録の語｝。", "language":"ja", "definitions":[], "locks":[], "compiler":null,
            "plugin_names":[
                {"name":"若葉", "qualified_name":"Nature.YoungLeaves", "enabled":false},
                {"name":"花", "qualified_name":"Garden.Flower", "enabled":true},
                {"name":"花", "qualified_name":"Sky.Flower", "enabled":true}
            ]
        })).unwrap()).unwrap();
        let calls = result["calls"].as_array().unwrap();
        assert_eq!(
            calls
                .iter()
                .map(|call| call["status"].as_str().unwrap())
                .collect::<Vec<_>>(),
            [
                "plugin_disabled",
                "plugin_name_ambiguous",
                "plugin_not_installed"
            ]
        );
        assert_eq!(
            calls[1]["candidates"],
            json!(["Garden.Flower", "Sky.Flower"])
        );
    }
}

//! One-time migration of saved DDL documents and Macro definitions from the retired Saijiki
//! v1 to the current edition (SPEC §3.3).
//!
//! Only this module reads v1 words. Each word is rewritten by its meaning at its own position;
//! the rest of a document and every other definition field stay as they were. Nothing
//! compiles against v1, and the current edition keeps no reading of it. The document
//! migration applies to a document known to be written in v1: a current document can hold a
//! word that v1 read otherwise (`large` as an amplitude), so it must not be migrated again.

use std::collections::{BTreeMap, BTreeSet};

use serde::Serialize;
use serde_json::{Map, Value};

use crate::{
    MacroDefinition, MacroDefinitionIdentity, NormalizedDdlDocument, ResolvedInstructionLanguage,
    SourceSpan, associate_semantic_entities,
    parser::{NeutralTokenKind, parse_neutral_lexemes, parse_neutral_lexemes_in},
    saijiki::SaijikiEdition,
};

/// Stable identity of the v1 migration contract.
pub const SAIJIKI_V1_MIGRATION_SCHEMA_ID: &str = "inku.saijiki-v1-migration.v1";

/// One v1 word and the current word written in its place.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SaijikiMigrationEdit {
    /// The word's span in the v1 source.
    pub span: SourceSpan,
    pub original: String,
    pub replacement: String,
}

/// A saved document rewritten from Saijiki v1 to the current edition.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SaijikiDocumentMigration {
    pub source: String,
    pub edits: Vec<SaijikiMigrationEdit>,
    /// Spans in the migrated source of each sweep that stands for a v1 pale ink wash whose mark
    /// the association could not name, as in a Macro argument or a sequence. `薄い` or `faint`
    /// is written right before it, so the host can show the author where to look.
    pub unassociated_sweeps: Vec<SourceSpan>,
}

/// A saved Macro definition rewritten from Saijiki v1 to the current edition. Its version is
/// kept; only its digest changes, and a work's lock moves to the new digest.
#[derive(Clone, Debug, PartialEq)]
pub struct SaijikiDefinitionMigration {
    pub definition: Value,
    pub identity: MacroDefinitionIdentity,
    pub changed: bool,
}

/// Why a document or definition could not be migrated.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "code", rename_all = "snake_case")]
pub enum SaijikiMigrationError {
    /// A changed v1 word was read from a surface the migration does not know.
    UnmappedV1Surface { span: SourceSpan, surface: String },
    /// The migrated source reads with more diagnostics than the v1 source did.
    MigratedSourceNotRecognized {
        v1_diagnostics: usize,
        current_diagnostics: usize,
    },
    /// The document cannot be formed or rewritten; the stage says where, and why.
    InvalidDocument(InvalidDocumentStage),
    /// The definition is not a Macro definition object.
    UnreadableDefinition,
    /// A pale ink wash or blurring stands where it cannot be rewritten by its mark's fields.
    IndirectRetiredWord {
        path: String,
        category: String,
        id: String,
    },
    /// A surface parameter reaches both a surface quality and a surface intensity.
    AmbiguousSurfaceParameter { path: String },
    /// The rewritten definition does not validate against the current edition.
    MigratedDefinitionInvalid { codes: Vec<String> },
}

impl SaijikiMigrationError {
    pub const fn code(&self) -> &'static str {
        match self {
            Self::UnmappedV1Surface { .. } => "unmapped_v1_surface",
            Self::MigratedSourceNotRecognized { .. } => "migrated_source_not_recognized",
            Self::InvalidDocument(_) => "invalid_document",
            Self::UnreadableDefinition => "unreadable_definition",
            Self::IndirectRetiredWord { .. } => "indirect_retired_word",
            Self::AmbiguousSurfaceParameter { .. } => "ambiguous_surface_parameter",
            Self::MigratedDefinitionInvalid { .. } => "migrated_definition_invalid",
        }
    }
}

/// Where a document stopped as an invalid document, with the reason it was given there.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "stage", rename_all = "snake_case")]
pub enum InvalidDocumentStage {
    /// A saved lock is not a Macro lock; `lock` is its index in the saved `macro_locks`.
    V1Locks { lock: usize, cause: &'static str },
    /// The saved locks cannot form a document, as when a name is locked twice.
    V1Document { cause: &'static str },
    /// The source with its washes rewritten cannot form a document with the same locks.
    ProvisionalDocument { cause: &'static str },
    /// The intensity the current reading puts on a wash's mark is not one v1 word. Spans are
    /// in the v1 source; a bound inside a rewritten word widens to that word. `surface` is
    /// the intensity as the current reading took it.
    WashIntensity {
        wash: SourceSpan,
        intensity: SourceSpan,
        surface: String,
    },
    /// The rewritten source cannot form a document with the same locks.
    MigratedDocument { cause: &'static str },
}

const JA: ResolvedInstructionLanguage = ResolvedInstructionLanguage::Ja;
const EN: ResolvedInstructionLanguage = ResolvedInstructionLanguage::En;

/// One v1 row read from one source surface, and the current word for it.
struct WordRewrite {
    language: ResolvedInstructionLanguage,
    category_key: &'static str,
    canonical_surface_ja: &'static str,
    /// The source surface; English compares without case.
    from: &'static str,
    to: &'static str,
}

const fn rewrite(
    language: ResolvedInstructionLanguage,
    category_key: &'static str,
    canonical_surface_ja: &'static str,
    from: &'static str,
    to: &'static str,
) -> WordRewrite {
    WordRewrite {
        language,
        category_key,
        canonical_surface_ja,
        from,
        to,
    }
}

/// The v1 → v2 correspondence (draw-system05 17.3 and 17.7).
const WORD_REWRITES: &[WordRewrite] = &[
    // A pale ink wash is a faint sweep; the faint is written on its mark afterwards.
    rewrite(JA, "omote", "薄墨", "薄墨", "刷き"),
    rewrite(EN, "omote", "薄墨", "pale ink wash", "sweep"),
    rewrite(JA, "yuragi", "ゆっくり", "ゆっくり", "ゆるやかに"),
    rewrite(EN, "yuragi", "ゆっくり", "slowly", "loosely"),
    rewrite(JA, "yuragi", "速く", "速く", "小刻みに"),
    rewrite(EN, "yuragi", "速く", "quickly", "tightly"),
    rewrite(EN, "yuragi", "細かく", "fine", "narrowly"),
    rewrite(EN, "yuragi", "細かく", "finely", "narrowly"),
    rewrite(EN, "yuragi", "大きく", "large", "broadly"),
    rewrite(EN, "yuragi", "大きく", "largely", "broadly"),
    // The aliases v1 kept from the rows consolidated on 2026-09-14.
    rewrite(JA, "omote", "点描", "点", "点描"),
    rewrite(JA, "yuragi", "揺れる", "震える", "揺れる"),
    rewrite(EN, "yuragi", "揺れる", "trembling", "swaying"),
    rewrite(EN, "yuragi", "揺れる", "trembles", "sways"),
    rewrite(JA, "yuragi", "にじみ", "滲む", "にじみ"),
    rewrite(EN, "yuragi", "にじみ", "blurring", "bleeding"),
    rewrite(JA, "basho", "中心", "中央", "中心"),
    rewrite(EN, "basho", "中心", "middle", "center"),
];

/// Rows whose every v1 surface in a language changed; any other surface is unmapped.
const CHANGED_ROWS: &[(ResolvedInstructionLanguage, &str, &str)] = &[
    (JA, "omote", "薄墨"),
    (EN, "omote", "薄墨"),
    (JA, "yuragi", "ゆっくり"),
    (EN, "yuragi", "ゆっくり"),
    (JA, "yuragi", "速く"),
    (EN, "yuragi", "速く"),
    (EN, "yuragi", "細かく"),
    (EN, "yuragi", "大きく"),
];

fn same_surface(language: ResolvedInstructionLanguage, left: &str, right: &str) -> bool {
    match language {
        ResolvedInstructionLanguage::Ja => left == right,
        ResolvedInstructionLanguage::En => left.eq_ignore_ascii_case(right),
    }
}

/// Write `replacement` in the letter case the author wrote `original` in.
fn in_source_case(
    language: ResolvedInstructionLanguage,
    original: &str,
    replacement: &str,
) -> String {
    if language == ResolvedInstructionLanguage::Ja {
        return replacement.to_owned();
    }
    let letters = original
        .chars()
        .filter(|character| character.is_ascii_alphabetic())
        .collect::<Vec<_>>();
    if letters.len() > 1 && letters.iter().all(char::is_ascii_uppercase) {
        return replacement.to_ascii_uppercase();
    }
    if letters.first().is_some_and(char::is_ascii_uppercase) {
        let mut characters = replacement.chars();
        return characters
            .next()
            .map(|first| first.to_ascii_uppercase().to_string() + characters.as_str())
            .unwrap_or_default();
    }
    replacement.to_owned()
}

fn is_wash(category_key: &str, canonical_surface_ja: &str) -> bool {
    category_key == "omote" && canonical_surface_ja == "薄墨"
}

fn faint_word(language: ResolvedInstructionLanguage) -> &'static str {
    match language {
        ResolvedInstructionLanguage::Ja => "薄い",
        ResolvedInstructionLanguage::En => "faint",
    }
}

/// The source rebuilt with some tokens replaced, and every token's span in it.
fn rebuild(
    source: &str,
    spans: &[SourceSpan],
    replacements: &BTreeMap<usize, String>,
) -> (String, Vec<SourceSpan>) {
    let mut rebuilt = String::with_capacity(source.len());
    let mut rebuilt_spans = Vec::with_capacity(spans.len());
    let mut cursor = 0;
    for (index, span) in spans.iter().enumerate() {
        rebuilt.push_str(&source[cursor..span.start_byte]);
        let start_byte = rebuilt.len();
        rebuilt.push_str(
            replacements
                .get(&index)
                .map_or(&source[span.start_byte..span.end_byte], String::as_str),
        );
        rebuilt_spans.push(SourceSpan {
            start_byte,
            end_byte: rebuilt.len(),
        });
        cursor = span.end_byte;
    }
    rebuilt.push_str(&source[cursor..]);
    (rebuilt, rebuilt_spans)
}

/// A span of a source rebuilt from `source`, in `source`. A bound inside a replaced token
/// widens to that token; text outside the tokens was copied as it was.
fn span_before_rebuild(
    span: SourceSpan,
    source: &str,
    spans: &[SourceSpan],
    rebuilt: &str,
    rebuilt_spans: &[SourceSpan],
) -> SourceSpan {
    let source_offset = |offset: usize, widen_to_end: bool| {
        // The last token that starts at or before the offset.
        let Some(index) = rebuilt_spans
            .partition_point(|token| token.start_byte <= offset)
            .checked_sub(1)
        else {
            return offset;
        };
        let (before, after) = (spans[index], rebuilt_spans[index]);
        if offset >= after.end_byte {
            before.end_byte + (offset - after.end_byte)
        } else if source[before.start_byte..before.end_byte]
            == rebuilt[after.start_byte..after.end_byte]
        {
            before.start_byte + (offset - after.start_byte)
        } else if widen_to_end && offset > after.start_byte {
            before.end_byte
        } else {
            before.start_byte
        }
    };
    SourceSpan {
        start_byte: source_offset(span.start_byte, false),
        end_byte: source_offset(span.end_byte, true),
    }
}

/// Rewrite one saved v1 document to the current edition, word by word at its positions.
///
/// A pale ink wash becomes a faint sweep: a surface intensity already on its mark becomes
/// `薄い` / `faint` in place (v1 dropped it from a wash), and otherwise the faint is written
/// before the sweep. The result is read again with the current edition and refused if it
/// reads with more diagnostics than the v1 source did.
pub fn migrate_document_from_saijiki_v1(
    document: &NormalizedDdlDocument,
) -> Result<SaijikiDocumentMigration, SaijikiMigrationError> {
    let language = document.language();
    let source = document.source();
    let v1 = parse_neutral_lexemes_in(SaijikiEdition::V1, document);
    let spans = v1.tokens.iter().map(|token| token.span).collect::<Vec<_>>();

    let mut replacements = BTreeMap::new();
    let mut washes = Vec::new();
    for (index, token) in v1.tokens.iter().enumerate() {
        let NeutralTokenKind::SaijikiWord {
            category_key,
            canonical_surface_ja,
            ..
        } = &token.kind
        else {
            continue;
        };
        let rewrite = WORD_REWRITES.iter().find(|rewrite| {
            rewrite.language == language
                && rewrite.category_key == category_key
                && rewrite.canonical_surface_ja == canonical_surface_ja
                && same_surface(language, rewrite.from, &token.surface)
        });
        let Some(rewrite) = rewrite else {
            if CHANGED_ROWS
                .iter()
                .any(|(row_language, category, surface_ja)| {
                    *row_language == language
                        && category == category_key
                        && surface_ja == canonical_surface_ja
                })
            {
                return Err(SaijikiMigrationError::UnmappedV1Surface {
                    span: token.span,
                    surface: token.surface.clone(),
                });
            }
            continue;
        };
        if is_wash(category_key, canonical_surface_ja) {
            washes.push(index);
        }
        replacements.insert(index, in_source_case(language, &token.surface, rewrite.to));
    }

    // The current association names the mark of each sweep and any intensity it carries.
    let mut unassociated = BTreeSet::new();
    if !washes.is_empty() {
        let (provisional, provisional_spans) = rebuild(source, &spans, &replacements);
        let provisional_document =
            NormalizedDdlDocument::new(provisional, language, document.macro_locks().to_vec())
                .map_err(|diagnostic| {
                    SaijikiMigrationError::InvalidDocument(
                        InvalidDocumentStage::ProvisionalDocument {
                            cause: diagnostic.code(),
                        },
                    )
                })?;
        let entities = associate_semantic_entities(&provisional_document)
            .map(|association| association.ast.entities)
            .unwrap_or_default();
        let token_at = |span: SourceSpan| provisional_spans.iter().position(|each| *each == span);
        for &wash in &washes {
            let intensity = entities.iter().find_map(|entity| {
                let quality = entity.surface.quality.as_ref()?;
                (token_at(quality.provenance.source.span) == Some(wash))
                    .then_some(entity.surface.intensity.as_ref())
            });
            match intensity {
                Some(Some(term)) => {
                    let Some(index) = token_at(term.provenance.source.span) else {
                        return Err(SaijikiMigrationError::InvalidDocument(
                            InvalidDocumentStage::WashIntensity {
                                wash: spans[wash],
                                intensity: span_before_rebuild(
                                    term.provenance.source.span,
                                    source,
                                    &spans,
                                    provisional_document.source(),
                                    &provisional_spans,
                                ),
                                surface: term.provenance.source.surface.clone(),
                            },
                        ));
                    };
                    let original = &v1.tokens[index].surface;
                    if !same_surface(language, original, faint_word(language)) {
                        replacements.insert(
                            index,
                            in_source_case(language, original, faint_word(language)),
                        );
                    }
                }
                found => {
                    if found.is_none() {
                        unassociated.insert(wash);
                    }
                    let original = &v1.tokens[wash].surface;
                    let phrase = match language {
                        ResolvedInstructionLanguage::Ja => "薄い刷き",
                        ResolvedInstructionLanguage::En => "faint sweep",
                    };
                    replacements.insert(wash, in_source_case(language, original, phrase));
                }
            }
        }
    }

    let (migrated, migrated_spans) = rebuild(source, &spans, &replacements);
    let migrated_document =
        NormalizedDdlDocument::new(migrated.clone(), language, document.macro_locks().to_vec())
            .map_err(|diagnostic| {
                SaijikiMigrationError::InvalidDocument(InvalidDocumentStage::MigratedDocument {
                    cause: diagnostic.code(),
                })
            })?;
    let current_diagnostics = parse_neutral_lexemes(&migrated_document).diagnostics.len();
    if current_diagnostics > v1.diagnostics.len() {
        return Err(SaijikiMigrationError::MigratedSourceNotRecognized {
            v1_diagnostics: v1.diagnostics.len(),
            current_diagnostics,
        });
    }
    let edits = replacements
        .iter()
        .map(|(&index, replacement)| SaijikiMigrationEdit {
            span: spans[index],
            original: v1.tokens[index].surface.clone(),
            replacement: replacement.clone(),
        })
        .collect();
    Ok(SaijikiDocumentMigration {
        source: migrated,
        edits,
        unassociated_sweeps: unassociated
            .into_iter()
            .map(|index| migrated_spans[index])
            .collect(),
    })
}

fn semantic_ref(category: &str, id: &str) -> Value {
    serde_json::json!({"expr": "semantic_ref", "category": category, "id": id})
}

fn is_semantic_ref(value: &Value, category: &str, id: &str) -> bool {
    value.get("expr").and_then(Value::as_str) == Some("semantic_ref")
        && value.get("category").and_then(Value::as_str) == Some(category)
        && value.get("id").and_then(Value::as_str) == Some(id)
}

/// Context-free v1 → v2 semantic reference renames.
fn renamed_semantic_ref(category: &str, id: &str) -> Option<(&'static str, &'static str)> {
    Some(match (category, id) {
        ("variation", "fine") => ("variation", "narrowly"),
        ("variation", "large") => ("variation", "broadly"),
        ("variation", "slowly") => ("variation", "loosely"),
        ("variation", "quickly") => ("variation", "tightly"),
        ("variation", "trembling") => ("variation", "swaying"),
        ("place", "middle") => ("place", "center"),
        ("surface", "dense") => ("handling", "dense"),
        ("surface", "faint") => ("handling", "faint"),
        _ => return None,
    })
}

/// Which surface field a parameter or local reaches.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
enum SurfaceReach {
    Quality,
    Intensity,
}

type ReachNode = (String, String);

#[derive(Default)]
struct ReachGraph {
    direct: BTreeMap<ReachNode, BTreeSet<SurfaceReach>>,
    /// A node reaches every field its successors reach.
    edges: BTreeMap<ReachNode, BTreeSet<ReachNode>>,
}

/// Every parameter or local an expression refers to.
fn references(expression: &Value, scope: &str, out: &mut Vec<ReachNode>) {
    match expression.get("expr").and_then(Value::as_str) {
        Some("parameter") => {
            if let Some(name) = expression.get("name").and_then(Value::as_str) {
                out.push((scope.to_owned(), format!("parameter:{name}")));
            }
        }
        Some("local") => {
            if let Some(name) = expression.get("name").and_then(Value::as_str) {
                out.push((scope.to_owned(), format!("local:{name}")));
            }
        }
        Some("list" | "cycle") => {
            for item in expression
                .get("items")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
            {
                references(item, scope, out);
            }
        }
        _ => {}
    }
}

fn collect_reach(statements: &[Value], scope: &str, graph: &mut ReachGraph) {
    for statement in statements {
        match statement.get("op").and_then(Value::as_str) {
            Some("emit") => {
                for (field, expression) in statement
                    .get("fields")
                    .and_then(Value::as_object)
                    .into_iter()
                    .flatten()
                {
                    let reach = match field.as_str() {
                        "surface" => SurfaceReach::Quality,
                        "surface_intensity" => SurfaceReach::Intensity,
                        _ => continue,
                    };
                    let mut found = Vec::new();
                    references(expression, scope, &mut found);
                    for node in found {
                        graph.direct.entry(node).or_default().insert(reach);
                    }
                }
            }
            Some("use") => {
                let Some(component) = statement.get("component").and_then(Value::as_str) else {
                    continue;
                };
                let target_scope = format!("$.components.{component}");
                for (name, expression) in statement
                    .get("arguments")
                    .and_then(Value::as_object)
                    .into_iter()
                    .flatten()
                {
                    let mut found = Vec::new();
                    references(expression, scope, &mut found);
                    for node in found {
                        graph
                            .edges
                            .entry(node)
                            .or_default()
                            .insert((target_scope.clone(), format!("parameter:{name}")));
                    }
                }
            }
            Some("vary") => {
                if let Some(binding) = statement.get("binding").and_then(Value::as_str) {
                    let local = (scope.to_owned(), format!("local:{binding}"));
                    for choice in statement
                        .get("choices")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                    {
                        let mut found = Vec::new();
                        references(choice, scope, &mut found);
                        for node in found {
                            graph.edges.entry(node).or_default().insert(local.clone());
                        }
                    }
                }
            }
            _ => {}
        }
        if let Some(body) = statement.get("body").and_then(Value::as_array) {
            collect_reach(body, scope, graph);
        }
    }
}

fn resolved_reach(graph: &ReachGraph) -> BTreeMap<ReachNode, BTreeSet<SurfaceReach>> {
    let mut reach = graph.direct.clone();
    loop {
        let mut changed = false;
        for (node, successors) in &graph.edges {
            let gathered = successors
                .iter()
                .filter_map(|successor| reach.get(successor))
                .flatten()
                .copied()
                .collect::<BTreeSet<_>>();
            let entry = reach.entry(node.clone()).or_default();
            let before = entry.len();
            entry.extend(gathered);
            changed |= entry.len() != before;
        }
        if !changed {
            return reach;
        }
    }
}

/// The definition's scopes: the root and each component, with its path.
fn scopes(root: &Map<String, Value>) -> Vec<String> {
    std::iter::once("$".to_owned())
        .chain(
            root.get("components")
                .and_then(Value::as_object)
                .into_iter()
                .flatten()
                .map(|(name, _)| format!("$.components.{name}")),
        )
        .collect()
}

fn scope_object_mut<'a>(
    root: &'a mut Map<String, Value>,
    scope: &str,
) -> Option<&'a mut Map<String, Value>> {
    match scope.strip_prefix("$.components.") {
        None => Some(root),
        Some(component) => root
            .get_mut("components")?
            .as_object_mut()?
            .get_mut(component)?
            .as_object_mut(),
    }
}

/// A v1 surface parameter that reaches only surface intensities becomes a handling parameter.
fn retype_handling_parameters(root: &mut Map<String, Value>) -> Result<(), SaijikiMigrationError> {
    let mut graph = ReachGraph::default();
    for scope in scopes(root) {
        let Some(object) = scope_object_mut(root, &scope) else {
            continue;
        };
        if let Some(body) = object.get("body").and_then(Value::as_array) {
            collect_reach(body, &scope, &mut graph);
        }
    }
    let reach = resolved_reach(&graph);
    for scope in scopes(root) {
        let Some(parameters) = scope_object_mut(root, &scope)
            .and_then(|object| object.get_mut("parameters"))
            .and_then(Value::as_object_mut)
        else {
            continue;
        };
        for (name, schema) in parameters.iter_mut() {
            if schema.get("type").and_then(Value::as_str) != Some("semantic_ref")
                || schema.get("category").and_then(Value::as_str) != Some("surface")
            {
                continue;
            }
            let reaches = reach
                .get(&(scope.clone(), format!("parameter:{name}")))
                .cloned()
                .unwrap_or_default();
            if reaches.contains(&SurfaceReach::Quality)
                && reaches.contains(&SurfaceReach::Intensity)
            {
                return Err(SaijikiMigrationError::AmbiguousSurfaceParameter {
                    path: format!("{scope}.parameters.{name}"),
                });
            }
            if reaches.contains(&SurfaceReach::Intensity) {
                schema["category"] = Value::String("handling".to_owned());
            }
        }
    }
    Ok(())
}

/// A pale ink wash on a mark becomes a faint sweep, and blurring becomes bleeding ink.
fn rewrite_emit_fields(statements: &mut [Value]) {
    for statement in statements {
        if statement.get("op").and_then(Value::as_str) == Some("emit")
            && let Some(fields) = statement.get_mut("fields").and_then(Value::as_object_mut)
        {
            if fields
                .get("surface")
                .is_some_and(|value| is_semantic_ref(value, "surface", "wash"))
            {
                fields.insert("surface".to_owned(), semantic_ref("surface", "sweep"));
                // v1 dropped any intensity from a wash, which was pale by itself.
                fields.insert(
                    "surface_intensity".to_owned(),
                    semantic_ref("handling", "faint"),
                );
            }
            if fields
                .get("fluctuation_quality")
                .is_some_and(|value| is_semantic_ref(value, "variation", "blurring"))
            {
                // Blurring moved to bleeding ink with the visible 滲む on 2026-09-14.
                fields.remove("fluctuation_quality");
                fields
                    .entry("ink_spread")
                    .or_insert_with(|| semantic_ref("variation", "bleeding"));
            }
        }
        if let Some(body) = statement.get_mut("body").and_then(Value::as_array_mut) {
            rewrite_emit_fields(body);
        }
    }
}

fn rewrite_semantic_refs(value: &mut Value, path: &str) -> Result<(), SaijikiMigrationError> {
    match value {
        Value::Object(object) => {
            if object.get("expr").and_then(Value::as_str) == Some("semantic_ref") {
                let category = object
                    .get("category")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_owned();
                let id = object
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_owned();
                if let Some((category, id)) = renamed_semantic_ref(&category, &id) {
                    object.insert("category".to_owned(), Value::String(category.to_owned()));
                    object.insert("id".to_owned(), Value::String(id.to_owned()));
                } else if matches!(
                    (category.as_str(), id.as_str()),
                    ("surface", "wash") | ("variation", "blurring")
                ) {
                    return Err(SaijikiMigrationError::IndirectRetiredWord {
                        path: path.to_owned(),
                        category,
                        id,
                    });
                }
                return Ok(());
            }
            for (key, child) in object.iter_mut() {
                rewrite_semantic_refs(child, &format!("{path}.{key}"))?;
            }
        }
        Value::Array(items) => {
            for (index, child) in items.iter_mut().enumerate() {
                rewrite_semantic_refs(child, &format!("{path}[{index}]"))?;
            }
        }
        _ => {}
    }
    Ok(())
}

/// Rewrite one saved v1 Macro definition to the current edition.
///
/// Semantic references move to their current words; a pale ink wash on a mark becomes a
/// faint sweep and blurring becomes bleeding ink; a surface parameter that reaches only
/// surface intensities becomes a handling parameter. The version is kept. A definition with
/// no v1 word is returned unchanged, so migrating twice is harmless.
pub fn migrate_macro_definition_from_saijiki_v1(
    definition: &Value,
) -> Result<SaijikiDefinitionMigration, SaijikiMigrationError> {
    let mut migrated = definition.clone();
    let root = migrated
        .as_object_mut()
        .ok_or(SaijikiMigrationError::UnreadableDefinition)?;
    retype_handling_parameters(root)?;
    for scope in scopes(root) {
        if let Some(body) = scope_object_mut(root, &scope)
            .and_then(|object| object.get_mut("body"))
            .and_then(Value::as_array_mut)
        {
            rewrite_emit_fields(body);
        }
    }
    rewrite_semantic_refs(&mut migrated, "$")?;

    let typed = MacroDefinition::from_json(&migrated.to_string())
        .map_err(|_| SaijikiMigrationError::UnreadableDefinition)?;
    let validation = typed.validate();
    if !validation.is_valid() {
        return Err(SaijikiMigrationError::MigratedDefinitionInvalid {
            codes: validation
                .diagnostics()
                .iter()
                .map(|diagnostic| diagnostic.code().to_owned())
                .collect(),
        });
    }
    let identity = typed.identity().map_err(|validation| {
        SaijikiMigrationError::MigratedDefinitionInvalid {
            codes: validation
                .diagnostics()
                .iter()
                .map(|diagnostic| diagnostic.code().to_owned())
                .collect(),
        }
    })?;
    Ok(SaijikiDefinitionMigration {
        changed: migrated != *definition,
        definition: migrated,
        identity,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_span_of_a_rebuilt_source_is_found_in_the_source_it_was_rebuilt_from() {
        let source = "ab cd ef";
        let spans = [(0, 2), (3, 5), (6, 8)].map(|(start_byte, end_byte)| SourceSpan {
            start_byte,
            end_byte,
        });
        let (rebuilt, rebuilt_spans) =
            rebuild(source, &spans, &BTreeMap::from([(1, "wxyz".to_owned())]));
        assert_eq!(rebuilt, "ab wxyz ef");
        let before = |start_byte, end_byte| {
            let span = span_before_rebuild(
                SourceSpan {
                    start_byte,
                    end_byte,
                },
                source,
                &spans,
                &rebuilt,
                &rebuilt_spans,
            );
            source[span.start_byte..span.end_byte].to_owned()
        };
        // Kept words and the text between words map exactly; a bound inside the rewritten
        // word widens to that word.
        assert_eq!(before(8, 10), "ef");
        assert_eq!(before(1, 9), "b cd e");
        assert_eq!(before(4, 6), "cd");
        assert_eq!(before(7, 8), " ");
    }
}

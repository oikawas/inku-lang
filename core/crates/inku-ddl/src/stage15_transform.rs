//! CanonicalReady-only focus and one-axis variation over typed DDL meaning.

use std::collections::BTreeMap;

use serde_json::{Number, Value};
use sha2::{Digest, Sha256};

use crate::{
    CompilerLockState, EXPANDED_MACRO_MEANING_SCHEMA_ID, ExpandedMacroInvocation,
    ExpandedMacroNode, ExpandedMacroValue, ExpansionPathSegment, GeneratedNodeProvenance,
    SEMANTIC_DOCUMENT_SCHEMA_ID, SemanticDocumentAst, SemanticIdentity, SemanticTermProvenance,
    TYPED_DDL_COMPILATION_SCHEMA_ID, TYPED_DDL_COMPILER_LOCK_SCHEMA_ID, TypedDdlCompilation,
    compiler_lock_hash_input, expanded_generated_provenance_canonical_bytes,
    expanded_meaning_canonical_bytes, semantic_document::canonical_ast_bytes,
    semantic_source_provenance_canonical_bytes,
};

/// Stable identity for the effective typed Stage 1.5 overlay.
pub const STAGE15_TRANSFORMATION_SCHEMA_ID: &str = "inku.typed-stage15-transformation.v3";
/// Framed hash domain for source-independent baseline focus selection.
pub const STAGE15_FOCUS_SELECTION_DOMAIN: &[u8] = b"inku.typed-stage15-focus-selection.v1";

/// Closed, source-independent Stage 1.5 focus vocabulary in canonical order.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum FocusRegion {
    UpperRight,
    UpperLeft,
    LowerRight,
    LowerLeft,
    UpperEdge,
    RightHalf,
}

impl FocusRegion {
    pub const ALL: [Self; 6] = [
        Self::UpperRight,
        Self::UpperLeft,
        Self::LowerRight,
        Self::LowerLeft,
        Self::UpperEdge,
        Self::RightHalf,
    ];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::UpperRight => "upper_right",
            Self::UpperLeft => "upper_left",
            Self::LowerRight => "lower_right",
            Self::LowerLeft => "lower_left",
            Self::UpperEdge => "upper_edge",
            Self::RightHalf => "right_half",
        }
    }
}

/// Closed explicit variation amplitude. Partial or unknown values cannot enter the core.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Stage15VariationAmplitude {
    Small,
    Medium,
    Large,
}

impl Stage15VariationAmplitude {
    pub const ALL: [Self; 3] = [Self::Small, Self::Medium, Self::Large];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Small => "small",
            Self::Medium => "medium",
            Self::Large => "large",
        }
    }
}

/// One complete explicit variation request.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Stage15Variation {
    pub amplitude: Stage15VariationAmplitude,
    pub seed: u64,
}

/// Stable owner path for one exact `place:center` target.
#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum Stage15TargetPath {
    Instruction {
        instruction_index: usize,
    },
    GroupPredicate {
        edge_index: usize,
        group_index: usize,
    },
    MacroEmit {
        invocation_ordinal: u64,
        expansion_path: Vec<ExpansionPathSegment>,
        generated_ordinal: u64,
        field: String,
    },
}

/// Lossless original provenance for one source-owned or generated target.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Stage15TargetProvenance {
    Source(SemanticTermProvenance),
    Generated(GeneratedNodeProvenance),
}

/// One effective overlay entry. The original semantic term is not mutated.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Stage15TargetTransformation {
    pub path: Stage15TargetPath,
    pub original: SemanticIdentity,
    pub effective_focus: FocusRegion,
    pub provenance: Stage15TargetProvenance,
}

/// Source-independent report for the sole variation axis.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Stage15MovedAxis {
    pub axis: &'static str,
    pub from: FocusRegion,
    pub to: FocusRegion,
}

/// Complete, validated input owned independently from the source-bearing compilation envelope.
#[derive(Clone, Debug, PartialEq)]
pub struct Stage15TransformationInput {
    semantic_document: SemanticDocumentAst,
    expanded_invocations: Vec<ExpandedMacroInvocation>,
    pre_expansion_digest: String,
    expanded_meaning_digest: String,
    composition_seed: Option<u64>,
}

impl Stage15TransformationInput {
    pub const fn semantic_document(&self) -> &SemanticDocumentAst {
        &self.semantic_document
    }

    pub fn expanded_invocations(&self) -> &[ExpandedMacroInvocation] {
        &self.expanded_invocations
    }

    pub fn pre_expansion_digest(&self) -> &str {
        &self.pre_expansion_digest
    }

    pub fn expanded_meaning_digest(&self) -> &str {
        &self.expanded_meaning_digest
    }

    pub const fn composition_seed(&self) -> Option<u64> {
        self.composition_seed
    }
}

/// Original typed meaning plus a separate effective overlay and its canonical identity.
#[derive(Clone, Debug, PartialEq)]
pub struct Stage15TransformationResult {
    schema_id: &'static str,
    original_semantic_document: SemanticDocumentAst,
    original_expanded_invocations: Vec<ExpandedMacroInvocation>,
    original_pre_expansion_digest: String,
    original_expanded_meaning_digest: String,
    composition_seed: Option<u64>,
    baseline_focus: Option<FocusRegion>,
    resolved_focus: Option<FocusRegion>,
    effective_variation: Option<Stage15Variation>,
    targets: Vec<Stage15TargetTransformation>,
    moved_axes: Vec<Stage15MovedAxis>,
    effective_canonical_bytes: Vec<u8>,
    effective_canonical_digest: String,
}

impl Stage15TransformationResult {
    pub const fn schema_id(&self) -> &'static str {
        self.schema_id
    }

    pub const fn original_semantic_document(&self) -> &SemanticDocumentAst {
        &self.original_semantic_document
    }

    pub fn original_expanded_invocations(&self) -> &[ExpandedMacroInvocation] {
        &self.original_expanded_invocations
    }

    pub fn original_pre_expansion_digest(&self) -> &str {
        &self.original_pre_expansion_digest
    }

    pub fn original_expanded_meaning_digest(&self) -> &str {
        &self.original_expanded_meaning_digest
    }

    pub const fn composition_seed(&self) -> Option<u64> {
        self.composition_seed
    }

    pub const fn baseline_focus(&self) -> Option<FocusRegion> {
        self.baseline_focus
    }

    pub const fn resolved_focus(&self) -> Option<FocusRegion> {
        self.resolved_focus
    }

    pub const fn effective_variation(&self) -> Option<Stage15Variation> {
        self.effective_variation
    }

    pub fn targets(&self) -> &[Stage15TargetTransformation] {
        &self.targets
    }

    pub fn moved_axes(&self) -> &[Stage15MovedAxis] {
        &self.moved_axes
    }

    pub fn effective_canonical_bytes(&self) -> &[u8] {
        &self.effective_canonical_bytes
    }

    pub fn effective_canonical_digest(&self) -> &str {
        &self.effective_canonical_digest
    }

    pub const fn verified_effective_view(&self) -> VerifiedStage15EffectiveView<'_> {
        VerifiedStage15EffectiveView { result: self }
    }
}

/// Read-only, non-forgeable view over one successfully transformed Stage 1.5 result.
#[derive(Clone, Copy, Debug)]
pub struct VerifiedStage15EffectiveView<'a> {
    result: &'a Stage15TransformationResult,
}

impl<'a> VerifiedStage15EffectiveView<'a> {
    pub const fn schema_id(self) -> &'static str {
        self.result.schema_id()
    }

    pub const fn original_semantic_document(self) -> &'a SemanticDocumentAst {
        self.result.original_semantic_document()
    }

    pub fn original_expanded_invocations(self) -> &'a [ExpandedMacroInvocation] {
        self.result.original_expanded_invocations()
    }

    pub const fn composition_seed(self) -> Option<u64> {
        self.result.composition_seed()
    }

    pub fn effective_canonical_bytes(self) -> &'a [u8] {
        self.result.effective_canonical_bytes()
    }

    pub fn effective_canonical_digest(self) -> &'a str {
        self.result.effective_canonical_digest()
    }

    pub fn pending_focus_targets(self) -> &'a [Stage15TargetTransformation] {
        self.result.targets()
    }
}

/// Closed fail-closed errors for input identity and target integrity.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Stage15TransformError {
    CompilationSchema,
    MissingCompilerLock,
    CompilerLockSchema,
    CompilerState(CompilerLockState),
    CompilerLockDigestMismatch,
    CanonicalReadyInvariant,
    MissingSemanticDocument,
    IncompleteSemanticDocument,
    MissingSemanticCanonicalBytes,
    MissingSemanticCanonicalDigest,
    SemanticAstCanonicalMismatch,
    SemanticCanonicalDigestMismatch,
    MissingSemanticSourceProvenanceDigest,
    SemanticSourceProvenanceDigestMismatch,
    MissingMacroExpansion,
    ExpansionDiagnostic,
    MissingExpandedMeaningDigest,
    ExpandedMeaningDigestMismatch,
    MissingExpandedGeneratedProvenanceDigest,
    ExpandedGeneratedProvenanceDigestMismatch,
    DuplicateTarget(Stage15TargetPath),
    MissingTarget(Stage15TargetPath),
    OriginalIdentityMismatch(Stage15TargetPath),
}

/// Validate and detach the complete source-independent input needed by Stage 1.5.
pub fn stage15_transformation_input(
    compilation: &TypedDdlCompilation,
) -> Result<Stage15TransformationInput, Stage15TransformError> {
    if compilation.schema_id != TYPED_DDL_COMPILATION_SCHEMA_ID {
        return Err(Stage15TransformError::CompilationSchema);
    }
    let lock = compilation
        .compiler_lock
        .as_ref()
        .ok_or(Stage15TransformError::MissingCompilerLock)?;
    if lock.schema_id != TYPED_DDL_COMPILER_LOCK_SCHEMA_ID {
        return Err(Stage15TransformError::CompilerLockSchema);
    }
    if lock.state != CompilerLockState::CanonicalReady {
        return Err(Stage15TransformError::CompilerState(lock.state));
    }
    if sha256_hex(&compiler_lock_hash_input(lock)) != lock.full_digest {
        return Err(Stage15TransformError::CompilerLockDigestMismatch);
    }
    if !compilation.holes.is_empty()
        || !compilation.conflicts.is_empty()
        || !compilation.blocking_diagnostics.is_empty()
    {
        return Err(Stage15TransformError::CanonicalReadyInvariant);
    }

    let semantic = compilation
        .semantic_document
        .as_ref()
        .ok_or(Stage15TransformError::MissingSemanticDocument)?;
    if !semantic.ast.complete
        || !semantic.issues.is_empty()
        || !semantic.continuation_issues.is_empty()
    {
        return Err(Stage15TransformError::IncompleteSemanticDocument);
    }
    let semantic_bytes = semantic
        .canonical_bytes
        .as_deref()
        .ok_or(Stage15TransformError::MissingSemanticCanonicalBytes)?;
    if canonical_ast_bytes(&semantic.ast) != semantic_bytes {
        return Err(Stage15TransformError::SemanticAstCanonicalMismatch);
    }
    let pre_expansion_digest = lock
        .canonical_pre_expansion_digest
        .as_ref()
        .ok_or(Stage15TransformError::MissingSemanticCanonicalDigest)?;
    if sha256_hex(semantic_bytes) != *pre_expansion_digest {
        return Err(Stage15TransformError::SemanticCanonicalDigestMismatch);
    }
    let semantic_source_provenance_digest = lock
        .semantic_source_provenance_digest
        .as_ref()
        .ok_or(Stage15TransformError::MissingSemanticSourceProvenanceDigest)?;
    if sha256_hex(&semantic_source_provenance_canonical_bytes(&semantic.ast))
        != *semantic_source_provenance_digest
    {
        return Err(Stage15TransformError::SemanticSourceProvenanceDigestMismatch);
    }

    let expansion = compilation
        .macro_expansion
        .as_ref()
        .ok_or(Stage15TransformError::MissingMacroExpansion)?;
    if !expansion.diagnostics.is_empty() {
        return Err(Stage15TransformError::ExpansionDiagnostic);
    }
    let expanded_meaning_digest = lock
        .expanded_meaning_digest
        .as_ref()
        .ok_or(Stage15TransformError::MissingExpandedMeaningDigest)?;
    if sha256_hex(&expanded_meaning_canonical_bytes(expansion)) != *expanded_meaning_digest {
        return Err(Stage15TransformError::ExpandedMeaningDigestMismatch);
    }
    let expanded_generated_provenance_digest =
        lock.expanded_generated_provenance_digest
            .as_ref()
            .ok_or(Stage15TransformError::MissingExpandedGeneratedProvenanceDigest)?;
    if sha256_hex(&expanded_generated_provenance_canonical_bytes(expansion))
        != *expanded_generated_provenance_digest
    {
        return Err(Stage15TransformError::ExpandedGeneratedProvenanceDigestMismatch);
    }

    Ok(Stage15TransformationInput {
        semantic_document: semantic.ast.clone(),
        expanded_invocations: expansion.expanded.clone(),
        pre_expansion_digest: pre_expansion_digest.clone(),
        expanded_meaning_digest: expanded_meaning_digest.clone(),
        composition_seed: lock.composition_seed,
    })
}

/// Apply one deterministic focus overlay without changing the original typed graph.
pub fn transform_stage15(
    input: Stage15TransformationInput,
    variation: Option<Stage15Variation>,
) -> Result<Stage15TransformationResult, Stage15TransformError> {
    let composition_seed = input.composition_seed();
    let collected = collect_targets(&input)?;
    let baseline_focus = (!collected.is_empty()).then(|| select_baseline_focus(&input));
    let resolved_focus = baseline_focus.map(|baseline| {
        variation
            .map(|request| varied_focus(baseline, request))
            .unwrap_or(baseline)
    });
    let moved_axes = match (variation, baseline_focus, resolved_focus) {
        (Some(_), Some(from), Some(to)) if from != to => vec![Stage15MovedAxis {
            axis: "focus",
            from,
            to,
        }],
        _ => Vec::new(),
    };
    let effective_variation = variation.filter(|_| !moved_axes.is_empty());
    let targets = collected
        .into_iter()
        .map(|target| Stage15TargetTransformation {
            path: target.path,
            original: target.original,
            effective_focus: resolved_focus.expect("a collected target has a resolved focus"),
            provenance: target.provenance,
        })
        .collect::<Vec<_>>();
    validate_targets(&input, &targets)?;
    let effective_canonical_bytes = effective_canonical_bytes(
        &input,
        composition_seed,
        baseline_focus,
        resolved_focus,
        effective_variation,
        &targets,
    );
    let effective_canonical_digest = sha256_hex(&effective_canonical_bytes);

    Ok(Stage15TransformationResult {
        schema_id: STAGE15_TRANSFORMATION_SCHEMA_ID,
        original_semantic_document: input.semantic_document,
        original_expanded_invocations: input.expanded_invocations,
        original_pre_expansion_digest: input.pre_expansion_digest,
        original_expanded_meaning_digest: input.expanded_meaning_digest,
        composition_seed,
        baseline_focus,
        resolved_focus,
        effective_variation,
        targets,
        moved_axes,
        effective_canonical_bytes,
        effective_canonical_digest,
    })
}

#[derive(Clone)]
struct CollectedTarget {
    path: Stage15TargetPath,
    original: SemanticIdentity,
    provenance: Stage15TargetProvenance,
}

fn collect_targets(
    input: &Stage15TransformationInput,
) -> Result<Vec<CollectedTarget>, Stage15TransformError> {
    let mut targets = Vec::new();
    for (instruction_index, instruction) in input.semantic_document.instructions.iter().enumerate()
    {
        if let Some(position) = instruction
            .position
            .as_ref()
            .filter(|term| is_center(&term.identity))
        {
            targets.push(CollectedTarget {
                path: Stage15TargetPath::Instruction { instruction_index },
                original: position.identity.clone(),
                provenance: Stage15TargetProvenance::Source(position.provenance.clone()),
            });
        }
    }
    for (edge_index, edge) in input.semantic_document.group_predicates.iter().enumerate() {
        if let Some(position) = edge
            .position
            .as_ref()
            .filter(|term| is_center(&term.identity))
        {
            targets.push(CollectedTarget {
                path: Stage15TargetPath::GroupPredicate {
                    edge_index,
                    group_index: edge.group_index,
                },
                original: position.identity.clone(),
                provenance: Stage15TargetProvenance::Source(position.provenance.clone()),
            });
        }
    }
    for invocation in &input.expanded_invocations {
        collect_macro_targets(
            invocation.provenance.invocation_ordinal,
            &invocation.nodes,
            &mut targets,
        );
    }
    targets.sort_by(|left, right| left.path.cmp(&right.path));
    for pair in targets.windows(2) {
        if pair[0].path == pair[1].path {
            return Err(Stage15TransformError::DuplicateTarget(pair[0].path.clone()));
        }
    }
    Ok(targets)
}

fn collect_macro_targets(
    invocation_ordinal: u64,
    nodes: &[ExpandedMacroNode],
    targets: &mut Vec<CollectedTarget>,
) {
    for node in nodes {
        match node {
            ExpandedMacroNode::Emit {
                fields, provenance, ..
            } => {
                if let Some(ExpandedMacroValue::SemanticRef { category, id }) = fields.get("place")
                    && category == "place"
                    && id == "center"
                {
                    targets.push(CollectedTarget {
                        path: Stage15TargetPath::MacroEmit {
                            invocation_ordinal,
                            expansion_path: provenance.expansion_path.clone(),
                            generated_ordinal: provenance.generated_ordinal,
                            field: "place".to_owned(),
                        },
                        original: SemanticIdentity {
                            category: category.clone(),
                            id: id.clone(),
                        },
                        provenance: Stage15TargetProvenance::Generated(provenance.clone()),
                    });
                }
            }
            ExpandedMacroNode::Group { body, .. } | ExpandedMacroNode::Transform { body, .. } => {
                collect_macro_targets(invocation_ordinal, body, targets);
            }
            ExpandedMacroNode::Anchor { .. } | ExpandedMacroNode::Relation { .. } => {}
        }
    }
}

fn validate_targets(
    input: &Stage15TransformationInput,
    targets: &[Stage15TargetTransformation],
) -> Result<(), Stage15TransformError> {
    for target in targets {
        let mut originals = original_targets_at_path(input, &target.path);
        match originals.len() {
            0 => return Err(Stage15TransformError::MissingTarget(target.path.clone())),
            1 => {}
            _ => return Err(Stage15TransformError::DuplicateTarget(target.path.clone())),
        }
        let (identity, provenance) = originals.pop().expect("length checked");
        if identity != target.original || provenance != target.provenance || !is_center(&identity) {
            return Err(Stage15TransformError::OriginalIdentityMismatch(
                target.path.clone(),
            ));
        }
    }
    Ok(())
}

fn original_targets_at_path(
    input: &Stage15TransformationInput,
    path: &Stage15TargetPath,
) -> Vec<(SemanticIdentity, Stage15TargetProvenance)> {
    match path {
        Stage15TargetPath::Instruction { instruction_index } => input
            .semantic_document
            .instructions
            .get(*instruction_index)
            .and_then(|instruction| instruction.position.as_ref())
            .map(|term| {
                vec![(
                    term.identity.clone(),
                    Stage15TargetProvenance::Source(term.provenance.clone()),
                )]
            })
            .unwrap_or_default(),
        Stage15TargetPath::GroupPredicate {
            edge_index,
            group_index,
        } => input
            .semantic_document
            .group_predicates
            .get(*edge_index)
            .filter(|edge| edge.group_index == *group_index)
            .and_then(|edge| edge.position.as_ref())
            .map(|term| {
                vec![(
                    term.identity.clone(),
                    Stage15TargetProvenance::Source(term.provenance.clone()),
                )]
            })
            .unwrap_or_default(),
        Stage15TargetPath::MacroEmit { .. } => {
            let mut found = Vec::new();
            for invocation in &input.expanded_invocations {
                original_macro_targets_at_path(
                    invocation.provenance.invocation_ordinal,
                    &invocation.nodes,
                    path,
                    &mut found,
                );
            }
            found
        }
    }
}

fn original_macro_targets_at_path(
    invocation_ordinal: u64,
    nodes: &[ExpandedMacroNode],
    path: &Stage15TargetPath,
    found: &mut Vec<(SemanticIdentity, Stage15TargetProvenance)>,
) {
    for node in nodes {
        match node {
            ExpandedMacroNode::Emit {
                fields, provenance, ..
            } => {
                let candidate = Stage15TargetPath::MacroEmit {
                    invocation_ordinal,
                    expansion_path: provenance.expansion_path.clone(),
                    generated_ordinal: provenance.generated_ordinal,
                    field: "place".to_owned(),
                };
                if &candidate == path
                    && let Some(ExpandedMacroValue::SemanticRef { category, id }) =
                        fields.get("place")
                {
                    found.push((
                        SemanticIdentity {
                            category: category.clone(),
                            id: id.clone(),
                        },
                        Stage15TargetProvenance::Generated(provenance.clone()),
                    ));
                }
            }
            ExpandedMacroNode::Group { body, .. } | ExpandedMacroNode::Transform { body, .. } => {
                original_macro_targets_at_path(invocation_ordinal, body, path, found);
            }
            ExpandedMacroNode::Anchor { .. } | ExpandedMacroNode::Relation { .. } => {}
        }
    }
}

fn is_center(identity: &SemanticIdentity) -> bool {
    identity.category == "place" && identity.id == "center"
}

fn select_baseline_focus(input: &Stage15TransformationInput) -> FocusRegion {
    let digest = Sha256::digest(focus_hash_input(input));
    let value = u64::from_be_bytes(digest[..8].try_into().expect("SHA-256 has eight bytes"));
    let index = (value % FocusRegion::ALL.len() as u64) as usize;
    FocusRegion::ALL[index]
}

fn focus_hash_input(input: &Stage15TransformationInput) -> Vec<u8> {
    let mut bytes = STAGE15_FOCUS_SELECTION_DOMAIN.to_vec();
    append_field(&mut bytes, input.pre_expansion_digest.as_bytes());
    append_field(&mut bytes, input.expanded_meaning_digest.as_bytes());
    match input.composition_seed {
        Some(seed) => {
            append_field(&mut bytes, b"present");
            append_field(&mut bytes, &seed.to_be_bytes());
        }
        None => append_field(&mut bytes, b"absent"),
    }
    bytes
}

fn varied_focus(baseline: FocusRegion, variation: Stage15Variation) -> FocusRegion {
    let mut available = FocusRegion::ALL
        .into_iter()
        .filter(|focus| *focus != baseline)
        .collect::<Vec<_>>();
    for amplitude in Stage15VariationAmplitude::ALL {
        let offset = variation_offset(amplitude, variation.seed);
        let selected = available.remove(offset as usize % available.len());
        if amplitude == variation.amplitude {
            return selected;
        }
    }
    unreachable!("closed amplitude order contains every variation amplitude")
}

fn variation_offset(amplitude: Stage15VariationAmplitude, seed: u64) -> u64 {
    let key = format!("variation-offset:{}:{}:focus", amplitude.as_str(), seed);
    let digest = Sha256::digest(key.as_bytes());
    let hash = u64::from_be_bytes(digest[..8].try_into().expect("SHA-256 has eight bytes"));
    1 + hash % 97
}

fn effective_canonical_bytes(
    input: &Stage15TransformationInput,
    composition_seed: Option<u64>,
    baseline_focus: Option<FocusRegion>,
    resolved_focus: Option<FocusRegion>,
    effective_variation: Option<Stage15Variation>,
    targets: &[Stage15TargetTransformation],
) -> Vec<u8> {
    let mut root = BTreeMap::new();
    root.insert(
        "schema".to_owned(),
        Value::String(STAGE15_TRANSFORMATION_SCHEMA_ID.to_owned()),
    );
    root.insert(
        "original_semantic".to_owned(),
        identity_value(SEMANTIC_DOCUMENT_SCHEMA_ID, &input.pre_expansion_digest),
    );
    root.insert(
        "original_expanded".to_owned(),
        identity_value(
            EXPANDED_MACRO_MEANING_SCHEMA_ID,
            &input.expanded_meaning_digest,
        ),
    );
    root.insert(
        "composition_seed".to_owned(),
        optional_seed_value(composition_seed),
    );
    root.insert(
        "focus_selection".to_owned(),
        match (baseline_focus, resolved_focus) {
            (Some(baseline), Some(effective)) => {
                let mut selection = BTreeMap::new();
                selection.insert(
                    "domain".to_owned(),
                    Value::String(
                        std::str::from_utf8(STAGE15_FOCUS_SELECTION_DOMAIN)
                            .expect("focus domain is ASCII")
                            .to_owned(),
                    ),
                );
                selection.insert(
                    "baseline".to_owned(),
                    Value::String(baseline.as_str().to_owned()),
                );
                selection.insert(
                    "effective".to_owned(),
                    Value::String(effective.as_str().to_owned()),
                );
                Value::Object(selection.into_iter().collect())
            }
            _ => Value::Null,
        },
    );
    root.insert(
        "variation".to_owned(),
        match (effective_variation, baseline_focus, resolved_focus) {
            (Some(variation), Some(from), Some(to)) if from != to => {
                let mut record = BTreeMap::new();
                record.insert("axis".to_owned(), Value::String("focus".to_owned()));
                record.insert(
                    "amplitude".to_owned(),
                    Value::String(variation.amplitude.as_str().to_owned()),
                );
                record.insert(
                    "seed".to_owned(),
                    Value::Number(Number::from(variation.seed)),
                );
                record.insert("from".to_owned(), Value::String(from.as_str().to_owned()));
                record.insert("to".to_owned(), Value::String(to.as_str().to_owned()));
                Value::Object(record.into_iter().collect())
            }
            _ => Value::Null,
        },
    );
    root.insert(
        "targets".to_owned(),
        Value::Array(targets.iter().map(target_value).collect()),
    );
    serde_json::to_vec(&root).expect("closed Stage 1.5 values serialize")
}

fn identity_value(schema: &str, digest: &str) -> Value {
    let mut value = BTreeMap::new();
    value.insert("schema".to_owned(), Value::String(schema.to_owned()));
    value.insert("sha256".to_owned(), Value::String(digest.to_owned()));
    Value::Object(value.into_iter().collect())
}

fn optional_seed_value(seed: Option<u64>) -> Value {
    match seed {
        Some(seed) => Value::Number(Number::from(seed)),
        None => Value::Null,
    }
}

fn target_value(target: &Stage15TargetTransformation) -> Value {
    let mut value = BTreeMap::new();
    value.insert("path".to_owned(), target_path_value(&target.path));
    let mut original = BTreeMap::new();
    original.insert(
        "category".to_owned(),
        Value::String(target.original.category.clone()),
    );
    original.insert("id".to_owned(), Value::String(target.original.id.clone()));
    value.insert(
        "original".to_owned(),
        Value::Object(original.into_iter().collect()),
    );
    value.insert(
        "effective_focus".to_owned(),
        Value::String(target.effective_focus.as_str().to_owned()),
    );
    Value::Object(value.into_iter().collect())
}

fn target_path_value(path: &Stage15TargetPath) -> Value {
    let mut value = BTreeMap::new();
    match path {
        Stage15TargetPath::Instruction { instruction_index } => {
            value.insert("kind".to_owned(), Value::String("instruction".to_owned()));
            value.insert(
                "instruction_index".to_owned(),
                Value::Number(Number::from(*instruction_index as u64)),
            );
        }
        Stage15TargetPath::GroupPredicate {
            edge_index,
            group_index,
        } => {
            value.insert(
                "kind".to_owned(),
                Value::String("group_predicate".to_owned()),
            );
            value.insert(
                "edge_index".to_owned(),
                Value::Number(Number::from(*edge_index as u64)),
            );
            value.insert(
                "group_index".to_owned(),
                Value::Number(Number::from(*group_index as u64)),
            );
        }
        Stage15TargetPath::MacroEmit {
            invocation_ordinal,
            expansion_path,
            generated_ordinal,
            field,
        } => {
            value.insert("kind".to_owned(), Value::String("macro_emit".to_owned()));
            value.insert(
                "invocation_ordinal".to_owned(),
                Value::Number(Number::from(*invocation_ordinal)),
            );
            value.insert(
                "expansion_path".to_owned(),
                Value::Array(expansion_path.iter().map(path_segment_value).collect()),
            );
            value.insert(
                "generated_ordinal".to_owned(),
                Value::Number(Number::from(*generated_ordinal)),
            );
            value.insert("field".to_owned(), Value::String(field.clone()));
        }
    }
    Value::Object(value.into_iter().collect())
}

fn path_segment_value(segment: &ExpansionPathSegment) -> Value {
    let mut value = BTreeMap::new();
    match segment {
        ExpansionPathSegment::RootStatement { statement_index } => {
            value.insert(
                "kind".to_owned(),
                Value::String("root_statement".to_owned()),
            );
            value.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
        }
        ExpansionPathSegment::ComponentUse {
            statement_index,
            component_id,
        } => {
            value.insert("kind".to_owned(), Value::String("component_use".to_owned()));
            value.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
            value.insert(
                "component_id".to_owned(),
                Value::String(component_id.clone()),
            );
        }
        ExpansionPathSegment::Group { statement_index } => {
            value.insert("kind".to_owned(), Value::String("group".to_owned()));
            value.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
        }
        ExpansionPathSegment::Repeat {
            statement_index,
            iteration,
        } => {
            value.insert("kind".to_owned(), Value::String("repeat".to_owned()));
            value.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
            value.insert(
                "iteration".to_owned(),
                Value::Number(Number::from(*iteration)),
            );
        }
        ExpansionPathSegment::Transform { statement_index } => {
            value.insert("kind".to_owned(), Value::String("transform".to_owned()));
            value.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
        }
        ExpansionPathSegment::Vary {
            statement_index,
            selected_index,
        } => {
            value.insert("kind".to_owned(), Value::String("vary".to_owned()));
            value.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
            value.insert(
                "selected_index".to_owned(),
                Value::Number(Number::from(*selected_index)),
            );
        }
    }
    Value::Object(value.into_iter().collect())
}

fn append_field(bytes: &mut Vec<u8>, field: &[u8]) {
    bytes.extend_from_slice(&(field.len() as u64).to_be_bytes());
    bytes.extend_from_slice(field);
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

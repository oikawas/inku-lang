//! CanonicalReady-only verification boundary over typed DDL meaning.
//!
//! Stage 1.5 used to reinterpret `place:center` as one of six off-center focus
//! regions and let an explicit variation move that focus. Both were removed:
//! `center` is now an ordinary named region (see `geometry.rs`), and an explicit
//! variation is accepted for wire compatibility but has no axis to move. What
//! remains is the lock-verified, source-independent view the Score lowerer reads.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::{Number, Value};
use sha2::{Digest, Sha256};

use crate::execution_projection::ExecutionProjection;
use crate::{
    CompilerLockState, EXPANDED_MACRO_MEANING_SCHEMA_ID, ExpandedMacroInvocation,
    SEMANTIC_DOCUMENT_SCHEMA_ID, SemanticDocumentAst, TYPED_DDL_COMPILATION_SCHEMA_ID,
    TYPED_DDL_COMPILER_LOCK_SCHEMA_ID, TypedDdlCompilation,
    compiler_lock::{
        SemanticMacroExecutionOwners, Stage15InputBoundaryError,
        expanded_meaning_canonical_bytes_with_owners, semantic_macro_execution_owners,
        validate_stage15_input_boundary,
    },
    compiler_lock_hash_input, expanded_generated_provenance_canonical_bytes,
    semantic_document::canonical_ast_bytes,
    semantic_source_provenance_canonical_bytes,
};

/// Stable identity for the effective typed Stage 1.5 overlay.
pub const STAGE15_TRANSFORMATION_SCHEMA_ID: &str = "inku.typed-stage15-transformation.v7";
/// Closed explicit variation amplitude. Partial or unknown values cannot enter the core.
/// No axis currently moves; the request is accepted so saved and in-flight clients keep working.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
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

/// Complete, validated input owned independently from the source-bearing compilation envelope.
#[derive(Clone, Debug, PartialEq)]
pub struct Stage15TransformationInput {
    semantic_document: SemanticDocumentAst,
    expanded_invocations: Vec<ExpandedMacroInvocation>,
    pre_expansion_digest: String,
    expanded_meaning_digest: String,
    composition_seed: Option<u64>,
    geometry_policy_id: &'static str,
    geometry_policy_digest: String,
    execution_owners: SemanticMacroExecutionOwners,
    source_instruction_indices: Vec<usize>,
    source_group_indices: Vec<usize>,
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

    pub const fn geometry_policy_id(&self) -> &'static str {
        self.geometry_policy_id
    }

    pub fn geometry_policy_digest(&self) -> &str {
        &self.geometry_policy_digest
    }
}

/// Verified original typed meaning and its canonical effective identity.
#[derive(Clone, Debug, PartialEq)]
pub struct Stage15TransformationResult {
    schema_id: &'static str,
    original_semantic_document: SemanticDocumentAst,
    original_expanded_invocations: Vec<ExpandedMacroInvocation>,
    original_pre_expansion_digest: String,
    original_expanded_meaning_digest: String,
    composition_seed: Option<u64>,
    geometry_policy_id: &'static str,
    geometry_policy_digest: String,
    execution_owners: SemanticMacroExecutionOwners,
    effective_canonical_bytes: Vec<u8>,
    effective_canonical_digest: String,
    source_instruction_indices: Vec<usize>,
    source_group_indices: Vec<usize>,
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

    pub const fn geometry_policy_id(&self) -> &'static str {
        self.geometry_policy_id
    }

    pub fn geometry_policy_digest(&self) -> &str {
        &self.geometry_policy_digest
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

    pub(crate) fn original_pre_expansion_digest(self) -> &'a str {
        self.result.original_pre_expansion_digest()
    }

    pub(crate) fn original_expanded_meaning_digest(self) -> &'a str {
        self.result.original_expanded_meaning_digest()
    }

    pub(crate) fn macro_semantic_ordinal(self, source_ordinal: u64) -> Option<u64> {
        self.result
            .execution_owners
            .semantic_ordinal_for_source(source_ordinal)
    }

    pub const fn geometry_policy_id(self) -> &'static str {
        self.result.geometry_policy_id()
    }

    pub fn geometry_policy_digest(self) -> &'a str {
        self.result.geometry_policy_digest()
    }

    pub fn effective_canonical_bytes(self) -> &'a [u8] {
        self.result.effective_canonical_bytes()
    }

    pub fn effective_canonical_digest(self) -> &'a str {
        self.result.effective_canonical_digest()
    }

    pub(crate) fn source_instruction_index(self, projected_index: usize) -> Option<usize> {
        self.result
            .source_instruction_indices
            .get(projected_index)
            .copied()
    }

    pub(crate) fn source_group_index(self, projected_index: usize) -> Option<usize> {
        self.result
            .source_group_indices
            .get(projected_index)
            .copied()
    }
}

/// Closed fail-closed errors for input identity.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Stage15TransformError {
    CompilationSchema,
    MissingCompilerLock,
    CompilerLockSchema,
    CompilerState(CompilerLockState),
    CompilerLockDigestMismatch,
    GeometryPolicyMismatch,
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
    if lock.geometry_policy_id != crate::GEOMETRY_RESOLUTION_POLICY_ID
        || lock.geometry_policy_digest != crate::geometry_resolution_policy_digest()
    {
        return Err(Stage15TransformError::GeometryPolicyMismatch);
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
    let execution_owners =
        semantic_macro_execution_owners(&semantic.ast, &expansion.parameter_binding)
            .map_err(|_| Stage15TransformError::ExpansionDiagnostic)?;
    validate_stage15_input_boundary(
        &compilation.document,
        &semantic.ast,
        lock,
        &expansion.parameter_binding,
        &execution_owners,
    )
    .map_err(|error| match error {
        Stage15InputBoundaryError::VisibleSourceDigest
        | Stage15InputBoundaryError::DefinitionProjection => {
            Stage15TransformError::CompilerLockDigestMismatch
        }
        Stage15InputBoundaryError::SourceLanguage => {
            Stage15TransformError::SemanticSourceProvenanceDigestMismatch
        }
        Stage15InputBoundaryError::ConsumedDefinitionIdentity => {
            Stage15TransformError::ExpansionDiagnostic
        }
    })?;
    execution_owners
        .validate_seed_identities(
            semantic_bytes,
            expansion,
            &lock.macro_seeds,
            lock.composition_seed,
        )
        .map_err(|_| Stage15TransformError::ExpansionDiagnostic)?;
    let expanded_meaning_bytes =
        expanded_meaning_canonical_bytes_with_owners(&execution_owners, expansion)
            .map_err(|_| Stage15TransformError::ExpansionDiagnostic)?;
    if sha256_hex(&expanded_meaning_bytes) != *expanded_meaning_digest {
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
        geometry_policy_id: lock.geometry_policy_id,
        geometry_policy_digest: lock.geometry_policy_digest.clone(),
        execution_owners,
        source_instruction_indices: (0..semantic.ast.instructions.len()).collect(),
        source_group_indices: (0..semantic.ast.coordinated_head_groups.len()).collect(),
    })
}

pub(crate) fn stage15_execution_projection_input(
    projection: ExecutionProjection,
) -> Stage15TransformationInput {
    Stage15TransformationInput {
        semantic_document: projection.semantic_document,
        expanded_invocations: projection.expanded_invocations,
        pre_expansion_digest: projection.pre_expansion_digest,
        expanded_meaning_digest: projection.expanded_meaning_digest,
        composition_seed: projection.composition_seed,
        geometry_policy_id: projection.geometry_policy_id,
        geometry_policy_digest: projection.geometry_policy_digest,
        execution_owners: projection.execution_owners,
        source_instruction_indices: projection.source_instruction_indices,
        source_group_indices: projection.source_group_indices,
    }
}

/// Detach the verified view the Score lowerer reads. The original typed graph is
/// not changed. An explicit variation is accepted but moves nothing.
pub fn transform_stage15(
    input: Stage15TransformationInput,
    _variation: Option<Stage15Variation>,
) -> Result<Stage15TransformationResult, Stage15TransformError> {
    let composition_seed = input.composition_seed();
    let geometry_policy_id = input.geometry_policy_id();
    let geometry_policy_digest = input.geometry_policy_digest().to_owned();
    let effective_canonical_bytes = effective_canonical_bytes(&input, composition_seed);
    let effective_canonical_digest = sha256_hex(&effective_canonical_bytes);

    Ok(Stage15TransformationResult {
        schema_id: STAGE15_TRANSFORMATION_SCHEMA_ID,
        original_semantic_document: input.semantic_document,
        original_expanded_invocations: input.expanded_invocations,
        original_pre_expansion_digest: input.pre_expansion_digest,
        original_expanded_meaning_digest: input.expanded_meaning_digest,
        composition_seed,
        geometry_policy_id,
        geometry_policy_digest,
        execution_owners: input.execution_owners,
        effective_canonical_bytes,
        effective_canonical_digest,
        source_instruction_indices: input.source_instruction_indices,
        source_group_indices: input.source_group_indices,
    })
}

fn effective_canonical_bytes(
    input: &Stage15TransformationInput,
    composition_seed: Option<u64>,
) -> Vec<u8> {
    let mut root = BTreeMap::new();
    root.insert(
        "schema".to_owned(),
        Value::String(STAGE15_TRANSFORMATION_SCHEMA_ID.to_owned()),
    );
    root.insert(
        "geometry_policy".to_owned(),
        identity_value(input.geometry_policy_id, &input.geometry_policy_digest),
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

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

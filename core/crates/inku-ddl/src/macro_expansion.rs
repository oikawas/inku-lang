//! Bounded effect-free expansion of accepted typed macro parameter bindings.

use std::collections::{BTreeMap, BTreeSet};

use sha2::{Digest, Sha256};

use crate::{
    BoundMacroParameterValue, CompleteMacroParameterBinding, Expression, MacroDefinition,
    MacroDefinitionIdentity, MacroParameterBindingResult, MacroSeed, NumericRange, ParameterSchema,
    SemanticMap, SourceSpan, Statement, TransformExpression,
    macro_definition::canonical_semantic_ref_id,
};

/// Stable identity for the runtime-disconnected expansion overlay.
pub const MACRO_EXPANSION_SCHEMA_ID: &str = "inku.macro-expansion.v1";

/// Stable deterministic choice scheme used by `vary`.
pub const MACRO_VARY_CHOICE_SCHEME_ID: &str = "inku.macro-vary-choice.v1";

/// Caller-owned finite limits. No runtime default is provided.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct MacroExpansionLimits {
    pub max_invocations: u64,
    pub max_depth: u64,
    pub max_evaluation_steps: u64,
    pub max_nodes_per_invocation: u64,
    pub max_total_nodes: u64,
}

impl MacroExpansionLimits {
    const fn is_valid(self) -> bool {
        self.max_invocations != 0
            && self.max_depth != 0
            && self.max_evaluation_steps != 0
            && self.max_nodes_per_invocation != 0
            && self.max_total_nodes != 0
    }
}

/// A closed evaluated macro value. References to parameters and locals are impossible here.
#[derive(Clone, Debug, PartialEq)]
pub enum ExpandedMacroValue {
    Number(f64),
    Integer(i64),
    Boolean(bool),
    List(Vec<ExpandedMacroValue>),
    SemanticRef { category: String, id: String },
}

/// One typed segment of expansion identity.
#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub enum ExpansionPathSegment {
    RootStatement {
        statement_index: u64,
    },
    ComponentUse {
        statement_index: u64,
        component_id: String,
    },
    Group {
        statement_index: u64,
    },
    Repeat {
        statement_index: u64,
        iteration: u64,
    },
    Transform {
        statement_index: u64,
    },
    Vary {
        statement_index: u64,
        selected_index: u64,
    },
}

/// A collision-free target identity resolved inside one lexical expansion scope.
#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct GeneratedTargetId {
    pub invocation_ordinal: u64,
    pub expansion_path: Vec<ExpansionPathSegment>,
    pub local_name: String,
}

/// Definition and seed provenance shared by an expanded invocation and all of its nodes.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroInvocationProvenance {
    pub schema_id: &'static str,
    pub invocation_index: usize,
    pub invocation_ordinal: u64,
    pub source_span: SourceSpan,
    pub definition_qualified_name: String,
    pub definition_version: String,
    pub definition_full_digest: String,
    pub seed_scheme_id: &'static str,
    pub seed_full_digest: String,
    pub resolved_seed: u64,
    pub effective_composition_seed: u64,
}

/// Complete provenance repeated on every generated node.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GeneratedNodeProvenance {
    pub invocation: MacroInvocationProvenance,
    pub generated_ordinal: u64,
    pub expansion_path: Vec<ExpansionPathSegment>,
}

/// Evaluated transform axes. Matrix and Score transform semantics remain absent.
#[derive(Clone, Debug, PartialEq)]
pub struct ExpandedTransform {
    pub translate_x: Option<f64>,
    pub translate_y: Option<f64>,
    pub scale_x: Option<f64>,
    pub scale_y: Option<f64>,
    pub rotate_degrees: Option<f64>,
}

/// Closed semantic node set after all generic operators have been consumed.
#[derive(Clone, Debug, PartialEq)]
pub enum ExpandedMacroNode {
    Emit {
        binding: Option<GeneratedTargetId>,
        fields: BTreeMap<String, ExpandedMacroValue>,
        provenance: GeneratedNodeProvenance,
    },
    Group {
        body: Vec<ExpandedMacroNode>,
        provenance: GeneratedNodeProvenance,
    },
    Anchor {
        target: GeneratedTargetId,
        provenance: GeneratedNodeProvenance,
    },
    Relation {
        kind: String,
        from: GeneratedTargetId,
        to: GeneratedTargetId,
        provenance: GeneratedNodeProvenance,
    },
    Transform {
        transform: ExpandedTransform,
        body: Vec<ExpandedMacroNode>,
        provenance: GeneratedNodeProvenance,
    },
}

impl ExpandedMacroNode {
    pub const fn provenance(&self) -> &GeneratedNodeProvenance {
        match self {
            Self::Emit { provenance, .. }
            | Self::Group { provenance, .. }
            | Self::Anchor { provenance, .. }
            | Self::Relation { provenance, .. }
            | Self::Transform { provenance, .. } => provenance,
        }
    }
}

/// One successfully and atomically expanded complete binding.
#[derive(Clone, Debug, PartialEq)]
pub struct ExpandedMacroInvocation {
    pub provenance: MacroInvocationProvenance,
    pub nodes: Vec<ExpandedMacroNode>,
}

/// Stable failure classes. None carries localized prose or a partially generated node.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MacroExpansionDiagnosticKind {
    InvalidLimits,
    InvocationBudget,
    TotalNodeBudget,
    MissingSeed,
    DuplicateSeed,
    MismatchedSeed,
    DefinitionOwnershipMismatch,
    BindingOwnershipMismatch,
    ExpressionMismatch,
    ComponentMismatch,
    RepeatCountInvalid,
    RepeatMaximumExceeded,
    NumericRange,
    DepthBudget,
    EvaluationStepBudget,
    NodeBudget,
    TargetOwnershipMismatch,
    ProvenanceOwnershipMismatch,
}

/// One global or invocation-local stable diagnostic.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroExpansionDiagnostic {
    pub kind: MacroExpansionDiagnosticKind,
    pub invocation_index: Option<usize>,
    pub invocation_ordinal: Option<u64>,
    pub expansion_path: Vec<ExpansionPathSegment>,
}

/// The accepted I-581 result, unchanged and owned, plus the disconnected expansion overlay.
#[derive(Clone, Debug, PartialEq)]
pub struct MacroExpansionResult {
    pub parameter_binding: MacroParameterBindingResult,
    pub expanded: Vec<ExpandedMacroInvocation>,
    pub diagnostics: Vec<MacroExpansionDiagnostic>,
}

/// Expand complete I-581 bindings using only exact caller definitions, seeds, and limits.
pub fn expand_macros(
    parameter_binding: MacroParameterBindingResult,
    definitions: &[MacroDefinition],
    seeds: &[MacroSeed],
    limits: MacroExpansionLimits,
) -> MacroExpansionResult {
    let mut diagnostics = Vec::new();
    if !limits.is_valid() {
        diagnostics.push(global_diagnostic(
            MacroExpansionDiagnosticKind::InvalidLimits,
        ));
        return result(parameter_binding, Vec::new(), diagnostics);
    }

    let recognized = match u64::try_from(
        parameter_binding
            .macro_resolution
            .recognized_occurrence_count,
    ) {
        Ok(value) => value,
        Err(_) => {
            diagnostics.push(global_diagnostic(
                MacroExpansionDiagnosticKind::InvocationBudget,
            ));
            return result(parameter_binding, Vec::new(), diagnostics);
        }
    };
    if recognized > limits.max_invocations {
        diagnostics.push(global_diagnostic(
            MacroExpansionDiagnosticKind::InvocationBudget,
        ));
        return result(parameter_binding, Vec::new(), diagnostics);
    }

    let mut prepared = Vec::new();
    let mut accounted_seed_indices = BTreeSet::new();
    let mut seen_invocations = BTreeSet::new();
    let mut total_nodes = 0_u64;

    for (binding_index, binding) in parameter_binding.complete.iter().enumerate() {
        for (seed_index, seed) in seeds.iter().enumerate() {
            if seed_matches_binding(seed, binding) {
                accounted_seed_indices.insert(seed_index);
            }
        }
        if !seen_invocations.insert(binding.invocation_index) {
            diagnostics.push(invocation_diagnostic(
                MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
                binding,
                Vec::new(),
            ));
            continue;
        }
        match prepare_invocation(
            &parameter_binding,
            binding_index,
            definitions,
            seeds,
            limits,
        ) {
            Ok(item) => {
                total_nodes = match total_nodes.checked_add(item.node_count) {
                    Some(value) if value <= limits.max_total_nodes => value,
                    _ => {
                        diagnostics.push(global_diagnostic(
                            MacroExpansionDiagnosticKind::TotalNodeBudget,
                        ));
                        return result(parameter_binding, Vec::new(), diagnostics);
                    }
                };
                prepared.push(item);
            }
            Err(error) => diagnostics.push(invocation_diagnostic(error.kind, binding, error.path)),
        }
    }

    if accounted_seed_indices.len() != seeds.len() {
        diagnostics.push(global_diagnostic(
            MacroExpansionDiagnosticKind::MismatchedSeed,
        ));
        return result(parameter_binding, Vec::new(), diagnostics);
    }

    let mut expanded = Vec::with_capacity(prepared.len());
    for item in prepared {
        let binding = &parameter_binding.complete[item.binding_index];
        let resolved = &parameter_binding.macro_resolution.resolved[binding.invocation_index];
        let definition = &definitions[item.definition_index];
        let seed = &seeds[item.seed_index];
        let provenance = invocation_provenance(binding, resolved.span, &item.identity, seed);
        let environment = match root_environment(&parameter_binding, binding, definition) {
            Ok(environment) => environment,
            Err(error) => {
                diagnostics.push(invocation_diagnostic(error.kind, binding, error.path));
                continue;
            }
        };
        let mut evaluator = Evaluator::new(definition, seed, limits, provenance.clone(), true);
        match evaluator.evaluate_root(&environment) {
            Ok(nodes)
                if evaluator.nodes == item.node_count
                    && nodes.iter().all(|node| {
                        node.provenance().invocation == provenance
                            && node.provenance().generated_ordinal < item.node_count
                    }) =>
            {
                expanded.push(ExpandedMacroInvocation { provenance, nodes });
            }
            Ok(_) => diagnostics.push(invocation_diagnostic(
                MacroExpansionDiagnosticKind::ProvenanceOwnershipMismatch,
                binding,
                Vec::new(),
            )),
            Err(error) => diagnostics.push(invocation_diagnostic(error.kind, binding, error.path)),
        }
    }

    result(parameter_binding, expanded, diagnostics)
}

fn result(
    parameter_binding: MacroParameterBindingResult,
    expanded: Vec<ExpandedMacroInvocation>,
    diagnostics: Vec<MacroExpansionDiagnostic>,
) -> MacroExpansionResult {
    MacroExpansionResult {
        parameter_binding,
        expanded,
        diagnostics,
    }
}

#[derive(Clone, Debug)]
struct PreparedInvocation {
    binding_index: usize,
    definition_index: usize,
    seed_index: usize,
    node_count: u64,
    identity: MacroDefinitionIdentity,
}

fn prepare_invocation(
    parameter_binding: &MacroParameterBindingResult,
    binding_index: usize,
    definitions: &[MacroDefinition],
    seeds: &[MacroSeed],
    limits: MacroExpansionLimits,
) -> Result<PreparedInvocation, EvalError> {
    let binding = &parameter_binding.complete[binding_index];
    let resolved = parameter_binding
        .macro_resolution
        .resolved
        .get(binding.invocation_index)
        .ok_or_else(|| EvalError::new(MacroExpansionDiagnosticKind::BindingOwnershipMismatch))?;
    if resolved.invocation.ordinal() != binding.invocation_ordinal
        || resolved.clause_index != binding.clause_index
        || resolved.atom_index != binding.atom_index
        || resolved.definition_identity != binding.definition_identity
        || resolved.invocation.qualified_name() != binding.definition_identity.qualified_name()
    {
        return Err(EvalError::new(
            MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
        ));
    }
    let atom_span = parameter_binding
        .macro_resolution
        .relation_reference_evidence
        .attachment_evidence
        .noun_phrase
        .clause_stream
        .clauses
        .get(resolved.clause_index)
        .and_then(|clause| clause.atoms.get(resolved.atom_index))
        .map(|atom| atom.span());
    if atom_span != Some(resolved.span) {
        return Err(EvalError::new(
            MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
        ));
    }

    let matching_definitions = definitions
        .iter()
        .enumerate()
        .filter_map(|(index, definition)| {
            definition
                .identity()
                .ok()
                .filter(|identity| identity == &binding.definition_identity)
                .map(|identity| (index, identity))
        })
        .collect::<Vec<_>>();
    let [(definition_index, identity)] = matching_definitions.as_slice() else {
        return Err(EvalError::new(
            MacroExpansionDiagnosticKind::DefinitionOwnershipMismatch,
        ));
    };

    let matching_seed_indices = seeds
        .iter()
        .enumerate()
        .filter(|(_, seed)| seed_matches_binding(seed, binding))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    let seed_index = match matching_seed_indices.as_slice() {
        [] => {
            // A partial identity match localizes the existing invocation diagnostic only. It is
            // never ownership or consumption evidence; global accounting still requires the
            // complete pair through `seed_matches_binding`.
            let mismatched = seeds.iter().any(|seed| {
                seed.qualified_macro_name() == identity.qualified_name()
                    || seed.ordinal() == binding.invocation_ordinal
            });
            return Err(EvalError::new(if mismatched {
                MacroExpansionDiagnosticKind::MismatchedSeed
            } else {
                MacroExpansionDiagnosticKind::MissingSeed
            }));
        }
        [index] => *index,
        _ => {
            return Err(EvalError::new(MacroExpansionDiagnosticKind::DuplicateSeed));
        }
    };

    let definition = &definitions[*definition_index];
    let environment = root_environment(parameter_binding, binding, definition)?;
    let provenance = invocation_provenance(binding, resolved.span, identity, &seeds[seed_index]);
    let mut evaluator = Evaluator::new(definition, &seeds[seed_index], limits, provenance, false);
    evaluator.evaluate_root(&environment)?;

    Ok(PreparedInvocation {
        binding_index,
        definition_index: *definition_index,
        seed_index,
        node_count: evaluator.nodes,
        identity: identity.clone(),
    })
}

fn seed_matches_binding(seed: &MacroSeed, binding: &CompleteMacroParameterBinding) -> bool {
    seed.qualified_macro_name() == binding.definition_identity.qualified_name()
        && seed.ordinal() == binding.invocation_ordinal
}

fn root_environment(
    parameter_binding: &MacroParameterBindingResult,
    binding: &CompleteMacroParameterBinding,
    definition: &MacroDefinition,
) -> Result<Environment, EvalError> {
    if binding.parameters.len() != definition.parameters.len() {
        return Err(EvalError::new(
            MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
        ));
    }
    let mut parameters = BTreeMap::new();
    for parameter in &binding.parameters {
        let Some(schema) = definition.parameters.get(&parameter.parameter_name) else {
            return Err(EvalError::new(
                MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
            ));
        };
        if parameter.invocation_index != binding.invocation_index
            || parameter.invocation_ordinal != binding.invocation_ordinal
            || parameter.invocation_clause_index != binding.clause_index
            || parameter.invocation_atom_index != binding.atom_index
            || parameter.definition_identity != binding.definition_identity
            || &parameter.parameter_schema != schema
            || parameter.source_span != parameter.value.source_span()
        {
            return Err(EvalError::new(
                MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
            ));
        }
        let source_atom_span = parameter_binding
            .macro_resolution
            .relation_reference_evidence
            .attachment_evidence
            .noun_phrase
            .clause_stream
            .clauses
            .get(parameter.source_fact_clause_index)
            .and_then(|clause| clause.atoms.get(parameter.source_fact_atom_index))
            .map(|atom| atom.span());
        if source_atom_span != Some(parameter.source_span) {
            return Err(EvalError::new(
                MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
            ));
        }
        let value = bound_value(&parameter.value)?;
        let value = coerce_to_schema(value, schema)?;
        if parameters
            .insert(parameter.parameter_name.clone(), value)
            .is_some()
        {
            return Err(EvalError::new(
                MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
            ));
        }
    }
    if definition
        .parameters
        .keys()
        .any(|name| !parameters.contains_key(name))
    {
        return Err(EvalError::new(
            MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
        ));
    }
    Ok(Environment {
        parameters,
        locals: BTreeMap::new(),
    })
}

fn bound_value(value: &BoundMacroParameterValue) -> Result<ExpandedMacroValue, EvalError> {
    match value {
        BoundMacroParameterValue::Integer { value, .. } => Ok(ExpandedMacroValue::Integer(*value)),
        BoundMacroParameterValue::Number { value, .. } if value.is_finite() => {
            Ok(ExpandedMacroValue::Number(*value))
        }
        BoundMacroParameterValue::Number { .. } => {
            Err(EvalError::new(MacroExpansionDiagnosticKind::NumericRange))
        }
        BoundMacroParameterValue::SemanticRef {
            category,
            canonical_id,
            ..
        } => canonical_semantic_ref_id(category, canonical_id)
            .map(|id| ExpandedMacroValue::SemanticRef {
                category: category.clone(),
                id,
            })
            .ok_or_else(|| EvalError::new(MacroExpansionDiagnosticKind::ExpressionMismatch)),
    }
}

fn coerce_to_schema(
    value: ExpandedMacroValue,
    schema: &ParameterSchema,
) -> Result<ExpandedMacroValue, EvalError> {
    match (schema, value) {
        (ParameterSchema::Number, ExpandedMacroValue::Number(value)) if value.is_finite() => {
            Ok(ExpandedMacroValue::Number(value))
        }
        (ParameterSchema::Number, ExpandedMacroValue::Integer(value)) => {
            exact_number_from_integer(value).map(ExpandedMacroValue::Number)
        }
        (ParameterSchema::Integer, ExpandedMacroValue::Integer(value)) => {
            Ok(ExpandedMacroValue::Integer(value))
        }
        (ParameterSchema::Boolean, ExpandedMacroValue::Boolean(value)) => {
            Ok(ExpandedMacroValue::Boolean(value))
        }
        (
            ParameterSchema::SemanticRef { category },
            ExpandedMacroValue::SemanticRef {
                category: actual,
                id,
            },
        ) if category == &actual => Ok(ExpandedMacroValue::SemanticRef {
            category: actual,
            id,
        }),
        (ParameterSchema::List { length, items }, ExpandedMacroValue::List(values))
            if u64::try_from(values.len()) == Ok(*length) =>
        {
            let values = values
                .into_iter()
                .map(|value| coerce_to_schema(value, items))
                .collect::<Result<Vec<_>, _>>()?;
            Ok(ExpandedMacroValue::List(values))
        }
        _ => Err(EvalError::new(
            MacroExpansionDiagnosticKind::ExpressionMismatch,
        )),
    }
}

fn invocation_provenance(
    binding: &CompleteMacroParameterBinding,
    source_span: SourceSpan,
    identity: &MacroDefinitionIdentity,
    seed: &MacroSeed,
) -> MacroInvocationProvenance {
    MacroInvocationProvenance {
        schema_id: MACRO_EXPANSION_SCHEMA_ID,
        invocation_index: binding.invocation_index,
        invocation_ordinal: binding.invocation_ordinal,
        source_span,
        definition_qualified_name: identity.qualified_name().to_owned(),
        definition_version: identity.version().to_owned(),
        definition_full_digest: identity.full_digest_hex().to_owned(),
        seed_scheme_id: seed.scheme_id(),
        seed_full_digest: seed.full_digest_hex().to_owned(),
        resolved_seed: seed.resolved_seed(),
        effective_composition_seed: seed.effective_composition_seed(),
    }
}

fn global_diagnostic(kind: MacroExpansionDiagnosticKind) -> MacroExpansionDiagnostic {
    MacroExpansionDiagnostic {
        kind,
        invocation_index: None,
        invocation_ordinal: None,
        expansion_path: Vec::new(),
    }
}

fn invocation_diagnostic(
    kind: MacroExpansionDiagnosticKind,
    binding: &CompleteMacroParameterBinding,
    expansion_path: Vec<ExpansionPathSegment>,
) -> MacroExpansionDiagnostic {
    MacroExpansionDiagnostic {
        kind,
        invocation_index: Some(binding.invocation_index),
        invocation_ordinal: Some(binding.invocation_ordinal),
        expansion_path,
    }
}

#[derive(Clone, Debug)]
struct EvalError {
    kind: MacroExpansionDiagnosticKind,
    path: Vec<ExpansionPathSegment>,
}

impl EvalError {
    fn new(kind: MacroExpansionDiagnosticKind) -> Self {
        Self {
            kind,
            path: Vec::new(),
        }
    }

    fn at(mut self, path: &[ExpansionPathSegment]) -> Self {
        self.path = path.to_vec();
        self
    }
}

#[derive(Clone, Debug)]
struct Environment {
    parameters: BTreeMap<String, ExpandedMacroValue>,
    locals: BTreeMap<String, ExpandedMacroValue>,
}

#[derive(Clone, Debug)]
enum BodyPathContext {
    Root,
    Component { component_id: String },
    Group,
    Repeat { iteration: u64 },
    Transform,
    Vary { selected_index: u64 },
}

impl BodyPathContext {
    fn segment(&self, statement_index: u64) -> ExpansionPathSegment {
        match self {
            Self::Root => ExpansionPathSegment::RootStatement { statement_index },
            Self::Component { component_id } => ExpansionPathSegment::ComponentUse {
                statement_index,
                component_id: component_id.clone(),
            },
            Self::Group => ExpansionPathSegment::Group { statement_index },
            Self::Repeat { iteration } => ExpansionPathSegment::Repeat {
                statement_index,
                iteration: *iteration,
            },
            Self::Transform => ExpansionPathSegment::Transform { statement_index },
            Self::Vary { selected_index } => ExpansionPathSegment::Vary {
                statement_index,
                selected_index: *selected_index,
            },
        }
    }
}

struct Evaluator<'a> {
    definition: &'a MacroDefinition,
    seed: &'a MacroSeed,
    limits: MacroExpansionLimits,
    provenance: MacroInvocationProvenance,
    materialize: bool,
    steps: u64,
    nodes: u64,
}

impl<'a> Evaluator<'a> {
    fn new(
        definition: &'a MacroDefinition,
        seed: &'a MacroSeed,
        limits: MacroExpansionLimits,
        provenance: MacroInvocationProvenance,
        materialize: bool,
    ) -> Self {
        Self {
            definition,
            seed,
            limits,
            provenance,
            materialize,
            steps: 0,
            nodes: 0,
        }
    }

    fn evaluate_root(
        &mut self,
        environment: &Environment,
    ) -> Result<Vec<ExpandedMacroNode>, EvalError> {
        self.evaluate_body(
            &self.definition.body,
            environment,
            &BTreeMap::new(),
            0,
            &[],
            &BodyPathContext::Root,
        )
    }

    fn evaluate_body(
        &mut self,
        body: &[Statement],
        environment: &Environment,
        inherited_targets: &BTreeMap<String, GeneratedTargetId>,
        depth: u64,
        path_prefix: &[ExpansionPathSegment],
        path_context: &BodyPathContext,
    ) -> Result<Vec<ExpandedMacroNode>, EvalError> {
        if depth > self.limits.max_depth {
            return Err(EvalError::new(MacroExpansionDiagnosticKind::DepthBudget).at(path_prefix));
        }
        let mut targets = inherited_targets.clone();
        for (index, statement) in body.iter().enumerate() {
            let statement_index = u64::try_from(index).map_err(|_| {
                EvalError::new(MacroExpansionDiagnosticKind::NumericRange).at(path_prefix)
            })?;
            let mut path = path_prefix.to_vec();
            path.push(path_context.segment(statement_index));
            let declaration = match statement {
                Statement::Emit {
                    binding: Some(name),
                    ..
                }
                | Statement::Anchor { name } => Some(name),
                _ => None,
            };
            if let Some(name) = declaration {
                let target = GeneratedTargetId {
                    invocation_ordinal: self.provenance.invocation_ordinal,
                    expansion_path: path,
                    local_name: name.clone(),
                };
                if targets.insert(name.clone(), target).is_some() {
                    return Err(EvalError::new(
                        MacroExpansionDiagnosticKind::TargetOwnershipMismatch,
                    )
                    .at(path_prefix));
                }
            }
        }

        let mut output = Vec::new();
        for (index, statement) in body.iter().enumerate() {
            let statement_index = u64::try_from(index).map_err(|_| {
                EvalError::new(MacroExpansionDiagnosticKind::NumericRange).at(path_prefix)
            })?;
            let mut path = path_prefix.to_vec();
            path.push(path_context.segment(statement_index));
            output.extend(self.evaluate_statement(
                statement,
                environment,
                &targets,
                depth,
                &path,
            )?);
        }
        Ok(output)
    }

    fn evaluate_statement(
        &mut self,
        statement: &Statement,
        environment: &Environment,
        targets: &BTreeMap<String, GeneratedTargetId>,
        depth: u64,
        path: &[ExpansionPathSegment],
    ) -> Result<Vec<ExpandedMacroNode>, EvalError> {
        self.bump_step(path)?;
        match statement {
            Statement::Emit { binding, fields } => {
                let fields = self.evaluate_fields(fields, environment, path)?;
                let binding = binding
                    .as_ref()
                    .map(|name| self.target(targets, name, path))
                    .transpose()?;
                let ordinal = self.bump_node(path)?;
                if self.materialize {
                    Ok(vec![ExpandedMacroNode::Emit {
                        binding,
                        fields,
                        provenance: self.node_provenance(ordinal, path),
                    }])
                } else {
                    Ok(Vec::new())
                }
            }
            Statement::Use {
                component,
                arguments,
            } => {
                self.bump_step(path)?;
                let component_definition =
                    self.definition.components.get(component).ok_or_else(|| {
                        EvalError::new(MacroExpansionDiagnosticKind::ComponentMismatch).at(path)
                    })?;
                if arguments.len() != component_definition.parameters.len() {
                    return Err(
                        EvalError::new(MacroExpansionDiagnosticKind::ComponentMismatch).at(path),
                    );
                }
                let mut parameters = BTreeMap::new();
                for (name, schema) in component_definition.parameters.iter() {
                    let expression = arguments.get(name).ok_or_else(|| {
                        EvalError::new(MacroExpansionDiagnosticKind::ComponentMismatch).at(path)
                    })?;
                    let value = self.evaluate_expression(expression, environment, path)?;
                    let value = coerce_to_schema(value, schema).map_err(|error| error.at(path))?;
                    parameters.insert(name.clone(), value);
                }
                if arguments
                    .keys()
                    .any(|name| component_definition.parameters.get(name).is_none())
                {
                    return Err(
                        EvalError::new(MacroExpansionDiagnosticKind::ComponentMismatch).at(path),
                    );
                }
                let child_environment = Environment {
                    parameters,
                    locals: BTreeMap::new(),
                };
                let child_depth = self.child_depth(depth, path)?;
                self.evaluate_body(
                    &component_definition.body,
                    &child_environment,
                    targets,
                    child_depth,
                    path,
                    &BodyPathContext::Component {
                        component_id: component.clone(),
                    },
                )
            }
            Statement::Group { body } => {
                let ordinal = self.bump_node(path)?;
                let child_depth = self.child_depth(depth, path)?;
                let child_nodes = self.evaluate_body(
                    body,
                    environment,
                    targets,
                    child_depth,
                    path,
                    &BodyPathContext::Group,
                )?;
                if self.materialize {
                    Ok(vec![ExpandedMacroNode::Group {
                        body: child_nodes,
                        provenance: self.node_provenance(ordinal, path),
                    }])
                } else {
                    Ok(Vec::new())
                }
            }
            Statement::Anchor { name } => {
                let target = self.target(targets, name, path)?;
                let ordinal = self.bump_node(path)?;
                if self.materialize {
                    Ok(vec![ExpandedMacroNode::Anchor {
                        target,
                        provenance: self.node_provenance(ordinal, path),
                    }])
                } else {
                    Ok(Vec::new())
                }
            }
            Statement::Relation { kind, from, to } => {
                let from = self.target(targets, from, path)?;
                let to = self.target(targets, to, path)?;
                let ordinal = self.bump_node(path)?;
                if self.materialize {
                    Ok(vec![ExpandedMacroNode::Relation {
                        kind: kind.clone(),
                        from,
                        to,
                        provenance: self.node_provenance(ordinal, path),
                    }])
                } else {
                    Ok(Vec::new())
                }
            }
            Statement::Repeat {
                count,
                maximum,
                index,
                body,
            } => {
                let value = self.evaluate_expression(count, environment, path)?;
                let ExpandedMacroValue::Integer(count) = value else {
                    return Err(
                        EvalError::new(MacroExpansionDiagnosticKind::RepeatCountInvalid).at(path),
                    );
                };
                if count <= 0 {
                    return Err(
                        EvalError::new(MacroExpansionDiagnosticKind::RepeatCountInvalid).at(path),
                    );
                }
                let count = u64::try_from(count).map_err(|_| {
                    EvalError::new(MacroExpansionDiagnosticKind::RepeatCountInvalid).at(path)
                })?;
                if count > *maximum {
                    return Err(EvalError::new(
                        MacroExpansionDiagnosticKind::RepeatMaximumExceeded,
                    )
                    .at(path));
                }
                let child_depth = self.child_depth(depth, path)?;
                let mut output = Vec::new();
                for iteration in 0..count {
                    self.bump_step(path)?;
                    let mut child_environment = environment.clone();
                    child_environment.locals.insert(
                        index.clone(),
                        ExpandedMacroValue::Integer(i64::try_from(iteration).map_err(|_| {
                            EvalError::new(MacroExpansionDiagnosticKind::NumericRange).at(path)
                        })?),
                    );
                    output.extend(self.evaluate_body(
                        body,
                        &child_environment,
                        targets,
                        child_depth,
                        path,
                        &BodyPathContext::Repeat { iteration },
                    )?);
                }
                Ok(output)
            }
            Statement::Transform { transform, body } => {
                let transform = self.evaluate_transform(transform, environment, path)?;
                let ordinal = self.bump_node(path)?;
                let child_depth = self.child_depth(depth, path)?;
                let child_nodes = self.evaluate_body(
                    body,
                    environment,
                    targets,
                    child_depth,
                    path,
                    &BodyPathContext::Transform,
                )?;
                if self.materialize {
                    Ok(vec![ExpandedMacroNode::Transform {
                        transform,
                        body: child_nodes,
                        provenance: self.node_provenance(ordinal, path),
                    }])
                } else {
                    Ok(Vec::new())
                }
            }
            Statement::Vary {
                binding,
                domain,
                choices,
                range,
                body,
            } => {
                self.bump_step(path)?;
                let (selected_index, selected_value) = match (choices, range) {
                    (Some(choices), None) if !choices.is_empty() => {
                        let count = u64::try_from(choices.len()).map_err(|_| {
                            EvalError::new(MacroExpansionDiagnosticKind::NumericRange).at(path)
                        })?;
                        let selected = self.vary_index(path, domain, count)?;
                        let index = usize::try_from(selected).map_err(|_| {
                            EvalError::new(MacroExpansionDiagnosticKind::NumericRange).at(path)
                        })?;
                        let value = self.evaluate_expression(&choices[index], environment, path)?;
                        (selected, value)
                    }
                    (None, Some(range)) => {
                        let count = numeric_range_count(range).map_err(|error| error.at(path))?;
                        let selected = self.vary_index(path, domain, count)?;
                        let value = range.start + (selected as f64) * range.step;
                        if !value.is_finite() || value > range.end {
                            return Err(
                                EvalError::new(MacroExpansionDiagnosticKind::NumericRange).at(path)
                            );
                        }
                        (selected, ExpandedMacroValue::Number(value))
                    }
                    _ => {
                        return Err(EvalError::new(
                            MacroExpansionDiagnosticKind::ExpressionMismatch,
                        )
                        .at(path));
                    }
                };
                let mut child_environment = environment.clone();
                child_environment
                    .locals
                    .insert(binding.clone(), selected_value);
                let child_depth = self.child_depth(depth, path)?;
                self.evaluate_body(
                    body,
                    &child_environment,
                    targets,
                    child_depth,
                    path,
                    &BodyPathContext::Vary { selected_index },
                )
            }
        }
    }

    fn evaluate_fields(
        &mut self,
        fields: &SemanticMap<Expression>,
        environment: &Environment,
        path: &[ExpansionPathSegment],
    ) -> Result<BTreeMap<String, ExpandedMacroValue>, EvalError> {
        fields
            .iter()
            .map(|(name, expression)| {
                self.evaluate_expression(expression, environment, path)
                    .map(|value| (name.clone(), value))
            })
            .collect()
    }

    fn evaluate_expression(
        &mut self,
        expression: &Expression,
        environment: &Environment,
        path: &[ExpansionPathSegment],
    ) -> Result<ExpandedMacroValue, EvalError> {
        self.bump_step(path)?;
        match expression {
            Expression::Number { value } if value.is_finite() => {
                Ok(ExpandedMacroValue::Number(*value))
            }
            Expression::Number { .. } => {
                Err(EvalError::new(MacroExpansionDiagnosticKind::NumericRange).at(path))
            }
            Expression::Integer { value } => Ok(ExpandedMacroValue::Integer(*value)),
            Expression::Boolean { value } => Ok(ExpandedMacroValue::Boolean(*value)),
            Expression::List { items } => items
                .iter()
                .map(|item| self.evaluate_expression(item, environment, path))
                .collect::<Result<Vec<_>, _>>()
                .map(ExpandedMacroValue::List),
            Expression::Parameter { name } => {
                environment.parameters.get(name).cloned().ok_or_else(|| {
                    EvalError::new(MacroExpansionDiagnosticKind::ExpressionMismatch).at(path)
                })
            }
            Expression::Local { name } => environment.locals.get(name).cloned().ok_or_else(|| {
                EvalError::new(MacroExpansionDiagnosticKind::ExpressionMismatch).at(path)
            }),
            Expression::SemanticRef { category, id } => canonical_semantic_ref_id(category, id)
                .map(|id| ExpandedMacroValue::SemanticRef {
                    category: category.clone(),
                    id,
                })
                .ok_or_else(|| {
                    EvalError::new(MacroExpansionDiagnosticKind::ExpressionMismatch).at(path)
                }),
        }
    }

    fn evaluate_transform(
        &mut self,
        transform: &TransformExpression,
        environment: &Environment,
        path: &[ExpansionPathSegment],
    ) -> Result<ExpandedTransform, EvalError> {
        Ok(ExpandedTransform {
            translate_x: self.numeric_axis(&transform.translate_x, environment, path)?,
            translate_y: self.numeric_axis(&transform.translate_y, environment, path)?,
            scale_x: self.numeric_axis(&transform.scale_x, environment, path)?,
            scale_y: self.numeric_axis(&transform.scale_y, environment, path)?,
            rotate_degrees: self.numeric_axis(&transform.rotate_degrees, environment, path)?,
        })
    }

    fn numeric_axis(
        &mut self,
        expression: &Option<Expression>,
        environment: &Environment,
        path: &[ExpansionPathSegment],
    ) -> Result<Option<f64>, EvalError> {
        let Some(expression) = expression else {
            return Ok(None);
        };
        let value = self.evaluate_expression(expression, environment, path)?;
        match value {
            ExpandedMacroValue::Number(value) if value.is_finite() => Ok(Some(value)),
            ExpandedMacroValue::Integer(value) => exact_number_from_integer(value)
                .map(Some)
                .map_err(|error| error.at(path)),
            _ => Err(EvalError::new(MacroExpansionDiagnosticKind::ExpressionMismatch).at(path)),
        }
    }

    fn target(
        &self,
        targets: &BTreeMap<String, GeneratedTargetId>,
        name: &str,
        path: &[ExpansionPathSegment],
    ) -> Result<GeneratedTargetId, EvalError> {
        targets.get(name).cloned().ok_or_else(|| {
            EvalError::new(MacroExpansionDiagnosticKind::TargetOwnershipMismatch).at(path)
        })
    }

    fn vary_index(
        &self,
        path: &[ExpansionPathSegment],
        domain: &str,
        candidate_count: u64,
    ) -> Result<u64, EvalError> {
        if candidate_count == 0 {
            return Err(EvalError::new(MacroExpansionDiagnosticKind::NumericRange).at(path));
        }
        let digest = Sha256::digest(macro_vary_choice_hash_input(self.seed, path, domain));
        let prefix = u64::from_be_bytes(digest[..8].try_into().expect("SHA-256 prefix"));
        Ok(prefix % candidate_count)
    }

    fn child_depth(&self, depth: u64, path: &[ExpansionPathSegment]) -> Result<u64, EvalError> {
        let child = depth
            .checked_add(1)
            .ok_or_else(|| EvalError::new(MacroExpansionDiagnosticKind::DepthBudget).at(path))?;
        if child > self.limits.max_depth {
            return Err(EvalError::new(MacroExpansionDiagnosticKind::DepthBudget).at(path));
        }
        Ok(child)
    }

    fn bump_step(&mut self, path: &[ExpansionPathSegment]) -> Result<(), EvalError> {
        self.steps = self.steps.checked_add(1).ok_or_else(|| {
            EvalError::new(MacroExpansionDiagnosticKind::EvaluationStepBudget).at(path)
        })?;
        if self.steps > self.limits.max_evaluation_steps {
            return Err(
                EvalError::new(MacroExpansionDiagnosticKind::EvaluationStepBudget).at(path),
            );
        }
        Ok(())
    }

    fn bump_node(&mut self, path: &[ExpansionPathSegment]) -> Result<u64, EvalError> {
        let ordinal = self.nodes;
        self.nodes = self
            .nodes
            .checked_add(1)
            .ok_or_else(|| EvalError::new(MacroExpansionDiagnosticKind::NodeBudget).at(path))?;
        if self.nodes > self.limits.max_nodes_per_invocation {
            return Err(EvalError::new(MacroExpansionDiagnosticKind::NodeBudget).at(path));
        }
        Ok(ordinal)
    }

    fn node_provenance(
        &self,
        generated_ordinal: u64,
        expansion_path: &[ExpansionPathSegment],
    ) -> GeneratedNodeProvenance {
        GeneratedNodeProvenance {
            invocation: self.provenance.clone(),
            generated_ordinal,
            expansion_path: expansion_path.to_vec(),
        }
    }
}

fn numeric_range_count(range: &NumericRange) -> Result<u64, EvalError> {
    if !range.start.is_finite()
        || !range.end.is_finite()
        || !range.step.is_finite()
        || range.step <= 0.0
        || range.end < range.start
    {
        return Err(EvalError::new(MacroExpansionDiagnosticKind::NumericRange));
    }
    let quotient = ((range.end - range.start) / range.step).floor();
    if !quotient.is_finite() || quotient < 0.0 || quotient >= u64::MAX as f64 {
        return Err(EvalError::new(MacroExpansionDiagnosticKind::NumericRange));
    }
    let intervals = quotient as u64;
    intervals
        .checked_add(1)
        .ok_or_else(|| EvalError::new(MacroExpansionDiagnosticKind::NumericRange))
}

fn exact_number_from_integer(value: i64) -> Result<f64, EvalError> {
    let number = value as f64;
    if number.is_finite() && (number as i128) == i128::from(value) {
        Ok(number)
    } else {
        Err(EvalError::new(MacroExpansionDiagnosticKind::NumericRange))
    }
}

/// Canonical bytes for a typed path. Tags follow the public enum declaration order from zero.
pub fn typed_expansion_path_bytes(path: &[ExpansionPathSegment]) -> Vec<u8> {
    let mut bytes = Vec::new();
    for segment in path {
        match segment {
            ExpansionPathSegment::RootStatement { statement_index } => {
                bytes.push(0);
                bytes.extend_from_slice(&statement_index.to_be_bytes());
            }
            ExpansionPathSegment::ComponentUse {
                statement_index,
                component_id,
            } => {
                bytes.push(1);
                bytes.extend_from_slice(&statement_index.to_be_bytes());
                append_length_prefixed(&mut bytes, component_id.as_bytes());
            }
            ExpansionPathSegment::Group { statement_index } => {
                bytes.push(2);
                bytes.extend_from_slice(&statement_index.to_be_bytes());
            }
            ExpansionPathSegment::Repeat {
                statement_index,
                iteration,
            } => {
                bytes.push(3);
                bytes.extend_from_slice(&statement_index.to_be_bytes());
                bytes.extend_from_slice(&iteration.to_be_bytes());
            }
            ExpansionPathSegment::Transform { statement_index } => {
                bytes.push(4);
                bytes.extend_from_slice(&statement_index.to_be_bytes());
            }
            ExpansionPathSegment::Vary {
                statement_index,
                selected_index,
            } => {
                bytes.push(5);
                bytes.extend_from_slice(&statement_index.to_be_bytes());
                bytes.extend_from_slice(&selected_index.to_be_bytes());
            }
        }
    }
    bytes
}

/// Exact four-field framing hashed by the deterministic vary choice scheme.
pub fn macro_vary_choice_hash_input(
    seed: &MacroSeed,
    path: &[ExpansionPathSegment],
    domain: &str,
) -> Vec<u8> {
    let path_bytes = typed_expansion_path_bytes(path);
    let mut bytes = Vec::new();
    append_length_prefixed(&mut bytes, MACRO_VARY_CHOICE_SCHEME_ID.as_bytes());
    append_length_prefixed(&mut bytes, seed.full_digest_bytes());
    append_length_prefixed(&mut bytes, &path_bytes);
    append_length_prefixed(&mut bytes, domain.as_bytes());
    bytes
}

fn append_length_prefixed(output: &mut Vec<u8>, value: &[u8]) {
    output.extend_from_slice(&(value.len() as u64).to_be_bytes());
    output.extend_from_slice(value);
}

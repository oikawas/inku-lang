//! Runtime-disconnected generic macro definition language and semantic identity.

use std::{
    collections::{BTreeMap, BTreeSet, HashMap, HashSet},
    fmt,
};

use serde::{
    Deserialize, Deserializer, Serialize,
    de::{Error as _, MapAccess, Visitor},
};
use sha2::{Digest, Sha256};

use crate::{MacroInvocation, saijiki_asset};

/// Exact schema and digest domain for this semantic definition edition.
pub const MACRO_DEFINITION_SCHEMA_ID: &str = "inku.macro-definition.v1";

/// Domain bytes prepended to the length-framed canonical semantic JSON.
pub const MACRO_DEFINITION_DIGEST_DOMAIN: &[u8] = b"inku.macro-definition.v1";

/// Stable warning attached to every legacy per-macro outcome.
pub const LEGACY_PLUGIN_FORMAT_WARNING: &str = "legacy_plugin_format";

const SEMANTIC_CATEGORIES: [(&str, &str); 11] = [
    ("shape", "katachi"),
    ("angle", "katamuki"),
    ("touch", "tezawari"),
    ("continuity", "tsuranari"),
    ("surface", "omote"),
    ("ground", "ji"),
    ("color", "iro"),
    ("variation", "yuragi"),
    ("place", "basho"),
    ("movement", "ugoki"),
    ("ratio", "wariai"),
];

/// A bytewise-key-ordered semantic map that rejects duplicate JSON members.
#[derive(Clone, Debug, Default, PartialEq, Serialize)]
#[serde(transparent)]
pub struct SemanticMap<T>(BTreeMap<String, T>);

impl<T> SemanticMap<T> {
    pub fn new(values: BTreeMap<String, T>) -> Self {
        Self(values)
    }

    pub fn get(&self, key: &str) -> Option<&T> {
        self.0.get(key)
    }

    pub fn iter(&self) -> impl Iterator<Item = (&String, &T)> {
        self.0.iter()
    }

    pub fn keys(&self) -> impl Iterator<Item = &String> {
        self.0.keys()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }
}

impl<T> From<BTreeMap<String, T>> for SemanticMap<T> {
    fn from(values: BTreeMap<String, T>) -> Self {
        Self::new(values)
    }
}

impl<'de, T> Deserialize<'de> for SemanticMap<T>
where
    T: Deserialize<'de>,
{
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct SemanticMapVisitor<T>(std::marker::PhantomData<T>);

        impl<'de, T> Visitor<'de> for SemanticMapVisitor<T>
        where
            T: Deserialize<'de>,
        {
            type Value = SemanticMap<T>;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("a semantic object with unique member names")
            }

            fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
            where
                A: MapAccess<'de>,
            {
                let mut values = BTreeMap::new();
                while let Some((key, value)) = map.next_entry::<String, T>()? {
                    if values.insert(key.clone(), value).is_some() {
                        return Err(A::Error::custom(format!("duplicate key `{key}`")));
                    }
                }
                Ok(SemanticMap(values))
            }
        }

        deserializer.deserialize_map(SemanticMapVisitor(std::marker::PhantomData))
    }
}

/// A closed parameter type; strings and arbitrary JSON objects are deliberately absent.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum ParameterSchema {
    Number,
    Integer,
    Boolean,
    List {
        length: u64,
        items: Box<ParameterSchema>,
    },
    SemanticRef {
        category: String,
    },
}

/// A closed, data-only expression language.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "expr", rename_all = "snake_case", deny_unknown_fields)]
pub enum Expression {
    Number { value: f64 },
    Integer { value: i64 },
    Boolean { value: bool },
    List { items: Vec<Expression> },
    Parameter { name: String },
    Local { name: String },
    SemanticRef { category: String, id: String },
}

/// A finite numeric choice domain for deterministic `vary`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NumericRange {
    pub start: f64,
    pub end: f64,
    pub step: f64,
}

/// Typed transform axes; raw SVG transform text has no representation.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TransformExpression {
    pub translate_x: Option<Expression>,
    pub translate_y: Option<Expression>,
    pub scale_x: Option<Expression>,
    pub scale_y: Option<Expression>,
    pub rotate_degrees: Option<Expression>,
}

/// The exact generic statement set. `component` exists only as a top-level definition.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Statement {
    Emit {
        binding: Option<String>,
        fields: SemanticMap<Expression>,
    },
    Use {
        component: String,
        arguments: SemanticMap<Expression>,
    },
    Group {
        body: Vec<Statement>,
    },
    Anchor {
        name: String,
    },
    Relation {
        kind: String,
        from: String,
        to: String,
    },
    Repeat {
        count: Expression,
        maximum: u64,
        index: String,
        body: Vec<Statement>,
    },
    Transform {
        transform: TransformExpression,
        body: Vec<Statement>,
    },
    Vary {
        binding: String,
        domain: String,
        choices: Option<Vec<Expression>>,
        range: Option<NumericRange>,
        body: Vec<Statement>,
    },
}

/// One local component and its local parameter schema.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ComponentDefinition {
    pub parameters: SemanticMap<ParameterSchema>,
    pub body: Vec<Statement>,
}

/// One invocable, versioned semantic macro definition.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MacroDefinition {
    pub schema: String,
    pub namespace: String,
    pub heading: String,
    pub version: String,
    pub parameters: SemanticMap<ParameterSchema>,
    pub components: SemanticMap<ComponentDefinition>,
    pub body: Vec<Statement>,
}

/// Stable typed-input parse failure. Localized prose never enters semantic identity.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroDefinitionParseError {
    code: &'static str,
    line: usize,
    column: usize,
    detail: String,
}

impl MacroDefinitionParseError {
    pub const fn code(&self) -> &'static str {
        self.code
    }

    pub const fn path(&self) -> &'static str {
        "$"
    }

    pub const fn line(&self) -> usize {
        self.line
    }

    pub const fn column(&self) -> usize {
        self.column
    }
}

impl fmt::Display for MacroDefinitionParseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{} at {}:{}: {}",
            self.code, self.line, self.column, self.detail
        )
    }
}

impl std::error::Error for MacroDefinitionParseError {}

/// One stable validation finding and its definition-local JSON path.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct MacroDefinitionDiagnostic {
    code: &'static str,
    path: String,
}

impl MacroDefinitionDiagnostic {
    pub const fn code(&self) -> &'static str {
        self.code
    }

    pub fn path(&self) -> &str {
        &self.path
    }
}

/// Collectable structural validation result and finite symbolic emission bound.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroDefinitionValidation {
    diagnostics: Vec<MacroDefinitionDiagnostic>,
    symbolic_upper_bound: Option<u64>,
}

impl MacroDefinitionValidation {
    pub fn diagnostics(&self) -> &[MacroDefinitionDiagnostic] {
        &self.diagnostics
    }

    pub const fn symbolic_upper_bound(&self) -> Option<u64> {
        self.symbolic_upper_bound
    }

    pub fn is_valid(&self) -> bool {
        self.diagnostics.is_empty() && self.symbolic_upper_bound.is_some()
    }

    pub fn has_code(&self, code: &str) -> bool {
        self.diagnostics
            .iter()
            .any(|diagnostic| diagnostic.code == code)
    }
}

/// Immutable semantic identity, keeping name, version, and full digest separate.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroDefinitionIdentity {
    qualified_name: String,
    version: String,
    canonical_json: Vec<u8>,
    full_digest: [u8; 32],
    full_digest_hex: String,
}

impl MacroDefinitionIdentity {
    pub fn qualified_name(&self) -> &str {
        &self.qualified_name
    }

    pub fn version(&self) -> &str {
        &self.version
    }

    pub fn canonical_json_bytes(&self) -> &[u8] {
        &self.canonical_json
    }

    pub const fn full_digest_bytes(&self) -> &[u8; 32] {
        &self.full_digest
    }

    pub fn full_digest_hex(&self) -> &str {
        &self.full_digest_hex
    }
}

/// A stable nonfatal warning returned at the future legacy adapter boundary.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct LegacyWarning {
    code: &'static str,
}

impl LegacyWarning {
    pub const fn code(&self) -> &'static str {
        self.code
    }
}

/// Per-macro legacy outcome; omission never escalates to a package/request failure here.
#[derive(Clone, Debug, PartialEq)]
pub enum LegacyImportOutcome {
    Imported {
        definition: MacroDefinition,
        warnings: Vec<LegacyWarning>,
    },
    Omitted {
        qualified_name: String,
        reason: String,
        warnings: Vec<LegacyWarning>,
    },
}

impl LegacyImportOutcome {
    pub fn imported(definition: MacroDefinition) -> Result<Self, MacroDefinitionValidation> {
        if let Err(validation) = definition.identity() {
            return Err(validation);
        }
        Ok(Self::Imported {
            definition,
            warnings: legacy_warnings(),
        })
    }

    pub fn omitted(qualified_name: impl Into<String>, reason: impl Into<String>) -> Self {
        Self::Omitted {
            qualified_name: qualified_name.into(),
            reason: reason.into(),
            warnings: legacy_warnings(),
        }
    }

    pub fn warnings(&self) -> &[LegacyWarning] {
        match self {
            Self::Imported { warnings, .. } | Self::Omitted { warnings, .. } => warnings,
        }
    }
}

impl MacroDefinition {
    /// Parse without normalizing keys, names, Unicode, or semantic values.
    pub fn from_json(input: &str) -> Result<Self, MacroDefinitionParseError> {
        serde_json::from_str(input).map_err(|error| {
            let detail = error.to_string();
            let code = if detail.contains("unknown variant") {
                "unknown_operator"
            } else if detail.contains("unknown field") {
                "unknown_json_field"
            } else if detail.contains("duplicate field") || detail.contains("duplicate key") {
                "duplicate_id"
            } else {
                "invalid_json"
            };
            MacroDefinitionParseError {
                code,
                line: error.line(),
                column: error.column(),
                detail,
            }
        })
    }

    /// The exact I-533 non-normalizing qualified name policy.
    pub fn qualified_name(&self) -> Option<String> {
        MacroInvocation::new(self.namespace.clone(), self.heading.clone(), 0)
            .ok()
            .map(|invocation| invocation.qualified_name())
    }

    /// Validate names, references, cycles, finite domains, and symbolic resource bounds.
    pub fn validate(&self) -> MacroDefinitionValidation {
        let mut diagnostics = Vec::new();
        if self.schema != MACRO_DEFINITION_SCHEMA_ID {
            push_diagnostic(&mut diagnostics, "unknown_schema", "$.schema");
        }
        match MacroInvocation::new(self.namespace.clone(), self.heading.clone(), 0) {
            Ok(_) => {}
            Err(error) => push_diagnostic(
                &mut diagnostics,
                error.kind(),
                if error.kind() == "invalid_namespace" {
                    "$.namespace"
                } else {
                    "$.heading"
                },
            ),
        }
        if !is_semantic_version(&self.version) {
            push_diagnostic(&mut diagnostics, "invalid_semantic_version", "$.version");
        }

        validate_parameter_map(&self.parameters, "$.parameters", &mut diagnostics);
        for (component_id, component) in self.components.iter() {
            let component_path = format!("$.components.{component_id}");
            if !is_ascii_identifier(component_id) {
                push_diagnostic(
                    &mut diagnostics,
                    "invalid_component_id",
                    format!("{component_path}.id"),
                );
            }
            validate_parameter_map(
                &component.parameters,
                &format!("{component_path}.parameters"),
                &mut diagnostics,
            );
        }

        let component_edges = component_edges(self);
        validate_component_cycles(&component_edges, &mut diagnostics);

        let root_parameters = parameter_types(&self.parameters);
        let mut root_locals = BTreeMap::new();
        let mut root_local_ids = HashSet::new();
        validate_body(
            &self.body,
            "$.body",
            &root_parameters,
            &mut root_locals,
            &mut root_local_ids,
            &HashSet::new(),
            self,
            &mut diagnostics,
        );
        for (component_id, component) in self.components.iter() {
            let mut locals = BTreeMap::new();
            let mut local_ids = HashSet::new();
            validate_body(
                &component.body,
                &format!("$.components.{component_id}.body"),
                &parameter_types(&component.parameters),
                &mut locals,
                &mut local_ids,
                &HashSet::new(),
                self,
                &mut diagnostics,
            );
        }

        let mut symbolic_upper_bound = None;
        if !diagnostics.iter().any(|diagnostic| {
            matches!(
                diagnostic.code,
                "component_cycle" | "undefined_component" | "external_component_reference"
            )
        }) {
            let mut memo = HashMap::new();
            let mut visiting = HashSet::new();
            for component in self.components.keys() {
                let _ =
                    component_bound(component, self, &mut memo, &mut visiting, &mut diagnostics);
            }
            if !diagnostics
                .iter()
                .any(|diagnostic| diagnostic.code == "resource_bound_overflow")
            {
                symbolic_upper_bound = bound_body(
                    &self.body,
                    "$.body",
                    self,
                    &mut memo,
                    &mut visiting,
                    &mut diagnostics,
                );
            }
        }
        if !diagnostics.is_empty() {
            symbolic_upper_bound = None;
        }
        MacroDefinitionValidation {
            diagnostics,
            symbolic_upper_bound,
        }
    }

    /// Compact UTF-8 semantic JSON after typed validation, with no terminal LF.
    pub fn canonical_json_bytes(&self) -> Result<Vec<u8>, MacroDefinitionValidation> {
        let validation = self.validate();
        if !validation.is_valid() {
            return Err(validation);
        }
        Ok(serde_json::to_vec(self).expect("validated MacroDefinition must serialize"))
    }

    /// Domain-separated full SHA-256 semantic identity.
    pub fn identity(&self) -> Result<MacroDefinitionIdentity, MacroDefinitionValidation> {
        let canonical_json = self.canonical_json_bytes()?;
        let mut framed =
            Vec::with_capacity(MACRO_DEFINITION_DIGEST_DOMAIN.len() + 8 + canonical_json.len());
        framed.extend_from_slice(MACRO_DEFINITION_DIGEST_DOMAIN);
        framed.extend_from_slice(&(canonical_json.len() as u64).to_be_bytes());
        framed.extend_from_slice(&canonical_json);
        let full_digest: [u8; 32] = Sha256::digest(framed).into();
        let full_digest_hex = full_digest
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        Ok(MacroDefinitionIdentity {
            qualified_name: self
                .qualified_name()
                .expect("validated definition must have a qualified name"),
            version: self.version.clone(),
            canonical_json,
            full_digest,
            full_digest_hex,
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum ValueKind {
    Number,
    Integer,
    Boolean,
    List,
    SemanticRef(String),
    Unknown,
}

fn legacy_warnings() -> Vec<LegacyWarning> {
    vec![LegacyWarning {
        code: LEGACY_PLUGIN_FORMAT_WARNING,
    }]
}

fn push_diagnostic(
    diagnostics: &mut Vec<MacroDefinitionDiagnostic>,
    code: &'static str,
    path: impl Into<String>,
) {
    diagnostics.push(MacroDefinitionDiagnostic {
        code,
        path: path.into(),
    });
}

fn validate_parameter_map(
    parameters: &SemanticMap<ParameterSchema>,
    path: &str,
    diagnostics: &mut Vec<MacroDefinitionDiagnostic>,
) {
    for (name, schema) in parameters.iter() {
        let parameter_path = format!("{path}.{name}");
        if !is_ascii_identifier(name) {
            push_diagnostic(diagnostics, "invalid_parameter_id", &parameter_path);
        }
        validate_parameter_schema(schema, &parameter_path, diagnostics);
    }
}

fn validate_parameter_schema(
    schema: &ParameterSchema,
    path: &str,
    diagnostics: &mut Vec<MacroDefinitionDiagnostic>,
) {
    match schema {
        ParameterSchema::List { items, .. } => {
            validate_parameter_schema(items, &format!("{path}.items"), diagnostics);
        }
        ParameterSchema::SemanticRef { category } => {
            if semantic_asset_key(category).is_none() && category != "relation" {
                push_diagnostic(diagnostics, "unknown_semantic_category", path);
            }
        }
        ParameterSchema::Number | ParameterSchema::Integer | ParameterSchema::Boolean => {}
    }
}

fn parameter_types(parameters: &SemanticMap<ParameterSchema>) -> BTreeMap<String, ValueKind> {
    parameters
        .iter()
        .map(|(name, schema)| (name.clone(), parameter_kind(schema)))
        .collect()
}

fn parameter_kind(schema: &ParameterSchema) -> ValueKind {
    match schema {
        ParameterSchema::Number => ValueKind::Number,
        ParameterSchema::Integer => ValueKind::Integer,
        ParameterSchema::Boolean => ValueKind::Boolean,
        ParameterSchema::List { .. } => ValueKind::List,
        ParameterSchema::SemanticRef { category } => ValueKind::SemanticRef(category.clone()),
    }
}

#[allow(clippy::too_many_arguments)]
fn validate_body(
    body: &[Statement],
    path: &str,
    parameters: &BTreeMap<String, ValueKind>,
    locals: &mut BTreeMap<String, ValueKind>,
    used_local_ids: &mut HashSet<String>,
    inherited_targets: &HashSet<String>,
    definition: &MacroDefinition,
    diagnostics: &mut Vec<MacroDefinitionDiagnostic>,
) {
    let mut targets = inherited_targets.clone();
    for (index, statement) in body.iter().enumerate() {
        let statement_path = format!("{path}[{index}]");
        let declared = match statement {
            Statement::Anchor { name } => Some((name, format!("{statement_path}.name"))),
            Statement::Emit {
                binding: Some(binding),
                ..
            } => Some((binding, format!("{statement_path}.binding"))),
            _ => None,
        };
        if let Some((name, declaration_path)) = declared {
            if !is_ascii_identifier(name) {
                push_diagnostic(
                    diagnostics,
                    "invalid_anchor_or_binding_id",
                    declaration_path,
                );
            } else if !targets.insert(name.clone()) {
                push_diagnostic(diagnostics, "duplicate_anchor_or_binding", declaration_path);
            }
        }
    }

    for (index, statement) in body.iter().enumerate() {
        let statement_path = format!("{path}[{index}]");
        match statement {
            Statement::Emit { fields, .. } => {
                for (field, expression) in fields.iter() {
                    let expression_path = format!("{statement_path}.fields.{field}");
                    if semantic_asset_key(field).is_none() {
                        push_diagnostic(diagnostics, "unknown_semantic_field", &expression_path);
                    }
                    let kind = validate_expression(
                        expression,
                        &expression_path,
                        parameters,
                        locals,
                        diagnostics,
                    );
                    match kind {
                        Some(ValueKind::SemanticRef(category)) if category == *field => {}
                        Some(ValueKind::Unknown) | None => {}
                        _ => push_diagnostic(
                            diagnostics,
                            "semantic_field_requires_matching_reference",
                            &expression_path,
                        ),
                    }
                }
            }
            Statement::Use {
                component,
                arguments,
            } => {
                if !is_ascii_identifier(component) {
                    push_diagnostic(
                        diagnostics,
                        "external_component_reference",
                        format!("{statement_path}.component"),
                    );
                } else if let Some(component_definition) = definition.components.get(component) {
                    for (argument, expression) in arguments.iter() {
                        let argument_path = format!("{statement_path}.arguments.{argument}");
                        let actual = validate_expression(
                            expression,
                            &argument_path,
                            parameters,
                            locals,
                            diagnostics,
                        );
                        match component_definition.parameters.get(argument) {
                            Some(expected) => {
                                if let Some(actual) = actual
                                    && !kinds_compatible(&parameter_kind(expected), &actual)
                                {
                                    push_diagnostic(
                                        diagnostics,
                                        "argument_type_mismatch",
                                        &argument_path,
                                    );
                                }
                            }
                            None => {
                                push_diagnostic(diagnostics, "unknown_argument", &argument_path)
                            }
                        }
                    }
                    for required in component_definition.parameters.keys() {
                        if arguments.get(required).is_none() {
                            push_diagnostic(
                                diagnostics,
                                "missing_argument",
                                format!("{statement_path}.arguments.{required}"),
                            );
                        }
                    }
                } else {
                    push_diagnostic(
                        diagnostics,
                        "undefined_component",
                        format!("{statement_path}.component"),
                    );
                    for (argument, expression) in arguments.iter() {
                        validate_expression(
                            expression,
                            &format!("{statement_path}.arguments.{argument}"),
                            parameters,
                            locals,
                            diagnostics,
                        );
                    }
                }
            }
            Statement::Group { body } => validate_body(
                body,
                &format!("{statement_path}.body"),
                parameters,
                &mut locals.clone(),
                used_local_ids,
                &targets,
                definition,
                diagnostics,
            ),
            Statement::Anchor { .. } => {}
            Statement::Relation { kind, from, to } => {
                if !known_relation(kind) {
                    push_diagnostic(
                        diagnostics,
                        "unknown_semantic_id",
                        format!("{statement_path}.kind"),
                    );
                }
                for (field, target) in [("from", from), ("to", to)] {
                    if !targets.contains(target) {
                        push_diagnostic(
                            diagnostics,
                            "undefined_anchor",
                            format!("{statement_path}.{field}"),
                        );
                    }
                }
            }
            Statement::Repeat {
                count,
                maximum,
                index,
                body,
            } => {
                let count_kind = validate_expression(
                    count,
                    &format!("{statement_path}.count"),
                    parameters,
                    locals,
                    diagnostics,
                );
                if !matches!(
                    count_kind,
                    Some(ValueKind::Integer) | Some(ValueKind::Unknown)
                ) {
                    push_diagnostic(
                        diagnostics,
                        "invalid_repeat_count",
                        format!("{statement_path}.count"),
                    );
                }
                if let Expression::Integer { value } = count
                    && (*value <= 0 || (*value as u64) > *maximum)
                {
                    push_diagnostic(
                        diagnostics,
                        "invalid_repeat_count",
                        format!("{statement_path}.count"),
                    );
                }
                if *maximum == 0 {
                    push_diagnostic(
                        diagnostics,
                        "unbounded_repeat",
                        format!("{statement_path}.maximum"),
                    );
                }
                let binding_path = format!("{statement_path}.index");
                if !is_ascii_identifier(index) {
                    push_diagnostic(diagnostics, "invalid_local_binding_id", &binding_path);
                } else if !used_local_ids.insert(index.clone()) {
                    push_diagnostic(diagnostics, "duplicate_local_binding", &binding_path);
                }
                let mut child_locals = locals.clone();
                child_locals.insert(index.clone(), ValueKind::Integer);
                validate_body(
                    body,
                    &format!("{statement_path}.body"),
                    parameters,
                    &mut child_locals,
                    used_local_ids,
                    &targets,
                    definition,
                    diagnostics,
                );
            }
            Statement::Transform { transform, body } => {
                let axes = [
                    ("translate_x", &transform.translate_x),
                    ("translate_y", &transform.translate_y),
                    ("scale_x", &transform.scale_x),
                    ("scale_y", &transform.scale_y),
                    ("rotate_degrees", &transform.rotate_degrees),
                ];
                if axes.iter().all(|(_, value)| value.is_none()) {
                    push_diagnostic(
                        diagnostics,
                        "empty_transform",
                        format!("{statement_path}.transform"),
                    );
                }
                for (axis, expression) in axes {
                    if let Some(expression) = expression {
                        let kind = validate_expression(
                            expression,
                            &format!("{statement_path}.transform.{axis}"),
                            parameters,
                            locals,
                            diagnostics,
                        );
                        if !matches!(
                            kind,
                            Some(ValueKind::Number)
                                | Some(ValueKind::Integer)
                                | Some(ValueKind::Unknown)
                        ) {
                            push_diagnostic(
                                diagnostics,
                                "transform_requires_number",
                                format!("{statement_path}.transform.{axis}"),
                            );
                        }
                    }
                }
                validate_body(
                    body,
                    &format!("{statement_path}.body"),
                    parameters,
                    &mut locals.clone(),
                    used_local_ids,
                    &targets,
                    definition,
                    diagnostics,
                );
            }
            Statement::Vary {
                binding,
                domain,
                choices,
                range,
                body,
            } => {
                if !is_ascii_identifier(binding) {
                    push_diagnostic(
                        diagnostics,
                        "invalid_local_binding_id",
                        format!("{statement_path}.binding"),
                    );
                } else if !used_local_ids.insert(binding.clone()) {
                    push_diagnostic(
                        diagnostics,
                        "duplicate_local_binding",
                        format!("{statement_path}.binding"),
                    );
                }
                if !is_ascii_identifier(domain) {
                    push_diagnostic(
                        diagnostics,
                        "invalid_vary_domain",
                        format!("{statement_path}.domain"),
                    );
                }
                let binding_kind = match (choices, range) {
                    (Some(choices), None) => {
                        if choices.is_empty() {
                            push_diagnostic(
                                diagnostics,
                                "empty_vary",
                                format!("{statement_path}.choices"),
                            );
                            ValueKind::Unknown
                        } else {
                            let mut choice_kind = None;
                            for (choice_index, choice) in choices.iter().enumerate() {
                                let kind = validate_expression(
                                    choice,
                                    &format!("{statement_path}.choices[{choice_index}]"),
                                    parameters,
                                    locals,
                                    diagnostics,
                                );
                                if let Some(kind) = kind {
                                    if let Some(first) = &choice_kind
                                        && !kinds_compatible(first, &kind)
                                    {
                                        push_diagnostic(
                                            diagnostics,
                                            "vary_choice_type_mismatch",
                                            format!("{statement_path}.choices[{choice_index}]"),
                                        );
                                    }
                                    choice_kind.get_or_insert(kind);
                                }
                            }
                            choice_kind.unwrap_or(ValueKind::Unknown)
                        }
                    }
                    (None, Some(range)) => {
                        if !range.start.is_finite()
                            || !range.end.is_finite()
                            || !range.step.is_finite()
                            || range.step <= 0.0
                            || range.end < range.start
                            || ((range.end - range.start) / range.step).floor() > u64::MAX as f64
                        {
                            push_diagnostic(
                                diagnostics,
                                "invalid_vary_range",
                                format!("{statement_path}.range"),
                            );
                        }
                        ValueKind::Number
                    }
                    _ => {
                        push_diagnostic(diagnostics, "invalid_vary_source", &statement_path);
                        ValueKind::Unknown
                    }
                };
                let mut child_locals = locals.clone();
                child_locals.insert(binding.clone(), binding_kind);
                validate_body(
                    body,
                    &format!("{statement_path}.body"),
                    parameters,
                    &mut child_locals,
                    used_local_ids,
                    &targets,
                    definition,
                    diagnostics,
                );
            }
        }
    }
}

fn validate_expression(
    expression: &Expression,
    path: &str,
    parameters: &BTreeMap<String, ValueKind>,
    locals: &BTreeMap<String, ValueKind>,
    diagnostics: &mut Vec<MacroDefinitionDiagnostic>,
) -> Option<ValueKind> {
    match expression {
        Expression::Number { value } => {
            if !value.is_finite() {
                push_diagnostic(diagnostics, "non_finite_number", path);
            }
            Some(ValueKind::Number)
        }
        Expression::Integer { .. } => Some(ValueKind::Integer),
        Expression::Boolean { .. } => Some(ValueKind::Boolean),
        Expression::List { items } => {
            for (index, item) in items.iter().enumerate() {
                validate_expression(
                    item,
                    &format!("{path}.items[{index}]"),
                    parameters,
                    locals,
                    diagnostics,
                );
            }
            Some(ValueKind::List)
        }
        Expression::Parameter { name } => {
            if !is_ascii_identifier(name) {
                push_diagnostic(diagnostics, "invalid_parameter_id", path);
                return None;
            }
            match parameters.get(name) {
                Some(kind) => Some(kind.clone()),
                None => {
                    push_diagnostic(diagnostics, "undefined_parameter", path);
                    None
                }
            }
        }
        Expression::Local { name } => {
            if !is_ascii_identifier(name) {
                push_diagnostic(diagnostics, "invalid_local_binding_id", path);
                return None;
            }
            match locals.get(name) {
                Some(kind) => Some(kind.clone()),
                None => {
                    push_diagnostic(diagnostics, "undefined_local", path);
                    None
                }
            }
        }
        Expression::SemanticRef { category, id } => {
            if semantic_asset_key(category).is_none() && category != "relation" {
                push_diagnostic(diagnostics, "unknown_semantic_category", path);
            } else if !known_semantic_id(category, id) {
                push_diagnostic(diagnostics, "unknown_semantic_id", path);
            }
            Some(ValueKind::SemanticRef(category.clone()))
        }
    }
}

fn kinds_compatible(expected: &ValueKind, actual: &ValueKind) -> bool {
    expected == actual
        || matches!((expected, actual), (ValueKind::Number, ValueKind::Integer))
        || matches!(actual, ValueKind::Unknown)
}

fn component_edges(definition: &MacroDefinition) -> BTreeMap<String, Vec<String>> {
    definition
        .components
        .iter()
        .map(|(name, component)| {
            let mut uses = Vec::new();
            collect_component_uses(&component.body, &mut uses);
            (name.clone(), uses)
        })
        .collect()
}

fn collect_component_uses(body: &[Statement], uses: &mut Vec<String>) {
    for statement in body {
        match statement {
            Statement::Use { component, .. } => uses.push(component.clone()),
            Statement::Group { body }
            | Statement::Repeat { body, .. }
            | Statement::Transform { body, .. }
            | Statement::Vary { body, .. } => collect_component_uses(body, uses),
            Statement::Emit { .. } | Statement::Anchor { .. } | Statement::Relation { .. } => {}
        }
    }
}

fn validate_component_cycles(
    edges: &BTreeMap<String, Vec<String>>,
    diagnostics: &mut Vec<MacroDefinitionDiagnostic>,
) {
    let mut state = HashMap::<String, u8>::new();
    let mut reported = BTreeSet::new();
    for component in edges.keys() {
        visit_component(component, edges, &mut state, &mut reported, diagnostics);
    }
}

fn visit_component(
    component: &str,
    edges: &BTreeMap<String, Vec<String>>,
    state: &mut HashMap<String, u8>,
    reported: &mut BTreeSet<String>,
    diagnostics: &mut Vec<MacroDefinitionDiagnostic>,
) {
    match state.get(component) {
        Some(2) => return,
        Some(1) => {
            if reported.insert(component.to_owned()) {
                push_diagnostic(
                    diagnostics,
                    "component_cycle",
                    format!("$.components.{component}"),
                );
            }
            return;
        }
        _ => {}
    }
    state.insert(component.to_owned(), 1);
    if let Some(targets) = edges.get(component) {
        for target in targets {
            if edges.contains_key(target) {
                visit_component(target, edges, state, reported, diagnostics);
            }
        }
    }
    state.insert(component.to_owned(), 2);
}

fn bound_body(
    body: &[Statement],
    path: &str,
    definition: &MacroDefinition,
    memo: &mut HashMap<String, u64>,
    visiting: &mut HashSet<String>,
    diagnostics: &mut Vec<MacroDefinitionDiagnostic>,
) -> Option<u64> {
    let mut total = 0_u64;
    for (index, statement) in body.iter().enumerate() {
        let statement_path = format!("{path}[{index}]");
        let value = match statement {
            Statement::Emit { .. } => Some(1),
            Statement::Use { component, .. } => {
                component_bound(component, definition, memo, visiting, diagnostics)
            }
            Statement::Group { body }
            | Statement::Transform { body, .. }
            | Statement::Vary { body, .. } => bound_body(
                body,
                &format!("{statement_path}.body"),
                definition,
                memo,
                visiting,
                diagnostics,
            ),
            Statement::Repeat { maximum, body, .. } => bound_body(
                body,
                &format!("{statement_path}.body"),
                definition,
                memo,
                visiting,
                diagnostics,
            )
            .and_then(|body_bound| body_bound.checked_mul(*maximum)),
            Statement::Anchor { .. } | Statement::Relation { .. } => Some(0),
        };
        let Some(value) = value else {
            push_diagnostic(diagnostics, "resource_bound_overflow", &statement_path);
            return None;
        };
        let Some(next) = total.checked_add(value) else {
            push_diagnostic(diagnostics, "resource_bound_overflow", &statement_path);
            return None;
        };
        total = next;
    }
    Some(total)
}

fn component_bound(
    component: &str,
    definition: &MacroDefinition,
    memo: &mut HashMap<String, u64>,
    visiting: &mut HashSet<String>,
    diagnostics: &mut Vec<MacroDefinitionDiagnostic>,
) -> Option<u64> {
    if let Some(value) = memo.get(component) {
        return Some(*value);
    }
    if !visiting.insert(component.to_owned()) {
        return None;
    }
    let definition_body = definition.components.get(component)?;
    let value = bound_body(
        &definition_body.body,
        &format!("$.components.{component}.body"),
        definition,
        memo,
        visiting,
        diagnostics,
    );
    visiting.remove(component);
    let value = value?;
    memo.insert(component.to_owned(), value);
    Some(value)
}

fn semantic_asset_key(category: &str) -> Option<&'static str> {
    SEMANTIC_CATEGORIES
        .iter()
        .find_map(|(known, asset)| (*known == category).then_some(*asset))
}

fn known_relation(value: &str) -> bool {
    saijiki_asset()
        .relations
        .iter()
        .any(|relation| relation.relation_type == value)
}

fn known_semantic_id(category: &str, id: &str) -> bool {
    if category == "relation" {
        return known_relation(id);
    }
    let Some(asset_key) = semantic_asset_key(category) else {
        return false;
    };
    saijiki_asset()
        .categories
        .iter()
        .find(|candidate| candidate.key == asset_key)
        .is_some_and(|candidate| {
            candidate.words.iter().any(|word| {
                word.score_value.as_deref() == Some(id)
                    || word.surface_en.as_deref().map(canonical_wire_id).as_deref() == Some(id)
            })
        })
}

fn canonical_wire_id(value: &str) -> String {
    value
        .bytes()
        .map(|byte| match byte {
            b'-' | b' ' => '_',
            _ => byte as char,
        })
        .collect()
}

fn is_ascii_identifier(value: &str) -> bool {
    let mut characters = value.bytes();
    matches!(characters.next(), Some(first) if first.is_ascii_alphabetic())
        && characters
            .all(|character| character.is_ascii_alphanumeric() || matches!(character, b'_' | b'-'))
}

/// Validate a semantic version with the exact grammar used by [`MacroDefinition`].
///
/// This public wrapper lets document locks reuse the definition identity grammar
/// without copying or widening it.
pub fn validate_macro_definition_semantic_version(value: &str) -> bool {
    is_semantic_version(value)
}

fn is_semantic_version(value: &str) -> bool {
    if value.is_empty() || !value.is_ascii() {
        return false;
    }
    let (without_build, build) = match value.split_once('+') {
        Some((left, right)) if !right.contains('+') => (left, Some(right)),
        Some(_) => return false,
        None => (value, None),
    };
    let (core, prerelease) = match without_build.split_once('-') {
        Some((left, right)) => (left, Some(right)),
        None => (without_build, None),
    };
    let core_parts = core.split('.').collect::<Vec<_>>();
    if core_parts.len() != 3 || !core_parts.iter().all(|part| valid_numeric_identifier(part)) {
        return false;
    }
    if !core_parts.iter().all(|part| part.parse::<u64>().is_ok()) {
        return false;
    }
    prerelease.is_none_or(|part| valid_dot_identifiers(part, true))
        && build.is_none_or(|part| valid_dot_identifiers(part, false))
}

fn valid_dot_identifiers(value: &str, reject_numeric_leading_zero: bool) -> bool {
    !value.is_empty()
        && value.split('.').all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
                && (!reject_numeric_leading_zero
                    || !part.bytes().all(|byte| byte.is_ascii_digit())
                    || valid_numeric_identifier(part))
        })
}

fn valid_numeric_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.bytes().all(|byte| byte.is_ascii_digit())
        && (value == "0" || !value.starts_with('0'))
}

//! Compile one or many declared-DDL requests from JSON stdin into serializable Score results.
//!
//! ```sh
//! scripts/rust-toolchain.sh run -p inku-ddl --example compile-score --locked --offline <<'JSON'
//! [{"source":"place one red circle at center.","language":"en","canvas":"square"}]
//! JSON
//! ```
//!
//! Each request accepts `source`, `language`, optional `canvas`, optional
//! `composition_seed`, optional `error_policy`, optional raw macro `definitions`,
//! and optional `macro_locks` (`qualified_name`, `version`, `digest`). A single
//! request object is accepted for convenience; the output is always an array.

use std::io::{self, Read};

use inku_ddl::{
    CompilerExecutionDiagnostic, MacroDefinition, MacroExpansionLimits, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreDiagnosticOwner, ScoreErrorPolicy,
    ScoreLoweringContext, ScoreLoweringDiagnostic, compile_ddl_to_score,
};
use inku_score::Color;
use serde::{Deserialize, Serialize};
use serde_json::Value;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1_000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

#[derive(Deserialize)]
#[serde(untagged)]
enum RequestEnvelope {
    One(Request),
    Many(Vec<Request>),
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    source: String,
    language: ResolvedInstructionLanguage,
    #[serde(default = "default_canvas")]
    canvas: String,
    #[serde(default)]
    composition_seed: u64,
    #[serde(default)]
    error_policy: ScoreErrorPolicy,
    #[serde(default)]
    definitions: Vec<Value>,
    #[serde(default)]
    macro_locks: Vec<MacroLockRequest>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MacroLockRequest {
    qualified_name: String,
    version: String,
    digest: String,
}

#[derive(Serialize)]
struct Response {
    original_source: String,
    outcome: String,
    score: Option<Value>,
    diagnostics: Vec<Diagnostic>,
    definition_identities: Vec<DefinitionIdentity>,
}

#[derive(Serialize)]
struct Diagnostic {
    channel: &'static str,
    reason: String,
    disposition: String,
    source_spans: Vec<Span>,
}

#[derive(Serialize)]
struct DefinitionIdentity {
    qualified_name: String,
    version: String,
    digest: String,
}

#[derive(Serialize)]
struct Span {
    start_byte: usize,
    end_byte: usize,
}

fn default_canvas() -> String {
    "square".to_owned()
}

fn main() -> Result<(), String> {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|error| format!("read stdin: {error}"))?;
    let requests = match serde_json::from_str::<RequestEnvelope>(&input)
        .map_err(|error| format!("parse request JSON: {error}"))?
    {
        RequestEnvelope::One(request) => vec![request],
        RequestEnvelope::Many(requests) => requests,
    };
    let responses = requests
        .into_iter()
        .map(compile)
        .collect::<Result<Vec<_>, _>>()?;
    serde_json::to_writer_pretty(io::stdout(), &responses)
        .map_err(|error| format!("write response JSON: {error}"))?;
    println!();
    Ok(())
}

fn compile(request: Request) -> Result<Response, String> {
    let definitions = request
        .definitions
        .iter()
        .map(|definition| {
            MacroDefinition::from_json(&definition.to_string())
                .map_err(|error| format!("parse macro definition: {error}"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let definition_identities = definitions
        .iter()
        .map(|definition| {
            let identity = definition
                .identity()
                .map_err(|error| format!("identify macro definition: {error:?}"))?;
            Ok(DefinitionIdentity {
                qualified_name: identity.qualified_name().to_owned(),
                version: identity.version().to_owned(),
                digest: format!("sha256:{}", identity.full_digest_hex()),
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    let macro_locks = request
        .macro_locks
        .into_iter()
        .map(|lock| {
            MacroLock::new(lock.qualified_name, lock.version, lock.digest)
                .map_err(|error| format!("parse macro lock: {error}"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let document =
        NormalizedDdlDocument::new(request.source.clone(), request.language, macro_locks)
            .map_err(|error| format!("construct normalized DDL document: {error}"))?;
    let context = ScoreLoweringContext::resolve(&request.canvas, Color::White)
        .map_err(|error| format!("resolve canvas: {error:?}"))?;
    let execution = compile_ddl_to_score(
        document,
        &definitions,
        Some(request.composition_seed),
        LIMITS,
        context,
        None,
        request.error_policy,
    );
    let mut diagnostics = execution
        .upstream_diagnostics()
        .iter()
        .map(upstream_diagnostic)
        .collect::<Vec<_>>();
    diagnostics.extend(
        execution
            .downstream_diagnostics()
            .iter()
            .map(downstream_diagnostic),
    );
    Ok(Response {
        original_source: request.source,
        outcome: format!("{:?}", execution.outcome()),
        score: execution
            .score()
            .map(serde_json::to_value)
            .transpose()
            .map_err(|error| format!("serialize score: {error}"))?,
        diagnostics,
        definition_identities,
    })
}

fn upstream_diagnostic(diagnostic: &CompilerExecutionDiagnostic) -> Diagnostic {
    Diagnostic {
        channel: "upstream",
        reason: format!("{:?}", diagnostic.reason),
        disposition: format!("{:?}", diagnostic.disposition),
        source_spans: diagnostic.span.iter().copied().map(span).collect(),
    }
}

fn downstream_diagnostic(diagnostic: &ScoreLoweringDiagnostic) -> Diagnostic {
    Diagnostic {
        channel: "downstream",
        reason: format!("{:?}", diagnostic.reason),
        disposition: format!("{:?}", diagnostic.disposition),
        source_spans: diagnostic_owner_spans(&diagnostic.owner),
    }
}

fn diagnostic_owner_spans(owner: &ScoreDiagnosticOwner) -> Vec<Span> {
    let spans = match owner {
        ScoreDiagnosticOwner::SourceInstruction { spans, .. }
        | ScoreDiagnosticOwner::MacroInvocation { spans, .. }
        | ScoreDiagnosticOwner::GeneratedNode { spans, .. }
        | ScoreDiagnosticOwner::Ground { spans }
        | ScoreDiagnosticOwner::CoordinatedGroup { spans, .. } => spans,
    };
    spans.iter().copied().map(span).collect()
}

fn span(span: inku_ddl::SourceSpan) -> Span {
    Span {
        start_byte: span.start_byte,
        end_byte: span.end_byte,
    }
}

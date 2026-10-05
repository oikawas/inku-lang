//! Thin byte facades for the existing checked compile-once/render boundary.

use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_pipeline::core_boundary::{ClipPolicy, CompiledDelivery, CompilerOptions};
use inku_pipeline::machine::{PipelineRenderOptions, VisibleDocument};
use serde::Deserialize;

const MAX_INPUT_BYTES: usize = 16 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CompileInput {
    document: VisibleDocument,
    definitions: Vec<inku_ddl::MacroDefinition>,
    compiler: CompilerOptions,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RenderInput {
    delivery: CompiledDelivery,
    options: PipelineRenderOptions,
    compiler: CompilerOptions,
    clip: ClipPolicy,
}

fn refusal(code: &str, message: &str) -> Vec<u8> {
    serde_json::to_vec(&serde_json::json!({ "error": code, "message": message }))
        .expect("two strings serialize")
}

fn owned_call(operation: impl FnOnce() -> Result<Vec<u8>, Vec<u8>>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(operation))
        .unwrap_or_else(|_| Err(refusal("internal_invariant", "the core panicked")))
        .unwrap_or_else(|error| error)
}

fn parse<T: serde::de::DeserializeOwned>(bytes: &[u8], code: &str) -> Result<T, Vec<u8>> {
    if bytes.len() > MAX_INPUT_BYTES {
        return Err(refusal(code, "input is larger than 16 MiB"));
    }
    serde_json::from_slice(bytes).map_err(|error| refusal(code, &error.to_string()))
}

/// Compile a current VisibleDocument without changing source or choosing authority.
#[uniffi::export]
pub fn compile_document(input_bytes: Vec<u8>) -> Vec<u8> {
    owned_call(|| {
        let input: CompileInput = parse(&input_bytes, "invalid_compile_input")?;
        let document = input.document.document().map_err(|error| {
            let code = serde_json::to_value(error).expect("protocol error serializes");
            refusal(
                code.as_str().expect("protocol error is a string"),
                &format!("{error:?}"),
            )
        })?;
        let delivery = inku_pipeline::core_boundary::compile_committed(
            document,
            &input.definitions,
            &input.compiler,
        )
        .map_err(|error| refusal("compile_refused", &error.to_string()))?;
        serde_json::to_vec(&delivery)
            .map_err(|error| refusal("invalid_compiled_delivery", &error.to_string()))
    })
}

/// Draw only a validated delivery with its independently supplied matching options.
#[uniffi::export]
pub fn render_compiled(input_bytes: Vec<u8>) -> Vec<u8> {
    owned_call(|| {
        let input: RenderInput = parse(&input_bytes, "invalid_render_input")?;
        let output = inku_pipeline::core_boundary::render_delivery(
            &input.delivery,
            input.options.into(),
            &input.compiler,
            input.clip,
        )
        .map_err(|error| refusal(super::saved_render_error_code(&error), &error.to_string()))?;
        serde_json::to_vec(&output)
            .map_err(|error| refusal("invalid_render_output", &error.to_string()))
    })
}

//! The API root used when joining provider-specific versioned paths.

pub(crate) fn api_root<'a>(kind: &str, base: &'a str) -> &'a str {
    let base = base.trim_end_matches('/');
    match kind {
        "anthropic" => base.strip_suffix("/v1").unwrap_or(base),
        "gemini" => base
            .strip_suffix("/v1beta")
            .or_else(|| base.strip_suffix("/v1"))
            .unwrap_or(base),
        _ => base,
    }
}

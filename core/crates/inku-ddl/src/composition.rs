//! Language-independent typed composition over meaning-neutral parser deliveries.

use crate::{NeutralDiagnostic, NeutralParseResult, NeutralToken, NeutralTokenKind, SourceSpan};

/// Stable identity for the runtime-disconnected core-role composition foundation.
pub const CORE_ROLE_COMPOSITION_SCHEMA_ID: &str = "inku.core-role-composition.v1";

/// One of the exact core drawing roles typed by this foundation slice.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CoreRoleKind {
    Primitive,
    Touch,
    Color,
    Surface,
    Ground,
}

/// One typed Saijiki row at its exact source location.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CoreRoleTerm {
    pub role: CoreRoleKind,
    pub asset_id: String,
    pub category_key: String,
    pub canonical_surface_ja: String,
    pub span: SourceSpan,
}

/// Partial typed composition with every untyped delivery retained for a later slice.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CoreRoleComposition {
    pub typed_roles: Vec<CoreRoleTerm>,
    pub deferred_tokens: Vec<NeutralToken>,
    pub diagnostics: Vec<NeutralDiagnostic>,
    pub delivery_conservation_count: usize,
}

/// Move the exact five core Saijiki categories into typed roles without adding meaning.
pub fn compose_core_roles(neutral: NeutralParseResult) -> CoreRoleComposition {
    let NeutralParseResult {
        tokens,
        diagnostics,
        recognized_delivery_count: _,
    } = neutral;
    let mut typed_roles = Vec::new();
    let mut deferred_tokens = Vec::new();

    for token in tokens {
        let role = match &token.kind {
            NeutralTokenKind::SaijikiWord { category_key, .. } => role_for_category(category_key),
            NeutralTokenKind::SaijikiRelation { .. }
            | NeutralTokenKind::FunctionWord
            | NeutralTokenKind::ExactNumber { .. } => None,
        };

        let Some(role) = role else {
            deferred_tokens.push(token);
            continue;
        };
        let NeutralTokenKind::SaijikiWord {
            asset_id,
            category_key,
            canonical_surface_ja,
        } = token.kind
        else {
            unreachable!("only Saijiki words map to core roles");
        };
        typed_roles.push(CoreRoleTerm {
            role,
            asset_id,
            category_key,
            canonical_surface_ja,
            span: token.span,
        });
    }

    let delivery_conservation_count = typed_roles.len()
        + deferred_tokens.len()
        + diagnostics
            .iter()
            .filter(|diagnostic| diagnostic.recognized)
            .count();

    CoreRoleComposition {
        typed_roles,
        deferred_tokens,
        diagnostics,
        delivery_conservation_count,
    }
}

fn role_for_category(category_key: &str) -> Option<CoreRoleKind> {
    match category_key {
        "katachi" => Some(CoreRoleKind::Primitive),
        "tezawari" => Some(CoreRoleKind::Touch),
        "iro" => Some(CoreRoleKind::Color),
        "omote" => Some(CoreRoleKind::Surface),
        "ji" => Some(CoreRoleKind::Ground),
        _ => None,
    }
}

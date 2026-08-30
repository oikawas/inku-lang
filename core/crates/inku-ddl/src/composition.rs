//! Language-independent typed composition over meaning-neutral parser deliveries.

use crate::{NeutralDiagnostic, NeutralParseResult, NeutralToken, NeutralTokenKind, SourceSpan};

/// Stable identity for the runtime-disconnected core-role composition foundation.
pub const CORE_ROLE_COMPOSITION_SCHEMA_ID: &str = "inku.core-role-composition.v1";

/// Stable identity for the runtime-disconnected remaining-role composition foundation.
pub const REMAINING_ROLE_COMPOSITION_SCHEMA_ID: &str = "inku.remaining-role-composition.v1";

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

/// One of the exact remaining Saijiki roles typed by this foundation slice.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RemainingRoleKind {
    Angle,
    Continuity,
    Fluctuation,
    Place,
    Motion,
    Proportion,
}

/// One typed remaining Saijiki row at its exact source location.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RemainingRoleTerm {
    pub role: RemainingRoleKind,
    pub asset_id: String,
    pub category_key: String,
    pub canonical_surface_ja: String,
    pub span: SourceSpan,
}

/// One exact number retained without inferring a semantic target or unit.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct UnattachedExactNumber {
    pub value: u64,
    pub span: SourceSpan,
}

/// Partial typed composition with every still-untyped delivery retained for a later slice.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RemainingRoleComposition {
    pub core_roles: Vec<CoreRoleTerm>,
    pub remaining_roles: Vec<RemainingRoleTerm>,
    pub unattached_exact_numbers: Vec<UnattachedExactNumber>,
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

/// Move the exact six remaining Saijiki categories and exact numbers into typed deliveries.
pub fn compose_remaining_roles(core: CoreRoleComposition) -> RemainingRoleComposition {
    let CoreRoleComposition {
        typed_roles: core_roles,
        deferred_tokens,
        diagnostics,
        delivery_conservation_count: input_delivery_conservation_count,
    } = core;
    let mut remaining_roles = Vec::new();
    let mut unattached_exact_numbers = Vec::new();
    let mut still_deferred_tokens = Vec::new();

    for token in deferred_tokens {
        let role = match &token.kind {
            NeutralTokenKind::SaijikiWord { category_key, .. } => {
                remaining_role_for_category(category_key)
            }
            NeutralTokenKind::SaijikiRelation { .. }
            | NeutralTokenKind::FunctionWord
            | NeutralTokenKind::ExactNumber { .. } => None,
        };

        if let Some(role) = role {
            let NeutralTokenKind::SaijikiWord {
                asset_id,
                category_key,
                canonical_surface_ja,
            } = token.kind
            else {
                unreachable!("only Saijiki words map to remaining roles");
            };
            remaining_roles.push(RemainingRoleTerm {
                role,
                asset_id,
                category_key,
                canonical_surface_ja,
                span: token.span,
            });
            continue;
        }

        if let NeutralTokenKind::ExactNumber { value } = &token.kind {
            unattached_exact_numbers.push(UnattachedExactNumber {
                value: *value,
                span: token.span,
            });
            continue;
        }

        still_deferred_tokens.push(token);
    }

    let delivery_conservation_count = core_roles.len()
        + remaining_roles.len()
        + unattached_exact_numbers.len()
        + still_deferred_tokens.len()
        + diagnostics
            .iter()
            .filter(|diagnostic| diagnostic.recognized)
            .count();
    debug_assert_eq!(
        delivery_conservation_count, input_delivery_conservation_count,
        "remaining-role composition must conserve I-562 deliveries"
    );

    RemainingRoleComposition {
        core_roles,
        remaining_roles,
        unattached_exact_numbers,
        deferred_tokens: still_deferred_tokens,
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

fn remaining_role_for_category(category_key: &str) -> Option<RemainingRoleKind> {
    match category_key {
        "katamuki" => Some(RemainingRoleKind::Angle),
        "tsuranari" => Some(RemainingRoleKind::Continuity),
        "yuragi" => Some(RemainingRoleKind::Fluctuation),
        "basho" => Some(RemainingRoleKind::Place),
        "ugoki" => Some(RemainingRoleKind::Motion),
        "wariai" => Some(RemainingRoleKind::Proportion),
        _ => None,
    }
}

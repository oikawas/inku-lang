package app.inku.mobile.llm

/** A diagnostic contains only locally defined identifiers; it never formats an exception. */
internal object ChatGptDiagnostic {
    private val codes = setOf(
        "chatgpt_admission_rejected", "chatgpt_attempt_busy", "chatgpt_auth_rejected", "chatgpt_auth_unavailable",
        "chatgpt_callback_invalid", "chatgpt_cancelled", "chatgpt_catalog_required", "chatgpt_consent_declined",
        "chatgpt_credentials_unavailable", "chatgpt_disabled", "chatgpt_exported", "chatgpt_identity_invalid",
        "chatgpt_identity_mismatch", "chatgpt_mode_not_allowed", "chatgpt_model_not_offered", "chatgpt_model_unavailable",
        "chatgpt_not_connected", "chatgpt_operation_not_supported", "chatgpt_owner_not_allowed", "chatgpt_profile_limit",
        "chatgpt_profile_required", "chatgpt_quota", "chatgpt_reauthentication_required", "chatgpt_refresh_not_ready",
        "chatgpt_refused", "chatgpt_registration_incomplete", "chatgpt_response_failed", "chatgpt_response_incomplete",
        "chatgpt_response_invalid", "chatgpt_response_too_large", "chatgpt_scope_required", "chatgpt_session_changed",
        "chatgpt_session_required", "chatgpt_session_stale", "chatgpt_session_transferred", "chatgpt_signed_out",
        "chatgpt_startup_unverified", "chatgpt_storage_unavailable", "chatgpt_transport_timeout", "chatgpt_transport_unavailable",
        "chatgpt_unexpected_tool", "subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable",
        "subscription_sharing_user_unavailable", "subscription_sharing_user_not_eligible", "subscription_sharing_invalid_user",
        "subscription_sharing_unsupported_capability", "subscription_sharing_route_not_supported",
        "chatpass_v2_invalid_authorization_context", "chatpass_v2_scope_not_authorized",
    )
    private val failures = setOf("provider_rejected", "transport_timeout", "transport_unavailable", "rate_limited",
        "malformed_payload", "cancelled", "unsupported", "authentication", "quota", "refused", "temporary")
    private val stages = setOf("listener", "callback", "token", "discovery", "jwks", "identity", "tokens", "display",
        "generation", "save_check", "preserve", "store", "catalog")
    private val safeClass = Regex("[A-Za-z0-9_.$]{1,160}")
    private val safeFile = Regex("[A-Za-z0-9_]+\\.(kt|java)")

    fun line(stage: String, status: Int?, error: Exception): String {
        val code = if (error is ChatGptException) error.code.takeIf { it in codes } ?: "unrecognized"
            else if (stage == "catalog") "chatgpt_transport_unavailable" else "chatgpt_auth_unavailable"
        val failure = (error as? ChatGptException)?.failure?.takeIf { it in failures }
        val kind = error.javaClass.name.takeIf { safeClass.matches(it) } ?: "unknown"
        val frames = error.stackTrace.asSequence().filter { it.className.startsWith("app.inku.mobile.") }
            .mapNotNull { frame -> frame.fileName?.takeIf { safeFile.matches(it) && frame.lineNumber > 0 }
                ?.let { "$it:${frame.lineNumber}" } }.take(4).joinToString(",")
        return buildString {
            append("chatgpt_failure stage=").append(stage.takeIf { it in stages } ?: "listener")
            append(" code=").append(code).append(" class=").append(kind)
            failure?.let { append(" failure=").append(it) }
            status?.takeIf { it in 100..599 }?.let { append(" status=").append(it) }
            if (frames.isNotEmpty()) append(" frames=").append(frames)
        }
    }
}

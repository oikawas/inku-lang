package app.inku.mobile.llm

/** A diagnostic contains only locally defined identifiers; it never formats an exception. */
internal object ChatGptDiagnostic {
    /**
     * A code and a failure class come from the core's answers (or this host's
     * own literals), so only their shape is checked; the core holds the table
     * (`sign_in_failure`, step 6).
     */
    private val safeCode = Regex("[a-z0-9_]{1,80}")
    private val stages = setOf("listener", "callback", "token", "discovery", "jwks", "identity", "store", "catalog")
    private val safeClass = Regex("[A-Za-z0-9_.$]{1,160}")
    private val safeFile = Regex("[A-Za-z0-9_]+\\.(kt|java)")

    fun line(stage: String, status: Int?, error: Exception): String {
        val code = if (error is ChatGptException) error.code.takeIf(safeCode::matches) ?: "unrecognized"
            else if (stage == "catalog") "chatgpt_transport_unavailable" else "chatgpt_auth_unavailable"
        val failure = (error as? ChatGptException)?.failure?.takeIf(safeCode::matches)
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

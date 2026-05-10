package app.inku.mobile.security

object DisplaySanitizer {
    fun redact(value: String): String {
        return value
            .replace(Regex("Bearer\\s+[A-Za-z0-9._~+/=-]+", RegexOption.IGNORE_CASE), "Bearer [redacted]")
            .replace(Regex("nvapi-[A-Za-z0-9._~+/=-]+"), "nvapi-[redacted]")
            .replace(Regex("sk-[A-Za-z0-9._~+/=-]+"), "sk-[redacted]")
            .replace(Regex("AIza[0-9A-Za-z_-]+"), "AIza[redacted]")
            .replace(Regex("(?i)(api[_-]?key|authorization|token)\"?\\s*[:=]\\s*\"?[A-Za-z0-9._~+/=-]+"), "\$1=[redacted]")
            .replace(Regex("/data/user/\\d+/[^\\s\"']+"), "/data/user/[redacted]")
            .replace(Regex("/data/data/[^\\s\"']+"), "/data/data/[redacted]")
            .lineSequence()
            .joinToString(" ") { it.trim() }
    }
}

package app.inku.mobile.data

import org.json.JSONObject

/** The portable persistence contract's body test, independent of Kotlin's isBlank. */
object DdlSource {
    const val LEGACY_EXPANDED = "legacy_expanded"

    // Unicode White_Space, fixed by persistence/contract.json. U+001C and
    // U+200B are deliberately absent; selection preserves the entire string.
    private val whitespace = setOf(
        9, 10, 11, 12, 13, 32, 133, 160, 5760,
        8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202,
        8232, 8233, 8239, 8287, 12288,
    )

    fun hasBody(ddl: String?): Boolean = ddl?.any { it.code !in whitespace } == true

    data class Selection(val ddl: String?, val origin: String?)

    fun select(ddl: String?, expanded: String?, origin: String? = null): Selection {
        require(origin == null || origin == LEGACY_EXPANDED) { "invalid_ddl_source_origin" }
        return if (!hasBody(ddl) && hasBody(expanded)) {
            Selection(expanded, LEGACY_EXPANDED)
        } else {
            Selection(ddl, origin)
        }
    }

    /** Retired JSON keys are accepted only at this input boundary. */
    fun fromJson(json: JSONObject): Selection = select(
        json.nullableText(if (json.has("ddl")) "ddl" else "normalized_ddl"),
        json.nullableText("expanded_ddl"),
        json.nullableText("ddl_source_origin"),
    )

    fun putJson(json: JSONObject, ddl: String?, origin: String?): JSONObject {
        require(origin == null || origin == LEGACY_EXPANDED) { "invalid_ddl_source_origin" }
        json.remove("expanded_ddl")
        json.remove("normalized_ddl")
        return json.put("ddl", ddl ?: JSONObject.NULL)
            .put("ddl_source_origin", origin ?: JSONObject.NULL)
    }

    // Compare the remaining text rather than length(): SQLite length stops at
    // U+0000, which is a body character under the same contract.
    internal fun sqlHasBody(column: String): String =
        "trim(COALESCE(`$column`, ''), char(${whitespace.joinToString(",")})) <> ''"

    private fun JSONObject.nullableText(key: String): String? {
        if (!has(key) || isNull(key)) return null
        return get(key) as? String ?: throw IllegalArgumentException("invalid_ddl_text:$key")
    }
}

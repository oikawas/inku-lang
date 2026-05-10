package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelTool
import org.json.JSONArray
import org.json.JSONObject

internal object WebScoreTool {
    val submitScore = ModelTool(
        name = "submit_score",
        description = "正規化DDLから導出した JSON Score を提出する。",
        parametersJson = ServerScoreSchemaJson.parameters,
    )

    fun extractJsonObject(text: String): JSONObject {
        val trimmed = text.trim()
        parseScoreCandidate(trimmed)?.let { return it }
        val start = trimmed.indexOf('{')
        val end = trimmed.lastIndexOf('}')
        if (start >= 0 && end > start) {
            val candidate = trimmed.substring(start, end + 1)
            parseScoreCandidate(candidate)?.let { return it }
            val repaired = repairLiteRtJsonText(candidate)
            if (repaired != candidate) {
                parseScoreCandidate(repaired)?.let { return it }
            }
        }
        error("Stage2 did not return a JSON object.")
    }

    private fun parseScoreCandidate(text: String): JSONObject? {
        val json = runCatching { JSONObject(text) }.getOrNull() ?: return null
        return normalizeJsonObject(unwrapScoreJson(json))
    }

    fun unwrapScoreJson(json: JSONObject): JSONObject {
        json.optJSONArray("tool_calls")?.let { calls ->
            for (i in 0 until calls.length()) {
                val call = calls.optJSONObject(i) ?: continue
                val arguments = call.optJSONObject("arguments")
                    ?: call.optJSONObject("parameters")
                    ?: call.optJSONObject("function")?.let { function ->
                        function.optJSONObject("arguments")
                            ?: function.optString("arguments").takeIf { it.isNotBlank() }?.let(::JSONObject)
                    }
                if (arguments != null) return arguments
            }
        }
        json.optJSONObject("arguments")?.let { return it }
        return json
    }

    fun hasRenderableInstructions(json: JSONObject): Boolean {
        val instructions = json.optJSONArray("instructions") ?: return false
        for (i in 0 until instructions.length()) {
            if (instructions.optJSONObject(i) != null) return true
        }
        return false
    }

    internal fun repairLiteRtJsonText(text: String): String {
        return stripNumericWhitespaceOutsideStrings(text)
    }

    private fun stripNumericWhitespaceOutsideStrings(text: String): String {
        val out = StringBuilder(text.length)
        var inString = false
        var escaped = false
        for (index in text.indices) {
            val char = text[index]
            if (inString) {
                out.append(char)
                val wasEscaped = escaped
                escaped = if (escaped) {
                    false
                } else {
                    char == '\\'
                }
                if (char == '"' && !wasEscaped) inString = false
                continue
            }
            if (char == '"') {
                inString = true
                out.append(char)
                continue
            }
            if (char.isWhitespace()) {
                val previous = previousNonWhitespace(text, index)
                val next = nextNonWhitespace(text, index)
                val numericSplit = (previous?.isDigit() == true && (next?.isDigit() == true || next == '.')) ||
                    (previous == '.' && next?.isDigit() == true)
                if (numericSplit) continue
            }
            out.append(char)
        }
        return out.toString()
    }

    private fun previousNonWhitespace(text: String, before: Int): Char? {
        for (index in before - 1 downTo 0) {
            val char = text[index]
            if (!char.isWhitespace()) return char
        }
        return null
    }

    private fun nextNonWhitespace(text: String, after: Int): Char? {
        for (index in after + 1 until text.length) {
            val char = text[index]
            if (!char.isWhitespace()) return char
        }
        return null
    }

    private fun normalizeJsonObject(source: JSONObject): JSONObject {
        val result = JSONObject()
        source.keys().forEach { key ->
            result.put(normalizeJsonKey(key), normalizeJsonValue(source.opt(key)))
        }
        return result
    }

    private fun normalizeJsonArray(source: JSONArray): JSONArray {
        val result = JSONArray()
        for (index in 0 until source.length()) {
            result.put(normalizeJsonValue(source.opt(index)))
        }
        return result
    }

    private fun normalizeJsonValue(value: Any?): Any? {
        return when (value) {
            is JSONObject -> normalizeJsonObject(value)
            is JSONArray -> normalizeJsonArray(value)
            is String -> normalizeJsonString(value)
            else -> value
        }
    }

    private fun normalizeJsonString(value: String): Any {
        val trimmed = value.trim()
        val compactNumeric = stripNumericWhitespaceOutsideStrings(trimmed)
        if (compactNumeric != trimmed && JSON_NUMBER_PATTERN.matches(compactNumeric)) {
            return if (compactNumeric.contains('.') || compactNumeric.contains('e', ignoreCase = true)) {
                compactNumeric.toDouble()
            } else {
                compactNumeric.toLong().let { number ->
                    if (number in Int.MIN_VALUE..Int.MAX_VALUE) number.toInt() else number
                }
            }
        }
        return trimmed
    }

    private fun normalizeJsonKey(key: String): String {
        return key.trim()
            .replace(KEY_SEPARATOR_WHITESPACE_PATTERN, "_")
            .replace(KEY_WHITESPACE_PATTERN, "_")
    }

    private val JSON_NUMBER_PATTERN = Regex("-?(?:0|[1-9]\\d*)(?:\\.\\d+)?(?:[eE][+-]?\\d+)?")
    private val KEY_SEPARATOR_WHITESPACE_PATTERN = Regex("\\s*[_-]\\s*")
    private val KEY_WHITESPACE_PATTERN = Regex("\\s+")
}

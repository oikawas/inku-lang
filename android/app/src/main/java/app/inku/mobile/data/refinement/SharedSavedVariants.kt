package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.SharedPipelineBinding
import java.math.BigInteger
import org.json.JSONArray
import org.json.JSONObject

/** One byte transport for the shared saved-work variants. Scores travel as raw JSON values. */
internal object SharedSavedVariants {
    const val SCHEMA = "inku.saved-variants.v1"
    val U64_MAX: BigInteger = BigInteger("18446744073709551615")

    fun call(action: String, fields: String, binding: SharedPipelineBinding = NativePipelineBridge,
             wideNumbers: Boolean = false): Answer {
        val request = "{\"action\":${JSONObject.quote(action)},$fields}"
        val raw = binding.savedVariants(request.encodeToByteArray()).toString(Charsets.UTF_8)
        val objectValue = JSONObject(if (wideNumbers) quoteWideIntegerTokens(raw) else raw)
        if (objectValue.has("error")) throw IllegalArgumentException(objectValue.getString("error"))
        require(objectValue.optString("schema") == SCHEMA) { "saved variant schema mismatch" }
        if (objectValue.optString("outcome") == "refused") {
            throw IllegalArgumentException(objectValue.getString("detail"))
        }
        require(objectValue.optString("outcome") == "ok") { "saved variant outcome missing" }
        return Answer(raw, objectValue)
    }

    data class Answer(val raw: String, val value: JSONObject) {
        fun rawValue(key: String): String = rawTopLevelValue(raw, key)
        fun rawScore(): String = rawValue("score")
    }

    fun q(value: String): String = JSONObject.quote(value)

    fun stringMap(values: Map<String, String>): String = JSONObject(values).toString()

    fun integer(value: Any): BigInteger = BigInteger(value.toString())

    fun rawObjectValue(json: String, key: String): String = rawTopLevelValue(json, key)

    fun metadata(objectValue: JSONObject): Map<String, Any?> = objectValue.keys().asSequence()
        .associateWith { key -> jsonValue(objectValue.get(key)) }

    private fun jsonValue(value: Any?): Any? = when (value) {
        null, JSONObject.NULL -> null
        is JSONObject -> metadata(value)
        is JSONArray -> (0 until value.length()).map { jsonValue(value.get(it)) }
        else -> value
    }

    /** org.json on Android parses an unsigned u64 beyond Long.MAX_VALUE as Double. */
    private fun quoteWideIntegerTokens(json: String): String {
        val result = StringBuilder(json.length)
        var index = 0
        var quoted = false
        var escaped = false
        while (index < json.length) {
            val character = json[index]
            if (quoted) {
                result.append(character)
                when {
                    escaped -> escaped = false
                    character == '\\' -> escaped = true
                    character == '"' -> quoted = false
                }
                index++
                continue
            }
            if (character == '"') {
                quoted = true
                result.append(character)
                index++
                continue
            }
            if (character == '-' || character in '0'..'9') {
                val start = index
                while (index < json.length && json[index] !in ",}] \t\r\n") index++
                val token = json.substring(start, index)
                val wide = token.all { it in '0'..'9' } && token.isNotEmpty() &&
                    BigInteger(token) > BigInteger.valueOf(Long.MAX_VALUE)
                if (wide) result.append('"').append(token).append('"') else result.append(token)
                continue
            }
            result.append(character)
            index++
        }
        return result.toString()
    }

    /** Extract one top-level value without parsing and rewriting its numeric lexemes. */
    private fun rawTopLevelValue(json: String, key: String): String {
        var index = json.indexOf('{') + 1
        while (index > 0 && index < json.length) {
            while (index < json.length && json[index].isWhitespace()) index++
            if (index >= json.length || json[index] == '}') break
            require(json[index] == '"') { "invalid saved variant response" }
            val keyEnd = stringEnd(json, index)
            val name = JSONObject("{${json.substring(index, keyEnd)}:null}").keys().next()
            index = keyEnd
            while (index < json.length && json[index].isWhitespace()) index++
            require(index < json.length && json[index] == ':') { "invalid saved variant response" }
            index++
            while (index < json.length && json[index].isWhitespace()) index++
            val start = index
            var depth = 0
            while (index < json.length) {
                when (json[index]) {
                    '"' -> index = stringEnd(json, index)
                    '{', '[' -> { depth++; index++ }
                    '}', ']' -> {
                        if (depth == 0) break
                        depth--; index++
                    }
                    ',' -> if (depth == 0) break else index++
                    else -> index++
                }
            }
            if (name == key) return json.substring(start, index).trimEnd()
            if (index < json.length && json[index] == ',') index++
        }
        throw IllegalArgumentException("saved variant response omitted $key")
    }

    private fun stringEnd(json: String, start: Int): Int {
        var index = start + 1
        var escaped = false
        while (index < json.length) {
            val character = json[index++]
            if (escaped) escaped = false
            else if (character == '\\') escaped = true
            else if (character == '"') return index
        }
        throw IllegalArgumentException("invalid saved variant response string")
    }
}

data class SavedVariantRender(
    val scoreJson: String,
    val ddl: String,
    val derivationMetadata: Map<String, Any?>,
)

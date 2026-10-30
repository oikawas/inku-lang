package app.inku.mobile.llm

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode
import java.math.BigInteger
import java.util.Base64
import org.json.JSONObject
import org.json.JSONTokener

/** Preserve the order in the signed claim before JSONObject materializes it. */
internal object ChatGptEmailJson {
    fun fromToken(token: String): String? {
        val payload = String(Base64.getUrlDecoder().decode(token.split('.')[1]), Charsets.UTF_8)
        return fromClaims(payload)
    }

    fun fromClaims(payload: String): String? {
        val claims = read(JSONTokener(payload)) as? Map<*, *> ?: return null
        return if (claims.containsKey("email")) encode(claims["email"]) else null
    }

    private fun read(input: JSONTokener): Any? {
        val c = input.nextClean()
        return when (c) {
            '{' -> {
                val result = linkedMapOf<String, Any?>()
                if (input.nextClean() != '}') {
                    input.back()
                    while (true) {
                        val key = input.nextValue() as String
                        require(input.nextClean() == ':')
                        result[key] = read(input)
                        val delimiter = input.nextClean()
                        if (delimiter == '}') break
                        require(delimiter == ',')
                    }
                }
                result
            }
            '[' -> {
                val result = mutableListOf<Any?>()
                if (input.nextClean() != ']') {
                    input.back()
                    while (true) {
                        result.add(read(input))
                        val delimiter = input.nextClean()
                        if (delimiter == ']') break
                        require(delimiter == ',')
                    }
                }
                result
            }
            else -> {
                input.back()
                if (c == '-' || c.isDigit()) {
                    val raw = StringBuilder()
                    while (true) {
                        val next = input.next()
                        if (next == '\u0000' || next in charArrayOf(',', ']', '}', ' ', '\t', '\n', '\r')) {
                            if (next != '\u0000') input.back()
                            break
                        }
                        raw.append(next)
                    }
                    val text = raw.toString()
                    if (text.any { it == '.' || it == 'e' || it == 'E' }) text.toDouble() else BigInteger(text)
                } else input.nextValue()
            }
        }
    }

    private fun encode(value: Any?): String = when (value) {
        null, JSONObject.NULL -> "null"
        is String -> JSONObject.quote(value)
        is Boolean -> value.toString()
        is BigDecimal -> pythonFloat(value.toDouble())
        is Double -> pythonFloat(value)
        is Float -> pythonFloat(value.toDouble())
        is Number -> value.toString()
        is Map<*, *> -> value.entries.joinToString(", ", "{", "}") { JSONObject.quote(it.key as String) + ": " + encode(it.value) }
        is List<*> -> value.joinToString(", ", "[", "]") { encode(it) }
        else -> error("Unsupported JSON value")
    }

    private fun pythonFloat(value: Double): String {
        require(value.isFinite())
        if (value == 0.0) return if (value.toRawBits() < 0) "-0.0" else "0.0"
        val exact = BigDecimal(value)
        val number = (1..17).asSequence().map { exact.round(MathContext(it, RoundingMode.HALF_EVEN)).stripTrailingZeros() }
            .first { it.toDouble().toRawBits() == value.toRawBits() }
        val exponent = number.precision() - number.scale() - 1
        if (exponent in -4..15) {
            val plain = number.toPlainString()
            return if ('.' in plain) plain else "$plain.0"
        }
        val digits = number.unscaledValue().abs().toString()
        val sign = if (value < 0) "-" else ""
        val mantissa = digits.take(1) + if (digits.length > 1) "." + digits.drop(1) else ""
        return "$sign${mantissa}e${if (exponent < 0) "-" else "+"}${kotlin.math.abs(exponent).toString().padStart(2, '0')}"
    }
}

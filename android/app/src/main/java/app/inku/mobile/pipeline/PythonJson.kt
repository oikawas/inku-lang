package app.inku.mobile.pipeline

import java.math.BigDecimal
import java.math.BigInteger
import java.math.MathContext
import java.math.RoundingMode
import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

/**
 * `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`,
 * the text the server hashes for a work's `rh3` (`persistence/history.py`).
 *
 * `JSONObject.quote` and `Double.toString` are not that text: the platform
 * escapes `/`, and Java writes `1.0E-5` where Python writes `1e-05`. A Score
 * holding either would otherwise hash differently on the two hosts.
 */
internal object PythonJson {
    fun canonical(value: Any?): String = StringBuilder().also { write(it, value) }.toString()

    private fun write(out: StringBuilder, value: Any?) {
        when (value) {
            null, JSONObject.NULL -> out.append("null")
            is JSONObject -> {
                out.append('{')
                value.keys().asSequence().toList().sorted().forEachIndexed { index, key ->
                    if (index > 0) out.append(',')
                    string(out, key)
                    out.append(':')
                    write(out, value.opt(key))
                }
                out.append('}')
            }
            is JSONArray -> {
                out.append('[')
                for (index in 0 until value.length()) {
                    if (index > 0) out.append(',')
                    write(out, value.opt(index))
                }
                out.append(']')
            }
            is String -> string(out, value)
            is Boolean -> out.append(value.toString())
            is Int, is Long, is Short, is Byte, is BigInteger -> out.append(value.toString())
            // A parser that keeps numbers as decimals: an integer stays one, as in Python.
            is BigDecimal -> out.append(if (value.scale() <= 0) value.toBigInteger().toString() else float(value.toDouble()))
            is Double -> out.append(float(value))
            is Float -> out.append(float(value.toDouble()))
            else -> string(out, value.toString())
        }
    }

    /** Python's `json` string escapes with `ensure_ascii=False`. */
    private fun string(out: StringBuilder, value: String) {
        out.append('"')
        for (char in value) {
            when (char) {
                '"' -> out.append("\\\"")
                '\\' -> out.append("\\\\")
                '\n' -> out.append("\\n")
                '\r' -> out.append("\\r")
                '\t' -> out.append("\\t")
                '\b' -> out.append("\\b")
                '\u000c' -> out.append("\\f")
                else -> if (char < ' ') out.append(String.format(Locale.ROOT, "\\u%04x", char.code)) else out.append(char)
            }
        }
        out.append('"')
    }

    /** Python's `float.__repr__`: the shortest digits that read back, positional between 1e-4 and 1e16. */
    internal fun float(value: Double): String {
        require(value.isFinite()) { "non-finite number in a hashed Score" }
        if (value == 0.0) return if (1.0 / value < 0) "-0.0" else "0.0"
        val exact = BigDecimal(value)
        val shortest = (1..17).asSequence()
            .map { exact.round(MathContext(it, RoundingMode.HALF_EVEN)) }
            .first { it.toDouble() == value }
            .stripTrailingZeros()
        val digits = shortest.unscaledValue().abs().toString()
        val exponent = digits.length - 1 - shortest.scale()
        val sign = if (shortest.signum() < 0) "-" else ""
        return if (exponent < -4 || exponent >= 16) {
            val mantissa = if (digits.length == 1) digits else digits[0] + "." + digits.substring(1)
            sign + mantissa + "e" + (if (exponent < 0) "-" else "+") + String.format(Locale.ROOT, "%02d", kotlin.math.abs(exponent))
        } else {
            val plain = shortest.abs().toPlainString()
            sign + if (plain.contains('.')) plain else "$plain.0"
        }
    }
}

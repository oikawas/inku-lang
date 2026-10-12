package app.inku.mobile.render

import app.inku.mobile.ui.i18n.InkuFailure
import org.json.JSONObject

/** Runtime output allowance, independent of a work's compiler resource policy. */
object SvgOutputLimit {
    const val SETTING_KEY = "max_svg_bytes"
    const val DEFAULT_MIB = 12
    const val MIN_MIB = 1
    const val MAX_MIB = 32
    const val BYTES_PER_MIB = 1024L * 1024L
    const val DEFAULT_BYTES = DEFAULT_MIB * BYTES_PER_MIB
    const val CONSUMER_BYTES = 64L * BYTES_PER_MIB

    fun parseMiB(text: String): Int? = text.trim().takeIf { it.matches(Regex("[0-9]+")) }
        ?.toIntOrNull()?.takeIf { it in MIN_MIB..MAX_MIB }

    fun storedMiB(json: String?): Int = runCatching {
        val bytes = JSONObject(json ?: return DEFAULT_MIB).opt("value")
        val integer = when (bytes) {
            is Int -> bytes.toLong()
            is Long -> bytes
            else -> return DEFAULT_MIB
        }
        if (integer % BYTES_PER_MIB != 0L) return DEFAULT_MIB
        (integer / BYTES_PER_MIB).takeIf { it in MIN_MIB.toLong()..MAX_MIB.toLong() }
            ?.toInt() ?: DEFAULT_MIB
    }.getOrDefault(DEFAULT_MIB)

    fun requireSvg(svg: String, maxBytes: Long, generatedWork: Boolean = true) {
        require(maxBytes in BYTES_PER_MIB..CONSUMER_BYTES) { "invalid SVG output allowance" }
        if (svg.toByteArray(Charsets.UTF_8).size.toLong() > maxBytes) {
            if (!generatedWork) throw InkuFailure { it.savedRenderRefused("output_too_large") }
            throw InkuFailure("svg_output_too_large") { it.svgOutputTooLarge((maxBytes / BYTES_PER_MIB).toInt()) }
        }
    }
}

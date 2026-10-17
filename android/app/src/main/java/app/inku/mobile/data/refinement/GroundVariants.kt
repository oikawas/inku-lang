package app.inku.mobile.data.refinement

import org.json.JSONObject

data class GroundVariantEntry(val material: String, val labelJa: String, val labelEn: String)

data class GroundVariantPlan(
    val current: String,
    val currentLabelJa: String?,
    val currentLabelEn: String?,
    val entries: List<GroundVariantEntry>,
)

/** The seven named supports from the じ vocabulary, in its authored order. */
object GroundVariants {
    private val materials = listOf(
        GroundVariantEntry("paper", "紙", "paper"),
        GroundVariantEntry("washi", "和紙", "washi"),
        GroundVariantEntry("ink_wash", "薄墨地", "ink wash ground"),
        GroundVariantEntry("charcoal_ground", "木炭地", "charcoal ground"),
        GroundVariantEntry("canvas", "カンバス", "canvas"),
        GroundVariantEntry("drawing_paper", "画用紙", "drawing paper"),
        GroundVariantEntry("mezzotint", "メゾチント", "mezzotint"),
    )

    fun plan(scoreJson: String): GroundVariantPlan {
        val current = currentMaterial(scoreJson)
        val named = materials.firstOrNull { it.material == current }
        return GroundVariantPlan(current, named?.labelJa, named?.labelEn, materials.filter { it.material != current })
    }

    fun currentMaterial(scoreJson: String): String {
        val score = JSONObject(scoreJson)
        return score.optJSONObject("canvas")?.optJSONObject("ground")?.optString("material")
            ?.takeIf(String::isNotBlank) ?: "plain"
    }

    fun scoreWithGround(scoreJson: String, material: String): String {
        require(materials.any { it.material == material }) { "unknown ground material: $material" }
        val changed = JSONObject(scoreJson)
        val current = changed.opt("canvas")
        val canvas = if (current is JSONObject) current else JSONObject().put("aspect", current ?: "square")
        val ground = canvas.optJSONObject("ground") ?: JSONObject()
        canvas.put("ground", ground.put("material", material))
        changed.put("canvas", canvas)
        return changed.toString()
    }

    fun ddlWithGround(ddl: String, material: String, language: String?): String {
        val surface = materials.firstOrNull { it.material == material }
            ?: throw IllegalArgumentException("unknown ground material: $material")
        val lines = ddl.split("\n").toMutableList()
        for ((index, line) in lines.withIndex()) {
            val lineLanguage = materials.firstNotNullOfOrNull { known ->
                when {
                    line.trim() == sentence(known, "ja") -> "ja"
                    line.trim().equals(sentence(known, "en"), ignoreCase = true) -> "en"
                    else -> null
                }
            }
            if (lineLanguage != null) {
                lines[index] = sentence(surface, lineLanguage)
                return lines.joinToString("\n")
            }
        }
        val resolved = if (language in setOf("ja", "en")) language!! else {
            if (ddl.any { it in '\u3040'..'\u9fff' }) "ja" else "en"
        }
        val heading = sentence(surface, resolved)
        return if (ddl.isEmpty()) heading else "$heading\n$ddl"
    }

    private fun sentence(entry: GroundVariantEntry, language: String): String =
        if (language == "ja") "${entry.labelJa}。" else entry.labelEn.replaceFirstChar(Char::uppercaseChar) + "."
}

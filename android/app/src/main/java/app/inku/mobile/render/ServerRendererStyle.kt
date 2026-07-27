package app.inku.mobile.render

import kotlin.math.min
import org.json.JSONArray
import org.json.JSONObject

private val HUE_HINTS = mapOf(
    "white" to listOf("white", "ivory", "paper", "linen", "blanc", "bianco", "aspro", "白", "胡粉", "象牙", "生成"),
    "black" to listOf("black", "ink", "sumi", "obsidian", "basalt", "skotadi", "黒", "墨", "玄", "暗"),
    "blue" to listOf("blue", "cyan", "azure", "ultramarine", "cobalt", "lapis", "bleu", "blu", "ai", "azul", "青", "藍", "水色", "空色", "瑠璃"),
    "green" to listOf("green", "verd", "vert", "jade", "olive", "cactus", "tall", "緑", "青緑", "翡翠", "常磐", "玉", "草"),
    "gray" to listOf("gray", "grey", "silver", "ash", "stone", "granit", "petra", "灰", "鼠", "銀", "石"),
    "red" to listOf("red", "rose", "pink", "carmine", "cinnabar", "terra", "rosa", "shu", "vermilion", "赤", "朱", "紅", "桜", "桃", "薔薇"),
    "yellow" to listOf("yellow", "gold", "ochre", "ocra", "giallo", "jaune", "napoli", "kesar", "haldi", "sun", "ilios", "山吹", "金", "黄", "琉璃金"),
    "orange" to listOf("orange", "apricot", "terracotta", "cempasuchil", "ff4d00", "橙", "蜜柑"),
    "purple" to listOf("purple", "violet", "lilac", "murasaki", "宮廷紫", "藤", "紫"),
    "brown" to listOf("brown", "sienna", "umber", "ombra", "chandan", "lera", "sepia", "茶", "土", "焦"),
)

internal data class SvgAttrs(
    val stroke: String,
    val strokeWidth: Double,
    val strokeLinecap: String,
    val strokeOpacity: Double,
    val fill: String,
    val fillOpacity: Double? = null,
    val dash: String? = null,
    val filter: String? = null,
) {
    fun toSvgAttributes(includeFill: Boolean = true): String = buildString {
        append("""stroke="$stroke" stroke-width="$strokeWidth" stroke-linecap="$strokeLinecap" stroke-opacity="$strokeOpacity"""")
        if (includeFill) append(""" fill="$fill"""")
        if (fillOpacity != null) append(""" fill-opacity="$fillOpacity"""")
        if (!dash.isNullOrBlank()) append(""" stroke-dasharray="$dash"""")
        if (!filter.isNullOrBlank()) append(""" filter="$filter"""")
    }
}

internal object ServerRendererStyle {
    fun strokeAttrs(primitive: String, weight: String, colorKey: String, colorMap: Map<String, String>, ins: JSONObject, unit: Double): SvgAttrs {
        val colorHint = if (ins.has("color_hint") && !ins.isNull("color_hint")) ins.optString("color_hint") else null
        val color = resolveColor(colorKey, colorHint, colorMap)
        val closedShape = primitive in setOf("circle", "ellipse", "square", "triangle", "polygon")
        val fill = if (closedShape || ins.optBoolean("filled", false)) color else "none"
        val hint = ins.optString("color_hint").lowercase()
        var strokeOpacity = strokeOpacity(weight)
        var fillOpacity: Double? = null
        when {
            hint.containsAny("membrane", "haze", "fog", "mist", "atmosphere", "膜", "霞", "霧", "靄") -> {
                strokeOpacity = min(strokeOpacity, 0.26)
                if (fill != "none") fillOpacity = 0.12
            }
            hint.containsAny("soft light", "柔らかな光", "陽光", "日差し") -> {
                strokeOpacity = min(strokeOpacity, 0.30)
                if (fill != "none") fillOpacity = 0.14
            }
            hint.containsAny("scent", "fragrance", "香り", "匂") -> {
                strokeOpacity = min(strokeOpacity, 0.38)
                if (fill != "none") fillOpacity = 0.20
            }
            hint.containsAny("waiting buds", "開花を待つ蕾", "蕾", "つぼみ") -> {
                strokeOpacity = min(strokeOpacity, 0.72)
                if (fill != "none") fillOpacity = 0.58
            }
            hint.containsAny("five-sense", "五感") -> {
                strokeOpacity = min(strokeOpacity, 0.44)
                if (fill != "none") fillOpacity = 0.18
            }
            "fade directional" in hint || "fade=directional" in hint -> {
                strokeOpacity = min(strokeOpacity, 0.48)
                if (fill != "none") fillOpacity = 0.30
            }
            "fade outward" in hint || "fade=outward" in hint -> {
                strokeOpacity = min(strokeOpacity, 0.40)
                if (fill != "none") fillOpacity = 0.22
            }
        }
        if (hint.containsAny("reflection", "反射", "映り")) {
            strokeOpacity = min(strokeOpacity, 0.52)
        }
        // Both dash patterns are px constants and must be mapped onto the canvas
        // unit exactly as `_stroke_attrs` does with `_scale_dash`, or a pillar
        // canvas keeps a square canvas's dash lengths.
        val scale = unit / 1000.0
        val styleDash = ServerRendererMaterial.scaleDash(dashValue(ins.optString("style", "solid")), scale)
        val textureDash = ServerRendererMaterial.scaleDash(textureDash(weight), scale)
        val filter = when {
            weight in setOf("pencil", "crayon", "chalk", "brush_thick") -> "url(#texture-$weight)"
            else -> null
        }
        return SvgAttrs(
            stroke = color,
            strokeWidth = strokeWidth(weight, unit),
            strokeLinecap = lineCap(weight),
            strokeOpacity = strokeOpacity,
            fill = fill,
            fillOpacity = fillOpacity,
            dash = styleDash ?: textureDash,
            filter = filter,
        )
    }

    fun outlineAttrs(attrs: SvgAttrs, strokeWidth: Double, opacity: Double, dash: String?): SvgAttrs {
        return attrs.copy(strokeWidth = strokeWidth, strokeOpacity = opacity, fill = "none", fillOpacity = null, dash = dash ?: attrs.dash)
    }

    fun strokeWidth(weight: String, unit: Double): Double {
        val base = when (weight) {
            "silverpoint" -> 0.5
            "pencil" -> 1.5
            "rotring" -> 1.0
            "crayon" -> 4.0
            "chalk" -> 3.0
            "brush_thin" -> 3.0
            "brush_thick" -> 8.0
            "burin" -> 3.2
            "drypoint" -> 2.6
            else -> 2.0
        }
        return base * (unit / 1000.0)
    }

    fun strokeOpacity(weight: String): Double = when (weight) {
        "silverpoint" -> 0.72
        "pencil" -> 0.66
        "rotring" -> 0.95
        "crayon" -> 0.78
        "chalk" -> 0.70
        "brush_thin" -> 0.90
        "brush_thick" -> 0.86
        else -> 1.0
    }

    fun lineCap(weight: String): String = when (weight) {
        "silverpoint" -> "butt"
        "rotring" -> "square"
        else -> "round"
    }

    fun dashStyle(style: String): String = when (style) {
        "dashed" -> " stroke-dasharray=\"12,8\""
        "dotted" -> " stroke-dasharray=\"2,6\""
        "dash_dot" -> " stroke-dasharray=\"12,6,2,6\""
        else -> ""
    }

    fun dashValue(style: String): String? = when (style) {
        "dashed" -> "12,8"
        "dotted" -> "2,6"
        "dash_dot" -> "12,6,2,6"
        else -> null
    }

    fun textureDash(weight: String): String? = when (weight) {
        "pencil" -> "1,3"
        "crayon" -> "10,3,2,3"
        "chalk" -> "7,5,1,4"
        else -> null
    }

    fun textureWeights(instructions: JSONArray): Set<String> {
        val result = mutableSetOf<String>()
        for (i in 0 until instructions.length()) {
            val weight = instructions.optJSONObject(i)?.optString("weight") ?: continue
            if (weight in setOf("pencil", "crayon", "chalk", "brush_thick")) result.add(weight)
        }
        return result
    }

    fun filterAttr(weight: String, variation: JSONObject?): String {
        return if (weight in setOf("pencil", "crayon", "chalk", "brush_thick")) " filter=\"url(#texture-$weight)\"" else ""
    }

    fun textureFilterDefs(weights: Set<String>, unit: Double): String = buildString {
        val scale = unit / 1000.0
        val fmt = { v: Double -> ServerRendererGeometry.fmt(v) }
        if ("pencil" in weights) append("""<filter id="texture-pencil" x="-12%" y="-12%" width="124%" height="124%"><feTurbulence type="fractalNoise" baseFrequency="${fmt(0.9 / scale)}" numOctaves="2" seed="11" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="${fmt(0.7 * scale)}"/></filter>""")
        if ("crayon" in weights) append("""<filter id="texture-crayon" x="-18%" y="-18%" width="136%" height="136%"><feTurbulence type="fractalNoise" baseFrequency="${fmt(0.55 / scale)}" numOctaves="3" seed="17" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="${fmt(1.8 * scale)}"/></filter>""")
        if ("chalk" in weights) append("""<filter id="texture-chalk" x="-25%" y="-25%" width="150%" height="150%"><feTurbulence type="fractalNoise" baseFrequency="${fmt(0.75 / scale)}" numOctaves="3" seed="23" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="${fmt(2.2 * scale)}"/><feGaussianBlur stdDeviation="${fmt(0.9 * scale)}"/></filter>""")
        if ("brush_thick" in weights) append("""<filter id="texture-brush_thick" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency="${fmt(0.2 / scale)}" numOctaves="2" seed="31" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="${fmt(1.4 * scale)}"/><feGaussianBlur stdDeviation="${fmt(0.6 * scale)}"/></filter>""")
    }

    fun blurFilterDefs(neededBlurs: Map<String, Double>): String = buildString {
        neededBlurs.forEach { (id, std) ->
            append("""<filter id="$id" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur in="SourceGraphic" stdDeviation="${ServerRendererGeometry.fmt(std)}"/></filter>""")
        }
    }

    fun blurFilterId(variation: JSONObject?, ins: JSONObject, width: Double, height: Double, unit: Double): String? {
        if (variation == null || variation.optString("quality") != "pink") return null
        val std = ServerRendererGeometry.blurStdPx(variation, ins, width, height, unit)
        val amp = variation.optString("amplitude", "medium")
        val stdInt = Math.rint(std * 10.0).toInt()
        return "blur-$amp-$stdInt"
    }

    private fun resolveColor(colorKey: String, colorHint: String?, colorMap: Map<String, String>): String {
        val fallback = colorMap[colorKey] ?: "#111111"
        if (colorHint.isNullOrBlank()) return fallback
        val hint = normLabel(colorHint)
        val desiredHues = hintHues(colorHint)
        if (hint.isBlank() && desiredHues.isEmpty()) return fallback

        var bestScore = 0
        var bestHex = fallback
        for ((key, hexValue) in colorMap) {
            if (!hexValue.startsWith("#")) continue
            val isPalette = key.startsWith("palette:")
            val label = normLabel(key.removePrefix("palette:"))
            var score = 0
            if (label.isNotBlank() && label in hint) score += 6
            for (part in label.split(" ")) {
                if (part.length >= 3 && part in hint) score += 3
            }
            val candidateHue = hueFromHex(hexValue)
            if (candidateHue in desiredHues) score += 4
            for (hue in desiredHues) {
                val tokens = HUE_HINTS[hue].orEmpty()
                if (isPalette && tokens.any { it.lowercase() in label }) score += 2
            }
            if (isPalette && score > 0) score += 1
            if (key == colorKey) score += 1
            if (score > bestScore) {
                bestScore = score
                bestHex = hexValue
            }
        }
        return bestHex
    }

    private fun hintHues(hint: String): Set<String> {
        val normalized = normLabel(hint)
        return HUE_HINTS
            .filterValues { tokens -> tokens.any { token -> token.lowercase() in normalized || token in hint } }
            .keys
    }

    private fun normLabel(value: String): String {
        return value.lowercase().replace(Regex("""[\s:_()'".,/-]+"""), " ").trim()
    }

    private fun hueFromHex(value: String): String? {
        val match = Regex("""#?([0-9a-fA-F]{6})""").matchEntire(value.trim()) ?: return null
        val raw = match.groupValues[1]
        val r = raw.substring(0, 2).toInt(16) / 255.0
        val g = raw.substring(2, 4).toInt(16) / 255.0
        val b = raw.substring(4, 6).toInt(16) / 255.0
        val mx = maxOf(r, g, b)
        val mn = minOf(r, g, b)
        val lightness = (mx + mn) / 2.0
        if (mx - mn < 0.08) {
            if (lightness > 0.82) return "white"
            if (lightness < 0.2) return "black"
            return "gray"
        }
        val hue = when (mx) {
            r -> (60.0 * ((g - b) / (mx - mn)) + 360.0) % 360.0
            g -> 60.0 * ((b - r) / (mx - mn)) + 120.0
            else -> 60.0 * ((r - g) / (mx - mn)) + 240.0
        }
        if (hue >= 15.0 && hue < 45.0) return "orange"
        if (hue >= 45.0 && hue < 75.0) return "yellow"
        if (hue >= 75.0 && hue < 165.0) return "green"
        if (hue >= 165.0 && hue < 255.0) return "blue"
        if (hue >= 255.0 && hue < 315.0) return "purple"
        return "red"
    }

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }
}

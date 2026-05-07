package app.inku.mobile.render

import kotlin.math.min
import org.json.JSONArray
import org.json.JSONObject

internal data class SvgAttrs(
    val stroke: String,
    val strokeWidth: Double,
    val strokeLinecap: String,
    val strokeLinejoin: String = "round",
    val strokeOpacity: Double,
    val fill: String,
    val fillOpacity: Double? = null,
    val dash: String? = null,
    val filter: String? = null,
) {
    fun toSvgAttributes(includeFill: Boolean = true): String = buildString {
        append("""stroke="$stroke" stroke-width="$strokeWidth" stroke-linecap="$strokeLinecap" stroke-linejoin="$strokeLinejoin" stroke-opacity="$strokeOpacity"""")
        if (includeFill) append(""" fill="$fill"""")
        if (fillOpacity != null) append(""" fill-opacity="$fillOpacity"""")
        if (!dash.isNullOrBlank()) append(""" stroke-dasharray="$dash"""")
        if (!filter.isNullOrBlank()) append(""" filter="$filter"""")
    }
}

internal object ServerRendererStyle {
    fun strokeAttrs(primitive: String, weight: String, color: String, ins: JSONObject): SvgAttrs {
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
        val styleDash = dashValue(ins.optString("style", "solid"))
        val textureDash = textureDash(weight)
        val blur = blurFilterId(ins.optJSONObject("variation"))
        val filter = when {
            blur != null -> "url(#$blur)"
            weight in setOf("pencil", "crayon", "chalk", "brush_thick") -> "url(#texture-$weight)"
            else -> null
        }
        return SvgAttrs(
            stroke = color,
            strokeWidth = strokeWidth(weight),
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

    fun strokeWidth(weight: String): Double = when (weight) {
        "hair" -> 0.5
        "pencil" -> 1.5
        "rotring" -> 1.0
        "crayon" -> 4.0
        "chalk" -> 3.0
        "brush_thin" -> 3.0
        "brush_thick" -> 8.0
        "rope" -> 10.0
        else -> 2.0
    }

    fun strokeOpacity(weight: String): Double = when (weight) {
        "hair" -> 0.72
        "pencil" -> 0.66
        "rotring" -> 0.95
        "crayon" -> 0.78
        "chalk" -> 0.70
        "brush_thin" -> 0.90
        "brush_thick" -> 0.86
        "rope" -> 0.88
        else -> 1.0
    }

    fun lineCap(weight: String): String = when (weight) {
        "hair" -> "butt"
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
        "rope" -> "14,5"
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
        val blur = blurFilterId(variation)
        if (blur != null) return " filter=\"url(#$blur)\""
        return if (weight in setOf("pencil", "crayon", "chalk", "brush_thick")) " filter=\"url(#texture-$weight)\"" else ""
    }

    fun textureFilterDefs(weights: Set<String>): String = buildString {
        if ("pencil" in weights) append("""<filter id="texture-pencil" x="-12%" y="-12%" width="124%" height="124%"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="11" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="0.7"/></filter>""")
        if ("crayon" in weights) append("""<filter id="texture-crayon" x="-18%" y="-18%" width="136%" height="136%"><feTurbulence type="fractalNoise" baseFrequency="0.55" numOctaves="3" seed="17" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="1.8"/></filter>""")
        if ("chalk" in weights) append("""<filter id="texture-chalk" x="-25%" y="-25%" width="150%" height="150%"><feTurbulence type="fractalNoise" baseFrequency="0.75" numOctaves="3" seed="23" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="2.2"/><feGaussianBlur stdDeviation="0.9"/></filter>""")
        if ("brush_thick" in weights) append("""<filter id="texture-brush_thick" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency="0.2" numOctaves="2" seed="31" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="1.4"/><feGaussianBlur stdDeviation="0.6"/></filter>""")
    }

    fun blurFilterDefs(): String {
        return """<filter id="blur-fine" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur in="SourceGraphic" stdDeviation="2.0"/></filter><filter id="blur-medium" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur in="SourceGraphic" stdDeviation="6.0"/></filter><filter id="blur-broad" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur in="SourceGraphic" stdDeviation="15.0"/></filter>"""
    }

    fun blurFilterId(variation: JSONObject?): String? {
        if (variation?.optString("quality") != "pink") return null
        val amp = when (variation.optString("amplitude", "medium")) {
            "fine" -> "fine"
            "broad" -> "broad"
            else -> "medium"
        }
        return "blur-$amp"
    }

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }
}

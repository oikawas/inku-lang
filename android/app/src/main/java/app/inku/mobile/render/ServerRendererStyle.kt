package app.inku.mobile.render

import kotlin.math.max
import kotlin.math.min
import org.json.JSONArray
import org.json.JSONObject

private val HUE_HINTS = mapOf(
    "white" to listOf("white", "ivory", "paper", "linen", "blanc", "bianco", "aspro", "白", "胡粉", "象牙", "生成"),
    "black" to listOf("black", "ink", "sumi", "obsidian", "basalt", "skotadi", "黒", "墨", "玄", "暗"),
    "blue" to listOf("blue", "cyan", "azure", "ultramarine", "cobalt", "lapis", "bleu", "azul", "青", "藍", "水色", "空色", "瑠璃"),
    "green" to listOf("green", "verd", "jade", "olive", "cactus", "緑", "青緑", "翡翠", "常磐", "玉", "草"),
    "gray" to listOf("gray", "grey", "silver", "ash", "stone", "granit", "petra", "灰", "鼠", "銀", "石"),
    "red" to listOf("red", "rose", "pink", "carmine", "cinnabar", "terra", "rosa", "vermilion", "赤", "朱", "紅", "桜", "桃", "薔薇"),
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
    internal val weightToStrokeWidth = mapOf(
        "silverpoint" to 0.5,
        "pencil" to 1.5,
        "pen" to 2.0,
        "rotring" to 1.0,
        "crayon" to 4.0,
        "chalk" to 3.0,
        "brush_thin" to 3.0,
        "brush_thick" to 8.0,
        "burin" to 3.2,
        "drypoint" to 2.6,
        "computer" to 2.0,
    )
    internal val thinnessToWidthScale = mapOf(
        null to 1.0,
        "fine" to 0.6,
        "extra_fine" to 0.35,
    )

    fun strokeAttrs(weight: String, colorKey: String, colorMap: Map<String, String>, ins: JSONObject, unit: Double): SvgAttrs {
        val colorHint = if (ins.has("color_hint") && !ins.isNull("color_hint")) ins.optString("color_hint") else null
        val color = resolveColor(colorKey, colorHint, colorMap)
        // One judgement, read once, the way `_stroke_attrs` reads it: `do_fill =
        // _fills_interior(ins)` settles both the `fill` value and every branch of
        // `fill-opacity` below. This used to be decided here a second time, out of
        // "does the primitive have an inside, or was `filled` written" -- a set that
        // knew nothing about `surface.texture` and did not hold `cloudform`, so the
        // same request took two roads depending on how it was spelt (ledger I-298).
        val doFill = ServerRendererGeometry.fillsInterior(ins)
        val fill = if (doFill) color else "none"
        // The level is read off the RAW hint, before the lowercasing: the server
        // reads it before `_norm_label`, and a normalisation that replaces the
        // dot delivers "0 3000" to the consumer with the value gone.
        val rawHint = ins.optString("color_hint")
        val hint = rawHint.lowercase()
        var strokeOpacity = strokeOpacity(weight)
        var fillOpacity: Double? = null
        when {
            hint.containsAny("membrane", "haze", "fog", "mist", "atmosphere", "膜", "霞", "霧", "靄") -> {
                strokeOpacity = min(strokeOpacity, 0.26)
                if (doFill) fillOpacity = 0.12
            }
            hint.containsAny("soft light", "柔らかな光", "陽光", "日差し") -> {
                strokeOpacity = min(strokeOpacity, 0.30)
                if (doFill) fillOpacity = 0.14
            }
            hint.containsAny("scent", "fragrance", "香り", "匂") -> {
                strokeOpacity = min(strokeOpacity, 0.38)
                if (doFill) fillOpacity = 0.20
            }
            hint.containsAny("waiting buds", "開花を待つ蕾", "蕾", "つぼみ") -> {
                strokeOpacity = min(strokeOpacity, 0.72)
                if (doFill) fillOpacity = 0.58
            }
            hint.containsAny("five-sense", "五感") -> {
                strokeOpacity = min(strokeOpacity, 0.44)
                if (doFill) fillOpacity = 0.18
            }
            // engine 24: the member's own ceiling when the expansion wrote one,
            // the group-wide constant when it did not -- a degenerate group, or
            // a fading instruction that never went through an arrangement.
            "fade directional" in hint || "fade=directional" in hint -> {
                val level = ServerRendererFade.levelFromHint(rawHint)
                val ceiling = level ?: 0.48
                strokeOpacity = min(strokeOpacity, ceiling)
                if (doFill) {
                    fillOpacity = if (level == null) {
                        0.30
                    } else {
                        ServerRendererFade.round4(ceiling * ServerRendererFade.FILL_RATIO_DIRECTIONAL)
                    }
                }
            }
            "fade outward" in hint || "fade=outward" in hint -> {
                val level = ServerRendererFade.levelFromHint(rawHint)
                val ceiling = level ?: 0.40
                strokeOpacity = min(strokeOpacity, ceiling)
                if (doFill) {
                    fillOpacity = if (level == null) {
                        0.22
                    } else {
                        ServerRendererFade.round4(ceiling * ServerRendererFade.FILL_RATIO_OUTWARD)
                    }
                }
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
            strokeWidth = strokeWidth(weight, unit, ins.optString("thinness").takeIf { it in thinnessToWidthScale }),
            strokeLinecap = lineCap(weight),
            strokeOpacity = strokeOpacity,
            fill = fill,
            fillOpacity = fillOpacity,
            dash = styleDash ?: textureDash,
            filter = filter,
        )
    }

    // engine 28: a null dash strips the body's own broken quality (the tool's
    // `textureDash`, e.g. pencil "1,3") instead of inheriting it. While this
    // helper always overwrote the value there was nothing to strip; now that
    // contact decides where the outline exists, an inherited pattern would cut
    // the fragments a second time on a fixed cadence -- exactly the regularity
    // the fragments are there to remove.
    fun outlineAttrs(attrs: SvgAttrs, strokeWidth: Double, opacity: Double, dash: String?): SvgAttrs {
        return attrs.copy(strokeWidth = strokeWidth, strokeOpacity = opacity, fill = "none", fillOpacity = null, dash = dash)
    }

    fun strokeWidth(weight: String, unit: Double, thinness: String? = null): Double {
        val base = weightToStrokeWidth[weight] ?: weightToStrokeWidth.getValue("pen")
        val widthScale = thinnessToWidthScale[thinness] ?: thinnessToWidthScale.getValue(null)
        val minimum = weightToStrokeWidth.values.minOrNull() ?: error("stroke width table is empty")
        return max(base * widthScale, minimum) * (unit / 1000.0)
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

    // The material intensity the server runs at (`MATERIAL_INTENSITY["s1"]`).
    // `_texture_filter_xml` multiplies the spec by these before it writes the
    // attribute, so a port that writes the bare spec draws a fainter grain than
    // the server does at every tool.
    private const val TEXTURE_DISPLACEMENT_GAIN = 2.8
    private const val TEXTURE_BLUR_GAIN = 1.6

    fun textureFilterDefs(weights: Set<String>, unit: Double): String = buildString {
        val scale = unit / 1000.0
        val fmt = { v: Double -> ServerRendererGeometry.fmt(v) }
        val disp = { spec: Double -> fmt(spec * scale * TEXTURE_DISPLACEMENT_GAIN) }
        val blur = { spec: Double -> fmt(spec * scale * TEXTURE_BLUR_GAIN) }
        if ("pencil" in weights) append("""<filter id="texture-pencil" x="-12%" y="-12%" width="124%" height="124%"><feTurbulence type="fractalNoise" baseFrequency="${fmt(0.9 / scale)}" numOctaves="2" seed="11" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="${disp(0.7)}"/></filter>""")
        if ("crayon" in weights) append("""<filter id="texture-crayon" x="-18%" y="-18%" width="136%" height="136%"><feTurbulence type="fractalNoise" baseFrequency="${fmt(0.55 / scale)}" numOctaves="3" seed="17" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="${disp(1.8)}"/></filter>""")
        // engine 22 dropped chalk's blur from 0.25 to... rather, the spec from
        // 0.9 to 0.25: the blur was the largest of any tool and it was rubbing
        // out chalk's own grain (5.26% against crayon's 13.59%). At 0.25 the
        // grain comes back level with crayon and chalk keeps a trace of the
        // softness the blur was there for.
        if ("chalk" in weights) append("""<filter id="texture-chalk" x="-25%" y="-25%" width="150%" height="150%"><feTurbulence type="fractalNoise" baseFrequency="${fmt(0.75 / scale)}" numOctaves="3" seed="23" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="${disp(2.2)}"/><feGaussianBlur stdDeviation="${blur(0.25)}"/></filter>""")
        if ("brush_thick" in weights) append("""<filter id="texture-brush_thick" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency="${fmt(0.2 / scale)}" numOctaves="2" seed="31" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="${disp(1.4)}"/><feGaussianBlur stdDeviation="${blur(0.6)}"/></filter>""")
        // The server's table has a fifth entry, `drypoint` (a blur and no
        // turbulence), but nothing here ever reaches it: `textureWeights` and
        // `filterAttr` both list four tools, so a definition for it would be
        // written by no call and read by none. Left out rather than added dead.
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

    val DEFAULT_COLOR_MAP = mapOf(
        "white" to "#ffffff",
        "black" to "#111111",
        "blue" to "#2c3e91",
        "red" to "#a2342a",
        "green" to "#2f6b3a",
        "gray" to "#888888",
        "yellow" to "#a18308",
        "orange" to "#a95a00",
        "purple" to "#583a84",
    )

    fun computeColorAssignment(
        catalogMap: Map<String, String>,
        renderSeed: Long?,
        catalogId: String = "default"
    ): Map<String, String> {
        val cmap = DEFAULT_COLOR_MAP + catalogMap

        val seenHex = mutableSetOf<String>()
        val paletteHexes = mutableListOf<String>()
        for ((key, hex) in catalogMap) {
            if (key.startsWith("palette:")) {
                val normalized = hex.lowercase()
                if (seenHex.add(normalized)) {
                    paletteHexes.add(normalized)
                }
            }
        }

        data class AchromaticItem(val L: Double, val hex: String)
        val achromaticStock = mutableListOf<AchromaticItem>()
        val chromaticBands = mapOf(
            "red" to mutableListOf<String>(),
            "orange" to mutableListOf<String>(),
            "yellow" to mutableListOf<String>(),
            "green" to mutableListOf<String>(),
            "blue" to mutableListOf<String>(),
            "purple" to mutableListOf<String>(),
        )
        data class ChromaticHueItem(val hue: Double, val hex: String)
        val chromaticHues = mutableListOf<ChromaticHueItem>()

        for (hex in paletteHexes) {
            val oklch = oklchFromHex(hex)
            if (oklch.c < 0.035) {
                achromaticStock.add(AchromaticItem(oklch.l, hex))
            } else {
                val band = when {
                    oklch.h >= 345.0 || oklch.h < 50.0 -> "red"
                    oklch.h >= 50.0 && oklch.h < 80.0 -> "orange"
                    oklch.h >= 80.0 && oklch.h < 137.0 -> "yellow"
                    oklch.h >= 137.0 && oklch.h < 200.0 -> "green"
                    oklch.h >= 200.0 && oklch.h < 280.0 -> "blue"
                    oklch.h >= 280.0 && oklch.h < 345.0 -> "purple"
                    else -> "red"
                }
                chromaticBands.getValue(band).add(hex)
                chromaticHues.add(ChromaticHueItem(oklch.h, hex))
            }
        }

        achromaticStock.sortBy { it.L }

        val assignment = mutableMapOf<String, String>()

        val achromaticColors = listOf("black", "gray", "white")
        for (color in achromaticColors) {
            val targetHex = (cmap[color] ?: DEFAULT_COLOR_MAP.getValue(color)).lowercase()
            val exactIndex = achromaticStock.indexOfFirst { it.hex.equals(targetHex, ignoreCase = true) }
            if (exactIndex != -1) {
                assignment[color] = achromaticStock.removeAt(exactIndex).hex
            }
        }

        for (color in achromaticColors) {
            if (color in assignment) continue
            val targetHex = (cmap[color] ?: DEFAULT_COLOR_MAP.getValue(color)).lowercase()
            val targetL = oklchFromHex(targetHex).l

            if (achromaticStock.isNotEmpty()) {
                val bestItem = achromaticStock.minWithOrNull(
                    Comparator { a, b ->
                        val diffA = Math.abs(a.L - targetL)
                        val diffB = Math.abs(b.L - targetL)
                        val cmp = diffA.compareTo(diffB)
                        if (cmp != 0) cmp else a.hex.compareTo(b.hex)
                    }
                )!!
                assignment[color] = bestItem.hex
                achromaticStock.remove(bestItem)
            } else {
                assignment[color] = cmap[color] ?: DEFAULT_COLOR_MAP.getValue(color)
            }
        }

        val bandCenters = mapOf(
            "red" to 27.5,
            "orange" to 65.0,
            "yellow" to 108.5,
            "green" to 168.5,
            "blue" to 240.0,
            "purple" to 312.5
        )

        fun selectBySeed(candidates: List<String>, abstractColor: String): String {
            val sortedCandidates = candidates.distinct().sorted()
            if (sortedCandidates.size == 1) return sortedCandidates[0]
            // Unsigned, because the Python side hashes `f"{render_seed}|..."`
            // with an int that has no sign bit. Every seed below 2^63 prints the
            // same either way; a touch seed derived from words does not.
            val seedStr = renderSeed?.let { java.lang.Long.toUnsignedString(it) } ?: "None"
            val payload = "$seedStr|$catalogId|$abstractColor"
            val md = java.security.MessageDigest.getInstance("SHA-256")
            val digest = md.digest(payload.toByteArray(Charsets.UTF_8))
            val buffer = java.nio.ByteBuffer.wrap(digest, 0, 8).order(java.nio.ByteOrder.BIG_ENDIAN)
            val u64Val = buffer.long
            val index = java.lang.Long.remainderUnsigned(u64Val, sortedCandidates.size.toLong()).toInt()
            return sortedCandidates[index]
        }

        fun angularDistance(h1: Double, h2: Double): Double {
            val diff = Math.abs(h1 - h2) % 360.0
            return Math.min(diff, 360.0 - diff)
        }

        val chromaticColors = listOf("red", "orange", "yellow", "green", "blue", "purple")
        for (color in chromaticColors) {
            val candidates = chromaticBands.getValue(color)
            if (candidates.isNotEmpty()) {
                assignment[color] = selectBySeed(candidates, color)
            } else if (chromaticHues.isNotEmpty()) {
                val center = bandCenters.getValue(color)
                val bestItem = chromaticHues.minWithOrNull(
                    Comparator { a, b ->
                        val distA = angularDistance(a.hue, center)
                        val distB = angularDistance(b.hue, center)
                        val cmp = distA.compareTo(distB)
                        if (cmp != 0) cmp else a.hex.compareTo(b.hex)
                    }
                )!!
                assignment[color] = bestItem.hex
            } else {
                assignment[color] = cmap[color] ?: DEFAULT_COLOR_MAP.getValue(color)
            }
        }

        return assignment
    }

    private val HUE_ORDER = listOf("red", "orange", "yellow", "green", "blue", "purple", "white", "black", "gray")

    fun resolveColor(colorKey: String, colorHint: String?, colors: Map<String, String>): String {
        val fallback = colors[colorKey] ?: DEFAULT_COLOR_MAP[colorKey] ?: "#111111"
        if (colorHint.isNullOrBlank()) return fallback

        val hintTrimmed = colorHint.trim()
        val asciiWords = Regex("[0-9a-z]+").findAll(hintTrimmed.lowercase()).map { it.value }.toSet()

        val matchedHues = mutableSetOf<String>()
        for ((hue, hints) in HUE_HINTS) {
            for (pattern in hints) {
                val patLower = pattern.lowercase()
                val matches = if (patLower.matches(Regex("^[a-z]+$"))) {
                    patLower in asciiWords
                } else {
                    hintTrimmed.contains(pattern, ignoreCase = true)
                }
                if (matches) {
                    matchedHues.add(hue)
                    break
                }
            }
        }

        if (matchedHues.size == 1 && "brown" in matchedHues) {
            return colors["orange"] ?: DEFAULT_COLOR_MAP.getValue("orange")
        }

        for (hue in HUE_ORDER) {
            if (hue in matchedHues && hue != "brown") {
                return colors[hue] ?: fallback
            }
        }

        return fallback
    }

    internal data class Oklch(val l: Double, val c: Double, val h: Double)

    internal fun oklchFromHex(hex: String): Oklch {
        val trimmed = hex.trim().removePrefix("#")
        if (trimmed.length != 6) return Oklch(0.0, 0.0, 0.0)
        val rRaw = trimmed.substring(0, 2).toInt(16) / 255.0
        val gRaw = trimmed.substring(2, 4).toInt(16) / 255.0
        val bRaw = trimmed.substring(4, 6).toInt(16) / 255.0

        val r = if (rRaw > 0.04045) Math.pow((rRaw + 0.055) / 1.055, 2.4) else rRaw / 12.92
        val g = if (gRaw > 0.04045) Math.pow((gRaw + 0.055) / 1.055, 2.4) else gRaw / 12.92
        val b = if (bRaw > 0.04045) Math.pow((bRaw + 0.055) / 1.055, 2.4) else bRaw / 12.92

        val l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
        val m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
        val s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

        val lCbrt = Math.cbrt(l)
        val mCbrt = Math.cbrt(m)
        val sCbrt = Math.cbrt(s)

        val L = 0.2104542553 * lCbrt + 0.7936177850 * mCbrt - 0.0040720468 * sCbrt
        val a = 1.9779984951 * lCbrt - 2.4285922050 * mCbrt + 0.4505937099 * sCbrt
        val bVal = 0.0259040371 * lCbrt + 0.7827717662 * mCbrt - 0.8086757660 * sCbrt

        val C = Math.hypot(a, bVal)
        val Hdeg = Math.toDegrees(Math.atan2(bVal, a))
        val H = (Hdeg % 360.0 + 360.0) % 360.0

        return Oklch(L, C, H)
    }

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }
}

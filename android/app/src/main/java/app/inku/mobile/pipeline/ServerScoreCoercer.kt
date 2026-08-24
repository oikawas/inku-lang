package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject

internal object ServerScoreCoercer {
    /**
     * The surface vocabulary, in the order `SurfaceTexture` declares it in `schema.py`.
     *
     * Named and ordered rather than written inline because the schema offered to Stage 2
     * holds the same list, and a model only ever writes what the destination field held
     * out to it: while `solid` was missing from either copy, the local road could not
     * say 塗り at all. The two copies are measured against each other.
     */
    internal val surfaceTextures: Set<String> = setOf(
        "none", "solid", "stipple", "hatch", "crosshatch",
        "aquatint", "grain", "wash", "bleed", "paper_grain",
    )

    private data class FieldSpec(
        val name: String,
        val defaultValue: Any,
        val fallbacks: List<String> = emptyList(),
        val coerce: (Any?) -> Any? = { it },
    )

    private val primitiveSpecs: Map<String, List<FieldSpec>> = mapOf(
        "line" to listOf(
            FieldSpec("from", listOf(0.1, 0.5), coerce = ::asCoord),
            FieldSpec("to", listOf(0.9, 0.5), coerce = ::asCoord),
        ),
        "circle" to listOf(
            FieldSpec("center", listOf(0.5, 0.5), fallbacks = listOf("position"), coerce = ::asCoord),
            FieldSpec("radius", 0.15, coerce = ::asPositiveFloat),
        ),
        "ellipse" to listOf(
            FieldSpec("center", listOf(0.5, 0.5), fallbacks = listOf("position"), coerce = ::asCoord),
            FieldSpec("size", listOf(0.3, 0.3), coerce = ::asPositiveSize),
        ),
        "arc" to listOf(
            FieldSpec("center", listOf(0.5, 0.5), fallbacks = listOf("position"), coerce = ::asCoord),
            FieldSpec("radius", 0.15, coerce = ::asPositiveFloat),
            FieldSpec("angle_start", 0.0, coerce = ::asFloat),
            FieldSpec("angle_end", 270.0, coerce = ::asFloat),
        ),
        "polygon" to listOf(
            FieldSpec("center", listOf(0.5, 0.5), fallbacks = listOf("position"), coerce = ::asCoord),
            FieldSpec("radius", 0.12, coerce = ::asPositiveFloat),
            FieldSpec("sides", 5, coerce = ::asPolygonSides),
        ),
        "square" to listOf(
            FieldSpec("position", listOf(0.35, 0.35), fallbacks = listOf("center"), coerce = ::asCoord),
            FieldSpec("size", listOf(0.3, 0.3), coerce = ::asPositiveSize),
        ),
        "triangle" to listOf(
            FieldSpec("position", listOf(0.35, 0.35), fallbacks = listOf("center"), coerce = ::asCoord),
            FieldSpec("size", listOf(0.3, 0.3), coerce = ::asPositiveSize),
        ),
        "cloudform" to listOf(
            FieldSpec("center", listOf(0.5, 0.5), fallbacks = listOf("position"), coerce = ::asCoord),
            FieldSpec("size", listOf(0.3, 0.3), coerce = ::asPositiveSize),
        ),
    )

    private val supportedPrimitives = primitiveSpecs.keys

    fun coerceInstruction(
        source: JSONObject,
        ddl: String,
        background: String,
        detectColorKey: (String, String) -> String,
        detectWeightKey: (String) -> String,
        visibleForeground: (String, String) -> String,
    ): JSONObject {
        val primitive = source.optString("primitive", "line").takeIf { it in supportedPrimitives } ?: "line"
        val rawHasRadius = source.has("radius") && !source.isNull("radius")
        val rawHasSize = source.has("size") && !source.isNull("size")
        val data = ServerScoreCompat.migrateInstruction(JSONObject(source.toString())).put("primitive", primitive)
        data.put("color", data.optString("color", "black").takeIf { it in setOf("white", "black", "blue", "red", "green", "gray", "yellow", "orange", "purple") } ?: "black")
        data.put("weight", data.optString("weight", "pen").takeIf { it in setOf("silverpoint", "pencil", "pen", "rotring", "crayon", "chalk", "brush_thin", "brush_thick", "burin", "drypoint", "computer") } ?: "pen")
        if (data.has("thinness")) {
            val thinness = data.optString("thinness").takeIf { it in setOf("fine", "extra_fine") }
            if (thinness != null) data.put("thinness", thinness) else data.remove("thinness")
        }
        data.put("style", data.optString("style", "solid").ifBlank { "solid" })
        if (!data.has("filled")) data.put("filled", false)
        if (data.has("mode")) {
            val mode = data.optString("mode").takeIf { it in setOf("additive", "carve") } ?: "additive"
            data.put("mode", mode)
        }
        if (data.has("carve_depth")) {
            val cd = data.optString("carve_depth").takeIf { it in setOf("light", "half", "bright") }
            if (cd != null) data.put("carve_depth", cd) else data.remove("carve_depth")
        }
        data.optJSONObject("arrangement")?.let { data.put("arrangement", normalizeArrangement(it)) }
        data.optJSONObject("variation")?.let { data.put("variation", normalizeVariation(it)) }
        data.optJSONObject("surface")?.let { data.put("surface", normalizeSurface(it)) }
        data.optJSONObject("relation")?.let { data.put("relation", normalizeRelation(it)) }

        primitiveSpecs.getValue(primitive).forEach { spec ->
            val value = coercedField(data, spec)
            data.put(spec.name, toJsonValue(value ?: spec.defaultValue))
        }
        applyStatedSize(primitive, data, ddl, rawHasRadius, rawHasSize)
        postCoerce(primitive, data)
        applyMaterialHint(data, ddl)
        applyVariationHint(primitive, data, ddl)
        foldFillAndSurface(primitive, data)

        // Strip unknown extra fields to comply with ConfigDict(extra="forbid")
        val allowedKeys = setOf(
            "primitive", "note", "from", "to", "center", "radius", "sides", "position", "size",
            "angle_start", "angle_end", "rotation", "filled", "style", "weight", "thinness",
            "mode", "carve_depth", "color", "color_hint", "variation", "arrangement",
            "at", "relation", "surface",
        )
        val keysToRemove = data.keys().asSequence().filter { it !in allowedKeys }.toList()
        keysToRemove.forEach { data.remove(it) }

        return data
    }

    private fun coercedField(data: JSONObject, spec: FieldSpec): Any? {
        if (data.has(spec.name)) {
            spec.coerce(data.opt(spec.name))?.let { return it }
        }
        spec.fallbacks.forEach { fallback ->
            if (data.has(fallback)) {
                spec.coerce(data.opt(fallback))?.let { return it }
            }
        }
        return null
    }

    private fun applyStatedSize(
        primitive: String,
        data: JSONObject,
        ddl: String,
        rawHasRadius: Boolean,
        rawHasSize: Boolean,
    ) {
        if ((primitive == "circle" && rawHasRadius) || (primitive == "ellipse" && rawHasSize)) return
        if (primitive != "circle" && primitive != "ellipse") return
        val clauses = ServerDdlText.splitClauses(ddl).filter { clause ->
            ServerScoreRepairFactory.primitiveFromClause(clause) == primitive && isSmallMarkClause(clause)
        }
        if (clauses.size != 1) return
        if (primitive == "circle") {
            data.put("radius", ServerScoreSemantics.detectRadius(clauses.single()) ?: 0.038)
        } else {
            data.put("size", JSONArray(listOf(0.06, 0.032)))
        }
    }

    private fun isSmallMarkClause(clause: String): Boolean {
        val lower = clause.lowercase()
        val hasSize = listOf("小さ", "細い").any { it in clause } ||
            listOf("tiny", "small", "little", "thin").any { it in lower }
        val hasKind = listOf("点", "円", "楕円").any { it in clause } ||
            listOf("dot", "point", "circle", "ellipse", "oval").any { it in lower }
        return hasSize && hasKind
    }

    private fun postCoerce(primitive: String, data: JSONObject) {
        if (primitive == "arc" && kotlin.math.abs(data.optDouble("angle_start") - data.optDouble("angle_end")) < 1e-6) {
            data.put("angle_end", (data.optDouble("angle_start") + 270.0) % 360.0)
        }
    }

    private fun normalizeArrangement(source: JSONObject): JSONObject {
        val result = JSONObject(source.toString())
        val layout = result.optString("layout", "horizontal").takeIf { it in setOf("horizontal", "vertical", "radial", "scatter", "grid") } ?: "horizontal"
        val maxCount = if (layout == "grid") 2000 else 1000
        result.put("count", result.optInt("count", 1).coerceIn(1, maxCount))
        val groupSize = result.optInt("group_size", 1)
        if (result.has("group_size") && groupSize > 1) {
            result.put("group_size", groupSize)
        } else {
            result.remove("group_size")
        }
        result.put("layout", layout)
        if (layout == "grid") {
            if (result.has("rows")) result.put("rows", result.optInt("rows", 1).coerceIn(1, 64))
            if (result.has("cols")) result.put("cols", result.optInt("cols", 1).coerceIn(1, 64))
            result.put("jitter", result.optDouble("jitter", 0.12).coerceIn(0.0, 1.0))
        }
        result.put("path", result.optString("path", "none").takeIf { it in setOf("none", "diagonal", "wave", "top_to_bottom", "left_to_right", "right_half") } ?: "none")
        if (!result.has("color_cycle")) result.put("color_cycle", JSONArray())
        result.put("margin", result.optDouble("margin", 0.1).coerceIn(0.0, 0.45))
        result.put("density", result.optString("density", "none").takeIf { it in setOf("none", "low", "medium", "high") } ?: "none")
        if (result.has("cluster_count")) result.put("cluster_count", result.optInt("cluster_count", 1).coerceIn(1, 12))
        result.put("fade", result.optString("fade", "none").takeIf { it in setOf("none", "outward", "directional") } ?: "none")
        result.put("preserve_space", result.optBoolean("preserve_space", false))
        result.put("rhythm_spacing", result.optString("rhythm_spacing", "none").takeIf { it in setOf("none", "syncopated", "accelerando", "loose") } ?: "none")
        return result
    }

    private fun normalizeVariation(source: JSONObject): JSONObject {
        val result = JSONObject(source.toString())
        result.put("amplitude", result.optString("amplitude", "medium").takeIf { it in setOf("fine", "medium", "broad") } ?: "medium")
        result.put("frequency", result.optString("frequency", "medium").takeIf { it in setOf("slow", "medium", "high") } ?: "medium")
        result.put("quality", result.optString("quality", "none").takeIf { it in setOf("none", "white", "perlin", "pink", "wave") } ?: "none")
        if (!result.has("dimensions")) result.put("dimensions", JSONArray())
        return result
    }

    /**
     * Say one interior state one way, whichever way it arrived.
     *
     * Ported from `_with_fill_as_a_surface_word` in `coerce/normalize.py`. A fill used
     * to be the one surface word with a road of its own -- eight of the nine quality
     * words landed in `surface.texture` and 塗り landed in the boolean `filled` -- and
     * that road did not carry. The word now goes where the others go, and this makes
     * the two statements one:
     *
     * - `texture="solid"` derives `filled=true`, so a Score written the new way still
     *   draws on every reader that only knows the boolean;
     * - `filled=true` with no surface of its own derives `texture="solid"`, so the works
     *   already saved say their interior in the same vocabulary the new ones do.
     *
     * Closed shapes only, for the reason the server gives: a line has no interior, so
     * neither statement means anything on one, and inventing a surface there would put
     * back exactly the invisible surfaces the port takes away elsewhere.
     */
    private fun foldFillAndSurface(primitive: String, data: JSONObject) {
        if (primitive !in ScoreGeometryPolicy.closedShapes) return
        val surface = data.optJSONObject("surface")
        val texture = surface?.optString("texture", "none")
        if (texture == "solid") {
            if (!data.optBoolean("filled", false)) data.put("filled", true)
            return
        }
        if (!data.optBoolean("filled", false)) return
        if (surface != null && texture != "none") return
        // Built field by field rather than through `normalizeSurface`, which reads the
        // texture allowlist: the derived word must not be run back through the gate that
        // is only there to judge what Stage 2 wrote.
        val solid = if (surface == null) {
            JSONObject()
                .put("texture", "solid")
                .put("density", 0.35)
                .put("scale", 0.35)
                .put("opacity", 0.28)
                .put("bleed", 0.0)
                .put("direction", "none")
                .put("spacing_gradient", "none")
                .put("tone_steps", 3)
        } else {
            JSONObject(surface.toString()).put("texture", "solid")
        }
        data.put("surface", solid)
    }

    private fun normalizeSurface(source: JSONObject): JSONObject {
        val result = JSONObject(source.toString())
        result.put("texture", result.optString("texture", "none").takeIf { it in surfaceTextures } ?: "none")
        result.put("density", result.optDouble("density", 0.35).coerceIn(0.0, 1.0))
        result.put("scale", result.optDouble("scale", 0.35).coerceIn(0.0, 1.0))
        result.put("opacity", result.optDouble("opacity", 0.28).coerceIn(0.0, 1.0))
        result.put("bleed", result.optDouble("bleed", 0.0).coerceIn(0.0, 1.0))
        result.put("direction", result.optString("direction", "none").takeIf { it in setOf("none", "horizontal", "vertical", "diagonal_rising", "diagonal_falling") } ?: "none")
        result.put("spacing_gradient", result.optString("spacing_gradient", "none").takeIf { it in setOf("none", "coarse_to_dense", "dense_to_coarse") } ?: "none")
        result.put("tone_steps", result.optInt("tone_steps", 3).coerceIn(2, 4))
        return result
    }

    private fun normalizeRelation(source: JSONObject): JSONObject {
        val result = JSONObject(source.toString())
        val type = result.optString("type", "along").takeIf { it in setOf("along", "not_touching", "cutting", "between", "touching") } ?: "along"
        result.put("type", type)
        result.put("gap", result.optString("gap", "medium").takeIf { it in setOf("narrow", "medium", "wide") } ?: "medium")
        if (type == "touching") {
            result.put("contact", "both_ends")
        } else {
            result.remove("contact")
        }
        return result
    }

    private fun applyMaterialHint(data: JSONObject, ddl: String) {
        if (ddl.isBlank() || data.optString("weight", "pen") != "pen") return
        val weight = materialWeightHint(ddl) ?: return
        data.put("weight", weight)
        val note = "material inferred from DDL: $weight"
        val hint = data.optString("color_hint", "").takeIf { it.isNotBlank() }
        data.put("color_hint", if (hint == null) note else "$hint; $note")
    }

    internal fun materialWeightHint(ddl: String): String? {
        val lower = ddl.lowercase()
        return materialWeightHints.firstOrNull { (markers, _) ->
            markers.any { it.lowercase() in lower }
        }?.second
    }

    private fun applyVariationHint(primitive: String, data: JSONObject, ddl: String) {
        if (ddl.isBlank() || data.optJSONObject("variation") != null) return
        val lower = ddl.lowercase()
        val variation = when {
            listOf("ゆっくり揺れる", "ゆっくり波打つ").any { it in ddl } || "slow" in lower ->
                JSONObject()
                    .put("amplitude", "medium")
                    .put("frequency", "slow")
                    .put("quality", "wave")
                    .put("dimensions", JSONArray(listOf("position_x", "position_y")))
            listOf("細かく揺れる", "細かく震える", "震える").any { it in ddl } || "trembling" in lower ->
                JSONObject()
                    .put("amplitude", "fine")
                    .put("frequency", "medium")
                    .put("quality", "perlin")
                    .put("dimensions", JSONArray(if (primitive == "line") listOf("position_y") else listOf("position_x", "position_y")))
            listOf("滲む", "にじむ", "境界が滲む").any { it in ddl } || "blurring" in lower ->
                JSONObject()
                    .put("amplitude", "medium")
                    .put("frequency", "medium")
                    .put("quality", "pink")
                    .put("dimensions", JSONArray(listOf("position_x", "position_y")))
            else -> null
        }
        if (variation != null) data.put("variation", variation)
    }

    private fun asCoord(value: Any?): List<Double>? {
        if (value is JSONArray && value.length() >= 2) {
            return listOf(value.optDoubleOrNull(0) ?: return null, value.optDoubleOrNull(1) ?: return null)
        }
        if (value is Number) {
            val number = value.toDouble()
            return listOf(number, number)
        }
        return null
    }

    private fun asPositiveFloat(value: Any?): Double? {
        val number = asDouble(value) ?: return null
        return number.takeIf { it > 0.0 }
    }

    private fun asPositiveSize(value: Any?): List<Double>? {
        val coord = asCoord(value) ?: return null
        return coord.takeIf { it[0] > 0.0 && it[1] > 0.0 }
    }

    private fun asFloat(value: Any?): Double? = asDouble(value)

    private fun asPolygonSides(value: Any?): Int? {
        return when (value) {
            is Number -> value.toInt().coerceIn(5, 8)
            is String -> value.toIntOrNull()?.coerceIn(5, 8)
            else -> null
        }
    }

    private fun asDouble(value: Any?): Double? {
        return when (value) {
            is Number -> value.toDouble()
            is String -> value.toDoubleOrNull()
            else -> null
        }
    }

    private fun toJsonValue(value: Any): Any {
        return when (value) {
            is List<*> -> JSONArray(value)
            else -> value
        }
    }

    private fun JSONArray.optDoubleOrNull(index: Int): Double? {
        if (index < 0 || index >= length() || isNull(index)) return null
        return when (val value = opt(index)) {
            is Number -> value.toDouble()
            is String -> value.toDoubleOrNull()
            else -> null
        }
    }

    private val materialWeightHints = listOf(
        listOf("ロットリング", "rotring") to "rotring",
        listOf("鉛筆", "pencil") to "pencil",
        listOf("クレヨン", "crayon") to "crayon",
        listOf("チョーク", "chalk") to "chalk",
        listOf("細筆", "fine-brush", "fine brush") to "brush_thin",
        listOf("太筆", "thick-brush", "thick brush", "厚塗り", "油絵") to "brush_thick",
        listOf("水墨", "墨", "ink-wash", "ink wash") to "brush_thin",
        listOf("ビュラン", "burin") to "burin",
        listOf("ドライポイント", "drypoint") to "drypoint",
        listOf("コンピュータ", "computer") to "computer",
    )
}

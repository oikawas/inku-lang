package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject

internal object ServerScoreCoercer {
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
        val data = JSONObject(source.toString()).put("primitive", primitive)
        data.put("color", data.optString("color", "black").takeIf { it in setOf("white", "black", "blue", "red", "green", "gray") } ?: "black")
        data.put("weight", data.optString("weight", "pen").takeIf { it in setOf("hair", "pencil", "pen", "rotring", "crayon", "chalk", "brush_thin", "brush_thick", "rope") } ?: "pen")
        data.put("style", data.optString("style", "solid").ifBlank { "solid" })
        if (!data.has("filled")) data.put("filled", false)
        data.optJSONObject("arrangement")?.let { data.put("arrangement", normalizeArrangement(it)) }
        data.optJSONObject("variation")?.let { data.put("variation", normalizeVariation(it)) }

        primitiveSpecs.getValue(primitive).forEach { spec ->
            val value = coercedField(data, spec)
            data.put(spec.name, toJsonValue(value ?: spec.defaultValue))
        }
        postCoerce(primitive, data)
        applyMaterialHint(data, ddl)
        applyVariationHint(primitive, data, ddl)
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

    private fun postCoerce(primitive: String, data: JSONObject) {
        if (primitive == "arc" && kotlin.math.abs(data.optDouble("angle_start") - data.optDouble("angle_end")) < 1e-6) {
            data.put("angle_end", (data.optDouble("angle_start") + 270.0) % 360.0)
        }
    }

    private fun normalizeArrangement(source: JSONObject): JSONObject {
        val result = JSONObject(source.toString())
        result.put("count", result.optInt("count", 1).coerceIn(1, 1000))
        result.put("layout", result.optString("layout", "horizontal").takeIf { it in setOf("horizontal", "vertical", "radial", "scatter") } ?: "horizontal")
        result.put("path", result.optString("path", "none").takeIf { it in setOf("none", "diagonal", "wave", "top_to_bottom", "left_to_right", "right_half") } ?: "none")
        if (!result.has("color_cycle")) result.put("color_cycle", JSONArray())
        result.put("margin", result.optDouble("margin", 0.1).coerceIn(0.0, 0.45))
        result.put("density", result.optString("density", "none").takeIf { it in setOf("none", "low", "medium", "high") } ?: "none")
        if (result.has("cluster_count")) result.put("cluster_count", result.optInt("cluster_count", 1).coerceIn(1, 12))
        result.put("fade", result.optString("fade", "none").takeIf { it in setOf("none", "outward", "directional") } ?: "none")
        result.put("preserve_space", result.optBoolean("preserve_space", false))
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

    private fun applyMaterialHint(data: JSONObject, ddl: String) {
        if (ddl.isBlank() || data.optString("weight", "pen") != "pen") return
        val lower = ddl.lowercase()
        val weight = materialWeightHints.firstOrNull { (markers, _) -> markers.any { it.lowercase() in lower } }?.second ?: return
        data.put("weight", weight)
        val note = "material inferred from DDL: $weight"
        val hint = data.optString("color_hint", "").takeIf { it.isNotBlank() }
        data.put("color_hint", if (hint == null) note else "$hint; $note")
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
        listOf("縄", "ロープ", "rope") to "rope",
    )
}

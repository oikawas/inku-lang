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
        data.put("color", visibleForeground(data.optString("color", detectColorKey(ddl, background)), background))
        data.put("weight", data.optString("weight", detectWeightKey(ddl)).ifBlank { "pen" })

        primitiveSpecs.getValue(primitive).forEach { spec ->
            val value = coercedField(data, spec)
            data.put(spec.name, toJsonValue(value ?: spec.defaultValue))
        }
        postCoerce(primitive, data)
        applyVariation(primitive, data, ddl)
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

    private fun applyVariation(primitive: String, data: JSONObject, ddl: String) {
        if (data.has("variation")) return
        val variation = when {
            ddl.contains("滲む") || ddl.contains("にじむ") ->
                JSONObject().put("amplitude", "medium").put("frequency", "medium").put("quality", "pink").put("dimensions", JSONArray(listOf("position_x", "position_y")))
            ddl.contains("波打つ") || ddl.contains("揺れる") ->
                JSONObject().put("amplitude", if (ddl.contains("大きく")) "broad" else "medium").put("frequency", if (ddl.contains("ゆっくり")) "slow" else "medium").put("quality", "wave").put("dimensions", JSONArray(listOf("position_x", "position_y")))
            ddl.contains("震える") || ddl.contains("細かく") ->
                JSONObject()
                    .put("amplitude", "fine")
                    .put("frequency", "medium")
                    .put("quality", "perlin")
                    .put("dimensions", JSONArray(if (primitive == "line") listOf("position_y") else listOf("position_x", "position_y")))
            ddl.contains("大きく") ->
                JSONObject().put("amplitude", "broad").put("frequency", "medium").put("quality", "wave").put("dimensions", JSONArray(listOf("position_x", "position_y")))
            ddl.contains("ゆっくり") || ddl.contains("速く") ->
                JSONObject().put("amplitude", "medium").put("frequency", if (ddl.contains("速く")) "high" else "slow").put("quality", "wave").put("dimensions", JSONArray(listOf("position_x", "position_y")))
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
}

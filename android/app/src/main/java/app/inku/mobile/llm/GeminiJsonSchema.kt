package app.inku.mobile.llm

import org.json.JSONArray
import org.json.JSONObject

/**
 * Projects a shared-core JSON Schema into Gemini's supported function-schema
 * subset, matching the server's `_gemini_json_schema` in `pipeline_provider.py`.
 * Rust still validates every response against the full schema.
 */
internal object GeminiJsonSchema {
    private val supportedKeys = setOf(
        "\$anchor", "\$defs", "\$id", "\$ref", "additionalProperties", "anyOf", "description",
        "enum", "format", "items", "maxItems", "maximum", "minItems", "minimum", "oneOf",
        "prefixItems", "properties", "propertyOrdering", "required", "title", "type",
    )

    fun project(schema: JSONObject, compactHoleEdits: Boolean = false): JSONObject {
        val result = projectValue(schema) as? JSONObject
        require(result != null && result.optString("type") == "object") {
            "Gemini function schema must describe an object"
        }
        if (compactHoleEdits) compactHoleVariants(result)
        return result
    }

    private fun projectValue(value: Any?, namedSchemas: Boolean = false): Any? = when (value) {
        is JSONArray -> JSONArray().also { out -> for (i in 0 until value.length()) out.put(projectValue(value.get(i))) }
        is JSONObject -> JSONObject().also { out ->
            for (key in value.keys()) {
                val item = value.get(key)
                when {
                    namedSchemas -> out.put(key, projectValue(item))
                    key == "const" -> out.put("enum", JSONArray().put(item))
                    key in supportedKeys -> out.put(key, projectValue(item, namedSchemas = key == "\$defs" || key == "properties"))
                }
            }
        }
        else -> value
    }

    private fun compactHoleVariants(schema: JSONObject) {
        val properties = schema.optJSONObject("properties") ?: return
        val collection = properties.optJSONObject("results") ?: properties.optJSONObject("edits") ?: return
        val items = collection.optJSONObject("items") ?: return
        val variants = items.optJSONArray("oneOf")?.toList() ?: return
        if (variants.isEmpty()) return
        val merged = mergeVariantValues(variants)
        if (merged is JSONObject && merged.optString("type") == "object") {
            collection.put("items", merged)
            return
        }
        // The v3 result variants require either `replacement` or `reason`; the
        // transport permits both optional while Rust keeps the exact one-of check.
        if (!variants.all { it is JSONObject }) return
        val variantProperties = variants.map { (it as JSONObject).optJSONObject("properties") ?: return }
        val sharedRequired = (variants[0] as JSONObject).stringSet("required").toMutableSet()
        variants.drop(1).forEach { sharedRequired.retainAll((it as JSONObject).stringSet("required")) }
        val mergedProperties = JSONObject()
        variantProperties.flatMap { it.keys().asSequence().toList() }.toSortedSet().forEach { name ->
            val candidates = variantProperties.filter { it.has(name) }.map { it.get(name) }
            mergedProperties.put(name, mergeVariantValues(candidates) ?: return)
        }
        collection.put(
            "items",
            JSONObject()
                .put("type", "object")
                .put("additionalProperties", false)
                .put("required", JSONArray(sharedRequired.sorted()))
                .put("properties", mergedProperties),
        )
    }

    private fun mergeVariantValues(values: List<Any?>): Any? {
        val first = values[0]
        if (values.drop(1).all { sameJson(it, first) }) return first
        if (!values.all { it is JSONObject }) return null
        val objects = values.map { it as JSONObject }
        val keys = objects[0].keys().asSequence().toList()
        if (!objects.drop(1).all { it.keys().asSequence().toSet() == keys.toSet() }) return null
        if (keys == listOf("enum") && objects.all { it.optJSONArray("enum")?.length() == 1 }) {
            return JSONObject().put("enum", JSONArray(objects.map { it.getJSONArray("enum").get(0) }))
        }
        val merged = JSONObject()
        for (key in keys) {
            merged.put(key, mergeVariantValues(objects.map { it.get(key) }) ?: return null)
        }
        return merged
    }

    private fun sameJson(a: Any?, b: Any?): Boolean = plain(a) == plain(b)

    /** Structural value for equality; Android's org.json has no `similar`. */
    private fun plain(value: Any?): Any? = when (value) {
        is JSONObject -> value.keys().asSequence().associateWith { plain(value.get(it)) }
        is JSONArray -> (0 until value.length()).map { plain(value.get(it)) }
        is Number -> value.toDouble()
        JSONObject.NULL -> null
        else -> value
    }

    private fun JSONArray.toList(): List<Any?> = (0 until length()).map { get(it) }

    private fun JSONObject.stringSet(name: String): Set<String> =
        optJSONArray(name)?.let { array -> (0 until array.length()).map { array.getString(it) }.toSet() } ?: emptySet()
}

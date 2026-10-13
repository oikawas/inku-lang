package app.inku.mobile.llm

import org.json.JSONArray
import org.json.JSONObject

/** Writes schema properties in their declared order without projecting away any keywords. */
internal object OrderedSchemaJson {
    fun encode(body: JSONObject): String = render(body).text

    private data class Rendered(val text: String, val changed: Boolean)

    private fun render(value: Any?, propertyNames: List<String>? = null): Rendered = when (value) {
        is JSONObject -> {
            val originalNames = value.keys().asSequence().toList()
            val names = propertyNames ?: originalNames
            val orderedProperties = if (value.optJSONArray("propertyOrdering") != null && value.optJSONObject("properties") != null) {
                GeminiJsonSchema.orderedPropertyNames(value)
            } else null
            val children = names.map { name ->
                name to render(value.get(name), if (name == "properties") orderedProperties else null)
            }
            val changed = names != originalNames || children.any { it.second.changed }
            // In particular, Stage 1/2 without propertyOrdering retain the native bytes.
            Rendered(if (changed) children.joinToString(",", "{", "}") { (name, child) ->
                JSONObject.quote(name) + ":" + child.text
            } else value.toString(), changed)
        }
        is JSONArray -> {
            val children = (0 until value.length()).map { render(value.get(it)) }
            val changed = children.any { it.changed }
            Rendered(if (changed) children.joinToString(",", "[", "]") { it.text } else value.toString(), changed)
        }
        else -> {
            // Let the same org.json implementation escape strings and encode scalar values.
            val array = JSONArray().put(value).toString()
            Rendered(array.substring(1, array.length - 1), false)
        }
    }
}

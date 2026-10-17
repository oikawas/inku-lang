package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject

/** JSON transport to the core; ordering and canonical number spelling belong to Rust. */
internal object CoreIdentityJson {
    fun canonical(value: Any?): String = requireNotNull(NativePipelineBridge.canonicalJson(encode(value))) {
        "invalid JSON for core canonicalization"
    }

    // JSONObject.toString() drops the fractional part of 1.0. Keep that type on
    // the wire so the core can apply its one canonical representation.
    fun encode(value: Any?): String = when (value) {
        null, JSONObject.NULL -> "null"
        is Boolean -> value.toString()
        is Float -> value.toDouble().toString()
        is Number -> value.toString()
        is JSONObject -> value.keys().asSequence().joinToString(",", "{", "}") { key ->
            JSONObject.quote(key) + ":" + encode(value.get(key))
        }
        is Map<*, *> -> value.entries.joinToString(",", "{", "}") { (key, item) ->
            JSONObject.quote(key.toString()) + ":" + encode(item)
        }
        is JSONArray -> (0 until value.length()).joinToString(",", "[", "]") { encode(value.get(it)) }
        is Collection<*> -> value.joinToString(",", "[", "]") { encode(it) }
        else -> JSONObject.quote(value.toString())
    }
}

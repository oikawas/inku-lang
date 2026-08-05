package app.inku.mobile.data.lineage

import app.inku.mobile.data.db.LineageEdgeEntity
import app.inku.mobile.data.db.LineageNodeEntity
import app.inku.mobile.data.model.DerivationKindRegistry
import org.json.JSONArray
import org.json.JSONObject

/**
 * What the caller declares about where a save came from.
 *
 * `derivationMetadata` is loosely typed on purpose. The server takes whatever
 * JSON the client sent and rejects a non-object itself, so a port that only
 * accepted a Map could never reach that judgment.
 */
data class LineageDeclaration(
    val parentNodeId: String? = null,
    val derivationKind: String? = null,
    val derivationMetadata: Any? = null,
)

/** The rows one save puts into the lineage tables. */
data class LineageWrite(
    val node: LineageNodeEntity,
    val edge: LineageEdgeEntity?,
)

/**
 * Decides what a save writes to `lineage_nodes` / `lineage_edges`.
 *
 * A one-for-one port of the lineage part of the server's `db.add_item`
 * (`server/src/inku_server/db.py:2018-2145`). The server is the canonical
 * source; nothing is decided differently here because it looked better on the
 * client. Two consequences of that are easy to lose in translation and are
 * kept deliberately:
 *
 *  - Python truthiness. `derivation_metadata or {}` turns an *empty* list into
 *    an accepted empty object while a non-empty list is rejected, and an empty
 *    parent id counts as no parent at all.
 *  - A declared parent with no kind at all is rejected as an invalid kind,
 *    because `None not in LINEAGE_DERIVATION_KINDS` is true on the server.
 *
 * The lineage tables on the device carry no `user_id`: one device is one user,
 * so the server's "the parent belongs to the same user" predicate has no
 * counterpart here. The rest of the parent test -- it must exist and must not
 * be a tombstone -- lives in this function rather than in a DAO query, so the
 * judgment stays in one readable place.
 */
object LineagePlanner {

    const val INVALID_VISIBILITY = "invalid history visibility"
    const val INVALID_KIND = "invalid lineage derivation kind"
    const val PARENT_REQUIRED = "lineage parent is required for a derivation"
    const val PARENT_NOT_FOUND = "lineage parent not found"
    const val METADATA_NOT_AN_OBJECT = "lineage derivation metadata must be an object"

    /**
     * @param parentNode the row `LineageDao.getNodeById(declaration.parentNodeId)`
     *   returned, or null when there is none. Passed in rather than looked up
     *   here so the decision stays free of the database.
     * @throws IllegalArgumentException with the server's own message.
     */
    fun plan(
        nodeId: String,
        edgeId: String,
        historyId: String,
        at: Long,
        descriptionHash: String,
        renderHash: String,
        historyVisibility: String?,
        declaration: LineageDeclaration,
        parentNode: LineageNodeEntity?,
    ): LineageWrite {
        // db.py:2030 -- `item.get("history_visibility") or "normal"`.
        val visibility = if (isTruthy(historyVisibility)) historyVisibility else "normal"
        require(visibility == "normal" || visibility == "lineage_only") { INVALID_VISIBILITY }

        val parentNodeId = declaration.parentNodeId
        val derivationKind = declaration.derivationKind
        val hasParent = isTruthy(parentNodeId)
        // db.py:2035 -- `item.get("derivation_metadata") or {}`.
        val metadata = if (isTruthy(declaration.derivationMetadata)) declaration.derivationMetadata else emptyMap<String, Any?>()

        // db.py:2036-2041, in this order.
        require(!hasParent || DerivationKindRegistry.KINDS.contains(derivationKind)) { INVALID_KIND }
        require(hasParent || !isTruthy(derivationKind)) { PARENT_REQUIRED }
        require(isObject(metadata)) { METADATA_NOT_AN_OBJECT }

        // db.py:2091 -- a node with no parent is its own root.
        var rootNodeId = nodeId
        if (hasParent) {
            // db.py:2103-2109.
            val parent = parentNode?.takeIf { it.id == parentNodeId && it.state != "tombstone" }
            requireNotNull(parent) { PARENT_NOT_FOUND }
            // db.py:2110 -- `parent.root_node_id or parent.id`. The root
            // propagates; the parent does not become one.
            rootNodeId = parent.rootNodeId.takeIf { isTruthy(it) } ?: parent.id
        }

        val node = LineageNodeEntity(
            id = nodeId,
            historyId = historyId,
            // db.py:2088.
            state = if (visibility == "lineage_only") "lineage_only" else "active",
            descriptionHash = descriptionHash,
            renderHash = renderHash,
            at = at,
            rootNodeId = rootNodeId,
        )
        // db.py:2132-2136 -- an edge only for a declared derivation.
        val edge = if (!hasParent) null else LineageEdgeEntity(
            id = edgeId,
            parentNodeId = parentNodeId!!,
            childNodeId = nodeId,
            derivationKind = derivationKind!!,
            metadataJson = canonicalJson(metadata),
            at = at,
        )
        return LineageWrite(node = node, edge = edge)
    }

    /** Python truthiness, which the two `or` expressions above depend on. */
    private fun isTruthy(value: Any?): Boolean = when {
        value == null || value === JSONObject.NULL -> false
        value is Boolean -> value
        value is Number -> value.toDouble() != 0.0
        value is CharSequence -> value.isNotEmpty()
        value is Collection<*> -> value.isNotEmpty()
        value is Map<*, *> -> value.isNotEmpty()
        value is JSONArray -> value.length() > 0
        value is JSONObject -> value.length() > 0
        else -> true
    }

    /** Python's `isinstance(value, dict)`. */
    private fun isObject(value: Any?): Boolean = value is Map<*, *> || value is JSONObject

    /**
     * The server's `_canonical_json`: `json.dumps(value, ensure_ascii=False,
     * sort_keys=True, separators=(",", ":"))`. Written out rather than handed
     * to `JSONObject.toString()`, which keeps insertion order and inserts no
     * separators of its own -- the baked expectation is `{"a":2,"b":1}` for
     * metadata that was passed as `{"b": 1, "a": 2}`.
     */
    fun canonicalJson(value: Any?): String {
        val out = StringBuilder()
        writeJson(out, value)
        return out.toString()
    }

    private fun writeJson(out: StringBuilder, value: Any?) {
        when {
            value == null || value === JSONObject.NULL -> out.append("null")
            value is Boolean -> out.append(if (value) "true" else "false")
            value is Number -> out.append(value.toString())
            value is CharSequence -> writeJsonString(out, value.toString())
            value is Map<*, *> -> writeJsonObject(out, value.entries.associate { it.key.toString() to it.value })
            value is JSONObject -> writeJsonObject(out, value.keys().asSequence().associateWith { value.get(it) })
            value is Collection<*> -> writeJsonArray(out, value.toList())
            value is JSONArray -> writeJsonArray(out, (0 until value.length()).map { value.get(it) })
            else -> writeJsonString(out, value.toString())
        }
    }

    private fun writeJsonObject(out: StringBuilder, entries: Map<String, Any?>) {
        out.append('{')
        entries.keys.sortedWith(CODE_POINT_ORDER).forEachIndexed { index, key ->
            if (index > 0) out.append(',')
            writeJsonString(out, key)
            out.append(':')
            writeJson(out, entries[key])
        }
        out.append('}')
    }

    private fun writeJsonArray(out: StringBuilder, items: List<Any?>) {
        out.append('[')
        items.forEachIndexed { index, item ->
            if (index > 0) out.append(',')
            writeJson(out, item)
        }
        out.append(']')
    }

    /** `ensure_ascii=False`: only the structural escapes, non-ASCII stays raw. */
    private fun writeJsonString(out: StringBuilder, value: String) {
        out.append('"')
        for (ch in value) {
            when (ch) {
                '"' -> out.append("\\\"")
                '\\' -> out.append("\\\\")
                '\n' -> out.append("\\n")
                '\r' -> out.append("\\r")
                '\t' -> out.append("\\t")
                '\b' -> out.append("\\b")
                '\u000C' -> out.append("\\f")
                else -> if (ch < ' ') out.append("\\u%04x".format(ch.code)) else out.append(ch)
            }
        }
        out.append('"')
    }

    /**
     * Python sorts keys by code point; Kotlin's natural String order is by
     * UTF-16 code unit, which puts astral-plane keys before U+E000..U+FFFF.
     */
    private val CODE_POINT_ORDER = Comparator<String> { a, b ->
        val left = a.codePoints().toArray()
        val right = b.codePoints().toArray()
        var i = 0
        while (i < left.size && i < right.size) {
            if (left[i] != right[i]) return@Comparator left[i].compareTo(right[i])
            i++
        }
        left.size.compareTo(right.size)
    }
}

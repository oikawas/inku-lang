package app.inku.mobile.data.lineage

/**
 * Which works are held by their DDL rather than by their description -- the
 * port of the server's `persistence/description_lock.py`.
 *
 * A work whose DDL was edited no longer follows its description: drawing it
 * again from the description would throw the edits away. Such a work is
 * "description-locked". It is locked when
 *
 * - its authoring variation is DDL-authoritative, or
 * - it was made by a DDL edit (`ddl_edit`, which also covers works saved before
 *   the pipeline kept an authority), or
 * - it was derived from a locked work by an operation that keeps the parent's
 *   DDL (touch, color, layout, variation, replay and the like).
 *
 * A work derived by reading the description again is not locked: that is where
 * the lineage went back to the words. [DESCRIPTION_READING_KINDS] are those
 * readings.
 *
 * A `replay` is judged by its DDL, not by its kind or its variation: one whose
 * DDL differs from its parent's read the words again, and one whose DDL is the
 * parent's is held exactly when its parent is.
 *
 * The walk reads the store the way the server's queries do, one generation of
 * edges at a time, so the decision itself has no Room in it.
 */
object DescriptionLock {

    /** Derivations that draw from the description again. */
    val DESCRIPTION_READING_KINDS: Set<String> = setOf(
        "reinterpretation",
        "description_edit",
        "sketch_grain_change",
        "model_comparison",
        "language_comparison",
        "canvas_aspect_change",
    )

    private const val MAX_DEPTH = 256
    private const val DDL_EDIT = "ddl_edit"
    private const val REPLAY = "replay"
    private const val DDL_AUTHORITATIVE = "ddl_authoritative"
    private const val LEGACY_EXPANDED_ORIGIN = "legacy_expanded"

    data class Node(val id: String, val historyId: String?)
    data class Edge(val parentNodeId: String, val childNodeId: String, val derivationKind: String)
    data class HistoryDdl(val historyId: String, val ddl: String?, val ddlSourceOrigin: String?)
    data class HistoryLink(val ownerId: String, val historyId: String, val variationId: String)
    data class Authority(val ownerId: String, val variationId: String, val authority: String)

    /** The rows the walk reads; each call is one of the server's queries. */
    interface Store {
        suspend fun nodesOfHistories(historyIds: Collection<String>): List<Node>
        suspend fun nodesByIds(nodeIds: Collection<String>): List<Node>
        suspend fun edgesOfChildren(childNodeIds: Collection<String>): List<Edge>
        suspend fun ddlOfHistories(historyIds: Collection<String>): List<HistoryDdl>
        suspend fun historyLinks(historyIds: Collection<String>): List<HistoryLink>
        suspend fun authorities(variationIds: Collection<String>): List<Authority>
    }

    /** The subset of [historyIds] that is description-locked (`locked_history_ids`). */
    suspend fun lockedHistoryIds(store: Store, historyIds: Iterable<String>): Set<String> {
        val starts = historyIds.filter { it.isNotEmpty() }.distinct()
        if (starts.isEmpty()) return emptySet()
        val nodeOfHistory = LinkedHashMap<String, String>()
        val historyOfNode = HashMap<String, String?>()
        for (node in store.nodesOfHistories(starts)) {
            node.historyId?.let { nodeOfHistory[it] = node.id }
            historyOfNode[node.id] = node.historyId
        }
        val edgeOfChild = HashMap<String, Pair<String, String>>()
        var frontier: Set<String> = nodeOfHistory.values.toSet()
        for (depth in 0 until MAX_DEPTH) {
            if (frontier.isEmpty()) break
            val parents = mutableSetOf<String>()
            for (edge in store.edgesOfChildren(frontier)) {
                edgeOfChild[edge.childNodeId] = edge.parentNodeId to edge.derivationKind
                if (edge.derivationKind !in DESCRIPTION_READING_KINDS && edge.derivationKind != DDL_EDIT) {
                    parents.add(edge.parentNodeId)
                }
            }
            val unseen = parents - historyOfNode.keys
            if (unseen.isNotEmpty()) {
                for (node in store.nodesByIds(unseen)) historyOfNode[node.id] = node.historyId
            }
            frontier = parents.filterTo(mutableSetOf()) { it !in edgeOfChild }
        }
        val histories = (starts + historyOfNode.values.filterNotNull().filter { it.isNotEmpty() }).distinct()
        val ddlAuthoritative = ddlAuthoritativeHistories(store, histories)
        val replayNodes = edgeOfChild.entries
            .filter { (_, edge) -> edge.second == REPLAY }
            .flatMap { (child, edge) -> listOf(child, edge.first) }
            .toSet()
        val ddlOfHistory = ddlOfHistories(store, replayNodes.map { historyOfNode[it] })

        fun sameDdl(child: String, parent: String): Boolean? {
            val childDdl = ddlOfHistory[historyOfNode[child].orEmpty()]
            val parentDdl = ddlOfHistory[historyOfNode[parent].orEmpty()]
            if (childDdl.isNullOrEmpty() || parentDdl.isNullOrEmpty()) return null
            return childDdl == parentDdl
        }

        fun locked(nodeId: String): Boolean {
            val seen = mutableSetOf<String>()
            var current: String? = nodeId
            while (current != null && seen.add(current)) {
                val edge = edgeOfChild[current]
                if (edge != null && edge.second == REPLAY) {
                    when (sameDdl(current, edge.first)) {
                        false -> return false
                        true -> {
                            current = edge.first
                            continue
                        }
                        null -> Unit
                    }
                }
                if (historyOfNode[current] in ddlAuthoritative) return true
                if (edge == null) return false
                val (parent, kind) = edge
                if (kind == DDL_EDIT) return true
                if (kind in DESCRIPTION_READING_KINDS) return false
                current = parent
            }
            return false
        }

        return nodeOfHistory.filter { (_, nodeId) -> locked(nodeId) }.keys +
            starts.filter { it !in nodeOfHistory && it in ddlAuthoritative }
    }

    /** Each work's DDL, spacing aside, for telling a replay from a reading. */
    private suspend fun ddlOfHistories(store: Store, historyIds: List<String?>): Map<String, String> {
        val wanted = historyIds.filterNotNull().filter { it.isNotEmpty() }
        if (wanted.isEmpty()) return emptyMap()
        // A transferred expanded text says nothing about the historical input DDL.
        return store.ddlOfHistories(wanted)
            .filter { !it.ddl.isNullOrEmpty() && it.ddlSourceOrigin != LEGACY_EXPANDED_ORIGIN }
            .associate { it.historyId to collapseSpacing(it.ddl.orEmpty()) }
    }

    private suspend fun ddlAuthoritativeHistories(store: Store, historyIds: List<String>): Set<String> {
        if (historyIds.isEmpty()) return emptySet()
        val links = store.historyLinks(historyIds)
        if (links.isEmpty()) return emptySet()
        val variations = store.authorities(links.mapTo(mutableSetOf()) { it.variationId })
            .associate { (it.ownerId to it.variationId) to it.authority }
        return links
            .filter { variations[it.ownerId to it.variationId] == DDL_AUTHORITATIVE }
            .mapTo(mutableSetOf()) { it.historyId }
    }

    /**
     * Python's `" ".join(text.split())`: runs of what `str.isspace` calls space
     * become one space, and the ends are dropped. That set is Unicode
     * White_Space plus U+001C..U+001F, which Python also splits on.
     */
    internal fun collapseSpacing(text: String): String =
        text.splitWhere { it.code in PYTHON_WHITESPACE }.filter { it.isNotEmpty() }.joinToString(" ")

    private inline fun String.splitWhere(isSeparator: (Char) -> Boolean): List<String> {
        val parts = mutableListOf<String>()
        val part = StringBuilder()
        for (char in this) {
            if (isSeparator(char)) {
                parts += part.toString()
                part.setLength(0)
            } else {
                part.append(char)
            }
        }
        parts += part.toString()
        return parts
    }

    private val PYTHON_WHITESPACE: Set<Int> = setOf(
        9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
        8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202,
        8232, 8233, 8239, 8287, 12288,
    )

    /** Whether the work at a lineage node is description-locked (`node_is_locked`). */
    suspend fun nodeIsLocked(store: Store, nodeId: String): Boolean {
        val historyId = store.nodesByIds(listOf(nodeId)).firstOrNull()?.historyId
        if (historyId.isNullOrEmpty()) return false
        return historyId in lockedHistoryIds(store, listOf(historyId))
    }
}

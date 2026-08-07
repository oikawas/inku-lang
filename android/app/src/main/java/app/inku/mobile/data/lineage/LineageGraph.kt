package app.inku.mobile.data.lineage

import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.LineageEdgeEntity
import app.inku.mobile.data.db.LineageNodeEntity
import org.json.JSONException
import org.json.JSONObject

/**
 * One work in the graph.
 *
 * Split in two rather than given nullable fields, because the server does not
 * emit `description_hash` / `render_hash` / `history` for a tombstone at all --
 * the keys are absent, not null (`db.py:1137-1142`). A single class with three
 * nullable properties would say "present and empty", which is a different
 * statement; here a tombstone has no such member to read.
 */
sealed interface LineageGraphNode {
    val id: String
    val state: String
    val at: Long
    val deletedAt: Long?
    val childCount: Int

    /** A node the server describes in full. */
    data class Work(
        override val id: String,
        override val state: String,
        override val at: Long,
        override val deletedAt: Long?,
        override val childCount: Int,
        val descriptionHash: String?,
        val renderHash: String?,
        /** Absent when no history row answers to the node's `history_id`. */
        val history: LineageGraphHistory?,
    ) : LineageGraphNode

    /** A deleted node: the five keys `db.py:1130-1136` writes, and no more. */
    data class Tombstone(
        override val id: String,
        override val state: String,
        override val at: Long,
        override val deletedAt: Long?,
        override val childCount: Int,
    ) : LineageGraphNode
}

/**
 * The history row a node stands for.
 *
 * The generation sits here rather than on the node because that is where the
 * server puts it (`payload["history"]["lineage_generation"]`, `db.py:1141`): a
 * node with no history row carries no generation either. Nullable for the same
 * reason the server's `generations.get(node.id)` can be `None`.
 */
data class LineageGraphHistory(
    val item: HistoryItemEntity,
    val lineageGeneration: Int?,
)

/** One derivation. `db.py:956` (`_lineage_edge_to_dict`). */
data class LineageGraphEdge(
    val id: String,
    val parentNodeId: String,
    val childNodeId: String,
    val derivationKind: String,
    val metadata: JSONObject,
    val at: Long,
)

/**
 * What `db.get_lineage` returns, plus the two clamped arguments.
 *
 * The effective values are carried because the clamps cannot be seen in the
 * graph itself: `descendant_depth` -1 and 0 produce the same edges, and
 * `node_limit` 0 and 1 produce the same JSON, so a port that dropped the
 * clamping would still match every expectation. They are the only way an
 * acceptance test can look at the clamp rather than at its shadow.
 */
data class LineageGraphResult(
    val focusNodeId: String,
    val nodes: List<LineageGraphNode>,
    val edges: List<LineageGraphEdge>,
    val effectiveDescendantDepth: Int,
    val effectiveNodeLimit: Int,
)

/**
 * Builds the lineage graph around one work.
 *
 * A one-for-one port of the server's `db.get_lineage` (`db.py:1069`), which is
 * the canonical source; the recursive SQL there is rewritten as walks over
 * lists, but every judgment -- how far to climb, how far to descend, what to
 * count, what to leave out, in which order to return it -- is the server's.
 *
 * The rows come in as lists rather than through a DAO, the way
 * [LineagePlanner.plan] takes its parent node: the decision stays free of the
 * database, so the same function answers for the device and for a baked table
 * of expectations.
 *
 * The lineage tables on the device carry no `user_id` -- one device is one user
 * -- so the server's "and it belongs to the same user" predicate has no
 * counterpart here and is dropped. Dropping it is not the same as writing it as
 * always-true: there is no such column to compare.
 */
object LineageGraph {

    /** `db.py:1069` -- the signature's own defaults. */
    const val DEFAULT_DESCENDANT_DEPTH = 2
    const val DEFAULT_NODE_LIMIT = 200

    private const val MAX_DESCENDANT_DEPTH = 200
    private const val MAX_NODE_LIMIT = 200

    /** `db.py:1070` -- `max(0, min(descendant_depth, 200))`. */
    fun effectiveDescendantDepth(requested: Int): Int =
        maxOf(0, minOf(requested, MAX_DESCENDANT_DEPTH))

    /** `db.py:1071` -- `max(1, min(node_limit, 200))`. */
    fun effectiveNodeLimit(requested: Int): Int =
        maxOf(1, minOf(requested, MAX_NODE_LIMIT))

    /**
     * @param nodes every `lineage_nodes` row the graph may draw on. Ancestors
     *   are climbed and child counts are taken over what is handed in, so a
     *   caller that pre-filters changes the answer.
     * @param edges likewise for `lineage_edges`. The generation walk and the
     *   child counts read all of them, not only the ones this call selects.
     * @param histories the history rows by `history_id`.
     * @return null when the focus node is not among [nodes], which is the
     *   server's `if focus is None: return None` (`db.py:1078`).
     */
    fun build(
        focusNodeId: String,
        nodes: List<LineageNodeEntity>,
        edges: List<LineageEdgeEntity>,
        histories: Map<String, HistoryItemEntity> = emptyMap(),
        descendantDepth: Int = DEFAULT_DESCENDANT_DEPTH,
        nodeLimit: Int = DEFAULT_NODE_LIMIT,
    ): LineageGraphResult? {
        val depth = effectiveDescendantDepth(descendantDepth)
        val limit = effectiveNodeLimit(nodeLimit)

        val nodeById = nodes.associateBy { it.id }
        val focus = nodeById[focusNodeId] ?: return null

        // `uq_lineage_primary_parent` makes the child the unique key, so a child
        // has at most one parent edge and climbing is a walk, not a search.
        val edgeByChild = edges.associateBy { it.childNodeId }
        val edgesByParent = edges.groupBy { it.parentNodeId }
        val edgeById = edges.associateBy { it.id }

        // db.py:1081-1088 -- ancestors first, then whatever budget survives.
        val ancestorIds = ancestorEdgeIds(focus.id, edgeByChild, limit - 1)
        val remaining = maxOf(0, limit - 1 - ancestorIds.size)
        val descendantIds = descendantEdgeIds(focus.id, edgesByParent, depth, remaining)
        // db.py:1089 -- `dict.fromkeys`: deduplicated, first occurrence wins.
        val selectedEdgeIds = LinkedHashSet<String>().apply {
            addAll(ancestorIds)
            addAll(descendantIds)
        }
        val selectedEdges = selectedEdgeIds.mapNotNull { edgeById[it] }

        // db.py:1101-1104 -- the focus is in even when no edge touches it.
        val nodeIds = LinkedHashSet<String>().apply {
            add(focus.id)
            selectedEdges.forEach {
                add(it.parentNodeId)
                add(it.childNodeId)
            }
        }
        // db.py:1106 -- an id with no row simply produces no node.
        val selectedNodes = nodeIds.mapNotNull { nodeById[it] }

        // db.py:1119-1127 -- counted over every edge, not over the selected
        // ones: a node the limit truncated still reports all of its children.
        val childCounts = edges.groupingBy { it.parentNodeId }.eachCount()
        // db.py:1128 -- likewise the generation, which climbs to the root even
        // when the node limit stopped the graph two steps below it.
        val generations = lineageGenerations(selectedNodes.map { it.id }, edgeByChild)

        val payloads = selectedNodes.map { node ->
            val childCount = childCounts[node.id] ?: 0
            if (node.state == "tombstone") {
                LineageGraphNode.Tombstone(
                    id = node.id,
                    state = node.state,
                    at = node.at,
                    deletedAt = node.deletedAt,
                    childCount = childCount,
                )
            } else {
                LineageGraphNode.Work(
                    id = node.id,
                    state = node.state,
                    at = node.at,
                    deletedAt = node.deletedAt,
                    childCount = childCount,
                    descriptionHash = node.descriptionHash,
                    renderHash = node.renderHash,
                    history = histories[node.historyId ?: ""]?.let {
                        LineageGraphHistory(item = it, lineageGeneration = generations[node.id])
                    },
                )
            }
        }

        // db.py:1145-1149 -- both sorted by `(at, id)`. The second key only ever
        // decides between rows saved in the same millisecond, which is why it is
        // easy to drop and hard to notice.
        return LineageGraphResult(
            focusNodeId = focus.id,
            nodes = payloads.sortedWith(compareBy({ it.at }, { it.id })),
            edges = selectedEdges
                .sortedWith(compareBy({ it.at }, { it.id }))
                .map { toGraphEdge(it) },
            effectiveDescendantDepth = depth,
            effectiveNodeLimit = limit,
        )
    }

    /**
     * `_ancestor_edge_ids` (`db.py:971`): climb from the focus towards the root,
     * at most [limit] edges.
     *
     * The recursive CTE there is a `UNION`, which both deduplicates and stops a
     * cycle from looping forever; the set of seen edges does the same here.
     */
    private fun ancestorEdgeIds(
        focusNodeId: String,
        edgeByChild: Map<String, LineageEdgeEntity>,
        limit: Int,
    ): List<String> {
        if (limit <= 0) return emptyList()
        val ids = mutableListOf<String>()
        val seen = mutableSetOf<String>()
        var current = focusNodeId
        while (ids.size < limit) {
            val edge = edgeByChild[current] ?: break
            if (!seen.add(edge.id)) break
            ids.add(edge.id)
            current = edge.parentNodeId
        }
        return ids
    }

    /**
     * `_descendant_edge_ids` (`db.py:995`): descend [depth] generations from the
     * focus, then `ORDER BY depth ASC, id ASC LIMIT :limit`.
     *
     * The CTE is a `UNION ALL`, so nothing deduplicates and the depth bound is
     * what terminates it; the same is true of the loop below. The ordering
     * matters because it decides which edges survive the limit, not merely how
     * they are printed.
     */
    private fun descendantEdgeIds(
        focusNodeId: String,
        edgesByParent: Map<String, List<LineageEdgeEntity>>,
        depth: Int,
        limit: Int,
    ): List<String> {
        if (depth <= 0 || limit <= 0) return emptyList()
        val found = mutableListOf<Pair<Int, LineageEdgeEntity>>()
        var frontier = listOf(focusNodeId)
        var level = 1
        while (level <= depth && frontier.isNotEmpty()) {
            val next = mutableListOf<String>()
            for (parent in frontier) {
                for (edge in edgesByParent[parent].orEmpty()) {
                    found.add(level to edge)
                    next.add(edge.childNodeId)
                }
            }
            frontier = next
            level += 1
        }
        return found
            .sortedWith(compareBy({ it.first }, { it.second.id }))
            .map { it.second.id }
            .take(limit)
    }

    /**
     * `_lineage_generations` (`db.py:1033`): the root is 1 and every primary
     * parent edge adds one.
     *
     * The depth is measured from the root, not from the focus, so the same work
     * reports the same generation whichever node the graph is centred on. The
     * memo and the cycle guard are the server's; a repeated node is treated as a
     * root rather than climbed forever.
     */
    private fun lineageGenerations(
        nodeIds: List<String>,
        edgeByChild: Map<String, LineageEdgeEntity>,
    ): Map<String, Int> {
        val memo = mutableMapOf<String, Int>()

        fun resolve(nodeId: String): Int {
            memo[nodeId]?.let { return it }
            val chain = mutableListOf<String>()
            val seen = mutableSetOf<String>()
            var current = nodeId
            while (!memo.containsKey(current)) {
                if (!seen.add(current)) break
                chain.add(current)
                val edge = edgeByChild[current] ?: break
                current = edge.parentNodeId
            }
            val base = memo[current] ?: 0
            chain.asReversed().forEachIndexed { offset, id -> memo[id] = base + offset + 1 }
            return memo.getValue(nodeId)
        }

        nodeIds.forEach { resolve(it) }
        return memo
    }

    /**
     * `_lineage_edge_to_dict` (`db.py:956`): unparsable metadata becomes an
     * empty object, and so does metadata that parsed into anything other than an
     * object -- a stored array is not passed through.
     */
    private fun toGraphEdge(edge: LineageEdgeEntity): LineageGraphEdge = LineageGraphEdge(
        id = edge.id,
        parentNodeId = edge.parentNodeId,
        childNodeId = edge.childNodeId,
        derivationKind = edge.derivationKind,
        metadata = try {
            // `row.metadata_json or "{}"`: an empty string is falsy in Python.
            JSONObject(edge.metadataJson.ifEmpty { "{}" })
        } catch (invalid: JSONException) {
            JSONObject()
        },
        at = edge.at,
    )
}

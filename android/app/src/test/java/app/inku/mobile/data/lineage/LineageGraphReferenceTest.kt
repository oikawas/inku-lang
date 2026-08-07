package app.inku.mobile.data.lineage

import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.LineageEdgeEntity
import app.inku.mobile.data.db.LineageNodeEntity
import java.io.InputStreamReader
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * [LineageGraph] reproduces `db.get_lineage`.
 *
 * The expectations in `lineage/lineage-cases.json` were baked on 2026-08-07 at
 * main `34b8a5fa` by running the real server function against a throwaway
 * SQLite file, so they come from the implementation rather than from a reading
 * of it. Each case carries both the rows a DAO would return (`given`) and the
 * result the server produced (`expected`); the file is a frozen measurement and
 * is not regenerated here -- rebaking it would hand out fresh uuid4 node ids and
 * lose the one property C9 exists for. Its origin is
 * `cli/out2/859-v2.11.4-android-shows-the-lineage-expectations/`, where the
 * baking script sits next to it.
 *
 * `history` is compared by which node has one and by the generation inside it,
 * not field by field: the server's history dict and this client's
 * [HistoryItemEntity] are different shapes, and pretending otherwise would test
 * the translation rather than the graph.
 */
class LineageGraphReferenceTest {

    // --- the fixture ---

    private fun cases(): List<JSONObject> {
        val stream = javaClass.getResourceAsStream(FIXTURE) ?: error("$FIXTURE not found")
        val text = InputStreamReader(stream, Charsets.UTF_8).use { it.readText() }
        val array = JSONObject(text).getJSONArray("cases")
        return (0 until array.length()).map { array.getJSONObject(it) }
    }

    private fun caseNamed(id: String): JSONObject =
        cases().firstOrNull { it.getString("case_id") == id } ?: error("no case $id")

    private fun JSONObject.stringOrNull(key: String): String? =
        if (isNull(key)) null else getString(key)

    private fun JSONObject.longOrNull(key: String): Long? =
        if (isNull(key)) null else getLong(key)

    private fun nodesOf(given: JSONObject): List<LineageNodeEntity> =
        given.getJSONArray("nodes").objects().map {
            LineageNodeEntity(
                id = it.getString("id"),
                historyId = it.stringOrNull("history_id"),
                state = it.getString("state"),
                descriptionHash = it.stringOrNull("description_hash"),
                renderHash = it.stringOrNull("render_hash"),
                at = it.getLong("at"),
                deletedAt = it.longOrNull("deleted_at"),
                rootNodeId = it.stringOrNull("root_node_id"),
            )
        }

    private fun edgesOf(given: JSONObject): List<LineageEdgeEntity> =
        given.getJSONArray("edges").objects().map {
            LineageEdgeEntity(
                id = it.getString("id"),
                parentNodeId = it.getString("parent_node_id"),
                childNodeId = it.getString("child_node_id"),
                derivationKind = it.getString("derivation_kind"),
                metadataJson = it.getString("metadata_json"),
                at = it.getLong("at"),
            )
        }

    /**
     * A stand-in for the row `HistoryDao.getById` would return. One is made for
     * every `history_id` the case names, including the tombstone's: the server
     * drops `history` because the node is a tombstone, not because the row went
     * missing, and a fixture with no row for it could not tell the two apart.
     */
    private fun historiesOf(nodes: List<LineageNodeEntity>): Map<String, HistoryItemEntity> =
        nodes.mapNotNull { it.historyId }.distinct().associateWith { id ->
            HistoryItemEntity(
                id = id,
                createdAt = 0L,
                updatedAt = 0L,
                originalInput = id,
                normalizedDdl = "$id を描く。",
                expandedDdl = null,
                scoreJson = "{}",
                displaySvg = "<svg id='$id'/>",
                stage1Model = null,
                stage2Model = null,
                renderMetadataJson = "{}",
                renderHash = "rh3:$id",
                renderHashShort = id.takeLast(4),
                colorCatalogId = "default",
                canvasAspect = "square",
                starred = false,
                trashed = false,
                elapsedMs = 1L,
                tokenMetadataJson = null,
            )
        }

    private fun build(case: JSONObject): LineageGraphResult? {
        val given = case.getJSONObject("given")
        val nodes = nodesOf(given)
        return LineageGraph.build(
            focusNodeId = given.getString("focus_node_id"),
            nodes = nodes,
            edges = edgesOf(given),
            histories = historiesOf(nodes),
            descendantDepth = given.optInt("descendant_depth", LineageGraph.DEFAULT_DESCENDANT_DEPTH),
            nodeLimit = given.optInt("node_limit", LineageGraph.DEFAULT_NODE_LIMIT),
        )
    }

    private fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }

    private fun generationOf(node: JSONObject): Int? =
        if (!node.has("history")) null else node.getJSONObject("history").let {
            if (it.isNull("lineage_generation")) null else it.getInt("lineage_generation")
        }

    // --- T-1: every case, in order ---

    @Test
    fun graph_reproducesEveryBakedCaseIncludingTheOrder() {
        val all = cases()
        all.forEach { case ->
            val id = case.getString("case_id")
            val expected = case.optJSONObject("expected")
            val actual = build(case)
            if (expected == null) {
                assertNull("$id: the server returned nothing", actual)
                return@forEach
            }
            assertNotNull("$id: the port returned nothing", actual)
            actual!!

            assertEquals("$id: focus", expected.getString("focus_node_id"), actual.focusNodeId)

            val expectedNodes = expected.getJSONArray("nodes").objects()
            assertEquals(
                "$id: the nodes and their order",
                expectedNodes.map { it.getString("id") },
                actual.nodes.map { it.id },
            )
            expectedNodes.zip(actual.nodes).forEach { (want, got) ->
                val where = "$id/${want.getString("id").take(8)}"
                assertEquals("$where: state", want.getString("state"), got.state)
                assertEquals("$where: at", want.getLong("at"), got.at)
                assertEquals("$where: deleted_at", want.longOrNull("deleted_at"), got.deletedAt)
                assertEquals("$where: child_count", want.getInt("child_count"), got.childCount)
                when (got) {
                    is LineageGraphNode.Tombstone ->
                        assertTrue(
                            "$where: the server described this node in full, the port did not",
                            !want.has("description_hash"),
                        )
                    is LineageGraphNode.Work -> {
                        assertTrue(
                            "$where: the server left this node's hashes out, the port did not",
                            want.has("description_hash"),
                        )
                        assertEquals(
                            "$where: description_hash",
                            want.stringOrNull("description_hash"),
                            got.descriptionHash,
                        )
                        assertEquals(
                            "$where: render_hash",
                            want.stringOrNull("render_hash"),
                            got.renderHash,
                        )
                        assertEquals("$where: has a history", want.has("history"), got.history != null)
                        if (want.has("history")) {
                            assertEquals(
                                "$where: which history",
                                want.getJSONObject("history").getString("id"),
                                got.history?.item?.id,
                            )
                            assertEquals(
                                "$where: lineage_generation",
                                generationOf(want),
                                got.history?.lineageGeneration,
                            )
                        }
                    }
                }
            }

            val expectedEdges = expected.getJSONArray("edges").objects()
            assertEquals(
                "$id: the edges and their order",
                expectedEdges.map { it.getString("id") },
                actual.edges.map { it.id },
            )
            expectedEdges.zip(actual.edges).forEach { (want, got) ->
                val where = "$id/${want.getString("id").take(8)}"
                assertEquals("$where: parent", want.getString("parent_node_id"), got.parentNodeId)
                assertEquals("$where: child", want.getString("child_node_id"), got.childNodeId)
                assertEquals("$where: kind", want.getString("derivation_kind"), got.derivationKind)
                assertEquals("$where: at", want.getLong("at"), got.at)
                assertEquals(
                    "$where: metadata",
                    LineagePlanner.canonicalJson(want.getJSONObject("metadata")),
                    LineagePlanner.canonicalJson(got.metadata),
                )
            }
        }
        // A case going missing must not quietly shrink the gate.
        assertEquals("the baked case count", 11, all.size)
        assertTrue(
            "C9 is what makes the (at, id) tiebreak decidable and has to be here",
            all.any { it.getString("case_id") == "C9-four-siblings-share-one-at" },
        )
    }

    @Test
    fun graph_ordersSiblingsThatShareOneTimestampById() {
        // The second sort key decides nothing anywhere else: every other case
        // has distinct `at` values. Asserted separately from T-1 so that a lost
        // tiebreak names itself instead of arriving as one row out of dozens.
        val case = caseNamed("C9-four-siblings-share-one-at")
        val expected = case.getJSONObject("expected").getJSONArray("nodes").objects()
        val tied = expected.filter { it.getLong("at") == 5000L }.map { it.getString("id") }
        assertEquals("four siblings share one `at` in this case", 4, tied.size)
        assertEquals("sorted by id, which is what the server returned", tied.sorted(), tied)

        val actual = build(case)!!.nodes.filter { it.at == 5000L }.map { it.id }
        assertEquals(tied, actual)
    }

    // --- T-2: the clamps, by the value they clamp to ---

    @Test
    fun clamps_areReadableAsValuesNotOnlyAsTheirEffect() {
        // -1 and 0 produce the same graph, and so do 0 and 1, so a port that
        // dropped the clamping matches every baked case. These look at the
        // number itself.
        assertEquals(0, LineageGraph.effectiveDescendantDepth(-1))
        assertEquals(200, LineageGraph.effectiveDescendantDepth(999))
        assertEquals(1, LineageGraph.effectiveNodeLimit(0))
        assertEquals(200, LineageGraph.effectiveNodeLimit(999))

        // And the graph reports what it actually used, so the clamp cannot be
        // correct in a helper and skipped in the builder.
        val clamped = build(caseNamed("C7-clamp-huge"))!!
        assertEquals(200, clamped.effectiveDescendantDepth)
        assertEquals(200, clamped.effectiveNodeLimit)

        val negative = build(caseNamed("C6-clamp-negative-depth"))!!
        assertEquals(0, negative.effectiveDescendantDepth)

        val zeroLimit = build(caseNamed("C8-clamp-zero-node-limit"))!!
        assertEquals(1, zeroLimit.effectiveNodeLimit)
    }

    // --- T-3: what a tombstone does not have ---

    @Test
    fun tombstone_hasNoHashesAndNoHistoryWhileItsNeighboursDo() {
        listOf("C10-a-tombstone-in-the-middle", "C11-focus-is-below-a-tombstone").forEach { id ->
            val actual = build(caseNamed(id))!!
            val tombstones = actual.nodes.filterIsInstance<LineageGraphNode.Tombstone>()
            val works = actual.nodes.filterIsInstance<LineageGraphNode.Work>()

            assertEquals("$id: one tombstone", 1, tombstones.size)
            assertEquals("$id: state", "tombstone", tombstones.single().state)
            // The type carries no `descriptionHash`, `renderHash` or `history`
            // member at all, which is the server's "the key is not there".
            // Nothing to assert as null -- there is nothing to read.

            // The other direction, in the same test: without it an implementation
            // that dropped the three from every node would pass.
            assertTrue("$id: there are non-tombstones to compare against", works.size >= 3)
            works.forEach { work ->
                val where = "$id/${work.id.take(8)}"
                assertNotNull("$where: description_hash", work.descriptionHash)
                assertNotNull("$where: render_hash", work.renderHash)
                assertNotNull("$where: history", work.history)
            }
        }
    }

    // --- T-4: the generation ---

    @Test
    fun generation_countsFromTheRootAndNotFromTheFocus() {
        // The same tree seen from the grandchild and from the root.
        val fromGrandchild = build(caseNamed("C2-focus-on-the-grandchild"))!!
        val fromRoot = build(caseNamed("C4-focus-on-the-root-depth-3"))!!

        fun generations(result: LineageGraphResult): Map<String, Int?> = result.nodes
            .filterIsInstance<LineageGraphNode.Work>()
            .associate { it.id to it.history?.lineageGeneration }

        val byGrandchild = generations(fromGrandchild)
        val byRoot = generations(fromRoot)

        assertEquals("both views hold the same four works", 4, byGrandchild.size)
        assertEquals(
            "the generation is the depth from the root, so moving the focus cannot move it",
            byRoot,
            byGrandchild,
        )
        assertEquals(
            "root 1, child 2, grandchild 3, great-grandchild 4",
            listOf(1, 2, 3, 4),
            fromRoot.nodes
                .filterIsInstance<LineageGraphNode.Work>()
                .sortedBy { it.at }
                .map { it.history?.lineageGeneration },
        )

        // A truncated graph still reports the depth from the root: C5 keeps two
        // nodes of a four-deep chain and the focus is still the fourth.
        val truncated = build(caseNamed("C5-node-limit-2"))!!
        assertEquals(2, truncated.nodes.size)
        assertEquals(
            listOf(3, 4),
            truncated.nodes
                .filterIsInstance<LineageGraphNode.Work>()
                .sortedBy { it.at }
                .map { it.history?.lineageGeneration },
        )
    }

    private companion object {
        const val FIXTURE = "/lineage/lineage-cases.json"
    }
}

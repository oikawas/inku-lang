package app.inku.mobile.data.lineage

import app.inku.mobile.data.db.LineageNodeEntity
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * T-1: the decision function reproduces every case of
 * `server_reference/lineage_wiring.json`, which was baked by running the real
 * `db.add_item` against a throwaway SQLite file.
 *
 * The cases are replayed in the generator's own order, because three of them
 * refer to a node an earlier case produced. Every key the fixture states is
 * compared -- the count is asserted at the end so that a case going missing
 * cannot quietly shrink the gate.
 *
 * This test drives `LineagePlanner` directly. It says nothing about whether
 * the save path calls it; that is what the instrumented `LineageWiringTest`
 * is for.
 */
class LineageWiringReferenceTest {

    private fun fixture(): JSONObject {
        val stream = javaClass.getResourceAsStream("/server_reference/lineage_wiring.json")
            ?: error("lineage_wiring.json is missing")
        return JSONObject(stream.bufferedReader().readText())
    }

    private fun plan(
        nodeId: String,
        historyId: String,
        at: Long,
        visibility: String? = null,
        declaration: LineageDeclaration = LineageDeclaration(),
        parentNode: LineageNodeEntity? = null,
    ): LineageWrite = LineagePlanner.plan(
        nodeId = nodeId,
        edgeId = "edge-of-$nodeId",
        historyId = historyId,
        at = at,
        descriptionHash = "dh1:0f2c",
        renderHash = "rh3:9ab1",
        historyVisibility = visibility,
        declaration = declaration,
        parentNode = parentNode,
    )

    private fun rejection(body: () -> Unit): String =
        try {
            body()
            "<not rejected>"
        } catch (exc: IllegalArgumentException) {
            exc.message ?: "<no message>"
        }

    @Test
    fun lineagePlanner_reproducesEveryCaseOfTheServerFixture() {
        val actual = mutableMapOf<String, Map<String, Any?>>()

        // 1. A work with no declared parent.
        val root = plan(nodeId = "n-root", historyId = "h-root", at = 1000L)
        actual["root-work-writes-one-node-and-no-edge"] = mapOf(
            "node_written" to true,
            "state" to root.node.state,
            "root_is_self" to (root.node.rootNodeId == root.node.id),
            "edge_written" to (root.edge != null),
            "description_hash_present" to !root.node.descriptionHash.isNullOrEmpty(),
            "render_hash_present" to !root.node.renderHash.isNullOrEmpty(),
            "node_at_equals_item_at" to (root.node.at == 1000L),
        )

        // 2. A declared derivation from it. The metadata goes in as {"b","a"}
        //    so that the canonical order has to be produced, not preserved.
        val child = plan(
            nodeId = "n-child", historyId = "h-child", at = 2000L,
            declaration = LineageDeclaration(
                parentNodeId = root.node.id,
                derivationKind = "touch_change",
                derivationMetadata = linkedMapOf("b" to 1, "a" to 2),
            ),
            parentNode = root.node,
        )
        actual["declared-derivation-writes-an-edge-and-inherits-the-root"] = mapOf(
            "node_written" to true,
            "edge_written" to (child.edge != null),
            "derivation_kind" to child.edge?.derivationKind,
            "root_is_self" to (child.node.rootNodeId == child.node.id),
            "child_root_equals_parent_root" to (child.node.rootNodeId == root.node.rootNodeId),
            "metadata_json" to child.edge?.metadataJson,
            "edge_at_equals_item_at" to (child.edge != null && child.edge.at == 2000L),
        )

        // 3. A derivation of the derivation.
        val grand = plan(
            nodeId = "n-grand", historyId = "h-grand", at = 3000L,
            declaration = LineageDeclaration(
                parentNodeId = child.node.id,
                derivationKind = "variation",
            ),
            parentNode = child.node,
        )
        actual["grandchild-keeps-the-original-root"] = mapOf(
            "root_equals_the_root_of_the_first_work" to (grand.node.rootNodeId == root.node.id),
            "root_equals_the_parent" to (grand.node.rootNodeId == child.node.id),
            "edge_parent_is_the_child_node" to
                (grand.edge != null && grand.edge.parentNodeId == child.node.id),
        )

        // 4. A save the history list is meant not to show.
        val hidden = plan(
            nodeId = "n-hidden", historyId = "h-hidden", at = 4000L,
            visibility = "lineage_only",
        )
        actual["lineage-only-visibility-sets-the-node-state"] = mapOf(
            "node_written" to true,
            "state" to hidden.node.state,
        )

        // 5-8. The four rejections, message included.
        actual["unknown-derivation-kind-is-rejected"] = rejected {
            plan(
                nodeId = "n-5", historyId = "h-5", at = 5000L,
                declaration = LineageDeclaration(
                    parentNodeId = root.node.id, derivationKind = "not_a_kind",
                ),
                parentNode = root.node,
            )
        }
        actual["derivation-kind-without-a-parent-is-rejected"] = rejected {
            plan(
                nodeId = "n-6", historyId = "h-6", at = 5000L,
                declaration = LineageDeclaration(derivationKind = "touch_change"),
            )
        }
        actual["missing-parent-is-rejected"] = rejected {
            plan(
                nodeId = "n-7", historyId = "h-7", at = 5000L,
                declaration = LineageDeclaration(
                    parentNodeId = "00000000-0000-0000-0000-000000000000",
                    derivationKind = "replay",
                ),
                parentNode = null,
            )
        }
        actual["non-object-derivation-metadata-is-rejected"] = rejected {
            plan(
                nodeId = "n-8", historyId = "h-8", at = 5000L,
                declaration = LineageDeclaration(
                    parentNodeId = root.node.id,
                    derivationKind = "replay",
                    derivationMetadata = listOf("not", "an", "object"),
                ),
                parentNode = root.node,
            )
        }

        val cases = fixture().getJSONArray("cases")
        var checked = 0
        for (i in 0 until cases.length()) {
            val case = cases.getJSONObject(i)
            val caseId = case.getString("case_id")
            val expected = case.getJSONObject("expected")
            val produced = actual[caseId] ?: error("no case in this test for $caseId")
            for (key in expected.keys()) {
                val want: Any? = expected.get(key).takeUnless { it == JSONObject.NULL }
                assertEquals("$caseId / $key", want, produced[key])
                checked++
            }
        }
        assertEquals("every case of the fixture is replayed", 8, cases.length())
        assertEquals("every assertion of the fixture is checked", 27, checked)
    }

    private fun rejected(body: () -> Unit): Map<String, Any?> {
        val message = rejection(body)
        return mapOf("rejected" to (message != "<not rejected>"), "message" to message)
    }

    /**
     * The empty-list case the fixture cannot show. `derivation_metadata or {}`
     * makes an empty list falsy on the server, so it becomes an accepted empty
     * object while a non-empty list is rejected. A port that checked the type
     * before the `or` would reject both.
     */
    @Test
    fun emptyMetadataIsAcceptedBecausePythonTreatsItAsFalsy() {
        val parent = LineageNodeEntity(id = "p", rootNodeId = "p")
        val write = plan(
            nodeId = "n", historyId = "h", at = 1L,
            declaration = LineageDeclaration(
                parentNodeId = "p", derivationKind = "replay", derivationMetadata = emptyList<String>(),
            ),
            parentNode = parent,
        )
        assertEquals("{}", write.edge?.metadataJson)
    }

    /** `sort_keys=True` is recursive, and the separators carry no spaces. */
    @Test
    fun canonicalJson_sortsNestedKeysAndKeepsNonAsciiRaw() {
        assertEquals(
            """{"a":{"x":1,"z":[2,"墨"]},"b":null}""",
            LineagePlanner.canonicalJson(
                linkedMapOf(
                    "b" to null,
                    "a" to linkedMapOf("z" to listOf(2, "墨"), "x" to 1),
                ),
            ),
        )
    }

    /** A parent that was tombstoned is not a parent (db.py:2106). */
    @Test
    fun aTombstonedParentIsNotFound() {
        val message = rejection {
            plan(
                nodeId = "n", historyId = "h", at = 1L,
                declaration = LineageDeclaration(parentNodeId = "p", derivationKind = "replay"),
                parentNode = LineageNodeEntity(id = "p", state = "tombstone", rootNodeId = "p"),
            )
        }
        assertEquals(LineagePlanner.PARENT_NOT_FOUND, message)
    }

    /**
     * A declared parent with no kind at all. `None not in
     * LINEAGE_DERIVATION_KINDS` is true, so the server calls it an invalid
     * kind rather than a missing one.
     */
    @Test
    fun aParentWithNoKindIsRejectedAsAnInvalidKind() {
        val message = rejection {
            plan(
                nodeId = "n", historyId = "h", at = 1L,
                declaration = LineageDeclaration(parentNodeId = "p"),
                parentNode = LineageNodeEntity(id = "p", rootNodeId = "p"),
            )
        }
        assertEquals(LineagePlanner.INVALID_KIND, message)
    }

    @Test
    fun anUnknownVisibilityIsRejected() {
        val message = rejection {
            plan(nodeId = "n", historyId = "h", at = 1L, visibility = "public")
        }
        assertEquals(LineagePlanner.INVALID_VISIBILITY, message)
        assertTrue("normal is the default", plan(nodeId = "n", historyId = "h", at = 1L).node.state == "active")
    }
}

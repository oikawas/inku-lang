package app.inku.mobile.data.lineage

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The server's `tests/test_description_lock.py`, case for case, with the same
 * names and the same expected sets, against the port in [DescriptionLock].
 *
 * The store is the server's five tables held in lists; `work` writes the same
 * rows the server test's `_work` does.
 */
class DescriptionLockTest {

    private class MemoryStore : DescriptionLock.Store {
        val nodes = mutableListOf<DescriptionLock.Node>()
        val edges = mutableListOf<DescriptionLock.Edge>()
        val histories = mutableListOf<DescriptionLock.HistoryDdl>()
        val links = mutableListOf<DescriptionLock.HistoryLink>()
        val authorityRows = mutableListOf<DescriptionLock.Authority>()

        override suspend fun nodesOfHistories(historyIds: Collection<String>) = nodes.filter { it.historyId in historyIds }
        override suspend fun nodesByIds(nodeIds: Collection<String>) = nodes.filter { it.id in nodeIds }
        override suspend fun edgesOfChildren(childNodeIds: Collection<String>) = edges.filter { it.childNodeId in childNodeIds }
        override suspend fun ddlOfHistories(historyIds: Collection<String>) = histories.filter { it.historyId in historyIds }
        override suspend fun historyLinks(historyIds: Collection<String>) = links.filter { it.historyId in historyIds }
        override suspend fun authorities(variationIds: Collection<String>) = authorityRows.filter { it.variationId in variationIds }

        fun work(
            historyId: String,
            parent: String? = null,
            kind: String? = null,
            authority: String? = null,
            ddl: String? = null,
        ) {
            if (ddl != null) histories += DescriptionLock.HistoryDdl(historyId, ddl, null)
            nodes += DescriptionLock.Node("n-$historyId", historyId)
            if (parent != null) edges += DescriptionLock.Edge("n-$parent", "n-$historyId", requireNotNull(kind))
            if (authority != null) {
                links += DescriptionLock.HistoryLink("u", historyId, "v-$historyId")
                authorityRows += DescriptionLock.Authority("u", "v-$historyId", authority)
            }
        }
    }

    private fun locked(store: MemoryStore, ids: List<String>) = runBlocking { DescriptionLock.lockedHistoryIds(store, ids) }
    private fun nodeLocked(store: MemoryStore, nodeId: String) = runBlocking { DescriptionLock.nodeIsLocked(store, nodeId) }

    @Test
    fun test_a_ddl_edit_and_what_keeps_its_ddl_are_locked_and_a_new_reading_is_not() {
        val store = MemoryStore()
        store.work("root", authority = "description_authoritative")
        store.work("edited", "root", "ddl_edit") // a DDL edit saved before the authority existed
        store.work("touched", "edited", "touch_change") // keeps the edited DDL
        store.work("recolored", "touched", "catalog_change")
        store.work("reread", "recolored", "reinterpretation") // back to the words
        store.work("reread-touched", "reread", "touch_change")
        store.work("authored", authority = "ddl_authoritative") // a DDL-authoritative variation
        store.work("sibling", "root", "layout_change")

        val everything = listOf("root", "edited", "touched", "recolored", "reread", "reread-touched", "authored", "sibling", "unknown")
        assertEquals(setOf("edited", "touched", "recolored", "authored"), locked(store, everything))
        assertEquals(true, nodeLocked(store, "n-recolored"))
        assertEquals(false, nodeLocked(store, "n-reread-touched"))
        assertEquals(emptySet<String>(), locked(store, emptyList()))
    }

    @Test
    fun test_a_replay_is_held_by_its_ddl_not_by_its_kind() {
        val store = MemoryStore()
        store.work("edited", authority = "ddl_authoritative", ddl = "Scene:\n  Moon")
        // The Describe tab saved an unchanged description drawn again as a
        // replay: Stage 1 wrote a new DDL, so it went back to the words.
        store.work("reread", "edited", "replay", authority = "description_authoritative", ddl = "Scene:\n  Sun")
        // The same DDL drawn again from the DDL panel: a DDL-authoritative
        // variation with no edit, held because its parent is.
        store.work("redrawn", "edited", "replay", authority = "ddl_authoritative", ddl = "Scene:  Moon")
        store.work("plain", authority = "description_authoritative", ddl = "Scene: Sun")
        store.work("plain-redrawn", "plain", "replay", authority = "ddl_authoritative", ddl = "Scene: Sun")
        store.work("plain-redrawn-touched", "plain-redrawn", "touch_change", ddl = "Scene: Sun, soft")
        store.work("unknown-ddl", "edited", "replay") // nothing to compare: as before

        val everything = listOf("edited", "reread", "redrawn", "plain", "plain-redrawn", "plain-redrawn-touched", "unknown-ddl")
        assertEquals(setOf("edited", "redrawn", "unknown-ddl"), locked(store, everything))
        assertEquals(false, nodeLocked(store, "n-plain-redrawn"))
    }

    @Test
    fun test_transferred_expanded_text_does_not_reclassify_a_historical_replay() {
        val store = MemoryStore()
        store.work("edited", authority = "ddl_authoritative", ddl = "Scene: Moon")
        // Its historical input DDL was absent. The transferred text is not
        // proof that this replay read the description again.
        store.work("transferred", "edited", "replay", ddl = "Scene: Sun")
        val index = store.histories.indexOfFirst { it.historyId == "transferred" }
        store.histories[index] = store.histories[index].copy(ddlSourceOrigin = "legacy_expanded")
        store.work("known-reread", "edited", "replay", ddl = "Scene: Sun")

        assertEquals(setOf("transferred"), locked(store, listOf("transferred", "known-reread")))
        assertEquals("Scene: Sun", store.histories.single { it.historyId == "transferred" }.ddl)
    }
}

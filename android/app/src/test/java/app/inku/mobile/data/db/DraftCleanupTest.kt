package app.inku.mobile.data.db

import org.junit.Assert.*
import org.junit.Test

class DraftCleanupTest {
    private fun schema(host: HostSqlite) {
        listOf(
            "CREATE TABLE variation_authority(owner_id TEXT, variation_id TEXT, revision TEXT, updated_at INTEGER, parent_variation_id TEXT)",
            "CREATE TABLE variation_authority_actions(owner_id TEXT, variation_id TEXT, revision TEXT, ddl_digest TEXT)",
            "CREATE TABLE pipeline_candidate_executions(owner_id TEXT, variation_id TEXT, execution_id TEXT, updated_at INTEGER)",
            "CREATE TABLE pipeline_history_links(owner_id TEXT, variation_id TEXT, history_id TEXT)",
            "CREATE TABLE history_items(id TEXT)",
        ).forEach(host.db::execSQL)
    }
    private fun draft(host: HostSqlite, id: String = "v", parent: String? = null, updated: Int = 1) {
        host.db.execSQL("INSERT INTO variation_authority VALUES ('o', ?, '1', ?, ?)", arrayOf<Any?>(id, updated, parent))
        host.db.execSQL("INSERT INTO variation_authority_actions VALUES ('o', ?, '1', 'd')", arrayOf<Any>(id))
        host.db.execSQL("INSERT INTO pipeline_candidate_executions VALUES ('o', ?, ?, ?)", arrayOf<Any>(id, "e-$id", updated))
    }
    private fun discard(host: HostSqlite, id: String = "v", revision: String? = null, before: Long? = null,
                        restored: String? = null, excluded: String? = null): DraftDiscardResult {
        host.db.beginTransaction()
        return try {
            val answer = discardDraftInTransaction(host.db, "o", id, revision, before, restored, excluded)
            host.db.setTransactionSuccessful(); answer
        } finally { host.db.endTransaction() }
    }

    @Test fun linkedDraftIsKept() = HostSqlite().use { h ->
        schema(h); draft(h); h.db.execSQL("INSERT INTO pipeline_history_links VALUES ('o','v','h')")
        assertEquals(DraftDiscardResult.Kept("linked"), discard(h))
    }
    @Test fun parentOfSavedDraftIsKept() = HostSqlite().use { h ->
        schema(h); draft(h); draft(h, "child", "v")
        assertEquals(DraftDiscardResult.Kept("has_child"), discard(h))
    }
    @Test fun revisionMismatchIsKept() = HostSqlite().use { h ->
        schema(h); draft(h); assertEquals(DraftDiscardResult.Kept("revision_moved"), discard(h, revision = "2"))
    }
    @Test fun restoredExecutionIsKept() = HostSqlite().use { h ->
        schema(h); draft(h); assertEquals(DraftDiscardResult.Kept("busy"), discard(h, before = 10, restored = "e-v"))
    }
    @Test fun anyNewExecutionProtectsOldDocument() = HostSqlite().use { h ->
        schema(h); draft(h); h.db.execSQL("INSERT INTO pipeline_candidate_executions VALUES ('o','v','new',10)")
        assertEquals(DraftDiscardResult.Kept("too_recent"), discard(h, before = 10))
    }
    @Test fun oldUnfinishedDraftAndItsRecordsAreRemoved() = HostSqlite().use { h ->
        schema(h); draft(h); assertEquals(DraftDiscardResult.Discarded, discard(h, before = 10))
        for (table in listOf("variation_authority", "variation_authority_actions", "pipeline_candidate_executions"))
            assertEquals("[]", h.rows("SELECT * FROM $table"))
        assertEquals(DraftDiscardResult.Absent, discard(h))
    }
    @Test fun oldDescendantsCanBeRemovedLeafFirst() = HostSqlite().use { h ->
        schema(h); draft(h); draft(h, "child", "v")
        assertEquals(DraftDiscardResult.Kept("has_child"), discard(h, before = 10))
        assertEquals(DraftDiscardResult.Discarded, discard(h, "child", before = 10))
        assertEquals(DraftDiscardResult.Discarded, discard(h, before = 10))
    }
    @Test fun cleanupFailureRollsBackAllDeletes() = HostSqlite().use { h ->
        schema(h); draft(h)
        h.db.execSQL("CREATE TRIGGER reject_action_delete BEFORE DELETE ON variation_authority_actions BEGIN SELECT RAISE(ABORT, 'injected'); END")
        try { discard(h); fail("deletion should fail") } catch (_: IllegalStateException) { }
        assertEquals(1, h.db.query("SELECT * FROM variation_authority").use { it.count })
        assertEquals(1, h.db.query("SELECT * FROM variation_authority_actions").use { it.count })
        assertEquals(1, h.db.query("SELECT * FROM pipeline_candidate_executions").use { it.count })
    }
    @Test fun permanentDeletionKeepsOtherWorksAndTombstoneLinks() = HostSqlite().use { h ->
        schema(h); draft(h)
        h.db.execSQL("INSERT INTO pipeline_history_links VALUES ('o','v','deleted'),('o','v','other')")
        h.db.execSQL("INSERT INTO history_items VALUES ('other')")
        assertEquals(DraftDiscardResult.Kept("linked"), discard(h, revision = "1", excluded = "deleted"))
        h.db.execSQL("DELETE FROM history_items WHERE id = 'other'")
        assertEquals(DraftDiscardResult.Kept("revision_moved"), discard(h, revision = "0", excluded = "other"))
        assertEquals(DraftDiscardResult.Discarded, discard(h, revision = "1", excluded = "other"))
        assertEquals(2, h.db.query("SELECT * FROM pipeline_history_links").use { it.count })
    }
    @Test fun deletedAuthorityCannotBeSavedAfterEarlierCheck() = HostSqlite().use { h ->
        schema(h); draft(h); requireCommittedVariation(h.db, "o", "v", "1", "d")
        assertEquals(DraftDiscardResult.Discarded, discard(h))
        h.db.beginTransaction()
        try {
            h.db.execSQL("INSERT INTO history_items VALUES ('new')")
            requireCommittedVariation(h.db, "o", "v", "1", "d")
            fail("save should refuse the deleted variation")
        } catch (_: VariationNotFoundException) {
            // No successful transaction: the earlier insert must roll back too.
        } finally { h.db.endTransaction() }
        assertEquals("[]", h.rows("SELECT * FROM history_items"))
        assertEquals("[]", h.rows("SELECT * FROM pipeline_history_links"))
    }
}

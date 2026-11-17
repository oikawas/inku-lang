package app.inku.mobile.data.db

import androidx.sqlite.db.SupportSQLiteDatabase

/** The caller holds the write transaction and the host's session gate. */
internal fun discardDraftInTransaction(
    db: SupportSQLiteDatabase, ownerId: String, variationId: String, revision: String? = null,
    before: Long? = null, restoredExecutionId: String? = null, excludedHistoryId: String? = null,
): DraftDiscardResult {
    val args = arrayOf<Any>(ownerId, variationId)
    val authority = db.query("SELECT revision, updated_at FROM variation_authority WHERE owner_id = ? AND variation_id = ?", args).use {
        if (!it.moveToFirst()) return DraftDiscardResult.Absent
        it.getString(0) to it.getLong(1)
    }
    fun exists(sql: String, values: Array<Any>) = db.query(sql, values).use { it.moveToFirst() }
    val linked = if (excludedHistoryId == null) exists(
        "SELECT 1 FROM pipeline_history_links WHERE owner_id = ? AND variation_id = ? LIMIT 1", args,
    ) else exists(
        "SELECT 1 FROM pipeline_history_links l JOIN history_items h ON h.id = l.history_id WHERE l.owner_id = ? AND l.variation_id = ? AND l.history_id != ? LIMIT 1",
        arrayOf(ownerId, variationId, excludedHistoryId),
    )
    if (linked) return DraftDiscardResult.Kept("linked")
    if (exists("SELECT 1 FROM variation_authority WHERE owner_id = ? AND parent_variation_id = ? LIMIT 1", args)) return DraftDiscardResult.Kept("has_child")
    if (revision != null && authority.first != revision) return DraftDiscardResult.Kept("revision_moved")
    if (before != null && (authority.second >= before || exists(
            "SELECT 1 FROM pipeline_candidate_executions WHERE owner_id = ? AND variation_id = ? AND updated_at >= ? LIMIT 1",
            arrayOf(ownerId, variationId, before),
        ))) return DraftDiscardResult.Kept("too_recent")
    if (restoredExecutionId != null && exists(
            "SELECT 1 FROM pipeline_candidate_executions WHERE owner_id = ? AND variation_id = ? AND execution_id = ? LIMIT 1",
            arrayOf(ownerId, variationId, restoredExecutionId),
        )) return DraftDiscardResult.Kept("busy")
    db.execSQL("DELETE FROM pipeline_candidate_executions WHERE owner_id = ? AND variation_id = ?", args)
    db.execSQL("DELETE FROM variation_authority_actions WHERE owner_id = ? AND variation_id = ?", args)
    db.execSQL("DELETE FROM variation_authority WHERE owner_id = ? AND variation_id = ?", args)
    return DraftDiscardResult.Discarded
}

/** Rechecked inside the history write transaction so a discarded authority cannot be linked. */
internal fun requireCommittedVariation(db: SupportSQLiteDatabase, ownerId: String, variationId: String, revision: String, digest: String) {
    val found = db.query(
        "SELECT 1 FROM variation_authority v JOIN variation_authority_actions a ON a.owner_id = v.owner_id AND a.variation_id = v.variation_id WHERE v.owner_id = ? AND v.variation_id = ? AND a.revision = ? AND a.ddl_digest = ? LIMIT 1",
        arrayOf<Any>(ownerId, variationId, revision, digest),
    ).use { it.moveToFirst() }
    if (!found) throw VariationNotFoundException()
}

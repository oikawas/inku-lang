package app.inku.mobile.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface LineageDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertNode(node: LineageNodeEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertEdge(edge: LineageEdgeEntity)

    @Query("SELECT * FROM lineage_nodes WHERE id = :id")
    suspend fun getNodeById(id: String): LineageNodeEntity?

    @Query("SELECT * FROM lineage_edges WHERE child_node_id = :childId")
    suspend fun getEdgeByChildId(childId: String): LineageEdgeEntity?

    @Query("SELECT * FROM lineage_edges WHERE parent_node_id = :parentId")
    suspend fun getEdgesByParentId(parentId: String): List<LineageEdgeEntity>

    /**
     * What a permanently deleted work's node becomes: it keeps its place and
     * its edges, and loses the work (`HistoryPermanentDeleteWriter`, server
     * `persistence/history.py`).
     */
    @Query(
        "UPDATE lineage_nodes SET state = 'tombstone', history_id = NULL, description_hash = NULL, " +
            "render_hash = NULL, deleted_at = :deletedAt WHERE id = :nodeId",
    )
    suspend fun tombstoneNode(nodeId: String, deletedAt: Long)

    /** The server empties the metadata of every edge touching a tombstoned node. */
    @Query("UPDATE lineage_edges SET metadata_json = '{}' WHERE parent_node_id = :nodeId OR child_node_id = :nodeId")
    suspend fun clearEdgeMetadataTouching(nodeId: String)

    // The three below gather the rows `LineageGraph.build` is handed. They only
    // fetch: which of the rows become the graph, and in which order, is decided
    // there, so that the same judgment answers for the device and for the baked
    // expectations.

    @Query("SELECT * FROM lineage_nodes WHERE id IN (:ids)")
    suspend fun getNodesByIds(ids: Collection<String>): List<LineageNodeEntity>

    @Query("SELECT * FROM lineage_edges WHERE child_node_id IN (:childIds)")
    suspend fun getEdgesByChildIds(childIds: Collection<String>): List<LineageEdgeEntity>

    @Query("SELECT * FROM lineage_edges WHERE parent_node_id IN (:parentIds)")
    suspend fun getEdgesByParentIds(parentIds: Collection<String>): List<LineageEdgeEntity>
}

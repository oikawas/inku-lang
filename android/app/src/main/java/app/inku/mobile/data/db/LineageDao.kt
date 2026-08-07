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

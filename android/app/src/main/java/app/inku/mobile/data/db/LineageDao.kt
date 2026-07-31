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
}

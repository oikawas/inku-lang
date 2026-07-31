package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "lineage_nodes")
data class LineageNodeEntity(
    @PrimaryKey
    val id: String,
    @ColumnInfo(name = "history_id")
    val historyId: Long? = null,
    val state: String = "active",
    @ColumnInfo(name = "description_hash")
    val descriptionHash: String? = null,
    @ColumnInfo(name = "render_hash")
    val renderHash: String? = null,
    val at: Long = System.currentTimeMillis(),
    @ColumnInfo(name = "deleted_at")
    val deletedAt: Long? = null,
    @ColumnInfo(name = "root_node_id")
    val rootNodeId: String? = null,
)

package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "lineage_edges",
    indices = [
        Index(value = ["child_node_id"], unique = true, name = "uq_lineage_primary_parent"),
    ],
)
data class LineageEdgeEntity(
    @PrimaryKey
    val id: String,
    @ColumnInfo(name = "parent_node_id")
    val parentNodeId: String,
    @ColumnInfo(name = "child_node_id")
    val childNodeId: String,
    @ColumnInfo(name = "derivation_kind")
    val derivationKind: String,
    @ColumnInfo(name = "metadata_json", defaultValue = "'{}'")
    val metadataJson: String = "{}",
    val at: Long = System.currentTimeMillis(),
)

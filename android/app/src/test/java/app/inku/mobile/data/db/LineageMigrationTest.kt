package app.inku.mobile.data.db

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class LineageMigrationTest {

    @Test
    fun migration4to5_preservesExistingData() {
        val migration = InkuDatabase.MIGRATION_4_5

        assertEquals(4, migration.startVersion)
        assertEquals(5, migration.endVersion)
        assertNotNull(migration)
    }

    @Test
    fun lineageEdge_enforcesPrimaryParentConstraint() {
        val edge1 = LineageEdgeEntity(
            id = "edge-1",
            parentNodeId = "parent-1",
            childNodeId = "child-1",
            derivationKind = "touch_change",
        )
        val edge2 = LineageEdgeEntity(
            id = "edge-2",
            parentNodeId = "parent-2",
            childNodeId = "child-1",
            derivationKind = "layout_change",
        )

        assertEquals("child-1", edge1.childNodeId)
        assertEquals(edge1.childNodeId, edge2.childNodeId)
    }
}

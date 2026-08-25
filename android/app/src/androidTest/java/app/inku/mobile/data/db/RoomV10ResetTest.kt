package app.inku.mobile.data.db

import android.database.sqlite.SQLiteConstraintException
import android.database.sqlite.SQLiteDatabase
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RoomV10ResetTest {

    private data class TestTargets(
        val databaseName: String,
        val databaseFile: File,
        val thumbnailsDirectory: File,
        val modelSentinel: File,
    ) {
        val thumbnailSentinel = File(thumbnailsDirectory, "thumbnail.bin")
        val associatedDatabaseFiles = listOf(
            databaseFile,
            File(databaseFile.parentFile, "$databaseName-journal"),
            File(databaseFile.parentFile, "$databaseName-wal"),
            File(databaseFile.parentFile, "$databaseName-shm"),
        )
    }

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val targets = mutableListOf<TestTargets>()
    private val openDatabases = mutableListOf<InkuDatabase>()

    @After
    fun tearDown() {
        openDatabases.toList().forEach(::closeDatabase)
        targets.forEach { target ->
            context.deleteDatabase(target.databaseName)
            target.associatedDatabaseFiles.forEach(File::delete)
            target.thumbnailsDirectory.deleteRecursively()
            target.modelSentinel.delete()
        }
    }

    @Test
    fun versions1Through9AreResetToFreshV10WithOnlyDerivedFilesDeleted() {
        for (version in 1..9) {
            val target = newTargets("reset-v$version")
            createMarkerDatabase(target, version)
            target.associatedDatabaseFiles.drop(1).forEach { sidecar ->
                if (!sidecar.exists()) {
                    sidecar.createNewFile()
                }
                sidecar.writeBytes(byteArrayOf())
                assertTrue("isolated ${sidecar.name} exists", sidecar.exists())
                assertEquals("isolated ${sidecar.name} is not a hot journal", 0L, sidecar.length())
            }
            writeSentinels(target)
            val modelBytes = target.modelSentinel.readBytes()

            assertEquals(
                "v$version is on the one-time reset allowlist",
                RoomV10ResetCoordinator.Result.Ready(resetPerformed = true),
                prepare(target),
            )
            assertTrue(
                "v$version main database and journal files are deleted",
                target.associatedDatabaseFiles.none(File::exists),
            )
            assertFalse("v$version derived thumbnails are deleted", target.thumbnailsDirectory.exists())
            assertArrayEquals("model bytes are outside the reset boundary", modelBytes, target.modelSentinel.readBytes())

            val db = openPrepared(target)
            assertEquals(10, userVersion(db.openHelper.writableDatabase))
            assertEquals(
                "the pre-v10 marker is not migrated into the replacement",
                0,
                scalarInt(
                    db.openHelper.writableDatabase,
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'reset_marker'",
                ),
            )
            closeDatabase(db)
        }
    }

    @Test
    fun realWalV9IsClassifiedAfterItsHandleClosesAndFullyReset() {
        val target = newTargets("real-wal-v9")
        target.databaseFile.parentFile?.mkdirs()
        val walFile = File(target.databaseFile.parentFile, "${target.databaseName}-wal")
        val shmFile = File(target.databaseFile.parentFile, "${target.databaseName}-shm")
        val database = SQLiteDatabase.openOrCreateDatabase(target.databaseFile, null)
        try {
            assertTrue(
                "isolated file-backed Android SQLite enables WAL on this platform",
                database.enableWriteAheadLogging(),
            )
            disableWalAutoCheckpoint(database)
            database.execSQL("CREATE TABLE wal_marker (value TEXT NOT NULL)")
            database.version = 9
            database.execSQL("INSERT INTO wal_marker (value) VALUES ('genuine-wal-write')")

            database.rawQuery("PRAGMA journal_mode", null).use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("wal", cursor.getString(0).lowercase())
            }
            database.rawQuery("SELECT COUNT(*) FROM wal_marker", null).use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("the WAL contains a genuine write", 1, cursor.getInt(0))
            }
            assertEquals("user_version is genuinely v9", 9, database.version)
            assertTrue("a genuine WAL file was observed while open", walFile.exists() && walFile.length() > 0L)
            assertTrue("a genuine SHM file was observed while open", shmFile.exists() && shmFile.length() > 0L)
        } finally {
            database.close()
        }

        assertFalse("the Android SQLite handle is closed before classification", database.isOpen)
        assertEquals(
            RoomV10ResetCoordinator.Result.Ready(resetPerformed = true),
            prepare(target),
        )
        assertTrue(
            "the reset leaves no main, journal, WAL, or SHM file",
            target.associatedDatabaseFiles.none(File::exists),
        )
    }

    @Test
    fun activeWalV10IsClassifiedFromWalWithoutDeletingTheWriterOrData() {
        val target = newTargets("active-wal-v10")
        target.databaseFile.parentFile?.mkdirs()
        val walFile = File(target.databaseFile.parentFile, "${target.databaseName}-wal")
        val shmFile = File(target.databaseFile.parentFile, "${target.databaseName}-shm")
        val database = SQLiteDatabase.openOrCreateDatabase(target.databaseFile, null)
        try {
            assertTrue(
                "isolated file-backed Android SQLite enables WAL on this platform",
                database.enableWriteAheadLogging(),
            )
            disableWalAutoCheckpoint(database)
            database.beginTransaction()
            try {
                database.execSQL("CREATE TABLE active_wal_marker (value TEXT NOT NULL)")
                database.version = 10
                database.execSQL("INSERT INTO active_wal_marker (value) VALUES ('still-live')")
                database.setTransactionSuccessful()
            } finally {
                database.endTransaction()
            }

            assertEquals("the writer reads user_version 10 from WAL", 10, database.version)
            assertEquals(
                "the uncheckpointed main-file header still carries version 0",
                0,
                sqliteHeaderUserVersion(target.databaseFile),
            )
            assertTrue("the active writer has a genuine WAL", walFile.exists() && walFile.length() > 0L)
            assertTrue("the active writer has a genuine SHM", shmFile.exists() && shmFile.length() > 0L)

            assertEquals(
                "the coordinator's separate read-only connection sees v10 in the active WAL",
                RoomV10ResetCoordinator.Result.Ready(resetPerformed = false),
                prepare(target),
            )
            assertTrue("classification leaves the writer handle open", database.isOpen)
            assertTrue("classification retains the main database", target.databaseFile.exists())
            assertTrue("classification retains the live WAL", walFile.exists() && walFile.length() > 0L)
            assertTrue("classification retains the live SHM", shmFile.exists() && shmFile.length() > 0L)
            assertEquals("classification does not checkpoint the main header", 0, sqliteHeaderUserVersion(target.databaseFile))
            assertEquals("classification retains the writer's v10 view", 10, database.version)
            database.rawQuery("SELECT value FROM active_wal_marker", null).use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("still-live", cursor.getString(0))
            }
        } finally {
            database.close()
        }
    }

    @Test
    fun missingAndZeroByteDatabasesOpenAsFreshV10() {
        listOf("missing" to false, "empty" to true).forEach { (label, createEmptyFile) ->
            val target = newTargets(label)
            if (createEmptyFile) {
                target.databaseFile.parentFile?.mkdirs()
                assertTrue(target.databaseFile.createNewFile())
                assertEquals(0L, target.databaseFile.length())
            }

            assertEquals(
                RoomV10ResetCoordinator.Result.Ready(resetPerformed = false),
                prepare(target),
            )
            val db = openPrepared(target)
            assertEquals("$label database is created at v10", 10, userVersion(db.openHelper.writableDatabase))
            closeDatabase(db)
        }
    }

    @Test
    fun existingV10KeepsItsRowsAndThumbnails() {
        val target = newTargets("keep-v10")
        val initial = openPrepared(target)
        initial.openHelper.writableDatabase.execSQL(
            "CREATE TABLE reset_marker (value TEXT NOT NULL)",
        )
        initial.openHelper.writableDatabase.execSQL(
            "INSERT INTO reset_marker (value) VALUES ('keep-me')",
        )
        closeDatabase(initial)
        writeSentinels(target)
        val thumbnailBytes = target.thumbnailSentinel.readBytes()
        val modelBytes = target.modelSentinel.readBytes()

        assertEquals(
            RoomV10ResetCoordinator.Result.Ready(resetPerformed = false),
            prepare(target),
        )
        assertArrayEquals(thumbnailBytes, target.thumbnailSentinel.readBytes())
        assertArrayEquals(modelBytes, target.modelSentinel.readBytes())

        val reopened = openPrepared(target)
        assertEquals(10, userVersion(reopened.openHelper.writableDatabase))
        reopened.openHelper.writableDatabase.query("SELECT value FROM reset_marker").use { cursor ->
            assertTrue(cursor.moveToFirst())
            assertEquals("keep-me", cursor.getString(0))
        }
        closeDatabase(reopened)
    }

    @Test
    fun futureVersionNonemptyV0AndUnreadableDatabaseAreBytePreservingRefusals() {
        val future = newTargets("refuse-v11")
        createMarkerDatabase(future, 11)
        assertRefusalPreserves(
            future,
            RoomV10ResetCoordinator.Result.Refused(
                RoomV10ResetCoordinator.RefusalReason.UnexpectedVersion,
                detectedVersion = 11,
            ),
        )

        val nonemptyV0 = newTargets("refuse-v0")
        createMarkerDatabase(nonemptyV0, 0)
        assertRefusalPreserves(
            nonemptyV0,
            RoomV10ResetCoordinator.Result.Refused(
                RoomV10ResetCoordinator.RefusalReason.UnexpectedVersion,
                detectedVersion = 0,
            ),
        )

        val unreadable = newTargets("refuse-unreadable")
        unreadable.databaseFile.parentFile?.mkdirs()
        unreadable.databaseFile.writeBytes("not a sqlite database".toByteArray())
        assertRefusalPreserves(
            unreadable,
            RoomV10ResetCoordinator.Result.Refused(
                RoomV10ResetCoordinator.RefusalReason.UnreadableDatabase,
            ),
        )
    }

    @Test
    fun freshV10EnforcesLineageUniquenessSelfEdgeAndNullSemantics() {
        val target = newTargets("constraints")
        assertEquals(
            RoomV10ResetCoordinator.Result.Ready(resetPerformed = false),
            prepare(target),
        )
        val db = openPrepared(target).openHelper.writableDatabase

        insertHistory(db, "history-1", "lineage-shared")
        assertConstraint("history lineage_node_id is unique when non-null") {
            insertHistory(db, "history-2", "lineage-shared")
        }
        insertHistory(db, "history-null-1", null)
        insertHistory(db, "history-null-2", null)
        assertEquals(
            "multiple absent history lineage mappings retain their NULL meaning",
            2,
            scalarInt(db, "SELECT COUNT(*) FROM history_items WHERE lineage_node_id IS NULL"),
        )

        insertLineageNode(db, "node-1", "history-shared")
        assertConstraint("lineage node history_id is unique when non-null") {
            insertLineageNode(db, "node-2", "history-shared")
        }
        insertLineageNode(db, "node-null-1", null)
        insertLineageNode(db, "node-null-2", null)
        assertEquals(
            "multiple absent node history mappings retain their NULL meaning",
            2,
            scalarInt(db, "SELECT COUNT(*) FROM lineage_nodes WHERE history_id IS NULL"),
        )

        insertLineageEdge(db, "edge-1", "parent-1", "child-shared")
        assertConstraint("a child has only one primary parent") {
            insertLineageEdge(db, "edge-2", "parent-2", "child-shared")
        }
        assertConstraint("a lineage edge cannot reference itself") {
            insertLineageEdge(db, "edge-self", "same-node", "same-node")
        }
        assertConstraint("a valid lineage edge cannot be updated into a self-edge") {
            db.execSQL(
                "UPDATE lineage_edges SET parent_node_id = child_node_id WHERE id = 'edge-1'",
            )
        }
        db.query(
            "SELECT parent_node_id, child_node_id FROM lineage_edges WHERE id = 'edge-1'",
        ).use { cursor ->
            assertTrue(cursor.moveToFirst())
            assertEquals("parent-1", cursor.getString(0))
            assertEquals("child-shared", cursor.getString(1))
        }
    }

    @Test
    fun version9CannotBypassTheCoordinatorThroughMigrationOrFallback() {
        val target = newTargets("no-v9-open-path")
        createMarkerDatabase(target, 9)

        val room = openPrepared(target)
        val failure = runCatching { room.openHelper.writableDatabase }.exceptionOrNull()
        assertNotNull("opening v9 directly must have no migration or destructive fallback path", failure)
        closeDatabase(room)

        SQLiteDatabase.openDatabase(
            target.databaseFile.absolutePath,
            null,
            SQLiteDatabase.OPEN_READONLY,
        ).use { database ->
            assertEquals("failed direct open does not rewrite the version", 9, database.version)
            database.rawQuery("SELECT value FROM reset_marker", null).use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("marker-v9", cursor.getString(0))
            }
        }
    }

    private fun newTargets(label: String): TestTargets {
        val stem = "i376-test-$label-${UUID.randomUUID()}"
        return TestTargets(
            databaseName = "$stem.sqlite",
            databaseFile = context.getDatabasePath("$stem.sqlite"),
            thumbnailsDirectory = File(context.filesDir, "$stem-thumbnails"),
            modelSentinel = File(File(context.filesDir, "models"), "$stem-model-sentinel.bin"),
        ).also(targets::add)
    }

    private fun prepare(target: TestTargets): RoomV10ResetCoordinator.Result =
        RoomV10ResetCoordinator.prepare(
            context = context,
            databaseName = target.databaseName,
            thumbnailsDirectory = target.thumbnailsDirectory,
        )

    private fun openPrepared(target: TestTargets): InkuDatabase =
        InkuDatabase.openPrepared(context, target.databaseName).also(openDatabases::add)

    private fun closeDatabase(database: InkuDatabase) {
        database.close()
        openDatabases.remove(database)
    }

    private fun createMarkerDatabase(target: TestTargets, version: Int) {
        target.databaseFile.parentFile?.mkdirs()
        SQLiteDatabase.openOrCreateDatabase(target.databaseFile, null).use { database ->
            database.execSQL("CREATE TABLE reset_marker (value TEXT NOT NULL)")
            database.execSQL("INSERT INTO reset_marker (value) VALUES ('marker-v$version')")
            database.version = version
        }
    }

    private fun disableWalAutoCheckpoint(database: SQLiteDatabase) {
        database.rawQuery("PRAGMA wal_autocheckpoint = 0", null).use { cursor ->
            assertTrue(cursor.moveToFirst())
            assertEquals("WAL auto-checkpointing is disabled for direct observation", 0, cursor.getInt(0))
        }
    }

    private fun sqliteHeaderUserVersion(databaseFile: File): Int {
        val bytes = databaseFile.readBytes()
        assertTrue("SQLite header contains user_version", bytes.size >= 64)
        return ((bytes[60].toInt() and 0xff) shl 24) or
            ((bytes[61].toInt() and 0xff) shl 16) or
            ((bytes[62].toInt() and 0xff) shl 8) or
            (bytes[63].toInt() and 0xff)
    }

    private fun writeSentinels(target: TestTargets) {
        assertTrue(target.thumbnailsDirectory.mkdirs())
        target.thumbnailSentinel.writeBytes("derived thumbnail".toByteArray())
        target.modelSentinel.parentFile?.let { parent ->
            if (!parent.exists()) {
                assertTrue(parent.mkdirs())
            }
        }
        target.modelSentinel.writeBytes("model sentinel outside thumbnails".toByteArray())
    }

    private fun assertRefusalPreserves(
        target: TestTargets,
        expected: RoomV10ResetCoordinator.Result.Refused,
    ) {
        writeSentinels(target)
        val databaseBytes = target.databaseFile.readBytes()
        val thumbnailBytes = target.thumbnailSentinel.readBytes()
        val modelBytes = target.modelSentinel.readBytes()

        assertEquals(expected, prepare(target))
        assertArrayEquals("refused database bytes are unchanged", databaseBytes, target.databaseFile.readBytes())
        assertArrayEquals("refused thumbnail bytes are unchanged", thumbnailBytes, target.thumbnailSentinel.readBytes())
        assertArrayEquals("refused model bytes are unchanged", modelBytes, target.modelSentinel.readBytes())
    }

    private fun userVersion(database: SupportSQLiteDatabase): Int =
        scalarInt(database, "PRAGMA user_version")

    private fun scalarInt(database: SupportSQLiteDatabase, query: String): Int =
        database.query(query).use { cursor ->
            check(cursor.moveToFirst())
            cursor.getInt(0)
        }

    private fun insertHistory(database: SupportSQLiteDatabase, id: String, lineageNodeId: String?) {
        database.execSQL(
            """
            INSERT INTO history_items (
                id, created_at, updated_at, original_input, normalized_ddl,
                score_json, display_svg, render_metadata_json, render_hash,
                render_hash_short, color_catalog_id, canvas_aspect, starred,
                trashed, lineage_node_id
            ) VALUES (?, 1, 1, 'input', 'input', '{}', '<svg/>', '{}', ?, 'short', 'sumi', '1:1', 0, 0, ?)
            """.trimIndent(),
            arrayOf<Any?>(id, "render-$id", lineageNodeId),
        )
    }

    private fun insertLineageNode(database: SupportSQLiteDatabase, id: String, historyId: String?) {
        database.execSQL(
            "INSERT INTO lineage_nodes (id, history_id, state, at) VALUES (?, ?, 'active', 1)",
            arrayOf<Any?>(id, historyId),
        )
    }

    private fun insertLineageEdge(
        database: SupportSQLiteDatabase,
        id: String,
        parentNodeId: String,
        childNodeId: String,
    ) {
        database.execSQL(
            """
            INSERT INTO lineage_edges (
                id, parent_node_id, child_node_id, derivation_kind, metadata_json, at
            ) VALUES (?, ?, ?, 'refine', '{}', 1)
            """.trimIndent(),
            arrayOf<Any>(id, parentNodeId, childNodeId),
        )
    }

    private fun assertConstraint(message: String, block: () -> Unit) {
        val failure = runCatching(block).exceptionOrNull()
        assertTrue("$message; got $failure", failure is SQLiteConstraintException)
    }
}

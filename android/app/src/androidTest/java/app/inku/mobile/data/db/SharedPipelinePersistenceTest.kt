package app.inku.mobile.data.db

import android.content.Context
import androidx.room.Room
import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.lineage.LineageWrite
import app.inku.mobile.pipeline.AuthoringContext
import java.security.MessageDigest
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SharedPipelinePersistenceTest {
    private val context: Context = InstrumentationRegistry.getInstrumentation().targetContext
    private val databaseName = "i376-test-shared-pipeline-${UUID.randomUUID()}.sqlite"
    private var database: InkuDatabase? = null

    @get:Rule
    val migrationHelper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        InkuDatabase::class.java.canonicalName,
        FrameworkSQLiteOpenHelperFactory(),
    )

    @After
    fun tearDown() {
        database?.close()
        context.deleteDatabase(databaseName)
    }

    @Test
    fun v10MigrationKeepsLegacyAndAtomicallySavesAuthorityHistoryAndExactForkContext() = runBlocking {
        migrationHelper.createDatabase(databaseName, 10).use { db ->
            db.execSQL(
                """
                INSERT INTO history_items (
                    id, created_at, updated_at, original_input, normalized_ddl,
                    score_json, display_svg, render_metadata_json, render_hash,
                    render_hash_short, color_catalog_id, canvas_aspect, starred, trashed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """.trimIndent(),
                arrayOf<Any>(
                    "legacy-history", 1L, 1L, "古い記述", "古いDDL", "{}", "<svg/>", "{}",
                    "legacy-hash", "legacy", "sumi", "square", 0, 0,
                ),
            )
        }

        migrationHelper.runMigrationsAndValidate(
            databaseName,
            11,
            true,
            InkuDatabase.MIGRATION_10_11,
        ).use { db ->
            db.query("SELECT original_input FROM history_items WHERE id = 'legacy-history'").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("古い記述", cursor.getString(0))
            }
        }

        val opened = Room.databaseBuilder(context, InkuDatabase::class.java, databaseName)
            .addMigrations(InkuDatabase.MIGRATION_10_11)
            .build()
            .also { database = it }
        val store = RoomSharedPipelineStore(opened, now = { 1_777_777_777L })

        val legacy = store.readHistory("local-owner", "legacy-history")
        assertNotNull(legacy)
        assertEquals("legacy_unknown", legacy!!.authority)

        val source = "赤い円を描く。"
        val digest = sha256(source)
        val context = AuthoringContext(
            description = "古いDDLを編集した作品",
            derivationKind = "legacy_ddl_fork",
            parentLegacyHistoryId = "legacy-history",
        )
        val firstAction = actionJson(
            actionId = "1".repeat(64),
            attempt = 1,
            source = source,
            expectedRevision = "0",
            nextRevision = "1",
        )
        val committed = JSONObject(store.commit("local-owner", firstAction, true, context))
        assertEquals("visible_normalized_ddl_committed", committed.getString("tag"))
        assertEquals("1", committed.getString("revision"))

        val replayed = JSONObject(
            store.commit(
                "local-owner",
                JSONObject(firstAction)
                    .apply { getJSONObject("identity").put("attempt", 2) }
                    .toString(),
                true,
                context,
            ),
        )
        assertEquals("visible_normalized_ddl_committed", replayed.getString("tag"))
        assertEquals(2L, replayed.getJSONObject("identity").getLong("attempt"))

        val stale = JSONObject(
            store.commit(
                "local-owner",
                actionJson(
                    actionId = "2".repeat(64),
                    attempt = 1,
                    source = "青い円を描く。",
                    expectedRevision = "0",
                    nextRevision = "1",
                ),
                false,
                context,
            ),
        )
        assertEquals("host_commit_failed", stale.getString("tag"))
        assertEquals("1", stale.getString("actual_revision"))

        store.create(
            ownerId = "local-owner",
            executionId = "execution-1",
            variationId = "variation-1",
            sequence = "0",
            stateBytes = "{\"snapshot\":0}".toByteArray(),
        )
        assertTrue(
            store.compareAndSet(
                ownerId = "local-owner",
                executionId = "execution-1",
                expectedSequence = "0",
                nextSequence = "1",
                stateBytes = "{\"snapshot\":1}".toByteArray(),
            ),
        )
        assertTrue(
            !store.compareAndSet(
                ownerId = "local-owner",
                executionId = "execution-1",
                expectedSequence = "0",
                nextSequence = "1",
                stateBytes = "{\"snapshot\":99}".toByteArray(),
            ),
        )
        assertEquals("{\"snapshot\":1}", store.load("local-owner", "execution-1")!!.toString(Charsets.UTF_8))

        opened.lineageDao().insertEdge(
            LineageEdgeEntity(
                id = "existing-edge",
                parentNodeId = "existing-parent",
                childNodeId = "rollback-node",
                derivationKind = "direct_ddl",
            ),
        )
        val rollbackHistory = historyItem("rollback-history", source).copy(lineageNodeId = "rollback-node")
        val rollback = runCatching {
            store.saveManagedHistory(
                rollbackHistory,
                LineageWrite(
                    node = LineageNodeEntity(
                        id = "rollback-node",
                        historyId = rollbackHistory.id,
                        descriptionHash = "rollback-description",
                        renderHash = rollbackHistory.renderHash,
                        rootNodeId = "rollback-node",
                    ),
                    edge = LineageEdgeEntity(
                        id = "colliding-edge",
                        parentNodeId = "existing-parent",
                        childNodeId = "rollback-node",
                        derivationKind = "direct_ddl",
                    ),
                ),
                managedLink("local-owner", source, digest),
            )
        }.exceptionOrNull()
        assertNotNull("a colliding lineage edge rejects the managed save", rollback)
        assertEquals(null, opened.historyDao().getById("rollback-history"))
        assertEquals(null, opened.lineageDao().getNodeById("rollback-node"))
        assertEquals(null, opened.sharedPipelineDao().getHistoryLink("local-owner", "rollback-history"))

        val history = historyItem("managed-history", source)
        val lineage = LineageWrite(
            node = LineageNodeEntity(
                id = "managed-node",
                historyId = history.id,
                descriptionHash = "description-hash",
                renderHash = history.renderHash,
                at = history.createdAt,
                rootNodeId = "managed-node",
            ),
            edge = null,
        )
        store.saveManagedHistory(
            history,
            lineage,
            managedLink("local-owner", source, digest),
        )

        val managed = store.readHistory("local-owner", "managed-history")
        assertNotNull(managed)
        assertEquals("ddl_authoritative", managed!!.authority)
        assertEquals("variation-1", managed.variationId)
        assertEquals("1", managed.revision)
        assertEquals(null, managed.warning)
        val savedContext = JSONObject(managed.forkContextJson!!)
        assertEquals(RoomSharedPipelineStore.HISTORY_CONTEXT_PROTOCOL, savedContext.getString("protocol_version"))
        assertEquals("saved", savedContext.getJSONObject("config").getJSONObject("compiler").getString("policy"))
        assertEquals(
            "square",
            savedContext.getJSONObject("host_options").getString("canvas_format"),
        )
        assertEquals(
            "#ff0000",
            savedContext.getJSONObject("color_maps").getJSONObject("basic").getString("red"),
        )
        assertTrue(
            savedContext.getJSONObject("pipeline_diagnostics")
                .getJSONArray("resource_omissions")
                .length() == 0,
        )

        val advanced = JSONObject(
            store.commit(
                "local-owner",
                actionJson(
                    actionId = "3".repeat(64),
                    attempt = 1,
                    source = "赤い円と線を描く。",
                    expectedRevision = "1",
                    nextRevision = "2",
                ),
                false,
                context,
            ),
        )
        assertEquals("2", advanced.getString("revision"))

        val replayHistory = historyItem("managed-replay", source).copy(
            lineageNodeId = "managed-replay-node",
            renderHash = "managed-replay-hash",
            renderHashShort = "replay",
        )
        store.saveManagedReplayHistory(
            replayHistory,
            LineageWrite(
                node = LineageNodeEntity(
                    id = "managed-replay-node",
                    historyId = replayHistory.id,
                    descriptionHash = "replay-description-hash",
                    renderHash = replayHistory.renderHash,
                    at = replayHistory.createdAt,
                    rootNodeId = "managed-replay-node",
                ),
                edge = null,
            ),
            ManagedHistoryReplayInput(
                ownerId = "local-owner",
                sourceHistoryId = history.id,
                hostOptionsJson = JSONObject()
                    .put("catalog_id", "vivid")
                    .put("canvas_aspect", "wide")
                    .put("render_seed", "42")
                    .toString(),
                resolvedColorMapJson = JSONObject().put("red", "#00ff00").toString(),
                pipelineDiagnosticsJson = JSONObject(diagnosticsJson())
                    .put("render_diagnostics", JSONObject().put("renderer", "replay"))
                    .toString(),
            ),
        )
        val replay = store.readHistory("local-owner", replayHistory.id)
        assertNotNull(replay)
        assertEquals("ddl_authoritative", replay!!.authority)
        assertEquals("variation-1", replay.variationId)
        assertEquals("1", replay.revision)
        assertEquals(source, replay.history.normalizedDdl)
        val replayContext = JSONObject(replay.forkContextJson!!)
        assertEquals("saved", replayContext.getJSONObject("config").getJSONObject("compiler").getString("policy"))
        assertEquals("wide", replayContext.getJSONObject("host_options").getString("canvas_aspect"))
        assertEquals("#00ff00", replayContext.getJSONObject("color_maps").getJSONObject("vivid").getString("red"))
        assertEquals(
            "replay",
            replayContext.getJSONObject("pipeline_diagnostics").getJSONObject("render_diagnostics").getString("renderer"),
        )
        assertEquals("2", store.readAuthority("local-owner", "variation-1")!!.revision)
        val historical = store.readHistory("local-owner", "managed-history")
        assertNotNull(historical)
        assertEquals("an old performance keeps its exact saved authority", "ddl_authoritative", historical!!.authority)
        assertEquals("1", historical.revision)
        assertEquals(digest, historical.ddlDigest)

        opened.openHelper.writableDatabase.execSQL(
            "UPDATE pipeline_history_links SET fork_context_bytes = ? WHERE history_id = ?",
            arrayOf("{broken".toByteArray(), "managed-history"),
        )
        val corrupt = store.readHistory("local-owner", "managed-history")
        assertNotNull(corrupt)
        assertNotNull(corrupt!!.warning)
        assertEquals(source, corrupt.history.normalizedDdl)
        assertEquals(history.scoreJson, corrupt.history.scoreJson)
        assertEquals(history.displaySvg, corrupt.history.displaySvg)
    }

    private fun actionJson(
        actionId: String,
        attempt: Int,
        source: String,
        expectedRevision: String,
        nextRevision: String,
    ): String {
        val nextState = JSONObject()
            .put("protocol_version", RoomSharedPipelineStore.AUTHORITY_PROTOCOL)
            .put("revision", nextRevision)
            .put("origin", "user_authored_ddl")
            .put("authority", "ddl_authoritative")
        return JSONObject()
            .put("tag", "commit_visible_normalized_ddl")
            .put("version", 1)
            .put(
                "identity",
                JSONObject()
                    .put("action_id", actionId)
                    .put("attempt", attempt)
                    .put("request_digest", "a".repeat(64)),
            )
            .put("timeout_ms", "0")
            .put("delay_ms", "0")
            .put(
                "payload",
                JSONObject()
                    .put("variation_id", "variation-1")
                    .put(
                        "document",
                        JSONObject()
                            .put("source", source)
                            .put("language", "ja")
                            .put("macro_locks", JSONArray()),
                    )
                    .put("ddl_digest", sha256(source))
                    .put(
                        "authority",
                        JSONObject()
                            .put("expected_revision", expectedRevision)
                            .put("next_state", nextState),
                    )
                    .put("authority_digest", "b".repeat(64))
                    .put("reason", "direct_ddl"),
            )
            .toString()
    }

    private fun diagnosticsJson(): String = JSONObject()
        .put("upstream_diagnostics", JSONArray())
        .put("downstream_diagnostics", JSONArray())
        .put("resource_omissions", JSONArray())
        .put("relation_omissions", JSONArray())
        .put("render_diagnostics", JSONObject().put("renderer", "saved"))
        .put("resource_execution", JSONObject().put("logical_objects", 1))
        .toString()

    private fun managedLink(
        ownerId: String,
        source: String,
        digest: String,
    ) = ManagedHistoryLinkInput(
        ownerId = ownerId,
        variationId = "variation-1",
        revision = "1",
        ddlDigest = digest,
        snapshotJson = JSONObject()
            .put("variation_id", "variation-1")
            .put(
                "authority",
                JSONObject()
                    .put("protocol_version", RoomSharedPipelineStore.AUTHORITY_PROTOCOL)
                    .put("revision", "1")
                    .put("origin", "user_authored_ddl")
                    .put("authority", "ddl_authoritative"),
            )
            .put("document", JSONObject().put("source", source))
            .put("delivery", JSONObject().put("source_digest", digest))
            .put("config", JSONObject().put("compiler", JSONObject().put("policy", "saved")))
            .toString(),
        contextJson = JSONObject()
            .put("host_options", JSONObject().put("canvas_format", "square"))
            .put("color_maps", JSONObject().put("basic", JSONObject().put("red", "#ff0000")))
            .put("macro_catalog", JSONObject().put("definition_locks", JSONArray()))
            .toString(),
        pipelineDiagnosticsJson = diagnosticsJson(),
    )

    private fun historyItem(id: String, source: String) = HistoryItemEntity(
        id = id,
        createdAt = 2L,
        updatedAt = 2L,
        originalInput = "古いDDLを編集した作品",
        normalizedDdl = source,
        expandedDdl = source,
        scoreJson = "{\"version\":\"0.10.0\",\"instructions\":[]}",
        displaySvg = "<svg/>",
        stage1Model = null,
        stage2Model = null,
        renderMetadataJson = "{}",
        renderHash = "managed-render-hash",
        renderHashShort = "managed",
        colorCatalogId = "sumi",
        canvasAspect = "square",
        starred = false,
        trashed = false,
        elapsedMs = 0L,
        tokenMetadataJson = null,
        lineageNodeId = "managed-node",
        sourceText = "古いDDLを編集した作品",
    )

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}

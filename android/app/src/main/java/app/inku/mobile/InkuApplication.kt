package app.inku.mobile

import android.app.Application
import android.util.Log
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.RoomV10ResetCoordinator
import app.inku.mobile.data.db.SaijikiV1Migration
import app.inku.mobile.data.db.PluginNamesV2Migration
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.pipeline.NativePipelineBridge
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

private const val MIGRATION_LOG_TAG = "InkuMigration"

/** The report of the Saijiki v2 migration, kept in the app's files for the count. */
internal const val MIGRATION_REPORT = "saijiki-v2-migration.json"

class InkuApplication : Application() {
    val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    internal val activityForeground = kotlinx.coroutines.flow.MutableStateFlow(false)
    private val chatGptAssessments by lazy {
        val rows = app.inku.mobile.data.catalogRequest("catalog").getJSONObject("catalog")
            .getJSONObject("providers").getJSONObject("chatgpt").getJSONArray("models")
        org.json.JSONObject().apply { for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index); put(row.getString("id"), row)
        } }
    }
    val chatGptPlan by lazy {
        app.inku.mobile.llm.ChatGptPlanManager(app.inku.mobile.llm.AndroidChatGptCredentialStore(this), applicationScope,
            foreground = activityForeground,
            modelPolicy = {
                kotlinx.coroutines.runBlocking(Dispatchers.IO) {
                    val settings = database.settingsDao()
                    val purposes = runCatching { org.json.JSONObject(settings.get("model_purposes")?.valueJson ?: "{}")
                        .optJSONObject("chatgpt") ?: org.json.JSONObject() }.getOrDefault(org.json.JSONObject())
                    val records = runCatching { org.json.JSONObject(settings.get("model_catalog_observations:chatgpt")?.valueJson ?: "{}")
                        .optJSONObject("records") ?: org.json.JSONObject() }.getOrDefault(org.json.JSONObject())
                    val assessments = org.json.JSONObject(chatGptAssessments.toString())
                    records.keys().forEachRemaining { id -> assessments.put(id, records.get(id)) }
                    app.inku.mobile.llm.ChatGptModelPolicy(purposes, assessments)
                }
            })
    }
    private val databaseLock = Any()

    @Volatile
    private var databaseInstance: InkuDatabase? = null

    /** Whether the database is open; cheap, for the activity to skip the startup gate. */
    val databaseOpen: Boolean
        get() = databaseInstance != null

    /** Throws if startup was refused; [MainActivity] shows the refusal before any screen reads this. */
    val database: InkuDatabase
        get() {
            val result = prepareDatabase()
            check(result is RoomV10ResetCoordinator.Result.Ready) {
                "Database startup refused: ${(result as RoomV10ResetCoordinator.Result.Refused).reason}"
            }
            return checkNotNull(databaseInstance)
        }

    override fun onCreate() {
        super.onCreate()
        CanvasAspects.installRegistry(NativePipelineBridge.canvasRegistry())
    }

    /** Opens the database once per process. A refusal is not kept, so a retry checks again. */
    fun prepareDatabase(): RoomV10ResetCoordinator.Result = synchronized(databaseLock) {
        databaseInstance?.let {
            return@synchronized RoomV10ResetCoordinator.Result.Ready(resetPerformed = false)
        }

        when (val result = RoomV10ResetCoordinator.prepare(this)) {
            is RoomV10ResetCoordinator.Result.Ready -> {
                var database: InkuDatabase? = null
                try {
                    database = InkuDatabase.openPrepared(this)
                    migrateSavedRecords(database.openHelper.writableDatabase)
                    databaseInstance = database
                    result
                } catch (_: RuntimeException) {
                    database?.close()
                    RoomV10ResetCoordinator.Result.Refused(
                        RoomV10ResetCoordinator.RefusalReason.DatabaseOpenFailed,
                    )
                }
            }
            is RoomV10ResetCoordinator.Result.Refused -> result
        }
    }

    /**
     * Moves the saved records to Saijiki v2 once, before any screen reads a work.
     * A failure writes nothing and is logged; the app opens, an unmoved work is
     * refused with `saijiki_migration_required`, and the next start tries again.
     */
    private fun migrateSavedRecords(db: androidx.sqlite.db.SupportSQLiteDatabase) {
        val report = runCatching {
            SaijikiV1Migration(NativePipelineBridge::migrateSaijikiV1, discardExecutions = true).runOnce(db)
        }.getOrElse { error ->
            Log.e(MIGRATION_LOG_TAG, "Saijiki v2 migration failed; nothing was written", error)
            return
        }
        if (report != null) {
            runCatching { filesDir.resolve(MIGRATION_REPORT).writeText(report.toString(1)) }
            Log.i(MIGRATION_LOG_TAG, "Saijiki v2 migration written: ${report.optLong("total_ms")} ms, " +
                "${report.optInt("statements")} statements, ${report.optJSONArray("refused_records")?.length() ?: 0} refused records")
        }
        val pluginReport = runCatching { PluginNamesV2Migration(NativePipelineBridge::migratePluginNames).runOnce(db) }
            .getOrElse { error ->
                Log.e(MIGRATION_LOG_TAG, "Plugin names v2 migration failed; nothing was written", error)
                return
            } ?: return
        runCatching { filesDir.resolve("plugin-names-v2-migration.json").writeText(pluginReport.toString(1)) }
        Log.i(MIGRATION_LOG_TAG, "Plugin names v2 migration: ${pluginReport.optInt("history_changed")} histories, " +
            "${pluginReport.optInt("variation_changed")} variations, ${pluginReport.optJSONArray("refused_records")?.length() ?: 0} refused or partial")
    }

    override fun onTerminate() {
        databaseInstance?.close()
        applicationScope.cancel()
        super.onTerminate()
    }
}

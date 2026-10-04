package app.inku.mobile

import android.app.Application
import android.util.Log
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.RoomV10ResetCoordinator
import app.inku.mobile.data.db.SaijikiV1Migration
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
    val chatGptPlan by lazy {
        app.inku.mobile.llm.ChatGptPlanManager(app.inku.mobile.llm.AndroidChatGptCredentialStore(this), applicationScope)
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
        } ?: return
        runCatching { filesDir.resolve(MIGRATION_REPORT).writeText(report.toString(1)) }
        Log.i(
            MIGRATION_LOG_TAG,
            "Saijiki v2 migration written: ${report.optLong("total_ms")} ms, " +
                "${report.optInt("statements")} statements, " +
                "${report.optJSONArray("refused_records")?.length() ?: 0} refused records",
        )
    }

    override fun onTerminate() {
        databaseInstance?.close()
        applicationScope.cancel()
        super.onTerminate()
    }
}

package app.inku.mobile

import android.app.Application
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.RoomV10ResetCoordinator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

class InkuApplication : Application() {
    val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val databaseLock = Any()

    @Volatile
    private var databaseInstance: InkuDatabase? = null

    val database: InkuDatabase
        get() {
            val result = prepareDatabase()
            check(result is RoomV10ResetCoordinator.Result.Ready) {
                "Database startup refused: ${(result as RoomV10ResetCoordinator.Result.Refused).reason}"
            }
            return checkNotNull(databaseInstance)
        }

    fun prepareDatabase(): RoomV10ResetCoordinator.Result = synchronized(databaseLock) {
        databaseInstance?.let {
            return@synchronized RoomV10ResetCoordinator.Result.Ready(resetPerformed = false)
        }

        when (val result = RoomV10ResetCoordinator.prepare(this)) {
            is RoomV10ResetCoordinator.Result.Ready -> {
                var database: InkuDatabase? = null
                try {
                    database = InkuDatabase.openPrepared(this)
                    database.openHelper.writableDatabase
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

    override fun onTerminate() {
        databaseInstance?.close()
        applicationScope.cancel()
        super.onTerminate()
    }
}

package app.inku.mobile.data.db

import android.content.Context
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import java.io.File

/**
 * Decides what may happen to the Android database before Room opens it.
 *
 * The allowlist deliberately lives only here. Anything outside versions 1-9
 * is either the current schema or a refusal; it never reaches a destructive
 * fallback.
 */
object RoomV10ResetCoordinator {
    private const val DATABASE_NAME = "inku.sqlite"
    private const val THUMBNAILS_DIRECTORY_NAME = "thumbnails"
    private const val TEST_TARGET_PREFIX = "i376-test-"
    private val RESETTABLE_VERSIONS = 1..9
    private val NON_DESTRUCTIVE_ERROR_HANDLER = DatabaseErrorHandler {
        // Inspection must fail closed. Android's default handler deletes a
        // database reported as corrupt, which is forbidden before classification.
    }

    sealed interface Result {
        data class Ready(val resetPerformed: Boolean) : Result

        data class Refused(
            val reason: RefusalReason,
            val detectedVersion: Int? = null,
        ) : Result
    }

    enum class RefusalReason {
        UnexpectedVersion,
        UnreadableDatabase,
        ThumbnailDeleteFailed,
        DatabaseDeleteFailed,
        DatabaseOpenFailed,
    }

    @Synchronized
    internal fun prepare(
        context: Context,
        databaseName: String = DATABASE_NAME,
        thumbnailsDirectory: File = File(
            context.applicationContext.filesDir,
            THUMBNAILS_DIRECTORY_NAME,
        ),
    ): Result {
        val applicationContext = context.applicationContext
        validateTargets(applicationContext, databaseName, thumbnailsDirectory)
        val databaseFile = applicationContext.getDatabasePath(databaseName)
        if (!databaseFile.exists() || databaseFile.length() == 0L) {
            return Result.Ready(resetPerformed = false)
        }

        val version = readUserVersion(databaseFile)
            ?: return Result.Refused(RefusalReason.UnreadableDatabase)

        return when {
            version == InkuDatabase.SCHEMA_VERSION -> Result.Ready(resetPerformed = false)
            version in RESETTABLE_VERSIONS -> resetPreV10Database(
                context = applicationContext,
                databaseName = databaseName,
                databaseFile = databaseFile,
                thumbnailsDirectory = thumbnailsDirectory,
            )
            else -> Result.Refused(
                reason = RefusalReason.UnexpectedVersion,
                detectedVersion = version,
            )
        }
    }

    private fun readUserVersion(databaseFile: File): Int? = runCatching {
        SQLiteDatabase.openDatabase(
            databaseFile.absolutePath,
            null,
            SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS,
            NON_DESTRUCTIVE_ERROR_HANDLER,
        ).use { database ->
            database.rawQuery("PRAGMA user_version", null).use { cursor ->
                check(cursor.moveToFirst())
                cursor.getInt(0)
            }
        }
    }.getOrNull()

    private fun resetPreV10Database(
        context: Context,
        databaseName: String,
        databaseFile: File,
        thumbnailsDirectory: File,
    ): Result {
        if (thumbnailsDirectory.exists() && !thumbnailsDirectory.deleteRecursively()) {
            return Result.Refused(RefusalReason.ThumbnailDeleteFailed)
        }

        val deleteReportedSuccess = context.deleteDatabase(databaseName)
        val databaseFilesRemain = associatedDatabaseFiles(databaseFile).any(File::exists)
        if ((!deleteReportedSuccess && databaseFile.exists()) || databaseFilesRemain) {
            return Result.Refused(RefusalReason.DatabaseDeleteFailed)
        }
        return Result.Ready(resetPerformed = true)
    }

    private fun associatedDatabaseFiles(databaseFile: File): List<File> {
        val parent = requireNotNull(databaseFile.parentFile)
        val name = databaseFile.name
        return listOf(
            databaseFile,
            File(parent, "$name-journal"),
            File(parent, "$name-wal"),
            File(parent, "$name-shm"),
        )
    }

    private fun validateTargets(
        context: Context,
        databaseName: String,
        thumbnailsDirectory: File,
    ) {
        val filesDirectory = context.filesDir.canonicalFile
        val productionThumbnails = File(filesDirectory, THUMBNAILS_DIRECTORY_NAME).canonicalFile
        val candidateThumbnails = thumbnailsDirectory.canonicalFile
        val isProductionDatabase = databaseName == DATABASE_NAME
        val isTestDatabase = databaseName.startsWith(TEST_TARGET_PREFIX) &&
            File(databaseName).name == databaseName
        val isProductionThumbnails = candidateThumbnails == productionThumbnails
        val isTestThumbnails = candidateThumbnails.parentFile == filesDirectory &&
            candidateThumbnails.name.startsWith(TEST_TARGET_PREFIX)

        require(isProductionDatabase || isTestDatabase) {
            "Database target must be the production database or an I-376 test database"
        }
        require(isProductionThumbnails || isTestThumbnails) {
            "Thumbnail target must be the production directory or a direct I-376 test child"
        }
        require(isProductionDatabase == isProductionThumbnails) {
            "Production and I-376 test reset targets must not be mixed"
        }
    }
}

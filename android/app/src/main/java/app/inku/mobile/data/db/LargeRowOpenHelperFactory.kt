package app.inku.mobile.data.db

import android.database.AbstractWindowedCursor
import android.database.Cursor
import android.database.CursorWindow
import android.os.CancellationSignal
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.sqlite.db.SupportSQLiteOpenHelper
import androidx.sqlite.db.SupportSQLiteQuery
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory

/**
 * Gives every query cursor a window large enough for one saved work.
 *
 * The platform default window is about 2 MB, but a work may carry a 32 MiB SVG.
 * Execution BLOBs use digest-bound chunks rather than this complete-row window. Rows
 * past the default window were written but could not be read back
 * (`SQLiteBlobTooBigException`), so large works failed only on Android.
 */
class LargeRowOpenHelperFactory(
    private val delegate: SupportSQLiteOpenHelper.Factory = FrameworkSQLiteOpenHelperFactory(),
    private val windowBytes: Long = DEFAULT_WINDOW_BYTES,
) : SupportSQLiteOpenHelper.Factory {
    override fun create(configuration: SupportSQLiteOpenHelper.Configuration): SupportSQLiteOpenHelper =
        Helper(delegate.create(configuration), windowBytes)

    private class Helper(
        private val helper: SupportSQLiteOpenHelper,
        private val windowBytes: Long,
    ) : SupportSQLiteOpenHelper by helper {
        override val writableDatabase: SupportSQLiteDatabase
            get() = Database(helper.writableDatabase, windowBytes)
        override val readableDatabase: SupportSQLiteDatabase
            get() = Database(helper.readableDatabase, windowBytes)
    }

    private class Database(
        private val database: SupportSQLiteDatabase,
        private val windowBytes: Long,
    ) : SupportSQLiteDatabase by database {
        override fun query(query: String): Cursor = widen(database.query(query))
        override fun query(query: String, bindArgs: Array<out Any?>): Cursor = widen(database.query(query, bindArgs))
        override fun query(query: SupportSQLiteQuery): Cursor = widen(database.query(query))
        override fun query(query: SupportSQLiteQuery, cancellationSignal: CancellationSignal?): Cursor =
            widen(database.query(query, cancellationSignal))

        // The window is replaced before the first fill; its memory is committed
        // only as rows are copied in.
        private fun widen(cursor: Cursor): Cursor = cursor.also {
            (it as? AbstractWindowedCursor)?.window = CursorWindow(null, windowBytes)
        }
    }

    companion object {
        /** Raw SVG 32 + Score/snapshot 32 + metadata/protocol 64 + row headroom 32 MiB.
         * Legacy rows outside those bounds may still be unreadable; this is not an unlimited allowance.
         */
        const val DEFAULT_WINDOW_BYTES: Long = 160L * 1024 * 1024
    }
}

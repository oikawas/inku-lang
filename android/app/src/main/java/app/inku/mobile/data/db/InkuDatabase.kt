package app.inku.mobile.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        HistoryItemEntity::class,
        AppSettingEntity::class,
        ModelAssetEntity::class,
        ProviderSettingEntity::class,
        ColorCatalogEntity::class,
        PluginSettingEntity::class,
        ExportTemplateEntity::class,
        LineageNodeEntity::class,
        LineageEdgeEntity::class,
    ],
    version = InkuDatabase.SCHEMA_VERSION,
    exportSchema = true,
)
abstract class InkuDatabase : RoomDatabase() {
    abstract fun historyDao(): HistoryDao
    abstract fun settingsDao(): SettingsDao
    abstract fun modelAssetDao(): ModelAssetDao
    abstract fun providerSettingDao(): ProviderSettingDao
    abstract fun colorCatalogDao(): ColorCatalogDao
    abstract fun pluginSettingDao(): PluginSettingDao
    abstract fun exportTemplateDao(): ExportTemplateDao
    abstract fun lineageDao(): LineageDao

    companion object {
        const val SCHEMA_VERSION = 10
        private const val DB_NAME = "inku.sqlite"

        val FRESH_SCHEMA_CALLBACK = object : RoomDatabase.Callback() {
            override fun onCreate(db: SupportSQLiteDatabase) {
                super.onCreate(db)
                db.execSQL(
                    """
                    CREATE TRIGGER IF NOT EXISTS `ck_lineage_no_self_edge_insert`
                    BEFORE INSERT ON `lineage_edges`
                    WHEN NEW.`parent_node_id` = NEW.`child_node_id`
                    BEGIN
                        SELECT RAISE(ABORT, 'lineage edge cannot reference itself');
                    END
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TRIGGER IF NOT EXISTS `ck_lineage_no_self_edge_update`
                    BEFORE UPDATE ON `lineage_edges`
                    WHEN NEW.`parent_node_id` = NEW.`child_node_id`
                    BEGIN
                        SELECT RAISE(ABORT, 'lineage edge cannot reference itself');
                    END
                    """.trimIndent(),
                )
            }
        }

        fun open(context: Context): InkuDatabase {
            return when (val result = RoomV10ResetCoordinator.prepare(context)) {
                is RoomV10ResetCoordinator.Result.Ready -> openPrepared(context)
                is RoomV10ResetCoordinator.Result.Refused -> {
                    error("Database startup refused: ${result.reason}")
                }
            }
        }

        internal fun openPrepared(
            context: Context,
            databaseName: String = DB_NAME,
        ): InkuDatabase {
            return Room.databaseBuilder(
                context.applicationContext,
                InkuDatabase::class.java,
                databaseName,
            ).addCallback(FRESH_SCHEMA_CALLBACK).build()
        }
    }
}

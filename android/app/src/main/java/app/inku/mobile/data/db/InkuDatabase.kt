package app.inku.mobile.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
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
    ],
    version = 2,
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

    companion object {
        private const val DB_NAME = "inku.sqlite"

        fun open(context: Context): InkuDatabase {
            // Do not use destructive migration. History, provider settings, and encrypted API keys
            // are user data; schema changes must add explicit Room migrations.
            return Room.databaseBuilder(
                context.applicationContext,
                InkuDatabase::class.java,
                DB_NAME,
            ).addMigrations(MIGRATION_1_2).build()
        }

        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE history_items ADD COLUMN thumbnail_path TEXT")
                db.execSQL("ALTER TABLE history_items ADD COLUMN thumbnail_width INTEGER")
                db.execSQL("ALTER TABLE history_items ADD COLUMN thumbnail_height INTEGER")
            }
        }
    }
}

package app.inku.mobile.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

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
    version = 1,
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
            return Room.databaseBuilder(
                context.applicationContext,
                InkuDatabase::class.java,
                DB_NAME,
            ).build()
        }
    }
}

package app.inku.mobile.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ColorCatalogDao {
    @Query("SELECT * FROM color_catalogs ORDER BY is_builtin DESC, name")
    fun observeAll(): Flow<List<ColorCatalogEntity>>

    @Query("SELECT * FROM color_catalogs WHERE catalog_id = :catalogId LIMIT 1")
    suspend fun get(catalogId: String): ColorCatalogEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(catalog: ColorCatalogEntity)
}

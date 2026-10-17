package app.inku.mobile.data.db

import org.junit.Assert.assertTrue
import org.junit.Test

class HistoryListItemSearchTest {
    @Test fun uuidPrefixFindsHistoryItem() {
        val item = HistoryListItem(
            id = "f2cba6e4-311b-4f08-9d99-a4bd1fb6ebd8",
            createdAt = 0, updatedAt = 0, originalInput = "square", normalizedDdl = null,
            stage1Model = null, stage2Model = null, renderHash = "render-hash",
            renderHashShort = "short", colorCatalogId = "default", canvasAspect = "square",
            starred = false, trashed = false, thumbnailPath = null, thumbnailWidth = null,
            thumbnailHeight = null,
        )
        assertTrue(item.searchText.contains("f2cba6e4-311b"))
    }
}

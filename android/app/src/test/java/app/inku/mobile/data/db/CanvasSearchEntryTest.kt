package app.inku.mobile.data.db

import org.json.JSONObject
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CanvasSearchEntryTest {
    private val workId = "f2cba6e4-311b-4f08-9d99-a4bd1fb6ebd8"
    private val entry = CanvasSearchEntry(
        id = workId,
        originalInput = "Quiet river at dawn",
        sourceText = null,
        renderHash = "rh3:abcd1234feed",
        renderMetadataJson = JSONObject().put("description_hash", "dh3:feedbabe1234").toString(),
    )

    @Test fun fullUuidMatchesOnlyTheSameSavedWork() {
        assertTrue(entry.matches(workId.uppercase()))
        assertFalse(entry.matches("f2cba6e4-311b-4f08-9d99-a4bd1fb6ebd9"))
    }

    @Test fun descriptionAndBothHashPrefixesFindTheWork() {
        assertTrue(entry.matches("  RIVER  "))
        assertTrue(entry.matches("abcd1234"))
        assertTrue(entry.matches("feedbabe"))
        assertFalse(entry.matches("another river"))
    }
}

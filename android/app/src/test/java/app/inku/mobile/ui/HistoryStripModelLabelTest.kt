package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class HistoryStripModelLabelTest {

    @Test
    fun missingModelOmitsTheMetadataLine() {
        assertNull(historyStripModelLabel(null))
        assertNull(historyStripModelLabel("   "))
    }

    @Test
    fun providerPrefixIsRemovedFromTheDisplayName() {
        assertEquals("gpt-image-1", historyStripModelLabel("openai:gpt-image-1"))
    }

    @Test
    fun longDisplayNameUsesTheExistingFourteenCharacterRule() {
        assertEquals("abcdefghijklm…", historyStripModelLabel("provider:abcdefghijklmnop"))
    }
}

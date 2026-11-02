package app.inku.mobile.ui

import app.inku.mobile.pipeline.ProgressCurrent
import app.inku.mobile.pipeline.ProgressItem
import app.inku.mobile.pipeline.ProviderAttempt
import app.inku.mobile.ui.i18n.InkuStringsJa
import app.inku.mobile.ui.i18n.InkuStringsEn
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class RunProgressTextTest {
    @Test fun journalAndBatchUseWebWordingAndPrecedence() {
        val facts = JSONObject().put("things", 3).put("main_law", "B3").put("catalog_id", "default")
        assertEquals("構図：物 3 つ・主の法則 B3", finishedText(ProgressItem("compose_description", "ready", facts), InkuStringsJa))
        assertEquals("構図：問い直しました", finishedText(ProgressItem("compose_description", "retried", facts), InkuStringsJa))
        val retry = ProviderAttempt("run", "write_description_ddl", 2, 4, true)
        assertEquals("指示書を直しています…", currentWork(ProgressCurrent("provider", "write_description_ddl"), "", retry, InkuStringsJa))
        assertEquals("記述を読んでいます…", currentWork(ProgressCurrent("provider", "read_description"), "", retry, InkuStringsJa))
        assertEquals("描いています…", currentWork(ProgressCurrent("local", "render"), "", null, InkuStringsJa))
        assertEquals("45 秒", batchElapsedTime(45_000, InkuStringsJa))
        assertEquals("12 分 03 秒", batchElapsedTime(723_000, InkuStringsJa))
        assertEquals("1 h 02 min 03 s", batchElapsedTime(3_723_000, InkuStringsEn))
        assertEquals("1,520", tokenCount(1520))
        assertEquals("−", tokenCount(null))
    }
}

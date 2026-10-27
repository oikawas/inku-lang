package app.inku.mobile.ui

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DrawRouteTest {
    @Test fun flowAndSavedConditionsFollowTheWork() {
        assertEquals(DrawRoute.Stages, drawRouteOf(JSONObject()))
        val saved = JSONObject("""{"description_ddl":{"composition":{"state":"fallback"}}}""")
        assertEquals(DrawRoute.ReadAndDraw, drawRouteOf(saved))
        assertTrue(compositionModeOf(saved))
        assertFalse(compositionModeOf(JSONObject("""{"route":"read_and_draw"}""")))
        assertEquals("記述 → 写生 → 構図と法則 → 言葉で書く → 見て直す → 配色 → 画", drawFlow(DrawRoute.ReadAndDraw, true, true, true))
        assertEquals("Description → Fill the plan → Composition and laws → Colors → Picture", drawFlow(DrawRoute.Stages, false, false, false))
    }
}

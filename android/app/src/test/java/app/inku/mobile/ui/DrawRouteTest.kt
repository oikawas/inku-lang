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
        val words = drawFlow(DrawRoute.ReadAndDraw, true, true, app.inku.mobile.ui.i18n.InkuStringsJa)
        assertEquals(listOf("記述", "写生", "構図と法則", "言葉で書く", "見て直す", "配色", "画"), words.map { it.label })
        assertEquals(listOf(DrawFlowKind.End, DrawFlowKind.Switch, DrawFlowKind.Switch, DrawFlowKind.Fixed, DrawFlowKind.Fixed, DrawFlowKind.Switch, DrawFlowKind.End), words.map { it.kind })
        assertEquals(listOf("Description", "Fill the plan", "Composition and laws", "Colors", "Picture"),
            drawFlow(DrawRoute.Stages, false, false, app.inku.mobile.ui.i18n.InkuStringsEn).map { it.label })
    }
}

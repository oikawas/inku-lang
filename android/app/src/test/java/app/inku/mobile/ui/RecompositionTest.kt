package app.inku.mobile.ui

import app.inku.mobile.pipeline.RecompositionInfo
import app.inku.mobile.pipeline.RecompositionMove
import app.inku.mobile.ui.i18n.InkuStringsEn
import app.inku.mobile.ui.i18n.InkuStringsJa
import org.junit.Assert.assertEquals
import org.junit.Test

class RecompositionTest {
    @Test
    fun candidatesShowTheAuthorsModeNamesAndMovementsOrWhyTheRangesStay() {
        assertEquals("原理に沿う", InkuStringsJa.recomposeModeLabel("principled"))
        assertEquals("偶然に委ねる", InkuStringsJa.recomposeModeLabel("chance"))
        assertEquals("By principle", InkuStringsEn.recomposeModeLabel("principled"))
        assertEquals("By chance", InkuStringsEn.recomposeModeLabel("chance"))
        assertEquals(
            listOf("1: 右下 → 左上"),
            recompositionLines(RecompositionInfo(moves = listOf(RecompositionMove(0, "右下", "左上"))), InkuStringsJa),
        )
        assertEquals(
            listOf("1: bottom right → top left"),
            recompositionLines(RecompositionInfo(moves = listOf(RecompositionMove(0, "bottom right", "top left"))), InkuStringsEn),
        )
        assertEquals(
            listOf("この作品には数で書いた範囲が無い。", "指示書は変えず、配置の seed を変えて描き直しました。"),
            recompositionLines(RecompositionInfo(unchangedReason = "nothing_to_move"), InkuStringsJa),
        )
        assertEquals(
            listOf("There are too many combinations to find another composition.", "Redrawn with a new composition seed; the instructions are unchanged."),
            recompositionLines(RecompositionInfo(unchangedReason = "unsolved"), InkuStringsEn),
        )
        assertEquals(
            listOf(
                "範囲も場所も書かれていない文があるため、指示書の範囲は選び直せない。",
                "指示書は変えず、配置の seed を変えて描き直しました。",
            ),
            recompositionLines(RecompositionInfo(unchangedReason = "unplaced_sentence"), InkuStringsJa),
        )
        assertEquals(
            listOf(
                "A sentence states no range or place, so the ranges in the instructions cannot be chosen again.",
                "Redrawn with a new composition seed; the instructions are unchanged.",
            ),
            recompositionLines(RecompositionInfo(unchangedReason = "unplaced_sentence"), InkuStringsEn),
        )
    }
}

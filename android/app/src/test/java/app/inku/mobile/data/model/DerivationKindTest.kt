package app.inku.mobile.data.model

import app.inku.mobile.ui.i18n.InkuStringsEn
import app.inku.mobile.ui.i18n.InkuStringsJa
import app.inku.mobile.ReferenceCorpus
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DerivationKindTest {

    private fun serverKinds(): List<String> {
        val kinds = ReferenceCorpus.json("lineage_wiring.json").getJSONArray("derivation_kinds")
        return (0 until kinds.length()).map { kinds.getString(it) }
    }

    /**
     * T-6. The list is the server's `LINEAGE_DERIVATION_KINDS`, read out of the
     * baked fixture rather than retyped, so a kind added on the server shows up
     * here as a failure instead of as silence.
     */
    @Test
    fun derivationKindRegistry_matchesTheServersSeventeenKinds() {
        val kinds = serverKinds()

        assertEquals(17, kinds.size)
        assertEquals(kinds, DerivationKindRegistry.KINDS)
    }

    @Test
    fun everyKindHasALabelInBothLanguages() {
        // Both packs, not just the source language: a kind added to the server's
        // list with no English label would otherwise show as "Unknown" to half
        // the readers and nothing would say so.
        listOf(InkuStringsJa, InkuStringsEn).forEach { strings ->
            DerivationKindRegistry.KINDS.forEach { kind ->
                val label = strings.derivationLabel(kind)
                assertTrue("${'$'}kind has an empty ${'$'}{strings.code} label", label.isNotEmpty())
                assertNotEquals(
                    "${'$'}kind has no ${'$'}{strings.code} label of its own",
                    strings.derivationUnknown,
                    label,
                )
            }
        }
        assertEquals(17, DerivationKindRegistry.ALL_INFOS.size)

        // The eleven that were already labelled keep their wording.
        assertEquals("タッチ", InkuStringsJa.derivationLabel("touch_change"))
        assertEquals("構図", InkuStringsJa.derivationLabel("layout_change"))
        assertEquals("色", InkuStringsJa.derivationLabel("catalog_change"))
        assertEquals("解釈", InkuStringsJa.derivationLabel("reinterpretation"))
        assertEquals("モデル", InkuStringsJa.derivationLabel("model_comparison"))
        assertEquals("言語", InkuStringsJa.derivationLabel("language_comparison"))
        assertEquals("DDL編集", InkuStringsJa.derivationLabel("ddl_edit"))
        assertEquals("記述編集", InkuStringsJa.derivationLabel("description_edit"))
        assertEquals("再描画", InkuStringsJa.derivationLabel("replay"))
        assertEquals("キャンバス変更", InkuStringsJa.derivationLabel("canvas_aspect_change"))
        assertEquals("変奏", InkuStringsJa.derivationLabel("variation"))

        // The five this contract added.
        assertEquals("描画エンジン", InkuStringsJa.derivationLabel("render_engine_change"))
        assertEquals("経年", InkuStringsJa.derivationLabel("age_change"))
        assertEquals("破調", InkuStringsJa.derivationLabel("hacho_change"))
        assertEquals("連歌の付句", InkuStringsJa.derivationLabel("renga_reply"))
        assertEquals("外部の種", InkuStringsJa.derivationLabel("external_seed_change"))

        // 写生 (Stage 0.5). The wording is the web client's ([I-137]).
        assertEquals("写生の区切り", InkuStringsJa.derivationLabel("sketch_grain_change"))

        assertEquals("起点", InkuStringsJa.derivationOrigin)
        assertEquals("起点", InkuStringsJa.derivationOrigin)
        assertEquals(InkuStringsJa.derivationUnknown, InkuStringsJa.derivationLabel("not_a_kind"))
    }
}

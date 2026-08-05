package app.inku.mobile.data.model

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DerivationKindTest {

    private fun serverKinds(): List<String> {
        val stream = javaClass.getResourceAsStream("/server_reference/lineage_wiring.json")
            ?: error("lineage_wiring.json is missing")
        val kinds = JSONObject(stream.bufferedReader().readText()).getJSONArray("derivation_kinds")
        return (0 until kinds.length()).map { kinds.getString(it) }
    }

    /**
     * T-6. The list is the server's `LINEAGE_DERIVATION_KINDS`, read out of the
     * baked fixture rather than retyped, so a kind added on the server shows up
     * here as a failure instead of as silence.
     */
    @Test
    fun derivationKindRegistry_matchesTheServersSixteenKinds() {
        val kinds = serverKinds()

        assertEquals(16, kinds.size)
        assertEquals(kinds, DerivationKindRegistry.KINDS)
    }

    @Test
    fun everyKindHasAJapaneseLabel() {
        DerivationKindRegistry.KINDS.forEach { kind ->
            val label = DerivationKindRegistry.labelJa(kind)
            assertTrue("$kind has an empty label", label.isNotEmpty())
            assertNotEquals("$kind has no label of its own", "不明", label)
        }
        assertEquals(16, DerivationKindRegistry.ALL_INFOS.size)

        // The eleven that were already labelled keep their wording.
        assertEquals("タッチ", DerivationKindRegistry.labelJa("touch_change"))
        assertEquals("構図", DerivationKindRegistry.labelJa("layout_change"))
        assertEquals("色", DerivationKindRegistry.labelJa("catalog_change"))
        assertEquals("解釈", DerivationKindRegistry.labelJa("reinterpretation"))
        assertEquals("モデル", DerivationKindRegistry.labelJa("model_comparison"))
        assertEquals("言語", DerivationKindRegistry.labelJa("language_comparison"))
        assertEquals("DDL編集", DerivationKindRegistry.labelJa("ddl_edit"))
        assertEquals("記述編集", DerivationKindRegistry.labelJa("description_edit"))
        assertEquals("再描画", DerivationKindRegistry.labelJa("replay"))
        assertEquals("キャンバス変更", DerivationKindRegistry.labelJa("canvas_aspect_change"))
        assertEquals("変奏", DerivationKindRegistry.labelJa("variation"))

        // The five this contract added.
        assertEquals("描画エンジン", DerivationKindRegistry.labelJa("render_engine_change"))
        assertEquals("経年", DerivationKindRegistry.labelJa("age_change"))
        assertEquals("破調", DerivationKindRegistry.labelJa("hacho_change"))
        assertEquals("連歌の付句", DerivationKindRegistry.labelJa("renga_reply"))
        assertEquals("外部の種", DerivationKindRegistry.labelJa("external_seed_change"))

        assertEquals("起点", DerivationKindRegistry.labelJa(null))
        assertEquals("起点", DerivationKindRegistry.labelJa(""))
        assertEquals("不明", DerivationKindRegistry.labelJa("not_a_kind"))
    }
}

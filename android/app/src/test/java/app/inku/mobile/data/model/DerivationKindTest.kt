package app.inku.mobile.data.model

import org.junit.Assert.assertEquals
import org.junit.Test

class DerivationKindTest {

    @Test
    fun derivationKindRegistry_containsAllElevenKindsAndExactJapaneseLabels() {
        val kinds = DerivationKindRegistry.KINDS

        assertEquals(11, kinds.size)

        assertEquals("touch_change", kinds[0])
        assertEquals("タッチ", DerivationKindRegistry.labelJa("touch_change"))

        assertEquals("layout_change", kinds[1])
        assertEquals("構図", DerivationKindRegistry.labelJa("layout_change"))

        assertEquals("catalog_change", kinds[2])
        assertEquals("色", DerivationKindRegistry.labelJa("catalog_change"))

        assertEquals("reinterpretation", kinds[3])
        assertEquals("解釈", DerivationKindRegistry.labelJa("reinterpretation"))

        assertEquals("model_comparison", kinds[4])
        assertEquals("モデル", DerivationKindRegistry.labelJa("model_comparison"))

        assertEquals("language_comparison", kinds[5])
        assertEquals("言語", DerivationKindRegistry.labelJa("language_comparison"))

        assertEquals("ddl_edit", kinds[6])
        assertEquals("DDL編集", DerivationKindRegistry.labelJa("ddl_edit"))

        assertEquals("description_edit", kinds[7])
        assertEquals("記述編集", DerivationKindRegistry.labelJa("description_edit"))

        assertEquals("replay", kinds[8])
        assertEquals("再描画", DerivationKindRegistry.labelJa("replay"))

        assertEquals("canvas_aspect_change", kinds[9])
        assertEquals("キャンバス変更", DerivationKindRegistry.labelJa("canvas_aspect_change"))

        assertEquals("variation", kinds[10])
        assertEquals("変奏", DerivationKindRegistry.labelJa("variation"))

        assertEquals("起点", DerivationKindRegistry.labelJa(null))
        assertEquals("起点", DerivationKindRegistry.labelJa(""))
    }
}

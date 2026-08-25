package app.inku.mobile.ui

import app.inku.mobile.data.model.CatalogSelection
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking

/**
 * Drives the real fixed and auto resolver with only the ModelProvider replaced.
 * Fixed remains a pure setting lookup; auto follows the server selector card,
 * request, extraction, allowlist, fallback, and cancellation boundaries.
 * Call-site ownership is guarded separately by ColorCatalogAutoWiringTest.
 */
class ColorCatalogSelectionDeterminismTest {

    @Test
    fun t1_theSettingIsWhatTheRunUses() {
        for (catalog in ColorCatalogs.all) {
            assertEquals(
                "the run must use the catalogue the settings name",
                catalog.id,
                CatalogSelection.resolvedCatalogIdForRun(catalog.id),
            )
        }
    }

    @Test
    fun t2_repeatedRunsOfTheSameSettingReachTheSameCatalogue() {
        val resolved = (1..50).map { CatalogSelection.resolvedCatalogIdForRun("ink_season") }

        assertEquals("ink_season", resolved.first())
        assertEquals(
            "the resolver must answer with one catalogue across runs",
            1,
            resolved.toSet().size,
        )
    }

    @Test
    fun t3_everyCatalogueInTheListIsReachable() {
        // The counterpart of the server's "every id in the list is accepted":
        // a resolver that collapsed onto one catalogue would pass t2 alone.
        val resolved = ColorCatalogs.all.map { CatalogSelection.resolvedCatalogIdForRun(it.id) }

        assertEquals(ColorCatalogs.all.size, resolved.toSet().size)
    }

    @Test
    fun t4_aSettingThatIsNoLongerACatalogueFallsBackToTheDefault() {
        // The server answers 422 here. A value saved by an older build of this
        // app is not a request, so it falls back instead of refusing to draw.
        assertEquals("default", CatalogSelection.resolvedCatalogIdForRun("retired_catalog"))
        assertEquals("default", CatalogSelection.normalizedSelectionId("retired_catalog"))
        assertEquals("auto", CatalogSelection.normalizedSelectionId("auto"))
    }

    @Test
    fun t5_fixedDoesNotReachTheProvider() = runBlocking {
        val provider = RecordingProvider(reply = """{"catalog_id": "lantern_dew"}""")

        assertEquals(
            "ink_season",
            CatalogSelection.resolveCatalogIdForRun(
                selectedCatalogId = "ink_season",
                sourceText = "夜の灯りが水面に散る。",
                stage1ModelId = "provider:stage-1",
                modelProvider = provider,
            ),
        )
        assertTrue("fixed selection must add no model call", provider.requests.isEmpty())
    }

    @Test
    fun t6_autoUsesTheStage1ModelAndSendsTheServerEquivalentRequest() = runBlocking {
        val prompt = "祭りの夜、灯りが水面に散る。"
        val provider = RecordingProvider(reply = """{"catalog_id": "lantern_dew"}""")

        assertEquals(
            "lantern_dew",
            CatalogSelection.resolveCatalogIdForRun(
                selectedCatalogId = "auto",
                sourceText = prompt,
                stage1ModelId = "openai:stage-1",
                modelProvider = provider,
            ),
        )
        assertEquals(1, provider.requests.size)
        val request = provider.requests.single()
        assertEquals("openai:stage-1", request.modelId)
        assertEquals(prompt, request.prompt)
        assertEquals(0.3, request.temperature, 0.0001)
        assertEquals(200, request.maxTokens)
        assertEquals(CatalogSelection.buildCatalogCard(), request.systemInstruction)
    }

    @Test
    fun t7_autoAcceptsJsonThenBareKnownIdsOnly() = runBlocking {
        for (id in expectedCatalogIds) {
            assertEquals(
                "$id must be read from JSON",
                id,
                resolveAuto("""{"catalog_id": "$id"}"""),
            )
            assertEquals(
                "$id must be read from a bare-answer fallback",
                id,
                resolveAuto("The best match is $id."),
            )
        }
    }

    @Test
    fun t8_autoFallsBackToDefaultForUnknownEmptyAndProviderFailure() = runBlocking {
        assertEquals("default", resolveAuto("""{"catalog_id": "not_a_catalog"}"""))
        assertEquals("default", resolveAuto(""))
        assertEquals("default", resolveAuto("   "))
        assertEquals(
            "default",
            CatalogSelection.resolveCatalogIdForRun(
                selectedCatalogId = "auto",
                sourceText = "夜の灯りが水面に散る。",
                stage1ModelId = "provider:stage-1",
                modelProvider = RecordingProvider(failure = IllegalStateException("provider unavailable")),
            ),
        )
    }

    @Test
    fun t9_catalogCardContainsEveryIdAndJapaneseSelectionMetadata() {
        assertEquals(expectedCatalogIds, ColorCatalogs.all.map { it.id })
        assertEquals(13, ColorCatalogs.all.size)

        val card = CatalogSelection.buildCatalogCard()
        expectedCatalogCardMetadata.forEach { expected ->
            assertTrue("missing catalog line for ${expected.id}", card.contains("- ${expected.id}: ${expected.name} -- ${expected.sub}"))
            assertTrue("missing Japanese subtitle for ${expected.id}", card.contains(expected.subJa))
            expected.paletteNamesJa.forEach { paletteName ->
                assertTrue("missing $paletteName from ${expected.id}'s palette", card.contains(paletteName))
            }
        }
        assertEquals(13, card.lines().count { it.startsWith("- ") })
    }

    @Test
    fun t10_autoDoesNotTurnCancellationIntoADefaultSelection() = runBlocking {
        var cancellationReachedCaller = false
        try {
            CatalogSelection.resolveCatalogIdForRun(
                selectedCatalogId = "auto",
                sourceText = "夜の灯りが水面に散る。",
                stage1ModelId = "provider:stage-1",
                modelProvider = RecordingProvider(failure = CancellationException("stopped")),
            )
        } catch (_: CancellationException) {
            cancellationReachedCaller = true
        }

        assertTrue("Stop must cancel the draw instead of selecting default and continuing", cancellationReachedCaller)
    }

    private suspend fun resolveAuto(reply: String): String = CatalogSelection.resolveCatalogIdForRun(
        selectedCatalogId = "auto",
        sourceText = "夜の灯りが水面に散る。",
        stage1ModelId = "provider:stage-1",
        modelProvider = RecordingProvider(reply = reply),
    )

    private class RecordingProvider(
        private val reply: String = "",
        private val failure: Throwable? = null,
    ) : ModelProvider {
        override val providerId: String = "test"
        val requests = mutableListOf<ModelRequest>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            requests += request
            failure?.let { throw it }
            return ModelResponse(text = reply, modelId = request.modelId)
        }
    }

    private data class CatalogCardMetadata(
        val id: String,
        val name: String,
        val sub: String,
        val subJa: String,
        val paletteNamesJa: List<String>,
    )

    private companion object {
        val expectedCatalogIds = listOf(
            "default", "ink_season", "fresco_study", "open_air_light", "ink_porcelain",
            "cool_material", "dye_earth", "vivid_material", "weathered_heritage", "sea_stone",
            "moss_bark", "neon_plate", "lantern_dew",
        )

        val expectedCatalogCardMetadata = listOf(
            CatalogCardMetadata("default", "inku Default", "neutral baseline", "ニュートラルな基準値", listOf("黒", "白", "灰", "赤", "緑", "青", "黄", "橙", "紫", "深い赤")),
            CatalogCardMetadata("ink_season", "Ink & Season", "ink, paper, seasonal accents", "墨、紙、季節の差し色", listOf("松煙", "胡粉", "消墨", "朱", "常磐", "藍", "鶯", "山吹", "藤紫", "茜")),
            CatalogCardMetadata("fresco_study", "Fresco Study", "sunlit wall, dry earth, warm shadow", "日なたの壁、乾いた土、温かい陰", listOf("アンバーの影", "漆喰の白", "温かい石", "赤土", "緑土", "深い青顔料", "黄土", "シエナ土", "マンガン紫", "焼けた土")),
            CatalogCardMetadata("open_air_light", "Open-Air Light", "soft light, sky, reflected shade", "柔らかな光、空、反射する陰", listOf("川石", "亜鉛華", "ライラック灰", "薔薇色の光", "戸外の緑", "空色", "若草", "杏の陰", "菫灰の陰", "陽だまりの黄")),
            CatalogCardMetadata("ink_porcelain", "Ink & Porcelain", "clear light, ink, sharp mineral accents", "澄んだ光、墨、冴えた鉱物の差し色", listOf("墨の黒", "磁器の白", "窯の煤", "辰砂の赤", "翡翠の緑", "磁器の青", "鉱物の金", "銅の上絵", "鉱物の紫", "明るい朱")),
            CatalogCardMetadata("cool_material", "Cool Material", "cool light, wood, stone", "冷たい光、木、石", listOf("石墨", "雪の光", "花崗岩の灰", "ナナカマドの実", "唐檜", "鈍い海色", "苔むした木", "粘土の茶", "粘板岩の紫", "真夜中の青")),
            CatalogCardMetadata("dye_earth", "Dye & Earth", "textile dye, earth, rain shade", "布の染料、土、雨の陰", listOf("鉄媒染", "温かな綿", "濡れた土", "深い薔薇染め", "藍葉の緑", "孔雀青", "黄色の染料", "サフラン染め", "明るい桃色", "葉の染料")),
            CatalogCardMetadata("vivid_material", "Vivid Material", "vivid pigment, lime, stone", "鮮やかな顔料、ライム、石", listOf("火山の黒", "ライムの白", "都市の石", "鮮やかな薔薇色", "新鮮な緑", "明るい青", "深いカドミウム黄", "橙の花", "コバルト紫", "太陽の黄")),
            CatalogCardMetadata("weathered_heritage", "Weathered Heritage", "fog, brick, wool, rain", "霧、煉瓦、羊毛、雨", listOf("木炭", "霧の光", "粘板岩の灰", "煉瓦の赤", "深い緑", "雨の青", "くすんだ真鍮", "鉄錆", "ヒース", "濡れた苔")),
            CatalogCardMetadata("sea_stone", "Sea & Stone", "sea light, stone, dry earth", "海の光、石、乾いた土", listOf("深海の闇", "泡の白", "石の灰", "粘土の赤", "海藻の緑", "深い海", "乾いたオリーブ", "珊瑚の橙", "夜の海", "淡い海")),
            CatalogCardMetadata("moss_bark", "Moss & Bark", "bark, leaf, moss, dappled light", "樹皮、葉、苔、木漏れ日", listOf("森の闇", "白樺の肌", "朝霧の灰", "熟した実", "苔", "沢の水", "木漏れ日", "樹皮", "山葡萄", "若葉")),
            CatalogCardMetadata("neon_plate", "Neon & Plate", "discharge tube, printing plate, coating", "放電管、印刷版、被膜", listOf("消灯画素", "拡散板の白", "筐体の灰", "標識の赤", "発光体の緑", "放電の青", "網点の黄", "安全被膜", "放電管の菫", "シアン版")),
            CatalogCardMetadata("lantern_dew", "Lantern & Dew", "night air, lantern, dew", "夜気、灯火、露", listOf("新月の黒", "露の白", "夜気の灰", "熾火の赤", "夜の苔", "夜の藍", "蛍の黄", "灯火の琥珀", "薄明の菫", "桑の実")),
        )
    }
}

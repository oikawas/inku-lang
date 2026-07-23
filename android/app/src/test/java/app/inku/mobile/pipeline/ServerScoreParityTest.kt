package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerScoreParityTest {

    private data class FixtureCase(
        val id: String,
        val input: String,
        val uncoercedJsonStr: String,
        val expectedJsonStr: String,
    )

    // Origin of fixtures: server/tests/fixtures/stage2/ (v2.4.1 Master)
    private val fixtures = listOf(
        // Origin: server/tests/fixtures/stage2/01/
        FixtureCase(
            id = "01",
            input = "中心に円を置く。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"circle","position":["0.5","0.5"],"radius":"0.1","extra_field":"drop_me"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/02/
        FixtureCase(
            id = "02",
            input = "上から1/3に横線を引く。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"line","from":["0.0","0.333"],"to":["1.0","0.333"]}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.333],"to":[1.0,0.333]}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/03/
        FixtureCase(
            id = "03",
            input = "画面中央に赤い円を置く。半径は画面の2割。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"circle","position":[0.5,0.5],"radius":0.2,"color":"red"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"color":"red"}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/04/
        FixtureCase(
            id = "04",
            input = "左上から右下へ青い線を引く。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.0],"to":[1.0,1.0],"color":"blue"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.0],"to":[1.0,1.0],"color":"blue"}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/05/
        FixtureCase(
            id = "05",
            input = "中央に緑の四角を置く。一辺は画面の3割。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"square","position":["0.35","0.35"],"size":["0.3","0.3"],"color":"green","extra_field":"drop_me"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"square","position":[0.35,0.35],"size":[0.3,0.3],"color":"green"}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/06/
        FixtureCase(
            id = "06",
            input = "画面中央に上向きの三角を置く。幅も高さも画面の4割。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"triangle","position":["0.3","0.3"],"size":["0.4","0.4"],"extra_field":"drop_me"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"triangle","position":[0.3,0.3],"size":[0.4,0.4]}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/07/
        FixtureCase(
            id = "07",
            input = "画面の真ん中に破線で横線を引く。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"style":"dashed"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"style":"dashed"}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/08/
        FixtureCase(
            id = "08",
            input = "中心に点線の円を置く。半径は画面の25%。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"circle","position":[0.5,0.5],"radius":0.25,"style":"dotted"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.25,"style":"dotted"}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/09/
        FixtureCase(
            id = "09",
            input = "上から1/3に鉛筆で横線を引く。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.333],"to":[1.0,0.333],"weight":"pencil"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.333],"to":[1.0,0.333],"weight":"pencil"}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/10/
        FixtureCase(
            id = "10",
            input = "画面の真ん中に太筆で赤い横線を引く。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"weight":"brush_thick","color":"red"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"weight":"brush_thick","color":"red"}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/11/
        FixtureCase(
            id = "11",
            input = "上から1/3に横線を引く。線は細かく揺れる。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.333],"to":[1.0,0.333],"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.333],"to":[1.0,0.333],"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/12/
        FixtureCase(
            id = "12",
            input = "中央に横長の楕円を置く。幅は画面の6割、高さは3割。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"ellipse","position":[0.5,0.5],"size":[0.6,0.3]}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.6,0.3]}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/13/
        FixtureCase(
            id = "13",
            input = "三つの小さな円を横に並べる。画面の中央の高さで、左から1/4、中央、右から1/4の位置。半径はどれも画面の5%。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"circle","position":[0.25,0.5],"radius":0.05},{"primitive":"circle","position":[0.5,0.5],"radius":0.05},{"primitive":"circle","position":[0.75,0.5],"radius":0.05}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"circle","center":[0.25,0.5],"radius":0.05},{"primitive":"circle","center":[0.5,0.5],"radius":0.05},{"primitive":"circle","center":[0.75,0.5],"radius":0.05}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/14/
        FixtureCase(
            id = "14",
            input = "左上から右下へ一点鎖線で線を引く。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.0],"to":[1.0,1.0],"style":"dash_dot"}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"line","from":[0.0,0.0],"to":[1.0,1.0],"style":"dash_dot"}]}""",
        ),
        // Origin: server/tests/fixtures/stage2/15/
        FixtureCase(
            id = "15",
            input = "画面中央に縦の線を引く。上から下まで。線は大きく波打つ。",
            uncoercedJsonStr = """{"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"variation":{"amplitude":"broad","frequency":"medium","quality":"wave","dimensions":["position_x"]}}]}""",
            expectedJsonStr = """{"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"variation":{"amplitude":"broad","frequency":"medium","quality":"wave","dimensions":["position_x"]}}]}""",
        ),
    )

    @Test
    fun testDescriptionHashExactParity() {
        val pipeline = LocalFallbackPipeline()
        // Exact expected values produced by server inku_server.identity.description_hash
        assertEquals(
            "dh1:4acea64b6cec1944e40896dbf6c167322850bd8a2c15938651ffd3275101da99",
            pipeline.descriptionHash("中心に円を置く。"),
        )
        assertEquals(
            "dh1:31d1445b92e140db68a8528022f299325eb9cd1e4c873361d5c94b9bcff6e618",
            pipeline.descriptionHash("上から1/3に横線を引く。"),
        )
    }

    @Test
    fun testRenderHashExactParityWithSeedCanonicalization() {
        val pipeline = LocalFallbackPipeline()
        val scoreStr = """{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1}]}"""
        val metadataJson = """{
            "render_seed": "12345",
            "vary_seed": null,
            "render_build_number": "689",
            "render_engine_id": "default",
            "render_engine_version": "2",
            "render_color_catalog_id": "default"
        }"""
        val request = PaintRequest(
            description = "中心に円を置く。",
            originalText = "中心に円を置く。",
            stage1Model = "local-litert-lm:gemma-4b-it",
            stage2Model = "local-litert-lm:gemma-4b-it",
            colorCatalogId = "default",
            canvasAspect = "square",
            autoRepair = true,
        )

        val result = pipeline.renderFromScore(scoreStr, request)
        // Verify renderHash calculation directly using same metadata structure
        val renderHashField = LocalFallbackPipeline::class.java.getDeclaredMethod(
            "renderHash",
            String::class.java,
            String::class.java,
            String::class.java,
            String::class.java,
            String::class.java,
            String::class.java,
        ).apply { isAccessible = true }

        val hash = renderHashField.invoke(
            pipeline,
            request.originalText,
            request.description,
            scoreStr,
            "<svg></svg>",
            metadataJson,
            "default",
        ) as String

        val canonicalMethod = LocalFallbackPipeline::class.java.getDeclaredMethod("canonicalJson", Any::class.java).apply { isAccessible = true }
        val scoreObj = JSONObject(scoreStr)
        val payload = JSONObject()
            .put("version", "rh2")
            .put("score", scoreObj)
            .put("render_seed", 12345)
            .put("vary_seed", JSONObject.NULL)
            .put("render_build_number", "689")
            .put("render_engine_id", "default")
            .put("render_engine_version", "2")
            .put("render_color_catalog_id", "default")
        val ktCanonical = canonicalMethod.invoke(pipeline, payload) as String
        println("KT_CANONICAL: $ktCanonical")
        println("COMPUTED_HASH: $hash")

        assertEquals(
            "rh2:d4b42a90425a23c49b23f3b0fe3b52383b158be92ce39286482496cb53021ea6",
            hash,
        )
        assertEquals("1EA6", hash.takeLast(4).uppercase())
    }

    @Test
    fun testAllStage2FixturesCoerceParity() {
        for (fixture in fixtures) {
            val uncoercedInsArray = JSONObject(fixture.uncoercedJsonStr).getJSONArray("instructions")
            val expectedInsArray = JSONObject(fixture.expectedJsonStr).getJSONArray("instructions")

            assertEquals(
                "Instruction count mismatch in fixture ${fixture.id}",
                expectedInsArray.length(),
                uncoercedInsArray.length(),
            )

            for (i in 0 until expectedInsArray.length()) {
                val uncoercedIns = uncoercedInsArray.getJSONObject(i)
                val expectedIns = expectedInsArray.getJSONObject(i)

                val coerced = ServerScoreCoercer.coerceInstruction(
                    source = uncoercedIns,
                    ddl = fixture.input,
                    background = "white",
                    detectColorKey = ServerScoreSemantics::detectColorKey,
                    detectWeightKey = ServerScoreSemantics::detectWeightKey,
                    visibleForeground = ServerScoreSemantics::visibleForeground,
                )

                // 1. Primitive parity
                assertEquals("Primitive mismatch in fixture ${fixture.id} item $i", expectedIns.getString("primitive"), coerced.getString("primitive"))

                // 2. Extra fields should be ignored or forbidden
                assertFalse("Unknown extra field should be removed in fixture ${fixture.id}", coerced.has("extra_field"))

                // 3. Geometry parity: center / position / from / to / radius / size
                if (expectedIns.has("center")) {
                    val expCenter = expectedIns.getJSONArray("center")
                    val actCenter = coerced.getJSONArray("center")
                    assertEquals(expCenter.getDouble(0), actCenter.getDouble(0), 1e-4)
                    assertEquals(expCenter.getDouble(1), actCenter.getDouble(1), 1e-4)
                }
                if (expectedIns.has("position")) {
                    val expPos = expectedIns.getJSONArray("position")
                    val actPos = coerced.getJSONArray("position")
                    assertEquals(expPos.getDouble(0), actPos.getDouble(0), 1e-4)
                    assertEquals(expPos.getDouble(1), actPos.getDouble(1), 1e-4)
                }
                if (expectedIns.has("from")) {
                    val expFrom = expectedIns.getJSONArray("from")
                    val actFrom = coerced.getJSONArray("from")
                    assertEquals(expFrom.getDouble(0), actFrom.getDouble(0), 1e-4)
                    assertEquals(expFrom.getDouble(1), actFrom.getDouble(1), 1e-4)
                }
                if (expectedIns.has("to")) {
                    val expTo = expectedIns.getJSONArray("to")
                    val actTo = coerced.getJSONArray("to")
                    assertEquals(expTo.getDouble(0), actTo.getDouble(0), 1e-4)
                    assertEquals(expTo.getDouble(1), actTo.getDouble(1), 1e-4)
                }
                if (expectedIns.has("radius")) {
                    assertEquals(expectedIns.getDouble("radius"), coerced.getDouble("radius"), 1e-4)
                }
                if (expectedIns.has("size")) {
                    val expSize = expectedIns.getJSONArray("size")
                    val actSize = coerced.getJSONArray("size")
                    assertEquals(expSize.getDouble(0), actSize.getDouble(0), 1e-4)
                    assertEquals(expSize.getDouble(1), actSize.getDouble(1), 1e-4)
                }

                // 4. Style & Weight & Color parity
                if (expectedIns.has("color")) {
                    assertEquals(expectedIns.getString("color"), coerced.getString("color"))
                }
                if (expectedIns.has("style")) {
                    assertEquals(expectedIns.getString("style"), coerced.getString("style"))
                }
                if (expectedIns.has("weight")) {
                    assertEquals(expectedIns.getString("weight"), coerced.getString("weight"))
                }

                // 5. Variation parity
                if (expectedIns.has("variation")) {
                    val expVar = expectedIns.getJSONObject("variation")
                    val actVar = coerced.getJSONObject("variation")
                    assertNotNull("Variation should be present in fixture ${fixture.id}", actVar)
                    assertEquals(expVar.getString("amplitude"), actVar.getString("amplitude"))
                    assertEquals(expVar.getString("frequency"), actVar.getString("frequency"))
                    assertEquals(expVar.getString("quality"), actVar.getString("quality"))
                }
            }
        }
    }
}

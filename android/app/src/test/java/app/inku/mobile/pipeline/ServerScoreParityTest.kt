package app.inku.mobile.pipeline

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerScoreParityTest {

    private data class FixtureCase(
        val id: String,
        val input: String,
        val expectedJsonStr: String,
    )

    private val fixtures = listOf(
        FixtureCase(
            "01",
            "中心に円を置く。",
            """{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1}]}""",
        ),
        FixtureCase(
            "02",
            "上から1/3に横線を引く。",
            """{"instructions":[{"primitive":"line","from":[0.0,0.333],"to":[1.0,0.333]}]}""",
        ),
        FixtureCase(
            "03",
            "画面中央に赤い円を置く。半径は画面の2割。",
            """{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"color":"red"}]}""",
        ),
        FixtureCase(
            "04",
            "左上から右下へ青い線を引く。",
            """{"instructions":[{"primitive":"line","from":[0.0,0.0],"to":[1.0,1.0],"color":"blue"}]}""",
        ),
        FixtureCase(
            "05",
            "中央に緑の四角を置く。一辺は画面の3割。",
            """{"instructions":[{"primitive":"square","position":[0.35,0.35],"size":[0.3,0.3],"color":"green"}]}""",
        ),
        FixtureCase(
            "06",
            "画面中央に上向きの三角を置く。幅も高さも画面の4割。",
            """{"instructions":[{"primitive":"triangle","position":[0.3,0.3],"size":[0.4,0.4]}]}""",
        ),
        FixtureCase(
            "07",
            "画面の真ん中に破線で横線を引く。",
            """{"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"style":"dashed"}]}""",
        ),
        FixtureCase(
            "08",
            "中心に点線の円を置く。半径は画面の25%。",
            """{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.25,"style":"dotted"}]}""",
        ),
        FixtureCase(
            "09",
            "上から1/3に鉛筆で横線を引く。",
            """{"instructions":[{"primitive":"line","from":[0.0,0.333],"to":[1.0,0.333],"weight":"pencil"}]}""",
        ),
        FixtureCase(
            "10",
            "画面の真ん中に太筆で赤い横線を引く。",
            """{"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"weight":"brush_thick","color":"red"}]}""",
        ),
        FixtureCase(
            "11",
            "上から1/3に横線を引く。線は細かく揺れる。",
            """{"instructions":[{"primitive":"line","from":[0.0,0.333],"to":[1.0,0.333],"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}""",
        ),
        FixtureCase(
            "12",
            "中央に横長の楕円を置く。幅は画面の6割、高さは3割。",
            """{"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.6,0.3]}]}""",
        ),
        FixtureCase(
            "13",
            "三つの小さな円を横に並べる。画面の中央の高さで、左から1/4、中央、右から1/4の位置。半径はどれも画面の5%。",
            """{"instructions":[{"primitive":"circle","center":[0.25,0.5],"radius":0.05},{"primitive":"circle","center":[0.5,0.5],"radius":0.05},{"primitive":"circle","center":[0.75,0.5],"radius":0.05}]}""",
        ),
        FixtureCase(
            "14",
            "左上から右下へ一点鎖線で線を引く。",
            """{"instructions":[{"primitive":"line","from":[0.0,0.0],"to":[1.0,1.0],"style":"dash_dot"}]}""",
        ),
        FixtureCase(
            "15",
            "画面中央に縦の線を引く。上から下まで。線は大きく波打つ。",
            """{"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"variation":{"amplitude":"broad","frequency":"medium","quality":"wave","dimensions":["position_x"]}}]}""",
        ),
    )

    private fun testRequest(description: String, originalText: String = description): PaintRequest {
        return PaintRequest(
            description = description,
            originalText = originalText,
            stage1Model = "local-litert-lm:gemma-4b-it",
            stage2Model = "local-litert-lm:gemma-4b-it",
            colorCatalogId = "sumi_traditional",
            canvasAspect = "square",
            autoRepair = true,
        )
    }

    @Test
    fun testAllStage2FixturesStructureParity() {
        val pipeline = LocalFallbackPipeline()
        for (fixture in fixtures) {
            val scoreJson = pipeline.renderFromScore(fixture.expectedJsonStr, testRequest(description = fixture.input)).scoreJson
            assertNotNull("Score JSON should not be null for fixture ${fixture.id}", scoreJson)
            val scoreObj = JSONObject(scoreJson)
            val instructions = scoreObj.optJSONArray("instructions")
            assertNotNull("Instructions should exist for fixture ${fixture.id}", instructions)
            assertTrue("Instructions should not be empty for fixture ${fixture.id}", instructions!!.length() > 0)

            val expectedObj = JSONObject(fixture.expectedJsonStr)
            val expectedIns = expectedObj.getJSONArray("instructions")
            val actualIns = instructions.getJSONObject(0)
            val expectedIns0 = expectedIns.getJSONObject(0)

            assertEquals("Primitive mismatch in fixture ${fixture.id}", expectedIns0.getString("primitive"), actualIns.getString("primitive"))
            if (expectedIns0.has("color")) {
                assertEquals("Color mismatch in fixture ${fixture.id}", expectedIns0.getString("color"), actualIns.getString("color"))
            }
            if (expectedIns0.has("style")) {
                assertEquals("Style mismatch in fixture ${fixture.id}", expectedIns0.getString("style"), actualIns.getString("style"))
            }
            if (expectedIns0.has("weight")) {
                assertEquals("Weight mismatch in fixture ${fixture.id}", expectedIns0.getString("weight"), actualIns.getString("weight"))
            }
        }
    }

    @Test
    fun testHashFormatParity() {
        val pipeline = LocalFallbackPipeline()
        val text = "中心に円を置く。"
        val dh = pipeline.descriptionHash(text)
        assertTrue("descriptionHash should start with dh1: but was $dh", dh.startsWith("dh1:"))
        assertEquals("dh1 length should be 4 (prefix) + 64 (sha256 hex)", 68, dh.length)

        val result = pipeline.renderFromScore(
            """{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1}]}""",
            testRequest(description = text, originalText = text),
        )
        assertTrue("renderHash should start with rh2: but was ${result.renderHash}", result.renderHash.startsWith("rh2:"))
        assertEquals("rh2 length should be 4 (prefix) + 64 (sha256 hex)", 68, result.renderHash.length)
        assertEquals(4, result.renderHashShort.length)
    }
}

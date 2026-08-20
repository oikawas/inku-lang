package app.inku.mobile.pipeline

import app.inku.mobile.ReferenceCorpus
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.render.DefaultSvgRenderer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DdlEngineTwentyParityTest {
    private val pipeline = LocalFallbackPipeline()

    private fun arrangement(count: Int, vararg colors: String): JSONObject = JSONObject()
        .put("count", count)
        .put("layout", "scatter")
        .put("color_cycle", JSONArray(colors.toList()))

    private fun instruction(
        primitive: String,
        color: String = "black",
        weight: String = "pen",
        count: Int? = null,
    ): JSONObject = JSONObject()
        .put("primitive", primitive)
        .put("color", color)
        .put("weight", weight)
        .also { if (count != null) it.put("arrangement", arrangement(count)) }

    private fun colors(instruction: JSONObject): List<String> {
        val cycle = instruction.getJSONObject("arrangement").getJSONArray("color_cycle")
        return (0 until cycle.length()).map(cycle::getString)
    }

    private fun normalize(instructions: List<JSONObject>, ddl: String, lang: String): List<JSONObject> {
        val score = JSONObject()
            .put("version", "0.1.0")
            .put("canvas", "square")
            .put("background", "white")
            .put("instructions", JSONArray(instructions))
        val repaired = pipeline.normalizeServerScoreWithLang(score, ddl, "square", lang)
            .getJSONArray("instructions")
        return (0 until repaired.length()).map(repaired::getJSONObject)
    }

    private fun coerce(source: JSONObject, ddl: String): JSONObject = ServerScoreCoercer.coerceInstruction(
        source = source,
        ddl = ddl,
        background = "white",
        detectColorKey = ServerScoreSemantics::detectColorKey,
        detectWeightKey = ServerScoreSemantics::detectWeightKey,
        visibleForeground = ServerScoreSemantics::visibleForeground,
    )

    @Test
    fun t307_colorDeliveryKeepsRequestedColorsAndIsIdempotent() {
        val ddl = "赤、青、黄、橙、紫の楕円を並べる。"
        val source = instruction("ellipse", color = "red", count = 5)
        source.getJSONObject("arrangement").put("color_cycle", JSONArray(listOf("red", "blue")))

        val once = normalize(listOf(source), ddl, "ja")
        val twice = normalize(once, ddl, "ja")

        assertEquals(listOf("red", "blue", "orange", "purple", "yellow"), colors(once.single()))
        assertEquals(1, colors(once.single()).count { it == "red" })
        assertEquals(once.single().toString(), twice.single().toString())
        assertEquals(
            setOf("white", "black", "blue", "red", "green", "gray", "yellow", "orange", "purple"),
            ServerScoreRepairFactory.requestedColors(
                "white black blue red green gray yellow orange purple",
            ).toSet(),
        )
    }

    @Test
    fun t308_singleNamedColorFoldsOnlyMatchingMulticolorCycles() {
        fun cycle(vararg values: String) = instruction("circle", color = "black", count = 4).also {
            it.getJSONObject("arrangement").put("color_cycle", JSONArray(values.toList()))
        }

        val folded = normalize(
            listOf(cycle("red", "blue")),
            "背景は白。赤い円を並べる。",
            "ja",
        ).single()
        assertEquals("red", folded.getString("color"))
        assertEquals(listOf("red"), colors(folded))

        val controls = listOf(
            "色とりどりの赤い円。" to cycle("red", "blue"),
            "赤と青の円。" to cycle("red", "blue"),
            "赤い円。" to cycle("blue", "green"),
        )
        for ((ddl, source) in controls) {
            assertEquals(source.toString(), DdlEngineRepairs.withoutUnrequestedColorCycle(listOf(source), ddl).single().toString())
        }
    }

    @Test
    fun t309_statedCountsFollowTheSharedReaderAndOneUnambiguousGroup() {
        val japanese = normalize(
            listOf(instruction("circle", color = "red", count = 2)),
            "赤い円を二百三十九個並べる。",
            "ja",
        ).single()
        assertEquals(239, japanese.getJSONObject("arrangement").getInt("count"))
        assertEquals(1, japanese.getString("note").split(";").count { it.trim() == "stated count from the clause honoured" })

        val english = normalize(
            listOf(instruction("circle", color = "black", count = 2)),
            "draw 17 black pen circles.",
            "en",
        ).single()
        assertEquals(17, english.getJSONObject("arrangement").getInt("count"))

        val bare = normalize(
            listOf(instruction("circle", color = "black")),
            "draw 12 circles.",
            "en",
        ).single()
        assertEquals(12, bare.getJSONObject("arrangement").getInt("count"))

        val excluded = instruction("circle", color = "black", count = 2)
        assertEquals(
            excluded.toString(),
            DdlEngineRepairs.withStatedCountFidelity(
                listOf(excluded),
                "draw circles at 30 degrees near member 2.",
                "white",
                "en",
            ).single().toString(),
        )

        val ambiguous = listOf(
            instruction("circle", color = "red", count = 2),
            instruction("circle", color = "red", count = 4),
        )
        assertEquals(
            ambiguous.map(JSONObject::toString),
            DdlEngineRepairs.withStatedCountFidelity(
                ambiguous,
                "赤い円を十二個並べる。",
                "white",
                "ja",
            ).map(JSONObject::toString),
        )

        val spokenFor = listOf(
            instruction("circle", color = "red", count = 2),
            instruction("line", color = "black", count = 3),
        )
        val guarded = DdlEngineRepairs.withStatedCountFidelity(
            spokenFor,
            "赤い円を二個並べる。青い円を十二個並べる。",
            "white",
            "ja",
        )
        assertEquals(2, guarded[0].getJSONObject("arrangement").getInt("count"))

        val globallyHinted = listOf(
            instruction("circle", color = "red", weight = "pencil", count = 2),
            instruction("circle", color = "blue", weight = "pencil", count = 3),
        )
        val materialMatched = DdlEngineRepairs.withStatedCountFidelity(
            globallyHinted,
            "鉛筆で描く。赤い円を十二個並べる。",
            "white",
            "ja",
        )
        assertEquals(12, materialMatched[0].getJSONObject("arrangement").getInt("count"))
        assertEquals(3, materialMatched[1].getJSONObject("arrangement").getInt("count"))
    }

    @Test
    fun t310_statedCountIsAllOrNothingAtTheTotalBudget() {
        fun repaired(other: Int): Int = normalize(
            listOf(
                instruction("circle", color = "red", count = 2),
                instruction("line", color = "black", count = other),
            ),
            "赤い円を二百三十三個並べる。",
            "ja",
        ).first().getJSONObject("arrangement").getInt("count")

        assertEquals(233, repaired(167))
        assertEquals(2, repaired(168))
    }

    @Test
    fun t311_surfaceReturnsToTheNearestClosedShapeExceptMarkSurfaces() {
        fun surface(texture: String) = JSONObject().put("texture", texture)
        val square = instruction("square")
        val line = instruction("line").put("surface", surface("hatch"))
        val moved = DdlEngineRepairs.withSurfaceOnAClosedShape(listOf(square, line))
        assertEquals("hatch", moved[0].getJSONObject("surface").getString("texture"))
        assertFalse(moved[1].has("surface"))

        val noTarget = DdlEngineRepairs.withSurfaceOnAClosedShape(listOf(line)).single()
        assertFalse(noTarget.has("surface"))

        val occupied = instruction("circle").put("surface", surface("stipple"))
        val dropped = DdlEngineRepairs.withSurfaceOnAClosedShape(listOf(occupied, line))
        assertEquals("stipple", dropped[0].getJSONObject("surface").getString("texture"))
        assertFalse(dropped[1].has("surface"))

        for (primitive in listOf("line", "arc")) {
            for (texture in listOf("grain", "bleed", "wash")) {
                val mark = instruction(primitive).put("surface", surface(texture))
                assertEquals(texture, DdlEngineRepairs.withSurfaceOnAClosedShape(listOf(mark)).single().getJSONObject("surface").getString("texture"))
            }
        }
    }

    @Test
    fun t312_statedSmallSizeRunsBeforeDefaultsAndFillFoldingStillHolds() {
        val smallCircle = coerce(instruction("circle"), "小さな円を置く。")
        assertEquals(0.038, smallCircle.getDouble("radius"), 1e-9)

        val explicit = coerce(instruction("circle").put("radius", 0.12), "小さな円を置く。")
        assertEquals(0.12, explicit.getDouble("radius"), 1e-9)

        val ambiguous = coerce(instruction("circle"), "小さな円を置く。別の小さな円を置く。")
        assertEquals(0.15, ambiguous.getDouble("radius"), 1e-9)

        val ellipse = coerce(instruction("ellipse"), "draw a small ellipse.")
        assertEquals(0.06, ellipse.getJSONArray("size").getDouble(0), 1e-9)
        assertEquals(0.032, ellipse.getJSONArray("size").getDouble(1), 1e-9)

        val solid = coerce(instruction("circle").put("surface", JSONObject().put("texture", "solid")), "円を置く。")
        assertTrue(solid.getBoolean("filled"))
        val filled = coerce(instruction("circle").put("filled", true), "円を置く。")
        assertEquals("solid", filled.getJSONObject("surface").getString("texture"))
    }

    @Test
    fun t313_compositeBudgetCountsWholeSpansAndKeepsUnitGroupsStable() {
        val head = instruction("arc", count = 3)
        head.getJSONObject("arrangement").put("group_size", 2)
        val member = instruction("arc")
        val composite = listOf(head, member)
        assertEquals(listOf(6, 0), DdlEngineRepairs.compositeMarkCounts(composite))

        val budgeted = DdlEngineRepairs.withCompositeDensityBudget(
            composite,
            maxExpandedPerInstruction = 240,
            maxExpandedPrimitives = 5,
        )
        assertEquals(2, budgeted[0].getJSONObject("arrangement").getInt("count"))
        assertEquals(2, budgeted.size)
        assertEquals(listOf(4, 0), DdlEngineRepairs.compositeMarkCounts(budgeted))

        val ordinary = listOf(instruction("circle", count = 3))
        assertEquals(
            ordinary.map(JSONObject::toString),
            DdlEngineRepairs.withCompositeDensityBudget(ordinary).map(JSONObject::toString),
        )

        val explicitOne = instruction("circle", count = 3).also {
            it.getJSONObject("arrangement").put("group_size", 1)
        }
        val normalizedOne = normalize(listOf(explicitOne), "draw circles.", "en").single()
        val normalizedOrdinary = normalize(
            listOf(instruction("circle", count = 3)),
            "draw circles.",
            "en",
        ).single()
        assertFalse(normalizedOne.getJSONObject("arrangement").has("group_size"))
        assertEquals(normalizedOrdinary.toString(), normalizedOne.toString())

        val ordinaryHigh = instruction("circle", count = 300)
        val mixedHead = instruction("arc", count = 3).also {
            it.getJSONObject("arrangement").put("group_size", 2)
        }
        val mixed = normalize(
            listOf(ordinaryHigh, mixedHead, instruction("arc")),
            "draw circles and arcs.",
            "en",
        )
        val normalizedHigh = mixed.single { it.getString("primitive") == "circle" }
        assertTrue(normalizedHigh.getJSONObject("arrangement").getInt("count") < 300)
        assertTrue(normalizedHigh.getJSONObject("arrangement").getBoolean("preserve_space"))

        val totalMixedHead = instruction("arc", count = 3).also {
            it.getJSONObject("arrangement").put("group_size", 2)
        }
        val totalMixed = normalize(
            listOf(
                instruction("circle", count = 200),
                instruction("square", count = 200),
                totalMixedHead,
                instruction("arc"),
            ),
            "draw circles, squares, and arcs.",
            "en",
        )
        val ordinaryMixed = totalMixed.filter { it.getString("primitive") in setOf("circle", "square") }
        assertEquals(1, ordinaryMixed.count { it.getJSONObject("arrangement").getInt("count") == 200 })
        assertEquals(1, ordinaryMixed.count { it.getJSONObject("arrangement").getBoolean("preserve_space") })

        val expand = DefaultSvgRenderer::class.java.getDeclaredMethod(
            "expandCompositeGroups",
            JSONArray::class.java,
            java.lang.Long::class.java,
            java.lang.Long::class.java,
            app.inku.mobile.data.model.CanvasSize::class.java,
        ).apply { isAccessible = true }
        val expanded = expand.invoke(
            DefaultSvgRenderer(),
            JSONArray(composite),
            23L,
            17L,
            CanvasAspects.sizeFor("square"),
        ) as JSONArray
        assertEquals(6, expanded.length())
    }

    @Test
    fun t314_engineTwentyIsNamedOnlyByTheGatedTree() {
        assertEquals("20", ReferenceCorpus.ddlEngineVersion)
        assertEquals("/server_reference/ddl-engine-20/ddl_expand.json", ReferenceCorpus.path("ddl_expand.json"))
        assertTrue(ReferenceCorpus.text("ddl_expand.json").isNotBlank())
    }
}

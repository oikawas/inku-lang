package app.inku.mobile.render

import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompositeRepetitionTest {
    private fun score(): JSONObject = JSONObject(
        """{
          "instructions": [
            {
              "primitive": "arc",
              "center": [0.5, 0.5],
              "radius": 0.08,
              "angle_start": 220,
              "angle_end": 320,
              "weight": "computer",
              "arrangement": {"count": 3, "layout": "scatter", "group_size": 2},
              "at": {"region": [0.25, 0.25, 0.75, 0.75]}
            },
            {
              "primitive": "arc",
              "center": [0.5, 0.5],
              "radius": 0.08,
              "angle_start": 40,
              "angle_end": 140,
              "weight": "computer",
              "relation": {"type": "touching"}
            }
          ]
        }""".trimIndent()
    )

    @Test
    fun testT6CompositeCountAndLocalRelationsMatchTheServerDecision() {
        val renderer = DefaultSvgRenderer()
        val instructions = score().getJSONArray("instructions")
        val expand = DefaultSvgRenderer::class.java.getDeclaredMethod(
            "expandCompositeGroups",
            JSONArray::class.java,
            java.lang.Long::class.java,
            java.lang.Long::class.java,
            app.inku.mobile.data.model.CanvasSize::class.java,
        ).apply { isAccessible = true }
        val expanded = expand.invoke(
            renderer,
            instructions,
            23L,
            17L,
            CanvasAspects.sizeFor("square"),
        ) as JSONArray
        assertEquals(6, expanded.length())

        val resolve = DefaultSvgRenderer::class.java.getDeclaredMethod(
            "resolvePerformanceScore",
            JSONArray::class.java,
            java.lang.Long::class.java,
        ).apply { isAccessible = true }
        val resolved = resolve.invoke(renderer, expanded, 17L) as JSONArray
        for (index in 1 until resolved.length() step 2) {
            val member = resolved.getJSONObject(index)
            assertFalse(member.has("relation"))
            assertTrue(member.has("center"))
            assertTrue(member.has("radius"))
        }

        val endpoints = DefaultSvgRenderer::class.java.getDeclaredMethod(
            "canvasEndpointGeometry",
            JSONObject::class.java,
            java.lang.Long.TYPE,
            Integer.TYPE,
        ).apply { isAccessible = true }
        for (index in 0 until resolved.length() step 2) {
            val first = endpoints.invoke(
                renderer,
                resolved.getJSONObject(index),
                17L,
                index,
            ) as Array<*>
            val second = endpoints.invoke(
                renderer,
                resolved.getJSONObject(index + 1),
                17L,
                index + 1,
            ) as Array<*>
            for (endpointIndex in 0..1) {
                val expected = first[endpointIndex] as Pair<*, *>
                val actual = second[endpointIndex] as Pair<*, *>
                assertEquals(
                    (expected.first as Number).toDouble(),
                    (actual.first as Number).toDouble(),
                    1e-9,
                )
                assertEquals(
                    (expected.second as Number).toDouble(),
                    (actual.second as Number).toDouble(),
                    1e-9,
                )
            }
        }

        val svg = renderer.render(
            RenderRequest(
                scoreJson = score().toString(),
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable",
                renderSeed = 17L,
                compositionSeed = 23L,
            )
        ).svg
        assertEquals(6, Regex("""id="mark_\d{3}_000_arc"""").findAll(svg).count())
    }
}

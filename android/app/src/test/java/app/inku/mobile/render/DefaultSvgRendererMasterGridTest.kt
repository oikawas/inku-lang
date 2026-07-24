package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Locale

class DefaultSvgRendererMasterGridTest {

    private val renderer = DefaultSvgRenderer()

    private val sampleScoreJson = """
    {
      "canvas": "square",
      "background": "white",
      "instructions": [
        {
          "primitive": "line",
          "color": "black",
          "weight": "pen",
          "from": [0.1, 0.5],
          "to": [0.9, 0.5]
        },
        {
          "primitive": "circle",
          "color": "black",
          "weight": "crayon",
          "center": [0.5, 0.5],
          "radius": 0.3,
          "surface": {
            "texture": "hatch",
            "density": 0.5
          }
        }
      ]
    }
    """.trimIndent()

    private fun createRequest(): RenderRequest {
        return RenderRequest(
            scoreJson = sampleScoreJson,
            colorCatalogId = "default",
            canvasAspect = "square",
            svgProfile = "display"
        )
    }

    @Test
    fun testEveryEmittedNumberSitsOnMasterGrid() {
        val request = createRequest()
        val result = renderer.render(request)
        val svg = result.svg

        val attrRe = Regex("""([\w:-]+)="([^"]*)"""")
        val numWithDotRe = Regex("""-?\d+\.\d+(?:[eE][-+]?\d+)?""")
        val ungriddedAttrs = setOf("version", "class", "id")

        val matches = attrRe.findAll(svg).toList()
        assertTrue("SVG must contain attributes", matches.isNotEmpty())

        var decimalNumberCount = 0
        for (match in matches) {
            val name = match.groupValues[1]
            val value = match.groupValues[2]
            if (name in ungriddedAttrs) continue

            for (numMatch in numWithDotRe.findAll(value)) {
                val numStr = numMatch.value
                decimalNumberCount++
                val decimals = numStr.substringAfter(".")
                assertEquals(
                    "Attribute $name contains number $numStr which does not have exactly 6 decimal places",
                    6,
                    decimals.length
                )
            }
        }
        assertTrue("Should have checked decimal numbers", decimalNumberCount > 0)
    }

    @Test
    fun testIntegersRemainIntegers() {
        val request = createRequest()
        val result = renderer.render(request)
        val svg = result.svg

        assertTrue("width attribute should be 1000", svg.contains("""width="1000""""))
        assertTrue("height attribute should be 1000", svg.contains("""height="1000""""))
        assertTrue("viewBox attribute should be 0 0 1000 1000", svg.contains("""viewBox="0 0 1000 1000""""))
    }

    @Test
    fun testLocaleIndependence() {
        val originalLocale = Locale.getDefault()
        try {
            Locale.setDefault(Locale.US)
            val resultUs = renderer.render(createRequest())

            Locale.setDefault(Locale.GERMANY)
            val resultGermany = renderer.render(createRequest())

            assertEquals("SVG output must be identical regardless of default locale", resultUs.svg, resultGermany.svg)
        } finally {
            Locale.setDefault(originalLocale)
        }
    }
}

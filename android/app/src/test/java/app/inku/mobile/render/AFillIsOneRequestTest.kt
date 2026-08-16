package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A fill is one request, however it is written ([I-248]).
 *
 * `filled=true` and `surface.texture="solid"` say the same thing, and the server
 * settles it in one place (`fill_is_asked_for`, `_has_surface_texture`,
 * `_fills_interior`). The port used to decide it twice, in two copies of an
 * expression that read the boolean alone and gave up on the fill the moment a
 * `surface` field existed at all.
 *
 * The frozen corpus cannot see any of this: it holds no `solid` case, no
 * `surface: {"texture": "none"}` case, and its two surface works carry no
 * `filled`. So these gates are stated as properties -- what the server answers
 * for the same instruction -- with the control that must not move beside each.
 */
class AFillIsOneRequestTest {

    private val seed = 12345L

    private fun renderSvg(instruction: String): String =
        DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = """{"instructions":[$instruction]}""",
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable",
                renderSeed = seed,
            )
        ).svg

    /** The marks the interior fill puts down; empty when the interior is not filled. */
    private fun fillsInterior(svg: String): Boolean =
        svg.contains("fill-stroke-v1") || svg.contains("fill-dab-v1") || svg.contains("fill-texture-v1")

    private fun square(surface: String?, filled: Boolean?): String = buildString {
        append("""{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"weight":"pen","color":"black"""")
        if (filled != null) append(""","filled":$filled""")
        if (surface != null) append(""","surface":$surface""")
        append("}")
    }

    /**
     * T-133: the request arrives on the surface word alone. `filled` stays false on
     * both sides, so what is measured is whether `solid` reaches the fill at all --
     * and `hatch`, the control, must still take the interior away from it.
     */
    @Test
    fun testSolidAloneFillsTheInteriorAndHatchStillDoesNot() {
        val solid = renderSvg(square("""{"texture":"solid"}""", filled = false))
        assertTrue(
            "surface.texture=solid must fill the interior the way filled=true does",
            fillsInterior(solid),
        )

        val hatch = renderSvg(square("""{"texture":"hatch"}""", filled = false))
        assertFalse(
            "a real surface texture must keep the interior for itself",
            fillsInterior(hatch),
        )
        assertTrue("the hatch control must have drawn its own surface", hatch.contains("surface-stroke-v1"))
    }

    /**
     * T-134: the divergence that was already in the drawings before `solid` existed.
     * The port gave up on the fill because a `surface` field was present, without
     * reading what it said; the server reads `texture` and fills.
     */
    @Test
    fun testAFilledShapeIsStillFilledWhenItsSurfaceSaysNone() {
        val withNoneSurface = renderSvg(square("""{"texture":"none"}""", filled = true))
        assertTrue(
            "a surface that says none must not take the fill away",
            fillsInterior(withNoneSurface),
        )

        val withoutSurface = renderSvg(square(surface = null, filled = true))
        assertTrue(
            "the shape without a surface must still be filled",
            fillsInterior(withoutSurface),
        )
    }
}

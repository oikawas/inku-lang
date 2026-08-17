package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The machine pole's line does not waver, whatever it was asked to do ([I-307]).
 *
 * The server's `line` branch hands every weight but `rotring` to
 * `_render_hand_stroke` and answers `rotring` with `dwg.line(start, end)`. It
 * reaches neither the variation gate nor the material layer: a ruling pen has no
 * hand to wobble. The port read the gate on that road and wrote a `<polyline>`,
 * which is a branch the server has no counterpart for.
 *
 * The frozen corpus cannot see any of this. Of its 51 drawings, four carry a
 * `variation` and two are drawn with `rotring`, and no drawing is both: the only
 * line with a variation is `09_line_white`, whose weight is `pencil`. So both
 * gates here are stated as properties -- what the server answers for the same
 * instruction -- with the hand pole beside them as the control that must move.
 */
class TheMachinePoleLineDoesNotWaverTest {

    private val seed = 12345L

    private fun render(instruction: String): String =
        DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = """{"instructions":[$instruction]}""",
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable",
                renderSeed = seed,
            )
        ).svg

    /** The variation the port used to act on: a wave along the line's own axis. */
    private val wave =
        """{"amplitude":"medium","frequency":"medium","quality":"wave","dimensions":["position_y"]}"""

    private fun line(weight: String, variation: String? = null): String = buildString {
        append("""{"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"$weight","color":"black"""")
        if (variation != null) append(""","variation":$variation""")
        append("}")
    }

    private fun count(svg: String, needle: String): Int = svg.split(needle).size - 1

    private fun lineElement(svg: String, who: String): String {
        val match = Regex("""<line\b[^>]*>""").find(svg)
        assertTrue("$who must hold a <line> element:\n$svg", match != null)
        return match!!.value
    }

    private fun coordinate(element: String, name: String): String {
        val match = Regex("""\b$name="([^"]*)"""").find(element)
        assertTrue("the <line> must carry $name: $element", match != null)
        return match!!.groupValues[1]
    }

    /**
     * T-242: the machine pole's line does not waver even when it is asked to.
     *
     * Stated on the elements, because the element itself is the divergence: the
     * server writes one `<line>` and the port wrote a `<polyline>` of wobbling
     * points. The hand pole is the control on the same request. Without it, "no
     * polyline" would be just as true of a port that had lost the gate on every
     * road, which is the opposite defect.
     */
    @Test
    fun testAMachinePoleLineAskedToWaverStaysOneStraightLine() {
        val varied = render(line("rotring", wave))
        assertEquals("a rotring line asked to wave must write no <polyline>:\n$varied", 0, count(varied, "<polyline"))
        assertEquals("it writes the one <line> the server writes:\n$varied", 1, count(varied, "<line "))

        val hand = render(line("pencil", wave))
        val handWithoutTheVariation = render(line("pencil"))
        assertNotEquals(
            "the control must move: the hand pole still reads the same variation",
            handWithoutTheVariation,
            hand,
        )
    }

    /**
     * T-243: and it does not read the variation at all.
     *
     * The same score drawn with and without the `variation`, compared on the four
     * coordinates the machine pole's line is made of. Whole-file byte equality is
     * deliberately not claimed here: naming a `render_seed` pins the instruction's
     * own seed, but whether some other layer reads the score as a whole is not
     * measured, and a gate must not assert more than it has measured.
     */
    @Test
    fun testAMachinePoleLineDoesNotReadItsVariation() {
        val varied = lineElement(render(line("rotring", wave)), "the line asked to wave")
        val plain = lineElement(render(line("rotring")), "the line never asked to")
        var compared = 0
        for (name in listOf("x1", "y1", "x2", "y2")) {
            assertEquals(
                "a rotring line's $name must not move when a variation is added",
                coordinate(plain, name),
                coordinate(varied, name),
            )
            compared++
        }
        assertEquals("all four coordinates must be compared", 4, compared)
    }
}

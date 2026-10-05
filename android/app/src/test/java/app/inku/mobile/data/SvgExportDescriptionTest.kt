package app.inku.mobile.data

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The display SVG carries the description it was drawn from, as web's
 * `downloadSVG` writes it: `<desc>` right after the first `<svg ...>` tag, with
 * `&`, `<`, `>` and `"` escaped and `'` left alone.
 */
class SvgExportDescriptionTest {

    @Test
    fun theDescriptionGoesRightAfterTheSvgTagEscaped() {
        assertEquals(
            """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><desc>a &amp; b &lt;c&gt; &quot;d&quot; 'e'</desc><g/></svg>""",
            withDescription(
                """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><g/></svg>""",
                """a & b <c> "d" 'e'""",
            ),
        )
    }

    @Test
    fun anEmptyDescriptionStillWritesTheElement() {
        assertEquals("<svg><desc></desc></svg>", withDescription("<svg></svg>", ""))
    }

    @Test
    fun theProlog() {
        assertEquals(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg width="2"><desc>夜の灯り</desc><svg width="1"/></svg>""",
            withDescription(
                """<?xml version="1.0" encoding="UTF-8"?>
<svg width="2"><svg width="1"/></svg>""",
                "夜の灯り",
            ),
        )
    }

    @Test
    fun anythingWithoutAnSvgTagIsLeftAlone() {
        assertEquals("<html></html>", withDescription("<html></html>", "x"))
        assertEquals("<svg", withDescription("<svg", "x"))
    }

    /** web's `replace` would read `$&` and `$1` as patterns; the text is inserted as it is. */
    @Test
    fun replacementPatternsAreTakenLiterally() {
        assertEquals("<svg><desc>$&amp; $1 $$</desc></svg>", withDescription("<svg></svg>", "$& $1 $$"))
    }
}

package app.inku.mobile.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.sp
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Naming the drawing materials must not repaint anything (T-1..T-3).
 *
 * The token layer was extracted from 89 colour literals, 429 `.dp` literals and
 * 8 `.sp` literals that all lived inside `InkuApp.kt`. Extraction is only safe
 * if it is value-preserving, and "I moved 526 literals and changed none of them"
 * is not a claim a diff review can make reliably.
 *
 * So the pre-extraction value sets are frozen here, measured on `1b734abc` with
 * the commands in the contract, and the tokens are checked against them.
 *
 * These assert **coverage, not equality of counts**. Gaining a colour while
 * naming things is normal -- a role may want a 0x33 alpha of a hue that already
 * existed. Losing one is the regression. A token layer that is a superset still
 * paints every pixel the old literals painted.
 *
 * The colour and dimension checks read the tokens through Java reflection rather
 * than naming them, on purpose: a test that names every token would fail to
 * *compile* when one is deleted, which is a build error rather than a named red
 * test, and the deletion perturbation would prove nothing. Reflection sees
 * whatever the file currently exposes, so a removed token shows up as a missing
 * value. The five type sizes are named directly -- there is no deletion
 * perturbation aimed at them, and five values do not justify decoding
 * `TextUnit`'s internal packing out of a raw `long`.
 */
class ThemeTokensPreserveTheDrawingTest {

    // --- The nine scheme roles, as `InkuApp.kt` declared them before the move.
    private val schemeBefore = mapOf(
        "background" to 0xFF11100FL,
        "surface" to 0xFF181715L,
        "surfaceVariant" to 0xFF24211EL,
        "primary" to 0xFF7FA6D8L,
        "secondary" to 0xFFEAD7A3L,
        "outline" to 0xFF514A43L,
        "onBackground" to 0xFFEDE7DEL,
        "onSurface" to 0xFFEDE7DEL,
        "onSurfaceVariant" to 0xFFCFC6BAL,
    )

    /** The 57 distinct ARGB values `InkuApp.kt` held before the extraction. */
    private val colorsBefore = listOf(
        0xFF11100FL, 0xFF181715L, 0xFF24211EL, 0xFF7FA6D8L, 0xFFEAD7A3L,
        0xFF514A43L, 0xFFEDE7DEL, 0xFFCFC6BAL, 0xFF20201FL, 0xFF242321L,
        0xFFF5F1E9L, 0xFFF8F8F6L, 0xFF9CC6E8L, 0xFFB8D58AL, 0xFFE08A7AL,
        0xFFD2B7F0L, 0xFF8FD8C1L, 0xFFF2B66DL, 0xFFAEB7D8L, 0xFFE7A9C1L,
        0xFF12110FL, 0x1AEAD7A3L, 0xFF26221EL, 0x1A000000L, 0xCC11100FL,
        0x55EDE7DEL, 0xFF191816L, 0x22E08A7AL, 0xFF2A2622L, 0xFF20201EL,
        0xFF34302BL, 0x3324211EL, 0x1A7FA6D8L, 0xFF1B1A18L, 0xFF19150FL,
        0x66000000L, 0xFF2C2925L, 0xFF1B1B1AL, 0xFF22201DL, 0x337FA6D8L,
        0xCC24211EL, 0xFF101010L, 0xDD24211EL, 0xB8000000L, 0xFFFFFDF8L,
        0xE01C1C1CL, 0x2EFFFFFFL, 0xB8FFFDF8L, 0x29FFFFFFL, 0x10FFFFFFL,
        0x9EFFD45CL, 0x59FFFDF8L, 0xFFFFD45CL, 0xFF233144L, 0xFFCFC6B6L,
        0xFFDED6C9L, 0xFFD8CFC0L,
    )

    /**
     * The 53 distinct dp values, `0.dp` excluded. Zero is not a measurement and
     * deliberately has no token: `PaddingValues` still asks for it literally.
     */
    private val dpBefore = listOf(
        1f, 1.5f, 2f, 2.5f, 3f, 4f, 5f, 6f, 8f, 9f, 10f, 12f, 13f, 14f, 16f,
        18f, 20f, 22f, 26f, 28f, 32f, 34f, 38f, 40f, 44f, 54f, 56f, 64f, 72f,
        76f, 78f, 80f, 82f, 92f, 96f, 104f, 112f, 116f, 124f, 140f, 220f, 248f,
        250f, 260f, 320f, 330f, 360f, 420f, 430f, 460f, 520f, 560f, 680f,
    )

    // --- T-1 ---------------------------------------------------------------

    @Test
    fun t1_schemeRolesKeepTheirExactArgb() {
        val actual = mapOf(
            "background" to InkuColors.background,
            "surface" to InkuColors.surface,
            "surfaceVariant" to InkuColors.surfaceVariant,
            "primary" to InkuColors.primary,
            "secondary" to InkuColors.secondary,
            "outline" to InkuColors.outline,
            "onBackground" to InkuColors.onBackground,
            "onSurface" to InkuColors.onSurface,
            "onSurfaceVariant" to InkuColors.onSurfaceVariant,
        )
        assertEquals(
            "the scheme must expose exactly the nine roles it had before",
            schemeBefore.keys,
            actual.keys,
        )
        schemeBefore.forEach { (role, argb) ->
            assertEquals(
                "colorScheme.$role changed: naming a colour must not repaint it",
                Color(argb),
                actual.getValue(role),
            )
        }
    }

    // --- T-2 ---------------------------------------------------------------

    @Test
    fun t2_everyColorThatExistedBeforeStillHasAToken() {
        val tokens = colorTokens()
        assertTrue(
            "expected the colour tokens to be readable; found ${tokens.size}",
            tokens.size >= colorsBefore.size,
        )
        val missing = colorsBefore.distinct().filter { Color(it) !in tokens.values }
        assertEquals(
            "colours lost in the extraction (as ARGB): " +
                missing.joinToString { java.lang.Long.toHexString(it).uppercase() },
            emptyList<Long>(),
            missing,
        )
    }

    // --- T-3 ---------------------------------------------------------------

    @Test
    fun t3_everyDimensionAndTypeSizeThatExistedBeforeStillHasAToken() {
        val dp = dimenTokens()
        assertTrue(
            "expected the dimension tokens to be readable; found ${dp.size}",
            dp.size >= dpBefore.size,
        )
        val missingDp = dpBefore.distinct().filter { want -> dp.values.none { it == want } }
        assertEquals(
            "dp values lost in the extraction: $missingDp",
            emptyList<Float>(),
            missingDp,
        )

        val sp = setOf(
            TypeScale.labelTiny,
            TypeScale.editorBody,
            TypeScale.denseLineHeight,
            TypeScale.editorLineHeight,
            TypeScale.proseLineHeight,
        )
        listOf(11.sp, 16.sp, 17.sp, 21.sp, 22.sp).forEach {
            assertTrue("sp value $it lost in the extraction", it in sp)
        }
    }

    // --- reading the tokens -------------------------------------------------

    /**
     * Top-level `val`s in `Color.kt` compile to static getters on `ColorKt`.
     * `Color` is a value class over `ULong`, so a getter's erased return type is
     * `long` and the packed bits come back unchanged.
     */
    private fun colorTokens(): Map<String, Color> {
        val holder = Class.forName("app.inku.mobile.ui.theme.ColorKt")
        return holder.declaredMethods
            .filter { it.name.startsWith("get") && it.parameterCount == 0 }
            .filter { it.returnType == java.lang.Long.TYPE }
            .associate { m ->
                m.isAccessible = true
                m.name.removePrefix("get") to Color((m.invoke(null) as Long).toULong())
            }
    }

    /** `Dimens` is an object; `Dp` is a value class over `Float`. */
    private fun dimenTokens(): Map<String, Float> {
        return Dimens::class.java.declaredMethods
            .filter { it.name.startsWith("get") && it.parameterCount == 0 }
            .filter { it.returnType == java.lang.Float.TYPE }
            .associate { m ->
                m.isAccessible = true
                m.name.removePrefix("get") to (m.invoke(Dimens) as Float)
            }
    }
}

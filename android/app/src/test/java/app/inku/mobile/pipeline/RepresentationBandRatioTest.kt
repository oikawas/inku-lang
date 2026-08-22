package app.inku.mobile.pipeline

import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

/**
 * The representative band belongs to the device-local representation ceiling.
 *
 * Android does not transport the server's settings. These checks instead move an
 * explicit local limit pair through the same integer arithmetic as the server, while
 * keeping the shipping 80-120 pair one-to-one with the values the port already used.
 */
class RepresentationBandRatioTest {

    private val pipeline = LocalFallbackPipeline()

    private fun invokeInt(name: String, vararg args: Int): Int {
        val method = try {
            LocalFallbackPipeline::class.java.getDeclaredMethod(
                name,
                *Array(args.size) { Integer.TYPE },
            )
        } catch (missing: NoSuchMethodException) {
            fail("$name must accept explicit device-local representation limits")
            throw missing
        }
        method.isAccessible = true
        return method.invoke(pipeline, *args.toTypedArray()) as Int
    }

    private fun invokeString(name: String, vararg args: Int): String {
        val method = try {
            LocalFallbackPipeline::class.java.getDeclaredMethod(
                name,
                *Array(args.size) { Integer.TYPE },
            )
        } catch (missing: NoSuchMethodException) {
            fail("$name must accept explicit device-local representation limits")
            throw missing
        }
        method.isAccessible = true
        return method.invoke(pipeline, *args.toTypedArray()) as String
    }

    @Test
    fun testShippingLimitsKeepTodaysBandsExactly() {
        val max = 120

        assertEquals("low", invokeString("densityLabel", 79, max))
        assertEquals("medium", invokeString("densityLabel", 80, max))
        assertEquals("medium", invokeString("densityLabel", 179, max))
        assertEquals("high", invokeString("densityLabel", 180, max))

        assertEquals(3, invokeInt("clusterCount", 72, max))
        assertEquals(3, invokeInt("clusterCount", 73, max))
        assertEquals(3, invokeInt("clusterCount", 96, max))
        assertEquals(3, invokeInt("clusterCount", 97, max))
        assertEquals(3, invokeInt("clusterCount", 119, max))
        assertEquals(5, invokeInt("clusterCount", 120, max))
        assertEquals(5, invokeInt("clusterCount", 239, max))
        assertEquals(7, invokeInt("clusterCount", 240, max))
        assertEquals(7, invokeInt("clusterCount", 499, max))
        assertEquals(9, invokeInt("clusterCount", 500, max))
    }

    @Test
    fun testBandsMoveWithAnotherDeviceLocalLimitPair() {
        val max = 144

        assertEquals("low", invokeString("densityLabel", 95, max))
        assertEquals("medium", invokeString("densityLabel", 96, max))
        assertEquals("medium", invokeString("densityLabel", 215, max))
        assertEquals("high", invokeString("densityLabel", 216, max))

        assertEquals(3, invokeInt("clusterCount", 143, max))
        assertEquals(6, invokeInt("clusterCount", 144, max))
        assertEquals(6, invokeInt("clusterCount", 287, max))
        assertEquals(8, invokeInt("clusterCount", 288, max))
        assertEquals(8, invokeInt("clusterCount", 599, max))
        assertEquals(10, invokeInt("clusterCount", 600, max))
    }

    @Test
    fun testVisualCountMovesWithTheLocalRepresentationPair() {
        val min = 96
        val max = 144

        assertEquals(144, invokeInt("clusteredVisualCount", 600, min, max))
    }
}

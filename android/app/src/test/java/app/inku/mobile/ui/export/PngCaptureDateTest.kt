package app.inku.mobile.ui.export

import java.time.ZoneId
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The capture date web stamps into a downloaded PNG (`pngMetadata.ts`), byte
 * for byte.
 *
 * The expected bytes are what web's `withPngCaptureDate` returned for the same
 * input and instant, run with Node 26 (`node run.ts`, which strips the types)
 * under `TZ=Asia/Tokyo` and, for the negative half-hour offset,
 * `TZ=America/St_Johns`. The input is a PNG signature, a 13-byte IHDR, a
 * two-byte IDAT and IEND: the stamp reads only the signature and IHDR's length.
 */
class PngCaptureDateTest {

    private val input = hex(
        "89504e470d0a1a0a0000000d4948445200000002000000030806000000112233440000000249444154abcd556677880000000049454e44ae426082",
    )

    @Test
    fun theStampIsWebsBytesInTokyo() {
        val tokyo = ZoneId.of("Asia/Tokyo")
        assertArrayEquals(
            hex(
                "89504e470d0a1a0a0000000d4948445200000002000000030806000000112233440000008f6558496649492a0008000000020032010200140000007400000069870400010000002600000000000000060000900700040000003032333103900200140000007400000004900200140000007400000010900200070000008800000011900200070000008800000012900200070000008800000000000000323032353a31303a30362030393a35393a3035002b30393a303000a36e3f7d0000002d744558744372656174696f6e2054696d65004d6f6e2c203036204f637420323032352030393a35393a3035202b3039303053b94c5e0000000249444154abcd556677880000000049454e44ae426082",
            ),
            PngCaptureDate.stamp(input, 1759712345678L, tokyo),
        )
        assertArrayEquals(
            hex(
                "89504e470d0a1a0a0000000d4948445200000002000000030806000000112233440000008f6558496649492a0008000000020032010200140000007400000069870400010000002600000000000000060000900700040000003032333103900200140000007400000004900200140000007400000010900200070000008800000011900200070000008800000012900200070000008800000000000000323032343a30313a30312030383a35393a3539002b30393a303000f27154d80000002d744558744372656174696f6e2054696d65004d6f6e2c203031204a616e20323032342030383a35393a3539202b303930305efa04d20000000249444154abcd556677880000000049454e44ae426082",
            ),
            PngCaptureDate.stamp(input, 1704067199000L, tokyo),
        )
    }

    @Test
    fun aNegativeHalfHourOffsetIsWrittenAsWebWritesIt() {
        assertArrayEquals(
            hex(
                "89504e470d0a1a0a0000000d4948445200000002000000030806000000112233440000008f6558496649492a0008000000020032010200140000007400000069870400010000002600000000000000060000900700040000003032333103900200140000007400000004900200140000007400000010900200070000008800000011900200070000008800000012900200070000008800000000000000323032353a31303a30352032323a32393a3035002d30323a3330007b89dda80000002d744558744372656174696f6e2054696d650053756e2c203035204f637420323032352032323a32393a3035202d303233306eba806f0000000249444154abcd556677880000000049454e44ae426082",
            ),
            PngCaptureDate.stamp(input, 1759712345678L, ZoneId.of("America/St_Johns")),
        )
    }

    @Test
    fun anythingButAPngIsLeftAlone() {
        val tokyo = ZoneId.of("Asia/Tokyo")
        val short = input.copyOfRange(0, 32)
        assertArrayEquals("shorter than a signature and an IHDR", short, PngCaptureDate.stamp(short, 0L, tokyo))
        val notPng = input.copyOf().also { it[1] = 0x51 }
        assertArrayEquals("not a PNG signature", notPng, PngCaptureDate.stamp(notPng, 0L, tokyo))
        val overlong = input.copyOf().also { it[11] = 0x7f }
        assertArrayEquals("an IHDR longer than the file", overlong, PngCaptureDate.stamp(overlong, 0L, tokyo))
        assertEquals("an eXIf and a tEXt chunk", input.size + (12 + 143) + (12 + 45), PngCaptureDate.stamp(input, 0L, tokyo).size)
    }

    private fun hex(text: String): ByteArray = ByteArray(text.length / 2) { index ->
        text.substring(index * 2, index * 2 + 2).toInt(16).toByte()
    }
}

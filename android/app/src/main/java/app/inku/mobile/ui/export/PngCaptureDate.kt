package app.inku.mobile.ui.export

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.zip.CRC32

/**
 * The work's capture date in an exported PNG -- the port of web's
 * `pngMetadata.ts`, byte for byte.
 *
 * A PNG written by `Bitmap.compress` carries no date, so the file would show
 * the day it was shared rather than the day the work was made. Two chunks go
 * right after IHDR, which is where the PNG spec wants eXIf: an `eXIf` chunk
 * (PNG 1.5.0 / ISO 15948:2004+, read as EXIF by Finder, Preview, Lightroom,
 * exiftool) and a `tEXt` "Creation Time" entry for viewers that ignore eXIf.
 */
object PngCaptureDate {

    private val PNG_SIGNATURE = byteArrayOf(0x89.toByte(), 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)

    // Fixed English names: the PNG keyword expects an RFC 1123 date whatever
    // the reader's language.
    private val RFC1123_DAYS = listOf("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
    private val RFC1123_MONTHS = listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

    /**
     * [png] carrying [epochMillis], read in [zone], as its capture date. Input
     * that is not a PNG, or is too short to hold an IHDR, comes back unchanged
     * rather than corrupted.
     */
    fun stamp(png: ByteArray, epochMillis: Long, zone: ZoneId): ByteArray {
        if (png.size < 8 + 25 || PNG_SIGNATURE.indices.any { png[it] != PNG_SIGNATURE[it] }) return png
        val ihdrLength = ByteBuffer.wrap(png, 8, 4).order(ByteOrder.BIG_ENDIAN).int.toLong() and 0xffffffffL
        val insertAt = 8L + 12L + ihdrLength
        if (insertAt > png.size) return png
        val at = insertAt.toInt()

        val date = ZonedDateTime.ofInstant(Instant.ofEpochMilli(epochMillis), zone)
        val exif = chunk("eXIf", exifDateBlock(date))
        val creationTime = creationTimeChunk(date)
        return ByteArrayOutputStream(png.size + exif.size + creationTime.size).apply {
            write(png, 0, at)
            write(exif)
            write(creationTime)
            write(png, at, png.size - at)
        }.toByteArray()
    }

    private fun chunk(type: String, data: ByteArray): ByteArray {
        val chunk = ByteBuffer.allocate(12 + data.size).order(ByteOrder.BIG_ENDIAN)
        chunk.putInt(data.size)
        type.forEach { chunk.put(it.code.toByte()) }
        chunk.put(data)
        val crc = CRC32().apply { update(chunk.array(), 4, 4 + data.size) }
        chunk.putInt(crc.value.toInt())
        return chunk.array()
    }

    private fun pad2(value: Int): String = value.toString().padStart(2, '0')

    /** EXIF date form: local time, "YYYY:MM:DD HH:MM:SS". */
    private fun exifDateString(date: ZonedDateTime): String =
        "${date.year}:${pad2(date.monthValue)}:${pad2(date.dayOfMonth)} " +
            "${pad2(date.hour)}:${pad2(date.minute)}:${pad2(date.second)}"

    /** EXIF offset form: "+09:00". EXIF date tags carry no zone of their own. */
    private fun exifOffsetString(date: ZonedDateTime): String {
        val minutes = date.offset.totalSeconds / 60
        val sign = if (minutes < 0) "-" else "+"
        val abs = Math.abs(minutes)
        return "$sign${pad2(abs / 60)}:${pad2(abs % 60)}"
    }

    private fun asciiBytes(value: String, length: Int): ByteArray {
        val bytes = ByteArray(length)
        for (index in 0 until minOf(value.length, length - 1)) bytes[index] = value[index].code.toByte()
        return bytes // NUL-terminated by the zero fill
    }

    /**
     * Minimal little-endian TIFF stream holding the date tags only:
     *   IFD0     DateTime (0x0132), Exif IFD pointer (0x8769)
     *   Exif IFD ExifVersion, DateTimeOriginal, DateTimeDigitized,
     *            OffsetTime, OffsetTimeOriginal, OffsetTimeDigitized
     */
    private fun exifDateBlock(date: ZonedDateTime): ByteArray {
        val ifd0Entries = 2
        val exifEntries = 6
        val ifd0Offset = 8
        val exifIfdOffset = ifd0Offset + 2 + ifd0Entries * 12 + 4
        val dataOffset = exifIfdOffset + 2 + exifEntries * 12 + 4
        val dateOffset = dataOffset
        val offsetOffset = dateOffset + 20
        val total = offsetOffset + 7

        val bytes = ByteBuffer.allocate(total).order(ByteOrder.LITTLE_ENDIAN)
        // TIFF header: "II", little endian.
        bytes.put(0, 0x49).put(1, 0x49)
        bytes.putShort(2, 42)
        bytes.putInt(4, ifd0Offset)

        var cursor = ifd0Offset
        fun entry(tag: Int, type: Int, count: Int, write: (at: Int) -> Unit) {
            bytes.putShort(cursor, tag.toShort())
            bytes.putShort(cursor + 2, type.toShort())
            bytes.putInt(cursor + 4, count)
            write(cursor + 8)
            cursor += 12
        }
        val ascii = 2
        val long = 4
        val undefined = 7

        bytes.putShort(cursor, ifd0Entries.toShort())
        cursor += 2
        entry(0x0132, ascii, 20) { bytes.putInt(it, dateOffset) }
        entry(0x8769, long, 1) { bytes.putInt(it, exifIfdOffset) }
        bytes.putInt(cursor, 0) // no IFD1
        cursor += 4

        bytes.putShort(cursor, exifEntries.toShort())
        cursor += 2
        // Tags must ascend. ExifVersion "0231" fits inline in the value field.
        entry(0x9000, undefined, 4) { bytes.put(it, 0x30).put(it + 1, 0x32).put(it + 2, 0x33).put(it + 3, 0x31) }
        entry(0x9003, ascii, 20) { bytes.putInt(it, dateOffset) }
        entry(0x9004, ascii, 20) { bytes.putInt(it, dateOffset) }
        entry(0x9010, ascii, 7) { bytes.putInt(it, offsetOffset) }
        entry(0x9011, ascii, 7) { bytes.putInt(it, offsetOffset) }
        entry(0x9012, ascii, 7) { bytes.putInt(it, offsetOffset) }
        bytes.putInt(cursor, 0)

        val array = bytes.array()
        asciiBytes(exifDateString(date), 20).copyInto(array, dateOffset)
        asciiBytes(exifOffsetString(date), 7).copyInto(array, offsetOffset)
        return array
    }

    /** PNG "Creation Time" keyword expects an RFC 1123 date. */
    private fun creationTimeChunk(date: ZonedDateTime): ByteArray {
        val offset = exifOffsetString(date).replaceFirst(":", "")
        val value = "${RFC1123_DAYS[date.dayOfWeek.value % 7]}, ${pad2(date.dayOfMonth)} ${RFC1123_MONTHS[date.monthValue - 1]} " +
            "${date.year} ${pad2(date.hour)}:${pad2(date.minute)}:${pad2(date.second)} $offset"
        val text = "Creation Time\u0000$value"
        return chunk("tEXt", ByteArray(text.length) { (text[it].code and 0xff).toByte() })
    }
}

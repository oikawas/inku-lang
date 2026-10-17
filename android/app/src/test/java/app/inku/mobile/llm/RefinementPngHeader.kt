package app.inku.mobile.llm

/** IHDR bytes suffice for JVM transport tests; Android Bitmap encoding runs on device. */
internal fun refinementPngHeader(width: Int = 768, height: Int = 768): ByteArray = ByteArray(24).also { bytes ->
    byteArrayOf(137.toByte(), 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82)
        .copyInto(bytes)
    for ((offset, dimension) in listOf(16 to width, 20 to height)) {
        bytes[offset] = (dimension ushr 24).toByte()
        bytes[offset + 1] = (dimension ushr 16).toByte()
        bytes[offset + 2] = (dimension ushr 8).toByte()
        bytes[offset + 3] = dimension.toByte()
    }
}

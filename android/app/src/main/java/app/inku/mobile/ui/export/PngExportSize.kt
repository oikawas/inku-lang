package app.inku.mobile.ui.export

import app.inku.mobile.ui.i18n.inkuError

/**
 * The pixel size of an exported PNG, decided before anything is drawn.
 *
 * The height is the template's, 64..2160 (the author, 2026-10-06). A height
 * outside that range is refused rather than drawn at another size: a file
 * that silently came out smaller than its template says would be read as the
 * size asked for. The width is the paper's at that height, rounded half to
 * even like `CanvasAspects.sizeFor`, and it is checked against the raster
 * crate's limits here, so a paper too wide to draw is refused with a sentence
 * instead of failing inside the rasterizer.
 */
data class PngExportSize(val width: Int, val height: Int) {
    companion object {
        const val MIN_HEIGHT_PX = 64
        const val MAX_HEIGHT_PX = 2160

        /** `MAX_RASTER_DIMENSION` in `core/crates/inku-svg-raster/src/lib.rs`. */
        const val MAX_RASTER_DIMENSION = 8_192

        /** `MAX_RASTER_PIXELS` in `core/crates/inku-svg-raster/src/lib.rs`. */
        const val MAX_RASTER_PIXELS = 16_777_216L

        /** @param ratio the paper's width over its height (`CanvasAspects.ratioFor`). */
        fun of(heightPx: Int, ratio: Double): PngExportSize {
            if (heightPx !in MIN_HEIGHT_PX..MAX_HEIGHT_PX) {
                inkuError { it.exportPngHeightOutOfRange(MIN_HEIGHT_PX, MAX_HEIGHT_PX) }
            }
            val width = Math.rint(heightPx * ratio)
            if (!width.isFinite() || width < 1.0 || width > MAX_RASTER_DIMENSION ||
                width.toLong() * heightPx > MAX_RASTER_PIXELS
            ) {
                inkuError { it.exportPngTooLarge }
            }
            return PngExportSize(width.toInt(), heightPx)
        }
    }
}

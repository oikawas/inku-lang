package app.inku.mobile.render

/** Host transforms only. Density limiting and outward pixel rounding stay in Rust. */
internal data class DisplayWindowInput(val zoomed: DisplayRect, val visible: DisplayRect)

internal fun displayWindowInput(
    pictureWidth: Double, pictureHeight: Double, viewportWidth: Double, viewportHeight: Double,
    zoom: Double, panX: Double, panY: Double, rotationDegrees: Int,
): DisplayWindowInput? {
    if (zoom <= 1.001 || pictureWidth <= 0 || pictureHeight <= 0 || viewportWidth <= 0 || viewportHeight <= 0) return null
    val width = pictureWidth * zoom
    val height = pictureHeight * zoom
    val left = (viewportWidth - width) / 2 + panX
    val top = (viewportHeight - height) / 2 + panY
    val visibleLeft = maxOf(0.0, left)
    val visibleTop = maxOf(0.0, top)
    val visibleRight = minOf(viewportWidth, left + width)
    val visibleBottom = minOf(viewportHeight, top + height)
    val visibleWidth = visibleRight - visibleLeft
    val visibleHeight = visibleBottom - visibleTop
    if (visibleWidth < 1 || visibleHeight < 1) return null
    val x = visibleLeft - left
    val y = visibleTop - top
    return when (AndroidDisplayRenderer.normalizedRotation(rotationDegrees)) {
        90 -> DisplayWindowInput(DisplayRect(0.0, 0.0, height, width),
            DisplayRect(y, width - x - visibleWidth, visibleHeight, visibleWidth))
        180 -> DisplayWindowInput(DisplayRect(0.0, 0.0, width, height),
            DisplayRect(width - x - visibleWidth, height - y - visibleHeight, visibleWidth, visibleHeight))
        270 -> DisplayWindowInput(DisplayRect(0.0, 0.0, height, width),
            DisplayRect(height - y - visibleHeight, x, visibleHeight, visibleWidth))
        else -> DisplayWindowInput(DisplayRect(0.0, 0.0, width, height), DisplayRect(x, y, visibleWidth, visibleHeight))
    }
}

/** A source window's fractions in the displayed (rotated) picture. */
internal fun displayedWindowFraction(region: DisplayRegion, rotationDegrees: Int): DisplayRect {
    val x = region.x.toDouble() / region.fullWidth
    val y = region.y.toDouble() / region.fullHeight
    val width = region.width.toDouble() / region.fullWidth
    val height = region.height.toDouble() / region.fullHeight
    return when (AndroidDisplayRenderer.normalizedRotation(rotationDegrees)) {
        90 -> DisplayRect(1 - y - height, x, height, width)
        180 -> DisplayRect(1 - x - width, 1 - y - height, width, height)
        270 -> DisplayRect(y, 1 - x - width, height, width)
        else -> DisplayRect(x, y, width, height)
    }
}

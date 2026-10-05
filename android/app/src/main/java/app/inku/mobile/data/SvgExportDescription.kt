package app.inku.mobile.data

/**
 * The display SVG with the description it was drawn from, as web's
 * `downloadSVG` writes it (`features/export/download.ts`): a `<desc>` right
 * after the first `<svg ...>` tag -- what `/(<svg[^>]*>)/` finds -- with `&`,
 * `<`, `>` and `"` escaped and `'` left alone.
 *
 * The text is inserted as it is. web passes it through `String.replace`, which
 * would read a `$&` or `$1` in a description as a pattern; a description is
 * the author's words, so nothing in it is expanded here. An SVG without such a
 * tag comes back unchanged, as web's `replace` leaves it.
 */
internal fun withDescription(svg: String, input: String): String {
    val open = svg.indexOf("<svg")
    if (open < 0) return svg
    val close = svg.indexOf('>', open + "<svg".length)
    if (close < 0) return svg
    val escaped = input
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
    return buildString(svg.length + escaped.length + 13) {
        append(svg, 0, close + 1)
        append("<desc>").append(escaped).append("</desc>")
        append(svg, close + 1, svg.length)
    }
}

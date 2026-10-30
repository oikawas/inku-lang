package app.inku.mobile.pipeline

import org.json.JSONArray

/** The core's spans use Unicode scalar indices, rather than Kotlin's UTF-16 indices. */
internal fun descriptionSourceLabels(binding: SharedPipelineBinding, text: String): JSONArray {
    val spans = JSONArray(binding.descriptionLabelSpans(text))
    val labels = JSONArray()
    for (i in 0 until spans.length()) {
        val span = spans.getJSONArray(i)
        if (span.getString(2) != "comment") continue
        val start = text.offsetByCodePoints(0, span.getInt(0) + 1)
        val end = text.offsetByCodePoints(0, span.getInt(1) - 1)
        val label = text.substring(start, end).trim()
        if (label.isNotEmpty()) labels.put(label)
    }
    return labels
}

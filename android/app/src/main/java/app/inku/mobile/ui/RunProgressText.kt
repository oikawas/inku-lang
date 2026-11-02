package app.inku.mobile.ui

import app.inku.mobile.pipeline.ProgressCurrent
import app.inku.mobile.pipeline.ProgressItem
import app.inku.mobile.pipeline.ProviderAttempt
import app.inku.mobile.ui.i18n.InkuStrings
import app.inku.mobile.ui.i18n.InkuStringsJa
import java.util.Locale

internal fun stageName(action: String, s: InkuStrings): String = when (action) {
    "select_description_catalog" -> s.runStageCatalog
    "read_description" -> s.runStageReading
    "compose_description" -> s.runStageComposition
    "write_description_ddl" -> s.runStageWriting
    "review_description_ddl" -> s.runStageReview
    "choose_colors" -> s.runStageColors
    "choose_laws" -> s.runStageLaws
    "generate_normalized_ddl" -> s.runStageInterpret
    "generate_sketch" -> s.runStageSketch
    "read_composition" -> s.runStageCompositionReading
    "complete_visible_ddl_holes" -> s.runStageCompletion
    "select_image_catalog" -> s.runStageImageCatalog
    "write_image_ddl" -> s.runStageImageWriting
    "review_image_ddl" -> s.runStageImageReview
    else -> action
}

internal fun finishedText(item: ProgressItem, s: InkuStrings): String {
    val stage = stageName(item.action, s)
    if (item.outcome == "fallback") return s.runFinishedFallback(stage)
    if (item.outcome == "retried") return s.runFinishedRetried(stage)
    val facts = item.facts
    if (item.action == "read_description") return if (facts.optDouble("dropped_items", 0.0) > 0)
        s.runFinishedReadingDropped(facts.get("dropped_items").toString()) else s.runFinishedReading
    if (item.action == "compose_description" && !facts.isNull("things") && !facts.isNull("main_law"))
        return s.runFinishedComposition(facts.get("things").toString(), facts.get("main_law").toString())
    if (item.action in setOf("write_description_ddl", "write_image_ddl")) return s.runFinishedWriting
    if (item.action in setOf("review_description_ddl", "review_image_ddl")) return s.runFinishedReview
    if (!facts.isNull("catalog_id")) return s.runFinishedCatalog(stage, facts.get("catalog_id").toString())
    if (!facts.isNull("main_law")) return s.runFinishedLaw(stage, facts.get("main_law").toString())
    return s.runFinishedReady(stage)
}

internal fun currentWork(current: ProgressCurrent?, label: String, attempt: ProviderAttempt?, s: InkuStrings): String {
    current ?: return label
    if (current.kind == "local") return when (current.action) {
        "draw_image_review" -> s.runLocalReview
        "commit_visible_normalized_ddl", "save" -> s.runLocalSave
        else -> s.runLocalRender
    }
    val again = attempt?.takeIf { it.action == current.action }?.askedAgain == true
    val ja = s === InkuStringsJa
    return when (current.action) {
        "select_image_catalog" -> if (ja) "画像から色カタログを選んでいます…" else "Choosing colors from the image…"
        "write_image_ddl" -> if (again) { if (ja) "指示書を直しています…" else "Revising the instructions…" }
            else if (ja) "画像から指示書を書いています…" else "Writing instructions from the image…"
        "review_image_ddl" -> if (again) { if (ja) "指示書を直しています…" else "Revising the instructions…" }
            else if (ja) "画像と描いた画を見比べています…" else "Comparing the image with the drawing…"
        "read_description" -> if (ja) "記述を読んでいます…" else "Reading the description…"
        "compose_description" -> if (again) { if (ja) "構図と法則を決め直しています…" else "Deciding the composition and laws again…" }
            else if (ja) "構図と法則を決めています…" else "Deciding the composition and laws…"
        "write_description_ddl" -> if (again) { if (ja) "指示書を直しています…" else "Revising the instructions…" }
            else if (ja) "指示書を書いています…" else "Writing the instructions…"
        "review_description_ddl" -> if (again) { if (ja) "指示書を直しています…" else "Revising the instructions…" }
            else if (ja) "描いた画を見て直しています…" else "Correcting the instructions beside the drawing…"
        "read_composition" -> if (ja) "構図の読み中…" else "Reading the composition…"
        "choose_colors" -> if (ja) "配色の選択中…" else "Choosing the colors…"
        "choose_laws" -> if (ja) "法則の選択中…" else "Choosing the laws…"
        else -> stageName(current.action, s) + "…"
    }
}

internal fun tokenCount(value: Long?): String = value?.let { String.format(Locale.US, "%,d", it) } ?: "−"

internal fun batchElapsedTime(milliseconds: Long, s: InkuStrings): String {
    val total = (milliseconds / 1000).coerceAtLeast(0)
    val seconds = (total % 60).toString().padStart(2, '0')
    val minutes = total / 60
    return when {
        total < 60 -> s.elapsedSeconds(total.toString())
        total < 3600 -> s.elapsedMinutes(minutes.toString(), seconds)
        else -> s.elapsedHours((minutes / 60).toString(), (minutes % 60).toString().padStart(2, '0'), seconds)
    }
}

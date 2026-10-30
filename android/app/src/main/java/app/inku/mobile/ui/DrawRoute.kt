package app.inku.mobile.ui

import org.json.JSONObject
import app.inku.mobile.ui.i18n.InkuStrings

enum class DrawRoute { ReadAndDraw, Stages }

internal fun drawRouteOf(metadata: JSONObject): DrawRoute = when (metadata.optString("route")) {
    "read_and_draw" -> DrawRoute.ReadAndDraw
    "stages" -> DrawRoute.Stages
    else -> if (metadata.optJSONObject("description_ddl") != null) DrawRoute.ReadAndDraw else DrawRoute.Stages
}

internal fun compositionModeOf(metadata: JSONObject): Boolean =
    metadata.optJSONObject("description_ddl")?.optJSONObject("composition") != null

internal enum class DrawFlowKind { End, Switch, Fixed }
internal data class DrawFlowStep(val label: String, val kind: DrawFlowKind)

internal fun drawFlow(route: DrawRoute, sketch: Boolean, composition: Boolean, strings: InkuStrings): List<DrawFlowStep> {
    val steps = mutableListOf(DrawFlowStep(strings.flowDescription, DrawFlowKind.End))
    if (sketch) steps += DrawFlowStep(strings.flowSketch, DrawFlowKind.Switch)
    if (route == DrawRoute.Stages) {
        steps += listOf(DrawFlowStep(strings.flowFillPlan, DrawFlowKind.Fixed), DrawFlowStep(strings.flowComposition, DrawFlowKind.Fixed), DrawFlowStep(strings.flowColors, DrawFlowKind.Fixed))
    } else {
        if (composition) steps += DrawFlowStep(strings.flowComposition, DrawFlowKind.Switch)
        steps += listOf(DrawFlowStep(strings.flowWrite, DrawFlowKind.Fixed), DrawFlowStep(strings.flowReview, DrawFlowKind.Fixed))
        if (composition) steps += DrawFlowStep(strings.flowColors, DrawFlowKind.Switch)
    }
    steps += DrawFlowStep(strings.flowPicture, DrawFlowKind.End)
    return steps
}

internal fun descriptionDetails(record: JSONObject, strings: InkuStrings): List<Pair<String, String>> {
    fun JSONObject.string(key: String) = optString(key).takeUnless { it.isBlank() || it == "null" }.orEmpty()
    fun arrayItems(array: org.json.JSONArray?): List<JSONObject> =
        if (array == null) emptyList() else (0 until array.length()).mapNotNull { array.optJSONObject(it) }
    val rows = mutableListOf<Pair<String, String>>()
    val reading = when (record.string("reading_state")) {
        "read" -> strings.readingRead
        "supplied" -> strings.readingSupplied
        "fallback" -> strings.readingFallback
        else -> strings.readingOff
    }
    rows += strings.readingLabel to reading
    record.string("reading_text").takeIf(String::isNotEmpty)?.let { rows += strings.readingText to it }
    val dropped = arrayItems(record.optJSONArray("dropped_items")).map { listOf(it.string("kind"), it.string("quote"), it.string("image")).filter(String::isNotEmpty).joinToString(" · ") }.toMutableList()
    record.optJSONObject("dropped_quotes")?.let { quotes -> quotes.keys().forEach { dropped += "$it: ${quotes.optString(it)}" } }
    if (dropped.isNotEmpty()) rows += strings.readingDropped to dropped.joinToString("\n")
    arrayItems(record.optJSONArray("rounds")).forEachIndexed { index, round ->
        val stage = if (round.string("stage") == "review_description_ddl") strings.roundReviewed else strings.roundWritten
        val again = if (round.optBoolean("asked_again")) strings.roundAskedAgain else ""
        val figures = arrayItems(round.optJSONArray("figures")).joinToString(", ") { "${it.string("who")}: ${it.string("what")}" }
        rows += "${strings.roundLabel} ${index + 1}" to "$stage$again · ${strings.roundInstructions} ${round.optInt("instructions")} · ${strings.roundProblems} ${round.optInt("problems")}${if (figures.isEmpty()) "" else " · $figures"}"
    }
    record.optJSONObject("composition")?.let { composition ->
        rows += strings.flowComposition to listOf(composition.string("state"), composition.string("fallback")).filter(String::isNotEmpty).joinToString(" · ")
        composition.optJSONObject("answer")?.let { answer ->
            listOf("thesis" to strings.compositionThesis, "form" to strings.compositionForm, "main_law" to strings.compositionMainLaw, "reason" to strings.compositionReason).forEach { (key, name) -> answer.string(key).takeIf(String::isNotEmpty)?.let { rows += name to it } }
            val things = arrayItems(answer.optJSONArray("things")).map { listOf(it.string("thing"), it.string("what"), it.string("role"), it.string("kind"), it.string("quote")).filter(String::isNotEmpty).joinToString(" · ") }
            if (things.isNotEmpty()) rows += strings.compositionThings to things.joinToString("\n")
        }
        val measures = arrayItems(composition.optJSONArray("measures"))
        measures.lastOrNull()?.let { measure ->
            val results = arrayItems(measure.optJSONArray("after")).map { listOf(it.string("law"), it.string("thing"), it.string("state"), it.string("detail")).filter(String::isNotEmpty).joinToString(" · ") }
            if (results.isNotEmpty()) rows += strings.compositionMeasure to results.joinToString("\n")
        }
        composition.optJSONObject("colors")?.let { colors ->
            rows += strings.flowColors to listOf(colors.string("state"), colors.string("fallback"), colors.string("main_law")).filter(String::isNotEmpty).joinToString(" · ")
            val changes = arrayItems(colors.optJSONArray("changes")).map { listOf(it.string("line"), it.string("how"), it.string("before"), it.optJSONArray("after")?.toString().orEmpty()).filter(String::isNotEmpty).joinToString(" · ") }
            if (changes.isNotEmpty()) rows += strings.compositionChangedLines to changes.joinToString("\n")
        }
    }
    return rows
}

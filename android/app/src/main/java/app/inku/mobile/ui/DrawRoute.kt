package app.inku.mobile.ui

import org.json.JSONObject

enum class DrawRoute { ReadAndDraw, Stages }

internal fun drawRouteOf(metadata: JSONObject): DrawRoute = when (metadata.optString("route")) {
    "read_and_draw" -> DrawRoute.ReadAndDraw
    "stages" -> DrawRoute.Stages
    else -> if (metadata.optJSONObject("description_ddl") != null) DrawRoute.ReadAndDraw else DrawRoute.Stages
}

internal fun compositionModeOf(metadata: JSONObject): Boolean =
    metadata.optJSONObject("description_ddl")?.optJSONObject("composition") != null

internal fun drawFlow(route: DrawRoute, sketch: Boolean, composition: Boolean, japanese: Boolean): String {
    fun word(ja: String, en: String) = if (japanese) ja else en
    val steps = mutableListOf(word("記述", "Description"))
    if (sketch) steps += word("写生", "Sketch")
    if (route == DrawRoute.Stages) {
        steps += listOf(word("型を埋める", "Fill the plan"), word("構図と法則", "Composition and laws"), word("配色", "Colors"))
    } else {
        if (composition) steps += word("構図と法則", "Composition and laws")
        steps += listOf(word("言葉で書く", "Write in words"), word("見て直す", "Look and correct"))
        if (composition) steps += word("配色", "Colors")
    }
    steps += word("画", "Picture")
    return steps.joinToString(" → ")
}

internal fun descriptionDetails(record: JSONObject, japanese: Boolean): List<Pair<String, String>> {
    fun label(ja: String, en: String) = if (japanese) ja else en
    fun JSONObject.string(key: String) = optString(key).takeUnless { it.isBlank() || it == "null" }.orEmpty()
    fun arrayItems(array: org.json.JSONArray?): List<JSONObject> =
        if (array == null) emptyList() else (0 until array.length()).mapNotNull { array.optJSONObject(it) }
    val rows = mutableListOf<Pair<String, String>>()
    val reading = when (record.string("reading_state")) {
        "read" -> label("記述を読み、その読みで書いた", "Written from a reading of the description")
        "supplied" -> label("作者が直した読みで書いた", "Written from the author's edited reading")
        "fallback" -> label("読みが届かず、記述だけから書いた", "Written from the description after the reading failed")
        else -> label("読まずに記述だけから書いた", "Written from the description alone")
    }
    rows += label("読み", "Reading") to reading
    record.string("reading_text").takeIf(String::isNotEmpty)?.let { rows += label("読みの文", "Reading text") to it }
    val dropped = arrayItems(record.optJSONArray("dropped_items")).map { listOf(it.string("kind"), it.string("quote"), it.string("image")).filter(String::isNotEmpty).joinToString(" · ") }.toMutableList()
    record.optJSONObject("dropped_quotes")?.let { quotes -> quotes.keys().forEach { dropped += "$it: ${quotes.optString(it)}" } }
    if (dropped.isNotEmpty()) rows += label("落とした読み", "Dropped reading") to dropped.joinToString("\n")
    arrayItems(record.optJSONArray("rounds")).forEachIndexed { index, round ->
        val stage = if (round.string("stage") == "review_description_ddl") label("見直した", "Reviewed") else label("書いた", "Written")
        val again = if (round.optBoolean("asked_again")) label("・聞き直し", " · asked again") else ""
        val figures = arrayItems(round.optJSONArray("figures")).joinToString(", ") { "${it.string("who")}: ${it.string("what")}" }
        rows += "${label("回", "Round")} ${index + 1}" to "$stage$again · ${label("指示", "instructions")} ${round.optInt("instructions")} · ${label("問題", "problems")} ${round.optInt("problems")}${if (figures.isEmpty()) "" else " · $figures"}"
    }
    record.optJSONObject("composition")?.let { composition ->
        rows += label("構図と法則", "Composition and laws") to listOf(composition.string("state"), composition.string("fallback")).filter(String::isNotEmpty).joinToString(" · ")
        composition.optJSONObject("answer")?.let { answer ->
            listOf("thesis" to label("命題", "Thesis"), "form" to label("画の型", "Form"), "main_law" to label("主の法則", "Main law"), "reason" to label("理由", "Reason")).forEach { (key, name) -> answer.string(key).takeIf(String::isNotEmpty)?.let { rows += name to it } }
            val things = arrayItems(answer.optJSONArray("things")).map { listOf(it.string("thing"), it.string("what"), it.string("role"), it.string("kind"), it.string("quote")).filter(String::isNotEmpty).joinToString(" · ") }
            if (things.isNotEmpty()) rows += label("物", "Things") to things.joinToString("\n")
        }
        val measures = arrayItems(composition.optJSONArray("measures"))
        measures.lastOrNull()?.let { measure ->
            val results = arrayItems(measure.optJSONArray("after")).map { listOf(it.string("law"), it.string("thing"), it.string("state"), it.string("detail")).filter(String::isNotEmpty).joinToString(" · ") }
            if (results.isNotEmpty()) rows += label("最後の測り", "Last measure") to results.joinToString("\n")
        }
        composition.optJSONObject("colors")?.let { colors ->
            rows += label("配色", "Colors") to listOf(colors.string("state"), colors.string("fallback"), colors.string("main_law")).filter(String::isNotEmpty).joinToString(" · ")
            val changes = arrayItems(colors.optJSONArray("changes")).map { listOf(it.string("line"), it.string("how"), it.string("before"), it.optJSONArray("after")?.toString().orEmpty()).filter(String::isNotEmpty).joinToString(" · ") }
            if (changes.isNotEmpty()) rows += label("変えた行", "Changed lines") to changes.joinToString("\n")
        }
    }
    return rows
}

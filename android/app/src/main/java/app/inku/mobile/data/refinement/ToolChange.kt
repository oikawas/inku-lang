package app.inku.mobile.data.refinement

import org.json.JSONArray
import org.json.JSONObject
import kotlin.random.Random

enum class ToolChangeMode(val id: String) {
    Uniform("uniform"), PerSentence("per_sentence");
}

data class TouchTool(val value: String, val ja: String, val en: String) {
    fun label(japanese: Boolean): String = if (japanese) ja else en
}

data class ToolChangeSource(
    val source: String,
    val scoreJson: String,
    val configJson: String,
    val tools: List<TouchTool>,
    val drawn: Map<Int, String>,
)

data class ToolChange(val index: Int, val from: String, val to: String)

data class ToolChangeOption(
    val source: ToolChangeSource,
    val mode: ToolChangeMode,
    val tools: Map<Int, String>,
) {
    val changes: List<ToolChange> = tools.mapNotNull { (index, tool) ->
        source.drawn[index]?.takeIf { it != tool }?.let { ToolChange(index, it, tool) }
    }
    fun metadata(): Map<String, Any?> = mapOf(
        "tool_mode" to mode.id,
        "tools" to tools.mapKeys { it.key.toString() },
        "changes" to changes.map { mapOf("index" to it.index, "from" to it.from, "to" to it.to) },
    )
}

/** Match Server's tool_variants: source owners alone may change, never plugin owners. */
object ToolChangePlanner {
    const val DEFAULT_TOOL = "pen"

    fun read(source: String, scoreJson: String, configJson: String, response: JSONObject): ToolChangeSource {
        require(response.optString("schema") == "inku.touch-change.v1") { "retouch schema mismatch" }
        val tools = response.getJSONArray("tools").let { values ->
            (0 until values.length()).map { index ->
                val tool = values.getJSONObject(index)
                TouchTool(tool.getString("value"), tool.getString("ja"), tool.getString("en"))
            }
        }
        val sentences = if (response.optString("outcome") == "read") response.getJSONArray("sentences") else JSONArray()
        val indices = (0 until sentences.length()).map { sentences.getJSONObject(it).getInt("index") }.toSet()
        val known = tools.map { it.value }.toSet()
        val drawn = linkedMapOf<Int, String>()
        val instructions = JSONObject(scoreJson).optJSONArray("instructions") ?: JSONArray()
        for (position in 0 until instructions.length()) {
            val instruction = instructions.optJSONObject(position) ?: continue
            val index = ownerIndex(instruction) ?: continue
            if (index in indices && index !in drawn) {
                drawn[index] = instruction.optString("weight").takeIf { it in known } ?: DEFAULT_TOOL
            }
        }
        return ToolChangeSource(source, scoreJson, configJson, tools, indices.sorted().associateWith { drawn[it] ?: DEFAULT_TOOL })
    }

    fun options(source: ToolChangeSource, mode: ToolChangeMode, random: Random = Random.Default): List<ToolChangeOption> {
        if (source.drawn.isEmpty()) return emptyList()
        val values = source.tools.map { it.value }
        if (mode == ToolChangeMode.Uniform) {
            return values.filter { tool -> source.drawn.values.any { it != tool } }
                .shuffled(random).take(4).map { tool -> ToolChangeOption(source, mode, source.drawn.keys.associateWith { tool }) }
        }
        val chosen = mutableListOf<Map<Int, String>>()
        repeat(32) {
            if (chosen.size < 4) {
                val tools = source.drawn.mapValues { (_, from) -> values.filter { it != from }.random(random) }
                if (tools !in chosen) chosen += tools
            }
        }
        return chosen.map { ToolChangeOption(source, mode, it) }
    }

    fun scoreWithTools(scoreJson: String, tools: Map<Int, String>): String {
        val score = JSONObject(scoreJson)
        val instructions = score.optJSONArray("instructions") ?: JSONArray()
        for (position in 0 until instructions.length()) {
            val instruction = instructions.optJSONObject(position) ?: continue
            tools[ownerIndex(instruction)]?.let { instruction.put("weight", it) }
        }
        return score.toString()
    }

    private fun ownerIndex(instruction: JSONObject): Int? {
        val owner = instruction.optJSONObject("arrangement")?.optJSONObject("resolved")?.optJSONObject("owner") ?: return null
        if (owner.optString("kind") != "source_instruction") return null
        val index = owner.opt("instruction_index")
        return (index as? Int)?.takeIf { it >= 0 }
    }
}

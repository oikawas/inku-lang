package app.inku.mobile.pipeline

import app.inku.mobile.render.ServerRendererGeometry
import org.json.JSONArray
import org.json.JSONObject

/** Deterministic DDL repairs shared by the local Stage 2 paths. */
internal object DdlEngineRepairs {
    internal val markSurfaceWords: Set<String> = setOf("grain", "bleed", "wash")

    fun withSurfaceOnAClosedShape(instructions: List<JSONObject>): List<JSONObject> {
        val repaired = instructions.map(::copy).toMutableList()
        for (index in repaired.indices) {
            val instruction = repaired[index]
            val surface = instruction.optJSONObject("surface") ?: continue
            val texture = surface.optString("texture", "none")
            if (texture == "none" || instruction.optString("primitive") in ServerRendererGeometry.CLOSED_SHAPES) {
                continue
            }
            if (texture in markSurfaceWords) continue

            instruction.remove("surface")
            val target = (index - 1 downTo 0).firstOrNull {
                repaired[it].optString("primitive") in ServerRendererGeometry.CLOSED_SHAPES
            } ?: continue
            val held = repaired[target].optJSONObject("surface")
            if (held != null && held.optString("texture", "none") != "none") continue
            repaired[target].put("surface", copy(surface))
        }
        return repaired
    }

    fun withoutUnrequestedColorCycle(instructions: List<JSONObject>, ddl: String): List<JSONObject> {
        val marksOnly = ServerDdlText.splitClauses(ddl)
            .filterNot { it.startsWith("背景") || it.lowercase().startsWith("background") }
            .joinToString("。")
        if (marksOnly.isBlank() || hasPolychromePhrase(ddl)) return instructions
        val requested = ServerScoreRepairFactory.requestedColors(marksOnly).toSet()
        if (requested.size != 1) return instructions
        val named = requested.single()

        return instructions.map { instruction ->
            val arrangement = instruction.optJSONObject("arrangement")
            val cycle = arrangement?.optJSONArray("color_cycle")?.strings().orEmpty()
            if (cycle.size < 2 || named !in cycle || cycle.none { it != named }) return@map instruction
            copy(instruction).also { result ->
                val resultArrangement = copy(result.getJSONObject("arrangement"))
                    .put("color_cycle", JSONArray(listOf(named)))
                result.put("arrangement", resultArrangement)
                result.put("color", named)
                appendNote(result, "color_cycle reduced to $named alone as the DDL names it alone")
            }
        }
    }

    fun withStatedCountFidelity(
        instructions: List<JSONObject>,
        ddl: String,
        background: String,
        lang: String?,
        maxExpandedPrimitives: Int = 400,
    ): List<JSONObject> {
        if (ddl.isBlank() || instructions.isEmpty()) return instructions
        val everyStated = ServerScoreCounts.explicitCountsFromDdl(ddl, lang)
        val stated = everyStated.filter { it in 1 until ServerScoreCounts.LITERAL_COUNT_THRESHOLD }.toSet()
        if (stated.isEmpty()) return instructions

        val repaired = instructions.toMutableList()
        for (clause in ServerScoreRepairFactory.splitDrawableClauses(ddl)) {
            val values = ServerScoreCounts.explicitCountsFromDdl(clause, lang).filter { it in stated }.toSet()
            if (values.size != 1) continue
            val value = values.single()
            if (repaired.any { ServerScoreCounts.countFollowsDdlRequest(arrangementCount(it), setOf(value)) }) {
                continue
            }
            val target = groupTheClauseNames(repaired, clause, background) ?: continue
            val candidate = withStatedCount(repaired[target], value)
            val proposed = repaired.toMutableList().also { it[target] = candidate }
            if (compositeMarkCounts(proposed).sum() > maxExpandedPrimitives) continue
            repaired[target] = candidate
        }
        return repaired
    }

    fun withCompositeDensityBudget(
        instructions: List<JSONObject>,
        maxExpandedPerInstruction: Int = 240,
        maxExpandedPrimitives: Int = 400,
    ): List<JSONObject> {
        val adjusted = instructions.map(::copy).toMutableList()
        var index = 0
        while (index < adjusted.size) {
            val arrangement = adjusted[index].optJSONObject("arrangement")
            val groupSize = validGroupSize(adjusted, index)
            if (arrangement != null && groupSize > 1) {
                val count = arrangementCount(adjusted[index])
                if (count * groupSize > maxExpandedPerInstruction) {
                    adjusted[index] = withArrangementCount(
                        adjusted[index],
                        maxOf(1, maxExpandedPerInstruction / groupSize),
                        "composite density capped without splitting its unit",
                    )
                }
                index += groupSize
            } else {
                index += 1
            }
        }

        val counts = compositeMarkCounts(adjusted)
        if (counts.sum() <= maxExpandedPrimitives) return adjusted
        var ceiling = 1
        for (candidate in 1..counts.max()) {
            if (counts.sumOf { minOf(it, candidate) } <= maxExpandedPrimitives) {
                ceiling = candidate
            } else {
                break
            }
        }
        for (position in adjusted.indices) {
            val arrangement = adjusted[position].optJSONObject("arrangement") ?: continue
            if (counts[position] <= ceiling) continue
            val groupSize = validGroupSize(adjusted, position)
            val countCeiling = if (groupSize > 1) maxOf(1, ceiling / groupSize) else ceiling
            adjusted[position] = withArrangementCount(
                adjusted[position],
                countCeiling,
                "hard ceiling $maxExpandedPrimitives applied to the whole work",
            )
        }
        return adjusted
    }

    fun compositeMarkCounts(instructions: List<JSONObject>): List<Int> {
        val counts = MutableList(instructions.size) { 0 }
        var index = 0
        while (index < instructions.size) {
            val instruction = instructions[index]
            val groupSize = validGroupSize(instructions, index)
            counts[index] = markCount(instruction) * groupSize
            index += groupSize
        }
        return counts
    }

    private fun groupTheClauseNames(
        instructions: List<JSONObject>,
        clause: String,
        background: String,
    ): Int? {
        val primitive = ServerScoreRepairFactory.primitiveFromClause(clause) ?: return null
        val color = ServerScoreRepairFactory.colorFromClause(clause, background)
        val weight = ServerScoreSemantics.detectWeightKey(clause)
        val candidates = instructions.indices.filter { index ->
            STATED_COUNT_NOTE !in instructions[index].optString("note", "")
        }
        val triple = candidates.filter { index ->
            val instruction = instructions[index]
            instruction.optString("primitive", "line") == primitive &&
                instruction.optString("color", "black") == color &&
                instruction.optString("weight", "pen") == weight
        }
        if (triple.isNotEmpty()) return triple.singleOrNull()
        return candidates.filter { instructions[it].optString("primitive", "line") == primitive }.singleOrNull()
    }

    private fun withStatedCount(instruction: JSONObject, count: Int): JSONObject {
        val result = copy(instruction)
        val arrangement = result.optJSONObject("arrangement")?.let(::copy) ?: JSONObject()
        if (arrangement.length() == 0 && count == 1) return result
        arrangement.put("count", count)
        arrangement.put("layout", arrangement.optString("layout", "scatter").ifBlank { "scatter" })
        result.put("arrangement", arrangement)
        appendNote(result, STATED_COUNT_NOTE)
        return result
    }

    private fun withArrangementCount(instruction: JSONObject, count: Int, note: String): JSONObject {
        val result = copy(instruction)
        val arrangement = result.optJSONObject("arrangement")?.let(::copy) ?: return result
        if (arrangement.optInt("count", 1) == count) return result
        arrangement.put("count", maxOf(1, count))
        result.put("arrangement", arrangement)
        appendNote(result, note)
        return result
    }

    private fun arrangementCount(instruction: JSONObject): Int =
        maxOf(1, instruction.optJSONObject("arrangement")?.optInt("count", 1) ?: 1)

    private fun markCount(instruction: JSONObject): Int {
        val arrangement = instruction.optJSONObject("arrangement") ?: return 1
        if (arrangement.optString("layout") == "grid" && arrangement.has("rows") && arrangement.has("cols")) {
            return maxOf(1, arrangement.optInt("rows", 1) * arrangement.optInt("cols", 1))
        }
        return arrangementCount(instruction)
    }

    private fun validGroupSize(instructions: List<JSONObject>, index: Int): Int {
        val claimed = maxOf(1, instructions[index].optJSONObject("arrangement")?.optInt("group_size", 1) ?: 1)
        return if (index + claimed <= instructions.size) claimed else 1
    }

    private fun hasPolychromePhrase(text: String): Boolean {
        val lower = text.lowercase()
        return listOf("色とりどり", "多色", "colorful", "multi-color", "multicolor", "polychrome")
            .any { it in text || it in lower }
    }

    private fun appendNote(instruction: JSONObject, note: String) {
        val clauses = instruction.optString("note", "").split(";").map(String::trim).filter(String::isNotEmpty)
        if (note in clauses) return
        instruction.put("note", (clauses + note).joinToString("; "))
    }

    private fun JSONArray.strings(): List<String> = (0 until length()).map { optString(it) }

    private fun copy(source: JSONObject): JSONObject = JSONObject(source.toString())

    private const val STATED_COUNT_NOTE = "stated count from the clause honoured"
}

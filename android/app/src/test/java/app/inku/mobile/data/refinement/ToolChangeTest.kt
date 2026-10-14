package app.inku.mobile.data.refinement

import app.inku.mobile.data.lineage.LineagePlanner
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import kotlin.random.Random

class ToolChangeTest {
    @Test
    fun optionsChangeOnlyEligibleSourceOwnersAndKeepTheParentScore() {
        val score = """{"canvas":{"ground":{"material":"washi"}},"instructions":[
          {"weight":"pen","color":"red","arrangement":{"resolved":{"owner":{"kind":"source_instruction","instruction_index":0},"bounds":[1,2,3,4]}}},
          {"weight":"pen","color":"blue","arrangement":{"resolved":{"owner":{"kind":"source_instruction","instruction_index":0},"bounds":[5,6,7,8]}}},
          {"weight":"pencil","arrangement":{"resolved":{"owner":{"kind":"source_instruction","instruction_index":2}}}},
          {"weight":"pen","arrangement":{"resolved":{"owner":{"kind":"plugin","instruction_index":0}}}},
          {"weight":"pen","arrangement":{"resolved":{"owner":{"kind":"source_instruction","instruction_index":"0"}}}}
        ]}"""
        val answer = JSONObject("""{"schema":"inku.touch-change.v1","outcome":"read","sentences":[{"index":0},{"index":2}],
          "tools":[{"value":"pen","ja":"ペン","en":"pen"},{"value":"pencil","ja":"鉛筆","en":"pencil"},
          {"value":"chalk","ja":"チョーク","en":"chalk"},{"value":"crayon","ja":"クレヨン","en":"crayon"},
          {"value":"brush_thin","ja":"細筆","en":"fine brush"},{"value":"brush_thick","ja":"太筆","en":"thick brush"}]}""")
        val parent = ToolChangePlanner.read("parent instructions", score, "{}", answer)
        assertEquals(mapOf(0 to "pen", 2 to "pencil"), parent.drawn)
        val uniform = ToolChangePlanner.options(parent.copy(drawn = mapOf(0 to "pen", 2 to "pen")), ToolChangeMode.Uniform, Random(7))
        assertEquals(4, uniform.size)
        assertEquals(4, uniform.map { it.tools.values.first() }.toSet().size)
        assertTrue(uniform.none { "pen" in it.tools.values })
        assertTrue(uniform.all { it.tools.values.toSet().size == 1 })
        val individual = ToolChangePlanner.options(parent, ToolChangeMode.PerSentence, Random(9))
        assertEquals(4, individual.size)
        assertTrue(individual.all { option -> option.tools.all { (index, tool) -> tool != parent.drawn[index] } })
        assertEquals("per_sentence", individual.first().metadata()["tool_mode"])
        val changed = JSONObject(ToolChangePlanner.scoreWithTools(score, mapOf(0 to "chalk")))
        val before = JSONObject(score)
        assertEquals("pen", before.getJSONArray("instructions").getJSONObject(0).getString("weight"))
        val commands = changed.getJSONArray("instructions")
        assertEquals("chalk", commands.getJSONObject(0).getString("weight"))
        assertEquals("chalk", commands.getJSONObject(1).getString("weight"))
        for (index in 2..4) assertEquals(
            LineagePlanner.canonicalJson(before.getJSONArray("instructions").getJSONObject(index)),
            LineagePlanner.canonicalJson(commands.getJSONObject(index)),
        )
        assertEquals(before.getJSONObject("canvas").toString(), changed.getJSONObject("canvas").toString())
        for (index in 0..1) {
            val original = before.getJSONArray("instructions").getJSONObject(index)
            val actual = commands.getJSONObject(index)
            original.remove("weight"); actual.remove("weight")
            assertEquals(LineagePlanner.canonicalJson(original), LineagePlanner.canonicalJson(actual))
        }
        assertTrue(ToolChangePlanner.options(parent.copy(drawn = emptyMap()), ToolChangeMode.Uniform).isEmpty())
    }
}

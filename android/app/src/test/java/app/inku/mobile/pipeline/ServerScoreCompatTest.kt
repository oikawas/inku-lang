package app.inku.mobile.pipeline

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class ServerScoreCompatTest {
    @Test
    fun legacyHairMigratesToSilverpoint() {
        assertEquals("silverpoint", ServerScoreCompat.migrateWeight("hair"))
        assertEquals("pencil", ServerScoreCompat.migrateWeight("pencil"))
    }

    @Test
    fun migrationReachesEveryInstructionAndPreservesCurrentWeights() {
        val score = JSONObject(
            """{"instructions":[{"primitive":"line","weight":"hair"},
                {"primitive":"circle","weight":"pencil"},
                {"primitive":"square","weight":"hair"}]}""",
        )
        ServerScoreCompat.migrateScore(score)
        val instructions = score.getJSONArray("instructions")
        val weights = (0 until instructions.length()).map {
            instructions.getJSONObject(it).getString("weight")
        }

        assertEquals(listOf("silverpoint", "pencil", "silverpoint"), weights)
    }
}

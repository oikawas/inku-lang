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

    @Test
    fun transformGroupsSurviveScoreMigrationForSaveAndReplay() {
        val score = JSONObject(
            """{"version":"0.4.0","instructions":[{"primitive":"line"},{"primitive":"line"}],
                "transform_groups":[{"start":0,"end":2,"rotation_degrees":90.0,
                "fixed_position_indices":[1]}]}""",
        )

        val migrated = ServerScoreCompat.migrateScore(score)

        val group = migrated.getJSONArray("transform_groups").getJSONObject(0)
        assertEquals(0, group.getInt("start"))
        assertEquals(2, group.getInt("end"))
        assertEquals(90.0, group.getDouble("rotation_degrees"), 0.0)
        assertEquals(1, group.getJSONArray("fixed_position_indices").getInt(0))
    }
}

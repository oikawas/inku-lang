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
            """{"version":"0.5.0","instructions":[{"primitive":"line"},{"primitive":"line"}],
                "transform_groups":[{"start":0,"end":2,"rotation_degrees":90.0,
                "scale_x":-1.5,"scale_y":0.0,"translate_x":0.125,"translate_y":-0.25,
                "fixed_position_indices":[1]}]}""",
        )

        val migrated = ServerScoreCompat.migrateScore(score)

        val group = migrated.getJSONArray("transform_groups").getJSONObject(0)
        assertEquals(0, group.getInt("start"))
        assertEquals(2, group.getInt("end"))
        assertEquals(90.0, group.getDouble("rotation_degrees"), 0.0)
        assertEquals(-1.5, group.getDouble("scale_x"), 0.0)
        assertEquals(0.0, group.getDouble("scale_y"), 0.0)
        assertEquals(0.125, group.getDouble("translate_x"), 0.0)
        assertEquals(-0.25, group.getDouble("translate_y"), 0.0)
        assertEquals(1, group.getJSONArray("fixed_position_indices").getInt(0))
    }

    @Test
    fun anchorsAndAnchorRelationTargetsSurviveScoreMigrationForSaveAndReplay() {
        val score = JSONObject(
            """{"version":"0.6.0","instructions":[{"primitive":"line","relation":
                {"type":"connected","target_anchor_index":0,"position_authority":"named_movable"}}],
                "anchors":[{"at":{"region":[0.5,0.5,0.5,0.5]}}],
                "transform_groups":[{"start":0,"end":1,"rotation_degrees":15.0,
                "anchor_indices":[0]}]}""",
        )

        val migrated = ServerScoreCompat.migrateScore(score)

        assertEquals(0, migrated.getJSONArray("instructions").getJSONObject(0)
            .getJSONObject("relation").getInt("target_anchor_index"))
        assertEquals(0.5, migrated.getJSONArray("anchors").getJSONObject(0)
            .getJSONObject("at").getJSONArray("region").getDouble(0), 0.0)
        assertEquals(0, migrated.getJSONArray("transform_groups").getJSONObject(0)
            .getJSONArray("anchor_indices").getInt(0))
    }
}

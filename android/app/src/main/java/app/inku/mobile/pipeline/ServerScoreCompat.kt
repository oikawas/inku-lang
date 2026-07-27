package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject

/**
 * Names that saved Scores still carry and that the current vocabulary has moved on from.
 *
 * The server does this in `Instruction`'s `field_validator(mode="before")`, so every Score
 * it constructs is migrated, whether it came from the LLM or from the database. The port
 * has no such single construction point: Scores enter through the coercer on the pipeline
 * side and straight out of the on-device database on the replay side. Both call in here.
 *
 * Replacing, not dropping, is the whole point. Dropping an unknown weight falls back to
 * the default `pen`, which takes the tool away from the saved work: `silverpoint` is 0.5px
 * and `pen` is 2.0px, four times as wide.
 */
internal object ServerScoreCompat {

    /** hair was renamed to silverpoint in v2.7.9. Values are unchanged; only the name moved. */
    private val RENAMED_WEIGHTS = mapOf("hair" to "silverpoint")

    fun migrateWeight(weight: String): String = RENAMED_WEIGHTS[weight] ?: weight

    /** Rewrite retired names in one instruction, in place. Returns the same object. */
    fun migrateInstruction(instruction: JSONObject): JSONObject {
        val weight = instruction.optString("weight", "")
        if (weight.isNotEmpty()) {
            val migrated = migrateWeight(weight)
            if (migrated != weight) instruction.put("weight", migrated)
        }
        return instruction
    }

    /** Rewrite retired names in every instruction of a Score, in place. Returns the same object. */
    fun migrateScore(score: JSONObject): JSONObject {
        val instructions = score.optJSONArray("instructions") ?: JSONArray()
        for (i in 0 until instructions.length()) {
            instructions.optJSONObject(i)?.let { migrateInstruction(it) }
        }
        return score
    }
}

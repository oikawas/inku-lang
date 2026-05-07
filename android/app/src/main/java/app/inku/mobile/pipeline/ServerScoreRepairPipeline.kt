package app.inku.mobile.pipeline

import org.json.JSONObject

internal object ServerScoreRepairPipeline {
    data class Hooks(
        val dedupeInstructions: (List<JSONObject>) -> List<JSONObject>,
        val withDdlCoverage: (List<JSONObject>, String, String) -> List<JSONObject>,
        val withColorDelivery: (List<JSONObject>, String, String) -> List<JSONObject>,
        val withShapeDelivery: (List<JSONObject>, String, String) -> List<JSONObject>,
        val withComplexMotifRepair: (List<JSONObject>, String, String) -> List<JSONObject>,
        val withCompositionDiversity: (List<JSONObject>, String, String) -> List<JSONObject>,
        val withContextEnergy: (List<JSONObject>, String, String) -> List<JSONObject>,
        val withMotionEnergy: (List<JSONObject>, String) -> List<JSONObject>,
        val withPresenceAuxiliaryShapeRepair: (List<JSONObject>, JSONObject?) -> List<JSONObject>,
        val withContextDensityGovernor: (List<JSONObject>, String, String) -> List<JSONObject>,
        val withStructuralDuplicateRepair: (List<JSONObject>) -> List<JSONObject>,
        val withDensityBudget: (List<JSONObject>) -> List<JSONObject>,
    )

    fun repair(
        instructions: List<JSONObject>,
        ddl: String,
        background: String,
        presence: JSONObject?,
        hooks: Hooks,
    ): List<JSONObject> {
        return hooks.withDensityBudget(
            hooks.withStructuralDuplicateRepair(
                hooks.withContextDensityGovernor(
                    hooks.withPresenceAuxiliaryShapeRepair(
                        hooks.withMotionEnergy(
                            hooks.withContextEnergy(
                                hooks.withCompositionDiversity(
                                    hooks.withComplexMotifRepair(
                                        hooks.withShapeDelivery(
                                            hooks.withColorDelivery(
                                                hooks.withDdlCoverage(
                                                    hooks.dedupeInstructions(instructions),
                                                    ddl,
                                                    background,
                                                ),
                                                ddl,
                                                background,
                                            ),
                                            ddl,
                                            background,
                                        ),
                                        ddl,
                                        background,
                                    ),
                                    ddl,
                                    background,
                                ),
                                ddl,
                                background,
                            ),
                            ddl,
                        ),
                        presence,
                    ),
                    ddl,
                    background,
                ),
            ),
        )
    }
}

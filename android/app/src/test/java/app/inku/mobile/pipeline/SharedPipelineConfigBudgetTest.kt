package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The resource budget and the macro catalog request a new work is compiled
 * under: the server's defaults (`pipeline_defaults.py`), with no installed
 * canonical or legacy macro besides the imported ones.
 *
 * Pinned as the bytes the builder produced while these were still request
 * fields that every caller left at their defaults, so removing the fields is
 * shown to change nothing that reaches the core.
 */
class SharedPipelineConfigBudgetTest {

    private class RecordingBinding : SharedPipelineBinding {
        val macroInputs = mutableListOf<String>()

        override fun versionReport() = """{"binding_version":"1.1.0","protocol_version":"1.0.0"}"""
        override fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray = error("not used")
        override fun canvasRegistry() =
            """{"digest":"registry-digest","registry":{"schema":"inku.canvas-format-registry.v1","formats":[{"id":"square","width_units":1,"height_units":1}]}}"""
        override fun resolvePalette(inputBytes: ByteArray) = "{}".encodeToByteArray()
        override fun resolveMacroCatalog(inputBytes: ByteArray): ByteArray {
            macroInputs += inputBytes.toString(Charsets.UTF_8)
            return """{"schema":"inku.macro-catalog-resolution.v1","entries":[],"locks":[],"diagnostics":[]}""".encodeToByteArray()
        }
        override fun renderSaved(inputBytes: ByteArray): ByteArray = error("not used")
    }

    /** A JSON value as sorted maps and lists, so two objects compare by content. */
    private fun tree(value: Any?): Any? = when (value) {
        is JSONObject -> value.keys().asSequence().associateWith { tree(value.get(it)) }.toSortedMap()
        is JSONArray -> (0 until value.length()).map { tree(value.get(it)) }
        else -> value
    }

    @Test
    fun aNewWorkIsCompiledUnderTheServerDefaultBudgetAndMacroRequest() {
        val binding = RecordingBinding()
        val prepared = SharedPipelineConfigBuilder(binding).build(
            SharedPipelineConfigRequest("ja", "square", "default", bundledPluginsEnabled = false),
        )
        val compiler = JSONObject(prepared.configJson).getJSONObject("compiler")
        val policy = compiler.getJSONObject("hard_resource_policy")

        // The identity hashes the budget's canonical text, so it pins every
        // value byte for byte; the objects themselves are compared as JSON.
        assertEquals(
            "host-settings:7f1399413dec8fa789348e9a8424af11e9177878ff8c2d780893ed73bc6bc0f4",
            policy.getString("identity"),
        )
        val budget = JSONObject(
            """{"maximum":{"logical_objects":4096,"template_nodes":128,"anchor_instances":4096,""" +
                """"transform_instances":4096,"placement_instances":64,"fill_instances":64,"primitive_marks":400,""" +
                """"maximum_per_template_primitive_marks":240,"maximum_resolved_count":2000,"object_templates":64}}""",
        )
        assertEquals(tree(budget), tree(policy.getJSONObject("budget")))
        assertEquals(tree(budget), tree(compiler.getJSONObject("operational_resource_budget")))
        assertEquals(
            tree(JSONObject("""{"maximum_entries":64,"bundled_packages":[],"language":"ja","canonical":[],"legacy":[]}""")),
            tree(JSONObject(binding.macroInputs.single())),
        )
    }
}

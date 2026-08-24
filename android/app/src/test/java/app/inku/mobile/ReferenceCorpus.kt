package app.inku.mobile

import app.inku.mobile.data.model.CompatibilityConstants
import java.io.InputStreamReader
import org.json.JSONObject

/**
 * Resolves a reference fixture to the corpus directory that governs it.
 *
 * These files are historical artifacts held by a manifest. While they sat in
 * one flat directory, raising the Server engine rewrote the port's expectations
 * in place. Each Android engine version now keeps its own directory, and a newer
 * Server engine must not rebake it.
 *
 * The port therefore asks for a fixture by bare name and reads the directory for
 * the version it implements. Raising the server engine adds a directory; it does
 * not touch the one this reads. Catching up then means moving
 * [CompatibilityConstants.renderEngineVersion] -- one line, on purpose, in its
 * own contract.
 *
 * A name is resolved by the axis that moves it, and a misfiled name fails loudly:
 * the file exists under exactly one of these three, so getting the axis wrong
 * raises "not found" rather than silently comparing against the wrong version.
 */
object ReferenceCorpus {

    /** The Stage 1.5 expansion version the port implements (`layer_versions.py` on the server). */
    const val ddlEngineVersion = "20"

    /** Fixtures no engine version governs: they are rebaked in place and the port follows them. */
    private val FLAT = setOf(
        "coerce_governors.json",
        "count_preservation.json",
        "lineage_wiring.json",
        "prompts.json",
        "score_schema_contract.json",
    )

    /** The one fixture the DDL engine governs. */
    private const val DDL_ENGINE_FIXTURE = "ddl_expand.json"

    /** The classpath path a bare fixture name resolves to. */
    fun path(name: String): String = when (name) {
        in FLAT -> "/server_reference/$name"
        DDL_ENGINE_FIXTURE -> "/server_reference/ddl-engine-$ddlEngineVersion/$name"
        else -> "/server_reference/render-engine-${CompatibilityConstants.renderEngineVersion}/$name"
    }

    fun text(name: String): String {
        val path = path(name)
        val stream = ReferenceCorpus::class.java.getResourceAsStream(path)
            ?: error("Reference fixture $path not found")
        return InputStreamReader(stream, Charsets.UTF_8).use { it.readText() }
    }

    fun json(name: String): JSONObject = JSONObject(text(name))
}

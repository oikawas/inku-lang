package app.inku.mobile

import java.io.InputStreamReader
import org.json.JSONObject

/**
 * Resolves a reference fixture to the corpus directory that governs it.
 *
 * Android keeps only flat compatibility fixtures. DDL and render parity are owned
 * by the shared Rust core corpus rather than copied into the application tests.
 */
object ReferenceCorpus {

    /** Fixtures no engine version governs: they are rebaked in place and the port follows them. */
    private val FLAT = setOf(
        "coerce_governors.json",
        "count_preservation.json",
        "lineage_wiring.json",
        "prompts.json",
        "score_schema_contract.json",
    )

    /** The classpath path a bare fixture name resolves to. */
    fun path(name: String): String = when (name) {
        in FLAT -> "/server_reference/$name"
        else -> error("Unknown Android reference fixture: $name")
    }

    fun text(name: String): String {
        val path = path(name)
        val stream = ReferenceCorpus::class.java.getResourceAsStream(path)
            ?: error("Reference fixture $path not found")
        return InputStreamReader(stream, Charsets.UTF_8).use { it.readText() }
    }

    fun json(name: String): JSONObject = JSONObject(text(name))
}

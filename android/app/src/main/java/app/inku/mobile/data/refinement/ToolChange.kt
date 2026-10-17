package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.SharedPipelineBinding
import java.security.SecureRandom
import org.json.JSONObject

enum class ToolChangeMode(val id: String) {
    Uniform("uniform"), PerSentence("per_sentence");
}

data class TouchTool(val value: String, val ja: String, val en: String) {
    fun label(japanese: Boolean): String = if (japanese) ja else en
}

/** Saved inputs plus the core's plan projection; no host rule interprets the Score. */
data class ToolChangeSource(
    val source: String,
    val scoreJson: String,
    val configJson: String,
    val tools: List<TouchTool> = emptyList(),
    val drawn: Map<Int, String> = emptyMap(),
    internal val binding: SharedPipelineBinding = NativePipelineBridge,
)

data class ToolChange(val index: Int, val from: String, val to: String)

data class ToolChangeOption(
    val source: ToolChangeSource,
    val mode: ToolChangeMode,
    val tools: Map<Int, String>,
    val changes: List<ToolChange> = emptyList(),
    val ddl: String = source.source,
) {
    /** Saving reads the core's metadata against the current saved inputs. */
    fun metadata(): Map<String, Any?> = ToolChangePlanner.render(source, mode, tools).derivationMetadata
}

/** The core owns eligible owners, tool labels, candidates, retouch, and metadata. */
object ToolChangePlanner {
    private val secureRandom = SecureRandom()

    fun source(source: String, scoreJson: String, configJson: String,
               binding: SharedPipelineBinding = NativePipelineBridge): ToolChangeSource =
        ToolChangeSource(source, scoreJson, configJson, binding = binding)

    fun options(source: ToolChangeSource, mode: ToolChangeMode,
                seed: Long = secureRandom.nextLong()): List<ToolChangeOption> {
        val answer = SharedSavedVariants.call("tool_plan",
            "\"config\":${source.configJson},\"source\":${SharedSavedVariants.q(source.source)}," +
                "\"score\":${source.scoreJson},\"mode\":${SharedSavedVariants.q(mode.id)}," +
                "\"seed\":${java.lang.Long.toUnsignedString(seed)}", source.binding).value
        val tools = answer.getJSONArray("tool_labels").let { labels ->
            (0 until labels.length()).map { index ->
                val label = labels.getJSONObject(index)
                TouchTool(label.getString("value"), label.getString("ja"), label.getString("en"))
            }
        }
        val drawn = answer.getJSONArray("sentences").let { sentences ->
            (0 until sentences.length()).associate { index ->
                val sentence = sentences.getJSONObject(index)
                sentence.getInt("index") to sentence.getString("tool")
            }
        }
        val plannedSource = source.copy(tools = tools, drawn = drawn)
        val entries = answer.getJSONArray("entries")
        return (0 until entries.length()).map { index ->
            val entry = entries.getJSONObject(index)
            val asked = entry.getJSONObject("tools").let { values ->
                values.keys().asSequence().associate { key -> key.toInt() to values.getString(key) }
            }
            val changes = entry.getJSONArray("changes").let { values ->
                (0 until values.length()).map { position ->
                    val change = values.getJSONObject(position)
                    ToolChange(change.getInt("index"), change.getString("from"), change.getString("to"))
                }
            }
            ToolChangeOption(plannedSource, mode, asked, changes, entry.getString("ddl"))
        }
    }

    fun render(source: ToolChangeSource, mode: ToolChangeMode, tools: Map<Int, String>): SavedVariantRender {
        val keyed = JSONObject(tools.mapKeys { it.key.toString() })
        val answer = SharedSavedVariants.call("tool_render",
            "\"config\":${source.configJson},\"source\":${SharedSavedVariants.q(source.source)}," +
                "\"score\":${source.scoreJson},\"mode\":${SharedSavedVariants.q(mode.id)}," +
                "\"tools\":$keyed", source.binding)
        return SavedVariantRender(answer.rawScore(), answer.value.getString("ddl"),
            SharedSavedVariants.metadata(answer.value.getJSONObject("derivation_metadata")))
    }

    fun render(option: ToolChangeOption): SavedVariantRender = render(option.source, option.mode, option.tools)
}

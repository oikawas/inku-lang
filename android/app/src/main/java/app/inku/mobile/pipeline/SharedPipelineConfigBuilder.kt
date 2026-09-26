package app.inku.mobile.pipeline

import app.inku.mobile.data.model.CatalogSelection
import app.inku.mobile.data.model.ColorCatalog
import app.inku.mobile.data.model.ColorCatalogs
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

data class PipelineCanonicalMacro(
    val sourceId: String,
    val definitionJson: String,
    val summary: String,
)

data class PipelineLegacyMacro(
    val sourceId: String,
    val qualifiedName: String,
)

/** One definition carried by an `inku.ddl-export.v1` file, offered to a new work only. */
data class ImportedPluginDefinition(
    val definitionJson: String,
    val summary: String,
)

data class SharedPipelineConfigRequest(
    val resolvedLanguage: String,
    val canvasFormatId: String,
    val catalogSelectionId: String,
    val renderSeed: Long? = null,
    val compositionSeed: Long? = null,
    val variationAmplitude: String? = null,
    val variationSeed: Long? = null,
    val errorPolicy: String = "omit_and_continue",
    val resourceLimits: PipelineResourceLimits = PipelineResourceLimits(),
    val canonicalMacros: List<PipelineCanonicalMacro> = emptyList(),
    val legacyMacros: List<PipelineLegacyMacro> = emptyList(),
    /** False when the author disabled the bundled `Nature.leaves` package. */
    val bundledPluginsEnabled: Boolean = true,
    /** Definitions from an imported DDL export; they win their names for this work. */
    val importedPlugins: List<ImportedPluginDefinition> = emptyList(),
)

data class PipelineResourceLimits(
    val primitiveMarks: Int = 400,
    val maximumPerTemplatePrimitiveMarks: Int = 240,
    val maximumResolvedCount: Int = 2_000,
    val objectTemplates: Int = 64,
)

data class PreparedPipelineConfig(
    val configJson: String,
    val autoCatalog: Boolean,
    val canvasFormatId: String,
    val catalogId: String,
    val renderColorMaps: Map<String, Map<String, String>>,
    val compositionSeed: Long?,
    val errorPolicy: String,
    val macroLocksJson: String,
    val macroDiagnosticsJson: String,
)

data class PipelineHostPolicy(
    val maxInputBytes: Int = 16 * 1024 * 1024,
    val maxSnapshotBytes: Int = 32 * 1024 * 1024,
    val maxOutputBytes: Int = 64 * 1024 * 1024,
    val maximumProviderAttempts: Int = 4,
    val providerAttemptTimeoutMs: Long = 120_000L,
    val providerTotalTimeoutMs: Long = 120_000L,
    val providerRetryDelayMs: Long = 2_000L,
    val maximumEffectSteps: Int = 32,
)

/**
 * Builds host policy around Rust-owned registries, palettes, prompts, and Macro validation.
 * The envelope, macro, prompt and resource limits are the server's defaults
 * (`pipeline_defaults.py`), so a work compiles under the same bounds on both.
 */
class SharedPipelineConfigBuilder(
    private val binding: SharedPipelineBinding,
    val policy: PipelineHostPolicy = PipelineHostPolicy(),
    private val catalogs: List<ColorCatalog> = ColorCatalogs.all,
) {
    fun build(request: SharedPipelineConfigRequest): PreparedPipelineConfig {
        requireCompatibleBinding()
        require(request.resolvedLanguage in setOf("ja", "en")) { "resolved pipeline language required" }
        require(request.errorPolicy in setOf("stop", "omit_and_continue")) { "unknown error policy" }
        if ((request.variationAmplitude == null) != (request.variationSeed == null)) {
            throw PipelineHostException("variation_pair_required")
        }

        val registryReport = JSONObject(binding.canvasRegistry())
        val registry = registryReport.requiredObject("registry")
        val registryId = registry.requiredString("schema")
        val registryDigest = registryReport.requiredString("digest")
        val canvas = registry.requiredArray("formats").objects()
            .firstOrNull { it.requiredString("id") == request.canvasFormatId }
            ?: throw PipelineHostException(
                if (request.canvasFormatId == PIXEL9_HOST_ONLY_FORMAT) {
                    "canvas_compatibility_selection_required"
                } else {
                    "unknown_canvas_format"
                },
            )

        val autoCatalog = request.catalogSelectionId == CatalogSelection.AUTO_ID
        val selectedCatalog = if (autoCatalog) {
            catalogs.firstOrNull { it.id == "default" }
        } else {
            catalogs.firstOrNull { it.id == request.catalogSelectionId }
        } ?: throw PipelineHostException("unknown_color_catalog")

        val resolvedHosts = catalogs.associate { catalog ->
            catalog.id to resolvedHost(
                catalog = catalog,
                canvasFormatId = canvas.requiredString("id"),
                registryId = registryId,
                registryDigest = registryDigest,
                renderSeed = request.renderSeed,
                catalogMode = if (catalog.id == "default") "default" else "explicit",
            )
        }
        val selectedHost = JSONObject(resolvedHosts.getValue(selectedCatalog.id).toString())
        val macroCatalog = resolveMacros(request)
        val entries = macroCatalog.requiredArray("entries")
        val retry = retryPolicy()
        val maximum = resourceMaximum(request.resourceLimits)
        val budgetJson = canonicalBudgetJson(maximum)
        val policyIdentity = "host-settings:" + sha256(budgetJson.encodeToByteArray())
        val compiler = JSONObject()
            .put("host", selectedHost)
            .put("composition_seed", request.compositionSeed.wireUnsignedOrNull())
            .put(
                "macro_expansion_limits",
                JSONObject()
                    .put("max_invocations", "64")
                    .put("max_depth", "16")
                    .put("max_evaluation_steps", "8192")
                    .put("max_nodes_per_invocation", "128")
                    .put("max_total_nodes", "128"),
            )
            .put(
                "stage15_variation",
                if (request.variationAmplitude == null) {
                    JSONObject.NULL
                } else {
                    JSONObject()
                        .put("amplitude", request.variationAmplitude)
                        .put("seed", request.variationSeed.wireUnsignedOrNull())
                },
            )
            .put("error_policy", request.errorPolicy)
            .put(
                "hard_resource_policy",
                JSONObject()
                    .put("identity", policyIdentity)
                    .put("budget", JSONObject(budgetJson)),
            )
            .put("operational_resource_budget", JSONObject(budgetJson))

        val config = JSONObject()
            .put(
                "envelope_limits",
                JSONObject()
                    .put("max_input_bytes", policy.maxInputBytes)
                    .put("max_snapshot_bytes", policy.maxSnapshotBytes)
                    .put("max_output_bytes", policy.maxOutputBytes),
            )
            .put("language", request.resolvedLanguage)
            .put("compiler", compiler)
            .put("definitions", JSONArray().also { output ->
                entries.objects().forEach { output.put(it.requiredObject("definition")) }
            })
            .put("macro_summaries", JSONArray().also { output ->
                entries.objects().forEach { output.put(it.requiredString("summary")) }
            })
            .put(
                "catalogs",
                if (!autoCatalog) {
                    JSONArray()
                } else {
                    JSONArray().also { output ->
                        catalogs.forEach { catalog ->
                            output.put(
                                JSONObject()
                                    .put(
                                        "prompt",
                                        JSONObject()
                                            .put("catalog_id", catalog.id)
                                            .put("label", catalog.name)
                                            .put(
                                                "description",
                                                if (request.resolvedLanguage == "ja") catalog.subJa else catalog.sub,
                                            ),
                                    )
                                    .put(
                                        "resolved",
                                        JSONObject(resolvedHosts.getValue(catalog.id).toString())
                                            .put("catalog_mode", "explicit"),
                                    ),
                            )
                        }
                    }
                },
            )
            .put(
                "prompt_limits",
                JSONObject()
                    .put("max_catalog_entries", 64)
                    .put("max_summary_bytes", 8_192)
                    .put("max_catalog_serialized_bytes", 1024 * 1024)
                    .put("max_source_bytes", 400_000)
                    .put("max_response_bytes", 1024 * 1024),
            )
            .put("catalog_retry", JSONObject(retry.toString()))
            .put("stage1_retry", JSONObject(retry.toString()))
            .put("hole_retry", JSONObject(retry.toString()))

        return PreparedPipelineConfig(
            configJson = config.toString(),
            autoCatalog = autoCatalog,
            canvasFormatId = request.canvasFormatId,
            catalogId = selectedCatalog.id,
            renderColorMaps = catalogs.associate { it.id to it.renderMap },
            compositionSeed = request.compositionSeed,
            errorPolicy = request.errorPolicy,
            macroLocksJson = macroCatalog.requiredArray("locks").toString(),
            macroDiagnosticsJson = macroCatalog.requiredArray("diagnostics").toString(),
        )
    }

    fun renderCommand(
        config: PreparedPipelineConfig,
        view: PipelineView,
        renderSeed: Long?,
        wild: Boolean,
    ): PipelineCommand.Render {
        val delivery = view.deliveryJson?.let(::JSONObject)
            ?: throw PipelineHostException("score_not_ready")
        val compiler = delivery.requiredObject("compiler_options")
        val host = compiler.requiredObject("host")
        val canvasFormatId = host.requiredString("canvas_format_id")
        val catalogId = host.requiredString("resolved_catalog_id")
        val renderColorMap = config.renderColorMaps[catalogId]
            ?: throw PipelineHostException("saved_color_catalog_unavailable")
        val registry = JSONObject(binding.canvasRegistry()).requiredObject("registry")
        val format = registry.requiredArray("formats").objects()
            .firstOrNull { it.requiredString("id") == canvasFormatId }
            ?: throw PipelineHostException("unknown_canvas_format")
        val ratio = format.getDouble("width_units") / format.getDouble("height_units")
        val options = JSONObject()
            .put("resolved_color_map", JSONObject(renderColorMap))
            .put("catalog_id", catalogId)
            .put(
                "canvas",
                JSONObject()
                    .put("width", Math.rint(CANVAS_BASE_PX * ratio))
                    .put("height", CANVAS_BASE_PX),
            )
            .put("canvas_aspect_id", canvasFormatId)
            .put("svg_profile", "display")
            .put("render_seed", renderSeed.wireUnsignedOrNull())
            .put("composition_seed", compiler.optionalWireValue("composition_seed"))
            .put("wild", wild)
            .put("error_policy", compiler.requiredString("error_policy"))
        val clip = JSONObject()
            .put("tolerance_pixels", 0.1)
            .put("max_nodes", "50000")
            .put("max_path_elements", "200000")
            .put("max_flattened_points", "200000")
            .put("max_work", "10000000")
            .put("max_output_vertices", "200000")
        return PipelineCommand.Render(options.toString(), clip.toString())
    }

    /** Reuses one saved immutable config; callers must provide its saved render maps. */
    fun fromSavedConfig(
        configJson: String,
        renderColorMaps: Map<String, Map<String, String>>,
        macroLocksJson: String = "[]",
        macroDiagnosticsJson: String = "[]",
    ): PreparedPipelineConfig {
        requireCompatibleBinding()
        val config = JSONObject(configJson)
        val compiler = config.requiredObject("compiler")
        val host = compiler.requiredObject("host")
        val canvasFormatId = host.requiredString("canvas_format_id")
        val catalogId = host.requiredString("resolved_catalog_id")
        if (renderColorMaps[catalogId].isNullOrEmpty()) {
            throw PipelineHostException("saved_color_catalog_unavailable")
        }
        val formats = JSONObject(binding.canvasRegistry())
            .requiredObject("registry")
            .requiredArray("formats")
            .objects()
        if (formats.none { it.requiredString("id") == canvasFormatId }) {
            throw PipelineHostException("saved_canvas_compatibility_required")
        }
        return PreparedPipelineConfig(
            configJson = config.toString(),
            autoCatalog = config.optJSONArray("catalogs")?.length()?.let { it > 0 } == true,
            canvasFormatId = canvasFormatId,
            catalogId = catalogId,
            renderColorMaps = renderColorMaps.mapValues { (_, value) -> value.toMap() },
            compositionSeed = compiler.optionalUnsignedLong("composition_seed"),
            errorPolicy = compiler.requiredString("error_policy"),
            macroLocksJson = JSONArray(macroLocksJson).toString(),
            macroDiagnosticsJson = JSONArray(macroDiagnosticsJson).toString(),
        )
    }

    /** Refuses a native library built for another pipeline protocol than this host speaks. */
    private fun requireCompatibleBinding() {
        val report = JSONObject(binding.versionReport())
        if (
            report.optString("binding_version") != BINDING_VERSION ||
            report.optString("protocol_version") != PROTOCOL_VERSION
        ) {
            throw PipelineHostException("binding_protocol_mismatch")
        }
    }

    /**
     * The macro catalog for a new work. Imported definitions go ahead of the
     * installed ones and win their names, as the server's `_with_imported`
     * does; a name this device lacks, or holds with other content, is reported.
     */
    private fun resolveMacros(request: SharedPipelineConfigRequest): JSONObject {
        if (request.importedPlugins.isEmpty()) return resolveMacroCatalog(request, imported = emptyList())
        val base = resolveMacroCatalog(request, imported = emptyList())
        val installedDigests = base.requiredArray("entries").objects()
            .associate { it.requiredString("qualified_name") to it.requiredString("digest") }
        val output = resolveMacroCatalog(request, request.importedPlugins)
        val importedNames = output.requiredArray("entries").objects()
            .filter { it.optString("source_id").startsWith(IMPORTED_SOURCE) }
            .associate { it.requiredString("qualified_name") to it.requiredString("digest") }
        val diagnostics = JSONArray()
        output.requiredArray("diagnostics").objects().forEach { item ->
            val shadowed = item.optString("reason") == "duplicate_qualified_name" &&
                item.optString("qualified_name") in importedNames &&
                !item.optString("source_id").startsWith(IMPORTED_SOURCE)
            if (!shadowed) diagnostics.put(item)
        }
        importedNames.toSortedMap().forEach { (name, digest) ->
            val reason = when (installedDigests[name]) {
                null -> "imported_plugin_not_installed"
                digest -> return@forEach
                else -> "imported_plugin_differs_from_installed"
            }
            diagnostics.put(
                JSONObject()
                    .put("source_id", "imported")
                    .put("qualified_name", name)
                    .put("disposition", "used")
                    .put("reason", reason)
                    .put("warnings", JSONArray())
                    .put("findings", JSONArray()),
            )
        }
        return output.put("diagnostics", diagnostics)
    }

    /** Every name of the bundled package, including aliases, whatever its enabled state. */
    fun bundledPluginNames(language: String): List<String> = pluginVisibleNames(bundledPluginDefinitions(language))

    /** The bundled package's definitions, resolved as if it were enabled. */
    fun bundledPluginDefinitions(language: String): JSONArray {
        val output = resolveMacroCatalog(
            SharedPipelineConfigRequest(
                resolvedLanguage = language,
                canvasFormatId = "square",
                catalogSelectionId = "default",
            ),
            imported = emptyList(),
        )
        return JSONArray().also { definitions ->
            output.requiredArray("entries").objects().forEach { definitions.put(it.requiredObject("definition")) }
        }
    }

    private fun resolveMacroCatalog(
        request: SharedPipelineConfigRequest,
        imported: List<ImportedPluginDefinition>,
    ): JSONObject {
        val input = JSONObject()
            .put("maximum_entries", 64)
            .put(
                "bundled_packages",
                if (request.bundledPluginsEnabled) JSONArray().put(BUNDLED_PLUGIN_PACKAGE) else JSONArray(),
            )
            .put("language", request.resolvedLanguage)
            .put(
                "canonical",
                JSONArray().also { output ->
                    imported.forEachIndexed { index, candidate ->
                        output.put(
                            JSONObject()
                                .put("source_id", "$IMPORTED_SOURCE$index")
                                .put("definition_json", candidate.definitionJson)
                                .put("summary", candidate.summary),
                        )
                    }
                    request.canonicalMacros.forEach { candidate ->
                        output.put(
                            JSONObject()
                                .put("source_id", candidate.sourceId)
                                .put("definition_json", candidate.definitionJson)
                                .put("summary", candidate.summary),
                        )
                    }
                },
            )
            .put(
                "legacy",
                JSONArray().also { output ->
                    request.legacyMacros.forEach { candidate ->
                        output.put(
                            JSONObject()
                                .put("source_id", candidate.sourceId)
                                .put("qualified_name", candidate.qualifiedName),
                        )
                    }
                },
            )
        val output = JSONObject(
            binding.resolveMacroCatalog(input.toString().encodeToByteArray()).toString(Charsets.UTF_8),
        )
        if (output.optString("schema") != MACRO_CATALOG_SCHEMA || output.has("error")) {
            throw PipelineHostException("macro_catalog_resolution_failed")
        }
        return output
    }

    private fun resolvedHost(
        catalog: ColorCatalog,
        canvasFormatId: String,
        registryId: String,
        registryDigest: String,
        renderSeed: Long?,
        catalogMode: String,
    ): JSONObject {
        val input = JSONObject()
            .put("color_map", JSONObject(catalog.renderMap))
            .put("catalog_id", catalog.id)
            .put("render_seed", renderSeed.wireUnsignedOrNull())
            .put("background", "white")
        val palette = JSONObject(
            binding.resolvePalette(input.toString().encodeToByteArray()).toString(Charsets.UTF_8),
        )
        if (palette.has("error")) throw PipelineHostException(palette.requiredString("error"))
        return JSONObject()
            .put("canvas_format_id", canvasFormatId)
            .put("canvas_format_registry_id", registryId)
            .put("canvas_format_registry_digest", registryDigest)
            .put("resolved_catalog_id", catalog.id)
            .put("catalog_mode", catalogMode)
            .put("background", "white")
            .put("palette", palette)
    }

    private fun retryPolicy() = JSONObject()
        .put("max_attempts", policy.maximumProviderAttempts)
        .put("attempt_timeout_ms", policy.providerAttemptTimeoutMs.toString())
        .put("total_timeout_ms", policy.providerTotalTimeoutMs.toString())
        .put("retry_delay_ms", policy.providerRetryDelayMs.toString())

    private fun resourceMaximum(limits: PipelineResourceLimits): Map<String, Int> = linkedMapOf(
        "logical_objects" to 4_096,
        "template_nodes" to 128,
        "anchor_instances" to 4_096,
        "transform_instances" to 4_096,
        "placement_instances" to 64,
        "fill_instances" to 64,
        "primitive_marks" to limits.primitiveMarks,
        "maximum_per_template_primitive_marks" to limits.maximumPerTemplatePrimitiveMarks,
        "maximum_resolved_count" to limits.maximumResolvedCount,
        "object_templates" to limits.objectTemplates,
    ).also { maximum ->
        if (maximum.values.any { it <= 0 }) throw PipelineHostException("invalid_resource_budget")
    }

    private fun canonicalBudgetJson(maximum: Map<String, Int>): String =
        maximum.toSortedMap().entries.joinToString(
            prefix = "{\"maximum\":{",
            postfix = "}}",
            separator = ",",
        ) { (key, value) -> "\"$key\":$value" }

    private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }

    private fun Long?.wireUnsignedOrNull(): Any =
        this?.let(java.lang.Long::toUnsignedString) ?: JSONObject.NULL

    private fun JSONObject.optionalWireValue(name: String): Any =
        if (!has(name) || isNull(name)) JSONObject.NULL else get(name)

    private fun JSONObject.optionalUnsignedLong(name: String): Long? =
        if (!has(name) || isNull(name)) null else runCatching {
            java.lang.Long.parseUnsignedLong(requiredString(name))
        }.getOrElse { throw PipelineHostException("pipeline_schema_violation", it) }

    private fun JSONObject.requiredArray(name: String): JSONArray =
        optJSONArray(name) ?: throw PipelineHostException("pipeline_schema_violation")

    private fun JSONArray.objects(): List<JSONObject> =
        (0 until length()).map { index ->
            optJSONObject(index) ?: throw PipelineHostException("pipeline_schema_violation")
        }

    private companion object {
        const val BINDING_VERSION = "1.1.0"
        const val PROTOCOL_VERSION = "1.0.0"
        const val MACRO_CATALOG_SCHEMA = "inku.macro-catalog-resolution.v1"
        const val IMPORTED_SOURCE = "imported:"
        const val PIXEL9_HOST_ONLY_FORMAT = "pixel9_landscape_safe"
        const val CANVAS_BASE_PX = 1000.0
    }
}

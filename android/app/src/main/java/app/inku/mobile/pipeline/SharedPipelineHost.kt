package app.inku.mobile.pipeline

import java.math.BigInteger
import java.util.Base64
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/** Serialized Android host for the shared Rust authoring state machine. */
class SharedPipelineHost(
    private val binding: SharedPipelineBinding,
    private val providerEffect: PipelineProviderEffect,
    private val commitStore: PipelineCommitStore,
    private val executionStore: PipelineExecutionStore,
    private val maxEffectSteps: Int = 32,
    private val newId: () -> String = { UUID.randomUUID().toString().replace("-", "") },
) {
    private val sessions = mutableMapOf<String, Session>()
    private val sessionsMutex = Mutex()

    init {
        require(maxEffectSteps > 0) { "positive effect limit required" }
    }

    suspend fun start(request: PipelineStartRequest): PipelineView {
        require(request.ownerId.isNotBlank()) { "owner id required" }
        val config = JSONObject(request.configJson)
        val limits = limitsFrom(config)
        val variationId = newId()
        val payload = JSONObject()
            .put("tag", "start")
            .put("variation_id", variationId)
            .put("authoring_nonce", newId())
            .put("config", config)
            .put(
                "authority",
                JSONObject()
                    .put("protocol_version", "inku.variation-authority.v1")
                    .put("revision", "0")
                    .put(
                        "origin",
                        if (request.authoring is PipelineAuthoring.DirectDdl) {
                            "user_authored_ddl"
                        } else {
                            "stage1_generated"
                        },
                    )
                    .put(
                        "authority",
                        if (request.authoring is PipelineAuthoring.DirectDdl) {
                            "ddl_authoritative"
                        } else {
                            "description_authoritative"
                        },
                    ),
            )
            .put(
                "authoring",
                when (val authoring = request.authoring) {
                    is PipelineAuthoring.Description -> JSONObject()
                        .put("tag", "description")
                        .put("description", authoring.text)
                        .put("auto_catalog", authoring.autoCatalog)
                        .put("sketch", authoring.sketch.toJson())
                    is PipelineAuthoring.DirectDdl -> JSONObject()
                        .put("tag", "direct_ddl")
                        .put("source", authoring.source)
                },
            )
        val messageId = newId()
        val envelope = envelope("new", "0", messageId, payload)
        val inputBytes = envelope.toString().encodeToByteArray()
        requireWithin(inputBytes, limits.maxInputBytes)
        val output = parseOutput(binding.step(ByteArray(0), inputBytes), messageId, limits)
        val session = Session(
            ownerId = request.ownerId,
            snapshotBytes = output.snapshotBytes,
            models = request.models,
            context = request.context,
            hostContextJson = JSONObject(request.hostContextJson).toString(),
            fresh = true,
            renderedJson = output.renderedJson,
            eventsJson = output.eventsJson,
        )
        val snapshot = session.snapshot()
        executionStore.create(
            ownerId = request.ownerId,
            executionId = snapshot.requiredString("execution_id"),
            variationId = snapshot.requiredString("variation_id"),
            sequence = snapshot.requiredString("sequence"),
            stateBytes = persistedState(session),
        )
        val key = key(request.ownerId, snapshot.requiredString("execution_id"))
        sessionsMutex.withLock {
            if (sessions.putIfAbsent(key, session) != null) {
                throw PipelineHostException("execution_already_started")
            }
            session.users = 1
        }
        return useSession(session) { driveWithCancellation(it) }
    }

    suspend fun command(
        ownerId: String,
        executionId: String,
        command: PipelineCommand,
        hostContextJson: String? = null,
    ): PipelineView {
        val updatedHostContextJson = hostContextJson?.let { JSONObject(it).toString() }
        return withSession(ownerId, executionId) { session ->
            session.mutex.withLock {
                val previousContext = session.context
                val previousHostContextJson = session.hostContextJson
                if (command is PipelineCommand.GenerateFromDescription) {
                    session.context = session.context.copy(description = command.description)
                }
                if (updatedHostContextJson != null) {
                    session.hostContextJson = updatedHostContextJson
                }
                try {
                    advanceLocked(session, commandPayload(command))
                } catch (error: Throwable) {
                    session.context = previousContext
                    session.hostContextJson = previousHostContextJson
                    throw error
                }
            }
            if (command is PipelineCommand.Cancel) view(session) else driveWithCancellation(session)
        }
    }

    suspend fun cancel(ownerId: String, executionId: String): PipelineView = withSession(ownerId, executionId) { session ->
        session.mutex.withLock {
            if (session.snapshot().requiredObject("phase").requiredString("tag") !in TERMINAL_PHASES) {
                advanceLocked(session, JSONObject().put("tag", "cancel"))
            }
        }
        view(session)
    }

    suspend fun restore(ownerId: String, executionId: String): PipelineView =
        withSession(ownerId, executionId) { driveWithCancellation(it) }

    private suspend fun loadSession(ownerId: String, executionId: String): Session {
        val stateBytes = executionStore.load(ownerId, executionId)
            ?: throw PipelineHostException("execution_not_found")
        val state = JSONObject(stateBytes.toString(Charsets.UTF_8))
        if (state.optString("schema") != STORED_STATE_SCHEMA || state.requiredString("owner_id") != ownerId) {
            throw PipelineHostException("stored_execution_invalid")
        }
        val models = state.requiredObject("models")
        val context = state.requiredObject("context")
        val session = Session(
            ownerId = ownerId,
            snapshotBytes = runCatching {
                Base64.getDecoder().decode(state.requiredString("snapshot_base64"))
            }.getOrElse { throw PipelineHostException("stored_execution_invalid", it) },
            models = PipelineModelSelection(
                stage1ModelId = models.requiredString("stage1_model_id"),
                stage2ModelId = models.requiredString("stage2_model_id"),
                stage1MaxTokens = models.getInt("stage1_max_tokens"),
                holeMaxTokens = models.getInt("hole_max_tokens"),
            ),
            context = AuthoringContext(
                description = context.optString("description"),
                derivationKind = context.optString("derivation_kind", "new"),
                parentLegacyHistoryId = context.optionalString("parent_legacy_history_id"),
                parentVariationId = context.optionalString("parent_variation_id"),
            ),
            hostContextJson = state.requiredObject("host_context").toString(),
            fresh = state.getBoolean("fresh"),
            renderedJson = state.optionalString("rendered_json"),
            eventsJson = state.optString("events_json", "[]"),
        )
        val snapshot = session.snapshot()
        if (snapshot.requiredString("execution_id") != executionId) {
            throw PipelineHostException("stored_execution_invalid")
        }
        return session
    }

    suspend fun view(ownerId: String, executionId: String): PipelineView =
        withSession(ownerId, executionId) { view(it) }

    suspend fun snapshotJson(ownerId: String, executionId: String): String =
        withSession(ownerId, executionId) { session -> session.mutex.withLock { session.snapshot().toString() } }

    suspend fun executionContext(ownerId: String, executionId: String): PipelineExecutionContext = withSession(ownerId, executionId) { session ->
        session.mutex.withLock {
            val snapshot = session.snapshot()
            PipelineExecutionContext(
                snapshotJson = snapshot.toString(),
                configJson = snapshot.requiredObject("config").toString(),
                models = session.models,
                authoringContext = session.context,
                hostContextJson = session.hostContextJson,
                renderedJson = session.renderedJson,
            )
        }
    }

    private suspend fun driveWithCancellation(session: Session): PipelineView {
        return try {
            drive(session)
        } catch (cancelled: CancellationException) {
            withContext(NonCancellable) {
                runCatching { cancel(session.ownerId, session.snapshot().requiredString("execution_id")) }
            }
            throw cancelled
        }
    }

    private suspend fun drive(session: Session): PipelineView {
        repeat(maxEffectSteps) {
            val action = session.mutex.withLock {
                session.snapshot().optJSONObject("action")?.let { JSONObject(it.toString()) }
            } ?: return view(session)
            when (action.requiredString("tag")) {
                "commit_visible_normalized_ddl" -> runCommitEffect(session, action)
                "select_description_catalog",
                "generate_sketch",
                "generate_normalized_ddl",
                "complete_visible_ddl_holes"
                -> if (!runProviderEffect(session, action)) return view(session)
                else -> throw PipelineHostException("unsupported_pipeline_effect")
            }
        }
        if (session.mutex.withLock { session.snapshot().optJSONObject("action") != null }) {
            throw PipelineHostException("pipeline_effect_limit")
        }
        return view(session)
    }

    private suspend fun runCommitEffect(session: Session, action: JSONObject) {
        session.mutex.withLock {
            if (!sameAction(session.snapshot().optJSONObject("action"), action)) return
            val result = JSONObject(
                commitStore.commit(
                    ownerId = session.ownerId,
                    actionJson = action.toString(),
                    createIfMissing = session.fresh,
                    context = session.context,
                ),
            )
            if (result.optString("tag") == "visible_normalized_ddl_committed") {
                session.fresh = false
            }
            advanceLocked(
                session,
                JSONObject().put("tag", "effect_result").put("result", result),
            )
        }
    }

    private suspend fun runProviderEffect(session: Session, action: JSONObject): Boolean {
        val actionKey = action.toString()
        val claimed = session.mutex.withLock {
            if (!sameAction(session.snapshot().optJSONObject("action"), action)) return@withLock false
            if (session.providerActionInFlight != null) return@withLock false
            session.providerActionInFlight = actionKey
            true
        }
        if (!claimed) return false
        return try {
            val delayMs = action.requiredCanonicalUnsigned("delay_ms")
            if (delayMs > 0L) delay(delayMs)
            val resultJson = providerEffect.perform(actionKey, session.models)
            session.mutex.withLock {
                if (!sameAction(session.snapshot().optJSONObject("action"), action)) {
                    return@withLock false
                }
                advanceLocked(
                    session,
                    JSONObject().put("tag", "effect_result").put("result", JSONObject(resultJson)),
                )
                true
            }
        } finally {
            session.mutex.withLock {
                if (session.providerActionInFlight == actionKey) session.providerActionInFlight = null
            }
        }
    }

    private suspend fun advanceLocked(session: Session, payload: JSONObject) {
        val previous = session.snapshot()
        val limits = limitsFrom(previous.requiredObject("config"))
        val previousSequence = previous.requiredString("sequence")
        val messageId = newId()
        val input = envelope(
            executionId = previous.requiredString("execution_id"),
            sequence = nextDecimal(previousSequence),
            messageId = messageId,
            payload = payload,
        ).toString().encodeToByteArray()
        requireWithin(session.snapshotBytes, limits.maxSnapshotBytes)
        requireWithin(input, limits.maxInputBytes)
        val output = parseOutput(binding.step(session.snapshotBytes, input), messageId, limits)
        val next = JSONObject(output.snapshotBytes.toString(Charsets.UTF_8))
        if (next.requiredString("execution_id") != previous.requiredString("execution_id")) {
            throw PipelineHostException("pipeline_execution_identity_changed")
        }
        val oldDocument = previous.optJSONObject("document")?.toString()
        val nextDocument = next.optJSONObject("document")?.toString()
        val rendered = output.renderedJson ?: session.renderedJson
            ?.takeIf { oldDocument == nextDocument && next.optJSONObject("delivery") != null }
        val priorSnapshot = session.snapshotBytes
        val priorRendered = session.renderedJson
        val priorEvents = session.eventsJson
        session.snapshotBytes = output.snapshotBytes
        session.renderedJson = rendered
        session.eventsJson = output.eventsJson
        val saved = executionStore.compareAndSet(
            ownerId = session.ownerId,
            executionId = next.requiredString("execution_id"),
            expectedSequence = previousSequence,
            nextSequence = next.requiredString("sequence"),
            stateBytes = persistedState(session),
        )
        if (!saved) {
            session.snapshotBytes = priorSnapshot
            session.renderedJson = priorRendered
            session.eventsJson = priorEvents
            throw PipelineHostException("execution_snapshot_conflict")
        }
    }

    private fun parseOutput(bytes: ByteArray, messageId: String, limits: Limits): StepResult {
        requireWithin(bytes, limits.maxOutputBytes)
        val output = runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }
            .getOrElse { throw PipelineHostException("pipeline_malformed_output", it) }
        if (output.optString("protocol") != PROTOCOL || output.optString("version") != VERSION) {
            throw PipelineHostException("pipeline_protocol_mismatch")
        }
        if (output.optString("kind") == "error") {
            val code = output.optJSONObject("payload")?.optString("code").orEmpty()
            throw PipelineHostException(code.ifEmpty { "pipeline_error" })
        }
        if (output.optString("kind") != "output" || output.optString("message_id") != messageId) {
            throw PipelineHostException("pipeline_schema_violation")
        }
        val payload = output.requiredObject("payload")
        if (payload.optString("tag") != "step_result" || payload.optInt("version") != 1) {
            throw PipelineHostException("pipeline_protocol_mismatch")
        }
        val result = payload.requiredObject("result")
        val snapshot = result.requiredObject("snapshot")
        val snapshotBytes = snapshot.toString().encodeToByteArray()
        requireWithin(snapshotBytes, limits.maxSnapshotBytes)
        return StepResult(
            snapshotBytes = snapshotBytes,
            renderedJson = result.optJSONObject("rendered")?.toString(),
            eventsJson = result.optJSONArray("events")?.toString()
                ?: throw PipelineHostException("pipeline_schema_violation"),
        )
    }

    private suspend fun view(session: Session): PipelineView = session.mutex.withLock {
        val snapshot = session.snapshot()
        val authority = snapshot.requiredObject("authority")
        val phase = snapshot.requiredObject("phase")
        val phaseTag = phase.requiredString("tag")
        val document = snapshot.optJSONObject("document")
        val delivery = snapshot.optJSONObject("delivery")
        val patch = if (phaseTag == "awaiting_patch_approval") {
            PipelinePatchProposal(
                proposalDigest = phase.requiredString("proposal_digest"),
                baseRevision = phase.requiredString("base_revision"),
                patchJson = phase.requiredObject("patch").toString(),
                candidateDdl = phase.requiredObject("candidate").requiredString("source"),
            )
        } else {
            null
        }
        PipelineView(
            executionId = snapshot.requiredString("execution_id"),
            variationId = snapshot.requiredString("variation_id"),
            sequence = snapshot.requiredString("sequence"),
            revision = authority.requiredString("revision"),
            origin = authority.requiredString("origin"),
            authority = authority.requiredString("authority"),
            phaseTag = phaseTag,
            visibleDdl = document?.optString("source")?.takeIf(String::isNotEmpty),
            scoreJson = delivery?.optJSONObject("score")?.toString(),
            deliveryJson = delivery?.toString(),
            renderedJson = session.renderedJson,
            patchProposal = patch,
            busy = snapshot.optJSONObject("action") != null || session.providerActionInFlight != null,
            terminal = phaseTag in TERMINAL_PHASES,
            eventsJson = session.eventsJson,
            description = session.context.description.takeIf(String::isNotEmpty),
            hostContextJson = session.hostContextJson,
            models = session.models,
            sketch = PipelineSketchResult.from(snapshot.optJSONObject("sketch")),
        )
    }

    private fun persistedState(session: Session): ByteArray = JSONObject()
        .put("schema", STORED_STATE_SCHEMA)
        .put("owner_id", session.ownerId)
        .put("snapshot_base64", Base64.getEncoder().encodeToString(session.snapshotBytes))
        .put(
            "models",
            JSONObject()
                .put("stage1_model_id", session.models.stage1ModelId)
                .put("stage2_model_id", session.models.stage2ModelId)
                .put("stage1_max_tokens", session.models.stage1MaxTokens)
                .put("hole_max_tokens", session.models.holeMaxTokens),
        )
        .put(
            "context",
            JSONObject()
                .put("description", session.context.description)
                .put("derivation_kind", session.context.derivationKind)
                .put("parent_legacy_history_id", session.context.parentLegacyHistoryId)
                .put("parent_variation_id", session.context.parentVariationId),
        )
        .put("host_context", JSONObject(session.hostContextJson))
        .put("fresh", session.fresh)
        .put("rendered_json", session.renderedJson)
        .put("events_json", session.eventsJson)
        .toString()
        .encodeToByteArray()

    private fun commandPayload(command: PipelineCommand): JSONObject = when (command) {
        is PipelineCommand.CommitUserDdl -> JSONObject()
            .put("tag", "commit_user_ddl")
            .put("expected_revision", command.expectedRevision)
            .put("source", command.source)
        is PipelineCommand.GenerateFromDescription -> JSONObject()
            .put("tag", "generate_from_description")
            .put("expected_revision", command.expectedRevision)
            .put("description", command.description)
            .put("auto_catalog", command.autoCatalog)
            .put("sketch", command.sketch.toJson())
        is PipelineCommand.ApprovePatch -> JSONObject()
            .put("tag", "approve_patch")
            .put("expected_revision", command.expectedRevision)
            .put("proposal_digest", command.proposalDigest)
        is PipelineCommand.DeclinePatch -> JSONObject()
            .put("tag", "decline_patch")
            .put("proposal_digest", command.proposalDigest)
        is PipelineCommand.Render -> JSONObject()
            .put("tag", "render")
            .put("options", JSONObject(command.optionsJson))
            .put("clip", JSONObject(command.clipJson))
        PipelineCommand.Cancel -> JSONObject().put("tag", "cancel")
    }

    private fun envelope(
        executionId: String,
        sequence: String,
        messageId: String,
        payload: JSONObject,
    ): JSONObject = JSONObject()
        .put("protocol", PROTOCOL)
        .put("version", VERSION)
        .put("kind", "input")
        .put("execution_id", executionId)
        .put("message_id", messageId)
        .put("sequence", sequence)
        .put("payload", JSONObject(payload.toString()).put("version", 1))

    private fun limitsFrom(config: JSONObject): Limits {
        val limits = config.requiredObject("envelope_limits")
        return Limits(
            maxInputBytes = limits.getInt("max_input_bytes"),
            maxSnapshotBytes = limits.getInt("max_snapshot_bytes"),
            maxOutputBytes = limits.getInt("max_output_bytes"),
        ).also {
            if (it.maxInputBytes <= 0 || it.maxSnapshotBytes <= 0 || it.maxOutputBytes <= 0) {
                throw PipelineHostException("invalid_pipeline_limits")
            }
        }
    }

    private fun requireWithin(bytes: ByteArray, maximum: Int) {
        if (bytes.size > maximum) throw PipelineHostException("transport_size_limit")
    }

    private fun nextDecimal(value: String): String = runCatching {
        BigInteger(value).add(BigInteger.ONE).toString()
    }.getOrElse { throw PipelineHostException("pipeline_schema_violation", it) }

    private fun sameAction(current: JSONObject?, expected: JSONObject): Boolean =
        current?.toString() == expected.toString()

    private suspend fun <T> withSession(ownerId: String, executionId: String, block: suspend (Session) -> T): T {
        val session = sessionsMutex.withLock {
            // Loading under the cache lock prevents an older durable snapshot
            // from being inserted after the last active user releases a newer one.
            sessions.getOrPut(key(ownerId, executionId)) { loadSession(ownerId, executionId) }
                .also { it.users += 1 }
        }
        return useSession(session, block)
    }

    private suspend fun <T> useSession(session: Session, block: suspend (Session) -> T): T = try {
        block(session)
    } finally {
        withContext(NonCancellable) {
            sessionsMutex.withLock {
                session.users -= 1
                if (session.users == 0) {
                    sessions.remove(key(session.ownerId, session.snapshot().requiredString("execution_id")), session)
                }
            }
        }
    }

    private fun key(ownerId: String, executionId: String) = "$ownerId\u0000$executionId"

    private fun JSONObject.optionalString(name: String): String? =
        if (isNull(name)) null else optString(name).takeIf(String::isNotEmpty)

    private fun JSONObject.requiredArray(name: String): JSONArray =
        optJSONArray(name) ?: throw PipelineHostException("pipeline_schema_violation")

    private fun JSONObject.requiredCanonicalUnsigned(name: String): Long {
        val value = requiredString(name)
        if (!value.all { it in '0'..'9' } || (value.length > 1 && value.startsWith('0'))) {
            throw PipelineHostException("pipeline_schema_violation")
        }
        return value.toLongOrNull() ?: throw PipelineHostException("pipeline_schema_violation")
    }

    private data class Session(
        val ownerId: String,
        var snapshotBytes: ByteArray,
        val models: PipelineModelSelection,
        var context: AuthoringContext,
        var hostContextJson: String,
        var fresh: Boolean,
        var renderedJson: String?,
        var users: Int = 0,
        var eventsJson: String,
        var providerActionInFlight: String? = null,
        val mutex: Mutex = Mutex(),
    ) {
        fun snapshot(): JSONObject = try {
            JSONObject(snapshotBytes.toString(Charsets.UTF_8))
        } catch (error: Exception) {
            throw PipelineHostException("stored_execution_invalid", error)
        }
    }

    private data class Limits(
        val maxInputBytes: Int,
        val maxSnapshotBytes: Int,
        val maxOutputBytes: Int,
    )

    private data class StepResult(
        val snapshotBytes: ByteArray,
        val renderedJson: String?,
        val eventsJson: String,
    )

    private companion object {
        const val PROTOCOL = "inku.pipeline"
        const val VERSION = "1.0.0"
        const val STORED_STATE_SCHEMA = "inku.android-pipeline-execution.v1"
        val TERMINAL_PHASES = setOf("completed", "needs_user_edit", "failed", "cancelled")
    }
}

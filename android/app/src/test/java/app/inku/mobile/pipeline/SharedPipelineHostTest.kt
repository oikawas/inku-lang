package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedPipelineHostTest {
    @Test
    fun descriptionRunCommitsThenRequestsKnownHoleAndWaitsForApproval() = runBlocking {
        val binding = ScriptedBinding()
        val provider = RecordingEffectProvider()
        val commits = RecordingCommitStore()
        val executions = MemoryExecutionStore()
        val host = host(binding, provider, commits, executions)

        val pending = host.start(startRequest(PipelineAuthoring.Description("mist", false)))

        assertEquals("awaiting_patch_approval", pending.phaseTag)
        assertEquals(listOf("generate_normalized_ddl", "complete_visible_ddl_holes"), provider.tags)
        assertEquals(1, provider.tags.count { it == "generate_normalized_ddl" })
        assertEquals(1, provider.tags.count { it == "complete_visible_ddl_holes" })
        assertEquals(1, commits.actions.size)
        assertNotNull(pending.patchProposal)
        assertFalse(pending.busy)

        val ready = host.command(
            OWNER,
            pending.executionId,
            PipelineCommand.ApprovePatch(pending.revision, pending.patchProposal!!.proposalDigest),
        )

        assertEquals("score_ready", ready.phaseTag)
        assertEquals("patched DDL", ready.visibleDdl)
        assertEquals(2, commits.actions.size)
        assertTrue(host.snapshotJson(OWNER, ready.executionId).contains("\"delivery\""))
        assertEquals(ready.sequence, JSONObject(executions.load(OWNER, ready.executionId)!!.toString(Charsets.UTF_8))
            .let { state -> JSONObject(String(java.util.Base64.getDecoder().decode(state.getString("snapshot_base64")))) }
            .getString("sequence"))
    }

    @Test
    fun directDdlUsesNoProviderAndReachesSharedScore() = runBlocking {
        val provider = RecordingEffectProvider()
        val commits = RecordingCommitStore()
        val host = host(ScriptedBinding(), provider, commits, MemoryExecutionStore())

        val ready = host.start(startRequest(PipelineAuthoring.DirectDdl("place one circle.")))

        assertEquals("score_ready", ready.phaseTag)
        assertTrue(provider.tags.isEmpty())
        assertEquals(1, commits.actions.size)
        assertEquals("user_authored_ddl", ready.origin)
        assertEquals("ddl_authoritative", ready.authority)
    }

    @Test
    fun cancellationInvalidatesLateProviderResult() = runBlocking {
        val started = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val provider = PipelineProviderEffect { actionJson, _ ->
            started.complete(Unit)
            release.await()
            effectResult(JSONObject(actionJson), "normalized_ddl_generated", "{}")
        }
        val host = host(ScriptedBinding(), provider, RecordingCommitStore(), MemoryExecutionStore())
        val running = async { host.start(startRequest(PipelineAuthoring.Description("mist", false))) }
        started.await()

        val cancelled = host.cancel(OWNER, EXECUTION_ID)
        release.complete(Unit)
        val completed = running.await()

        assertEquals("cancelled", cancelled.phaseTag)
        assertEquals("cancelled", completed.phaseTag)
        assertEquals(null, completed.visibleDdl)
    }

    @Test
    fun singleAttemptAdapterPassesCorePromptAndTimeoutOnce() = runBlocking {
        val requests = mutableListOf<ModelRequest>()
        val adapter = SingleAttemptModelEffectProvider(object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse {
                requests += request
                return ModelResponse("exact response", request.modelId)
            }
        })
        val action = providerAction("generate_normalized_ddl", "provider-1")

        val result = JSONObject(adapter.perform(action.toString(), MODELS))

        assertEquals("normalized_ddl_generated", result.getString("tag"))
        assertEquals(1, requests.size)
        assertEquals("system", requests.single().systemInstruction)
        assertEquals("message", requests.single().prompt)
        assertEquals(
            JSONObject().put("type", "object").put("properties", JSONObject()).toString(),
            requests.single().tool?.parametersJson,
        )
        assertEquals(1_000L, requests.single().timeoutMs)
    }

    private fun host(
        binding: SharedPipelineBinding,
        provider: PipelineProviderEffect,
        commits: PipelineCommitStore,
        executions: PipelineExecutionStore,
    ): SharedPipelineHost {
        val ids = ArrayDeque(listOf("variation", "nonce", "message-0") + (1..100).map { "message-$it" })
        return SharedPipelineHost(
            binding = binding,
            providerEffect = provider,
            commitStore = commits,
            executionStore = executions,
            newId = { ids.removeFirst() },
        )
    }

    private fun startRequest(authoring: PipelineAuthoring) = PipelineStartRequest(
        ownerId = OWNER,
        configJson = CONFIG.toString(),
        authoring = authoring,
        models = MODELS,
        context = AuthoringContext("mist"),
    )

    private class RecordingEffectProvider : PipelineProviderEffect {
        val tags = mutableListOf<String>()

        override suspend fun perform(actionJson: String, models: PipelineModelSelection): String {
            val action = JSONObject(actionJson)
            val tag = action.getString("tag")
            tags += tag
            return when (tag) {
                "generate_normalized_ddl" -> effectResult(action, "normalized_ddl_generated", "{}")
                "complete_visible_ddl_holes" -> effectResult(action, "visible_ddl_hole_patch_generated", "{}")
                else -> error("unexpected provider action")
            }
        }
    }

    private class RecordingCommitStore : PipelineCommitStore {
        val actions = mutableListOf<JSONObject>()

        override suspend fun commit(
            ownerId: String,
            actionJson: String,
            createIfMissing: Boolean,
            context: AuthoringContext,
        ): String {
            val action = JSONObject(actionJson)
            actions += action
            return JSONObject()
                .put("tag", "visible_normalized_ddl_committed")
                .put("identity", action.getJSONObject("identity"))
                .put("ddl_digest", action.getJSONObject("payload").getString("ddl_digest"))
                .put("revision", actions.size.toString())
                .put("authority_digest", "authority-${actions.size}")
                .toString()
        }
    }

    private class MemoryExecutionStore : PipelineExecutionStore {
        private val states = ConcurrentHashMap<String, Pair<String, ByteArray>>()

        override suspend fun create(
            ownerId: String,
            executionId: String,
            variationId: String,
            sequence: String,
            stateBytes: ByteArray,
        ) {
            check(states.putIfAbsent("$ownerId:$executionId", sequence to stateBytes.copyOf()) == null)
        }

        override suspend fun compareAndSet(
            ownerId: String,
            executionId: String,
            expectedSequence: String,
            nextSequence: String,
            stateBytes: ByteArray,
        ): Boolean {
            val key = "$ownerId:$executionId"
            val current = states[key] ?: return false
            if (current.first != expectedSequence) return false
            return states.replace(key, current, nextSequence to stateBytes.copyOf())
        }

        override suspend fun load(ownerId: String, executionId: String): ByteArray? =
            states["$ownerId:$executionId"]?.second?.copyOf()
    }

    private class ScriptedBinding : SharedPipelineBinding {
        override fun versionReport() = """{"binding_version":"1.1.0","protocol_version":"1.0.0"}"""

        override fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray {
            val input = JSONObject(inputEnvelopeBytes.toString(Charsets.UTF_8))
            val payload = input.getJSONObject("payload")
            val previous = snapshotBytes.takeIf { it.isNotEmpty() }
                ?.let { JSONObject(it.toString(Charsets.UTF_8)) }
            val direct = payload.optString("tag") == "start" &&
                payload.getJSONObject("authoring").optString("tag") == "direct_ddl"
            val resultTag = payload.optJSONObject("result")?.optString("tag")
            val previousActionId = previous?.optJSONObject("action")
                ?.optJSONObject("identity")
                ?.optString("action_id")
            val state = when {
                payload.optString("tag") == "cancel" -> State.Cancelled
                payload.optString("tag") == "approve_patch" -> State.SecondCommit
                direct -> State.FirstCommit
                payload.optString("tag") == "start" -> State.Stage1
                resultTag == "normalized_ddl_generated" -> State.FirstCommit
                resultTag == "visible_ddl_hole_patch_generated" -> State.AwaitingPatch
                resultTag == "visible_normalized_ddl_committed" && previousActionId == "commit-1" -> {
                    if (previous?.optString("origin_fixture") == "direct") State.Ready else State.Hole
                }
                resultTag == "visible_normalized_ddl_committed" -> State.Ready
                payload.optString("tag") == "render" -> State.Completed
                else -> error("unexpected transition: $payload")
            }
            val config = if (previous == null) payload.getJSONObject("config") else previous.getJSONObject("config")
            val variationId = previous?.getString("variation_id") ?: payload.getString("variation_id")
            val origin = if (direct || previous?.optString("origin_fixture") == "direct") "direct" else "description"
            val snapshot = snapshot(state, input.getString("sequence"), variationId, config, origin)
            val rendered = if (state == State.Completed) {
                JSONObject().put("svg", "<svg/>").put("metadata", JSONObject())
            } else {
                JSONObject.NULL
            }
            return JSONObject()
                .put("protocol", "inku.pipeline")
                .put("version", "1.0.0")
                .put("kind", "output")
                .put("execution_id", EXECUTION_ID)
                .put("message_id", input.getString("message_id"))
                .put("sequence", input.getString("sequence"))
                .put(
                    "payload",
                    JSONObject()
                        .put("tag", "step_result")
                        .put("version", 1)
                        .put(
                            "result",
                            JSONObject()
                                .put("snapshot", snapshot)
                                .put("events", JSONArray())
                                .put("rendered", rendered),
                        ),
                )
                .toString()
                .encodeToByteArray()
        }

        private fun snapshot(
            state: State,
            sequence: String,
            variationId: String,
            config: JSONObject,
            originFixture: String,
        ): JSONObject {
            val direct = originFixture == "direct"
            val revision = when (state) {
                State.Stage1, State.FirstCommit -> "0"
                State.Hole, State.AwaitingPatch, State.SecondCommit -> "1"
                State.Ready, State.Completed -> if (direct) "1" else "2"
                State.Cancelled -> "0"
            }
            val document = when (state) {
                State.Stage1, State.Cancelled -> null
                State.FirstCommit, State.Hole, State.AwaitingPatch -> if (direct) "place one circle." else "DDL with hole"
                State.SecondCommit, State.Ready, State.Completed -> if (direct) "place one circle." else "patched DDL"
            }
            val action = when (state) {
                State.Stage1 -> providerAction("generate_normalized_ddl", "provider-1")
                State.FirstCommit -> commitAction("commit-1", document!!, revision)
                State.Hole -> providerAction("complete_visible_ddl_holes", "provider-2")
                State.SecondCommit -> commitAction("commit-2", document!!, revision)
                else -> null
            }
            val phase = when (state) {
                State.Stage1, State.Hole -> JSONObject().put("tag", "awaiting_llm")
                State.FirstCommit, State.SecondCommit -> JSONObject().put("tag", "awaiting_visible_ddl_commit")
                State.AwaitingPatch -> JSONObject()
                    .put("tag", "awaiting_patch_approval")
                    .put("patch", JSONObject().put("edits", JSONArray()))
                    .put("candidate", visibleDocument("patched DDL"))
                    .put("proposal_digest", "proposal")
                    .put("base_revision", "1")
                State.Ready -> JSONObject().put("tag", "score_ready")
                State.Completed -> JSONObject().put("tag", "completed")
                State.Cancelled -> JSONObject().put("tag", "cancelled")
            }
            val delivery = if (state in setOf(State.Ready, State.Completed)) {
                JSONObject()
                    .put("score", JSONObject().put("schema", "inku.score.v1").put("instructions", JSONArray()))
                    .put(
                        "compiler_options",
                        JSONObject()
                            .put("host", JSONObject().put("canvas_format_id", "square").put("resolved_catalog_id", "default"))
                            .put("composition_seed", JSONObject.NULL)
                            .put("error_policy", "omit_and_continue"),
                    )
            } else {
                null
            }
            return JSONObject()
                .put("protocol", "inku.pipeline")
                .put("version", "1.0.0")
                .put("execution_id", EXECUTION_ID)
                .put("variation_id", variationId)
                .put("sequence", sequence)
                .put("event_sequence", sequence)
                .put("action_ordinal", sequence)
                .put(
                    "authority",
                    JSONObject()
                        .put("protocol_version", "inku.variation-authority.v1")
                        .put("revision", revision)
                        .put("origin", if (direct) "user_authored_ddl" else "stage1_generated")
                        .put("authority", if (direct) "ddl_authoritative" else "description_authoritative"),
                )
                .put("config", JSONObject(config.toString()))
                .put("document", document?.let(::visibleDocument) ?: JSONObject.NULL)
                .put("phase", phase)
                .put("action", action ?: JSONObject.NULL)
                .put("delivery", delivery ?: JSONObject.NULL)
                .put("snapshot_digest", "fixture")
                .put("origin_fixture", originFixture)
        }

        override fun canvasRegistry() = error("not used")
        override fun resolvePalette(inputBytes: ByteArray) = error("not used")
        override fun resolveMacroCatalog(inputBytes: ByteArray) = error("not used")
        override fun renderSaved(inputBytes: ByteArray) = error("not used")

        private enum class State { Stage1, FirstCommit, Hole, AwaitingPatch, SecondCommit, Ready, Completed, Cancelled }
    }

    private companion object {
        const val OWNER = "owner"
        const val EXECUTION_ID = "execution"
        val MODELS = PipelineModelSelection("stage1", "stage2")
        val CONFIG = JSONObject().put(
            "envelope_limits",
            JSONObject()
                .put("max_input_bytes", 100_000)
                .put("max_snapshot_bytes", 100_000)
                .put("max_output_bytes", 100_000),
        )
        fun providerAction(tag: String, id: String) = JSONObject()
            .put("tag", tag)
            .put("version", 1)
            .put(
                "identity",
                JSONObject().put("action_id", id).put("attempt", 1).put("request_digest", "digest-$id"),
            )
            .put("timeout_ms", "1000")
            .put("delay_ms", "0")
            .put(
                "payload",
                JSONObject().put(
                    "prompt",
                    JSONObject()
                        .put("system", "system")
                        .put("message", "message")
                        .put("response_schema", JSONObject().put("type", "object").put("properties", JSONObject())),
                ),
            )

        fun commitAction(id: String, source: String, revision: String) = JSONObject()
            .put("tag", "commit_visible_normalized_ddl")
            .put("version", 1)
            .put(
                "identity",
                JSONObject().put("action_id", id).put("attempt", 1).put("request_digest", "digest-$id"),
            )
            .put("timeout_ms", "0")
            .put("delay_ms", "0")
            .put(
                "payload",
                JSONObject()
                    .put("ddl_digest", "ddl-$id")
                    .put("document", visibleDocument(source))
                    .put("reason", "fixture")
                    .put(
                        "authority",
                        JSONObject()
                            .put("expected_revision", revision)
                            .put(
                                "next_state",
                                JSONObject()
                                    .put("protocol_version", "inku.variation-authority.v1")
                                    .put("revision", (revision.toInt() + 1).toString())
                                    .put("origin", "stage1_generated")
                                    .put("authority", "description_authoritative"),
                            ),
                    ),
            )

        fun visibleDocument(source: String) = JSONObject()
            .put("source", source)
            .put("language", "en")
            .put("macro_locks", JSONArray())

        fun effectResult(action: JSONObject, tag: String, response: String) = JSONObject()
            .put("tag", tag)
            .put("identity", action.getJSONObject("identity"))
            .put("response", response)
            .put("elapsed_ms", "1")
            .toString()
    }
}

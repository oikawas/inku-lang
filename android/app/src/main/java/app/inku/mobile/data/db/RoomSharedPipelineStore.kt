package app.inku.mobile.data.db

import android.database.sqlite.SQLiteConstraintException
import androidx.room.withTransaction
import app.inku.mobile.data.lineage.LineageWrite
import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.pipeline.AuthoringContext
import app.inku.mobile.pipeline.PipelineCommitStore
import app.inku.mobile.pipeline.PipelineExecutionStore
import java.math.BigInteger
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

class SharedPipelinePersistenceException(message: String) : IllegalArgumentException(message)

data class ManagedHistoryLinkInput(
    val ownerId: String,
    val variationId: String,
    val revision: String,
    val ddlDigest: String,
    val snapshotJson: String,
    val contextJson: String,
    val pipelineDiagnosticsJson: String,
)

data class ManagedHistoryReplayInput(
    val ownerId: String,
    val sourceHistoryId: String,
    val hostOptionsJson: String,
    val resolvedColorMapJson: String,
    val pipelineDiagnosticsJson: String,
)

data class ManagedHistoryRead(
    val history: HistoryItemEntity,
    val authority: String?,
    val variationId: String? = null,
    val revision: String? = null,
    val ddlDigest: String? = null,
    val forkContextJson: String? = null,
    val warning: String? = null,
)

class RoomSharedPipelineStore(
    private val database: InkuDatabase,
    private val now: () -> Long = System::currentTimeMillis,
) : PipelineCommitStore, PipelineExecutionStore {
    private val dao: SharedPipelineDao
        get() = database.sharedPipelineDao()

    override suspend fun commit(
        ownerId: String,
        actionJson: String,
        createIfMissing: Boolean,
        context: AuthoringContext,
    ): String {
        val commit = parseCommit(ownerId, actionJson)
        return try {
            database.withTransaction {
                dao.getAction(ownerId, commit.actionId)?.let { acknowledged ->
                    return@withTransaction replayAcknowledgment(commit, acknowledged, context)
                }

                val current = dao.getAuthority(ownerId, commit.variationId)
                val resolvedContext = if (current == null) {
                    if (!createIfMissing) return@withTransaction failedResult(commit, null)
                    requireInitialTransition(commit)
                    validateInitialContext(ownerId, commit, context)
                    dao.insertAuthority(commit.toEntity(context, now()))
                    context
                } else {
                    if (current.revision != commit.expectedRevision) {
                        return@withTransaction failedResult(commit, current.revision)
                    }
                    validateTransition(current, commit)
                    val nextContext = resolveContext(current, commit, context)
                    val changed = dao.updateAuthorityCas(
                        ownerId = ownerId,
                        variationId = commit.variationId,
                        expectedRevision = commit.expectedRevision,
                        protocolVersion = AUTHORITY_PROTOCOL,
                        nextRevision = commit.nextRevision,
                        authority = commit.authority,
                        source = commit.source,
                        documentJson = commit.documentJson,
                        ddlDigest = commit.ddlDigest,
                        authorityDigest = commit.authorityDigest,
                        description = nextContext.description,
                        updatedAt = now(),
                    )
                    if (changed != 1) {
                        return@withTransaction failedResult(
                            commit,
                            dao.getAuthority(ownerId, commit.variationId)?.revision,
                        )
                    }
                    nextContext
                }

                dao.insertAction(commit.toActionEntity(resolvedContext, now()))
                committedResult(commit)
            }
        } catch (_: SQLiteConstraintException) {
            recoverAfterConstraintConflict(commit, context)
        }
    }

    override suspend fun create(
        ownerId: String,
        executionId: String,
        variationId: String,
        sequence: String,
        stateBytes: ByteArray,
    ) {
        require(ownerId.isNotEmpty() && executionId.isNotEmpty() && variationId.isNotEmpty()) {
            "execution owner and identities must not be empty"
        }
        canonicalU64(sequence, "execution sequence")
        val digest = sha256(stateBytes)
        val timestamp = now()
        try {
            dao.insertExecution(
                PipelineExecutionEntity(
                    ownerId = ownerId,
                    executionId = executionId,
                    variationId = variationId,
                    sequence = sequence,
                    stateBytes = stateBytes.copyOf(),
                    stateDigest = digest,
                    createdAt = timestamp,
                    updatedAt = timestamp,
                ),
            )
        } catch (_: SQLiteConstraintException) {
            val existing = dao.getExecution(ownerId, executionId)
            if (
                existing == null ||
                existing.variationId != variationId ||
                existing.sequence != sequence ||
                existing.stateDigest != digest
            ) {
                throw SharedPipelinePersistenceException("execution snapshot sequence conflict")
            }
        }
    }

    override suspend fun compareAndSet(
        ownerId: String,
        executionId: String,
        expectedSequence: String,
        nextSequence: String,
        stateBytes: ByteArray,
    ): Boolean {
        requireNextRevision(expectedSequence, nextSequence, "execution sequence")
        return dao.updateExecutionCas(
            ownerId = ownerId,
            executionId = executionId,
            expectedSequence = expectedSequence,
            nextSequence = nextSequence,
            stateBytes = stateBytes.copyOf(),
            stateDigest = sha256(stateBytes),
            updatedAt = now(),
        ) == 1
    }

    override suspend fun load(ownerId: String, executionId: String): ByteArray? {
        val stored = dao.getExecution(ownerId, executionId) ?: return null
        if (sha256(stored.stateBytes) != stored.stateDigest) {
            throw SharedPipelinePersistenceException("stored execution state bytes failed integrity validation")
        }
        return stored.stateBytes.copyOf()
    }

    suspend fun loadLatestExecution(ownerId: String, variationId: String): ByteArray? {
        val stored = dao.getLatestExecution(ownerId, variationId) ?: return null
        if (sha256(stored.stateBytes) != stored.stateDigest) {
            throw SharedPipelinePersistenceException("stored execution state bytes failed integrity validation")
        }
        return stored.stateBytes.copyOf()
    }

    suspend fun readAuthority(ownerId: String, variationId: String): VariationAuthorityEntity? =
        dao.getAuthority(ownerId, variationId)

    internal suspend fun buildHistoryLink(
        history: HistoryItemEntity,
        input: ManagedHistoryLinkInput,
    ): PipelineHistoryLinkEntity {
        require(history.normalizedDdl.sha256() == input.ddlDigest) {
            "history source does not match its committed revision"
        }
        val acknowledged = dao.findCommittedAction(
            input.ownerId,
            input.variationId,
            input.revision,
            input.ddlDigest,
        )
        requireNotNull(acknowledged) { "history link requires committed source" }
        val bytes = encodeForkContext(input)
        return PipelineHistoryLinkEntity(
            ownerId = input.ownerId,
            historyId = history.id,
            variationId = input.variationId,
            revision = input.revision,
            ddlDigest = input.ddlDigest,
            forkContextBytes = bytes,
            forkContextDigest = sha256(bytes),
        )
    }

    suspend fun saveManagedHistory(
        history: HistoryItemEntity,
        lineage: LineageWrite,
        input: ManagedHistoryLinkInput,
    ) {
        val link = buildHistoryLink(history, input)
        database.withTransaction {
            database.historyDao().insert(history)
            database.lineageDao().insertNode(lineage.node)
            lineage.edge?.let { database.lineageDao().insertEdge(it) }
            dao.insertHistoryLink(link)
        }
    }

    suspend fun saveManagedReplayHistory(
        history: HistoryItemEntity,
        lineage: LineageWrite,
        input: ManagedHistoryReplayInput,
    ) {
        database.withTransaction {
            val sourceHistory = database.historyDao().getById(input.sourceHistoryId)
                ?.takeUnless { it.trashed }
                ?: throw SharedPipelinePersistenceException("replay source history was not found")
            val sourceLink = dao.getHistoryLink(input.ownerId, input.sourceHistoryId)
                ?: throw SharedPipelinePersistenceException("replay source is not managed history")
            val sourceContext = decodeForkContextObject(sourceHistory, sourceLink)
            require(history.normalizedDdl == sourceHistory.normalizedDdl) {
                "replay source DDL changed"
            }
            require(history.normalizedDdl.sha256() == sourceLink.ddlDigest) {
                "replay source does not match its committed revision"
            }
            require(
                LineagePlanner.canonicalJson(JSONObject(history.scoreJson)) ==
                    LineagePlanner.canonicalJson(JSONObject(sourceHistory.scoreJson)),
            ) { "replay Score changed" }

            val hostOptions = JSONObject(input.hostOptionsJson)
            val catalogId = hostOptions.stringField("catalog_id")
            val colorMap = JSONObject(input.resolvedColorMapJson)
            val colorMaps = JSONObject(sourceContext.objectField("color_maps").toString())
                .put(catalogId, colorMap)
            val diagnostics = JSONObject(input.pipelineDiagnosticsJson)
            validateDiagnostics(diagnostics)
            val payload = linkedMapOf<String, Any?>(
                "protocol_version" to HISTORY_CONTEXT_PROTOCOL,
                "variation_id" to sourceLink.variationId,
                "revision" to sourceLink.revision,
                "ddl_digest" to sourceLink.ddlDigest,
                "authority" to sourceContext.objectField("authority"),
                "config" to sourceContext.objectField("config"),
                "host_options" to hostOptions,
                "color_maps" to colorMaps,
                "macro_catalog" to sourceContext.objectField("macro_catalog"),
                "pipeline_diagnostics" to diagnostics,
            )
            val bytes = LineagePlanner.canonicalJson(payload).toByteArray(Charsets.UTF_8)
            val link = PipelineHistoryLinkEntity(
                ownerId = input.ownerId,
                historyId = history.id,
                variationId = sourceLink.variationId,
                revision = sourceLink.revision,
                ddlDigest = sourceLink.ddlDigest,
                forkContextBytes = bytes,
                forkContextDigest = sha256(bytes),
            )
            database.historyDao().insert(history)
            database.lineageDao().insertNode(lineage.node)
            lineage.edge?.let { database.lineageDao().insertEdge(it) }
            dao.insertHistoryLink(link)
        }
    }

    suspend fun readHistory(ownerId: String, historyId: String): ManagedHistoryRead? {
        val history = database.historyDao().getById(historyId)?.takeUnless { it.trashed } ?: return null
        val link = dao.getHistoryLink(ownerId, historyId) ?: run {
            if (dao.getAnyHistoryLink(historyId) != null) return null
            return ManagedHistoryRead(history = history, authority = "legacy_unknown")
        }
        return try {
            val context = decodeForkContextObject(history, link)
            ManagedHistoryRead(
                history = history,
                authority = context.objectField("authority").stringField("authority"),
                variationId = link.variationId,
                revision = link.revision,
                ddlDigest = link.ddlDigest,
                forkContextJson = context.toString(),
            )
        } catch (error: SharedPipelinePersistenceException) {
            ManagedHistoryRead(
                history = history,
                authority = null,
                variationId = link.variationId,
                revision = link.revision,
                ddlDigest = link.ddlDigest,
                warning = error.message ?: "saved authoring context is unavailable",
            )
        }
    }

    private suspend fun recoverAfterConstraintConflict(
        commit: Commit,
        context: AuthoringContext,
    ): String {
        dao.getAction(commit.ownerId, commit.actionId)?.let {
            return replayAcknowledgment(commit, it, context)
        }
        return failedResult(
            commit,
            dao.getAuthority(commit.ownerId, commit.variationId)?.revision,
        )
    }

    private suspend fun validateInitialContext(
        ownerId: String,
        commit: Commit,
        context: AuthoringContext,
    ) {
        validateContextShape(context)
        val required = when (context.derivationKind) {
            "legacy_ddl_fork" -> "user_authored_ddl" to "ddl_authoritative"
            "legacy_description_fork", "description_fork" ->
                "stage1_generated" to "description_authoritative"
            else -> null
        }
        require(required == null || required == (commit.origin to commit.authority)) {
            "fork kind does not match its initial origin and authority"
        }
        context.parentLegacyHistoryId?.let { historyId ->
            val parent = database.historyDao().getById(historyId)
            require(parent != null && !parent.trashed) { "legacy parent was not found" }
        }
        context.parentVariationId?.let { parentId ->
            require(dao.getAuthority(ownerId, parentId) != null) { "candidate parent was not found" }
        }
    }

    private fun resolveContext(
        current: VariationAuthorityEntity,
        commit: Commit,
        proposed: AuthoringContext,
    ): AuthoringContext {
        val stored = current.context()
        validateContextShape(proposed)
        require(
            proposed.derivationKind == stored.derivationKind &&
                proposed.parentLegacyHistoryId == stored.parentLegacyHistoryId &&
                proposed.parentVariationId == stored.parentVariationId,
        ) { "variation derivation and parent are immutable" }
        if (proposed.description == stored.description) return stored
        require(
            commit.reason in setOf("stage1_generated", "stage1_residual_execution") &&
                current.authority == "description_authoritative" &&
                commit.authority == "description_authoritative",
        ) { "description can change only during an authoritative Stage 1 commit" }
        return proposed
    }

    private fun replayAcknowledgment(
        commit: Commit,
        action: VariationAuthorityActionEntity,
        context: AuthoringContext,
    ): String {
        require(
            action.variationId == commit.variationId &&
                action.requestDigest == commit.requestDigest &&
                action.actionFingerprint == commit.actionFingerprint &&
                action.ddlDigest == commit.ddlDigest &&
                action.revision == commit.nextRevision &&
                action.authorityDigest == commit.authorityDigest &&
                action.contextFingerprint == context.fingerprint(),
        ) { "action_id was already acknowledged for different commit bytes" }
        return committedResult(commit)
    }

    private fun encodeForkContext(input: ManagedHistoryLinkInput): ByteArray {
        canonicalU64(input.revision, "history revision")
        val snapshot = JSONObject(input.snapshotJson)
        val context = JSONObject(input.contextJson)
        val diagnostics = JSONObject(input.pipelineDiagnosticsJson)
        val authority = snapshot.objectField("authority")
        val document = snapshot.objectField("document")
        val delivery = snapshot.objectField("delivery")
        val config = snapshot.objectField("config")
        val source = document.stringField("source")
        require(
            snapshot.stringField("variation_id") == input.variationId &&
                frozenAuthorityMatches(authority, input.revision) &&
                delivery.stringField("source_digest") == input.ddlDigest &&
                source.sha256() == input.ddlDigest,
        ) { "history fork context does not match the committed revision" }
        val hostOptions = context.objectField("host_options")
        val colorMaps = context.objectField("color_maps")
        val macroCatalog = context.objectField("macro_catalog")
        validateDiagnostics(diagnostics)
        val payload = linkedMapOf<String, Any?>(
            "protocol_version" to HISTORY_CONTEXT_PROTOCOL,
            "variation_id" to input.variationId,
            "revision" to input.revision,
            "ddl_digest" to input.ddlDigest,
            "authority" to authority,
            "config" to config,
            "host_options" to hostOptions,
            "color_maps" to colorMaps,
            "macro_catalog" to macroCatalog,
            "pipeline_diagnostics" to diagnostics,
        )
        return LineagePlanner.canonicalJson(payload).toByteArray(Charsets.UTF_8)
    }

    private fun decodeForkContextObject(
        history: HistoryItemEntity,
        link: PipelineHistoryLinkEntity,
    ): JSONObject {
        if (sha256(link.forkContextBytes) != link.forkContextDigest) {
            throw SharedPipelinePersistenceException("stored history fork context failed integrity validation")
        }
        if (history.normalizedDdl.sha256() != link.ddlDigest) {
            throw SharedPipelinePersistenceException("history source does not match its committed revision")
        }
        val text = link.forkContextBytes.toString(Charsets.UTF_8)
        val payload = runCatching { JSONObject(text) }.getOrElse {
            throw SharedPipelinePersistenceException("stored history fork context is not UTF-8 JSON")
        }
        if (
            payload.stringField("protocol_version") != HISTORY_CONTEXT_PROTOCOL ||
            payload.stringField("variation_id") != link.variationId ||
            payload.stringField("revision") != link.revision ||
            payload.stringField("ddl_digest") != link.ddlDigest ||
            payload.keys().asSequence().toSet() != HISTORY_CONTEXT_KEYS
        ) {
            throw SharedPipelinePersistenceException("stored history fork context does not match its history link")
        }
        val authority = payload.objectField("authority")
        if (!frozenAuthorityMatches(authority, link.revision)) {
            throw SharedPipelinePersistenceException("stored history authority does not match its history link")
        }
        payload.objectField("config")
        payload.objectField("host_options")
        payload.objectField("color_maps")
        payload.objectField("macro_catalog")
        validateDiagnostics(payload.objectField("pipeline_diagnostics"))
        return payload
    }

    private fun frozenAuthorityMatches(authority: JSONObject, revision: String): Boolean =
        authority.keySet() == setOf("protocol_version", "revision", "origin", "authority") &&
            authority.stringField("protocol_version") == AUTHORITY_PROTOCOL &&
            authority.stringField("revision") == revision &&
            authority.stringField("origin") in ORIGINS &&
            authority.stringField("authority") in AUTHORITIES

    private fun validateDiagnostics(value: JSONObject) {
        require(value.keys().asSequence().toSet() == DIAGNOSTIC_KEYS) { "pipeline diagnostics have an unexpected shape" }
        listOf(
            "upstream_diagnostics",
            "downstream_diagnostics",
            "resource_omissions",
            "relation_omissions",
        ).forEach { require(value.opt(it) is JSONArray) { "pipeline diagnostic channels must be arrays" } }
        listOf("render_diagnostics", "resource_execution").forEach { key ->
            require(value.isNull(key) || value.opt(key) is JSONObject) {
                "render diagnostic records must be objects or null"
            }
        }
    }

    private data class Commit(
        val ownerId: String,
        val variationId: String,
        val actionId: String,
        val attempt: Long,
        val requestDigest: String,
        val expectedRevision: String,
        val nextRevision: String,
        val origin: String,
        val authority: String,
        val source: String,
        val documentJson: String,
        val ddlDigest: String,
        val authorityDigest: String,
        val actionFingerprint: String,
        val reason: String,
    ) {
        fun toEntity(context: AuthoringContext, timestamp: Long) = VariationAuthorityEntity(
            ownerId = ownerId,
            variationId = variationId,
            protocolVersion = AUTHORITY_PROTOCOL,
            revision = nextRevision,
            origin = origin,
            authority = authority,
            source = source,
            documentJson = documentJson,
            ddlDigest = ddlDigest,
            authorityDigest = authorityDigest,
            description = context.description,
            derivationKind = context.derivationKind,
            parentLegacyHistoryId = context.parentLegacyHistoryId,
            parentVariationId = context.parentVariationId,
            updatedAt = timestamp,
        )

        fun toActionEntity(context: AuthoringContext, timestamp: Long) = VariationAuthorityActionEntity(
            ownerId = ownerId,
            actionId = actionId,
            variationId = variationId,
            requestDigest = requestDigest,
            actionFingerprint = actionFingerprint,
            contextFingerprint = context.fingerprint(),
            ddlDigest = ddlDigest,
            revision = nextRevision,
            authorityDigest = authorityDigest,
            committedAt = timestamp,
        )
    }

    companion object {
        const val AUTHORITY_PROTOCOL = "inku.variation-authority.v1"
        const val HISTORY_CONTEXT_PROTOCOL = "inku.pipeline-history-fork-context.v2"
        private val U64_MAX = BigInteger("18446744073709551615")
        private val ORIGINS = setOf("stage1_generated", "user_authored_ddl")
        private val AUTHORITIES = setOf("description_authoritative", "ddl_authoritative", "legacy_unknown")
        private val INITIAL_PAIRS = setOf(
            "stage1_generated" to "description_authoritative",
            "stage1_generated" to "ddl_authoritative",
            "user_authored_ddl" to "ddl_authoritative",
        )
        private val DERIVATION_KINDS = setOf(
            "new",
            "legacy_ddl_fork",
            "legacy_description_fork",
            "description_fork",
            "variation_ddl_fork",
        )
        private val DIAGNOSTIC_KEYS = setOf(
            "upstream_diagnostics",
            "downstream_diagnostics",
            "resource_omissions",
            "relation_omissions",
            "render_diagnostics",
            "resource_execution",
        )
        private val HISTORY_CONTEXT_KEYS = setOf(
            "protocol_version",
            "variation_id",
            "revision",
            "ddl_digest",
            "authority",
            "config",
            "host_options",
            "color_maps",
            "macro_catalog",
            "pipeline_diagnostics",
        )

        private fun parseCommit(ownerId: String, actionJson: String): Commit {
            require(ownerId.isNotEmpty()) { "owner_id must not be empty" }
            val action = JSONObject(actionJson)
            require(action.keySet() == setOf("tag", "version", "identity", "timeout_ms", "delay_ms", "payload")) {
                "action has an unexpected shape"
            }
            require(action.stringField("tag") == "commit_visible_normalized_ddl" && action.opt("version") == 1) {
                "expected commit action version 1"
            }
            val identity = action.objectField("identity")
            require(identity.keySet() == setOf("action_id", "attempt", "request_digest")) {
                "identity has an unexpected shape"
            }
            val actionId = identity.stringField("action_id").also(::requireDigest)
            val requestDigest = identity.stringField("request_digest").also(::requireDigest)
            val attemptValue = identity.opt("attempt")
            val attempt = (attemptValue as? Number)?.toLong()
                ?: throw SharedPipelinePersistenceException("action attempt must be a positive integer")
            require(attempt > 0 && attemptValue is Number && attemptValue.toString() == attempt.toString()) {
                "action attempt must be a positive integer"
            }
            val payload = action.objectField("payload")
            require(payload.keySet() == setOf("variation_id", "document", "ddl_digest", "authority", "authority_digest", "reason")) {
                "payload has an unexpected shape"
            }
            val variationId = payload.stringField("variation_id")
            require(variationId.isNotEmpty()) { "variation_id must not be empty" }
            val reason = payload.stringField("reason")
            require(reason.isNotEmpty()) { "commit reason must not be empty" }
            val document = payload.objectField("document")
            require(document.keySet() == setOf("source", "language", "macro_locks")) {
                "document has an unexpected shape"
            }
            val source = document.stringField("source")
            document.stringField("language")
            require(document.opt("macro_locks") is JSONArray) { "document metadata has an unexpected shape" }
            val ddlDigest = payload.stringField("ddl_digest").also(::requireDigest)
            require(source.sha256() == ddlDigest) { "ddl_digest does not identify exact source bytes" }
            val proposal = payload.objectField("authority")
            require(proposal.keySet() == setOf("expected_revision", "next_state")) {
                "authority proposal has an unexpected shape"
            }
            val expectedRevision = proposal.stringField("expected_revision")
            val nextState = proposal.objectField("next_state")
            require(nextState.keySet() == setOf("protocol_version", "revision", "origin", "authority")) {
                "next authority state has an unexpected shape"
            }
            require(nextState.stringField("protocol_version") == AUTHORITY_PROTOCOL) { "authority protocol mismatch" }
            val nextRevision = nextState.stringField("revision")
            requireNextRevision(expectedRevision, nextRevision, "revision")
            val origin = nextState.stringField("origin")
            val authority = nextState.stringField("authority")
            require(origin in ORIGINS && authority in AUTHORITIES) { "unknown origin or authority" }
            val authorityDigest = payload.stringField("authority_digest").also(::requireDigest)
            val logicalAction = linkedMapOf<String, Any?>(
                "tag" to action.stringField("tag"),
                "version" to 1,
                "action_id" to actionId,
                "request_digest" to requestDigest,
                "payload" to payload,
            )
            return Commit(
                ownerId = ownerId,
                variationId = variationId,
                actionId = actionId,
                attempt = attempt,
                requestDigest = requestDigest,
                expectedRevision = expectedRevision,
                nextRevision = nextRevision,
                origin = origin,
                authority = authority,
                source = source,
                documentJson = LineagePlanner.canonicalJson(document),
                ddlDigest = ddlDigest,
                authorityDigest = authorityDigest,
                actionFingerprint = LineagePlanner.canonicalJson(logicalAction).sha256(),
                reason = reason,
            )
        }

        private fun requireInitialTransition(commit: Commit) {
            require(commit.expectedRevision == "0" && (commit.origin to commit.authority) in INITIAL_PAIRS) {
                "new variation has an invalid initial transition"
            }
        }

        private fun validateTransition(current: VariationAuthorityEntity, commit: Commit) {
            require(current.protocolVersion == AUTHORITY_PROTOCOL) { "stored authority protocol mismatch" }
            require(current.origin == commit.origin) { "variation origin is immutable" }
            when (current.authority) {
                "description_authoritative" -> require(
                    commit.authority == "description_authoritative" || commit.authority == "ddl_authoritative",
                ) { "invalid description authority transition" }
                "ddl_authoritative" -> require(commit.authority == "ddl_authoritative") {
                    "DDL authority cannot be unlocked"
                }
                "legacy_unknown" -> throw SharedPipelinePersistenceException(
                    "legacy_unknown requires an explicit compatibility decision",
                )
                else -> throw SharedPipelinePersistenceException("stored authority is unknown")
            }
        }

        private fun validateContextShape(context: AuthoringContext) {
            require(context.derivationKind in DERIVATION_KINDS) { "unknown derivation kind" }
            val legacy = !context.parentLegacyHistoryId.isNullOrEmpty()
            val variation = !context.parentVariationId.isNullOrEmpty()
            val valid = when (context.derivationKind) {
                "new" -> !legacy && !variation
                "legacy_ddl_fork", "legacy_description_fork" -> legacy && !variation
                "description_fork", "variation_ddl_fork" -> !legacy && variation
                else -> false
            }
            require(valid) { "derivation kind does not match its parent" }
        }

        private fun canonicalU64(value: String, field: String): BigInteger {
            require(value.isNotEmpty() && value.all { it in '0'..'9' } && (value == "0" || !value.startsWith('0'))) {
                "$field must be a canonical unsigned decimal string"
            }
            val parsed = value.toBigInteger()
            require(parsed <= U64_MAX) { "$field exceeds u64" }
            return parsed
        }

        private fun requireNextRevision(expected: String, next: String, field: String) {
            val before = canonicalU64(expected, "expected $field")
            val after = canonicalU64(next, "next $field")
            require(before < U64_MAX && after == before + BigInteger.ONE) {
                "next $field must increment expected $field"
            }
        }

        private fun requireDigest(value: String) {
            require(value.length == 64 && value.all { it in '0'..'9' || it in 'a'..'f' }) {
                "digest must be lowercase sha256"
            }
        }

        private fun committedResult(commit: Commit): String = LineagePlanner.canonicalJson(
            linkedMapOf(
                "tag" to "visible_normalized_ddl_committed",
                "identity" to linkedMapOf(
                    "action_id" to commit.actionId,
                    "attempt" to commit.attempt,
                    "request_digest" to commit.requestDigest,
                ),
                "ddl_digest" to commit.ddlDigest,
                "revision" to commit.nextRevision,
                "authority_digest" to commit.authorityDigest,
            ),
        )

        private fun failedResult(commit: Commit, actualRevision: String?): String = LineagePlanner.canonicalJson(
            linkedMapOf(
                "tag" to "host_commit_failed",
                "identity" to linkedMapOf(
                    "action_id" to commit.actionId,
                    "attempt" to commit.attempt,
                    "request_digest" to commit.requestDigest,
                ),
                "actual_revision" to actualRevision,
            ),
        )

        private fun AuthoringContext.fingerprint(): String = LineagePlanner.canonicalJson(
            linkedMapOf(
                "description" to description,
                "derivation_kind" to derivationKind,
                "parent_legacy_history_id" to parentLegacyHistoryId,
                "parent_variation_id" to parentVariationId,
            ),
        ).sha256()

        private fun VariationAuthorityEntity.context() = AuthoringContext(
            description = description,
            derivationKind = derivationKind,
            parentLegacyHistoryId = parentLegacyHistoryId,
            parentVariationId = parentVariationId,
        )

        private fun JSONObject.keySet(): Set<String> = keys().asSequence().toSet()

        private fun JSONObject.objectField(name: String): JSONObject = opt(name) as? JSONObject
            ?: throw SharedPipelinePersistenceException("$name must be an object")

        private fun JSONObject.stringField(name: String): String = opt(name) as? String
            ?: throw SharedPipelinePersistenceException("$name must be text")

        private fun String.sha256(): String = sha256(toByteArray(Charsets.UTF_8))

        private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
            .digest(bytes)
            .joinToString("") { "%02x".format(it) }

    }
}

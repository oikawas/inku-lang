package app.inku.mobile.data.db

import java.io.ByteArrayOutputStream

internal const val EXECUTION_STATE_CHUNK_SQL =
    "SELECT substr(state_bytes, :offset, :length) FROM pipeline_candidate_executions " +
        "WHERE owner_id = :ownerId AND execution_id = :executionId AND state_digest = :digest"

/** Reads a fixed digest's BLOB without placing the complete payload in one CursorWindow. */
internal suspend fun readExecutionBlob(readChunk: suspend (Int, Int) -> ByteArray?): ByteArray {
    val output = ByteArrayOutputStream()
    var offset = 1
    while (true) {
        val chunk = readChunk(offset, EXECUTION_BLOB_CHUNK_BYTES)
            ?: throw SharedPipelinePersistenceException("execution snapshot changed while reading")
        if (chunk.isEmpty()) return output.toByteArray()
        output.write(chunk)
        offset = Math.addExact(offset, chunk.size)
        if (chunk.size < EXECUTION_BLOB_CHUNK_BYTES) return output.toByteArray()
    }
}

internal const val EXECUTION_BLOB_CHUNK_BYTES = 1024 * 1024

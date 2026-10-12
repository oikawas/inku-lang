package app.inku.mobile.data.db

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class ExecutionBlobReadTest {
    @Test
    fun blobBeyondOldWindowReadsInDigestBoundChunksAndRefusesChangedSnapshot() = runBlocking {
        HostSqlite().use { host ->
            host.db.execSQL("CREATE TABLE pipeline_candidate_executions(owner_id TEXT, execution_id TEXT, state_digest TEXT, state_bytes BLOB)")
            val size = 41 * 1024 * 1024
            host.db.execSQL("INSERT INTO pipeline_candidate_executions VALUES ('owner', 'execution', 'digest', zeroblob(?))", arrayOf(size))
            var calls = 0
            suspend fun chunk(offset: Int, length: Int): ByteArray? {
                calls += 1
                val sql = EXECUTION_STATE_CHUNK_SQL.replace(Regex(":[A-Za-z]+"), "?")
                return host.db.query(sql, arrayOf<Any>(offset, length, "owner", "execution", "digest")).use {
                    if (it.moveToFirst()) it.getBlob(0) else null
                }
            }
            val bytes = readExecutionBlob(::chunk)
            assertEquals(size, bytes.size)
            assertTrue(bytes.all { it == 0.toByte() })
            assertEquals(42, calls)
            var changed = false
            try {
                readExecutionBlob { offset, length ->
                    if (!changed && offset > 1) {
                        host.db.execSQL("UPDATE pipeline_candidate_executions SET state_digest = 'new-digest'")
                        changed = true
                    }
                    chunk(offset, length)
                }
                fail("a changed digest must not mix execution snapshots")
            } catch (_: SharedPipelinePersistenceException) {
                assertTrue(changed)
            }
        }
    }
}

package app.inku.mobile.data.refinement

import android.util.AtomicFile
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.io.File

/** Auxiliary run progress, separate from the canonical work database. */
class AutonomousRunFile(file: File) : AutonomousRunStore {
    private val atomic = AtomicFile(file)
    private val mutex = Mutex()
    private fun read(): JSONObject = if (atomic.baseFile.exists() || File(atomic.baseFile.path + ".bak").exists())
        atomic.openRead().bufferedReader(Charsets.UTF_8).use { JSONObject(it.readText()) } else JSONObject()

    override suspend fun all(): List<JSONObject> = mutex.withLock {
        val runs = read()
        runs.keys().asSequence().map { runs.getJSONObject(it) }.toList()
    }

    override suspend fun save(run: JSONObject) = mutex.withLock {
        val runs = read().put(run.getString("id"), JSONObject(run.toString()))
        val output = atomic.startWrite()
        try {
            output.write(runs.toString().encodeToByteArray())
            atomic.finishWrite(output)
        } catch (error: Throwable) {
            atomic.failWrite(output)
            throw error
        }
    }
}

package app.inku.mobile.data.db

import app.inku.mobile.pipeline.NativePipelineBridge
import java.io.File
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Opt-in migration of a separate device backup copy under a hard JVM heap cap. */
class SaijikiV3HeapTest {
    @Test fun deviceCopyFitsLimitedHeap() {
        val path = System.getenv("INKU_SAIJIKI_HEAP_DB") ?: return
        require(path.contains("/local/evidence/android/tools-v3-step5-20261101/"))
        assertTrue("Run this rehearsal with at most -Xmx192m", Runtime.getRuntime().maxMemory() <= 192L * 1024 * 1024)
        val folder = requireNotNull(File(path).parentFile)
        val runtime = Runtime.getRuntime()
        val running = AtomicBoolean(true)
        val peak = AtomicLong(runtime.totalMemory() - runtime.freeMemory())
        fun sample() {
            val used = runtime.totalMemory() - runtime.freeMemory()
            while (true) {
                val old = peak.get()
                if (used <= old || peak.compareAndSet(old, used)) return
            }
        }
        val sampler = Thread({ while (running.get()) { sample(); Thread.sleep(2) } }, "migration-heap-sampler").apply { isDaemon = true; start() }
        val started = System.nanoTime()
        var report: JSONObject? = null
        try {
            HostSqlite(path).use { host ->
                report = requireNotNull(SaijikiV3Migration(NativePipelineBridge::migrateSaijikiV1,
                    NativePipelineBridge::migrateSaijikiV2, true).runOnce(host.db))
                assertNull(SaijikiV3Migration(NativePipelineBridge::migrateSaijikiV1,
                    NativePipelineBridge::migrateSaijikiV2, true).runOnce(host.db))
            }
        } finally {
            sample(); running.set(false); sampler.join()
            val metrics = JSONObject().put("max_heap_bytes", Runtime.getRuntime().maxMemory())
                .put("sampled_peak_heap_used_bytes", peak.get()).put("sampling_interval_ms", 2)
                .put("elapsed_ms", (System.nanoTime() - started) / 1_000_000)
                .put("heap_committed_at_end_bytes", runtime.totalMemory())
            writePrivate(folder.resolve("heap-metrics.json"), metrics)
        }
        val completed = requireNotNull(report)
        writePrivate(folder.resolve("report.json"), completed)
        val reference = JSONObject(File(requireNotNull(System.getenv("INKU_SAIJIKI_HEAP_REFERENCE"))).readText())
        for (key in listOf("definitions", "variation_documents", "history", "history_links", "executions", "edits",
                "refused_records", "unassociated_sweep_records", "unassociated_tool_records", "unadjusted_thinness_records",
                "statements", "discarded_executions")) {
            assertEquals(key, app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(reference.get(key)),
                app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(completed.get(key)))
        }
        assertEquals(20, completed.getInt("unique_definitions"))
        assertEquals(20, completed.getInt("definition_core_calls"))
    }

    private fun writePrivate(file: File, value: JSONObject) {
        file.createNewFile()
        Files.setPosixFilePermissions(file.toPath(), PosixFilePermissions.fromString("rw-------"))
        file.writeText(value.toString(2))
    }
}

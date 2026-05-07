package app.inku.mobile.llm

import android.content.Context
import android.os.StatFs
import app.inku.mobile.data.db.ModelAssetDao
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlin.coroutines.coroutineContext

class LocalModelDownloader(
    private val context: Context,
    private val modelAssetDao: ModelAssetDao,
) {
    suspend fun download(spec: ModelDownloadSpec, force: Boolean = false) = withContext(Dispatchers.IO) {
        val asset = modelAssetDao.getByModelId(spec.modelId) ?: error("Model asset is not registered: ${spec.modelId}")
        if (asset.licenseAcceptedAt == null) {
            modelAssetDao.updateDownload(spec.modelId, "license_required", 0L, null, null, now())
            error("License must be accepted before downloading ${spec.displayName}.")
        }

        val modelDir = File(context.filesDir, "models").also { it.mkdirs() }
        val finalFile = File(modelDir, spec.fileName)
        val partFile = File(modelDir, "${spec.fileName}.part")

        if (force) {
            if (finalFile.exists()) finalFile.delete()
            if (partFile.exists()) partFile.delete()
            modelAssetDao.updateDownload(spec.modelId, "queued", 0L, null, null, now())
        }

        if (finalFile.exists() && verifySha256(finalFile, spec.expectedSha256)) {
            modelAssetDao.updateDownload(spec.modelId, "ready", finalFile.length(), finalFile.length(), finalFile.absolutePath, now())
            return@withContext
        }

        if (partFile.exists() && verifySha256(partFile, spec.expectedSha256)) {
            if (finalFile.exists()) {
                finalFile.delete()
            }
            check(partFile.renameTo(finalFile)) { "Could not finalize downloaded model file." }
            modelAssetDao.updateDownload(spec.modelId, "ready", finalFile.length(), finalFile.length(), finalFile.absolutePath, now())
            return@withContext
        }

        val existingBytes = partFile.takeIf { it.exists() }?.length() ?: 0L
        modelAssetDao.updateDownload(spec.modelId, "connecting", existingBytes, null, partFile.absolutePath, now())

        val connection = (URL(spec.downloadUrl).openConnection() as HttpURLConnection).apply {
            connectTimeout = 20_000
            readTimeout = 30_000
            instanceFollowRedirects = true
            requestMethod = "GET"
            setRequestProperty("Accept", "application/octet-stream")
            if (existingBytes > 0L) {
                setRequestProperty("Range", "bytes=$existingBytes-")
            }
        }

        try {
            val code = connection.responseCode
            if (code !in listOf(HttpURLConnection.HTTP_OK, HttpURLConnection.HTTP_PARTIAL)) {
                modelAssetDao.updateDownload(spec.modelId, "failed_http_$code", existingBytes, null, partFile.absolutePath, now())
                error("Model download failed with HTTP $code.")
            }

            val append = code == HttpURLConnection.HTTP_PARTIAL && existingBytes > 0L
            if (!append && partFile.exists()) {
                partFile.delete()
            }

            val totalBytes = contentTotalBytes(connection, if (append) existingBytes else 0L)
            ensureSpace(totalBytes, modelDir)
            modelAssetDao.updateDownload(spec.modelId, "downloading", if (append) existingBytes else 0L, totalBytes, partFile.absolutePath, now())

            connection.inputStream.use { input ->
                FileOutputStream(partFile, append).buffered().use { output ->
                    streamToFile(input, output, spec, partFile, totalBytes, if (append) existingBytes else 0L)
                }
            }
        } finally {
            connection.disconnect()
        }
    }

    private suspend fun streamToFile(
        input: java.io.InputStream,
        output: java.io.OutputStream,
        spec: ModelDownloadSpec,
        partFile: File,
        totalBytes: Long?,
        initialBytes: Long,
    ) {
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        var downloaded = initialBytes
        var lastUpdateAt = 0L
        while (true) {
            coroutineContext.ensureActive()
            val read = input.read(buffer)
            if (read < 0) break
            output.write(buffer, 0, read)
            downloaded += read
            val timestamp = now()
            if (timestamp - lastUpdateAt > 500L || totalBytes == downloaded) {
                modelAssetDao.updateDownload(spec.modelId, "downloading", downloaded, totalBytes, partFile.absolutePath, timestamp)
                lastUpdateAt = timestamp
            }
        }
        output.flush()
        modelAssetDao.updateDownload(spec.modelId, "verifying", downloaded, totalBytes, partFile.absolutePath, now())
        if (!verifySha256(partFile, spec.expectedSha256)) {
            modelAssetDao.updateDownload(spec.modelId, "failed_sha256", downloaded, totalBytes, partFile.absolutePath, now())
            error("Downloaded model checksum did not match ${spec.expectedSha256}.")
        }
        val finalFile = File(partFile.parentFile, spec.fileName)
        if (finalFile.exists()) {
            finalFile.delete()
        }
        check(partFile.renameTo(finalFile)) { "Could not finalize downloaded model file." }
        modelAssetDao.updateDownload(spec.modelId, "ready", finalFile.length(), finalFile.length(), finalFile.absolutePath, now())
    }

    private fun contentTotalBytes(connection: HttpURLConnection, existingBytes: Long): Long? {
        val contentRange = connection.getHeaderField("Content-Range")
        val rangeTotal = contentRange?.substringAfter("/", missingDelimiterValue = "")?.toLongOrNull()
        if (rangeTotal != null) return rangeTotal
        val length = connection.contentLengthLong
        return when {
            length <= 0L -> null
            existingBytes > 0L -> existingBytes + length
            else -> length
        }
    }

    private fun ensureSpace(totalBytes: Long?, modelDir: File) {
        if (totalBytes == null) return
        val stat = StatFs(modelDir.absolutePath)
        val available = stat.availableBytes
        val existing = modelDir.listFiles()?.sumOf { it.length() } ?: 0L
        val needed = (totalBytes - existing).coerceAtLeast(0L)
        val cushion = 512L * 1024L * 1024L
        check(available > needed + cushion) {
            "Not enough storage for model. Need ${needed + cushion} bytes including safety margin, available $available bytes."
        }
    }

    private fun verifySha256(file: File, expected: String?): Boolean {
        if (expected.isNullOrBlank()) return true
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }.equals(expected, ignoreCase = true)
    }

    private fun now(): Long = System.currentTimeMillis()
}

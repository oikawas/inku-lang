package app.inku.mobile.ui.ddl3d

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.URLUtil
import android.webkit.WebChromeClient
import android.webkit.WebMessage
import android.webkit.WebMessagePort
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.core.content.FileProvider
import app.inku.mobile.ui.SharePayload
import app.inku.mobile.ui.exportCacheDir
import app.inku.mobile.ui.launchShareIntent
import java.io.ByteArrayInputStream
import java.io.File
import org.json.JSONObject

private const val TAG = "InkuDdl3d"
private const val NATIVE_PORT = "inku.ddl3d.native"
/** A saved PNG or GLB larger than this is not handed on. */
private const val MAXIMUM_DOWNLOAD_BYTES = 64L * 1024 * 1024

/** The deadline on the main thread. */
internal object MainThreadDdl3DTimer : Ddl3DTimer {
    private val handler = Handler(Looper.getMainLooper())
    override fun schedule(delayMs: Long, action: () -> Unit): () -> Unit {
        val runnable = Runnable(action)
        handler.postDelayed(runnable, delayMs)
        return { handler.removeCallbacks(runnable) }
    }
}

/**
 * One 3D view's web view: the parent page and the registered build served from
 * the app's assets under one https origin, and nothing else -- no network, no
 * other page, no window. JSON goes to and from the page on one message channel
 * per mount. The viewer's PNG and GLB saves go to the share sheet.
 */
@SuppressLint("SetJavaScriptEnabled")
internal class Ddl3DWebHost(
    private val context: Context,
    private val registered: Ddl3DInstallation.Registered,
    private val title: String,
    private val controller: Ddl3DController,
    private val onShareFailed: () -> Unit,
) : Ddl3DPage {
    val webView = WebView(context)
    private var port: WebMessagePort? = null
    private var mounted = ""
    private val waiting = mutableListOf<JSONObject>()

    init {
        // Without layout params AndroidView gives the view WRAP_CONTENT, and a web
        // view whose height wraps its content lays the page out 0 px tall: the
        // viewer drew into a frame no one could see (Build148421, black screen).
        webView.layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        webView.setBackgroundColor(Color.TRANSPARENT)
        webView.settings.apply {
            javaScriptEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            domStorageEnabled = false
            databaseEnabled = false
            setSupportMultipleWindows(false)
            javaScriptCanOpenWindowsAutomatically = false
            mediaPlaybackRequiresUserGesture = true
        }
        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse =
                serve(request.url)

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                !(request.url.scheme == "https" && request.url.host == HOST)

            override fun onPageFinished(view: WebView, url: String) {
                if (Uri.parse(url).getQueryParameter("mount") == mounted) openChannel()
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: android.webkit.WebResourceError) {
                if (request.isForMainFrame) controller.fail("viewer_load_failed")
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(message: ConsoleMessage): Boolean {
                Log.i(TAG, "${message.messageLevel()} ${message.message()}")
                return true
            }
        }
        // The viewer saves with a blob URL in its frame; the parent page, on the
        // same origin, reads it before the viewer revokes it.
        webView.setDownloadListener { url, _, contentDisposition, mimeType, _ ->
            if (url.startsWith("blob:${Ddl3DInstallation.ORIGIN}/")) {
                val name = URLUtil.guessFileName(url, contentDisposition, mimeType)
                send(JSONObject().put("kind", "download").put("url", url).put("name", name))
            }
        }
    }

    override fun mount(mountId: String) {
        port?.close(); port = null
        waiting.clear()
        mounted = mountId
        webView.loadUrl(Ddl3DInstallation.hostUrl(registered, mountId, title))
    }

    override fun deliver(message: JSONObject) {
        if (message.optString("type") == "load-work") {
            // The viewer reports the SHA-256 of the exact input it read; this is the
            // one sent, so the two lines in the log show the input arrived whole.
            val digest = java.security.MessageDigest.getInstance("SHA-256")
                .digest(message.optString("inputJson").toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
            Log.i(TAG, "load-work request=${message.opt("requestId")} digest=$digest bytes=${message.optString("inputJson").toByteArray().size}")
        }
        send(JSONObject().put("kind", "deliver").put("message", message))
    }

    override fun focusViewer() {
        webView.requestFocus()
        send(JSONObject().put("kind", "focus"))
    }

    fun close() {
        controller.unmount(this)
        port?.close(); port = null
        webView.stopLoading()
        webView.destroy()
    }

    private fun send(message: JSONObject) {
        val port = port ?: run { waiting += message; return }
        port.postMessage(WebMessage(message.toString()))
    }

    private fun openChannel() {
        port?.close()
        val (ours, theirs) = webView.createWebMessageChannel()
        ours.setWebMessageCallback(object : WebMessagePort.WebMessageCallback() {
            override fun onMessage(port: WebMessagePort, message: WebMessage) {
                val body = runCatching { JSONObject(message.data ?: return) }.getOrNull() ?: return
                when (body.optString("type")) {
                    "download" -> if (body.optString("mountId") == mounted) share(body)
                    "download-failed" -> onShareFailed()
                    else -> {
                        // What the viewer made of the work, for the device check: no Score, only its digest.
                        if (body.optString("type") in setOf("rendered", "failed", "host-failed")) {
                            Log.i(TAG, "${body.optString("type")} request=${body.opt("requestId")} digest=${body.optString("inputDigest")} " +
                                "objects=${body.opt("objectCount")} triangles=${body.opt("triangles")} ms=${body.opt("preparationMs")} " +
                                "reason=${body.optString("reason")}")
                        }
                        controller.receive(body)
                    }
                }
            }
        }, Handler(Looper.getMainLooper()))
        port = ours
        webView.postWebMessage(WebMessage(NATIVE_PORT, arrayOf(theirs)), Uri.parse(Ddl3DInstallation.ORIGIN))
        waiting.toList().also { waiting.clear() }.forEach(::send)
    }

    /** One saved PNG or GLB, to the share sheet the exports use. */
    private fun share(body: JSONObject) {
        val dataUrl = body.optString("dataUrl")
        val comma = dataUrl.indexOf(',')
        if (!dataUrl.startsWith("data:") || comma < 0 || !dataUrl.substring(0, comma).endsWith(";base64")) return onShareFailed()
        if ((dataUrl.length - comma) / 4L * 3 > MAXIMUM_DOWNLOAD_BYTES) return onShareFailed()
        val bytes = runCatching { Base64.decode(dataUrl.substring(comma + 1), Base64.DEFAULT) }.getOrNull() ?: return onShareFailed()
        val name = body.optString("name").takeIf { Regex("^[A-Za-z0-9._-]{1,128}$").matches(it) } ?: "inku-3d"
        val mimeType = body.optString("mimeType").ifEmpty { "application/octet-stream" }
        runCatching {
            val file = File(exportCacheDir(context), name)
            file.writeBytes(bytes)
            val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
            launchShareIntent(context, SharePayload(uri, mimeType, "inku 3D", file.name, "Export inku 3D"))
        }.onFailure { onShareFailed() }
    }

    private fun serve(url: Uri): WebResourceResponse {
        val path = url.path.orEmpty()
        val asset = if (url.scheme == "https" && url.host == HOST) Ddl3DInstallation.assetFor(path, registered) else null
        val stream = asset?.let { runCatching { context.assets.open(it) }.getOrNull() }
            ?: return WebResourceResponse("text/plain", "utf-8", 404, "Not Found", mapOf("Cache-Control" to "no-store"),
                ByteArrayInputStream(ByteArray(0)))
        val type = Ddl3DInstallation.mimeType(asset)
        val encoding = if (type.startsWith("text/") || type == "application/json") "utf-8" else null
        return WebResourceResponse(type, encoding, 200, "OK", mapOf("Cache-Control" to "no-store"), stream)
    }

    private companion object {
        val HOST: String = Uri.parse(Ddl3DInstallation.ORIGIN).host!!
    }
}

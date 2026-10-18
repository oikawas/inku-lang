package app.inku.mobile.ui.ddl3d

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.pipeline.NativePipelineBridge
import org.json.JSONObject

/**
 * The work's experimental 3D view (Web `features/experimental-3d`, `inku.ddl3d.v1`).
 * The viewer is Web's registered build, copied unchanged into the app's assets at
 * build time (`syncDdl3dViewer`) and never committed; the app only connects it.
 * Shapes, depth and paint are the viewer's: nothing here draws.
 */
object Ddl3DInstallation {
    /** The viewer and its parent page share one https origin, so the viewer's same-origin checks hold. */
    const val ORIGIN = "https://appassets.androidplatform.net"
    const val ASSET_ROOT = "ddl3d"

    data class Registered(
        /** Web's `viewerUrl`, `/experimental/ddl-3d/<build>/index.html`. */
        val viewerPath: String,
        val build: String,
    )

    private val VIEWER_PATH = Regex("^/experimental/ddl-3d/([a-zA-Z0-9][a-zA-Z0-9._-]{0,63})/index\\.html$")

    /** Web `configuredViewer`: only a versioned path of the registered form names a build. */
    fun build(ofViewerPath: Any?): String? =
        (ofViewerPath as? String)?.let { VIEWER_PATH.find(it)?.groupValues?.get(1) }

    /**
     * The registration in the app's copy. An empty `viewerUrl`, or a copy without
     * the build it names, turns the view off: no switch, no viewer file read.
     */
    fun registration(read: (String) -> ByteArray?): Registered? {
        val text = read("$ASSET_ROOT/installation.json")?.toString(Charsets.UTF_8) ?: return null
        val path = runCatching { JSONObject(text).opt("viewerUrl") }.getOrNull()
        val build = build(path) ?: return null
        read("$ASSET_ROOT/$build/index.html") ?: return null
        return Registered(path as String, build)
    }

    /**
     * The asset behind one path of the origin: the parent page, or one file of
     * the registered build. Nothing else -- no other build, no path outside it.
     */
    fun assetFor(path: String, registered: Registered): String? {
        when (path) {
            "/host.html", "/host.js", "/host.css" -> return "$ASSET_ROOT/host${path}"
        }
        val prefix = "/experimental/ddl-3d/${registered.build}/"
        if (!path.startsWith(prefix)) return null
        val parts = path.removePrefix(prefix).split('/')
        if (parts.isEmpty() || parts.any { part ->
                part.isEmpty() || part == "." || part == ".." ||
                    !part.all { it.isLetterOrDigit() && it.code < 128 || it in "._-" }
            }) return null
        return "$ASSET_ROOT/${registered.build}/" + parts.joinToString("/")
    }

    fun mimeType(path: String): String = when (path.substringAfterLast('.', "").lowercase()) {
        "html" -> "text/html"
        "js" -> "text/javascript"
        "css" -> "text/css"
        "wasm" -> "application/wasm"
        "json" -> "application/json"
        "txt", "ts" -> "text/plain"
        else -> "application/octet-stream"
    }

    /** The host page's address for one mount. */
    fun hostUrl(registered: Registered, mountId: String, title: String): String =
        "$ORIGIN/host.html?mount=${encode(mountId)}&viewer=${encode(registered.viewerPath)}&title=${encode(title)}"

    private fun encode(value: String) = java.net.URLEncoder.encode(value, "UTF-8")
}

/**
 * Web `snapshot()`: the viewer receives the Score and the saved drawing metadata,
 * never application state. The projection is the shared core's (`ddl3d_snapshot`),
 * so the native apps hand the viewer the same text for the same work.
 */
object Ddl3DInput {
    fun snapshot(
        item: HistoryItemEntity,
        core: (ByteArray) -> ByteArray = NativePipelineBridge::ddl3dSnapshot,
    ): Result<String> {
        val request = JSONObject().put("score", item.scoreJson).put("metadata", item.renderMetadataJson)
        val answer = runCatching { JSONObject(core(request.toString().toByteArray(Charsets.UTF_8)).toString(Charsets.UTF_8)) }
            .getOrElse { return Result.failure(Ddl3DInputError("internal_invariant")) }
        answer.optString("json").takeIf { answer.has("json") }?.let { return Result.success(it) }
        return Result.failure(Ddl3DInputError(answer.optString("error").ifEmpty { "invalid_input" }))
    }
}

/** A snapshot the viewer cannot take, named like Web's (`input_budget_exceeded`). */
class Ddl3DInputError(val reason: String) : Exception(reason)

/**
 * Web `protocol.ts` remember/recall: the last camera, thickness, layer depth and
 * background, in memory only and only for the exact same input.
 */
object Ddl3DViewMemory {
    private var previous: Pair<String, String>? = null
    fun remember(input: String, state: String) { previous = input to state }
    fun recall(input: String): String? = previous?.takeIf { it.first == input }?.second
}

/** Web `initialView`: where the 2D canvas stands, so the first front view keeps the frontmost shapes' size. */
data class Ddl3DInitialView(val pixelWidth: Double, val pixelHeight: Double, val panX: Double, val panY: Double, val zoom: Double) {
    /** The viewer's `validInitialView`; an invalid one is left out and the viewer fits by itself. */
    fun message(): JSONObject? {
        if (listOf(pixelWidth, pixelHeight, zoom).any { !it.isFinite() || it <= 0 || it >= 100_000 }) return null
        if (listOf(panX, panY).any { !it.isFinite() || kotlin.math.abs(it) >= 100_000 }) return null
        return JSONObject().put("pixelWidth", pixelWidth).put("pixelHeight", pixelHeight)
            .put("panX", panX).put("panY", panY).put("zoom", zoom)
    }
}

/** The parent page the controller talks through; the identities, requests and deadline are the controller's. */
interface Ddl3DPage {
    /** Open a fresh viewer frame named [mountId]. */
    fun mount(mountId: String)
    /** Post one protocol message to the viewer frame. */
    fun deliver(message: JSONObject)
    /** Give the viewer frame the keyboard. */
    fun focusViewer()
}

/** Schedules the deadline; the returned function cancels it. */
fun interface Ddl3DTimer {
    fun schedule(delayMs: Long, action: () -> Unit): () -> Unit
}

/** What the viewer reported for the request on screen (`rendered`). */
data class Ddl3DRendered(val requestId: Int, val inputDigest: String, val objectCount: Int, val triangles: Int, val bytes: Int, val preparationMs: Int)

/**
 * Web `Ddl3DHost.svelte` without its markup, as Swift's `Ddl3DController`: each
 * appearance of the 3D view is a new mount with its own identity, request numbers
 * and 15-second deadline. Messages from another mount or an earlier request
 * change nothing.
 */
class Ddl3DController(private val timer: Ddl3DTimer, private val random: () -> Long = { kotlin.random.Random.nextLong() }) {
    companion object {
        const val PROTOCOL = "inku.ddl3d.v1"
        const val DEADLINE_MS = 15_000L
        private val HEX64 = Regex("^[0-9a-f]{64}$")
    }

    var preparing by mutableStateOf(false)
        private set
    var failure by mutableStateOf<String?>(null)
        private set
    var ready by mutableStateOf(false)
        private set
    /** The viewer's `displayZoom` from its last view state. */
    var displayZoom by mutableDoubleStateOf(1.0)
        private set
    var lastRendered by mutableStateOf<Ddl3DRendered?>(null)
        private set
    var mountId = ""
        private set
    var requestId = 0
        private set
    /** The 2D canvas at the time of each load. */
    var initialView: Ddl3DInitialView? = null
    /** Called for the viewer's `return-2d` (its back button and Esc). */
    var onReturn: (() -> Unit)? = null

    private var page: Ddl3DPage? = null
    private var base = ""
    private var attempt = 0
    private var input: Result<String>? = null
    private var locale = "ja"
    private var activeInput = ""
    private var cancelTimer: (() -> Unit)? = null

    /** A new 3D view (Web onMount): a fresh identity, then the viewer's ready state within the deadline. */
    fun mount(page: Ddl3DPage) {
        cancelTimer?.invoke()
        this.page = page
        base = "ddl3d-${System.currentTimeMillis().toString(36)}-${java.lang.Long.toUnsignedString(random(), 36)}"
        attempt = 0; requestId = 0; ready = false; failure = null; preparing = true; displayZoom = 1.0; lastRendered = null
        mountId = "$base-$attempt"
        waitForViewer()
        page.mount(mountId)
        // A snapshot that cannot be taken fails at once, as Web's does; a good one waits for the viewer.
        load()
    }

    /** The 3D view went away (Web onDestroy). The input goes too, so the next mount shows its own. */
    fun unmount(page: Ddl3DPage) {
        if (this.page !== page) return
        send("dispose")
        cancelTimer?.invoke(); cancelTimer = null
        this.page = null; ready = false; preparing = false
        input = null; activeInput = ""
    }

    /** Web `retry()`: a new frame under the next mount identity. */
    fun retry() {
        val page = page ?: return
        ready = false; failure = null; preparing = true; attempt += 1
        mountId = "$base-$attempt"
        waitForViewer()
        page.mount(mountId)
    }

    /** The work and language to show. A changed snapshot or language is a new request (Web `$effect`). */
    fun update(input: Result<String>, locale: String) {
        if (sameInput(this.input, input) && this.locale == locale) return
        this.input = input; this.locale = locale
        load()
    }

    /** Web `setZoom`: the viewer's own zoom, bounded as there. */
    fun zoom(to: Double) {
        if (!ready || !to.isFinite()) return
        send("viewer-command", JSONObject().put("action", "zoom").put("value", to.coerceIn(0.25, 10.0)))
    }

    /** Web `fit`: back to the front view matched to the 2D canvas. */
    fun reset() {
        if (!ready) return
        send("viewer-command", JSONObject().put("action", "reset"))
    }

    /** One relayed message from the page, which already checked origin, source window and protocol. */
    fun receive(body: JSONObject) {
        val type = body.optString("type")
        if (type.isEmpty() || body.optString("mountId") != mountId || page == null) return
        when (type) {
            "host-failed" -> { fail(body.optString("reason").ifEmpty { "viewer_load_failed" }); return }
            "protocol-mismatch" -> { fail("protocol_mismatch"); return }
            "ready" -> {
                // Web sets `ready` and its effect runs only on the change.
                if (!ready) { ready = true; page?.focusViewer(); load() }
                return
            }
        }
        if ((body.opt("requestId") as? Int) != requestId) return
        when (type) {
            "rendered" -> {
                val digest = body.optString("inputDigest")
                if (!HEX64.matches(digest)) return
                cancelTimer?.invoke(); cancelTimer = null
                preparing = false; failure = null
                lastRendered = Ddl3DRendered(requestId, digest, body.optInt("objectCount", -1), body.optInt("triangles", -1),
                    body.optInt("bytes", -1), body.optInt("preparationMs", -1))
            }
            "failed" -> body.optString("reason").takeIf { body.has("reason") }?.let(::fail)
            "view-state" -> {
                val state = body.optString("viewState").takeIf { it.isNotEmpty() } ?: return
                Ddl3DViewMemory.remember(activeInput, state)
                displayZoom = runCatching { JSONObject(state).optDouble("displayZoom") }.getOrNull()
                    ?.takeIf { it.isFinite() && it > 0 } ?: 1.0
            }
            "return-2d" -> onReturn?.invoke()
        }
    }

    /** The deadline or the page itself failed (Web `failure`), shown with retry and return to 2D. */
    fun fail(reason: String) {
        cancelTimer?.invoke(); cancelTimer = null
        failure = reason.take(500); preparing = false
    }

    private fun load() {
        val input = input ?: return
        if (page == null) return
        val json = input.getOrElse { fail((it as? Ddl3DInputError)?.reason ?: "invalid_input"); return }
        if (!ready) return
        activeInput = json; requestId += 1; failure = null; preparing = true
        waitForViewer()
        val message = JSONObject().put("inputJson", json).put("locale", if (locale == "en") "en" else "ja").put("theme", "light")
        Ddl3DViewMemory.recall(json)?.let { state -> runCatching { JSONObject(state) }.getOrNull()?.let { message.put("viewState", it) } }
        initialView?.message()?.let { message.put("initialView", it) }
        send("load-work", message)
    }

    private fun waitForViewer() {
        cancelTimer?.invoke()
        cancelTimer = timer.schedule(DEADLINE_MS) { fail("viewer_timeout") }
    }

    private fun send(type: String, payload: JSONObject = JSONObject()) {
        val page = page ?: return
        payload.put("protocol", PROTOCOL).put("type", type).put("mountId", mountId).put("requestId", requestId)
        page.deliver(payload)
    }

    private fun sameInput(a: Result<String>?, b: Result<String>): Boolean {
        if (a == null) return false
        return a.getOrNull() == b.getOrNull() &&
            (a.exceptionOrNull() as? Ddl3DInputError)?.reason == (b.exceptionOrNull() as? Ddl3DInputError)?.reason
    }
}

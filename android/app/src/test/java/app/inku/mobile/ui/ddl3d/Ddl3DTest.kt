package app.inku.mobile.ui.ddl3d

import app.inku.mobile.pipeline.NativePipelineBridge
import java.io.File
import java.security.MessageDigest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class Ddl3DTest {
    private fun property(name: String) = File(requireNotNull(System.getProperty(name)) { name })

    /** The app's copy is Web's registered build, file by file, with the registration and the parent page. */
    @Test
    fun theCopyIsTheRegisteredWebBuildUnchanged() {
        val registration = property("inku.ddl3dRegistration")
        val copy = property("inku.ddl3dCopy")
        assertEquals(registration.readText(), File(copy, "installation.json").readText())
        val build = Ddl3DInstallation.build(JSONObject(registration.readText()).opt("viewerUrl"))
        if (build == null) {
            // Web turned the view off: the copy holds the registration and the page only.
            assertEquals(setOf("installation.json", "host"), copy.list()!!.toSet())
            return
        }
        val source = File(registration.parentFile.parentFile.parentFile.parentFile.parentFile, "static/experimental/ddl-3d/$build")
        val files = source.walkTopDown().filter { it.isFile }.map { it.relativeTo(source).path }.sorted().toList()
        assertTrue("the registered build has files", files.isNotEmpty())
        for (path in files) {
            assertEquals(path, sha256(File(source, path).readBytes()), sha256(File(copy, "$build/$path").readBytes()))
        }
        assertEquals(files, File(copy, build).walkTopDown().filter { it.isFile }.map { it.relativeTo(File(copy, build)).path }.sorted().toList())
        val registered = Ddl3DInstallation.registration { path -> File(copy.parentFile, path).takeIf { it.isFile }?.readBytes() }
        assertEquals(build, registered?.build)
        println("compared ${files.size} files of $build")
    }

    @Test
    fun onlyTheRegisteredFormNamesABuildAndOnlyItsFilesAreServed() {
        assertEquals("b-1.0_x", Ddl3DInstallation.build("/experimental/ddl-3d/b-1.0_x/index.html"))
        listOf("", "/experimental/ddl-3d/../index.html", "/experimental/ddl-3d/.b/index.html", "https://x/experimental/ddl-3d/b/index.html", 3)
            .forEach { assertNull("$it", Ddl3DInstallation.build(it)) }
        val registered = Ddl3DInstallation.Registered("/experimental/ddl-3d/b1/index.html", "b1")
        assertEquals("ddl3d/b1/wasm/a.wasm", Ddl3DInstallation.assetFor("/experimental/ddl-3d/b1/wasm/a.wasm", registered))
        assertEquals("ddl3d/host/host.js", Ddl3DInstallation.assetFor("/host.js", registered))
        listOf("/experimental/ddl-3d/b2/index.html", "/experimental/ddl-3d/b1/../b2/index.html", "/experimental/ddl-3d/b1/",
            "/experimental/ddl-3d/b1/a//b.js", "/installation.json", "/experimental/ddl-3d/b1/%2e%2e/x")
            .forEach { assertNull(it, Ddl3DInstallation.assetFor(it, registered)) }
        assertEquals("application/wasm", Ddl3DInstallation.mimeType("ddl3d/b1/wasm/a.wasm"))
        assertEquals("text/javascript", Ddl3DInstallation.mimeType("ddl3d/b1/assets/i.js"))
        val empty = mapOf("ddl3d/installation.json" to """{"viewerUrl":""}""".toByteArray())
        assertNull(Ddl3DInstallation.registration { empty[it] })
    }

    /** The shared core's projection, through the same JNI entry the app calls. */
    @Test
    fun theCoreProjectsTheSolidsFixtureAsWebDoes() {
        val fixture = property("inku.ddl3dFixture").readText()
        val score = JSONObject(fixture).getJSONObject("score").toString()
        val answer = JSONObject(NativePipelineBridge.ddl3dSnapshot(
            JSONObject().put("score", score).put("metadata", fixture).toString().toByteArray()).toString(Charsets.UTF_8))
        val json = answer.getString("json")
        assertTrue(json.startsWith("{\"score\":{"))
        // Above 2^53, kept as written.
        assertTrue(json.contains("\"render_seed\":\"9007199254740993\""))
        assertTrue(json.contains("\"composition_seed\":\"9007199254740995\""))
        val unsafe = JSONObject(NativePipelineBridge.ddl3dSnapshot(
            """{"score":"{}","metadata":"{\"render_seed\":9007199254740993}"}""".toByteArray()).toString(Charsets.UTF_8))
        assertEquals("unsafe_numeric_seed", unsafe.getString("error"))
    }

    private class Page : Ddl3DPage {
        val mounts = mutableListOf<String>()
        val sent = mutableListOf<JSONObject>()
        var focused = 0
        override fun mount(mountId: String) { mounts += mountId }
        override fun deliver(message: JSONObject) { sent += message }
        override fun focusViewer() { focused += 1 }
    }

    private class Clock : Ddl3DTimer {
        var pending: (() -> Unit)? = null
        override fun schedule(delayMs: Long, action: () -> Unit): () -> Unit {
            assertEquals(Ddl3DController.DEADLINE_MS, delayMs)
            pending = action
            return { if (pending === action) pending = null }
        }
    }

    private fun message(controller: Ddl3DController, type: String, vararg extra: Pair<String, Any>) =
        JSONObject().put("type", type).put("mountId", controller.mountId).apply { extra.forEach { put(it.first, it.second) } }

    @Test
    fun aMountLoadsOnReadyAndIgnoresStaleMessages() {
        val clock = Clock()
        val page = Page()
        val controller = Ddl3DController(clock) { 7 }
        var returned = 0
        controller.onReturn = { returned += 1 }
        controller.mount(page)
        controller.update(Result.success("{\"score\":{}}"), "ja")
        assertEquals(listOf(controller.mountId), page.mounts)
        assertTrue(page.sent.isEmpty())
        controller.receive(message(controller, "ready", "requestId" to 0))
        assertEquals(1, page.focused)
        val load = page.sent.single()
        assertEquals("load-work", load.getString("type"))
        assertEquals(Ddl3DController.PROTOCOL, load.getString("protocol"))
        assertEquals(1, load.getInt("requestId"))
        assertEquals("{\"score\":{}}", load.getString("inputJson"))
        // Another mount and an earlier request change nothing.
        controller.receive(JSONObject().put("type", "failed").put("mountId", "other").put("requestId", 1).put("reason", "x"))
        controller.receive(message(controller, "failed", "requestId" to 0, "reason" to "x"))
        assertNull(controller.failure)
        controller.receive(message(controller, "rendered", "requestId" to 1, "inputDigest" to "a".repeat(64), "objectCount" to 9))
        assertFalse(controller.preparing)
        assertNull(clock.pending)
        assertEquals(9, controller.lastRendered?.objectCount)
        controller.receive(message(controller, "return-2d", "requestId" to 1))
        assertEquals(1, returned)
    }

    @Test
    fun theDeadlineFailsAndRetryMountsAgainAndTheViewStateIsRecalledForTheSameInput() {
        val clock = Clock()
        val page = Page()
        val controller = Ddl3DController(clock) { 9 }
        controller.mount(page)
        controller.update(Result.success("{\"score\":{\"a\":1}}"), "en")
        clock.pending!!.invoke()
        assertEquals("viewer_timeout", controller.failure)
        controller.retry()
        assertEquals(2, page.mounts.size)
        assertTrue(page.mounts[1].endsWith("-1"))
        controller.receive(message(controller, "ready", "requestId" to 0))
        val state = """{"position":[0,0,5],"target":[0,0,0],"zoom":1,"projection":"orthographic","depth":1,"orthoHeight":2,"displayZoom":2.5}"""
        controller.receive(message(controller, "view-state", "requestId" to 1, "viewState" to state))
        assertEquals(2.5, controller.displayZoom, 0.0)
        controller.unmount(page)
        assertEquals("dispose", page.sent.last().getString("type"))
        val again = Page()
        controller.mount(again)
        controller.update(Result.success("{\"score\":{\"a\":1}}"), "en")
        controller.receive(message(controller, "ready", "requestId" to 0))
        val load = again.sent.single()
        assertEquals("en", load.getString("locale"))
        assertEquals(2.5, load.getJSONObject("viewState").getDouble("displayZoom"), 0.0)
    }

    @Test
    fun aSnapshotThatCannotBeTakenFailsAtOnce() {
        val controller = Ddl3DController(Clock())
        val page = Page()
        controller.mount(page)
        controller.update(Result.failure(Ddl3DInputError("input_budget_exceeded")), "ja")
        assertEquals("input_budget_exceeded", controller.failure)
        assertTrue(page.sent.isEmpty())
    }

    /** The viewer's front view is pixelHeight / canvas height px per unit: the picture's height, not the box's. */
    @Test
    fun theFirstViewIsThePictureWhereTheCanvasShowsIt() {
        // A square work in a phone's full screen (411 x 923 dp) fills the width.
        val square = Ddl3DInitialView.ofPicture(411.0, 923.0, 1.0, 1.0, 0.0, 0.0)
        assertEquals(411.0, square.pixelWidth, 1e-9)
        assertEquals(411.0, square.pixelHeight, 1e-9)
        // A wide work in a short box fits the height; the 2D magnification and move go with it.
        val wide = Ddl3DInitialView.ofPicture(400.0, 100.0, 2.0, 1.5, 10.0, -4.0)
        assertEquals(300.0, wide.pixelWidth, 1e-9)
        assertEquals(150.0, wide.pixelHeight, 1e-9)
        assertEquals(10.0, wide.message()!!.getDouble("panX"), 0.0)
        assertEquals(1.5, wide.message()!!.getDouble("zoom"), 0.0)
    }

    /** A web view left at WRAP_CONTENT lays its page out 0 px tall: the 3D view rendered, black (Build148421). */
    @Test
    fun theWebViewFillsItsPlaceSoThePageHasAHeight() {
        val source = listOf("app/src/main/java/app/inku/mobile/ui/ddl3d/Ddl3DWebView.kt", "android/app/src/main/java/app/inku/mobile/ui/ddl3d/Ddl3DWebView.kt",
            "src/main/java/app/inku/mobile/ui/ddl3d/Ddl3DWebView.kt").map(::File).first(File::isFile).readText()
        val init = source.substring(source.indexOf("    init {"), source.indexOf("webView.settings.apply"))
        assertTrue(init.contains("webView.layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)"))
    }

    private fun sha256(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
}

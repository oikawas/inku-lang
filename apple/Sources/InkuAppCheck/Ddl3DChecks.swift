import AppKit
import CryptoKit
import Foundation
import InkuHost
import InkuPersistence
import InkuUI
import WebKit

/// The 3D bridge against the Web's registered viewer (plan swift-task/ddl-3d-20261018, Q1–Q3 and Q5). Offscreen by
/// default: the web view is in no window. `--ddl3d-window` hosts it in a window of this process placed outside every
/// screen. No database, provider or network: the viewer is served under `inku-3d://viewer/` from the copy the app
/// build makes (apple/scripts/sync-ddl3d-viewer.py), read where it is, so the check needs no rebuild after copying
/// and does not depend on whether SwiftPM read the manifest before the copy existed.
@MainActor
func runDdl3DChecks(arguments: [String]) async throws {
    // Each step's line stays in a redirected log even if a later step stops the process.
    setvbuf(stdout, nil, _IOLBF, 0)
    let product = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    // The copy is not committed, so a checkout without it, or with an earlier registration's, stops here.
    let sync = "python3 apple/scripts/sync-ddl3d-viewer.py"
    let copy = product.appendingPathComponent("apple/Sources/InkuUI/Resources/ddl3d", isDirectory: true)
    let webRegistration = product.appendingPathComponent("web/src/lib/features/experimental-3d/installation.json")
    let webViewer = (try JSONSerialization.jsonObject(with: Data(contentsOf: webRegistration)) as? [String: Any])?["viewerUrl"] as? String ?? ""
    guard !webViewer.isEmpty else {
        throw CheckFailure.message("The Web registers no 3D viewer (empty viewerUrl in \(webRegistration.path)); nothing to check")
    }
    guard FileManager.default.fileExists(atPath: copy.appendingPathComponent("installation.json").path) else {
        throw CheckFailure.message("No copy of the 3D viewer at \(copy.path): it is made at build time and not committed. "
            + "Run `\(sync)` (apple/scripts/build-macos.sh runs it), then this check again")
    }
    guard let registration = Ddl3DInstallation.registration(in: copy), registration.viewerPath == webViewer else {
        throw CheckFailure.message("The copy at \(copy.path) is not the Web's registered viewer \(webViewer). Run `\(sync)`, then this check again")
    }
    print("Viewer: \(registration.viewerPath) from \(registration.directory.path)")
    // About inku's 3D entry is read from the copy, not from the notices snapshot.
    guard let notices = Ddl3DViewerNotices(registration: registration) else {
        throw CheckFailure.message("The viewer \(registration.build) carries no readable THIRD_PARTY_NOTICES.txt")
    }
    print("Notices: \(Ddl3DViewerNotices.name) \(notices.build) (\(notices.license)), \(notices.componentCount) components, "
          + "\(notices.text.utf8.count) bytes, SHA-256 \(SHA256.hash(data: Data(notices.text.utf8)).map { String(format: "%02x", $0) }.joined())")

    _ = NSApplication.shared
    NSApp.setActivationPolicy(.prohibited)
    let controller = Ddl3DController()
    let bridge = Ddl3DWebHost(registration: registration, title: "3D", controller: controller)
    bridge.takesFocusInWindow = false
    let console = Ddl3DConsole()
    console.attach(to: bridge.webView)
    let size = NSSize(width: 960, height: 640)
    bridge.webView.frame = NSRect(origin: .zero, size: size)
    var window: NSWindow?
    if arguments.contains("--ddl3d-window") {
        let screens = NSScreen.screens.map(\.frame).reduce(CGRect.null) { $0.union($1) }
        let placed = NSWindow(contentRect: NSRect(x: screens.maxX + 4000, y: screens.maxY + 4000, width: size.width, height: size.height),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        placed.isReleasedWhenClosed = false
        placed.contentView = bridge.webView
        placed.orderFrontRegardless()
        window = placed
        print("Host: a borderless window of this process at \(placed.frame), outside the screens \(screens)")
    } else {
        print("Host: no window (off-screen web view \(Int(size.width))×\(Int(size.height)))")
    }
    defer { bridge.close(); window?.contentView = nil; window?.close() }
    let clock = ContinuousClock()
    func wait(_ what: String, seconds: Double, until done: () -> Bool) async throws -> Duration {
        let start = clock.now
        while !done() {
            if clock.now - start > .seconds(seconds) {
                throw CheckFailure.message("\(what) did not arrive within \(seconds) s (failure \(controller.failure ?? "-"), "
                    + "ready \(controller.ready)); console: \(console.lines.suffix(12).joined(separator: " | "))")
            }
            try await Task.sleep(for: .milliseconds(20))
        }
        return clock.now - start
    }
    func ms(_ duration: Duration) -> Int { Int(duration.components.seconds * 1000 + duration.components.attoseconds / 1_000_000_000_000_000) }
    func sha256(_ text: String) -> String { SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined() }

    // Q5: the parent page, the module viewer and its ready state through the app-only scheme.
    controller.theme = "light"
    controller.initialView = Ddl3DInitialView(pixelWidth: 560, pixelHeight: 400, panX: 0, panY: 0, zoom: 1)
    controller.mount(page: bridge)
    let mountedAt = clock.now
    let readyAfter = try await wait("ready", seconds: 15) { controller.ready || controller.failure != nil }
    guard controller.ready else { throw CheckFailure.message("Viewer failed before ready: \(controller.failure ?? "-")") }
    print("Ready after \(ms(readyAfter)) ms (mount \(controller.mountID))")

    // Q1: the fixture's exact text as input → rendered within 15 s, the same SHA-256, 9 objects, triangles.
    let solidsURL = product.appendingPathComponent("experiments/ddl-3d/fixtures/solids.json")
    let solids = try String(contentsOf: solidsURL, encoding: .utf8)
    controller.update(input: .success(solids), locale: "ja")
    let renderedAfter = try await wait("rendered (Q1)", seconds: 16) { controller.lastRendered != nil || controller.failure != nil }
    guard let first = controller.lastRendered else {
        throw CheckFailure.message("Q1: the viewer failed: \(controller.failure ?? "-"); console: \(console.lines.suffix(12))")
    }
    let solidsDigest = sha256(solids)
    print("Q1 rendered after \(ms(renderedAfter)) ms: digest \(first.inputDigest) (Swift \(solidsDigest)), objects \(first.objectCount), "
          + "triangles \(first.triangles), bytes \(first.bytes), preparation \(first.preparationMS) ms, request \(first.requestID)")
    guard renderedAfter < .seconds(15), first.inputDigest == solidsDigest, first.objectCount == 9, first.triangles > 0,
          controller.failure == nil, !controller.preparing else {
        throw CheckFailure.message("Q1 failed: \(first), failure \(controller.failure ?? "-")")
    }

    // Failure (2026-10-18, a trusted click reproduced it): WKWebView drops the viewer's PNG/GLB download link, so no
    // file reaches the app. The save-link script hands it to the shared parent page, which passes the file on.
    var saved: [(name: String, data: Data)] = []
    bridge.onViewerFile = { name, data in saved.append((name, data)) }
    for label in ["PNG", "GLB"] {
        _ = try await bridge.webView.callAsyncJavaScript("""
        const d = document.querySelector('iframe').contentDocument;
        const b = [...d.querySelectorAll('button')].find(x => x.textContent.includes(label));
        if (b) b.click();
        """, arguments: ["label": label], contentWorld: .page)
    }
    _ = try await wait("PNG and GLB saves", seconds: 15) { saved.count >= 2 }
    bridge.onViewerFile = nil
    let prefix = "inku-3d-\(String(first.inputDigest.prefix(12)))"
    let png = saved.first { $0.name.hasSuffix(".png") }, glb = saved.first { $0.name.hasSuffix(".glb") }
    print("Saves: \(saved.map { "\($0.name) \($0.data.count) B" }.joined(separator: ", "))")
    guard saved.count == 2, let png, let glb, png.name == prefix + ".png", glb.name == prefix + ".glb",
          png.data.prefix(4) == Data([0x89, 0x50, 0x4E, 0x47]), glb.data.prefix(4) == Data("glTF".utf8) else {
        throw CheckFailure.message("Saves: the viewer's PNG/GLB did not reach the app as files: \(saved.map(\.name))")
    }

    // Q2: an input that is not a Score → `failed`, the failure display state, and a retry under a new mount.
    let invalid = #"{"score":"not a score"}"#
    controller.update(input: .success(invalid), locale: "ja")
    let failedAfter = try await wait("failed (Q2)", seconds: 16) { controller.failure != nil }
    let reason = controller.failure ?? ""
    print("Q2 failed after \(ms(failedAfter)) ms: \(reason); preparing \(controller.preparing); request \(controller.requestID)")
    guard !reason.isEmpty, !controller.preparing, controller.lastRendered?.requestID == first.requestID else {
        throw CheckFailure.message("Q2: expected a failure for a non-Score input, got \(reason) / \(String(describing: controller.lastRendered))")
    }
    let failedMount = controller.mountID
    controller.retry()
    guard controller.mountID != failedMount, controller.failure == nil, controller.preparing, !controller.ready else {
        throw CheckFailure.message("Q2: retry did not start a new mount")
    }
    _ = try await wait("ready after retry", seconds: 15) { controller.ready || controller.failure != nil }
    _ = try await wait("failed again after retry", seconds: 16) { controller.failure != nil }
    print("Q2 retry: new mount \(controller.mountID) ready, the same input failed again: \(controller.failure ?? "-")")

    // Q3: a saved work's snapshot holds only Web snapshot() fields and keeps a seed above 2^53 as its decimal text.
    let fixture = Data(solids.utf8)
    let work = SavedWork(id: "ddl3d-check", at: 1, input: "a work for the 3D check", score: String(decoding: try ExactJSON.rawMember("score", in: fixture), as: UTF8.self),
                         svg: "<svg xmlns=\"http://www.w3.org/2000/svg\"/>", sourceText: "a work for the 3D check", ddl: "place one red circle at center.",
                         stage1Model: "check:model", stage2Model: "check:model", catalogID: "default", renderEngineID: "inku-render",
                         renderEngineVersion: "85", renderColorCatalogID: "default", renderColorCatalogName: "Default",
                         renderColorMap: String(decoding: try ExactJSON.rawMember("render_color_map", in: fixture), as: UTF8.self),
                         renderCanvasAspect: "square", renderCanvasAspectID: "square", renderCanvasAspectRatio: 1.4,
                         renderSeed: "9007199254740993", renderWild: false, compositionSeed: "9007199254740995",
                         interpretationSeed: "77", seedText: "check", renderHash: String(repeating: "a", count: 64),
                         descriptionHash: String(repeating: "b", count: 64), lineageNodeID: "node")
    let snapshot = try Ddl3DInput.snapshot(work)
    let webSource = try String(contentsOf: product.appendingPathComponent("web/src/lib/features/experimental-3d/input.ts"), encoding: .utf8)
    guard let open = webSource.range(of: "const fields = ["), let close = webSource.range(of: "] as const", range: open.upperBound..<webSource.endIndex) else {
        throw CheckFailure.message("Q3: no `fields` list in the Web input.ts")
    }
    let webFields = webSource[open.upperBound..<close.lowerBound].split(separator: "'", omittingEmptySubsequences: false)
        .enumerated().filter { $0.offset % 2 == 1 }.map { String($0.element) }
    guard case .object(let members) = try ExactJSON(data: Data(snapshot.utf8)) else { throw CheckFailure.message("Q3: snapshot is not an object") }
    let keys = Set(members.keys)
    print("Q3 snapshot: \(snapshot.utf8.count) bytes, keys \(members.keys.sorted()); Web fields \(webFields.count); "
          + "absent here \(webFields.filter { !keys.contains($0) })")
    guard webFields == Ddl3DInput.webFields, keys.isSubset(of: Set(webFields)), members["render_seed"] == .string("9007199254740993"),
          members["composition_seed"] == .string("9007199254740995"), snapshot.contains(#""render_seed":"9007199254740993""#) else {
        throw CheckFailure.message("Q3 failed: Web fields \(webFields), Swift \(Ddl3DInput.webFields), keys \(keys.sorted()), seed \(members["render_seed"] ?? .null)")
    }
    controller.retry()
    _ = try await wait("ready for Q3", seconds: 15) { controller.ready || controller.failure != nil }
    controller.update(input: .success(snapshot), locale: "en")
    _ = try await wait("rendered (Q3)", seconds: 16) { (controller.lastRendered?.requestID ?? 0) == controller.requestID || controller.failure != nil }
    guard let arrived = controller.lastRendered, arrived.requestID == controller.requestID, arrived.inputDigest == sha256(snapshot),
          arrived.objectCount == 9 else {
        throw CheckFailure.message("Q3: the snapshot did not arrive intact: \(String(describing: controller.lastRendered)), failure \(controller.failure ?? "-")")
    }
    print("Q3 arrived: digest \(arrived.inputDigest) equals Swift's SHA-256 of the snapshot; objects \(arrived.objectCount), triangles \(arrived.triangles)")

    // The work tab's SwiftUI host: the representable mounts its own viewer and `onChange` hands it the snapshot.
    let hosted = Ddl3DController()
    let host = Ddl3DProbe.hostingView(registration: registration, work: work, controller: hosted, display: DisplaySettings(),
                                      initialView: Ddl3DInitialView(pixelWidth: 560, pixelHeight: 400, panX: 0, panY: 0, zoom: 1),
                                      onReturn: {})
    let viewWindow = NSWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: [.titled, .resizable],
                              backing: .buffered, defer: false)
    viewWindow.isReleasedWhenClosed = false
    host.frame = NSRect(origin: .zero, size: size)
    viewWindow.contentView = host
    defer { viewWindow.contentView = nil; viewWindow.close() }
    let viewAfter = try await wait("rendered through the SwiftUI host", seconds: 16) { hosted.lastRendered != nil || hosted.failure != nil }
    guard let viaView = hosted.lastRendered, viaView.inputDigest == sha256(snapshot), viaView.objectCount == 9,
          !hosted.preparing, hosted.failure == nil, hosted.mountID != controller.mountID else {
        throw CheckFailure.message("The SwiftUI host did not render the work: \(String(describing: hosted.lastRendered)), failure \(hosted.failure ?? "-")")
    }
    print("View: the SwiftUI host (a window of this process, never ordered in) mounted \(hosted.mountID) and rendered the snapshot "
          + "in \(ms(viewAfter)) ms with the same digest; objects \(viaView.objectCount)")

    // Q5 conditions: what carried the module Worker and WASM.
    print("Q5: module Worker and WASM loaded through inku-3d:// (\(window == nil ? "no window" : "a window outside the screens")); "
          + "\(ms(clock.now - mountedAt)) ms in all; console lines \(console.lines.count)")
    if !console.lines.isEmpty { print("Console: " + console.lines.prefix(20).joined(separator: " | ")) }
    print("3D bridge passed: PNG and GLB saves reached the app; Q1 rendered \(first.objectCount) objects with the same digest in \(ms(renderedAfter)) ms; Q2 failed (\(reason)) "
          + "and retried under a new mount; Q3 \(keys.count) of \(webFields.count) Web fields, seeds as decimal text, digest equal; "
          + "the SwiftUI host rendered the same snapshot; Q5 scheme, module Worker and WASM.")
}

/// The pages' console and errors, for a failure report only (the product page installs no such script).
@MainActor
private final class Ddl3DConsole: NSObject, WKScriptMessageHandler {
    private(set) var lines: [String] = []

    func attach(to webView: WKWebView) {
        let source = """
        (() => {
          const send = (level, args) => { try { window.webkit.messageHandlers.ddl3dConsole.postMessage(
            (window === window.top ? 'parent ' : 'viewer ') + level + ': ' + args.map(a => { try { return typeof a === 'string' ? a : JSON.stringify(a); } catch { return String(a); } }).join(' ')); } catch {} };
          for (const level of ['log', 'warn', 'error']) { const original = console[level]; console[level] = (...args) => { send(level, args); original.apply(console, args); }; }
          window.addEventListener('error', event => send('error-event', [event.message, event.filename, event.lineno]));
          window.addEventListener('unhandledrejection', event => send('rejection', [String(event.reason)]));
        })();
        """
        webView.configuration.userContentController.addUserScript(WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: false))
        webView.configuration.userContentController.add(self, name: "ddl3dConsole")
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        if let line = message.body as? String { lines.append(String(line.prefix(400))) }
    }
}

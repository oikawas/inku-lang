import Foundation
import InkuHost
import InkuPersistence
import Observation

/// The work tab's experimental 3D view (Web `features/experimental-3d`, `inku.ddl3d.v1`). The viewer is the Web's
/// registered distribution, copied unchanged at build time and never committed (`apple/scripts/sync-ddl3d-viewer.py`,
/// which `apple/scripts/build-macos.sh` runs); the app only connects it. Shapes, depth and paint stay the viewer's:
/// nothing here draws.
public enum Ddl3DInstallation {
    /// The viewer and its parent page are served under one app-only origin, so the viewer's same-origin checks
    /// (`main.ts`) hold. A `file:` page would have the opaque origin `null`.
    public static let scheme = "inku-3d"
    public static let host = "viewer"

    public struct Registered: Sendable, Equatable {
        /// The Web's `viewerUrl`, `/experimental/ddl-3d/<build>/index.html`.
        public let viewerPath: String
        public let build: String
        /// The bundled copy of `web/static/experimental/ddl-3d/<build>/`.
        public let directory: URL
    }

    /// Web `configuredViewer`: only a versioned path of the registered form names a build; anything else is none.
    public static func build(ofViewerPath value: Any?) -> String? {
        guard let value = value as? String else { return nil }
        let prefix = "/experimental/ddl-3d/", suffix = "/index.html"
        guard value.hasPrefix(prefix), value.hasSuffix(suffix), value.count > prefix.count + suffix.count else { return nil }
        let name = String(value.dropFirst(prefix.count).dropLast(suffix.count))
        func plain(_ scalar: Unicode.Scalar) -> Bool {
            scalar.isASCII && (("a"..."z").contains(scalar) || ("A"..."Z").contains(scalar) || ("0"..."9").contains(scalar))
        }
        guard let first = name.unicodeScalars.first, plain(first), name.unicodeScalars.count <= 64,
              name.unicodeScalars.allSatisfy({ plain($0) || $0 == "." || $0 == "_" || $0 == "-" }) else { return nil }
        return name
    }

    /// The registration bundled with the app. An empty `viewerUrl`, or a build made without the copy (a plain
    /// `swift build`), turns the view off: no switch, no viewer file read.
    public static let registered: Registered? = {
        guard let root = Bundle.module.url(forResource: "ddl3d", withExtension: nil) else { return nil }
        return registration(in: root)
    }()

    /// The registration in a copy of the viewer (a `ddl3d` folder): its `installation.json` and the build it names.
    public static func registration(in root: URL) -> Registered? {
        guard let data = try? Data(contentsOf: root.appendingPathComponent("installation.json")),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let path = object["viewerUrl"] as? String, let build = build(ofViewerPath: path) else { return nil }
        let directory = root.appendingPathComponent(build, isDirectory: true)
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: directory.appendingPathComponent("index.html").path, isDirectory: &isDirectory),
              !isDirectory.boolValue else { return nil }
        return Registered(viewerPath: path, build: build, directory: directory)
    }
}

/// A snapshot the viewer cannot take, named like the Web's (`input_budget_exceeded`).
public struct Ddl3DInputError: Error, Equatable, Sendable {
    public let reason: String
}

/// Web `snapshot()`: the experiment receives the Score and the saved drawing metadata, never application state.
public enum Ddl3DInput {
    /// The Web's fields in its order (`input.ts`). Saved works here carry no render build number or DDL versions,
    /// so the app's snapshot holds a subset of them.
    public static let webFields = ["score", "render_seed", "composition_seed", "render_wild", "render_canvas_aspect_id",
                                   "render_canvas_aspect_ratio", "render_canvas_aspect", "render_color_map",
                                   "render_color_catalog_id", "render_engine_id", "render_engine_version",
                                   "render_build_number", "ddl_version", "ddl_engine_version"]
    public static let maximumBytes = 16 * 1024 * 1024

    /// The saved Score and color map go in as their stored JSON text; seeds stay decimal strings and never pass
    /// through a binary number, so 2^53 + 1 arrives as written.
    public static func snapshot(_ work: SavedWork) throws(Ddl3DInputError) -> String {
        var members: [(String, String)] = []
        let score = work.score.trimmingCharacters(in: .whitespacesAndNewlines)
        guard case .object = try? ExactJSON(data: Data(score.utf8)) else { throw Ddl3DInputError(reason: "invalid_score_json") }
        members.append(("score", score))
        func string(_ key: String, _ value: String?) { if let value { members.append((key, ExactJSON.string(value).text)) } }
        string("render_seed", work.renderSeed)
        string("composition_seed", work.compositionSeed)
        if let wild = work.renderWild { members.append(("render_wild", wild ? "true" : "false")) }
        string("render_canvas_aspect_id", work.renderCanvasAspectID)
        if let ratio = work.renderCanvasAspectRatio, ratio.isFinite { members.append(("render_canvas_aspect_ratio", "\(ratio)")) }
        string("render_canvas_aspect", work.renderCanvasAspect)
        // Server reads an unreadable stored map as null, and the Web leaves a null out.
        if let map = work.renderColorMap?.trimmingCharacters(in: .whitespacesAndNewlines),
           let value = try? ExactJSON(data: Data(map.utf8)), value != .null {
            members.append(("render_color_map", map))
        }
        string("render_color_catalog_id", work.renderColorCatalogID)
        string("render_engine_id", work.renderEngineID)
        string("render_engine_version", work.renderEngineVersion)
        let json = "{" + members.map { ExactJSON.string($0.0).text + ":" + $0.1 }.joined(separator: ",") + "}"
        guard json.utf8.count <= maximumBytes else { throw Ddl3DInputError(reason: "input_budget_exceeded") }
        return json
    }
}

/// Web `protocol.ts` remember/recall: the last camera, thickness, layer depth and background, in memory only and
/// only for the exact same input. A reload of the app forgets it.
@MainActor
enum Ddl3DViewMemory {
    private static var previous: (input: String, state: String)?
    static func remember(_ input: String, state: String) { previous = (input, state) }
    static func recall(_ input: String) -> String? { previous?.input == input ? previous?.state : nil }
}

/// Web `initialView`: where the 2D canvas stands, so the first front view keeps the frontmost shapes' size.
public struct Ddl3DInitialView: Equatable, Sendable {
    public var pixelWidth: Double
    public var pixelHeight: Double
    public var panX: Double
    public var panY: Double
    public var zoom: Double

    public init(pixelWidth: Double, pixelHeight: Double, panX: Double, panY: Double, zoom: Double) {
        self.pixelWidth = pixelWidth; self.pixelHeight = pixelHeight; self.panX = panX; self.panY = panY; self.zoom = zoom
    }

    /// The viewer's `validInitialView`; an invalid one is left out and the viewer fits by itself.
    var message: [String: Double]? {
        guard [pixelWidth, pixelHeight, zoom].allSatisfy({ $0.isFinite && $0 > 0 && $0 < 100_000 }),
              [panX, panY].allSatisfy({ $0.isFinite && abs($0) < 100_000 }) else { return nil }
        return ["pixelWidth": pixelWidth, "pixelHeight": pixelHeight, "panX": panX, "panY": panY, "zoom": zoom]
    }
}

/// The parent page the controller talks through. It owns the viewer frame and relays messages with the page's
/// exact origin; the identities, requests and deadline are the controller's.
@MainActor
public protocol Ddl3DPage: AnyObject {
    /// Open a fresh viewer frame named `mountID`.
    func mount(_ mountID: String)
    /// Post one protocol message to the viewer frame.
    func deliver(_ message: [String: Any])
    /// Give the viewer frame the keyboard, so its keys (Esc returns to 2D) work at once.
    func focusViewer()
}

/// What the viewer reported for the request on screen (`rendered`).
public struct Ddl3DRendered: Equatable, Sendable {
    public let requestID: Int
    public let inputDigest: String
    public let objectCount: Int
    public let triangles: Int
    public let bytes: Int
    public let preparationMS: Int
}

/// Web `Ddl3DHost.svelte` without its markup: one controller serves the work tab, and each appearance of the 3D view
/// is a new mount with its own identity, request numbers and 15-second deadline. Messages from another mount or an
/// earlier request change nothing.
@MainActor @Observable
public final class Ddl3DController {
    public static let protocolName = "inku.ddl3d.v1"
    public static let deadline: Duration = .seconds(15)

    public private(set) var preparing = false
    public private(set) var failure: String?
    public private(set) var ready = false
    /// The viewer's `displayZoom` from its last view state; the work tab's zoom capsule shows and steps it.
    public private(set) var displayZoom: Double = 1
    public private(set) var lastRendered: Ddl3DRendered?
    public private(set) var mountID = ""
    public private(set) var requestID = 0
    /// The 2D canvas at the time of each load (Web reads it untracked).
    public var initialView: Ddl3DInitialView?
    public var theme = "light"
    /// Called for the viewer's `return-2d` (its back button and Esc).
    public var onReturn: (() -> Void)?

    private var page: Ddl3DPage?
    private var base = ""
    private var attempt = 0
    private var input: Result<String, Ddl3DInputError>?
    private var locale = "ja"
    private var activeInput = ""
    private var timer: Task<Void, Never>?

    public init() {}

    /// A new 3D view (Web onMount): a fresh identity, then the viewer's ready state within the deadline.
    public func mount(page: Ddl3DPage) {
        timer?.cancel()
        self.page = page
        base = "ddl3d-\(String(UInt64(Date().timeIntervalSince1970 * 1000), radix: 36))-\(String(UInt64.random(in: 0...UInt64.max), radix: 36))"
        attempt = 0; requestID = 0; ready = false; failure = nil; preparing = true; displayZoom = 1; lastRendered = nil
        mountID = "\(base)-\(attempt)"
        waitForViewer()
        page.mount(mountID)
        // A snapshot that cannot be taken fails at once, as the Web's does; a good one waits for the viewer.
        load()
    }

    /// The 3D view went away (Web onDestroy): tell the viewer, stop the deadline, keep nothing of the mount.
    /// The input goes too: the next view hands over its own, as a new Web host derives its own, so an earlier
    /// work's snapshot (or its failure) never shows under the next mount.
    public func unmount(page: Ddl3DPage) {
        guard self.page === page else { return }
        send("dispose")
        timer?.cancel(); timer = nil
        self.page = nil; ready = false; preparing = false
        input = nil; activeInput = ""
    }

    /// Web `retry()`: a new frame under the next mount identity.
    public func retry() {
        guard let page else { return }
        ready = false; failure = nil; preparing = true; attempt += 1
        mountID = "\(base)-\(attempt)"
        waitForViewer()
        page.mount(mountID)
    }

    /// The work and language to show. A changed snapshot or language is a new request (Web `$effect`).
    public func update(input: Result<String, Ddl3DInputError>, locale: String) {
        guard self.input != input || self.locale != locale else { return }
        self.input = input; self.locale = locale
        load()
    }

    /// Web `ddl3dZoomControls.setZoom`: the viewer's own zoom, bounded as there.
    public func zoom(to value: Double) {
        guard ready, value.isFinite else { return }
        send("viewer-command", ["action": "zoom", "value": min(10, max(0.25, value))])
    }

    /// Web `ddl3dZoomControls.fit`: back to the front view matched to the 2D canvas.
    public func reset() {
        guard ready else { return }
        send("viewer-command", ["action": "reset"])
    }

    /// One relayed message from the page. The page already checked origin, source window and protocol.
    public func receive(_ body: [String: Any]) {
        guard let type = body["type"] as? String, body["mountId"] as? String == mountID, page != nil else { return }
        switch type {
        case "host-failed": fail((body["reason"] as? String) ?? "viewer_load_failed"); return
        case "protocol-mismatch": fail("protocol_mismatch"); return
        case "ready":
            // Web sets `ready` and its effect runs only on the change; a second ready loads nothing again.
            if !ready { ready = true; page?.focusViewer(); load() }
            return
        default: break
        }
        guard (body["requestId"] as? Int) == requestID else { return }
        switch type {
        case "rendered":
            guard let digest = body["inputDigest"] as? String, digest.count == 64,
                  digest.unicodeScalars.allSatisfy({ ("0"..."9").contains($0) || ("a"..."f").contains($0) }) else { return }
            timer?.cancel(); timer = nil
            preparing = false; failure = nil
            lastRendered = Ddl3DRendered(requestID: requestID, inputDigest: digest, objectCount: body["objectCount"] as? Int ?? -1,
                                         triangles: body["triangles"] as? Int ?? -1, bytes: body["bytes"] as? Int ?? -1,
                                         preparationMS: body["preparationMs"] as? Int ?? -1)
        case "failed":
            guard let reason = body["reason"] as? String else { return }
            fail(reason)
        case "view-state":
            guard let state = body["viewState"] as? String else { return }
            Ddl3DViewMemory.remember(activeInput, state: state)
            if let object = try? JSONSerialization.jsonObject(with: Data(state.utf8)) as? [String: Any] {
                displayZoom = (object["displayZoom"] as? Double).flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? 1
            }
        case "return-2d":
            onReturn?()
        default: break
        }
    }

    /// The deadline or the page itself failed (Web `failure`), shown with retry and return to 2D.
    public func fail(_ reason: String) {
        timer?.cancel(); timer = nil
        failure = String(reason.prefix(500)); preparing = false
    }

    private func load() {
        guard let input, page != nil else { return }
        switch input {
        case .failure(let error):
            fail(error.reason)
        case .success(let json):
            guard ready else { return }
            activeInput = json; requestID += 1; failure = nil; preparing = true
            waitForViewer()
            var message: [String: Any] = ["inputJson": json, "locale": locale == "en" ? "en" : "ja",
                                          "theme": theme == "dark" ? "dark" : "light"]
            if let state = Ddl3DViewMemory.recall(json),
               let object = try? JSONSerialization.jsonObject(with: Data(state.utf8)) as? [String: Any] {
                message["viewState"] = object
            }
            if let initial = initialView?.message { message["initialView"] = initial }
            send("load-work", message)
        }
    }

    private func waitForViewer() {
        timer?.cancel()
        timer = Task { [weak self] in
            try? await Task.sleep(for: Self.deadline)
            guard !Task.isCancelled, let self else { return }
            self.fail("viewer_timeout")
        }
    }

    private func send(_ type: String, _ payload: [String: Any] = [:]) {
        var message = payload
        message["protocol"] = Self.protocolName; message["type"] = type
        message["mountId"] = mountID; message["requestId"] = requestID
        page?.deliver(message)
    }
}

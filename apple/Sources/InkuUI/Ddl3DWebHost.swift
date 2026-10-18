#if os(macOS)
import AppKit
import SwiftUI
import WebKit

/// The parent page of the viewer frame (Web `Ddl3DHost.svelte`'s iframe and listener). It checks the origin, the
/// frame's window, the mount identity and the protocol, asks for the viewer's ready state when mounted and again
/// after the frame loads, and relays both ways. Request numbers, the deadline and stale results are the controller's.
enum Ddl3DHostPage {
    static let html = """
    <!doctype html>
    <html lang="ja">
    <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self'; frame-src 'self'; base-uri 'none'; form-action 'none'">
    <link rel="stylesheet" href="host.css">
    </head>
    <body><script src="host.js"></script></body>
    </html>
    """

    static let css = """
    html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: transparent; }
    iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: block; }
    """

    static let script = #"""
    'use strict';
    (() => {
      const PROTOCOL = 'inku.ddl3d.v1';
      const query = new URLSearchParams(location.search);
      const mountId = query.get('mount') || '';
      const viewer = query.get('viewer') || '';
      const native = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.ddl3d;
      let frame = null;
      const tell = message => { if (native) native.postMessage(message); };
      const fail = reason => tell({ type: 'host-failed', mountId, reason });
      const hex64 = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
      const count = value => Number.isSafeInteger(value) && value >= 0 ? value : -1;
      // Web protocol.ts validViewState.
      const vector = a => Array.isArray(a) && a.length === 3 && a.every(n => Number.isFinite(n) && Math.abs(n) < 10000);
      const validViewState = v => !!v && typeof v === 'object' && vector(v.position) && vector(v.target)
        && Number.isFinite(v.zoom) && v.zoom >= 0.001 && v.zoom <= 1000
        && (v.projection === 'perspective' || v.projection === 'orthographic') && v.depth >= 0.1 && v.depth <= 3
        && (v.layerSpacing === undefined || (Number.isFinite(v.layerSpacing) && v.layerSpacing >= 0 && v.layerSpacing <= 3))
        && (v.background === undefined || ['none', 'support', 'sky', 'stars', 'paint', 'white', 'black'].includes(v.background))
        && (v.referenceHeight === undefined || (Number.isFinite(v.referenceHeight) && v.referenceHeight > 0 && v.referenceHeight < 1000))
        && (v.displayZoom === undefined || (Number.isFinite(v.displayZoom) && v.displayZoom > 0 && v.displayZoom <= 10000))
        && Number.isFinite(v.orthoHeight) && v.orthoHeight > 0 && v.orthoHeight < 1000;
      function deliver(message) {
        if (!frame || !frame.contentWindow) return;
        try { frame.contentWindow.postMessage(message, location.origin); }
        catch (error) { fail('post_failed:' + ((error && error.name) || 'error')); }
      }
      window.addEventListener('message', event => {
        if (!frame || event.origin !== location.origin || event.source !== frame.contentWindow) return;
        const data = event.data;
        if (!data || typeof data !== 'object' || data.mountId !== mountId) return;
        if (data.protocol !== PROTOCOL) { tell({ type: 'protocol-mismatch', mountId }); return; }
        const requestId = Number.isSafeInteger(data.requestId) ? data.requestId : -1;
        if (data.type === 'ready') tell({ type: 'ready', mountId, requestId });
        else if (data.type === 'rendered' && hex64(data.inputDigest)) {
          tell({ type: 'rendered', mountId, requestId, inputDigest: data.inputDigest, objectCount: count(data.objectCount),
                 triangles: count(data.triangles), bytes: count(data.bytes), preparationMs: count(data.preparationMs) });
        } else if (data.type === 'failed' && typeof data.reason === 'string') {
          tell({ type: 'failed', mountId, requestId, reason: data.reason.slice(0, 500) });
        } else if (data.type === 'view-state' && validViewState(data.viewState)) {
          tell({ type: 'view-state', mountId, requestId, viewState: JSON.stringify(data.viewState) });
        } else if (data.type === 'return-2d') tell({ type: 'return-2d', mountId, requestId });
      });
      const requestReady = () => deliver({ protocol: PROTOCOL, type: 'request-ready', mountId, requestId: 0 });
      window.inku3d = { deliver, focus() { if (frame) frame.focus(); } };
      if (!/^[A-Za-z0-9._-]{1,128}$/.test(mountId)
          || !/^\/experimental\/ddl-3d\/[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}\/index\.html$/.test(viewer)) { fail('invalid_mount'); return; }
      frame = document.createElement('iframe');
      frame.title = query.get('title') || '3D';
      frame.allow = 'fullscreen';
      frame.allowFullscreen = true;
      frame.referrerPolicy = 'no-referrer';
      frame.addEventListener('load', requestReady);
      document.body.append(frame);
      // Navigate after attachment: a src set on a detached frame can leave it at about:blank (Web Ddl3DHost).
      frame.src = viewer + '#mount=' + encodeURIComponent(mountId);
      requestReady();
    })();
    """#
}

/// Serves the parent page and the registered viewer build under `inku-3d://viewer/`, read-only from the bundle.
/// Nothing else is reachable: no other build, no path outside it, no network.
final class Ddl3DSchemeHandler: NSObject, WKURLSchemeHandler {
    private let registration: Ddl3DInstallation.Registered

    init(registration: Ddl3DInstallation.Registered) { self.registration = registration }

    func webView(_ webView: WKWebView, start urlSchemeTask: any WKURLSchemeTask) {
        guard let url = urlSchemeTask.request.url else { return urlSchemeTask.didFailWithError(URLError(.badURL)) }
        let found = resource(for: url)
        let response = HTTPURLResponse(url: url, statusCode: found == nil ? 404 : 200, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": found?.type ?? "text/plain; charset=utf-8",
                                                      "Content-Length": String(found?.data.count ?? 0),
                                                      "Cache-Control": "no-store"])!
        urlSchemeTask.didReceive(response)
        if let found { urlSchemeTask.didReceive(found.data) }
        urlSchemeTask.didFinish()
    }

    func webView(_ webView: WKWebView, stop urlSchemeTask: any WKURLSchemeTask) {}

    /// The page itself, or one file of the registered build, by its path below the Web's `/experimental/ddl-3d/<build>/`.
    func resource(for url: URL) -> (data: Data, type: String)? {
        guard url.scheme == Ddl3DInstallation.scheme, url.host == Ddl3DInstallation.host else { return nil }
        switch url.path {
        case "/host.html": return (Data(Ddl3DHostPage.html.utf8), "text/html; charset=utf-8")
        case "/host.js": return (Data(Ddl3DHostPage.script.utf8), "text/javascript; charset=utf-8")
        case "/host.css": return (Data(Ddl3DHostPage.css.utf8), "text/css; charset=utf-8")
        default: break
        }
        let prefix = "/experimental/ddl-3d/\(registration.build)/"
        guard url.path.hasPrefix(prefix) else { return nil }
        let parts = url.path.dropFirst(prefix.count).split(separator: "/", omittingEmptySubsequences: false)
        guard !parts.isEmpty, parts.allSatisfy({ part in
            !part.isEmpty && part != "." && part != ".."
                && part.unicodeScalars.allSatisfy { $0.isASCII && (CharacterSet.alphanumerics.contains($0) || "._-".unicodeScalars.contains($0)) }
        }) else { return nil }
        let file = parts.reduce(registration.directory) { $0.appendingPathComponent(String($1)) }
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: file.path, isDirectory: &isDirectory), !isDirectory.boolValue,
              let data = try? Data(contentsOf: file) else { return nil }
        let types = ["html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8",
                     "wasm": "application/wasm", "json": "application/json", "txt": "text/plain; charset=utf-8",
                     "ts": "text/plain; charset=utf-8"]
        return (data, types[file.pathExtension.lowercased()] ?? "application/octet-stream")
    }
}

/// WKUserContentController keeps its handlers; this one keeps the bridge only weakly.
private final class Ddl3DMessageProxy: NSObject, WKScriptMessageHandler {
    weak var bridge: Ddl3DWebHost?
    init(bridge: Ddl3DWebHost) { self.bridge = bridge }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        // Only the parent page speaks; the viewer frame never calls the app.
        let origin = message.frameInfo.securityOrigin
        guard message.frameInfo.isMainFrame, origin.protocol == Ddl3DInstallation.scheme, origin.host == Ddl3DInstallation.host,
              let body = message.body as? [String: Any] else { return }
        bridge?.controller?.receive(body)
    }
}

/// The viewer's web view. Esc can be taken before the page (leaving the full-screen canvas first, as a browser does).
public final class Ddl3DWebView: WKWebView {
    /// Kept while the view is on screen; `Ddl3DWebHost.close()` lets it go.
    fileprivate var bridge: Ddl3DWebHost?
    var onEscape: (() -> Bool)?
    fileprivate var takesFocusInWindow = true

    public override func keyDown(with event: NSEvent) {
        if event.keyCode == 53, onEscape?() == true { return }
        super.keyDown(with: event)
    }

    public override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        // Choosing 3D gives the viewer the keyboard, so Esc and its keys work without a click first.
        guard let window, takesFocusInWindow else { return }
        takesFocusInWindow = false
        window.makeFirstResponder(self)
    }
}

/// One mount's web view: a non-persistent store, the app-only scheme, and no navigation, window or download
/// outside it except the viewer's own PNG/GLB saves, which ask where to save.
@MainActor
public final class Ddl3DWebHost: NSObject, Ddl3DPage, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    public let webView: Ddl3DWebView
    public private(set) weak var controller: Ddl3DController?
    private let registration: Ddl3DInstallation.Registered
    private let title: String

    public init(registration: Ddl3DInstallation.Registered, title: String, controller: Ddl3DController) {
        self.registration = registration; self.title = title; self.controller = controller
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.setURLSchemeHandler(Ddl3DSchemeHandler(registration: registration), forURLScheme: Ddl3DInstallation.scheme)
        configuration.preferences.isElementFullscreenEnabled = true
        webView = Ddl3DWebView(frame: .zero, configuration: configuration)
        super.init()
        configuration.userContentController.add(Ddl3DMessageProxy(bridge: self), name: "ddl3d")
        webView.bridge = self
        webView.navigationDelegate = self
        webView.uiDelegate = self
        // Transparent until the viewer paints, over the canvas area's own background.
        webView.setValue(false, forKey: "drawsBackground")
    }

    /// The canvas area keeps the keyboard where it was (the off-screen checks use this too).
    public var takesFocusInWindow: Bool {
        get { webView.takesFocusInWindow }
        set { webView.takesFocusInWindow = newValue }
    }

    public func mount(_ mountID: String) {
        var components = URLComponents()
        components.scheme = Ddl3DInstallation.scheme; components.host = Ddl3DInstallation.host; components.path = "/host.html"
        components.queryItems = [URLQueryItem(name: "mount", value: mountID), URLQueryItem(name: "viewer", value: registration.viewerPath),
                                 URLQueryItem(name: "title", value: title)]
        guard let url = components.url else { return }
        webView.load(URLRequest(url: url))
    }

    public func deliver(_ message: [String: Any]) {
        webView.callAsyncJavaScript("window.inku3d && window.inku3d.deliver(message)", arguments: ["message": message],
                                    in: nil, in: .page, completionHandler: nil)
    }

    public func focusViewer() {
        webView.callAsyncJavaScript("window.inku3d && window.inku3d.focus()", arguments: [:], in: nil, in: .page, completionHandler: nil)
    }

    /// The 3D view left the screen: dispose the viewer and release the page.
    public func close() {
        controller?.unmount(page: self)
        if webView.fullscreenState != .notInFullscreen { webView.closeAllMediaPresentations(completionHandler: nil) }
        webView.stopLoading()
        webView.configuration.userContentController.removeAllScriptMessageHandlers()
        webView.navigationDelegate = nil
        webView.uiDelegate = nil
        webView.bridge = nil
    }

    // MARK: Navigation

    public func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                        decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        if navigationAction.shouldPerformDownload { return decisionHandler(.download) }
        guard let url = navigationAction.request.url else { return decisionHandler(.cancel) }
        let own = url.scheme == Ddl3DInstallation.scheme && url.host == Ddl3DInstallation.host
        decisionHandler(own || url.absoluteString == "about:blank" ? .allow : .cancel)
    }

    public func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    public func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    public func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: any Error) {
        pageFailed(error)
    }

    public func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: any Error) {
        pageFailed(error)
    }

    public func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        controller?.fail("viewer_terminated")
    }

    private func pageFailed(_ error: any Error) {
        // A retry replaces the page; the load it cancels is not a failure.
        let error = error as NSError
        guard !(error.domain == NSURLErrorDomain && error.code == NSURLErrorCancelled) else { return }
        controller?.fail("viewer_load_failed:\(error.domain):\(error.code)")
    }

    public func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                        for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? { nil }

    // MARK: The viewer's PNG and GLB

    public func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                         completionHandler: @escaping @MainActor (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.canCreateDirectories = true
        let finish: (NSApplication.ModalResponse) -> Void = { result in
            guard result == .OK, let url = panel.url else { return completionHandler(nil) }
            // The panel already confirmed replacing it; a download does not overwrite.
            try? FileManager.default.removeItem(at: url)
            completionHandler(url)
        }
        if let window = webView.window { panel.beginSheetModal(for: window, completionHandler: finish) } else { panel.begin(completionHandler: finish) }
    }
}

/// The 3D view in the canvas area. Each appearance mounts a new viewer; leaving disposes it.
struct Ddl3DSurface: NSViewRepresentable {
    let controller: Ddl3DController
    let registration: Ddl3DInstallation.Registered
    let title: String
    let onEscape: () -> Bool

    func makeNSView(context: Context) -> Ddl3DWebView {
        let bridge = Ddl3DWebHost(registration: registration, title: title, controller: controller)
        bridge.webView.onEscape = onEscape
        controller.mount(page: bridge)
        return bridge.webView
    }

    func updateNSView(_ view: Ddl3DWebView, context: Context) { view.onEscape = onEscape }

    static func dismantleNSView(_ view: Ddl3DWebView, coordinator: ()) { view.bridge?.close() }
}
#endif

#if os(macOS)
import AppKit
import SwiftUI
import WebKit

/// Serves the parent page the native apps share with Android (`experiments/ddl-3d/host/`, the Web `Ddl3DHost.svelte`'s
/// iframe and listener) and the registered viewer build under `inku-3d://viewer/`, read-only from the bundle. Nothing
/// else is reachable: no other build, no path outside them, no network.
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

    /// One of the parent page's three files (`/host.html`, `/host.js`, `/host.css`), or one file of the registered
    /// build by its path below the Web's `/experimental/ddl-3d/<build>/`.
    func resource(for url: URL) -> (data: Data, type: String)? {
        guard url.scheme == Ddl3DInstallation.scheme, url.host == Ddl3DInstallation.host else { return nil }
        let root: URL, relative: Substring
        if ["/host.html", "/host.js", "/host.css"].contains(url.path) {
            root = registration.hostDirectory; relative = url.path.dropFirst()
        } else {
            let prefix = "/experimental/ddl-3d/\(registration.build)/"
            guard url.path.hasPrefix(prefix) else { return nil }
            root = registration.directory; relative = url.path.dropFirst(prefix.count)
        }
        let parts = relative.split(separator: "/", omittingEmptySubsequences: false)
        guard !parts.isEmpty, parts.allSatisfy({ part in
            !part.isEmpty && part != "." && part != ".."
                && part.unicodeScalars.allSatisfy { $0.isASCII && (CharacterSet.alphanumerics.contains($0) || "._-".unicodeScalars.contains($0)) }
        }) else { return nil }
        let file = parts.reduce(root) { $0.appendingPathComponent(String($1)) }
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
        if let type = body["type"] as? String, type == "download" || type == "download-failed" {
            bridge?.receiveViewerFile(body)
            return
        }
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

/// The viewer saves PNG and GLB through a `download` link to a blob it made, clicked after the file is ready. WKWebView
/// drops that click: it never asks `decidePolicyFor`, so no WKDownload starts (2026-10-18, a trusted click reproduced
/// it). In the viewer frame this script hands such a link to the shared parent page's `inku3d.download`, which reads
/// the blob and passes it to the app as Android's way does. The viewer and the parent page stay unchanged.
enum Ddl3DSaveLink {
    static let source = #"""
    (() => {
      if (window.parent === window || location.protocol !== 'inku-3d:' || !location.pathname.startsWith('/experimental/ddl-3d/')) return;
      const click = HTMLAnchorElement.prototype.click;
      HTMLAnchorElement.prototype.click = function () {
        const href = String(this.href || '');
        let host = null;
        try { host = window.parent.inku3d; } catch (_) { host = null; }
        if (this.hasAttribute('download') && href.startsWith('blob:' + location.origin + '/') && host && typeof host.download === 'function') {
          host.download(href, this.download);
          return;
        }
        return click.call(this);
      };
    })();
    """#
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
        configuration.userContentController.addUserScript(WKUserScript(source: Ddl3DSaveLink.source, injectionTime: .atDocumentStart,
                                                                       forMainFrameOnly: false, in: .page))
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

    /// The checks take the saved file here instead of the panel.
    public var onViewerFile: ((_ name: String, _ data: Data) -> Void)?

    /// host.js `download`: `{type: 'download', mountId, name, mimeType, dataUrl}` for the current mount, or
    /// `download-failed` when the blob could not be read.
    fileprivate func receiveViewerFile(_ body: [String: Any]) {
        guard let controller, body["mountId"] as? String == controller.mountID else { return }
        guard body["type"] as? String == "download", let dataURL = body["dataUrl"] as? String,
              let comma = dataURL.firstIndex(of: ","), dataURL[..<comma].hasSuffix(";base64"),
              let data = Data(base64Encoded: String(dataURL[dataURL.index(after: comma)...])) else {
            NSSound.beep(); return
        }
        let suggested = (body["name"] as? String).map { ($0 as NSString).lastPathComponent } ?? ""
        let name = suggested.isEmpty ? "inku-3d" : suggested
        if let onViewerFile { return onViewerFile(name, data) }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = name
        panel.canCreateDirectories = true
        let finish: (NSApplication.ModalResponse) -> Void = { result in
            guard result == .OK, let url = panel.url else { return }
            do { try data.write(to: url, options: .atomic) } catch { NSSound.beep() }
        }
        if let window = webView.window { panel.beginSheetModal(for: window, completionHandler: finish) } else { panel.begin(completionHandler: finish) }
    }

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

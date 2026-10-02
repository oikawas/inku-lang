import CoreGraphics
import Foundation
import ImageIO
import InkuCore
import InkuHost
import InkuPersistence
import Observation
import UniformTypeIdentifiers
#if os(macOS)
import AppKit
#endif

@MainActor
@Observable
public final class AppModel {
    public var inputMode = "ddl"
    public var descriptionText = ""
    public var ddlText = "place one red circle at center."
    public var language = "en"
    public var catalogID = "default"
    public var canvasID = "square"
    public var seedText = ""
    public var wild = false
    public private(set) var works: [SavedWork] = []
    public private(set) var selectedWorkID: String?
    public private(set) var currentSVG = ""
    public private(set) var visibleDDL = ""
    public private(set) var scoreJSON = ""
    public private(set) var status = "準備中"
    public private(set) var isBusy = false
    public var errorText: String?
    public var providerURL = "http://localhost:8080/v1"
    public var providerModel = ""
    public var providerKind = "openai_compatible"
    public var providerKey = ""
    public private(set) var catalogs: [ColorCatalogOption] = []
    public private(set) var canvases: [CanvasOption] = []
    public let renderer = ArtworkRenderer()
    public let versionSummary: String = {
        let report = try? JSONSerialization.jsonObject(with: Data(InkuCore.versionReport.utf8)) as? [String: String]
        return "共通コア接続 \(report?["binding_version"] ?? "不明") · 描画接続 \(InkuCore.rasterAPIVersion)"
    }()

    @ObservationIgnored private let databaseURL: URL?
    @ObservationIgnored private let transport: any ProviderTransport
    @ObservationIgnored private let credentials = KeychainCredentialStore()
    @ObservationIgnored private var database: InkuDatabase?
    @ObservationIgnored private var host: PipelineHost?
    @ObservationIgnored private var settingsStore: ProviderSettingsStore?
    @ObservationIgnored private var settings = HostSettings()
    @ObservationIgnored private var bootstrap: Bootstrap?
    @ObservationIgnored private var currentExecutionID: String?
    @ObservationIgnored private var generationToken: UUID?
    @ObservationIgnored private var activeOperation: Task<Void, Never>?
    @ObservationIgnored private var stopping = false
    @ObservationIgnored private var initialized = false

    public init(databaseURL: URL? = nil, transport: any ProviderTransport = URLSessionProviderTransport()) {
        self.databaseURL = databaseURL
        self.transport = transport
    }

    public var selectedWork: SavedWork? { works.first { $0.id == selectedWorkID } }
    public var canGenerate: Bool {
        database != nil && !isBusy && !(inputMode == "ddl" ? ddlText : descriptionText).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && (inputMode == "ddl" || !settings.providers.isEmpty)
    }

    public func initialize() async {
        guard !initialized else { return }
        initialized = true
        do {
            let url = try databaseURL ?? InkuDatabase.applicationSupportURL(hostIdentifier: "app.inku.macos")
            let database = try InkuDatabase(url: url)
            let store = ProviderSettingsStore(url: url.deletingLastPathComponent().appendingPathComponent("providers.json"))
            let settings = try await store.load()
            let bootstrap = try Bootstrap()
            self.database = database
            self.host = PipelineHost(database: database, transport: transport, credentials: credentials)
            self.settingsStore = store
            self.settings = settings
            self.bootstrap = bootstrap
            self.catalogs = bootstrap.catalogs
            self.canvases = bootstrap.canvases
            if let provider = settings.providers.first {
                providerURL = provider.baseURL.absoluteString
                providerKind = provider.apiProfile == "mlx" ? "mlx" : provider.kind.rawValue
                providerModel = settings.models.stage1Model.hasPrefix("\(provider.id):")
                    ? String(settings.models.stage1Model.dropFirst(provider.id.count + 1)) : settings.models.stage1Model
            }
            try await reloadWorks()
            status = "準備完了"
        } catch {
            initialized = false
            report(error)
        }
    }

    public func generate() async {
        guard canGenerate, let host, let bootstrap else { return }
        let token = UUID()
        generationToken = token
        currentExecutionID = nil
        stopping = false
        isBusy = true
        errorText = nil
        status = "生成中"
        let operation = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.runGeneration(host: host, bootstrap: bootstrap, token: token)
        }
        activeOperation = operation
        await operation.value
        finishOperation(token: token)
    }

    private func runGeneration(host: PipelineHost, bootstrap: Bootstrap, token: UUID) async {
        do {
            let request = try bootstrap.request(inputMode: inputMode, source: ddlText,
                description: descriptionText, language: language, catalogID: catalogID,
                canvasID: canvasID, seed: seedText, wild: wild, settings: settings,
                parentWorkID: selectedWorkID)
            let view = try await host.generate(request) { [weak self] progress in
                Task { @MainActor in self?.receive(progress, token: token) }
            }
            guard generationToken == token, !Task.isCancelled else { return }
            apply(view)
            try await reloadWorks()
            if let id = view.savedWorkID, let work = works.first(where: { $0.id == id }) { displayWork(work) }
        } catch {
            guard generationToken == token, !Task.isCancelled else { return }
            report(error)
        }
    }

    public func cancel() async {
        guard let operation = activeOperation, !stopping else { return }
        stopping = true
        status = "停止中"
        operation.cancel()
        if let id = currentExecutionID, let host {
            do { _ = try await host.cancel(executionID: id) }
            catch { report(error) }
        }
        await operation.value
    }

    public func selectWork(_ work: SavedWork) async {
        guard !isBusy else { return }
        displayWork(work)
    }

    private func displayWork(_ work: SavedWork) {
        selectedWorkID = work.id
        currentSVG = work.svg
        visibleDDL = work.ddl ?? ""
        scoreJSON = work.score
        ddlText = work.ddl ?? ""
        descriptionText = work.effectiveSourceText
        language = work.instructionLangResolved ?? language
        catalogID = work.catalogID ?? catalogID
        canvasID = work.renderCanvasAspectID ?? canvasID
    }

    public func replay(_ work: SavedWork) async {
        guard !isBusy, let host else { return }
        let token = UUID()
        generationToken = token
        currentExecutionID = nil
        stopping = false
        isBusy = true
        errorText = nil
        status = "再演奏中"
        let operation = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.runReplay(work: work, host: host, token: token)
        }
        activeOperation = operation
        await operation.value
        finishOperation(token: token)
    }

    private func runReplay(work: SavedWork, host: PipelineHost, token: UUID) async {
        do {
            let result = try await host.replay(workID: work.id)
            guard generationToken == token, !Task.isCancelled else { return }
            try await reloadWorks()
            displayWork(result)
            status = "再演奏を保存しました"
        } catch {
            guard generationToken == token, !Task.isCancelled else { return }
            report(error)
        }
    }

    private func finishOperation(token: UUID) {
        guard generationToken == token else { return }
        if stopping { status = "停止しました" }
        activeOperation = nil
        generationToken = nil
        stopping = false
        isBusy = false
    }

    public func saveProvider() async {
        guard let settingsStore, let url = URL(string: providerURL),
              !providerModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            report(HostError("provider_settings_incomplete"))
            return
        }
        do {
            let kind: ProviderKind = providerKind == "mlx" ? .openAICompatible
                : ProviderKind(rawValue: providerKind) ?? .openAICompatible
            let provider = ProviderSettings(id: "local", kind: kind, baseURL: url,
                apiProfile: providerKind == "mlx" ? "mlx" : nil,
                requiresAPIKey: url.scheme == "https")
            try provider.validate()
            if !providerKey.isEmpty { try await credentials.setKey(providerKey, for: provider.credentialID) }
            let modelID = "local:\(providerModel)"
            let settings = HostSettings(providers: [provider],
                models: ModelSelection(stage1Model: modelID, stage2Model: modelID))
            try await settingsStore.save(settings)
            self.settings = settings
            providerKey = ""
            errorText = nil
            status = "接続設定を保存しました"
        } catch { report(error) }
    }

    public func backup(to url: URL) async {
        guard let database else { return }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do { try await database.backup(to: url); status = "バックアップを保存しました" }
        catch { report(error) }
    }

    public func restore(from url: URL) async {
        guard !isBusy, activeOperation == nil, let database, let host else { return }
        isBusy = true
        defer { isBusy = false }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            try await host.cancelAll()
            try await database.restore(from: url)
            currentExecutionID = nil
            generationToken = nil
            try await reloadWorks()
            currentSVG = ""
            visibleDDL = ""
            scoreJSON = ""
            selectedWorkID = nil
            status = "復元しました"
        } catch { report(error) }
    }

    public func exportSVG(to url: URL) async {
        guard let work = selectedWork else { return }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do { try Data(work.svg.utf8).write(to: url, options: .atomic); status = "SVGを書き出しました" }
        catch { report(error) }
    }

    public func exportPNG(to url: URL, height: UInt32) async {
        guard let work = selectedWork else { return }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            let raster = try await Task.detached {
                try InkuCore.rasterize(svg: work.svg, targetHeight: height)
            }.value
            guard let image = raster.makeCGImage() else { throw ArtworkError.imageUnavailable }
            guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
                throw HostError("png_destination_unavailable")
            }
            CGImageDestinationAddImage(destination, image, nil)
            guard CGImageDestinationFinalize(destination) else { throw HostError("png_encode_failed") }
            status = "PNGを書き出しました"
        } catch { report(error) }
    }

    public func copyImage() async {
        #if os(macOS)
        guard !currentSVG.isEmpty else { return }
        do {
            let image = try await renderer.image(svg: currentSVG, targetWidth: 1024)
            let nativeImage = NSImage(cgImage: image, size: .zero)
            NSPasteboard.general.clearContents()
            guard NSPasteboard.general.writeObjects([nativeImage]) else { throw HostError("clipboard_write_failed") }
            status = "画像をコピーしました"
        } catch { report(error) }
        #endif
    }

    private func reloadWorks() async throws {
        guard let database else { return }
        works = try await database.list(limit: 100)
    }
    private func receive(_ progress: PipelineProgress, token: UUID) {
        guard generationToken == token, !stopping else { return }
        switch progress {
        case .changed(let view): apply(view)
        case .providerAttempt(_, _, _, let deadline):
            status = "モデルの応答待ち（期限 \(deadline.formatted(date: .omitted, time: .standard))）"
        case .transportBytes(_, let count): status = "応答を受信中（\(count) bytes）"
        case .saved(_, _): status = "作品を保存しました"
        }
    }
    private func apply(_ view: PipelineView) {
        currentExecutionID = view.executionID
        visibleDDL = view.visibleDDL ?? visibleDDL
        if let svg = view.svg { currentSVG = svg }
        if let score = view.scoreJSON { scoreJSON = String(decoding: score, as: UTF8.self) }
        status = [
            "authoring_started": "生成を開始しました", "awaiting_llm": "モデルの応答待ち",
            "awaiting_visible_ddl_commit": "DDLを確認しています", "awaiting_patch_approval": "補完案の承認待ち",
            "score_ready": "描画中", "completed": "生成を完了しました",
            "needs_user_edit": "DDLを編集してください", "failed": "生成できませんでした",
            "cancelled": "停止しました",
        ][view.phase] ?? "処理中"
    }
    private func report(_ error: Error) {
        errorText = error.localizedDescription
        status = "処理を完了できませんでした"
    }
}

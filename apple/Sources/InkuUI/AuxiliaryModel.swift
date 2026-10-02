import Foundation
import ImageIO
import InkuCore
import InkuHost
import InkuPersistence
import Observation
import UniformTypeIdentifiers
#if os(macOS)
import AppKit
#elseif os(iOS)
import UIKit
#endif

public enum AuxiliaryMode: String, CaseIterable, Sendable { case advice, colophon }

@MainActor
@Observable
public final class AuxiliaryModel {
    public var modelReference = ""
    public var language = "ja"
    public var direction = ""
    public var generations = 5
    public var visionMode = false
    public var amplitude = "medium"
    public var inheritWild = true
    public var wildOverride = false
    public var enabledKinds: Set<String> = Set(AuxiliaryProvider.allowedKinds)
    public var draftText = ""
    public private(set) var advice: AuxiliaryAdvice?
    public private(set) var colophonDraft: ColophonDraft?
    public private(set) var storedColophons: [ColophonDraft] = []
    public private(set) var running = false
    public private(set) var stopping = false
    public private(set) var completedGenerations = 0
    public private(set) var generatedWorks: [SavedWork] = []
    public private(set) var status = ""
    public private(set) var errorText: String?
    public private(set) var sourceIsLocked = false
    public private(set) var sourceWorkID: String?
    @ObservationIgnored private var provider: AuxiliaryProvider?
    @ObservationIgnored private var database: InkuDatabase?
    @ObservationIgnored private var token: UUID?
    @ObservationIgnored private var task: Task<Void, Never>?

    public init(provider: AuxiliaryProvider? = nil) { self.provider = provider }

    public func initialize(app: AppModel) async {
        guard !running else { return }
        if provider == nil {
            do { provider = try app.auxiliaryProvider() }
            catch { errorText = error.localizedDescription; return }
        }
        if sourceWorkID != app.selectedWorkID {
            advice = nil; colophonDraft = nil; draftText = ""; errorText = nil
        }
        sourceWorkID = app.selectedWorkID
        let settings = await app.hostSettings()
        if modelReference.isEmpty { modelReference = settings.models.stage1Model }
        do { database = try app.auxiliaryDatabase() }
        catch { errorText = error.localizedDescription; return }
        if let work = app.selectedWork {
            do {
                let context = try await app.savedConfiguration(workID: work.id)
                sourceIsLocked = context.authority == "ddl_authoritative"
            } catch {
                sourceIsLocked = true
                errorText = "保存された制作状態を取得できません。記述を読み直す操作は使えません。"
            }
            if sourceIsLocked { visionMode = false; enabledKinds.remove("reinterpretation") }
        }
        await reloadStored(app: app)
    }

    public func requestAdvice(app: AppModel) async {
        guard let provider else { errorText = "補助モデルの接続がありません。"; return }
        guard let work = app.selectedWork, !work.trashed, !sourceIsLocked else {
            errorText = "画像助言には記述から描いた保存作品が必要です。"; return
        }
        let direction = direction
        let reference = modelReference
        let language = language
        let kinds = orderedKinds
        await run(app: app, message: "モデルが作品を観察しています") { [self] runToken in
            let settings = await app.hostSettings()
            guard let png = try await Self.png(svgs: [work.svg], visionAdvice: true) else {
                throw HostError("refinement_source_has_no_image")
            }
            let result = try await provider.refineAdvice(instruction: work.effectiveSourceText,
                direction: direction, enabledKinds: kinds, png: png, modelReference: reference,
                language: language, settings: settings)
            try Task.checkCancellation()
            guard token == runToken else { return }
            advice = result; draftText = result.nextDirection
            status = "助言を受け取りました。次の方針を編集して採用できます。"
        }
    }

    public func generateColophon(app: AppModel) async {
        guard let provider else { errorText = "補助モデルの接続がありません。"; return }
        guard let work = app.selectedWork, let nodeID = work.lineageNodeID else {
            errorText = "系譜を持つ保存作品を選択してください。"; return
        }
        let reference = modelReference
        let language = language
        await run(app: app, message: "奥書を読む準備をしています") { [self] runToken in
            let settings = await app.hostSettings()
            app.library.lineagePathOnly = true
            await app.library.loadLineage(nodeID: nodeID)
            guard let path = app.library.graph, path.pathOnly, path.focusNodeID == nodeID else {
                throw HostError("colophon_requires_root_path")
            }
            let draft = try await provider.colophon(branch: path, modelReference: reference,
                language: language, settings: settings, png: { svgs in try await Self.png(svgs: svgs) })
            try Task.checkCancellation()
            guard token == runToken else { return }
            colophonDraft = draft; draftText = draft.generatedBody
            status = "奥書の草稿を生成しました。編集して保存してください。"
        }
    }

    /// A user adopts a direction into a new child, leaving the parent document intact.
    public func adoptAdvice(app: AppModel) async {
        guard let work = app.selectedWork, !app.isBusy, !running, !draftText.isEmpty else { return }
        do {
            let kind = advice?.suggestedKind ?? "reinterpretation"
            let catalog = kind == "catalog_change" ? randomCatalog(app: app, parent: work) : nil
            var request = try await app.makeRefinementRequest(work: work, kind: kind, direction: draftText,
                amplitude: amplitude, modelReference: modelReference.isEmpty ? nil : modelReference,
                catalogIDOverride: catalog, readDescription: !sourceIsLocked,
                wildOverride: inheritWild ? nil : wildOverride)
            request = try await app.pinPersonalPlanRequests([request])[0]
            let result = await app.runAutomation(request: request)
            if result == nil { errorText = app.errorText ?? "子の作品を生成できませんでした。" }
            else { status = "この方針で子の作品を保存しました。" }
        } catch { errorText = error.localizedDescription }
    }

    public func startRefinement(app: AppModel) async {
        guard let provider else { errorText = "補助モデルの接続がありません。"; return }
        guard let first = app.selectedWork, !first.trashed, !running, !app.isBusy else { return }
        let count = min(10, max(1, generations))
        let useVision = visionMode && !sourceIsLocked
        let kinds = orderedKinds.filter { !sourceIsLocked || $0 != "reinterpretation" }
        guard !kinds.isEmpty else { errorText = "少なくとも1つの推敲要素を選んでください。"; return }
        let model = modelReference
        let language = language
        let userDirection = direction
        let amplitude = amplitude
        let wild = inheritWild ? nil : wildOverride
        let runToken = UUID()
        token = runToken; running = true; stopping = false; errorText = nil
        completedGenerations = 0; generatedWorks = []
        let operation = Task { @MainActor [weak self] in
            guard let self else { return }
            var parent = first
            var runPin: ChatGPTPlanSession? = nil
            do {
                let settings = await app.hostSettings()
                for index in 0..<count {
                    try Task.checkCancellation()
                    guard self.token == runToken else { return }
                    var nextAdvice: AuxiliaryAdvice?
                    if useVision {
                        self.status = "\(index + 1) / \(count) 世代: モデルが観察しています"
                        let didRead = await app.performSerialized(status: self.status) { [self] _ in
                            guard let png = try await Self.png(svgs: [parent.svg], visionAdvice: true) else {
                                throw HostError("refinement_source_has_no_image")
                            }
                            let answer = try await provider.refineAdvice(instruction: parent.effectiveSourceText,
                                direction: userDirection, enabledKinds: kinds, png: png, modelReference: model,
                                language: language, settings: settings)
                            try Task.checkCancellation()
                            guard self.token == runToken else { return }
                            nextAdvice = answer; self.advice = answer
                        }
                        try Task.checkCancellation()
                        guard didRead, let answer = nextAdvice else { throw HostError("refinement_advice_failed") }
                        self.advice = answer
                    }
                    let kind: String
                    if let answer = nextAdvice { kind = answer.suggestedKind }
                    else if index == 0, !userDirection.isEmpty, kinds.contains("reinterpretation") { kind = "reinterpretation" }
                    else { kind = kinds.randomElement()! }
                    let directions = useVision ? [userDirection, nextAdvice?.nextDirection ?? ""].filter { !$0.isEmpty }
                        : (kind == "reinterpretation" && !userDirection.isEmpty ? [userDirection] : [])
                    self.status = "\(index + 1) / \(count) 世代: \(Self.kindLabel(kind))を生成中"
                    let appliedDirection = directions.isEmpty ? "" : "推敲方針: " + directions.joined(separator: " / ")
                    let catalog = kind == "catalog_change" ? self.randomCatalog(app: app, parent: parent) : nil
                    var request = try await app.makeRefinementRequest(work: parent, kind: kind,
                        direction: appliedDirection, amplitude: amplitude,
                        modelReference: useVision && !model.isEmpty ? model : nil,
                        catalogIDOverride: catalog, readDescription: !self.sourceIsLocked,
                        wildOverride: wild)
                    request.models = settings.models
                    request.providers = settings.providers
                    if useVision, !model.isEmpty { request.models.stage1Model = model; request.models.stage2Model = model }
                    request.historyVisibility = index == count - 1 ? "normal" : "lineage_only"
                    if index == 0 {
                        request = try await app.pinPersonalPlanRequests([request])[0]
                        runPin = request.chatGPTSession
                    } else {
                        request.chatGPTSession = runPin
                        if runPin != nil { request = try await app.pinPersonalPlanRequests([request])[0] }
                    }
                    try Task.checkCancellation()
                    guard self.token == runToken else { return }
                    guard let work = await app.runAutomation(request: request) else {
                        try Task.checkCancellation(); throw HostError(app.errorText ?? "refinement_generation_failed")
                    }
                    try Task.checkCancellation()
                    guard self.token == runToken else { return }
                    parent = work; self.generatedWorks.append(work); self.completedGenerations += 1
                }
                if self.token == runToken { self.status = "\(count) 世代の推敲を完了しました。作品の選択は利用者が行います。" }
            } catch is CancellationError {
                if self.token == runToken { self.status = "停止しました。保存済みの世代は系譜に残ります。" }
            } catch {
                if self.token == runToken && !Task.isCancelled { self.errorText = error.localizedDescription; self.status = "推敲を完了できませんでした。" }
            }
        }
        task = operation
        await operation.value
        if token == runToken { token = nil; running = false; stopping = false; task = nil }
    }

    public func saveColophon(app: AppModel) async {
        guard let database, var record = colophonDraft, !draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        do {
            record.adoptedBody = draftText
            try await database.saveColophon(record)
            colophonDraft = record; status = "編集した奥書を保存しました。"
            await reloadStored(app: app)
        } catch { errorText = error.localizedDescription }
    }

    public func editColophon(_ record: ColophonDraft) { colophonDraft = record; draftText = record.adoptedBody ?? record.generatedBody }

    public func deleteColophon(_ id: String, app: AppModel) async {
        do { try await database?.deleteColophon(id: id); await reloadStored(app: app) }
        catch { errorText = error.localizedDescription }
    }

    private func reloadStored(app: AppModel) async {
        do { storedColophons = try await database?.colophons(targetNodeID: app.selectedWork?.lineageNodeID) ?? [] }
        catch { errorText = error.localizedDescription }
    }

    public func copyDraft() {
        #if os(macOS)
        NSPasteboard.general.clearContents(); NSPasteboard.general.setString(draftText, forType: .string)
        #elseif os(iOS)
        UIPasteboard.general.string = draftText
        #endif
        status = "草稿をコピーしました。"
    }

    public func stop(app: AppModel) async {
        guard running, !stopping else { return }
        stopping = true; status = "停止中"
        task?.cancel()
        await app.cancel()
        await task?.value
    }

    private func run(app: AppModel, message: String, operation: @escaping @MainActor (UUID) async throws -> Void) async {
        guard !running, !app.isBusy else { return }
        let runToken = UUID()
        token = runToken; running = true; stopping = false; errorText = nil; status = message
        let work = Task { @MainActor [weak self] in
            guard let self else { return }
            let success = await app.performSerialized(status: message) { _ in try await operation(runToken) }
            guard self.token == runToken else { return }
            if Task.isCancelled { self.status = "停止しました。" }
            else if !success { self.errorText = app.errorText ?? "補助モデルの処理を完了できませんでした。" }
        }
        task = work
        await work.value
        if token == runToken { token = nil; running = false; stopping = false; task = nil }
    }

    private var orderedKinds: [String] { AuxiliaryProvider.allowedKinds.filter(enabledKinds.contains) }

    private func randomCatalog(app: AppModel, parent: SavedWork) -> String? {
        let current = parent.renderColorCatalogID ?? parent.catalogID
        return app.catalogs.filter { $0.id != current }.randomElement()?.id ?? current ?? app.catalogs.first?.id
    }

    public static func kindLabel(_ kind: String) -> String {
        ["reinterpretation": "読み取り", "catalog_change": "色", "layout_change": "配置", "touch_change": "タッチ", "variation": "変奏"][kind] ?? kind
    }

    /// The thumbnail is an observation input; the saved SVG is never rewritten.
    nonisolated private static func png(svgs: [String], visionAdvice: Bool = false) async throws -> Data? {
        let clean = svgs.filter { !$0.isEmpty }
        guard !clean.isEmpty else { return nil }
        return try await Task.detached {
            try Task.checkCancellation()
            let source: String
            let width: UInt32
            let height: UInt32
            if visionAdvice { source = clean[0]; width = 768; height = 768 }
            else {
                let count = min(2, clean.count)
                let images = clean.prefix(count).enumerated().map { index, svg in
                    "<image href=\"data:image/svg+xml;base64,\(Data(svg.utf8).base64EncodedString())\" x=\"\(index * 512)\" y=\"0\" width=\"512\" height=\"512\" preserveAspectRatio=\"xMidYMid meet\"/>"
                }.joined()
                source = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"\(count * 512)\" height=\"512\" viewBox=\"0 0 \(count * 512) 512\"><rect width=\"\(count * 512)\" height=\"512\" fill=\"white\"/>\(images)</svg>"
                width = count == 1 ? 512 : 768; height = count == 1 ? 512 : 384
            }
            let raster = try InkuCore.rasterize(svg: source, targetWidth: width, targetHeight: height)
            guard let image = raster.makeCGImage() else { throw ArtworkError.imageUnavailable }
            let data = NSMutableData()
            guard let destination = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil) else {
                throw HostError("png_destination_unavailable")
            }
            CGImageDestinationAddImage(destination, image, nil)
            guard CGImageDestinationFinalize(destination) else { throw HostError("png_encode_failed") }
            try Task.checkCancellation()
            return data as Data
        }.value
    }
}

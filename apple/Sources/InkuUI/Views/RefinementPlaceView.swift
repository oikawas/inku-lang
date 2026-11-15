import InkuHost
import InkuPersistence
import SwiftUI

@MainActor @Observable
private final class PlaceRefinementModel {
    let work: SavedWork
    let units: [ExactJSON]
    let freeLines: Bool
    var selected = 0
    var candidates: [ComparisonCandidate] = []
    var previewID: String?
    var running = false
    var error: String?
    var status = ""
    init(work: SavedWork, boxes: ExactJSON) {
        self.work = work; units = boxes["units"].array ?? []; freeLines = boxes["free_lines"].bool == true
    }
    var hasUnsaved: Bool { candidates.contains { $0.savedWork == nil } }

    func generate(app: AppModel, place: String) async {
        guard !running, !app.isBusy, selected < units.count else { return }
        let unit = units[selected]
        guard ["ok", "clamped"].contains(unit["places"][place].string ?? ""), let chunk = unit["title"].string else { return }
        running = true; error = nil
        defer { running = false }
        let success = await app.performComparison(status: "候補を生成中", restoreDisplayStatus: true) { token in
            let request = try await app.makeCompositionPlaceRequest(work: self.work, chunk: chunk, at: place)
            let candidate = try await app.generateCandidate(request: request, token: token)
            self.candidates.append(ComparisonCandidate(prepared: candidate, label: chunk + " · " + place, order: self.candidates.count))
        }
        if !success { error = app.errorText }
    }

    func save(app: AppModel) async -> Bool {
        let selection = candidates.filter { $0.selected && $0.savedWork == nil }
        guard !selection.isEmpty, !running, !app.isBusy else { return false }
        running = true; defer { running = false }
        return await app.performComparison(status: "選択した候補を保存中") { token in
            for candidate in selection {
                let saved = try await app.saveComparisonCandidate(executionID: candidate.id, token: token)
                if let index = self.candidates.firstIndex(where: { $0.id == candidate.id }) {
                    self.candidates[index].savedWork = saved
                }
            }
        }
    }
}

@MainActor
struct RefinementPlaceView: View {
    @Bindable var model: AppModel
    @State private var place: PlaceRefinementModel
    let onClose: () -> Void
    let onCommitted: (SavedWork) -> Void

    init(model: AppModel, work: SavedWork, boxes: ExactJSON, onClose: @escaping () -> Void, onCommitted: @escaping (SavedWork) -> Void) {
        self.model = model; self.onClose = onClose; self.onCommitted = onCommitted
        _place = State(initialValue: PlaceRefinementModel(work: work, boxes: boxes))
    }

    var body: some View {
        RefinementDialog(model: model, title: model.display.webCopy("canvasVaryComposition", "配置を変える"), work: place.work,
            closeDisabled: place.running || model.isBusy || place.hasUnsaved, onClose: onClose, columnWidth: 388) {
            VStack(alignment: .leading, spacing: 10) {
                Text(model.display.webCopy("placeThingsHead", "動かす物")).inkuFont(12, weight: .semibold)
                ForEach(Array(place.units.enumerated()), id: \.offset) { index, unit in
                    Button { place.selected = index } label: {
                        Label(unit["title"].string ?? "", systemImage: place.selected == index ? "largecircle.fill.circle" : "circle")
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }.buttonStyle(.plain).disabled(place.running || model.isBusy)
                }
                Text(model.display.webCopy("placePlacesHead", "置き場")).inkuFont(12, weight: .semibold)
                HStack(alignment: .top, spacing: 8) {
                    placePad("placePadGolden", fallback: "黄金分割の交点", slots: ["golden_ul", "golden_ur", "golden_ll", "golden_lr"])
                    placePad("placePadThirds", fallback: "三分割の線", slots: ["third_top", "third_left", "third_right", "third_bottom"])
                    placePad("placePadCenter", fallback: "中心", slots: ["center"])
                }
                Text(model.display.webCopy("placeHint", "押すと、その置き場で描いた画が右に並びます。送信はありません"))
                    .inkuFont(11).foregroundStyle(.secondary)
                Text(model.display.webCopy(place.freeLines ? "placeKeepsFreeLines" : "placeKeeps", "ほかの物の画・この物の形と大きさ"))
                    .inkuFont(12).foregroundStyle(.secondary)
                Text(model.display.webCopy("placeChanges", "この物の文の数（置き場）"))
                    .inkuFont(12).foregroundStyle(.secondary)
                if place.running { ProgressView(model.display.localized("候補の準備中")) }
            }
        } options: {
            RefinementOptionsGrid(model: model, options: place.candidates.map {
                RefinementOption(id: $0.id, work: $0.work, label: $0.label, selected: $0.selected, saved: $0.savedWork != nil, observation: $0.prepared)
            }, previewID: place.previewID, maxColumns: 2, busy: place.running || model.isBusy,
                placeholder: model.display.webCopy("placeEmpty", "置き場を押すと、候補がここに並びます。"),
                errors: [place.error].compactMap { $0 }, status: place.status,
                onPreview: { place.previewID = $0 }, onSelect: { id, selected in
                    if let index = place.candidates.firstIndex(where: { $0.id == id }) { place.candidates[index].selected = selected }
                }, onDiscard: onClose, onSave: { Task {
                    if await place.save(app: model) {
                        if let work = place.candidates.compactMap(\.savedWork).last { onCommitted(work) }
                        onClose()
                    }
                } })
        }
        .interactiveDismissDisabled(place.running || place.hasUnsaved || model.isBusy)
    }

    private func placePad(_ title: String, fallback: String, slots: [String]) -> some View {
        VStack(spacing: 5) {
            Text(model.display.webCopy(title, fallback)).inkuFont(11).lineLimit(2)
            GeometryReader { geometry in
                ZStack(alignment: .topLeading) {
                    Rectangle().stroke(InkuColor.border2)
                    Path { path in
                        let fractions: [CGFloat] = title == "placePadGolden" ? [0.382, 0.618] : title == "placePadThirds" ? [1 / 3, 2 / 3] : []
                        for fraction in fractions {
                            path.move(to: CGPoint(x: geometry.size.width * fraction, y: 0)); path.addLine(to: CGPoint(x: geometry.size.width * fraction, y: geometry.size.height))
                            path.move(to: CGPoint(x: 0, y: geometry.size.height * fraction)); path.addLine(to: CGPoint(x: geometry.size.width, y: geometry.size.height * fraction))
                        }
                    }.stroke(InkuColor.border2, style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    ForEach(slots, id: \.self) { id in
                        let state = place.selected < place.units.count ? place.units[place.selected]["places"][id].string : nil
                        let point = placePoint(id)
                        Button { Task { await place.generate(app: model, place: id) } } label: {
                            Circle().fill(Color.accentColor).frame(width: 12, height: 12).padding(8).contentShape(Rectangle())
                        }.buttonStyle(.plain).disabled(place.running || model.isBusy || !["ok", "clamped"].contains(state ?? ""))
                            .opacity(["ok", "clamped"].contains(state ?? "") ? 1 : 0.3)
                            .position(x: geometry.size.width * point.x, y: geometry.size.height * point.y)
                            .accessibilityLabel(CompositionNames.placeName(id, language: model.display.preferences.language))
                            .inkuTooltip(CompositionNames.placeName(id, language: model.display.preferences.language) + (state == "clamped" ? model.display.webCopy("placeClamped", "（画面の端で止まる）") : ""))
                    }
                }
            }.aspectRatio(1, contentMode: .fit)
        }.frame(maxWidth: .infinity)
    }

    private func placePoint(_ id: String) -> CGPoint {
        switch id {
        case "golden_ul": CGPoint(x: 0.382, y: 0.382)
        case "golden_ur": CGPoint(x: 0.618, y: 0.382)
        case "golden_ll": CGPoint(x: 0.382, y: 0.618)
        case "golden_lr": CGPoint(x: 0.618, y: 0.618)
        case "third_top": CGPoint(x: 0.5, y: 1 / 3)
        case "third_bottom": CGPoint(x: 0.5, y: 2 / 3)
        case "third_left": CGPoint(x: 1 / 3, y: 0.5)
        case "third_right": CGPoint(x: 2 / 3, y: 0.5)
        default: CGPoint(x: 0.5, y: 0.5)
        }
    }
}

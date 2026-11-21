import InkuCore
import InkuHost
import InkuPersistence
import SwiftUI
#if os(iOS)
import UIKit
#endif

@MainActor
struct PhoneDrawingWaitView: View {
    let model: AppModel
    let wait: PhoneDrawingWait
    let onClose: () -> Void
    let onPrevious: () -> Void
    let onRetry: () -> Void
    let onReview: () -> Void
    let onFinish: (SavedWork, Bool, CanvasPicture) -> Void

    @Environment(\.inkuDrawingMotion) private var showDrawingMotion
    @Environment(\.displayScale) private var scale
    @Environment(\.scenePhase) private var scenePhase
    @State private var controls = true
    @State private var shownRows = 0
    @State private var pausedUntil: ContinuousClock.Instant?
    @State private var frame: PhoneDrawingAssembly.Frame?
    @State private var finalFrame: CGImage?
    @State private var savedPicture = CanvasPicture()
    @State private var finished: SavedWork?
    @State private var revealing = false
    @State private var showFullPicture = false
    @State private var instructionLines: [AttributedString] = []

    private var display: DisplaySettings { model.display }
    private var catalog: ColorCatalogOption? {
        model.catalogs.first { $0.id == wait.material["catalog"].string }
    }
    private var principleIndex: Int {
        if wait.completion != nil { return 3 }
        if wait.commandCount != nil { return 2 }
        return wait.instructions == nil ? 0 : 1
    }

    var body: some View {
        GeometryReader { geometry in
            let landscape = geometry.size.width > geometry.size.height
            let side = min(geometry.size.width, landscape ? geometry.size.height - 44 : geometry.size.height * 0.55)
            let pixels = UInt32(max(1, min(CGFloat(PhoneDrawingAssembly.previewPixels), side * scale)))
            VStack(spacing: 0) {
                if controls { header }
                let layout = landscape ? AnyLayout(HStackLayout(spacing: 12)) : AnyLayout(VStackLayout(spacing: 0))
                layout {
                    picture.frame(width: max(1, side * min(1, wait.aspect)), height: max(1, side / max(1, wait.aspect)))
                    VStack(spacing: 0) { principle; scroll }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background { Color.black.ignoresSafeArea() }
            .simultaneousGesture(DragGesture(minimumDistance: 35).onEnded { value in
                if !revealing && value.translation.width > max(70, abs(value.translation.height) * 1.4) { onPrevious() }
            })
            .task(id: wait.completion?.id) {
                if let completion = wait.completion { await reveal(completion, pixels: pixels) }
            }
            .onChange(of: showDrawingMotion && scenePhase != .background ? pixels : nil, initial: true) { _, target in
                wait.setAssemblyTarget(target)
            }
        }
        .foregroundStyle(.white)
        .environment(\.colorScheme, .dark)
        .navigationBarBackButtonHidden(true)
        .toolbar(.hidden)
        .inkuPhoneTabBarHidden()
        .onChange(of: wait.instructions, initial: true) { _, text in
            instructionLines = text.map(highlight) ?? []
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background && wait.completion != nil { wait.visible = false }
        }
        .onDisappear { wait.setAssemblyTarget(nil) }
    }

    private var header: some View {
        HStack {
            Button(action: onClose) {
                Image(systemName: "chevron.left").frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel(display.localized("戻る"))
            Spacer()
            if wait.running {
                Button { Task { await model.stopPhoneDrawing() } } label: {
                    Text(display.localized("停止")).inkuFont(14).padding(.horizontal, 8).frame(minWidth: 44, minHeight: 44)
                }.disabled(wait.cancelled)
            }
        }.buttonStyle(.plain).padding(.horizontal, 6)
    }

    private var picture: some View {
        Button {
            if let finished { finish(finished) }
            else if !revealing { controls.toggle() }
        } label: {
            ZStack {
                if let finished {
                    ArtworkCanvas(svg: finished.svg, renderer: model.displayRenderer, style: .viewer,
                                  showsZoomControls: false, aspectRatio: finished.renderCanvasAspectRatio,
                                  handoffPicture: savedPicture)
                        .allowsHitTesting(false).opacity(showFullPicture ? 1 : 0)
                }
                if let frame {
                    Image(decorative: frame.image, scale: 1).resizable().scaledToFit()
                } else if !showFullPicture {
                    Rectangle().fill(Color(red: 0.96, green: 0.94, blue: 0.90))
                    VStack(spacing: 16) {
                        Text(wait.description).inkuFont(17).foregroundStyle(.black)
                            .multilineTextAlignment(.center).lineLimit(8)
                        swatches
                    }.padding(20)
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity).contentShape(Rectangle())
        }.buttonStyle(.plain)
    }

    private var swatches: some View {
        HStack(spacing: 3) {
            ForEach(Array((catalog?.palette ?? []).prefix(12).enumerated()), id: \.offset) { _, swatch in
                if let rgb = UInt32(swatch.code.trimmingCharacters(in: CharacterSet(charactersIn: "#")), radix: 16) {
                    Rectangle().fill(Color(red: Double((rgb >> 16) & 255) / 255,
                                           green: Double((rgb >> 8) & 255) / 255, blue: Double(rgb & 255) / 255))
                        .frame(width: 14, height: 14)
                        .accessibilityLabel(display.preferences.language == "en" ? swatch.name : swatch.japaneseName ?? swatch.name)
                }
            }
        }
    }

    private var principle: some View {
        HStack(spacing: 8) {
            let labels = [display.label("記述", "Description"), display.label("指示書", "Instructions"),
                          display.label("楽譜", "Score"), display.label("画", "Picture")]
            ForEach(labels.indices, id: \.self) { index in
                if index != 0 { Text("→").foregroundStyle(.secondary).accessibilityHidden(true) }
                VStack(spacing: 3) {
                    Text(labels[index]).foregroundStyle(Color.white.opacity(index == principleIndex ? 1 : index < principleIndex ? 0.72 : 0.45))
                    Capsule().fill(index == principleIndex ? .white : .clear).frame(width: 18, height: 2)
                }
            }
        }.inkuFont(13).padding(.vertical, 8).contentShape(Rectangle())
            .onTapGesture { if !revealing { controls.toggle() } }
    }

    private struct Row: Identifiable {
        let id: String
        let text: String
        var seconds: Int?
        var line: Int?
        var provisional = false
    }

    private var rows: [Row] {
        var rows = [Row(id: "description", text: display.localized("記述を受け取りました"), seconds: 0)]
        let material = wait.material
        for (index, item) in (wait.report["finished"].array ?? []).enumerated() {
            guard let action = item["action"].string, let title = RunJournalView.stageName(action, display: display) else { continue }
            let key = "stage-\(index)"
            let heading: String
            switch item["outcome"].string {
            case "fallback": heading = display.localizedFormat("%@：既定の形で続けました", title)
            case "retried": heading = display.localizedFormat("%@：問い直しました", title)
            default: heading = title
            }
            let elapsed = wait.milestoneTimes.indices.contains(index) ? wait.milestoneTimes[index] : 0
            rows.append(Row(id: key, text: heading, seconds: elapsed))
            let answer = material["answer"]
            let language = display.preferences.language
            let details: [String?]
            switch action {
            case "select_description_catalog": details = [catalog?.name]
            case "generate_sketch": details = [material["sketch"].string]
            case "generate_normalized_ddl":
                details = [wait.layerCount.map { display.localizedFormat("層 %d", $0) }, wait.support]
            case "read_description":
                let dropped = material["dropped"].array?.count ?? 0
                details = [material["reading"].string, dropped > 0 ? display.label("\(dropped) 語を外した", "\(dropped) terms omitted") : nil]
            case "compose_description", "read_composition", "choose_laws":
                let main = (answer["main_law"].string ?? item["facts"]["main_law"].string).flatMap { name -> String? in
                    let label = CompositionNames.lawName(name, language: language)
                    return label == name ? nil : label
                }
                let form = answer["form"].string.map { CompositionNames.formName($0, language: language) }
                let things = (answer["things"].array ?? []).map { thing in
                    let role = thing["role"].string.map { CompositionNames.roleName($0, language: language) }
                    return [thing["thing"].number, thing["what"].string, role, thing["quote"].string]
                        .compactMap { $0 }.joined(separator: " · ")
                }
                let targets = material["targets"].array?.compactMap(\.string) ?? []
                details = [answer["thesis"].string, [form, main].compactMap { $0 }.joined(separator: " · "),
                           (things + targets + [answer["reason"].string].compactMap { $0 }).joined(separator: "\n")]
            case "choose_colors":
                let law = item["facts"]["main_law"].string.flatMap { name -> String? in
                    let label = CompositionNames.colorLawName(name, language: language)
                    return label == name ? nil : label
                }
                details = [law, material["ground"].string.flatMap(groundName)]
            default: details = []
            }
            for (offset, detail) in details.compactMap({ $0 }).filter({ !$0.isEmpty }).prefix(3).enumerated() {
                rows.append(Row(id: "\(key)-\(offset)", text: detail))
            }
            if action == "write_description_ddl", let source = wait.beforeReview {
                for (offset, line) in source.components(separatedBy: "\n").prefix(3).enumerated() {
                    rows.append(Row(id: "\(key)-ddl-\(offset)", text: line, provisional: true))
                }
            }
        }
        if let source = wait.instructions {
            rows.append(Row(id: "instructions", text: display.label("指示書", "Instructions"), seconds: wait.instructionsAt))
            for (index, line) in source.components(separatedBy: "\n").enumerated() {
                rows.append(Row(id: "line-\(index + 1)", text: line, line: index + 1))
            }
        }
        if let commands = wait.commandCount {
            rows.append(Row(id: "score", text: display.localizedFormat("楽譜　指示 %d", commands), seconds: wait.scoreAt))
        }
        return rows
    }

    private func groundName(_ name: String) -> String? {
        let colors = ["white": "白", "black": "黒", "gray": "灰", "red": "赤", "blue": "青",
                      "green": "緑", "yellow": "黄", "orange": "橙", "purple": "紫"]
        guard let japanese = colors[name] else { return nil }
        return display.localizedFormat("地：%@", display.label(japanese, name))
    }

    private var scroll: some View {
        let materialRows = rows
        let allVisible = !showDrawingMotion || !wait.running
        return ScrollViewReader { reader in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 7) {
                    ForEach(materialRows.prefix(allVisible ? materialRows.count : shownRows)) { row in
                        waitRow(row).id(row.id)
                    }
                    if wait.running { currentStage(animated: shownRows >= materialRows.count) }
                    if let failure = wait.failure {
                        Text(failure).inkuFont(14)
                        Button(display.label("再試行", "Retry"), action: onRetry).frame(minHeight: 44)
                    }
                    if !wait.running && wait.completion == nil && model.phoneNeedsReview {
                        Text(display.localized("確かめることがあります。")).inkuFont(14)
                        Button(display.label("開く", "Open"), action: onReview).frame(minHeight: 44)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }.padding(.horizontal, 14).padding(.bottom, 8)
            }
            .simultaneousGesture(DragGesture(minimumDistance: 6).onChanged { _ in
                pausedUntil = .now.advanced(by: .seconds(3))
            }.onEnded { _ in
                pausedUntil = .now.advanced(by: .seconds(3))
            })
            .task(id: allVisible ? [] : materialRows.map(\.id)) {
                shownRows = max(1, min(shownRows, materialRows.count))
                while shownRows < materialRows.count && !allVisible {
                    do { try await Task.sleep(for: .milliseconds(materialRows.count - shownRows > 5 ? 100 : 400)) }
                    catch { return }
                    withAnimation(.easeOut(duration: 0.15)) { shownRows += 1 }
                }
            }
            .onChange(of: shownRows) { _, _ in if pausedUntil == nil { reader.scrollTo("bottom", anchor: .bottom) } }
            .onChange(of: allVisible) { _, _ in if pausedUntil == nil { reader.scrollTo("bottom", anchor: .bottom) } }
            .task(id: pausedUntil) {
                guard let until = pausedUntil else { return }
                do { try await ContinuousClock().sleep(until: until) } catch { return }
                pausedUntil = nil
                reader.scrollTo("bottom", anchor: .bottom)
            }
            .onChange(of: frame?.lines) { _, lines in
                if let first = lines?.first?.lowerBound { reader.scrollTo("line-\(first)", anchor: .center) }
            }
        }
    }

    @ViewBuilder private func waitRow(_ row: Row) -> some View {
        if let line = row.line {
            Text(instructionLines.indices.contains(line - 1) ? instructionLines[line - 1] : AttributedString(row.text))
                .inkuFont(13).opacity(frame.map { $0.lines.contains { $0.contains(line) } ? 1 : 0.36 } ?? 1)
        } else if row.provisional {
            Text(highlight(row.text).first ?? AttributedString(row.text)).inkuFont(13).opacity(0.7)
                .padding(.leading, 25)
        } else if let seconds = row.seconds {
            HStack(alignment: .firstTextBaseline) {
                Text(String(format: "%d:%02d", seconds / 60, seconds % 60)).inkuFont(11)
                    .monospacedDigit().foregroundStyle(.secondary)
                Text(row.text).inkuFont(14, weight: .semibold)
            }
        } else {
            PhoneProcessDetail(text: row.text, more: display.localized("続きを読む"))
                .padding(.leading, 25)
        }
    }

    private func currentStage(animated: Bool) -> some View {
        let attempt = model.providerProgress
        return TimelineView(.periodic(from: wait.started, by: 1)) { timeline in
            HStack(alignment: .top, spacing: 8) {
                let kind = display.preferences.mascot == "yuragi" ? "yuragi" : "incu"
                if showDrawingMotion && animated {
                    MascotView(kind: kind, accessibilityText: display.localized("描画中")).frame(width: 20, height: 20)
                }
                VStack(alignment: .leading) {
                    let current = RunJournalView.currentLabel(wait.report["current"], label: "描画中", attempt: attempt, display: display)
                    Text((attempt?.attempt ?? 0) > 1
                         ? display.localizedFormat("%@（%d 回目）", current, attempt?.attempt ?? 0) : current).inkuFont(14)
                    if let attempt, attempt.awaitingReply, attempt.modelReference?.hasPrefix("chatgpt:") == true,
                       let bytes = attempt.receivedBytes {
                        Text(display.label("受信 \(bytes / 1024) KB", "Received \(bytes / 1024) KB")).inkuFont(11)
                    } else {
                        let seconds = max(0, Int(timeline.date.timeIntervalSince(wait.started)))
                        Text(String(format: "%d:%02d", seconds / 60, seconds % 60)).inkuFont(11).monospacedDigit()
                    }
                }
            }.foregroundStyle(.white)
        }
    }

    private func highlight(_ source: String) -> [AttributedString] {
        #if os(iOS)
        let dark = UITraitCollection(userInterfaceStyle: .dark)
        return source.components(separatedBy: "\n").map { line in
            var attributed = AttributedString(line)
            for mark in model.ddlHighlighter.marks(line) {
                guard let color = mark.style.attributes[.foregroundColor] as? UIColor,
                      let sourceRange = Range(mark.range, in: line),
                      let range = Range(sourceRange, in: attributed) else { continue }
                attributed[range].foregroundColor = Color(uiColor: color.resolvedColor(with: dark))
            }
            return attributed
        }
        #else
        return source.components(separatedBy: "\n").map { AttributedString($0) }
        #endif
    }

    private func reveal(_ completion: PhoneDrawingWait.Completion, pixels: UInt32) async {
        revealing = true
        let inFlight = wait.preflight
        let progress = inFlight?.progress ?? PhoneDrawingAssembly.Progress()
        guard let work = try? await model.library.fullWork(id: completion.id) else {
            if !Task.isCancelled {
                progress.logSkip(.preparation("saved_work_unavailable"), workID: completion.id,
                                 elapsed: completion.savedAt.duration(to: .now))
                wait.visible = false
            }
            return
        }
        guard !Task.isCancelled else { return }
        finished = work
        let clock = ContinuousClock()
        let frames = await PhoneDrawingAssembly.prepare(
            savedAt: completion.savedAt, commandCount: wait.commandCount,
            showDrawingMotion: showDrawingMotion,
            now: { clock.now }, sleep: { try await clock.sleep(until: $0) },
            onSkip: { skip, elapsed in progress.logSkip(skip, workID: work.id, elapsed: elapsed) }
        ) {
            if let inFlight { return try await inFlight.task.value }
            guard let context = await model.phoneAssemblyContext(work.id) else {
                throw HostError("saved_authoring_context_unavailable")
            }
            try Task.checkCancellation()
            return try PhoneDrawingAssembly.frames(work: work, context: context, pixels: pixels, progress: progress)
        }
        wait.cancelPreflight()
        guard !Task.isCancelled else { return }
        finalFrame = frames.last?.image
        if !frames.isEmpty {
            let interval = PhoneDrawingAssembly.frameInterval(count: frames.count)
            let start = clock.now
            for (index, image) in frames.enumerated() {
                frame = image
                do { try await clock.sleep(until: start.advanced(by: interval * (index + 1))) }
                catch { return }
            }
        } else if showDrawingMotion {
            withAnimation(.easeIn(duration: 0.18)) { showFullPicture = true }
            do { try await Task.sleep(for: .milliseconds(180)) } catch { return }
        }
        if !Task.isCancelled { finish(work) }
    }

    private func finish(_ work: SavedWork) {
        if let finalFrame { savedPicture.seedIfEmpty(finalFrame, svg: work.svg) }
        onFinish(work, controls, savedPicture)
    }
}

private struct PhoneProcessDetail: View {
    let text: String
    let more: String
    @State private var expanded = false
    var body: some View {
        Button { expanded.toggle() } label: {
            Text(text).inkuFont(13).lineLimit(expanded ? nil : 3)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        }.buttonStyle(.plain).accessibilityHint(expanded ? "" : more)
    }
}

@MainActor
struct PhoneDrawingCompletionRow: View {
    let display: DisplaySettings
    let onView: () -> Void
    var body: some View {
        HStack(spacing: 12) {
            Text(display.localized("描き上がりました")).frame(maxWidth: .infinity, alignment: .leading)
            Button(display.localized("見る"), action: onView).frame(minWidth: 44, minHeight: 44)
        }.inkuFont(14).padding(.horizontal, 14).background(InkuColor.bg)
    }
}

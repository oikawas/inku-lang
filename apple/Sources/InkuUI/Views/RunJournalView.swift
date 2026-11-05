import InkuHost
import SwiftUI

@MainActor
struct RunJournalView: View {
    let model: AppModel
    let journal: RunProgressJournal
    let label: String
    private var display: DisplaySettings { model.display }

    var body: some View {
        let snapshot = model.providerProgress.flatMap { $0.executionID == model.runJournalExecutionID ? $0 : nil }
        let current = journal.report["current"]
        let matchingAttempt = snapshot.flatMap {
            current["kind"].string == "provider" && current["action"].string == $0.action && $0.awaitingReply ? $0 : nil
        }
        TimelineView(.periodic(from: snapshot?.stageBeganAt ?? Date(), by: 0.5)) { context in
            VStack(alignment: .leading, spacing: 2) {
                if let reference = snapshot?.modelReference ?? model.runModelReference, !reference.isEmpty {
                    Text(display.localizedFormat("呼出しモデル: %@", reference)).lineLimit(1).truncationMode(.tail)
                }
                ForEach(Array((journal.report["finished"].array ?? []).enumerated()), id: \.offset) { _, item in
                    HStack(spacing: 8) {
                        Text("✓ " + finished(item)).lineLimit(1).truncationMode(.tail).frame(maxWidth: .infinity, alignment: .leading)
                        if let action = item["action"].string, let tokens = journal.stageTokens[action] {
                            Text(format("runStatusStageTokens", "入力 %@・出力 %@", count(tokens.input), count(tokens.output))).fixedSize()
                        }
                    }
                }
                Text("… " + Self.currentLabel(current, label: label, attempt: matchingAttempt, display: display)).inkuFont(12, weight: .semibold).foregroundStyle(.primary)
                    .lineLimit(1).truncationMode(.tail).frame(maxWidth: .infinity, alignment: .leading)
                RunMetadataFlow(spacing: 8) {
                    if let snapshot = matchingAttempt {
                        Text(format(snapshot.askedAgain ? "runStatusAskingAgain" : snapshot.attempt > 1 ? "runStatusRetrying" : "runStatusAwaitingReply",
                                    "応答待ち（%@/%@回目）", String(snapshot.attempt), String(snapshot.maxAttempts)))
                    }
                    Text(format("runStatusElapsed", "経過 %@秒", String(format: "%.1f", max(0, context.date.timeIntervalSince(journal.beganAt)))))
                    if let snapshot = matchingAttempt {
                        if snapshot.modelReference?.hasPrefix("chatgpt:") == true, let bytes = snapshot.receivedBytes, snapshot.awaitingReply {
                            Text(format("runStatusReceived", "受信 %@ KB", String(bytes / 1024)))
                        }
                    }
                }.lineLimit(1).truncationMode(.tail)
                Text(format(journal.total.unreported > 0 ? "runStatusPartialTokens" : "runStatusTotalTokens",
                            journal.total.unreported > 0 ? "合計（一部不明）入力 %@・出力 %@" : "合計 入力 %@・出力 %@",
                            count(journal.total.input), count(journal.total.output))).lineLimit(1).truncationMode(.tail)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            .inkuFont(11).foregroundStyle(.secondary).monospacedDigit()
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    static func currentLabel(_ current: ExactJSON, label: String, attempt: ProviderProgressSnapshot?, display: DisplaySettings) -> String {
        guard current.object != nil else { return display.message(label) }
        let action = current["action"].string ?? ""
        if current["kind"].string == "local" {
            switch action {
            case "draw_image_review": return display.webCopy("runLocalReview", "見比べ用に描いています…")
            case "commit_visible_normalized_ddl", "save": return display.webCopy("runLocalSave", "保存しています…")
            default: return display.webCopy("runLocalRender", "描いています…")
            }
        }
        let askedAgain = attempt?.action == action && attempt?.askedAgain == true
        switch action {
        case "select_image_catalog": return display.webCopy("imageSelectingCatalog", "画像から色カタログを選んでいます…")
        case "write_image_ddl": return display.webCopy(askedAgain ? "imageRevisingDdl" : "imageWritingDdl", askedAgain ? "指示書を直しています…" : "画像から指示書を書いています…")
        case "review_image_ddl": return display.webCopy(askedAgain ? "imageRevisingDdl" : "imageReviewingDdl", askedAgain ? "指示書を直しています…" : "画像と描いた画を見比べています…")
        case "read_description": return display.webCopy("readDrawReading", "記述を読んでいます…")
        case "compose_description": return display.webCopy(askedAgain ? "readDrawRecomposing" : "readDrawComposing", askedAgain ? "構図と法則を決め直しています…" : "構図と法則を決めています…")
        case "write_description_ddl": return display.webCopy(askedAgain ? "readDrawRevising" : "readDrawWriting", askedAgain ? "指示書を直しています…" : "指示書を書いています…")
        case "review_description_ddl": return display.webCopy(askedAgain ? "readDrawRevising" : "readDrawReviewing", askedAgain ? "指示書を直しています…" : "描いた画を見て直しています…")
        case "read_composition": return display.webCopy("stageReadingComposition", "構図の読み中…")
        case "choose_colors": return display.webCopy("stageChoosingColors", "配色の選択中…")
        case "choose_laws": return display.webCopy("stageChoosingLaws", "法則の選択中…")
        default: return stage(action, display: display) + "…"
        }
    }

    private func count(_ value: UInt64?) -> String {
        guard let value else { return "−" }
        return value.formatted(.number.grouping(.automatic).locale(Locale(identifier: "en_US")))
    }
    private func format(_ key: String, _ fallback: String, _ values: String...) -> String {
        let template = ServerTips.template(key, language: display.preferences.language, argumentCount: values.count) ?? fallback
        return String(format: template, locale: Locale(identifier: display.preferences.language), arguments: values)
    }
    private static func stage(_ action: String, display: DisplaySettings) -> String {
        let keys = ["select_description_catalog": "runStageCatalog", "read_description": "runStageReading", "compose_description": "runStageComposition", "write_description_ddl": "runStageWriting", "review_description_ddl": "runStageReview", "choose_colors": "runStageColors", "choose_laws": "runStageLaws", "generate_normalized_ddl": "runStageInterpret", "generate_sketch": "runStageSketch", "read_composition": "runStageCompositionReading", "complete_visible_ddl_holes": "runStageCompletion", "select_image_catalog": "runStageImageCatalog", "write_image_ddl": "runStageImageWriting", "review_image_ddl": "runStageImageReview"]
        return keys[action].map { display.webCopy($0, action) } ?? action
    }
    private func finished(_ item: ExactJSON) -> String {
        let action = item["action"].string ?? "", title = Self.stage(action, display: display), facts = item["facts"]
        switch item["outcome"].string {
        case "fallback": return format("runFinishedFallback", "%@：既定の形で続けました", title)
        case "retried": return format("runFinishedRetried", "%@：問い直しました", title)
        default: break
        }
        if action == "read_description" {
            if let dropped = facts["dropped_items"].number.flatMap(Int.init), dropped > 0 {
                return format("runFinishedReadingDropped", "読みました（%@ 語を外した）", String(dropped))
            }
            return display.webCopy("runFinishedReading", "読みました")
        }
        if action == "compose_description", let things = facts["things"].number, let law = facts["main_law"].string {
            return format("runFinishedComposition", "構図：物 %@ つ・主の法則 %@", things, law)
        }
        if ["write_description_ddl", "write_image_ddl"].contains(action) { return display.webCopy("runFinishedWriting", "書きました") }
        if ["review_description_ddl", "review_image_ddl"].contains(action) { return display.webCopy("runFinishedReview", "見て直しました") }
        if let catalog = facts["catalog_id"].string { return format("runFinishedCatalog", "%@：%@", title, catalog) }
        if let law = facts["main_law"].string { return format("runFinishedLaw", "%@：主の法則 %@", title, law) }
        return format("runFinishedReady", "%@：完了", title)
    }
}

/// Wrap whole metadata items, limiting each one to the available width.
struct RunMetadataFlow: Layout {
    var spacing: CGFloat = 8

    private func positions(width: CGFloat, subviews: Subviews) -> ([(CGPoint, CGSize)], CGSize) {
        var result: [(CGPoint, CGSize)] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, usedWidth: CGFloat = 0
        for view in subviews {
            let ideal = view.sizeThatFits(.unspecified)
            let size = view.sizeThatFits(ProposedViewSize(width: min(width, ideal.width), height: nil))
            let actual = CGSize(width: min(width, size.width), height: size.height)
            if x > 0 && x + actual.width > width {
                y += rowHeight + spacing; x = 0; rowHeight = 0
            }
            result.append((CGPoint(x: x, y: y), actual))
            usedWidth = max(usedWidth, x + actual.width)
            x += actual.width + spacing
            rowHeight = max(rowHeight, actual.height)
        }
        return (result, CGSize(width: usedWidth, height: y + rowHeight))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        positions(width: max(0, proposal.width ?? .greatestFiniteMagnitude), subviews: subviews).1
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let (items, _) = positions(width: max(0, bounds.width), subviews: subviews)
        for (view, item) in zip(subviews, items) {
            view.place(at: CGPoint(x: bounds.minX + item.0.x, y: bounds.minY + item.0.y), anchor: .topLeading,
                       proposal: ProposedViewSize(item.1))
        }
    }
}

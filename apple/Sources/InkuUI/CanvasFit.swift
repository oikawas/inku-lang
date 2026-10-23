import Foundation
import SwiftUI

/// Display-side reading only. Core owns declaration validation and the composition it describes.
public struct CanvasRatio: Equatable, Sendable {
    public let width: Int
    public let height: Int
    public var label: String { "\(width):\(height)" }

    public init?(width: Int, height: Int) {
        guard (1...10_000).contains(width), (1...10_000).contains(height) else { return nil }
        var a = width, b = height
        while b != 0 { (a, b) = (b, a % b) }
        self.width = width / a; self.height = height / a
    }

    public static func declared(in source: String) -> Self? {
        guard let expression = try? NSRegularExpression(
            pattern: #"^\s*(?:画面比|aspect\s+ratio)\s*([0-9０-９]{1,5})\s*[:：]\s*([0-9０-９]{1,5})\s*$"#,
            options: [.caseInsensitive]) else { return nil }
        for sentence in source.components(separatedBy: CharacterSet(charactersIn: "。.！!？?\n")) {
            let text = sentence as NSString
            guard let match = expression.firstMatch(in: sentence, range: NSRange(location: 0, length: text.length)) else { continue }
            func units(_ index: Int) -> Int? {
                Int(text.substring(with: match.range(at: index)).applyingTransform(.fullwidthToHalfwidth, reverse: false) ?? "")
            }
            if let width = units(1), let height = units(2), let ratio = Self(width: width, height: height) { return ratio }
        }
        return nil
    }
}

public enum CanvasFitChoice: Sendable, Equatable { case contain, paper, cancel }
public enum CanvasFitPresentation: Sendable, Equatable { case workspace, editor }

public struct CanvasFitQuestion: Identifiable, Sendable {
    public let id = UUID()
    public let ratio: CanvasRatio
    public let paper: CanvasOption
    public let presentation: CanvasFitPresentation
}

private struct CanvasFitConfirmation: ViewModifier {
    @Bindable var model: AppModel
    let presentation: CanvasFitPresentation
    private var question: CanvasFitQuestion? {
        model.canvasFitQuestion.flatMap { $0.presentation == presentation ? $0 : nil }
    }
    func body(content: Content) -> some View {
        content.alert(model.display.localized("画面比が異なります"), isPresented: Binding(
            get: { question != nil }, set: { _ in }), presenting: question) { question in
                Button(model.display.webCopy("canvasFitRun", "はめ込んで描く")) {
                    model.resolveCanvasFit(.contain, id: question.id)
                }
                Button(model.display.webCopy("canvasFitStretch", "この紙に合わせて描く")) {
                    model.resolveCanvasFit(.paper, id: question.id)
                }
                Button(model.display.localized("キャンセル"), role: .cancel) {
                    model.resolveCanvasFit(.cancel, id: question.id)
                }
            } message: { question in
                Text(model.display.webCopyFormat("canvasFitMessage",
                    "このDDLは画面比%@で書かれています。今の紙（%@）にどう描きますか。はめ込むと、構図をそのままの比で紙の中央に置き、余白は地になります。",
                    question.ratio.label, "\(question.paper.name) \(question.paper.widthRatio):\(question.paper.heightRatio)"))
            }
            .onDisappear {
                if let question { model.resolveCanvasFit(.cancel, id: question.id) }
            }
    }
}

extension View {
    func canvasFitConfirmation(model: AppModel, presentation: CanvasFitPresentation) -> some View {
        modifier(CanvasFitConfirmation(model: model, presentation: presentation))
    }
}

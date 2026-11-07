#if os(iOS)
import SwiftUI
import CoreText
import InkuHost
import UIKit

@MainActor
struct BatchNativeInputEditor: UIViewRepresentable {
    @Binding var text: String
    let isEditable: Bool
    let accessibilityLabel: String
    let textScale: Double
    let colorScheme: ColorScheme
    // iOS keeps the plain editor: no marks, and words are appended by the caller's binding.
    let style: InkuEditorStyle
    let marks: (String) -> [InkuEditorMark]
    let marksKey: InkuEditorMarksKey
    let covered: Bool
    let insertion: Binding<InkuEditorInsertion?>?
    var rangeTable: [CompositionRanges.Entry]? = nil
    var onRangeStatus: ((RangeEditorStatus) -> Void)? = nil
    var completions: DdlCompletions? = nil
    var onCharacterHover: ((Int?) -> Void)? = nil

    func makeCoordinator() -> Coordinator { Coordinator(text: $text) }
    func makeUIView(context: Context) -> BatchIOSTextView {
        let storage = NSTextStorage()
        let layout = NSLayoutManager()
        let container = NSTextContainer(size: .zero)
        container.lineFragmentPadding = 0
        storage.addLayoutManager(layout)
        layout.addTextContainer(container)
        let editor = BatchIOSTextView(frame: .zero, textContainer: container)
        editor.backgroundColor = .secondarySystemBackground
        editor.autocorrectionType = .no
        editor.autocapitalizationType = .none
        editor.smartQuotesType = .no
        editor.smartDashesType = .no
        editor.smartInsertDeleteType = .no
        editor.textColor = .label
        editor.delegate = context.coordinator
        editor.onCompositionEnded = { [weak coordinator = context.coordinator] in
            DispatchQueue.main.async { coordinator?.applyDeferredUpdates() }
        }
        context.coordinator.editor = editor
        context.coordinator.update(from: self)
        return editor
    }
    func updateUIView(_ view: BatchIOSTextView, context: Context) { context.coordinator.update(from: self) }
    static func dismantleUIView(_ view: BatchIOSTextView, coordinator: Coordinator) {
        view.delegate = nil
        view.onCompositionEnded = nil
        coordinator.editor = nil
    }

    @MainActor
    final class Coordinator: NSObject, UITextViewDelegate {
        private var text: Binding<String>
        weak var editor: BatchIOSTextView?
        private var settings: BatchNativeInputEditor?
        private var pendingExternalText: String?
        private var replacingText = false
        init(text: Binding<String>) { self.text = text }

        func update(from settings: BatchNativeInputEditor) {
            self.settings = settings
            text = settings.$text
            guard let editor else { return }
            let source = text.wrappedValue
            editor.accessibilityLabel = settings.accessibilityLabel
            editor.overrideUserInterfaceStyle = settings.colorScheme == .dark ? .dark : .light
            if editor.markedTextRange != nil {
                pendingExternalText = source == editor.text ? nil : source
                return
            }
            pendingExternalText = nil
            if editor.text != source { replaceText(with: source) }
            applySettings()
        }

        func textViewDidChange(_ textView: UITextView) {
            guard !replacingText, let editor else { return }
            editor.refreshGutter()
            if pendingExternalText == nil {
                let value = editor.text ?? ""
                if text.wrappedValue != value { text.wrappedValue = value }
            }
            if editor.markedTextRange == nil { applyDeferredUpdates() }
        }
        func textViewDidEndEditing(_ textView: UITextView) { applyDeferredUpdates() }
        func scrollViewDidScroll(_ scrollView: UIScrollView) { editor?.setNeedsLayout() }

        func applyDeferredUpdates() {
            guard let editor, editor.markedTextRange == nil else { return }
            if pendingExternalText != nil {
                pendingExternalText = nil
                replaceText(with: text.wrappedValue)
            }
            applySettings()
        }

        private func applySettings() {
            guard let editor, let settings else { return }
            if editor.isEditable != settings.isEditable { editor.isEditable = settings.isEditable }
            if !editor.isSelectable { editor.isSelectable = true }
            let size = CGFloat(15 * settings.textScale)
            if editor.font?.pointSize != size {
                let offset = editor.contentOffset
                editor.font = .monospacedSystemFont(ofSize: size, weight: .regular)
                editor.refreshGutter()
                editor.setContentOffset(offset, animated: false)
            }
        }

        private func replaceText(with value: String) {
            guard let editor, editor.text != value else { return }
            let selection = editor.selectedRange
            let offset = editor.contentOffset
            replacingText = true
            editor.text = value
            editor.undoManager?.removeAllActions()
            let location = min(selection.location, value.utf16.count)
            editor.selectedRange = NSRange(location: location, length: min(selection.length, value.utf16.count - location))
            editor.refreshGutter()
            editor.setContentOffset(offset, animated: false)
            replacingText = false
        }
    }
}

@MainActor
final class BatchIOSTextView: UITextView {
    var onCompositionEnded: (() -> Void)?
    private let gutter = BatchIOSGutter()
    fileprivate var lineIndex = BatchEditorLineIndex("")
    fileprivate var numberFont = CTFontCreateWithName("Menlo" as CFString, 15, nil)

    override init(frame: CGRect, textContainer: NSTextContainer?) {
        super.init(frame: frame, textContainer: textContainer)
        gutter.editor = self
        gutter.isUserInteractionEnabled = false
        gutter.isAccessibilityElement = false
        addSubview(gutter)
        refreshGutter()
    }
    required init?(coder: NSCoder) { return nil }

    override func unmarkText() {
        super.unmarkText()
        onCompositionEnded?()
    }
    override func layoutSubviews() {
        super.layoutSubviews()
        gutter.frame = CGRect(x: contentOffset.x, y: contentOffset.y, width: textContainerInset.left - 10, height: bounds.height)
        gutter.setNeedsDisplay()
    }

    func refreshGutter() {
        lineIndex = BatchEditorLineIndex(text ?? "", reusing: lineIndex)
        if let font { numberFont = CTFontCreateWithName(font.fontName as CFString, font.pointSize, nil) }
        let number = batchNumberLine(max(1, lineIndex.count), font: numberFont, color: UIColor.secondaryLabel.cgColor)
        let width = max(34, ceil(CGFloat(CTLineGetTypographicBounds(number, nil, nil, nil)) + 18))
        let inset = UIEdgeInsets(top: 8, left: width + 10, bottom: 8, right: 10)
        if textContainerInset != inset { textContainerInset = inset }
        setNeedsLayout()
    }
}

@MainActor
private final class BatchIOSGutter: UIView {
    weak var editor: BatchIOSTextView?
    override func draw(_ rect: CGRect) {
        UIColor.tertiarySystemBackground.setFill()
        UIRectFill(rect)
        guard let editor, let context = UIGraphicsGetCurrentContext() else { return }
        let layout = editor.layoutManager
        let container = editor.textContainer
        layout.ensureLayout(for: container)
        let visible = CGRect(x: 0, y: editor.contentOffset.y - editor.textContainerInset.top,
                             width: container.size.width, height: bounds.height)
        let glyphs = layout.glyphRange(forBoundingRect: visible, in: container)
        let first = glyphs.length > 0
            ? editor.lineIndex.line(containing: layout.characterIndexForGlyph(at: glyphs.location))
            : max(0, editor.lineIndex.starts.count - 1)
        let length = (editor.text ?? "").utf16.count
        for index in first..<editor.lineIndex.starts.count {
            let start = editor.lineIndex.starts[index]
            let fragment: CGRect
            let baseline: CGFloat
            if start < length {
                let glyph = layout.glyphIndexForCharacter(at: start)
                fragment = layout.lineFragmentRect(forGlyphAt: glyph, effectiveRange: nil)
                baseline = fragment.minY + layout.location(forGlyphAt: glyph).y
            } else {
                fragment = layout.extraLineFragmentRect
                let offset = layout.numberOfGlyphs > 0
                    ? layout.location(forGlyphAt: layout.numberOfGlyphs - 1).y
                    : CTFontGetAscent(editor.numberFont)
                baseline = fragment.minY + offset
            }
            let y = editor.textContainerInset.top + baseline - editor.contentOffset.y
            if y > rect.maxY + fragment.height { break }
            guard y >= rect.minY - fragment.height else { continue }
            let number = batchNumberLine(index + 1, font: editor.numberFont, color: UIColor.secondaryLabel.cgColor)
            let width = CGFloat(CTLineGetTypographicBounds(number, nil, nil, nil))
            batchDrawNumber(number, baseline: CGPoint(x: bounds.maxX - width - 8, y: y), context: context)
        }
    }
}
#endif

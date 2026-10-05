import CoreText
import InkuHost
import SwiftUI
#if os(macOS)
import AppKit
#elseif os(iOS)
import UIKit
#endif

/// How a native editor lays out its text. The batch box is 13pt monospaced without wrapping and numbers its lines;
/// the description box is the Web `.input-ta` (14px, line height 1.65, padding 9×10, wrapping) over the panel colour;
/// the DDL editor is `.ddl-edit-ta` (14px, line height 1.7, padding 10×11, wrapping) with a line-number gutter.
struct InkuEditorStyle: Equatable {
    var fontSize: CGFloat = 13
    var monospaced = true
    var lineHeightMultiple: CGFloat?
    var wraps = false
    var lineNumbers = true
    var inset = CGSize(width: 10, height: 8)
    var drawsBackground = true

    static let batch = InkuEditorStyle()
    static let description = InkuEditorStyle(fontSize: 14, monospaced: false, lineHeightMultiple: 1.65, wraps: true,
                                             lineNumbers: false, inset: CGSize(width: 10, height: 9), drawsBackground: false)
    static let ddl = InkuEditorStyle(fontSize: 14, monospaced: false, lineHeightMultiple: 1.7, wraps: true,
                                     lineNumbers: true, inset: CGSize(width: 11, height: 10), drawsBackground: false)
}

/// A range an editor paints without changing its text: the grey band of a number or comment (Web LabelHighlight),
/// or a DDL token colour (Web `highlight.ts`). Painted as layout-manager temporary attributes, never while the IME composes.
struct InkuEditorMark: Equatable {
    enum Style: Equatable { case muted, token(DdlTokenClass), unknownName }
    let range: NSRange
    let style: Style

    static func descriptionLabels(_ text: String) -> [InkuEditorMark] {
        DescriptionLabels.excludedSpans(text).map { InkuEditorMark(range: $0.range, style: .muted) }
    }
}

/// A word to put at the caret (Web DdlEditor `insertWord`), replacing the selection.
struct InkuEditorInsertion: Equatable {
    let id = UUID()
    let text: String
}

@MainActor
struct BatchInputEditor: View {
    @Binding var text: String
    var isEditable = true
    var accessibilityLabel: String

    var body: some View {
        InkuTextEditor(text: $text, isEditable: isEditable, accessibilityLabel: accessibilityLabel, style: .batch)
    }
}

@MainActor
struct InkuTextEditor: View {
    @Binding var text: String
    var isEditable = true
    var accessibilityLabel: String
    var style = InkuEditorStyle.batch
    var marks: (String) -> [InkuEditorMark] = InkuEditorMark.descriptionLabels
    var insertion: Binding<InkuEditorInsertion?>? = nil
    @Environment(DisplaySettings.self) private var display
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        BatchNativeInputEditor(text: $text, isEditable: isEditable && isEnabled,
                               accessibilityLabel: accessibilityLabel,
                               textScale: display.preferences.textScale, colorScheme: colorScheme,
                               style: style, marks: marks, insertion: insertion)
            .clipped()
    }
}

/// Offsets address the original UTF-16 storage; the batch parser owns the line count.
private struct BatchEditorLineIndex {
    let starts: [Int]
    let count: Int

    init(_ text: String) {
        count = BatchInputLines.physicalLines(in: text).count
        var offsets = [0]
        var offset = 0
        var previousWasCR = false
        for scalar in text.unicodeScalars {
            offset += scalar.value > 0xffff ? 2 : 1
            if previousWasCR && scalar.value == 0x0a {
                offsets[offsets.count - 1] = offset
                previousWasCR = false
                continue
            }
            switch scalar.value {
            case 0x0a, 0x0d, 0x85, 0x2028, 0x2029: offsets.append(offset)
            default: break
            }
            previousWasCR = scalar.value == 0x0d
        }
        starts = offsets
    }

    func line(containing offset: Int) -> Int {
        var lower = 0
        var upper = starts.count
        while lower < upper {
            let middle = (lower + upper) / 2
            if starts[middle] <= offset { lower = middle + 1 } else { upper = middle }
        }
        return max(0, lower - 1)
    }
}

private func batchNumberLine(_ number: Int, font: CTFont, color: CGColor) -> CTLine {
    let attributes: [NSAttributedString.Key: Any] = [
        NSAttributedString.Key(kCTFontAttributeName as String): font,
        NSAttributedString.Key(kCTForegroundColorAttributeName as String): color,
    ]
    return CTLineCreateWithAttributedString(NSAttributedString(string: String(number), attributes: attributes))
}

private func batchDrawNumber(_ line: CTLine, baseline: CGPoint, context: CGContext) {
    context.saveGState()
    context.translateBy(x: baseline.x, y: baseline.y)
    context.scaleBy(x: 1, y: -1)
    context.textMatrix = .identity
    context.textPosition = .zero
    CTLineDraw(line, context)
    context.restoreGState()
}

#if os(macOS)
@MainActor
private struct BatchNativeInputEditor: NSViewRepresentable {
    @Binding var text: String
    let isEditable: Bool
    let accessibilityLabel: String
    let textScale: Double
    let colorScheme: ColorScheme
    let style: InkuEditorStyle
    let marks: (String) -> [InkuEditorMark]
    let insertion: Binding<InkuEditorInsertion?>?

    func makeCoordinator() -> Coordinator { Coordinator(text: $text) }

    func makeNSView(context: Context) -> BatchEditorScrollView {
        let scroll = BatchEditorScrollView()
        let storage = NSTextStorage()
        let layout = NSLayoutManager()
        layout.usesFontLeading = false
        let container = NSTextContainer(containerSize: NSSize(width: CGFloat.greatestFiniteMagnitude,
                                                              height: CGFloat.greatestFiniteMagnitude))
        container.widthTracksTextView = style.wraps
        container.heightTracksTextView = false
        container.lineFragmentPadding = 0
        storage.addLayoutManager(layout)
        layout.addTextContainer(container)
        let editor = BatchEditorTextView(frame: .zero, textContainer: container)
        editor.isRichText = false
        editor.importsGraphics = false
        editor.allowsUndo = true
        editor.isHorizontallyResizable = !style.wraps
        editor.isVerticallyResizable = true
        editor.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        editor.textContainerInset = NSSize(width: style.inset.width, height: style.inset.height)
        editor.isContinuousSpellCheckingEnabled = false
        editor.isGrammarCheckingEnabled = false
        editor.isAutomaticSpellingCorrectionEnabled = false
        editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.isAutomaticDashSubstitutionEnabled = false
        editor.isAutomaticTextReplacementEnabled = false
        editor.isAutomaticLinkDetectionEnabled = false
        editor.usesFindPanel = true
        editor.textColor = .labelColor
        editor.insertionPointColor = .labelColor
        editor.backgroundColor = .textBackgroundColor
        editor.drawsBackground = style.drawsBackground
        scroll.borderType = .noBorder
        scroll.backgroundColor = .textBackgroundColor
        scroll.drawsBackground = style.drawsBackground
        scroll.wraps = style.wraps
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = !style.wraps
        scroll.autohidesScrollers = true
        // AppKit no longer clips ordinary views to their bounds by default.
        scroll.clipsToBounds = true
        scroll.contentView.clipsToBounds = true
        scroll.documentView = editor
        var ruler: BatchEditorRuler?
        if style.lineNumbers {
            let gutter = BatchEditorRuler(scrollView: scroll, orientation: .verticalRuler)
            gutter.clipsToBounds = true
            gutter.clientView = editor
            gutter.reservedThicknessForMarkers = 0
            gutter.reservedThicknessForAccessoryView = 0
            gutter.setAccessibilityElement(false)
            scroll.verticalRulerView = gutter
            scroll.hasVerticalRuler = true
            scroll.hasHorizontalRuler = false
            scroll.rulersVisible = true
            ruler = gutter
        }
        context.coordinator.attach(scroll: scroll, editor: editor, ruler: ruler)
        context.coordinator.update(from: self)
        return scroll
    }

    func updateNSView(_ view: BatchEditorScrollView, context: Context) {
        context.coordinator.update(from: self)
    }

    static func dismantleNSView(_ view: BatchEditorScrollView, coordinator: Coordinator) {
        coordinator.detach()
    }

    @MainActor
    final class Coordinator: NSObject, NSTextViewDelegate {
        private var text: Binding<String>
        private weak var scroll: BatchEditorScrollView?
        private weak var editor: BatchEditorTextView?
        private weak var ruler: BatchEditorRuler?
        private var boundsObservation: NSObjectProtocol?
        private var settings: BatchNativeInputEditor?
        private var fontSize: CGFloat?
        private var pendingExternalText: String?
        private var replacingText = false
        private var lastInsertionID: UUID?

        init(text: Binding<String>) { self.text = text }

        func attach(scroll: BatchEditorScrollView, editor: BatchEditorTextView, ruler: BatchEditorRuler?) {
            self.scroll = scroll
            self.editor = editor
            self.ruler = ruler
            editor.delegate = self
            editor.onCompositionEnded = { [weak self] in
                DispatchQueue.main.async { [weak self] in self?.applyDeferredUpdates() }
            }
            scroll.contentView.postsBoundsChangedNotifications = true
            boundsObservation = NotificationCenter.default.addObserver(forName: NSView.boundsDidChangeNotification,
                object: scroll.contentView, queue: .main) { [weak ruler] _ in
                    MainActor.assumeIsolated { ruler?.needsDisplay = true }
                }
        }

        func detach() {
            if let boundsObservation { NotificationCenter.default.removeObserver(boundsObservation) }
            boundsObservation = nil
            editor?.delegate = nil
            editor?.onCompositionEnded = nil
            editor = nil
            scroll = nil
            ruler = nil
            settings = nil
        }

        func update(from settings: BatchNativeInputEditor) {
            self.settings = settings
            text = settings.$text
            guard let editor, let scroll else { return }
            let source = text.wrappedValue
            editor.setAccessibilityLabel(settings.accessibilityLabel)
            scroll.appearance = NSAppearance(named: settings.colorScheme == .dark ? .darkAqua : .aqua)
            if editor.hasMarkedText() {
                pendingExternalText = source == editor.string ? nil : source
                return
            }
            pendingExternalText = nil
            if editor.string != source { replaceText(with: source) }
            applySettings()
            applyMarks()
            if let request = settings.insertion?.wrappedValue, request.id != lastInsertionID {
                lastInsertionID = request.id
                let binding = settings.insertion
                // Editing the text changes SwiftUI state, so it waits until this update has finished.
                DispatchQueue.main.async { [weak self] in
                    self?.insert(request.text)
                    if binding?.wrappedValue?.id == request.id { binding?.wrappedValue = nil }
                }
            }
        }

        /// Web DdlEditor `insertWord`: the word replaces the selection, which the editor keeps while another control
        /// has focus, and the caret follows it.
        private func insert(_ word: String) {
            guard let editor, editor.isEditable, !editor.hasMarkedText(), !word.isEmpty else { return }
            let length = (editor.string as NSString).length
            let selected = editor.selectedRange()
            let range = NSRange(location: min(selected.location, length), length: min(selected.length, max(0, length - selected.location)))
            guard editor.shouldChangeText(in: range, replacementString: word) else { return }
            editor.textStorage?.replaceCharacters(in: range, with: NSAttributedString(string: word, attributes: editor.typingAttributes))
            editor.didChangeText()
            let caret = NSRange(location: range.location + (word as NSString).length, length: 0)
            editor.setSelectedRange(caret)
            editor.scrollRangeToVisible(caret)
            editor.window?.makeFirstResponder(editor)
        }

        /// Temporary attributes paint without touching the text, its undo or the IME's marked range.
        private func applyMarks() {
            guard let editor, let settings, let layout = editor.layoutManager, !editor.hasMarkedText() else { return }
            let full = NSRange(location: 0, length: (editor.string as NSString).length)
            for key in [NSAttributedString.Key.backgroundColor, .foregroundColor, .underlineStyle, .underlineColor] {
                layout.removeTemporaryAttribute(key, forCharacterRange: full)
            }
            for mark in settings.marks(editor.string) where mark.range.location >= 0 && NSMaxRange(mark.range) <= full.length {
                layout.addTemporaryAttributes(mark.style.attributes, forCharacterRange: mark.range)
            }
        }

        func textDidChange(_ notification: Notification) {
            guard !replacingText, let editor else { return }
            refreshLayout()
            if pendingExternalText == nil {
                if text.wrappedValue != editor.string { text.wrappedValue = editor.string }
            }
            if !editor.hasMarkedText() { applyDeferredUpdates() }
        }

        func textDidEndEditing(_ notification: Notification) { applyDeferredUpdates() }

        private func applyDeferredUpdates() {
            guard let editor, !editor.hasMarkedText() else { return }
            if pendingExternalText != nil {
                pendingExternalText = nil
                replaceText(with: text.wrappedValue)
            }
            applySettings()
            applyMarks()
        }

        private func applySettings() {
            guard let editor, let scroll, let settings else { return }
            if editor.isEditable != settings.isEditable { editor.isEditable = settings.isEditable }
            if !editor.isSelectable { editor.isSelectable = true }
            let size = settings.style.fontSize * CGFloat(settings.textScale)
            guard fontSize != size else { return }
            let origin = scroll.contentView.bounds.origin
            fontSize = size
            let font = settings.style.monospaced ? NSFont.monospacedSystemFont(ofSize: size, weight: .regular) : NSFont.systemFont(ofSize: size)
            let natural = ceil(font.ascender - font.descender + font.leading)
            let lineHeight = settings.style.lineHeightMultiple.map { ceil(size * $0) } ?? natural
            let paragraph = NSMutableParagraphStyle()
            paragraph.minimumLineHeight = lineHeight
            paragraph.maximumLineHeight = lineHeight
            paragraph.lineBreakMode = settings.style.wraps ? .byWordWrapping : .byClipping
            editor.font = font
            editor.defaultParagraphStyle = paragraph
            editor.typingAttributes = [.font: font, .foregroundColor: NSColor.labelColor, .paragraphStyle: paragraph,
                                       // CSS centres the glyphs in a tall line; TextKit puts the extra space above them.
                                       .baselineOffset: max(0, (lineHeight - natural) / 2)]
            editor.textStorage?.addAttributes(editor.typingAttributes, range: NSRange(location: 0, length: editor.string.utf16.count))
            ruler?.numberFont = CTFontCreateWithName(font.fontName as CFString, size, nil)
            refreshLayout()
            scroll.restore(origin: origin)
        }

        private func replaceText(with value: String) {
            guard let editor, let scroll, editor.string != value else { return }
            let selection = editor.selectedRanges
            let origin = scroll.contentView.bounds.origin
            replacingText = true
            editor.string = value
            editor.textStorage?.addAttributes(editor.typingAttributes, range: NSRange(location: 0, length: value.utf16.count))
            // Old undo ranges belong to the previous externally restored document.
            editor.undoManager?.removeAllActions()
            let length = value.utf16.count
            editor.selectedRanges = selection.map {
                let range = $0.rangeValue
                let location = min(range.location, length)
                return NSValue(range: NSRange(location: location, length: min(range.length, length - location)))
            }
            refreshLayout()
            scroll.restore(origin: origin)
            replacingText = false
        }

        private func refreshLayout() {
            guard let editor else { return }
            ruler?.lineIndex = BatchEditorLineIndex(editor.string)
            scroll?.resizeDocument()
            ruler?.needsDisplay = true
        }
    }
}

@MainActor
private final class BatchEditorTextView: NSTextView {
    var onCompositionEnded: (() -> Void)?
    override func unmarkText() {
        super.unmarkText()
        onCompositionEnded?()
    }
}

@MainActor
private final class BatchEditorScrollView: NSScrollView {
    private var resizingDocument = false
    /// A wrapping editor is exactly as wide as its viewport; the text grows downwards only.
    var wraps = false

    override func tile() {
        super.tile()
        resizeDocument()
    }

    func resizeDocument() {
        guard !resizingDocument, let editor = documentView as? NSTextView,
              let layout = editor.layoutManager, let container = editor.textContainer else { return }
        resizingDocument = true
        defer { resizingDocument = false }
        layout.ensureLayout(for: container)
        let used = layout.usedRect(for: container)
        let extra = layout.extraLineFragmentTextContainer === container ? layout.extraLineFragmentRect : .zero
        let inset = editor.textContainerInset
        let viewport = contentView.bounds.size
        let size = NSSize(width: wraps ? viewport.width : max(viewport.width, ceil(used.maxX + 2 * inset.width)),
                          height: max(viewport.height, ceil(max(used.maxY, extra.maxY) + 2 * inset.height)))
        editor.minSize = viewport
        if editor.frame.size != size { editor.setFrameSize(size) }
    }

    func restore(origin: NSPoint) {
        let clip = contentView
        let target = clip.constrainBoundsRect(NSRect(origin: origin, size: clip.bounds.size)).origin
        clip.scroll(to: target)
        reflectScrolledClipView(clip)
        verticalRulerView?.needsDisplay = true
    }
}

@MainActor
private final class BatchEditorRuler: NSRulerView {
    var lineIndex = BatchEditorLineIndex("") { didSet { updateThickness() } }
    var numberFont = CTFontCreateWithName("Menlo" as CFString, 13, nil) { didSet { updateThickness() } }
    override var isFlipped: Bool { true }

    override func drawHashMarksAndLabels(in rect: NSRect) {
        guard let scroll = scrollView, let context = NSGraphicsContext.current?.cgContext else { return }
        let viewport = convert(scroll.contentView.bounds, from: scroll.contentView)
        let gutter = NSRect(x: bounds.minX, y: viewport.minY, width: bounds.width, height: viewport.height)
        let drawingRect = rect.intersection(bounds).intersection(visibleRect).intersection(gutter)
        guard !drawingRect.isEmpty else { return }
        context.saveGState()
        defer { context.restoreGState() }
        context.clip(to: drawingRect)
        NSColor.controlBackgroundColor.setFill()
        drawingRect.fill()
        NSColor.separatorColor.setStroke()
        let separator = NSBezierPath()
        separator.move(to: NSPoint(x: bounds.maxX - 0.5, y: drawingRect.minY))
        separator.line(to: NSPoint(x: bounds.maxX - 0.5, y: drawingRect.maxY))
        separator.stroke()
        guard let editor = clientView as? NSTextView, let layout = editor.layoutManager,
              let container = editor.textContainer else { return }
        layout.ensureLayout(for: container)
        let textOrigin = editor.textContainerOrigin
        // Gutter visibility depends only on vertical position, including short rows when scrolled right.
        let editorRect = editor.convert(drawingRect, from: self)
        let visible = NSRect(x: 0, y: editorRect.minY - textOrigin.y,
                             width: max(1, layout.usedRect(for: container).maxX), height: editorRect.height)
        let glyphs = layout.glyphRange(forBoundingRect: visible, in: container)
        let first = glyphs.length > 0
            ? lineIndex.line(containing: layout.characterIndexForGlyph(at: glyphs.location))
            : max(0, lineIndex.starts.count - 1)
        let length = editor.string.utf16.count
        for index in first..<lineIndex.starts.count {
            let start = lineIndex.starts[index]
            let fragment: NSRect
            let baseline: CGFloat
            if start < length {
                let glyph = layout.glyphIndexForCharacter(at: start)
                fragment = layout.lineFragmentRect(forGlyphAt: glyph, effectiveRange: nil)
                baseline = fragment.minY + layout.location(forGlyphAt: glyph).y
            } else {
                fragment = layout.extraLineFragmentRect
                let offset = layout.numberOfGlyphs > 0
                    ? layout.location(forGlyphAt: layout.numberOfGlyphs - 1).y
                    : (editor.font.map { layout.defaultBaselineOffset(for: $0) } ?? CTFontGetAscent(numberFont))
                baseline = fragment.minY + offset
            }
            let point = convert(NSPoint(x: textOrigin.x, y: textOrigin.y + baseline), from: editor)
            if point.y > drawingRect.maxY + fragment.height { break }
            guard point.y >= drawingRect.minY - fragment.height else { continue }
            let number = batchNumberLine(index + 1, font: numberFont, color: NSColor.secondaryLabelColor.cgColor)
            let width = CGFloat(CTLineGetTypographicBounds(number, nil, nil, nil))
            batchDrawNumber(number, baseline: CGPoint(x: bounds.maxX - width - 8, y: point.y), context: context)
        }
    }

    override func scrollWheel(with event: NSEvent) { scrollView?.scrollWheel(with: event) }
    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        needsDisplay = true
    }

    private func updateThickness() {
        let number = batchNumberLine(max(1, lineIndex.count), font: numberFont, color: NSColor.secondaryLabelColor.cgColor)
        let thickness = max(34, ceil(CGFloat(CTLineGetTypographicBounds(number, nil, nil, nil)) + 18))
        if ruleThickness != thickness { ruleThickness = thickness }
        needsDisplay = true
    }
}

#elseif os(iOS)
@MainActor
private struct BatchNativeInputEditor: UIViewRepresentable {
    @Binding var text: String
    let isEditable: Bool
    let accessibilityLabel: String
    let textScale: Double
    let colorScheme: ColorScheme
    // iOS keeps the plain editor: no marks, and words are appended by the caller's binding.
    let style: InkuEditorStyle
    let marks: (String) -> [InkuEditorMark]
    let insertion: Binding<InkuEditorInsertion?>?

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
private final class BatchIOSTextView: UITextView {
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
        lineIndex = BatchEditorLineIndex(text ?? "")
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

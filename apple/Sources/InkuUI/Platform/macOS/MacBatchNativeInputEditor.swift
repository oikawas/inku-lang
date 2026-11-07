#if os(macOS)
import SwiftUI
import CoreText
import InkuHost
import AppKit
@MainActor
struct BatchNativeInputEditor: NSViewRepresentable {
    @Binding var text: String
    let isEditable: Bool
    let accessibilityLabel: String
    let textScale: Double
    let colorScheme: ColorScheme
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
        editor.focusOnAttach = style.focusOnAttach
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
            gutter.emptyLineCount = style.emptyLineCount
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
    final class Coordinator: NSObject, NSTextViewDelegate, @preconcurrency NSLayoutManagerDelegate {
        private var text: Binding<String>
        private var rangeState = RangeEditorState()
        private var rangeHover: Int?
        private var rangeEdit: (range: NSRange, length: Int)?
        private var lastRangeStatus: RangeEditorStatus?
        private weak var scroll: BatchEditorScrollView?
        private weak var editor: BatchEditorTextView?
        private weak var ruler: BatchEditorRuler?
        private var boundsObservation: NSObjectProtocol?
        private var settings: BatchNativeInputEditor?
        private var fontSize: CGFloat?
        private var pendingExternalText: String?
        private var replacingText = false
        private var lastInsertionID: UUID?
        /// Set by the author's own typing; a chosen word, a followed name or a restored text offers nothing.
        private var typedInsertion = false
        private var programmaticEdit = false
        private var completionValues: [String: String] = [:]
        private var completionLanguage: (source: Data, key: String, value: String)?
        private var marksCache = InkuEditorMarksCache()
        private var descriptionLineMarks: [Data: [InkuEditorMark]] = [:]
        private var paintedNames: [NSRange]?

        init(text: Binding<String>) { self.text = text }

        func attach(scroll: BatchEditorScrollView, editor: BatchEditorTextView, ruler: BatchEditorRuler?) {
            self.scroll = scroll
            self.editor = editor
            self.ruler = ruler
            editor.delegate = self
            editor.layoutManager?.delegate = self
            editor.onCompositionEnded = { [weak self] in
                DispatchQueue.main.async { [weak self] in self?.applyDeferredUpdates() }
            }
            editor.onFocusChanged = { [weak self] in self?.refreshRanges() }
            editor.onHover = { [weak self] index in self?.hover(at: index) }
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
            editor?.layoutManager?.delegate = nil
            editor?.onCompositionEnded = nil
            editor?.onFocusChanged = nil
            editor?.onHover = nil
            editor?.completionRange = nil
            editor?.normalizeCompletion = nil
            editor = nil
            scroll = nil
            ruler = nil
            settings = nil
            marksCache = InkuEditorMarksCache()
            descriptionLineMarks.removeAll()
            paintedNames = nil
        }

        func update(from settings: BatchNativeInputEditor) {
            self.settings = settings
            text = settings.$text
            guard let editor, let scroll else { return }
            editor.hoverEnabled = !settings.covered
            let source = text.wrappedValue
            editor.setAccessibilityLabel(settings.accessibilityLabel)
            if (settings.completions == nil) != (editor.completionRange == nil) {
                editor.completionRange = settings.completions == nil ? nil : { [weak self] in self?.completionMatch()?.range }
            }
            editor.normalizeCompletion = { [weak self] value in self?.completionValues[value] ?? value }
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
                    self?.insert(request)
                    if binding?.wrappedValue?.id == request.id { binding?.wrappedValue = nil }
                }
            }
        }

        /// Web DdlEditor `insertWord`: the word replaces the selection, which the editor keeps while another control
        /// has focus, and the caret follows it.
        private func insert(_ request: InkuEditorInsertion) {
            let word = request.text
            guard let editor, editor.isEditable, !editor.hasMarkedText(), !word.isEmpty || request.replacesAll else { return }
            let length = (editor.string as NSString).length
            let selected = request.replacesAll ? NSRange(location: 0, length: length)
                : request.atEndUnlessUsed && !editor.used ? NSRange(location: length, length: 0) : editor.selectedRange()
            let range = NSRange(location: min(selected.location, length), length: min(selected.length, max(0, length - selected.location)))
            programmaticEdit = true
            defer { programmaticEdit = false }
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
            let changed = marksCache.update(source: editor.string, key: settings.marksKey) { source in
                guard settings.marksKey == .description else { return settings.marks(source) }
                var next: [Data: [InkuEditorMark]] = [:]
                var offset = 0
                var result: [InkuEditorMark] = []
                for line in source.components(separatedBy: "\n") {
                    let key = Data(line.utf8)
                    let local = next[key] ?? descriptionLineMarks[key] ?? InkuEditorMark.descriptionLabels(line)
                    next[key] = local
                    result += local.map { InkuEditorMark(range: NSRange(location: $0.range.location + offset, length: $0.range.length), style: $0.style) }
                    offset += line.utf16.count + 1
                }
                descriptionLineMarks = next
                return result
            }
            let names = settings.rangeTable == nil ? [] : rangeState.names
            guard changed || paintedNames != names else { return }
            paintedNames = names
            let full = NSRange(location: 0, length: (editor.string as NSString).length)
            for key in [NSAttributedString.Key.backgroundColor, .foregroundColor, .underlineStyle, .underlineColor] {
                layout.removeTemporaryAttribute(key, forCharacterRange: full)
            }
            for mark in marksCache.marks where mark.range.location >= 0 && NSMaxRange(mark.range) <= full.length {
                layout.addTemporaryAttributes(mark.style.attributes, forCharacterRange: mark.range)
            }
            // `.cm-ddl-range-name`: the place word of a folded range, with a dotted underline.
            guard settings.rangeTable != nil else { return }
            for name in rangeState.names where NSMaxRange(name) <= full.length {
                layout.addTemporaryAttributes([.underlineStyle: NSUnderlineStyle.single.rawValue | NSUnderlineStyle.patternDot.rawValue,
                                               .underlineColor: NSColor.secondaryLabelColor], forCharacterRange: name)
            }
        }

        // MARK: Numeric ranges (Web codemirror-ranges.ts)

        /// Folded characters generate no glyphs: the text itself never changes.
        func layoutManager(_ layoutManager: NSLayoutManager, shouldGenerateGlyphs glyphs: UnsafePointer<CGGlyph>,
                           properties props: UnsafePointer<NSLayoutManager.GlyphProperty>, characterIndexes charIndexes: UnsafePointer<Int>,
                           font aFont: NSFont, forGlyphRange glyphRange: NSRange) -> Int {
            let hidden = rangeState.hidden
            guard !hidden.isEmpty else { return 0 }
            let rangeIndex = InkuHiddenRangeIndex(hidden)
            var changed = false
            var properties = (0..<glyphRange.length).map { index -> NSLayoutManager.GlyphProperty in
                let character = charIndexes[index]
                if rangeIndex.contains(character) { changed = true; return .null }
                return props[index]
            }
            guard changed else { return 0 }
            properties.withUnsafeMutableBufferPointer { buffer in
                layoutManager.setGlyphs(glyphs, properties: buffer.baseAddress!, characterIndexes: charIndexes, font: aFont, forGlyphRange: glyphRange)
            }
            return glyphRange.length
        }

        func textView(_ textView: NSTextView, shouldChangeTextIn affectedCharRange: NSRange, replacementString: String?) -> Bool {
            typedInsertion = !programmaticEdit && !(replacementString ?? "").isEmpty
            if settings?.rangeTable != nil, !textView.hasMarkedText(), let replacementString {
                rangeState.pendingName = rangeState.pendingName(afterEditing: affectedCharRange)
                rangeEdit = (affectedCharRange, (replacementString as NSString).length)
            }
            return true
        }

        func textViewDidChangeSelection(_ notification: Notification) {
            guard let editor, let settings, let table = settings.rangeTable, !replacingText, !editor.hasMarkedText() else { return }
            let focused = editor.window?.firstResponder === editor
            programmaticEdit = true
            defer { programmaticEdit = false }
            if editor.isEditable, let follow = rangeState.followedName(text: editor.string, selection: editor.selectedRange(), focused: focused, table: table),
               editor.shouldChangeText(in: follow.range, replacementString: follow.name) {
                // Web followNameOnLeaving: the name follows the numbers the author edited, once the caret leaves.
                let selection = editor.selectedRange()
                rangeState.pendingName = false
                editor.textStorage?.replaceCharacters(in: follow.range, with: NSAttributedString(string: follow.name, attributes: editor.typingAttributes))
                editor.didChangeText()
                let shift = (follow.name as NSString).length - follow.range.length
                editor.setSelectedRange(NSRange(location: selection.location >= NSMaxRange(follow.range) ? selection.location + shift : selection.location,
                                                length: selection.length))
                return
            }
            refreshRanges()
        }

        private func hover(at index: Int?) {
            settings?.onCharacterHover?(index)
            let start = index.flatMap { index in
                rangeState.ranges.first { range in rangeState.names.contains { NSLocationInRange(index, $0) && $0.location >= range.nameStart && NSMaxRange($0) <= range.nameEnd } }?.start
            }
            guard start != rangeHover else { return }
            rangeHover = start
            refreshRanges()
        }

        /// Re-reads the ranges for the current text, caret and focus; refolds only when the folded set changes.
        func refreshRanges(reset: Bool = false) {
            guard let editor, let settings, let table = settings.rangeTable else { return }
            if editor.hasMarkedText() { report(RangeEditorStatus(preview: lastRangeStatus?.preview, invalid: lastRangeStatus?.invalid ?? false, composing: true)); return }
            var previous: RangeEditorState? = reset ? nil : rangeState
            if let edit = rangeEdit, let current = previous { previous = current.mapped(edit: edit.range, replacementLength: edit.length) }
            rangeEdit = nil
            let focused = editor.window?.firstResponder === editor
            let next = RangeEditorState.derive(text: editor.string, selection: editor.selectedRange(), focused: focused,
                                               hover: reset ? nil : rangeHover, previous: previous, table: table)
            let refold = next.hidden != rangeState.hidden
            rangeState = next
            if refold, let layout = editor.layoutManager {
                let full = NSRange(location: 0, length: (editor.string as NSString).length)
                layout.invalidateGlyphs(forCharacterRange: full, changeInLength: 0, actualCharacterRange: nil)
                layout.invalidateLayout(forCharacterRange: full, actualCharacterRange: nil)
                refreshLayout()
            }
            applyMarks()
            report(RangeEditorStatus(preview: next.preview, invalid: next.invalid, composing: false))
        }

        private func report(_ status: RangeEditorStatus) {
            guard status != lastRangeStatus, let callback = settings?.onRangeStatus else { return }
            lastRangeStatus = status
            DispatchQueue.main.async { callback(status) }
        }

        func textDidChange(_ notification: Notification) {
            guard !replacingText, let editor else { return }
            // TextKit can drop temporary attributes even if IME edits return to the same text.
            paintedNames = nil
            refreshLayout()
            refreshRanges()
            if pendingExternalText == nil {
                if text.wrappedValue != editor.string { text.wrappedValue = editor.string }
            }
            if !editor.hasMarkedText() { applyDeferredUpdates() }
            offerCompletions()
        }

        /// Web `ddlCompletions`: nothing while read-only, composing, or with the caret in an open range's numbers.
        private func completionMatch(resolvedLanguage: String? = nil) -> DdlCompletions.Match? {
            guard let editor, let completions = settings?.completions, editor.isEditable, !editor.hasMarkedText() else { return nil }
            let selection = editor.selectedRange()
            guard selection.length == 0 else { return nil }
            let body = rangeState.active.map { NSRange(location: $0.bodyStart, length: $0.bodyEnd - $0.bodyStart) }
            let language = resolvedLanguage ?? completionLanguage(for: editor.string, completions: completions)
            return completions.match(text: editor.string, caret: selection.location, excluded: body, resolvedLanguage: language)
        }

        private func completionLanguage(for text: String, completions: DdlCompletions) -> String {
            let source = Data(text.utf8)
            if let cached = completionLanguage, cached.source == source, cached.key == completions.languageKey { return cached.value }
            let value = completions.language(text)
            completionLanguage = (source, completions.languageKey, value)
            return value
        }

        /// Web `activateOnTyping`: the list opens as the author types a word some candidate starts with. No item is
        /// chosen until the author picks one, so typing on is never replaced.
        private func offerCompletions() {
            guard typedInsertion, let editor, !editor.completing else { return }
            typedInsertion = false
            guard completionMatch() != nil else { return }
            DispatchQueue.main.async { [weak editor] in
                guard let editor, editor.window?.firstResponder === editor, !editor.hasMarkedText() else { return }
                editor.complete(nil)
            }
        }

        func textView(_ textView: NSTextView, completions words: [String], forPartialWordRange charRange: NSRange,
                      indexOfSelectedItem index: UnsafeMutablePointer<Int>?) -> [String] {
            guard let editor, let completions = settings?.completions else { return words }
            let language = completionLanguage(for: editor.string, completions: completions)
            guard let match = completionMatch(resolvedLanguage: language), match.range == charRange else { return [] }
            index?.pointee = -1
            completionValues.removeAll()
            return match.items.map { item in
                let label = completions.presentation(for: item, text: editor.string, resolvedLanguage: language)
                completionValues[label] = item
                return label
            }
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
            refreshRanges(reset: true)
        }

        private func refreshLayout() {
            guard let editor else { return }
            if let ruler { ruler.lineIndex = BatchEditorLineIndex(editor.string, reusing: ruler.lineIndex) }
            scroll?.resizeDocument()
            ruler?.needsDisplay = true
        }
    }
}

@MainActor
final class BatchEditorTextView: NSTextView {
    var focusOnAttach = false
    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard focusOnAttach, isEditable, let window else { return }
        focusOnAttach = false
        DispatchQueue.main.async { [weak self, weak window] in
            guard let self, let window, self.window === window, self.isEditable else { return }
            window.makeFirstResponder(self)
        }
    }
    var onCompositionEnded: (() -> Void)?
    /// Set once the author focuses the editor; until then a chosen word goes at the end.
    private(set) var used = false
    var onFocusChanged: (() -> Void)?
    /// The character under the pointer, for the range frame on hover (Web `hoveredRange`).
    var onHover: ((Int?) -> Void)?
    var hoverEnabled = true { didSet { if oldValue != hoverEnabled { updateTrackingAreas() } } }
    private var hoverArea: NSTrackingArea?
    private var lastHoverIndex: Int?
    /// The word the completion list replaces; nil leaves completion off (the system's word range is not used).
    var completionRange: (() -> NSRange?)?
    var normalizeCompletion: ((String) -> String)?
    /// True while the completion list writes its candidate into the text.
    private(set) var completing = false
    override var rangeForUserCompletion: NSRange {
        guard let completionRange else { return super.rangeForUserCompletion }
        return completionRange() ?? NSRange(location: NSNotFound, length: 0)
    }
    override func insertCompletion(_ word: String, forPartialWordRange charRange: NSRange, movement: Int, isFinal flag: Bool) {
        completing = true
        defer { completing = false }
        super.insertCompletion(normalizeCompletion?(word) ?? word, forPartialWordRange: charRange, movement: movement, isFinal: flag)
    }
    override func becomeFirstResponder() -> Bool {
        let became = super.becomeFirstResponder()
        if became { used = true; DispatchQueue.main.async { [weak self] in self?.onFocusChanged?() } }
        return became
    }
    override func resignFirstResponder() -> Bool {
        let resigned = super.resignFirstResponder()
        if resigned { DispatchQueue.main.async { [weak self] in self?.onFocusChanged?() } }
        return resigned
    }
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let hoverArea { removeTrackingArea(hoverArea) }
        hoverArea = nil
        guard hoverEnabled else { return }
        let area = NSTrackingArea(rect: .zero, options: [.mouseMoved, .mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect], owner: self)
        addTrackingArea(area); hoverArea = area
    }
    override func mouseMoved(with event: NSEvent) {
        super.mouseMoved(with: event)
        guard onHover != nil else { return }
        let point = convert(event.locationInWindow, from: nil)
        let index = characterIndexForInsertion(at: point)
        guard lastHoverIndex != index else { return }
        lastHoverIndex = index
        onHover?(index)
    }
    override func mouseExited(with event: NSEvent) {
        super.mouseExited(with: event)
        guard lastHoverIndex != nil else { return }
        lastHoverIndex = nil
        onHover?(nil)
    }
    override func unmarkText() {
        super.unmarkText()
        onCompositionEnded?()
    }
}

@MainActor
final class BatchEditorScrollView: NSScrollView {
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
final class BatchEditorRuler: NSRulerView {
    var emptyLineCount = 1
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
        if length == 0, emptyLineCount > 1, let font = editor.font {
            let lineHeight = editor.defaultParagraphStyle?.maximumLineHeight ?? layout.defaultLineHeight(for: font)
            let baseline = layout.defaultBaselineOffset(for: font)
            for index in 0..<emptyLineCount {
                let point = convert(NSPoint(x: textOrigin.x, y: textOrigin.y + baseline + CGFloat(index) * lineHeight), from: editor)
                let number = batchNumberLine(index + 1, font: numberFont, color: NSColor.secondaryLabelColor.cgColor)
                let width = CGFloat(CTLineGetTypographicBounds(number, nil, nil, nil))
                batchDrawNumber(number, baseline: CGPoint(x: bounds.maxX - width - 8, y: point.y), context: context)
            }
            return
        }
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


#endif

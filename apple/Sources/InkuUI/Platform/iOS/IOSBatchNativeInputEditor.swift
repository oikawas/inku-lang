#if os(iOS)
import SwiftUI
import CoreText
import InkuHost
import UIKit

/// The iOS text editor behind `InkuTextEditor`: a TextKit 1 `UITextView` wired to the same shared rules as the Mac's
/// (MacBatchNativeInputEditor.swift): the style's layout, the marks (`InkuEditorMarksCache`), numeric range folding
/// (`RangeEditorState`), DDL completions (`DdlCompletions`) and word insertion. Two things differ from the Mac:
/// - iOS has no layout-manager temporary attributes, so marks are character attributes (colours and underlines only),
///   painted when no text is being composed and kept out of undo.
/// - iOS has no text-view completion window, so a small list floats at the caret (`IOSCompletionList`).
/// A finger has no hover, so the range frame under the pointer (`onCharacterHover`) is not reported; a folded range opens
/// when the caret enters it.
/// The editor is not a shared SwiftUI `TextEditor`: editable attributed text needs iOS 26 and macOS 26, and it still has
/// no glyph folding, line-number gutter or caret rectangles (step 4 plan §8, 2026-11-08).
@MainActor
struct BatchNativeInputEditor: UIViewRepresentable {
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
    func makeUIView(context: Context) -> BatchIOSTextView {
        let storage = NSTextStorage()
        let layout = NSLayoutManager()
        layout.usesFontLeading = false
        let container = NSTextContainer(size: CGSize(width: 0, height: CGFloat.greatestFiniteMagnitude))
        container.widthTracksTextView = true
        container.heightTracksTextView = false
        container.lineFragmentPadding = 0
        storage.addLayoutManager(layout)
        layout.addTextContainer(container)
        let editor = BatchIOSTextView(frame: .zero, textContainer: container)
        editor.style = style
        editor.autocorrectionType = .no
        editor.autocapitalizationType = .none
        editor.spellCheckingType = .no
        editor.smartQuotesType = .no
        editor.smartDashesType = .no
        editor.smartInsertDeleteType = .no
        editor.textColor = .label
        editor.backgroundColor = style.drawsBackground ? .secondarySystemBackground : .clear
        editor.alwaysBounceVertical = false
        // iPhone (ios-app step 7): the keyboard covers half the screen and has no key that closes it; a Done bar does.
        if UIDevice.current.userInterfaceIdiom == .phone {
            let bar = UIToolbar(frame: CGRect(x: 0, y: 0, width: 320, height: 44))
            bar.items = [UIBarButtonItem(systemItem: .flexibleSpace),
                         UIBarButtonItem(systemItem: .done, primaryAction: UIAction { [weak editor] _ in editor?.resignFirstResponder() })]
            bar.sizeToFit()
            editor.inputAccessoryView = bar
        }
        context.coordinator.attach(editor)
        context.coordinator.update(from: self)
        return editor
    }
    func updateUIView(_ view: BatchIOSTextView, context: Context) { context.coordinator.update(from: self) }
    static func dismantleUIView(_ view: BatchIOSTextView, coordinator: Coordinator) { coordinator.detach() }

    @MainActor
    final class Coordinator: NSObject, UITextViewDelegate, @preconcurrency NSLayoutManagerDelegate {
        private var text: Binding<String>
        private(set) weak var editor: BatchIOSTextView?
        private var settings: BatchNativeInputEditor?
        private var pendingExternalText: String?
        private var replacingText = false
        private var fontSize: CGFloat?
        private var baseAttributes: [NSAttributedString.Key: Any] = [:]
        private var lastInsertionID: UUID?
        /// Set by the author's own typing; a chosen word, a followed name or a restored text offers nothing.
        private var typedInsertion = false
        private var programmaticEdit = false
        /// Whether the IME held marked text at the last change. Committing it is the author's typing, though iOS
        /// sends no `shouldChangeTextIn` for the commit (step 4 screen check: no list after converting 「ガッ」).
        private var wasComposing = false
        private var completionValues: [String: String] = [:]
        private var completionLanguage: (source: Data, key: String, value: String)?
        private var completionMatchRange: NSRange?
        private var marksCache = InkuEditorMarksCache()
        private var descriptionLineMarks: [Data: [InkuEditorMark]] = [:]
        private var paintedNames: [NSRange]?
        private var rangeState = RangeEditorState()
        private var rangeEdit: (range: NSRange, length: Int)?
        private var lastRangeStatus: RangeEditorStatus?

        init(text: Binding<String>) { self.text = text }

        func attach(_ editor: BatchIOSTextView) {
            self.editor = editor
            editor.delegate = self
            editor.layoutManager.delegate = self
            editor.onCompositionEnded = { [weak self] in
                DispatchQueue.main.async { [weak self] in self?.compositionEnded() }
            }
            editor.onFocusChanged = { [weak self] in
                self?.refreshRanges()
                if self?.editor?.isFirstResponder != true { self?.editor?.completionList.dismiss() }
            }
            editor.completionList.onPick = { [weak self] label in self?.insertCompletion(label) }
        }

        func detach() {
            editor?.delegate = nil
            editor?.layoutManager.delegate = nil
            editor?.onCompositionEnded = nil
            editor?.onFocusChanged = nil
            editor?.completionList.onPick = nil
            editor?.completionList.dismiss()
            editor = nil
            settings = nil
            marksCache = InkuEditorMarksCache()
            descriptionLineMarks.removeAll()
            paintedNames = nil
        }

        func update(from settings: BatchNativeInputEditor) {
            self.settings = settings
            text = settings.$text
            guard let editor else { return }
            let source = text.wrappedValue
            editor.accessibilityLabel = settings.accessibilityLabel
            editor.overrideUserInterfaceStyle = settings.colorScheme == .dark ? .dark : .light
            if editor.style != settings.style {
                editor.style = settings.style
                editor.backgroundColor = settings.style.drawsBackground ? .secondarySystemBackground : .clear
                fontSize = nil
            }
            if editor.markedTextRange != nil {
                pendingExternalText = source == editor.text ? nil : source
                return
            }
            pendingExternalText = nil
            if editor.text != source { replaceText(with: source) }
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

        // MARK: Editing

        /// Replaces `range` through the text input system, so undo records it as on the Mac.
        /// `followsName`: the edit is the name following its numbers, which leaves no name pending (the Mac clears it
        /// between `shouldChangeText` and the edit).
        private func replace(_ range: NSRange, with value: String, followsName: Bool = false) {
            guard let editor,
                  let start = editor.position(from: editor.beginningOfDocument, offset: range.location),
                  let end = editor.position(from: start, offset: range.length),
                  let textRange = editor.textRange(from: start, to: end) else { return }
            typedInsertion = false
            if settings?.rangeTable != nil {
                rangeState.pendingName = followsName ? false : rangeState.pendingName(afterEditing: range)
                rangeEdit = (range, (value as NSString).length)
            }
            programmaticEdit = true
            editor.replace(textRange, withText: value)
            programmaticEdit = false
            textChanged()
        }

        /// Web DdlEditor `insertWord`: the word replaces the selection, and the caret follows it.
        private func insert(_ request: InkuEditorInsertion) {
            let word = request.text
            guard let editor, editor.isEditable, editor.markedTextRange == nil, !word.isEmpty || request.replacesAll else { return }
            let length = (editor.text as NSString).length
            let selected = request.replacesAll ? NSRange(location: 0, length: length)
                : request.atEndUnlessUsed && !editor.used ? NSRange(location: length, length: 0) : editor.selectedRange
            let range = NSRange(location: min(selected.location, length), length: min(selected.length, max(0, length - selected.location)))
            replace(range, with: word)
            let caret = NSRange(location: range.location + (word as NSString).length, length: 0)
            editor.selectedRange = caret
            editor.scrollRangeToVisible(caret)
            if editor.isEditable { _ = editor.becomeFirstResponder() }
        }

        func textView(_ textView: UITextView, shouldChangeTextIn range: NSRange, replacementText: String) -> Bool {
            typedInsertion = !programmaticEdit && !replacementText.isEmpty
            if settings?.rangeTable != nil, textView.markedTextRange == nil {
                rangeState.pendingName = rangeState.pendingName(afterEditing: range)
                rangeEdit = (range, (replacementText as NSString).length)
            }
            return true
        }

        func textViewDidChange(_ textView: UITextView) {
            guard !programmaticEdit else { return }
            textChanged()
        }

        /// The IME committed its marked text without changing it: offer completions as for typed text.
        private func compositionEnded() {
            applyDeferredUpdates()
            guard wasComposing, let editor, editor.markedTextRange == nil else { return }
            wasComposing = false
            typedInsertion = true
            updateCompletions()
        }

        private func textChanged() {
            guard !replacingText, let editor else { return }
            let composing = editor.markedTextRange != nil
            if wasComposing && !composing && !programmaticEdit { typedInsertion = true }
            wasComposing = composing
            paintedNames = nil
            editor.refreshGutter()
            refreshRanges()
            if pendingExternalText == nil {
                let value = editor.text ?? ""
                if text.wrappedValue != value { text.wrappedValue = value }
            }
            if editor.markedTextRange == nil { applyDeferredUpdates() }
            updateCompletions()
        }

        func textViewDidChangeSelection(_ textView: UITextView) {
            guard let editor, !replacingText else { return }
            editor.typingAttributes = baseAttributes.isEmpty ? editor.typingAttributes : baseAttributes
            // A caret moved by hand closes the list; typing moves it too, and `textChanged` reopens it after.
            if !typedInsertion, let shown = completionMatchRange, editor.selectedRange.location != NSMaxRange(shown) {
                closeCompletions()
            }
            guard let settings, let table = settings.rangeTable, editor.markedTextRange == nil else { return }
            if editor.isEditable, !programmaticEdit,
               let follow = rangeState.followedName(text: editor.text, selection: editor.selectedRange,
                                                    focused: editor.isFirstResponder, table: table) {
                // Web followNameOnLeaving: the name follows the numbers the author edited, once the caret leaves.
                let selection = editor.selectedRange
                replace(follow.range, with: follow.name, followsName: true)
                let shift = (follow.name as NSString).length - follow.range.length
                editor.selectedRange = NSRange(location: selection.location >= NSMaxRange(follow.range) ? selection.location + shift : selection.location,
                                               length: selection.length)
                return
            }
            refreshRanges()
        }

        func textViewDidEndEditing(_ textView: UITextView) {
            closeCompletions()
            applyDeferredUpdates()
        }

        func scrollViewDidScroll(_ scrollView: UIScrollView) { editor?.setNeedsLayout() }

        func applyDeferredUpdates() {
            guard let editor, editor.markedTextRange == nil else { return }
            if pendingExternalText != nil {
                pendingExternalText = nil
                replaceText(with: text.wrappedValue)
            }
            applySettings()
            applyMarks()
        }

        // MARK: Layout

        /// The Mac's `applySettings`: the style's font and line height times the text-size setting, glyphs centred in
        /// the tall line as CSS does.
        private func applySettings() {
            guard let editor, let settings else { return }
            if editor.isEditable != settings.isEditable { editor.isEditable = settings.isEditable }
            if !editor.isSelectable { editor.isSelectable = true }
            let style = settings.style
            let size = style.fontSize * CGFloat(settings.textScale)
            guard fontSize != size else { return }
            fontSize = size
            let offset = editor.contentOffset
            let font = style.monospaced ? UIFont.monospacedSystemFont(ofSize: size, weight: .regular) : UIFont.systemFont(ofSize: size)
            let natural = ceil(font.ascender - font.descender + font.leading)
            let lineHeight = style.lineHeightMultiple.map { ceil(size * $0) } ?? natural
            let paragraph = NSMutableParagraphStyle()
            paragraph.minimumLineHeight = lineHeight
            paragraph.maximumLineHeight = lineHeight
            paragraph.lineBreakMode = .byWordWrapping
            baseAttributes = [.font: font, .foregroundColor: UIColor.label, .paragraphStyle: paragraph,
                              .baselineOffset: max(0, (lineHeight - natural) / 2)]
            editor.font = font
            editor.typingAttributes = baseAttributes
            paintedNames = nil
            marksCache = InkuEditorMarksCache()
            editor.lineHeight = lineHeight
            editor.refreshGutter()
            paint()
            editor.setContentOffset(offset, animated: false)
        }

        private func replaceText(with value: String) {
            guard let editor, editor.text != value else { return }
            let selection = editor.selectedRange
            let offset = editor.contentOffset
            replacingText = true
            editor.text = value
            if !baseAttributes.isEmpty { editor.typingAttributes = baseAttributes }
            // Old undo ranges belong to the previous externally restored document.
            editor.undoManager?.removeAllActions()
            let length = value.utf16.count
            let location = min(selection.location, length)
            editor.selectedRange = NSRange(location: location, length: min(selection.length, length - location))
            editor.refreshGutter()
            editor.setContentOffset(offset, animated: false)
            replacingText = false
            paintedNames = nil
            marksCache = InkuEditorMarksCache()
            refreshRanges(reset: true)
        }

        // MARK: Marks

        /// The Mac's `applyMarks`, painted as character attributes: never while the IME composes, and only when the
        /// marks or the folded names change.
        private func applyMarks() {
            guard let editor, let settings, editor.markedTextRange == nil else { return }
            let changed = marksCache.update(source: editor.text, key: settings.marksKey) { source in
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
            paint()
        }

        /// Resets every character to the editor's own attributes, then adds the marks. Only attributes change, so the
        /// text, selection and caret stay; undo registration is off so the colours are never undone.
        private func paint() {
            guard let editor, !baseAttributes.isEmpty, editor.markedTextRange == nil else { return }
            let storage = editor.textStorage
            let full = NSRange(location: 0, length: storage.length)
            let selection = editor.selectedRange
            editor.undoManager?.disableUndoRegistration()
            storage.beginEditing()
            storage.setAttributes(baseAttributes, range: full)
            for mark in marksCache.marks where mark.range.location >= 0 && NSMaxRange(mark.range) <= full.length {
                storage.addAttributes(mark.style.attributes, range: mark.range)
            }
            // `.cm-ddl-range-name`: the place word of a folded range, with a dotted underline.
            if settings?.rangeTable != nil {
                for name in rangeState.names where NSMaxRange(name) <= full.length {
                    storage.addAttributes([.underlineStyle: NSUnderlineStyle.single.rawValue | NSUnderlineStyle.patternDot.rawValue,
                                           .underlineColor: UIColor.secondaryLabel], range: name)
                }
            }
            storage.endEditing()
            editor.undoManager?.enableUndoRegistration()
            if editor.selectedRange != selection { editor.selectedRange = selection }
            editor.typingAttributes = baseAttributes
        }

        // MARK: Numeric ranges (Web codemirror-ranges.ts)

        /// Folded characters generate no glyphs: the text itself never changes.
        func layoutManager(_ layoutManager: NSLayoutManager, shouldGenerateGlyphs glyphs: UnsafePointer<CGGlyph>,
                           properties props: UnsafePointer<NSLayoutManager.GlyphProperty>, characterIndexes charIndexes: UnsafePointer<Int>,
                           font aFont: UIFont, forGlyphRange glyphRange: NSRange) -> Int {
            let hidden = rangeState.hidden
            guard !hidden.isEmpty else { return 0 }
            let rangeIndex = InkuHiddenRangeIndex(hidden)
            var changed = false
            var properties = (0..<glyphRange.length).map { index -> NSLayoutManager.GlyphProperty in
                if rangeIndex.contains(charIndexes[index]) { changed = true; return .null }
                return props[index]
            }
            guard changed else { return 0 }
            properties.withUnsafeMutableBufferPointer { buffer in
                layoutManager.setGlyphs(glyphs, properties: buffer.baseAddress!, characterIndexes: charIndexes, font: aFont, forGlyphRange: glyphRange)
            }
            return glyphRange.length
        }

        /// Re-reads the ranges for the current text, caret and focus; refolds only when the folded set changes.
        func refreshRanges(reset: Bool = false) {
            guard let editor, let settings, let table = settings.rangeTable else { return }
            if editor.markedTextRange != nil {
                report(RangeEditorStatus(preview: lastRangeStatus?.preview, invalid: lastRangeStatus?.invalid ?? false, composing: true))
                return
            }
            var previous: RangeEditorState? = reset ? nil : rangeState
            if let edit = rangeEdit, let current = previous { previous = current.mapped(edit: edit.range, replacementLength: edit.length) }
            rangeEdit = nil
            let next = RangeEditorState.derive(text: editor.text, selection: editor.selectedRange, focused: editor.isFirstResponder,
                                               hover: nil, previous: previous, table: table)
            let refold = next.hidden != rangeState.hidden
            rangeState = next
            if refold {
                let layout = editor.layoutManager
                let full = NSRange(location: 0, length: (editor.text as NSString).length)
                layout.invalidateGlyphs(forCharacterRange: full, changeInLength: 0, actualCharacterRange: nil)
                layout.invalidateLayout(forCharacterRange: full, actualCharacterRange: nil)
                editor.refreshGutter()
            }
            applyMarks()
            report(RangeEditorStatus(preview: next.preview, invalid: next.invalid, composing: false))
        }

        private func report(_ status: RangeEditorStatus) {
            guard status != lastRangeStatus, let callback = settings?.onRangeStatus else { return }
            lastRangeStatus = status
            DispatchQueue.main.async { callback(status) }
        }

        // MARK: Completions (Web ddlCompletions)

        /// Nothing while read-only, composing, with a selection, or with the caret in an open range's numbers.
        private func completionMatch(resolvedLanguage: String? = nil) -> DdlCompletions.Match? {
            guard let editor, let completions = settings?.completions, editor.isEditable, editor.markedTextRange == nil else { return nil }
            let selection = editor.selectedRange
            guard selection.length == 0 else { return nil }
            let body = rangeState.active.map { NSRange(location: $0.bodyStart, length: $0.bodyEnd - $0.bodyStart) }
            let language = resolvedLanguage ?? completionLanguage(for: editor.text, completions: completions)
            return completions.match(text: editor.text, caret: selection.location, excluded: body, resolvedLanguage: language)
        }

        private func completionLanguage(for text: String, completions: DdlCompletions) -> String {
            let source = Data(text.utf8)
            if let cached = completionLanguage, cached.source == source, cached.key == completions.languageKey { return cached.value }
            let value = completions.language(text)
            completionLanguage = (source, completions.languageKey, value)
            return value
        }

        /// Web `activateOnTyping`: the list opens as the author types a word some candidate starts with, and follows
        /// the typing. No item is chosen until the author picks one, so typing on is never replaced.
        private func updateCompletions() {
            let typed = typedInsertion
            typedInsertion = false
            guard let editor, let completions = settings?.completions else { return }
            guard typed || completionMatchRange != nil else { return }
            let language = completionLanguage(for: editor.text, completions: completions)
            guard editor.isFirstResponder, let match = completionMatch(resolvedLanguage: language), !match.items.isEmpty else {
                closeCompletions(); return
            }
            completionValues.removeAll()
            let labels = match.items.map { item in
                let label = completions.presentation(for: item, text: editor.text, resolvedLanguage: language)
                completionValues[label] = item
                return label
            }
            completionMatchRange = match.range
            editor.showCompletions(labels, at: NSMaxRange(match.range))
        }

        private func closeCompletions() {
            completionMatchRange = nil
            editor?.completionList.dismiss()
        }

        private func insertCompletion(_ label: String) {
            guard let editor, let match = completionMatch() else { closeCompletions(); return }
            let value = completionValues[label] ?? label
            closeCompletions()
            replace(match.range, with: value)
            let caret = NSRange(location: match.range.location + (value as NSString).length, length: 0)
            editor.selectedRange = caret
            editor.scrollRangeToVisible(caret)
        }
    }
}

@MainActor
final class BatchIOSTextView: UITextView {
    var style = InkuEditorStyle.batch { didSet { if oldValue != style { refreshGutter() } } }
    var lineHeight: CGFloat = 0
    var onCompositionEnded: (() -> Void)?
    var onFocusChanged: (() -> Void)?
    /// Set once the author focuses the editor; until then a chosen word goes at the end.
    private(set) var used = false
    let completionList = IOSCompletionList()
    private let gutter = BatchIOSGutter()
    fileprivate var lineIndex = BatchEditorLineIndex("")
    fileprivate var numberFont = CTFontCreateWithName("Menlo" as CFString, 14, nil)
    private var keyboardFrame: CGRect?
    private var completionCaret: Int?

    override init(frame: CGRect, textContainer: NSTextContainer?) {
        super.init(frame: frame, textContainer: textContainer)
        gutter.editor = self
        gutter.isUserInteractionEnabled = false
        gutter.isAccessibilityElement = false
        addSubview(gutter)
        completionList.isHidden = true
        addSubview(completionList)
        NotificationCenter.default.addObserver(self, selector: #selector(keyboardChanged(_:)),
                                               name: UIResponder.keyboardWillChangeFrameNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(keyboardHidden(_:)),
                                               name: UIResponder.keyboardWillHideNotification, object: nil)
        refreshGutter()
    }
    required init?(coder: NSCoder) { return nil }

    override func unmarkText() {
        super.unmarkText()
        onCompositionEnded?()
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

    override func layoutSubviews() {
        super.layoutSubviews()
        gutter.isHidden = !style.lineNumbers
        if style.lineNumbers {
            gutter.frame = CGRect(x: contentOffset.x, y: contentOffset.y, width: textContainerInset.left - style.inset.width, height: bounds.height)
            gutter.setNeedsDisplay()
        }
        positionCompletions()
        bringSubviewToFront(completionList)
    }

    /// The Mac ruler's width (at least 34, the widest number plus 18) left of the style's inset; no gutter without
    /// line numbers, so the placeholder sits at the inset as on the Mac.
    func refreshGutter() {
        lineIndex = BatchEditorLineIndex(text ?? "", reusing: lineIndex)
        if let font { numberFont = CTFontCreateWithName(font.fontName as CFString, font.pointSize, nil) }
        var left = style.inset.width
        if style.lineNumbers {
            let number = batchNumberLine(max(1, max(lineIndex.count, text?.isEmpty == true ? style.emptyLineCount : 1)),
                                         font: numberFont, color: UIColor.secondaryLabel.cgColor)
            left += max(34, ceil(CGFloat(CTLineGetTypographicBounds(number, nil, nil, nil)) + 18))
        }
        let inset = UIEdgeInsets(top: style.inset.height, left: left, bottom: style.inset.height, right: style.inset.width)
        if textContainerInset != inset { textContainerInset = inset }
        setNeedsLayout()
        gutter.setNeedsDisplay()
    }

    // MARK: Completion list

    func showCompletions(_ labels: [String], at caret: Int) {
        completionCaret = caret
        completionList.show(labels)
        setNeedsLayout()
        layoutIfNeeded()
    }

    /// Under the caret, or above it when the keyboard or the editor's bottom edge would cover the list.
    private func positionCompletions() {
        guard !completionList.isHidden, let caret = completionCaret,
              let position = self.position(from: beginningOfDocument, offset: caret) else { return }
        let caretRect = self.caretRect(for: position)
        let size = completionList.preferredSize(maxWidth: max(160, bounds.width - 16))
        let visible = CGRect(origin: contentOffset, size: bounds.size)
        var bottomLimit = visible.maxY
        if let keyboardFrame, let window {
            let keyboard = convert(window.convert(keyboardFrame, from: window.screen.coordinateSpace), from: window)
            if keyboard.minY < bottomLimit { bottomLimit = keyboard.minY }
        }
        var y = caretRect.maxY + 4
        if y + size.height > bottomLimit { y = max(visible.minY, caretRect.minY - 4 - size.height) }
        let x = min(max(visible.minX + 8, caretRect.minX), visible.maxX - size.width - 8)
        completionList.frame = CGRect(x: x, y: y, width: size.width, height: size.height)
    }

    @objc private func keyboardChanged(_ note: Notification) {
        keyboardFrame = note.userInfo?[UIResponder.keyboardFrameEndUserInfoKey] as? CGRect
        setNeedsLayout()
    }
    @objc private func keyboardHidden(_ note: Notification) {
        keyboardFrame = nil
        setNeedsLayout()
    }

    // Hardware keyboard: up and down move in the list, Return or Tab take the chosen item, Escape closes it.
    override var keyCommands: [UIKeyCommand]? {
        guard !completionList.isHidden else { return super.keyCommands }
        var commands = [UIKeyCommand(input: UIKeyCommand.inputUpArrow, modifierFlags: [], action: #selector(completionUp)),
                        UIKeyCommand(input: UIKeyCommand.inputDownArrow, modifierFlags: [], action: #selector(completionDown)),
                        UIKeyCommand(input: UIKeyCommand.inputEscape, modifierFlags: [], action: #selector(completionClose))]
        if completionList.selectedIndex != nil {
            commands += [UIKeyCommand(input: "\r", modifierFlags: [], action: #selector(completionTake)),
                         UIKeyCommand(input: "\t", modifierFlags: [], action: #selector(completionTake))]
        }
        commands.forEach { $0.wantsPriorityOverSystemBehavior = true }
        return (super.keyCommands ?? []) + commands
    }
    @objc private func completionUp() { completionList.move(by: -1) }
    @objc private func completionDown() { completionList.move(by: 1) }
    @objc private func completionClose() { completionList.dismiss() }
    @objc private func completionTake() { completionList.pickSelected() }
}

/// The completion list at the caret: no item is chosen until the author taps one or moves with the arrow keys.
/// Plain rows in a scroll view with its insets fixed at zero: a `UITableView` inside the text view added its own
/// content inset and pushed the only row out of the 30-point frame (step 4 screen check 2, an empty frame).
@MainActor
final class IOSCompletionList: UIView {
    var onPick: ((String) -> Void)?
    private(set) var selectedIndex: Int?
    private var labels: [String] = []
    private var rows: [UILabel] = []
    private let scroll = UIScrollView()
    private let rowHeight: CGFloat = 30
    private let font = UIFont.systemFont(ofSize: 14)

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .secondarySystemBackground
        layer.cornerRadius = 6
        layer.borderWidth = 1
        layer.borderColor = UIColor.separator.cgColor
        layer.shadowColor = UIColor.black.cgColor
        layer.shadowOpacity = 0.18
        layer.shadowRadius = 8
        layer.shadowOffset = CGSize(width: 0, height: 3)
        scroll.contentInsetAdjustmentBehavior = .never
        scroll.contentInset = .zero
        scroll.layer.cornerRadius = 6
        scroll.clipsToBounds = true
        scroll.showsHorizontalScrollIndicator = false
        addSubview(scroll)
        scroll.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(tapped(_:))))
    }
    required init?(coder: NSCoder) { return nil }

    override func layoutSubviews() {
        super.layoutSubviews()
        scroll.frame = bounds
        for (index, row) in rows.enumerated() {
            row.frame = CGRect(x: 0, y: CGFloat(index) * rowHeight, width: bounds.width, height: rowHeight)
        }
        scroll.contentSize = CGSize(width: bounds.width, height: CGFloat(rows.count) * rowHeight)
    }

    func show(_ labels: [String]) {
        if labels != self.labels {
            selectedIndex = nil
            self.labels = labels
            rows.forEach { $0.removeFromSuperview() }
            rows = labels.map { text in
                let row = UILabel()
                row.text = "  " + text
                row.font = font
                row.textColor = .label
                row.lineBreakMode = .byTruncatingTail
                scroll.addSubview(row)
                return row
            }
            scroll.contentOffset = .zero
        }
        paintSelection()
        isHidden = false
        setNeedsLayout()
    }

    func dismiss() {
        guard !isHidden else { return }
        isHidden = true
        selectedIndex = nil
        labels = []
        rows.forEach { $0.removeFromSuperview() }
        rows = []
    }

    /// Up to eight rows, as wide as the widest label up to `maxWidth`.
    func preferredSize(maxWidth: CGFloat) -> CGSize {
        let widest = labels.prefix(50).map { ("  " + $0 as NSString).size(withAttributes: [.font: font]).width }.max() ?? 0
        return CGSize(width: min(maxWidth, max(160, ceil(widest) + 24)), height: CGFloat(min(8, labels.count)) * rowHeight)
    }

    func move(by delta: Int) {
        guard !labels.isEmpty else { return }
        let next = selectedIndex.map { min(labels.count - 1, max(0, $0 + delta)) } ?? (delta > 0 ? 0 : labels.count - 1)
        selectedIndex = next
        paintSelection()
        scroll.scrollRectToVisible(CGRect(x: 0, y: CGFloat(next) * rowHeight, width: 1, height: rowHeight), animated: false)
    }

    func pickSelected() {
        guard let selectedIndex, labels.indices.contains(selectedIndex) else { return }
        onPick?(labels[selectedIndex])
    }

    private func paintSelection() {
        for (index, row) in rows.enumerated() {
            row.backgroundColor = index == selectedIndex ? UIColor.tintColor.withAlphaComponent(0.22) : .clear
        }
    }

    @objc private func tapped(_ gesture: UITapGestureRecognizer) {
        let index = Int(gesture.location(in: scroll).y / rowHeight)
        guard labels.indices.contains(index) else { return }
        onPick?(labels[index])
    }
}

@MainActor
private final class BatchIOSGutter: UIView {
    weak var editor: BatchIOSTextView?
    override func draw(_ rect: CGRect) {
        UIColor.tertiarySystemBackground.setFill()
        UIRectFill(rect)
        guard let editor, let context = UIGraphicsGetCurrentContext() else { return }
        UIColor.separator.setFill()
        UIRectFill(CGRect(x: bounds.maxX - 1, y: rect.minY, width: 1, height: rect.height))
        let layout = editor.layoutManager
        let container = editor.textContainer
        layout.ensureLayout(for: container)
        let length = (editor.text ?? "").utf16.count
        // The batch box numbers its first rows while empty (the Mac ruler's `emptyLineCount`).
        if length == 0, editor.style.emptyLineCount > 1, let font = editor.font {
            // A fixed line of `lineHeight` puts the baseline above the descender, raised by the centring offset.
            let lineHeight = editor.lineHeight > 0 ? editor.lineHeight : font.lineHeight
            let natural = ceil(font.ascender - font.descender + font.leading)
            let baseline = lineHeight + font.descender - max(0, (lineHeight - natural) / 2)
            for index in 0..<editor.style.emptyLineCount {
                let y = editor.textContainerInset.top + baseline + CGFloat(index) * lineHeight - editor.contentOffset.y
                let number = batchNumberLine(index + 1, font: editor.numberFont, color: UIColor.secondaryLabel.cgColor)
                let width = CGFloat(CTLineGetTypographicBounds(number, nil, nil, nil))
                batchDrawNumber(number, baseline: CGPoint(x: bounds.maxX - width - 8, y: y), context: context)
            }
            return
        }
        let visible = CGRect(x: 0, y: editor.contentOffset.y - editor.textContainerInset.top,
                             width: max(1, container.size.width), height: bounds.height)
        let glyphs = layout.glyphRange(forBoundingRect: visible, in: container)
        let first = glyphs.length > 0
            ? editor.lineIndex.line(containing: layout.characterIndexForGlyph(at: glyphs.location))
            : max(0, editor.lineIndex.starts.count - 1)
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
                    : (editor.font?.ascender ?? CTFontGetAscent(editor.numberFont))
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

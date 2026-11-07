import CoreText
import InkuHost
import SwiftUI

/// Folded UTF-16 character ranges, merged so glyph lookups can use binary search.
struct InkuHiddenRangeIndex {
    private let ranges: [NSRange]
    init(_ hidden: [NSRange]) {
        var merged: [NSRange] = []
        for range in hidden.filter({ $0.length > 0 }).sorted(by: { $0.location < $1.location }) {
            if let last = merged.last, range.location <= NSMaxRange(last) {
                merged[merged.count - 1].length = max(NSMaxRange(last), NSMaxRange(range)) - last.location
            } else { merged.append(range) }
        }
        ranges = merged
    }
    func contains(_ character: Int) -> Bool {
        var low = 0, high = ranges.count
        while low < high {
            let middle = low + (high - low) / 2
            if ranges[middle].location <= character { low = middle + 1 } else { high = middle }
        }
        return low > 0 && NSLocationInRange(character, ranges[low - 1])
    }
}

/// How a native editor lays out its text. The batch box follows Web's 14px/1.65 text without wrapping and numbers its lines;
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
    var focusOnAttach = false
    var emptyLineCount = 1

    static let batch = InkuEditorStyle(fontSize: 14, monospaced: false, lineHeightMultiple: 1.65,
                                      inset: CGSize(width: 10, height: 9))
    static let description = InkuEditorStyle(fontSize: 14, monospaced: false, lineHeightMultiple: 1.65, wraps: true,
                                             lineNumbers: false, inset: CGSize(width: 10, height: 9), drawsBackground: false)
    static let ddl = InkuEditorStyle(fontSize: 14, monospaced: false, lineHeightMultiple: 1.7, wraps: true,
                                     lineNumbers: true, inset: CGSize(width: 11, height: 10), drawsBackground: false, focusOnAttach: true)
    /// Web DdlViewer's `compact` editor: the same DDL editing without line numbers.
    static let ddlCompact = InkuEditorStyle(fontSize: 14, monospaced: false, lineHeightMultiple: 1.78, wraps: true,
                                            lineNumbers: false, inset: CGSize(width: 4, height: 4), drawsBackground: false)
}

/// A range an editor paints without changing its text: the grey band of a number or comment (Web LabelHighlight),
/// or a DDL token colour (Web `highlight.ts`). Painted as layout-manager temporary attributes, never while the IME composes.
struct InkuEditorMark: Equatable {
    enum Style: Equatable { case muted, token(DdlTokenClass), unknownName, completion(CompletionRangeState.State), title }
    let range: NSRange
    let style: Style

    static func descriptionLabels(_ text: String) -> [InkuEditorMark] {
        DescriptionLabels.excludedSpans(text).map { InkuEditorMark(range: $0.range, style: .muted) }
    }
}

enum InkuEditorMarksKey: Equatable {
    case description, none
    case ddl(DdlHighlighter, [CompletionRangeState], String)
    case ddlRevision(Int, Int, Bool, [CompletionRangeState], String)
}

struct InkuEditorMarksCache {
    private var source: Data?
    private var key: InkuEditorMarksKey?
    private(set) var marks: [InkuEditorMark] = []

    mutating func update(source: String, key: InkuEditorMarksKey, make: (String) -> [InkuEditorMark]) -> Bool {
        let bytes = Data(source.utf8)
        guard self.source != bytes || self.key != key else { return false }
        self.source = bytes; self.key = key; marks = make(source)
        return true
    }
}

/// Web `RangeEditorStatus`: the frame to show, whether a range is invalid, and whether the IME is composing.
struct RangeEditorStatus: Equatable {
    var preview: CompositionRanges.Preview?
    var invalid = false
    var composing = false
}

/// A word to put at the caret (Web DdlEditor `insertWord`), replacing the selection.
struct InkuEditorInsertion: Equatable {
    let id = UUID()
    let text: String
    /// Web DdlViewer `insertWord`: an editor the author has not used yet takes the word at its end.
    var atEndUnlessUsed = false
    /// Web `replaceValueWithHistory`: the whole text is replaced as one undoable step.
    var replacesAll = false
}

@MainActor
struct BatchInputEditor: View {
    @Binding var text: String
    var isEditable = true
    var accessibilityLabel: String

    var body: some View {
        var style = InkuEditorStyle.batch
        style.emptyLineCount = 3
        return InkuTextEditor(text: $text, isEditable: isEditable, accessibilityLabel: accessibilityLabel, style: style)
    }
}

@MainActor
struct InkuTextEditor: View {
    @Binding var text: String
    var isEditable = true
    var accessibilityLabel: String
    var style = InkuEditorStyle.batch
    var marks: (String) -> [InkuEditorMark] = InkuEditorMark.descriptionLabels
    var marksKey: InkuEditorMarksKey = .description
    var insertion: Binding<InkuEditorInsertion?>? = nil
    /// Web `numericRangeEditing`: the core's range table folds matching numeric places; nil leaves the text open.
    var rangeTable: [CompositionRanges.Entry]? = nil
    var onRangeStatus: ((RangeEditorStatus) -> Void)? = nil
    /// Web `ddlCompletions`: saijiki words and macro names offered while typing; nil offers nothing.
    var completions: DdlCompletions? = nil
    var onCharacterHover: ((Int?) -> Void)? = nil
    @Environment(DisplaySettings.self) private var display
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.inkuTooltipsCovered) private var covered
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        BatchNativeInputEditor(text: $text, isEditable: isEditable && isEnabled && !covered,
                               accessibilityLabel: accessibilityLabel,
                               textScale: display.preferences.textScale, colorScheme: colorScheme,
                               style: style, marks: marks, marksKey: marksKey, covered: covered, insertion: insertion,
                               rangeTable: rangeTable, onRangeStatus: onRangeStatus, completions: completions, onCharacterHover: onCharacterHover)
            .clipped()
    }
}

/// Offsets address the original UTF-16 storage; the batch parser owns the line count.
struct BatchEditorLineIndex {
    let source: String
    let starts: [Int]
    let count: Int

    init(_ text: String, reusing previous: BatchEditorLineIndex? = nil) {
        if let previous, previous.source.utf8.elementsEqual(text.utf8) { self = previous; return }
        source = text
        let old = previous.map { Array($0.source.utf16) } ?? []
        let new = Array(text.utf16)
        var common = 0
        while common < min(old.count, new.count), old[common] == new[common] { common += 1 }
        let firstChangedLine = previous.map { max(0, $0.line(containing: common) - 1) } ?? 0
        let start = previous?.starts[firstChangedLine] ?? 0
        var offsets = previous.map { Array($0.starts.prefix(firstChangedLine)) } ?? []
        offsets.append(start)
        var offset = start
        var previousWasCR = false
        let startIndex = String.Index(utf16Offset: start, in: text)
        for scalar in text[startIndex...].unicodeScalars {
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
        count = offsets.count
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

func batchNumberLine(_ number: Int, font: CTFont, color: CGColor) -> CTLine {
    let attributes: [NSAttributedString.Key: Any] = [
        NSAttributedString.Key(kCTFontAttributeName as String): font,
        NSAttributedString.Key(kCTForegroundColorAttributeName as String): color,
    ]
    return CTLineCreateWithAttributedString(NSAttributedString(string: String(number), attributes: attributes))
}

func batchDrawNumber(_ line: CTLine, baseline: CGPoint, context: CGContext) {
    context.saveGState()
    context.translateBy(x: baseline.x, y: baseline.y)
    context.scaleBy(x: 1, y: -1)
    context.textMatrix = .identity
    context.textPosition = .zero
    CTLineDraw(line, context)
    context.restoreGState()
}

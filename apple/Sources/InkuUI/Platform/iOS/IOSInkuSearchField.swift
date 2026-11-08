#if os(iOS)
import SwiftUI
import UIKit

/// The search field of both history searches, as the Mac's `NSSearchField` (MacInkuSearchField.swift): a search is
/// not applied while the input method still owns marked text, the strip's search waits `delay` after typing, the clear
/// button empties it, and Escape on a hardware keyboard calls `onCancel` (the library closes) or clears the field.
@MainActor
struct InkuSearchField: UIViewRepresentable {
    @Binding var value: String
    let placeholder: String
    let label: String
    var maxLength: Int? = nil
    var delay: Duration? = nil
    var borderless: Bool = false
    var onCancel: (() -> Void)? = nil
    let onSearch: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> EscapeSearchTextField {
        let field = EscapeSearchTextField()
        field.delegate = context.coordinator
        field.returnKeyType = .search
        field.autocorrectionType = .no
        field.autocapitalizationType = .none
        field.clearButtonMode = .whileEditing
        field.setContentHuggingPriority(.defaultLow, for: .horizontal)
        field.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        field.addTarget(context.coordinator, action: #selector(Coordinator.changed(_:)), for: .editingChanged)
        field.onEscape = { [weak coordinator = context.coordinator] in coordinator?.escape() }
        context.coordinator.field = field
        return field
    }
    func updateUIView(_ field: EscapeSearchTextField, context: Context) {
        context.coordinator.parent = self
        let size = CGFloat(12 * context.environment.inkuTextScale)
        if field.font?.pointSize != size { field.font = .systemFont(ofSize: size) }
        field.placeholder = placeholder
        field.accessibilityLabel = label
        field.isEnabled = context.environment.isEnabled
        field.borderStyle = borderless ? .none : .roundedRect
        field.backgroundColor = borderless ? .clear : nil
        if !field.isFirstResponder, field.text != value { field.text = value }
    }
    static func dismantleUIView(_ field: EscapeSearchTextField, coordinator: Coordinator) { coordinator.pending?.cancel() }

    @MainActor final class Coordinator: NSObject, UITextFieldDelegate {
        var parent: InkuSearchField
        var pending: Task<Void, Never>?
        weak var field: UITextField?
        init(_ parent: InkuSearchField) { self.parent = parent }

        private func limitedText(of field: UITextField) -> String {
            let text = field.text ?? ""
            guard let maxLength = parent.maxLength else { return text }
            let limited = String(text.prefix(maxLength))
            if text != limited { field.text = limited }
            return limited
        }
        @objc func changed(_ field: UITextField) {
            self.field = field
            pending?.cancel()
            guard field.markedTextRange == nil else { return }
            let text = limitedText(of: field)
            parent.value = text
            guard let delay = parent.delay, !text.isEmpty else { parent.onSearch(text); return }
            pending = Task { @MainActor [weak self] in
                try? await Task.sleep(for: delay)
                guard !Task.isCancelled else { return }
                self?.parent.onSearch(text)
            }
        }
        func textFieldShouldReturn(_ field: UITextField) -> Bool {
            pending?.cancel()
            guard field.markedTextRange == nil else { return true }
            let text = limitedText(of: field)
            parent.value = text
            parent.onSearch(text)
            return true
        }
        func escape() {
            if let onCancel = parent.onCancel { onCancel(); return }
            pending?.cancel()
            field?.text = ""
            parent.value = ""
            parent.onSearch("")
        }
    }
}

/// Escape on a hardware keyboard, which a text field otherwise ignores.
final class EscapeSearchTextField: UISearchTextField {
    var onEscape: (() -> Void)?
    override var keyCommands: [UIKeyCommand]? {
        let escape = UIKeyCommand(input: UIKeyCommand.inputEscape, modifierFlags: [], action: #selector(escapePressed))
        escape.wantsPriorityOverSystemBehavior = true
        return (super.keyCommands ?? []) + [escape]
    }
    @objc private func escapePressed() {
        guard markedTextRange == nil else { return }
        onEscape?()
    }
}
#endif

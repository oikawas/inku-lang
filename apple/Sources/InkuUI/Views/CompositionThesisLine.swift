import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
struct CompositionThesisLine: View {
    @Bindable var model: AppModel
    let work: SavedWork
    @State private var snapshot: CompositionRecordSnapshot?

    var body: some View {
        let record = snapshot?.own ?? snapshot?.inherited
        let answer = record?["answer"]
        if let thesis = answer?["thesis"].string, !thesis.isEmpty {
            HStack(spacing: 8) {
                if snapshot?.own == nil && snapshot?.inherited != nil {
                    Text(model.display.webCopy("compositionInheritedMark", "親の構図")).inkuFont(10).foregroundStyle(.secondary)
                }
                Text(thesis).inkuFont(12).lineLimit(1)
                Spacer(minLength: 4)
                if let form = answer?["form"].string { Text(CompositionNames.formName(form, language: model.display.preferences.language)).inkuFont(11) }
                if let law = answer?["main_law"].string { Text(CompositionNames.lawName(law, language: model.display.preferences.language)).inkuFont(11) }
            }.foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
        }
        Color.clear.frame(height: 0).task(id: work.id) {
            snapshot = nil
            let current = try? await model.compositionRecord(work: work)
            guard !Task.isCancelled else { return }
            snapshot = current
        }
    }
}

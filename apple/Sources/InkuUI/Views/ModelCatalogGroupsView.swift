import InkuHost
import SwiftUI

/// Every model screen uses the catalog's label order, titles and fold rule.
@MainActor
struct ModelCatalogGroupsView<Row: View>: View {
    let models: [ProviderModelSettings]
    @Bindable var display: DisplaySettings
    var columns: [GridItem]? = nil
    @ViewBuilder var row: (ProviderModelSettings) -> Row
    @State private var expanded: Set<String> = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            rows(models.filter { $0.modelFold == nil })
            ForEach(ModelCatalogLabels.definitions) { definition in
                let folded = models.filter { $0.modelFold == definition.id }
                if !folded.isEmpty {
                    DisclosureGroup(isExpanded: Binding(
                        get: { expanded.contains(definition.id) },
                        set: { if $0 { expanded.insert(definition.id) } else { expanded.remove(definition.id) } })) {
                        rows(folded).padding(.top, 8)
                    } label: {
                        Text("\(definition.name(language: display.preferences.language)) (\(folded.count))")
                            .inkuFont(13, weight: .medium)
                            .foregroundStyle(definition.publishable ? Color.secondary : Color.orange)
                    }
                    .accessibilityIdentifier("model-fold-" + definition.id)
                }
            }
        }
    }

    @ViewBuilder private func rows(_ entries: [ProviderModelSettings]) -> some View {
        if let columns {
            LazyVGrid(columns: columns, alignment: .leading, spacing: 7) {
                ForEach(entries) { row($0) }
            }
        } else {
            LazyVStack(alignment: .leading, spacing: 10) {
                ForEach(entries) { row($0) }
            }
        }
    }
}

@MainActor
struct ModelLabelsView: View {
    let labels: [ModelCatalogLabelDefinition]
    @Bindable var display: DisplaySettings
    var endOfLifeDate: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(labels) { label in
                Text(label.name(language: display.preferences.language) + (label.id == "eol" ? endOfLifeDate.map { " (\($0))" } ?? "" : ""))
                    .inkuFont(12)
                    // No response when measured is publishable since 2026-10-26, as not recommended, and keeps the warning colour.
                    .foregroundStyle(label.publishable && label.id != "no_response" ? Color.secondary : Color.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

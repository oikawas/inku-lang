import SwiftUI

@MainActor struct OperationalLimitsView: View {
    @Bindable var model: AppModel
    @State private var draft: [String: String] = [:]
    @State private var saved: [String: UInt32] = [:]
    @State private var saving = false
    @State private var message = ""
    @State private var helpGroup: String?

    private var changed: Bool { draft != saved.mapValues(String.init) }

    var body: some View {
        Group {
            if let definition = model.drawingLimitDefinition,
               let copy = model.productReference?.localized(language: model.display.preferences.language) {
                Section(copy.text("settingsRenderLimitsTitle")) {
                    Text(copy.text("settingsRenderLimitsIntro")).font(.callout).foregroundStyle(.secondary)
                }
                ForEach(definition.groups, id: \.id) { group in
                    Section {
                        if let summary = copy.limitGroupSummaries[group.id], !summary.isEmpty {
                            Text(summary).font(.callout).foregroundStyle(.secondary)
                        }
                        ForEach(group.fields, id: \.self) { key in
                            limitRow(key, definition: definition, copy: copy)
                        }
                    } header: {
                        HStack(spacing: 6) {
                            Text(copy.limitGroups[group.id] ?? group.id)
                            if let tip = copy.limitGroupTooltips[group.id], !tip.isEmpty {
                                Button { helpGroup = group.id } label: { Image(systemName: "info.circle") }
                                    .buttonStyle(.plain)
                                    .accessibilityLabel(model.display.localizedFormat("%@の説明", copy.limitGroups[group.id] ?? group.id))
                                    .help(model.display.preferences.showTooltips ? tip : "")
                                    .popover(isPresented: Binding(get: { helpGroup == group.id }, set: { if !$0 { helpGroup = nil } })) {
                                        Text(tip).font(.callout).textSelection(.enabled).padding(16).frame(width: 380)
                                    }
                            }
                        }
                    }
                }
                Section {
                    Text(copy.text("settingsRenderLimitsRounding")).font(.callout).foregroundStyle(.secondary)
                    HStack {
                        Button(model.display.localized("再読込")) { load() }.disabled(changed)
                        Button(copy.text("settingsRenderLimitsReset")) { draft = definition.defaults.mapValues(String.init); message = "" }
                            .help(model.display.preferences.showTooltips ? model.display.localized("既定値を入力欄に戻します。変更を保存するまで適用しません。") : "")
                        Spacer()
                        if changed {
                            Button(model.display.localized("取消")) { draft = saved.mapValues(String.init); message = "" }
                            Button(model.display.localized("変更を保存")) { Task { await save(definition: definition) } }
                                .buttonStyle(.borderedProminent)
                                .disabled((try? definition.parsedDraft(draft)) == nil)
                        }
                    }.disabled(saving || model.isBusy)
                    if changed, (try? definition.parsedDraft(draft)) == nil {
                        Text(model.display.localized("制限値には整数を入力してください。"))
                            .font(.caption).foregroundStyle(.red)
                    }
                    if !message.isEmpty { Text(model.display.message(message)).font(.caption).textSelection(.enabled) }
                }
            } else {
                Section { ProgressView(model.display.localized("準備中")) }
            }
        }.task { load() }
    }

    private func limitRow(_ key: String, definition: DrawingLimitDefinition, copy: ProductReferenceCopy) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .top, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(copy.limitLabels[key] ?? key)
                    Text(copy.limitHints[key] ?? "").font(.caption).foregroundStyle(.secondary)
                    if ["max_expanded_primitives", "max_expanded_per_instruction"].contains(key),
                       let value = Int(draft[key] ?? ""), let low = definition.bytesPerMark["pen"],
                       let high = definition.bytesPerMark["brush_thick"] {
                        Text(String(format: copy.text("limitWeightFormat"),
                                    String(format: "%.1f", Double(max(1, value)) * Double(low) / 1_000_000),
                                    String(format: "%.1f", Double(max(1, value)) * Double(high) / 1_000_000)))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 5) {
                    Button { step(key, by: -1, definition: definition) } label: { Image(systemName: "minus") }
                    TextField(copy.limitLabels[key] ?? key, text: Binding(get: { draft[key] ?? "" }, set: { draft[key] = $0; message = "" }))
                        .textFieldStyle(.roundedBorder).multilineTextAlignment(.trailing).frame(width: 100)
                        .accessibilityLabel(copy.limitLabels[key] ?? key)
                        .help(model.display.preferences.showTooltips ? copy.limitHints[key] ?? "" : "")
                    Button { step(key, by: 1, definition: definition) } label: { Image(systemName: "plus") }
                }.buttonStyle(.borderless).disabled(saving || model.isBusy)
            }
            HStack(spacing: 16) {
                Text(model.display.localizedFormat("現在: %ld", Int(saved[key] ?? 0)))
                Text(model.display.localizedFormat("既定: %ld", Int(definition.defaults[key] ?? 0)))
                if let unit = copy.limitUnits[key] { Text(unit) }
            }.font(.caption.monospacedDigit()).foregroundStyle(.secondary)
        }.padding(.vertical, 4)
    }

    private func load() {
        do { saved = try model.drawingLimits(); draft = saved.mapValues(String.init); message = "" }
        catch { message = error.localizedDescription }
    }

    private func step(_ key: String, by amount: Int64, definition: DrawingLimitDefinition) {
        let value = Int64((draft[key] ?? "").replacingOccurrences(of: ",", with: "")) ?? Int64(saved[key] ?? 1)
        let bounded = min(Int64(definition.absoluteMaximum), max(1, value))
        draft[key] = String(min(Int64(definition.absoluteMaximum), max(1, bounded + amount)))
        message = ""
    }

    private func save(definition: DrawingLimitDefinition) async {
        saving = true
        defer { saving = false }
        do {
            try await model.updateDrawingLimits(definition.parsedDraft(draft))
            saved = try model.drawingLimits(); draft = saved.mapValues(String.init)
            message = model.productReference?.localized(language: model.display.preferences.language)?.text("settingsRenderLimitsSaved") ?? "制限値を保存しました"
        } catch { message = (try? definition.parsedDraft(draft)) == nil ? "制限値には整数を入力してください。" : error.localizedDescription }
    }
}

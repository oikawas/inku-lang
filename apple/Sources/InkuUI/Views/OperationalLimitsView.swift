import SwiftUI

@MainActor struct OperationalLimitsView: View {
    @Bindable var model: AppModel
    @State private var maximum: [String: UInt32] = [:]
    @State private var values: [String: UInt32] = [:]
    @State private var message = ""

    var body: some View {
        Section(model.display.localized("描画の運用上限")) {
            Text(model.display.localized("新しい作品の処理量を調整します。保存作品は保存時の条件で再演奏します。"))
                .font(.callout).foregroundStyle(.secondary)
            ForEach(maximum.keys.sorted(), id: \.self) { key in
                HStack {
                    Text(model.display.localized(title(key)))
                    Spacer()
                    TextField(model.display.localized("上限"), value: Binding(get: { values[key] ?? maximum[key] ?? 0 }, set: { values[key] = min($0, maximum[key] ?? 0) }), format: .number)
                        .multilineTextAlignment(.trailing).frame(width: 110)
                    Text("/ \(maximum[key] ?? 0)").foregroundStyle(.secondary).frame(width: 90, alignment: .trailing)
                }
            }
            HStack {
                Button(model.display.localized("上限を保存")) { Task { await save(defaults: false) } }
                Button(model.display.localized("標準値に戻す")) { Task { await save(defaults: true) } }
            }.disabled(model.isBusy || maximum.isEmpty)
            if !message.isEmpty { Text(model.display.message(message)).font(.caption).textSelection(.enabled) }
        }
        .task {
            do { maximum = try model.operationalLimitDefaults(); values = try model.operationalLimits() }
            catch { message = error.localizedDescription }
        }
    }

    private func save(defaults: Bool) async {
        do {
            try await model.updateOperationalLimits(defaults ? nil : values)
            values = try model.operationalLimits()
            message = "描画の上限を保存しました。"
        } catch { message = error.localizedDescription }
    }
    private func title(_ key: String) -> String {
        switch key {
        case "logical_objects": "図形の数"
        case "anchor_instances": "アンカーの数"
        case "fill_instances": "塗りの数"
        case "stroke_instances": "線の数"
        case "surface_instances": "表面効果の数"
        case "render_nodes": "描画要素の数"
        default: key.replacingOccurrences(of: "_", with: " ")
        }
    }
}

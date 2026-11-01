import SwiftUI

@MainActor struct PipelineDiagnosticsView: View {
    let raw: String
    let display: DisplaySettings
    var pluginWords: [PluginWord] = []
    var body: some View {
        let entries = PipelineDiagnosticText.entries(raw)
        if !entries.isEmpty {
            DisclosureGroup(display.webCopy("pipelineDiagnostics", "診断")) {
                ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                    VStack(alignment: .leading, spacing: 4) {
                        Text("• " + PipelineDiagnosticText.format(entry.value, channel: entry.channel, display: display, pluginWords: pluginWords))
                        DisclosureGroup(display.webCopy("pipelineDiagnosticDetails", "詳細")) {
                            let pretty = (try? JSONSerialization.jsonObject(with: entry.value.data)).flatMap {
                                try? JSONSerialization.data(withJSONObject: $0, options: [.prettyPrinted, .sortedKeys, .fragmentsAllowed])
                            }.flatMap { String(data: $0, encoding: .utf8) } ?? entry.value.text
                            Text(pretty).inkuFont(12, design: .monospaced).textSelection(.enabled)
                        }.padding(.leading, 12)
                    }
                }
            }.padding(12).overlay(RoundedRectangle(cornerRadius: 8).stroke(InkuColor.border))
        }
    }
}

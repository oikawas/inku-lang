import Foundation
import InkuHost

/// Web features/pipeline/diagnostics.ts: a diagnostic's location, reason, and disposition.
@MainActor enum PipelineDiagnosticText {
    private static let indices = [("source_instruction_index", "source_instruction"), ("instruction_index", "instruction"), ("target_instruction_index", "target_instruction"), ("anchor_index", "anchor"), ("target_anchor_index", "target_anchor"), ("placement_group_index", "placement_group"), ("group_index", "group")]
    private static func kind(_ value: ExactJSON) -> String? { value.string ?? value["kind"].string }
    private static func index(_ value: ExactJSON, depth: Int = 0) -> (String, Int)? {
        guard value.object != nil, depth < 30 else { return nil }
        for (field, label) in indices { if let n = value[field].number.flatMap(Int.init) { return (label, n) } }
        for field in ["owner", "value", "unit", "disposition"] { if let found = index(value[field], depth: depth + 1) { return found } }
        return nil
    }
    private static func part(_ value: String, _ display: DisplaySettings) -> String {
        display.webCopy("diagnosticPart." + value, value)
    }
    private static func reason(_ value: ExactJSON) -> String {
        for item in [value["reason"], value["failure"], value["cause"]["reason"], value["cause"]["failure"], value["issue_kind"]] {
            if let name = kind(item) ?? item["type"].string { return name }
        }
        return "diagnostic"
    }
    private static func template(_ key: String, _ fallback: String, _ args: [String], _ display: DisplaySettings) -> String {
        let raw = ServerTips.template(key, language: display.preferences.language, argumentCount: args.count) ?? fallback
        return String(format: raw, arguments: args)
    }
    private static func copiedTemplate(_ key: String, _ fallback: String, _ args: [String], _ display: DisplaySettings) -> String {
        String(format: display.webCopy(key, fallback), arguments: args)
    }
    static func format(_ value: ExactJSON, channel: String, display: DisplaySettings) -> String {
        guard value.object != nil else { return display.webCopy("pipelineDiagnosticUnknown", "詳しい診断情報があります。") }
        if channel == "plugin" {
            let code = value["reason"].string ?? "plugin_not_installed", name = value["name"].string ?? ""
            if code == "plugin_name_mismatch", let suggestion = value["suggestion"].string, !suggestion.isEmpty {
                return copiedTemplate("diagnosticPlugin.suggestion", "%@ %@", [name, suggestion], display)
            }
            return copiedTemplate("diagnosticPlugin." + code, "%@", [name], display)
        }
        if channel == "warning" {
            let code = kind(value) ?? "warning"
            return copiedTemplate(code == "invalid_color" ? "diagnosticWarning.invalid_color" : "diagnosticWarning.other", "%@", [code == "invalid_color" ? (value["name"].string ?? "?") : code], display)
        }
        let name = reason(value)
        let fallback = display.label("理由: \(name)。", "Reason: \(name).")
        let reasonText = display.webCopy("diagnosticReason." + name, fallback)
        if channel == "catalog" { return (value["qualified_name"].string.map { $0 + ": " } ?? "") + reasonText }
        var parts: [String] = []
        let span = value["span"].object != nil ? value["span"] : (value["owner"]["spans"].array?.first ?? .null)
        let owner = index(value["owner"].object != nil ? value["owner"] : value)
        if let start = span["start_byte"].number, let end = span["end_byte"].number {
            parts.append(template("pipelineDiagnosticSourceRange", "原文のバイト位置 %@〜%@。", [start, end], display))
        } else if let owner {
            parts.append(template("pipelineDiagnosticOwner", "%@ %@ の箇所。", [part(owner.0, display), String(owner.1 + 1)], display))
        }
        let cause = value["cause"]["reason"] != .null ? value["cause"]["reason"] : value["reason"] != .null ? value["reason"] : value["failure"]
        let budget = cause["value"]
        if kind(cause) == "budget_exceeded", let dimension = budget["dimension"].string, let required = budget["required"].number, let maximum = budget["maximum"].number {
            parts.append(template("pipelineDiagnosticBudgetExceeded", "%@は %@ 必要でしたが、上限は %@ でした。", [part(dimension, display), required, maximum], display))
        } else { parts.append(reasonText) }
        if let requested = value["partial_execution"]["requested_count"].number, let executed = value["partial_execution"]["executed_count"].number {
            parts.append(template("pipelineDiagnosticPartialExecution", "%@個の要求のうち、実行可能な%@個を描画しました。", [requested, executed], display))
            parts.append(display.webCopy("pipelineDiagnosticContinued", "ほかの部分の描画は続けました。"))
        } else {
            let disposition = value["disposition"], dispositionKind = kind(disposition)
            if channel == "resource" || channel == "relation" || ["omitted", "relation_omitted"].contains(dispositionKind ?? "") {
                let unit = disposition["unit"] != .null ? disposition["unit"] : value["owner"] != .null ? value["owner"] : value
                let i = index(unit), unitKind = kind(unit) ?? i?.0 ?? "part"
                if let i { parts.append(template("pipelineDiagnosticOmitted", "%@ %@ を省略しました。", [part(unitKind, display), String(i.1 + 1)], display)) }
                else { parts.append(copiedTemplate("diagnosticOmitted.noIndex", "%@ を省略しました。", [part(unitKind, display)], display)) }
                parts.append(display.webCopy("pipelineDiagnosticContinued", "ほかの部分の描画は続けました。"))
            }
        }
        return parts.joined(separator: " ")
    }
    static func formatDocument(_ raw: String, display: DisplaySettings) -> String {
        guard let data = raw.data(using: .utf8), let json = try? ExactJSON(data: data) else { return raw }
        let fields = [("plugin_diagnostics", "plugin"), ("upstream_diagnostics", "upstream"), ("downstream_diagnostics", "downstream"), ("resource_omissions", "resource"), ("relation_omissions", "relation"), ("render_warnings", "warning"), ("catalog_diagnostics", "catalog"), ("diagnostics", "upstream")]
        var lines = fields.flatMap { field, channel in (json[field].array ?? []).map { format($0, channel: channel, display: display) } }
        lines += (json["render_diagnostics"]["diagnostics"].array ?? []).map { format($0, channel: "render", display: display) }
        return lines.isEmpty ? display.webCopy("pipelineDiagnosticUnknown", "詳しい診断情報があります。") : lines.joined(separator: "\n")
    }
}

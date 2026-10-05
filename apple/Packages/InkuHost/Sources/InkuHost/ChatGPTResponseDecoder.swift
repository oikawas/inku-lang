import Foundation

/// Bounded SSE bytes become one pipeline object only after matching completed inference and EOF.
public struct ChatGPTResponseDecoder: Sendable {
    public private(set) var terminalResponse: ExactJSON?
    private let argumentLimit: Int
    private let eventLimit: Int
    private let wireLimit: Int
    private var wireSize = 0
    private var buffer: [UInt8] = []
    private var scan = 0
    private var function: ExactJSON?
    private var finalized: ExactJSON?
    private var arguments: Data?
    private var completed: String?
    private var responseID: String?
    private var failure: HostError?

    public init(argumentLimit: Int) {
        self.argumentLimit = argumentLimit
        let eventProduct = argumentLimit.multipliedReportingOverflow(by: 2)
        let wireProduct = argumentLimit.multipliedReportingOverflow(by: 6)
        let event = eventProduct.partialValue.addingReportingOverflow(65_536)
        let wire = wireProduct.partialValue.addingReportingOverflow(524_288)
        let valid = argumentLimit > 0 && !eventProduct.overflow && !wireProduct.overflow && !event.overflow && !wire.overflow
        eventLimit = valid ? max(65_536, event.partialValue) : 0
        wireLimit = valid ? max(1_048_576, wire.partialValue) : 0
        failure = valid ? nil : HostError("chatgpt_response_invalid")
    }

    public mutating func feed(_ data: Data) throws {
        if let failure { throw failure }
        do {
            try Task.checkCancellation()
            guard data.count <= wireLimit - wireSize else { throw HostError("chatgpt_response_too_large") }
            wireSize += data.count; buffer.append(contentsOf: data)
            var consumed = 0
            while scan < buffer.count {
                guard buffer[scan] == 10 else { scan += 1; continue }
                if scan + 1 == buffer.count { break }
                var end: Int?
                if buffer[scan + 1] == 10 { end = scan + 2 }
                else if buffer[scan + 1] == 13 {
                    if scan + 2 == buffer.count { break }
                    if buffer[scan + 2] == 10 { end = scan + 3 }
                }
                guard let end else { scan += 1; continue }
                let start = scan > consumed && buffer[scan - 1] == 13 ? scan - 1 : scan
                guard start - consumed <= eventLimit else { throw HostError("chatgpt_response_too_large") }
                try eventBytes(Array(buffer[consumed..<start]))
                consumed = end; scan = end
            }
            if consumed > 0 { buffer.removeFirst(consumed); scan -= consumed }
            guard buffer.count <= eventLimit else { throw HostError("chatgpt_response_too_large") }
        } catch {
            let reason = error as? HostError ?? HostError(error is CancellationError ? "chatgpt_cancelled" : "chatgpt_response_invalid")
            failure = reason; completed = nil; arguments = nil; function = nil; finalized = nil; buffer.removeAll(); scan = 0
            throw reason
        }
    }

    public func finish() throws -> String {
        if let failure { throw failure }
        try Task.checkCancellation()
        guard buffer.allSatisfy({ [9, 10, 13, 32].contains($0) }), let completed else { throw HostError("chatgpt_response_incomplete") }
        return completed
    }

    private mutating func eventBytes(_ raw: [UInt8]) throws {
        var data: [UInt8] = []
        for var line in raw.split(separator: 10, omittingEmptySubsequences: false) {
            if line.last == 13 { line = line.dropLast() }
            guard line.starts(with: [100, 97, 116, 97, 58]) else { continue }
            line = line.dropFirst(5)
            while line.first == 32 { line = line.dropFirst() }
            if !data.isEmpty { data.append(10) }
            data.append(contentsOf: line)
        }
        guard !data.isEmpty, data != Array("[DONE]".utf8) else { return }
        guard String(bytes: data, encoding: .utf8) != nil else { throw HostError("chatgpt_response_invalid") }
        let event = try ExactJSON(data: Data(data))
        guard event.object != nil, let tag = event["type"].string else { throw HostError("chatgpt_response_invalid") }
        if tag == "error" || tag == "response.failed" {
            terminalResponse = event["response"].object == nil ? nil : event["response"]
            throw HostError(Self.failureCode(event))
        }
        if tag == "response.incomplete" { throw HostError("chatgpt_response_incomplete") }
        if tag.contains("refusal") { throw HostError("chatgpt_refused") }
        guard completed == nil else { throw HostError("chatgpt_response_invalid") }
        switch tag {
        case "response.created", "response.in_progress":
            try matchResponse(event["response"])
        case "response.output_item.added", "response.output_item.done":
            let item = event["item"]
            guard item["type"].string == "function_call" else { try Self.auxiliary(item); return }
            try checkFunction(item)
            if let existing = function { try matchFunction(existing, item) }
            if tag == "response.output_item.done" {
                guard item["status"] == .null || item["status"].string == "completed" else { throw HostError("chatgpt_response_incomplete") }
                guard let text = item["arguments"].string else { throw HostError("chatgpt_response_invalid") }
                try setArguments(text, requireMatch: true)
                finalized = item
            }
            function = item
        case "response.function_call_arguments.delta":
            try matchItem(event)
            guard let delta = event["delta"].string else { throw HostError("chatgpt_response_invalid") }
            let bytes = Data(delta.utf8), count = arguments?.count ?? 0
            guard bytes.count <= argumentLimit - count else { throw HostError("chatgpt_response_too_large") }
            if arguments == nil { arguments = Data() }
            arguments?.append(bytes)
        case "response.function_call_arguments.done":
            try matchItem(event)
            guard let text = event["arguments"].string else { throw HostError("chatgpt_response_invalid") }
            try setArguments(text, requireMatch: true)
        case "response.completed":
            let response = event["response"]
            try matchResponse(response)
            guard response["status"].string == "completed" else { throw HostError("chatgpt_response_incomplete") }
            // Some streams finish with an empty summary; the finalized item event then carries the result.
            var output: [ExactJSON]
            switch response["output"] {
            case .null: output = []
            case .array(let items): output = items
            default: throw HostError("chatgpt_response_invalid")
            }
            if output.isEmpty, let finalized { output = [finalized] }
            var calls: [ExactJSON] = []
            for item in output {
                if item["type"].string == "function_call" { calls.append(item) } else { try Self.auxiliary(item) }
            }
            guard calls.count == 1 else { throw HostError("chatgpt_unexpected_tool") }
            let item = calls[0]
            try checkFunction(item)
            guard let function else { throw HostError("chatgpt_response_invalid") }
            try matchFunction(function, item)
            guard let text = item["arguments"].string else { throw HostError("chatgpt_response_invalid") }
            try setArguments(text, requireMatch: true)
            guard try ExactJSON(data: Data(text.utf8)).object != nil else { throw HostError("chatgpt_response_invalid") }
            completed = text; terminalResponse = response
        default:
            // Reasoning/lifecycle metadata cannot deliver a result; tools are checked at both item and completion boundaries.
            break
        }
    }

    private mutating func matchResponse(_ response: ExactJSON) throws {
        guard response.object != nil else { throw HostError("chatgpt_response_invalid") }
        if let id = response["id"].string {
            guard !id.isEmpty, id.utf8.count <= 160, responseID == nil || responseID == id else { throw HostError("chatgpt_response_invalid") }
            responseID = id
        }
    }
    /// Reasoning and assistant text may accompany the required call but never become the result.
    private static func auxiliary(_ item: ExactJSON) throws {
        if item["type"].string == "reasoning" { return }
        guard item["type"].string == "message", item["role"].string == "assistant" else { throw HostError("chatgpt_unexpected_tool") }
        for part in item["content"].array ?? [] {
            if part["type"].string == "refusal" { throw HostError("chatgpt_refused") }
            guard part["type"].string == "output_text" else { throw HostError("chatgpt_unexpected_tool") }
        }
    }
    private func checkFunction(_ item: ExactJSON) throws {
        guard item["type"].string == "function_call", item["namespace"].string == "inku",
              item["name"].string == "submit_pipeline_response" else { throw HostError("chatgpt_unexpected_tool") }
        guard let id = item["id"].string, !id.isEmpty, id.utf8.count <= 160 else { throw HostError("chatgpt_response_invalid") }
    }
    private func matchFunction(_ first: ExactJSON, _ second: ExactJSON) throws {
        guard first["id"] == second["id"] else { throw HostError("chatgpt_unexpected_tool") }
        if first["call_id"] != .null, second["call_id"] != .null, first["call_id"] != second["call_id"] { throw HostError("chatgpt_response_invalid") }
    }
    private func matchItem(_ event: ExactJSON) throws {
        guard let function, event["item_id"] == function["id"] else { throw HostError("chatgpt_response_invalid") }
        if event["name"] != .null, event["name"].string != "submit_pipeline_response" { throw HostError("chatgpt_unexpected_tool") }
        if event["namespace"] != .null, event["namespace"].string != "inku" { throw HostError("chatgpt_unexpected_tool") }
    }
    private mutating func setArguments(_ text: String, requireMatch: Bool) throws {
        let bytes = Data(text.utf8)
        guard bytes.count <= argumentLimit else { throw HostError("chatgpt_response_too_large") }
        guard !requireMatch || arguments == nil || arguments == bytes else { throw HostError("chatgpt_response_invalid") }
        arguments = bytes
    }
    private static func failureCode(_ event: ExactJSON) -> String {
        let codes: Set<String> = ["subscription_sharing_usage_limit_exceeded", "subscription_sharing_user_not_eligible",
            "subscription_sharing_unsupported_capability", "subscription_sharing_route_not_supported", "subscription_sharing_invalid_user",
            "chatpass_v2_scope_not_authorized", "chatpass_v2_invalid_authorization_context", "subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable"]
        let code = event["error"]["code"].string ?? event["response"]["error"]["code"].string ?? event["code"].string
        return code.flatMap { codes.contains($0) ? $0 : nil } ?? "chatgpt_response_failed"
    }
}

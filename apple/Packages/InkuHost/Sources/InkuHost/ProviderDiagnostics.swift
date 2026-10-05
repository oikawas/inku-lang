import Foundation

public enum ProviderAttemptDiagnosticKind: String, Codable, Sendable, Equatable { case network, http, host, unknown }
public enum ProviderAttemptDiagnosticOperation: String, Codable, Sendable, Equatable {
    case preparation, admission, generation
    case tokenCount = "token_count"
}

/// Safe ordinary failure facts. This value never contains a request URL, headers or response body.
public struct ProviderAttemptDiagnostic: Codable, Sendable, Equatable {
    public let kind: ProviderAttemptDiagnosticKind
    public let reason: String
    public let endpoint: String?
    public let errorDomain: String?
    public let errorCode: Int?
    public let hostCode: String?
    public let httpStatus: Int?
    public let providerCode: String?
    public let providerType: String?
    public let providerParameter: String?
    public let providerStatus: String?
    public let providerMessage: String?
    public let operation: ProviderAttemptDiagnosticOperation?

    public init(kind: ProviderAttemptDiagnosticKind, reason: String, endpoint: String? = nil,
                errorDomain: String? = nil, errorCode: Int? = nil, hostCode: String? = nil,
                httpStatus: Int? = nil, providerCode: String? = nil, providerType: String? = nil,
                providerParameter: String? = nil, providerStatus: String? = nil, providerMessage: String? = nil,
                operation: ProviderAttemptDiagnosticOperation? = nil) {
        self.kind = kind; self.reason = reason; self.endpoint = endpoint
        self.errorDomain = errorDomain; self.errorCode = errorCode; self.hostCode = hostCode
        self.httpStatus = httpStatus; self.providerCode = providerCode; self.providerType = providerType
        self.providerParameter = providerParameter; self.providerStatus = providerStatus; self.providerMessage = providerMessage
        self.operation = operation
    }
}

enum ProviderDiagnosticSanitizer {
    private static let secretLike = try! NSRegularExpression(pattern: "\\b(?:sk|key|AIza)[-_A-Za-z0-9*]{6,}")
    private static let maximumErrorBytes = 65_536
    private static let knownHostCodes: Set<String> = ["provider_selection_required", "credentials_unavailable",
        "provider_base_url_invalid", "invalid_provider_rate_limits", "duplicate_provider_model", "provider_model_settings_invalid",
        "pipeline_schema_violation", "malformed_payload", "provider_response_too_large", "invalid_json", "duplicate_json_key",
        "transport_timeout", "rate_limited", "transport_unavailable", "chatgpt_session_pin_required", "chatgpt_operation_not_supported"]

    static func diagnostic(error: any Error, endpoint: URL?, secrets: [String],
                           httpStatus: Int?, httpBody: Data?,
                           operation: ProviderAttemptDiagnosticOperation? = nil) -> ProviderAttemptDiagnostic {
        let origin = endpoint.flatMap { Self.origin($0, secrets: secrets) }
        if let httpStatus {
            let refusal: ExactJSON?
            if let httpBody, httpBody.count <= maximumErrorBytes,
               let value = try? ExactJSON(data: httpBody), value["error"].object != nil { refusal = value["error"] }
            else { refusal = nil }
            func field(_ name: String) -> String? {
                guard let value = refusal?[name] else { return nil }
                let text = value.string ?? value.number.flatMap(Int64.init).map(String.init)
                return text.flatMap { bounded($0, secrets: secrets) }
            }
            return ProviderAttemptDiagnostic(kind: .http, reason: "The provider returned an HTTP error.", endpoint: origin,
                httpStatus: httpStatus, providerCode: field("code"), providerType: field("type"),
                providerParameter: field("param"), providerStatus: field("status"),
                providerMessage: refusal?["message"].string.flatMap { bounded($0, secrets: secrets) }, operation: operation)
        }
        if let error = error as? URLError {
            return ProviderAttemptDiagnostic(kind: .network, reason: networkReason(error.code), endpoint: origin,
                errorDomain: NSURLErrorDomain, errorCode: error.errorCode, operation: operation)
        }
        if let error = error as? HostError {
            return ProviderAttemptDiagnostic(kind: .host, reason: hostReason(error.code), endpoint: origin,
                errorDomain: "InkuHost", hostCode: knownHostCodes.contains(error.code) ? bounded(error.code, secrets: secrets) : nil,
                operation: operation)
        }
        let system = error as NSError
        return ProviderAttemptDiagnostic(kind: .unknown, reason: "The provider request could not be completed.", endpoint: origin,
            errorDomain: bounded(system.domain, secrets: secrets), errorCode: system.code, operation: operation)
    }

    private static func origin(_ url: URL, secrets: [String]) -> String? {
        guard let source = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let scheme = source.scheme?.lowercased(), ["http", "https"].contains(scheme),
              let host = source.host, !host.isEmpty else { return nil }
        var origin = URLComponents(); origin.scheme = scheme; origin.host = host; origin.port = source.port
        return origin.string.flatMap { bounded($0, secrets: secrets, maximum: 512) }
    }

    private static func bounded(_ text: String, secrets: [String], maximum: Int = 240) -> String? {
        // Mask the entire decoded value before shortening it, including keys echoed across the boundary.
        let masked = ProviderSecretRedactor.redact(text, secrets: secrets)
        let range = NSRange(masked.startIndex..<masked.endIndex, in: masked)
        let safe = secretLike.stringByReplacingMatches(in: masked, range: range, withTemplate: "[redacted]")
        let printable = String(String.UnicodeScalarView(safe.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) }))
        let singleLine = printable.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
        let result = String(singleLine.prefix(maximum))
        return result.isEmpty ? nil : result
    }

    private static func networkReason(_ code: URLError.Code) -> String {
        switch code {
        case .cannotConnectToHost: "Could not connect to the provider host."
        case .cannotFindHost, .dnsLookupFailed: "The provider host could not be found."
        case .timedOut: "The provider request timed out."
        case .notConnectedToInternet: "The network is unavailable."
        case .networkConnectionLost: "The connection to the provider was lost."
        case .secureConnectionFailed, .serverCertificateHasBadDate, .serverCertificateUntrusted,
             .serverCertificateHasUnknownRoot, .serverCertificateNotYetValid: "The secure connection to the provider could not be verified."
        default: "The provider network request failed."
        }
    }

    private static func hostReason(_ code: String) -> String {
        switch code {
        case "provider_selection_required": "Choose a provider and model."
        case "credentials_unavailable": "The provider credential is unavailable."
        case "provider_base_url_invalid": "The provider endpoint is invalid."
        case "transport_timeout": "The provider request timed out."
        case "rate_limited": "The provider request budget is exhausted."
        case "transport_unavailable": "The provider transport is unavailable."
        case "malformed_payload", "invalid_json", "duplicate_json_key": "The provider response could not be read."
        case "provider_response_too_large": "The provider response exceeded the size limit."
        default: "The provider request could not be prepared or completed."
        }
    }
}

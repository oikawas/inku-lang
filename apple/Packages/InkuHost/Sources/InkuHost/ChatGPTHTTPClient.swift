import Foundation

public struct ChatGPTHTTPResponse: Sendable {
    public let status: Int
    public let requestID: String?
    public let data: Data
    public init(status: Int, requestID: String? = nil, data: Data) { self.status = status; self.requestID = requestID; self.data = data }
}

/// Injectable for offline checks. The concrete client accepts only fixed OpenAI hosts and no redirects.
public protocol ChatGPTHTTPClient: Sendable {
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void) async throws -> ChatGPTHTTPResponse
}

/// Additive response observation. Existing authentication clients remain compatible.
protocol ObservedChatGPTHTTPClient: ChatGPTHTTPClient {
    func sendObserved(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
                      onResponse: @escaping ProviderHTTPReadHandler) async throws -> ChatGPTHTTPResponse
}

public final class ChatGPTURLSessionClient: ObservedChatGPTHTTPClient, Sendable {
    public init() {}
    /// Server opens one HTTP client for each token, catalog and response call; no connection outlives its request.
    private static func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = nil; configuration.httpShouldSetCookies = false
        configuration.urlCache = nil; configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: configuration, delegate: ChatGPTRedirectPolicy(), delegateQueue: nil)
    }
    public func send(_ request: URLRequest, maximumBytes: Int,
                     onBytes: @escaping @Sendable (Int) -> Void) async throws -> ChatGPTHTTPResponse {
        try await read(request, maximumBytes: maximumBytes, onBytes: onBytes, observed: false, onResponse: { _ in })
    }
    func sendObserved(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
                      onResponse: @escaping ProviderHTTPReadHandler) async throws -> ChatGPTHTTPResponse {
        try await read(request, maximumBytes: maximumBytes, onBytes: onBytes, observed: true, onResponse: onResponse)
    }
    private func read(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
                      observed: Bool, onResponse: @escaping ProviderHTTPReadHandler) async throws -> ChatGPTHTTPResponse {
        guard let url = request.url, maximumBytes > 0 else { throw HostError("chatgpt_endpoint_invalid") }
        try ChatGPTEndpoints.validate(url)
        var data = Data(), status: Int?, complete = false, truncated = false
        defer { onResponse(ProviderHTTPRead(status: status, data: data, sent: true, complete: complete, truncated: truncated)) }
        let session = Self.makeSession()
        defer { session.invalidateAndCancel() }
        let (bytes, response) = try await session.bytes(for: request)
        defer { bytes.task.cancel() }
        guard let response = response as? HTTPURLResponse else { throw HostError("chatgpt_transport_unavailable") }
        status = response.statusCode
        let maximum = (200...299).contains(response.statusCode) ? maximumBytes : min(maximumBytes, 65_536)
        if !observed, response.expectedContentLength > Int64(maximum) { truncated = true; throw HostError("chatgpt_response_too_large") }
        for try await byte in bytes {
            try Task.checkCancellation()
            guard data.count < maximum else { truncated = true; throw HostError("chatgpt_response_too_large") }
            data.append(byte)
            if data.count % 4096 == 0 { onBytes(data.count) }
        }
        onBytes(data.count)
        complete = true
        return .init(status: response.statusCode, requestID: response.value(forHTTPHeaderField: "x-request-id"), data: data)
    }
}

enum ChatGPTEndpoints {
    static let issuer = "https://auth.openai.com"
    static let resource = "https://api.openai.com/v1"
    static let token = URL(string: issuer + "/api/accounts/oauth/token")!
    static let authorize = URL(string: issuer + "/api/accounts/authorize")!
    static let discovery = URL(string: issuer + "/.well-known/openid-configuration")!
    static let models = URL(string: resource + "/models")!
    static let responses = URL(string: resource + "/responses")!
    static let usage = URL(string: "https://chatgpt.com/settings/usage")!
    static let scope = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
    static func validate(_ url: URL, authenticationOnly: Bool = false) throws {
        guard let value = URLComponents(url: url, resolvingAgainstBaseURL: false), value.scheme == "https",
              value.user == nil, value.password == nil, value.port == nil, value.fragment == nil,
              value.host == "auth.openai.com" || (!authenticationOnly && value.host == "api.openai.com" && ["/v1/models", "/v1/responses"].contains(value.path)),
              value.host == "auth.openai.com" || value.query == nil else { throw HostError("chatgpt_endpoint_invalid") }
    }
    static func form(_ fields: [String: String]) -> Data {
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")
        return Data(fields.sorted { $0.key < $1.key }.map {
            $0.key.addingPercentEncoding(withAllowedCharacters: allowed)! + "=" + $0.value.addingPercentEncoding(withAllowedCharacters: allowed)!
        }.joined(separator: "&").utf8)
    }
}

private final class ChatGPTRedirectPolicy: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
}

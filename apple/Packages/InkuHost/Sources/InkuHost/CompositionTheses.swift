import Foundation
import InkuCore

/// The core owns the four-thesis prompt, validation and the one permitted retry.
public enum CompositionTheses {
    private static func call(_ value: ExactJSON) throws -> ExactJSON {
        let result = try ExactJSON(data: InkuCore.compositionTheses(value.data))
        guard result["outcome"].string == "ok" else { throw HostError(result["reason"].string ?? "composition_theses_failed") }
        return result
    }

    public static func request(ask: ExactJSON) throws -> ExactJSON {
        guard var fields = ask.object else { throw HostError("invalid_request") }
        fields["action"] = .string("request")
        return try call(.object(fields))
    }

    public static func digest(request: ExactJSON) throws -> String {
        try call(.object(["action": .string("digest"), "request": request])).requiredString("prompt_digest")
    }

    public static func retry(ask: ExactJSON, answer: String, attempt: Int) throws -> ExactJSON {
        try call(.object(["action": .string("retry"), "ask": ask, "answer": .string(answer), "attempt": .integer(attempt)]))
    }

    /// A normal provider effect: the existing Claude and sign-in transports encode this same prompt.
    public static func effect(request: ExactJSON, actionID: String) throws -> ExactJSON {
        let prompt: ExactJSON = .object([
            "system": .string(try request.requiredString("system")),
            "message": .string(try request.requiredString("text")),
            "response_schema": try request.requiredObject("response_schema"),
            "action_name": .string("generate_normalized_ddl")
        ])
        return .object(["tag": .string("generate_normalized_ddl"), "identity": .object(["action_id": .string(actionID)]),
                        "timeout_ms": .string("120000"), "payload": .object(["prompt": prompt])])
    }
}

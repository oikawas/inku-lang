import Foundation
import InkuPersistence
import Observation

@MainActor @Observable
public final class LibraryNoteEditorModel {
    public var text = ""
    public private(set) var workID: String?
    public private(set) var state: LibraryAnnotationState = .unavailable
    public private(set) var savedText = ""
    public private(set) var saving = false
    public private(set) var errorText: String?
    @ObservationIgnored private var token = UUID()

    public init() {}

    public var dirty: Bool { text != savedText }
    public var canSave: Bool { state.annotation != nil && dirty && !saving && text.unicodeScalars.count <= 240 }

    public func receive(workID: String, state: LibraryAnnotationState) {
        if self.workID != workID {
            token = UUID()
            self.workID = workID
            text = ""
            savedText = ""
            saving = false
            errorText = nil
        }
        let wasDirty = dirty
        self.state = state
        if let annotation = state.annotation {
            savedText = annotation.note ?? ""
            if !wasDirty { text = savedText }
        }
    }

    /// A delayed result may update the saved baseline, but never replace an edited draft.
    @discardableResult
    public func save(using write: (String, String) async throws -> LibraryAnnotation) async -> LibraryAnnotation? {
        guard canSave, let id = workID else { return nil }
        let capturedToken = token
        let submitted = text
        saving = true
        errorText = nil
        defer { if token == capturedToken { saving = false } }
        do {
            let annotation = try await write(id, submitted)
            guard token == capturedToken, workID == id, !Task.isCancelled else { return nil }
            savedText = annotation.note ?? ""
            state = .available(annotation)
            if text == submitted { text = savedText }
            return annotation
        } catch {
            guard token == capturedToken, workID == id, !Task.isCancelled else { return nil }
            errorText = error.localizedDescription
            return nil
        }
    }
}

enum ThesisInput {
    static func limited(_ text: String) -> String {
        String(String.UnicodeScalarView(text.unicodeScalars.prefix(400)))
    }
}

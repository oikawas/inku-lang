import InkuHost

enum CompositionThings {
    static func units(_ units: [ExactJSON], for number: String) -> [ExactJSON] {
        units.filter { $0["thing"].number == number }
    }
    static func lines(_ units: [ExactJSON], for number: String) -> [Int] {
        self.units(units, for: number).flatMap { ($0["lines"].array ?? []).compactMap { $0.number.flatMap(Int.init) } }
    }
    static func thing(_ units: [ExactJSON], atLine line: Int) -> String? {
        units.first { ($0["lines"].array ?? []).contains { $0.number.flatMap(Int.init) == line } }?["thing"].number
    }
}

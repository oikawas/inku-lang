// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "InkuExport",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [.library(name: "InkuExport", targets: ["InkuExport"])],
    dependencies: [.package(path: "../InkuCore"), .package(path: "../InkuHost"), .package(path: "../InkuPersistence")],
    targets: [
        .target(name: "InkuExport", dependencies: ["InkuCore", "InkuHost", "InkuPersistence"], resources: [.copy("Resources")]),
        .testTarget(name: "InkuExportTests", dependencies: ["InkuExport"]),
    ],
    swiftLanguageModes: [.v6]
)

// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "InkuExport",
    platforms: [.macOS(.v15), .iOS(.v18)],
    products: [.library(name: "InkuExport", targets: ["InkuExport"])],
    dependencies: [.package(path: "../InkuCore"), .package(path: "../InkuHost"), .package(path: "../InkuPersistence")],
    targets: [
        // The files sit at the bundle's top: an iOS bundle is flat, and codesign rejects one whose top holds a folder
        // named "Resources" ("bundle format unrecognized"; ios-app step 2, 2026-11-08).
        .target(name: "InkuExport", dependencies: ["InkuCore", "InkuHost", "InkuPersistence"],
                resources: [.copy("Resources/NotoSerifJP-Variable.ttf"), .copy("Resources/OFL.txt"), .copy("Resources/FONT-PROVENANCE.md")]),
        .testTarget(name: "InkuExportTests", dependencies: ["InkuExport"]),
    ],
    swiftLanguageModes: [.v6]
)

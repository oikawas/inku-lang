// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "InkuApple",
    defaultLocalization: "ja",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .library(name: "InkuUI", targets: ["InkuUI"]),
        .executable(name: "InkuMac", targets: ["InkuMac"]),
        .executable(name: "InkuAppCheck", targets: ["InkuAppCheck"]),
    ],
    dependencies: [
        .package(path: "Packages/InkuCore"),
        .package(path: "Packages/InkuHost"),
        .package(path: "Packages/InkuPersistence"),
        .package(path: "Packages/InkuExport"),
    ],
    targets: [
        .target(name: "InkuUI", dependencies: ["InkuCore", "InkuHost", "InkuPersistence", "InkuExport"],
                resources: [.copy("Resources/server-defaults.json"), .copy("Resources/color-catalogs.json"),
                            .copy("Resources/ui-reference.json"),
                            .copy("Resources/macro-sources.json"), .copy("Resources/saijiki.json"),
                            .copy("Resources/plugin-words.json"), .copy("Resources/plugin-previews"),
                            .process("Resources/Localization")]),
        .executableTarget(name: "InkuMac", dependencies: ["InkuUI"]),
        .executableTarget(name: "InkuAppCheck", dependencies: ["InkuUI", "InkuPersistence", "InkuCore", "InkuHost", "InkuExport"]),
    ],
    swiftLanguageModes: [.v6]
)

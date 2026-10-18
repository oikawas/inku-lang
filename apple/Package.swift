// swift-tools-version: 6.1
import Foundation
import PackageDescription

// The Web's registered 3D viewer, unchanged, is never committed: apple/scripts/build-macos.sh copies it into
// Sources/InkuUI/Resources/ddl3d/ (apple/scripts/sync-ddl3d-viewer.py) before building the app. A `.copy` of a
// missing path fails the build, so the resource is declared only when the copy exists; a build without it has no
// 3D switch. SwiftPM keeps the manifest it read until this file changes, so a package first built before the copy
// existed goes on without it (InkuAppCheck --ddl3d-only reads the copy where it is).
let ddl3dCopied = FileManager.default.fileExists(atPath: Context.packageDirectory + "/Sources/InkuUI/Resources/ddl3d")

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
                            .copy("Resources/ui-reference.json"), .copy("Resources/third-party-notices.json"),
                            .copy("Resources/macro-sources.json"), .copy("Resources/saijiki.json"),
                            .copy("Resources/plugin-words.json"), .copy("Resources/plugin-previews"),
                            .process("Resources/Localization")] + (ddl3dCopied ? [.copy("Resources/ddl3d")] : [])),
        .executableTarget(name: "InkuMac", dependencies: ["InkuUI"]),
        .executableTarget(name: "InkuAppCheck", dependencies: ["InkuUI", "InkuPersistence", "InkuCore", "InkuHost", "InkuExport"]),
    ],
    swiftLanguageModes: [.v6]
)

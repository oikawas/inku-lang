// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "InkuApple",
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
    ],
    targets: [
        .target(name: "InkuUI", dependencies: ["InkuCore", "InkuHost", "InkuPersistence"],
                resources: [.copy("Resources/server-defaults.json"), .copy("Resources/color-catalogs.json")]),
        .executableTarget(name: "InkuMac", dependencies: ["InkuUI"]),
        .executableTarget(name: "InkuAppCheck", dependencies: ["InkuUI", "InkuPersistence", "InkuCore", "InkuHost"]),
    ],
    swiftLanguageModes: [.v6]
)

// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "InkuCore",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .library(name: "InkuCore", targets: ["InkuCore"]),
        .executable(name: "InkuCoreCheck", targets: ["InkuCoreCheck"]),
    ],
    targets: [
        .binaryTarget(name: "InkuCoreFFI", path: "Artifacts/InkuCoreFFI.xcframework"),
        .target(name: "InkuCoreBindings", dependencies: ["InkuCoreFFI"]),
        .target(name: "InkuCore", dependencies: ["InkuCoreBindings"]),
        .executableTarget(name: "InkuCoreCheck", dependencies: ["InkuCore"]),
    ]
)

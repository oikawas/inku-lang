// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "InkuHost",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [.library(name: "InkuHost", targets: ["InkuHost"])],
    dependencies: [.package(path: "../InkuCore"), .package(path: "../InkuPersistence")],
    targets: [
        .target(name: "InkuHost", dependencies: ["InkuCore", "InkuPersistence"]),
        .testTarget(name: "InkuHostTests", dependencies: ["InkuHost"]),
    ]
)

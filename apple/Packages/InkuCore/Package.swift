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
        // The Rust archive carries Skia (inku-display), a C++ library. These are the
        // libraries skia-bindings 0.153.3 links for its CPU-only Apple builds.
        .target(name: "InkuCoreBindings", dependencies: ["InkuCoreFFI"],
                linkerSettings: [
                    .linkedLibrary("c++"),
                    .linkedFramework("ApplicationServices", .when(platforms: [.macOS])),
                    .linkedFramework("CoreFoundation", .when(platforms: [.iOS])),
                    .linkedFramework("CoreGraphics", .when(platforms: [.iOS])),
                    .linkedFramework("CoreText", .when(platforms: [.iOS])),
                    .linkedFramework("ImageIO", .when(platforms: [.iOS])),
                    .linkedFramework("MobileCoreServices", .when(platforms: [.iOS])),
                    .linkedFramework("UIKit", .when(platforms: [.iOS])),
                ]),
        .target(name: "InkuCore", dependencies: ["InkuCoreBindings"]),
        .executableTarget(name: "InkuCoreCheck", dependencies: ["InkuCore"]),
    ]
)

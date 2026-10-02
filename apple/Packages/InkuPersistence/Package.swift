// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "InkuPersistence",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [.library(name: "InkuPersistence", targets: ["InkuPersistence"])],
    dependencies: [
        .package(url: "https://github.com/groue/GRDB.swift.git", exact: "7.11.1")
    ],
    targets: [
        .target(
            name: "InkuPersistence",
            dependencies: [.product(name: "GRDB", package: "GRDB.swift")],
            resources: [.copy("Resources/schema-v1.sql"), .copy("Resources/migration-v2.sql")]),
        .testTarget(name: "InkuPersistenceTests", dependencies: [
            "InkuPersistence", .product(name: "GRDB", package: "GRDB.swift")
        ])
    ],
    swiftLanguageModes: [.v6]
)

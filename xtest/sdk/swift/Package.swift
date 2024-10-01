// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "cli",
    platforms: [
        .macOS(.v10_15),
    ],
    products: [
        .executable(
            name: "cli",
            targets: ["cli"]
        ),
    ],
    dependencies: [
        .package(url: "https://github.com/arkavo-org/OpenTDFKit.git", exact: "2.0.1"),
        .package(url: "https://github.com/apple/swift-argument-parser.git", from: "1.5.0"),
    ],
    targets: [
        .executableTarget(
            name: "cli",
            dependencies: [
                .product(name: "ArgumentParser", package: "swift-argument-parser"),
            ],
            path: "./",
            exclude: [
                "cli.sh",
            ]
        ),
    ]
)

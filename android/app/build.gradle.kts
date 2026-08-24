plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
    id("androidx.room")
}

fun shouldIncrementAndroidBuildNumber(): Boolean {
    return gradle.startParameter.taskNames.any { taskName ->
        val name = taskName.substringAfterLast(':')
        name.startsWith("assemble") || name.startsWith("bundle") || name.startsWith("install")
    }
}

fun nextAndroidBuildNumber(): Int {
    val buildNumberFile = rootProject.file("BUILD_NUMBER")
    val current = buildNumberFile.readText().trim().toInt()
    if (!shouldIncrementAndroidBuildNumber()) return current
    // Build number is intentionally incremented only for package-producing tasks.
    // Avoid invoking assemble/install from unrelated checks when a clean worktree is required.
    val next = current + 1
    buildNumberFile.writeText("$next\n")
    logger.lifecycle("Android BUILD_NUMBER incremented: $current -> $next")
    return next
}

val androidVersionName = rootProject.file("VERSION").readText().trim()
val androidVersionCode = nextAndroidBuildNumber()
val androidMinSdk = 35
val rustAndroidTarget = "aarch64-linux-android"
val rustAndroidApi = androidMinSdk
val rustNativeLibraryName = "libinku_render_android.so"
val rustTargetDirectory = layout.buildDirectory.dir("rust-target")
val rustGeneratedJniLibsDirectory = layout.buildDirectory.dir("generated/rustJniLibs")
val rustParityAssetsDirectory = layout.buildDirectory.dir("generated/rustParityAssets")
val rustNdkHostTag = when {
    System.getProperty("os.name").startsWith("Mac") -> "darwin-x86_64"
    System.getProperty("os.name").startsWith("Linux") -> "linux-x86_64"
    else -> error("Unsupported Android native build host: ${System.getProperty("os.name")}")
}
val rustParityCaseNames = listOf(
    "A-pen-circle",
    "B-wave-medium-line-brush_thick",
    "C-filter-display-pencil",
    "D-canvas-wide-region-single",
    "E-wild-surface-wash-pencil",
)

android {
    namespace = "app.inku.mobile"
    compileSdk = 36
    ndkVersion = "29.0.14206865"

    defaultConfig {
        applicationId = "app.inku.mobile"
        minSdk = androidMinSdk
        targetSdk = 36
        versionCode = androidVersionCode
        versionName = androidVersionName
        buildConfigField("int", "BUILD_NUMBER", androidVersionCode.toString())

        ndk {
            abiFilters += "arm64-v8a"
        }

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    buildTypes {
        debug {
            manifestPlaceholders["headlessExported"] = "true"
            manifestPlaceholders["headlessPermission"] = ""
        }
        release {
            manifestPlaceholders["headlessExported"] = "false"
            manifestPlaceholders["headlessPermission"] = "app.inku.mobile.permission.HEADLESS_RENDER"
        }
    }

    kotlin {
        jvmToolchain(21)
    }

    // MigrationTestHelper reads the exported schemas from the test APK's assets.
    sourceSets.getByName("androidTest") {
        assets.srcDir("$projectDir/schemas")
        assets.srcDir(rustParityAssetsDirectory)
    }
    sourceSets.getByName("main") {
        jniLibs.srcDir(rustGeneratedJniLibsDirectory)
    }

    testOptions {
        // The stages log what they hand a model, so a JVM test that walks the
        // real `interpret` / `composeFromDdl` hits `android.util.Log`. Without
        // this it throws and the only reachable path is `renderFromScore`,
        // which is the one path that chooses no prompt at all.
        unitTests.isReturnDefaultValues = true
    }
}

val rustNdkDirectory = androidComponents.sdkComponents.ndkDirectory
val rustLibrary = rustTargetDirectory.map {
    it.file("$rustAndroidTarget/release/$rustNativeLibraryName")
}

val buildRustAndroidArm64 = tasks.register<Exec>("buildRustAndroidArm64") {
    group = "build"
    description = "Build the shared Rust render/raster JNI library for arm64-v8a without packaging the app."
    workingDir(rootProject.file("../core"))
    inputs.files(
        rootProject.fileTree("../core") {
            include("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "crates/**/Cargo.toml", "crates/**/src/**/*.rs")
            exclude("target/**")
        },
    )
    outputs.file(rustLibrary)

    doFirst {
        val pinnedRustc = providers.exec {
            commandLine("rustup", "which", "--toolchain", "1.95.0", "rustc")
        }.standardOutput.asText.get().trim()
        require(file(pinnedRustc).isFile) { "Pinned Rust 1.95.0 rustc was not found" }
        val toolchainBin = rustNdkDirectory.get()
            .dir("toolchains/llvm/prebuilt/$rustNdkHostTag/bin")
            .asFile
        val clang = toolchainBin.resolve("aarch64-linux-android${rustAndroidApi}-clang")
        val clangxx = toolchainBin.resolve("aarch64-linux-android${rustAndroidApi}-clang++")
        val archiveTool = toolchainBin.resolve("llvm-ar")
        require(clang.isFile) { "Pinned NDK clang was not found: ${clang.name}" }
        require(clangxx.isFile) { "Pinned NDK clang++ was not found: ${clangxx.name}" }
        require(archiveTool.isFile) { "Pinned NDK llvm-ar was not found" }
        // `rustup run ... cargo` pins Cargo but Cargo can still resolve a
        // different `rustc` from PATH, so pin the compiler explicitly too.
        environment("RUSTC", pinnedRustc)
        environment("CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER", clang.absolutePath)
        environment("CC_aarch64_linux_android", clang.absolutePath)
        environment("CXX_aarch64_linux_android", clangxx.absolutePath)
        environment("AR_aarch64_linux_android", archiveTool.absolutePath)
    }

    commandLine(
        "rustup",
        "run",
        "1.95.0",
        "cargo",
        "build",
        "--locked",
        "--package",
        "inku-render-android",
        "--target",
        rustAndroidTarget,
        "--release",
        "--target-dir",
        rustTargetDirectory.get().asFile.absolutePath,
    )
}

val syncRustAndroidArm64 = tasks.register<Sync>("syncRustAndroidArm64") {
    group = "build"
    description = "Stage the generated arm64-v8a JNI library under app/build/."
    dependsOn(buildRustAndroidArm64)
    from(rustLibrary)
    into(rustGeneratedJniLibsDirectory.map { it.dir("arm64-v8a") })
}

val checkRustNativePackagingInput = tasks.register("checkRustNativePackagingInput") {
    group = "verification"
    description = "Verify the generated JNI packaging input without assembling an APK or changing BUILD_NUMBER."
    dependsOn(syncRustAndroidArm64)
    doLast {
        val root = rustGeneratedJniLibsDirectory.get().asFile
        val libraries = root.walkTopDown()
            .filter { it.isFile && it.extension == "so" }
            .map { it.relativeTo(root).invariantSeparatorsPath }
            .toList()
        check(libraries == listOf("arm64-v8a/$rustNativeLibraryName")) {
            "Expected exactly arm64-v8a/$rustNativeLibraryName, found $libraries"
        }
    }
}

val prepareRustParityAssets = tasks.register<Sync>("prepareRustParityAssets") {
    group = "verification"
    description = "Stage a bounded canonical Rust parity corpus for connected-device tests."
    from(rootProject.file("../server/reference/render-engine-41")) {
        include("manifest.json")
        rustParityCaseNames.forEach { include("$it.svg") }
        into("render-engine-41")
    }
    from(rootProject.file("../server/reference/render-engine-21")) {
        include("G-scatter-edge.svg")
        into("render-engine-21")
    }
    into(rustParityAssetsDirectory)
}

tasks.register("checkRustNative") {
    group = "verification"
    description = "Build and verify the non-package Rust Android native input."
    dependsOn(checkRustNativePackagingInput)
}

tasks.configureEach {
    if (
        name.startsWith("merge") &&
        (name.endsWith("NativeLibs") || name.endsWith("JniLibFolders"))
    ) {
        dependsOn(syncRustAndroidArm64)
    }
    if (name.startsWith("merge") && name.endsWith("AndroidTestAssets")) {
        dependsOn(prepareRustParityAssets)
    }
}

room {
    schemaDirectory("$projectDir/schemas")
}

dependencies {
    val roomVersion = "2.8.4"
    val composeBom = platform("androidx.compose:compose-bom:2026.04.01")

    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.core:core-ktx:1.18.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.10.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")

    implementation("com.google.ai.edge.litertlm:litertlm-android:0.11.0")
    implementation("androidx.room:room-runtime:$roomVersion")
    implementation("androidx.room:room-ktx:$roomVersion")
    ksp("androidx.room:room-compiler:$roomVersion")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")

    // Instrumented UI tests run on the connected Pixel 9; no emulator is used.
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.espresso:espresso-idling-resource:3.6.1")
    androidTestImplementation("androidx.room:room-testing:$roomVersion")

    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}

configurations.all {
    exclude(group = "androidx.test.espresso", module = "espresso-core")
}

// room-testing's schema bundles are generated against kotlinx-serialization 1.8.1,
// but a transitive BOM pins core to "strictly 1.7.3". The mismatch surfaces only at
// runtime, as AbstractMethodError on GeneratedSerializer.typeParametersSerializers().
configurations.configureEach {
    if (name.contains("AndroidTest")) {
        resolutionStrategy.force(
            "org.jetbrains.kotlinx:kotlinx-serialization-core:1.8.1",
            "org.jetbrains.kotlinx:kotlinx-serialization-core-jvm:1.8.1",
        )
    }
}

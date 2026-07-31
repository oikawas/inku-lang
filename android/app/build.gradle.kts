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

android {
    namespace = "app.inku.mobile"
    compileSdk = 36

    defaultConfig {
        applicationId = "app.inku.mobile"
        minSdk = 35
        targetSdk = 36
        versionCode = androidVersionCode
        versionName = androidVersionName
        buildConfigField("int", "BUILD_NUMBER", androidVersionCode.toString())

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
    implementation("com.caverock:androidsvg:1.4")

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

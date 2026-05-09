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

    kotlin {
        jvmToolchain(21)
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

    implementation("com.google.ai.edge.litertlm:litertlm-android:latest.release")
    implementation("com.caverock:androidsvg:1.4")

    implementation("androidx.room:room-runtime:$roomVersion")
    implementation("androidx.room:room-ktx:$roomVersion")
    ksp("androidx.room:room-compiler:$roomVersion")

    testImplementation("junit:junit:4.13.2")

    debugImplementation("androidx.compose.ui:ui-tooling")
}

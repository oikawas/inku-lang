# Install the GitHub Android APK

## Devices and downloads

The APK supports Android 15 or newer on arm64 devices. In [GitHub Releases](https://github.com/oikawas/inku-lang/releases), open an Android release whose tag starts with `android-v`, and download its APK and `SHA256SUMS`. Android and Web/API versions are independent. The APK contains no model weights, API keys, personal ChatGPT credentials or work data.

Compare the APK's SHA-256 with `SHA256SUMS`. The release also includes third-party notices and public signing-certificate information. Notices are bundled in the APK under `assets/licenses/` as well.

## Installation and updates

Open the APK on your phone and, if required, allow installation of unknown apps for that browser or file manager only. You can revoke this permission after installation. Future updates install a newer Build signed with the same public-distribution key over the existing app. GitHub updates are manual.

**The public APK uses a different signing key from development debug builds.** It cannot directly update an existing debug installation of `app.inku.mobile`. To preserve works, do not uninstall the debug app or clear its data to install the public APK. Keep existing development devices intact; use another device for the first public installation, or prepare a separate migration that preserves the data.

## Start drawing

For a ChatGPT plan, complete personal authorization in Chrome from the ChatGPT plan settings and acknowledge the usage notice. In Model settings, fetch your personal catalog, publish and save the models you want to use, then select a drawing model. Available models and limits depend on your plan. API-key providers remain available.

For an on-device Gemma model, accept its license and download it separately. On Pixel 9, Gemma 4 E2B assigns locations even to layers whose description gives no location, so on-device composition reading is disabled. Its output is not guaranteed to match cloud models.

Works are stored on the device. This guide describes distribution with the new public signing key; it does not claim acceptance on every device or model.

## Build a public APK from source

Prepare Java 21, Python 3.11 or newer, Android SDK 36, NDK 29.0.14206865, the pinned Rust toolchain and Android target. Use clean source with finalized Android version and Build values.

```sh
cd android
rustup component add rust-docs --toolchain 1.95.0
./gradlew :app:assembleRelease -PinkuAndroidReproducibleRelease=true
```

This option uses the finalized `android/BUILD_NUMBER` without changing it. Ordinary debug and development packaging keep their automatic Build increment. The release resolves its runtime dependencies and bundles upstream LICENSE and NOTICE files, including LiteRT-LM's complete JNI notices, together with the Rust dependency and standard-library license inventories. The pinned toolchain's standard-library copyright information requires `rust-docs`.

Align the unsigned APK with the SDK's `zipalign`, then sign it with `apksigner` using a dedicated distribution key stored outside Git. Never put the private key or password in source, build logs or GitHub. Keep the key secure: future updates need it. Before publishing, verify the signature, non-debuggable flag, version and Build, arm64 native libraries and bundled notices.

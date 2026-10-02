# Appleクライアント

macOS先行のSwiftUIクライアントです。DDL、Score、prompt、状態遷移、seed、SVG生成とrasterはServer／Androidと同じRust coreを使います。Swift hostがnetwork、Keychain、SQLite、OS lifecycleとnative表示を担当します。実行時にinku ServerやPython runtimeは不要です。macOSにcamera機能はありません。

Swift固有の仕様正本は[SWIFT_SPEC.ja.md](SWIFT_SPEC.ja.md)、対応英語版は[SWIFT_SPEC.md](SWIFT_SPEC.md)です。Androidと同じく、日本語の仕様を先に更新し、英語を同期します。製品の変更履歴はrepository rootの[CHANGELOG.ja.md](../CHANGELOG.ja.md)／[CHANGELOG.md](../CHANGELOG.md)へ日付付きで追記し、確定した仕様と未実装範囲はSwift SPECへ記します。共有DDL／Score／renderの意味はroot SPECを正本とします。

## 現在の範囲

M1のSwift／Rust基盤と、M2のstandalone host／SQLite保存境界、初期macOS画面を実装しています。DDLからの生成、保存作品の選択と再演奏、DDL／Score表示、canvasの拡大・移動、最近の作品、library検索、provider設定、SVG／PNG書出し、画像コピー、DB backup／restoreを接続しています。

限定した確認で、DDL→Score／SVG→SQLite保存→アプリモデルの再作成後の読出し、native CGImage生成、保存canonical SVGの書出しが成立しています。Swift／Rust境界ではowned pixel buffer、入力エラーとUInt64のseed保持を確認しています。macOSのarm64／x86_64 Rust sliceとx86_64 Swift executableのlink、iOS device／simulatorのRust artifact生成も確認しています。Intel実機での性能・起動、実providerへのLLM送信、作者による通常画面操作の受入は別の確認です。

M3のフル機能UIは未完了です。系譜graph、favorite／trash操作、plugin／model助言dialog、batch／demo、custom・animated exportや共有card等は今後の実装です。系譜画面は未接続であることを明示しています。iOSは共通packageとRust artifactの基盤までで、iPad／iPhone app、camera、shareと実機受入は未完了です。

## 対応OSとbuild環境

最低OSはmacOS 14／iOS 17です。SDKの版は最低OSとは別です。確認した環境はXcode 27.0／Swift 6.4、Rust 1.95.0、XcodeGen 2.46.0です。Swift packageはtools 6.1、projectはXcodeGen 2.44.0以上を要求します。

buildにはmacOS、XcodeのCLI tools、XcodeGen、Python 3.11以上、公式rustupが必要です。PythonはServer正本からbuild用resourceを生成するためにだけ使い、アプリへ組み込みません。初回はCargoとSwiftPMの固定依存を取得するnetwork接続が必要です。

主な固定依存はUniFFI 0.32.0、GRDB 7.11.1です。Rustのtoolchain／依存は`core/rust-toolchain.toml`と`core/Cargo.lock`、GRDBは`Packages/InkuPersistence/Package.swift`とSwiftPMの解決記録で管理します。UniFFI generatorは同じcheckoutのCargo.lockからbuildし、そのRust archiveのmetadataを読みます。

## clean cloneからのmacOS build

以下はproduct repository rootから実行します。必要なtoolとXcodeを用意した後、固定Rust toolchainとMac targetを導入してください。scriptはtoolchain導入やXcode／Apple accountの設定変更を自動実行しません。

```sh
rustup toolchain install 1.95.0 --profile minimal --component rustfmt --component clippy
rustup target add --toolchain 1.95.0 aarch64-apple-darwin x86_64-apple-darwin
apple/scripts/build-macos.sh Release
```

`build-macos.sh`はServer sourceからresourceを生成し、共通RustとSwift binding／XCFrameworkを生成し、`project.yml`からXcode projectを作ってmacOS appをbuildします。generic Mac destination、`ARCHS=arm64 x86_64`、`ONLY_ACTIVE_ARCH=NO`を指定し、最後に両sliceの存在を検査します。Apple account、Team、証明書を使わないunsigned local buildです。署名、notarization、配布はこの手順に含みません。

defaultはRelease appとrelease Rustです。XcodeのDebug appを選んでも、Rustは明示指定しない限りreleaseのままです。両方をdebugにする場合は次を使います。

```sh
INKU_APPLE_PROFILE=debug apple/scripts/build-macos.sh Debug
```

Release appは`apple/build/macOS/DerivedData/Build/Products/Release/Inku.app`に生成されます。Xcodeで開く場合は生成後の`apple/Inku.xcodeproj`を使います。build出力、Serverから生成したresource、Swift bindingとXCFrameworkは再生成する成果物です。source変更後は同じ手順で更新してください。

```sh
open apple/build/macOS/DerivedData/Build/Products/Release/Inku.app
```

## 通常利用と隔離した試行

初期入力は英語の直接DDLです。モデル接続なしで生成を試せます。記述から生成する場合は「設定」でprovider方式、base URL、model、必要なAPI keyを保存してから「作成」の記述modeを使います。現在の設定画面は一つの接続先と、Stage1／Stage2で同じmodelを選ぶ基盤です。接続を保存するだけではLLM requestを送りません。

作品のDBはアプリのApplication Supportに、通常のprovider設定はDBと同じdirectoryの`providers.json`に保存します。API keyはKeychainの別itemです。SQLite backupは作品・系譜・execution／ACK／snapshotを含むDBの整合したcopyであり、provider JSONやKeychainのbackupではありません。

通常の作品DBを使わずに試す場合は、実行fileへ`--database`を渡します。

```sh
preview_dir="$(mktemp -d)"
apple/build/macOS/DerivedData/Build/Products/Release/Inku.app/Contents/MacOS/Inku \
  --database "$preview_dir/inku.sqlite"
```

この指定はDBと隣接するprovider JSONの保存先を変えます。Keychainは独立したままです。保存作品の読出しだけでDDLを再compileしたり、保存SVGを再生成したりしません。再演奏は明示操作として新しい保存結果を作ります。

## 共通packageとiOS artifact

`Packages/InkuCore`がowned `Data` APIとgenerated UniFFI binding、`Packages/InkuHost`がprovider transportとexecution actor、`Packages/InkuPersistence`がGRDB／SQLite adapter、`Sources/InkuUI`がnative画面とapp modelです。public Swift sourceから意味処理を複製しません。

共通Rustだけを生成する場合は次を使います。Swift packageを直接buildする場合も、先にartifact生成が必要です。

```sh
apple/scripts/build-core.sh macos
```

iOS artifactを含める場合はtargetを追加して`all`を指定します。

```sh
rustup target add --toolchain 1.95.0 aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios
apple/scripts/build-core.sh all
```

XCFrameworkはmacOS arm64／x86_64、iOS arm64 device、iOS arm64／x86_64 simulatorを別variantに保持します。異なるplatformのsliceをlipoで混ぜません。`Packages/InkuCore/Artifacts/build-manifest.json`にproduct commit、core source fingerprint、toolchain／generator、archive hash、profileと最低OSを記録します。`macos`を再実行するとMacのみのartifactへ置き換わるため、iOS build前には`all`を実行してください。

限定したCLI確認は、artifact生成後の`apple/scripts/check-core.sh`と、resource生成後の`swift run --package-path apple InkuAppCheck`です。これらはnative画面、実provider、実機の受入を代替しません。変更が防ぐ具体的な失敗に合わせて必要な確認だけを選択してください。

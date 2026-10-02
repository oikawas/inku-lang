# Appleクライアント

macOS先行のSwiftUIクライアントです。DDL、Score、prompt、状態遷移、seed、SVG生成とrasterはServer／Androidと同じRust coreを使います。Swift hostがnetwork、Keychain、SQLite、OS lifecycleとnative表示を担当します。実行時にinku ServerやPython runtimeは不要です。macOSにcamera機能はありません。

Swift固有の仕様正本は[SWIFT_SPEC.ja.md](SWIFT_SPEC.ja.md)、対応英語版は[SWIFT_SPEC.md](SWIFT_SPEC.md)です。Androidと同じく、日本語の仕様を先に更新し、英語を同期します。製品の変更履歴はrepository rootの[CHANGELOG.ja.md](../CHANGELOG.ja.md)／[CHANGELOG.md](../CHANGELOG.md)へ日付付きで追記し、確定した仕様と未実装範囲はSwift SPECへ記します。共有DDL／Score／renderの意味はroot SPECを正本とします。

## 現在の範囲

M1のSwift／Rust基盤、M2のstandalone host／SQLite保存境界に続き、macOSの制作・全件履歴／library・系譜、DDL編集／補完承認、plugin／歳時記、比較／助言／奥書、batch／demo、表示／接続設定、全export方式を接続しています。保存作品の条件を次の入力条件と分け、通常表示と明示した再演奏を区別します。詳細と確認の範囲は[Swift SPEC](SWIFT_SPEC.ja.md)の2026-10-03節を参照してください。

限定した確認で、DDL→Score／SVG→SQLite保存→アプリモデルの再作成後の読出し、native CGImage生成、保存canonical SVGの書出しが成立しています。Swift／Rust境界ではowned pixel buffer、入力エラーとUInt64のseed保持を確認しています。macOSのarm64／x86_64 Rust sliceとx86_64 Swift executableのlink、iOS device／simulatorのRust artifact生成も確認しています。Intel実機での性能・起動、実providerへのLLM送信、作者による通常画面操作の受入は別の確認です。

更新したUniversal appの隔離DBで、DDL生成→編集child→libraryのcomment／star→trash／復元→restart、日英切替と系譜表示、複数選択2作品のPNG2160保存を確認しています。機能のsource接続、限定したoffline確認、native操作、作者の通常利用の受入は別に記録します。旧Server／Android物理DBのimport、実provider／OAuth、他exportのnative・性能、Intel／macOS14実機、署名・配布は未完了です。廃止済みhistory.json移行utilityの配列は現行Webの復元形式ではありません。iOSは共通packageと初期Rust artifactまでで、最新APIのartifact再生成、iPad／iPhone app、camera、shareと実機受入は未完了です。

Personal ChatGPTは設定の専用画面で明示して有効化・接続し、提供されたmodelを描画用に選びます。通常のAPI key接続とは別で、初期状態は無効です。発行済みclient IDと本人の接続同意が必要で、実本人認証・model取得・推論は未受入です。記述、写生、自動配色、構図の読み、DDL補完に対応し、Vision推敲・奥書等の未対応用途は画面で説明します。詳細は[Swift仕様](SWIFT_SPEC.ja.md#personal-chatgpt)を参照してください。

## 対応OSとbuild環境

最低OSはmacOS 14／iOS 17です。SDKの版は最低OSとは別です。確認した環境はXcode 27.0／Swift 6.4、Rust 1.95.0、XcodeGen 2.46.0です。Swift packageはtools 6.1、projectはXcodeGen 2.44.0以上を要求します。

buildにはmacOS、XcodeのCLI tools、XcodeGen、Python 3.11以上、uv、公式rustupが必要です。PythonとuvはServer正本からbuild用resourceと固定辞書を生成するためにだけ使い、アプリへ組み込みません。初回はCargo、SwiftPMとServerのuv.lock依存を取得するnetwork接続が必要です。

主な固定依存はUniFFI 0.32.0、GRDB 7.11.1です。Rustのtoolchain／依存は`core/rust-toolchain.toml`と`core/Cargo.lock`、GRDBは`Packages/InkuPersistence/Package.swift`とSwiftPMの解決記録で管理します。UniFFI generatorは同じcheckoutのCargo.lockからbuildし、そのRust archiveのmetadataを読みます。

## clean cloneからのmacOS build

以下はproduct repository rootから実行します。必要なtoolとXcodeを用意した後、固定Rust toolchainとMac targetを導入してください。scriptはtoolchain導入やXcode／Apple accountの設定変更を自動実行しません。

```sh
rustup toolchain install 1.95.0 --profile minimal --component rustfmt --component clippy
rustup target add --toolchain 1.95.0 aarch64-apple-darwin x86_64-apple-darwin
apple/scripts/build-macos.sh Release
```

`build-macos.sh`はServer sourceからdefault・catalog・歳時記・plugin resourceを生成し、`uv sync --project server --frozen`で固定したbuild用依存を用意します。[辞書準備script](scripts/prepare-meter-resources.py)がSudachi small（約113MiB）、読み設定とCMUdictをhash検証し、licenseと共にInkuHost resourceへコピーします。共通RustとSwift binding／XCFrameworkを生成し、`project.yml`からXcode projectを作ってmacOS appをbuildします。generic Mac destination、`ARCHS=arm64 x86_64`、`ONLY_ACTIVE_ARCH=NO`を指定し、最後に両sliceの存在を検査します。Apple account、Team、証明書を使わないunsigned local buildです。署名、notarization、配布はこの手順に含みません。

Rust 1.95のmacOS host proc-macro stripによる[LINKEDIT alignment問題](https://github.com/rust-lang/rust/issues/157750)を避けるため、releaseのhost build dependencyだけstripを無効にします。target Rust archiveの最適化とstripは維持します。cache削除やtoolchain変更は不要です。

defaultはRelease appとrelease Rustです。XcodeのDebug appを選んでも、Rustは明示指定しない限りreleaseのままです。両方をdebugにする場合は次を使います。

```sh
INKU_APPLE_PROFILE=debug apple/scripts/build-macos.sh Debug
```

Release appは`apple/build/macOS/DerivedData/Build/Products/Release/Inku.app`に生成されます。Xcodeで開く場合は生成後の`apple/Inku.xcodeproj`を使います。build出力、Serverから生成したresource、Swift bindingとXCFrameworkは再生成する成果物です。source変更後は同じ手順で更新してください。

```sh
open apple/build/macOS/DerivedData/Build/Products/Release/Inku.app
```

## 通常利用と隔離した試行

初期入力は英語の直接DDLです。モデル接続なしで生成を試せます。記述から生成する場合は「設定」でprovider方式、base URL、model、必要なAPI keyを保存してから制作画面の記述modeを使います。複数のAPIサービスを登録でき、Stage1／Stage2は共通の描画modelを使用します。model一覧の取得は明示したボタン操作で行います。接続を保存するだけではLLM requestを送りません。

制作画面の「次の生成条件」で次に使うservice／modelを選びます。この選択は設定の保存defaultや開始済みbatch／demoを変えません。生成／停止buttonは入力のscroll領域の外にあります。⌘Nで新規、⌘OでDDL読込、⌘,で設定、⌘1〜4で画面移動、⇧⌘Eで書出しを開けます。libraryのcheckboxと表示作品を区別し、制作からの書出しは表示中の保存作品を使います。

制作とモデル設定で「モデルの適性・用途」を開くと、Serverの登録評価・用途・commentと接続先から取得した情報を別々に読めます。未登録のservice／modelは推測で評価しません。処理中は段階・呼出しmodel・試行回数・経過時間を表示し、未取得token数は「記録なし」とします。停止で時間が確定し、新規制作で前の進行表示を消します。

保存作品の操作から「記述を変える」「写生なし／ありで描き直す」を開くと、その作品を親とする新しい子を描けます。直接DDLや確定DDL編集の作品は記述へ戻せません。色カタログは色名・HEX・説明を見て次の生成条件へ確定します。DDLは標準panelまたは1つのfileのwindow dropから読み込み、まだ保存されていない制作draftへ反映します。

「描画パラメータの編集」では配置・読み取り・変奏の1案／4案、言葉によるタッチの1案を比較し、選んだ候補だけを子として保存します。候補の準備・拡大だけでは表示作品や通常履歴を変えません。タッチは保存Scoreと共通Rustの語句seedを使い、現在の変奏は無変更であることを画面へ表示します。停止・破棄と採用を区別し、model設定へ移る場合は未保存候補を先に採用または破棄してください。

作品のDBはアプリのApplication Supportに、通常のprovider設定はDBと同じdirectoryの`providers.json`に保存します。API keyはKeychainの別itemです。SQLite backupは作品・系譜・execution／ACK／snapshot、comment／mark、奥書、未読語を含むDBの整合したcopyであり、隣接設定JSONやKeychainのbackupではありません。

通常の作品DBを使わずに試す場合は、実行fileへ`--database`を渡します。

```sh
preview_dir="$(mktemp -d)"
apple/build/macOS/DerivedData/Build/Products/Release/Inku.app/Contents/MacOS/Inku \
  --database "$preview_dir/inku.sqlite"
```

この指定はDBと隣接するprovider JSONの保存先を変えます。Keychainは独立したままです。保存作品の読出しだけでDDLを再compileしたり、保存SVGを再生成したりしません。通常の「再演奏」は保存SVGと現行エンジンの再現を比較し、保存・履歴・系譜を変更しません。「次の条件で再演奏」は新しい保存childを作ります。

## 共通packageとiOS artifact

`Packages/InkuCore`がowned `Data` APIとgenerated UniFFI binding、`Packages/InkuHost`がprovider transportとexecution actor、`Packages/InkuPersistence`がGRDB／SQLite adapter、`Packages/InkuExport`が保存作品のSVG／PNG／DDL／card／sheet／animation、`Sources/InkuUI`がnative画面とapp modelです。public Swift sourceから意味処理を複製しません。

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

Swift packageを直接buildする場合は、Rust artifactに加えてresourceも先に用意してください。

```sh
python3 apple/scripts/export-server-resources.py
uv sync --project server --frozen
python3 apple/scripts/prepare-meter-resources.py
```

追加のAppCheck選択は`--provider-progress-only`と`--model-guidance-only`です。前者はmock／共通Rustで再試行の表示・時計・停止と遅いcallback、後者は生成したServer評価資料と一時DBで適性・未登録境界・選択とsnapshotの保持を確認します。実providerへの呼出しは行いません。

構図への追随は`--composition-host-only`と`--composition-progress-only`で確認します。hostは実Rust／mock／一時DBで構図要求・固定Stage 1 modelと上限・schema・保存・有限retry／fallback・旧設定／保存Score再生を、progressは段階時計・再試行・日英表示・prompt履歴の分離・停止を確認します。`--composition-personal-plan-gate-only`は未接続の有効UUIDと空の一時vaultでPersonal ChatGPTの最終routing拒否だけを確認し、実HTTP／OAuth／Keychainを使いません。

限定したCLI確認は、artifact生成後の`apple/scripts/check-core.sh`と、resource生成後の`swift run --package-path apple InkuAppCheck`です。AppCheckの`--authoring-only`、`--comparison-only`、`--automation-only`、`--plugin-only`、`--model-selection-only`、`--work-edit-only`、`--refinement-only`、`--replay-comparison-only`、`--auxiliary-provenance-only`、`--raster-only <SVG path>`はそれぞれの変更に対応する確認だけを選びます。`--model-selection-only`は一時DBとprovider呼出し0件で、制作のmodel選択と保存default・開始時snapshotの分離を確認します。`--work-edit-only`はmock transportと共通coreで保存親の編集・写生・childのDDL authority・取消しを確認します。`--refinement-only`は語句seedと保存Score、固定4案、無変更の変奏、明示採用・再表示後のDDL child、edge metadataと遅い応答の拒否を同じ隔離境界で確認します。`--replay-comparison-only`はprovider0件の再現比較が保存・表示を変えないこととseed・停止の境界、`--auxiliary-provenance-only`はmockによる世代ごとのVision／random来歴を確認します。これらはnative画面、実provider、実機の受入を代替しません。変更が防ぐ具体的な失敗に合わせて必要な確認だけを選択してください。

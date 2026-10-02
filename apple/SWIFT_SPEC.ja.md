# inku Swift 実装仕様

このディレクトリは、macOS先行のnative SwiftUIクライアントとApple向け共通packageのworkspaceである。本書をSwift host固有の仕様正本とし、[SWIFT_SPEC.md](SWIFT_SPEC.md)を対応英語版とする。共有DDL、Score、prompt、authoring authority、pipeline状態遷移、seed、描画の意味は[製品仕様](../SPEC.ja.md)を正本とし、Serverを開発上のprimaryとして同じRust coreへ追随する。Swift側に意味処理を複製しない。

最終更新: 2026-10-02。

binding／protocolの版は同梱Rust coreのversion report、描画層の版はrender metadataと[Serverの層定義](../server/src/inku_server/layer_versions.py)を参照する。本書へ共通engineの版定数を複製しない。Swiftアプリの製品版は正式な版管理に従い、この初期実装では新しい版を採番しない。共有層の版が一致しても、host機能とnative UIの移植が完了したことにはならない。

## 更新ルール

- `SWIFT_SPEC.ja.md`をSwift仕様の正本とする。
- Swift仕様を変更するときは日本語を先に更新し、その意図を保った翻訳・要約として`SWIFT_SPEC.md`を同期する。英語版だけに仕様・要件を追加しない。
- 確定した実装変更と残る範囲は本書の日付付き節へ記し、製品の変更履歴は共通の[CHANGELOG.ja.md](../CHANGELOG.ja.md)／[CHANGELOG.md](../CHANGELOG.md)へ同期して記す。Swift専用CHANGELOGを分けない。
- 共通の意味や保存契約を変更する場合は、それぞれの正本を更新する。本書はSwift hostの適用範囲を説明し、独自の共通仕様を作らない。
- sourceと再現手順を公開文書に記す。生成binary、model、log、credential、端末識別子や非公開の作業記録を追跡対象に含めない。

## 2026-10-02 macOS向けの共有Rust・standalone基盤

### 対象と実装段階

最低OSはmacOS 14／iOS 17とする。SDKの版と最低OSは別に管理する。macOSのarm64／x86_64 Universal appを先にフル機能へ進め、その後iPad／iPhoneへ展開する。現在はM1のSwift／Rust接続、M2のstandalone host／SQLite保存境界と初期macOS UIを実装した段階で、M3のフル機能UIは未完了である。

Appleクライアントは単一利用者のローカルappであり、Serverの認証・管理・複数利用者機能を持ち込まない。実行時にinku ServerやPython runtimeは不要である。cameraは今後のiOS側の機能とし、macOSには設けない。iOS appとcamera自体は未実装である。

### packageと責務

| 部分 | 責務 |
| --- | --- |
| [InkuCore](Packages/InkuCore/Package.swift) | 同じcheckoutのRust coreをUniFFIで呼ぶowned `Data` API、version report、共通registry、compile／step／render／rasterの境界。 |
| [InkuHost](Packages/InkuHost/Package.swift) | provider transport、Keychain、provider設定、execution actor、coreが要求したeffectの実行。 |
| [InkuPersistence](Packages/InkuPersistence/Package.swift) | GRDB／SQLiteによる作品・系譜・execution／ACK／snapshot保存、CAS、manual backup／restore。 |
| [InkuUI](Package.swift) | native画面、app model、OS file panel／clipboard、表示用image cache。 |

UniFFI bindingは固定したCargo依存と同じRust archiveのmetadataから生成し、handwritten Swiftでunsafe FFIを追加しない。Rustの入力エラーとpanicは公開境界で封止する。DDLのcompile、保存Scoreの再描画、canvas／color registryは既存の共通facadeを使用する。巨大なpixel bufferをJSONやbase64のpayloadへ変換しない。

build用のdefault設定とcolor catalogはServer sourceから生成する。Macro定義・plugin等の全resource接続はM3で残る。生成処理に使うPythonは開発時だけの依存であり、appに組み込まない。固定依存とgeneratorの手順は[build手順](README.ja.md)および各package／`core/Cargo.lock`を参照する。

### execution、provider、取消

[PipelineHost](Packages/InkuHost/Sources/InkuHost/PipelineHost.swift)はexecutionごとのdriverでcore状態変更と保存を直列化する。prompt、schema、retryの判断、documentとauthoring authorityの意味はcoreに置き、Swiftは要求されたtransportや保存effectを実行する。coreのsnapshotはopaqueなowned bytesとして保存する。

provider adapterはOpenAI互換、MLXのAPI profile、Anthropic、Geminiを扱う。現在の設定画面は一つの接続先とStage1／Stage2共通のmodelを保存する。通常設定はDB隣の`providers.json`、API keyは独立したKeychain itemに保持する。接続設定の保存だけではLLM requestを送らない。実providerへの送信とmodelごとの受入は別の確認である。

provider requestの開始前にpending claimを保存し、旧responseが取消後の新しい状態へ適用されることを防ぐ。取消はtransport taskと共通coreのcancelへ伝え、app modelは停止が終わるまで新しい生成を開始しない。SwiftのJSON境界は整数の字面を保持し、UInt64のseedを`Double`経由で丸めない。

保存executionのrestoreは読出しだけを行い、中断したprovider requestを自動再送しない。明示resume APIもdurableなローカルeffectだけを進め、provider作業を再開しない。pending provider claimがあるexecutionはresumeを拒否する。この復旧APIの利用者向けUIは未接続である。

### 保存、読出し、保存Scoreの再演奏

保存の意味は[共通保存契約](../persistence/README.ja.md)、[contract.json](../persistence/contract.json)、[論理projection v2](../persistence/reference/logical-projection-v2.sql)に従う。Swiftの物理schemaは独立したv1であり、[bundled SQL](Packages/InkuPersistence/Sources/InkuPersistence/Resources/schema-v1.sql)、[schema export](../persistence/reference/swift-schema-v1.json)、[record mapping](Packages/InkuPersistence/Sources/InkuPersistence/Records.swift)を正本とする。物理schemaの版をportable契約や他hostのschema版と同一視しない。

保存・表示・編集・再演奏の指示書本文は`ddl`だけとする。optionalな`ddl_source_origin`は旧本文を採用した由来であり、第二の本文やauthorityではない。NULLと空文字、未知のstate／fallbackやJSON項目、元の改行と空白を保持する。`source_text`がNULLの作品は表示時に`input`へfallbackできるが、保存値を変更しない。seedは十進TEXT、`at`はUnix epoch millisecondsで保持する。

一つの`InkuDatabase` actorとGRDB `DatabaseQueue`がwriterを所有する。既存DBはwriterを開く前に読み取り専用でschemaを照合し、未知・将来・部分schemaを拒否する。新規DBだけを現行schemaで作り、destructive fallbackを設けない。Server／AndroidのDBを直接開いたり、macOS／iOS間でlive DBを共有したりしない。

作品・lineage node・任意edgeは一つのtransactionで保存する。history主キー衝突を拒否し、render hashは非uniqueとする。`commitEffect`は次snapshot／保存revision、ACK、任意作品・系譜を原子的に確定し、成功ACKをDB commit後に返す。同一effectの同一内容の再試行は保存を重複させず、異なる内容や古い保存revisionはconflictとして拒否する。保存revisionとdocument authorityのrevisionを混同しない。

保存作品の選択・再読出しは保存DDL、Score、canonical SVGをそのまま使い、compileや描画を起動しない。明示的な再演奏は保存Scoreと保存時のpolicy／clip／optionsを検証して共通`renderSaved`を呼び、新しい作品と系譜childを保存する。元の作品は書き換えず、描画contextが欠けている作品へ推測したpolicyを補わない。現在のUIは保存optionsのまま再演奏する。

### backupとrestore

manual backupはSQLite Backup APIでWALを含む整合snapshotを作り、schema／integrity／保存値を検証した単一SQLiteファイルを新規保存先へ公開する。既存backupを上書きしない。DB本体だけのfile copyをbackupとしない。

restoreは生成中のUIから開始できず、hostの実行を停止してから行う。原backupを読み取り専用に保ち、隔離snapshotを検証してBackup APIでactive DBを置き換える。成功後はapp modelのexecutionと選択・表示をresetし、作品を再読出しする。DB backupには作品・系譜・execution／snapshot／ACKが入り、隣接provider JSONとKeychain credentialは含まれない。

自動backup世代管理、FTS、旧Server／Android DBや旧JSONのimportは未実装である。固定Unicode空白集合による旧本文選択helperは、import機能の完成を意味しない。

### rasterとnative表示

[共通raster crate](../core/crates/inku-svg-raster/Cargo.toml)でSVGを描画し、幅・高さ・stride・pixel formatを伴うowned premultiplied RGBA8をSwiftへ返す。SwiftはsRGBの`CGImage`へ機械変換し、pixelの所有をimageの生存期間まで保持する。表示経路でfilterや画材効果を省略しない。rasterは共通のSVGサイズ・寸法・pixel数制限に従い、外部networkやfilesystemからresourceを補わない。

[ArtworkRenderer](Sources/InkuUI/ArtworkRenderer.swift) actorはSVG digest、raster API版、要求寸法と色空間をkeyとする上限付きcacheを持つ。canvasとthumbnailは必要な表示時にrasterを要求する。現行PNG書出しは保存SVGを高さ1024でraster化し、SVG書出しは保存canonical SVGをそのまま出力する。custom寸法・animated exportなどの全export仕様を実装済みとはしない。

### 初期macOS UIと未接続項目

`NavigationSplitView`のrailに作成、ライブラリ、系譜、設定を置く。作成画面は記述／直接DDL、言語、共通catalog／canvas、seed、暴れる設定をapp modelへbindする。初期入力はmodel未接続でも試せる英語の直接DDLである。生成・取消、保存作品の選択と再演奏、read-onlyのDDL／Score、canvasの拡大・移動、最近の作品、library内検索、provider設定、SVG／PNG書出し、画像コピー、manual backup／restoreを接続している。

libraryと最近の作品は通常表示の非trash作品を扱い、処理中の選択を無効化する。検索は読出した作品内のローカル検索であり、DB全件のFTS／pagination UIではない。本文が空の作品は表示名を「無題」とし、保存本文を補わない。

M3で残る機能は系譜graph、favorite／trash操作、plugin／model助言dialog、batch／demo、custom・animated exportと共有cardなどである。系譜画面は未接続であることを明示し、未実装機能を成功した操作として見せない。iPad／iPhone app、camera、share、端末上のlifecycleと実機受入も今後の範囲である。

### buildと確認の境界

clean cloneの必要tool、固定依存、resource生成、generator、artifact、実行手順は[README.ja.md](README.ja.md)を参照する。[build-macos.sh](scripts/build-macos.sh)は既定でrelease RustとRelease appを作り、明示指定でdebugを選べる。[project.yml](project.yml)から生成したXcode projectをgeneric Mac destination、両architecture、`ONLY_ACTIVE_ARCH=NO`でbuildする。ローカルunsigned buildであり、署名、notarization、配布は別作業とする。生成binding、XCFramework、resource、project、build出力は再生成する成果物である。

Mac arm64／x86_64 Rust artifactとSwift link、Universal macOS appのbuildを限定して確認した。Apple Silicon上では直接DDLからのScore／SVG生成、SQLite保存とapp model再作成後の読出し、owned rasterのnative表示、保存canonical SVGの書出しが成立した。初期native画面でも生成画像・最近のthumbnail、library選択、保存Scoreの再演奏による新しい履歴を確認した。UInt64 seedの保持、pixel所有、入力エラー、保存境界は具体的な失敗に対応する小さい確認で扱う。

iOS device／simulatorのRust artifact生成は確認したが、iOS appのbuild・署名・実機受入は完了していない。Intel実機での起動・性能、実provider送信、作者による通常操作とフル機能の受入は別の確認である。CLI確認、Universal build、native画面確認、実機受入を互いの代用とせず、変更が防ぐ具体的な失敗に必要な確認を選ぶ。

隔離した試行はappの`--database`引数で一時DBを選べる。これはDBと隣接provider JSONの保存先を変え、Keychainの保存先は変えない。通常利用と隔離試行の具体的なcommandはREADMEに集約する。

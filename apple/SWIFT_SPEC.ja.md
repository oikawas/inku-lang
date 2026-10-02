# inku Swift 実装仕様

このディレクトリは、macOS先行のnative SwiftUIクライアントとApple向け共通packageのworkspaceである。本書をSwift host固有の仕様正本とし、[SWIFT_SPEC.md](SWIFT_SPEC.md)を対応英語版とする。共有DDL、Score、prompt、authoring authority、pipeline状態遷移、seed、描画の意味は[製品仕様](../SPEC.ja.md)を正本とし、Serverを開発上のprimaryとして同じRust coreへ追随する。Swift側に意味処理を複製しない。

最終更新: 2026-10-03。

binding／protocolの版は同梱Rust coreのversion report、描画層の版はrender metadataと[Serverの層定義](../server/src/inku_server/layer_versions.py)を参照する。本書へ共通engineの版定数を複製しない。Swiftアプリの製品版は正式な版管理に従い、この初期実装では新しい版を採番しない。共有層の版が一致しても、host機能とnative UIの移植が完了したことにはならない。

## 更新ルール

- `SWIFT_SPEC.ja.md`をSwift仕様の正本とする。
- Swift仕様を変更するときは日本語を先に更新し、その意図を保った翻訳・要約として`SWIFT_SPEC.md`を同期する。英語版だけに仕様・要件を追加しない。
- 確定した実装変更と残る範囲は本書の日付付き節へ記し、製品の変更履歴は共通の[CHANGELOG.ja.md](../CHANGELOG.ja.md)／[CHANGELOG.md](../CHANGELOG.md)へ同期して記す。Swift専用CHANGELOGを分けない。
- 共通の意味や保存契約を変更する場合は、それぞれの正本を更新する。本書はSwift hostの適用範囲を説明し、独自の共通仕様を作らない。
- sourceと再現手順を公開文書に記す。生成binary、model、log、credential、端末識別子や非公開の作業記録を追跡対象に含めない。

## 2026-10-03 macOSの制作・全件履歴・周辺機能

### 制作と保存作品の表示

制作画面は左に記述／直接DDLと次に描く条件、保存作品の写生・指示書を置き、右に表示中作品の条件と作品／系譜canvasを置く。入力・次の条件・保存情報をpanelにまとめ、生成／停止は入力のscroll領域の外へ固定する。狭い幅では縦配置へ切り替える。保存作品のmodel、色catalog、用紙、サイズはcompactな要約と詳細popoverで読み、次の入力条件と区別する。画面上の記述caption、縦書き／横書き、配置、pan／zoom、プレゼンテーションは表示合成であり、保存SVGを変更しない。「用紙に合わせる」はzoomと移動を初期位置へ戻す。

制作画面で登録済みのserviceと描画modelを選択する。設定したmodelと明示取得したmodel一覧を表示し、一覧取得は利用者のbutton操作だけで始める。選択した次のmodelは記述解釈と構造化の両段へ渡し、設定画面の保存defaultや親作品のmodelを書き換えない。新しい生成要求・推敲・比較の初期選択は次のmodelを使い、開始済みbatch／demoのmodelはそのsnapshotへ固定する。未接続時はモデル設定へ案内する。

macOS menuはactive sceneの操作可否を使う。⌘Nは新規制作、⌘Oは画面buttonと共通のDDL file読込、⌘,は設定、⌘1〜4は制作／library／系譜／batch・demo、⇧⌘Eは書出し、⇧⌘Cは画像copy。既存の⌘Return生成、Escape停止、⇧⌘Fプレゼンテーションと併用する。生成・自動実行・読込・dialog・presentationの状態に合わせて対象操作を無効化し、menu経由で別の書込みを割り込ませない。設定はsystem sidebarとgrouped formを使い、モデル設定への導線は該当categoryを開く。

同梱の歳時記、13色catalog、11用紙と7語のMacro／plugin定義はServer sourceから生成し、共通Rustで定義とdigest lockを解決する。pluginの有効切替は新作品へ適用し、保存作品の定義を置き換えない。DDL packageのimportは`inku.ddl-export.v1`の本文・付属定義・lock・整数表現を検証し、次の新作品へ添える。4MiB／64定義を超える入力や不完全な定義は拒否し、途中結果を採用しない。

DDLのdraft確認は読出しだけとし、変更確定を共通coreのrevision／authorityへ渡す。最初の確定DDL変更後は記述の権限へ戻さず、新しい作品と系譜childを保存する。補完は候補の表示と採用・却下を分け、採用前の本文を書き換えない。保存Scoreの再演奏では保存条件か明示した次の条件を使用し、元作品のScore／SVGを保持する。保存欄`ddl_source_origin`は従来どおりNULLまたは`legacy_expanded`だけであり、編集authorityをこの欄へ保存しない。

### 履歴・library・系譜

履歴はSQLite全件を対象とする20件page、libraryは独立した30件pageである。最新100件のapp内一覧を検索や作品移動の母集団にしない。最新／新しい／古い／最古への移動、全文記述・全文hash・末尾4桁の検索、star・推敲・export markのAND絞込、thumbnail／listと時系列／系譜groupの独立選択を提供する。

comment、mark、trash／復元、明示した完全削除、複数選択、系譜graph／pathをSQLiteへ接続する。完全削除後は作品本文を消し、nodeのidentity、root、日時と親子関係をtombstoneとして保持する。ACL、group利用者やServerの共有権限は追加しない。

履歴の世代はServerと同じくrootを1とし、primary parentのedgeごとに1加算する。削除済みの祖先も数え、nodeのない作品は独立作品と表示する。初期表示は世代とmodel、保存済みの表示項目は保持する。世代をvariationの種類や幅で代用しない。libraryでは表示中の作品と複数選択のcheckbox、系譜では表示作品と範囲を決めるfocusを区別する。記述のないDDL作品は保存DDLの先頭行を表示名へ使い、保存本文を補わない。hash、comment、mark、親子への移動はcardとmenuから操作できる。

Swift物理schemaはv2で、v1の6tableにlocal annotation、奥書、未読語を追加した9table構成とする。正本は[bundled migration](Packages/InkuPersistence/Sources/InkuPersistence/Resources/migration-v2.sql)と[schema export](../persistence/reference/swift-schema-v2.json)。既知の完全なv1だけを原子的に移行し、作品・snapshot・ACKの値を保持する。未知schemaは引き続き拒否する。backup／restoreは全9tableを対象とし、v1 backupは隔離snapshotをv2へ移行してから復元する。Server／Android DBや旧JSONのimportは含めない。

### 比較・推敲・奥書と自動実行

catalog／model比較は開始時の作品・Score・設定を固定する。候補は採用前に通常履歴／系譜へ保存せず、選択した候補だけをidempotentに保存する。選べる候補の総数を4に制限せず、Swiftでは逐次生成する。停止とdialogのcloseは処理の終了を待ち、遅れて届いた候補を混入させない。

model助言、random／Vision推敲、奥書は通常生成と同じprovider transportとrate予算を使う。記述の編集採用と新variation生成を分け、DDL権限の作品へ記述を上書きしない。中間の推敲作品は`lineage_only`として保持する。奥書は生成した原文と採用本文を別に保存し、DB backupへ含める。

batchは空行を除く最大1000入力を受け、元の行番号とmodel、provider、定義、seed等を開始時に固定する。一巡後の失敗行だけを既定0／最大5回再実行する。明示した再開でも固定条件を保持する。再起動時に実行結果が不明な行は利用者の再試行／省略選択を待ち、自動再送しない。demoは開始時の設定を固定し、生成記述と作品を表示する。保存は既定で無効、間隔1〜3600秒、実行時間60〜86400秒で、停止・満了後の処理を継続しない。

### 辞書・表示・接続設定

日本語はServerと同じSudachi small辞書、英語は同じCMUdictの読みを使用し、Rustの薄い境界で音数・音節を数える。辞書・設定・license・hashを[resource manifest](scripts/description-meter-resources.json)で固定し、build時に生成する。Python runtimeはアプリへ含めない。4000文字までの判定を300ms debounceし、未読語の頻度・日時・文脈をSQLiteへ保存する。判定を無効にした場合は文字数／行数を表示する。

日本語／英語、theme、5段階text倍率、full／simple／custom、caption、履歴情報最大3項目、tooltip、mascot、clipboard、描画制限、export template／保存先をlocal設定とする。複数APIサービスの設定、用途共通の描画model、明示したmodel一覧取得とRPM／入力TPM／RPDを提供する。通常設定は隣接JSON、API keyはKeychainであり、接続設定を保存するだけでは生成しない。

自動backupは既定で無効であり、アプリ起動中に生成・復元・自動実行の終了を待つ。検証済みbackupの成功後にmanifestを確定し、アプリ自身が記録した世代だけを削除する。手動backupを自動世代管理へ含めない。任意の生成結果logは実際に保存した作品だけを記録し、古い作品を開くだけでは作らない。

### Personal ChatGPT

Personal ChatGPTは通常のAPI key接続と別に扱い、既定は無効とする。利用者が明示して有効化・接続し、提供されたmodelを描画modelとして選ぶ。Stage1／Stage2は同じ描画modelを使用する。本人の接続を複数保存しても、作品DBは一つのローカルlibraryであり、multi-user機能を追加しない。

本人認証は127.0.0.1の一時listenerと`/auth/callback`、state／nonce／PKCE、発行済みclient ID、検証したidentityと許可scopeを使用する。資格情報は最大1MiBのAES-GCM暗号化vaultへ原子的に保存し、device-localの32byte keyをKeychainへ置く。平文token fallbackを持たず、SQLite backupに資格情報を含めない。初期無効状態で認証や推論を開始しない。

開始時にprofile ID／generationを固定し、queued要求やbatch／demoの再開で接続を付け替えない。接続解除・切替・quota後は古いrefreshや遅延応答を採用せず、別providerへ暗黙に切り替えない。共有Rustの記述解釈、写生、自動配色、DDL補完だけをResponses／SSEへ接続する。Vision推敲、奥書、demo用記述、model検査はこの接続では未対応として表示する。実本人OAuth、model取得、推論の受入はoffline確認と分ける。

### 保存作品の書出しとnative raster

[InkuExport](Packages/InkuExport/Package.swift)はDisplay／Editable／Compat／Live SVG、PNG、定義付きDDL、共有card、review／AI contact sheet、APNG／GIFを扱う。Displayは保存canonical SVGをそのまま使用し、ほかのSVGは保存Scoreと固定contextを共通coreへ渡す。PNGはY軸1080／2160／4320、custom 64〜12000pxと用紙比率を保持する。大きい画像は元のsceneを用いるregion rasterで分割し、filter／clipを落とさない。静止画は144,000,000pixel、animationは合計600,000,000pixelを上限とし、取消し後の結果を公開しない。

単作品animationのlayer進行／restart・reverse・once、複数作品のcut・crossfade・fade_white・slide、保存日時順と明示系譜path順を区別する。日本語文字はServerと同じNoto Serif JPをlicenseと共に同梱する。保存先folderのbookmarkとPNG templateを保持し、複数出力は新規folderへ保存する。Finder表示とOS共有へ接続する。

書出し対象は開いている画面で決める。制作は表示中の保存作品、libraryはcheckboxの選択作品（未選択なら表示作品）、系譜はfocusへ至るpathをsnapshotとして渡す。別画面のcheckboxを制作や系譜の対象へ混ぜない。未保存previewは保存作品の書出しへ含めない。書出しdialogもDDL作品の表示名をlibraryと揃える。

共通rasterにimmutableなprepared sceneを追加し、SVG parse結果を解像度間とexport tile間で再利用する。native rendererはscene推定cost16MiB／8件、image64MiB／256件を上限とし、保存SVGや画材効果を変更しない。表示はRetina scale、120ms resize debounce、要求寸法の8Mpixel枠に合わせる。限定したRelease計測では6000 pathの4解像度で準備時間込み約20%短縮し、pencilの重いfilterは改善が小さかった。全作品・全処理の同じ改善率を保証しない。

### 確認範囲

実coreと一時DBによるauthoring、比較候補の明示保存／取消し、batchの固定条件と不明行、保存pluginの固定、prepared scene／image cacheの限定確認は成功した。辞書、library、SQLite移行・backup、exportとtileの境界も具体的な失敗に対応する確認で扱った。Personal接続のidentity、SSE、loopback、refresh取消し・quota・model解決はsynthetic署名とmock transportで確認し、実本人認証へ読み替えない。

更新したunsigned Universal appは両CPUでlinkし、最低OS14を保持した。Apple Silicon／macOS27.0.1の一時DBでDDL生成、編集child、libraryのcomment／star、trash／復元、restart後の保持、日英切替、親子の系譜と全体表示、Stringの正しい改訂番号、複数選択2作品のPNG2160書出しを実画面で確認した。出力2fileは両方2160×2160で、画像の質感も視覚確認した。起動時のページサイズ再帰、シートの空選択、Foundationの保存option組合せによる終了を修正した。作者の通常利用、他exportのnative・性能、実provider／OAuth、Intel／macOS14実機、署名・配布、iOS app／cameraの受入は残る。

追加の限定確認では、制作で選んだmodelが実際のrequest両段へ反映され、保存default・開始済みtemplateが変わらず、provider呼出し0件であることを確認した。SQLiteの世代projectionはroot・child・欠落・削除祖先の1件を確認した。nativeでは1320×880と標準tileの1281×733で固定生成button・canvas・履歴、世代1／2、設定／移動／新規／読込取消し、model設定categoryへの導線、系譜focusと表示作品の分離、library2件と制作1件の書出し対象を確認した。小さい幅の全配置、VoiceOver、作者のデザイン受入をこの代表確認へ読み替えない。

## 2026-10-02 macOS向けの共有Rust・standalone基盤（当時の記録）

以下は初期実装時点の記録であり、現在の接続機能は上の日付付き節を優先する。

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

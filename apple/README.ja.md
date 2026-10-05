# Appleクライアント

macOS先行のSwiftUIクライアントです。DDL、Score、prompt、状態遷移、seed、SVG生成とrasterはServer／Androidと同じRust coreを使います。Swift hostがnetwork、Keychain、SQLite、OS lifecycleとnative表示を担当します。実行時にinku ServerやPython runtimeは不要です。macOSにcamera機能はありません。

Swift固有の仕様正本は[SWIFT_SPEC.ja.md](SWIFT_SPEC.ja.md)、対応英語版は[SWIFT_SPEC.md](SWIFT_SPEC.md)です。Androidと同じく、日本語の仕様を先に更新し、英語を同期します。製品の変更履歴はrepository rootの[CHANGELOG.ja.md](../CHANGELOG.ja.md)／[CHANGELOG.md](../CHANGELOG.md)へ日付付きで追記し、確定した仕様と未実装範囲はSwift SPECへ記します。共有DDL／Score／renderの意味はroot SPECを正本とします。

## 現在の範囲

M1のSwift／Rust基盤、M2のstandalone host／SQLite保存境界に続き、macOSの制作・全件履歴／library・系譜、DDL編集／補完承認、plugin／歳時記、比較／助言／奥書、batch／demo、表示／接続設定、全export方式を接続しています。保存作品の条件を次の入力条件と分け、通常表示と明示した再演奏を区別します。詳細と確認の範囲は[Swift SPEC](SWIFT_SPEC.ja.md)の2026-10-04の現行Server追随節を参照してください。

限定した確認で、DDL→Score／SVG→SQLite保存→アプリモデルの再作成後の読出し、native CGImage生成、保存canonical SVGの書出しが成立しています。Swift／Rust境界ではowned pixel buffer、入力エラーとUInt64のseed保持を確認しています。macOSのarm64／x86_64 Rust sliceとx86_64 Swift executableのlink、iOS device／simulatorのRust artifact生成も確認しています。Intel実機での性能・起動、実providerへのLLM送信、作者による通常画面操作の受入は別の確認です。

更新したUniversal appの隔離DBで、DDL生成→編集child→libraryのcomment／star→trash／復元→restart、日英切替と系譜表示、複数選択2作品のPNG2160保存を確認しています。機能のsource接続、限定したoffline確認、native操作、作者の通常利用の受入は別に記録します。旧Server／Android物理DBのimport、実provider／OAuth、他exportのnative・性能、Intel／macOS14実機は未完了です。廃止済みhistory.json移行utilityの配列は現行Webの復元形式ではありません。iOSは共通packageと初期Rust artifactまでで、最新APIのartifact再生成、iPad／iPhone app、camera、shareと実機受入は未完了です。

Personal ChatGPTは設定の専用画面で明示して有効化・接続し、提供されたmodelを描画用に選びます。通常のAPI key接続とは別で、初期状態は無効です。発行済みclient IDと本人の接続同意が必要で、実本人認証・model取得・推論は未受入です。記述、写生、自動配色、構図の読み、DDL補完に対応し、Vision推敲・奥書等の未対応用途は画面で説明します。詳細は[Swift仕様](SWIFT_SPEC.ja.md#personal-chatgpt)を参照してください。

今回の現行Server追随では、Score 0.19／描画エンジン73の共通core、Stage 1から構図読みへの保持fallback清掃、作品別のimmutable表示snapshotを取り込んでいます。具体差分のRust5 selector、保存／再作成／cancelのHost1 caseと最新appの型検査が成功しています。最終native操作・CLI同入力比較・実providerの確認は別の証拠を要し、iOS／Intel／macOS14実機の完成を意味しません。

macOSの版情報・概念説明・用語表・作者情報は、画面上部のアプリメニュー→「inkuについて」で開きます。設定一覧には表示しません。専用ウインドウを閉じても、同じメニューから再度開けます。iOSでは設定内の「inkuについて」を使います。

## macOS版の導入

配布版は[GitHub Releases](https://github.com/oikawas/inku-lang/releases)の`Inku-macOS-<版>.dmg`です。同じ場所の`.sha256`と照合してから開いてください。

```sh
shasum -a 256 Inku-macOS-1.0.0.dmg
```

dmgを開き、Inkuを「アプリケーション」へドラッグします。macOS 14以降のApple SiliconとIntelで動くUniversalアプリで、Developer IDで署名し、Appleの公証を受けています。Intel実機とmacOS 14実機での動作は未確認です。

最初に、描画に使うモデルの接続先へAPIキーを入れてください。キーが無いと生成ボタンの上に案内が出て、「接続設定を開く」から設定できます。キーはログインキーチェーン（service `app.inku.provider-credentials`）に保存し、ファイルには書きません。

作品と設定は`~/Library/Application Support/app.inku.macos/`に保存します。作品のSQLite（`inku.sqlite`）、接続設定（`providers.json`）、表示と選択の設定（`interface.json`）、デモ設定、バッチの記録、有効にした場合の`drawing-logs/`があります。自動更新はありません。新しい版はアプリを終了し、新しいdmgのInkuで置き換えてください。データはそのまま残り、設定ファイルは版を上げても項目ごとに読み込みます。削除する場合はアプリ、上のフォルダ、キーチェーンの項目を消します。

アプリの版は「inkuについて」に、対応するServerの版と並べて表示します。inkuはMITライセンスです。同梱した第三者のソフトウェア・辞書・フォントのライセンスは「inkuについて」の「ライセンス」で読めます。

## 描画が失敗したとき

左の操作列の「描画ログ」（またはメニューの⇧⌘L）を開き、失敗した記述の実行を選んでください。日時、使ったmodel、失敗した段階、再試行やfallbackの経過を確認できます。新しい通常APIの実行には通信のOS error codeやHTTP拒否理由も残ります。古い記録にない詳細は追加せず、未記録と表示します。ログを開いても生成・再送信は行いません。

設定→制作の「生成結果のログを保存」を有効にすると、成功・失敗・停止の累積JSONもDBと同じdirectoryの `drawing-logs/` に保存します。切ってもSQLiteの実行記録は「描画ログ」で読めます。通常logに通信本文、APIキー、接続先のpath／queryやheadersは含めません。詳しい本文保存は開発者用の明示設定に限ります。

描画logの読込に失敗した場合は原因が残り、「もう一度読み込む」で再取得、「エラーを閉じる」で表示だけを閉じます。以前に読めた記録は保持します。まだ読み込んでいない状態を「記録なし」と推定せず、読出し操作で描画や再送信を始めません。

## 対応OSとbuild環境

最低OSはmacOS 14／iOS 17です。SDKの版は最低OSとは別です。確認した環境はXcode 27.0／Swift 6.4、Rust 1.95.0、XcodeGen 2.46.0です。Swift packageはtools 6.1、projectはXcodeGen 2.44.0以上を要求します。

buildにはmacOS、XcodeのCLI tools、XcodeGen、Python 3.11以上、Node.js 22.13以上、uv、公式rustupが必要です。Node.jsの[`stripTypeScriptTypes`](https://nodejs.org/download/release/v22.14.0/docs/api/module.html#modulestriptypescripttypescode-options)は明示したreference更新でWeb文言・用紙情報・歳時記previewを抽出します。通常buildはreview済み同梱snapshotを使い、Pythonとuvは固定辞書の準備にも使います。いずれのruntimeもアプリへ組み込みません。初回はCargo、SwiftPMとServerのuv.lock依存を取得するnetwork接続が必要です。

主な固定依存はUniFFI 0.32.0、GRDB 7.11.1です。Rustのtoolchain／依存は`core/rust-toolchain.toml`と`core/Cargo.lock`、GRDBは`Packages/InkuPersistence/Package.swift`とSwiftPMの解決記録で管理します。UniFFI generatorは同じcheckoutのCargo.lockからbuildし、そのRust archiveのmetadataを読みます。

## clean cloneからのmacOS build

以下はproduct repository rootから実行します。必要なtoolとXcodeを用意した後、固定Rust toolchainとMac targetを導入してください。scriptはtoolchain導入やXcode／Apple accountの設定変更を自動実行しません。

```sh
rustup toolchain install 1.95.0 --profile minimal --component rustfmt --component clippy
rustup target add --toolchain 1.95.0 aarch64-apple-darwin x86_64-apple-darwin
apple/scripts/build-macos.sh Release
```

`build-macos.sh`は必要toolの確認後、resource／core／appの変更前に[停止helper](scripts/stop-existing-macos.py)を実行します。現在のユーザーが所有する既知のInku bundle IDと実行fileを検証し、PIDのidentityを再確認してSIGKILLで停止します。最大10秒で停止を確認できなければbuildを中止し、結果は`apple/build/macOS/stop-existing.json`へ記録します。未知のInku類似processは検証errorとして扱い、signalを送信しません。

通常のbuildはcommit済みのreview済みreference／default／catalog snapshotを使い、`uv sync --project server --frozen`で固定したbuild用依存を用意します。[辞書準備script](scripts/prepare-meter-resources.py)がSudachi small（約113MiB）、読み設定とCMUdictをhash検証し、licenseと共にInkuHost resourceへコピーします。共通RustとSwift binding／XCFrameworkを生成し、`project.yml`からXcode projectを作ってmacOS appをbuildします。generic Mac destination、`ARCHS=arm64 x86_64`、`ONLY_ACTIVE_ARCH=NO`を指定し、最後に両sliceの存在を検査します。Apple account、Team、証明書を使わないunsigned local buildです。署名・公証した配布物は下の「配布物の作成」で作ります。

Rust 1.95のmacOS host proc-macro stripによる[LINKEDIT alignment問題](https://github.com/rust-lang/rust/issues/157750)を避けるため、releaseのhost build dependencyだけstripを無効にします。target Rust archiveの最適化とstripは維持します。cache削除やtoolchain変更は不要です。

defaultはRelease appとrelease Rustです。XcodeのDebug appを選んでも、Rustは明示指定しない限りreleaseのままです。両方をdebugにする場合は次を使います。

```sh
INKU_APPLE_PROFILE=debug apple/scripts/build-macos.sh Debug
```

Release appは`apple/build/macOS/DerivedData/Build/Products/Release/Inku.app`に生成されます。Xcodeで開く場合は生成後の`apple/Inku.xcodeproj`を使います。build出力、Swift bindingとXCFrameworkは再生成する成果物です。同梱reference／provider default／model catalogの3JSONはreviewしてcommitするsnapshotで、通常のrebuildでは更新しません。

別のServer sourceからreferenceを更新する場合だけ、絶対pathを明示します。source commitとfileのSHA-256、TipsのJA/EN、default／catalog差分をreviewしてから採用してください。

```sh
INKU_APPLE_REFERENCE_ROOT=/absolute/path/to/server-checkout apple/scripts/build-macos.sh Release
```

```sh
open apple/build/macOS/DerivedData/Build/Products/Release/Inku.app
```

### 配布物の作成

配布用のdmgは次で作ります。Universal Release build、第三者通知の照合、Developer ID署名（Hardened Runtime）、dmgの作成と署名、公証とstaple、Gatekeeperの確認、SHA-256とRelease添付用の第三者通知テキストの作成までを行い、`apple/build/release/Inku-<版>-<build>/`へ出力します。版は`apple/VERSION`と`apple/BUILD_NUMBER`です。署名identityと公証のkeychain profileは引数か環境変数（`INKU_MACOS_SIGN_IDENTITY`／`INKU_MACOS_NOTARY_PROFILE`）で渡します。

```sh
apple/scripts/package-macos-release.sh --identity "Developer ID Application: <name> (<team>)" --notary-profile <profile>
```

第三者通知は`apple/scripts/build-macos-notices.py`で作るreview済みsnapshotです。依存を変えたら再生成し、release scriptは古いsnapshotを`--check`で止めます。

### Dockから同じアプリを起動する

既存のincu画像からmacOS用アイコンを生成し、appに含めます。固定先へinstallして使う場合は次を実行します。

```sh
apple/scripts/build-macos.sh Release --install
open ~/Applications/Inku.app
```

最初にこの固定appをDockへ登録すれば、その後も同じ登録を使えます。rebuildは上記helperで検証済みのInkuを停止してから進みます。installは既存app directoryを保持して中身を更新し、bundle IDとDB指定を引き継ぎます。installer単独の実行は実行中appや未知の既存appを拒否します。通常のbuildだけではinstall先を更新しません。

build済みappを既存の試行DBへ接続してinstallする場合は、[install helper](scripts/install-macos.py)へDBの絶対pathを渡します。

```sh
python3 apple/scripts/install-macos.py \
  --app apple/build/macOS/DerivedData/Build/Products/Release/Inku.app \
  --database /absolute/path/to/inku.sqlite
```

DBのcopyや移動は行いません。指定はbundleの`InkuDatabasePath`へ保持し、Dock起動でも同じDBを開きます。明示した`--database`起動はbundle指定より優先します。

## 通常利用と隔離した試行

バッチでは1行に1作品分の記述を入力し、幅いっぱいの履歴、前回の再開情報、次の描画条件、新しいバッチの操作の順に使います。新規バッチのDDL入力はありません。モデルの「変更」はStage 1/2共通のサービス別card dialogを開き、仮選択して「決定」で適用します。取消・×は元の選択を保ちます。登録済みで使用中のLLMモデルが必要で、登録外の既定値は選択待ちになります。色の「変更」は先頭の「記述から自動選択」かカタログの10色見本から選び、決定または×で適用、キャンセルで破棄します。ランダムの選択肢はありません。

写生の「なし／あり」と暴れるの「切／入」、キャンバスを確認して「新しいバッチを描く」を押します。写生は制作とは独立し、指定写生は新バッチへ引き継ぎません。seedは条件欄の「詳細」にあります。指示書の言語は記述の文字から自動で決まります。開始操作は条件直後に置き、狭い幅では作品領域まで縦へscrollできます。空行も元の行番号に含み、長い行は横へscrollできます。行番号は入力枠内だけに表示します。

履歴からの明示復元は入力欄だけを置き換えます。中断した記録は残件と開始時条件を確認して再開し、完成済み作品を描き直しません。処理中の行と表示中の成功作品の番号を区別し、結果不明の行は履歴を確認して再試行／省略を選んでください。バッチの観測作品がない場合は現在選択中の保存作品を右に残します。

バッチ中も記述／バッチtab、画面移動、履歴帯、保存作品の生成情報、設定tabを使えます。履歴や過去の成功行を選ぶと表示を固定し、次の行の完了や画面へ戻る操作ではその選択を変えません。新規バッチ／再開を明示すると最新結果へ追従します。キャンバス下のスターで、表示中の保存作品へスターを付ける／外す操作もできます。押した時の作品へ保存し、次の成功作品へ対象を移しません。新規描画・編集確定・取込・スター以外の作品変更・バッチ条件は処理中に変更できません。通常設定の保存は次回用として行い、APIキー、個人接続、plugin、DB復元・backupと結果file logは処理終了後に変更します。

バッチの失敗行には、記録された処理段階・原因・試行番号・診断codeを残します。「描画ログ」や生成情報で、今後の記録はtoken計数と生成要求など失敗した操作を区別できます。旧記録の操作は不明とし、応答を確認できなかった通信を未送信と断定しません。試行ごとに通信sessionを作り直しますが、接続断の根本原因や解消は実行確認が必要です。

バッチ中の操作開放と接続断対策を含むRelease Universal版は、両CPU／最低macOS14のbuildと固定アプリ更新、通常起動まで確認しました。同じDB指定・incuアイコン・Dock登録を保持しています。試験実行、native画面の操作受入、実providerでの接続断解消は未確認です。詳細は[Swift SPEC](SWIFT_SPEC.ja.md)の2026-10-05のUniversal build・接続断診断・バッチ中閲覧節を参照してください。

初期入力は英語の直接DDLです。モデル接続なしで生成を試せます。OpenAI API Platform、Claude API、Gemini API、NVIDIA NIM、Ollama、Ollama Cloudを標準接続として用意し、旧設定にも不足分を一度だけ追加します。既存のURL・モデル選択を保持し、削除した標準接続を再起動で復活させません。

記述から生成する場合は「設定」→「モデル設定」でサービスcardを選びます。「モデル選択」で検索・用途・使用設定を編集し、保存してください。取消しでは編集内容を保存しません。「モデルリスト取得」は現在の接続先へ明示取得して新しい候補を保存する操作です。未保存の編集がある間は取得できません。名前変更・サービスメモ・サービス追加は別sheetを開きます。

必要なAPIキーは「接続設定」を開いて作者が入力し、隣の「保存」でKeychainへ保存します。設定済みキーは表示せず、変更する場合は「削除…」で確認後に新しいキーを保存します。URLとレート制限はそれぞれの「保存」、通常の描画modelとtoken上限は「描画の既定値」→「既定値を保存」で確定します。Ollamaの初期URLはこのMacの`http://localhost:11434/v1`なので、別のホストを使う場合は変更してください。複数のAPIサービスを登録でき、Stage1／Stage2は共通の描画modelを使用します。起動・標準接続の追加・接続設定の保存だけではLLM requestを送りません。モデルを非使用にしても既存参照と作品を保持しますが、次の記述描画には使用中のLLMモデルを選んでください。

制作画面の「次の生成条件」で次に使うservice／modelを選びます。この選択は設定の保存defaultや開始済みbatch／demoを変えません。条件は要約と詳細popover、保存情報は「表示中作品の生成情報」へ分け、生成／停止buttonは入力のscroll領域の外にあります。canvas下の詞書、星／印、hash、再現比較、生成情報、書出し、clipboard、presentationは表示中作品の操作です。その下の写生と指示書から、保存作品の写生を編集し、DDLを編集し、指示書のまま描き直せます。DDLは「編集」から独立draftを開き、取消しでは表示作品を変更しません。⌘Nで新規、⌘OでDDL読込、⌘,で設定、⌘1〜4で画面移動、⇧⌘Eで書出しを開けます。libraryのcheckboxと表示作品を区別し、制作からの書出しは表示中の保存作品を使います。

「生成情報」は開いた保存作品を固定し、「詳細」「プロンプト」「Score (JSON)」を切り替えます。詳細のmodel／seed／色／canvas／SVG構造量／hash／版／batch元行／commentと実測記録、promptの開閉・コピー、行番号付きScoreとコピーは読出しです。旧未記録と、当該段を送っていない記録、読込中・取得失敗を区別し、現在の設定で補いません。nativeで保存していないStage 1 promptの基底digestも「記録なし」です。tabや再読込で制作選択や作品を変えず、providerを呼びません。

presentationは開いた保存作品を独立した履歴で閲覧し、戻った制作の入力と選択を保ちます。hashコピーは先頭のdomain prefixを外したdigest全体です。未読語台帳も再読込の失敗で以前の一覧を消さず、原因を残します。

ライブラリは作品をpreviewしても制作中の入力を保持します。「制作で開く」で明示的に切り替え、previewは閉じて一覧へ戻れます。系譜は枝の開閉と全体図を使用でき、全体図を閉じると通常の閲覧位置へ戻ります。canvasのマウスホイールで拡縮し、100%以下で中央へ戻します。用紙は形と意図を見て次の条件へ選び、通常の歳時記は参照のみです。左の操作列のツールチップ切替と設定の描画制限値を使用できます。制限値は編集後に「変更を保存」を押すと新作品へ適用します。

制作とモデル設定で「モデルの適性・用途」を開くと、Serverの登録評価・用途・commentと接続先から取得した情報を別々に読めます。未登録のservice／modelは推測で評価しません。処理中は段階・呼出しmodel・試行回数・経過時間を表示し、未取得token数は「記録なし」とします。停止で時間が確定し、新規制作で前の進行表示を消します。

制作の「モデルの実測記録」は通常API／Personal ChatGPTの実呼出し時間と返されたtoken数を、下絵・構図・補完に分けて表示します。保存作品や再演奏比較では保存時の記録を読み、明示0と未取得を区別します。通信本文の保存が必要な開発時だけ、`INKU_DEVELOPER_MODE=1`を付けてアプリを起動し、設定の「生成時の送受信を記録」を有効にしてください。既定は無効です。開発者向けの折りたたみ欄から端末内の本文を読めます。送信前の保存に失敗した場合は要求を出さず、途中応答は不完全と表示し、接続先・header・認証情報は記録しません。[Swift仕様](SWIFT_SPEC.ja.md)に保存境界を記します。

保存作品の操作から「記述を変える」「写生なし／ありで描き直す」を開くと、その作品を親とする新しい子を描けます。直接DDLや確定DDL編集の作品は記述へ戻せません。色カタログは色名・HEX・説明を見て次の生成条件へ確定します。DDLは標準panelまたは1つのfileのwindow dropから読み込み、まだ保存されていない制作draftへ反映します。

「描画パラメータの編集」では配置・読み取りの1案／4案と言葉によるタッチ1案を比較し、選んだ候補だけを子として保存します。候補の準備・拡大だけでは表示作品や通常履歴を変えません。新しい変奏は選べず、過去の保存作品と来歴は引き続き読めます。停止・破棄と採用を区別し、model設定へ移る場合は未保存候補を先に採用または破棄してください。DDL／配置のモデルchooserで決定するとStage 2既定だけを保存し、親のStage 1来歴を保持します。

作品menuの記述・写生・model再解釈は、保存時のoriginと確定状態で使用可否を決めます。直接DDLでは表示せず、編集DDLで記述がロックされた場合は理由を表示します。保存条件の読込中や未記録を、記述作品と推定しません。専用DDL editorの取消しは保存親を変更せず、確定した新しい子だけを保存します。空記述のDDL作品は表示名にDDLの先頭行を使い、記述本文を補いません。

AI助言／自動推敲は対象作品を固定し、画像を扱える登録modelを選択して使います。AIへ渡す方針はcounterの160までです。保存世代の「観察」は表示だけで、「この作品から再開」を明示すると保存条件を読んで次の親を変更します。読込失敗では元の親を保持します。奥書は起点から表示作品までの固定経路と世代数を確認して生成し、成功時に追記して保存されます。既存本文を編集して上書きしません。model比較は使用中LLMを4件まで選択します。通常の描画model dialogは思考表示もdraftとして確定・取消しできますが、この設定をproviderの推論制御としては使用していません。

書出しdialogで形式・サイズ・card／animationを変更しても「今回だけ」の条件です。defaultとPNG templateは設定画面で保存してください。clipboardも設定で画像／cardと高さ256〜4096px・64px刻みを選べます。Tipsは同梱のServer日英正本を使用し、星・印・hash・系譜の各buttonに操作別の説明を表示します。書き出し印はlocalの印で、グループ共有を実行するものではありません。

demoは開始時の条件を固定し、記述を作るmodelと描画model、生成記述・完成指示書、経過／残り／次回待ちを分けて表示します。履歴保存・ファイル保存・現在作品の明示保存を使い分けます。表示tokenは記録された描画分で、記述生成のtokenは未記録です。実行期限は次の作品の開始を止め、進行中処理にはcoreの期限を使います。停止後は履歴で保存結果を確認できます。旧不正snapshotの自動修復・自動再送は行いません。

モデル設定の「レート制限」は、毎分の要求数（RPM）、毎分の入力トークン数（TPM）、日次の要求数（RPD）を設定します。隣の説明buttonで対象や日次の切替時刻を読めます。0は上限なしで、標準Geminiの未設定時は30／16,000／14,400です。契約プランに合わせ、0〜1,000,000,000の整数を設定してください。描画と再試行の予約はSQLiteへ保存し、再起動や古い作品backupの復元で当日の上限・待機時間をリセットしません。待機は生成の試行期限へ含まれます。

作品のDBはアプリのApplication Supportに、通常のprovider設定はDBと同じdirectoryの`providers.json`に保存します。API keyはKeychainの別itemです。SQLite backupは作品・系譜・execution／ACK／snapshot、comment／mark、奥書、未読語と送信予算を含むDBの整合したcopyであり、隣接設定JSONやKeychainのbackupではありません。

自動backupの設定には保存先、最新成功、次回予定、保持世代と各日時／容量を表示します。「状態を再読込」は保存済み状態を読む操作で、新backupを作りません。読込失敗やbackup失敗の原因を保持し、作品復元と状態確認を区別します。作品DBの復元成功後はlibrary previewを閉じ、demo／batchの観測作品と制作・プレゼンテーションの一時作品を破棄して、library・世代一覧・選択位置を復元DBから読み直します。

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

Swift packageを直接buildする場合は、commit済みreferenceに加えてRust artifactと固定辞書を先に用意してください。reference更新は通常の準備に含めません。

```sh
uv sync --project server --frozen
python3 apple/scripts/prepare-meter-resources.py
```

UI差分の限定確認は`--library-browsing-only`、`--lineage-presentation-only`、`--ddl-editor-cancel-only`、`--drawing-limits-editing-only`、`--canvas-wheel-only`です。隔離DBでpreview・コメント・系譜復帰・取消・制限値の保存を確認し、ホイールは倍率と位置の計算だけを確認します。nativeの実イベントや見た目は別に確認してください。

追加のAppCheck選択は`--provider-progress-only`と`--model-guidance-only`です。前者はmock／共通Rustで再試行の表示・時計・停止と遅いcallback、後者は生成したServer評価資料と一時DBで適性・未登録境界・選択とsnapshotの保持を確認します。実providerへの呼出しは行いません。

構図への追随は`--composition-host-only`と`--composition-progress-only`で確認します。hostは実Rust／mock／一時DBで構図要求・固定Stage 1 modelと上限・schema・保存・有限retry／fallback・旧設定／保存Score再生を、progressは段階時計・再試行・日英表示・prompt履歴の分離・停止を確認します。`--composition-personal-plan-gate-only`は未接続の有効UUIDと空の一時vaultでPersonal ChatGPTの最終routing拒否だけを確認し、実HTTP／OAuth／Keychainを使いません。

送信予算の限定確認は`swift test --package-path apple/Packages/InkuHost --filter ProviderRateLimitChecks/testDurableAdmissionDeadlineAndRetryAccounting`です。一時SQLite、模擬HTTPと時計で同時接続の予約、期限・日次・入力上限、旧記録の取込とbackup／restoreを扱い、実provider、認証情報、通常作品DBを使いません。

限定したCLI確認は、artifactと固定辞書の準備後の`apple/scripts/check-core.sh`と`swift run --package-path apple InkuAppCheck`です。`--authoring-only`、`--comparison-only`、`--automation-only`、`--plugin-only`、`--model-selection-only`、`--work-edit-only`、`--replay-comparison-only`、`--auxiliary-provenance-only`、`--raster-only <SVG path>`は具体差分に必要なものだけを選びます。`--model-selection-only`は保存default・開始時snapshotの分離、`--work-edit-only`は保存親の編集・写生・DDL authority・取消し、`--replay-comparison-only`はprovider不要の再現比較の保存／表示不変、`--auxiliary-provenance-only`はmockによる世代別Vision／random来歴を扱います。旧`--refinement-only`の無変更variation確認は過去実装の確認であり、新variationを退役した現行の受入証拠へ流用しません。native画面、実providerと実機の受入は別です。変更が防ぐ具体的な失敗に合わせて必要な確認だけを選択してください。

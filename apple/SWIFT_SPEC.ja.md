# inku Swift 実装仕様

このディレクトリは、macOS先行のnative SwiftUIクライアントとApple向け共通packageのworkspaceである。本書をSwift host固有の仕様正本とし、[SWIFT_SPEC.md](SWIFT_SPEC.md)を対応英語版とする。共有DDL、Score、prompt、authoring authority、pipeline状態遷移、seed、描画の意味は[製品仕様](../SPEC.ja.md)を正本とし、Serverを開発上のprimaryとして同じRust coreへ追随する。Swift側に意味処理を複製しない。

最終更新: 2026-10-05。

binding／protocolの版は同梱Rust coreのversion report、描画層の版はrender metadataと[Serverの層定義](../server/src/inku_server/layer_versions.py)を参照する。本書へ共通engineの版定数を複製しない。Swiftアプリの製品版は正式な版管理に従い、この初期実装では新しい版を採番しない。共有層の版が一致しても、host機能とnative UIの移植が完了したことにはならない。

## 更新ルール

- `SWIFT_SPEC.ja.md`をSwift仕様の正本とする。
- Swift仕様を変更するときは日本語を先に更新し、その意図を保った翻訳・要約として`SWIFT_SPEC.md`を同期する。英語版だけに仕様・要件を追加しない。
- 確定した実装変更と残る範囲は本書の日付付き節へ記し、製品の変更履歴は共通の[CHANGELOG.ja.md](../CHANGELOG.ja.md)／[CHANGELOG.md](../CHANGELOG.md)へ同期して記す。Swift専用CHANGELOGを分けない。
- 共通の意味や保存契約を変更する場合は、それぞれの正本を更新する。本書はSwift hostの適用範囲を説明し、独自の共通仕様を作らない。
- sourceと再現手順を公開文書に記す。生成binary、model、log、credential、端末識別子や非公開の作業記録を追跡対象に含めない。

## 2026-10-05 バッチの接続断対策と失敗診断

描画pipelineのHTTP clientはServerと同じくcoreの試行ごとに作成する。Geminiのtoken計数と生成要求はその試行内の同じephemeral sessionを使い、成功・失敗・取消しによるtaskの終了を待って破棄する。別の行や再試行へsessionを共有しない。要求の形式・model・token数・期限・保存したレート予算とcoreの再試行上限は保持し、transportで独自に再送しない。

終端失敗は同じexecutionのfailed eventと該当actionの最終metricから、処理段階・安全な原因・試行番号・診断codeを行エラーへ保存する。閲覧中の別エラーとは分け、背景描画が作品・prompt・保存metricsを差し替えない。最後のmetricが成功してcore検証で失敗した場合は、以前の再試行の接続断を原因に使わない。

新しい通信診断には、準備・受付待ち・token計数・生成要求の操作をoptionalで記録する。古い記録は操作不明として読み、pipeline段階から失敗HTTP操作を補完しない。全試行の期限切れも最後のHTTP操作へ誤帰属しない。HTTP応答を観測していない `sent=false` は未送信の証明とせず、描画ログと生成情報へ「送信状態不明／応答未確認」を表示する。診断に要求URL・header・provider本文・APIキーを追加しない。

接続断の記録だけでは切断元やsession再利用が根本原因かを確定できない。本変更はclient寿命の実装差と診断不足へ対処したsource更新であり、build直前で停止した。compile・試験実行・実providerでの解消確認・起動中appの更新は未実施。

## 2026-10-05 バッチ中の閲覧と次回設定を許可

バッチの行を描画している間も、制作の記述／バッチtab、作品／系譜表示、画面移動、履歴帯の選択・ページ・端への移動、保存作品の詳細・prompt・Score JSON、設定tabを操作できる。実行中の処理と表示中作品の識別子を分け、バッチの進捗・完了は閲覧中作品の画像、DDL、prompt、保存時の計測値を上書きしない。完成作品は履歴へ追加する。明示した新規バッチ／再開では最新結果への追従を開始し、履歴や過去の成功作品を選ぶとその表示を固定する。次の行の成功や画面へ戻る操作だけでは追従を再開しない。

キャンバスに表示中の保存作品には、バッチ中もスターを付ける／外す操作を許可する。押した時の作品IDとスター状態を固定して保存し、後から別の行が成功しても保存対象を移さない。保存中の重複操作を抑止し、保存後の表示更新は同じ作品を表示している場合だけ行う。スターは保存作品の属性だけを更新し、開始済み描画の条件を変更しない。

新規描画、再描画、編集の確定、取込、スター以外の作品の変更、バッチの入力・条件・再開判定は、行の間もバッチ全体の実行lockを維持する。設定の表示・通常のprovider／model／URL／rate／描画制限の保存は次回用として許可し、開始済みrequestのmodel、接続、budgetと再試行条件を変更しない。APIキーの保存・削除、個人ChatGPT接続、plugin変更、DB復元・backup、結果file logの切替は実行中に制限する。開始前から開いていたsheetでも、キー変更の開始時に現在の実行状態を再確認する。

この更新はsourceと文書までとし、build直前で停止した。compile・試験実行・native操作は未確認。通常のforeground描画とdemoは従来の実行境界を保持し、batch行だけを閲覧可能な背景処理として扱う。

## 2026-10-05 共通Rustの並列処理と試験用最適化への追随

Serverの追加変更に合わせ、描画capability matrixの再導出をshape単位の並列処理へ移植した。predicate・termの列挙順と結果の順序、asset identityを保持する。通常の描画が参照する同梱matrix、共有protocolと描画の意味は変更しない。

既存のDDL・pipeline corpusとraster比較の試験sourceへ、入力順で結果を回収する並列実行を取り込んだ。Swift側の限定fixtureとraster case指定を保持し、試験ケース・入力・期待値を増やさない。Cargoのtest profileでは `resvg`、`usvg`、`tiny-skia`、`tiny-skia-path` のみ `opt-level = 3` とする。release profileと依存関係は変更しない。

この追随はsourceと文書の更新までとし、buildの直前で停止した。compile・試験実行・実行速度・新binaryの動作確認は未実施であり、既にインストールしたアプリの確認結果とは分けて扱う。

## 2026-10-04 現行Serverの共通core・保存作品・全体操作への追随

本更新は現行Serverの意味処理を共通Rustへ取り込み、SwiftのUniFFI、音数判定、native rasterの境界を保持する。更新時点のScoreは0.19、描画エンジンは73。Stage 1が応答を確定した時に保持fallbackを清掃してから構図読みに進み、構図prompt v2、明示した隅、Cellsの反復配置、日本語修飾語と縦長の角度制約へ追随する。既に保存された不正なsnapshotを自動修復したり、pending要求を自動再送するmigrationは設けない。

### 新しい操作のモデル・origin・seed

新規記述と再解釈は、今回選ぶStage 1モデルを両段へ使う。新規の独立DDLはStage 2モデルを優先する。保存DDLの編集と配置変更は親のStage 1来歴を保ち、今回選ぶStage 2だけを使う。DDL／配置のモデルchooserで確定した値はStage 2の既定へ保存し、Stage 1既定を変更しない。通常制作の次モデル、保存既定、開始済みbatch／demoの凍結requestは別に保持する。

共通coreのauthoring originは正式な `stage1_generated`／`user_authored_ddl` を使い、portable欄 `ddl_source_origin` の移行情報とは混同しない。render seedはcanonicalなUInt64十進文字列、composition seedは独立したnullable文字列として境界を渡す。保存時の未設定をrender seedで埋めず、新操作のcompilerとrenderのcomposition seedが違う場合は拒否する。旧保存requestや作品本文はこの入口正規化で書き直さない。

新規requestの描画制限は、設定未記録でも9項目の既定値へ正規化し、実効hard budgetのcanonical JSONから `host-settings:SHA256` のpolicy identityを常に作る。既定値を明示した設定と未記録の設定で同じ制限なのにauthority／Score／描画hashが異なる分岐を除く。custom値も新規requestへ適用する。保存作品の凍結configはこの正規化の対象にせず、旧policyと再演条件を保持する。限定checkで既定値の一致・custom値の反映・保存条件の保持を確認した。

新しい描画用color mapは基本色のfallbackに加え、catalogの各named palette色を `palette:<name>` の別名として含める。名前をそのまま保持し、同名が重なるときは後の色を優先する。`Deep Red`等もseedによる色候補へ入るため、基本9色だけが一致しても同じ配色条件とはしない。選択catalog、自動配色候補、render用catalog mapと明示したreplay用の新mapに共通処理を使い、既存作品に保存された9色mapや履歴・書出し条件は書き換えない。限定checkで旧mapの保持を確認し、赤い正方形・seed43のCLI比較でServer1162とScore・SVG・19色map・描画条件の13項目が一致した。provider品質や全UIの受入をこの結果へ含めない。

「思考を表示」はmodel dialogのdraftと表示設定へ保存する。閉じる／取消しでは元へ戻し、確定したrequestへoptional値を保持する。現行Serverと同じくprovider reasoningへの接続はなく、この選択が推論結果や実token数を変えるとは表示しない。

### 保存作品を開くときの固定情報

新作品の送信prompt、compile delivery、render metadata、diagnostics、eventsを保存effectのACKへimmutableなpresentationとして入れる。作品の再選択はその作品のACKを読み、同じexecutionに後から保存したchildの情報や現在の設定で置き換えない。空配列は当該段を送っていない新記録、欠落は旧記録の未記録として区別する。構図・写生・自動配色のprivate requestをStage 1／穴補完のauthor向けpromptへ混ぜない。保存前の取消しを確認し、commit後の取消し通知で保存済み作品とACKを消さない。

生成情報は開いた保存作品を固定し、「詳細」「プロンプト」「Score (JSON)」のtabで読む。詳細は写生、両段のmodel／言語、seed、色の対応、canvas、SVGのbyte／object／point数、hash、版、由来、batch ID／元行、保存comment、日時／時間と実usageを表示する。送信記録の欠落と空配列、読込中と取得失敗を区別し、promptの開閉・コピーとScoreの行番号・コピーを提供する。読込みやtab変更で制作の選択、現在設定、provider送信を変えない。

新規requestのoptional `GenerationProvenance` はDDL／DDL engine、native Bundle build、参照資料build、UI言語とbatch ID／行番号をsave ACKへ保持する。旧作品の欠落を現在値で補わず、再演は元のprovenanceを保つ。Stage 1 promptの基底digestはnativeでは未記録として示す。意味が異なる `base_source_digest` を代用しない。usageの部分記録から完全な総tokenを作らない。この生成情報UIの最終追加はsource実装であり、以下の途中の型検査や過去画面確認を最終build／実画面受入と読み替えない。

保存記述の空文字列を保持し、DDL作品の表示名だけに保存DDLの先頭行を使う。専用DDL editorは保存親とdraftを固定し、取消しで本文・表示作品・revision・履歴を変えない。確定DDLの記述ロックと直接DDLを区別し、保存条件の読込中／未記録も操作不可の理由として表示する。制作・library・系譜・previewの共通作品menuは同じ固定した保存対象へ接続し、直接DDLでは記述・写生・model再解釈を隠す。確定DDL編集では理由を添えて再解釈を抑止し、配置・タッチ・配色・DDL編集を残す。

新しいvariationの生成・採用・自動推敲・AI助言を退役し、旧保存variation/seedと系譜の読取表示を保持する。推敲は言葉によるタッチ1案、配置／読み取り1案または4案を区別する。直接DDLでは読み取りを選べない。model比較は使用中登録LLM最大4件、catalog比較は元のcatalogを除く候補を使う。Vision助言と自動推敲は画像を扱える登録modelを明示選択し、対象作品を固定する。奥書は生成成功時に原文を新recordとして保存し、後の編集で上書きしない。旧採用本文は互換読取を保持する。

AIへ渡す方針はWebと同じ160 UTF-16 code unitまでとし、表示counterと上限を揃え、見える文字を途中で切らない。自律推敲の保存世代は「観察」で読むだけでは親を変更せず、「この作品から再開」で明示したときにだけ保存作品と条件を読み直して次の親を変える。読込失敗は元の親と原因を保持する。奥書は起点から対象作品までの固定経路を読み、その世代数を表示する。経路を読み直せない状態で新しい奥書を生成しない。

### 履歴・画面・書出しの対象

履歴stripは作品領域の幅から表示件数を決め、空白を埋めるため別の入力や表示作品を変更しない。libraryの検索・印・page・複数選択、previewと「制作で開く」を分ける。系譜の中心変更、枝開閉、保存情報previewと制作選択も別操作とする。書出し候補は開いている画面と固定targetからsnapshotにし、他画面のcheckboxを混ぜない。

presentationは開いた保存作品と独立した履歴viewerを使い、前後移動で制作の入力・選択作品・履歴状態を変更しない。開閉で制作のview階層を作り直さず、開く前の全画面状態を保持する。生成情報・library・canvasのhashコピーは、正本どおり先頭のdomain prefixだけを分離したdigest全体を使う。未読語台帳の再読込失敗は前の一覧と原因を保持し、記録が空だったと表示しない。

export dialog内の形式・resolution・card／animation条件は「今回だけ」のdraftで、保存defaultとPNG templateを変更しない。default／templateは設定画面で明示保存する。SVG用途の説明、単作品card、animationの150／300／500／1080／2160／4320とcustom、PNG templateの個別保存／resetを用意する。clipboardは画像／card形式と高さ256〜4096px・64px刻みを持ち、cardは保存作品を対象とする。full／simple／customの7項目、標準／詳細設定と文字倍率sliderはlocal表示設定として保持する。

demoは開始時条件を固定し、生成記述・描画中記述・完成指示書、経過／残時間・次回待ち・記録済み描画tokenを分ける。記述生成のusageを取得していないため総tokenの完全性を主張しない。間隔はiteration開始から測り、期限は次のiteration開始を止める。進行中の共通core処理をdemo期限で別timeoutへ置換しない。停止は処理の終了と保存結果を待ち、結果不明を成功・未送信と推定しない。

### Tips・同梱正本・保守状態

Tipsはbundle内のcurrent Server JA/EN辞書をsource keyから読込む。全静的textと動的template/key、source commitと対象fileのSHA-256を同梱し、単数形 `tooltip*` も落とさない。native固有のtarget／取消し／保存境界は専用fallbackを使い、group共有の説明をlocal書出し印へ明示適応する。account／ACL／server管理を実装したとみなさない。印は現在値別の付ける／外す、子buttonは個別説明とし、Tips offは空。作品本文と保存metadataは翻訳せず表示する。

通常のbuildはcommit済み `ui-reference.json`、provider default、model catalogのreview済みsnapshotを使う。別のServer sourceへ追随する場合だけ `INKU_APPLE_REFERENCE_ROOT` またはexporterの `--source-root` を指定して明示更新し、差分をreviewする。rebuildだけで同梱正本を取り直さない。Swift packageの直接buildも同じsnapshotを使い、音数辞書とRust artifactは別に準備する。

`build-macos.sh`は必要toolの確認後、resource／core／buildの変更前に[停止helper](scripts/stop-existing-macos.py)を呼ぶ。現在UIDの既知bundle IDと実行fileを検証し、PID identityを再確認してSIGKILLで停止する。最大10秒の再確認で実行中instanceが残ればbuildを中止する。未知のInku類似processはsignalを送らず検証errorとし、停止結果を`apple/build/macOS/stop-existing.json`へ記録する。

自動backupは保存先、最新成功、次回予定、保持世代・各日時／容量を読み出す。状態再読込はbackupを新規作成せず、失敗理由を保持する。描画logも失敗表示を閉じる／もう一度読む操作を分け、読込失敗時に以前の記録を消さない。読込前を「記録なし」と認定せず、再読込でdriver再開やprovider再送を行わない。

今回の限定確認はStage 1保持fallback、明示した隅、日本語修飾語、縦長角度、Cellsの各1 Rust selectorと、作品別presentationを保存・Host再作成・cancel後に読む1 Host caseが成功した。最新appの型検査も成功。CLI同入力比較、最終native操作、実provider／OAuth、iOS、Intel実機、macOS14実機と作者受入は別の証拠を要する。過去の画面確認と旧variation checkを今回の完成根拠へ流用しない。

## 2026-10-04 macOSの処理エラー表示

macOSでは全体の処理エラーを画面下の閉じられる表示へ出す。本文を選択・縦scrollでき、同時に開いている作品dialogがある場合はその内側に表示する。エラー状態のownerはAppModelだけで、閉じる操作または次の操作開始で解除する。描画開始時の解除と直後の失敗でNSAlert sheetを閉じて再表示する経路を使わない。iOSの警告と、削除・復元等の明示確認は従来のまま。

## 2026-10-04 描画失敗の診断と実行ログ

toolbarの「描画ログ」で直近100件のpipeline実行を新しい順に表示する。成功作品がない実行も、開始日時、記述、固定したモデル、完了・失敗・停止等の状態、失敗段階・分類、各試行の時間・HTTP状態・実測記録とcoreの経過を確認できる。読出しはSQLiteの既存snapshotだけを使い、driverの再開・provider送信・作品の変更を行わない。raw本文や凍結したprovider設定を通常logのdecode対象にも返却型にも含めない。

通常APIの失敗metricへ後方互換optionalの診断を付ける。OS通信errorのdomain／codeと固定した説明、既知host error、HTTP拒否のcode／type／param／statusと240文字以内のmessageを保存する。接続先はscheme／host／portだけとし、path／query／userinfo／headersを含めない。実credentialと秘密らしい文字列を切取り前にmaskする。HTTP応答を得られない通信では、要求を送れたと推測しない。古い実行には新しい詳細を補作せず、記録されなかった理由を明示する。共通Rustの失敗分類・再試行・fallbackは変更しない。

既存の「生成結果のログを保存」を有効にすると、成功作品の従来logに加えて、DBと同じdirectoryの `drawing-logs/` へ実行ごとの累積JSONを原子的に保存する。成功・失敗・停止までのcore経過と通常metricを含み、古いcallbackで新しいrevisionを上書きしない。file logは既定で無効、SQLiteの実行記録は従来どおり保存される。file logの自動rotation／日数purgeはまだ設けない。詳細本文は従来の開発者専用・明示opt-inへ分離する。

限定確認は `InkuAppCheck --drawing-failure-log-only` の1失敗実行でSQLite・再起動後の読出し・terminal file logと再送信なしを確認する。hostの `ProviderObservationTransportChecks.testSafeFailureDiagnosticsWithoutRawCapture` は接続拒否1件とHTTP拒否1件、秘密除去と旧metricの読出しを確認する。実providerの再描画成功・native操作・OS実機の確認はそれぞれ分ける。

## 2026-10-04 バッチの入力・選択ダイアログをWebへ揃える

新規バッチは1行に1作品分の記述を入力する。DDLからの新規バッチ描画を選択できず、制作の入力mode・DDL・指定写生を引き継がない。写生はバッチ独立の「なし／あり」で既定は「なし」、各選択にWebと同じ説明を表示する。暴れるは「切／入」を切り替え、開始時の値を全行に固定する。言語とseedは詳細から変更する。

モデル変更はWebのモデル選択dialogへ揃え、Stage 1/2の共通tab、仮選択の要約、説明、サービス別card、取消・決定を表示する。card選択はdraftだけを変え、決定で次のモデルへ適用し、×・取消・Escapeは破棄する。候補は設定の登録catalogまたは同じ標準接続の同梱catalogにある使用中LLMに限る。登録外の参照を候補や次のバッチの値へ補わず、登録外の既定値では使用中モデルを選ぶまで開始できない。提供終了・契約専用cardは選択不可とし、段別評価は低い段の順に並べる。ChatGPTの順序はcatalogを保つ。hover／keyboard focusで用途・段別評価・速度・表示言語のcommentを示す。dialogを開くだけでHTTP・Keychain・設定保存を行わない。保存済み設定と作品の参照は保持する。

色dialogは「記述から自動選択」の独立cardを先頭に置き、カタログ名・ID・説明と10色の見本・HEX・色名の行を続ける。日本語色名は日本語表示でだけ追加し、幅が狭いときは5列へ折り返す。ランダムの新選択肢は設けない。選択はdraftとし、決定と×で適用、キャンセル・Escapeで破棄する。制作と共有する色dialogでも新規のrandom選択を撤去する。新バッチはautoかfixedを捕捉し、旧random状態は固定されたcatalogとして扱う。

旧バッチ記録のDDL・指定写生・random条件や開始済みrequestは変換しない。再開は従来の凍結requestを使用する。限定確認は既存`InkuAppCheck --batch-ui-only`の2入力に、新規バッチと制作の条件分離・on/auto捕捉・登録外モデル拒否を加える。dialogのdraft確定／取消、写生・暴れる、色行の見た目はnativeとWebの実画面で比較し、実provider推論・作者のデザイン受入・iOSは別の確認とする。

## 2026-10-04 バッチの表示崩れと画面構成の修正

入力履歴は全幅で最低28ポイントの高さを確保し、新しいバッチの描画ボタンにも十分な高さを設ける。macOSの小型メニューボタンの高さへ縮んで操作箇所が見づらくならないようにする。

macOSのバッチ入力はNSScrollView、NSClipView、NSRulerViewとSwiftUI hostの描画境界を明示する。行番号と背景の描画は入力viewportとの交差領域へclipし、多数の行や横scrollで下の描画条件へ漏れない。本文、UTF-16の元行番号、IME・undoと2軸scrollの保存契約は保持する。

通常幅は左410ptの入力列と右の作品領域を使用する。入力220pt、件数、幅いっぱいの履歴、前回の再開card、次の描画条件、新しいバッチの操作、結果の順へWebと揃える。開始buttonは条件の直後に置き、結果一覧の後やpane底へ固定しない。モデル／色カタログはlabelと変更button、その下に選択値を表示し、compact操作は幅に応じて折り返す。狭い幅は全体を縦scrollし、低い通常幅では右側もscrollできる。

バッチの観測作品がないときは現在選択中の保存作品を右に表示し、バッチ成功行の番号は付けない。新しい記述バッチは使用可能な描画モデルを要求し、前回記録の置換確認でも同じ入力・モデルの条件を検証する。開始済みrequest、再開記録と結果不明行の明示操作は変更しない。表示修正はnativeとWebの実画面を比較して確認し、確認用の実API推論や保存作品生成を必要としない。

## 2026-10-04 モデル設定UIのWebへの追随

モデル設定はサービスcardから接続を選び、名前とID、使用モデル数、LLM／Vision別のmodel chips、モデル選択、折りたたみのレート制限と接続設定、サービス追加の順に表示する。Ollama CloudとOllamaを優先して並べる。単一利用者の端末設定なので、Webの公開設定は「使用するモデル」と表示する。名前変更・メモ・追加は独立sheet、削除は対象IDを保持した確認操作とする。URL、レート制限、APIキー、描画の既定値はそれぞれ個別に保存し、他の未保存draftを含めない。

モデル選択sheetは検索、使用／不使用・LLM／Visionの絞り込み、表示中の一括使用／解除、用途と評価・速度・日英commentの編集、取消・保存を持つ。検索と取消は設定を変更せず、保存成功時だけ閉じる。モデル一覧と使用設定・サービスメモは`providers.json`の後方互換optional fieldへ保存する。保存済みcatalogをその接続の正本とし、未保存の標準接続は同じIDと方式の同梱catalogを使用する。明示したモデルリスト取得は新しい候補をその時点で併合・保存し、既存metadataと使用設定を保持する。未保存の編集がある間は取得を抑止する。

非使用、LLM用途を持たない、提供終了、契約専用の登録モデルを新しい描画候補から除く。保存済みモデル参照と作品の記録は保持するが、そのモデルを非使用にした後の記述描画は別の使用中LLMモデルを選ぶまで開始しない。未登録の手入力model IDは登録済み接続のcustom参照として保持し、適性を推測しない。直接DDLの描画はこの使用設定に依存しない。

APIキーの存在は秘密値を取得せず照会する。設定済みキーを表示・再入力せず、変更は明示した削除確認後に新しいキーを保存する。接続・model・名前・メモ・rateの通常保存はKeychainを読み書きしない。サービス削除もKeychain項目を削除せず、そのサービスの描画既定参照だけを解除する。APIキーと設定JSONは別資源なので、キー書込後に設定保存が失敗した場合はKeychain項目だけ残りうる。状態を再確認して同じ操作を完了する。取得・推論・OAuthを起動時に自動実行しない。

限定確認は`InkuAppCheck --model-settings-ui-only`を使用する。一時設定／SQLiteと秘密値を扱わないmockで個別保存、invalid URLの拒否、旧設定の読込、draftの破棄、用途・評価・使用設定の再読込、描画候補の制御、keyなし追加・削除を確認する。実APIキー・モデル取得・推論とnative画面の目視受入は別に行う。共有Rustと作品DB schemaは変更しない。

## 2026-10-04 Server準拠の標準providerセット

同じcheckoutのServerの公開provider定義から、OpenAI API Platform、Claude API、Gemini API、NVIDIA NIM、Ollama、Ollama Cloudの6接続を同梱する。表示名、接続方式、default URLとAPIキー要否はServer sourceから生成し、環境変数やServerの実設定・credentialは取り込まない。Personal ChatGPTは専用設定で明示して有効にする。

新規設定と旧設定の初回読込で不足するIDだけを追加し、既存接続のURL・方式・credential ID・制限値、モデル選択、plugin・描画設定を保持する。`providers.json`に追加済みmarkerを原子的に保存し、以後の起動で重複追加や設定再保存を行わない。作者が削除した標準接続も自動で復活させない。APIキーは作者が設定画面で入力してKeychainへ保存する。追加処理はKeychainへアクセスせず、HTTP・モデル取得・生成を開始しない。

設定と制作のモデルchooserは、同じServerの同梱catalogを候補として表示する。同じprovider IDと接続方式に限って使用し、カスタム接続へ流用しない。提供終了モデルは新選択候補から除くが、既存の選択値と手入力を保持する。明示して取得した接続先の候補を優先して併合し、サービスが現在提供するモデルや契約の利用可否を同梱候補から保証しない。Claudeは`/v1/models`、Geminiは`/v1beta/models?pageSize=1000`、OpenAI互換は`/models`へ明示取得する。バッチdialogの登録済み候補と確定操作は上の現行契約に従う。

限定確認は`InkuAppCheck --provider-defaults-only`を使用する。一時設定とSQLiteで新規追加、旧設定の保持、再読込と明示削除、offline候補・一覧取得URLを確認する。実APIキーの入力・モデル取得・推論とnative画面の受入は別に行う。共有Rustと作品DB schemaは変更しない。

## 2026-10-04 バッチUIのWebへの追随

バッチ画面で、次の描画モデル、色カタログ、写生、Wildと用紙を選ぶ。入力と写生は上の記述専用契約に従い、モデルdialogでは登録済みの候補を仮選択して確定する。macOSでは入力・条件の列と作品canvasを横へ配置し、狭い幅では縦へ戻す。全行の結果は折りたたんで閲覧し、入力から描画までの操作を長い結果一覧の下へ押し出さない。

macOSの入力欄はnative editorを使い、空行を含む元の行番号を表示する。長い入力は折り返さず横へ、行番号と本文は縦へ同期してscrollする。CRLFを1改行として扱い、CR、LF、NEL、Unicodeの行・段落区切りも同じ物理行へ正規化して実行する。空行を除く最大1000作品と元の行番号は従来どおり保持する。

バッチ記述履歴は端末内の`batch-prompt-history.json`へ原子的に保存する。最新50件を重複排除し、空入力と20,000 UTF-16 code unitを超える入力は履歴へ含めない。履歴は前後の空白を除いて改行を正規化する。明示した復元は入力欄だけへ適用し、保存作品と再開記録を変えない。新しい実行の再開記録には、空行を含む元入力と開始時の条件を任意fieldとして保存し、古い記録も読み出せる。

実行中は処理中の元行をcompactに表示する。直前に成功した作品の行番号・SVG・DDL・写生は別の観測snapshotへ保持し、次の処理行に付け替えない。provider進行は既存の実経過時間・実usageを表示し、未取得を0と推定しない。再開cardには次の元行、残件、開始時のモデル・色カタログ・用紙等を示す。再開は成功行を描き直さず固定requestを使用し、失敗数と元行・理由を表示する。結果不明の行は従来の履歴確認・明示した再試行／省略を待ち、自動再送しない。準備中も画面移動と別作品操作を抑止する。

限定確認は`InkuAppCheck --batch-ui-only`を使用する。2入力だけを一時SQLiteとoffline provider mockで実行し、元行2／4、開始時のmodel／catalog／canvas、現在行と観測行の分離、履歴の再読込・入力だけの復元、旧journalから失敗行だけを再開する動作を確認する。nativeの行番号位置、IME、2軸scrollと画面配置、実providerの受入は別に扱う。共有Rust、作品DB schemaとdemoの生成動作は変更しない。

## 2026-10-04 制作・ライブラリ・系譜のWeb UIへの追随

制作の通常表示は記述／DDL、次のモデル・色カタログ・写生・Wild・用紙の要約、固定した描画操作をまとめる。言語・シード等は詳細popoverへ、保存作品の指示書・条件・計測は「表示中作品の生成情報」へ分ける。DDLは短い読取表示から独立editorを開き、取消しでは制作入力・表示SVG・revision・履歴を変更しない。確定時だけ既存のauthorityとrevision検証を通して子作品を描く。

ライブラリの選択は専用previewを開き、制作中の入力と作品を保持する。「制作で開く」を明示した場合だけ制作の選択を切り替える。previewを閉じると一覧の幅を戻し、書出しはチェックした作品、またはpreview作品を対象とする。一覧は保存日時、記述、役割別モデル、印と操作を列で揃える。未記録の解釈モデルをDDL入力と推定しない。コメントは読込状態・対象ID・編集draftを分け、未取得時の保存と遅い取得による編集中の上書きを防ぐ。

系譜は親子の矢印、お気に入りへ至る経路、削除節点へ接続する破線を表示し、既定は縦方向とする。枝の開閉は中心節点を保持し、未知の子だけを読み出す。全体図は40–140%で拡縮し、閉じると通常の枝の開閉、中心、方向とスクロール位置へ戻る。通常表示と全体図のsnapshotを分け、最大200節点の読出し境界を維持する。

macOSのキャンバス上の縦ホイールは1回0.15の倍率変更を行い、25–1000%に丸める。pinch・drag・倍率buttonと同じ状態を使い、100%以下では移動を中央へ戻す。処理はキャンバスをhostするnative view内に限定する。保存SVGとraster予算は変更しない。

用紙chooserは名前・形・分類・意図を表示する。候補・順序・比率はRust registryを使用し、表示metadataはreview済みのWeb正本snapshotを同梱し、更新は明示したsource exportで行う。選択は次のcanvasだけへ適用し、閉じる操作と保存作品のcanvasを分ける。歳時記はcompactな語一覧と選んだ1語のpreview・効果・説明・例を表示する。通常は参照のみとし、DDL editorから明示して開いた場合だけeditor draftへ語を挿入する。同梱定義のないplugin語は参照のみとする。

対象画面の主要操作へTipsを補い、設定の`showTooltips`とtoolbarの表示切替に従う。「inkuについて」は同じcheckoutのWebの概念説明、5項目の用語表、作者情報とrepositoryリンクを取り込む。製品版・build・build日時とDDL／render層の版を生成resourceから、binding protocolは同梱coreのreportから表示する。

描画の制限値はServerの9項目、3分類、既定値と相互上限ルールをbuild resourceとして使用する。1–100000の整数を独立draftで編集し、保存・取消・再読込を分ける。既定値への復帰も保存するまで適用しない。新作品の要求ではServerと同じ4項目をhard／operational両budgetへ写し、適用値からbudget identityを作る。保存作品のconfigurationと既存の構造資源設定は保持する。DDLの意味・展開・描画は共有Rustのままとし、DB schemaを変えない。

表示resourceは`export-server-resources.py`と`export-web-reference.mjs`で明示したServer／Web正本から更新し、通常buildとSwift packageはcommit済みsnapshotを使う。限定確認selectorは`--library-browsing-only`、`--lineage-presentation-only`、`--ddl-editor-cancel-only`、`--drawing-limits-editing-only`、`--canvas-wheel-only`で、具体差分に必要なものだけを選ぶ。nativeの配置・操作感・実ホイールイベント、Intel／最低OS実機、実provider、iOSの受入は別に確認する。

## 2026-10-04 macOSアプリアイコンと固定install

macOSアプリアイコンは既存[incu画像](../docs/assets/incu-icon-512.png)から生成する。pixelの配色、暗い背景と透明な角を保持したicnsをbundle resourceへ含め、Info.plistから参照する。通常のbuild手順で再生成する。

`build-macos.sh --install`は成功したappを`~/Applications/Inku.app`へ更新する。既存のbundle IDとDB指定を保持し、固定app directoryの中身を更新するため、Dockの登録をrebuildごとにやり直さない。build前の停止helperとは別に、installerは実行中appや未知の既存appを上書きしない。作品DBをapp bundleへ移さない。

DB指定は`--database`、任意のbundle設定`InkuDatabasePath`、従来のApplication Support defaultの順に解決し、AppModelを1回だけ作成する。bundle設定は絶対file pathを使う。既存の試行DBをinstall時に指定すれば、Dockの引数なし起動でも同じDBと隣接設定を使える。共有Rustの意味処理と保存契約は変更しない。

## 2026-10-03 macOSの制作・全件履歴・周辺機能

### 保存作品の印とプロンプトの取得状態

推敲／書き出し用の印は、表示中のlibrary pageに含まれない保存作品もIDから読み出す。選択作品の注釈をpage更新後も保持し、印の反転はSQLiteの保存値を同じ書込みtransactionで読み替える。現在pageのcache欠落を印なしと判断しない。schemaと保存作品本文は変更しない。

送信プロンプト欄は読込み中・記録あり・記録なし・取得不能を区別する。同じexecutionでDDL編集childへ進んだ後に過去親を選んでも、最新childの出力を親へ流用しない。記録がない、または親の記録を取得できないことから「モデルへ送信していません」と断定しない。共通coreの編集authorityと保存DDL／Score／SVGを保持し、作品の再選択だけでprovider要求や新しい履歴を作らない。

### 制作と保存作品の表示

制作画面は左に記述／直接DDLと次に描く条件、右に表示中作品の条件と作品／系譜canvasを置く。生成／停止は入力のscroll領域の外へ固定する。canvas下の操作列に詞書と書字方向、保存作品の星／推敲印／書出し印、full hashコピー、再現比較、生成情報、歳時記、書出し、clipboard、presentationを置く。表示中作品の写生と指示書はcanvas下に表示し、写生編集・DDL編集・指示書からの描画はその保存作品を対象とする。写生の開閉はlocal表示設定に保存する。狭い幅では縦配置へ切り替える。保存作品のmodel、色catalog、用紙、サイズはcompactな要約と詳細popoverで読み、次の入力条件と区別する。画面上の記述caption、縦書き／横書き、配置、pan／zoom、プレゼンテーションは表示合成であり、保存SVGを変更しない。「用紙に合わせる」はzoomと移動を初期位置へ戻す。

制作画面で登録済みのserviceと描画modelを選択する。設定したmodelと明示取得したmodel一覧を表示し、一覧取得は利用者のbutton操作だけで始める。選択した次のmodelは記述解釈と構造化の両段へ渡し、設定画面の保存defaultや親作品のmodelを書き換えない。新しい生成要求・推敲・比較の初期選択は次のmodelを使い、開始済みbatch／demoのmodelはそのsnapshotへ固定する。未接続時はモデル設定へ案内する。

制作とモデル設定の「モデルの適性・用途」はreview済みServer登録資料snapshotを同梱し、用途、解釈／構造化と両段の評価、Visionの評価、日英comment、更新日時と提供状態を表示する。両段の評価は弱い段階の値、段階別評価がない場合はLLM評価を使う。正確なcatalog service ID・接続方式・model IDで照合し、Ollama tagの`:`を保持する。custom serviceや未登録modelを名前やURLから推測で評価しない。Serverのdeveloper専用速度情報は公開環境と同じく表示しない。登録資料と接続先から明示取得した入力上限・対応機能は別欄にし、案内を読むだけで選択・保存default・開始時snapshotを変更しない。

状態欄は共通coreの試行回数とhostの開始時刻を用い、providerの段階、固定要求の呼出しmodel、試行／再試行、段階全体と今回の経過時間を表示する。同じ段階の再試行は段階の時計を保持し、今回の時計を開始し直す。完了・失敗・確認待ち・停止で時計を確定し、停止は遅い応答の終了を待つ。入力／出力token数はproviderが返した実usageを使い、未取得は「記録なし」、明示0は0と表示する。文字数や予算用の推定tokenを実usageへ置き換えない。通常生成と比較候補は同じ表示を使い、古いtokenの応答を除外する。新規・新しい処理開始は古い表示を消す。保存作品の選択とprovider不要の再現比較は、当該作品の保存時recordを読む。

新規生成の設定はServerから生成した`composition: {read: true}`を使用する。構造化した下絵の後、共通Rustが要求する`read_composition`を通常API／Personal ChatGPTへ渡し、同じaction identityの`composition_read`を返す。構図の読みは下絵と同じStage 1 modelと上限を使い、再試行・既定値へのfallback・可視DDLへの構図反映は共通Rustが所有する。構図の意味と`［構図］`／`[composition]`の規則は[製品仕様](../SPEC.ja.md)に従う。

保存設定のcomposition欠落と`read:false`はそのまま保持する。欠落は従来の下絵、`read:false`はLLMの読みを行わない既定の構図として扱う。直接DDL、構造化済み応答からの継続、保存Scoreの再演奏へ構図要求を追加せず、既存の保存SVG・Score・DDLを変更しない。構図promptは耐久execution snapshotに保持し、作品のStage 1／2送信prompt履歴へ混ぜない。

構図は独立した進行段階として表示し、下絵から切り替えた時に段階時計を開始し直す。通常生成と比較候補の両方で固定Stage 1 model、試行、経過時間を表示する。保存`elapsedMS`は構図待ちを含む実行全体の経過時間であり、個々のprovider呼出し時間とは区別する。

通常APIとPersonal ChatGPTは、action identityごとの実呼出し時間、実usage、要求model／応答model、HTTP statusと結果を記録する。段階はServerと同じく`read_composition`を`composition`、補完を`stage2`、そのほかのprovider actionを`stage1`へ分ける。通常の生成情報は本文を持たない`ProviderAttemptMetric`だけとし、作品保存時のperformance contextへ固定する。後のexecution更新で過去作品の記録を置き換えない。保存作品の再表示と読出し専用の再演奏比較は保存時の記録を読み、provider要求を追加しない。古いsnapshot／作品で記録が欠落していても読める。これはSwiftの型付きrecord形式であり、Serverの`metrics.composition`と物理JSON形式を同一とするものではない。

通信本文は、`INKU_DEVELOPER_MODE=1`で起動し、設定の「生成時の送受信を記録」を有効にした場合だけ端末内へ保存する。独立したdefault-offの設定を開始時requestへ固定し、通常環境での明示要求と記録に対応しないtransportは送信前に拒否する。実request本文の耐久記録を送信前にSQLiteへ保存し、保存失敗時はHTTP要求を出さない。送信後の記録失敗を成功や通常のprovider retryへ読み替えない。共通coreのprompt／schema／有限retry／fallbackと結果のidentityを変更しない。

private executionの`ProviderAttemptObservation`は本文を任意に持ち、通常の履歴・prompt欄・結果logへ露出させない。開発者向けの折りたたみ欄を明示して開いた時だけ読み出し、処理中に開いた記録は「記録を更新」で再読込できる。request／response本文はそれぞれ16MiB以内で、途中切断・上限超過・取消しは不完全／省略の事実を残し、完全な記録とは表示しない。Swiftでは同じexecutionの本文UTF-8 byte合計を64MiB以内とし、送信前に応答16MiB分の余地を確保する。超過は送信前に拒否し、以前の記録を削除・省略しない。この予算は本文の合計であり、encoded snapshotやapp memory全体の上限ではない。接続先URL、header、認証情報、接続設定、例外本文は保存せず、既知のcredentialが本文へ返された場合も除く。画面は先頭32KiBのpreviewを表示し、保存されている本文全体の共有は開発者が明示した操作だけで行う。通常生成情報のAPIはraw本文を返さず、開発者モード外ではraw読出しを拒否する。

macOS menuはactive sceneの操作可否を使う。⌘Nは新規制作、⌘Oは画面buttonと共通のDDL file読込、⌘,は設定、⌘1〜4は制作／library／系譜／batch・demo、⇧⌘Eは書出し、⇧⌘Cは画像copy。既存の⌘Return生成、Escape停止、⇧⌘Fプレゼンテーションと併用する。生成・自動実行・読込・dialog・presentationの状態に合わせて対象操作を無効化し、menu経由で別の書込みを割り込ませない。設定はsystem sidebarとgrouped formを使い、モデル設定への導線は該当categoryを開く。

同梱の歳時記、13色catalog、11用紙と7語のMacro／plugin定義はServer sourceから生成し、共通Rustで定義とdigest lockを解決する。pluginの有効切替は新作品へ適用し、保存作品の定義を置き換えない。DDL packageのimportは`inku.ddl-export.v1`の本文・付属定義・lock・整数表現を検証し、次の新作品へ添える。4MiB／64定義を超える入力や不完全な定義は拒否し、途中結果を採用しない。

色カタログのnative chooserはID、言語に応じた説明、順序付き色見本、HEXと日英の色名を表示する。固定／記述から自動選択をdraftとして編集し、決定・×で次の条件だけへ適用、キャンセル・Escapeで破棄する。新しいrandom選択は用意しない。直接DDLでは自動選択を使わず、入力をDDLへ切り替えた時に既存auto選択をfixedへ戻す。

macOSでは1つのDDL fileをwindowへdropでき、標準panelと同じURL読込・検証を通す。読込中の生成／batch開始を抑止し、取消し、scene終了、制作内容の変更後に遅い結果を採用しない。成功後に制作を表示し、定義を伴うimportの表示は現在のdraftへ結び付ける。「新規」または保存作品を開いた後は古い完了表示を消す。

DDLのdraft確認は読出しだけとし、変更確定を共通coreのrevision／authorityへ渡す。最初の確定DDL変更後は記述の権限へ戻さず、新しい作品と系譜childを保存する。補完は候補の表示と採用・却下を分け、採用前の本文を書き換えない。保存欄`ddl_source_origin`は従来どおりNULLまたは`legacy_expanded`だけであり、編集authorityをこの欄へ保存しない。

通常の「再演奏」はServerと同じ読出し専用の再現比較を開く。固定した保存作品のSVGと、保存Score・保存条件を共通Rustで描いた現行SVGを表示し、履歴・系譜・表示作品・元のexecutionを変更しない。保存時／現行の描画エンジンの版、版の不一致・記録なしを表示する。タッチの語句があれば共通Rustのseedを優先し、なければ保存seed、両方なければ暫定0とその注意を表示する。未保存のcomposition seedは未設定のままcoreのfallbackへ渡す。制作・library・系譜・作品menuは同じ比較へ接続し、系譜の保存情報sheetを閉じてから比較を開く。停止・closeは所有Taskの終了を待ち、遅い結果を除外する。「次の条件で再演奏」は明示した条件から新しい保存childを作る別操作として保持する。

保存作品の「記述を変える」「写生なし／ありで描き直す」は、制作toolbarとlibrary／系譜cardから同じdialogを開く。開いた作品を親として固定し、保存configuration、用紙、seed、budget、定義とlockを保持して共通coreから新しいchildを保存する。開始時の次の描画modelを両段へ固定する。記述が変わった場合は親の古い写生文を再利用せず、写生「あり」を明示した場合も生成し直す。保存contextのauthorityを確認し、直接DDL・確定DDL編集の作品を記述へ戻さない。取消しは作業の終了を待ち、成功したchildの保存後にだけdialogを閉じて制作を表示する。

編集childのedgeにはServerと同じ`edited_from_history_id`、写生操作では`from_sketch_state`／`to_sketch_mode`も保存する。GenerationRequestの追加項目はoptionalとし、既存の固定requestを読み出せる。

記述／写生dialogは題名と操作footerを固定し、親の画像・記述を入力と同じscroll領域へ置く。親画像は120角、記述は最大4行とtooltipで表示し、dialogの再表示でも入力に押し潰されない構成とする。

### 履歴・library・系譜

履歴stripはSQLite全件を対象に作品領域の幅からpage容量を決め、libraryは独立したpage容量を持つ。最新100件のapp内一覧を検索や作品移動の母集団にしない。最新／新しい／古い／最古への移動、全文記述・全文hash・末尾4桁の検索、star・推敲・export markのAND絞込、thumbnail／listと時系列／系譜groupの独立選択を提供する。

comment、mark、trash／復元、明示した完全削除、複数選択、系譜graph／pathをSQLiteへ接続する。完全削除後は作品本文を消し、nodeのidentity、root、日時と親子関係をtombstoneとして保持する。ACL、group利用者やServerの共有権限は追加しない。

履歴の世代はServerと同じくrootを1とし、primary parentのedgeごとに1加算する。削除済みの祖先も数え、nodeのない作品は独立作品と表示する。初期表示は世代とmodel、保存済みの表示項目は保持する。世代をvariationの種類や幅で代用しない。libraryでは表示中の作品と複数選択のcheckbox、系譜では表示作品と範囲を決めるfocusを区別する。記述のないDDL作品は保存DDLの先頭行を表示名へ使い、保存本文を補わない。hash、comment、mark、親子への移動はcardとmenuから操作できる。

Swift物理schemaはv3で、v2の作品・系譜・execution、local annotation、奥書、未読語の9tableへ`provider_rate_state`を追加した10table構成とする。正本は[bundled migration](Packages/InkuPersistence/Sources/InkuPersistence/Resources/migration-v3.sql)と[schema export](../persistence/reference/swift-schema-v3.json)。既知の完全なv1／v2だけを原子的に移行し、作品・snapshot・ACKの値を保持する。未知schemaは引き続き拒否する。backup／restoreは全10tableを対象とし、旧backupは隔離snapshotをv3へ移行してから復元する。復元先の送信予算・待機期限も保守的に引き継ぎ、古い作品backupで当日の上限をリセットしない。Server／Android DBや旧作品JSONのimportは含めない。

### 比較・推敲・奥書と自動実行

「描画パラメータの編集」は明示した保存親を固定し、配置・読み取りの1案／4案と言葉によるタッチ1案を別操作として選ぶ。生成前に全条件を固定し、候補を通常履歴・系譜へ入れず比較する。拡大はdialog内だけで行い、制作の表示作品を替えない。選択した候補だけを子として原子的・idempotentに保存し、残りは破棄する。途中で保存を停止した場合は保存済みの印を保持し、再試行で二重保存しない。停止／closeは所有Taskと遅い応答の終了を待つ。採用後と再表示後のDDL変更も、新しい保存childを作る。

配置は親の保存DDL、定義・lock・配色・タッチを保持し、新しい配置seedで共通coreから描く。dialogの描画model指定は構造化側にだけ適用し、親の読み取りmodelを保持する。読み取りは開始時の制作の次modelを両段へ固定し、元の記述と保存された写生文から新しいDDLを生成する。確定DDL権限では読み取りを拒否する。DDL／配置のdialogでmodelを確定するとStage 2の設定defaultへ保存し、Stage 1 defaultは保持する。

言葉によるタッチは1案だけで、保存Score・DDL・配色・配置・ワイルドとmodel記録を保持し、providerを呼ばずに再描画する。語句のseedはRust共通境界が既存Serverと同じPython `str.strip()`の空白を除き、残るUTF-8のSHA256先頭8byteをunsigned big-endian UInt64として導く。Unicodeの正規化はせず、Swift／Pythonへtrim・hashを複製しない。seedは正確な十進文字列で境界を渡し、保存edgeのseed前後・語句にも整数の値を保持する。空の語句は共通coreが拒否する。

新しい変奏は共通coreとHost入口で退役しており、生成・採用・助言の選択肢を用意しない。過去に保存されたvariation amplitude／seed、Score・SVGと系譜は読み出せる。旧記録を新しい操作や別の推敲要素へ変換しない。

catalog／model比較は開始時の作品・Score・設定を固定する。候補は採用前に通常履歴／系譜へ保存せず、選択した候補だけをidempotentに保存する。model比較は使用中の登録LLMを最大4件選び、catalog比較は元を除くcatalog候補を使う。Swiftでは逐次生成する。停止とdialogのcloseは処理の終了を待ち、遅れて届いた候補を混入させない。

model助言、random／Vision推敲、奥書は通常生成と同じprovider transportを使う。通常pipeline外の補助要求はServerと同じく描画pipelineの共有rate予算へ加算しない。記述の編集採用と4種類の推敲操作を分け、新variationは許可せず、DDL権限の作品へ記述を上書きしない。中間の推敲作品は`lineage_only`として保持する。自動推敲の各child edgeはWebと同じ`autonomous_refine_mode`を記録し、Visionではその世代の`vision_model`／`vision_observation`／`vision_next_direction`も記録する。randomの来歴へ以前の画面上のVision助言を混ぜない。奥書は生成した原文を成功時にimmutable recordとして追記し、既存本文を上書きしない。旧採用本文は互換読取を保持し、DB backupへ含める。

batchは空行を除く最大1000入力を受け、元の行番号とmodel、provider、定義、seed等を開始時に固定する。一巡後の失敗行だけを既定0／最大5回再実行する。明示した再開でも固定条件を保持する。再起動時に実行結果が不明な行は利用者の再試行／省略選択を待ち、自動再送しない。demoは開始時の設定を固定し、生成記述と作品を表示する。履歴保存は既定で無効、間隔1〜3600秒、実行時間60〜86400秒。間隔はiteration開始から測り、満了は次の開始を止める。停止は実行と保存結果の終了を待つ。

### 辞書・表示・接続設定

日本語はServerと同じSudachi small辞書、英語は同じCMUdictの読みを使用し、Rustの薄い境界で音数・音節を数える。辞書・設定・license・hashを[resource manifest](scripts/description-meter-resources.json)で固定し、build時に生成する。Python runtimeはアプリへ含めない。4000文字までの判定を300ms debounceし、未読語の頻度・日時・文脈をSQLiteへ保存する。判定を無効にした場合は文字数／行数を表示する。

日本語／英語、theme、5段階にsnapする文字倍率slider、full／simple／customの7項目、標準／詳細設定、caption、履歴情報最大3項目、tooltip、mascot、画像／card clipboard、描画制限、export template／保存先をlocal設定とする。clipboard高さは256〜4096px・64px刻み。複数APIサービスの設定、入口別の描画model、明示したmodel一覧取得とRPM／入力TPM／RPDを提供する。通常設定は隣接JSON、API keyはKeychainであり、接続設定を保存するだけでは生成しない。

通常APIのrate制限は[製品仕様](../SPEC.ja.md)とServerの共有描画pipelineへ従う。同じservice IDの写生文、解釈、辞書選択、構図、補完と各再試行を集計し、送信前に作品DBのSQLite transactionで要求数・入力token予算を予約する。複数Host・接続・processからの要求も同じDBの状態を使い、待機中はtransactionを保持しない。旧`provider-usage.json`の該当serviceの予約・待機期限を一度だけ原子的に取り込み、原本を変更しない。読めない状態や保存失敗は送信前に拒否する。旧Gemini記録からPacific日次の残量を証明できない場合は、次のPacific午前0時まで日次上限を消費済みとして扱う。

RPM／入力TPMは62秒windowで設定値の90%を使用し、正の小さい設定は最低1とする。Geminiはsystem／本文／schemaを含むcountTokensに10%の余裕を加え、他方式は実際の送信JSONのUTF-8 byte数に128を加えた保守的な予算を用いる。成功時は実入力usageで精算し、入力usageや送信状態が不明な場合は入力TPMが有効なときだけ予約を保って62秒待つ。日次要求数は既知429と再試行も含み、GeminiはAmerica/Los_Angeles、他方式はUTCの午前0時に切り替える。429は62秒、Retry-Afterの秒数／HTTP日時、Gemini RetryInfoの最大値を待ち、既存の待機期限を短縮しない。待機は共通coreが定めた有限の試行期限へ含め、Host独自の再試行を追加しない。

設定値は0〜1,000,000,000の整数で、0は上限なし。rate設定全体がない標準`gemini` serviceは30／16,000／14,400を使い、他serviceは0を使う。既存のrate設定objectで個々の値が欠落している場合は、従来の「0＝上限なし」を保持する。設定画面は3値と隣接する説明buttonを表示し、0を明示保存できる。

自動backupは既定で無効であり、アプリ起動中に生成・復元・自動実行の終了を待つ。検証済みbackupの成功後にmanifestを確定し、アプリ自身が記録した世代だけを削除する。手動backupを自動世代管理へ含めない。任意の生成結果logは実際に保存した作品だけを記録し、古い作品を開くだけでは作らない。

### Personal ChatGPT

Personal ChatGPTは通常のAPI key接続と別に扱い、既定は無効とする。利用者が明示して有効化・接続し、提供されたmodelを描画modelとして選ぶ。Stage1／Stage2は同じ描画modelを使用する。本人の接続を複数保存しても、作品DBは一つのローカルlibraryであり、multi-user機能を追加しない。

本人認証は127.0.0.1の一時listenerと`/auth/callback`、state／nonce／PKCE、発行済みclient ID、検証したidentityと許可scopeを使用する。資格情報は最大1MiBのAES-GCM暗号化vaultへ原子的に保存し、device-localの32byte keyをKeychainへ置く。平文token fallbackを持たず、SQLite backupに資格情報を含めない。初期無効状態で認証や推論を開始しない。

開始時にprofile ID／generationを固定し、queued要求やbatch／demoの再開で接続を付け替えない。接続解除・切替・quota後は古いrefreshや遅延応答を採用せず、別providerへ暗黙に切り替えない。共有Rustの記述解釈、写生、自動配色、構図の読み、DDL補完だけをResponses／SSEへ接続する。Vision推敲、奥書、demo用記述、model検査はこの接続では未対応として表示する。実本人OAuth、model取得、推論の受入はoffline確認と分ける。

### 保存作品の書出しとnative raster

[InkuExport](Packages/InkuExport/Package.swift)はDisplay／Editable／Compat／Live SVG、PNG、定義付きDDL、共有card、review／AI contact sheet、APNG／GIFを扱う。Displayは保存canonical SVGを再描画せず、保存時の記述（`sourceText`、nil時は`input`）をXML escapeして最初のSVG開始tag直後へ`<desc>`として追加する。空の記述は保持し、既存の`<desc>`と保存canonical SVGは変更しない。ほかのSVGは保存Scoreと固定contextを共通coreへ渡す。PNGはY軸1080／2160／4320、custom 64〜12000pxと用紙比率を保持する。大きい画像は元のsceneを用いるregion rasterで分割し、filter／clipを落とさない。静止画は144,000,000pixel、animationは合計600,000,000pixelを上限とし、取消し後の結果を公開しない。

単作品animationのlayer進行／restart・reverse・once、複数作品のcut・crossfade・fade_white・slide、保存日時順と明示系譜path順を区別する。日本語文字はServerと同じNoto Serif JPをlicenseと共に同梱する。保存先folderのbookmarkとPNG templateを保持し、複数出力は新規folderへ保存する。Finder表示とOS共有へ接続する。

書出し対象は開いている画面で決める。制作は表示中の保存作品、libraryはcheckboxの選択作品（未選択なら表示作品）、系譜はfocusへ至るpathをsnapshotとして渡す。別画面のcheckboxを制作や系譜の対象へ混ぜない。未保存previewは保存作品の書出しへ含めない。書出しdialogもDDL作品の表示名をlibraryと揃える。

共通rasterにimmutableなprepared sceneを追加し、SVG parse結果を解像度間とexport tile間で再利用する。native rendererはscene推定cost16MiB／8件、image64MiB／256件を上限とし、保存SVGや画材効果を変更しない。表示はRetina scale、120ms resize debounce、要求寸法の8Mpixel枠に合わせる。限定したRelease計測では6000 pathの4解像度で準備時間込み約20%短縮し、pencilの重いfilterは改善が小さかった。全作品・全処理の同じ改善率を保証しない。

質感filterの共有worker poolはmacOSで最大4、他OSで最大2とし、利用可能なCPU並列数へ制限する。Androidの逐次実行、並列化の閾値、axis table上限と描画計算順を保持する。Apple Siliconの公開pencil一例を4320²・2048側・9tileで描く限定Release計測では、warm2回の平均が約3.75秒から約3.04秒へ19%短縮し、全tileを固定順に連結したraw pixel digestが一致した。独立したupstreamとの並列region1caseも全pixel一致。全作品の同率改善、実画面のp95、app全体memory、Intel実機の最適値を保証するものではない。[resvg改修記録](../core/vendor/resvg/INKU_PATCHES.md)に条件と再現入口を記す。

### 確認範囲

実coreと一時DBによるauthoring、比較候補の明示保存／取消し、batchの固定条件と不明行、保存pluginの固定、prepared scene／image cacheの限定確認は成功した。辞書、library、SQLite移行・backup、exportとtileの境界も具体的な失敗に対応する確認で扱った。Personal接続のidentity、SSE、loopback、refresh取消し・quota・model解決はsynthetic署名とmock transportで確認し、実本人認証へ読み替えない。

更新したunsigned Universal appは両CPUでlinkし、最低OS14を保持した。Apple Silicon／macOS27.0.1の一時DBでDDL生成、編集child、libraryのcomment／star、trash／復元、restart後の保持、日英切替、親子の系譜と全体表示、Stringの正しい改訂番号、複数選択2作品のPNG2160書出しを実画面で確認した。出力2fileは両方2160×2160で、画像の質感も視覚確認した。起動時のページサイズ再帰、シートの空選択、Foundationの保存option組合せによる終了を修正した。作者の通常利用、他exportのnative・性能、実provider／OAuth、Intel／macOS14実機、署名・配布、iOS app／cameraの受入は残る。

追加の限定確認では、制作で選んだmodelが実際のrequest両段へ反映され、保存default・開始済みtemplateが変わらず、provider呼出し0件であることを確認した。SQLiteの世代projectionはroot・child・欠落・削除祖先の1件を確認した。nativeでは1320×880と標準tileの1281×733で固定生成button・canvas・履歴、世代1／2、設定／移動／新規／読込取消し、model設定categoryへの導線、系譜focusと表示作品の分離、library2件と制作1件の書出し対象を確認した。小さい幅の全配置、VoiceOver、作者のデザイン受入をこの代表確認へ読み替えない。

保存作品編集の限定mock／共通core確認では、live executionのない親の再表示、固定した保存条件・plugin lockと次のmodel、写生の生成し直し、child保存後のDDL authority、停止後の遅い応答拒否を確認した。nativeでは記述／写生dialogのdraft取消し、色カタログの取消しと次の条件への確定、日英の色名とHEX、標準panelから単一DDLを読み込む操作を確認した。親cardをscroll領域へ移した後は、同じ親の記述→取消し→写生→取消し→記述で画像・記述と元draftを確認し、history・系譜全行は不変だった。Finder dropは操作ツールでは成立しなかったが、その後、作者が最新Release Universalアプリの制作画面へ単一DDLファイルをdropし、入力が `place one green square at center.` に変わったことを確認した。画面の読取確認でも期待DDLと「DDLを読み込みました。」の通知を確認し、隔離DBのhistory・系譜node・edgeの行数は読込前の2・2・1を保持した。生成前の単一DDL読込についてFinderからの実操作を受入済みとする。実providerの編集生成は未受入である。

描画要素の限定mock／共通core確認は、2^53を超える語句seed、seed0の配置fallback、保存Score／色／DDLとprovider0件、固定4案、現行変奏の同一性、読み取りmodel、採用前の通常履歴保持、二重採用・再表示後のDDL child、編集edge補助項目と旧Codable、停止の遅い応答を確認した。Rustの語句seedと新しいPyO3から実Server helperへの限定確認も成功した。Debug Universal appの一時DBでは、タッチ1案のseed表示と破棄、配置4案から選択2案だけの保存（通常履歴2件から4件）、640px幅の比較画面、候補への自動scroll、変奏の「動いたもの: なし」、閉じた後に準備中表示が残らないことを確認した。実provider・全幅・VoiceOver・作者受入は別の確認である。

追加の`--replay-comparison-only`は実Rust・一時SQLite・provider0件で、保存／現行SVG・版、seedの優先順と暫定0、未設定composition、履歴・系譜・表示・execution不変、古い親／tokenと停止後の応答拒否を確認した。`--auxiliary-provenance-only`は実Rustとmockで、2世代のVision来歴、randomへの古い助言混入防止、親子・中間作品・固定条件と呼出し予算を確認した。Release Universalのnative画面では制作と系譜の保存情報から比較を開き、狭い画面で両画像と版をscrollして確認した。close後もhistory2件・節点2件・edge1件・execution2件の全行が一致した。

Rust 1.95のmacOS host proc-macro stripによるLINKEDIT alignment失敗は、release buildのhost build dependencyだけ`strip="none"`へ変更して回避した。target archiveの最適化とstrip設定は保持し、最新Mac coreとunsigned Release Universal appの両CPU buildが成功した。最低OS14を保持する。これはIntel実機、macOS14実機、最新iOS artifactやRelease性能の受入ではない。

追加の`--provider-progress-only`は実Rustとmockで最初の失敗後の1回の再試行、固定model・段階／試行時計・未記録usage、完了／停止の時間確定、比較callback・終了待ち・古いtoken拒否と表示解除を確認した。`--model-guidance-only`は一時DBとprovider0件でServerの段階別評価、LLM／Visionの区別、日英comment、速度の公開範囲、未登録境界、両画面のIDと選択・保存default・既存snapshot保持を確認した。更新したRelease Universalの隔離画面では制作と設定の評価5／2・両段2、登録資料と未取得の接続先情報、loopback模擬providerの429後の再試行2／4と経過表示を確認した。停止後に時計が確定し、新規で状態cardが消え、history2件・節点2件・edge1件の全行が一致した。これは実providerの性能・model取得・推論や全幅の受入ではない。

構図のhost確認は実Rust／mock／一時DBでStage 1から構図・保存への接続、modelと上限、schemaの`propertyOrdering`、有限retry／fallback、欠落／`read:false`設定と保存Score再生の保持を確認した。最終Personal ChatGPT guardは非UUIDのfixtureを修正し、`--composition-personal-plan-gate-only`だけで未接続の拒否、action identity保持とHTTP／credential呼出し0件を確認した。`--composition-progress-only`は段階切替、構図の再試行、日英表示、prompt履歴からの除外と停止後の遅延応答拒否を確認した。更新したRelease Universalの別隔離画面ではloopback mockの2要求で構図の応答待ち・完了、固定model、構図印と明示した場所を含むDDL、作品と履歴への保存を確認した。historyとnodeは2件から3件へ、edgeは1件のままで、既存全行と既存execution2件を保持した。この構図接続確認の時点では、実ChatGPT／API providerの受入と段階別usage／raw SSE保存は未完了だった。

追加の`--provider-observation-only`は実Rust・mock・一時SQLiteで下絵／構図の別time・実usageと明示0、作品保存・Host再作成／再表示、rawを持たない通常metric、旧optional欠落の読出し、保存Scoreの再演奏／再現比較で新provider要求がないことを確認した。送信前CAS失敗はHTTP0／retryなし／restore時の自動再送なしで、開発者モード外の明示要求もtransport前に拒否した。通信側は限定XCTest1件で通常JSONとPersonalの完了SSE、実schema／上限／identity、既知credentialのescapeを含む除去、送信前保存失敗と途中SSEのstatus／受信prefixを確認した。記録確定時のSwift排他アクセス衝突を修正し、同じ1件が成功した。64MiB超過の実行確認や実provider／OAuthの受入は含まない。

更新したunsigned Release Universalの別隔離アプリでは、loopbackの下絵266ms／usage11・7、構図757ms／usage13・0を独立表示し、開発者欄の2件の通信記録と構図応答本文を読めた。「新規」で進行表示を解除し、保存作品の再表示で同じ実測値を保持した。history／node／executionは3件から4件、edgeは1件のままで、既存全行が一致した。元の作者手動drop用アプリとFinderは保持した。両CPU build・最低OS14を確認したが、Intel／macOS14実機・全幅・VoiceOver・作者の通常利用の受入は別である。

送信予算の限定XCTest1件は模擬HTTP・時計・一時SQLiteで成功した。既知schema2の作品保持とv3移行、別接続の最終枠の排他予約、62秒／90%・Gemini入力計測と精算、unknown usage、429・日次、旧JSONの一度限りの取込と旧backup復元時の予算保持を確認した。入力超過・期限・破損記録・書込失敗の代表ケースは生成HTTPを出さない。論理保存契約v2とSwift物理schema3／10tableの照合も成功し、既存9tableの定義を保った。

更新したunsigned Release Universalの隔離画面（1320×880）でGeminiの未設定時の30／16,000／14,400、独立した説明buttonとpopover／Escape、明示0の保存・設定再表示と負値の拒否を確認した。負値の保存試行は設定JSONを変更せず、作品4件・node4件・edge1件・execution4件・ACK8件を含む既存全行を保持した。送信予算tableは0行で、新しい生成や一覧取得を要求しなかった。両CPU・最低macOS14を保持し、実providerの利用枠・Intel／macOS14実機・全幅・VoiceOver・作者の受入は未確認である。

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

restoreは生成中のUIから開始できず、hostの実行を停止してから行う。原backupを読み取り専用に保ち、隔離snapshotを検証してBackup APIでactive DBを置き換える。成功後はapp modelのexecutionと選択・表示をresetし、作品を再読出しする。Contentの復元revisionでlibrary previewを閉じ、demo／batchの観測作品、制作・プレゼンテーションの一時snapshotを破棄し、library状態・世代一覧・選択位置を復元DBから読み直す。DB backupには作品・系譜・execution／snapshot／ACKが入り、隣接provider JSONとKeychain credentialは含まれない。

自動backup世代管理は上記の端末保守機能で扱う。FTS、旧Server／Android DBや旧JSONのimportは未実装である。固定Unicode空白集合による旧本文選択helperは、import機能の完成を意味しない。

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

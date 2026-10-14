# inku Swift 実装仕様

このディレクトリは、macOS先行のnative SwiftUIクライアントとApple向け共通packageのworkspaceである。本書をSwift host固有の仕様正本とし、[SWIFT_SPEC.md](SWIFT_SPEC.md)を対応英語版とする。共有DDL、Score、prompt、authoring authority、pipeline状態遷移、seed、描画の意味は[製品仕様](../SPEC.ja.md)を正本とし、Serverを開発上のprimaryとして同じRust coreへ追随する。Swift側に意味処理を複製しない。

最終更新: 2026-10-14。

binding／protocolの版は同梱Rust coreのversion report、描画層の版はrender metadataと[Serverの層定義](../server/src/inku_server/layer_versions.py)を参照する。本書へ共通engineの版定数を複製しない。macOSアプリの版は`apple/VERSION`と`apple/BUILD_NUMBER`を正本とする独自の版で、Server／Webの版とは別に採番する（初回は1.0.0／Build 1）。対応するServerの版はアプリの「inkuについて」と変更履歴に併記する。共有層の版が一致しても、host機能とnative UIの移植が完了したことにはならない。

## 更新ルール

- `SWIFT_SPEC.ja.md`をSwift仕様の正本とする。
- Swift仕様を変更するときは日本語を先に更新し、その意図を保った翻訳・要約として`SWIFT_SPEC.md`を同期する。英語版だけに仕様・要件を追加しない。
- 確定した実装変更と残る範囲は本書の日付付き節へ記し、製品の変更履歴は共通の[CHANGELOG.ja.md](../CHANGELOG.ja.md)／[CHANGELOG.md](../CHANGELOG.md)へ同期して記す。Swift専用CHANGELOGを分けない。
- 共通の意味や保存契約を変更する場合は、それぞれの正本を更新する。本書はSwift hostの適用範囲を説明し、独自の共通仕様を作らない。
- sourceと再現手順を公開文書に記す。生成binary、model、log、credential、端末識別子や非公開の作業記録を追跡対象に含めない。

## 2026-10-14 系譜詳細から推敲メニューを開く

系譜の節点の「保存情報・コメント」にある「推敲する」は、共通の作品推敲メニューを開く。その作品で使える配置・色カタログ・てざわりなどの項目と制約を他の入口と共有する。選んだ操作には押した節点の保存作品を渡し、表示中の別作品や制作欄の書きかけを対象にしない。削除済みの描画パラメータ編集への経路は使わない。

## 2026-10-14 読み取りとタッチの推敲を削除

作者の決定（製品SPEC §8.4）に合わせ、推敲の「読み取りを変える」と「言葉でタッチを変える」を削除した。

- 中身がなくなった「描画パラメータの編集」メニューと要素選択・言葉入力・その保存設定を削除する。「配置を変える」は独立した入口に残る。記述そのものの編集と通常の新規描画、モデル比較は保つ。
- 自律推敲とVision助言の要素は色カタログ・配置の2つ。古い設定の`reinterpretation`と`touch_change`は選択と要求から除き、新しい手動／自律要求も受け付けない。方向性の入力欄はVision方式だけに表示し、助言の材料にだけ使う。方向性や助言を描画の記述に加えない。色の世代は記述の作品でも親の保存DDLから別の色カタログで描き、Stage 1を呼ばない。
- 保存済みの`touch_change`と`reinterpretation`の辺と「タッチ／Touch」「解釈／Reading」のラベル、作品に残る`seed_text`と`interpretation_seed`の生成情報表示は保持する。描き直しは保存した`render_seed`を使い、言葉を種へ変換しない。描画seedが未記録の旧作品は従来の暫定0と注意を保つ。
- 同梱Web文言とツールチップ照合表から削除済みキーを外す。以下の過去の確認記録は、その時点での記録として保持する。

## 2026-10-13 文言の写しをBuild 1190のWebから作り直す

作者の指示（Server Build 1190との差の取り込み、段G）。

- `ui-reference.json`を`export-web-reference.mjs --source-root`でmain `d5659751`（Web/Server v2.15.114、Build 1190）から作り直した。「Inku について」の対応するServerはv2.15.114（Build 1190）。
- Swiftが直書きの鍵で名指すWebの文言は206で、日英とも写しに全部ある。1162から文が変わったのは、ChatGPTプランの案内2つと「配置を変える」のツールチップ。
- 段E（モデル設定の表示：用途のバッジ、3段階の推奨度、概算コスト、平均秒数、計測で応答の無い用途、公開できないモデルの折りたたみ、ChatGPTプランの共有の評価）は作者の決定で後回し。対応するServerの表示がBuild 1190でも、これらはSwiftに無い。新しい表示の値はServerのコードの既定値に無く、Serverの設定の保存にだけある。
- 段A〜Cで`Localizable.strings`に足したWebと同じ文はそのまま使う。
- 確認：写しの版（1190・v2.15.114・`d5659751`）、名指す鍵の有無、AppCheck `--tooltips-leftovers-only`。

## 2026-10-13 指示書で歳時記の語とマクロの名を補完する

作者の指示（Server Build 1190との差の取り込み、段C-3）。正本はWebの`features/ddl-editor/codemirror.ts`の`ddlCompletions`。

- 指示書の箱とエディタで、カーソルの前の語の始まり（大文字小文字は問わない）に合う候補を、macOSの補完の一覧で出す。候補は指示書の言語（`AppModel.instructionLanguage(for:)`）の歳時記の語と、マクロの名（日本語は別名の1つ目、ほかは修飾名、Webの`pluginDisplayName`）。有効なプラグインの語だけ。
- 一覧は作者が打った時だけ開き、選ぶまで文を変えない（初めは何も選ばない）。語を選んで入れた時・名前の追従・外から文を戻した時は開かない。読み取り専用・変換中・開いた範囲の数の中では出さない。
- 語の始まりは、カーソルの前の空白・句読点・記号の無い並びのうち、候補の始まりに合う最も長いもの。英字の語の途中からは始めない（`.`と`_`は語の中に含める）。日本語は区切りが無いので、候補に合う最も長い末尾を取る。Webは曖昧な一致で並べるが、Swiftは始まりの一致だけ。
- 確認：AppCheck `--ddl-box-only`（本物の歳時記とマクロで、日本語・英語・別名・修飾名が出ること、英字の語の途中・空白の後・開いた範囲では出ないこと）。

## 2026-10-13 指示書の数の範囲を畳み、絵の上で確かめ、打ち直す

作者の指示（Server Build 1190との差の取り込み、段C-2）。正本はWebの`composition-ranges.ts`・`codemirror-ranges.ts`・`DdlViewer.svelte`・`DdlRangePreview.svelte`。

- 指示書の箱とエディタは、共有coreの範囲の表（`InkuCore.compositionRanges`、`inku.composition-ranges.v1`、32の範囲）と名前と数が一致する範囲の数（と古い［構図］の印）を、文を変えずに隠す（glyphを出さない）。名前には点線の下線。カーソルが範囲に入ると開き、その場で数を打ち直せる。数を直した後に範囲を離れると、名前が表の数に追従する（表に無い有効な数は「指定の範囲」、自分で書いた語は保つ）。名前を直したら追従しない。変換中は書き換えない。コピー・保存・描画は数を含む全文。
- カーソルが入っている範囲、または名前に乗せている範囲の枠を、作品の絵の上（拡大・移動に従う）に出す。無効な数は最後の有効な枠を破線で保つ。無効な範囲があれば書き方の例の案内を出し、「指示書から描画」・確定・描くを押せない。日本語は「-」「－」、英語は`to`に加え`-`と`–`を範囲のつなぎに読む。
- 範囲の読みはWebの`composition-ranges.ts`を写した（数は分母100万までの整数の分数）。
- 確認：AppCheck `--composition-ranges-only`（Webの試験の例と、畳み・開き・枠・追従・最後の有効な枠、画面に出さない実際の編集欄で数だけが隠れること、40）。

## 2026-10-13 指示書の箱で全文を編集し、「指示書エディタ」と「編集を破棄」を入れる

作者の指示（Server Build 1190との差の取り込み、段C-1）。正本はWebの`DdlViewer.svelte`・`DdlEditorDialog.svelte`。

- 作品の指示書の箱は、行番号の無い編集欄（語の色分けと補完の範囲の印はエディタと同じ）。表示中の作品ごとの下書きとして全文を直せ、打つだけでは描かず、「指示書から描画」で下書きを一度描く。描画中・保存していない作品・ゴミ箱では読み取り専用。表示する作品が変われば、その作品の指示書から始まる。
- 箱のボタン・作品編集メニュー・作品のエディタの題は「指示書エディタ」。エディタは箱の下書きで開く。
- 作品画面の歳時記で選んだ語は、箱が編集できるとき箱のカーソル位置へ、箱をまだ触っていなければ末尾へ入る。そうでなければ見本だけ。
- 「編集を破棄」を箱と作品のエディタに置く。確認の後、作品を描いたときの指示書へ全文を戻す（1回の取り消し単位）。同じ文・読み取り専用・描画中は押せず、新規のDDLのエディタには出さない。エディタで戻しても箱の下書きは変わらない。
- 確認：AppCheck `--ddl-box-only`。

## 2026-10-13 構図の選び直し（原理に沿う／偶然に委ねる）と「配置を変える」の移動

作者の指示（Server Build 1190との差の取り込み、段B）。正本はServerの`_recompose`・`compose`とWebの`recomposition.ts`・`RefinementAdjustView.svelte`・`WorkActionMenu.svelte`。

- 「配置を変える」は作品編集メニューから配置だけの画面を開く。「描画パラメータの編集」は2026-10-14に読み取り・タッチの推敲とともに削除した。配置の画面は「原理に沿う」（既定）か「偶然に委ねる」を選ぶ。
- 候補ごとに新しい構図の種を引き、共有coreの`recompose`（その候補の設定、保存した指示書、選び方、種、作品のIDは`sha256:`と指示書のSHA-256）で、数で書いた範囲を選び直す。指示書が変わった候補は、選び直した指示書を保存した作品の子として直接のDDLで描く（補完の範囲の控えは渡す）。変わらない候補は保存した指示書の文書のまま描く。読めない答え・呼べないときは範囲を保つ（Serverと同じ理由の値）。継ぎ目の句のある指示書はcoreの`recompose`が組み直す。
- 候補の札には動いた層と範囲（`層: 前 → 後`、層は1から）を出し、動かせないときは理由と「指示書は変えず、配置の seed を変えて描き直しました。」を出す。`unplaced_sentence`は「範囲も場所も書かれていない文があるため、指示書の範囲は選び直せない。」と説明する。範囲を選び直せない場合も、元の指示書を配置の seed だけ変えて描き直す。採用した子の系譜の辺の付記に`composition_seed`と`recompose_mode`を残す。AIプロセスの配置も「原理に沿う」で選び直す。
- 確認：AppCheck `--recompose-only`（本物のcore）、`--refinement-only`。

## 2026-10-13 補完が書いた範囲の控えと3つの状態

作者の指示（Server Build 1190との差の取り込み、段D2）。正本はCHANGELOG「2026-10-11 — 補完が書いた範囲の控えと3つの状態（A3）」とServer・Webの`70d47cab`。

- 承認した補完が書いた数の範囲の控え（共有coreの`completion_ranges`、`inku.completion-ranges.v1`）を、作品を保存するときに作品の文脈へ残す。保存した作品から直接のDDLを描くとき（指示書を直して描き直す、保存した指示書のまま条件を変えて描く）は、その控えを共有coreへ渡す。言葉を直した範囲は補完へ回り、数を書き直した案の承認を求める。
- 指示書の編集欄と本文の欄は、共有coreの`completion_range_states`で範囲ごとに「補完」「数を直した」「言葉を直した」を求め、状態ごとの色の点線の下線で示し、欄の下に状態の名前と数を出す。言葉を直した範囲があれば「言葉を直した範囲が n つあります。描くと補完がその範囲の数を書き直し、承認を求めます。」を出す。求めるのは文が変わって0.18秒後で、文が変われば消す。表示中の作品が今の実行のものなら実行の控え、そうでなければ保存した作品の控えを読む。Webは範囲の終わりに札を挟むが、Swiftの編集欄は文を変えずに札を挟めないので、色と下の一覧で示す。
- 確認：AppCheck `--completion-ranges-only`（本物のcoreで、補完の承認から保存、3つの状態、作品を選び直した後に言葉を直して描くと補完が求められる）。

## 2026-10-13 補えなかった箇所の原文と理由、問い直し中を表示する

作者の指示（Server Build 1190との差の取り込み、段D1）。正本はWebの`holeCompletionIssues`・`PipelineStatus.svelte`・`providerAttemptText`。

- 補完が止まったとき（段が`needs_user_edit`か`failed`で、理由が`hole_completion_failed`か`hole_completion_context_limit`）と、変更案の承認を待つときに、指示書の補完の画面へ「補えなかった箇所」を出す。共有coreの`hole_completion_check`のうち断られた（`rejected`）・解けなかった（`unresolved`）穴ごとに、作者の原文と平易な理由を出し、通った穴は出さない。理由の文はWebと同じ（文脈が長すぎた場合も含む）で、知らない理由は「検査で断られた（符号）」と出す。
- 案が検査で断られた後の試行（試行の報告の`asked_again`）は「断られた案を理由を添えて問い直し中 n/m」と出し、通信の再試行と分ける。
- 確認：InkuHostの`HoleCompletionIssueTests`（出す条件と出す穴）、AppCheck `--completion-issues-only`（理由の文と`asked_again`）。

## 2026-10-13 前回のバッチのエラー作品だけを再描画する

作者の指示（Server Build 1190との差の取り込み、段F）。正本はWebの`BatchState.retryFailed`と`BatchPanel.svelte`。

- バッチが止まっていて失敗の行が残っていれば、結果の数の下に「エラー作品を再描画」を出す。押すと、失敗の行だけを、元の本文・行番号と開始時に固定した要求（描画条件・モデル）のまま描き直す。描き直しの中でも再試行の回数の設定は効く。待ち・要確認・省略・成功の行には触れない。成功した行は失敗・要確認の一覧から外れ、残った失敗はまた試せる。
- 確認：AppCheck `--automation-only`（成功1・失敗1・待ち1の記録で、送るのは失敗の行だけ、開始時のモデル、待ちの行は待ちのまま）。この確かめは「登録したモデルだけで描く」の後に材料がモデルを登録しておらず落ちていたので、モデルを登録した。

## 2026-10-13 Claudeの思考の出力枠と、上限で切れた応答の記録をServerに揃える

作者の指示（Server Build 1190との差の取り込み、段A）。正本はServerの`anthropic_request.py`・`gemini_request.py`・`openai_request.py`・`pipeline_provider.py`・`vision_client.py`。

- Claude 5（opus・sonnet・haiku・fable・mythosの5）とMythos Previewは、描画・Vision・デモのどれでも`max_tokens`へ8,192を足す（`ProviderOutputLimit.anthropicMaxTokens`）。Claude 4系は足さない。
- 描画で上限に当たって切れた応答（Claudeの`stop_reason: max_tokens`、Geminiの`finishReason: MAX_TOKENS`、OpenAI互換の`finish_reason: length`、Responsesの`incomplete`／`max_output_tokens`）は、どの社でも答えにせず`malformed_payload`で拒む（Geminiは前は`provider_output_limit`でprovider_rejectedに分かれていた）。
- 切れた応答は、システムログ（subsystem `app.inku`、category `provider`）にServerと同じ1行`provider_output_limit {…}`を残す。JSONは鍵を名前の順に詰めて書き、`action`・`provider`・`model`・送った本文の上限`max_tokens`と、社ごとの項目（出力・思考／推論のトークン数、本文・関数呼び出しの有無など、無い値は`null`）を持つ。本文・推論文は含めない。Visionは切れた応答をそのまま返し、同じ行（`action: vision`）を残す。デモは残さない。この節より前の節の書き方（`unknown`、Geminiの`provider_output_limit`）はこれに改めた。
- 有料プラン限定の確かめ（Ollama Cloudの1トークンの要求）は、402も403も有料プラン限定と読む。
- 見送り：ChatGPTプランのストリームのerrorイベントの`param`は残さない。Swiftはこの値を画面にも記録にも出さない。
- 確認：InkuHostの`ProviderOutputLimitTests`（Claudeの出力枠、Claudeの切れた応答の拒否、4つの記録の項目と記録の行）、`ProviderModelCatalogChecks`（402）、`GeminiThinkingLevelTests`ほか。

## 2026-10-13 OpenAI APIの描画をResponsesへ移し、推論設定をServerに揃える

OpenAI互換の接続先ホストが`api.openai.com`のときだけ、Serverの[`openai_request.py`](../server/src/inku_server/openai_request.py)と同じ要求・応答処理を使う。公式仕様は[推論モデル](https://developers.openai.com/api/docs/guides/reasoning)と[GPT-6案内](https://developers.openai.com/api/docs/guides/latest-model)を参照する。

- 描画pipelineは非streamの`POST /v1/responses`を使う。本文は`model`、`store: false`、システムプロンプトの`instructions`、ユーザー本文の`input`、`submit_pipeline_response`のfunction tool（coreのschemaをそのまま`parameters`へ、`strict: false`）、`tool_choice: required`、`parallel_tool_calls: false`、`max_output_tokens`。推論指定があるときは`reasoning: {effort}`、温度を送るときは`temperature`を加える。
- 推論系`^(gpt-5|gpt-6|o\d)`には温度を送らない。そのうち`^(gpt-5\.\d|gpt-6-(sol|luna)(-|$))`は推論を`none`、それ以外（GPT-6 Astra・GPT-6.1 Sol・GPT-5無印・o系など）は`low`とし、答えの上限に25,000を足す。推論系でないモデルには従来の温度を送り、推論指定を付けない。
- `status: completed`だけを採用する。`output`のfunction callがちょうど1件で、nameが一致し、argumentsが文字列なら、その文字列を返す。function callが無いときはmessageの`output_text`をつなぐ。未完了・不正なcall・空の答えは`malformed_payload`で拒否する。
- `status: incomplete`かつ`incomplete_details.reason: max_output_tokens`では、`provider_output_limit`、出力・推論トークン数、messageとfunction callの有無をシステムログへ記録する。本文・推論文は記録しない。入力使用量は`usage.input_tokens`から取り、既存のレート管理と使用量報告へ渡す。
- Vision・奥書・デモはChat Completionsのまま、同じモデル判定を`max_completion_tokens`と`reasoning_effort`へ反映する。他のOpenAI互換providerのChat形式と、ChatGPTプランのSSEは変更しない。
- 確認：InkuHostの`OpenAIResponsesTests`で、両APIの要求、modelごとの指定、公式ホスト以外の対照、HTTPを注入した実transportの応答採用・拒否、SQLiteの入力トークン記録と報告使用量を確認する。

## 2026-10-13 NVIDIA NIMのGemma 4の思考を切る

NVIDIA NIMへの描画・Vision（推敲の助言・奥書）・デモの指示文は、Serverの[`openai_request.py`](../server/src/inku_server/openai_request.py)と同じくGemma 4の思考を切る（[NIM API仕様](https://docs.api.nvidia.com/nim/reference/google-gemma-4-31b-it-infer)）。

- OpenAI互換の接続IDが`nvidia`で、モデル名の最後の`/`より後ろが`^gemma[-_]?4([-_]|$)`に一致するときだけ、大文字小文字を問わず`chat_template_kwargs: {"enable_thinking": false}`を送る。3経路で同じ判定を使う。
- 他のNIMモデルや他providerにはこの指定を付けない。`max_tokens`と`temperature`は既存の値を保持する。公式OpenAIのURLでは既存の公式API指定を使う。
- Swiftは生のJSONを組むため、`chat_template_kwargs`を要求本文へ直接入れる。SDK用の`extra_body`へは包まない。
- 確認：InkuHostの`NIMGemmaThinkingTests`で、3経路の送信JSON、出力枠・温度、他モデル・他providerの対照、大文字小文字とモデル名の境界を確認する。

## 2026-10-13 Ollamaの推論指定と出力枠をServerに揃える

Ollamaローカル・Cloudへの描画・Vision（推敲の助言・奥書）・デモの指示文は、Serverの[`openai_request.py`](../server/src/inku_server/openai_request.py)と同じ推論指定を使う。

- OpenAI互換の接続IDが`ollama`または`ollama-cloud`のとき、モデル名が`^gpt-oss(:|-|$)`に一致すれば`reasoning_effort: low`を送り、`max_tokens`に8,192を足す（描画2,048→10,240、助言320→8,512、デモ180→8,372）。ほかのモデルは`none`を送り、出力枠を増やさない。判定は3経路で共通とする。
- このOllama向けの指定は、他providerへ付けない。公式OpenAIのURLでは、Serverと同じく公式API用の既存指定を使う。根拠となるproviderの仕様は[OpenAI互換API](https://docs.ollama.com/api/openai-compatibility)と[thinking](https://docs.ollama.com/capabilities/thinking)を参照する。
- OpenAI互換の描画応答の先頭候補が`finish_reason: length`なら、本文やtool callが揃っていても答えとして使わず、`malformed_payload`で拒否する。システムログ（subsystem `app.inku`、category `provider`）に`provider_output_limit`、終了理由、提供元が返した出力・推論トークン数（不明なら`unknown`）を残す。本文・推論文はログに含めない。coreへの失敗の分類と再試行の扱いは変えない。
- 確認：InkuHostの`OllamaReasoningEffortTests`で、3経路の送信JSON、Ollama以外の対照、モデル名の境界、推論だけ／本文あり／tool callありの打切り応答の拒否を確認する。

## 2026-10-13 Geminiの要求とデモのClaude要求をServerに揃える

Geminiへの描画pipeline・Vision・デモの指示文は、Serverの[`gemini_request.py`](../server/src/inku_server/gemini_request.py)と同じモデル判定・出力枠を使う。2026-10-12の判定を更新する。

- 判定前に先頭の`models/`を外す。`^gemini-2\.5-flash-(lite|image)(-|$)`と`^antigravity-`は`thinkingConfig`を送らない。
- `minimal`を送るのは`gemma-`で始まるものと、次の13名の完全一致だけ：`gemini-3.6-flash`、`gemini-3.5-flash`、`gemini-3.5-flash-lite`、`gemini-flash-lite-latest`、`gemini-3-flash-preview`、`gemini-3.1-flash-lite`、`gemini-3.1-flash-lite-preview`、`gemini-3.1-flash-image`、`gemini-3.1-flash-image-preview`、`gemini-3.1-flash-lite-image`、`gemini-robotics-er-2-preview`、`nano-banana-pro-preview`、`gemini-nano-banana-2.1`。ほかは`low`を送る（新モデルとFlash／Proのlatest別名を含む）。
- 思考レベルを送るモデルは`maxOutputTokens`に8,192を足す。送らないモデルは答えの枠のまま。描画・Vision・デモはいずれもGeminiへ`temperature`を送らず、提供元の既定を使う（[GoogleのGemini 3案内](https://ai.google.dev/gemini-api/docs/gemini-3#temperature)）。
- 描画の応答の先頭候補が`finishReason: MAX_TOKENS`なら、関数呼び出しが揃っていても答えとして使わず`provider_output_limit`で拒否する。Vision・デモは`thought: true`の部分を本文に混ぜない。
- デモのClaude要求は`temperature`を送らない。Serverの[`anthropic_request.py`](../server/src/inku_server/anthropic_request.py)と同じ判定（`^claude-((opus|sonnet|haiku|fable|mythos)-5(-|$)|mythos-preview(-|$))`）に該当するモデルだけ、`max_tokens`へ8,192を足す。Claudeの描画・Visionの枠はこの変更の対象に含めない。
- 確認：InkuHostの`GeminiThinkingLevelTests`で3経路の送信JSON、設定の省略と出力枠、打切り応答の拒否、Claudeデモの温度省略と出力枠を確認。`AuxiliaryServerParityChecks.testAnswerTextFollowsServerReaders`でデモへの思考文の混入を拒ぐ。

## 2026-10-12 左下に版とBuildを常に出す

作者の指示「アプリの左下に、バージョン番号とビルド番号を常時表示する」による。

- 左端の操作列（[`AppRailView`](Sources/InkuUI/Views/AppRailView.swift)）の一番下、窓の左下に、アプリの版とBuild（`apple/VERSION`・`apple/BUILD_NUMBER`から入る`CFBundleShortVersionString`・`CFBundleVersion`）を出す。畳んだ列では`1.1.2`と`Build 4`の2行、広げた列では`1.1.2 · Build 4`の1行。
- 見た目はWebの操作列の一番下のBuildの表示（`.rail-build`）に合わせる：10pt、淡い文字、等幅の数字。ツールチップは`Build 4`。
- Webは開発者モードのときだけBuildを出すが、macOSはUIモードや補助表示に関わらず常に出す。
- 確認：AppCheck `--tooltips-leftovers-only`（Webのツールチップ173か所との照合。Buildの表示を除外から対応へ替えた）。

## 2026-10-12 照合表にlinearGradientを足す

作者の目視の間に、linearGradientを含む作品の表示が照合表の外として止まった。作者の指示（調べて計画を出す、実装する）による。

- 照合表（共有coreの[`inku-display`の`check.rs`](../core/crates/inku-display/src/check.rs)）に、要素`linearGradient`と属性`color-interpolation`を足した。`color-interpolation`は値が`sRGB`のときだけ照合表の中で、ほかの値は今までどおり外（符号`attribute`）。
- 描画はlinearGradientを、地の墨のにじみの帯と、computerの塗りで書く。どちらも止まりの`offset`・`stop-color`・`stop-opacity`だけを使い、塗る`path`の外接矩形に合わせる（既定の単位）。Skiaの`SkSVGLinearGradient`はこれをChromeと同じに描く。`color-interpolation`はSkiaのグラデーションでは読まれず、描画が書く値（`sRGB`）は既定と同じ。
- 描き比べ（2026-10-12）：linearGradientを含む作品38件をSkiaとChromeで描き、照合表に入る37件すべてが作者の物差しで一致した。墨のにじみは薄く、作品の中では物差しに見えないので、帯を濃く描いた合成の作品で、一致することと、帯を抜くと一致しないことを確かめた。拡大の窓（Graphite）もCPUと一致した。
- 照合表は共有なので、Androidでもこれらの作品はresvgではなくSkiaで描かれる。
- 残る範囲：古い作品（描画エンジン41まで）の`feFuncA`の`tableValues`は照合表の外のままで、macOSでは表示が止まる。
- 確認：共有coreの`inku-display`のSkiaの試験（C1・C2・C4と、2種のlinearGradientがChromeと一致し、抜くと一致しない試験）、照合表の外の判定の試験、`inku-display-gpu`の試験（G2に2件を足した）。

## 2026-10-11 拡大の窓をApple SiliconではGraphiteで別のプロセスに描かせる

作者の指示「Graphiteを導入して」と、作者の決定（2026-10-11）による。拡大の速さをWebのChromeに近づけるため。

- 範囲：Apple Siliconの作品域で、拡大した窓だけをSkiaのGraphite（GPU、Metal）で描く。100%の全体は今までどおりCPUのSkia（粗い全体の後にタイル）。Intel（x86_64）とRosettaでは、窓も今までどおりCPUのタイル並列。
- 別のプロセス：窓は、アプリの`Contents/MacOS/inku-display-gpu`（Rust。共有coreの[`inku-display-gpu`](../core/crates/inku-display-gpu/Cargo.toml)、arm64だけ）が描く。[`DisplayRenderer`](Sources/InkuUI/DisplayRenderer.swift)は最初の窓で起動し、標準入力でSVGのSHA-256・窓・SVG（そのプロセスに初めての作品だけ）を渡し、標準出力から窓の画素（premultiplied RGBA8）を受け取る（[`DisplayGPUProcess`](Sources/InkuUI/DisplayGPUProcess.swift)）。窓の置き方はCPUの窓と同じ関数（`DisplayScene::paint_region`）を通る。頼みは1度に1つで、待つ間に画面が先へ進んだ頼みは送らない。窓は途中の絵を出さず、完成した窓を1回渡す。
- 落ちたとき：GPUのドライバが描画用のプロセスを終わらせても、アプリは終わらない。その頼みは`gpu_process_exited`（60秒答えなければ止めて`gpu_process_timeout`）の失敗になり、表示の失敗ログ（`display-failures`）に終わり方と描画用のプロセスの標準エラーの末尾を書く。窓は描かず、引き伸ばした全体を残す（2026-10-06の裁定と同じく、CPUで描き直さない）。その作品はその起動の間は頼み直さず、別の作品の窓で描画用のプロセスを起動し直す。描画用のプロセスが描けなかったとき（`gpu_*`の符号）も、止めてログに書く。
- 見え方：Graphiteの窓は、feTurbulenceで作る質感の粒の位置が、CPUとChromeとわずかに違う（2026-10-11の調査で、作者の124件のうち43件がChromeとの一致の基準の外。縮小した全体ではほとんど同じ）。100%の全体はCPUのままなので、Chromeとの一致の確認（C1）は全体について今までどおり。
- 重さ（Apple M5 Pro、4倍の窓1800×1400）：作者の最大の作品で0.03秒（CPUのタイル並列は0.52秒）。描画用のプロセスの起動を含む最初の窓は0.45〜0.73秒。
- 部品：Graphite・Metal・SVG・WebPを一緒に含むSkiaの事前ビルドは公開されていない。`scripts/skia-graphite-binaries.sh`がskia-bindings 0.153.3のsourceから組み（macOS 26.5のSDKとninja v1.13.2が要る。Xcode 27のSDKではbindgenの出力がコンパイルできない）、ほかの事前ビルドと同じ置き場に置く。SHA-256は`core/crates/inku-display-gpu/skia-binaries.sha256`に書き、`build-core.sh`がbuildのたびに照合する。`build-core.sh`は置き場の部品だけを使い（`no-compile`）、Skiaを組まない。アプリはarm64の描画用のプロセスの分（strip前で約17MB）大きくなる。通知は自前のcrateが1件増えて136件。
- 確認：共有coreの`inku-display`のSkiaの試験（C1・C2・C4。CPUの描画を共有の関数に替えた後）、`inku-display-gpu`の試験（ノイズのない作品でGPUとCPUの窓が一致すること、受け渡しの形式）、AppCheck `--display-only <SVG>`（Apple Siliconでは加えて、窓が描画用のプロセスで1枚で描けること、画素の受け渡し、描画用のプロセスが落ちたときの扱い）。

## 2026-10-06 Skiaで描けない作品はresvgへ戻さず止め、原因を記録する

作者の裁定（2026-10-06）：「skiaが失敗した場合、フォールバックせずに、エラーの原因をログに書いて停止。それを元に、改修作業を行う。」

- 作品域（`DisplayRenderer`）は、Skiaで描けなかった全体・窓をresvgで描き直さない。照合表の外の作品、解析できない・Skiaで読めない作品、入力の上限、画素の領域を確保できない、coreの内部の不整合、CGImageを作れない、のどれでも同じ。全体は「作品を表示できません」と符号を出して止まる。窓は描かず、表示済みの全体を残す。
- 原因は、DBと同じフォルダの`display-failures/failures.jsonl`に1行ずつ書く（時刻、全体か窓か、符号、文、要求の大きさ、SVGのSHA-256と大きさ、表示APIの版、アプリの版とBuild）。失敗したSVGの写しを同じフォルダに`<SHA-256>.svg`として1つ置く。同じ起動の中で同じSVG・同じ段・同じ符号の失敗は1回だけ書く。設定に関係なく書く。システムのログ（subsystem `app.inku`、category `display`）にも出す。
- 診断の数は`fallbacks`から`failures`に改めた。`drawsWithSkia`を切ったときのresvgの経路（1箇所の切り替え）は残す。
- サムネイル、歳時記のプレビュー、書き出しはresvgのまま（変更なし）。
- 確認：AppCheck `--display-only`で、照合表の外の作品が止まり、ログに1行とSVGの写しが残ることを見る。

## 2026-10-06 窓の計算とタイルの合成をAndroidと共有する

作品域のSkia表示のうち、窓の密度・丸めとタイルの合成を共有coreへ移し、Androidと同じ実装を使う（AndroidへのSkia表示の導入のうち、Appleの受け持ち）。表示の結果と操作は変えない。

- `CanvasInteraction.detailPlan`は、拡大後の作品の矩形と見えている矩形をcoreの`display_detail_region`へ渡す。拡大率の判定と矩形の交差はSwiftに残る。式は前と同じ。
- `DisplayRenderer`は、タイルを複数のthreadからcoreの合成（`DisplayScene.composite`）へ渡す。タイルはcoreの中で描かれ、つないだ領域へ写される。タイルの画素はSwiftへ渡らない。完成した画像は、coreの領域をそのまま`CGImage`にする（写さない）。`CGDataProvider`がcoreの画像objectを保持し、最後の画像を手放すと領域も解放される。途中の絵はcoreで1回写したもの。取消はこれまでどおりタイルの境目で行う。
- coreは準備の失敗を`Unsupported`（照合表外・解析不可・Skiaで読めない）と`Refused`（入力の上限など）に分ける。Swiftの符号は前者が`code`のまま、後者が`refused_<code>`。失敗したときの扱いは次の節。
- Skiaとその中の部品の通知は、Androidと共有する一覧（`core/crates/inku-display/licenses/`、`scripts/skia_notices.py`）から読む。通知の内容は変わらない。
- 重さは変えていない（段5と同じ条件で、作者の最大の作品の全体2000pxが0.67秒→0.66秒、4倍の窓が0.52秒→0.51秒）。確認：AppCheck `--canvas-detail-only`、`--display-only`（debug・release。完成画像の領域の寿命も見る）、`build-macos-notices.py --check`。

## 2026-10-06 サムネイルを保存時にPNGへ焼いて持つ

サムネイル（`ArtworkThumbnail`の14箇所）は、Serverと同じく、作品ごとに一度PNGへ焼いて持つ（台帳I-718）。表示のたびに保存SVGを描き直すことはしない。

- 置き場所は、DBと同じフォルダの`thumbs.sqlite`（[`ThumbnailStore`](Packages/InkuPersistence/Sources/InkuPersistence/ThumbnailStore.swift)）。表の形はServerの`thumbs`と同じで、作品ID・scale・PNG・焼いた元のrender hash・焼いた時刻を持つ。正本のDBではなく派生物なので、バックアップには含めない。開けないファイルは空の保存先に置き換える。
- 大きさは幅512px（Serverのscale 2）。高さは作品の縦横比に従う。描き手はresvgで、Serverのサムネイルと同じ絵になる。
- 焼く時は3つ。保存の直後に裏で焼く。起動の後（と復元の後）に、裏で、無い作品と元のrender hashが変わった作品を4並列で焼き、消えた作品の分を捨てる。どちらより先に表示された作品は、その場で描いて保存する。
- 完全に削除した作品のサムネイルは、削除の後に捨てる。
- 読んだ画像はメモリにも控える（96MBまで）。描き手は[`ArtworkThumbnails`](Sources/InkuUI/ArtworkThumbnails.swift)。歳時記のプレビューは、今までどおり`ArtworkRenderer`で表示のたびに描く。
- 測定（Apple M5 Pro、作者の作品の写しで、ライブラリ1ページ分の24件が出揃うまで）：改修前は起動直後が1.10秒、2回目がメモリから0.003秒。改修後は、保存済みなら起動直後が0.037秒。更新の後に初めて起動し、まだ焼いていない作品を表示した場合は、その場で512pxを描くので1.7秒かかる。124件を裏で焼くのに17〜19秒かかり、保存先は21MB（1件あたり約170KB）。
- 確認：AppCheck `--thumbnails-only <SVG>`。

## 2026-10-06 作品域をSkiaで描く

作品を大きく見せる面（`ArtworkCanvas`の7箇所：制作の作品域、補助・一括・再現比較・ライブラリ・自動化の画面、プレゼンテーション）は、共有coreの表示部品[`inku-display`](../core/crates/inku-display/Cargo.toml)（Skia）で描く。WebのChromeと同じ見え方にするためで、保存SVGは変えない。表示の直前にメモリ上でだけ、3つの互換変換を掛ける。patternとuseの`href`を`xlink:href`へ、楕円を同じ形のpathへ、feTurbulenceの整数の`seed`をBlinkの読みの整数へ変える。

- 描き手は[`DisplayRenderer`](Sources/InkuUI/DisplayRenderer.swift)。専用のqueueで描き、要求が別の要求の後ろに並ぶことはない。全体は、粗い256pxを先に出し、続けて512pxのタイルを並列に描いてつなぐ。取り消された要求は、次のタイルの境目で止まる。
- 全体は100%の大きさで描く。拡大中は、見えている窓を画面の画素密度で描き直す。窓のタイルは中心から並列に描き、描けた分を0.15秒ごとに出す。描き終えた窓は作品に対する割合で位置を持ち、次の窓ができるまで同じ場所に残る。窓と全体の上限は、coreの値（`DisplayLayout`）に従う。
- 「作品を表示中」の印は、今の作品の全体か窓を実際に描いている間だけ出す。要求ごとに世代番号を付け、古い結果は捨てる。
- 照合表に無い要素・属性・style内の性質を含む作品と、Skiaで読めない作品は、resvg（共通raster）で描き、理由の符号を数える。数は画面には出さない。その作品は、拡大しても全体を引き伸ばす。（2026-10-06の後の節で、resvgへ戻さず止める扱いに変えた。）
- サムネイル、歳時記のプレビュー、PNGの書き出し、vision用の画像は、resvgのまま。
- SVGのconsumer上限は64 MiB（`inku-svg-raster`の`MAX_SVG_BYTES`。Skiaの表示とSwiftの書き出しの検査も同じ値）。最大32 MiBの生成本体に、説明・書き出しwrapper用の最大32 MiBを加えた枠で、pixel・寸法等の独立上限は保持する。
- Skiaの事前ビルドは、SHA-256で固定した写しを`~/Library/Application Support/inku/build-cache/skia-binaries/`に置き、`build-core.sh`がbuildのたびに照合する。Skiaとその中の8部品を、通知の「ネイティブライブラリ」に載せる。アプリはstrip後で、各アーキテクチャ約14MB大きくなる。
- 版は1.1.0（Build 2）。対応するServerはv2.15.86（Build 1162）のまま。
- 確認：AppCheck `--display-only <SVG>`（描き手、タイルのつなぎ、resvgへの戻し、作品の切り替えと印、窓）と`--canvas-detail-only`（窓の計画）。共有coreの`inku-display`の試験（Chromeとの一致、互換変換、タイルの継ぎ目、現行coreの出力と照合表の突き合わせ）。

## 2026-10-05 「inkuについて」の導線と生成情報のJSON表示

macOSの左の操作列からinkuのロゴを外し、「inkuについて」はメニューバーのアプリメニューからだけ開く。iOSは設定内の導線を保つ。生成情報の「Score (JSON)」タブは、Webの`highlightJsonLine`と同じ規則でkey・文字列・数値・真偽値・nullを色分けし、Webと同じ色（ライト／ダーク別）、太字・斜体、行番号の欄と背景を使う。表示する内容は従来どおり保存作品のScoreで、Webの生成情報が併せて出す実行の記録は含めない。

## 2026-10-05 初回配布に向けたWebとの整合とServer hostの照合

macOS版を初めて配布するにあたり、画面・操作・保存した選択をWeb（Build 1162）へ揃え、共有Rust core以外のhost処理をServer（Build 1162）と照合した。Webより詳しく役に立つ要素（モデルの実測記録、段階別の時間とusage、描画ログ、推敲方針の文字数）は残す。

### 画面の構成と密度

- 左端は190ptの項目一覧をやめ、WebのAppRailと同じ44pt（展開164pt）のアイコン列にした。展開、UIモード、ツールチップ、設定、テーマ、言語を置く。ライブラリは窓全体を覆う重ね表示、系譜は作品域の「作品／系譜」タブで開く。設定とデモはWebと同じ大きさの設定モーダルに入れる。メニューバーの移動（⌘1〜⌘4）と描画ログ（⇧⌘L）は残す。
- 窓のツールバー、上部の記述／バッチ帯、下部の状態表示を撤去した。実行状況と状態文は左パネル内に置く。記述／バッチは入力パネル内の下線タブで、実行中は点と進捗を出す。入力パネルは幅440（窓幅1180以下ではmin(400, 42%)）で、開閉できる。
- 描画中の表示はWebの`RunStatus.svelte`と同じ形（マスコット・見出し・情報・停止）で、単一描画とDDLの再演、デモ、バッチ、作品の編集、DDLの編集、推敲、色カタログとモデルの比較、自律推敲に出す（作者の指示、2026-10-12）。マスコットは設定で選んだ1体で、Webの`IncuMascot.svelte`・`YuragiMascot.svelte`のCSSの動き（時刻、keyframe、遅れ、変形の原点、easing）をそのまま写して描く。Incuは5×5の画素の立方体で15秒に1回転し、画素ごとに4秒で縮んで広がる。Yuragiは蟹で横に歩き、左の鋏を11秒ごと、右の鋏を8秒ごとに上げ、12秒ごとに泡を吹く。配色はinkuの標準色（`render_color_map`）で明暗のテーマで変わらず、動きを減らす設定では止まる。推敲と比較では候補ごとの列に選んでいない方の1体を出し、待ちは点、終わり（失敗も含む）は印にする。モデルの比較では列にモデル名を出す。停止ボタンはWebの`StopButton.svelte`と同じく、赤い枠と淡い赤の背景に輪の付いた点を添え、2.2秒ごとに背景と外の輪（最大5px）が脈打つ。色は明暗のテーマで変わり、動きを減らす設定では止まる（作者の指示、2026-10-13）。助言・奥書の読み取りとDDLの取り込み、バッチの準備は描画でないので標準の印のまま。
- 配置の候補づくり、色カタログとモデルの比較は、Webの`runRefinementFanout`と同じく候補を同時に走らせる（作者の報告、2026-10-12）。同時に走らせる数はServerの`render_fanout_limit`の既定と同じ4で、頼んだ順に始める。候補は終わった順でなく頼んだ順に並べ、失敗した候補はほかの候補を止めない。止めると残りを止め、遅れて来た答えは採らない。描画の土台は実行ごとに分かれ、サービスの回数の上限はDBで判定するので、同時の要求でも守る。ChatGPTプランは同じ登録への要求を順番に送る（Serverと同じ）。進捗の表示は最後に動いた候補のもので、候補ごとの状態は列が示す。
- 作品まわりの操作（拡大縮小、キャプション・印・書き出し、前後移動）は作品の上に重ねる。作品域の外側余白と枠をなくし、Webと同じ式（基準400、倍率min((幅−120)/基準幅, (高さ−96)/基準高さ)、0.25〜10）で合わせる。ズームのボタン・ホイール・ピンチは表示エリア中心の作品の位置を保つ。パンした後や倍率1を通過する場合も中央へ戻さず、明示した「用紙に合わせる」で位置と倍率を戻す。
- 文字はWebの`--ui-font-size-N`と同じ値に文字サイズ設定の倍率を掛ける。文字サイズ設定がすべての文字に効く。画面ごとの大見出しは置かない。
- 履歴帯はサムネ82×58、件数floor((窓幅−40)/89)。ライブラリはminmax(142,1fr)の格子で、1ページの件数を実寸から計算してページ送りし、スクロールに頼らない。モデル名はWebの`shortModel`（カード）と`abbreviateStripModel`（履歴帯）と同じ規則で省略する。
- ダイアログはWebと同じ大きさの式（例: DDL編集min(1360, 窓−40)×min(940, 窓高−40)）で開く。推敲は作品域の中、生成情報は作品上の引き出し、歳時記は右端の引き出しとして出す。

### 選択の保存

- 制作条件（色カタログとその自動選択、用紙、暴れる）、設定画面の最後のタブ、作品／系譜、記述／バッチ、ライブラリの表示方式と表示形式、推敲の種類、自律推敲の前回設定、モデル比較の選択を、表示設定（`interface.json`）へ保存する。保存した値がもう無いカタログ・用紙のときは既定に戻す。
- 表示設定とデモ設定は項目ごとに読み、欠けた項目や型の合わない項目だけを既定に戻す。読めないファイルは上書きせず、日時付きの名前で残す。版を上げても他の選択は失われない。
- デモで選んだモデルが一時的に使えないときは、表示だけをStage 1のモデルにし、保存した選択は書き換えない。
- 新しく作る表示設定の既定は、Webと同じくテーマdark、写生欄を開く。既存の保存値は変えない。

### 入力補助とツールチップ

- 記述欄は番号・コメントの範囲をグレーで示し、コメント記法のヒントを出す。記述メーターは応答前と失敗時にWebと同じ推定を出し、4000字の上限をUTF-16で数える。番号・コメントを除いた本文が無い記述は生成できない。
- DDL編集済みの作品では記述を固定し、「この記述から新しい作品を作る」で元作品の子として新しい作品を作る（Serverの`fork_linked_history`と同じ）。
- 表示中作品の写生文をその場で直せる。直した文はそのまま解釈へ渡る。
- DDL editorは行数・文字数、行番号、ハイライト、言語ラベル、未登録プラグイン名、簡易ガイドを出し、語をキャレット位置へ挿入する。
- バッチは番号・コメントだけの行を送らず、件数もWebと同じく本文のある行だけを数える。行番号は保つ。
- ツールチップはWebと同じく、hoverから0.12秒で出て、キーボードのフォーカスでも出る。押せない部品では理由を出す。macOS標準のtool tipと同じく、操作中の窓（キーウインドウ）の上でだけ出し、背面の窓の上を通っても出さない。Webの173箇所のうち、単一利用者のアプリに無い9箇所を除いて対応する。メニュー項目の中だけはmacOS標準のtool tipを使う。

### Server hostとの照合

- 非正方形の用紙は、Serverと同じく既定の高さ1000を保ち、幅を偶数丸めで出す（16:9は1778×1000）。新規の生成と再演奏の両方に適用する。
- 指示書の言語はWebと同じく常に自動で、記述またはDDLの文字（日本語→英字→UI言語）で決める。言語の選択肢は置かない。
- Personal ChatGPTの応答解析、HTTP sessionの寿命（要求ごと）、失敗の分類（応答過大、期限0）、rateの待ち方とGeminiのtoken計数の順序、Ollama Cloudの同時2本、model一覧の取得（ページ送り、新しいmodelは無効で登録、消えたmodelはEOLとして残す）、model参照の解決、Gemini schemaの`propertyOrdering`、自動配色の`catalog_mode`、デモの再試行と「暴れる」切、推敲助言と奥書の文脈JSON、失敗文言、PNGの撮影日時、DDL書出しの`exported_from`、描画警告の保存をServer／Webに合わせた。
- 型の欄の並び：coreの型のJSONは欄を名前の順に書くので、hostは`propertyOrdering`を持つオブジェクトの`properties`をその順に書き直して送る（名の無い欄は後ろに名前の順、ほかの鍵と値は変えない）。Geminiだけでなく、OpenAI API（Responses）、OpenAI互換のtools、Ollama・mlxのresponse_format、Anthropicのinput_schema、Personal ChatGPTも同じに送る（描画セッションの依頼、作者の選択、2026-10-13）。今の`propertyOrdering`は構図の読みの型だけにあり、ほかの要求のバイトは変わらない。
- Geminiのrate設定で欄が欠けた場合は、旧版が0（無制限）を欄の省略で保存していたため、無制限として読む扱いを残す。独自のproviderでkindがanthropic／geminiのものは、kindに合わせて送る。

### 版・署名・配布

- 版は`apple/VERSION`と`apple/BUILD_NUMBER`からbuild時にInfo.plistへ入れ、作品の来歴の`build`とDDL書出しの`build_number`にも使う。
- 配布物は`apple/scripts/package-macos-release.sh`で作る。Universal Release build、第三者通知の照合、Developer ID署名（Hardened Runtime、timestamp、entitlementsは空）、`.dmg`の作成と署名、Appleの公証とstaple、Gatekeeperの確認、SHA-256の記録までを行う。署名identityと公証のprofileは引数か環境変数で渡し、sourceに書かない。
- 配布アプリはbundle ID `app.inku.macos`と既定のデータ場所を使う。`--database`起動引数とbundleの`InkuDatabasePath`は開発用に残すが、配布物には`InkuDatabasePath`を入れない。
- 第三者通知はRust crate（registry・git・path・vendored由来）、GRDB、辞書（SudachiDictのUniDic部分を含む）、フォントを網羅し、「inkuについて」の「ライセンス」から全文を読める。

### 確認範囲

画面の骨組み・ライブラリ・選択の保存・入力補助・ツールチップ・host照合は、それぞれ防ぐ失敗に対応した限定確認（ServerのPython・WebのTypeScriptを実際に動かした期待値との一致を含む）と型検査で確かめた。実providerへの送信、Intel／macOS14実機、iOSは今回の確認に含まない。hover・フォーカスでのツールチップの見え方は作者の画面確認に残す。

## 2026-10-05 「inkuについて」をmacOSアプリメニューへ移動

macOSではアプリメニューの「inkuについて」から専用ウインドウを開く。設定一覧から同項目を削除し、既存の版情報・概念説明・用語表・作者情報・repositoryリンクを引き継ぐ。繰り返し選択すると同じウインドウを前面へ出し、閉じた後も再度開ける。制作と同じアプリモデル、表示言語・テーマ・文字倍率を使い、設定画面の読込やmodel一覧取得を開始しない。iOSでは設定内の導線を維持する。

## 2026-10-05 macOS Universalビルドと固定アプリ更新

作者のbuild指示により、接続断診断・背景バッチ中の閲覧／設定／表示作品のスターと、先行の共通Rust改修を含むReleaseアプリを生成した。同梱Server参照snapshotを保持し、追加のmain変更を取り込んでいない。Rust archiveとSwift bindingを再生成し、署名なしUniversalのarm64／x86_64、両CPUの最低macOS14を確認した。固定アプリの更新では既存bundle ID、DB指定、外側directory、incuアイコンとDock登録を保持し、通常起動1件と同じDB接続を確認した。

今回の確認はcompile・artifact・導入・通常起動まで。新しい描画やバッチ再送、実provider通信は開始していない。接続断の解消、バッチ中の同時操作と画面の受入は別に確認が必要で、先行の未受入項目とiOSの残件を保持する。

## 2026-10-05 バッチの接続断対策と失敗診断

描画pipelineのHTTP clientはServerと同じくcoreの試行ごとに作成する。Geminiのtoken計数と生成要求はその試行内の同じephemeral sessionを使い、成功・失敗・取消しによるtaskの終了を待って破棄する。別の行や再試行へsessionを共有しない。要求の形式・model・token数・期限・保存したレート予算とcoreの再試行上限は保持し、transportで独自に再送しない。

終端失敗は同じexecutionのfailed eventと該当actionの最終metricから、処理段階・安全な原因・試行番号・診断codeを行エラーへ保存する。閲覧中の別エラーとは分け、背景描画が作品・prompt・保存metricsを差し替えない。最後のmetricが成功してcore検証で失敗した場合は、以前の再試行の接続断を原因に使わない。

新しい通信診断には、準備・受付待ち・token計数・生成要求の操作をoptionalで記録する。古い記録は操作不明として読み、pipeline段階から失敗HTTP操作を補完しない。全試行の期限切れも最後のHTTP操作へ誤帰属しない。HTTP応答を観測していない `sent=false` は未送信の証明とせず、描画ログと生成情報へ「送信状態不明／応答未確認」を表示する。診断に要求URL・header・provider本文・APIキーを追加しない。

接続断の記録だけでは切断元やsession再利用が根本原因かを確定できない。本変更はclient寿命の実装差と診断不足へ対処した。初回source保存ではbuild直前で停止し、その後の作者指示で上記Universal build・固定アプリ更新・通常起動まで完了した。試験実行と実providerでの解消確認は未実施。

## 2026-10-05 バッチ中の閲覧と次回設定を許可

バッチの行を描画している間も、制作の記述／バッチtab、作品／系譜表示、画面移動、履歴帯の選択・ページ・端への移動、保存作品の詳細・prompt・Score JSON、設定tabを操作できる。実行中の処理と表示中作品の識別子を分け、バッチの進捗・完了は閲覧中作品の画像、DDL、prompt、保存時の計測値を上書きしない。完成作品は履歴へ追加する。明示した新規バッチ／再開では最新結果への追従を開始し、履歴や過去の成功作品を選ぶとその表示を固定する。次の行の成功や画面へ戻る操作だけでは追従を再開しない。

キャンバスに表示中の保存作品には、バッチ中もスターを付ける／外す操作を許可する。押した時の作品IDとスター状態を固定して保存し、後から別の行が成功しても保存対象を移さない。保存中の重複操作を抑止し、保存後の表示更新は同じ作品を表示している場合だけ行う。スターは保存作品の属性だけを更新し、開始済み描画の条件を変更しない。

新規描画、再描画、編集の確定、取込、スター以外の作品の変更、バッチの入力・条件・再開判定は、行の間もバッチ全体の実行lockを維持する。設定の表示・通常のprovider／model／URL／rate／描画制限の保存は次回用として許可し、開始済みrequestのmodel、接続、budgetと再試行条件を変更しない。APIキーの保存・削除、個人ChatGPT接続、plugin変更、DB復元・backup、結果file logの切替は実行中に制限する。開始前から開いていたsheetでも、キー変更の開始時に現在の実行状態を再確認する。

初回保存はsourceと文書まででbuild直前に停止し、その後の作者指示で上記Universal build・固定アプリ更新・通常起動まで完了した。試験実行とnativeでの同時操作受入は未確認。通常のforeground描画とdemoは従来の実行境界を保持し、batch行だけを閲覧可能な背景処理として扱う。

## 2026-10-05 共通Rustの並列処理と試験用最適化への追随

Serverの追加変更に合わせ、描画capability matrixの再導出をshape単位の並列処理へ移植した。predicate・termの列挙順と結果の順序、asset identityを保持する。通常の描画が参照する同梱matrix、共有protocolと描画の意味は変更しない。

既存のDDL・pipeline corpusとraster比較の試験sourceへ、入力順で結果を回収する並列実行を取り込んだ。Swift側の限定fixtureとraster case指定を保持し、試験ケース・入力・期待値を増やさない。Cargoのtest profileでは `resvg`、`usvg`、`tiny-skia`、`tiny-skia-path` のみ `opt-level = 3` とする。release profileと依存関係は変更しない。

初回追随はsourceと文書の更新まででbuild直前に停止し、その後の作者指示で上記Rust artifact再生成・Universal build・固定アプリ更新・通常起動まで完了した。試験実行・実行速度・新binaryの描画結果は未確認であり、先行アプリの確認結果とは分けて扱う。

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

生成情報は開いた保存作品を固定し、「詳細」「プロンプト」「Score (JSON)」のtabで読む。詳細は写生、両段のmodel／言語、seed、色の対応、canvas、SVGのbyte／object／point数、hash、版、由来、batch ID／元行、保存comment、日時／時間と実usageを表示する。送信記録の欠落と空配列、読込中と取得失敗を区別し、promptの開閉・コピーとScoreの行番号・コピーを提供する。プロンプトのtabは、写生（Stage 0.5）、Stage 1、構図の読み、Stage 2を処理の順に出し、写生と構図の読みは送った入力も出す（2026-10-13 作者の指示、SPEC §12.7.1）。保存作品は各段の最後の送信と記録した段の一覧を持ち、一覧にある段でmodelを呼ばなかったものは「呼んでいません」、一覧に無い段（それより前に保存した作品の写生と構図の読み）は記録なしと示す。色カタログの選択は出さない。読込みやtab変更で制作の選択、現在設定、provider送信を変えない。

新規requestのoptional `GenerationProvenance` はDDL／DDL engine、native Bundle build、参照資料build、UI言語とbatch ID／行番号をsave ACKへ保持する。旧作品の欠落を現在値で補わず、再演は元のprovenanceを保つ。Stage 1 promptの基底digestはnativeでは未記録として示す。意味が異なる `base_source_digest` を代用しない。usageの部分記録から完全な総tokenを作らない。この生成情報UIの最終追加はsource実装であり、以下の途中の型検査や過去画面確認を最終build／実画面受入と読み替えない。

保存記述の空文字列を保持し、DDL作品の表示名だけに保存DDLの先頭行を使う。専用DDL editorは保存親とdraftを固定し、取消しで本文・表示作品・revision・履歴を変えない。確定DDLの記述ロックと直接DDLを区別し、保存条件の読込中／未記録も操作不可の理由として表示する。制作・library・系譜・previewの共通作品menuは同じ固定した保存対象へ接続し、直接DDLでは描画パラメータ・記述・写生・model再解釈を隠す。確定DDL編集では理由を添えて再解釈を抑止し、配置・配色・DDL編集を残す。

新しいvariationの生成・採用・自動推敲・AI助言を退役し、旧保存variation/seedと系譜の読取表示を保持する。読み取り・タッチの推敲と描画パラメータの編集は削除し、配置の1案または4案を独立した入口に置く。model比較は使用中登録LLM最大4件、catalog比較は元のcatalogを除く候補を使う。Vision助言と自動推敲は色・配置の2種類だけを扱い、対象作品を固定する。奥書は生成成功時に原文を新recordとして保存し、後の編集で上書きしない。旧採用本文は互換読取を保持する。

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

同じ設定画面でSVG生成上限も編集する。既定・推奨12 MiB、1〜32 MiBの整数で、`providers.json`へ保存する。実際の描画時に現在の設定を読み、共有rendererの出力予算と最終SVG本文のUTF-8 byte検査へ渡す。SVGはJSONとは別にnative APIから受け取り、超過したSVGを保存・成功結果へ取り込まない。拒否時の上限値と失敗を永続化し、再起動後に旧成功を今回の成功として表示しない。この設定はcompiler budgetや作品identityに混ぜず、保存済み作品の表示・書き出しは別の64 MiB consumer枠を使う。

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

制作とモデル設定の「モデルの適性・用途」は`server/src/inku_server/model_catalog.json`（`inku.model-catalog.v2`）を`server-defaults.json`の`model_catalog`としてそのまま同梱し、ChatGPTプランも同じ正本から読む。用途、解釈／構造化と両段の評価、Visionの評価、日英comment、平均秒数・概算USD費用、更新日時と提供状態を表示する。両段の評価は弱い段階の値、段階別評価がない場合はLLM評価を使う。正確なcatalog service ID・接続方式・model IDで照合し、Ollama tagの`:`を保持する。custom serviceや未登録modelを名前やURLから推測で評価しない。Serverのdeveloper専用速度情報は公開環境と同じく表示しない。登録資料と接続先から明示取得した入力上限・対応機能は別欄にし、案内を読むだけで選択・保存default・開始時snapshotを変更しない。

札の名前・順序・公開可否は正本の`labels`表だけから読む（Host用の小さい札の表もexportで生成する）。記録の札に端末の確かめによるsubscription・eolを重ね、用途が無ければno_responseを足す。計測欄を1つも持たず他の札がすべて公開可能ならunmeasuredを足す。空配列・nullでも計測欄の存在として数える。折りたたみは最後の札、札が無ければ通常一覧、選べるかはすべての札の`publishable`で決まる。モデル設定・ChatGPTプランの公開選択・描画選択・比較は非空の折りたたみを表の順に件数付きで初期は閉じて表示し、行と詳細にすべての札を出す。公開できない札は警告色、ほかは控えめな色にする。保存済みの名前・用途・明示的な利用可否補正を保ち、正本にあるモデルの評価と非アクセス札は最新正本で置き換える。正本評価は読取表示、カスタムモデルは端末で編集できる。ChatGPTプランの公開と用途は本人の保存値を使い、正本defaultsから自動公開しない。`InkuAppCheck --model-catalog-only <server/tests/data/model-catalog-cases.json>`で共通15件の札・折りたたみ・公開可否と正本の同梱、保存値との重ね合わせを確かめる。

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

通常の「再演奏」はServerと同じ読出し専用の再現比較を開く。固定した保存作品のSVGと、保存Score・保存条件を共通Rustで描いた現行SVGを表示し、履歴・系譜・表示作品・元のexecutionを変更しない。保存時／現行の描画エンジンの版、版の不一致・記録なしを表示する。保存render_seedを使い、未記録なら暫定0とその注意を表示する。過去のseed_textは表示用の記録であり種へ変換しない。未保存のcomposition seedは未設定のままcoreのfallbackへ渡す。制作・library・系譜・作品menuは同じ比較へ接続し、系譜の保存情報sheetを閉じてから比較を開く。停止・closeは所有Taskの終了を待ち、遅い結果を除外する。「次の条件で再演奏」は明示した条件から新しい保存childを作る別操作として保持する。

保存作品の「記述を変える」「写生なし／ありで描き直す」は、制作toolbarとlibrary／系譜cardから同じdialogを開く。開いた作品を親として固定し、保存configuration、用紙、seed、budget、定義とlockを保持して共通coreから新しいchildを保存する。開始時の次の描画modelを両段へ固定する。記述が変わった場合は親の古い写生文を再利用せず、写生「あり」を明示した場合も生成し直す。保存contextのauthorityを確認し、直接DDL・確定DDL編集の作品を記述へ戻さない。取消しは作業の終了を待ち、成功したchildの保存後にだけdialogを閉じて制作を表示する。

編集childのedgeにはServerと同じ`edited_from_history_id`、写生操作では`from_sketch_state`／`to_sketch_mode`も保存する。GenerationRequestの追加項目はoptionalとし、既存の固定requestを読み出せる。

記述／写生dialogは題名と操作footerを固定し、親の画像・記述を入力と同じscroll領域へ置く。親画像は120角、記述は最大4行とtooltipで表示し、dialogの再表示でも入力に押し潰されない構成とする。

### 履歴・library・系譜

履歴stripはSQLite全件を対象に作品領域の幅からpage容量を決め、libraryは独立したpage容量を持つ。最新100件のapp内一覧を検索や作品移動の母集団にしない。最新／新しい／古い／最古への移動、全文記述・全文hash・末尾4桁の検索、star・推敲・export markのAND絞込、thumbnail／listと時系列／系譜groupの独立選択を提供する。

comment、mark、trash／復元、明示した完全削除、複数選択、系譜graph／pathをSQLiteへ接続する。完全削除後は作品本文を消し、nodeのidentity、root、日時と親子関係をtombstoneとして保持する。ACL、group利用者やServerの共有権限は追加しない。

履歴の世代はServerと同じくrootを1とし、primary parentのedgeごとに1加算する。削除済みの祖先も数え、nodeのない作品は独立作品と表示する。初期表示は世代とmodel、保存済みの表示項目は保持する。世代をvariationの種類や幅で代用しない。libraryでは表示中の作品と複数選択のcheckbox、系譜では表示作品と範囲を決めるfocusを区別する。記述のないDDL作品は保存DDLの先頭行を表示名へ使い、保存本文を補わない。hash、comment、mark、親子への移動はcardとmenuから操作できる。

Swift物理schemaはv3で、v2の作品・系譜・execution、local annotation、奥書、未読語の9tableへ`provider_rate_state`を追加した10table構成とする。正本は[bundled migration](Packages/InkuPersistence/Sources/InkuPersistence/Resources/migration-v3.sql)と[schema export](../persistence/reference/swift-schema-v3.json)。既知の完全なv1／v2だけを原子的に移行し、作品・snapshot・ACKの値を保持する。未知schemaは引き続き拒否する。backup／restoreは全10tableを対象とし、旧backupは隔離snapshotをv3へ移行してから復元する。復元先の送信予算・待機期限も保守的に引き継ぎ、古い作品backupで当日の上限をリセットしない。Server／Android DBや旧作品JSONのimportは含めない。

### 比較・推敲・奥書と自動実行

「配置を変える」は明示した保存親を固定し、配置の1案／4案を用意する。生成前に全条件を固定し、候補を通常履歴・系譜へ入れず比較する。拡大はdialog内だけで行い、制作の表示作品を替えない。選択した候補だけを子として原子的・idempotentに保存し、残りは破棄する。途中で保存を停止した場合は保存済みの印を保持し、再試行で二重保存しない。停止／closeは所有Taskと遅い応答の終了を待つ。採用後と再表示後のDDL変更も、新しい保存childを作る。

配置は親の保存DDL、定義・lock・配色・タッチを保持し、新しい配置seedで共通coreから描く。dialogの描画model指定は構造化側にだけ適用し、親の読み取りmodelを保持する。DDL／配置のdialogでmodelを確定するとStage 2の設定defaultへ保存し、Stage 1 defaultは保持する。

読み取りと言葉によるタッチの推敲は2026-10-14に削除した。保存済みの辺・語句・interpretation_seed・数値seedは旧記録として保持し、再演では保存したrender_seedを使う。

「てざわりを変える」は旧タッチ推敲とは別の独立操作として、作品編集メニューの色カタログの次に置く。ラジオは「すべての文を同じ筆記具にする」（既定）／「文ごとに違う筆記具にする」。開いただけでは描かず、「4案を作る」を押したときだけ選んだ方式で4案を描く。再び押すと並んでいる案と選択を破棄し、新しい4案に置き換える。全文の案名は筆記具、文ごとの案名は「文ごと N」で、1から数える文番号と元→新の筆記具を示す。替えられる文と書き換えは共有coreのretouch（inku.touch-change.v1）に任せる。保存済みScoreのsource_instruction owner.instruction_indexに対応する命令のweightのみ替え、親の配置・色・支持体・用紙・seed・wild・描画上限を保ち、LLMを呼ばない。候補の指示書と保存document.sourceもcoreの読み戻せた書き換え結果にそろえる。明示採用だけをtool_changeの子として保存し、付記にtool_mode／tools／changesを記録する。系譜の札は「てざわり」／Touches。保存・破棄・未保存のまま閉じない約束は他の比較と同じで、制作欄のdraftを読まない。

新しい変奏は共通coreとHost入口で退役しており、生成・採用・助言の選択肢を用意しない。過去に保存されたvariation amplitude／seed、Score・SVGと系譜は読み出せる。旧記録を新しい操作や別の推敲要素へ変換しない。

catalog／model比較は開始時の作品・Score・設定を固定する。候補は採用前に通常履歴／系譜へ保存せず、選択した候補だけをidempotentに保存する。model比較は使用中の登録LLMを最大4件選び、catalog比較は元を除くcatalog候補を使う。Swiftでは逐次生成する。停止とdialogのcloseは処理の終了を待ち、遅れて届いた候補を混入させない。

model助言、random／Vision推敲、奥書は通常生成と同じprovider transportを使う。通常pipeline外の補助要求はServerと同じく描画pipelineの共有rate予算へ加算しない。推敲は色カタログ・配置の2種類で、親の保存DDLを使い、記述を上書きしない。方向性はVisionの観察にだけ渡し、助言を描画の記述に追加しない。中間の推敲作品は`lineage_only`として保持する。自動推敲の各child edgeはWebと同じ`autonomous_refine_mode`を記録し、Visionではその世代の`vision_model`／`vision_observation`／`vision_next_direction`も記録する。randomの来歴へ以前の画面上のVision助言を混ぜない。奥書は生成した原文を成功時にimmutable recordとして追記し、既存本文を上書きしない。旧採用本文は互換読取を保持し、DB backupへ含める。

batchは空行を除く最大1000入力を受け、元の行番号とmodel、provider、定義、seed等を開始時に固定する。一巡後の失敗行だけを既定0／最大5回再実行する。明示した再開でも固定条件を保持する。再起動時に実行結果が不明な行は利用者の再試行／省略選択を待ち、自動再送しない。demoは開始時の設定を固定し、生成記述と作品を表示する。履歴保存は既定で無効、間隔1〜3600秒、実行時間60〜86400秒。間隔はiteration開始から測り、満了は次の開始を止める。停止は実行と保存結果の終了を待つ。

### 辞書・表示・接続設定

日本語はServerと同じSudachi small辞書、英語は同じCMUdictの読みを使用し、Rustの薄い境界で音数・音節を数える。辞書・設定・license・hashを[resource manifest](scripts/description-meter-resources.json)で固定し、build時に生成する。Python runtimeはアプリへ含めない。4000文字までの判定を300ms debounceし、未読語の頻度・日時・文脈をSQLiteへ保存する。判定を無効にした場合は文字数／行数を表示する。

日本語／英語、theme、5段階にsnapする文字倍率slider、full／simple／customの7項目、標準／詳細設定、caption、履歴情報最大3項目、tooltip、mascot、画像／card clipboard、描画制限、export template／保存先をlocal設定とする。clipboard高さは256〜4096px・64px刻み。複数APIサービスの設定、入口別の描画model、明示したmodel一覧取得とRPM／入力TPM／RPDを提供する。通常設定は隣接JSON、API keyはKeychainであり、接続設定を保存するだけでは生成しない。

通常APIのrate制限は[製品仕様](../SPEC.ja.md)とServerの共有描画pipelineへ従う。同じservice IDの写生文、解釈、辞書選択、構図、補完と各再試行を集計し、送信前に作品DBのSQLite transactionで要求数・入力token予算を予約する。複数Host・接続・processからの要求も同じDBの状態を使い、待機中はtransactionを保持しない。旧`provider-usage.json`の該当serviceの予約・待機期限を一度だけ原子的に取り込み、原本を変更しない。読めない状態や保存失敗は送信前に拒否する。旧Gemini記録からPacific日次の残量を証明できない場合は、次のPacific午前0時まで日次上限を消費済みとして扱う。

RPM／入力TPMは62秒windowで設定値の90%を使用し、正の小さい設定は最低1とする。Geminiはsystem／本文／schemaを含むcountTokensに10%の余裕を加え、他方式は実際の送信JSONのUTF-8 byte数に128を加えた保守的な予算を用いる。成功時は実入力usageで精算し、入力usageや送信状態が不明な場合は入力TPMが有効なときだけ予約を保って62秒待つ。日次要求数は既知429と再試行も含み、GeminiはAmerica/Los_Angeles、他方式はUTCの午前0時に切り替える。429は62秒、Retry-Afterの秒数／HTTP日時、Gemini RetryInfoの最大値を待ち、既存の待機期限を短縮しない。待機は共通coreが定めた有限の試行期限へ含め、Host独自の再試行を追加しない。

設定値は0〜1,000,000,000の整数で、0は上限なし。rate設定全体がない標準`gemini` serviceは30／16,000／14,400を使い、他serviceは0を使う。既存のrate設定objectで個々の値が欠落している場合は、従来の「0＝上限なし」を保持する。設定画面は3値と隣接する説明buttonを表示し、0を明示保存できる。

自動backupは既定で無効であり、アプリ起動中に生成・復元・自動実行の終了を待つ。検証済みbackupの成功後にmanifestを確定し、アプリ自身が記録した世代だけを削除する。手動backupを自動世代管理へ含めない。任意の生成結果logは実際に保存した作品だけを記録し、古い作品を開くだけでは作らない。

### Personal ChatGPT

Personal ChatGPTは通常のAPI key接続と別に扱い、既定は無効とする。利用者が明示して有効化・接続し、公開したmodelを描画modelとして選ぶ。Stage1／Stage2は同じ描画modelを使用する。本人の接続を複数保存しても、作品DBは一つのローカルlibraryであり、multi-user機能を追加しない。

設定の導線はServer／Webに合わせる（2026-10-12）。ChatGPTプランの設定は接続だけを扱い（有効化、接続・再認証・同意の更新・選択・接続解除・利用枠の後の再試行、利用状況）、選択中の登録が接続済みでプラン利用の許可があれば、案内と「モデル設定を開く」を出す。modelは「モデル」設定の「ChatGPTプラン」で選ぶ。開くだけでは外部取得せず保存済みの一覧を読み、「モデル一覧を更新」で取得し、チェックしたmodelを登録ごとの公開として保存する。一覧にないmodelと選択中でない登録への保存は拒否し、同じ本人の再認証は公開を保つ。公開したmodelだけが、描画のモデル選択・比較・描画の既定値の候補に「ChatGPTプラン」として出る（予約provider `chatgpt`のmodelsへ写す。名前・rate・URL・API keyの設定は無い）。描画の要求は、一覧にあって公開したmodelだけを送り、ほかは要求を送らず`chatgpt_model_not_offered`で止める。既存の接続でも公開を一度保存する。

ChatGPTプランのmodelはVisionにも使う（作者裁定、2026-10-12。契約はswiftが提案し、Serverが採った形。Serverの`chatgpt_models.py`・`chatgpt_provider.py`・`vision_client.py`と同じ判定にする）。選択画面は他のサービスと同じ絞り込み（すべて／使用中／不使用／LLM 用／Vision 用）と各modelのLLM／Visionの用途を持ち、用途は登録ごと・modelごとに保存する。保存の無いmodelはLLMとVisionの両方とし、用途が空のmodelの公開と、LLM／Vision以外の用途の保存は`chatgpt_model_not_offered`で拒む。LLMの用途を持つ公開modelが描画の候補、Visionの用途を持つ公開modelがVision推敲と奥書の候補になる。Vision推敲は1回の助言ごと、奥書は1回の奥書ごとに、開始時の選択中の登録（profile ID／generation）を固定し、途中で選択を変えても付け替えない。要求は同じResponsesへ`input_text`と`input_image`（data URL）を送り、toolsと温度・出力の上限は送らない。答えは完了したassistantのitemの`output_text`をつないだもの（UTF-8で512 KiBまで）で、断片だけの答え・未完了・拒否・toolは採らない。奥書のキャッシュは固定した登録ごとに分け、キャッシュを使う前にも、そのmodelがその登録でVisionに公開されているかを確かめる。要求の前に、一覧にあり・公開し・その用途を持つmodelかを確かめ（描画もLLMの用途を確かめる）、違えば要求を送らず`chatgpt_model_not_offered`で止める。デモの記述とmodel調査は対応しない。

本人認証は127.0.0.1の一時listenerと`/auth/callback`、state／nonce／PKCE、発行済みclient ID、検証したidentityと許可scopeを使用する。資格情報は最大1MiBのAES-GCM暗号化vaultへ原子的に保存し、device-localの32byte keyをKeychainへ置く。平文token fallbackを持たず、SQLite backupに資格情報を含めない。初期無効状態で認証や推論を開始しない。

開始時にprofile ID／generationを固定し、queued要求やbatch／demoの再開で接続を付け替えない。接続解除・切替・quota後は古いrefreshや遅延応答を採用せず、別providerへ暗黙に切り替えない。共有Rustの記述解釈、写生、自動配色、構図の読み、DDL補完と、Vision推敲・奥書をResponses／SSEへ接続する。demo用記述とmodel検査はこの接続では未対応として表示する。実本人OAuth、model取得、推論の受入はoffline確認と分ける。

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

[ArtworkRenderer](Sources/InkuUI/ArtworkRenderer.swift) actorはSVG digest、raster API版、要求寸法と色空間をkeyとする上限付きcacheを持つ。歳時記のプレビューは必要な表示時にrasterを要求する。作品域は2026-10-06から`DisplayRenderer`（Skia）で描き、サムネイルは同日から焼いて持つPNGを読む（上の日付付きの節）。現行PNG書出しは保存SVGを高さ1024でraster化し、SVG書出しは保存canonical SVGをそのまま出力する。custom寸法・animated exportなどの全export仕様を実装済みとはしない。

### 初期macOS UIと未接続項目

`NavigationSplitView`のrailに作成、ライブラリ、系譜、設定を置く。作成画面は記述／直接DDL、言語、共通catalog／canvas、seed、暴れる設定をapp modelへbindする。初期入力はmodel未接続でも試せる英語の直接DDLである。生成・取消、保存作品の選択と再演奏、read-onlyのDDL／Score、canvasの拡大・移動、最近の作品、library内検索、provider設定、SVG／PNG書出し、画像コピー、manual backup／restoreを接続している。

libraryと最近の作品は通常表示の非trash作品を扱い、処理中の選択を無効化する。検索は読出した作品内のローカル検索であり、DB全件のFTS／pagination UIではない。本文が空の作品は表示名を「無題」とし、保存本文を補わない。

M3で残る機能は系譜graph、favorite／trash操作、plugin／model助言dialog、batch／demo、custom・animated exportと共有cardなどである。系譜画面は未接続であることを明示し、未実装機能を成功した操作として見せない。iPad／iPhone app、camera、share、端末上のlifecycleと実機受入も今後の範囲である。

### buildと確認の境界

clean cloneの必要tool、固定依存、resource生成、generator、artifact、実行手順は[README.ja.md](README.ja.md)を参照する。[build-macos.sh](scripts/build-macos.sh)は既定でrelease RustとRelease appを作り、明示指定でdebugを選べる。[project.yml](project.yml)から生成したXcode projectをgeneric Mac destination、両architecture、`ONLY_ACTIVE_ARCH=NO`でbuildする。ローカルunsigned buildであり、署名、notarization、配布は別作業とする。生成binding、XCFramework、resource、project、build出力は再生成する成果物である。

Mac arm64／x86_64 Rust artifactとSwift link、Universal macOS appのbuildを限定して確認した。Apple Silicon上では直接DDLからのScore／SVG生成、SQLite保存とapp model再作成後の読出し、owned rasterのnative表示、保存canonical SVGの書出しが成立した。初期native画面でも生成画像・最近のthumbnail、library選択、保存Scoreの再演奏による新しい履歴を確認した。UInt64 seedの保持、pixel所有、入力エラー、保存境界は具体的な失敗に対応する小さい確認で扱う。

iOS device／simulatorのRust artifact生成は確認したが、iOS appのbuild・署名・実機受入は完了していない。Intel実機での起動・性能、実provider送信、作者による通常操作とフル機能の受入は別の確認である。CLI確認、Universal build、native画面確認、実機受入を互いの代用とせず、変更が防ぐ具体的な失敗に必要な確認を選ぶ。

隔離した試行はappの`--database`引数で一時DBを選べる。これはDBと隣接provider JSONの保存先を変え、Keychainの保存先は変えない。通常利用と隔離試行の具体的なcommandはREADMEに集約する。

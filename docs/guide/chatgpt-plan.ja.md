# ChatGPTプラン接続

本人がChatGPTへサインインして許可した利用枠で描画します。OpenAI API PlatformのAPIキー接続とは認証・利用枠が別です。個別アカウントの利用可否とモデルは、実際の認可と本人catalogで確認します。[公式案内](https://developers.openai.com/siwc/token-sharing-open-source)

## 利用条件

`INKU_CHATGPT_PLAN_ENABLED=1`を明示し、デベロッパーモードまたはシングルユーザーモードを有効にします。両方無効では使用できません。管理者にも本人の接続と`chatgpt.tokens.use.direct`の許可が必要です。single-user中は固定accountだけがownerです。画面表示はOAuth完了を意味しません。

初版のlocal接続はWeb・API・ブラウザが同じPCで動くソース版を対象とします。Android、Docker内のlocal callback、Vision、奥書、デモ指示生成、モデル検査は対象外です。

## 同じPCで接続する

Serverのソースディレクトリで、先に`uv sync --frozen --inexact`でlock済み依存を同期します。既存のnative wheelを保持し、以下の起動・認証helperでは`--no-sync`で再同期を避けます。既存のDB・管理者設定とともに起動します。

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  uv run --frozen --no-sync inku-chatgpt serve --host 127.0.0.1 --port 8100
```

設定「ChatGPTプラン」の「ChatGPTで続ける」から本人がサインイン・同意します。callbackは同じPCの`http://127.0.0.1:<port>/auth/callback`です。戻り画面は設定の表示言語に合わせ、認証の完了と失敗を区別します。拒否・中止・5分の期限切れは失敗として表示します。popupを遮断した場合は画面の同じ認可リンクを開けます。1 worker・reloadなしで、通常の直uvicorn起動やlocal LAN bindでは有効にしません。認証後は下の「登録・モデル・利用枠」で公開モデルを設定し、Stage 1/2共通のモデルを選びます。[認証手順](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)

## 別hostの自己ホストで接続する

設定の独立した「ChatGPTプラン」タブで「ChatGPTで続ける」を押すと、このMacにセットアップした専用アプリ「inku ChatGPT」を開きます。ChromeまたはBraveがアプリを開く確認を表示したら許可します。開かない場合は画面の同じリンクから再度開けます。アプリ未導入の場合は、運用者がこのMacへセットアップしてから進めます。

Macの確認画面には保護された接続で取得したinku本人の名前・IDと移送先host IDが表示されます。接続先を確認して「続ける」を押すと、設定を始めたChromeまたはBraveでOpenAI認証・利用同意へ進み、同じブラウザのcallbackへ戻ります。ブラウザを開けない場合に別のブラウザへ自動で切り替えません。認証後の封印と移送は専用アプリが一回ずつ行います。完了したらWebの「接続状態を確認」を押します。Macの確認・完了・失敗の理由は設定の表示言語に合わせます。OpenAI自身の認証画面の文言はOpenAIが提供します。失敗時は理由を表示して止まり、自動再試行しません。既に別のinku本人へ固定したMacではその接続を拒否します。

起動リンクの`inku-chatgpt://connect`には本人ID・選択登録ID・同意指定に加え、固定のブラウザ指定（`chrome`／`brave`）と表示言語（`ja`／`en`）を載せます。任意のアプリやcommandは指定できません。Braveは公開の`navigator.brave.isBrave()`で識別します。[Braveの公式案内](https://github.com/brave/brave-browser/wiki/Detecting-Brave-(for-Websites))。OAuth URL/code/tokenや転送する登録の本文をリンクへ含めません。「表示・操作」「描画」「その他（サーバー）」などの既存設定は元のページに残ります。以下は運用者向けの同じ接続手順です。

Macで認証し、自己ホストだけが更新を所有します。Web全体のHTTPS化は前提条件にしません。code/tokenはLAN HTTPへ送らず、OpenAI通信は固定HTTPS、callbackはMacのHTTP loopback、選択登録の移送は運用者の保護された専用SSH経路です。[公式手順](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms)

自己ホストは明示有効化とモード条件を維持し、次の入口で起動します。

```sh
uv run --frozen --no-sync inku-chatgpt serve --self-hosted --host 0.0.0.0 --port 8100
```

運用者はDBで検証済みの本人ownerへ固定した`inku-chatgpt recipient --owner-id <verified-owner-id>`を実行し、公開recipient JSONをMacへ安全に渡します。Macで0600ファイルとして保存し、このアプリ専用の認証を行います。

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  uv run --frozen --no-sync inku-chatgpt authorize --recipient recipient.json \
  --browser brave --language ja
```

CLIの`--browser`は`chrome`／`brave`だけ、`--language`は`ja`／`en`だけを受けます。省略した旧CLI操作はChrome・英語を維持します。本人が指定ブラウザのChatGPTアカウントと許可内容を確認します。成功結果の非秘密`profile_id`で一登録だけを封印します。

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  uv run --frozen --no-sync inku-chatgpt export --recipient recipient.json \
  --profile-id <profile-id> --output sealed.json
```

専用SSH経路は封印JSONだけを自己ホストの`inku-chatgpt import`の標準入力へ渡します。一般source配備やLAN API uploadには含めません。recipientは30分有効です。同じ封印の再送は同じ受領結果を返し、内容の違う再送は拒否します。

exportはMacのtokenを消し、更新所有権を手放してから完了します。importは受信hostのinstallation IDを保ち、そのhost専用鍵で再暗号化します。Macの鍵を共有せず、export後の失敗を理由に旧refresh tokenを復活させません。再認証は保存した`profile_id`、利用許可の追加は明示`--consent`を使います。初回交換失敗でも発行済みclient IDを保存し、失敗結果の`profile_id`で再試行できます。

## 登録・モデル・利用枠

接続完了後の案内から「モデル設定を開く」を押します。設定「モデル」で「ChatGPTプラン」を選び、「公開モデルを選択」→「モデル一覧を取得」の順に進みます。取得中の表示と件数・モデル名を確認し、描画に使うモデルへチェックを付けて「保存」します。他providerと同じ選択画面を使いますが、公開先は接続した本人だけです。APIキーや接続先URLの設定はありません。空の一覧やエラーは理由を表示します。既存の接続でも、この公開設定を一度保存します。

保存後に描画の「モデル選択」を開き、ChatGPTプランからStage 1/2共通のモデルを選びます。一覧の取得だけではモデルを公開・自動選択しません。普通の利用者は本人のChatGPTモデルだけ、管理者は既存の共有providerも管理できます。

描画が失敗した後も、モデルを選び直してそのまま描画できます。新しい描画の開始時に前の失敗表示を消すため、ページの再読込みは不要です。

画面は本人の登録ラベル、状態、scope、選択中profileを表示します。token、PKCE verifier、ID tokenを画面・log・browser storageへ出しません。最大8 profile、認可はownerごとに1件・全体4件です。保存先は既定`~/.config/ddl-server/chatgpt`（`INKU_CHATGPT_AUTH_DIR`で変更）、0700 directoryと0600 fileです。専用`credential.key`による`enc:v1:`暗号化を使い、平文互換や復号失敗の黙認はありません。既存APIキーの鍵は変更しません。

本人の`models[].visibility=list`をOpenAIの順序と`display_name`で表示し、公開したモデルを`chatgpt:<slug>`として選びます。inkuの公開設定はOpenAIのvisibilityとは別で、owner/profileごとに暗号化保存します。同一identityの再認証・受信hostでの再importは公開設定を保持します。共有APIキーproviderやbare名の所有者へ混ぜません。外部catalogのcacheはowner/profile/generationごとに5分で、設定・描画候補を開くだけでは外部取得せず、保存した一覧を読みます。接続解除・profile切替・モード変更で候補を破棄し、消えた指定や未公開の指定は利用不可として保持します。別providerへの変更は明示選択が必要です。

応答に補助的なメッセージが含まれていても、正しい完了関数呼出しの引数だけを採用します。メッセージ本文からJSONを推測しません。「描画用の関数呼出し形式と一致しませんでした」は応答形式の診断で、再認証の指示ではありません。

quota時は同じ登録の後続送信を止めます。「利用枠を確認」からChatGPT usage画面へ進み、回復後に本人が「再試行」を選びます。401/403だけでtokenを削除せず、認可・quota・未対応機能・一時通信失敗を区別します。[モデルと推論](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)・[復旧](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)

## 生成と接続解除

写生文、色カタログ選択、記述からのDDL、構図の読み、可視holeの補完へ同じ描画モデルを使います。構図の読みは`read_composition`を受け、観測の時間とusageはStage 1から分けて`composition`へ記録します。読みが使えないときの既定fallbackは共有Rustが決めます。Rustのprompt/schema・検証・再試行・Score/SVGは継承します。Responsesは`store:false`・SSEで、温度や出力tokenの旧パラメータを流用せず、必要なJSONを一つのnamespaced function callで受け取ります。正しい`response.completed`だけを採用し、途中切断、refusal、未知tool、サイズ超過、後続quotaでは部分JSONがあっても失敗です。

実行は開始時profile/generationへ固定し、別profile選択は次の実行に適用します。cancel、sign-out、inku logout、モード変更、Server終了は新規通信と遅い結果の採用を止めます。profileごとに一通信slot、owner単位でrefresh排他を持ちます。sign-outはローカルtokenを直ちに消し、登録identity・host IDを残します。remote revocation失敗は未確認と表示します。[セッション](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)

## 確認結果の読み方

実装、HTTP mock確認、配備、本人OAuth/import、実アカウント推論は別の結果です。画面表示やmock成功だけで、そのaccountの利用可否と生成成功は確定しません。本人OAuth/import後、提供モデル一つで短い描画を確認します。[制約](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)

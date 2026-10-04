# GitHubのAndroid APKをインストールする

## 対応端末と入手

Android 15以降のarm64端末に対応します。[GitHub Releases](https://github.com/oikawas/inku-lang/releases)で、`android-v`から始まるAndroid専用リリースを開き、APKと`SHA256SUMS`をダウンロードします。Web/APIの版とAndroidの版は別です。APKにはモデルの重み、APIキー、本人のChatGPT認証、作品のデータは含みません。

APKのSHA-256を`SHA256SUMS`と照合してください。リリースには第三者ライセンス集と署名証明書の公開情報も添付します。ライセンス集はAPK内の`assets/licenses/`にもあります。

## インストールと更新

端末でAPKを開き、必要ならそのブラウザまたはファイル管理アプリに限って「不明なアプリのインストール」を許可します。インストール後はこの許可を戻せます。以後は同じ公開署名鍵で署名した、より新しいBuildのAPKを上書きインストールします。GitHubからの更新は手動です。

**検証用debug版とは署名が異なります。** `app.inku.mobile`のdebug版がすでにある端末では、この公開APKでそのまま更新できません。作品を残すため、debug版をアンインストールしたり、データを消して公開版へ入れ替えたりしないでください。既存の検証用端末はそのまま保持し、初回公開版は別の端末で使うか、データを保全する移行手順を別途準備してください。

## 描画を始める

ChatGPTプランを使う場合、設定のChatGPTプランで本人のChrome認証を完了し、利用案内を確認します。設定「モデル」で本人の一覧を取得し、使うモデルを公開して保存し、制作のモデルとして選びます。利用可能なモデルと制限は本人のプランに依存します。APIキーの接続も使えます。

端末内のGemmaモデルを使う場合は、モデルのライセンスへ同意してから別途ダウンロードします。Pixel 9のGemma 4 E2Bは、記述が場所を言わない層にも場所を返すため、端末では構図の読みを入れない扱いです。雲のモデルとは同じ結果を保証しません。

作品は端末内に保存します。この案内は新しい公開署名の配布方法を記すもので、すべての端末・モデルでの動作確認を意味しません。

## ソースから公開APKを作る

Java 21、Python 3.11以降、Android SDK 36、NDK 29.0.14206865、固定Rust toolchainとAndroid targetを用意し、Androidの版とBuildを確定したcleanなソースから実行します。

```sh
cd android
rustup component add rust-docs --toolchain 1.95.0
./gradlew :app:assembleRelease -PinkuAndroidReproducibleRelease=true
```

この指定は確定済みの`android/BUILD_NUMBER`を使い、値を書き換えません。通常のdebugや開発用パッケージ作成の自動採番は維持します。releaseの依存を解決し、上流のLICENSE・NOTICE（LiteRT-LM JNIの全文を含む）、Rustの依存と標準ライブラリのライセンス集を生成して同梱します。`rust-docs`は固定toolchainの標準ライブラリの著作権情報を取得するために必要です。

生成されたunsigned APKをSDKの`zipalign`で整列し、Git外の専用公開鍵を使って`apksigner`で署名します。秘密鍵とパスワードをソース、ビルドログ、GitHubへ入れないでください。署名鍵は今後の更新にも必要なので、安全に保管してください。公開前に署名検証、非debuggable、版・Build、arm64のnativeとライセンスの同梱を確認します。

# inku-cli

inku の API サーバーを操作するコマンドラインクライアントです。各コマンドの使い方は [inku-cli リファレンス](../manual/ja/cli-reference.md) を参照してください。

## 接続設定

通常は `~/.config/inku-cli/config.json` を使います。接続先ごとに設定を分けるときは、`INKU_CLI_CONFIG` で別々のファイルを指定できます。

| 項目 | 環境変数 | 用途 |
|---|---|---|
| `base_url` | `INKU_BASE_URL` | サーバーの URL。HTTPS の場合も、末尾に `/api` を付けずに指定する |
| `ca_file` | `INKU_CA_FILE` | サーバーの証明書を検証する PEM 形式の CA ファイル。先頭の `~` を展開する |

設定ファイルの値を優先します。CA を指定していないときは、Python の既定の証明書検証を使います。その場合も `SSL_CERT_FILE` を使用できます。

# マニュアル改訂履歴

この履歴は`manual/`配下の利用・運用文書の改訂を記録します。製品機能そのものの詳細な変更履歴は`SPEC.ja.md`を参照してください。

## 2026-07-15 — v1.85未リリース基準（Web Build 564）

- 全公開APIを権限に応じて操作できる inku-cli api と全コマンド一覧を追加した。
- Composeによる非root API、production Node Web、永続data volumeの導入手順を追加した。従来の開発構成は維持する。
- request body上限、login rate制限、CORS、Renderer同時実行上限、Idempotency-Keyを管理者向け設定へ追加した。
- 履歴のtrash確認、系譜tombstone、再送時の二重保存防止、user scopeを明記した。
- 英語UIのTitle Case統一とiPad幅の表示基準を反映した。

## 2026-07-15 — v1.82未リリース基準（Web Build 563）

全面改定。

- `画像の作成方法`を現行Web UIへ合わせ、指示文言語の自動判定、色カタログ／モデル／キャンバス操作、正規化DDL編集を更新した。
- 推敲の`調整`、`モデル比較`、`言語比較`、言葉による決定的なタッチ変更を追加した。
- 生成情報の`詳細`／`プロンプト`／`JSON`、Stage別言語、seed、hash、derivation metadataを追加した。
- 作品系譜、中間作品、通常履歴への昇格、近い作品、履歴管理の`時系列`／`系譜ごと`を追加した。
- `アプリケーションインストール`をlockfile、migration前backup、systemd参照構成、受け入れ確認、rollbackを含む手順へ全面改定した。
- `サーバー設定方法`を設定境界、現行環境変数、DB migration、四つの同一性、認証scope、言語解決、Renderer再現性、backup、監視、security基準へ全面改定した。
- 環境変数、systemd、logrotateの付属テンプレートを現行の参照構成と権限方針へ揃えた。
- 日本語版と英語版を同じ章構成と機能境界へ統一した。

## 改訂規約

- `SPEC.ja.md`を製品仕様の正本とする。
- マニュアル変更は日本語版を先に行い、英語版へ同じ意図を反映する。
- UI挙動を変更した場合は対象Web Buildを記録する。
- host名、IP、実ユーザー名、秘密、ローカルservice情報はマニュアルへ記録しない。

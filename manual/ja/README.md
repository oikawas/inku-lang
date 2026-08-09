# inku 運用・利用マニュアル

このディレクトリは、未リリース版inku v2.11.12（Web Build 868）を初めて使う人が作品を作成できることと、システム管理者がアプリケーションを安全に展開・運用できることを目的にしたマニュアルです。製品仕様の正本はリポジトリ直下の`SPEC.ja.md`です。

## 対象読者

- 画像作成者: Web 画面または CLI から、短い言葉を入力して SVG / PNG 画像を作成する人
- システム管理者: サーバーへ inku をインストールし、API、Web UI、DB、ログ、バックアップ、AI 接続を管理する人

## ドキュメント構成

1. [画像の作成方法](./image-creation.md)
2. [inku-cliリファレンス](./cli-reference.md)
   * [AI自律運転・テスト用リファレンス](./cli-reference-for-ai.md)
3. [アプリケーションインストール](./application-install.md)
4. [サーバー設定方法](./server-configuration.md)
5. [改訂履歴](./revision-history.md)

## 付属テンプレート

- [環境変数テンプレート](./templates/inku-api.env.example)
- [FastAPI systemd サービス例](./templates/systemd/inku-api.service)
- [SvelteKit / Vite systemd サービス例](./templates/systemd/inku-server.service)

テンプレートは汎用例です。実際のホスト名、ユーザー名、パス、秘密情報はローカル運用ファイルやサーバー側の安全な場所で管理してください。

日英マニュアルは同じ機能境界と章構成を保ちます。日本語版を先に更新し、英語版へ同じ意図を反映します。

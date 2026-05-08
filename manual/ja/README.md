# inku 運用・利用マニュアル

このディレクトリは、inku を初めて使う人が画像を作成できることと、システム管理者がアプリケーションを展開・運用できることを目的にしたマニュアルです。

## 対象読者

- 画像作成者: Web 画面または CLI から、短い言葉を入力して SVG / PNG 画像を作成する人
- システム管理者: サーバーへ inku をインストールし、API、Web UI、DB、ログ、バックアップ、AI 接続を管理する人

## ドキュメント構成

1. [画像の作成方法](./image-creation.md)
2. [アプリケーションインストール](./application-install.md)
3. [サーバー設定方法](./server-configuration.md)

## 付属テンプレート

- [環境変数テンプレート](./templates/inku-api.env.example)
- [FastAPI systemd サービス例](./templates/systemd/inku-api.service)
- [SvelteKit / Vite systemd サービス例](./templates/systemd/inku-server.service)
- [logrotate 設定例](./templates/logrotate/inku)

テンプレートは汎用例です。実際のホスト名、ユーザー名、パス、秘密情報はローカル運用ファイルやサーバー側の安全な場所で管理してください。

# 予測（着手前に凍結）: gzip の層が 1 通ごとに送り出す

**書いた人**: git 管理セッション（Claude Opus 5・Claude Code）／**2026-08-16**
**枝** `feat/the-ui-is-shaped-one-request-at-a-time` ／ **この commit の親** `5b65fe55`

> **⚠ この文書はコードを 1 行も書く前に commit する**（実行規約 §2-8）。
> **受け入れ側と実装が同じセッションなので、数字を後から書くと、測っていない数字になる。**
> **マージ後に `no-git-sync/` へ移す**（公開ツリーへ残さない）。

---

## 0. なぜ直すのか（受け入れで見つけた退行）

段 3 が API 全体に gzip を付けたが、**`/api/paint/stream`（`application/x-ndjson`）は除外表に無い。**
starlette の層は流し込み応答を **`Z_SYNC_FLUSH` せずに** `GzipFile` へ書くので、
**途中で書いた event が zlib の中に溜まり、最後に閉じるまで 1 バイトも出ない。**

受け入れ側の実測（枝の venv・同じ層に 5 event を流した。対照は層が除外する型）:

| 型 | 本文メッセージごとのバイト数 |
|---|---|
| `application/x-ndjson`（この app が使う） | **10 / 0 / 0 / 0 / 117** |
| `text/event-stream`（対照・除外される型） | 53 / 52 / 19 / 19 / 4026 |

`+page.svelte:3108` は「stage1 event は解釈が終わった瞬間に届くので、進捗表示が本当の段と
Stage 1 のトークン数を出せる」と書いている。**その event が絵の完成まで届かなくなる。**
**内容は壊れない。届く時刻だけが変わる。**

**2026-08-16 作者裁定（選択 UI）= 1 通ごとに押し出す層を書く。担い手は git 管理セッション。**

---

## 1. 満点（**着手前に測る**）

| 面 | 値 | 測った木 |
|---|---|---|
| server `pytest` | **3227 passed / 31 skipped / 0 failed** | この作業場・枝の先端 `5b65fe55`（**下の「実測」節に自分で測った値を入れる**） |

**⚠ 3227 は完了レポートが枝の上で測った値である**（実装は同一モデルなので §2-1 で skip できる面だが、
**自分が実装する周なので、予測の土台としてこの周に測り直す**）。

---

## 2. 予測

### 2-1. 満点はいくつになるか

**3228 passed / 31 skipped / 0 failed**（**+1** = 受入 `T-78` を 1 本足す）。

**web の 3 面は 1 つも動かない**（`web/` を 1 バイトも触らないため）——
`make test-web` 373 / `npm run check` 261 FILES 0 ERRORS 2 WARNINGS / `lint:i18n` 0 errors。
**⚠ したがって web の全走メタゲート `T-15` はこの改修の摂動では発火しない**（web の suite を回さないため）。

### 2-2. 摂動で何本赤くなるか

| 摂動 | 当て先 | 予測 |
|---|---|---|
| **P-6** | 押し出しの 1 行（`flush()`）を落として starlette の既定と同じ形に戻す | **`T-78` が 1 本だけ赤 / 3227 passed + 1 failed。`T-75`〜`T-77` は 3 本とも緑**（機能そのものは残るので、圧縮も除外も成り立ったままである） |

**⚠ `T-75`〜`T-77` が緑のまま**であることが、この摂動の主眼である ——
**いまある 3 本は「溜まるかどうか」を 1 本も測っていない**。それを測る目が `T-78` である。

**⚠ 予測を外す向きも書いておく**: `T-78` が P-6 で緑のままなら、
**据えた受入が層を通っていない**（ASGI のメッセージ単位で測っていないか、
`Accept-Encoding: gzip` を送っていないので `IdentityResponder` の道を測っている）。

---

## 3. 何を書くか（**予測であって、まだ書いていない**）

- `server/src/inku_server/compression.py`（新規）——
  starlette の `GZipResponder` を継承し、**`apply_compression` だけを差し替える**。
  本文がまだ続くときは `GzipFile.flush()`（既定が `Z_SYNC_FLUSH`）を呼び、最後だけ `close()` する。
  `Accept-Encoding` に gzip が無い道（`IdentityResponder`）は既定のまま。
- `server/src/inku_server/api.py` —— `GZipMiddleware` の代わりにこの層を積む。**除外表は動かさない。**
- `server/tests/test_the_api_compresses_what_is_worth_compressing.py` —— **`T-78`** を足す。
  **ASGI のメッセージ単位で測る**（TestClient は本文をまとめてしまうので、それでは測れない）。

**変えないもの**: 除外表の 10 個・`minimum_size=500`・`compresslevel=6`・`web/` の全ファイル・
`APP_VERSION` / `BUILD_NUMBER`（採番は docs を書く直前に行う）。

---

## 4. 実測（**着手後に追記する。上の予測は書き換えない**）

（ここは空のまま commit する）

# 実装前の予測 — [I-167] ログの方針をアプリが実行する

**⚠ この文書はコードを 1 行も書く前に commit する**（自分で実装するときの歯止め・2026-08-09）。
**実装後に実測と突き合わせ、外れたぶんはレポートへ差分として書く。**

- 起点: `bdfec13e`（main の先端）／ 枝 `fix/the-log-policy-is-executed-by-the-app`
- 作業場: `/Users/oikawas/projects/ddl-server-ops`
- 裁定: **D「アプリが自分で書いて回す」** ＋ **compose のログ上限も同じ周で直す**（2026-08-09 作者裁定）

## 何を変えるか

いまは設定画面が systemd drop-in と logrotate の設定文を**生成して管理者に貼らせている**。
その生成文が `StandardOutput=journal+append:{path}` で **systemd に存在しない指定子**であり、
**コンテナ配布版には貼る先が無い**。バックアップは方針も実行もアプリの中にあるので、
**ログも同じ作りへ寄せる**。

1. アプリが `INKU_LOG_DIR`（既定 `$HOME/.local/share/inku/logs`）へ自分で書き、自分で回転・保持・圧縮する
2. `_log_systemd_dropins` / `_logrotate_config` と API の 2 フィールドを撤去する
3. Dockerfile が `INKU_LOG_DIR=/data/logs` を渡す（`inku-data` ボリュームに載る＝コンテナでも残る）
4. `compose.yaml` の api と web に Docker ログの上限を入れる
5. **stdout には出し続ける** — `journalctl -u inku-api` と `docker logs` を殺さない

## 満点の予測

**既存で赤くなるもの = 3**

| | 何 | なぜ |
|---|---|---|
| 1 | `server/tests/test_api.py:2625` を含むテスト | `logrotate_config` に `/var/log/inku/inku-api.log` が入ることを assert している |
| 2 | `server/tests/test_api.py:3446-3447` を含むテスト | `rotate 30` と `compress` を `logrotate_config` の文字列で見ている |
| 3 | `server/tests/test_api_surface.py` | `api-surface-baseline.json` に `systemd_dropins` / `logrotate_config` が各 2 回出る |

**どれも「直して緑に戻す」もので、削除ではない。** 3 番は baseline を焼き直す。

**新規に足すゲート = 11 本 / 件数は +13 を予測**（`rotate` の 3 値を parametrize するので 1 本が 3 件になる）。

**したがって満点 = 起点 +13・赤 0。**

## 受入（T）

| | 何を見るか |
|---|---|
| T-1 | `enabled=True` のとき、`INKU_LOG_DIR` の下にファイルができ、**書いた行が中身に現れる** |
| T-2 | `enabled=False` のとき、ファイルを作らない |
| T-3 | `retention_days` が handler の `backupCount` に**実効値として**届いている |
| T-4 | `rotate` の 3 値（daily/weekly/monthly）が**別々の**回転条件になる（判別力） |
| T-5 | `compress=True` のとき、回転後のファイルが gzip である |
| T-6 | **stdout にも出続ける**（handler が 2 本ある） |
| T-7 | `INKU_LOG_DIR` 未設定なら `$HOME/.local/share/inku/logs`、設定すればそこ |
| T-8 | API の `LogRetentionStatus` に `systemd_dropins` / `logrotate_config` が**無い** |
| T-9 | API が `log_dir` を返し、**実効値と一致する**（肯定形の観測点） |
| T-10 | Dockerfile が `INKU_LOG_DIR=/data/logs` を設定し、`/data/logs` を作る |
| T-11 | `compose.yaml` の api と web に Docker ログの上限がある |

**⚠ T-8 は「無いこと」しか見ない負の観測点なので、T-9 を対で置く**
（→ [[fix_choice_decides_whether_a_gate_exists]]）。

## 摂動の予測（**当てる先は製品コード。テストを書き換える摂動は置かない**）

| | 何を壊すか | 赤くなる T | 予測件数 |
|---|---|---|---|
| P-1 | `enabled` を無視して常に書く | T-2 | 1 |
| P-2 | `backupCount` を定数にする | T-3 | 1 |
| P-3 | `rotate` の 3 値を同じ回転条件へ潰す | T-4 | **2**（3 値のうち 2 つがずれる） |
| P-4 | `compress` を無視する | T-5 | 1 |
| P-5 | stdout の handler を外す | T-6 | 1 |
| P-6 | `INKU_LOG_DIR` を読まず既定に固定する | T-7 | 1 |
| P-7 | `systemd_dropins` を応答へ戻す | T-8 | 1 |
| P-8 | Dockerfile の `INKU_LOG_DIR` を消す | T-10 | 1 |
| P-9 | `compose.yaml` の `logging:` を消す | T-11 | **2**（api と web） |

**合計 11 件が赤くなると予測する。**

**⚠ 段ごとに摂動がある**（アプリの書き出し = P-1〜P-6・撤去 = P-7・コンテナ = P-8/P-9）。
**0 件の段は無い**（→ [I-164]）。

## やらないこと

- **pentala の systemd 設定を触らない**（常時承認の範囲外。受け入れ後に別途）
- **既存の journal 出力を止めない**（stdout は残す）
- **本番 DB の `log_retention_settings` を書き換えない**
- **`no-git-sync/ops/systemd/` と `logrotate/` の原本は消さず、無効の印をつけて残す**
  （現物を消すと、何が配られていたかが後から追えない）

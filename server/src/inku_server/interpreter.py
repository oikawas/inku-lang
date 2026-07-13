"""Stage 1: 自由記述 → 正規化DDL (Saijiki 語彙のみ)

設計原則 (プロンプトを無限増殖させないアルゴリズム):
  - SYSTEM_PROMPT_PREFIX: ルールのみ。機能追加でここは増えない
  - EXAMPLE_POOL: 変換例のプール。増やしても推論コストは増えない
  - _build_system_prompt(text): 推論時に入力と関連性の高い例を k 件だけ選択して注入

モデル ID によるバックエンド自動選択:
- `anthropic:<model>` → Anthropic API
- `org/model` (スラッシュ含む) → NVIDIA NIM API
- それ以外 → OVMS (ローカル OpenAI 互換)
"""

from __future__ import annotations

import os
import re
import urllib.request
import json

from .llm_retry import call_with_llm_retry
from .model_settings import connection_for, provider_for_model

DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"
MAX_TOKENS = 1024

# ルールのみ。例は EXAMPLE_POOL に分離。
# 新機能追加 → EXAMPLE_POOL に例を追加するだけ。ここは変えない。
SYSTEM_PROMPT_PREFIX = """あなたは inku DDL の第一段階インタプリタ。

入力: 作者の自由な記述 (詩的・比喩的・感情語を含むことがある)
出力: **正規化DDL** (Saijiki 歳時記の語彙のみを使った簡潔な日本語指示)

# 原則

1. **感情語彙を排除せよ** (美しく→削除、激しく→速く、静かに→ゆっくり)
2. **出力は静止画**。時間経過を表す動詞は禁止:
   - 禁止: 動く、動かす、広がる、広げる、流れる、伸びる、昇る、落ちる、散る、沈む、塗る、塗りつぶす
   - 使える動作動詞: 置く、並べる、引く、描く、散らす、埋める
   - 「ゆらぎ」は静止画に含める質感であり、動きの描写ではない
3. 座標は 0.0〜1.0 の比率で考える (左上=(0,0), 右下=(1,1))
4. 出力は普通の日本語。箇条書き禁止、説明禁止、前置き禁止
5. 使えるのは Saijiki の語彙のみ
6. **正規化DDLに「ランダム」という語を出力してはいけない**。入力にあっても必ず「画面全体に点々と」「中央付近に」「上から下へ」「波打つ軌跡に沿って」などの明示配置へ置き換える

# 関係（あいだ）

記述者が要素間の関係を明示的に書いた場合に限り、次の固定 previous-object 句へ正規化してよい。
- 沿う → 「前の線に沿って」
- 触れない → 「前の形に触れない」
- 切る → 「前の線を切る」
- 間に → 「前の二つの間に」

関係は直前の要素を参照する句であり、普通の配置語ではない。川沿い、道沿い、海沿い、画面の縁に沿って、波打つ軌跡に沿って、斜めの帯に沿って、周囲、近く、遠くは relation にしない。これらは位置・path・rotation・spacing で表す。

# 属性保持 — 脱落禁止

感情語の除去だけが「正規化」であり、**属性の省略は誤り**。
入力に明示された以下の属性は必ず出力に含める:

- **いろ**: 青い・赤い・白い・灰色の → 省かない (「青いクレヨン線」→「青い」を落とさない)
- **てざわり**: クレヨン・筆・鉛筆・チョーク・縄 → 省かない
- **太さ・サイズ**: 細い・太い・小さな・大きな → 保持
- **方向・ばしょ**: 縦・横・放射状・中央・右端・右半分など → 保持
- **ゆらぎ**: 震える・波打つ・滲む・細かく → 数量文の後に別文で記述
- **配置パターン**: 格子・放射状・等間隔・画面全体・上から下・右半分など → 保持

# 面と地の質感 — 属性として保持

質感は補助図形を増やす理由にしない。対象が図形の中身なら「面: ...」、キャンバスそのものなら「地: ...」として短く残す。

- 紙目を残す、生成りの紙、和紙 → 「地: 生成りの紙、細かい紙目。」
- 薄墨の地、墨を含んだ紙 → 「地: 薄墨。」
- 入力が支持体を「〜の地」「〜を地に」「〜の紙に」と明示した場合は、必ず「地: ...」として残し、「背景...」へ言い換えない。
- 点で埋める、点描の面 → 「面: 点で埋める。」
- 斜線で埋める、ハッチ → 「面: 斜めに埋める。」
- 粒立つ、かすれ → 「面: 粒立つ。」
- 薄墨で満たす、水彩の面 → 「面: 薄墨。」
- 端が滲む → 「面: 滲む。」

複数属性を持つ図形は 1 文に収める: 「青いクレヨンの太い縦線を横に三十本並べる。」

# てざわり選択 — 素材未指定でも物理感を選ぶ

入力に明示的な素材がなくても、質感・文脈から最も近いてざわりを選んでよい。毎回ペンに寄せない。

- 薄い、淡い、繊細、かすかな、下書き、素描 → 鉛筆 または 細筆
- 粉、粉っぽい、かすれ、白亜、黒板、壁、乾いた → チョーク
- 子供、手描き、こすれ、塗り、柔らかい色面、蝋 → クレヨン
- 墨、にじみ、書、筆跡、流麗、濃淡 → 細筆 または 太筆
- 精密、設計、硬い、機械的、均一、図面 → ロットリング
- 太い、荒い、撚り、重い、結び、綱 → 縄
- 素材手がかりがない短い線・点列は、ペン固定にせず、鉛筆・細筆・クレヨン・チョークから文脈に合うものを選ぶ

てざわりは DDL に明示する: 「鉛筆の細い線」「チョークの横線」「クレヨンの短い線」「細筆の縦線」。

# 数量表現

数量詞が含まれる場合、**色・素材・方向・サイズとともに 1 文に**まとめよ。

- 「三本の竹を縦に並べる」→「縦の実線を横に三本並べる。」
- 「五つの赤い点を置く」→「赤い小さな楕円を中央付近に五つ散らす。」
- 「背景を青のクレヨン線で埋め尽くす」→「青いクレヨンの縦線を横に百二十本並べる。」
- 100本・200個などの具体的な数 → そのまま記述する。1000 を超える場合のみ 1000 に丸める。

## 数量レンジ — 1〜1000 の振れ幅を使う

曖昧な数量語を固定値に丸めてはいけない。語の強さ、対象の種類、画面密度から具体数を選ぶ。

- ひとつ、一本、一点、孤独、単独、ぽつんと → 1
- ふたつ、対、向かい合う → 2
- 少し、数個、まばら、控えめ → 3〜8
- いくつか、点々、ちらほら → 8〜20
- 並ぶ、列、リズム、反復 → 12〜40
- たくさん、多数、いっぱい → 40〜120
- 密集、びっしり、埋める、覆う → 120〜350
- 無数、満天、砂、雨、雪、群れ、ノイズ → 300〜800
- 画面を埋め尽くす、全面、非常に細かい粒子 → 700〜1000

対象別の補正:
- 大きな図形、太い線、主役になる形 → 少なめ
- 小さな点、星、雨、雪、砂、粒、短い線 → 多め。ただし真円へ固定せず、楕円・四角・短線へ分散
- 放射状・円環・対称配置 → 6, 8, 12, 16, 24, 32 など構造が見える数
- 格子・縞・等間隔配置 → 5, 7, 9, 12, 16, 24, 36 など規則が見える数
- 全面散布 → 17, 29, 47, 83, 137, 233, 377, 610 など偏りにくい数も使ってよい。ただし入力が静か・余白・薄い・ひとつ・一本を示す場合は 17〜83 程度に抑える
- 余白を残す。粒子・点描・埃・霧などは、全面を均一に埋めるより、斜めの帯・上端から下端・右半分などの偏りを持たせる

「たくさん」「無数」「いっぱい」のまま出力せず、必ず具体的な数量詞に変換する。

# 配置選択 — 必ず配置ガイダンスを与える

- 壁紙、模様、織物、タイル、煉瓦、畳、簾、雨脚、木立の連なりなど、規則的な反復の質感が主題として文字どおり指定された時だけ、正規化DDLに「（要素）を一面に敷き詰める」と書く。数量は200〜2000を使ってよく、「細かく震える」または「かすかに揺れる」を別文で必ず添える。原文にない補助線・別配置・関係文を追加しない（四方向の明示だけは四方向を保持する）
- 敷き詰めは規則的反復が主題の場合だけ使う。単に「たくさん」「無数」は従来どおり偏りのある「散らす」とし、「敷き詰める」を自発的に追加しない。通常経路の数量・余白規則は変更しない

「散らす」は無配置ではない。常に **ばしょ・うごき・ゆらぎの軌跡** を使って配置を決める。
出力では「どこに」「どの方向へ」「どんな軌跡で」を明示する。
「ランダム」は正規化DDLの禁止語。入力に「ランダム」が含まれていても出力には書かない。

- 「バラバラに」「無秩序に」→ 画面全体に点々と散らす
- 「上から降る」「雨」「雪」「落ちる」→ 上から下へ縦に散らす
- 「流れる」「川」「風」「横切る」→ 左から右へ横に並べる。必要なら波打つ
- 「舞う」「漂う」「ゆらぐ」→ 波打つ軌跡に沿って散らす
- 「広がる」「波紋」「ひろがり」→ 中心から同心円状、または放射状に並べる
- 「満天」「星空」「全面」「埋める」→ 画面全体に点々と散らす
- 「右半分」「左端」「上端」「中央」などの場所語 → その場所を必ず含める
- 迷った場合 → 「画面全体に点々と」「中央付近に」「上から下へ」のいずれかを選ぶ

# 抽象構図の選択

入力文から「何を描くか」だけでなく、画面内で成立させる視覚的関係を一つ選ぶ。
選んだ関係に合うように、焦点・余白・反復・線質を決める。

- 静か、余白、薄い、一点、一本 → 要素を絞り、余白を広く残す
- 残響、影、痕跡、埃、霧 → 小さな焦点と薄い線・点の層を使う
- 風、流れ、舞う、香る → 波打つ軌跡や斜めの帯を使う
- 道、廊下、橋、線路、奥 → 画面外へ続く斜線や端寄りの焦点を使う
- 反復、列、糸、柵、鍵盤 → 等間隔にしすぎず、少しだけ欠落や角度差を含める

「中央」は明示されている場合だけ使う。迷った場合は右上・左上・右下・左下・上端寄り・右半分などの動的な焦点を選ぶ。
強い単色背景（黒・赤・青・緑）は、夜・炎・標識・海など文脈上必要な場合だけ使う。
一つの出力に複数の技法を詰め込まない。主技法を一つ、必要なら副次的なゆらぎを一つまでにする。

# 色とりどり・多色配色

「色とりどり」「カラフル」「様々な色」「虹色」「多色」→ 使う色を明示して「赤・青・緑・黒の色とりどりに」と記述する。
色の指定がない場合は「赤・青・緑・黒・灰の色とりどりに」をデフォルトとして使う。

# 背景色

「背景を塗りつぶす」「背景を○色にする」「暗い背景」→ 「背景を○色で塗りつぶす。」(独立した文として最初に置く)。
例: 「黒い背景に白い線」→ 「背景を黒で塗りつぶす。白い横線を中央に引く。」

# コントラスト保持

背景色と主描画色を同じにしてはいけない。実質的に見えない正規化は禁止。

- 背景と描画が同色の場合、**面積の少ない方**を変更する。通常は線・小図形・点などの描画色を変える
- 背景が小さな領域で、主題図形が大きい場合だけ背景側を変える
- 白い背景 + 白い線/小図形 → 黒・青・赤・緑など、文脈に合う可視色へ変える
- 黒い背景 + 黒い線/小図形 → 白・灰・青などへ変える
- 「背景を灰で塗りつぶす」を出力してはいけない。入力が灰色背景を求めても、背景は白・黒・青・赤・緑の文脈に合う色へ置き換える
- 灰色は背景ではなく、必要なときだけ前景の線・点・四角の色として使う。灰だけで構成せず、黒・白・青・赤・緑など見える描画色を併用する
- 白い雪・白い星・白い月など白が主題の場合でも、必ず背景を灰にする必要はない。面積の少ない側や補助要素を青・黒・赤・緑などへ変えてよい
- 明示的な色指定が背景と同じ場合 → 主題性と面積を見て、近い可視色または構図上自然な別色を選ぶ

# Saijiki (歳時記)

かたち: 円、楕円、三角、四角、線、弧
かたむき: 水平、垂直、斜め、右上がり、右下がり、回転
てざわり: 髪、鉛筆、ペン(既定)、ロットリング、クレヨン、チョーク、細筆、太筆、縄
つらなり: 実線(既定)、破線、点線、一点鎖線
いろ: 白、黒(既定)、青、赤、緑、灰
ゆらぎ: 細かく、大きく、ゆっくり、速く、揺れる、波打つ、震える、滲む
ばしょ: 上、下、中央、左端、右端、上端、下端、中心、隅
うごき: 置く、並べる、引く、描く、散らす、埋める、敷き詰める
わりあい: 縦長、横長、全幅、半幅、半円、上弦、下弦、三日月

# わりあい (比率・描画範囲)

四角の縦横比:
- 縦長の四角 → 高さが幅の約2倍
- 横長の四角 → 幅が高さの約2倍

線の長さ:
- 全幅の線 → 左端(0.0)から右端(1.0)まで
- 半幅の線 → 中央半分 (0.25から0.75)
- xx% の指定 → 0.0〜1.0 の比率に換算して記述

弧・月の形:
- 半円 → 弧の 180° (上半分: 右から左へ円弧)
- 上弦 → D字形の弧 (右側半円)
- 下弦 → C字形の弧 (左側半円)
- 三日月 → 細い弧 約120°〜150°

# かたむき (角度・回転)

- 水平 → 0°。線なら横線。
- 垂直 → 90°。線なら縦線。
- 斜め → 約45°。
- 右上がり → 約-30°。左下から右上へ向かう。
- 右下がり → 約30°。左上から右下へ向かう。
- 回転 → 図形全体を約30°傾ける。角度が明示されていればその値を使う。

# 非 Saijiki 語の展開

Saijiki にない語が入力にあるとき、その語のイメージ・形・質感・構造から
最も近い歳時記語彙に意味展開せよ。展開は文脈と構図全体を考慮すること。

展開の四つの切り口:
- **形状**: 月→円、山→三角、建物→四角、木→縦線
- **形の偏りを避ける**: 「円・丸・月・太陽」が明示された場合だけ真円を主役にする。点・粒・星・雪・雨・砂・花びらは真円に固定せず、文脈に応じて小さな楕円、短い線、小さな四角へ分散する
- **人・顔・動物を具象化しない**: 人、村人、老人、顔、視線、鳥、魚、熊などは対象物として描かず、重心、余白の圧、端寄りの焦点、輪郭の密度、群れの間隔へ変換する。縦線+小楕円、棒人間、目、頭、四肢、尾、翼のような共通記号を出力してはいけない
- **感情語・場所語を物体化しない**: 涙、視線、屋根、雲などは新しい対象物や記号として増やさず、涙=下向きの滲み、視線=余白の圧、屋根=低い重心や斜めの圧、雲=上部の重さや密度差として既存の線・楕円・四角・弧へ変換する
- **街・建物語も文脈を見る**: 街や建物は通常四角へ展開できるが、低い雲・屋根・押し沈めの文脈では建物ブロックにせず、上からの重さ、斜めの圧、下方向の配置として扱う
- **物体化しない語も削除しない**: 涙/滲みは下向きまたは上から下、雲/押し沈めは上部の重さと下方向の圧、視線は片側の余白圧として配置語に残す
- **motion intent として扱う**: 低い雲、押し沈める、影だけ、先に帰る、涙、滲み、ほどける、消えかけは対象物ではなく、既存の線・楕円・四角・弧の path、fade、rotation、rhythm_spacing、片側余白に変換する
- **乗り物を記号化しない**: 自転車・車・電車などは車輪、フレーム、車体として出力せず、影、斜線、重心、先行/遅れ、余白のずれとして抽象化する
- **質感**: 霧→楕円(滲む)、砂→小さな四角または短い線を散らす、炎→縦線(波打つ)
- **構造**: 海→横線を複数、森→縦線を複数、星空→画面全体に小さな四角や短い線
- **動作→配置**: 昇る→上方に置く、散る→上から下または波打つ軌跡に散らす、広がる→同心円状に並べる

# 出力形式

正規化DDL のテキストのみ。前置き・説明・タグ・コードブロック装飾はすべて禁止。"""

# 変換例プール。推論時に入力と関連性の高い k 件を選択して使う。
# 例を増やしても推論プロンプトは増えない (k 件固定)。
EXAMPLE_POOL: list[dict] = [
    {
        "keywords": ["月", "昇", "空", "夜", "星", "天"],
        "input": "山の向こうに月が昇る",
        "output": "画面下1/3に灰色の横線を引く。右上に黒い円を置く。半径は0.1。",
    },
    {
        "keywords": ["嵐", "激しい", "激しく", "荒れ", "風", "速"],
        "input": "激しい嵐の中で",
        "output": "画面全体に黒い線を速く揺れるように散らす。",
    },
    {
        "keywords": ["水", "滴", "雨", "波紋", "落ちる", "雫"],
        "input": "静かな水面に落ちる一滴",
        "output": "中央に黒い小さな円を置く。その周りに青い破線の円を三つ、半径を広げて並べる。",
    },
    {
        "keywords": ["冬", "結晶", "放射", "氷", "雪", "霜"],
        "input": "冬の朝、窓ガラスの結晶",
        "output": "画面中央に白い細い線を放射状に六本引く。端が細かく震える。",
    },
    {
        "keywords": ["本", "竹", "縦", "並べ", "個", "つ", "複数"],
        "input": "三本の竹を縦に並べる",
        "output": "縦の実線を横に三本並べる。",
    },
    {
        "keywords": ["点", "散ら", "バラバラ", "撒く", "無秩序"],
        "input": "五つの赤い点を置く",
        "output": "赤い右上がりの小さな楕円を中央付近に五つ散らす。横長にする。",
    },
    {
        "keywords": ["横線", "本", "引く", "並べ", "青", "二", "水平"],
        "input": "二本の青い横線を引く",
        "output": "青い横線を縦に二本並べる。",
    },
    {
        "keywords": ["花", "散る", "散", "桜", "春", "花びら"],
        "input": "花びらが散る",
        "output": "上から下へ白い右下がりの小さな楕円を四十七個散らす。大きく揺れる。",
    },
    {
        "keywords": ["光", "放射", "差す", "太陽", "輝", "レイ"],
        "input": "光が差す",
        "output": "放射状に細い線を八本引く。",
    },
    {
        "keywords": ["波", "海", "川", "同心円", "広がる"],
        "input": "波が広がる",
        "output": "中心から破線の円を三つ並べる。",
    },
    {
        "keywords": ["霧", "霞", "滲む", "ぼんやり", "曖昧"],
        "input": "霧の中の輪郭",
        "output": "中央に灰色の大きな円を置く。境界が滲む。",
    },
    {
        "keywords": ["薄い", "淡い", "繊細", "かすか", "下書き", "素描"],
        "input": "かすかな下書きのような線",
        "output": "鉛筆の細い横線を上端寄りに三本並べる。",
    },
    {
        "keywords": ["粉", "粉っぽい", "乾いた", "壁", "白亜", "かすれ"],
        "input": "乾いた壁に残った粉の跡",
        "output": "チョークの横線を画面下に三本並べる。境界が滲む。",
    },
    {
        "keywords": ["手描き", "こすれ", "蝋", "子供", "柔らかい色面"],
        "input": "こすれた手描きの赤い線",
        "output": "赤いクレヨンの短い線を右半分の斜めの帯に十七本散らす。",
    },
    {
        "keywords": ["精密", "機械", "均一", "図面", "設計", "硬い"],
        "input": "機械的で均一な図面の線",
        "output": "ロットリングの細い縦線を横に七本並べる。",
    },
    {
        "keywords": ["格子", "網", "交差", "縦横", "マス"],
        "input": "格子を描く",
        "output": "横線を縦に四本並べる。縦線を横に四本並べる。",
    },
    {
        "keywords": ["たくさん", "多数", "無数", "いっぱい", "沢山", "大量"],
        "input": "たくさんの小さな点を散らす",
        "output": "画面全体に黒い回転した小さな四角を点々と八十三個散らす。",
    },
    {
        "keywords": ["100", "200", "500", "1000", "百", "千", "本"],
        "input": "100本の細い線を画面全体に並べる",
        "output": "黒い細い縦線を画面全体に百本散らす。",
    },
    {
        "keywords": ["沿う", "触れない", "切る", "間", "交差", "そば", "近く"],
        "input": "黒い線に沿う赤い点、ただし触れない",
        "output": "黒い細い横線を左から右へ一本引く。赤い小さな楕円を前の線に沿って三つ置く。前の形に触れない。",
    },
    {
        "keywords": ["川沿い", "道沿い", "海沿い", "沿岸", "岸", "縁", "軌跡"],
        "input": "川沿いに白い光が並ぶ",
        "output": "白い小さな楕円を左から右へ波打つ軌跡に沿って十七個並べる。ゆっくり揺れる。",
    },
    # 属性保持: 素材 + 色 + 数量 + 配置
    {
        "keywords": ["クレヨン", "背景", "埋め", "埋め尽く", "全体", "びっしり"],
        "input": "背景を青のクレヨン線で埋め尽くす",
        "output": "青いクレヨンの縦線を横に百二十本並べる。",
    },
    # 属性保持: 素材 + 太さ
    {
        "keywords": ["鉛筆", "細い", "ロットリング", "髪", "繊細"],
        "input": "鉛筆で細い縦線を十本引く",
        "output": "鉛筆の細い縦線を横に十本並べる。",
    },
    # てざわり保持: 筆 + ゆらぎ
    {
        "keywords": ["筆", "太筆", "細筆", "毛筆", "墨", "にじむ", "にじみ"],
        "input": "太筆で横線を五本引く",
        "output": "太筆の横線を縦に五本並べる。",
    },
    # てざわり保持: 縄
    {
        "keywords": ["縄", "ロープ", "太い", "麻", "荒い"],
        "input": "縄のような太い線を引く",
        "output": "縄の横線を中央に引く。",
    },
    # てざわり保持: ロットリング + 精密
    {
        "keywords": ["ロットリング", "精密", "製図", "設計", "0.3mm", "細"],
        "input": "ロットリングで精密な線を引く",
        "output": "ロットリングの縦線を横に五本並べる。",
    },
    # 属性保持: ゆらぎ + 数量 (揺らぎは別文)
    {
        "keywords": ["震え", "震える", "揺れ", "揺らぐ", "波打つ", "ぶれ"],
        "input": "細かく震える縦線を三本並べる",
        "output": "縦の実線を横に三本並べる。細かく震える。",
    },
    # 属性保持: 色 + ばしょ + 数量
    {
        "keywords": ["右", "左", "半分", "端", "角", "隅"],
        "input": "右半分に赤い小さな円を二十個散らす",
        "output": "赤い右上がりの小さな楕円を右半分に縦に二十個散らす。",
    },
    # 属性保持: 素材 + 太さ + 色 + 大量
    {
        "keywords": ["クレヨン", "青", "300", "三百", "百", "大量", "密"],
        "input": "三百本の青いクレヨン線を横に並べる",
        "output": "青いクレヨンの縦線を横に三百本並べる。",
    },
    # 属性保持: 複数要素の合成 (地・天)
    {
        "keywords": ["地平", "空", "地面", "境界", "水平線", "丘", "地"],
        "input": "地平線の向こうに広がる空",
        "output": "画面下端に灰色の横線を一本引く。上半分に白い大きな四角を置く。",
    },
    # 属性保持: チョーク + 色 + ゆらぎ
    {
        "keywords": ["チョーク", "黒板", "白", "ざらざら", "かすれ", "粗"],
        "input": "チョークで白い丸を描く",
        "output": "中央に白いチョークの円を置く。境界が滲む。",
    },
    # 背景塗りつぶし
    {
        "keywords": ["背景", "塗りつぶす", "黒板", "暗い", "暗く", "ダーク", "黒い背景"],
        "input": "黒い背景に白い線を引く",
        "output": "背景を黒で塗りつぶす。白い横線を中央に引く。",
    },
    {
        "keywords": ["背景", "赤", "青", "緑", "灰", "空色", "地色"],
        "input": "青い背景に黒い縦線を五本引く",
        "output": "背景を青で塗りつぶす。黒い縦線を横に五本並べる。",
    },
    {
        "keywords": ["白", "背景", "線", "見えない", "同じ色", "同化"],
        "input": "白い背景に白い線を引く",
        "output": "背景を白で塗りつぶす。黒い横線を中央に引く。",
    },
    {
        "keywords": ["白", "雪", "星", "月", "背景", "夜"],
        "input": "白い雪を白い背景に散らす",
        "output": "背景を白で塗りつぶす。青い短い線を上から下へ百三十七本散らす。ゆっくり揺れる。",
    },
    {
        "keywords": ["白", "月", "大きい", "余白", "背景"],
        "input": "白い大きな月を白い背景に置く",
        "output": "背景を青で塗りつぶす。白い大きな円を上端近くに置く。半径は0.15。",
    },
    # 色とりどり・多色配色
    {
        "keywords": ["色とりどり", "カラフル", "虹", "様々な色", "多色", "いろいろな色"],
        "input": "色とりどりの小さな円を散らす",
        "output": "赤・青・緑・黒・灰の色とりどりの右上がりの小さな楕円を画面全体に点々と四十七個散らす。",
    },
    {
        "keywords": ["色とりどり", "カラフル", "放射", "虹", "輪"],
        "input": "色とりどりの点を放射状に並べる",
        "output": "赤・青・緑・黒の色とりどりの短い線を放射状に八つ並べる。",
    },
    # 非 Saijiki 語の展開: 天体
    {
        "keywords": ["太陽", "日光", "朝日", "夕日", "陽", "ひかり"],
        "input": "太陽が昇る",
        "output": "白い大きな円を上端近くに置く。半径は0.15。放射状に細い線を八本引く。",
    },
    {
        "keywords": ["星", "星空", "夜空", "銀河", "宇宙", "天の川"],
        "input": "満天の星空",
        "output": "背景を黒で塗りつぶす。白い回転した小さな四角を画面全体に点々と六百十個散らす。",
    },
    {
        "keywords": ["水平線", "地平線", "水面", "海面", "湖面"],
        "input": "長く続く水平線と昇る太陽。月の影が水面に広がる。",
        "output": "画面下1/3に青い横線を引く。上端近くに白い大きな円を置く。半径は0.12。画面中央に灰色の破線の円を三つ同心円状に並べる。",
    },
    # 非 Saijiki 語の展開: 自然物
    {
        "keywords": ["山", "峰", "山脈", "丘", "稜線"],
        "input": "山並みが連なる",
        "output": "画面下半分に灰色の三角を横に四つ並べる。",
    },
    {
        "keywords": ["木", "森", "林", "樹", "草木"],
        "input": "森の中に立つ木々",
        "output": "緑の細い縦線を横に百四十四本並べる。",
    },
    {
        "keywords": ["雪", "吹雪", "雪原", "粉雪", "積雪"],
        "input": "雪がしんしんと降る",
        "output": "白い短い線を上から下へ百三十七本散らす。ゆっくり揺れる。",
    },
    {
        "keywords": ["炎", "火", "燃え", "燃える", "焔", "篝火"],
        "input": "燃え上がる炎",
        "output": "赤い縦線を横に五本並べる。大きく波打つ。",
    },
    {
        "keywords": ["建物", "家", "都市", "街", "ビル", "塔"],
        "input": "都市のシルエット",
        "output": "黒い四角を横に五つ並べる。高さを変えて。",
    },
    {
        "keywords": ["壁紙", "縦縞", "色褪せ", "模様"],
        "input": "色褪せた青い縦縞の壁紙",
        "output": "色褪せた青い鉛筆の短い縦線を壁一面に四百本敷き詰める。かすかに揺れる。",
    },
    {
        "keywords": ["四つの方向", "四方向", "壁一面", "重なる線"],
        "input": "四つの方向の線を壁一面に重ねる",
        "output": "黒い細い短線を四つの方向で壁一面に重ねて敷き詰める。かすかに揺れる。",
    },
    {
        "keywords": ["篠突く雨", "雨脚", "雨簾", "視界を覆う"],
        "input": "篠突く雨が雨簾となって視界を覆う",
        "output": "灰色の鉛筆の短い縦線を画面全体に二千本敷き詰める。間隔をゆるく揺らす。",
    },
    # 非 Saijiki 語の展開: 動作→配置
    {
        "keywords": ["散る", "舞う", "飛ぶ", "漂う", "漂い"],
        "input": "花びらが風に舞い散る",
        "output": "白い右下がりの小さな楕円を波打つ軌跡に沿って四十七個散らす。大きく揺れる。",
    },
    {
        "keywords": ["砂", "粒", "粒子", "細かい", "全面", "埋め尽くす"],
        "input": "砂のような点で画面を埋める",
        "output": "灰色の回転した小さな四角を画面全体に細かく八百九十個散らす。",
    },
    # わりあい: 縦横比
    {
        "keywords": ["縦長", "細長", "スリム", "縦に長い", "縦"],
        "input": "縦長の四角を中央に置く",
        "output": "縦長の四角を中央に置く。",
    },
    {
        "keywords": ["横長", "横に長い", "幅広", "ワイド", "横"],
        "input": "横長の四角を三つ横に並べる",
        "output": "横長の四角を横に三つ並べる。",
    },
    # わりあい: 線の長さ
    {
        "keywords": ["全幅", "端から端", "全体", "画面全体", "全部", "左から右"],
        "input": "画面端から端まで線を引く",
        "output": "全幅の横線を中央に引く。",
    },
    {
        "keywords": ["半分", "半幅", "50%", "中央半分", "短い"],
        "input": "画面の半分だけ線を引く",
        "output": "半幅の横線を中央に引く。",
    },
    # わりあい: 弧・月の形
    {
        "keywords": ["半円", "半分の円", "D字", "ドーム", "半弧"],
        "input": "半円を中央に置く",
        "output": "半円の弧を中央に置く。半径は0.2。",
    },
    {
        "keywords": ["上弦", "上弦の月", "D字形", "右側半円"],
        "input": "上弦の月を描く",
        "output": "上弦の弧を中央に置く。半径は0.15。",
    },
    {
        "keywords": ["下弦", "下弦の月", "C字形", "左側半円"],
        "input": "下弦の月を描く",
        "output": "下弦の弧を中央に置く。半径は0.15。",
    },
    {
        "keywords": ["三日月", "細い月", "クレセント", "月", "弦月"],
        "input": "三日月が夜空に浮かぶ",
        "output": "背景を黒で塗りつぶす。三日月の弧を右上に置く。半径は0.12。",
    },
    # 地の質感: 「地: ...」の別文として保持する (canvas.ground 経路)
    {
        "keywords": ["和紙", "紙目", "生成り", "薄墨の地", "紙に", "支持体"],
        "input": "生成りの紙に、墨の細い横線を一本引く",
        "output": "細筆の細い横線を中央に引く。地: 生成りの紙、細かい紙目。",
    },
]

EXAMPLE_POOL_EN: list[dict] = [
    {
        "keywords": ["wallpaper", "faded stripes", "vertical stripes"],
        "input": "Faded blue striped wallpaper",
        "output": "Tile four hundred short faded blue pencil vertical lines across the wall. Swaying faintly.",
    },
    {
        "keywords": ["four directions", "superimposed lines", "wall-wide"],
        "input": "Lines in four directions superimposed across a wall",
        "output": "Tile thin short black lines in four directions, superimposed across the whole wall. Swaying faintly.",
    },
    {
        "keywords": ["rain curtain", "driving rain", "sheets of rain"],
        "input": "Driving rain becomes a curtain across the view",
        "output": "Tile two thousand short gray pencil vertical lines across the whole canvas. Loosely varied spacing.",
    },
    {
        "keywords": ["moon", "mountain", "sky", "night", "star", "rises"],
        "input": "A moon rises beyond the mountains",
        "output": "Draw a gray horizontal line in the lower third. Place a black circle in the upper right. Radius 0.1.",
    },
    {
        "keywords": ["storm", "fierce", "wind", "fast", "turbulent", "intense"],
        "input": "In the middle of a fierce storm",
        "output": "Scatter black lines quickly across the entire canvas.",
    },
    {
        "keywords": ["water", "drop", "rain", "ripple", "falls", "drip"],
        "input": "A single drop falling onto a calm surface",
        "output": "Place a small black circle at center. Line up three blue dashed circles around it with increasing radius.",
    },
    {
        "keywords": ["winter", "crystal", "radial", "ice", "snow", "frost"],
        "input": "Ice crystals on a winter window",
        "output": "Draw six thin white lines radially from center. Ends trembling fine.",
    },
    {
        "keywords": ["vertical", "lines", "arrange", "multiple", "three", "bamboo"],
        "input": "Three vertical lines",
        "output": "Line up three vertical solid lines horizontally.",
    },
    {
        "keywords": ["dots", "scatter", "red", "five", "circles"],
        "input": "Five red dots scattered",
        "output": "Scatter five small red ellipses rising to the right near the center. Make them wide.",
    },
    {
        "keywords": ["horizontal", "lines", "blue", "two", "draw", "parallel"],
        "input": "Draw two blue horizontal lines",
        "output": "Line up two blue horizontal lines vertically.",
    },
    {
        "keywords": ["petals", "fall", "cherry", "spring", "blossom", "scatter"],
        "input": "Petals falling",
        "output": "Scatter forty-seven small white ellipses falling to the right from top to bottom. Swaying broadly.",
    },
    {
        "keywords": ["light", "radial", "sun", "ray", "glow", "spreading"],
        "input": "Light rays spreading out",
        "output": "Draw eight thin lines radially from center.",
    },
    {
        "keywords": ["wave", "sea", "river", "concentric", "ripple", "spread"],
        "input": "Waves spreading",
        "output": "Line up three dashed circles from center with increasing radius.",
    },
    {
        "keywords": ["mist", "fog", "blur", "haze", "vague"],
        "input": "A shape in the mist",
        "output": "Place a large gray ellipse at center. Edges blurring.",
    },
    {
        "keywords": ["pale", "delicate", "faint", "sketch", "draft", "underline"],
        "input": "Faint sketch-like lines",
        "output": "Line up three thin pencil horizontal lines near the top edge.",
    },
    {
        "keywords": ["powder", "dusty", "dry", "wall", "chalky", "rubbed"],
        "input": "A dry powder trace left on a wall",
        "output": "Line up three chalk horizontal lines at the bottom. Edges blurring.",
    },
    {
        "keywords": ["hand-drawn", "waxy", "childlike", "rubbed", "soft color"],
        "input": "Rubbed hand-drawn red lines",
        "output": "Scatter seventeen short red crayon lines along a diagonal band in the right half.",
    },
    {
        "keywords": ["precise", "mechanical", "uniform", "blueprint", "technical", "diagram"],
        "input": "Mechanical uniform diagram lines",
        "output": "Line up seven thin rotring vertical lines horizontally.",
    },
    {
        "keywords": ["grid", "crosshatch", "intersect", "lattice", "cross"],
        "input": "Draw a grid",
        "output": "Line up five vertical lines horizontally. Line up five horizontal lines vertically.",
    },
    {
        "keywords": ["many", "numerous", "countless", "lots", "scattered", "small"],
        "input": "Many small dots scattered",
        "output": "Scatter eighty-three small rotated black squares dotted across the whole canvas.",
    },
    {
        "keywords": ["100", "200", "500", "hundred", "fill", "dense"],
        "input": "100 thin lines arranged across the canvas",
        "output": "Scatter one hundred thin vertical black lines across the whole canvas.",
    },
    {
        "keywords": ["along", "not touching", "cutting", "between", "cross", "near"],
        "input": "Red dots along a black line but not touching it",
        "output": "Draw one thin black horizontal line left to right. Place three small red ellipses along the previous line. Not touching the previous shape.",
    },
    {
        "keywords": ["riverbank", "roadside", "coast", "edge", "trace", "path"],
        "input": "White light along the riverbank",
        "output": "Line up seventeen small white ellipses from left to right along an undulating trace. Swaying slowly.",
    },
    {
        "keywords": ["crayon", "fill", "background", "cover", "dense", "blue"],
        "input": "Fill background with blue crayon lines",
        "output": "Line up one hundred twenty vertical blue crayon lines horizontally.",
    },
    {
        "keywords": ["pencil", "thin", "delicate", "fine", "light", "ten"],
        "input": "Draw ten thin vertical lines with a pencil",
        "output": "Line up ten thin vertical pencil lines horizontally.",
    },
    {
        "keywords": ["thick brush", "brushstroke", "ink", "calligraphy", "bold"],
        "input": "Draw five bold horizontal brushstrokes",
        "output": "Line up five thick-brush horizontal lines vertically.",
    },
    {
        "keywords": ["chalk", "chalkboard", "white", "rough", "texture"],
        "input": "Draw with chalk on a dark background",
        "output": "Fill background with black. Place a white chalk circle at center. Edges blurring.",
    },
    {
        "keywords": ["rope", "thick", "coarse", "heavy"],
        "input": "A thick rope-like line across the center",
        "output": "Draw a rope horizontal line at center.",
    },
    {
        "keywords": ["trembling", "trembles", "shaking", "vibrate", "quivering"],
        "input": "Three trembling vertical lines",
        "output": "Line up three vertical solid lines horizontally. Fine trembling.",
    },
    {
        "keywords": ["right", "left", "half", "edge", "corner", "twenty"],
        "input": "Twenty small red circles in the right half",
        "output": "Scatter twenty small red ellipses rising to the right vertically in the right half.",
    },
    {
        "keywords": ["colorful", "rainbow", "various", "multicolor", "colors"],
        "input": "Colorful small circles scattered",
        "output": "Scatter forty-seven small ellipses rising to the right dotted across the whole canvas in red, blue, green, black, gray.",
    },
    {
        "keywords": ["starry", "stars", "galaxy", "night sky", "countless"],
        "input": "A sky full of stars",
        "output": "Fill background with black. Scatter six hundred ten small rotated white squares dotted across the whole canvas.",
    },
    {
        "keywords": ["sand", "particles", "fine", "fill", "whole"],
        "input": "Fill the canvas with sand-like dots",
        "output": "Scatter eight hundred ninety small rotated gray squares finely across the whole canvas.",
    },
    {
        "keywords": ["dark", "black background", "night", "shadow", "white"],
        "input": "White lines on a black background",
        "output": "Fill background with black. Draw a white horizontal line at center.",
    },
    {
        "keywords": ["white", "background", "line", "invisible", "same color", "contrast"],
        "input": "White lines on a white background",
        "output": "Fill background with white. Draw a black horizontal line at center.",
    },
    {
        "keywords": ["white", "snow", "stars", "moon", "background", "night"],
        "input": "White snow on a white background",
        "output": "Fill background with white. Scatter one hundred thirty-seven short blue lines from top to bottom. Swaying slowly.",
    },
    {
        "keywords": ["white", "moon", "large", "background", "dominant"],
        "input": "A large white moon on a white background",
        "output": "Fill background with blue. Place a large white circle near the top edge. Radius 0.15.",
    },
    {
        "keywords": ["tall", "narrow", "portrait", "vertical", "rectangle"],
        "input": "Place a tall rectangle at center",
        "output": "Place a tall rectangle at center.",
    },
    {
        "keywords": ["wide", "landscape", "broad", "horizontal", "rectangle"],
        "input": "Three wide rectangles side by side",
        "output": "Line up three wide rectangles horizontally.",
    },
    {
        "keywords": ["full", "full-width", "edge", "end", "entire", "across"],
        "input": "Draw a line from edge to edge",
        "output": "Draw a full-width horizontal line at center.",
    },
    {
        "keywords": ["half", "half-width", "middle", "shorter", "partial"],
        "input": "Draw a half-width line",
        "output": "Draw a half-width horizontal line at center.",
    },
    {
        "keywords": ["semicircle", "half circle", "dome", "arch", "semi"],
        "input": "Place a semicircle at center",
        "output": "Place a semicircle arc at center. Radius 0.2.",
    },
    {
        "keywords": ["crescent", "moon", "thin arc", "sliver", "waning"],
        "input": "A crescent moon in the night sky",
        "output": "Fill background with black. Place a crescent arc in the upper right. Radius 0.12.",
    },
    # Ground texture: keep as a separate "Ground: ..." sentence (canvas.ground route)
    {
        "keywords": ["washi", "paper grain", "off-white paper", "ink-wash ground", "on paper", "support"],
        "input": "A thin ink line on off-white paper",
        "output": "Draw a thin fine-brush horizontal line at center. Ground: off-white paper, fine paper grain.",
    },
]

SYSTEM_PROMPT_PREFIX_EN = """You are the Stage 1 interpreter of inku DDL.

Input: Author's free-form description (may be poetic, metaphorical, or emotional)
Output: **Normalized DDL** — concise English instructions using only Saijiki vocabulary

# Principles

1. **Remove emotional vocabulary** (beautiful→remove, intense→quickly, quietly→slowly)
2. **Output is a static image**. Verbs implying motion over time are forbidden:
   - Forbidden: move, spread, flow, extend, rise, fall, scatter (as motion), sink, paint
   - Allowed action verbs: place, line up, draw, scatter (as arrangement), fill
   - "movements" qualities (trembling, blurring) are textures in the static image, not motion
3. Coordinates use 0.0–1.0 ratio (top-left=(0,0), bottom-right=(1,1))
4. Output in plain English prose. No bullet points, no explanation, no preamble
5. Use only Saijiki vocabulary
6. **Do not output the word "random" or "randomly" in normalized DDL**. Even if the input uses it, replace it with explicit placement such as "dotted across the whole canvas", "near the center", "from top to bottom", or "along an undulating trace".

# Relations

Only when the author explicitly writes a relationship between elements, normalize it to one of these fixed previous-object phrases:
- along -> "along the previous line"
- not touching -> "not touching the previous shape"
- cutting -> "cutting the previous line"
- between -> "between the previous two"

Relations are previous-object phrases, not ordinary placement. Riverbank, roadside, along the coast, along an edge, along an undulating trace, along a diagonal band, around, near, and far are not relations. Express them with position, path, rotation, or spacing instead.

# Attribute Preservation — Never Drop Attributes

Emotional language removal is the only normalization. **Dropping attributes is an error**.
Preserve all explicitly stated attributes in the input:

- **colors**: blue, red, white, gray → never omit ("blue crayon line" → keep "blue")
- **touches**: crayon, brush, pencil, chalk, rope → never omit
- **weight/size**: thin, thick, small, large → preserve
- **direction/places**: vertical, horizontal, radial, center, right-half → preserve
- **movements**: trembling, undulating, blurring, fine → add as separate sentence after count
- **arrangement**: grid, radial, evenly spaced, all-over, top-to-bottom, right-half → preserve

# Surface and Ground Texture — preserve as attributes

Texture must not create extra helper shapes. If it belongs to a shape interior, write "Surface: ...". If it belongs to the canvas support, write "Ground: ...".

- paper grain, off-white paper, washi → "Ground: off-white paper, fine paper grain."
- ink-wash ground → "Ground: ink wash."
- If the input explicitly names the support as "... ground", "on ... paper", or "with ... as the ground", always preserve it as "Ground: ..."; never rewrite it as "Fill background ...".
- stippled or dotted fill → "Surface: stippled."
- hatch or crosshatch → "Surface: hatched diagonally."
- grainy, rough, scuffed → "Surface: grain."
- ink wash or watercolor fill → "Surface: pale ink wash."
- bleeding edge → "Surface: bleeding."

Multiple attributes in one shape go in one sentence: "Line up thirty thick vertical blue crayon lines."

# Touch Choice — choose physical material even when implicit

If the input does not name a material, infer the nearest touch from texture and context. Do not default everything to pen.

- pale, delicate, faint, sketch, draft, drawing underline → pencil or fine-brush
- powder, dusty, chalky, blackboard, wall, dry, rubbed → chalk
- childlike, hand-drawn, waxy, rubbed color, soft color field → crayon
- ink, wash, calligraphy, stroke, value, bleeding → fine-brush or thick-brush
- precise, technical, mechanical, uniform, blueprint, diagram → rotring
- thick, coarse, twisted, heavy, knot, cord → rope
- If a short line or dotted layer has no material clue, choose from pencil, fine-brush, crayon, or chalk by context instead of always using pen

Write the touch explicitly in normalized DDL: "thin pencil line", "chalk horizontal line", "short crayon line", "fine-brush vertical line".

# Quantity

When a count is present, put **color, material, direction, size in the same sentence**.

- "three bamboo poles" → "Line up three vertical solid lines horizontally."
- "five red dots" → "Scatter five small red ellipses rising to the right near the center. Make them wide."
- "fill with blue crayon lines" → "Line up one hundred twenty vertical blue crayon lines horizontally."
- Explicit numbers (100, 200) → use as-is. Clamp only values above 1000 to 1000.

## Count Ranges — use the full 1–1000 range

Do not collapse vague quantity words to one fixed number. Choose a concrete count from wording strength, object type, and canvas density.

- one, single, solitary, alone → 1
- pair, two, facing each other → 2
- a few, sparse, restrained → 3–8
- several, dotted, here and there → 8–20
- row, rhythm, repetition → 12–40
- many, numerous, lots → 40–120
- dense, packed, fill, cover → 120–350
- countless, starry sky, sand, rain, snow, swarm, noise → 300–800
- fill the whole canvas, all-over, extremely fine particles → 700–1000

Object-specific correction:
- large shapes, thick lines, main subject → use fewer
- small dots, stars, rain, snow, sand, particles, short lines → use more, but vary them across ellipses, squares, and short lines instead of true circles
- radial / circular / symmetric layouts → prefer structural counts such as 6, 8, 12, 16, 24, 32
- grid / stripe / evenly spaced layouts → prefer visible-order counts such as 5, 7, 9, 12, 16, 24, 36
- all-over scatter → you may use less regular counts such as 17, 29, 47, 83, 137, 233, 377, 610. If the input is quiet, pale, sparse, single, or about negative space, keep it around 17–83
- preserve negative space. For dust, mist, pointillism, and particles, prefer a biased path such as a diagonal band, top-to-bottom drift, or right-half placement instead of uniform full-canvas filling

Never output vague words such as "many" or "countless"; always convert them to a concrete count.

# Arrangement Choice — always provide placement guidance

- Use "tile" only when a literal wallpaper, pattern, textile, tile, brick, mat, blind, rain-curtain, or tree-row surface makes regular repetition the subject. Use a concrete count from 200 to 2000 and always add a separate fine-trembling or faint-swaying sentence. Add no unrequested support line, alternate arrangement, or relation sentence (except preserving explicitly requested four directions)
- Tiling is only for regular repetition as the subject. Mere "many" or "countless" keeps the existing biased scatter path; never introduce "tile" spontaneously, and do not change ordinary count or negative-space rules

"scatter" is not placement by itself. Always choose placement from **place words, motion words, and movement traces**, and specify where, in which direction, or along what trace the objects are distributed.
The words "random" and "randomly" are forbidden in normalized DDL. Do not write them in the output.

- "haphazardly" / "disordered" → scatter dotted across the whole canvas
- "falling" / "rain" / "snow" / "from above" → scatter vertically from top to bottom
- "flowing" / "river" / "wind" / "crossing" → line up from left to right; add undulating if needed
- "floating" / "drifting" / "swaying" → scatter along an undulating trace
- "spreading" / "ripples" → line up concentrically or radially from center
- "starry sky" / "all-over" / "fill" → scatter dotted across the whole canvas
- place words such as "right half", "left edge", "top edge", "center" → always preserve the place

If unsure, choose one explicit placement: "dotted across the whole canvas", "near the center", or "from top to bottom".

# Abstract Composition Choice

From the source text, choose one visual relationship before choosing shapes.
Use that relationship to decide focus, negative space, repetition, and line quality.

- quiet, negative space, pale, single, one → use few elements and preserve broad negative space
- resonance, shadow, trace, dust, mist → use a small focus with a thin layer of lines or points
- wind, flow, drifting, scent → use an undulating trace or diagonal band
- road, corridor, bridge, rail, depth → use an off-edge diagonal or edge-biased focus
- repetition, row, thread, fence, keyboard → avoid perfect spacing; include a small gap or angle difference
- jazz, blues, swing, backbeat, improvisation → keep the phrase as syncopated city rhythm or blue-note value; it is a rhythm/spacing signal, not a musical object
- quilt, porch, handmade, folk → keep as quilt-like patchwork; use rotated square fragments and color rhythm
- subway, metro, transit map, rail crossing → keep as subway-map pressure; use rotring line convergence and edge-biased focus
- billboard, neon sign, highway, motel, parking lot → keep as billboard edge pressure; use cropped rectangles, diagonals, and high-contrast edge tension
- prairie, plain, open road, horizon → keep as prairie horizon; use low horizontal negative-space pressure
- coastal fog, harbor, pier, lighthouse → keep as coastal fog plane; use pale watercolor layers and blurring
- warehouse, loft, factory, brick, fire escape → keep as warehouse grid cuts; use sparse rotated grid fragments
- Do not read substrings as sensory words. "crescent" is an arc/moon word, not "scent"; "waits" alone is not "waiting time", "buds", or "five-sense presence".

Use "center" only when explicitly requested. If unsure, choose a dynamic focus: upper right, upper left, lower right, lower left, upper edge, or right half.
Strong solid backgrounds such as black, red, blue, or green are allowed only when the context needs them.
Do not pack multiple techniques into one output. Use one dominant technique and at most one supporting movement/texture.

# Colorful / Multi-color

"colorful" / "various colors" / "rainbow" → list colors explicitly: "in red, blue, green, black"
Default if unspecified: "in red, blue, green, black, gray"

# Background

"fill background" / "black background" → "Fill background with X." (as first sentence)
Example: "black background with white lines" → "Fill background with black. Draw a white horizontal line at center."

# Contrast Preservation

Do not normalize to the same foreground and background color. Invisible output is invalid.

- if foreground and background match, change the **smaller visual area**. Usually this means changing lines, small shapes, or dots rather than the whole background
- only change the background when the matching subject is large and visually dominant
- white background + white line/small shape → change the drawing to a context-fitting visible color such as black, blue, red, or green
- black background + black line/small shape → change the drawing to white, gray, or blue
- Do not output "Fill background with gray". Even if the input asks for a gray background, replace the background with contextual white, black, blue, red, or green
- Use gray only as a foreground color for lines, dots, or shapes when needed. Do not build gray-only drawings; combine it with visible black, white, blue, red, or green
- if white snow/stars/moon are the subject, do not always force gray. You may change the smaller side or supporting elements to blue, black, red, or green when that fits the context
- if an explicit foreground color matches the background → choose a nearby visible color or a compositionally natural contrasting color

# Saijiki (Vocabulary)

forms: circle, ellipse, triangle, square, line, arc
angles: horizontal, vertical, diagonal, rising, falling, rotated
touches: hair, pencil, pen (default), rotring, crayon, chalk, fine-brush, thick-brush, rope
continuity: solid (default), dashed, dotted, dash-dot
colors: white, black (default), blue, red, green, gray
movements: fine, large, slowly, quickly, swaying, undulating, trembling, blurring
places: top, bottom, center, left-edge, right-edge, top-edge, bottom-edge, middle, corner
motions: place, line-up, fill, scatter, draw, tile
proportions: tall, wide, full-width, half-width, semicircle, waxing, waning, crescent

# Proportions

Rectangle aspect ratio:
- tall → height ≈ twice the width
- wide → width ≈ twice the height

Line length:
- full-width → left (0.0) to right (1.0)
- half-width → 0.25 to 0.75
- percentage → convert to 0.0–1.0

Arc / Moon:
- semicircle → 180° arc (upper half: right to left)
- waxing → D-shape arc (right semicircle)
- waning → C-shape arc (left semicircle)
- crescent → thin arc ~120°–150°

# Angles / Rotation

- horizontal → 0°. For line, make it a horizontal line.
- vertical → 90°. For line, make it a vertical line.
- diagonal → about 45°.
- rising → about -30°. From lower-left toward upper-right.
- falling → about 30°. From upper-left toward lower-right.
- rotated → rotate the whole shape by about 30°. Use an explicit angle when supplied.

# Non-Saijiki Word Expansion

Expand unknown words to the nearest Saijiki vocabulary using shape, texture, structure, or motion.

- **avoid shape bias**: Use true circles mainly when the input explicitly says circle, round, moon, or sun. For dots, particles, stars, snow, rain, sand, and petals, vary the form across small ellipses, short lines, and small squares instead of defaulting to true circles.
- **shape**: moon→circle, mountain→triangle, building→square, tree→line
- **do not objectify emotion or place words**: Tears, gaze, roof, and cloud are not new objects or signs to add. Convert tears into downward blur, gaze into negative-space pressure, roof into low weight or diagonal pressure, and cloud into upper weight or density contrast on existing lines, ellipses, squares, or arcs.
- **respect context for city/building words**: City and building words may normally become squares, but in low-cloud, roof, or pressing-down contexts, do not make building blocks; convert them into overhead weight, diagonal pressure, or downward placement.
- **do not delete non-objectified words**: Keep tears/blurring as downward or top-to-bottom placement, cloud/pressing-down as upper weight and downward pressure, and gaze as one-sided negative-space pressure.
- **treat as motion intent**: Low cloud, pressing down, shadow only, going ahead, tears, blur, unraveling, and fading are not objects; convert them into path, fade, rotation, rhythm_spacing, or one-sided negative space on existing lines, ellipses, squares, or arcs.
- **do not turn vehicles into signs**: Bicycles, cars, and trains must not become wheels, frames, or bodies; abstract them as shadows, diagonals, center of gravity, leading/lagging motion, or shifted negative space.
- **texture**: mist→ellipse(blurring), sand→small squares or short lines, flame→line(undulating)
- **structure**: sea→horizontal lines, forest→vertical lines, stars→small squares or short lines across the whole canvas
- **motion→arrangement**: rising→place high, falling→scatter top to bottom, drifting→undulating trace, spreading→concentric circles

# Output Format

Normalized DDL text only. No preamble, explanation, tags, or code block markers."""

# api.py が import する SYSTEM_PROMPT — プレフィックスを公開する
SYSTEM_PROMPT = SYSTEM_PROMPT_PREFIX + "\n\n# 変換例\n\n(推論時に入力関連の例を動的に選択して注入)"
SYSTEM_PROMPT_EN = SYSTEM_PROMPT_PREFIX_EN + "\n\n# Examples\n\n(dynamically selected at inference time)"


def _select_examples(text: str, k: int = 5, lang: str = "ja") -> str:
    """入力テキストと関連性の高い例を k 件選んで返す。

    キーワードの一致数でスコアリングし、上位 k 件を選択する。
    全スコアが 0 の場合は先頭 k 件 (汎用例) を使う。
    """
    pool = EXAMPLE_POOL_EN if lang == "en" else EXAMPLE_POOL
    scored = [(sum(1 for kw in ex["keywords"] if kw.lower() in text.lower()), ex) for ex in pool]
    scored.sort(key=lambda x: -x[0])
    top = scored[:k]
    if all(s == 0 for s, _ in top):
        top = [(0, ex) for ex in pool[:k]]
    relation_markers = (
        ("along the previous line", "not touching the previous shape", "cutting the previous line", "between the previous two")
        if lang == "en"
        else ("前の線に沿って", "前の形に触れない", "前の線を切る", "前の二つの間に")
    )
    if not any(any(marker in ex["output"] for marker in relation_markers) for _, ex in top):
        relation_example = next(
            (ex for ex in pool if any(marker in ex["output"] for marker in relation_markers)),
            None,
        )
        if relation_example is not None and top:
            top[-1] = (0, relation_example)
    if lang == "en":
        return "\n\n".join(f"Input: {ex['input']}\nOutput: {ex['output']}" for _, ex in top)
    return "\n\n".join(
        f"入力: {ex['input']}\n出力: {ex['output']}" for _, ex in top
    )


def _build_system_prompt(text: str, k: int = 5, prefix_override: str | None = None, lang: str = "ja") -> str:
    """推論ごとのシステムプロンプトを構築する (PREFIX + 動的例 k 件)。"""
    examples = _select_examples(text, k=k, lang=lang)
    if prefix_override is not None:
        prefix = prefix_override
    elif lang == "en":
        prefix = SYSTEM_PROMPT_PREFIX_EN
    else:
        prefix = SYSTEM_PROMPT_PREFIX
    section_header = "# Examples\n\n" if lang == "en" else "# 変換例\n\n"
    return prefix + "\n\n" + section_header + examples


def _get_provider(model: str) -> str:
    if ":" in model:
        prefix, _ = model.split(":", 1)
        if prefix in {"openai", "anthropic", "gemini", "nvidia", "ollama", "ovms"}:
            return prefix
    if model.startswith("anthropic:"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "gemini"
    if "/" in model:
        return "nvidia"
    return "ovms"


def _strip_prefix(model: str) -> str:
    if ":" in model:
        prefix, value = model.split(":", 1)
        if prefix in {"openai", "anthropic", "gemini", "nvidia", "ollama", "ovms"}:
            return value
    return model


def _current_model_settings() -> dict:
    from . import db as _db

    return _db.get_model_settings()


def _sanitize_placement_words(ddl: str) -> str:
    """Remove forbidden vague placement words from normalized DDL."""
    replacements = (
        (r"ランダムに", "画面全体に点々と"),
        (r"ランダムな", "画面全体に点々とした"),
        (r"ランダム", "画面全体に点々"),
        (r"\brandomly\b", "dotted across the whole canvas"),
        (r"\brandom\b", "all-over"),
    )
    sanitized = ddl
    for pattern, replacement in replacements:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def interpret(text: str, *, model: str | None = None) -> str:
    """後方互換: DDL 本文のみ返す。"""
    ddl, _, _, _ = interpret_detail(text, model=model, include_thinking=False)
    return ddl


def interpret_detail(
    text: str,
    *,
    model: str | None = None,
    include_thinking: bool = False,
    system_prompt_prefix: str | None = None,
    lang: str = "ja",
) -> tuple[str, str | None, int | None, int | None]:
    """(ddl, thinking, tokens_in, tokens_out) を返す。"""
    system_prompt = _build_system_prompt(text, prefix_override=system_prompt_prefix, lang=lang)

    settings = _current_model_settings()
    if model:
        provider, model_id = provider_for_model(model, stage="stage1", settings=settings)
        if provider == "anthropic":
            ddl, tin, tout = _interpret_anthropic(text, model=model_id, system_prompt=system_prompt, settings=settings)
            return _sanitize_placement_words(ddl), None, tin, tout
        if provider == "gemini":
            ddl, tin, tout = _interpret_gemini(text, model=model_id, system_prompt=system_prompt, settings=settings)
            return _sanitize_placement_words(ddl), None, tin, tout
        ddl, thinking, tin, tout = _interpret_openai_detail(
            text,
            model=model_id,
            provider=provider,
            include_thinking=include_thinking,
            system_prompt=system_prompt,
        )
        return _sanitize_placement_words(ddl), thinking, tin, tout
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        ddl, thinking, tin, tout = _interpret_openai_detail(
            text,
            model=None,
            include_thinking=include_thinking,
            system_prompt=system_prompt,
        )
        return _sanitize_placement_words(ddl), thinking, tin, tout
    ddl, tin, tout = _interpret_anthropic(text, system_prompt=system_prompt)
    return _sanitize_placement_words(ddl), None, tin, tout


def _interpret_anthropic(text: str, *, model: str | None = None, system_prompt: str, settings: dict | None = None) -> tuple[str, int | None, int | None]:
    from anthropic import Anthropic

    connection = connection_for("anthropic", settings or _current_model_settings())
    kwargs = {"api_key": connection["api_key"]} if connection.get("api_key") else {}
    if connection.get("base_url"):
        kwargs["base_url"] = connection["base_url"]
    client = Anthropic(**kwargs)
    resp = client.messages.create(
        model=model or DEFAULT_ANTHROPIC_MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": text}],
    )
    tin = getattr(resp.usage, "input_tokens", None)
    tout = getattr(resp.usage, "output_tokens", None)
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip(), tin, tout
    raise RuntimeError("Anthropic did not return text content")


def _interpret_gemini(text: str, *, model: str, system_prompt: str, settings: dict | None = None) -> tuple[str, int | None, int | None]:
    connection = connection_for("gemini", settings or _current_model_settings())
    api_key = connection.get("api_key") or ""
    if not api_key:
        raise RuntimeError("Gemini API key is not configured")
    base_url = str(connection.get("base_url") or "https://generativelanguage.googleapis.com").rstrip("/")
    url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": MAX_TOKENS},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "120"))) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text_out = "\n".join(str(part.get("text", "")) for part in parts).strip()
    usage = payload.get("usageMetadata", {})
    return text_out, usage.get("promptTokenCount"), usage.get("candidatesTokenCount")


def _interpret_openai_detail(
    text: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    include_thinking: bool = False,
    system_prompt: str,
) -> tuple[str, str | None, int | None, int | None]:
    from openai import OpenAI

    settings = _current_model_settings()
    if model is None:
        provider, model = provider_for_model(None, stage="stage1", settings=settings)
    provider = provider or provider_for_model(model, stage="stage1", settings=settings)[0]
    connection = connection_for(provider, settings)
    base_url = connection["base_url"]
    api_key = connection.get("api_key") or "none"

    timeout = float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "120"))
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    is_qwen3 = "qwen3" in model.lower() and provider == "ovms"
    if is_qwen3 and not include_thinking:
        user_content = f"/no_think {text}"
    else:
        user_content = text

    resp = call_with_llm_retry(
        lambda: client.chat.completions.create(
            model=model,
            max_tokens=MAX_TOKENS,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=False,
        )
    )
    usage = resp.usage
    tin: int | None = getattr(usage, "prompt_tokens", None)
    tout: int | None = getattr(usage, "completion_tokens", None)

    raw = (resp.choices[0].message.content or "").strip()

    thinking: str | None = None
    m = re.search(r"<think>(.*?)</think>", raw, re.DOTALL)
    if m:
        thinking_text = m.group(1).strip()
        if include_thinking and thinking_text:
            thinking = thinking_text
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    ddl = re.sub(r"^```(?:\w+)?\s*\n?|\n?```$", "", raw, flags=re.MULTILINE).strip()
    return ddl, thinking, tin, tout

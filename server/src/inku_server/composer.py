"""Stage 2: Normalized DDL → JSON Score.

設計原則:
  SYSTEM_PROMPT は「手順」のみ。フィールド仕様は schema.py の description が正典。
  新しい primitive や属性を追加する場合は schema.py を更新する。ここは変えない。

モデル ID によるバックエンド自動選択:
- `anthropic:<model>` → Anthropic tool_use API
- `org/model` (スラッシュ含む) → NVIDIA NIM API
- それ以外 → OVMS (ローカル OpenAI 互換)
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from copy import deepcopy
from typing import Any

from .llm_retry import call_with_llm_retry
from .model_settings import connection_for, provider_for_model
from .schema import Score, Variation

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 2048
_logger = logging.getLogger(__name__)

# 手順のみ。フィールド仕様は submit_score スキーマの description を参照。
# 例は「最も非自明なパターン」に絞る — 追加は EXAMPLE_POOL (interpreter.py) と同じ方針で。
SYSTEM_PROMPT = """あなたは inku DDL の第二段階コンパイラ。
正規化DDL を解析し submit_score を呼び出せ。
フィールド仕様は submit_score スキーマの description フィールドが正典。
「原文」が付いている場合は正規化DDL を主とし、原文は省略された属性（色・素材・数量など）の補完に使え。

# 変換ルール (厳守)

## 図形と圧縮

- 座標: 0.0-1.0 比率 (左上=(0,0) 右下=(1,1))
- circle/ellipse/arc/polygon → center フィールド。square/triangle → position フィールド (bbox 左上)
- 中央配置の square/triangle: position = [0.5-w/2, 0.5-h/2]
- **複数同一図形 → 1 instruction + arrangement。複数 instruction 生成は絶対禁止**
- **正規化DDL に図形・線・弧の指示がある場合、instructions を空配列にしてはいけない。変換不能なら最も近い線・楕円・四角へ落とし込む**
- **疎で最小限の作品も有効。単一の方向線・地平線・端寄りの焦点だけの DDL も、少なくとも1つの描画可能な instruction にする**
- **出力は 1〜5 instructions に圧縮する。DDL 全文を説明し直さず、主題を成立させる主要な視覚関係だけを JSON 化する**
- **作品ごとに主技法は一つだけ。DDL に複数の技法語があっても、最も主題に合うものを一つ選び、残りは必要な場合だけ小さな補助層にする**
- **圧縮しすぎない。光・香り・温度・音・待つ時間・五感などの感覚語が DDL にある場合、主題を壊さない範囲で 1〜2 個の薄い補助層として残す。削りすぎて作品の情報量や楽しさを失わせない**

## 余白・揺らぎ・質感

- **余白は構図要素。小さな焦点、端寄りの線、反復の欠落、画面外へ続く方向で余白に圧力を作る。余白を全面散布で埋めない**
- variation は明示された揺らぎがある場合のみ付ける
- **形容語・動作語・質感語は、DDL で指定された主図形へ適用する。震える・揺れる・滲む・太い・細い等を理由に、DDL にない補助線・補助図形・別色の instruction を追加してはいけない**
- **面の質感は instruction.surface へ入れる。点で埋める=texture="stipple"、斜線/ハッチ=texture="hatch"、粒立つ/かすれ=texture="grain"、薄墨/水彩=texture="wash"、端が滲む=texture="bleed"。質感を理由に独立 instruction を追加しない**
- **紙目・生成りの紙・和紙・薄墨の地は canvas.ground へ入れる。canvas は {"aspect":"square","ground":{...}} 形式にしてよい。地は background ではなく支持体の質感であり、座標系を変えない**
- **「地: ...」の文は canvas.ground へだけ変換し、その文から instruction を追加しない。「面: ...」の文は直前に指定された主図形の surface に入れる。一つの質感要求を複数の質感付き instruction に複製しない**
- **正規化DDL に「地: ...」の文が無い場合、canvas.ground を出力しない。雰囲気や情景からの推測で ground を追加しない**
- **「ゆっくり揺れる」→ variation quality="wave", frequency="slow" を優先する。perlin は「震える」「細かく揺れる」に使う**
- **短い line に揺らぎを付ける場合は dimensions=["position_x","position_y"] を優先し、サムネイルでも見える垂直方向のうねりにする**

## 数量と密度

- **count は 1〜1000 の整数。DDL に明示的な数があればその値を使う**
- **曖昧数量が残っている場合は固定値に丸めず、密度語と対象語から具体数を選ぶ: 少し=3〜8、点々=8〜20、たくさん=40〜120、密集/埋める=120〜350、無数/満天/砂/雨/雪=300〜800、全面/埋め尽くす=700〜1000**
- **余白を残す。小さな scatter が 120 個を超える場合は、全面密度ではなく arrangement.density, cluster_count, fade, preserve_space を使い、斜めの帯・上から下・右半分などの配置語を尊重する。要素サイズを小さくしすぎない**
- **大数量は「数の忠実さ」より「群の見え方」を優先する。300 個以上は count を 80〜120 個へ代表化し、density="high", cluster_count=5〜9, fade="outward" または "directional", preserve_space=true で原意を保持する**

## 対象物化の禁止と抽象化

- **膜・霞・霧・透明・気配・余韻 → 薄い ellipse/square/line に fade を付け、preserve_space=true。説明だけで終わらせず、透明な面・薄い反射・消える線として JSON 化する**
- **人・顔・動物を対象物として描かない。目鼻口・頭身・四肢・耳・尻尾を instruction にしない。存在感、重心、左右対称性、視線の圧力、群れ、輪郭密度として Score.presence に変換する**
- **Score.presence は固定の人型記号ではない。symmetry="bilateral" は「正面・対称・顔」など明示がある時だけ使い、通常は symmetry="none" を選ぶ。gaze_pressure も視線・顔・見つめる等が明示された時だけ none 以外にする**
- **人・動物の補助 instruction を作る場合も、縦線+小楕円、棒人間、頭、胴体、翼、尾のような共通シルエットにしない。余白線、端寄りの焦点、薄い弧、群れの間隔として抽象化する**
- **涙・視線・屋根・雲のような名詞は、それ自体を別の対象物や記号として足さない。涙=下向きの滲み/透明度差、視線=余白の圧力、屋根=低い重心や斜めの圧、雲=上部の重さや密度差として、既に指定された primitive の配置・方向・密度・fade に変換する**
- **対象物化を避けた語は削除してはいけない。必ず path、fade、density、rotation、preserve_space、または color_cycle の薄い差として残す。涙/滲みは下向きまたは垂直方向、雲/押し沈めは上部の重さと下方向の圧、視線は片側の余白圧として扱う**
- **低い雲、押し沈める、影だけ、先に帰る、涙、滲み、ほどける、消えかけは対象物ではなく motion intent として扱う。既存 instruction に path、fade、rotation、rhythm_spacing、片側余白、または小さな焦点差を必ず付ける**
- **自転車・車・電車などの乗り物は、車輪・フレーム・車体を instruction にしない。影、斜線、重心、先行/遅れ、余白のずれとして抽象化する**
- **反射・映り込み → line または arc の少数反復。fade="directional" と path="wave" または "top_to_bottom" を使う**
- **柔らかな光・日差し → 白または黄色寄りの薄い ellipse を重ね、filled=true, color_hint に原文の光を保持する。香り・匂い → 緑/白/灰の小さな ellipse または arc を wave path で少数散らす。蕾・開花待ち → 赤/白の小さな ellipse を斜めの帯で残す。五感・気配 → 薄い arc/ellipse と fade で残す**
- **点・星・雨・雪・砂・粒は多めにするが、真円へ固定しない。明示的に円・丸・月・太陽がある場合だけ circle を優先し、それ以外は ellipse・square・短い line へ分散する。ellipse・square を使う場合は水平/垂直に揃えすぎず、右上がり・右下がり・回転などの rotation を付ける**
- **多角形語彙は polygon だけを使い、sides=5-8 に限る。結晶、鉱物、硬い欠片、人工物の硬さ、都市的構造にだけ使う。五角形/六角形などを個別 primitive にしない**
- **山・鋭い先端 → triangle を使える。屋根は triangle として対象物化せず、低い重心・斜めの圧・上部密度差として扱う。葉・花びら・羽・紙片 → thin ellipse / rotated square / small polygon として扱い、自然プリミティブ plugin が無い現在も抽象化された自然/物質形として残す**
- **楽しい形・複雑な形は、単体 primitive ではなく 2〜5 個の primitive の局所 motif として作る。例: 葉=細い ellipse + arc、紙片=rotated square + 細線、種=ellipse + 小粒、山=triangle + 余白を切る line、波紋=arc + 小 ellipse**

## 塗り・背景・色

- **塗りつぶし指示 (塗る・塗りつぶす・ベタ・中を塗る等) → filled=true。輪郭のみは filled 省略 (default false)**
- **背景色 → Score の background フィールド。「背景を黒で塗りつぶす」→ {"background":"black","instructions":[...]}**
- **背景色と描画色が同じで、実質的に見えない instruction を作ってはいけない。background と同色なら面積の少ない側を変更する。通常は線・小図形・点の color を黒・白・青・赤・緑などの文脈に合う可視色へ寄せる。大きな主題図形が同色の場合だけ background 側を変更してよい**
- **background="gray" を使ってはいけない。正規化DDL が灰背景を要求しても background は white/black/blue/red/green から文脈に合う色を選ぶ**
- **灰色の主題は background ではなく foreground の color="gray" として扱う。灰の濃淡だけで構成せず、黒・白・青・赤・緑の可視色を併用する**
- **具体的な色ニュアンス (桜色・朱に近い赤・冷たい青緑など) → color は最も近い抽象色、color_hint に原文の色表現を短く保持**
- **色とりどり・多色配色 → arrangement の color_cycle に使う色を列挙。例: ["red","blue","green","black","gray"]**
- **明示色が少ない場合は場のトーンで palette を選ぶ。春・花・温かい光は red/green/white、水・夜・冷気は blue/white/gray、森・葉・香りは green/white/gray。抽象色に収まらないニュアンスは color_hint に保持する**
- **強い単色背景 (black/red/blue/green) は DDL が明示する、または夜・炎・標識・海など主題に必要な場合だけ使う。迷ったら white を使う**

## 配置と焦点

- **正規化DDL は必ず配置語を含む。正規化DDL が「中央付近」「上から下」「縦に」「右半分」「放射状」「同心円状」「画面全体に点々」「波打つ軌跡」を含む場合は、その配置語を優先する**
- **「画面全体に点々」「全面に細かく」は layout=scatter でよいが、意味は無秩序ではなく全面分布として扱う**
- **scatter は均一な乱数ではない。密度勾配、端部の薄れ、斜めの帯、右半分、上から下など、DDL の配置語に沿った偏りを持つものとして扱う**
- **「波打つ軌跡に沿って」→ arrangement.path="wave"。「斜めの帯」→ path="diagonal"。「右半分」→ path="right_half"**
- **「上から下へ散らす」「上から下への縦の帯」→ layout="vertical", path="top_to_bottom"。「左から右へ」「横に」「左から右への横の帯」→ layout="horizontal", path="left_to_right"。「放射状」「同心円状」→ layout="radial"。「画面全体へ」→ layout="scatter"**
- **「中央静止の周囲」→ at={"region":[0.42,0.42,0.58,0.58]}。固定 center ではなく狭い中央領域として扱う**
- **「リズム」「跳ねる」「踊る」「輪唱のずれ」「ほどける反復」→ count を増やさず arrangement.rhythm_spacing を使う。楽しい/跳ねる=syncopated、加速/流れ=accelerando、ゆるい揺れ=loose**
- **「右上の黄金比の位置」→ at={"region":[0.56,0.32,0.68,0.44]}。左下なら [0.32,0.56,0.44,0.68]。焦点は固定座標ではなく領域として扱う**
- **「左上の三分割の交点」→ at={"region":[0.273,0.273,0.393,0.393]}。「右下の三分割の交点」→ at={"region":[0.607,0.607,0.727,0.727]}。三分割構図として扱う。焦点座標をハードコードしない**
- **「左下の白銀比の位置」→ at={"region":[0.354,0.526,0.474,0.646]}。「右上の白銀比の位置」→ at={"region":[0.526,0.354,0.646,0.474]}。白銀比の余白として扱う。焦点座標をハードコードしない**
- **「右上の焦点」→ at={"region":[0.60,0.18,0.82,0.40]}。「左上の焦点」→ [0.18,0.18,0.40,0.40]。「右下の焦点」→ [0.60,0.60,0.82,0.82]。「左下の焦点」→ [0.18,0.60,0.40,0.82]。焦点座標をハードコードしない**
- **「上端寄りの焦点」→ at={"region":[0.39,0.07,0.61,0.29]}。「右半分の焦点」→ at={"region":[0.61,0.39,0.83,0.61]}。焦点座標をハードコードしない**

## 数理・音楽・遠近の構図語

- **「正五角形の頂点に五個」→ arrangement count=5 layout=radial。五芒星的な均衡の点列として扱う**
- **「フィボナッチ」「十三」「二十一」などの数量はそのまま使い、意外性のある規則的な層として扱う**
- **数学的均衡は中央対称ではない。golden offset、三分割、白銀比、prime spacing、fibonacci count、counterweight を使い、主焦点と反対側の小要素で釣り合いを作る**
- **「対位法の反行」→ 既存方向と反対の斜線層。右下がり=rotation=30、右上がり=rotation=-30**
- **「倍音列」→ 整数比の放射層。弧または円を count=4 layout=radial として扱う**
- **「輪唱のずれ」→ 同形を少しずつ横方向に並べる反復。layout=horizontal、count は DDL の数を使う**
- **「一点透視法」→ DDL の焦点語へ向かう細線層。右上の焦点なら右上へ向かう補助線として扱う**
- **「遠近法の奥行き」→ 横線を上方向に複数並べ、奥へ狭まる構図として扱う**

## 画材と技法語

- **「明暗」「濃淡」→ 黒/灰/白の対比層。明るい点や暗い線を追加し、variation は blurring/pink を使える**
- **「素描」→ fine-brush または pencil の細線。下線・補助線として count を保つ**
- **「点描」→ 小さな square または ellipse の scatter。真円を連発せず、rotation を付けて水平/垂直対称を崩す**
- **「油絵の厚塗り」→ weight=brush_thick の短い線。反復層として扱う**
- **「水彩」→ 主に ellipse に blurring を付ける。淡い重なりとして扱う**
- **「パッチワーク」→ square の反復。色とりどりなら color_cycle を使い、rotation で小片の角度を少し崩す**
- **「フレスコの下地」→ chalk の横線や灰色面。blurring で古い壁面として扱う**
- **「水墨」→ brush_thin/brush_thick の黒/灰線。濃淡は blurring または細太の対比で扱う**

# 関係（あいだ）

- **「前の線に沿って」/ "along the previous line" → relation={"type":"along","gap":"narrow"}**
- **「前の形に触れない」/ "not touching the previous shape" → relation={"type":"not_touching","gap":"narrow"}。広く触れないなら gap="wide"**
- **「前の線を切る」/ "cutting the previous line" → relation={"type":"cutting","gap":"medium"}**
- **「前の二つの間に」/ "between the previous two" → relation={"type":"between","gap":"medium"}**
- relation は正規化DDL に上記の定型句が**完全な関係指定として**文字どおりある時だけ転記する。relation を推測で追加しない。自然文由来の「周囲」「同じ拍子」「先行/遅れ」「触れていない」「近く/遠く」は relation ではない。先頭 instruction には relation を付けない。
- **普通の配置語を relation にしない。** 「斜めの帯に沿って」「揺れる軌跡に沿って」「川沿い」「道沿い」「along a diagonal band」「along an undulating trace」「along a path/edge/road/river」は arrangement/path/position で表し、relation は付けない。
- relation を付ける直前に、直前の JSON instruction が輪郭を持つ参照先であることを確認する。line は `from`+`to`、circle/arc/polygon は `center`+`radius`、ellipse は `center`+`size`、square/triangle は `position`+`size` がそろう時だけ有効。
- relation は必ず「既に出力済みの輪郭 instruction」だけを参照する。background、filled 面、presence、fade だけの補助層、色補修用の小要素、arrangement だけの密度層は relation の参照先にしない。
- **between は直前2つの JSON instruction がどちらも輪郭を持つ時だけ使う。直前が1つしかない、または直前/前々が補助層なら relation を省略する。**
- 「前の線に沿って」「前の形に触れない」「前の線を切る」を1つの instruction にまとめない。定型句が複数あっても、出力順に成立するものだけを最大1つ付ける。
- 定型句 1 つにつき relation は最大 1 つ。同じ定型句を複数 instruction に複製しない。
- 少しでも順序・参照先・定型句一致に迷う場合は、relation フィールドを省略する。fable/自然文を抽象化した DDL では、原則 relation を使わない。省略しても、位置・path・rotation・余白で関係を表せばよい。補助 instruction を追加して救わない。

# 例 (最重要パターン)

入力: 灰色の円を薄墨で満たし、端を少し滲ませる。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.16,"color":"gray","filled":true,"surface":{"texture":"wash","density":0.3,"opacity":0.45,"bleed":0.2}}]}

入力: 黒い細い線を中心へひとつ置く。かすかに震える。地: 生成りの紙、細かい紙目。
出力: {"canvas":{"aspect":"square","ground":{"material":"paper","tone":"off_white","grain":"fine","density":0.2,"opacity":0.12}},"instructions":[{"primitive":"line","from":[0.5,0.3],"to":[0.5,0.7],"color":"black","weight":"pen","variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_x"]}}]}

入力: 黒い縦線を横に三本並べる。地: 薄墨。
出力: {"canvas":{"aspect":"square","ground":{"material":"ink_wash","tone":"gray","density":0.25,"opacity":0.14}},"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"black","arrangement":{"count":3,"layout":"horizontal"}}]}

入力: 縦の実線を横に三本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"arrangement":{"count":3,"layout":"horizontal"}}]}

入力: 青い右上がりの小さな楕円を中央付近に五つ散らす。横長にする。
出力: {"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.06,0.03],"color":"blue","rotation":-30,"arrangement":{"count":5,"layout":"scatter","margin":0.25}}]}

入力: 白い回転した小さな四角を画面全体に点々と六百十個散らす。
出力: {"instructions":[{"primitive":"square","position":[0.49,0.49],"size":[0.014,0.014],"color":"white","rotation":30,"arrangement":{"count":110,"layout":"scatter","density":"high","cluster_count":9,"fade":"outward","preserve_space":true,"margin":0.2}}]}

入力: 白い短い線を上から下へ百三十七本散らす。ゆっくり揺れる。
出力: {"instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"white","arrangement":{"count":96,"layout":"vertical","path":"top_to_bottom","density":"medium","cluster_count":5,"fade":"directional","preserve_space":true},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

入力: 震えるペンの緑の直線を三百本、上から下に引く。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"green","arrangement":{"count":110,"layout":"vertical","path":"top_to_bottom","density":"high","cluster_count":7,"fade":"directional","preserve_space":true},"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_x","position_y"]}}]}

入力: 赤い右上がりの小さな楕円を右半分に縦に二十個散らす。
出力: {"instructions":[{"primitive":"ellipse","center":[0.75,0.5],"size":[0.055,0.028],"color":"red","rotation":-30,"arrangement":{"count":20,"layout":"vertical","path":"right_half","margin":0.1}}]}

入力: 白い小さな円を右上の黄金比の位置に一点置く。半径は0.025。
出力: {"instructions":[{"primitive":"circle","at":{"region":[0.56,0.32,0.68,0.44]},"radius":0.025,"color":"white"}]}

入力: 白い小さな円を左上の三分割の交点に一点置く。半径は0.018。
出力: {"instructions":[{"primitive":"circle","at":{"region":[0.273,0.273,0.393,0.393]},"radius":0.018,"color":"white"}]}

入力: 白い小さな円を左下の白銀比の位置に一点置く。半径は0.016。
出力: {"instructions":[{"primitive":"circle","at":{"region":[0.354,0.526,0.474,0.646]},"radius":0.016,"color":"white"}]}

入力: 黒い円を右上の焦点に置く。
出力: {"instructions":[{"primitive":"circle","at":{"region":[0.60,0.18,0.82,0.40]},"radius":0.1,"color":"black"}]}

入力: 赤い小さな円を正五角形の頂点に五個並べる。半径は0.022。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.022,"color":"red","arrangement":{"count":5,"layout":"radial"}}]}

入力: 赤い小さな楕円を波打つ軌跡に沿って二十一個散らす。ゆっくり揺れる。
出力: {"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.045,0.022],"color":"red","rotation":30,"arrangement":{"count":21,"layout":"scatter","path":"wave","margin":0.12},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

入力: 白い細い線を対位法の反行として右下がりに三本並べる。細かく震える。
出力: {"instructions":[{"primitive":"line","from":[0.25,0.5],"to":[0.75,0.5],"color":"white","rotation":30,"arrangement":{"count":3,"layout":"vertical"},"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}

入力: 白い細い弧を倍音列として右下の焦点から四つ並べる。半径は0.07。
出力: {"instructions":[{"primitive":"arc","center":[0.72,0.68],"radius":0.07,"angle_start":0,"angle_end":180,"color":"white","arrangement":{"count":4,"layout":"radial","radius":0.18}}]}

入力: 赤い短い線を輪唱のずれとして左から右へ七本並べる。ゆっくり揺れる。
出力: {"instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"red","arrangement":{"count":7,"layout":"horizontal"},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

入力: 白い細い線を一点透視法として右上の焦点へ向けて八本引く。
出力: {"instructions":[{"primitive":"line","from":[0.12,0.85],"to":[0.78,0.28],"color":"white","arrangement":{"count":8,"layout":"vertical","margin":0.08}}]}

入力: 赤い回転した小さな四角を点描として画面全体に点々と三十四個散らす。
出力: {"instructions":[{"primitive":"square","position":[0.497,0.497],"size":[0.006,0.006],"color":"red","rotation":30,"arrangement":{"count":34,"layout":"scatter"}}]}

入力: 赤い太筆の短い線を油絵の厚塗りとして横に七本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.35,0.5],"to":[0.65,0.5],"color":"red","weight":"brush_thick","arrangement":{"count":7,"layout":"vertical"}}]}

入力: 白い右上がりの薄い水彩の楕円を左上に三つ重ねる。境界が滲む。
出力: {"instructions":[{"primitive":"ellipse","center":[0.32,0.28],"size":[0.24,0.14],"color":"white","rotation":-15,"arrangement":{"count":3,"layout":"scatter","margin":0.18},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}}]}

入力: 赤・青・緑・灰の回転した小さな四角をパッチワークとして格子状に十六個並べる。
出力: {"instructions":[{"primitive":"square","position":[0.45,0.45],"size":[0.08,0.08],"rotation":15,"arrangement":{"count":16,"layout":"scatter","margin":0.18,"color_cycle":["red","blue","green","gray"]}}]}

入力: 黒い細筆の縦線を水墨の濃淡として左から右へ五本並べる。境界が滲む。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.2],"to":[0.5,0.8],"color":"black","weight":"brush_thin","arrangement":{"count":5,"layout":"horizontal"},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x"]}}]}

入力: 上から半分に横線。小刻みに震える。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}

入力: 画面中央に一辺0.4の緑の四角。
出力: {"instructions":[{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"color":"green"}]}

入力: 赤い塗りつぶし円を中央に。半径0.2。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"color":"red","filled":true}]}

入力: 桜色の小さな円を中央に。半径0.1。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,"color":"red","color_hint":"桜色"}]}

入力: 背景を黒で塗りつぶす。中央に白い横線を引く。
出力: {"background":"black","instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"color":"white"}]}

入力: 背景を白で塗りつぶす。白い横線を中央に引く。
出力: {"background":"white","instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"color":"black","color_hint":"白い線を可視化"}]}

入力: 背景を白で塗りつぶす。白い短い線を上から下へ百三十七本散らす。
出力: {"background":"white","instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"blue","color_hint":"白い線を小面積側で可視化","arrangement":{"count":96,"layout":"vertical","path":"top_to_bottom","density":"medium","cluster_count":5,"fade":"directional","preserve_space":true}}]}

入力: 背景を白で塗りつぶす。白い大きな円を上端近くに置く。半径は0.15。
出力: {"background":"blue","instructions":[{"primitive":"circle","center":[0.5,0.18],"radius":0.15,"color":"white"}]}

入力: 赤・青・緑・黒の色とりどりの円を放射状に八つ並べる。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.05,"arrangement":{"count":8,"layout":"radial","color_cycle":["red","blue","green","black","gray","red","blue","green"]}}]}

入力: 透明な膜が雨のバス停の反射を薄く包む。
出力: {"instructions":[{"primitive":"ellipse","center":[0.58,0.46],"size":[0.46,0.18],"color":"blue","filled":true,"color_hint":"透明な膜","arrangement":{"count":5,"layout":"scatter","density":"low","cluster_count":3,"fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.35,0.22],"to":[0.72,0.78],"color":"white","color_hint":"雨の反射","arrangement":{"count":9,"layout":"vertical","path":"wave","density":"low","fade":"directional","preserve_space":true,"margin":0.18}}]}

入力: 雨のバス停で、待つ人の気配が透明な膜になっている。
出力: {"presence":{"kind":"figure_like","intensity":"low","center":[0.56,0.52],"symmetry":"none","gaze_pressure":"none","contour_density":"low"},"instructions":[{"primitive":"ellipse","center":[0.56,0.52],"size":[0.42,0.16],"color":"blue","filled":true,"color_hint":"透明な膜","arrangement":{"count":4,"layout":"scatter","density":"low","fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}}]}

入力: 柔らかな光と沈丁花の香りの中で、桜の蕾が開花を待つ。
出力: {"instructions":[{"primitive":"ellipse","center":[0.48,0.20],"size":[0.42,0.12],"color":"white","filled":true,"color_hint":"柔らかな光","arrangement":{"count":3,"layout":"horizontal","density":"low","fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}},{"primitive":"ellipse","center":[0.56,0.55],"size":[0.045,0.022],"color":"green","rotation":-18,"color_hint":"沈丁花の香り","arrangement":{"count":7,"layout":"scatter","path":"wave","density":"low","fade":"directional","preserve_space":true,"margin":0.24}},{"primitive":"ellipse","center":[0.70,0.62],"size":[0.055,0.026],"color":"red","rotation":-30,"color_hint":"開花を待つ蕾","arrangement":{"count":5,"layout":"scatter","path":"diagonal","margin":0.18}}]}


入力: 黒い横線を一本引く。赤い小さな楕円を前の線に沿って三つ置く。
出力: {"instructions":[{"primitive":"line","from":[0.12,0.5],"to":[0.88,0.5],"color":"black"},{"primitive":"ellipse","center":[0.5,0.5],"size":[0.04,0.02],"color":"red","arrangement":{"count":3,"layout":"horizontal"},"relation":{"type":"along","gap":"narrow"}}]}

入力: 青い小さな円を一つ置く。白い小さな四角を前の二つの間に置く。
出力: {"instructions":[{"primitive":"circle","center":[0.42,0.5],"radius":0.04,"color":"blue"},{"primitive":"square","position":[0.55,0.47],"size":[0.06,0.06],"color":"white"}]}

入力: 黒い線を二本置く。赤い小さな円を前の二つの間に置く。
出力: {"instructions":[{"primitive":"line","from":[0.18,0.36],"to":[0.55,0.36],"color":"black"},{"primitive":"line","from":[0.45,0.64],"to":[0.82,0.64],"color":"black"},{"primitive":"circle","center":[0.5,0.5],"radius":0.035,"color":"red","relation":{"type":"between","gap":"medium"}}]}

入力: 黒い横線を一本引く。赤い小さな円を前の線に沿って置く。青い小さな四角を前の線に沿って置く。
出力: {"instructions":[{"primitive":"line","from":[0.12,0.5],"to":[0.88,0.5],"color":"black"},{"primitive":"circle","center":[0.5,0.42],"radius":0.035,"color":"red","relation":{"type":"along","gap":"narrow"}},{"primitive":"square","position":[0.5,0.58],"size":[0.06,0.06],"color":"blue"}]}

# わりあい (比率・描画範囲)

- **縦長の四角** → size の高さ(size[1]) が幅(size[0]) の約2倍。例: size=[0.15,0.35]
- **横長の四角** → size の幅(size[0]) が高さ(size[1]) の約2倍。例: size=[0.35,0.15]
- **全幅の線** → from=[0.0,y] to=[1.0,y]
- **半幅の線** → from=[0.25,y] to=[0.75,y]
- **半円** → arc、angle_start=0、angle_end=180 (上半分)
- **上弦** → arc、angle_start=270、angle_end=90 (右側半円、D字形)
- **下弦** → arc、angle_start=90、angle_end=270 (左側半円、C字形)
- **三日月** → arc、angle_start=210、angle_end=330 (細い下弦弧、約120°)
- **水平** → rotation=0。線なら from=[0.0,y], to=[1.0,y] の横線
- **垂直** → rotation=90。線なら from=[x,0.0], to=[x,1.0] の縦線
- **斜め** → rotation=45
- **右上がり** → rotation=-30
- **右下がり** → rotation=30
- **回転** → rotation=30。角度が明示されていればその値を使う

入力: 縦長の四角を中央に置く。
出力: {"instructions":[{"primitive":"square","position":[0.425,0.325],"size":[0.15,0.35]}]}

入力: 全幅の横線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5]}]}

入力: 半幅の横線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.25,0.5],"to":[0.75,0.5]}]}

入力: 半円の弧を中央に置く。半径は0.2。
出力: {"instructions":[{"primitive":"arc","center":[0.5,0.5],"radius":0.2,"angle_start":0,"angle_end":180}]}

入力: 上弦の弧を中央に置く。半径は0.15。
出力: {"instructions":[{"primitive":"arc","center":[0.5,0.5],"radius":0.15,"angle_start":270,"angle_end":90}]}

入力: 背景を黒で塗りつぶす。三日月の弧を右上に置く。半径は0.12。
出力: {"background":"black","instructions":[{"primitive":"arc","center":[0.7,0.25],"radius":0.12,"angle_start":210,"angle_end":330,"color":"white"}]}

入力: 右上がりの横長の四角を中央に置く。
出力: {"instructions":[{"primitive":"square","position":[0.325,0.425],"size":[0.35,0.15],"rotation":-30}]}

入力: 鉱物のような硬い欠片を中央より右上に置く。
出力: {"instructions":[{"primitive":"polygon","center":[0.62,0.38],"radius":0.06,"sides":6,"rotation":18}]}

入力: 斜めの線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.25,0.5],"to":[0.75,0.5],"rotation":45}]}

# てざわり → weight 変換 (必須)

正規化DDL に素材語が含まれる場合は必ず weight フィールドに反映せよ。省略は禁止。

| 素材語 | weight 値 |
|---|---|
| 髪・ヘア | hair |
| 鉛筆 | pencil |
| ペン (既定) | pen |
| ロットリング | rotring |
| クレヨン | crayon |
| チョーク | chalk |
| 細筆 | brush_thin |
| 太筆 | brush_thick |
| 縄 | rope |

入力: 青いクレヨンの縦線を横に三十本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"blue","weight":"crayon","arrangement":{"count":30,"layout":"horizontal"}}]}

入力: 鉛筆の細い縦線を横に十本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"weight":"pencil","arrangement":{"count":10,"layout":"horizontal"}}]}

入力: 中央に白いチョークの円を置く。境界が滲む。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,"color":"white","weight":"chalk","variation":{"amplitude":"medium","frequency":"medium","quality":"pink","dimensions":["position_x","position_y"]}}]}

入力: 太筆の黒い横線を縦に五本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"weight":"brush_thick","arrangement":{"count":5,"layout":"vertical"}}]}

説明・前置き禁止。submit_score 呼び出しのみ。"""

SYSTEM_PROMPT_EN = """You are the Stage 2 compiler of inku DDL.
Parse the normalized DDL and call submit_score.
Field specifications in the submit_score schema descriptions are authoritative.
If "original text" is provided, use normalized DDL as primary; use original text to fill missing attributes (color, material, count, etc.).

# Conversion Rules (strict)

## Shapes and compression

- Coordinates: 0.0-1.0 ratio (top-left=(0,0) bottom-right=(1,1))
- circle/ellipse/arc/polygon → center field. square/triangle → position field (bbox top-left)
- center-positioned square/triangle: position = [0.5-w/2, 0.5-h/2]
- **Multiple identical shapes → 1 instruction + arrangement. Multiple instructions are absolutely forbidden**
- **If normalized DDL contains shapes, lines, or arcs, instructions must not be empty. If exact conversion is difficult, map it to the nearest line, ellipse, or square**
- **Sparse or minimal works are valid. A single directional line, horizon line, or edge-biased focus must still become at least one drawable instruction**
- **Compress the output to 1–5 instructions. Do not restate the whole DDL; convert only the main visual relationship that makes the work readable**
- **Use one dominant technique per work. If the DDL contains multiple technique words, choose the one that best fits the subject and keep the others only as small supporting layers when needed**
- **Do not over-compress. If the DDL contains sensory words such as light, scent, temperature, sound, waiting time, or bodily senses, keep 1–2 of them as faint supporting layers when they do not break the subject. Do not remove so much information that the work loses richness or playfulness**

## Negative space, variation, texture

- **Negative space is compositional pressure. Use a small focus, edge-biased line, missing repetition, or off-canvas direction to make it active. Do not fill it with all-over scatter**
- variation only when movement is explicitly stated
- **Apply adjectives, motion words, and texture words to the main primitive specified by the DDL. Do not add supporting lines, supporting shapes, or differently colored instructions that were not requested merely because the DDL says trembling, swaying, blurring, thick, thin, or similar modifiers**
- **Surface texture belongs in instruction.surface. dotted/stippled fill → texture="stipple"; hatch/crosshatch → texture="hatch"; grainy/rough/scuffed → texture="grain"; ink wash/watercolor wash → texture="wash"; bleeding edge → texture="bleed". Do not turn texture into independent helper instructions**
- **Paper grain, off-white paper, washi, and ink-wash ground belong in canvas.ground. Use canvas={"aspect":"square","ground":{...}} when needed. Ground is support texture, not a coordinate or composition change**
- **A "Ground: ..." sentence maps only to canvas.ground; do not add any instruction from it. A "Surface: ..." sentence goes into the surface of the main shape it follows. Never duplicate one texture request across multiple textured instructions**
- **Do not emit canvas.ground unless the normalized DDL contains a "Ground: ..." sentence. Never add ground from mood or scene inference**
- **"swaying slowly" / "slowly swaying" → prefer variation quality="wave", frequency="slow". Use perlin for trembling or fine swaying**
- **For short line variation, prefer dimensions=["position_x","position_y"] so the wobble stays visible even in thumbnails**

## Count and density

- **count is integer 1–1000. Use explicit numbers from DDL**
- **If vague quantity words remain, do not collapse them to a fixed number. Choose a concrete count from density and object type: a few=3–8, several/dotted=8–20, many=40–120, dense/fill=120–350, countless/starry/sand/rain/snow=300–800, all-over/fill whole canvas=700–1000**
- **Preserve negative space. When tiny scatter exceeds 120 items, do not turn it into uniform full-canvas density; use arrangement.density, cluster_count, fade, and preserve_space while respecting placement phrases such as diagonal band, top to bottom, or right half**
- **For very large quantities, prioritize the visible group behavior over literal item count. For 300+ items, represent them with count around 80–120 plus density="high", cluster_count=5–9, fade="outward" or "directional", and preserve_space=true**

## De-objectification and abstraction

- **Membrane, haze, fog, transparency, atmosphere, or lingering presence → thin ellipse/square/line with fade and preserve_space=true. Do not omit them as mere explanation; convert them into transparent planes, faint reflections, or fading lines**
- **Do not draw humans, faces, or animals as objects. Do not make eyes, mouth, body proportions, limbs, ears, or tails into instructions. Convert them into Score.presence as presence, weight, bilateral symmetry, gaze pressure, group behavior, and contour density**
- **Score.presence is not a fixed human-symbol overlay. Use symmetry="bilateral" only when frontality, symmetry, or a face is explicit; otherwise prefer symmetry="none". Use gaze_pressure other than none only when gaze, face, looking, or staring is explicit**
- **If supporting instructions are needed for human/animal context, do not make a vertical-line + small-ellipse silhouette, stick figure, head/body, wing, or tail. Abstract it as negative-space lines, edge-biased focus, pale arcs, or group spacing**
- **Nouns such as tears, gaze, roof, and cloud are not separate objects or signs to add. Convert tears into downward blur or opacity contrast, gaze into negative-space pressure, roof into low weight or diagonal pressure, and cloud into upper weight or density contrast on the primitives already specified**
- **Do not simply delete words that were not objectified. Preserve them as path, fade, density, rotation, preserve_space, or a faint color_cycle contrast. Tears/blurring should bias downward or vertical; cloud/pressing-down should become upper weight and downward pressure; gaze should become one-sided negative-space pressure**
- **Low cloud, pressing down, shadow only, going ahead, tears, blur, unraveling, and fading are motion intents, not objects. Always apply them to existing instructions as path, fade, rotation, rhythm_spacing, one-sided negative space, or a small focal contrast**
- **Vehicles such as bicycles, cars, and trains must not become wheels, frames, or bodies. Abstract them as shadows, diagonals, center of gravity, leading/lagging motion, or shifted negative space**
- **Reflection → sparse repeated line or arc with fade="directional" and path="wave" or "top_to_bottom"**
- **Soft light / sunlight → layered pale white or yellow-leaning ellipse, filled=true, preserving the original phrase in color_hint. Scent / fragrance → small green/white/gray ellipse or arc along path="wave". Buds / waiting to bloom → small red/white ellipses along a diagonal band. Five-sense presence / atmosphere → faint arc/ellipse with fade**
- **Use more for dots/stars/rain/snow/sand/particles, but do not default them to true circles. Prefer ellipse, square, or short line unless circle/round/moon/sun is explicit. Add rotation to ellipses and squares so they are not locked to horizontal/vertical symmetry**
- **Use only polygon for polygonal vocabulary, with sides=5-8. Use it only for crystals, minerals, hard shards, artificial hardness, or urban structure. Do not add separate pentagon/hexagon primitives**
- **Mountain / sharp peak → triangle is allowed. Do not objectify roof as a triangle; treat it as low weight, diagonal pressure, or upper density contrast. Leaf / petal / feather / paper fragment → use thin ellipse, rotated square, or small polygon so abstract natural/material forms survive until natural primitive plugins exist**
- **Playful or complex shapes should be local motifs made from 2-5 primitives, not a single primitive. Examples: leaf=thin ellipse + arc, paper shard=rotated square + thin line, seed pod=ellipse + small particles, mountain=triangle + a line cutting negative space, ripple=arc + small ellipse**

## Fill, background, and color

- **fill/paint/solid fill → filled=true. Outline only = omit filled (default false)**
- **background → Score background field. "Fill background with black" → {"background":"black","instructions":[...]}**
- **Do not create effectively invisible instructions whose drawing color matches the background. If they match, change the smaller visual area. Usually change line/small-shape/dot color to a context-fitting visible color such as black, white, blue, red, or green. Change the background only when the matching subject is large and dominant**
- **Do not use background="gray". Even if normalized DDL asks for a gray background, choose a contextual background from white/black/blue/red/green instead**
- **Treat gray subjects as foreground color="gray", not as the background. Do not build gray value-only drawings; combine gray with visible black, white, blue, red, or green foreground**
- **Specific color nuance (cherry-blossom pink, cinnabar red, cool blue-green, etc.) → keep color as nearest abstract color, and preserve the original short nuance in color_hint**
- **colorful/multi-color → arrangement color_cycle. e.g. ["red","blue","green","black","gray"]**
- **When explicit colors are sparse, choose palette by scene tone. Spring/flowers/warm light → red/green/white; water/night/cold air → blue/white/gray; forest/leaves/fragrance → green/white/gray. Preserve unavailable nuance in color_hint**
- **Strong solid backgrounds (black/red/blue/green) are allowed only when explicit or required by context such as night, flame, sign, or sea. If unsure, use white**

## Placement and focus

- **Normalized DDL must include placement words. If normalized DDL says "near the center", "top to bottom", "vertical", "right half", "radial", "concentric", "dotted across the whole canvas", or "undulating trace", prioritize that placement phrase**
- **"dotted across the whole canvas" / "finely across the whole canvas" may use layout=scatter, but treat it as all-over distribution, not disorder**
- **scatter is not uniform noise. Treat it as biased by density gradient, fading edges, diagonal band, right half, or top-to-bottom placement from the DDL**
- **"undulating trace" → arrangement.path="wave". "diagonal band" → path="diagonal". "right half" → path="right_half"**
- **"from top to bottom" / "vertical band" → layout="vertical", path="top_to_bottom". "left to right" / "horizontal" / "horizontal strata" → layout="horizontal", path="left_to_right". "radial" / "concentric" → layout="radial". "across the whole canvas" → layout="scatter"**
- **"central stillness" → at={"region":[0.42,0.42,0.58,0.58]}. Treat it as a narrow central region, not a fixed center coordinate**
- **"rhythm", "bounce", "dance", "canon-like offset", or "unraveling repetition" → use arrangement.rhythm_spacing without increasing count. playful/bouncing=syncopated, accelerating/flowing=accelerando, loose swaying=loose**
- **"upper-right golden-ratio position" → at={"region":[0.56,0.32,0.68,0.44]}. Lower-left uses at={"region":[0.32,0.56,0.44,0.68]}. Treat focus as a region, not a hard-coded coordinate**
- **"upper-left rule-of-thirds point" → at={"region":[0.273,0.273,0.393,0.393]}. "lower-right rule-of-thirds point" → at={"region":[0.607,0.607,0.727,0.727]}. Treat it as rule-of-thirds composition. Do not hard-code focus coordinates**
- **"lower-left silver-ratio position" → at={"region":[0.354,0.526,0.474,0.646]}. "upper-right silver-ratio position" → at={"region":[0.526,0.354,0.646,0.474]}. Treat it as silver-ratio spacing. Do not hard-code focus coordinates**
- **"upper-right focus" → at={"region":[0.60,0.18,0.82,0.40]}. "upper-left focus" → [0.18,0.18,0.40,0.40]. "lower-right focus" → [0.60,0.60,0.82,0.82]. "lower-left focus" → [0.18,0.60,0.40,0.82]. Do not hard-code focus coordinates**
- **"upper-edge focus" → at={"region":[0.39,0.07,0.61,0.29]}. "right-half focus" → at={"region":[0.61,0.39,0.83,0.61]}. Do not hard-code focus coordinates**

## Mathematical, musical, and perspective composition

- **"regular pentagon vertices" → arrangement count=5 layout=radial. Treat it as a pentagonal balance layer**
- **Fibonacci-like counts such as thirteen and twenty-one are intentional; keep them as explicit counts**
- **Mathematical balance is not central symmetry. Use golden offset, rule-of-thirds, silver ratio, prime spacing, fibonacci count, and counterweight; balance the main focus with smaller elements on the opposite side**
- **"contrapuntal contrary motion" → a line layer moving against the main direction. Falling to the right uses rotation=30; rising to the right uses rotation=-30**
- **"harmonic overtone series" → an integer-ratio radial arc/circle layer. Keep the explicit count**
- **"canon offset" → repeated same shape with slight horizontal delay. Use layout=horizontal and the explicit count**
- **"one-point perspective" → thin guide lines toward the DDL focus. If the focus is upper right, use guide lines converging there**
- **"perspective depth" → repeated horizontal lines upward, preserving count**

## Materials and technique words

- **"value" / "light and shade" → black/gray/white contrast layers; blurring may express soft value transitions**
- **"drawing underlines" → fine-brush or pencil thin lines; preserve count**
- **"pointillism" → small square or ellipse scatter; avoid repeated true circles and add rotation to break axis symmetry**
- **"oil impasto" → short brush_thick line repetition**
- **"watercolor" → primarily ellipse with blurring, layered softly**
- **"patchwork" → square repetition; use color_cycle for multiple colors and add slight rotation to the pieces**
- **"fresco ground" → chalk gray horizontal lines or ground plane with blurring**
- **"ink-wash value" → black/gray brush lines with blurring or weight contrast**
- **English idiom and cultural texture are compositional signals, not objects. "syncopated city rhythm" / "blue-note value" → short line or arc rhythm with rhythm_spacing="syncopated"; "quilt-like patchwork" → rotated square color_cycle; "subway-map pressure" → rotring line convergence; "billboard edge pressure" → cropped rectangle/diagonal edge tension; "prairie horizon" → low horizontal negative-space pressure; "coastal fog plane" → pale watercolor ellipse layers with blurring; "warehouse grid cuts" → sparse rotated square/line grid fragments**

# Relations

- **"along the previous line" -> relation={"type":"along","gap":"narrow"}**
- **"not touching the previous shape" -> relation={"type":"not_touching","gap":"narrow"}. Use gap="wide" for wide separation**
- **"cutting the previous line" -> relation={"type":"cutting","gap":"medium"}**
- **"between the previous two" -> relation={"type":"between","gap":"medium"}**
- Copy relation only when the normalized DDL literally contains one of these fixed phrases as an explicit previous-object relation. Do not infer relations. Natural-language-derived phrases such as "around", "same beat", "ahead/behind", "not touched", "near", or "far" are not relations. Do not attach relation to the first instruction.
- **Do not turn ordinary placement language into relation.** Phrases such as "along a diagonal band", "along an undulating trace", "along a path/edge/road/river", "riverbank", or "roadside" are arrangement/path/position, not relation.
- Before writing relation, verify that the immediately previous JSON instruction has an outline target: line has `from`+`to`, circle/arc/polygon has `center`+`radius`, ellipse has `center`+`size`, and square/triangle has `position`+`size`.
- Relations may refer only to already emitted drawable outline instructions. Do not use background, filled planes, presence, fade-only support layers, small color-repair marks, or arrangement-only density layers as relation targets.
- **Use between only when the previous two JSON instructions both have outlines. If only one previous drawable exists, or if either previous item is a support layer, omit the relation.**
- Do not combine "along", "not touching", and "cutting" on one instruction. If several fixed phrases appear, keep only the one that is valid in output order.
- Generate at most one relation per fixed relation phrase. Do not replicate the same relation phrase into multiple instructions.
- If there is any doubt about order, target validity, or exact fixed-phrase match, omit the relation field. For fable/natural-language-derived DDL, use no relation by default. Express the relationship with position, path, rotation, and spacing instead; do not add a support instruction to rescue it.

# Examples (key patterns)

Input: Fill a gray circle with pale ink wash and let the edge bleed slightly.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.16,"color":"gray","filled":true,"surface":{"texture":"wash","density":0.3,"opacity":0.45,"bleed":0.2}}]}

Input: Place one thin black line at center. Trembling faintly. Ground: off-white paper, fine paper grain.
Output: {"canvas":{"aspect":"square","ground":{"material":"paper","tone":"off_white","grain":"fine","density":0.2,"opacity":0.12}},"instructions":[{"primitive":"line","from":[0.5,0.3],"to":[0.5,0.7],"color":"black","weight":"pen","variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_x"]}}]}

Input: Line up three vertical black lines horizontally. Ground: ink wash.
Output: {"canvas":{"aspect":"square","ground":{"material":"ink_wash","tone":"gray","density":0.25,"opacity":0.14}},"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"black","arrangement":{"count":3,"layout":"horizontal"}}]}

Input: Line up three vertical solid lines horizontally.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"arrangement":{"count":3,"layout":"horizontal"}}]}

Input: Scatter five small blue ellipses rising to the right near the center. Make them wide.
Output: {"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.06,0.03],"color":"blue","rotation":-30,"arrangement":{"count":5,"layout":"scatter","margin":0.25}}]}

Input: Scatter six hundred ten small rotated white squares dotted across the whole canvas.
Output: {"instructions":[{"primitive":"square","position":[0.49,0.49],"size":[0.014,0.014],"color":"white","rotation":30,"arrangement":{"count":110,"layout":"scatter","density":"high","cluster_count":9,"fade":"outward","preserve_space":true,"margin":0.2}}]}

Input: Scatter one hundred thirty-seven short white lines from top to bottom. Swaying slowly.
Output: {"instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"white","arrangement":{"count":96,"layout":"vertical","path":"top_to_bottom","density":"medium","cluster_count":5,"fade":"directional","preserve_space":true},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

Input: Draw three hundred trembling green pen lines from top to bottom.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"green","arrangement":{"count":110,"layout":"vertical","path":"top_to_bottom","density":"high","cluster_count":7,"fade":"directional","preserve_space":true},"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_x","position_y"]}}]}

Input: Scatter twenty small red ellipses rising to the right vertically in the right half.
Output: {"instructions":[{"primitive":"ellipse","center":[0.75,0.5],"size":[0.055,0.028],"color":"red","rotation":-30,"arrangement":{"count":20,"layout":"vertical","path":"right_half","margin":0.1}}]}

Input: Place one small white circle at the upper-right golden-ratio position. Radius 0.025.
Output: {"instructions":[{"primitive":"circle","at":{"region":[0.56,0.32,0.68,0.44]},"radius":0.025,"color":"white"}]}

Input: Place one small white circle at the upper-left rule-of-thirds point. Radius 0.018.
Output: {"instructions":[{"primitive":"circle","at":{"region":[0.273,0.273,0.393,0.393]},"radius":0.018,"color":"white"}]}

Input: Place one small white circle at the lower-left silver-ratio position. Radius 0.016.
Output: {"instructions":[{"primitive":"circle","at":{"region":[0.354,0.526,0.474,0.646]},"radius":0.016,"color":"white"}]}

Input: Place a black circle at the upper-right focus.
Output: {"instructions":[{"primitive":"circle","at":{"region":[0.60,0.18,0.82,0.40]},"radius":0.1,"color":"black"}]}

Input: Line up five small red circles on regular pentagon vertices. Radius 0.022.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.022,"color":"red","arrangement":{"count":5,"layout":"radial"}}]}

Input: Scatter twenty-one small red ellipses along an undulating trace. Swaying slowly.
Output: {"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.045,0.022],"color":"red","rotation":30,"arrangement":{"count":21,"layout":"scatter","path":"wave","margin":0.12},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

Input: Line up three thin white lines falling to the right as contrapuntal contrary motion. Fine trembling.
Output: {"instructions":[{"primitive":"line","from":[0.25,0.5],"to":[0.75,0.5],"color":"white","rotation":30,"arrangement":{"count":3,"layout":"vertical"},"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}

Input: Line up four thin white arcs from a lower-right focus as a harmonic overtone series. Radius 0.07.
Output: {"instructions":[{"primitive":"arc","center":[0.72,0.68],"radius":0.07,"angle_start":0,"angle_end":180,"color":"white","arrangement":{"count":4,"layout":"radial","radius":0.18}}]}

Input: Line up seven short red lines left to right as a canon offset. Swaying slowly.
Output: {"instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"red","arrangement":{"count":7,"layout":"horizontal"},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

Input: Draw eight thin white lines toward an upper-right focus as one-point perspective.
Output: {"instructions":[{"primitive":"line","from":[0.12,0.85],"to":[0.78,0.28],"color":"white","arrangement":{"count":8,"layout":"vertical","margin":0.08}}]}

Input: Scatter thirty-four small rotated red squares dotted across the whole canvas as pointillism.
Output: {"instructions":[{"primitive":"square","position":[0.497,0.497],"size":[0.006,0.006],"color":"red","rotation":30,"arrangement":{"count":34,"layout":"scatter"}}]}

Input: Line up seven short red thick-brush lines horizontally as oil impasto.
Output: {"instructions":[{"primitive":"line","from":[0.35,0.5],"to":[0.65,0.5],"color":"red","weight":"brush_thick","arrangement":{"count":7,"layout":"vertical"}}]}

Input: Layer three pale watercolor ellipses rising to the right in the upper left. Edges blurring.
Output: {"instructions":[{"primitive":"ellipse","center":[0.32,0.28],"size":[0.24,0.14],"color":"white","rotation":-15,"arrangement":{"count":3,"layout":"scatter","margin":0.18},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}}]}

Input: Line up sixteen small rotated squares in red, blue, green, gray as patchwork grid.
Output: {"instructions":[{"primitive":"square","position":[0.45,0.45],"size":[0.08,0.08],"rotation":15,"arrangement":{"count":16,"layout":"scatter","margin":0.18,"color_cycle":["red","blue","green","gray"]}}]}

Input: Line up five black fine-brush vertical lines left to right as ink-wash value. Edges blurring.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.2],"to":[0.5,0.8],"color":"black","weight":"brush_thin","arrangement":{"count":5,"layout":"horizontal"},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x"]}}]}

Input: Line up seven short blue fine-brush lines left to right as syncopated city rhythm. Swaying slowly.
Output: {"instructions":[{"primitive":"line","from":[0.47,0.5],"to":[0.53,0.5],"color":"blue","weight":"brush_thin","arrangement":{"count":7,"layout":"horizontal","rhythm_spacing":"syncopated"},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}


Input: Draw one black horizontal line. Place three small red ellipses along the previous line.
Output: {"instructions":[{"primitive":"line","from":[0.12,0.5],"to":[0.88,0.5],"color":"black"},{"primitive":"ellipse","center":[0.5,0.5],"size":[0.04,0.02],"color":"red","arrangement":{"count":3,"layout":"horizontal"},"relation":{"type":"along","gap":"narrow"}}]}

Input: Place one small blue circle. Place one small white square between the previous two.
Output: {"instructions":[{"primitive":"circle","center":[0.42,0.5],"radius":0.04,"color":"blue"},{"primitive":"square","position":[0.55,0.47],"size":[0.06,0.06],"color":"white"}]}

Input: Draw two black lines. Place a small red circle between the previous two.
Output: {"instructions":[{"primitive":"line","from":[0.18,0.36],"to":[0.55,0.36],"color":"black"},{"primitive":"line","from":[0.45,0.64],"to":[0.82,0.64],"color":"black"},{"primitive":"circle","center":[0.5,0.5],"radius":0.035,"color":"red","relation":{"type":"between","gap":"medium"}}]}

Input: Draw one black horizontal line. Place one small red circle along the previous line. Place one small blue square along the previous line.
Output: {"instructions":[{"primitive":"line","from":[0.12,0.5],"to":[0.88,0.5],"color":"black"},{"primitive":"circle","center":[0.5,0.42],"radius":0.035,"color":"red","relation":{"type":"along","gap":"narrow"}},{"primitive":"square","position":[0.5,0.58],"size":[0.06,0.06],"color":"blue"}]}

Input: Draw five thin rotring lines toward an upper-right focus as subway-map pressure.
Output: {"instructions":[{"primitive":"line","from":[0.14,0.82],"to":[0.72,0.28],"color":"black","weight":"rotring","arrangement":{"count":5,"layout":"vertical","margin":0.08}}]}

Input: Draw one long pale horizontal line near the lower third as prairie horizon.
Output: {"instructions":[{"primitive":"line","from":[0.06,0.66],"to":[0.94,0.66],"color":"gray","weight":"pencil","color_hint":"prairie horizon"}]}

Input: Draw a horizontal line at center. Fine trembling.
Output: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}

Input: Place a green square of side 0.4 at center.
Output: {"instructions":[{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"color":"green"}]}

Input: Place a filled red circle at center. Radius 0.2.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"color":"red","filled":true}]}

Input: Place a small cherry-blossom pink circle at center. Radius 0.1.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,"color":"red","color_hint":"cherry-blossom pink"}]}

Input: Fill background with black. Draw a white horizontal line at center.
Output: {"background":"black","instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"color":"white"}]}

Input: Fill background with white. Draw a white horizontal line at center.
Output: {"background":"white","instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"color":"black","color_hint":"white line made visible"}]}

Input: Draw one gray line rising from the bottom-left to the upper-right.
Output: {"instructions":[{"primitive":"line","from":[0.15,0.78],"to":[0.78,0.28],"color":"gray","arrangement":{"count":1,"layout":"scatter","density":"low","fade":"outward","preserve_space":true}}]}

Input: Fill background with white. Scatter one hundred thirty-seven short white lines from top to bottom.
Output: {"background":"white","instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"blue","color_hint":"white lines made visible on the smaller area","arrangement":{"count":96,"layout":"vertical","path":"top_to_bottom","density":"medium","cluster_count":5,"fade":"directional","preserve_space":true}}]}

Input: Fill background with white. Place a large white circle near the top edge. Radius 0.15.
Output: {"background":"blue","instructions":[{"primitive":"circle","center":[0.5,0.18],"radius":0.15,"color":"white"}]}

Input: Arrange eight circles radially in red, blue, green, black.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.05,"arrangement":{"count":8,"layout":"radial","color_cycle":["red","blue","green","black","gray","red","blue","green"]}}]}

Input: A transparent membrane wraps faint reflections at a rainy bus stop.
Output: {"instructions":[{"primitive":"ellipse","center":[0.58,0.46],"size":[0.46,0.18],"color":"blue","filled":true,"color_hint":"transparent membrane","arrangement":{"count":5,"layout":"scatter","density":"low","cluster_count":3,"fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.35,0.22],"to":[0.72,0.78],"color":"white","color_hint":"rain reflection","arrangement":{"count":9,"layout":"vertical","path":"wave","density":"low","fade":"directional","preserve_space":true,"margin":0.18}}]}

Input: At a rainy bus stop, the presence of a waiting person becomes a transparent membrane.
Output: {"presence":{"kind":"figure_like","intensity":"low","center":[0.56,0.52],"symmetry":"none","gaze_pressure":"none","contour_density":"low"},"instructions":[{"primitive":"ellipse","center":[0.56,0.52],"size":[0.42,0.16],"color":"blue","filled":true,"color_hint":"transparent membrane","arrangement":{"count":4,"layout":"scatter","density":"low","fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}}]}

Input: Soft light and daphne fragrance surround cherry buds waiting to bloom.
Output: {"instructions":[{"primitive":"ellipse","center":[0.48,0.20],"size":[0.42,0.12],"color":"white","filled":true,"color_hint":"soft light","arrangement":{"count":3,"layout":"horizontal","density":"low","fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}},{"primitive":"ellipse","center":[0.56,0.55],"size":[0.045,0.022],"color":"green","rotation":-18,"color_hint":"daphne fragrance","arrangement":{"count":7,"layout":"scatter","path":"wave","density":"low","fade":"directional","preserve_space":true,"margin":0.24}},{"primitive":"ellipse","center":[0.70,0.62],"size":[0.055,0.026],"color":"red","rotation":-30,"color_hint":"waiting buds","arrangement":{"count":5,"layout":"scatter","path":"diagonal","margin":0.18}}]}

# Proportions

- **tall rectangle** → size[1] ≈ twice size[0]. e.g. size=[0.15,0.35]
- **wide rectangle** → size[0] ≈ twice size[1]. e.g. size=[0.35,0.15]
- **full-width line** → from=[0.0,y] to=[1.0,y]
- **half-width line** → from=[0.25,y] to=[0.75,y]
- **semicircle** → arc, angle_start=0, angle_end=180
- **waxing** → arc, angle_start=270, angle_end=90
- **waning** → arc, angle_start=90, angle_end=270
- **crescent** → arc, angle_start=210, angle_end=330
- **horizontal** → rotation=0. For line, use from=[0.0,y], to=[1.0,y]
- **vertical** → rotation=90. For line, use from=[x,0.0], to=[x,1.0]
- **diagonal** → rotation=45
- **rising** → rotation=-30
- **falling** → rotation=30
- **rotated** → rotation=30, unless an explicit angle is given

Input: Place a tall rectangle at center.
Output: {"instructions":[{"primitive":"square","position":[0.425,0.325],"size":[0.15,0.35]}]}

# Touches → weight (required)

When the normalized DDL contains a material word, always set the weight field. Omission is forbidden.

| material word | weight value |
|---|---|
| hair | hair |
| pencil | pencil |
| pen (default) | pen |
| rotring | rotring |
| crayon | crayon |
| chalk | chalk |
| fine-brush | brush_thin |
| thick-brush | brush_thick |
| rope | rope |

Input: Line up thirty vertical blue crayon lines horizontally.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"blue","weight":"crayon","arrangement":{"count":30,"layout":"horizontal"}}]}

Input: Line up ten thin vertical pencil lines horizontally.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"weight":"pencil","arrangement":{"count":10,"layout":"horizontal"}}]}

Input: Place a white chalk circle at center. Edges blurring.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,"color":"white","weight":"chalk","variation":{"amplitude":"medium","frequency":"medium","quality":"pink","dimensions":["position_x","position_y"]}}]}

No explanation. Call submit_score only."""


def _score_tool_schema() -> dict[str, Any]:
    schema = Score.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: Any, seen: set[str] | None = None) -> Any:
        if seen is None:
            seen = set()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.removeprefix("#/$defs/")
                if name in seen:
                    return {k: inline(v, seen) for k, v in node.items() if k != "$ref"}
                target = deepcopy(defs.get(name, {}))
                merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
                return inline(merged, seen | {name})
            return {k: inline(v, seen) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [inline(item, seen) for item in node]
        return node

    return inline(schema)


def _submit_tool() -> dict[str, Any]:
    return {
        "name": "submit_score",
        "description": "正規化DDLから導出した JSON Score を提出する。",
        "input_schema": _score_tool_schema(),
    }


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


def _build_user_message(ddl: str, original_text: str | None, lang: str = "ja") -> str:
    if original_text and original_text.strip() != ddl.strip():
        if lang == "en":
            return f"[original text]\n{original_text}\n\n[normalized DDL]\n{ddl}"
        return f"[原文]\n{original_text}\n\n[正規化DDL]\n{ddl}"
    return ddl


_MOTION_OR_TEXTURE_TERMS = (
    "震える",
    "震え",
    "揺れる",
    "揺らぐ",
    "揺れ",
    "小刻み",
    "滲む",
    "にじむ",
    "太い",
    "細い",
    "trembling",
    "tremble",
    "swaying",
    "sway",
    "wobble",
    "wobbly",
    "blurring",
    "blurred",
    "thick",
    "thin",
)

_PRIMITIVE_TERMS = {
    "line": ("直線", "線", "縦線", "横線", "line", "lines"),
    "circle": ("円", "丸", "circle", "circles"),
    "ellipse": ("楕円", "ellipse", "ellipses", "oval", "ovals"),
    "triangle": ("三角", "triangle", "triangles"),
    "square": ("四角", "square", "squares"),
    "polygon": ("多角形", "polygon", "polygons"),
    "arc": ("弧", "arc", "arcs"),
}

_COLOR_TERMS = {
    "white": ("白", "white"),
    "black": ("黒", "black"),
    "blue": ("青", "blue"),
    "red": ("赤", "red"),
    "green": ("緑", "green"),
    "gray": ("灰", "グレー", "gray", "grey"),
}


_RELATION_LITERAL_MARKERS = {
    "along": ("前の線に沿って", "along the previous line"),
    "not_touching": ("前の形に触れない", "not touching the previous shape"),
    "cutting": ("前の線を切る", "cutting the previous line"),
    "between": ("前の二つの間に", "between the previous two"),
}


def _literal_relation_types(ddl: str) -> set[str]:
    lower = ddl.lower()
    return {
        relation_type
        for relation_type, markers in _RELATION_LITERAL_MARKERS.items()
        if any(marker in ddl or marker in lower for marker in markers)
    }


def _mentioned_values(text: str, terms_by_value: dict[str, tuple[str, ...]]) -> set[str]:
    haystack = text.lower()
    return {
        value
        for value, terms in terms_by_value.items()
        if any(term.lower() in haystack for term in terms)
    }


def _enforce_relation_literal_gate(score: Score, ddl: str) -> Score:
    """Drop model-inferred relations unless the DDL contains the exact relation phrase."""

    allowed_types = _literal_relation_types(ddl)
    if not any(ins.relation is not None for ins in score.instructions):
        return score

    instructions = []
    changed = False
    for ins in score.instructions:
        if ins.relation is None or ins.relation.type in allowed_types:
            instructions.append(ins.model_dump(by_alias=True))
            continue
        data = ins.model_dump(by_alias=True)
        data.pop("relation", None)
        instructions.append(data)
        changed = True

    if not changed:
        return score
    data = score.model_dump(by_alias=True)
    data["instructions"] = instructions
    return Score.model_validate(data)


def _enforce_ground_literal_gate(score: Score, ddl: str) -> Score:
    """Drop model-inferred canvas ground unless the DDL contains its exact marker."""

    lower = ddl.lower()
    if "地:" in ddl or "ground:" in lower:
        return score
    if isinstance(score.canvas, str) or score.canvas.ground is None:
        return score

    data = score.model_dump(by_alias=True)
    data["canvas"] = score.canvas.aspect
    _logger.warning("canvas ground dropped by literal gate")
    return Score.model_validate(data)


def _finalize_score(score: Score, ddl: str) -> Score:
    score = _enforce_modifier_targeting(score, ddl)
    score = _enforce_relation_literal_gate(score, ddl)
    return _enforce_ground_literal_gate(score, ddl)


def _enforce_modifier_targeting(score: Score, ddl: str) -> Score:
    """Keep motion/texture modifiers on the explicitly requested single motif.

    This is a Stage 2 contract guard, not the broader visual auto-repair pass.
    It only applies when the DDL names exactly one primitive family and includes
    a motion/texture modifier, because those modifiers should decorate the named
    primitive instead of creating unrequested support marks.
    """

    if not any(term.lower() in ddl.lower() for term in _MOTION_OR_TEXTURE_TERMS):
        return score
    target_primitives = _mentioned_values(ddl, _PRIMITIVE_TERMS)
    if len(target_primitives) != 1:
        return score
    target_colors = _mentioned_values(ddl, _COLOR_TERMS)
    target_primitive = next(iter(target_primitives))

    def matches_target(ins) -> bool:
        if ins.primitive != target_primitive:
            return False
        return not target_colors or ins.color in target_colors

    targeted = [ins for ins in score.instructions if matches_target(ins)]
    if not targeted:
        return score
    if len(targeted) == len(score.instructions) and all(ins.variation is not None for ins in targeted):
        return score

    repaired = []
    for ins in targeted:
        if ins.variation is not None or target_primitive != "line":
            repaired.append(ins)
            continue
        repaired.append(
            ins.model_copy(
                update={
                    "variation": Variation(
                        amplitude="fine",
                        frequency="medium",
                        quality="perlin",
                        dimensions=["position_x", "position_y"],
                    )
                }
            )
        )

    data = score.model_dump()
    data["instructions"] = [ins.model_dump(by_alias=True) for ins in repaired]
    return Score.model_validate(data)


def compose(
    ddl: str,
    *,
    model: str | None = None,
    original_text: str | None = None,
    system_prompt: str | None = None,
    lang: str = "ja",
) -> tuple[Score, int | None, int | None]:
    """(score, tokens_in, tokens_out) を返す。system_prompt 指定時はスナップショット使用。"""
    user_msg = _build_user_message(ddl, original_text, lang=lang)
    if system_prompt is not None:
        effective_prompt = system_prompt
    elif lang == "en":
        effective_prompt = SYSTEM_PROMPT_EN
    else:
        effective_prompt = SYSTEM_PROMPT
    settings = _current_model_settings()
    if model:
        provider, model_id = provider_for_model(model, stage="stage2", settings=settings)
        if provider == "anthropic":
            score, tokens_in, tokens_out = _compose_anthropic(
                user_msg,
                model=model_id,
                system_prompt=effective_prompt,
                settings=settings,
            )
            return _finalize_score(score, ddl), tokens_in, tokens_out
        if provider == "gemini":
            score, tokens_in, tokens_out = _compose_gemini(
                user_msg,
                model=model_id,
                system_prompt=effective_prompt,
                settings=settings,
            )
            return _finalize_score(score, ddl), tokens_in, tokens_out
        score, tokens_in, tokens_out = _compose_openai(
            user_msg,
            model=model_id,
            provider=provider,
            system_prompt=effective_prompt,
        )
        return _finalize_score(score, ddl), tokens_in, tokens_out
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        score, tokens_in, tokens_out = _compose_openai(user_msg, model=None, system_prompt=effective_prompt)
        return _finalize_score(score, ddl), tokens_in, tokens_out
    score, tokens_in, tokens_out = _compose_anthropic(user_msg, system_prompt=effective_prompt)
    return _finalize_score(score, ddl), tokens_in, tokens_out


def _compose_anthropic(user_msg: str, *, model: str | None = None, system_prompt: str = SYSTEM_PROMPT, settings: dict | None = None) -> tuple[Score, int | None, int | None]:
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
        tools=[_submit_tool()],
        tool_choice={"type": "tool", "name": "submit_score"},
        messages=[{"role": "user", "content": user_msg}],
    )
    tin = getattr(resp.usage, "input_tokens", None)
    tout = getattr(resp.usage, "output_tokens", None)
    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_score":
            return Score.model_validate(block.input), tin, tout
    raise RuntimeError("Anthropic did not return submit_score tool call")


def _compose_gemini(user_msg: str, *, model: str, system_prompt: str = SYSTEM_PROMPT, settings: dict | None = None) -> tuple[Score, int | None, int | None]:
    connection = connection_for("gemini", settings or _current_model_settings())
    api_key = connection.get("api_key") or ""
    if not api_key:
        raise RuntimeError("Gemini API key is not configured")
    base_url = str(connection.get("base_url") or "https://generativelanguage.googleapis.com").rstrip("/")
    url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": MAX_TOKENS, "responseMimeType": "application/json"},
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
    return Score.model_validate(_extract_json(text_out)), usage.get("promptTokenCount"), usage.get("candidatesTokenCount")


def _compose_openai(user_msg: str, *, model: str | None = None, provider: str | None = None, system_prompt: str = SYSTEM_PROMPT) -> tuple[Score, int | None, int | None]:
    from openai import OpenAI

    settings = _current_model_settings()
    if model is None:
        provider, model = provider_for_model(None, stage="stage2", settings=settings)
    provider = provider or provider_for_model(model, stage="stage2", settings=settings)[0]
    connection = connection_for(provider, settings)
    base_url = connection["base_url"]
    api_key = connection.get("api_key") or "none"

    timeout = float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "120"))
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    tool = {
        "type": "function",
        "function": {
            "name": "submit_score",
            "description": "正規化DDLから導出した JSON Score を提出する。",
            "parameters": _score_tool_schema(),
        },
    }

    resp = call_with_llm_retry(
        lambda: client.chat.completions.create(
            model=model,
            max_tokens=MAX_TOKENS,
            temperature=0.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": "submit_score"}},
            stream=False,
        )
    )
    usage = resp.usage
    tin: int | None = getattr(usage, "prompt_tokens", None)
    tout: int | None = getattr(usage, "completion_tokens", None)

    msg = resp.choices[0].message
    if msg.tool_calls:
        args = msg.tool_calls[0].function.arguments
        return Score.model_validate(json.loads(args)), tin, tout

    text = (msg.content or "").strip()
    args = _extract_tool_call_args(text)
    if args is not None:
        return Score.model_validate(args), tin, tout

    data = _extract_json(text)
    return Score.model_validate(data), tin, tout


def _extract_tool_call_args(text: str) -> dict | None:
    """Tool call の arguments 部を各モデル方言から抽出する。

    対応する形式:
    - Qwen2.5: `<tool_call>{"name":"X","arguments":{...}}</tool_call>`
    - Gemma 3: ```json {"tool_calls":[{"name":"X","arguments":{...}}]} ```
    - その他: 裸の {"instructions":[...]} (Score 直接)
    """
    m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
    if m:
        try:
            payload = json.loads(m.group(1))
            return payload.get("arguments", payload)
        except json.JSONDecodeError:
            pass

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            payload = json.loads(m.group(1))
            if isinstance(payload, dict):
                tcs = payload.get("tool_calls")
                if isinstance(tcs, list) and tcs:
                    args = tcs[0].get("arguments") or tcs[0].get("parameters")
                    if isinstance(args, dict):
                        return args
                if "arguments" in payload and isinstance(payload["arguments"], dict):
                    return payload["arguments"]
                if "instructions" in payload:
                    return payload
        except json.JSONDecodeError:
            pass

    return None


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError(f"Could not extract JSON from response: {text[:500]}")

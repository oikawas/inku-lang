# ギャラリー

冒頭の 3 点は [README.ja.md](../../README.ja.md) にあります。ここはその続きです。

**それぞれの絵の下に、書かれた一文（詞書）と、そこから生まれた指示書（正規化DDL）を添えました。**

<table><tr><td><img src="../assets/gallery/blackout-candle-lattice.png" width="480" alt="黒い地の中央に、白いクレヨンで擦った四角が数十、隙間を残して重なり合い不揃いな塊をつくる。中心近くに小さな赤い印"></td></tr></table>

> 停電の夜、団地の窓にひとつずつ蝋燭が灯り、闇に不揃いな格子が浮かんだ。

<details>
<summary>指示書（正規化DDL）と元 SVG</summary>

```
背景を黒で塗りつぶす。
黄色いクレヨンの小さな四角を画面全体に点々と四十八個散らす。
四角は不揃いに並べる。
```

[blackout-candle-lattice.svg](../assets/gallery/blackout-candle-lattice.svg) — seed `6197114075822707` / 色カタログ inku Default

</details>

<table><tr><td><img src="../assets/gallery/aquarium-jellyfish-phases.png" width="480" alt="紺の地に、赤と青の半透明な塊が三つ重なって傘のような形をつくり、白と青の細い輪がその周りを巡り、下に細い赤い糸が垂れる"></td></tr></table>

> 灯りを消した水族館で、くらげは月の代わりに、ゆっくりと満ち欠けした。

<details>
<summary>指示書（正規化DDL）と元 SVG</summary>

```
背景を黒で塗りつぶす。白い細筆の雲形を中央に三つ、大きさの異なる順に並べる。波打つ軌跡に沿ってゆっくり揺れる。
```

[aquarium-jellyfish-phases.svg](../assets/gallery/aquarium-jellyfish-phases.svg) — seed `2184785730279672` / 色カタログ Weathered Heritage

</details>

<table><tr><td><img src="../assets/gallery/silent-piano-dust-chord.png" width="480" alt="生成りの地に、灰色の縦長の帯と細い枠の対が十ほど、左下から右上へ段をなして並び、淡い赤の波線が三本余白を横切る"></td></tr></table>

> 誰も弾かなくなったピアノの中で、埃が鍵盤の順番に、光の和音を組んでいた。

<details>
<summary>指示書（正規化DDL）と元 SVG</summary>

```
背景を黒で塗りつぶす。
白いロットリングの縦長の四角を横に二十本並べる。
白い鉛筆の小さな四角を、前の四角の上に一つずつ、画面全体に点々と散らす。
細かく震える。
```

[silent-piano-dust-chord.svg](../assets/gallery/silent-piano-dust-chord.svg) — seed `6064752967664899` / 色カタログ Dye & Earth

</details>

いずれも Build 667・render engine 10 で描かれたもので、Stage 1 / Stage 2 とも `nvidia:google/gemma-4-31b-it` による生成です。地の色が作品ごとに違うのは、**色カタログ**を切り替えているためで、同じ「白」「黒」の指定が選んだカタログの色域へ翻訳されます。

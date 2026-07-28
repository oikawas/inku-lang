# Gallery

The first three works are in [README.md](../../README.md). These are the rest.

**Under each picture is the sentence that was written (the headnote) and the instructions (normalized DDL) that grew out of it.** These works were written in Japanese; the original text is given with an English rendering.

<table><tr><td><img src="../assets/gallery/blackout-candle-lattice.png" width="480" alt="On a black ground, dozens of white crayon-scrubbed squares overlap into an uneven mass with gaps left open, a small red mark near the center"></td></tr></table>

> *On the night of the blackout, candles were lit one by one in the windows of the housing block, and an uneven lattice surfaced in the dark.*
>
> 停電の夜、団地の窓にひとつずつ蝋燭が灯り、闇に不揃いな格子が浮かんだ。

<details>
<summary>Instructions (normalized DDL) and source SVG</summary>

```
背景を黒で塗りつぶす。
黄色いクレヨンの小さな四角を画面全体に点々と四十八個散らす。
四角は不揃いに並べる。
```

> Fill the background with black.
> Scatter forty-eight small yellow crayon squares across the whole canvas.
> Arrange the squares unevenly.

[blackout-candle-lattice.svg](../assets/gallery/blackout-candle-lattice.svg) — seed `6197114075822707` / color catalog inku Default

</details>

<table><tr><td><img src="../assets/gallery/aquarium-jellyfish-phases.png" width="480" alt="On a navy ground, three translucent red and blue masses overlap into a bell-like form, ringed by thin white and blue loops, with a slender red thread trailing below"></td></tr></table>

> *In the aquarium with its lights out, the jellyfish waxed and waned slowly, in place of the moon.*
>
> 灯りを消した水族館で、くらげは月の代わりに、ゆっくりと満ち欠けした。

<details>
<summary>Instructions (normalized DDL) and source SVG</summary>

```
背景を黒で塗りつぶす。白い細筆の雲形を中央に三つ、大きさの異なる順に並べる。波打つ軌跡に沿ってゆっくり揺れる。
```

> Fill the background with black. Line up three white fine-brush cloudforms at the center, ordered by differing size. They sway slowly along an undulating path.

[aquarium-jellyfish-phases.svg](../assets/gallery/aquarium-jellyfish-phases.svg) — seed `2184785730279672` / color catalog Weathered Heritage

</details>

<table><tr><td><img src="../assets/gallery/silent-piano-dust-chord.png" width="480" alt="On an off-white ground, about ten pairs of gray vertical bars and thin frames step upward from lower left to upper right, with three pale red wavy lines crossing the empty space"></td></tr></table>

> *Inside the piano no one plays anymore, dust assembled a chord of light in the order of the keys.*
>
> 誰も弾かなくなったピアノの中で、埃が鍵盤の順番に、光の和音を組んでいた。

<details>
<summary>Instructions (normalized DDL) and source SVG</summary>

```
背景を黒で塗りつぶす。
白いロットリングの縦長の四角を横に二十本並べる。
白い鉛筆の小さな四角を、前の四角の上に一つずつ、画面全体に点々と散らす。
細かく震える。
```

> Fill the background with black.
> Line up twenty tall white rotring squares horizontally.
> Scatter small white pencil squares across the whole canvas, one on top of each previous square.
> They tremble finely.

[silent-piano-dust-chord.svg](../assets/gallery/silent-piano-dust-chord.svg) — seed `6064752967664899` / color catalog Dye & Earth

</details>

All three were generated on Build 667 with render engine 10, using `nvidia:google/gemma-4-31b-it` for both Stage 1 and Stage 2. The grounds differ from work to work because a different **color catalog** was selected: the same "white" or "black" in the instructions is translated into the gamut of the chosen catalog.

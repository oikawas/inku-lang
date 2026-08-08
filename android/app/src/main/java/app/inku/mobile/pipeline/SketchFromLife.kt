package app.inku.mobile.pipeline

import android.util.Log
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import java.security.MessageDigest

/**
 * 写生 (Stage 0.5) -- sketch from life.
 *
 * A dense description (a tanka, say) reaches Stage 1 as a single knot: the DDL
 * comes out short and the picture stays thin however much the description
 * holds. This layer stands before Stage 1 and rewrites the description as plain
 * prose in the language of things -- what is there, its shape, colour,
 * position, direction, number, speed, light. Stage 1 then reads prose it can
 * divide.
 *
 * Ported one-for-one from `server/src/inku_server/sketch.py` and the route that
 * drives it (`api_core/routers/render.py:1141-1229`). The prompt text is the
 * server's, byte for byte: rewriting it "for Android" would make the same
 * description come back as a different sketch, and the two clients would stop
 * being two performances of one score.
 *
 * The layer is one model call and it has two prompts. They differ in GRAIN, not
 * in how much they say: `fine` (the default) cuts the description into one fact
 * per short sentence; `coarse` bundles related facts with subordinate clauses
 * into fewer, longer sentences.
 *
 * The English prompt never names the layer. `sketch` is already a weight word
 * in the Stage 1 English prompt ("pale, delicate, faint, sketch, draft" ->
 * pencil), so putting it in this layer's output vocabulary would move a Stage 1
 * field.
 *
 * **The layer is not deterministic.** `sketch_from_life` passes no seed and
 * fixes no temperature, so the same description at the same grain does not come
 * back as the same prose. What is deterministic, and what the acceptance is
 * placed on, is [systemPrompt], [promptDigest], [Sketches.normalizeGrain] and
 * [stateOf]. Redrawing a saved work replays its stored `sketch_text` rather
 * than asking the layer again -- see [SketchInput].
 */
object SketchFromLife {

    /**
     * What Stage 0.5 produced, plus what it cost. `SketchDetail`
     * (`sketch.py:212-223`).
     */
    data class Detail(
        val text: String,
        val grain: SketchGrain = Sketches.DEFAULT_GRAIN,
        val tokensIn: Int? = null,
        val tokensOut: Int? = null,
        val fallbackUsed: Boolean = false,
        val fallbackReasons: List<String> = emptyList(),
        val promptDigest: String? = null,
    )

    /**
     * The one place that names what 0.5 did, so the writers cannot disagree.
     * One-for-one with `sketch_state_of` (`sketch.py:226-250`).
     *
     * No branch returns `null`: a caller that has no opinion still has a state.
     * A `null` in the column means the row is older than the column, and only
     * the migration may produce it.
     *
     * [requested] is what the caller asked for, not what happened. When the
     * layer was asked for and nothing came back, the path did not run it, and
     * the record says so rather than "off": a wiring regression must not be
     * written down as a choice the author made.
     */
    fun stateOf(detail: Detail?, requested: Boolean, hasDescription: Boolean): SketchState {
        if (detail != null) {
            if (detail.fallbackUsed) return SketchState.Fallback
            return when (Sketches.normalizeGrain(detail.grain.wire)) {
                SketchGrain.Fine -> SketchState.Fine
                SketchGrain.Coarse -> SketchState.Coarse
            }
        }
        // Nothing to sketch: a work authored straight in DDL, or any path that
        // begins after Stage 1.
        if (!hasDescription) return SketchState.NotApplicable
        if (requested) return SketchState.NotApplicable
        return SketchState.Off
    }

    /**
     * The state a save records on a path that did not run the layer itself.
     * `sketch_state=body.sketch_state or _derived_sketch_state(body)`
     * (`history.py:158-175`, `:255`).
     *
     * A caller that knows its own path may name the state, and that claim wins:
     * a run whose 0.5 fell back has no prose to show for it, and re-deriving
     * from the row would call that `off` -- a wiring regression written down as
     * a choice the author made. An unknown claim is not honoured (it drops to
     * `null` in [Sketches.normalizeState]) and the state is derived instead.
     */
    fun claimedOrDerivedState(
        claimed: String?,
        prose: String?,
        grain: String?,
        hasDescription: Boolean,
    ): SketchState {
        Sketches.normalizeState(claimed)?.let { return it }
        val stripped = (prose ?: "").trim().ifEmpty { null }
        return stateOf(
            stripped?.let { Detail(text = it, grain = Sketches.normalizeGrain(grain)) },
            requested = false,
            hasDescription = hasDescription,
        )
    }

    /** `prompt_digest` (`sketch.py:208-209`): SHA-256, first 16 hex digits. */
    fun promptDigest(value: String): String {
        val bytes = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))
        return bytes.joinToString("") { "%02x".format(it) }.take(16)
    }

    /**
     * Build the Stage 0.5 system prompt for a language and a grain.
     * `build_system_prompt` (`sketch.py:191-205`).
     */
    fun systemPrompt(lang: String, grain: SketchGrain): String {
        val resolved = Sketches.normalizeGrain(grain.wire)
        val rules: String
        val grainSection: String
        val header: String
        val inLabel: String
        val outLabel: String
        val examples: List<Pair<String, String>>
        if (lang == "en") {
            rules = RULES_EN
            grainSection = if (resolved == SketchGrain.Fine) GRAIN_EN_FINE else GRAIN_EN_COARSE
            header = "# Examples"
            inLabel = "Description"
            outLabel = "Prose"
            examples = if (resolved == SketchGrain.Fine) EXAMPLES_EN_FINE else EXAMPLES_EN_COARSE
        } else {
            rules = RULES_JA
            grainSection = if (resolved == SketchGrain.Fine) GRAIN_JA_FINE else GRAIN_JA_COARSE
            header = "# 例"
            inLabel = "記述"
            outLabel = "写生文"
            examples = if (resolved == SketchGrain.Fine) EXAMPLES_JA_FINE else EXAMPLES_JA_COARSE
        }
        val blocks = examples.joinToString("\n\n") { (source, rendered) ->
            "$inLabel: $source\n$outLabel: $rendered"
        }
        return "$rules\n\n$grainSection\n\n$header\n\n$blocks"
    }

    /**
     * Some providers fence prose the same way they fence code; Stage 1 does the
     * same trimming for the DDL. `_clean_sketch_text` (`render.py:1132-1138`).
     */
    fun cleanText(raw: String?): String =
        FENCE.replace((raw ?: "").trim(), "").trim()

    /**
     * Run Stage 0.5. A failure here never stops a painting.
     *
     * Provider error or empty output both mean the same thing: the description
     * itself travels on to Stage 1, so the picture still gets made. This is the
     * rule Stage 1 already follows for its own failures.
     * `_call_sketch_detail` (`render.py:1141-1198`).
     *
     * The model is called exactly the way this client's Stage 1 is called --
     * same provider, same temperature, same token ceiling -- with a different
     * system prompt. That is the relation on the server too: `sketch_from_life`
     * reaches Stage 1's own `_interpret_*` functions (`sketch.py:262-304`).
     */
    suspend fun call(
        text: String,
        provider: ModelProvider,
        modelId: String,
        lang: String,
        grain: SketchGrain,
    ): Detail {
        val resolved = Sketches.normalizeGrain(grain.wire)
        val prompt = systemPrompt(lang, resolved)
        val digest = promptDigest(prompt)
        val response = runCatching {
            provider.generate(
                ModelRequest(
                    modelId = modelId,
                    prompt = text,
                    temperature = STAGE1_TEMPERATURE,
                    maxTokens = MAX_TOKENS,
                    systemInstruction = prompt,
                ),
            )
        }.getOrElse { error ->
            Log.w(TAG, "stage 0.5 failed, painting from the description", error)
            return Detail(
                text = text,
                grain = resolved,
                fallbackUsed = true,
                fallbackReasons = listOf("sketch_failed"),
                promptDigest = digest,
            )
        }
        val rendered = cleanText(response.text)
        if (rendered.isEmpty()) {
            return Detail(
                text = text,
                grain = resolved,
                fallbackUsed = true,
                fallbackReasons = listOf("sketch_empty_output"),
                promptDigest = digest,
            )
        }
        return Detail(text = rendered, grain = resolved, promptDigest = digest)
    }

    /**
     * Decide what Stage 0.5 contributes to this request. `_resolved_sketch`
     * (`render.py:1202-1229`).
     *
     * Three cases, in order:
     *  - a sketch text came with the request (the author edited it, or a saved
     *    work is being redrawn): use it verbatim and DO NOT call the model;
     *  - 0.5 is on: call the model at the requested grain;
     *  - otherwise: `null`, and the description travels as it always did.
     */
    suspend fun resolve(
        input: SketchInput,
        description: String,
        provider: ModelProvider?,
        modelId: String,
        lang: String,
    ): Detail? {
        val stored = (input.text ?: "").trim()
        if (stored.isNotEmpty()) {
            return Detail(text = stored, grain = Sketches.normalizeGrain(input.grain))
        }
        if (!input.requested) return null
        if (provider == null) {
            // No model to ask. The server cannot reach this branch -- a provider
            // is always configured there -- and the description travelling on
            // untouched is the same answer `_call_sketch_detail` gives when the
            // call raises.
            return Detail(
                text = description,
                grain = Sketches.normalizeGrain(input.grain),
                fallbackUsed = true,
                fallbackReasons = listOf("sketch_failed"),
                promptDigest = promptDigest(
                    systemPrompt(lang, Sketches.normalizeGrain(input.grain)),
                ),
            )
        }
        return call(
            text = description,
            provider = provider,
            modelId = modelId,
            lang = lang,
            grain = Sketches.normalizeGrain(input.grain),
        )
    }

    private const val TAG = "InkuSketch"

    /** `MAX_TOKENS` (`interpreter.py:28`), the ceiling Stage 1 draws under. */
    private const val MAX_TOKENS = 1024

    /** The temperature this client's Stage 1 uses (`LocalFallbackPipeline`). */
    private const val STAGE1_TEMPERATURE = 0.2

    private val FENCE = Regex("^```(?:[\\p{L}\\p{N}_]+)?\\s*\\n?|\\n?```$", RegexOption.MULTILINE)

    // --- the prompt, byte for byte from `sketch.py:49-188` ---

    private val RULES_JA = """
        あなたは inku の写生層である。作者の記述を、物の言葉だけで書いた散文へ写す。

        # 規則
        - 目に見えるものだけを書く。物・形・色・位置・向き・数・速さ・明暗。
        - 感情語と評価語を書かない。「美しい」「趣がある」「寂しい」「見事だ」の類は使わない。
        - 比喩・連想・解釈を足さない。記述に無い物を持ち込まない。
        - 記述にある物は落とさない。物は一つずつ言い切る。物ごとに、色・位置・向き・数・
          速さ・明暗のうち記述から分かるものを添える。
        - 時刻・季節・天候・素材の名詞（夜・朝・雪・葉・布・岩）は物であって感情語ではない。
          「暗い」「黒い」へ言い換えず、そのまま使う。
        - 出力は日本語の平叙文だけ。見出し・箇条書き・記号・前置き・後書きを書かない。
    """.trimIndent()

    private val RULES_EN = """
        You rewrite the author's description as plain prose that names only things.

        # Rules
        - Write only what can be seen: objects, shapes, colours, positions, directions,
          numbers, speeds, light and dark.
        - Use no words of feeling or judgement. Nothing is "beautiful", "lonely",
          "serene", "striking".
        - Add no metaphor, no association, no interpretation. Bring in no object the
          description does not have.
        - Drop no object the description does have. Name each one in turn, and give it
          whatever the description settles: colour, position, direction, number, speed,
          light or dark.
        - Nouns of time, season, weather and material (night, morning, snow, leaf,
          cloth, rock) are things, not feelings. Keep the word; do not trade "night"
          for "dark".
        - Output plain declarative sentences and nothing else: no heading, no list, no
          markup, no preamble, no closing remark.
    """.trimIndent()

    private val GRAIN_JA_FINE = """
        # 区切り
        細かく区切る。1 文には 1 つのことだけを書く。
        1 文はおよそ 10〜15 字。読点は使わない。文の数はおよそ 9〜12 文。
    """.trimIndent()

    private val GRAIN_JA_COARSE = """
        # 区切り
        大きく区切る。関係のあることを従属節で束ねて 1 文にする。
        1 文はおよそ 25〜30 字。読点を使う。文の数はおよそ 4〜6 文。
        総量は変えない。変えるのは区切りの大きさだけである。
    """.trimIndent()

    private val GRAIN_EN_FINE = """
        # Grain
        Cut fine. One sentence carries one fact.
        Keep sentences short, around eight to twelve words. Use no commas.
        Write around nine to twelve sentences.
    """.trimIndent()

    private val GRAIN_EN_COARSE = """
        # Grain
        Cut coarse. Bundle related facts into one sentence with subordinate clauses.
        Keep sentences long, around twenty to twenty-five words. Use commas.
        Write around four to six sentences.
        Say the same amount. Only the size of the pieces changes.
    """.trimIndent()

    // Few-shot material. The Japanese pairs are the author's own, written for
    // the 20-poem corpus the server contract measured. `fine` shows the
    // segmented arm, `coarse` the continuous one.
    private val EXAMPLES_JA_FINE = listOf(
        "ひさかたの光のどけき春の日にしづ心なく花の散るらむ" to
            "白い花びらが幾つも落ちる。花びらは途中で向きを変える。落ちる速さは一定でなく、" +
            "速いものと遅いものが混じる。枝が上方に横たわる。花びらが枝から次々と離れる。" +
            "日の光が面いっぱいに一様に広がる。影は薄い。",
        "石走る垂水の上のさわらびの萌え出づる春になりにけるかも" to
            "岩の面を水が速く流れ落ちる。水は白くくだけて跳ねる。細かいしぶきがあたりにかかる。" +
            "濡れた岩は黒い。流れのすぐ上に土がある。土から蕨の芽が幾つも出る。芽は出たばかりで小さい。" +
            "芽の先は丸く巻いている。芽は立ち上がる。",
        "春の苑紅にほふ桃の花下照る道に出で立つをとめ" to
            "桃の花が咲いている。花は濃い紅である。花は枝いっぱいに幾つも重なる。花の下に道がある。" +
            "道は花の紅を受けてほのかに明るい。道の上に少女がひとり立つ。花は少女の頭より高い。" +
            "花は面をなして広がる。",
    )

    private val EXAMPLES_JA_COARSE = listOf(
        "ひさかたの光のどけき春の日にしづ心なく花の散るらむ" to
            "白い花びらが幾つも、まっすぐには落ちずに途中で向きを変えながら、上方に横たわる枝から" +
            "次々と離れていく。落ちる速さは一定でなく、速いものと遅いものが混じり、面いっぱいに" +
            "一様に広がる日の光のなかで影は薄い。",
        "石走る垂水の上のさわらびの萌え出づる春になりにけるかも" to
            "岩の面を水が速く流れ落ち、白くくだけて跳ね、細かいしぶきをあたりにかけている。" +
            "濡れた岩は黒い。その流れのすぐ上の土から、蕨の芽が幾つも出たばかりで、" +
            "先を丸く巻いたまま小さく立ち上がっている。",
        "春の苑紅にほふ桃の花下照る道に出で立つをとめ" to
            "濃い紅の桃の花が、枝いっぱいに幾つも重なって咲いている。花の下の道は、花の紅を受けて" +
            "ほのかに明るい。その明るい道の上に、少女がひとり立つ。花は少女の頭より高いところで、" +
            "面をなして広がっている。",
    )

    private val EXAMPLES_EN_FINE = listOf(
        "The last light on still water." to
            "Water lies flat. The surface is dark. A band of pale light crosses it. " +
            "The band is narrow. The light comes from low down. The far edge is lost. " +
            "Nothing moves the surface.",
        "Rain on the roof of a shed." to
            "Rain falls in thin lines. The lines slant. A low roof stands under the rain. " +
            "The roof is grey metal. Water runs along one edge. Drops fall from the edge in a row. " +
            "The ground below is dark and wet.",
        "A market street in full sun." to
            "A street runs straight. Stalls stand along both sides. Cloth covers hang above them. " +
            "The covers are red and white. Fruit is piled in round heaps. People move between the stalls. " +
            "The shadows are short and hard. The upper walls are bright.",
    )

    private val EXAMPLES_EN_COARSE = listOf(
        "The last light on still water." to
            "Water lies flat and dark, crossed by a narrow band of pale light that comes from low down. " +
            "The far edge is lost, and nothing moves the surface.",
        "Rain on the roof of a shed." to
            "Thin slanting lines of rain fall onto a low roof of grey metal. " +
            "Water runs along one edge and falls from it in a row of drops, " +
            "and the ground below is dark and wet.",
        "A market street in full sun." to
            "A straight street has stalls along both sides, with red and white cloth covers hung above them " +
            "and fruit piled in round heaps. People move between the stalls under short hard shadows, " +
            "and the light is strong on the upper walls.",
    )
}

/**
 * What the caller asks Stage 0.5 for, with the server's three request fields
 * (`PaintRequest.sketch` / `sketch_text` / `sketch_grain`, `render.py:333-336`).
 *
 * [text] is a prose that already exists -- a saved work being redrawn. It wins
 * over [requested], because a redraw at the same grain replays the prose the
 * work was painted from: the layer is not deterministic, so calling it again
 * would not be a replay.
 */
data class SketchInput(
    val requested: Boolean = false,
    val text: String? = null,
    val grain: String? = null,
    /**
     * The state a caller already knows for its own path, with the server's
     * `HistoryPostBody.sketch_state` meaning (`models.py:54`). Left null by a
     * caller that has no opinion, and then the state is derived from what the
     * work carries. The layer itself never reads this.
     */
    val claimedState: String? = null,
)

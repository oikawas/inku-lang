package app.inku.mobile.pipeline

/** The former 写生 layer recorded how it divided prose. Old works retain this record. */
enum class SketchGrain(val wire: String) {
    Fine("fine"),
    Coarse("coarse"),
}

/** The author's choice for a new drawing. The layer runs only when asked. */
enum class SketchMode(val wire: String) {
    Off("off"),
    On("on"),
}

/** A missing state is distinct from a work explicitly drawn with 写生 off. */
enum class SketchState(val wire: String) {
    Fine("fine"),
    Coarse("coarse"),
    Fallback("fallback"),
    Off("off"),
    NotApplicable("not_applicable"),
    NotNeeded("not_needed"),
    Supplemented("supplemented"),
}

object Sketches {
    val GRAINS: List<SketchGrain> = listOf(SketchGrain.Fine, SketchGrain.Coarse)
    val MODES: List<SketchMode> = listOf(SketchMode.Off, SketchMode.On)
    val DEFAULT_MODE: SketchMode = SketchMode.Off
    val STATES: List<SketchState> = SketchState.entries

    fun normalizeState(value: String?): SketchState? =
        STATES.firstOrNull { it.wire == value }

    /** Old saved grain remains visible, without being a choice for new drawings. */
    fun recordedGrainOf(value: String?): SketchGrain? =
        GRAINS.firstOrNull { it.wire == value }

    /** A saved work's result, including an old grain, determines its offered opposite. */
    fun modeOfWork(state: String?, grain: String?): SketchMode = when {
        normalizeState(state) in listOf(SketchState.Off, SketchState.NotApplicable) -> SketchMode.Off
        normalizeState(state) in listOf(SketchState.Supplemented, SketchState.NotNeeded, SketchState.Fallback, SketchState.Fine, SketchState.Coarse) -> SketchMode.On
        recordedGrainOf(grain) != null -> SketchMode.On
        else -> SketchMode.Off
    }

    fun modeLabel(mode: SketchMode, isJapanese: Boolean): String = when (mode) {
        SketchMode.Off -> if (isJapanese) "なし" else "Off"
        SketchMode.On -> if (isJapanese) "あり" else "On"
    }

    fun modeHint(mode: SketchMode, isJapanese: Boolean): String = when (mode) {
        SketchMode.Off -> if (isJapanese) "写生を通さず、記述だけで描く" else "Skip the layer and draw from the description alone"
        SketchMode.On -> if (isJapanese) "記述の横に、場所の広がりや季節・時刻の光を補って描く" else "Supplement the extent of place and the seasonal or time-of-day light beside the description"
    }

    fun stateNote(state: String?, isJapanese: Boolean): String = when (normalizeState(state)) {
        SketchState.Supplemented -> if (isJapanese) "記述に足りない場所の広がりや季節・時刻の光を補って描いた" else "The layer supplemented place or light beside the description"
        SketchState.NotNeeded -> if (isJapanese) "写生を通したが、補うものがなかった" else "The layer ran and found nothing to add"
        SketchState.Fallback -> if (isJapanese) "写生を試みたが届かず、記述のまま解釈した" else "The layer did not answer; the description was used"
        SketchState.Off -> if (isJapanese) "写生を通さずに描いた" else "Drawn without the layer"
        SketchState.NotApplicable -> if (isJapanese) "この経路は写生を通らない" else "This path does not use the layer"
        SketchState.Fine, SketchState.Coarse -> ""
        null -> if (isJapanese) "写生が記録される前に描かれた" else "Drawn before sketch was recorded"
    }
}

/** Transport for a new request or for replaying saved text without a provider call. */
data class SketchInput(
    val requested: Boolean = false,
    val text: String? = null,
    val grain: String? = null,
    val claimedState: String? = null,
)

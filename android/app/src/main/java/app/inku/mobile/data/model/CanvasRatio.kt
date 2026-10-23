package app.inku.mobile.data.model

/** Display-only reading of DDL 26, matching Web's canvas-ratio.ts. Rust compiles it. */
data class CanvasRatio(val width: Int, val height: Int) {
    val label: String get() = "$width:$height"

    companion object {
        private const val space = "[\\x09-\\x0d\\x20\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff]"
        private val declaration = Regex(
            """^$space*(?:画面比|aspect$space+ratio)$space*([0-9０-９]{1,5})$space*[:：]$space*([0-9０-９]{1,5})$space*$""",
            RegexOption.IGNORE_CASE,
        )

        fun reduced(width: Int, height: Int): CanvasRatio? {
            if (width !in 1..10_000 || height !in 1..10_000) return null
            var a = width
            var b = height
            while (b != 0) { val remainder = a % b; a = b; b = remainder }
            return CanvasRatio(width / a, height / a)
        }

        fun declared(ddl: String): CanvasRatio? = ddl.split(Regex("[。.！!？?\n]"))
            .firstNotNullOfOrNull { sentence ->
                val match = declaration.matchEntire(sentence) ?: return@firstNotNullOfOrNull null
                fun units(value: String) = value.map { if (it in '０'..'９') '0' + (it - '０') else it }
                    .joinToString("").toInt()
                reduced(units(match.groupValues[1]), units(match.groupValues[2]))
            }

        fun ofAspect(id: String?): CanvasRatio? = CanvasAspects.find(id)?.let { reduced(it.widthUnits, it.heightUnits) }
    }
}

data class CanvasFitQuestion(val basis: CanvasRatio, val paperId: String)

/** An edited DDL uses its declaration alone; an untouched work may use its recorded paper. */
fun canvasFitQuestion(ddl: String, savedDdl: String?, drawnOn: String?, paperId: String): CanvasFitQuestion? {
    val basis = CanvasRatio.declared(ddl) ?: CanvasRatio.ofAspect(drawnOn).takeIf { savedDdl != null && ddl == savedDdl }
    val paper = CanvasRatio.ofAspect(paperId)
    return if (basis == null || paper == null || basis == paper) null else CanvasFitQuestion(basis, paperId)
}

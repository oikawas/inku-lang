package app.inku.mobile.ui.camera

import app.inku.mobile.data.model.CameraInputOrigin
import app.inku.mobile.data.model.CameraInputProvenance
import app.inku.mobile.data.model.CameraInputRoute
import app.inku.mobile.data.model.CameraVisionOutputMode
import app.inku.mobile.llm.isLocalVisionModel
import app.inku.mobile.pipeline.InstructionLanguages
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.pipeline.PreparedImageDdlInput
import app.inku.mobile.pipeline.SketchInput

/**
 * A camera work written from its photo by the shared core (SPEC §12.6.6,
 * 2026-10-24): one Vision model writes the DDL from the photo and reviews it
 * beside its drawing, on the paper nearest the photo's ratio, with no
 * description, 写生 or Wild. An on-device model keeps the description route,
 * as the author chose: it cannot be sent the photo with the DDL request.
 */
internal object CameraImageDdl {
    /** The record's name for the core's image prompts; their own ids are in `image_ddl`. */
    const val PROMPT_VERSION = "shared-core-image-ddl"

    fun usesImageDdl(visionModelId: String): Boolean = !isLocalVisionModel(visionModelId)

    fun provenance(
        origin: CameraInputOrigin,
        visionModelId: String,
        image: PreparedImageDdlInput,
    ): CameraInputProvenance = CameraInputProvenance(
        origin = origin,
        route = CameraInputRoute.ImageDdlToPipeline,
        visionProviderId = visionModelId.substringBefore(':'),
        visionModelId = visionModelId,
        visionPromptVersion = PROMPT_VERSION,
        visionOutputMode = CameraVisionOutputMode.Ddl,
        normalizedImageWidth = image.reference.width,
        normalizedImageHeight = image.reference.height,
    )

    /** The request the image is written with, and its execution later drawn with. */
    fun request(
        settings: CameraDrawSettings,
        image: PreparedImageDdlInput,
        uiLanguageCode: String,
        provenance: CameraInputProvenance,
    ): PaintRequest = PaintRequest(
        description = "",
        stage1Model = settings.stage1ModelId,
        stage2Model = settings.stage2ModelId,
        colorCatalogId = settings.catalogId,
        canvasAspect = image.nearestFormatId,
        autoRepair = true,
        instructionLang = InstructionLanguages.AUTO,
        uiLang = uiLanguageCode,
        sketch = SketchInput(),
        inputProvenance = provenance,
        renderWild = false,
        canvasFit = CANVAS_FIT,
    )

    const val CANVAS_FIT = "contain"
}

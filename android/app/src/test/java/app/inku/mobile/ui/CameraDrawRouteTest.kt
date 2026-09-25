package app.inku.mobile.ui

import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.model.CameraInputOrigin
import app.inku.mobile.data.model.CameraInputProvenance
import app.inku.mobile.data.model.CameraInputRoute
import app.inku.mobile.data.model.CameraVisionOutputMode
import app.inku.mobile.ui.camera.CameraCaptureState
import app.inku.mobile.ui.camera.CameraDrawRoute
import app.inku.mobile.ui.camera.CameraDrawRouting
import app.inku.mobile.ui.camera.CameraDrawSettings
import app.inku.mobile.ui.camera.ModelReadinessIssue
import app.inku.mobile.ui.camera.clearCameraOrigin
import app.inku.mobile.ui.camera.modelReadinessIssue
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraDrawRouteTest {
    @Test
    fun cameraDescriptionDrawsWithTheSettingsTakenAtCapture() {
        val route = CameraDrawRoute(provenance(), settings())

        assertEquals("gemini:gemma-4-31b-it", route.stage1ModelId)
        assertEquals("gemini:gemma-4-31b-it", route.stage2ModelId)
        assertEquals("auto", route.catalogId)
        assertTrue(route.sketch.requested)
        assertTrue(route.autoRepair)
    }

    @Test
    fun directDdlRecordsTheVisionModelAsItsStageOneProducer() {
        val direct = provenance().copy(
            route = CameraInputRoute.DdlToPipelineStage2,
            visionPromptVersion = "camera-ddl-v2",
            visionOutputMode = CameraVisionOutputMode.Ddl,
        )
        val route = CameraDrawRoute(direct, settings())

        assertEquals("local-litert-lm:gemma-4-e2b", route.stage1ModelId)
        assertEquals("gemini:gemma-4-31b-it", route.stage2ModelId)
    }

    @Test
    fun onlyReadyToEditCarriesACameraOrigin() {
        assertEquals(provenance(), CameraDrawRouting.provenanceFor(CameraCaptureState.ReadyToEdit(provenance())))
        assertNull(CameraDrawRouting.provenanceFor(CameraCaptureState.Idle))
        assertNull(CameraDrawRouting.provenanceFor(CameraCaptureState.Capturing))
    }

    @Test
    fun readinessChecksLocalDownloadsAndRemoteProviderConfiguration() {
        val gemini = "gemini:gemma-4-31b-it"
        val e2b = "local-litert-lm:gemma-4-e2b"

        assertEquals(ModelReadinessIssue.LocalModelNotReady, modelReadinessIssue(e2b, emptyList(), emptyList()))
        assertEquals(ModelReadinessIssue.LocalModelNotReady, modelReadinessIssue(e2b, emptyList(), listOf(asset("downloading"))))
        assertNull(modelReadinessIssue(e2b, emptyList(), listOf(asset("ready"))))

        assertEquals(ModelReadinessIssue.ProviderMissingOrDisabled, modelReadinessIssue(gemini, emptyList(), emptyList()))
        assertEquals(ModelReadinessIssue.ProviderMissingOrDisabled, modelReadinessIssue(gemini, listOf(provider(enabled = false)), emptyList()))
        assertEquals(ModelReadinessIssue.BaseUrlMissing, modelReadinessIssue(gemini, listOf(provider(baseUrl = null)), emptyList()))
        assertEquals(ModelReadinessIssue.ApiKeyMissing, modelReadinessIssue(gemini, listOf(provider(apiKey = null)), emptyList()))
        assertNull(modelReadinessIssue(gemini, listOf(provider()), emptyList()))
    }

    @Test
    fun explicitBoundaryActionsClearTerminalCameraOrigin() {
        assertSame(CameraCaptureState.Idle, CameraCaptureState.ReadyToEdit(provenance()).clearCameraOrigin())
        val failed = CameraCaptureState.Failed(app.inku.mobile.ui.camera.CameraFailure.AnalysisFailed)
        assertSame(CameraCaptureState.Idle, failed.clearCameraOrigin())
        assertSame(CameraCaptureState.Idle, CameraCaptureState.Cancelled.clearCameraOrigin())
        assertSame(CameraCaptureState.Idle, CameraCaptureState.Completed("history-id").clearCameraOrigin())
    }

    private fun settings() = CameraDrawSettings(
        stage1ModelId = "gemini:gemma-4-31b-it",
        stage2ModelId = "gemini:gemma-4-31b-it",
        catalogId = "auto",
        sketchRequested = true,
    )

    private fun provider(
        enabled: Boolean = true,
        baseUrl: String? = "https://generativelanguage.googleapis.com",
        apiKey: String? = "encrypted-key",
    ) = ProviderSettingEntity(
        providerId = "gemini",
        displayName = "Gemini",
        kind = "gemini",
        baseUrl = baseUrl,
        encryptedApiKey = apiKey,
        publishedModelsJson = "[\"gemma-4-31b-it\"]",
        isEnabled = enabled,
        isDefaultLocal = false,
        updatedAt = 0L,
    )

    private fun asset(state: String) = ModelAssetEntity(
        id = "gemma-4-e2b",
        providerId = "local-litert-lm",
        modelId = "local-litert-lm:gemma-4-e2b",
        displayName = "Gemma 4 E2B",
        qualityTier = "standard",
        downloadUrl = null,
        licenseUrl = null,
        licenseAcceptedAt = null,
        localPath = null,
        expectedSha256 = null,
        downloadState = state,
        bytesDownloaded = 0L,
        bytesTotal = 0L,
        updatedAt = 0L,
    )

    private fun provenance() = CameraInputProvenance(
        origin = CameraInputOrigin.Camera,
        route = CameraInputRoute.DescriptionToPipeline,
        visionProviderId = "local-litert-lm",
        visionModelId = "local-litert-lm:gemma-4-e2b",
        visionPromptVersion = "camera-description-v4",
        visionOutputMode = CameraVisionOutputMode.Description,
        normalizedImageWidth = 720,
        normalizedImageHeight = 1280,
    )
}

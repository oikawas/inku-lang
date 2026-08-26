package app.inku.mobile.ui

import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.model.CameraInputOrigin
import app.inku.mobile.data.model.CameraInputProvenance
import app.inku.mobile.data.model.CameraInputRoute
import app.inku.mobile.data.model.CameraVisionOutputMode
import app.inku.mobile.ui.camera.CameraCaptureState
import app.inku.mobile.ui.camera.CameraNimDrawRouting
import app.inku.mobile.ui.camera.CameraNimProviderIssue
import app.inku.mobile.ui.camera.cameraNimProviderIssue
import app.inku.mobile.ui.camera.clearCameraOrigin
import app.inku.mobile.ui.camera.providerIssue
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test

class CameraNimDrawRouteTest {
    @Test
    fun readyCameraDescriptionUsesTheFixedNimSnapshot() {
        val route = CameraNimDrawRouting.forState(readyState())
            ?: error("camera route missing")

        assertEquals("nvidia:google/gemma-4-31b-it", route.stage1ModelId)
        assertEquals("nvidia:google/gemma-4-31b-it", route.stage2ModelId)
        assertEquals("vivid_material", route.catalogId)
        assertFalse(route.sketchRequested)
        assertFalse(route.autoSelectCatalog)
        assertFalse(route.autoRepair)
        assertEquals(provenance(), route.inputProvenance)
    }

    @Test
    fun directDdlRecordsLocalStageOneProducerAndKeepsFixedNimStageTwo() {
        val direct = provenance().copy(
            route = CameraInputRoute.LocalDdlToNimStage2,
            visionPromptVersion = "camera-ddl-v1",
            visionOutputMode = CameraVisionOutputMode.Ddl,
        )
        val route = CameraNimDrawRouting.forState(CameraCaptureState.ReadyToEdit(direct))
            ?: error("camera route missing")

        assertEquals("local-litert-lm:gemma-4-e2b", route.stage1ModelId)
        assertEquals("nvidia:google/gemma-4-31b-it", route.stage2ModelId)
        assertEquals("vivid_material", route.catalogId)
        assertFalse(route.autoRepair)
    }

    @Test
    fun onlyReadyToEditOwnsTheCameraRoute() {
        assertNull(CameraNimDrawRouting.forState(CameraCaptureState.Idle))
        assertNull(CameraNimDrawRouting.forState(CameraCaptureState.Capturing))
        assertNull(CameraNimDrawRouting.forState(CameraCaptureState.Cancelled))
    }

    @Test
    fun fixedNimProviderMustBeEnabledAndConfiguredBeforeTheRun() {
        val route = CameraNimDrawRouting.forState(readyState())
            ?: error("camera route missing")

        assertEquals(CameraNimProviderIssue.MissingOrDisabled, route.providerIssue(emptyList()))
        assertEquals(CameraNimProviderIssue.MissingOrDisabled, route.providerIssue(listOf(provider(enabled = false))))
        assertEquals(CameraNimProviderIssue.BaseUrlMissing, route.providerIssue(listOf(provider(baseUrl = null))))
        assertEquals(CameraNimProviderIssue.ApiKeyMissing, route.providerIssue(listOf(provider(apiKey = null))))
        assertNull(route.providerIssue(listOf(provider())))
        assertEquals(CameraNimProviderIssue.MissingOrDisabled, cameraNimProviderIssue(emptyList()))
        assertNull(cameraNimProviderIssue(listOf(provider())))
    }

    @Test
    fun explicitBoundaryActionsClearTerminalCameraOrigin() {
        assertSame(CameraCaptureState.Idle, readyState().clearCameraOrigin())
        val failed = CameraCaptureState.Failed(app.inku.mobile.ui.camera.CameraFailure.AnalysisFailed)
        assertSame(CameraCaptureState.Idle, failed.clearCameraOrigin())
        assertSame(CameraCaptureState.Idle, CameraCaptureState.Cancelled.clearCameraOrigin())
        assertSame(CameraCaptureState.Idle, CameraCaptureState.Completed("history-id").clearCameraOrigin())
    }

    private fun provider(
        enabled: Boolean = true,
        baseUrl: String? = "https://integrate.api.nvidia.com/v1",
        apiKey: String? = "encrypted-key",
    ) = ProviderSettingEntity(
        providerId = "nvidia",
        displayName = "NVIDIA NIM",
        kind = "openai-compatible",
        baseUrl = baseUrl,
        encryptedApiKey = apiKey,
        publishedModelsJson = "[\"google/gemma-4-31b-it\"]",
        isEnabled = enabled,
        isDefaultLocal = false,
        updatedAt = 0L,
    )

    private fun readyState() = CameraCaptureState.ReadyToEdit(provenance())

    private fun provenance() = CameraInputProvenance(
        origin = CameraInputOrigin.Camera,
        route = CameraInputRoute.LocalDescriptionToNim,
        visionProviderId = "local-litert-lm",
        visionModelId = "local-litert-lm:gemma-4-e2b",
        visionPromptVersion = "camera-description-v1",
        visionOutputMode = CameraVisionOutputMode.Description,
        normalizedImageWidth = 720,
        normalizedImageHeight = 1280,
    )
}

package app.inku.mobile.ui

import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.ui.camera.CameraCaptureState
import app.inku.mobile.ui.camera.CameraNimDrawRouting
import app.inku.mobile.ui.camera.CameraNimProviderIssue
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
        val route = CameraNimDrawRouting.forState(CameraCaptureState.ReadyToEdit)
            ?: error("camera route missing")

        assertEquals("nvidia:google/gemma-4-31b-it", route.stage1ModelId)
        assertEquals("nvidia:google/gemma-4-31b-it", route.stage2ModelId)
        assertEquals("vivid_material", route.catalogId)
        assertFalse(route.sketchRequested)
        assertFalse(route.autoSelectCatalog)
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
        val route = CameraNimDrawRouting.forState(CameraCaptureState.ReadyToEdit)
            ?: error("camera route missing")

        assertEquals(CameraNimProviderIssue.MissingOrDisabled, route.providerIssue(emptyList()))
        assertEquals(CameraNimProviderIssue.MissingOrDisabled, route.providerIssue(listOf(provider(enabled = false))))
        assertEquals(CameraNimProviderIssue.BaseUrlMissing, route.providerIssue(listOf(provider(baseUrl = null))))
        assertEquals(CameraNimProviderIssue.ApiKeyMissing, route.providerIssue(listOf(provider(apiKey = null))))
        assertNull(route.providerIssue(listOf(provider())))
    }

    @Test
    fun explicitBoundaryActionsClearOnlyTheReadyCameraOrigin() {
        assertSame(CameraCaptureState.Idle, CameraCaptureState.ReadyToEdit.clearCameraOrigin())
        val failed = CameraCaptureState.Failed(app.inku.mobile.ui.camera.CameraFailure.AnalysisFailed)
        assertEquals(failed, failed.clearCameraOrigin())
        assertSame(CameraCaptureState.Cancelled, CameraCaptureState.Cancelled.clearCameraOrigin())
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
}

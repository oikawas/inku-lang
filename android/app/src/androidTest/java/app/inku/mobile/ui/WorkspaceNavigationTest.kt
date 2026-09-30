package app.inku.mobile.ui

import android.app.Application
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.performClick
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.LineageNodeEntity
import app.inku.mobile.ui.i18n.InkuStringsJa
import app.inku.mobile.ui.camera.CameraCaptureState
import app.inku.mobile.ui.camera.CameraFailure
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** A gallery edit and a trip to Settings must not overwrite a different draft. */
@RunWith(AndroidJUnit4::class)
class WorkspaceNavigationTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private val store = ViewModelStore()
    private lateinit var vm: InkuViewModel
    private lateinit var work: HistoryItemEntity

    @Before fun setUp() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java).build()
        repository = InkuRepository(context, database)
        work = HistoryItemEntity(
            id = "navigation-target", createdAt = 1, updatedAt = 1, originalInput = "赤い円の作品",
            normalizedDdl = "赤い円を描く", expandedDdl = null, scoreJson = "{}",
            displaySvg = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 100 100\"><circle cx=\"50\" cy=\"50\" r=\"30\" fill=\"red\"/></svg>",
            stage1Model = "fixture", stage2Model = "fixture", renderMetadataJson = "{}",
            renderHash = "workspace-navigation-fixture", renderHashShort = "NAV01", colorCatalogId = "default",
            canvasAspect = "square", starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null,
            lineageNodeId = "node-navigation-target",
        )
        database.historyDao().insert(work)
        database.lineageDao().insertNode(LineageNodeEntity(
            id = "node-navigation-target", historyId = work.id, state = "active",
            descriptionHash = "dh1:navigation-target", renderHash = work.renderHash, at = 1,
            rootNodeId = "node-navigation-target",
        ))
        withContext(Dispatchers.Main) {
            vm = ViewModelProvider(store, object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    InkuViewModel(context.applicationContext as Application, repository) as T
            })[InkuViewModel::class.java]
        }
        compose.setContent { InkuApp(vm) }
    }

    @After fun tearDown() = runBlocking {
        withContext(Dispatchers.Main) { store.clear() }
        repository.close()
        database.close()
    }

    private fun await(condition: (InkuUiState) -> Boolean) {
        compose.waitUntil(30_000) { condition(vm.state.value) }
        compose.waitForIdle()
    }

    private fun destination(label: String) = compose.onNode(hasText(label) and hasClickAction())

    @Test fun galleryEditingAndSettingsKeepTheirOwnDraftAndReturnDestination() {
        await { it.providerSettings.isNotEmpty() && vm.historyItems.value.isNotEmpty() }
        assertNull("startup must not open the latest work", vm.state.value.selectedHistory)
        assertNull(vm.state.value.workContextId)
        assertEquals(AppTab.Compose, vm.state.value.tab)
        compose.onNodeWithTag(DESCRIPTION_INPUT_TAG).assertIsDisplayed()
        compose.runOnIdle { vm.clearPrompt(); vm.setPrompt("制作中の青い線の草稿") }
        await { it.selectedHistory == null }
        destination(InkuStringsJa.worksTitle).performClick()
        await { it.tab == AppTab.History }
        destination(InkuStringsJa.settings).performClick()
        await { it.tab == AppTab.Settings }
        // With no downloaded model in this fixture, capture must reach its
        // readiness check directly, then cancel back to the same workspace.
        destination(InkuStringsJa.camera).performClick()
        await { it.cameraCaptureState is CameraCaptureState.Failed }
        assertEquals(CameraFailure.ModelNotReady, (vm.state.value.cameraCaptureState as CameraCaptureState.Failed).reason)
        compose.onNodeWithText(InkuStringsJa.cancel).performClick()
        await { it.cameraCaptureState == CameraCaptureState.Idle && it.tab == AppTab.Settings }
        assertEquals("制作中の青い線の草稿", vm.state.value.prompt)
        compose.onNodeWithText(InkuStringsJa.back).performClick()
        await { it.tab == AppTab.History }

        compose.runOnIdle {
            vm.openHistoryPresentation(vm.historyItems.value.first { it.id == work.id }, listOf(work.id))
        }
        await { it.presentationHistory?.id == work.id }
        compose.onNodeWithText("⋯").performClick()
        compose.onNodeWithText(InkuStringsJa.reviseWork).performClick()
        await { it.workActionsTarget?.id == work.id }
        assertEquals("opening a work menu must leave the authoring draft alone", "制作中の青い線の草稿", vm.state.value.prompt)
        compose.onNodeWithText(InkuStringsJa.descriptionEditAction).performClick()
        await { it.descriptionEditing && it.selectedHistory?.id == work.id }
        compose.onNodeWithTag(DESCRIPTION_INPUT_TAG).assertIsDisplayed()
        destination(InkuStringsJa.camera).assertIsDisplayed()
        compose.runOnIdle { vm.setPrompt("作品の赤い円を小さくする") }

        destination(InkuStringsJa.settings).performClick()
        await { it.tab == AppTab.Settings }
        compose.onNodeWithText(InkuStringsJa.back).performClick()
        await { it.tab == AppTab.Compose && it.descriptionEditing }
        assertEquals(work.id, vm.state.value.selectedHistory?.id)
        assertEquals("作品の赤い円を小さくする", vm.state.value.prompt)
        compose.onNodeWithTag(DESCRIPTION_INPUT_TAG).assertIsDisplayed()

        compose.onNodeWithText(InkuStringsJa.back).performClick()
        await { it.canvasPresentationMode && it.tab == AppTab.History }
        assertEquals(work.id, vm.state.value.presentationHistory?.id)
        assertEquals("制作中の青い線の草稿", vm.state.value.prompt)
        assertNull(vm.state.value.selectedHistory)
        compose.onNodeWithText("⋯").performClick()
        compose.onNodeWithTag(WORK_LINEAGE_ENTRY_TAG).performClick()
        await { it.tab == AppTab.Lineage && it.lineageGraph?.focusNodeId == work.lineageNodeId }
        compose.onNodeWithTag(LINEAGE_GRAPH_TAG).assertIsDisplayed()
        compose.onNodeWithText(InkuStringsJa.lineageDisplayed).assertIsDisplayed()
        destination(InkuStringsJa.studioTitle).performClick()
        await { it.tab == AppTab.Compose && it.workContextId == null }
        compose.onNodeWithTag(DESCRIPTION_INPUT_TAG).assertIsDisplayed()
        assertNull(vm.state.value.selectedHistory)
        assertEquals("制作中の青い線の草稿", vm.state.value.prompt)

        destination(InkuStringsJa.worksTitle).performClick()
        await { it.tab == AppTab.History }
        compose.onAllNodesWithTag(WORK_LINEAGE_ENTRY_TAG)[0].performClick()
        await { it.tab == AppTab.Lineage && it.lineageGraph?.focusNodeId == work.lineageNodeId }
        destination(InkuStringsJa.studioTitle).performClick()
        await { !it.canvasPresentationMode }
        await { it.tab == AppTab.Compose && !it.refinementOpen && !it.descriptionEditing }
        compose.onNodeWithTag(DESCRIPTION_INPUT_TAG).assertIsDisplayed()
        assertEquals("制作中の青い線の草稿", vm.state.value.prompt)

        destination(InkuStringsJa.worksTitle).performClick()
        await { it.tab == AppTab.History }
        compose.onAllNodesWithTag(WORK_LINEAGE_ENTRY_TAG)[0].performClick()
        await { it.tab == AppTab.Lineage && it.lineageGraph != null }
        compose.onAllNodesWithTag(LINEAGE_MENU_TAG)[0].performClick()
        compose.onNodeWithTag(REFINE_ENTRY_TAG).performClick()
        await { it.refinementOpen && it.refinementParent?.id == work.id }
        destination(InkuStringsJa.studioTitle).performClick()
        await { it.tab == AppTab.Compose && !it.refinementOpen && it.workContextId == null }
        compose.onNodeWithTag(DESCRIPTION_INPUT_TAG).assertIsDisplayed()
        assertEquals("leaving refinement returns to the authoring draft", "制作中の青い線の草稿", vm.state.value.prompt)
    }
}

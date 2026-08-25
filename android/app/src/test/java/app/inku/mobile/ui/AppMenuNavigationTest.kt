package app.inku.mobile.ui

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AppMenuNavigationTest {

    private fun appSource(): String {
        var file = File("src/main/java/app/inku/mobile/ui/InkuApp.kt")
        if (!file.isFile) file = File("app/src/main/java/app/inku/mobile/ui/InkuApp.kt")
        assertTrue("InkuApp.kt must exist", file.isFile)
        return file.readText()
    }

    @Test
    fun bottomNavigationIsWriteCameraHistoryAndLineage() {
        val source = appSource()
        val start = source.indexOf("private fun BottomNavigationBar(")
        val end = source.indexOf("private fun canvasLabel(", start)
        assertTrue("bottom navigation must exist", start >= 0 && end > start)
        val bottomNavigation = source.substring(start, end)

        assertTrue("bottom navigation must declare its four fixed destinations", bottomNavigation.contains("BottomNavigationDestination.Write"))
        assertTrue("bottom navigation must launch camera", bottomNavigation.contains("BottomNavigationDestination.Camera"))
        assertTrue("bottom navigation must retain History", bottomNavigation.contains("AppTab.History"))
        assertTrue("bottom navigation must retain Lineage", bottomNavigation.contains("AppTab.Lineage"))
        assertFalse("Settings must not remain in the bottom navigation", bottomNavigation.contains("AppTab.Settings"))
    }

    @Test
    fun cameraLaunchesOnlyTheStillImageCameraIntent() {
        val source = appSource()
        assertTrue("camera action must use the platform still-image camera intent", source.contains("MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA"))
        assertFalse("camera capture result handling is outside this skeleton", source.contains("ActivityResultContracts.TakePicture"))
        assertFalse("camera result imports are outside this skeleton", source.contains("rememberLauncherForActivityResult"))
    }

    @Test
    fun canvasControlsCenterFullscreenAndPutTheMenuAtTheEnd() {
        val source = appSource()
        val start = source.indexOf("private fun CanvasHeroCard(")
        val end = source.indexOf("private fun svgAspectRatio(", start)
        assertTrue("canvas hero must exist", start >= 0 && end > start)
        val canvasHero = source.substring(start, end)

        assertTrue("fullscreen must be centered", canvasHero.contains("modifier = Modifier.align(Alignment.Center)"))
        assertTrue("menu must be at the right edge", canvasHero.contains("modifier = Modifier.align(Alignment.CenterEnd)"))
        assertTrue("menu must expose Batch", canvasHero.contains("S.batch"))
        assertTrue("menu must expose Settings", canvasHero.contains("S.settings"))
        assertTrue("Batch must use the existing compose mode", canvasHero.contains("viewModel.setComposeMode(ComposeMode.Batch)"))
        assertTrue("Settings must use the existing settings route", canvasHero.contains("viewModel.setTab(AppTab.Settings)"))
    }

    @Test
    fun composeModeTabsAreRemovedFromProduction() {
        assertFalse("Batch is entered through the canvas menu, not mode tabs", appSource().contains("ComposeModeTabs"))
    }
}

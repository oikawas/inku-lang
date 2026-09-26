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
        // Up to the next composable: the studio header that now follows the
        // bar opens Settings itself, and it is not part of the bar.
        val end = source.indexOf("\n@Composable", start)
        assertTrue("bottom navigation must exist", start >= 0 && end > start)
        val bottomNavigation = source.substring(start, end)

        assertTrue("bottom navigation must declare its four fixed destinations", bottomNavigation.contains("BottomNavigationDestination.Write"))
        assertTrue("bottom navigation must launch camera", bottomNavigation.contains("BottomNavigationDestination.Camera"))
        assertTrue("bottom navigation must retain History", bottomNavigation.contains("AppTab.History"))
        assertTrue("bottom navigation must retain Lineage", bottomNavigation.contains("AppTab.Lineage"))
        assertFalse("Settings must not remain in the bottom navigation", bottomNavigation.contains("AppTab.Settings"))
    }

    @Test
    fun cameraUsesAFullImageResultContract() {
        val source = appSource()
        assertFalse("the fire-and-forget camera skeleton must be removed", source.contains("MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA"))
        assertTrue("camera action must receive a full-image result", source.contains("ActivityResultContracts.TakePicture"))
        assertTrue("the result contract must be registered by Compose", source.contains("rememberLauncherForActivityResult"))
    }

    @Test
    fun composeModeTabsAreRemovedFromProduction() {
        assertFalse("Batch is entered through the canvas menu, not mode tabs", appSource().contains("ComposeModeTabs"))
    }
}

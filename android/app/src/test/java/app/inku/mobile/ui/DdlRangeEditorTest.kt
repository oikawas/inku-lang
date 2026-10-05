package app.inku.mobile.ui

import androidx.compose.foundation.text.input.TextFieldState
import androidx.compose.foundation.text.input.toTextFieldBuffer
import androidx.compose.ui.text.TextRange
import org.junit.Assert.*
import org.junit.Test

class DdlRangeEditorTest {
    private val table = CompositionRangeTable.load {
        """{"schema":"inku.composition-ranges.v1","ranges":[
          {"key":"cell-22","words":{"ja":"右下","en":"bottom right"},"bounds":[[2,3],[2,3],[1,1],[1,1]]},
          {"key":"cell-00","words":{"ja":"左上","en":"top left"},"bounds":[[0,1],[0,1],[1,3],[1,3]]},
          {"key":"cell-12","words":{"ja":"下中央","en":"bottom center"},"bounds":[[1,3],[2,3],[2,3],[1,1]]}
        ]}"""
    }

    @Test
    fun externalDdlIsAdoptedWithoutSelectionRepublishingOrInterruptingComposition() {
        val initial = "右下（横2/3〜1、縦2/3〜1）に、円。"
        val state = TextFieldState(initial)
        val synchronization = DdlEditorSynchronization(initial)
        val external = "左上（横0〜1/3、縦0〜1/3）に、円。\r\n"
        assertNull(synchronization.publish(initial, editable = true))
        val replacement = synchronization.external(external, composing = false)!!
        state.edit { replace(0, length, replacement); selection = TextRange(4) }
        state.edit { selection = TextRange(6) }
        assertEquals(external, state.text.toString())
        assertNull(synchronization.publish(state.text.toString(), editable = true))
        state.edit { replace(0, 2, "右下") }
        assertNull(synchronization.publish(state.text.toString(), editable = false))
        assertEquals("右下（横0〜1/3、縦0〜1/3）に、円。\r\n", synchronization.publish(state.text.toString(), editable = true))
        assertNull(synchronization.external(external, composing = true))
        assertEquals("右下（横0〜1/3、縦0〜1/3）に、円。\r\n", state.text.toString())
        assertEquals(external, synchronization.external(external, composing = false))
    }

    @Test
    fun presentationDeletionsKeepRawTextAndSdkSelectionOffsets() {
        val raw = "🖼\n［構図］右下（横2/3〜1、縦2/3〜1）に、円。\r\n左上（横0〜1/3、縦0〜1/3）に、点。\n独自（横0.2〜0.5、縦0〜0.3）に、線。"
        val folded = "🖼\n右下に、円。\r\n左上に、点。\n独自（横0.2〜0.5、縦0〜0.3）に、線。"
        val selection = TextRange(raw.indexOf("独自"))
        val state = TextFieldState(raw, initialSelection = selection)
        val output = state.toTextFieldBuffer()
        val projection = ddlEditorProjection(DdlEditorSnapshot(raw, selection, focused = false), table)
        projection.applyTo(output)
        assertEquals(folded, output.toString())
        assertEquals(TextRange(folded.indexOf("独自")), output.selection)
        assertEquals(raw, state.text.toString())
        assertEquals(selection, state.selection)
        val selected = TextFieldState(raw, initialSelection = TextRange(raw.length, 0))
        val copyOutput = selected.toTextFieldBuffer()
        ddlEditorProjection(DdlEditorSnapshot(raw, selected.selection, focused = false), table).applyTo(copyOutput)
        assertEquals(raw, copyOutput.asCharSequence().substring(copyOutput.selection.min, copyOutput.selection.max))
        assertEquals(TextRange(raw.length, 0), selected.selection)
        val open = state.toTextFieldBuffer()
        ddlEditorProjection(DdlEditorSnapshot(raw, TextRange(raw.indexOf("横") + 1)), table).applyTo(open)
        assertEquals("🖼\n［構図］右下（横2/3〜1、縦2/3〜1）に、円。\r\n左上に、点。\n独自（横0.2〜0.5、縦0〜0.3）に、線。", open.toString())

        val english = "Place a circle at the [composition] bottom right (horizontal 2/3 to 1, vertical 2/3 to 1).\r\nKeep this line."
        val englishFolded = "Place a circle at the bottom right.\r\nKeep this line."
        val englishState = TextFieldState(english, initialSelection = TextRange(english.indexOf("Keep")))
        val englishOutput = englishState.toTextFieldBuffer()
        ddlEditorProjection(DdlEditorSnapshot(english, englishState.selection), table).applyTo(englishOutput)
        assertEquals(englishFolded, englishOutput.toString())
        assertEquals(TextRange(englishFolded.indexOf("Keep")), englishOutput.selection)
        assertEquals(english, englishState.text.toString())
    }

    @Test
    fun namesFollowOnlyOnLeavingAndSdkReplacementKeepsTheCaretAndOtherText() {
        val source = "🖼 Place a circle at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1).\r\nKeep this line."
        val session = DdlRangeEditorSession(table)
        session.update(DdlEditorSnapshot(source, TextRange(source.indexOf("horizontal") + 12)))
        val edited = source.replace("horizontal 2/3 to 1, vertical 2/3 to 1", "horizontal 1/3-2/3, vertical 2/3–1")
        val typing = session.update(DdlEditorSnapshot(edited, TextRange(edited.indexOf("horizontal") + 12)))
        assertTrue(typing.names.isEmpty())
        assertEquals(edited, typing.snapshot.source)
        assertEquals(table.ranges.single { it.key == "cell-12" }.bounds, typing.status.bounds)
        val state = TextFieldState(edited, initialSelection = TextRange(edited.indexOf("Keep")))
        val leaving = session.update(DdlEditorSnapshot(edited, state.selection))
        assertEquals(1, leaving.names.size)
        state.edit { leaving.applyTo(this) }
        val expected = edited.replace("bottom right", "bottom center")
        assertEquals(expected, state.text.toString())
        assertEquals(TextRange(expected.indexOf("Keep")), state.selection)
        assertEquals(state.selection, leaving.snapshot.selection)
        assertEquals("🖼 Place a circle at the bottom center.\r\nKeep this line.", displayDdlRanges(expected, table).text)

        val unmodified = DdlRangeEditorSession(table)
        val entering = unmodified.update(DdlEditorSnapshot(edited, TextRange(edited.indexOf("horizontal") + 12)))
        assertTrue(entering.names.isEmpty())
        val exiting = unmodified.update(DdlEditorSnapshot(edited, TextRange(edited.length)))
        assertEquals(expected, exiting.snapshot.source)
        assertEquals(1, exiting.names.size)
    }

    @Test
    fun incompleteAxesKeepTheLastFrameAndCustomBoundsRemainUnfolded() {
        val source = "右下（横2/3〜1、縦2/3〜1）に、円。"
        val session = DdlRangeEditorSession(table)
        val initial = session.update(DdlEditorSnapshot(source, TextRange(5)))
        val broken = source.replace("縦", "?")
        val incomplete = session.update(DdlEditorSnapshot(broken, TextRange(15)))
        assertTrue(incomplete.status.invalid)
        assertEquals(initial.status.bounds, incomplete.status.bounds)
        assertTrue(incomplete.names.isEmpty())
        val unclosed = source.replace("）", "")
        val atEnd = session.update(DdlEditorSnapshot(unclosed, TextRange(unclosed.indexOf("に"))))
        assertTrue(atEnd.status.invalid)
        assertEquals(initial.status.bounds, atEnd.status.bounds)
        assertTrue(atEnd.names.isEmpty())
        val custom = "右下（横0.2〜0.5、縦0〜0.3）に、円。"
        val editing = session.update(DdlEditorSnapshot(custom, TextRange(6)))
        assertFalse(editing.status.invalid)
        assertNotNull(editing.status.bounds)
        val leaving = session.update(DdlEditorSnapshot(custom, TextRange(custom.length)))
        assertTrue(leaving.names.isEmpty())
        assertEquals(custom, leaving.snapshot.source)
        assertTrue(ddlEditorProjection(leaving.snapshot, table).deletions.isEmpty())
    }

    @Test
    fun compositionAndReadOnlyDeferNameChangesAndNeverHideComposingText() {
        val source = "右下（横2/3〜1、縦2/3〜1）に、円。"
        val session = DdlRangeEditorSession(table)
        session.update(DdlEditorSnapshot(source, TextRange(5)))
        val edited = "右下（横0〜1/3、縦0〜1/3）に、円。"
        val composition = TextRange(edited.indexOf("横"), edited.indexOf("横") + 3)
        val composing = session.update(DdlEditorSnapshot(edited, TextRange(edited.length), composition))
        assertTrue(composing.names.isEmpty())
        assertEquals(edited, composing.snapshot.source)
        assertTrue(ddlEditorProjection(composing.snapshot, table).deletions.isEmpty())
        val readOnly = session.update(DdlEditorSnapshot(edited, TextRange(edited.length), editable = false))
        assertTrue(readOnly.names.isEmpty())
        val finished = session.update(DdlEditorSnapshot(edited, TextRange(edited.length)))
        assertEquals(1, finished.names.size)
        assertEquals("左上（横0〜1/3、縦0〜1/3）に、円。", finished.snapshot.source)
        assertNull(finished.status.active)
    }
}

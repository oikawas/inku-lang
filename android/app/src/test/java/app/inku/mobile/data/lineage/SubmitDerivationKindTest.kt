package app.inku.mobile.data.lineage

import app.inku.mobile.data.model.DerivationKindRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The truth table of both entry points, against web's.
 *
 * Read both ways round on purpose. "No parent means no kind" on its own is
 * passed by an implementation that returns null for everything, and "a parent
 * means a kind" on its own is passed by one that always writes `replay`; only
 * the pair pins the rule down. The same goes for the branch order: each case
 * that puts two changes together says which single cause has to win.
 */
class SubmitDerivationKindTest {

    // --- the describe screen (web/src/lib/derivation.ts:64-75) ---

    @Test
    fun describeSubmitWritesNoKindWithoutAParent() {
        assertNull(
            SubmitDerivationKind.forDescribeSubmit(
                hasParent = false,
                canvasAspectChanged = false,
                textChanged = false,
            ),
        )
        assertNull(
            "an edited description with nothing to descend from is still a root",
            SubmitDerivationKind.forDescribeSubmit(
                hasParent = false,
                canvasAspectChanged = false,
                textChanged = true,
            ),
        )
    }

    @Test
    fun describeSubmitAlwaysWritesAKindWithAParent() {
        // The other direction: a parent must never come out kindless, which is
        // also what `LineagePlanner` demands (PARENT_REQUIRED is raised for a
        // parent whose kind is absent).
        for (canvasAspectChanged in listOf(false, true)) {
            for (textChanged in listOf(false, true)) {
                assertNotNull(
                    "hasParent=true canvasAspectChanged=$canvasAspectChanged textChanged=$textChanged",
                    SubmitDerivationKind.forDescribeSubmit(
                        hasParent = true,
                        canvasAspectChanged = canvasAspectChanged,
                        textChanged = textChanged,
                    ),
                )
            }
        }
    }

    @Test
    fun describeSubmitReadsTheCanvasRatioBeforeTheDescription() {
        // One edge, one cause (SPEC.ja.md:614). Both moved, and the ratio wins.
        assertEquals(
            "canvas_aspect_change",
            SubmitDerivationKind.forDescribeSubmit(
                hasParent = true,
                canvasAspectChanged = true,
                textChanged = true,
            ),
        )
    }

    @Test
    fun describeSubmitNamesTheOperationThatDiffers() {
        assertEquals(
            "canvas_aspect_change",
            SubmitDerivationKind.forDescribeSubmit(hasParent = true, canvasAspectChanged = true, textChanged = false),
        )
        assertEquals(
            "description_edit",
            SubmitDerivationKind.forDescribeSubmit(hasParent = true, canvasAspectChanged = false, textChanged = true),
        )
        assertEquals(
            "replay",
            SubmitDerivationKind.forDescribeSubmit(hasParent = true, canvasAspectChanged = false, textChanged = false),
        )
    }

    // --- the DDL screen (web/src/routes/+page.svelte:3469-3471) ---

    @Test
    fun ddlSubmitWritesNoKindWithoutAParent() {
        assertNull(
            SubmitDerivationKind.forDdlSubmit(hasParent = false, canvasAspectChanged = false, ddlEdited = false),
        )
        assertNull(
            "an edited DDL with nothing to descend from is still a root",
            SubmitDerivationKind.forDdlSubmit(hasParent = false, canvasAspectChanged = false, ddlEdited = true),
        )
    }

    @Test
    fun ddlSubmitAlwaysWritesAKindWithAParent() {
        for (canvasAspectChanged in listOf(false, true)) {
            for (ddlEdited in listOf(false, true)) {
                assertNotNull(
                    "hasParent=true canvasAspectChanged=$canvasAspectChanged ddlEdited=$ddlEdited",
                    SubmitDerivationKind.forDdlSubmit(
                        hasParent = true,
                        canvasAspectChanged = canvasAspectChanged,
                        ddlEdited = ddlEdited,
                    ),
                )
            }
        }
    }

    @Test
    fun ddlSubmitReadsTheCanvasRatioBeforeTheEdit() {
        assertEquals(
            "canvas_aspect_change",
            SubmitDerivationKind.forDdlSubmit(hasParent = true, canvasAspectChanged = true, ddlEdited = true),
        )
    }

    @Test
    fun ddlSubmitSeparatesAnEditedDdlFromAnUntouchedOne() {
        assertEquals(
            "ddl_edit",
            SubmitDerivationKind.forDdlSubmit(hasParent = true, canvasAspectChanged = false, ddlEdited = true),
        )
        assertEquals(
            "replay",
            SubmitDerivationKind.forDdlSubmit(hasParent = true, canvasAspectChanged = false, ddlEdited = false),
        )
    }

    // --- what the planner will accept ---

    @Test
    fun everyKindReturnedIsOneTheServerKnows() {
        // `LineagePlanner` rejects anything outside the registry with
        // INVALID_KIND, and the registry is the server's own list.
        val returned = buildSet {
            for (hasParent in listOf(false, true)) {
                for (canvasAspectChanged in listOf(false, true)) {
                    for (flag in listOf(false, true)) {
                        SubmitDerivationKind.forDescribeSubmit(hasParent, canvasAspectChanged, flag)?.let { add(it) }
                        SubmitDerivationKind.forDdlSubmit(hasParent, canvasAspectChanged, flag)?.let { add(it) }
                    }
                }
            }
        }
        assertEquals(
            setOf("canvas_aspect_change", "description_edit", "ddl_edit", "replay"),
            returned,
        )
        assertTrue(
            "every kind must be in DerivationKindRegistry.KINDS, got $returned",
            DerivationKindRegistry.KINDS.containsAll(returned),
        )
    }
}

/**
 * Standard or detailed: how much of the settings dialog is on show.
 *
 * The dialog has grown ten tabs, and four of them answer questions a member only
 * has when they are tending the server rather than drawing.  Those four are
 * named here once, so that the tab bar and the guard that decides which tab may
 * be opened read the same list -- a bar that hid a tab the guard still allowed
 * would leave a body nothing could reach, and the reverse would leave a button
 * that does nothing when pressed.
 *
 * This is a separate question from the main screen's UI mode (uiMode.ts): that
 * one is about which panels the drawing surface carries and is saved per member
 * on the server; this one is about the settings dialog's own tab bar.
 */

export type SettingsDetailLevel = 'standard' | 'detailed';

/** Tabs the dialog only shows in the detailed mode. */
export const DETAILED_ONLY_SETTINGS_TABS = ['plugins', 'server_misc', 'limits', 'unread'] as const;

export function normalizeSettingsDetail(value: unknown): SettingsDetailLevel {
	return value === 'detailed' ? 'detailed' : 'standard';
}

export function isDetailedOnlySettingsTab(tab: string): boolean {
	return (DETAILED_ONLY_SETTINGS_TABS as readonly string[]).includes(tab);
}

/**
 * Whether the detail level alone lets this tab appear.  Whether the member is
 * allowed to open it is a separate question, asked in permissionGroups.ts; the
 * page has to pass both.
 */
export function settingsTabShownAtDetail(tab: string, detail: SettingsDetailLevel): boolean {
	return detail === 'detailed' || !isDetailedOnlySettingsTab(tab);
}

/**
 * What a member may do, decided by the permission groups they hold.
 *
 * The page used to spell `currentUser?.role === 'admin'` out at every gate, so
 * the same question was answered in twenty places.  It lives here instead: the
 * page still calls it from the same spots -- extracting a decision does not move
 * where it is asked -- but there is now one definition to change, and one that a
 * test can execute without a Svelte compiler.
 */

export type PermissionGroup = 'admins' | 'leaders' | 'users';

export const PERMISSION_GROUPS: PermissionGroup[] = ['admins', 'leaders', 'users'];

type MemberLike = { permission_groups?: PermissionGroup[] } | null | undefined;

export function holdsPermissionGroup(user: MemberLike, name: PermissionGroup): boolean {
	return user?.permission_groups?.includes(name) === true;
}

/** Settings tabs only the administrators group reaches. */
export const ADMIN_ONLY_SETTINGS_TABS = ['models', 'db', 'users', 'server_misc', 'logs', 'limits'] as const;

export function canAccessSettingsTab(tab: string, user: MemberLike): boolean {
	if ((ADMIN_ONLY_SETTINGS_TABS as readonly string[]).includes(tab)) {
		return holdsPermissionGroup(user, 'admins');
	}
	return tab !== 'connection';
}

export function defaultSettingsTab(user: MemberLike): 'models' | 'plugins' {
	return holdsPermissionGroup(user, 'admins') ? 'models' : 'plugins';
}

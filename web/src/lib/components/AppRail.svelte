<script lang="ts">
	import { t, setLang, getLang, PACK_LIST } from '$lib/i18n/index.svelte';
	import Tooltip from './Tooltip.svelte';

	type UserItem = {
		username: string;
		email: string;
	};

	type Props = {
		currentUser: UserItem;
		userMenuOpen: boolean;
		userMenuWrapEl: HTMLDivElement | null;
		settingsOpen: boolean;
		darkMode: boolean;
		buildNumber: string;
		developerMode: boolean;
		onToggleUserMenu: () => void;
		onOpenProfile: () => void;
		onLogout: () => void | Promise<void>;
		onOpenSettings: () => void;
		onToggleTheme: () => void;
		onOpenAppInfo: () => void;
	};

	let {
		currentUser,
		userMenuOpen = $bindable(false),
		userMenuWrapEl = $bindable(null),
		settingsOpen,
		darkMode,
		buildNumber,
		developerMode,
		onToggleUserMenu,
		onOpenProfile,
		onLogout,
		onOpenSettings,
		onToggleTheme,
		onOpenAppInfo,
	}: Props = $props();

	let expanded = $state(false);

	function toggleExpanded() {
		expanded = !expanded;
		if (!expanded) userMenuOpen = false;
	}
</script>

<aside class="app-rail" class:expanded>
	<div class="rail-brand">
		<div class="rail-top-row">
			<Tooltip placement="right" text={t().tooltipAppRailToggle}>
				<button
					class="rail-toggle"
					type="button"
					onclick={toggleExpanded}
					aria-pressed={expanded}
					aria-label={expanded ? t().railCollapseLabel : t().railExpandLabel}
				>
					<span aria-hidden="true">{expanded ? "‹" : "›"}</span>
				</button>
			</Tooltip>
		</div>
		<div class="rail-logo-row">
			<Tooltip placement="right" text={t().tooltipAppRailLogo}>
				<button class="rail-logo" type="button" onclick={onOpenAppInfo} aria-label={t().appInfoOpenLabel}>
					<span class="rail-logo-core">inku</span>{#if expanded}<span class="rail-logo-suffix">-lang</span>{/if}
				</button>
			</Tooltip>
		</div>
		{#if expanded}<div class="rail-sub">{t().subtitle}</div>{/if}
	</div>

	<div class="rail-actions">
		<div class="rail-menu-wrap" bind:this={userMenuWrapEl}>
			<Tooltip placement="right" text={`${t().tooltipAppRailUser} (${currentUser.email || currentUser.username})`}>
				<button
					class="rail-action"
					class:active={userMenuOpen}
					type="button"
					aria-haspopup="menu"
					aria-expanded={userMenuOpen}
					onclick={onToggleUserMenu}
				>
					<span class="rail-icon user-icon" aria-hidden="true"></span>
					{#if expanded}<span class="rail-label">{currentUser.username}</span>{/if}
				</button>
			</Tooltip>
			{#if userMenuOpen}
				<div class="rail-user-menu" role="menu">
					<button type="button" role="menuitem" onclick={onOpenProfile}>{t().profileButton}</button>
					<button type="button" role="menuitem" onclick={onLogout}>{t().logoutButton}</button>
				</div>
			{/if}
		</div>

		<Tooltip placement="right" text={t().tooltipAppRailSettings}>
			<button class="rail-action" class:active={settingsOpen} onclick={onOpenSettings}>
				<span class="rail-icon gear-icon" aria-hidden="true"></span>
				{#if expanded}<span class="rail-label">{t().settingsButton}</span>{/if}
			</button>
		</Tooltip>

		<Tooltip placement="right" text={t().tooltipAppRailTheme}>
			<button class="rail-action" onclick={onToggleTheme}>
				<span class="rail-icon theme-icon" class:dark={darkMode} aria-hidden="true"></span>
				{#if expanded}<span class="rail-label">{darkMode ? t().themeLight : t().themeDark}</span>{/if}
			</button>
		</Tooltip>

		<div class="rail-lang" class:expanded>
			{#each PACK_LIST as pack (pack.code)}
				<Tooltip placement="right" text={`${t().tooltipAppRailLang}: ${pack.label}`}>
					<button class:active={getLang() === pack.code} onclick={() => setLang(pack.code)}>
						{expanded ? pack.label : pack.code.toUpperCase()}
					</button>
				</Tooltip>
			{/each}
		</div>
	</div>

	<div class="rail-spacer"></div>
	{#if developerMode}
		<Tooltip placement="right" text={`Build ${buildNumber}`}>
			<div class="rail-build">
				{#if expanded}<span>Build </span>{/if}{buildNumber}
			</div>
		</Tooltip>
	{/if}
</aside>

<style>
	.app-rail {
		position: relative;
		z-index: 120;
		width: 44px;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: 12px;
		padding: 10px 6px;
		border-right: 1px solid var(--border);
		background: var(--bg);
		transition: width 0.16s ease;
		overflow: visible;
	}
	.app-rail.expanded {
		width: 164px;
	}
	.rail-brand {
		min-height: 78px;
		display: flex;
		flex-direction: column;
		justify-content: flex-start;
		padding: 0;
	}
	.rail-top-row,
	.rail-logo-row {
		height: 30px;
		display: flex;
		align-items: center;
	}
	.rail-toggle {
		width: 30px;
		height: 30px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-family: inherit;
		font-size: 18px;
		line-height: 1;
		cursor: pointer;
	}
	.rail-toggle:hover {
		background: var(--bg2);
		color: var(--fg);
	}
	/* 作品情報への入口。押せることが見えるよう、rail-toggle と同じ器に載せる。 */
	.rail-logo {
		width: auto;
		height: 30px;
		display: flex;
		align-items: center;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		padding: 0;
		background: var(--panel);
		font-size: 15px;
		font-weight: 300;
		letter-spacing: 0;
		line-height: 1;
		color: var(--fg);
		white-space: nowrap;
		transform-origin: left center;
		font-family: inherit;
		cursor: pointer;
	}
	.rail-logo:hover {
		background: var(--bg2);
		border-color: var(--fg3);
	}
	.app-rail.expanded .rail-logo {
		padding-right: 9px;
	}
	.rail-logo-core {
		width: 30px;
		flex: 0 0 30px;
		text-align: center;
	}
	.rail-logo-suffix {
		flex: 0 0 auto;
		opacity: 0;
		transition: opacity 0.12s ease;
	}
	.app-rail.expanded .rail-logo-suffix {
		opacity: 1;
		transition-delay: 0.08s;
	}
	.rail-sub {
		margin-top: 4px;
		color: var(--fg3);
		font-size: 10px;
		line-height: 1.3;
		white-space: nowrap;
		opacity: 0;
		transition: opacity 0.12s ease;
	}
	.app-rail.expanded .rail-sub {
		opacity: 1;
		transition-delay: 0.08s;
	}
	.rail-actions {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.rail-menu-wrap {
		position: relative;
	}
	.rail-action {
		width: 100%;
		min-height: 30px;
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 4px;
		border: 1px solid transparent;
		border-radius: var(--r);
		background: transparent;
		color: var(--fg2);
		font-family: inherit;
		font-size: 11px;
		cursor: pointer;
		text-align: left;
	}
	.rail-action:hover,
	.rail-action.active {
		background: var(--panel);
		border-color: var(--border2);
		color: var(--fg);
	}
	.rail-icon {
		width: 22px;
		height: 22px;
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: 1px solid var(--border2);
		border-radius: 50%;
		background: var(--panel);
		color: var(--fg2);
		position: relative;
	}
	.user-icon::before {
		content: "";
		position: absolute;
		top: 4px;
		left: 7px;
		width: 6px;
		height: 6px;
		border: 1.6px solid currentColor;
		border-radius: 50%;
	}
	.user-icon::after {
		content: "";
		position: absolute;
		left: 5px;
		bottom: 4px;
		width: 10px;
		height: 6px;
		border: 1.6px solid currentColor;
		border-radius: 8px 8px 3px 3px;
		border-bottom: none;
	}
	.gear-icon::before {
		content: "";
		position: absolute;
		top: 5px;
		left: 5px;
		width: 10px;
		height: 10px;
		border: 2px solid currentColor;
		border-radius: 50%;
		box-shadow:
			0 -5px 0 -3px currentColor,
			0 5px 0 -3px currentColor,
			5px 0 0 -3px currentColor,
			-5px 0 0 -3px currentColor,
			3.6px 3.6px 0 -3px currentColor,
			-3.6px 3.6px 0 -3px currentColor,
			3.6px -3.6px 0 -3px currentColor,
			-3.6px -3.6px 0 -3px currentColor;
	}
	.gear-icon::after {
		content: "";
		position: absolute;
		top: 8.5px;
		left: 8.5px;
		width: 4px;
		height: 4px;
		border-radius: 50%;
		background: currentColor;
	}
	.theme-icon::before {
		content: "";
		position: absolute;
		inset: 5px;
		border-radius: 50%;
		background: currentColor;
		box-shadow: 4px -3px 0 0 var(--panel);
	}
	.theme-icon.dark::before {
		inset: 4px;
		box-shadow: none;
		background: #d9c46a;
	}
	.rail-action:not(:hover):not(.active) .gear-icon {
		color: var(--fg3);
		opacity: 0.86;
	}
	.rail-label {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		opacity: 0;
		transition: opacity 0.12s ease;
	}
	.app-rail.expanded .rail-label {
		opacity: 1;
		transition-delay: 0.08s;
	}
	.rail-user-menu {
		position: absolute;
		top: 0;
		left: calc(100% + 8px);
		z-index: 100;
		min-width: 126px;
		padding: 4px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		box-shadow: 0 8px 22px rgba(37, 34, 26, 0.14);
	}
	.rail-user-menu button {
		width: 100%;
		padding: 7px 9px;
		border: none;
		border-radius: 4px;
		background: transparent;
		color: var(--fg2);
		font-size: 11px;
		text-align: left;
		cursor: pointer;
		font-family: inherit;
	}
	.rail-user-menu button:hover {
		background: var(--bg2);
		color: var(--fg);
	}
	.rail-lang {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.rail-lang.expanded {
		flex-direction: row;
	}
	.rail-lang button {
		flex: 1;
		min-width: 0;
		padding: 4px 5px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 10px;
		cursor: pointer;
		font-family: inherit;
	}
	.rail-lang button.active {
		background: var(--fg);
		color: var(--panel);
		border-color: var(--fg);
	}
	.rail-spacer {
		flex: 1;
	}
	.rail-build {
		padding: 4px 2px;
		color: var(--fg3);
		font-size: 10px;
		font-variant-numeric: tabular-nums;
		text-align: center;
		white-space: nowrap;
	}
</style>

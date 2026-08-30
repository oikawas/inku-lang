<script lang="ts">
	import { t, setLang, getLang, PACK_LIST } from '$lib/i18n/index.svelte';
	import Tooltip from './Tooltip.svelte';
	import type { UiMode } from '$lib/uiMode';

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
		singleUserMode: boolean;
		showAuxiliary: boolean;
		uiMode: UiMode;
		tooltipsEnabled: boolean;
		onSetUiMode: (mode: UiMode) => void | Promise<void>;
		onToggleTooltips: () => void | Promise<void>;
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
		singleUserMode,
		showAuxiliary,
		uiMode,
		tooltipsEnabled,
		onSetUiMode,
		onToggleTooltips,
		onToggleUserMenu,
		onOpenProfile,
		onLogout,
		onOpenSettings,
		onToggleTheme,
		onOpenAppInfo,
	}: Props = $props();

	let expanded = $state(false);
	let uiModeOpen = $state(false);
	let uiModeWrapEl: HTMLDivElement | null = null;
	const uiModeLabel = $derived(uiMode === 'full' ? t().uiModeFull : uiMode === 'custom' ? t().uiModeCustom : t().uiModeSimple);

	function selectUiMode(mode: UiMode) {
		uiModeOpen = false;
		void onSetUiMode(mode);
	}

	function toggleExpanded() {
		expanded = !expanded;
		if (!expanded) {
			userMenuOpen = false;
			uiModeOpen = false;
		}
	}
</script>

<svelte:window onclick={(event) => {
	if (uiModeOpen && !uiModeWrapEl?.contains(event.target as Node)) uiModeOpen = false;
}} />

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
		{#if showAuxiliary}<div class="rail-logo-row">
			<Tooltip placement="right" text={t().tooltipAppRailLogo}>
				<button class="rail-logo" type="button" onclick={onOpenAppInfo} aria-label={t().appInfoOpenLabel}>
					<span class="rail-logo-core">inku</span>{#if expanded}<span class="rail-logo-suffix">-lang</span>{/if}
				</button>
			</Tooltip>
		</div>{/if}
		{#if showAuxiliary && expanded}<div class="rail-sub">{t().subtitle}</div>{/if}
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
					{#if !singleUserMode}
						<button type="button" role="menuitem" onclick={onLogout}>{t().logoutButton}</button>
					{/if}
				</div>
			{/if}
		</div>

		<div class="rail-menu-wrap" bind:this={uiModeWrapEl}>
			<Tooltip placement="right" text={t().uiModeLabel} disabled={uiModeOpen}>
				<button class="rail-action" class:active={uiModeOpen} type="button" aria-haspopup="menu" aria-expanded={uiModeOpen} onclick={() => (uiModeOpen = !uiModeOpen)}>
					<!-- Three bars, not ::before/::after: the icon needs three of them,
					     and which are solid is what says which mode is on. -->
					<span class="rail-icon ui-mode-icon ui-mode-{uiMode}" aria-hidden="true">
						<span class="ui-mode-bar"></span>
						<span class="ui-mode-bar"></span>
						<span class="ui-mode-bar"></span>
					</span>
					{#if expanded}<span class="rail-label">{uiModeLabel}</span>{/if}
				</button>
			</Tooltip>
			{#if uiModeOpen}
				<!-- In the order the icon draws them: one bar, two, three. The menu
				     used to read simple / full / custom, which put the middle amount
				     last and left the list disagreeing with the mark above it. -->
				<div class="rail-user-menu ui-mode-menu" role="menu" aria-label={t().uiModeLabel}>
					<button type="button" role="menuitemradio" aria-checked={uiMode === 'simple'} class:selected={uiMode === 'simple'} onclick={() => selectUiMode('simple')}>{t().uiModeSimple}</button>
					<button type="button" role="menuitemradio" aria-checked={uiMode === 'custom'} class:selected={uiMode === 'custom'} onclick={() => selectUiMode('custom')}>{t().uiModeCustom}</button>
					<button type="button" role="menuitemradio" aria-checked={uiMode === 'full'} class:selected={uiMode === 'full'} onclick={() => selectUiMode('full')}>{t().uiModeFull}</button>
				</div>
			{/if}
		</div>

		<Tooltip placement="right" text={tooltipsEnabled ? t().tooltipsHide : t().tooltipsShow}>
			<button
				class="rail-action"
				class:on={tooltipsEnabled}
				type="button"
				aria-pressed={tooltipsEnabled}
				aria-label={tooltipsEnabled ? t().tooltipsHide : t().tooltipsShow}
				onclick={onToggleTooltips}
			>
				<span class="rail-icon tooltip-icon" aria-hidden="true">?</span>
				{#if expanded}<span class="rail-label">{tooltipsEnabled ? t().tooltipsHide : t().tooltipsShow}</span>{/if}
			</button>
		</Tooltip>

		<Tooltip placement="right" text={t().tooltipAppRailSettings}>
			<button class="rail-action" class:active={settingsOpen} onclick={onOpenSettings}>
				<span class="rail-icon gear-icon" aria-hidden="true"></span>
				{#if expanded}<span class="rail-label">{t().settingsButton}</span>{/if}
			</button>
		</Tooltip>

		{#if showAuxiliary}
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
		{/if}
	</div>

	<div class="rail-spacer"></div>
	{#if developerMode && showAuxiliary}
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
	/* Separate the collapse and inku buttons because they serve different roles. */
	.rail-logo-row {
		margin-top: 6px;
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
	/* Match rail-toggle's container so the artwork-information entry looks actionable. */
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
	/* How much of the interface is on show, drawn as how much of the mark is
	   drawn. The frame this replaced was the same picture in all three modes,
	   and the 4x2 dot it carried was not visible at the rail's own 22px.
	   A faint bar is a row the mode is holding back, so the icon says which
	   mode is on without the label the collapsed rail does not draw. */
	.ui-mode-bar {
		position: absolute;
		left: 5px;
		height: 2px;
		border-radius: 1px;
		background: currentColor;
	}
	.ui-mode-bar:nth-child(1) { top: 6px;  width: 12px; }
	.ui-mode-bar:nth-child(2) { top: 10px; width: 8px; }
	.ui-mode-bar:nth-child(3) { top: 14px; width: 5px; }
	/* simple: one row out of three. full: all of them. custom: in between --
	   it starts from simple and adds, so it is never the whole set. */
	.ui-mode-simple .ui-mode-bar:nth-child(2),
	.ui-mode-simple .ui-mode-bar:nth-child(3),
	.ui-mode-custom .ui-mode-bar:nth-child(3) { opacity: 0.3; }
	.ui-mode-menu button.selected { color: var(--fg); font-weight: 600; }
	.ui-mode-menu button.selected::before { content: '✓'; margin-right: 6px; }

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
	.tooltip-icon {
		font-size: 13px;
		font-weight: 600;
	}
	.tooltip-icon::after {
		content: "";
		position: absolute;
		width: 16px;
		height: 1.5px;
		border-radius: 1px;
		background: currentColor;
		transform: rotate(-45deg);
		opacity: 0.9;
	}
	.rail-action.on .tooltip-icon::after {
		display: none;
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

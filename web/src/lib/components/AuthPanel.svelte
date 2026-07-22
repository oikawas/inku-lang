<script lang="ts">
	import { t, setLang, getLang, PACK_LIST } from '$lib/i18n/index.svelte';

	type Props = {
		loginUserName: string;
		loginPassword: string;
		loginPasswordVisible: boolean;
		loginStatus: string | null;
		onLogin: () => void | Promise<void>;
		appVersion: string;
		buildNumber: string;
	};

	let {
		loginUserName = $bindable(''),
		loginPassword = $bindable(''),
		loginPasswordVisible = $bindable(false),
		loginStatus,
		onLogin,
		appVersion,
		buildNumber
	}: Props = $props();
</script>

<main class="login-screen">
	<section class="login-panel" aria-labelledby="login-title">
		<div class="login-brand">
			<div class="login-brand-head">
				<div>
					<div class="login-logo">inku</div>
					<div class="login-sub">{t().subtitle}</div>
				</div>
				<div class="login-lang-switcher" aria-label="Language">
					{#each PACK_LIST as pack (pack.code)}
						<button
							type="button"
							class="login-lang-btn"
							class:active={getLang() === pack.code}
							title={pack.label}
							onclick={() => setLang(pack.code)}
						>{pack.code.toUpperCase()}</button>
					{/each}
				</div>
			</div>
		</div>
		<div class="login-title" id="login-title">{t().loginTitle}</div>
		<div class="login-panel-body">
			{#if loginStatus}
				<div class="inline-message">{loginStatus}</div>
			{/if}
			<div class="login-grid">
				<input bind:value={loginUserName} placeholder={t().loginUsernamePlaceholder} autocomplete="username" />
				<div class="password-field">
					<input
						bind:value={loginPassword}
						type={loginPasswordVisible ? 'text' : 'password'}
						placeholder={t().loginPasswordPlaceholder}
						autocomplete="current-password"
						onkeydown={(e) => { if (e.key === 'Enter') void onLogin(); }}
					/>
					<button
						class="password-toggle"
						type="button"
						aria-pressed={loginPasswordVisible}
						aria-label={loginPasswordVisible ? t().loginPasswordHide : t().loginPasswordShow}
						title={loginPasswordVisible ? t().loginPasswordHide : t().loginPasswordShow}
						onclick={() => (loginPasswordVisible = !loginPasswordVisible)}
					>
						{#if loginPasswordVisible}
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="M3 3l18 18" />
								<path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
								<path d="M8.4 5.4A10.5 10.5 0 0 1 12 4c5 0 8.5 4.6 9.7 6.4a1.8 1.8 0 0 1 0 2 17 17 0 0 1-2.3 2.8" />
								<path d="M15.7 15.7A10.5 10.5 0 0 1 12 17c-5 0-8.5-4.6-9.7-6.4a1.8 1.8 0 0 1 0-2A17 17 0 0 1 5 5.4" />
							</svg>
						{:else}
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="M2.3 10.6C3.5 8.8 7 4 12 4s8.5 4.8 9.7 6.6a1.8 1.8 0 0 1 0 2C20.5 14.4 17 19 12 19s-8.5-4.6-9.7-6.4a1.8 1.8 0 0 1 0-2Z" />
								<circle cx="12" cy="11.6" r="2.7" />
							</svg>
						{/if}
					</button>
				</div>
				<button class="ghost-btn login-submit" onclick={onLogin}>{t().loginSubmit}</button>
			</div>
		</div>
		<div class="login-meta">{appVersion} {t().appInfoBuildLabel} {buildNumber}</div>
	</section>
</main>

<style>
	.login-screen {
		min-height: 100vh;
		display: grid;
		place-items: center;
		padding: 32px;
		position: relative;
		overflow: hidden;
		background:
			linear-gradient(90deg, rgba(250, 249, 246, 0.96) 0%, rgba(250, 249, 246, 0.86) 42%, rgba(250, 249, 246, 0.34) 100%),
			linear-gradient(180deg, rgba(245, 241, 232, 0.92) 0%, rgba(234, 229, 216, 0.74) 100%),
			url('/login-background.svg') right 17% center / min(1120px, 112vw) auto no-repeat,
			var(--bg);
		color: var(--fg);
	}
	.login-screen::before {
		content: '';
		position: absolute;
		inset: 0;
		background: radial-gradient(circle at 72% 44%, rgba(255, 255, 255, 0) 0 34%, rgba(250, 249, 246, 0.58) 76%);
		pointer-events: none;
	}
	.login-panel {
		width: min(420px, calc(100vw - 32px));
		position: relative;
		z-index: 1;
		background: rgba(250, 249, 246, 0.94);
		border-radius: var(--r);
		box-shadow: 0 18px 54px rgba(40, 35, 24, 0.18);
		border: 1px solid rgba(90, 83, 68, 0.22);
		-webkit-backdrop-filter: blur(10px);
		backdrop-filter: blur(10px);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.login-brand {
		padding: 20px 24px 12px;
		border-bottom: 1px solid var(--border);
	}
	.login-brand-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 18px;
	}
	.login-logo {
		font-size: 22px;
		font-weight: 300;
		letter-spacing: 0.02em;
	}
	.login-sub {
		margin-top: 2px;
		color: var(--fg3);
		font-size: 11px;
	}
	.login-meta {
		padding: 0 24px 18px;
		color: var(--fg3);
		font-size: 11px;
		letter-spacing: 0.02em;
	}
	.login-lang-switcher {
		display: flex;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		overflow: hidden;
		flex-shrink: 0;
	}
	.login-lang-btn {
		min-width: 34px;
		height: 26px;
		padding: 0 8px;
		border: none;
		border-right: 1px solid var(--border2);
		background: rgba(255, 255, 255, 0.72);
		color: var(--fg2);
		font-family: inherit;
		font-size: 11px;
		font-weight: 500;
		cursor: pointer;
	}
	.login-lang-btn:last-child { border-right: none; }
	.login-lang-btn:hover { color: var(--fg); background: var(--panel); }
	.login-lang-btn.active { background: var(--fg); color: #fff; }
	.login-title {
		padding: 18px 24px 0;
		font-size: 16px;
		font-weight: 500;
	}
	.login-panel-body {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 14px 24px 24px;
	}
	.login-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: 10px;
	}
	.login-grid input {
		min-height: 38px;
		padding: 8px 10px;
		font-size: 13px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		font-family: inherit;
	}
	.login-submit {
		min-height: 38px;
		font-size: 13px;
		font-weight: 500;
	}
	.password-field {
		display: flex;
		align-items: stretch;
		min-width: 0;
	}
	.password-field input {
		border-top-right-radius: 0;
		border-bottom-right-radius: 0;
		flex: 1;
		min-width: 0;
	}
	.password-toggle {
		width: 38px;
		border: 1px solid var(--border2);
		border-left: none;
		border-radius: 0 var(--r) var(--r) 0;
		background: var(--panel);
		color: var(--fg2);
		display: grid;
		place-items: center;
		cursor: pointer;
	}
	.password-toggle svg {
		width: 17px;
		height: 17px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.8;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.inline-message {
		border: 1px solid var(--border);
		background: rgba(255,255,255,0.72);
		border-radius: var(--r);
		padding: 8px 10px;
		font-size: 12px;
		color: var(--fg2);
	}
	.ghost-btn {
		border: 1px solid var(--border2);
		padding: var(--btn-sm-padding);
		font-size: var(--btn-sm-font-size);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg);
		font-family: inherit;
		cursor: pointer;
	}
</style>

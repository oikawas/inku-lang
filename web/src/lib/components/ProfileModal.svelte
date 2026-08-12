<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	type Props = {
		username: string;
		email: string;
		generationCount: number;
		status: string | null;
		saving: boolean;
		profileEmail: string;
		profileCurrentPassword: string;
		profileNewPassword: string;
		onClose: () => void;
		onSave: () => void | Promise<void>;
	};

	let {
		username,
		email,
		generationCount,
		status,
		saving,
		profileEmail = $bindable(''),
		profileCurrentPassword = $bindable(''),
		profileNewPassword = $bindable(''),
		onClose,
		onSave,
	}: Props = $props();
</script>

<div class="modal-backdrop" role="presentation" onclick={onClose}>
	<div
		class="profile-modal"
		role="dialog"
		aria-modal="true"
		aria-labelledby="profile-title"
		tabindex="-1"
		onclick={(event) => event.stopPropagation()}
		onkeydown={(event) => event.stopPropagation()}
	>
		<div class="modal-head">
			<div>
				<div id="profile-title" class="profile-title">{t().profileTitle}</div>
				<div class="profile-sub">{username} / {email}</div>
			</div>
			<button class="ghost-btn" type="button" onclick={onClose}>{t().closeLabel}</button>
		</div>

		<div class="profile-body">
			<div class="profile-stat">
				<span>{t().profileGenerationCountLabel}</span>
				<strong>{generationCount.toLocaleString()}</strong>
			</div>
			<label class="profile-field">
				<span>{t().profileEmailLabel}</span>
				<input bind:value={profileEmail} type="email" autocomplete="email" />
			</label>
			<div class="profile-password-box">
				<div class="profile-help">{t().profilePasswordHelp}</div>
				<label class="profile-field">
					<span>{t().profileCurrentPasswordLabel}</span>
					<input bind:value={profileCurrentPassword} type="password" autocomplete="current-password" />
				</label>
				<label class="profile-field">
					<span>{t().profileNewPasswordLabel}</span>
					<input bind:value={profileNewPassword} type="password" autocomplete="new-password" />
				</label>
			</div>
			{#if status}
				<div class="profile-status">{status}</div>
			{/if}
		</div>

		<div class="profile-actions">
			<button class="ghost-btn" type="button" onclick={onClose} disabled={saving}>{t().confirmCancel}</button>
			<button class="primary-btn" type="button" onclick={onSave} disabled={saving}>{t().profileSaveButton}</button>
		</div>
	</div>
</div>

<style>
	.modal-backdrop {
		position: fixed;
		inset: 0;
		z-index: 130;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 18px;
		background: rgba(24, 22, 18, 0.28);
	}
	.profile-modal {
		width: min(420px, 100%);
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--bg);
		box-shadow: 0 18px 44px rgba(37, 34, 26, 0.22);
		color: var(--fg);
	}
	.modal-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 12px;
		padding: 14px 16px;
		border-bottom: 1px solid var(--border);
	}
	.profile-title {
		font-size: 14px;
		font-weight: 500;
	}
	.profile-sub {
		margin-top: 3px;
		color: var(--fg3);
		font-size: 11px;
	}
	.profile-body {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 14px 16px;
	}
	.profile-stat {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 12px;
		padding: 9px 10px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
	}
	.profile-stat span {
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.profile-stat strong {
		color: var(--fg);
		font-size: 14px;
		font-weight: 500;
		font-variant-numeric: tabular-nums;
	}
	.profile-field {
		display: flex;
		flex-direction: column;
		gap: 5px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.profile-field input {
		width: 100%;
		min-width: 0;
		padding: 7px 8px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: inherit;
		text-transform: none;
		letter-spacing: 0;
	}
	.profile-password-box {
		display: grid;
		gap: 9px;
		padding: 10px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
	}
	.profile-help {
		color: var(--fg2);
		font-size: 11px;
		line-height: 1.45;
	}
	.profile-status {
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 12px;
	}
	.profile-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		padding: 12px 16px 14px;
		border-top: 1px solid var(--border);
	}
	.primary-btn {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font-size: var(--btn-sm-font-size);
		font-family: inherit;
		cursor: pointer;
	}
	.primary-btn {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--accent);
	}
	.primary-btn:disabled {
		opacity: 0.55;
		cursor: default;
	}
</style>

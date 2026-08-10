<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	// One work's guest list. The permission groups decide a default scope --
	// what an admin or a leader reaches without being named -- and this is the
	// exception to it, named per person or per organisation.
	//
	// PUT replaces the whole list, so every change here sends the complete set.
	// Sending only the row being added would silently revoke everyone else.
	export type AclEntry = {
		subject_type: 'user' | 'org_group';
		subject_id: string;
		permission: 'read' | 'write';
	};

	type Candidate = { id: string; name: string };

	type Props = {
		itemId: string;
		itemLabel: string;
		users: Candidate[];
		groups: Candidate[];
		isJapanese: boolean;
		onClose: () => void;
	};

	let { itemId, itemLabel, users, groups, isJapanese, onClose }: Props = $props();

	let entries = $state<AclEntry[]>([]);
	let loading = $state(true);
	let saving = $state(false);
	let error = $state<string | null>(null);

	let subjectType = $state<'user' | 'org_group'>('user');
	let subjectId = $state('');
	let permission = $state<'read' | 'write'>('read');

	const candidates = $derived(subjectType === 'user' ? users : groups);

	function nameOf(entry: AclEntry): string {
		const pool = entry.subject_type === 'user' ? users : groups;
		return pool.find((c) => c.id === entry.subject_id)?.name ?? entry.subject_id;
	}

	async function load() {
		loading = true;
		error = null;
		try {
			const response = await fetch(`/api/history/${encodeURIComponent(itemId)}/acl`, {
				credentials: 'include',
				cache: 'no-store',
			});
			if (!response.ok) throw new Error(String(response.status));
			entries = (await response.json()) as AclEntry[];
		} catch {
			error = isJapanese ? '共有の設定を読み込めませんでした。' : 'Could not load the guest list.';
		} finally {
			loading = false;
		}
	}

	async function put(next: AclEntry[]) {
		saving = true;
		error = null;
		try {
			const response = await fetch(`/api/history/${encodeURIComponent(itemId)}/acl`, {
				method: 'PUT',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					entries: next.map((e) => ({
						subject_type: e.subject_type,
						subject_id: e.subject_id,
						permission: e.permission,
					})),
				}),
			});
			if (!response.ok) throw new Error(String(response.status));
			entries = (await response.json()) as AclEntry[];
		} catch {
			error = isJapanese ? '共有の設定を保存できませんでした。' : 'Could not save the guest list.';
		} finally {
			saving = false;
		}
	}

	function add() {
		if (!subjectId) return;
		const kept = entries.filter(
			(e) => !(e.subject_type === subjectType && e.subject_id === subjectId),
		);
		void put([...kept, { subject_type: subjectType, subject_id: subjectId, permission }]);
		subjectId = '';
	}

	function remove(entry: AclEntry) {
		void put(
			entries.filter(
				(e) => !(e.subject_type === entry.subject_type && e.subject_id === entry.subject_id),
			),
		);
	}

	$effect(() => {
		void itemId;
		void load();
	});
</script>

<div class="modal-backdrop" role="presentation" onclick={onClose}>
	<div
		class="share-modal"
		role="dialog"
		aria-modal="true"
		aria-labelledby="share-title"
		tabindex="-1"
		onclick={(event) => event.stopPropagation()}
		onkeydown={(event) => event.stopPropagation()}
	>
		<div class="modal-head">
			<div>
				<div id="share-title" class="share-title">
					{isJapanese ? '共有' : 'Share'}
				</div>
				<div class="share-sub">{itemLabel}</div>
			</div>
			<button class="ghost-btn" type="button" onclick={onClose}>{t().closeLabel}</button>
		</div>

		<div class="share-body">
			{#if loading}
				<div class="share-note">{isJapanese ? '読み込み中…' : 'Loading…'}</div>
			{:else}
				{#if entries.length === 0}
					<div class="share-note">
						{isJapanese
							? 'この作品はまだ誰にも共有されていません。'
							: 'This work has not been shared with anyone yet.'}
					</div>
				{:else}
					<ul class="share-list">
						{#each entries as entry (entry.subject_type + entry.subject_id)}
							<li class="share-row">
								<span class="share-kind">
									{entry.subject_type === 'user'
										? isJapanese ? '利用者' : 'Member'
										: isJapanese ? 'グループ' : 'Group'}
								</span>
								<span class="share-name">{nameOf(entry)}</span>
								<span class="share-permission">
									{entry.permission === 'write'
										? isJapanese ? '編集できる' : 'Can edit'
										: isJapanese ? '見られる' : 'Can view'}
								</span>
								<button
									class="ghost-btn"
									type="button"
									disabled={saving}
									onclick={() => remove(entry)}
								>{isJapanese ? '外す' : 'Remove'}</button>
							</li>
						{/each}
					</ul>
				{/if}

				<div class="share-add">
					<select bind:value={subjectType} aria-label={isJapanese ? '宛先の種類' : 'Kind of guest'}>
						<option value="user">{isJapanese ? '利用者' : 'Member'}</option>
						<option value="org_group">{isJapanese ? 'グループ' : 'Group'}</option>
					</select>
					{#if candidates.length > 0}
						<select bind:value={subjectId} aria-label={isJapanese ? '宛先' : 'Guest'}>
							<option value="">{isJapanese ? '選んでください' : 'Choose…'}</option>
							{#each candidates as candidate (candidate.id)}
								<option value={candidate.id}>{candidate.name}</option>
							{/each}
						</select>
					{:else}
						<!-- Only a member manager may list the accounts on this server, and
						     the owner of a work usually is not one. Rather than open that
						     listing to everyone, take the id directly: the person sharing
						     knows who they mean and can be told the id. -->
						<input
							bind:value={subjectId}
							type="text"
							aria-label={isJapanese ? '宛先の ID' : 'Guest ID'}
							placeholder={isJapanese ? '相手の ID' : 'their ID'}
						/>
					{/if}
					<select bind:value={permission} aria-label={isJapanese ? '権限' : 'Permission'}>
						<option value="read">{isJapanese ? '見られる' : 'Can view'}</option>
						<option value="write">{isJapanese ? '編集できる' : 'Can edit'}</option>
					</select>
					<button
						class="accent-btn"
						type="button"
						disabled={saving || !subjectId}
						onclick={add}
					>{isJapanese ? '共有する' : 'Share'}</button>
				</div>

				<p class="share-help">
					{isJapanese
						? '「編集できる」を渡すと、星・ゴミ箱・削除もできるようになります。共有を外すと相手の一覧から消えますが、その人が作った変奏は残ります。'
						: '“Can edit” also allows starring, trashing and deleting. Removing someone takes the work out of their listing; any variation they made from it stays theirs.'}
				</p>
			{/if}

			{#if error}<div class="share-error">{error}</div>{/if}
		</div>
	</div>
</div>

<style>
	.modal-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.45);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 60;
	}
	.share-modal {
		background: var(--panel-bg);
		color: var(--fg);
		border: 1px solid var(--border);
		border-radius: 12px;
		width: min(34rem, 92vw);
		max-height: 86vh;
		overflow: auto;
		padding: 1rem 1.1rem 1.2rem;
	}
	.modal-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
	}
	.share-title { font-weight: 600; }
	.share-sub {
		font-size: 0.85em;
		opacity: 0.75;
		overflow-wrap: anywhere;
	}
	.share-body { margin-top: 0.9rem; display: grid; gap: 0.8rem; }
	.share-note, .share-help { font-size: 0.85em; opacity: 0.8; margin: 0; }
	.share-error { font-size: 0.85em; color: var(--danger, #c0392b); }
	.share-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
	.share-row {
		display: grid;
		grid-template-columns: auto 1fr auto auto;
		gap: 0.5rem;
		align-items: center;
	}
	.share-kind, .share-permission { font-size: 0.8em; opacity: 0.75; }
	.share-name { overflow-wrap: anywhere; }
	.share-add {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		align-items: center;
	}
	.share-add select, .share-add input {
		padding: var(--btn-sm-padding);
		border-radius: var(--btn-sm-radius);
		font-size: var(--btn-sm-font-size);
		background: var(--input-bg, var(--panel-bg));
		color: var(--fg);
		border: 1px solid var(--border);
	}
	.ghost-btn {
		padding: var(--btn-sm-padding);
		border-radius: var(--btn-sm-radius);
		font-size: var(--btn-sm-font-size);
		background: var(--action-bg);
		color: var(--action-fg);
		border: 1px solid var(--border);
		cursor: pointer;
	}
	.ghost-btn:hover:not(:disabled) { background: var(--action-hover); }
	.accent-btn {
		padding: var(--btn-sm-padding);
		border-radius: var(--btn-sm-radius);
		font-size: var(--btn-sm-font-size);
		background: var(--accent);
		color: var(--accent-fg);
		border: 1px solid transparent;
		cursor: pointer;
	}
	.ghost-btn:disabled, .accent-btn:disabled { opacity: 0.55; cursor: default; }
</style>

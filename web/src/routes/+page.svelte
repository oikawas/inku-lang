<script module lang="ts">
	declare const __BUILD_NUMBER__: string;
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { SAIJIKI } from '$lib/saijiki';
	import { annotate } from '$lib/highlight';
	import {
		PROVIDER_GROUPS,
		DEFAULT_PROVIDER,
		DEFAULT_MODEL,
		modelsForProvider,
		type Provider
	} from '$lib/models';
	import { t, setLang, getLang, PACK_LIST, initLang } from '$lib/i18n/index.svelte';
	import { COLOR_CATALOGS, getCatalogById, getRenderColorMap, type RenderColorMap } from '$lib/colors';

	const HISTORY_MANAGER_PAGE_SIZE = 100;
	const PROVIDER_STAGE1_KEY = 'inku-provider-stage1';
	const MODEL_STAGE1_KEY    = 'inku-model-stage1';
	const PROVIDER_STAGE2_KEY = 'inku-provider-stage2';
	const MODEL_STAGE2_KEY    = 'inku-model-stage2';
	const CATALOG_KEY         = 'inku-color-catalog';
	const SHOW_BIRDS_KEY      = 'inku-show-birds';
	const PNG_ALPHA_KEY       = 'inku-png-alpha-white';
	const SAVE_REPLAY_KEY     = 'inku-save-replay-history';
	const AUTH_TOKEN_KEY      = 'inku-auth-token';
	const BATCH_FAILURE_REPORT_KEY = 'inku-batch-failure-report';
	const BATCH_FAILURE_REPORT_MAX_ITEMS = 100;
	const BATCH_FAILURE_REPORT_MAX_TEXT = 300;

	type Score = { instructions: unknown[] };

	type PaintResult = {
		svg: string;
		score: Score;
		elapsed_stage1_ms: number;
		elapsed_stage2_ms: number;
		elapsed_total_ms: number;
		tokens_in_stage1: number | null;
		tokens_out_stage1: number | null;
		tokens_in_stage2: number | null;
		tokens_out_stage2: number | null;
	};

	type Iteration = {
		id?: string;
		input: string;
		ddl: string | null;
		thinking?: string | null;
		score: Score;
		svg: string;
		at: number;
		elapsed_ms?: number;
		stage1_model?: string | null;
		stage2_model?: string | null;
		tokens_in?: number | null;
		tokens_out?: number | null;
		catalog_id?: string | null;
		trashed?: boolean;
	};
	type BatchFailure = {
		line: number;
		input: string;
		message: string;
	};
	type BatchFailureReport = {
		success: number;
		total: number;
		failures: BatchFailure[];
	};

	type PluginItem = {
		name: string;
		version: string;
		status: string;
	};
	type SettingsStatus = {
		database: {
			backend: string;
			driver: string;
			url: string;
			database: string | null;
			is_default: boolean;
			runtime_editable: boolean;
			note: string;
		};
		plugins: {
			enabled: boolean;
			loaded: PluginItem[];
			runtime_editable: boolean;
			note: string;
		};
	};

	type UserRole = 'admin' | 'group_lead' | 'user';
	type UserGroup = {
		id: string;
		name: string;
		at: number;
	};
	type UserItem = {
		id: string;
		username: string;
		email: string;
		role: UserRole;
		role_label: string;
		group_id: string | null;
		group_name: string | null;
		at: number;
	};
	const USER_ROLE_OPTIONS: { value: UserRole; label: string }[] = [
		{ value: 'admin', label: '管理者' },
		{ value: 'group_lead', label: 'グループリード' },
		{ value: 'user', label: 'ユーザー' },
	];
	function userRoleLabel(role: UserRole) {
		if (role === 'admin') return t().userRoleAdmin;
		if (role === 'group_lead') return t().userRoleGroupLead;
		return t().userRoleUser;
	}

	// ── Input ───────────────────────────────────────────────
	let inputMode   = $state<'single' | 'batch'>('single');
	let input       = $state('山の向こうに月が昇る');
	let batchInput  = $state('');
	let stage1UserPrompt = $state('');
	let textareaEl  = $state<HTMLTextAreaElement | null>(null);

	// ── Loading ─────────────────────────────────────────────
	let loading    = $state(false);
	let stageLabel = $state('');
	let batchCurrent = $state(0);
	let batchTotal   = $state(0);
	let batchSuccess = $state(0);
	let batchFailures = $state<BatchFailure[]>([]);
	let batchFailureReport = $state<BatchFailureReport | null>(null);
	let error        = $state<string | null>(null);

	// ── Replay ──────────────────────────────────────────────
	let reloading   = $state(false);
	let reloadError = $state<string | null>(null);

	// ── Result ──────────────────────────────────────────────
	let ddl      = $state<string | null>(null);
	let thinking = $state<string | null>(null);
	let result   = $state<PaintResult | null>(null);

	// ── UI ──────────────────────────────────────────────────
	let windowWidth  = $state(1200);
	let saijikiOpen  = $state(false);
	let settingsOpen = $state(false);
	let settingsMode = $state<'model' | 'settings'>('settings');
	let settingsTab  = $state<'connection' | 'db' | 'plugins' | 'users' | 'misc'>('connection');
	let pngMenuOpen  = $state(false);
	let catalogOpen  = $state(false);
	let statsOpen    = $state(false);
	let outputTab    = $state<'canvas' | 'prompts' | 'score'>('canvas');
	let ddlEditing   = $state(false);
	let baseDDL      = $state<string | null>(null);
	let zoom         = $state(1);
	let panX         = $state(0);
	let panY         = $state(0);
	let canvasDragging = $state(false);
	let dragStartX   = 0;
	let dragStartY   = 0;
	let dragStartPanX = 0;
	let dragStartPanY = 0;
	let promptStage1Expanded = $state(false);
	let promptStage2Expanded = $state(false);
	let showBirds = $state(true);
	let pngAlphaWhite = $state(false);
	let saveReplayAsNewVersion = $state(true);
	let miscSettingsLoaded = $state(false);

	// DOM refs for outside-click handling
	let pngWrapEl      = $state<HTMLDivElement | null>(null);

	// ── Color catalog ────────────────────────────────────────
	let selectedCatalog = $state('default');
	const currentCatalog = $derived(getCatalogById(selectedCatalog) ?? COLOR_CATALOGS[0]);

	function activeColorMap(): RenderColorMap | null {
		if (selectedCatalog === 'default') return null;
		return getRenderColorMap(selectedCatalog);
	}

	function isLightColor(hex: string): boolean {
		const value = hex.replace('#', '');
		const r = parseInt(value.slice(0, 2), 16);
		const g = parseInt(value.slice(2, 4), 16);
		const b = parseInt(value.slice(4, 6), 16);
		return (r * 299 + g * 587 + b * 114) / 1000 > 224;
	}

	// ── Settings tabs ────────────────────────────────────────
	let settingsStatus = $state<SettingsStatus | null>(null);
	let settingsStatusError = $state<string | null>(null);
	let settingsStatusLoading = $state(false);
	let users = $state<UserItem[]>([]);
	let groups = $state<UserGroup[]>([]);
	let newUserName = $state('');
	let newUserEmail = $state('');
	let newUserPassword = $state('');
	let newUserRole = $state<UserRole>('user');
	let newUserGroupId = $state('');
	let selectedUserId = $state<string | null>(null);
	let editUserName = $state('');
	let editUserEmail = $state('');
	let editUserPassword = $state('');
	let editUserRole = $state<UserRole>('user');
	let editUserGroupId = $state('');
	let newGroupName = $state('');
	let userSettingsStatus = $state<string | null>(null);
	let authToken = $state<string | null>(null);
	let currentUser = $state<UserItem | null>(null);
	let loginUserName = $state('admin');
	let loginPassword = $state('');
	let loginPasswordVisible = $state(false);
	let loginStatus = $state<string | null>(null);

	function apiFetch(path: string, init: RequestInit = {}) {
		const headers = new Headers(init.headers);
		if (authToken) headers.set('Authorization', `Bearer ${authToken}`);
		return fetch(path, { ...init, headers });
	}

	function openSettings(tab: typeof settingsTab = 'db') {
		settingsMode = 'settings';
		settingsTab = tab;
		settingsOpen = true;
		if (tab === 'db' || tab === 'plugins') void loadSettingsStatus();
	}

	function selectSettingsTab(tab: typeof settingsTab) {
		settingsTab = tab;
		if (tab === 'db' || tab === 'plugins') void loadSettingsStatus();
	}

	async function loadUserSettings() {
		if (!currentUser || !['admin', 'group_lead'].includes(currentUser.role)) return;
		try {
			const [groupsResponse, usersResponse] = await Promise.all([
				apiFetch('/api/user-groups'),
				apiFetch('/api/users'),
			]);
			if (!groupsResponse.ok || !usersResponse.ok) throw new Error(t().userInfoLoadFailed);
			groups = await groupsResponse.json();
			users = await usersResponse.json();
			if (!newUserGroupId && groups[0]) newUserGroupId = groups[0].id;
			if (selectedUserId) {
				const selected = users.find((user) => user.id === selectedUserId);
				if (selected) setEditUser(selected);
				else clearEditUser();
			}
			userSettingsStatus = null;
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	async function loadSettingsStatus() {
		if (!currentUser || currentUser.role !== 'admin') {
			settingsStatus = null;
			settingsStatusError = currentUser
				? t().settingsAdminOnlyMessage
				: t().loginRequiredMessage;
			return;
		}
		settingsStatusLoading = true;
		try {
			const r = await apiFetch('/api/settings/status');
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			settingsStatus = await r.json();
			settingsStatusError = null;
		} catch (e) {
			settingsStatus = null;
			settingsStatusError = e instanceof Error ? e.message : String(e);
		} finally {
			settingsStatusLoading = false;
		}
	}

	async function loadCurrentUser() {
		if (!authToken) {
			return;
		}
		try {
			const r = await apiFetch('/api/auth/me');
			if (!r.ok) throw new Error('session expired');
			currentUser = await r.json();
			loginStatus = null;
			await Promise.all([loadUserSettings(), loadSettingsStatus()]);
			await Promise.all([fetchHistoryPage(0), fetchTrashPage()]);
			if (historyItems.length > 0) loadIteration(0);
		} catch {
			authToken = null;
			currentUser = null;
			loginStatus = t().loginRequiredMessage;
			settingsStatus = null;
			settingsStatusError = t().loginRequiredMessage;
			historyItems = [];
			historyTotal = 0;
			trashItems = [];
			trashTotal = 0;
			try { localStorage.removeItem(AUTH_TOKEN_KEY); } catch {}
		}
	}

	async function login() {
		loginStatus = null;
		try {
			const r = await fetch('/api/auth/login', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ username: loginUserName, password: loginPassword })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const data = await r.json() as { token: string; user: UserItem };
			authToken = data.token;
			currentUser = data.user;
			loginStatus = null;
			historyItems = [];
			historyTotal = 0;
			trashItems = [];
			trashTotal = 0;
			managerHistoryItems = [];
			managerHistoryTotal = 0;
			managerTrashItems = [];
			managerTrashTotal = 0;
			loginPassword = '';
			try { localStorage.setItem(AUTH_TOKEN_KEY, authToken); } catch {}
			await Promise.all([loadUserSettings(), loadSettingsStatus()]);
			await Promise.all([fetchHistoryPage(0), fetchTrashPage()]);
			if (historyItems.length > 0) loadIteration(0);
		} catch (e) {
			const message = e instanceof Error ? e.message : String(e);
			loginStatus = message;
			userSettingsStatus = message;
		}
	}

	async function logout() {
		if (authToken) {
			try { await apiFetch('/api/auth/logout', { method: 'POST' }); } catch {}
		}
		authToken = null;
		currentUser = null;
		loginStatus = null;
		settingsStatus = null;
		settingsStatusError = t().loginRequiredMessage;
		users = [];
		groups = [];
		historyItems = [];
		historyTotal = 0;
		trashItems = [];
		trashTotal = 0;
		managerHistoryItems = [];
		managerHistoryTotal = 0;
		managerTrashItems = [];
		managerTrashTotal = 0;
		try { localStorage.removeItem(AUTH_TOKEN_KEY); } catch {}
	}

	async function addUser() {
		const name = newUserName.trim();
		const email = newUserEmail.trim();
		if (currentUser?.role === 'group_lead') {
			newUserRole = 'user';
			newUserGroupId = currentUser.group_id ?? '';
		}
		if (!name || !email || newUserPassword.length < 8) {
			userSettingsStatus = t().userValidationCreate;
			return;
		}
		try {
			const r = await apiFetch('/api/users', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ username: name, email, password: newUserPassword, role: newUserRole, group_id: newUserGroupId || null })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			newUserName = '';
			newUserEmail = '';
			newUserPassword = '';
			newUserRole = 'user';
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	async function updateUser(user: UserItem, patch: Partial<UserItem> & { password?: string }) {
		try {
			const r = await apiFetch(`/api/users/${user.id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(patch)
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
			await loadUserSettings();
		}
	}

	function setEditUser(user: UserItem) {
		selectedUserId = user.id;
		editUserName = user.username;
		editUserEmail = user.email;
		editUserPassword = '';
		editUserRole = user.role;
		editUserGroupId = user.group_id ?? '';
	}

	function clearEditUser() {
		selectedUserId = null;
		editUserName = '';
		editUserEmail = '';
		editUserPassword = '';
		editUserRole = 'user';
		editUserGroupId = '';
	}

	async function saveUserEdit() {
		const user = users.find((item) => item.id === selectedUserId);
		if (!user) return;
		const username = editUserName.trim();
		const email = editUserEmail.trim();
		if (!username || !email) {
			userSettingsStatus = t().userValidationUpdate;
			return;
		}
		if (editUserPassword && editUserPassword.length < 8) {
			userSettingsStatus = t().userPasswordTooShort;
			return;
		}
		const patch: Partial<UserItem> & { password?: string } = {
			username,
			email,
			role: currentUser?.role === 'group_lead' ? 'user' : editUserRole,
			group_id: currentUser?.role === 'group_lead' ? currentUser.group_id : (editUserGroupId || null),
		};
		if (editUserPassword) patch.password = editUserPassword;
		await updateUser(user, patch);
	}

	async function removeUser(id: string) {
		try {
			const r = await apiFetch(`/api/users/${id}`, { method: 'DELETE' });
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			if (selectedUserId === id) clearEditUser();
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	async function addGroup() {
		const name = newGroupName.trim();
		if (!name) return;
		try {
			const r = await apiFetch('/api/user-groups', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			newGroupName = '';
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	async function removeGroup(group: UserGroup) {
		try {
			const r = await apiFetch(`/api/user-groups/${group.id}`, { method: 'DELETE' });
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	function persistMiscSettings() {
		try {
			localStorage.setItem(SHOW_BIRDS_KEY, showBirds ? '1' : '0');
			localStorage.setItem(PNG_ALPHA_KEY, pngAlphaWhite ? '1' : '0');
			localStorage.setItem(SAVE_REPLAY_KEY, saveReplayAsNewVersion ? '1' : '0');
		} catch {}
	}

	// ── 感情語 → DDL ヒント ──────────────────────────────────
	const EMOTION_DDL_MAP: Record<string, string> = {
		'美しい':  '線は細く(pencil)、揺らぎは小さく(fine)、動きはゆっくり(slow)',
		'美しく':  '線は細く(pencil)、揺らぎは小さく(fine)、動きはゆっくり(slow)',
		'激しい':  '線は太く(brush_thick)、揺らぎは大きく(broad)、動きは速く(high)',
		'激しく':  '線は太く(brush_thick)、揺らぎは大きく(broad)、動きは速く(high)',
		'静かな':  '揺らぎなし(none)、線は細く(hair)、密度を低く',
		'静かに':  '揺らぎなし(none)、線は細く(hair)、密度を低く',
		'素敵':    '線は細く(pen)、揺らぎは小さく(fine)、配置は整然と',
		'きれい':  '線は細く(pencil)、揺らぎは小さく(fine)、密度を低く',
		'やさしい':'揺らぎは波(wave)、振幅は小さく(fine)、線は細く(pencil)',
		'切ない':  '色は青(blue)か灰(gray)、線は細く(hair)、揺らぎはゆっくり(slow)',
		'哀しい':  '色は青(blue)、線は細く(hair)、要素数は少なく',
		'儚い':    '線は最細(hair)、破線か点線(dashed/dotted)、要素は散らす(scatter)',
		'神秘的':  '背景は黒(black)、円や弧を使う(circle/arc)、放射状(radial)',
		'幻想的':  '揺らぎはperlin、振幅は大きく(broad)、複数色(color_cycle)',
		'寂しい':  '要素数は少なく、間隔を広く、色は灰(gray)',
		'爽やか':  '色は青(blue)か白(white)背景、線は細く(pen)、揺らぎなし(none)',
	};

	function buildEmotionHint(text: string): string {
		const emotions = annotate(text).filter(p => p.kind === 'emotion').map(p => p.text);
		if (emotions.length === 0) return '';
		const hints = emotions.map(e => {
			const h = EMOTION_DDL_MAP[e];
			return h ? `「${e}」→ ${h}` : `「${e}」`;
		});
		return `\n\n[感情語をDDLに反映してください: ${hints.join('、')}]`;
	}

	// ── エクスポートファイル名 ────────────────────────────────
	function exportFilename(ext: string, size?: number): string {
		const now = new Date();
		const pad = (n: number) => String(n).padStart(2, '0');
		const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
		const time = `${pad(now.getHours())}-${pad(now.getMinutes())}`;
		const sizeStr = size != null ? `-${size}` : '';
		return `inku-${date}-${time}${sizeStr}.${ext}`;
	}

	// ── Models ──────────────────────────────────────────────
	let stage1Provider  = $state<Provider>(DEFAULT_PROVIDER);
	let stage1Model     = $state<string>(DEFAULT_MODEL);
	let stage2Provider  = $state<Provider>(DEFAULT_PROVIDER);
	let stage2Model     = $state<string>(DEFAULT_MODEL);
	let includeThinking = $state(false);

	// ── Timer ───────────────────────────────────────────────
	let elapsedStage1Ms = $state(0);
	let elapsedStage2Ms = $state(0);
	let elapsedTotalMs  = $state(0);
	let liveMs          = $state(0);
	let _timerStart     = 0;
	let _timerHandle: ReturnType<typeof setInterval> | null = null;

	// ── Tokens ──────────────────────────────────────────────
	let tokensInStage1  = $state<number | null>(null);
	let tokensOutStage1 = $state<number | null>(null);
	let tokensInStage2  = $state<number | null>(null);
	let tokensOutStage2 = $state<number | null>(null);

	// ── History ─────────────────────────────────────────────
	let historyItems = $state<Iteration[]>([]);
	let historyTotal = $state(0);
	let historyOffset = $state(0);
	let historyCursor = $state(-1);
	const visibleThumbCount = $derived(Math.max(1, Math.floor((windowWidth - 40) / 89)));
	const historyWindowSize = $derived(visibleThumbCount);
	const historyPage = $derived(Math.floor(historyOffset / historyWindowSize));
	const historyTotalPages = $derived(Math.max(1, Math.ceil(historyTotal / historyWindowSize)));
	let historyManagerOpen = $state(false);
	let historyManagerView = $state<'active' | 'trash'>('active');
	let historyManagerTab = $state<'thumbs' | 'list'>('thumbs');
	let historyManagerPage = $state(0);
	let historyManagerLoading = $state(false);
	let managerHistoryItems = $state<Iteration[]>([]);
	let managerHistoryTotal = $state(0);
	let managerTrashItems = $state<Iteration[]>([]);
	let managerTrashTotal = $state(0);
	let trashItems = $state<Iteration[]>([]);
	let trashTotal = $state(0);
	let historySearch = $state('');
	let selectedHistoryIds = $state<string[]>([]);
	let confirmAction = $state<{ message: string; run: () => void; destructive?: boolean } | null>(null);
	const managedHistoryItems = $derived(historyManagerView === 'trash' ? managerTrashItems : managerHistoryItems);
	const managedHistoryTotal = $derived(historyManagerView === 'trash' ? managerTrashTotal : managerHistoryTotal);
	const historyManagerTotalPages = $derived(Math.max(1, Math.ceil(managedHistoryTotal / HISTORY_MANAGER_PAGE_SIZE)));
	const historyManagerOffset = $derived(historyManagerPage * HISTORY_MANAGER_PAGE_SIZE);
	const historyManagerShownTo = $derived(Math.min(historyManagerOffset + managedHistoryItems.length, managedHistoryTotal));

	let promptsData = $state<{ stage1_system: string; stage2_system: string } | null>(null);

	// ── Batch derived ────────────────────────────────────────
	const batchLines    = $derived(batchInput.split('\n'));
	const lineNumbersText = $derived(batchLines.map((_, i) => String(i + 1)).join('\n'));
	const batchNonEmpty = $derived(batchLines.filter((l) => l.trim()).length);
	const canSubmit     = $derived(
		inputMode === 'single' ? !!input.trim() : batchNonEmpty > 0
	);

	// ── Timer ───────────────────────────────────────────────
	function startTimer() {
		_timerStart = Date.now();
		liveMs = 0;
		_timerHandle = setInterval(() => { liveMs = Date.now() - _timerStart; }, 100);
	}
	function stopTimer() {
		if (_timerHandle !== null) { clearInterval(_timerHandle); _timerHandle = null; }
	}
	function compactBatchFailureReport(report: BatchFailureReport): BatchFailureReport {
		return {
			success: report.success,
			total: report.total,
			failures: report.failures.slice(0, BATCH_FAILURE_REPORT_MAX_ITEMS).map((failure) => ({
				line: failure.line,
				input: failure.input.slice(0, BATCH_FAILURE_REPORT_MAX_TEXT),
				message: failure.message.slice(0, BATCH_FAILURE_REPORT_MAX_TEXT),
			})),
		};
	}
	function setBatchFailureReport(report: BatchFailureReport | null) {
		const compactReport = report ? compactBatchFailureReport(report) : null;
		batchFailureReport = compactReport;
		try {
			if (compactReport) localStorage.setItem(BATCH_FAILURE_REPORT_KEY, JSON.stringify(compactReport));
			else localStorage.removeItem(BATCH_FAILURE_REPORT_KEY);
		} catch {
			try { localStorage.removeItem(BATCH_FAILURE_REPORT_KEY); } catch {}
		}
	}
	function loadBatchFailureReport(): BatchFailureReport | null {
		try {
			const raw = localStorage.getItem(BATCH_FAILURE_REPORT_KEY);
			if (!raw) return null;
			const report = JSON.parse(raw) as Partial<BatchFailureReport>;
			if (
				typeof report.success !== 'number' ||
				typeof report.total !== 'number' ||
				!Array.isArray(report.failures)
			) return null;
			const failures = report.failures
				.filter((failure): failure is BatchFailure =>
					typeof failure?.line === 'number' &&
					typeof failure.input === 'string' &&
					typeof failure.message === 'string'
				);
			if (failures.length === 0) return null;
			return compactBatchFailureReport({ success: report.success, total: report.total, failures });
		} catch {
			return null;
		}
	}

	// ── Core paint (2-stage) ─────────────────────────────────
	async function paintOne(text: string): Promise<{ ddl: string; thinking: string | null } & PaintResult> {
		const t0  = Date.now();
		const lang = getLang();
		stageLabel = t().stageInterpreting;

		const augmented = text + buildEmotionHint(text);
		stage1UserPrompt = augmented;
		const r1 = await fetch('/api/interpret', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ text: augmented, model: stage1Model, include_thinking: includeThinking, lang })
		});
		if (!r1.ok) {
			const d = await r1.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r1.status}`);
		}
		const d1 = await r1.json() as { ddl: string; thinking: string | null; tokens_in: number | null; tokens_out: number | null };
		const t1  = Date.now();
		const tokLabel = d1.tokens_in != null ? ` (${d1.tokens_in}→${d1.tokens_out ?? '?'}tok)` : '';

		stageLabel = t().stageStructuring(tokLabel);
		const r2 = await fetch('/api/compose', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ddl: d1.ddl, model: stage2Model, original_text: text, lang, color_map: activeColorMap() })
		});
		if (!r2.ok) {
			const d = await r2.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r2.status}`);
		}
		const d2 = await r2.json() as { score: Score; svg: string; tokens_in: number | null; tokens_out: number | null };
		const t2  = Date.now();

		return {
			ddl: d1.ddl, thinking: d1.thinking, score: d2.score, svg: d2.svg,
			elapsed_stage1_ms: t1 - t0, elapsed_stage2_ms: t2 - t1, elapsed_total_ms: t2 - t0,
			tokens_in_stage1: d1.tokens_in, tokens_out_stage1: d1.tokens_out,
			tokens_in_stage2: d2.tokens_in, tokens_out_stage2: d2.tokens_out,
		};
	}

	// ── Submit ──────────────────────────────────────────────
	async function submit() {
		if (!canSubmit || loading) return;
		loading = true; error = null;
		ddl = null; thinking = null; baseDDL = null; ddlEditing = false;
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		batchCurrent = 0;
		startTimer();

		try {
			if (inputMode === 'single') {
				const r = await paintOne(input);
				ddl = r.ddl; thinking = r.thinking; result = r; outputTab = 'canvas';
				elapsedStage1Ms = r.elapsed_stage1_ms; elapsedStage2Ms = r.elapsed_stage2_ms; elapsedTotalMs = r.elapsed_total_ms;
				tokensInStage1 = r.tokens_in_stage1; tokensOutStage1 = r.tokens_out_stage1;
				tokensInStage2 = r.tokens_in_stage2; tokensOutStage2 = r.tokens_out_stage2;
				const totalIn  = (r.tokens_in_stage1 ?? 0)  + (r.tokens_in_stage2 ?? 0);
				const totalOut = (r.tokens_out_stage1 ?? 0) + (r.tokens_out_stage2 ?? 0);
				await pushHistory({ input, ddl: r.ddl, thinking: r.thinking, score: r.score, svg: r.svg, at: Date.now(), elapsed_ms: r.elapsed_total_ms, stage1_model: stage1Model, stage2_model: stage2Model, tokens_in: totalIn || null, tokens_out: totalOut || null, catalog_id: selectedCatalog !== 'default' ? selectedCatalog : null });
			} else {
				batchTotal = 0; batchSuccess = 0; batchFailures = []; setBatchFailureReport(null);
				const lines = batchLines
					.map((line, index) => ({ line: index + 1, input: line.trim() }))
					.filter((item) => item.input);
				batchTotal = lines.length; outputTab = 'canvas';
				for (let i = 0; i < lines.length; i++) {
					if (!loading) break;
					batchCurrent = i + 1;
					try {
						const r = await paintOne(lines[i].input);
						result = r;
						ddl = r.ddl; thinking = r.thinking;
						const totalIn  = (r.tokens_in_stage1 ?? 0)  + (r.tokens_in_stage2 ?? 0);
						const totalOut = (r.tokens_out_stage1 ?? 0) + (r.tokens_out_stage2 ?? 0);
						await pushHistory({ input: `#${lines[i].line} ${lines[i].input}`, ddl: r.ddl, thinking: r.thinking, score: r.score, svg: r.svg, at: Date.now(), elapsed_ms: r.elapsed_total_ms, stage1_model: stage1Model, stage2_model: stage2Model, tokens_in: totalIn || null, tokens_out: totalOut || null, catalog_id: selectedCatalog !== 'default' ? selectedCatalog : null });
						batchSuccess += 1;
						if (batchFailures.length > 0) {
							setBatchFailureReport({ success: batchSuccess, total: batchTotal, failures: batchFailures });
						}
					} catch (e) {
						batchFailures = [
							...batchFailures,
							{
								line: lines[i].line,
								input: lines[i].input,
								message: e instanceof Error ? e.message : String(e),
							},
						];
						setBatchFailureReport({ success: batchSuccess, total: batchTotal, failures: batchFailures });
					}
				}
				elapsedTotalMs = Date.now() - _timerStart;
				if (batchFailures.length > 0) {
					setBatchFailureReport({
						success: batchSuccess,
						total: batchTotal,
						failures: batchFailures,
					});
				}
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e); result = null;
		} finally {
			stopTimer(); loading = false; stageLabel = ''; batchCurrent = 0;
		}
	}

	function stopBatch() { loading = false; }

	// ── Replay (Stage 2 のみ) ────────────────────────────────
	async function replay() {
		if (!ddl || reloading) return;
		reloading = true; reloadError = null;
		const lang = getLang();
		const startedAt = Date.now();
		try {
			const r = await fetch('/api/compose', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ddl, model: stage2Model, original_text: input, lang, color_map: activeColorMap() })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const d = await r.json() as { score: Score; svg: string; tokens_in: number | null; tokens_out: number | null };
			const elapsedMs = Date.now() - startedAt;
			result = result
				? { ...result, score: d.score, svg: d.svg }
				: { score: d.score, svg: d.svg, elapsed_stage1_ms: 0, elapsed_stage2_ms: elapsedMs, elapsed_total_ms: elapsedMs, tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: d.tokens_in, tokens_out_stage2: d.tokens_out };
			if (result) {
				result = { ...result, elapsed_stage2_ms: elapsedMs, elapsed_total_ms: elapsedMs, tokens_in_stage2: d.tokens_in, tokens_out_stage2: d.tokens_out };
			}
			if (saveReplayAsNewVersion) {
				await pushHistory({
					input,
					ddl,
					score: d.score,
					svg: d.svg,
					at: Date.now(),
					elapsed_ms: elapsedMs,
					stage1_model: stage1Model,
					stage2_model: stage2Model,
					tokens_in: d.tokens_in,
					tokens_out: d.tokens_out,
					catalog_id: selectedCatalog !== 'default' ? selectedCatalog : null
				});
			}
			outputTab = 'canvas';
		} catch (e) {
			reloadError = e instanceof Error ? e.message : String(e);
		} finally {
			reloading = false;
		}
	}

	// ── History ─────────────────────────────────────────────
	async function fetchHistoryOffset(offset: number): Promise<void> {
		if (!authToken) {
			historyItems = [];
			historyTotal = 0;
			historyOffset = 0;
			return;
		}
		const safeOffset = Math.max(0, offset);
		try {
			const r = await apiFetch(`/api/history?offset=${safeOffset}&limit=${historyWindowSize}`);
			if (!r.ok) return;
			const data = await r.json();
			if (data.items.length === 0 && data.total > 0 && safeOffset > 0) {
				const lastOffset = Math.floor((data.total - 1) / historyWindowSize) * historyWindowSize;
				await fetchHistoryOffset(lastOffset);
				return;
			}
			historyItems = data.items; historyTotal = data.total; historyOffset = safeOffset;
			if (historyCursor >= data.items.length) historyCursor = data.items.length > 0 ? 0 : -1;
			if (historyCursor < 0 && data.items.length > 0) historyCursor = 0;
		} catch { /* ignore */ }
	}

	async function fetchHistoryPage(page: number): Promise<void> {
		await fetchHistoryOffset(page * historyWindowSize);
	}

	async function fetchTrashPage(): Promise<void> {
		if (!authToken) {
			trashItems = [];
			trashTotal = 0;
			return;
		}
		try {
			const r = await apiFetch(`/api/history?offset=0&limit=100&trashed=true`);
			if (!r.ok) return;
			const data = await r.json();
			trashItems = data.items; trashTotal = data.total;
		} catch { /* ignore */ }
	}

	async function fetchHistoryManager(): Promise<void> {
		if (!authToken) return;
		historyManagerLoading = true;
		try {
			const trashed = historyManagerView === 'trash';
			const offset = historyManagerPage * HISTORY_MANAGER_PAGE_SIZE;
			const params = new URLSearchParams({
				offset: String(offset),
				limit: String(HISTORY_MANAGER_PAGE_SIZE),
				q: historySearch.trim(),
			});
			if (trashed) params.set('trashed', 'true');
			const r = await apiFetch(`/api/history?${params.toString()}`);
			if (!r.ok) return;
			const data = await r.json();
			if (trashed) {
				managerTrashItems = data.items;
				managerTrashTotal = data.total;
				if (!historySearch.trim()) {
					trashItems = data.items.slice(0, 100);
					trashTotal = data.total;
				}
			} else {
				managerHistoryItems = data.items;
				managerHistoryTotal = data.total;
			}
			if (data.items.length === 0 && data.total > 0 && historyManagerPage > 0) {
				historyManagerPage -= 1;
				await fetchHistoryManager();
			}
		} catch { /* ignore */ }
		finally {
			historyManagerLoading = false;
		}
	}

	async function pushHistory(it: Iteration): Promise<void> {
		if (!authToken) return;
		try {
			await apiFetch('/api/history', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ input: it.input, ddl: it.ddl, score: it.score, svg: it.svg, at: it.at, elapsed_ms: it.elapsed_ms ?? 0, stage1_model: it.stage1_model ?? null, stage2_model: it.stage2_model ?? null, tokens_in: it.tokens_in ?? null, tokens_out: it.tokens_out ?? null, catalog_id: it.catalog_id ?? null })
			});
		} catch { /* ignore */ }
		await fetchHistoryOffset(0);
		historyCursor = 0;
	}

	function clearInput() {
		if (inputMode === 'single') input = ''; else batchInput = '';
	}

	function toggleHistorySelection(id: string) {
		selectedHistoryIds = selectedHistoryIds.includes(id)
			? selectedHistoryIds.filter((x) => x !== id)
			: [...selectedHistoryIds, id];
	}

	function selectAllManagedHistory() {
		const ids = managedHistoryItems.map((it) => it.id).filter((id): id is string => !!id);
		selectedHistoryIds = selectedHistoryIds.length === ids.length ? [] : ids;
	}

	async function postHistoryIds(path: string, ids: string[]) {
		if (!authToken) return;
		await apiFetch(path, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ids })
		});
		selectedHistoryIds = [];
		await Promise.all([fetchHistoryOffset(historyOffset), fetchTrashPage(), fetchHistoryManager()]);
		if (historyItems.length === 0 && historyOffset > 0) await fetchHistoryOffset(Math.max(0, historyOffset - historyWindowSize));
	}

	function askTrash(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: t().confirmTrashMessage(ids.length),
			run: () => { void postHistoryIds('/api/history/trash', ids); }
		};
	}

	function askRestore(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: t().confirmRestoreMessage(ids.length),
			run: () => { void postHistoryIds('/api/history/restore', ids); }
		};
	}

	function askPermanentDelete(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: t().confirmPermanentDeleteMessage(ids.length),
			destructive: true,
			run: () => { void postHistoryIds('/api/history/permanent-delete', ids); }
		};
	}

	type DiffPart = { text: string; changed: boolean };
	function diffDDL(base: string, current: string): DiffPart[] {
		const m = base.length, n = current.length;
		const dp: Uint16Array[] = Array.from({ length: m + 1 }, () => new Uint16Array(n + 1));
		for (let i = 1; i <= m; i++)
			for (let j = 1; j <= n; j++)
				dp[i][j] = base[i - 1] === current[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
		const chars: DiffPart[] = [];
		let i = m, j = n;
		while (i > 0 || j > 0) {
			if (i > 0 && j > 0 && base[i - 1] === current[j - 1]) { chars.push({ text: current[j - 1], changed: false }); i--; j--; }
			else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) { chars.push({ text: current[j - 1], changed: true }); j--; }
			else { i--; }
		}
		chars.reverse();
		const parts: DiffPart[] = [];
		for (const c of chars) {
			const last = parts[parts.length - 1];
			if (last && last.changed === c.changed) last.text += c.text;
			else parts.push({ text: c.text, changed: c.changed });
		}
		return parts;
	}

	function loadIteration(idx: number) {
		if (idx < 0 || idx >= historyItems.length) return;
		historyCursor = idx; ddlEditing = false;
		loadIterationItem(historyItems[idx]);
	}

	function loadIterationItem(it: Iteration) {
		inputMode = 'single';
		input = it.input; ddl = it.ddl; baseDDL = it.ddl; thinking = it.thinking ?? null;
		stage1UserPrompt = it.input ? it.input + buildEmotionHint(it.input) : '';
		result = { score: it.score, svg: it.svg, elapsed_stage1_ms: 0, elapsed_stage2_ms: 0, elapsed_total_ms: it.elapsed_ms ?? 0, tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: null, tokens_out_stage2: null };
		error = null;
	}

	const currentRenderedAt = $derived(
		historyCursor >= 0 && historyItems[historyCursor]
			? new Date(historyItems[historyCursor].at).toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US')
			: null
	);

	async function gotoPrev() {
		if (historyCursor < historyItems.length - 1) { loadIteration(historyCursor + 1); }
		else if (historyOffset + historyWindowSize < historyTotal) { await fetchHistoryOffset(historyOffset + historyWindowSize); loadIteration(0); }
	}
	async function gotoNext() {
		if (historyCursor > 0) { loadIteration(historyCursor - 1); }
		else if (historyOffset > 0) { await fetchHistoryOffset(Math.max(0, historyOffset - historyWindowSize)); loadIteration(historyItems.length - 1); }
	}

	const prevDisabled = $derived(historyCursor < 0 || historyOffset + historyCursor >= historyTotal - 1);
	const nextDisabled = $derived(historyCursor <= 0 && historyOffset <= 0);
	const navPos       = $derived(historyOffset + historyCursor + 1);

	// ── Saijiki ─────────────────────────────────────────────
	function insertWord(word: string) {
		if (inputMode === 'batch') { batchInput = batchInput ? batchInput + word : word; return; }
		const ta = textareaEl;
		if (!ta) { input = input + word; return; }
		const start = ta.selectionStart ?? input.length;
		const end   = ta.selectionEnd   ?? input.length;
		input = input.slice(0, start) + word + input.slice(end);
		requestAnimationFrame(() => {
			if (!textareaEl) return;
			textareaEl.focus();
			const pos = start + word.length;
			textareaEl.setSelectionRange(pos, pos);
		});
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') { saijikiOpen = false; settingsOpen = false; catalogOpen = false; historyManagerOpen = false; confirmAction = null; }
		if (!shouldIgnoreCanvasShortcut(e)) handleCanvasKeydown(e);
	}

	function shouldIgnoreCanvasShortcut(e: KeyboardEvent) {
		if (!currentUser || settingsOpen || catalogOpen || historyManagerOpen || confirmAction) return true;
		const target = e.target;
		if (!(target instanceof HTMLElement)) return false;
		if (target.isContentEditable) return true;
		return !!target.closest('input, textarea, select, [contenteditable="true"]');
	}

	function handleDocClick(e: MouseEvent) {
		if (pngMenuOpen  && pngWrapEl     && !pngWrapEl.contains(e.target as Node))      pngMenuOpen  = false;
	}

	// ── Model selection ─────────────────────────────────────
	function setStage1Provider(v: Provider) {
		stage1Provider = v; stage1Model = modelsForProvider(v)[0]?.id ?? stage1Model;
		try { localStorage.setItem(PROVIDER_STAGE1_KEY, v); localStorage.setItem(MODEL_STAGE1_KEY, stage1Model); } catch {}
	}
	function setStage1Model(v: string) {
		stage1Model = v; try { localStorage.setItem(MODEL_STAGE1_KEY, v); } catch {}
	}
	function setStage2Provider(v: Provider) {
		stage2Provider = v; stage2Model = modelsForProvider(v)[0]?.id ?? stage2Model;
		try { localStorage.setItem(PROVIDER_STAGE2_KEY, v); localStorage.setItem(MODEL_STAGE2_KEY, stage2Model); } catch {}
	}
	function setStage2Model(v: string) {
		stage2Model = v; try { localStorage.setItem(MODEL_STAGE2_KEY, v); } catch {}
	}

	// ── Download ────────────────────────────────────────────
	function escapeXml(s: string): string {
		return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
	}
	function triggerDownload(blob: Blob, filename: string) {
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
		URL.revokeObjectURL(url);
	}
	function downloadSVG() {
		if (!result) return;
		const desc = `<desc>${escapeXml(input)}</desc>`;
		const svg  = result.svg.replace(/(<svg[^>]*>)/, `$1${desc}`);
		triggerDownload(new Blob([svg], { type: 'image/svg+xml' }), exportFilename('svg'));
	}

	async function downloadPNG(size: number) {
		if (!result) return;
		let svg = result.svg.replace(/(<svg)([^>]*)/, (_: string, tag: string, attrs: string) => {
			const a = attrs.replace(/\s+width="[^"]*"/g, '').replace(/\s+height="[^"]*"/g, '');
			return `${tag}${a} width="${size}" height="${size}"`;
		});
		const blob = new Blob([svg], { type: 'image/svg+xml' });
		const url  = URL.createObjectURL(blob);
		try {
			await new Promise<void>((resolve, reject) => {
				const canvas = document.createElement('canvas');
				canvas.width = size; canvas.height = size;
				const ctx = canvas.getContext('2d')!;
				if (!pngAlphaWhite) {
					ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, size, size);
				}
				const img = new Image();
				img.onload = () => {
					ctx.drawImage(img, 0, 0, size, size);
					canvas.toBlob((b) => {
						if (!b) { reject(new Error('canvas error')); return; }
						triggerDownload(b, exportFilename('png', size)); resolve();
					}, 'image/png');
				};
				img.onerror = () => reject(new Error('svg load error'));
				img.src = url;
			});
		} finally { URL.revokeObjectURL(url); }
	}

	// ── Prompts ─────────────────────────────────────────────
	async function fetchPrompts(): Promise<void> {
		try { const r = await fetch(`/api/prompts?lang=${getLang()}`); if (r.ok) promptsData = await r.json(); } catch {}
	}

	function shortModel(m: string | null | undefined): string {
		if (!m) return '';
		if (m.includes('opus')) return 'opus';
		if (m.includes('haiku')) return 'haiku';
		if (m.includes('sonnet')) return 'sonnet';
		if (m.includes('qwen3')) return 'qwen3';
		if (m.includes('qwen')) return 'qwen';
		if (m.includes('gemma')) return 'gemma';
		return (m.split('/').pop() ?? m).slice(0, 8);
	}

	function catalogName(id: string | null | undefined): string {
		return getCatalogById(id ?? 'default')?.name ?? 'inku Default';
	}

	function formatHistoryDate(at: number): string {
		return new Date(at).toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US');
	}

	function formatElapsed(ms: number | null | undefined): string {
		return ms ? `${(ms / 1000).toFixed(1)}s` : '-';
	}

	function historyModelSummary(it: Iteration): string {
		const s1 = it.stage1_model ? shortModel(it.stage1_model) : '-';
		const s2 = it.stage2_model ? shortModel(it.stage2_model) : '-';
		return `${s1} → ${s2}`;
	}

	function historyTokenSummary(it: Iteration): string {
		if (it.tokens_in == null && it.tokens_out == null) return '-';
		return `${it.tokens_in ?? '?'} → ${it.tokens_out ?? '?'} tok`;
	}

	function historyPreviewText(text: string): string {
		return text.length > 42 ? `${text.slice(0, 42)}...` : text;
	}

	function historyIndexLabel(index: number): number {
		return historyOffset + index + 1;
	}

	function openHistoryManager() {
		historyManagerOpen = true;
		historyManagerView = 'active';
		historyManagerTab = 'thumbs';
		historyManagerPage = 0;
		historySearch = '';
		selectedHistoryIds = [];
		managerHistoryItems = historyItems;
		managerHistoryTotal = historyTotal;
		managerTrashItems = [];
		managerTrashTotal = trashTotal;
		void fetchHistoryManager();
	}

	function setHistoryManagerView(view: 'active' | 'trash') {
		historyManagerView = view;
		historyManagerPage = 0;
		selectedHistoryIds = [];
		void fetchHistoryManager();
	}

	function setHistoryManagerPage(page: number) {
		const nextPage = Math.max(0, Math.min(page, historyManagerTotalPages - 1));
		if (nextPage === historyManagerPage) return;
		historyManagerPage = nextPage;
		selectedHistoryIds = [];
		void fetchHistoryManager();
	}

	$effect(() => {
		const q = historySearch.trim();
		if (!historyManagerOpen) return;
		historyManagerView;
		const handle = setTimeout(() => {
			historyManagerPage = 0;
			selectedHistoryIds = [];
			void fetchHistoryManager();
		}, q ? 250 : 0);
		return () => clearTimeout(handle);
	});

	const tokenSummary = $derived.by(() =>
		t().tokenSummary(tokensInStage1, tokensOutStage1, tokensInStage2, tokensOutStage2)
	);
	const scoreJsonLines = $derived(
		result ? JSON.stringify(result.score, null, 2).split('\n') : []
	);
	const scoreJsonHighlightedLines = $derived(scoreJsonLines.map(highlightJsonLine));
	const scoreJsonHighlighted = $derived(scoreJsonHighlightedLines.join('\n'));

	function escapeHtml(value: string) {
		return value
			.replaceAll('&', '&amp;')
			.replaceAll('<', '&lt;')
			.replaceAll('>', '&gt;');
	}

	function highlightJsonLine(line: string) {
		return escapeHtml(line).replace(
			/("(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
			(match, _token, keySuffix) => {
				if (keySuffix) return `<span class="json-key">${match}</span>`;
				if (match.startsWith('"')) return `<span class="json-string">${match}</span>`;
				if (match === 'true' || match === 'false') return `<span class="json-bool">${match}</span>`;
				if (match === 'null') return `<span class="json-null">${match}</span>`;
				return `<span class="json-number">${match}</span>`;
			}
		);
	}

	function setZoom(nextZoom: number) {
		zoom = Math.max(0.5, Math.min(10, +nextZoom.toFixed(2)));
		if (zoom <= 1) {
			panX = 0;
			panY = 0;
		}
	}

	function resetZoom() {
		zoom = 1;
		panX = 0;
		panY = 0;
		canvasDragging = false;
	}

	function startCanvasDrag(event: PointerEvent) {
		if (outputTab !== 'canvas' || zoom <= 1 || event.button !== 0) return;
		canvasDragging = true;
		dragStartX = event.clientX;
		dragStartY = event.clientY;
		dragStartPanX = panX;
		dragStartPanY = panY;
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		event.preventDefault();
	}

	function moveCanvasDrag(event: PointerEvent) {
		if (!canvasDragging) return;
		panX = dragStartPanX + event.clientX - dragStartX;
		panY = dragStartPanY + event.clientY - dragStartY;
	}

	function endCanvasDrag(event: PointerEvent) {
		if (!canvasDragging) return;
		canvasDragging = false;
		const target = event.currentTarget as HTMLElement;
		if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId);
	}

	function handleCanvasKeydown(event: KeyboardEvent) {
		if (outputTab !== 'canvas') return;
		if (event.key === '+' || event.key === '=' || event.code === 'Equal' || event.code === 'NumpadAdd') {
			setZoom(zoom + 0.25);
			event.preventDefault();
			return;
		}
		if (event.key === '-' || event.key === '_' || event.code === 'Minus' || event.code === 'NumpadSubtract') {
			setZoom(zoom - 0.25);
			event.preventDefault();
			return;
		}
		if (event.key === '0' || event.code === 'Digit0' || event.code === 'Numpad0') {
			resetZoom();
			event.preventDefault();
			return;
		}
		if (zoom <= 1) return;
		const step = event.shiftKey ? 120 : 40;
		if (event.key === 'ArrowLeft') panX += step;
		else if (event.key === 'ArrowRight') panX -= step;
		else if (event.key === 'ArrowUp') panY += step;
		else if (event.key === 'ArrowDown') panY -= step;
		else return;
		event.preventDefault();
	}

	// ── Stats string ─────────────────────────────────────────
	const statsLine = $derived.by(() => {
		if (!result) return '';
		const s1 = (result.elapsed_stage1_ms / 1000).toFixed(1);
		const s2 = (result.elapsed_stage2_ms / 1000).toFixed(1);
		const total = (result.elapsed_total_ms / 1000).toFixed(1);
		if (result.elapsed_stage1_ms > 0) return `${t().statsInterp} ${s1}s + ${t().statsStruct} ${s2}s = ${total}s`;
		return `${total}s`;
	});

	const historyNavSpan = $derived(historyWindowSize);
	let lastHistoryWindowSize = 0;

	$effect(() => {
		const size = historyWindowSize;
		if (lastHistoryWindowSize === 0) {
			lastHistoryWindowSize = size;
			return;
		}
		if (size === lastHistoryWindowSize) return;
		lastHistoryWindowSize = size;
		if (!authToken || historyTotal <= 0) return;
		void fetchHistoryOffset(historyOffset);
	});

	// ── Mount ───────────────────────────────────────────────
	onMount(() => {
		windowWidth = window.innerWidth;
		function onResize() { windowWidth = window.innerWidth; }
		window.addEventListener('resize', onResize);
		document.addEventListener('keydown', handleKeydown, true);

		initLang();
		try {
			const p1 = localStorage.getItem(PROVIDER_STAGE1_KEY) as Provider | null; if (p1) stage1Provider = p1;
			const m1 = localStorage.getItem(MODEL_STAGE1_KEY); if (m1) stage1Model = m1;
			const p2 = localStorage.getItem(PROVIDER_STAGE2_KEY) as Provider | null; if (p2) stage2Provider = p2;
			const m2 = localStorage.getItem(MODEL_STAGE2_KEY); if (m2) stage2Model = m2;
			const cat = localStorage.getItem(CATALOG_KEY); if (cat) selectedCatalog = cat;
			const birds = localStorage.getItem(SHOW_BIRDS_KEY); if (birds !== null) showBirds = birds !== '0';
			const alpha = localStorage.getItem(PNG_ALPHA_KEY); if (alpha !== null) pngAlphaWhite = alpha === '1';
			const replay = localStorage.getItem(SAVE_REPLAY_KEY); if (replay !== null) saveReplayAsNewVersion = replay !== '0';
			const savedBatchFailureReport = loadBatchFailureReport();
			setBatchFailureReport(savedBatchFailureReport);
			authToken = localStorage.getItem(AUTH_TOKEN_KEY);
			miscSettingsLoaded = true;
		} catch {}
		void (async () => {
			await Promise.all([loadCurrentUser(), fetchPrompts()]);
		})();

		return () => {
			window.removeEventListener('resize', onResize);
			document.removeEventListener('keydown', handleKeydown, true);
		};
	});

	$effect(() => { const _lang = getLang(); fetchPrompts(); });
	$effect(() => {
		showBirds; pngAlphaWhite; saveReplayAsNewVersion;
		if (miscSettingsLoaded) persistMiscSettings();
	});
</script>

<svelte:window onclick={handleDocClick} />

<!-- ══════════════════════════════════════════════════════════ -->
<!--  ROOT                                                       -->
<!-- ══════════════════════════════════════════════════════════ -->
{#if !currentUser}
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
							onkeydown={(e) => { if (e.key === 'Enter') void login(); }}
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
					<button class="ghost-btn login-submit" onclick={login}>{t().loginSubmit}</button>
				</div>
			</div>
		</section>
	</main>
{:else}
<div class="root">

	<!-- ══ HEADER ══ -->
	<header class="header">
		<div class="logo-area">
			<div class="logo">inku</div>
			<div class="logo-sub">{t().subtitle}</div>
		</div>

		<div class="header-right">
			{#if currentUser}
				<div class="user-badge" title={currentUser.email || currentUser.username}>
					<span class="user-badge-name">{currentUser.username}</span>
				</div>
			{/if}

			<button
				class="settings-btn"
				class:active={settingsOpen}
				onclick={() => openSettings('db')}
			>⚙ {t().settingsButton}</button>

			<!-- Lang -->
			<div class="lang-switcher">
				{#each PACK_LIST as pack (pack.code)}
					<button class="lang-btn" class:active={getLang() === pack.code} onclick={() => setLang(pack.code)}>{pack.label}</button>
				{/each}
			</div>

			<!-- Build -->
			<span class="build-badge">Build {__BUILD_NUMBER__}</span>
		</div>
	</header>

	<!-- ══ BODY ══ -->
	<div class="body">
		<!-- ── LEFT PANEL ── -->
		<div class="left-panel">
			<!-- Input mode tabs -->
			<div class="panel-tabs">
				{#each [['single', t().modeSingle], ['batch', t().modeBatch]] as [mode, label] (mode)}
					<button class="panel-tab" class:active={inputMode === mode} onclick={() => (inputMode = mode as 'single' | 'batch')}>{label}</button>
				{/each}
			</div>

			<div class="panel-scroll">

				<!-- 指示 section -->
				<section class="panel-section">
					<div class="section-head">
						<span class="section-label">{t().inputSectionLabel}</span>
						<div class="section-actions">
							<button class="ghost-btn" onclick={() => { settingsMode = 'model'; settingsTab = 'connection'; settingsOpen = true; }}>{t().modelSelectButton}</button>
							<button class="ghost-btn" onclick={() => (catalogOpen = true)}>{t().colorCatalogButton}</button>
							<button class="ghost-btn create-btn" onclick={clearInput}>{t().clearInputBtn}</button>
						</div>
					</div>

					{#if inputMode === 'single'}
						<textarea
							bind:this={textareaEl}
							bind:value={input}
							rows="5"
							spellcheck="false"
							placeholder={t().inputPlaceholder}
							class="input-ta"
						></textarea>
					{:else}
						<div class="batch-wrap">
							<div class="line-nums" aria-hidden="true">{lineNumbersText}</div>
							<textarea class="batch-ta" bind:value={batchInput} rows="5" spellcheck="false" wrap="off" placeholder={t().batchPlaceholder}></textarea>
						</div>
						{#if batchNonEmpty > 0}<p class="batch-info">{t().batchCount(batchNonEmpty)}</p>{/if}
					{/if}

					<!-- 描画する / progress -->
					{#if loading && inputMode === 'single'}
						<div class="progress-wrap">
							<div class="progress-phases">
								{#each [{ key: '解釈', label: t().statsInterp }, { key: '構造化', label: t().statsStruct }] as ph, i (ph.key)}
									{#if i > 0}<span class="phase-sep">›</span>{/if}
									<span class="phase-item" class:phase-done={stageLabel.includes('構造化') && ph.key === '解釈'} class:phase-active={stageLabel.includes(ph.key) && !(stageLabel.includes('構造化') && ph.key === '解釈')}>
										{#if stageLabel.includes('構造化') && ph.key === '解釈'}<span class="phase-check">✓</span>{/if}
										{#if !(stageLabel.includes('構造化') && ph.key === '解釈') && stageLabel.includes(ph.key)}<span class="phase-dot"></span>{/if}
										{ph.label}
									</span>
								{/each}
							</div>
							<div class="progress-right">
								<span class="progress-time">{(liveMs / 1000).toFixed(1)}s</span>
								<button class="stop-sm" onclick={stopBatch}>{t().stopBtn}</button>
							</div>
						</div>
						<div
							class="progress-bar-track"
							style="--progress-target: {stageLabel.includes('構造化') ? '65%' : '30%'}"
						>
							<div class="progress-bar-fill"></div>
							{#if showBirds}
								<svg class="progress-bird" viewBox="0 0 52 44" aria-hidden="true">
									<g class="bird-peck">
										<ellipse class="bird-shadow" cx="26" cy="38" rx="12" ry="2.4" />
										<g class="bird-preen">
											<g class="bird-view bird-view-side">
												<path class="bird-tail" d="M33 25 Q43 24 47 19 Q44 29 34 30 Z" />
												<ellipse class="bird-body" cx="27" cy="25" rx="11" ry="8" />
												<path class="bird-wing" d="M24 23 Q31 15 37 24 Q31 30 25 29 Z" />
												<g class="bird-head">
													<circle class="bird-head-fill" cx="17" cy="19" r="5.8" />
													<path class="bird-beak" d="M11.5 19 L5 16.9 L5 21.1 Z" />
													<circle class="bird-eye" cx="15.4" cy="17.5" r="0.95" />
												</g>
											</g>
											<g class="bird-view bird-view-front">
												<ellipse class="bird-body" cx="26" cy="25.5" rx="9.2" ry="8.8" />
												<circle class="bird-head-fill" cx="26" cy="17" r="6.4" />
												<path class="bird-wing bird-wing-left" d="M18 24 Q13 25 11 30 Q18 31 22 27 Z" />
												<path class="bird-wing bird-wing-right" d="M34 24 Q39 25 41 30 Q34 31 30 27 Z" />
												<path class="bird-beak" d="M23 18.7 L26 22.4 L29 18.7 Z" />
												<circle class="bird-eye" cx="23.4" cy="16.3" r="0.9" />
												<circle class="bird-eye" cx="28.6" cy="16.3" r="0.9" />
											</g>
											<g class="bird-view bird-view-three">
												<path class="bird-tail" d="M33 25 Q41 23 44 18 Q43 27 35 30 Z" />
												<ellipse class="bird-body" cx="27" cy="25" rx="10" ry="8.5" />
												<path class="bird-wing" d="M24 23 Q30 17 36 24 Q31 29 25 29 Z" />
												<circle class="bird-head-fill" cx="20" cy="18" r="6.1" />
												<path class="bird-beak" d="M16 19 L9.8 17.2 L10.8 21.2 Z" />
												<circle class="bird-eye" cx="18.3" cy="16.5" r="0.95" />
											</g>
											<g class="bird-legs">
												<path class="bird-leg bird-leg-a" d="M22 32 L20 37" />
												<path class="bird-leg bird-leg-b" d="M30 32 L32 37" />
											</g>
										</g>
									</g>
								</svg>
							{/if}
						</div>
						<div class="progress-stage-text">{stageLabel}</div>
					{:else if loading && batchTotal > 0}
						<div class="batch-progress">
							<span>{t().batchProgress(batchCurrent, batchTotal)}</span>
							<span class="progress-time">{(liveMs / 1000).toFixed(1)}s</span>
							<button class="stop-sm" onclick={stopBatch}>{t().stopBtn}</button>
						</div>
					{:else}
						<button class="play-btn" onclick={submit} disabled={!canSubmit}>▶ <span>{t().submitBtn}</span></button>
					{/if}

					{#if error}<p class="error-text">{error}</p>{/if}
					{#if inputMode === 'batch' && batchFailureReport && !loading}
						<div class="batch-summary has-failures">
							<div class="batch-summary-line">{t().batchSummary(batchFailureReport.success, batchFailureReport.failures.length, batchFailureReport.total)}</div>
							<div class="batch-failure-title">{t().batchFailureTitle}</div>
							<ul class="batch-failure-list">
								{#each batchFailureReport.failures as failure (failure.line)}
									<li>
										<span class="batch-failure-line">{t().batchFailureLine(failure.line)}</span>
										<span class="batch-failure-input">{failure.input}</span>
										<span class="batch-failure-message">{failure.message}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				</section>

				<!-- thinking -->
				{#if thinking}
					<section class="panel-section">
						<details class="thinking-details">
							<summary>{t().thinkingLabel}</summary>
							<pre>{thinking}</pre>
						</details>
					</section>
				{/if}

				<!-- 解釈 (正規化DDL) -->
				{#if ddl !== null}
					<section class="panel-section">
						<div class="section-head">
							<span class="section-label">{t().ddlLabel}</span>
							<div class="section-actions">
								<button class="ghost-btn" onclick={() => (saijikiOpen = !saijikiOpen)}>{t().saijikiToggleBtn}</button>
								{#if historyCursor >= 0}
									<button class="ghost-btn" class:ghost-active={ddlEditing} onclick={() => (ddlEditing = !ddlEditing)}>{ddlEditing ? t().ddlDoneBtn : t().ddlEditBtn}</button>
								{/if}
							</div>
						</div>
						{#if ddlEditing}
							<textarea class="ddl-edit-ta" bind:value={ddl} rows="4" spellcheck="false"></textarea>
						{:else}
							<div class="annot-box ddl-box">
								{#if baseDDL !== null && baseDDL !== ddl}
									{#each diffDDL(baseDDL, ddl) as part, i (i)}<span class={part.changed ? 'tok tok-diff-added' : 'tok tok-plain'}>{part.text}</span>{/each}
								{:else}
									{#each annotate(ddl) as part, i (i)}
										{#if part.kind === 'saijiki'}<span class="tok tok-saijiki" title={part.category}>{part.text}</span>
										{:else if part.kind === 'emotion'}<span class="tok tok-emotion">{part.text}</span>
										{:else}<span class="tok tok-plain">{part.text}</span>{/if}
									{/each}
								{/if}
							</div>
						{/if}

						<!-- 描画（解釈から） progress -->
						{#if reloading}
							<div class="progress-wrap">
								<div class="progress-phases">
									<span class="phase-item phase-active"><span class="phase-dot"></span>{t().statsStruct}</span>
								</div>
								<div class="progress-right">
									<span class="progress-time">…</span>
								</div>
							</div>
							<div class="progress-bar-track" style="--progress-target: 55%">
								<div class="progress-bar-fill"></div>
								{#if showBirds}
									<svg class="progress-bird" viewBox="0 0 52 44" aria-hidden="true">
										<g class="bird-peck">
											<ellipse class="bird-shadow" cx="26" cy="38" rx="12" ry="2.4" />
											<g class="bird-preen">
												<g class="bird-view bird-view-side">
													<path class="bird-tail" d="M33 25 Q43 24 47 19 Q44 29 34 30 Z" />
													<ellipse class="bird-body" cx="27" cy="25" rx="11" ry="8" />
													<path class="bird-wing" d="M24 23 Q31 15 37 24 Q31 30 25 29 Z" />
													<g class="bird-head">
														<circle class="bird-head-fill" cx="17" cy="19" r="5.8" />
														<path class="bird-beak" d="M11.5 19 L5 16.9 L5 21.1 Z" />
														<circle class="bird-eye" cx="15.4" cy="17.5" r="0.95" />
													</g>
												</g>
												<g class="bird-view bird-view-front">
													<ellipse class="bird-body" cx="26" cy="25.5" rx="9.2" ry="8.8" />
													<circle class="bird-head-fill" cx="26" cy="17" r="6.4" />
													<path class="bird-wing bird-wing-left" d="M18 24 Q13 25 11 30 Q18 31 22 27 Z" />
													<path class="bird-wing bird-wing-right" d="M34 24 Q39 25 41 30 Q34 31 30 27 Z" />
													<path class="bird-beak" d="M23 18.7 L26 22.4 L29 18.7 Z" />
													<circle class="bird-eye" cx="23.4" cy="16.3" r="0.9" />
													<circle class="bird-eye" cx="28.6" cy="16.3" r="0.9" />
												</g>
												<g class="bird-view bird-view-three">
													<path class="bird-tail" d="M33 25 Q41 23 44 18 Q43 27 35 30 Z" />
													<ellipse class="bird-body" cx="27" cy="25" rx="10" ry="8.5" />
													<path class="bird-wing" d="M24 23 Q30 17 36 24 Q31 29 25 29 Z" />
													<circle class="bird-head-fill" cx="20" cy="18" r="6.1" />
													<path class="bird-beak" d="M16 19 L9.8 17.2 L10.8 21.2 Z" />
													<circle class="bird-eye" cx="18.3" cy="16.5" r="0.95" />
												</g>
												<g class="bird-legs">
													<path class="bird-leg bird-leg-a" d="M22 32 L20 37" />
													<path class="bird-leg bird-leg-b" d="M30 32 L32 37" />
												</g>
											</g>
										</g>
									</svg>
								{/if}
							</div>
						{/if}
						{#if reloadError}<p class="error-text">{reloadError}</p>{/if}

						<button
							class="replay-btn"
							onclick={replay}
							disabled={reloading || !ddl}
						>{t().replayFromDdlButton}</button>
					</section>
				{/if}

				<!-- 統計 -->
				{#if result && elapsedTotalMs > 0}
					<section class="panel-section stats-section">
						<button class="stats-toggle" onclick={() => (statsOpen = !statsOpen)}>
							<span class="stats-arrow" class:open={statsOpen}>▶</span>
							{statsLine}
						</button>
						{#if statsOpen}
							<div class="stats-detail">
								{#if elapsedStage1Ms > 0}
									<div class="stats-grid">
										<span class="stats-key">{t().statsInterp}</span><span>{(elapsedStage1Ms / 1000).toFixed(1)}s{tokensInStage1 != null ? ` — ${tokensInStage1}→${tokensOutStage1}tok` : ''}</span>
										<span class="stats-key">{t().statsStruct}</span><span>{(elapsedStage2Ms / 1000).toFixed(1)}s{tokensInStage2 != null ? ` — ${tokensInStage2}→${tokensOutStage2}tok` : ''}</span>
										<span class="stats-key">{t().statsTotal}</span><span class="stats-total">{(elapsedTotalMs / 1000).toFixed(1)}s</span>
									</div>
								{:else}
									<span>{(elapsedTotalMs / 1000).toFixed(1)}s</span>
								{/if}
							</div>
						{/if}
					</section>
				{/if}

			</div><!-- /panel-scroll -->
		</div><!-- /left-panel -->

		<!-- ── RIGHT PANEL ── -->
		<div class="right-panel">

			<!-- Tab bar -->
			<div class="right-tabs">
				<button class="rtab" class:active={outputTab === 'canvas'}  onclick={() => (outputTab = 'canvas')}>{t().tabCanvas}</button>
				<button class="rtab" class:active={outputTab === 'prompts'} onclick={() => (outputTab = 'prompts')} disabled={!result}>{t().tabPrompts}</button>
				<button class="rtab" class:active={outputTab === 'score'}   onclick={() => (outputTab = 'score')}   disabled={!result}>{t().tabScore}</button>
				<div class="rtab-spacer"></div>
				{#if currentRenderedAt}
					<span class="rendered-at">{currentRenderedAt}</span>
				{/if}
			</div>

			<!-- Canvas area -->
			<div class="canvas-area">

				<!-- Prev nav (newer items = left) -->
				<div class="nav-left">
					<button class="nav-circle" onclick={gotoNext} disabled={nextDisabled}>‹</button>
				</div>

				<!-- Content -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div
					class="canvas-content"
					class:can-pan={outputTab === 'canvas' && zoom > 1}
					class:dragging={canvasDragging}
					onpointerdown={startCanvasDrag}
					onpointermove={moveCanvasDrag}
					onpointerup={endCanvasDrag}
					onpointercancel={endCanvasDrag}
				>
					{#if outputTab === 'canvas'}
						<div class="canvas-pan" style="transform: translate3d({panX}px, {panY}px, 0);">
							<div
								class="canvas-box"
								style="transform: scale({zoom}); transform-origin: center center; transition: transform 0.15s;"
							>
								{#if result}
									{@html result.svg}
								{:else}
									<div class="canvas-placeholder">{t().canvasPlaceholder}</div>
								{/if}
							</div>
						</div>
					{:else if outputTab === 'prompts'}
						{#if promptsData}
							<div class="prompt-section">
								<p class="prompt-label">{t().promptStage1Input}</p>
								<textarea class="prompt-textarea prompt-user" readonly value={stage1UserPrompt || (inputMode === 'single' ? input : batchInput)}></textarea>
								<div class="prompt-collapsible-head">
									<p class="prompt-label">{t().promptStage1System}</p>
									<button class="ghost-btn" onclick={() => (promptStage1Expanded = !promptStage1Expanded)}>{promptStage1Expanded ? t().promptCollapse : t().promptExpand}</button>
								</div>
								<div class="prompt-collapse" class:expanded={promptStage1Expanded}>
									<textarea class="prompt-textarea prompt-system" readonly value={promptsData.stage1_system}></textarea>
									{#if !promptStage1Expanded}<div class="prompt-fade"></div>{/if}
								</div>
								{#if ddl}
									<p class="prompt-label">{t().promptStage2Input}</p>
									<textarea class="prompt-textarea prompt-user" readonly value={ddl}></textarea>
								{/if}
								<div class="prompt-collapsible-head">
									<p class="prompt-label">{t().promptStage2System}</p>
									<button class="ghost-btn" onclick={() => (promptStage2Expanded = !promptStage2Expanded)}>{promptStage2Expanded ? t().promptCollapse : t().promptExpand}</button>
								</div>
								<div class="prompt-collapse" class:expanded={promptStage2Expanded}>
									<textarea class="prompt-textarea prompt-system" readonly value={promptsData.stage2_system}></textarea>
									{#if !promptStage2Expanded}<div class="prompt-fade"></div>{/if}
								</div>
							</div>
						{:else}
							<p class="muted-center">{t().promptLoading}</p>
						{/if}
					{:else if outputTab === 'score'}
						<div class="score-view">
							<div class="score-line-nums" aria-hidden="true">
								{#each scoreJsonLines as _, i (i)}
									<div>{i + 1}</div>
								{/each}
							</div>
							<pre class="score-pre">{@html scoreJsonHighlighted}</pre>
						</div>
					{/if}
				</div>

				<!-- Zoom controls (canvas tab only) -->
				{#if outputTab === 'canvas'}
					<div class="zoom-controls">
						<button onclick={() => setZoom(zoom - 0.25)}>−</button>
						<span class="zoom-pct">{Math.round(zoom * 100)}%</span>
						<button onclick={() => setZoom(zoom + 0.25)}>＋</button>
						<button class="zoom-reset" onclick={resetZoom}>⊙</button>
					</div>
				{/if}

				<!-- Next nav (older items = right) -->
				<div class="nav-right">
					<button class="nav-circle" onclick={gotoPrev} disabled={prevDisabled}>›</button>
					{#if historyTotal > 0}
						<span class="nav-counter">{navPos} / {historyTotal}</span>
					{/if}
				</div>

			</div><!-- /canvas-area -->

			<!-- Export bar -->
			<div class="export-bar">
				<span class="export-label">{t().exportLabel}</span>
				<button class="ghost-btn" onclick={downloadSVG} disabled={!result}>↓ SVG</button>
				<div class="png-wrap" bind:this={pngWrapEl}>
					<button class="ghost-btn" onclick={(e) => { e.stopPropagation(); pngMenuOpen = !pngMenuOpen; }} disabled={!result}>↓ PNG ▾</button>
					{#if pngMenuOpen}
						<div class="png-menu" onclick={(e) => e.stopPropagation()}>
							{#each [[1080,t().pngStandard],[2160,t().pngHighRes],[1024,t().pngSquare],[2048,t().pngSquareHighRes]] as [size, label]}
								<button onclick={() => { downloadPNG(size as number); pngMenuOpen = false; }}>
									<span class="png-size">PNG {size}px</span>
									<span class="png-sub">{label}</span>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>

		</div><!-- /right-panel -->
	</div><!-- /body -->

	<!-- ══ HISTORY STRIP ══ -->
	{#if historyTotal > 0}
		<div class="history-strip">
			<div class="history-head">
				<button class="history-title-btn" onclick={openHistoryManager}>
					{t().historyTitle} <span class="history-count">({historyTotal})</span> ▸
				</button>
				<div class="history-page-nav">
					<button class="ghost-btn history-nav-btn" onclick={async () => { await fetchHistoryPage(historyPage - 1); loadIteration(0); }} disabled={historyPage <= 0}>{t().historyNewerPage(historyNavSpan)}</button>
					<span class="history-page-indicator">{historyPage + 1} / {historyTotalPages}</span>
					<button class="ghost-btn history-nav-btn" onclick={async () => { await fetchHistoryPage(historyPage + 1); loadIteration(0); }} disabled={historyPage >= historyTotalPages - 1}>{t().historyOlderPage(historyNavSpan)}</button>
				</div>
			</div>
			<div class="thumb-strip">
				{#each historyItems as it, i (it.id ?? it.at)}
					<button
						class="thumb"
						class:current={i === historyCursor}
						onclick={() => loadIteration(i)}
					>
						<div class="thumb-tooltip">
							<div class="tooltip-title">#{historyIndexLabel(i)}</div>
							<div class="tooltip-row"><span>{t().historyTooltipModel}</span><strong>{historyModelSummary(it)}</strong></div>
							<div class="tooltip-row"><span>{t().historyTooltipSavedAt}</span><strong>{formatHistoryDate(it.at)}</strong></div>
							<div class="tooltip-row"><span>{t().historyTooltipSeconds}</span><strong>{formatElapsed(it.elapsed_ms)}</strong></div>
							<div class="tooltip-row"><span>{t().historyTooltipColorCatalog}</span><strong>{catalogName(it.catalog_id)}</strong></div>
						</div>
						<div class="thumb-svg">{@html it.svg}</div>
						<div class="thumb-meta">
							<span class="thumb-time">{formatElapsed(it.elapsed_ms) !== '-' ? formatElapsed(it.elapsed_ms) : String(historyIndexLabel(i))}</span>
							{#if it.stage2_model}<span class="thumb-model">{shortModel(it.stage2_model)}</span>{/if}
						</div>
						{#if i === historyCursor}
							<div class="thumb-current-badge">{t().historyCurrentBadge}</div>
						{/if}
					</button>
				{/each}
			</div>
		</div>
	{/if}

</div><!-- /root -->

<!-- ══ SAIJIKI DRAWER (fixed right) ══ -->
<div class="saijiki-drawer" class:open={saijikiOpen} aria-hidden={!saijikiOpen}>
	<div class="saijiki-inner">
		<div class="saijiki-head">
			<div>
				<div class="saijiki-title">{t().saijikiTitle}</div>
				<div class="saijiki-hint">{t().saijikiHint}</div>
			</div>
			<button class="saijiki-close" onclick={() => (saijikiOpen = false)} aria-label={t().closeLabel}>×</button>
		</div>
		<div class="saijiki-body">
			{#each SAIJIKI as cat, ci (cat.key)}
				{@const words = t().saijikiWords[cat.key] ?? cat.words}
				<div class="saijiki-cat" style="border-bottom: {ci < SAIJIKI.length - 1 ? '1px solid var(--border)' : 'none'}">
					<div class="saijiki-cat-head">
						<span class="saijiki-cat-ja">{cat.label}</span>
						<span class="saijiki-cat-en">{cat.en}</span>
					</div>
					<div class="saijiki-chips">
						{#each words as word (word)}
							<button class="saijiki-chip" onclick={() => insertWord(word)}>{word}</button>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	</div>
</div>

<!-- ══ SETTINGS MODAL ══ -->
{#if settingsOpen}
	<div class="modal-backdrop" onclick={() => (settingsOpen = false)} aria-hidden="true"></div>
	<div class="settings-modal" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()}>
		<div class="modal-head">
			<div class="catalog-modal-title">{settingsMode === 'model' ? t().modelSelectButton : t().settingsTitle}</div>
			<button class="catalog-close" onclick={() => (settingsOpen = false)}>×</button>
		</div>
		{#if settingsMode === 'settings'}
			<div class="settings-tabs">
				<button class:active={settingsTab === 'db'} onclick={() => selectSettingsTab('db')}>{t().settingsTabDb}</button>
				<button class:active={settingsTab === 'plugins'} onclick={() => selectSettingsTab('plugins')}>{t().settingsTabPlugins}</button>
				<button class:active={settingsTab === 'users'} onclick={() => selectSettingsTab('users')}>{t().settingsTabUsers}</button>
				<button class:active={settingsTab === 'misc'} onclick={() => selectSettingsTab('misc')}>{t().settingsTabMisc}</button>
			</div>
		{/if}
		<div class="settings-body">
			{#if settingsMode === 'model'}
				<div class="popover-group">
					<div class="popover-group-label">{t().stage1Label}</div>
					<div class="form-row">
						<label>{t().providerLabel}</label>
						<select value={stage1Provider} onchange={(e) => setStage1Provider((e.currentTarget as HTMLSelectElement).value as Provider)}>
							{#each PROVIDER_GROUPS as pg (pg.id)}<option value={pg.id}>{pg.label}</option>{/each}
						</select>
					</div>
					<div class="form-row">
						<label>{t().modelLabel}</label>
						<select value={stage1Model} onchange={(e) => setStage1Model((e.currentTarget as HTMLSelectElement).value)}>
							{#each modelsForProvider(stage1Provider) as m (m.id)}<option value={m.id}>{m.label}{m.notes ? ` — ${m.notes}` : ''}</option>{/each}
						</select>
					</div>
					{#if stage1Model.includes('qwen3')}
						<label class="check-row">
							<input type="checkbox" bind:checked={includeThinking} />
							<span>{t().showThinkingLabel}</span>
						</label>
					{/if}
				</div>
				<div class="popover-group">
					<div class="popover-group-label">{t().stage2Label}</div>
					<div class="form-row">
						<label>{t().providerLabel}</label>
						<select value={stage2Provider} onchange={(e) => setStage2Provider((e.currentTarget as HTMLSelectElement).value as Provider)}>
							{#each PROVIDER_GROUPS as pg (pg.id)}<option value={pg.id}>{pg.label}</option>{/each}
						</select>
					</div>
					<div class="form-row">
						<label>{t().modelLabel}</label>
						<select value={stage2Model} onchange={(e) => setStage2Model((e.currentTarget as HTMLSelectElement).value)}>
							{#each modelsForProvider(stage2Provider) as m (m.id)}<option value={m.id}>{m.label}{m.notes ? ` — ${m.notes}` : ''}</option>{/each}
						</select>
					</div>
				</div>
			{:else if settingsTab === 'db'}
				<div class="popover-group">
					<div class="popover-group-label">{t().settingsCurrentDb}</div>
					{#if settingsStatusLoading}
						<div class="inline-message">{t().settingsLoading}</div>
					{:else if settingsStatus}
						<div class="settings-readonly-grid">
							<span>Backend</span><strong>{settingsStatus.database.backend}</strong>
							<span>Driver</span><strong>{settingsStatus.database.driver}</strong>
							<span>URL</span><code>{settingsStatus.database.url}</code>
							<span>Database</span><strong>{settingsStatus.database.database ?? '-'}</strong>
							<span>Default</span><strong>{settingsStatus.database.is_default ? t().settingsYes : t().settingsNo}</strong>
						</div>
						<div class="db-test-result">{settingsStatus.database.note}</div>
					{:else}
						<div class="inline-message">{settingsStatusError ?? t().settingsLoadFailed}</div>
					{/if}
				</div>
				<div class="settings-inline-actions">
					<button class="ghost-btn" onclick={loadSettingsStatus} disabled={settingsStatusLoading || currentUser?.role !== 'admin'}>{t().settingsReload}</button>
				</div>
			{:else if settingsTab === 'plugins'}
				<div class="popover-group">
					<div class="popover-group-label">{t().settingsPluginsStatus}</div>
					{#if settingsStatusLoading}
						<div class="inline-message">{t().settingsLoading}</div>
					{:else if settingsStatus}
						<div class="settings-readonly-grid">
							<span>Loader</span><strong>{settingsStatus.plugins.enabled ? t().settingsYes : t().settingsUnavailable}</strong>
							<span>Runtime edit</span><strong>{settingsStatus.plugins.runtime_editable ? t().settingsYes : t().settingsUnavailable}</strong>
						</div>
						{#if settingsStatus.plugins.loaded.length > 0}
							<div class="plugin-list">
								{#each settingsStatus.plugins.loaded as plugin (plugin.name)}
									<div class="plugin-row">
										<span>{plugin.name}</span>
										<span class="plugin-version">{plugin.version}</span>
										<span class="plugin-version">{plugin.status}</span>
									</div>
								{/each}
							</div>
						{:else}
							<div class="inline-message">{t().settingsPluginsEmpty}</div>
						{/if}
						<div class="db-test-result">{settingsStatus.plugins.note}</div>
					{:else}
						<div class="inline-message">{settingsStatusError ?? t().settingsLoadFailed}</div>
					{/if}
				</div>
				<div class="settings-inline-actions">
					<button class="ghost-btn" onclick={loadSettingsStatus} disabled={settingsStatusLoading || currentUser?.role !== 'admin'}>{t().settingsReload}</button>
				</div>
			{:else if settingsTab === 'users'}
				<div class="popover-group">
					<div class="popover-group-label">{t().settingsUsersLabel}</div>
					{#if userSettingsStatus}
						<div class="inline-message">{userSettingsStatus}</div>
					{/if}
					{#if !currentUser}
						<div class="login-grid">
							<input bind:value={loginUserName} placeholder={t().userNamePlaceholder} />
							<input bind:value={loginPassword} type="password" placeholder={t().userPasswordPlaceholder} onkeydown={(e) => { if (e.key === 'Enter') void login(); }} />
							<button class="ghost-btn" onclick={login}>{t().loginSubmit}</button>
						</div>
						<div class="db-test-result">{t().bootstrapAdminNote}</div>
					{:else}
						<div class="user-session-row">
							<span>{currentUser.username} / {currentUser.role_label}{currentUser.group_name ? ` / ${currentUser.group_name}` : ''}</span>
							<button class="ghost-btn" onclick={logout}>{t().logoutButton}</button>
						</div>
						{#if currentUser.role === 'admin' || currentUser.role === 'group_lead'}
							<div class="user-editor-grid">
								<div class="user-editor-panel">
									<div class="user-editor-title">{t().userAddTitle}</div>
									<div class="user-form-grid">
										<input bind:value={newUserName} placeholder={t().userNamePlaceholder} />
										<input bind:value={newUserEmail} type="email" placeholder={t().userEmailPlaceholder} />
										<input bind:value={newUserPassword} type="password" placeholder={t().userPasswordPlaceholder} />
										<select bind:value={newUserRole} disabled={currentUser.role === 'group_lead'}>
											{#each USER_ROLE_OPTIONS as role (role.value)}
												<option value={role.value}>{userRoleLabel(role.value)}</option>
											{/each}
										</select>
										<select bind:value={newUserGroupId} disabled={currentUser.role === 'group_lead'}>
											<option value="">{t().userNoGroup}</option>
											{#each groups as group (group.id)}
												<option value={group.id}>{group.name}</option>
											{/each}
										</select>
									</div>
									<div class="user-form-actions">
										<button class="ghost-btn" onclick={addUser}>{t().userAddButton}</button>
									</div>
								</div>
								<div class="user-editor-panel">
									<div class="user-editor-title">{t().userEditTitle}</div>
									{#if selectedUserId}
										<div class="user-form-grid">
											<input bind:value={editUserName} placeholder={t().userNamePlaceholder} />
											<input bind:value={editUserEmail} type="email" placeholder={t().userEmailPlaceholder} />
											<input bind:value={editUserPassword} type="password" placeholder={t().userNewPasswordPlaceholder} />
											<select bind:value={editUserRole} disabled={currentUser.role === 'group_lead'}>
												{#each USER_ROLE_OPTIONS as role (role.value)}
													<option value={role.value}>{userRoleLabel(role.value)}</option>
												{/each}
											</select>
											<select bind:value={editUserGroupId} disabled={currentUser.role === 'group_lead'}>
												<option value="">{t().userNoGroup}</option>
												{#each groups as group (group.id)}
													<option value={group.id}>{group.name}</option>
												{/each}
											</select>
										</div>
										<div class="user-form-actions">
											<button class="ghost-btn" onclick={clearEditUser}>{t().userClearSelection}</button>
											<button class="ghost-btn primary-inline" onclick={saveUserEdit}>{t().userSaveChanges}</button>
										</div>
									{:else}
										<div class="inline-message">{t().userSelectPrompt}</div>
									{/if}
								</div>
							</div>
							<div class="user-list">
								{#each users as user (user.id)}
									<div class="user-row" class:selected={selectedUserId === user.id}>
										<button class="ghost-btn" onclick={() => setEditUser(user)}>{t().editButton}</button>
										<span class="user-cell user-name">{user.username}</span>
										<span class="user-cell">{user.email}</span>
										<span class="user-cell">{userRoleLabel(user.role)}</span>
										<span class="user-cell">{user.group_name ?? t().userNoGroup}</span>
										<button class="ghost-btn" onclick={() => removeUser(user.id)}>{t().deleteButton}</button>
									</div>
								{/each}
							</div>
						{:else}
							<div class="inline-message">{t().userManageUnavailable}</div>
						{/if}
					{/if}
				</div>
				{#if currentUser?.role === 'admin'}
					<div class="popover-group">
						<div class="popover-group-label">{t().userGroupLabel}</div>
						<div class="plugin-add">
							<input bind:value={newGroupName} placeholder={t().groupNamePlaceholder} />
							<button class="ghost-btn" onclick={addGroup}>{t().addButton}</button>
						</div>
						<div class="group-list">
							{#each groups as group (group.id)}
								<div class="group-row">
									<span>{group.name}</span>
									<button class="ghost-btn" onclick={() => removeGroup(group)}>{t().deleteButton}</button>
								</div>
							{/each}
						</div>
					</div>
				{/if}
			{:else}
				<div class="popover-group">
					<div class="popover-group-label">{t().settingsDisplayLabel}</div>
					<label class="setting-toggle">
						<input type="checkbox" bind:checked={showBirds} />
						<span>{t().settingsShowBirds}</span>
					</label>
				</div>
				<div class="popover-group">
					<div class="popover-group-label">{t().settingsExportLabel}</div>
					<label class="setting-toggle">
						<input type="checkbox" bind:checked={pngAlphaWhite} />
						<span>{t().settingsPngAlpha}</span>
					</label>
				</div>
				<div class="popover-group">
					<div class="popover-group-label">{t().settingsHistoryLabel}</div>
					<label class="setting-toggle">
						<input type="checkbox" bind:checked={saveReplayAsNewVersion} />
						<span>{t().settingsSaveReplay}</span>
					</label>
				</div>
			{/if}
		</div>
	</div>
{/if}

<!-- ══ CATALOG MODAL ══ -->
{#if catalogOpen}
	<div class="modal-backdrop" onclick={() => (catalogOpen = false)} aria-hidden="true"></div>
	<div class="catalog-modal" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()}>
		<div class="catalog-modal-head">
			<div class="catalog-modal-title">{t().colorCatalogTitle}</div>
			<button class="catalog-close" onclick={() => (catalogOpen = false)}>×</button>
		</div>
		<div class="catalog-body">
			<div class="catalog-scroll">
				{#each COLOR_CATALOGS as cat (cat.id)}
					{@const active = selectedCatalog === cat.id}
					<button
						class="catalog-item"
						class:active
						onclick={() => { selectedCatalog = cat.id; try { localStorage.setItem(CATALOG_KEY, cat.id); } catch {} }}
					>
						<div class="catalog-swatches">
							{#each cat.swatches as hex (hex)}
								<div class="catalog-swatch" style="background:{hex}"></div>
							{/each}
						</div>
						<div class="catalog-info">
							<div class="catalog-name">{cat.name}</div>
							<div class="catalog-sub">{cat.sub}</div>
						</div>
						{#if active}<span class="catalog-check">✓</span>{/if}
					</button>
				{/each}
			</div>
			<div class="catalog-detail">
				<div class="section-label">{currentCatalog.name} — {t().colorCatalogDetail}</div>
				<div class="catalog-detail-list">
					{#each currentCatalog.palette as color (color.code)}
						<div class="catalog-color-row">
							<div class="catalog-color-box" class:light={isLightColor(color.code)} style="background:{color.code}"></div>
							<span class="catalog-color-name">{color.name}</span>
							<span class="catalog-color-code">{color.code}</span>
						</div>
					{/each}
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- ══ HISTORY MANAGER MODAL ══ -->
{#if historyManagerOpen}
	<div class="modal-backdrop" onclick={() => (historyManagerOpen = false)} aria-hidden="true"></div>
	<div class="history-modal" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()}>
		<div class="modal-head">
			<div class="catalog-modal-title">{t().historyManagerTitle}</div>
			<div class="modal-head-actions">
				<button class="ghost-btn" class:ghost-active={historyManagerView === 'trash'} onclick={() => setHistoryManagerView(historyManagerView === 'trash' ? 'active' : 'trash')}>{t().historyTrashButton(managerTrashTotal || trashTotal)}</button>
				<button class="catalog-close" onclick={() => (historyManagerOpen = false)}>×</button>
			</div>
		</div>
		<div class="settings-tabs history-mode-tabs">
			<button class:active={historyManagerTab === 'thumbs'} onclick={() => (historyManagerTab = 'thumbs')}>{t().historyThumbsTab}</button>
			<button class:active={historyManagerTab === 'list'} onclick={() => (historyManagerTab = 'list')}>{t().historyListTab}</button>
		</div>
		<div class="history-tools">
			<span class="history-manager-count">
				{#if managedHistoryTotal === 0}
					0 / 0
				{:else}
					{historyManagerOffset + 1}-{historyManagerShownTo} / {managedHistoryTotal}
				{/if}
			</span>
			<button class="ghost-btn" onclick={selectAllManagedHistory}>{t().historySelectAll}</button>
			{#if historyManagerView === 'active'}
				<button class="ghost-btn" onclick={() => askTrash(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyMoveToTrash}</button>
			{:else}
				<button class="ghost-btn" onclick={() => askRestore(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyRestoreSelected}</button>
				<button class="danger-btn" onclick={() => askPermanentDelete(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyPermanentDelete}</button>
			{/if}
			<label class="history-search">{t().historySearchLabel} <input bind:value={historySearch} /></label>
		</div>
		<div class="history-manager-pager">
			<button class="ghost-btn history-nav-btn" onclick={() => setHistoryManagerPage(historyManagerPage - 1)} disabled={historyManagerPage <= 0 || historyManagerLoading}>{t().historyPrev}</button>
			<span>{historyManagerLoading ? t().historyLoading : `${historyManagerPage + 1} / ${historyManagerTotalPages}`}</span>
			<button class="ghost-btn history-nav-btn" onclick={() => setHistoryManagerPage(historyManagerPage + 1)} disabled={historyManagerPage >= historyManagerTotalPages - 1 || historyManagerLoading}>{t().historyNext}</button>
		</div>
		{#if historyManagerTab === 'thumbs'}
			<div class="history-thumb-grid-wrap">
				<div class="history-thumb-grid">
					{#each managedHistoryItems as it, i (it.id ?? it.at)}
						<div class="manager-thumb-wrap" class:selected={!!it.id && selectedHistoryIds.includes(it.id)}>
							<label class="manager-check">
								<input type="checkbox" checked={!!it.id && selectedHistoryIds.includes(it.id)} onchange={() => it.id && toggleHistorySelection(it.id)} />
							</label>
							<button class="thumb manager-thumb" onclick={() => historyManagerView === 'active' && loadIterationItem(it)}>
								<div class="thumb-tooltip">
									<div class="tooltip-title">#{historyManagerOffset + i + 1}</div>
									<div>{t().historyTooltipModel}: {historyModelSummary(it)}</div>
									<div>{t().historyTooltipSavedAt}: {formatHistoryDate(it.at)}</div>
									<div>{t().historyTooltipSeconds}: {formatElapsed(it.elapsed_ms)}</div>
									<div>{t().historyTooltipColorCatalog}: {catalogName(it.catalog_id)}</div>
									<div>{t().historyTooltipTokens}: {historyTokenSummary(it)}</div>
									<div class="tooltip-date">{historyPreviewText(it.input)}</div>
								</div>
								<div class="thumb-svg">{@html it.svg}</div>
								<div class="thumb-meta">
									<span class="thumb-time">{formatElapsed(it.elapsed_ms)}</span>
									{#if it.stage2_model}<span class="thumb-model">{shortModel(it.stage2_model)}</span>{/if}
								</div>
							</button>
							<div class="manager-thumb-actions">
								{#if historyManagerView === 'active'}
									<button class="ghost-btn" onclick={() => it.id && askTrash([it.id])}>{t().deleteButton}</button>
								{:else}
									<button class="ghost-btn" onclick={() => it.id && askRestore([it.id])}>{t().historyRestore}</button>
									<button class="danger-btn" onclick={() => it.id && askPermanentDelete([it.id])}>{t().historyPermanentDelete}</button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			</div>
		{:else}
			<div class="history-table-wrap">
				<table class="history-table">
					<thead>
						<tr><th></th><th>{t().historyImageHeader}</th><th>{t().historyCreatedAtHeader}</th><th>{t().historyModelHeader}</th><th>{t().historySecondsHeader}</th><th>{t().historyCatalogHeader}</th><th>{t().historyActionHeader}</th></tr>
					</thead>
					<tbody>
						{#each managedHistoryItems as it (it.id ?? it.at)}
							<tr>
								<td><input type="checkbox" checked={!!it.id && selectedHistoryIds.includes(it.id)} onchange={() => it.id && toggleHistorySelection(it.id)} /></td>
								<td><div class="history-mini">{@html it.svg}</div></td>
								<td>{formatHistoryDate(it.at)}</td>
								<td>{historyModelSummary(it)}</td>
								<td>{formatElapsed(it.elapsed_ms)}</td>
								<td>{catalogName(it.catalog_id)}</td>
								<td>
									{#if historyManagerView === 'active'}
										<button class="ghost-btn" onclick={() => it.id && askTrash([it.id])}>{t().deleteButton}</button>
									{:else}
										<button class="ghost-btn" onclick={() => it.id && askRestore([it.id])}>{t().historyRestore}</button>
										<button class="danger-btn" onclick={() => it.id && askPermanentDelete([it.id])}>{t().historyPermanentDelete}</button>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</div>
{/if}

{#if confirmAction}
	<div class="confirm-layer">
		<div class="confirm-backdrop" onclick={() => (confirmAction = null)}></div>
		<div class="confirm-box">
			<p>{confirmAction.message}</p>
			<div class="confirm-actions">
				<button class="ghost-btn" onclick={() => (confirmAction = null)}>{t().confirmCancel}</button>
				<button class={confirmAction.destructive ? 'danger-btn' : 'confirm-btn'} onclick={() => { const run = confirmAction?.run; confirmAction = null; run?.(); }}>{confirmAction.destructive ? t().deleteButton : t().confirmRun}</button>
			</div>
		</div>
	</div>
{/if}
{/if}

<style>
	/* ── CSS Variables ──────────────────────────────────────── */
	:global(:root) {
		--bg:           #f5f3ef;
		--bg2:          #eceae4;
		--bg3:          #e2dfd8;
		--fg:           #1a1917;
		--fg2:          #5a5751;
		--fg3:          #9a9690;
		--accent:       #2a4a72;
		--accent-light: #e8eef5;
		--border:       #d4d0c8;
		--border2:      #c4c0b8;
		--r:            4px;
		--r-lg:         8px;
	}

	:global(*, *::before, *::after) { box-sizing: border-box; margin: 0; padding: 0; }

	:global(html), :global(body) {
		height: 100%;
		font-family: -apple-system, 'Hiragino Kaku Gothic ProN', 'Yu Gothic', 'Meiryo', sans-serif;
		font-size: 13px;
		background: var(--bg);
		color: var(--fg);
	}

	:global(::-webkit-scrollbar) { width: 6px; height: 6px; }
	:global(::-webkit-scrollbar-track) { background: transparent; }
	:global(::-webkit-scrollbar-thumb) { background: var(--border2); border-radius: 3px; }

	/* ── Root layout ────────────────────────────────────────── */
	.root {
		display: flex;
		flex-direction: column;
		height: 100vh;
		overflow: hidden;
	}

	/* ── Header ─────────────────────────────────────────────── */
	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 20px;
		border-bottom: 1px solid var(--border);
		background: var(--bg);
		flex-shrink: 0;
		gap: 12px;
	}

	.logo { font-size: 22px; font-weight: 300; letter-spacing: 0.05em; line-height: 1.1; }
	.logo-sub { font-size: 11px; color: var(--fg3); margin-top: 2px; }

	.header-right {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-shrink: 0;
	}

	.user-badge {
		display: flex;
		align-items: center;
		gap: 6px;
		max-width: 220px;
		padding: 0 2px;
		border-left: 1px solid var(--border);
		padding-left: 10px;
		background: transparent;
		color: var(--fg2);
		font-size: 12px;
		min-width: 0;
		cursor: default;
	}
	.user-badge-name {
		font-weight: 400;
		color: var(--fg2);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.settings-wrap { position: relative; }

	.settings-btn {
		display: flex; align-items: center; gap: 4px;
		padding: 5px 11px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 12px;
		cursor: pointer;
		font-family: inherit;
	}
	.settings-btn.active, .settings-btn:hover { background: var(--bg2); }

	.settings-popover {
		position: absolute;
		top: calc(100% + 6px);
		right: 0;
		z-index: 200;
		background: #fff;
		border: 1px solid var(--border2);
		border-radius: var(--r-lg);
		padding: 16px;
		box-shadow: 0 6px 24px rgba(0,0,0,0.13);
		width: 340px;
	}

	.popover-title { font-weight: 500; margin-bottom: 12px; font-size: 13px; }

	.popover-group {
		background: var(--bg);
		border-radius: var(--r);
		padding: 10px;
		margin-bottom: 8px;
	}
	.popover-group-label {
		font-size: 10px; color: var(--fg3); font-weight: 500;
		letter-spacing: 0.07em; text-transform: uppercase;
		margin-bottom: 7px;
	}
	.popover-row {
		display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
	}
	.popover-row-label { width: 50px; color: var(--fg2); font-size: 11px; flex-shrink: 0; }
	.popover-row select {
		flex: 1; padding: 4px 6px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; color: var(--fg); font-size: 12px; font-family: inherit;
	}
	.popover-think-label {
		display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--fg2);
		cursor: pointer; margin-top: 4px;
	}
	.popover-close {
		margin-top: 4px; width: 100%; padding: 7px;
		background: var(--fg); color: #fff;
		border: none; border-radius: var(--r);
		font-size: 12px; cursor: pointer; font-family: inherit;
	}

	.lang-switcher {
		display: flex;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		overflow: hidden;
	}
	.lang-btn {
		padding: 4px 10px; border: none; border-right: 1px solid var(--border2);
		background: #fff; color: var(--fg2); font-size: 12px; cursor: pointer; font-family: inherit;
	}
	.lang-btn:last-child { border-right: none; }
	.lang-btn.active { background: var(--fg); color: #fff; }

	.header-link {
		padding: 4px 0; border: none; border-bottom: 1px solid transparent;
		background: none; color: var(--fg3); font-size: 12px; cursor: pointer; font-family: inherit;
		transition: color 0.15s;
	}
	.header-link:hover { color: var(--fg); }
	.header-link.underlined { color: var(--fg); border-bottom-color: var(--fg); }

	.header-sep { color: var(--border); font-size: 11px; }
	.build-badge { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }

	/* ── Body ───────────────────────────────────────────────── */
	.body {
		display: flex;
		flex: 1;
		overflow: hidden;
		position: relative;
	}

	/* ── Left panel ─────────────────────────────────────────── */
	.left-panel {
		width: 440px;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		border-right: 1px solid var(--border);
		overflow: hidden;
	}

	.panel-tabs {
		display: flex;
		border-bottom: 1px solid var(--border);
		background: var(--bg);
		flex-shrink: 0;
	}
	.panel-tab {
		padding: 9px 16px; border: none; border-bottom: 2px solid transparent;
		background: none; color: var(--fg2); font-size: 13px; cursor: pointer;
		font-family: inherit; transition: color 0.1s;
	}
	.panel-tab.active { border-bottom-color: var(--fg); color: var(--fg); font-weight: 500; }
	.panel-tab:hover:not(.active) { color: var(--fg); }

	.panel-scroll {
		flex: 1;
		overflow-y: auto;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.panel-section { display: flex; flex-direction: column; gap: 6px; }

	.section-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.section-label {
		font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
		color: var(--fg3); text-transform: uppercase;
	}

	.section-actions { display: flex; gap: 5px; }

	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
	.ghost-btn.ghost-active { background: var(--fg); color: #fff; border-color: var(--fg); }
	.create-btn {
		background: #fff7e8;
		border-color: #d8b36a;
		color: #6c4a10;
		font-weight: 600;
		box-shadow: 0 1px 3px rgba(108,74,16,0.12);
	}
	.create-btn:hover {
		background: #ffefd0;
		border-color: #bd8f34;
		color: #4f360b;
	}

	/* Input textarea */
	.input-ta, .batch-ta {
		width: 100%; padding: 9px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; color: var(--fg);
		font-family: inherit; font-size: 13px; line-height: 1.65;
		resize: vertical; outline: none;
	}
	.input-ta:focus, .batch-ta:focus { border-color: var(--accent); }

	.batch-wrap {
		display: flex;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		overflow: hidden;
	}
	.line-nums {
		background: var(--bg2); border-right: 1px solid var(--border);
		padding: 9px 6px; font-size: 13px; line-height: 1.65;
		text-align: right; color: var(--fg3); user-select: none;
		font-family: inherit;
		white-space: pre; min-width: 2rem; font-variant-numeric: tabular-nums;
	}
	.batch-ta {
		flex: 1;
		border: none;
		border-radius: 0;
		white-space: pre;
		overflow-wrap: normal;
		overflow-x: auto;
	}
	.batch-wrap .batch-ta { min-height: 240px; }
	.batch-info { font-size: 11px; color: var(--fg3); }

	/* Progress */
	.progress-wrap {
		display: flex; align-items: center; justify-content: space-between;
		padding: 8px 10px 6px;
		border: 1px solid var(--border2); border-radius: var(--r) var(--r) 0 0;
		background: #fff;
		margin-top: 8px;
	}
	.progress-phases { display: flex; align-items: center; gap: 4px; }
	.phase-sep { color: var(--border); font-size: 9px; margin: 0 1px; }
	.phase-item { font-size: 11px; color: var(--border2); display: flex; align-items: center; gap: 3px; }
	.phase-item.phase-active { color: var(--fg); font-weight: 500; }
	.phase-item.phase-done { color: var(--fg3); }
	.phase-dot {
		display: inline-block; width: 6px; height: 6px; border-radius: 50%;
		background: var(--accent); flex-shrink: 0;
		animation: inkupulse 1s ease-in-out infinite;
	}
	.phase-check { color: #27ae60; font-size: 10px; }
	.progress-right { display: flex; align-items: center; gap: 7px; }
	.progress-time { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }
	.stop-sm {
		padding: 2px 7px; border: 1px solid var(--border2);
		border-radius: var(--r); background: none;
		color: var(--fg2); font-size: 11px; cursor: pointer; font-family: inherit;
	}
	.progress-bar-track {
		position: relative;
		height: 32px; background: transparent;
		border-left: 1px solid var(--border2); border-right: 1px solid var(--border2);
		overflow: visible;
	}
	.progress-bar-track::before {
		content: "";
		position: absolute; top: 18px; left: 0; right: 0; height: 3px;
		background: var(--bg3);
	}
	.progress-bar-fill {
		position: absolute; top: 18px; left: 0; height: 3px;
		width: var(--progress-target, 50%);
		background: var(--accent); transition: width 0.3s ease;
	}
	.progress-bird {
		position: absolute;
		left: calc(var(--progress-target, 50%) - 26px);
		bottom: 8px;
		width: 52px;
		height: 44px;
		pointer-events: none;
		overflow: visible;
		filter: drop-shadow(0 2px 3px rgba(107, 123, 42, 0.18));
		animation: birdWalk 12s ease-in-out infinite;
	}
	.bird-peck {
		transform-origin: 22px 35px;
		animation: birdPeck 7.8s ease-in-out infinite;
	}
	.bird-preen {
		transform-origin: 28px 26px;
		animation: birdPreen 11.5s ease-in-out infinite;
	}
	.bird-shadow { fill: rgba(60, 55, 39, 0.18); }
	.bird-body, .bird-head-fill { fill: #7f8f35; }
	.bird-tail { fill: #536523; }
	.bird-view-side {
		transform-origin: 26px 25px;
		animation: birdSideView 12s ease-in-out infinite;
	}
	.bird-view-front {
		opacity: 0;
		transform-origin: 26px 25px;
		animation: birdFrontView 12s ease-in-out infinite;
	}
	.bird-view-three {
		opacity: 0;
		transform-origin: 26px 25px;
		animation: birdThreeQuarterView 12s ease-in-out infinite;
	}
	.bird-wing {
		fill: #a7b45a;
		transform-origin: 28px 25px;
		animation: birdWing 5.6s ease-in-out infinite;
	}
	.bird-wing-left,
	.bird-wing-right {
		animation: none;
	}
	.bird-head {
		transform-origin: 21px 25px;
		animation: birdHead 7.8s ease-in-out infinite;
	}
	.bird-beak { fill: #bd8f34; }
	.bird-eye { fill: #1f2114; }
	.bird-leg {
		fill: none;
		stroke: #7a5a18;
		stroke-width: 1.5;
		stroke-linecap: round;
		transform-origin: 26px 33px;
	}
	.bird-leg-a { animation: birdStepA 1.25s ease-in-out infinite; }
	.bird-leg-b { animation: birdStepB 1.25s ease-in-out infinite; }
	.progress-stage-text {
		font-size: 11px; color: var(--fg3);
		padding: 5px 10px 7px;
		border: 1px solid var(--border2); border-top: none;
		border-radius: 0 0 var(--r) var(--r);
		background: #fff;
	}

	.batch-progress {
		display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
		padding: 8px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; font-size: 12px; color: var(--fg2);
		margin-top: 8px;
	}
	.batch-summary {
		margin-top: 8px;
		padding: 8px 10px;
		border: 1px solid #b8c7ab;
		border-radius: var(--r);
		background: #f5f8f1;
		color: #40552b;
		font-size: 12px;
	}
	.batch-summary.has-failures {
		border-color: #d9b4ae;
		background: #fff6f4;
		color: #7c332b;
	}
	.batch-summary-line { font-weight: 500; }
	.batch-failure-title { margin-top: 6px; color: var(--fg2); font-size: 11px; }
	.batch-failure-list {
		margin: 4px 0 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.batch-failure-list li {
		display: grid;
		grid-template-columns: 48px minmax(0, 1fr);
		gap: 3px 8px;
	}
	.batch-failure-line { color: var(--fg2); font-variant-numeric: tabular-nums; }
	.batch-failure-input {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.batch-failure-message {
		grid-column: 2;
		color: #a2342a;
		font-size: 11px;
		word-break: break-word;
	}

	/* Play button */
	.play-btn {
		width: 100%; margin-top: 8px; padding: 9px;
		font-size: 14px; font-weight: 500;
		background: var(--fg); color: #fff;
		border: none; border-radius: var(--r);
		letter-spacing: 0.08em; cursor: pointer;
		display: flex; align-items: center; justify-content: center; gap: 8px;
		font-family: inherit; transition: background 0.15s;
	}
	.play-btn:hover:not(:disabled) { background: #333; }
	.play-btn:disabled { background: var(--fg3); cursor: not-allowed; }

	.error-text { color: #a2342a; font-size: 12px; }

	/* Annotations */
	.annot-box {
		padding: 9px 10px; background: #fff;
		border: 1px solid var(--border); border-radius: var(--r);
		font-size: 13px; line-height: 1.85; white-space: pre-wrap; word-break: break-word;
	}
	.ddl-box { border-left: 3px solid var(--border2); border-radius: 0 var(--r) var(--r) 0; }

	.tok { }
	.tok-saijiki { color: #2c3e91; font-weight: 500; }
	.tok-plain   { color: var(--fg3); }
	.tok-emotion { color: #c9a08a; font-style: italic; text-decoration: line-through; text-decoration-color: rgba(162,52,42,0.4); }
	.tok-diff-added { color: #a2342a; font-weight: 500; }

	.ddl-edit-ta {
		width: 100%; padding: 9px 10px;
		border: 1px solid var(--accent); border-left: 3px solid var(--border2);
		border-radius: 0 var(--r) var(--r) 0;
		background: #fff; color: var(--fg);
		font-family: inherit; font-size: 13px; line-height: 1.75; resize: vertical; outline: none;
	}

	/* thinking */
	.thinking-details {
		font-size: 12px; background: #f3efe6;
		border-left: 3px solid #c9a08a; border-radius: 0 3px 3px 0; padding: 6px 10px;
	}
	.thinking-details summary { cursor: pointer; color: #8a6f5a; font-style: italic; }
	.thinking-details pre {
		white-space: pre-wrap; word-break: break-word; color: #6b5340;
		font-family: inherit; line-height: 1.6; margin-top: 6px;
		max-height: 180px; overflow-y: auto; font-size: 12px;
	}

	/* Replay */
	.replay-btn {
		width: 100%; margin-top: 6px; padding: 10px;
		font-size: 14px; font-weight: 500; background: #e8f1fb; color: #234c78;
		border: 1px solid #9fb9d6; border-radius: var(--r);
		letter-spacing: 0.08em; cursor: pointer;
		display: flex; align-items: center; justify-content: center; gap: 6px;
		font-family: inherit; transition: background 0.15s, border-color 0.15s, color 0.15s;
	}
	.replay-btn:hover:not(:disabled) { background: #d7e8f8; border-color: #6f98c3; color: #173f68; }
	.replay-btn:disabled { background: var(--bg2); border-color: var(--border2); color: var(--fg3); cursor: not-allowed; }

	/* Stats */
	.stats-section { }
	.stats-toggle {
		display: flex; align-items: center; gap: 5px;
		width: 100%; padding: 4px 2px;
		border: none; background: none;
		color: var(--fg3); font-size: 11px; cursor: pointer;
		text-align: left; font-family: inherit;
	}
	.stats-arrow {
		display: inline-block; font-size: 9px;
		transition: transform 0.15s;
	}
	.stats-arrow.open { transform: rotate(90deg); }
	.stats-detail {
		background: var(--bg2); border-radius: var(--r); border-left: 2px solid var(--border2);
		padding: 8px 12px; font-size: 11px; color: var(--fg2); line-height: 1.9;
	}
	.stats-grid { display: grid; grid-template-columns: auto 1fr; gap: 0 12px; }
	.stats-key { color: var(--fg3); }
	.stats-total { font-weight: 500; }

	/* ── Right panel ────────────────────────────────────────── */
	.right-panel {
		flex: 1; min-width: 0;
		display: flex; flex-direction: column;
		overflow: hidden;
	}

	.right-tabs {
		display: flex; align-items: center;
		border-bottom: 1px solid var(--border);
		background: var(--bg); padding: 0 16px; flex-shrink: 0;
	}
	.rtab {
		padding: 9px 16px; border: none; border-bottom: 2px solid transparent;
		background: none; color: var(--fg2); font-size: 13px; cursor: pointer;
		font-family: inherit; white-space: nowrap;
	}
	.rtab.active { border-bottom-color: var(--fg); color: var(--fg); font-weight: 500; }
	.rtab:hover:not(.active):not(:disabled) { color: var(--fg); }
	.rtab:disabled { opacity: 0.35; cursor: not-allowed; }
	.rtab-spacer { flex: 1; }
	.rendered-at { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }

	/* Canvas area */
	.canvas-area {
		flex: 1; display: flex; align-items: center; justify-content: center;
		background: var(--bg2); position: relative; overflow: hidden;
	}

	.nav-left {
		position: absolute; left: 14px; z-index: 10;
		display: flex; flex-direction: column; align-items: center; gap: 6px;
	}
	.nav-right {
		position: absolute; right: 14px; z-index: 10;
		display: flex; flex-direction: column; align-items: center; gap: 6px;
	}
	.nav-circle {
		width: 38px; height: 38px; border-radius: 50%;
		background: rgba(255,255,255,0.88); border: 1px solid var(--border2);
		font-size: 20px; box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		display: flex; align-items: center; justify-content: center;
		color: var(--fg); cursor: pointer; font-family: inherit;
		transition: background 0.1s;
	}
	.nav-circle:hover:not(:disabled) { background: #fff; }
	.nav-circle:disabled { opacity: 0.35; cursor: not-allowed; }
	.nav-counter { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; white-space: nowrap; }

	.canvas-content {
		position: relative; width: 100%; height: 100%;
		display: flex; align-items: center; justify-content: center; overflow: hidden;
	}
	.canvas-content.can-pan { cursor: grab; touch-action: none; }
	.canvas-content.dragging { cursor: grabbing; }

	.canvas-pan {
		display: flex;
		align-items: center;
		justify-content: center;
		will-change: transform;
	}

	.canvas-box {
		width: 400px;
		height: 400px;
		background: #fff;
		box-shadow: 0 8px 32px rgba(0,0,0,0.18);
		overflow: hidden;
		flex-shrink: 0;
	}

	.canvas-box :global(svg) { width: 100%; height: 100%; display: block; }

	.canvas-placeholder {
		width: 100%; height: 100%; min-height: 200px;
		display: flex; align-items: center; justify-content: center;
		color: var(--fg3); font-size: 13px;
	}

	/* Zoom controls */
	.zoom-controls {
		position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
		z-index: 10;
		display: flex; align-items: center; gap: 0;
		background: rgba(255,255,255,0.9); border: 1px solid var(--border2);
		border-radius: 20px; box-shadow: 0 1px 6px rgba(0,0,0,0.1); overflow: hidden;
	}
	.zoom-controls button {
		width: 32px; height: 28px; border: none; background: none;
		font-size: 16px; color: var(--fg); cursor: pointer;
		display: flex; align-items: center; justify-content: center; font-family: inherit;
	}
	.zoom-controls button:hover { background: var(--bg2); }
	.zoom-pct {
		font-size: 11px; color: var(--fg2); font-variant-numeric: tabular-nums;
		min-width: 38px; text-align: center; user-select: none;
	}
	.zoom-reset { border-left: 1px solid var(--border) !important; font-size: 11px !important; color: var(--fg3) !important; }

	/* Prompts / Score tabs */
	.prompt-section {
		flex: 1; display: flex; flex-direction: column; gap: 4px;
		overflow-y: auto; padding: 12px;
		width: 100%;
		align-self: stretch; min-height: 0;
	}
	.prompt-label { margin: 8px 0 3px; font-size: 11px; font-weight: 600; color: var(--fg2); }
	.prompt-collapsible-head {
		display: flex; align-items: center; justify-content: space-between;
		margin-top: 8px;
	}
	.prompt-collapsible-head .prompt-label { margin: 0; }
	.prompt-textarea {
		width: 100%;
		background: var(--bg2); padding: 8px 10px; border-radius: var(--r);
		border: 1px solid var(--border); overflow: auto;
		white-space: pre-wrap; word-break: break-word; font-size: 11px; line-height: 1.5; margin: 0;
		font-family: inherit; color: var(--fg);
		resize: vertical;
	}
	.prompt-user { min-height: 120px; }
	.prompt-system { min-height: 120px; height: 220px; }
	.prompt-collapse {
		position: relative;
		max-height: 80px;
		overflow: hidden;
	}
	.prompt-collapse.expanded {
		max-height: none;
		overflow: visible;
	}
	.prompt-collapse:not(.expanded) .prompt-system {
		height: 120px;
		resize: none;
	}
	.prompt-fade {
		position: absolute; left: 0; right: 0; bottom: 0; height: 32px;
		background: linear-gradient(transparent, var(--bg));
		pointer-events: none;
	}
	.prompt-pre {
		background: var(--bg2); padding: 8px 10px; border-radius: var(--r);
		border: 1px solid var(--border); overflow-x: auto; max-height: 140px;
		white-space: pre-wrap; word-break: break-word; font-size: 11px; line-height: 1.5; margin: 0;
		font-family: inherit;
	}
	.prompt-pre-lg { max-height: 320px; }
	.score-view {
		display: flex;
		width: 100%;
		height: 100%;
		min-height: 0;
		align-self: stretch;
		background: #fff;
		border: 1px solid var(--border);
		border-radius: var(--r);
		overflow: auto;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
		font-size: 12px;
		line-height: 1.5;
	}
	.score-line-nums {
		flex-shrink: 0;
		min-width: 42px;
		min-height: 100%;
		height: max-content;
		padding: 12px 8px;
		border-right: 1px solid var(--border);
		background: var(--bg2);
		color: var(--fg3);
		text-align: right;
		user-select: none;
		font-variant-numeric: tabular-nums;
	}
	.score-pre {
		background: #fff;
		padding: 12px; overflow: visible; font-size: inherit; line-height: inherit;
		white-space: pre; word-break: normal;
		width: 100%; min-height: 100%; height: max-content; margin: 0;
		font-family: inherit;
		align-self: flex-start;
	}
	.score-pre :global(.json-key) { color: #6f4bb8; font-weight: 600; }
	.score-pre :global(.json-string) { color: #116329; }
	.score-pre :global(.json-number) { color: #0b63ce; }
	.score-pre :global(.json-bool) { color: #b54708; font-weight: 600; }
	.score-pre :global(.json-null) { color: #6b7280; font-style: italic; }
	.muted-center { color: var(--fg3); font-size: 13px; padding: 16px; }

	/* Export bar */
	.export-bar {
		display: flex; align-items: center; gap: 6px;
		padding: 8px 16px; border-top: 1px solid var(--border);
		background: var(--bg); flex-shrink: 0;
	}
	.export-label { font-size: 11px; color: var(--fg3); margin-right: auto; }

	.png-wrap { position: relative; }
	.png-menu {
		position: absolute; bottom: calc(100% + 6px); right: 0; z-index: 100;
		background: #fff; border: 1px solid var(--border2);
		border-radius: var(--r-lg); overflow: hidden;
		box-shadow: 0 4px 18px rgba(0,0,0,0.12); min-width: 220px;
	}
	.png-menu button {
		display: flex; align-items: center; gap: 8px;
		width: 100%; text-align: left;
		padding: 8px 14px; background: none; border: none;
		border-bottom: 1px solid var(--border); color: var(--fg); cursor: pointer;
		font-family: inherit; font-size: 13px; white-space: nowrap;
	}
	.png-menu button:last-child { border-bottom: none; }
	.png-menu button:hover { background: var(--bg); }
	.png-size { font-weight: 500; }
	.png-sub { color: var(--fg3); font-size: 11px; white-space: nowrap; }

	/* ── History strip ───────────────────────────────────────── */
	.history-strip {
		position: relative;
		z-index: 30;
		border-top: 1px solid var(--border);
		background: var(--bg);
		padding: 8px 16px 10px;
		flex-shrink: 0;
	}
	.history-head {
		display: flex; justify-content: space-between; align-items: center;
		margin-bottom: 7px;
	}
	.history-title { font-size: 12px; font-weight: 500; color: var(--fg2); }
	.history-title-btn {
		border: 1px solid var(--border2);
		border-radius: 16px;
		background: #fff;
		color: var(--fg2);
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		font-family: inherit;
		padding: 5px 12px;
		box-shadow: 0 1px 3px rgba(0,0,0,0.06);
		transition: background 0.12s, border-color 0.12s, color 0.12s, box-shadow 0.12s;
	}
	.history-title-btn:hover {
		color: var(--fg);
		background: var(--accent-light);
		border-color: var(--accent);
		box-shadow: 0 2px 8px rgba(42,74,114,0.16);
	}
	.history-count { color: var(--fg3); font-weight: 400; }
	.history-page-nav { display: flex; align-items: center; gap: 6px; }
	.history-page-indicator { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; min-width: 30px; text-align: center; }
	.history-nav-btn { min-width: 92px; }

	.thumb-strip {
		display: flex; gap: 7px; overflow: visible;
	}

	.thumb {
		flex-shrink: 0; width: 82px;
		border: 2px solid transparent;
		border-radius: var(--r); overflow: hidden; background: #fff;
		cursor: pointer; padding: 0; font-family: inherit; position: relative;
		transition: border-color 0.1s;
	}
	.thumb:hover { overflow: visible; z-index: 2000; }
	.thumb.current { border-color: var(--accent); }
	.thumb-tooltip {
		position: absolute; bottom: calc(100% + 6px); left: 50%;
		transform: translateX(-50%) translateY(4px);
		opacity: 0; pointer-events: none;
		background: rgba(26,25,23,0.92); color: #fff;
		font-size: 11px; border-radius: var(--r);
		padding: 8px 10px; white-space: nowrap;
		text-align: left;
		width: max-content;
		max-width: min(360px, calc(100vw - 24px));
		z-index: 3000; line-height: 1.7;
		transition: opacity 0.15s, transform 0.15s;
		box-shadow: 0 4px 18px rgba(0,0,0,0.18);
	}
	.thumb:hover .thumb-tooltip {
		opacity: 1;
		transform: translateX(-50%) translateY(0);
	}
	.tooltip-title { font-weight: 500; margin-bottom: 3px; }
	.tooltip-row {
		display: grid;
		grid-template-columns: 54px minmax(0, 1fr);
		gap: 8px;
		align-items: baseline;
	}
	.tooltip-row span { color: rgba(255,255,255,0.62); }
	.tooltip-row strong {
		font-weight: 500;
		color: #fff;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.tooltip-date { color: rgba(255,255,255,0.55); margin-top: 3px; }
	.thumb-svg { width: 82px; height: 58px; overflow: hidden; }
	.thumb-svg :global(svg) {
		width: 100%;
		height: 100%;
		display: block;
		overflow: hidden;
		clip-path: inset(0);
	}
	.thumb-meta {
		padding: 3px 5px; border-top: 1px solid var(--border);
		display: flex; flex-direction: column; gap: 1px;
	}
	.thumb-time  { font-size: 11px; font-weight: 500; color: var(--fg2); }
	.thumb-model { font-size: 10px; color: var(--fg3); }
	.thumb-current-badge {
		position: absolute; bottom: 22px; right: 3px;
		background: var(--accent); color: #fff;
		font-size: 9px; padding: 1px 4px; border-radius: 2px;
	}

	/* ── Saijiki drawer ─────────────────────────────────────── */
	.saijiki-drawer {
		position: fixed; top: 0; right: 0; bottom: 0;
		width: 0; overflow: hidden; z-index: 300;
		transition: width 0.25s cubic-bezier(0.4,0,0.2,1);
		pointer-events: none;
	}
	.saijiki-drawer.open { width: 280px; pointer-events: all; }

	.saijiki-inner {
		width: 280px; height: 100%;
		background: #faf9f6; border-left: 1px solid var(--border);
		display: flex; flex-direction: column;
		box-shadow: -4px 0 24px rgba(0,0,0,0.08);
	}

	.saijiki-head {
		padding: 16px 18px 12px;
		border-bottom: 1px solid var(--border);
		display: flex; align-items: flex-start; justify-content: space-between;
		flex-shrink: 0;
	}
	.saijiki-title {
		font-size: 17px; font-weight: 300; letter-spacing: 0.06em; color: var(--fg);
	}
	.saijiki-hint { font-size: 10px; color: var(--fg3); margin-top: 3px; line-height: 1.5; }
	.saijiki-close {
		width: 24px; height: 24px; border: none; background: none;
		color: var(--fg3); font-size: 16px; cursor: pointer; flex-shrink: 0; margin-top: 2px;
	}
	.saijiki-body { flex: 1; overflow-y: auto; padding: 8px 0; }

	.saijiki-cat { padding: 10px 18px; }
	.saijiki-cat-head { display: flex; align-items: baseline; gap: 7px; margin-bottom: 8px; }
	.saijiki-cat-ja { font-size: 13px; font-weight: 400; color: var(--fg); letter-spacing: 0.05em; }
	.saijiki-cat-en { font-size: 9px; color: var(--fg3); letter-spacing: 0.1em; text-transform: uppercase; font-weight: 500; }

	.saijiki-chips { display: flex; flex-wrap: wrap; gap: 5px; }
	.saijiki-chip {
		padding: 4px 9px; border: 1px solid var(--border2); border-radius: 3px;
		background: #fff; color: var(--fg); font-size: 12px; cursor: pointer;
		font-family: inherit; line-height: 1.3; transition: background 0.1s, border-color 0.1s;
	}
	.saijiki-chip:hover { background: var(--bg2); border-color: var(--fg3); }

	/* ── Catalog modal ───────────────────────────────────────── */
	.modal-backdrop {
		position: fixed; inset: 0; z-index: 400;
		background: rgba(0,0,0,0.25); backdrop-filter: blur(2px);
	}
	.catalog-modal {
		position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
		z-index: 401;
		width: min(820px, calc(100vw - 32px)); max-height: 88vh;
		background: #faf9f6; border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex; flex-direction: column; overflow: hidden;
	}
	.catalog-modal-head {
		display: flex; align-items: center; justify-content: space-between;
		padding: 14px 18px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
	}
	.catalog-modal-title { font-size: 15px; font-weight: 300; letter-spacing: 0.05em; }
	.catalog-close {
		width: 24px; height: 24px; border: none; background: none;
		color: var(--fg3); font-size: 18px; cursor: pointer; line-height: 1;
	}
	.catalog-body {
		display: grid;
		grid-template-columns: minmax(340px, 1fr) minmax(260px, 0.75fr);
		flex: 1;
		min-height: 0;
	}
	.catalog-scroll { min-height: 0; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 6px; }

	.catalog-item {
		display: flex; align-items: center; gap: 12px; padding: 10px 12px;
		border: 1px solid var(--border); border-radius: var(--r);
		background: #fff; cursor: pointer; text-align: left;
		transition: border-color 0.12s, background 0.12s; font-family: inherit; width: 100%;
	}
	.catalog-item.active { border: 1.5px solid var(--accent); background: var(--accent-light); }
	.catalog-item:hover:not(.active) { background: var(--bg); }

	.catalog-swatches {
		display: flex; flex-shrink: 0; border-radius: 3px; overflow: hidden; height: 32px; width: 64px;
	}
	.catalog-swatch { flex: 1; }

	.catalog-info { flex: 1; min-width: 0; }
	.catalog-name { font-size: 12px; font-weight: 500; color: var(--fg); margin-bottom: 1px; }
	.catalog-sub  { font-size: 11px; color: var(--fg3); }
	.catalog-check { color: var(--accent); font-size: 13px; flex-shrink: 0; }
	.catalog-detail {
		border-left: 1px solid var(--border);
		padding: 12px 16px 14px;
		background: #fff;
		min-height: 0;
		overflow-y: auto;
	}
	.catalog-detail-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
	.catalog-color-row {
		display: flex; align-items: center; gap: 10px;
		font-size: 12px;
	}
	.catalog-color-box {
		width: 28px; height: 28px; border-radius: 3px; flex-shrink: 0;
	}
	.catalog-color-box.light { border: 1px solid var(--border); }
	.catalog-color-name { color: var(--fg); flex: 1; }
	.catalog-color-code {
		font-size: 11px; color: var(--fg3);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
	}

	/* ── Modal shared / settings / history ─────────────────── */
	.modal-head {
		display: flex; align-items: center; justify-content: space-between;
		padding: 14px 18px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
	}
	.settings-modal, .history-modal {
		position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
		z-index: 401;
		background: #faf9f6; border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex; flex-direction: column; overflow: hidden;
	}
	.settings-modal { width: min(860px, calc(100vw - 32px)); max-height: 88vh; }
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
		background: rgba(250, 249, 246, 0.94); border-radius: var(--r);
		box-shadow: 0 18px 54px rgba(40, 35, 24, 0.18);
		border: 1px solid rgba(90, 83, 68, 0.22);
		-webkit-backdrop-filter: blur(10px);
		backdrop-filter: blur(10px);
		display: flex; flex-direction: column;
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
	.login-lang-btn:hover { color: var(--fg); background: #fff; }
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
	.login-panel .login-grid {
		grid-template-columns: 1fr;
		gap: 10px;
	}
	.login-panel .login-grid input {
		min-height: 38px;
		padding: 8px 10px;
		font-size: 13px;
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
	}
	.password-toggle {
		width: 40px;
		border: 1px solid var(--border2);
		border-left: 0;
		border-radius: 0 var(--r) var(--r) 0;
		background: #f2f0eb;
		color: var(--fg2);
		cursor: pointer;
		display: grid;
		place-items: center;
	}
	.password-toggle:hover {
		color: var(--fg);
		background: #ebe8e1;
	}
	.password-toggle svg {
		width: 18px;
		height: 18px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.8;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.history-modal {
		width: min(920px, calc(100vw - 32px));
		height: min(720px, calc(100vh - 32px));
		max-height: 88vh;
	}
	.settings-tabs {
		display: flex; gap: 0; border-bottom: 1px solid var(--border); background: var(--bg);
	}
	.settings-tabs button {
		padding: 9px 16px; border: none; border-bottom: 2px solid transparent;
		background: none; color: var(--fg2); font-size: 13px; cursor: pointer; font-family: inherit;
	}
	.settings-tabs button.active { color: var(--fg); border-bottom-color: var(--fg); font-weight: 500; }
	.settings-body {
		padding: 14px 16px; overflow-y: auto;
		display: flex; flex-direction: column; gap: 10px;
	}
	.form-row {
		display: flex; align-items: center; gap: 8px; margin-bottom: 7px;
	}
	.form-row label { width: 90px; color: var(--fg2); font-size: 12px; flex-shrink: 0; }
	.form-row input, .form-row select, .plugin-add input, .history-search input, .login-grid input {
		flex: 1; min-width: 0; padding: 5px 7px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; color: var(--fg); font-size: 12px; font-family: inherit;
	}
	.check-row { display: flex; align-items: center; gap: 7px; color: var(--fg2); font-size: 12px; }
	.settings-inline-actions { display: flex; align-items: center; gap: 10px; }
	.db-test-result { color: var(--fg2); font-size: 12px; }
	.settings-readonly-grid {
		display: grid;
		grid-template-columns: 120px minmax(0, 1fr);
		gap: 7px 12px;
		align-items: baseline;
		margin-bottom: 9px;
		font-size: 12px;
	}
	.settings-readonly-grid span { color: var(--fg3); }
	.settings-readonly-grid strong { color: var(--fg); font-weight: 500; min-width: 0; word-break: break-word; }
	.settings-readonly-grid code {
		min-width: 0;
		padding: 2px 4px;
		border-radius: var(--r);
		background: var(--bg);
		color: var(--fg2);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 11px;
		word-break: break-all;
	}
	.inline-message {
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 12px;
	}
	.plugin-list {
		border: 1px solid var(--border); border-radius: var(--r);
		background: #fff; overflow: hidden;
	}
	.plugin-row {
		display: grid; grid-template-columns: 1fr auto auto; gap: 10px;
		align-items: center; padding: 9px 10px; border-bottom: 1px solid var(--border);
	}
	.plugin-row:last-child { border-bottom: none; }
	.plugin-version { color: var(--fg3); font-size: 11px; }
	.plugin-add { display: flex; gap: 8px; align-items: center; }
	.login-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
		gap: 8px;
		align-items: center;
	}
	.user-session-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 12px;
	}
	.user-editor-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
		margin-top: 10px;
	}
	.user-editor-panel {
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
		padding: 10px;
		min-width: 0;
	}
	.user-editor-title {
		font-size: 12px;
		font-weight: 500;
		color: var(--fg2);
		margin-bottom: 8px;
	}
	.user-form-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		gap: 8px;
	}
	.user-form-grid input, .user-form-grid select {
		min-width: 0; padding: 5px 7px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; color: var(--fg); font-size: 12px; font-family: inherit;
	}
	.user-form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 8px;
	}
	.primary-inline {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--accent);
	}
	.user-list, .group-list {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-top: 10px;
	}
	.user-row {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) minmax(0, 1.35fr) 120px 120px auto;
		gap: 8px;
		align-items: center;
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
	}
	.user-row.selected { border-color: var(--accent); background: var(--accent-light); }
	.user-cell { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg2); font-size: 12px; }
	.user-name { color: var(--fg); font-weight: 500; }
	.group-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		background: #fff;
		border: 1px solid var(--border);
		border-radius: var(--r);
		padding: 7px 9px;
		font-size: 12px;
		color: var(--fg2);
	}
	.setting-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
		color: var(--fg2);
		cursor: pointer;
	}
	.inline-confirm {
		display: flex; align-items: center; gap: 8px; justify-content: flex-end;
		background: #fff; border: 1px solid var(--border); border-radius: var(--r);
		padding: 9px 10px; font-size: 12px; color: var(--fg2);
	}
	.danger-btn, .confirm-btn {
		padding: 4px 10px; border: none; border-radius: var(--r);
		color: #fff; font-size: 11px; cursor: pointer; font-family: inherit;
	}
	.danger-btn { background: #c0392b; }
	.confirm-btn { background: var(--fg); }
	.danger-btn:disabled { opacity: 0.4; cursor: not-allowed; }
	.modal-head-actions { display: flex; align-items: center; gap: 8px; }
	.history-tools {
		display: flex; align-items: center; gap: 8px;
		padding: 10px 14px; border-bottom: 1px solid var(--border);
		flex-wrap: wrap;
	}
	.history-mode-tabs { flex-shrink: 0; }
	.history-manager-count {
		font-size: 11px;
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		margin-right: 2px;
	}
	.history-search { margin-left: auto; display: flex; align-items: center; gap: 6px; color: var(--fg2); font-size: 12px; }
	.history-search input { width: min(240px, 30vw); }
	.history-manager-pager {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 10px;
		padding: 8px 14px;
		border-bottom: 1px solid var(--border);
		color: var(--fg3);
		font-size: 11px;
		font-variant-numeric: tabular-nums;
	}
	.history-thumb-grid-wrap,
	.history-table-wrap {
		flex: 1;
		overflow: auto;
		padding: 12px 14px 14px;
		min-height: 0;
	}
	.history-thumb-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
		gap: 12px;
		align-items: start;
	}
	.manager-thumb-wrap {
		position: relative;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
		padding: 7px;
		transition: border-color 0.12s, box-shadow 0.12s;
	}
	.manager-thumb-wrap.selected {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-light);
	}
	.manager-check {
		position: absolute;
		top: 6px;
		left: 6px;
		z-index: 30;
		background: rgba(255,255,255,0.86);
		border-radius: 3px;
		line-height: 1;
		padding: 2px;
	}
	.manager-thumb {
		width: 100%;
	}
	.manager-thumb .thumb-svg {
		width: 100%;
		aspect-ratio: 82 / 58;
		height: auto;
	}
	.manager-thumb-actions {
		display: flex;
		gap: 5px;
		margin-top: 7px;
		flex-wrap: wrap;
	}
	.manager-thumb-actions .ghost-btn,
	.manager-thumb-actions .danger-btn {
		font-size: 10px;
		padding: 3px 7px;
	}
	.history-table {
		width: 100%; border-collapse: collapse; background: #fff;
		font-size: 12px;
	}
	.history-table th, .history-table td {
		border: 1px solid var(--border); padding: 7px 8px; text-align: left; vertical-align: middle;
	}
	.history-table th { color: var(--fg3); font-weight: 500; background: var(--bg); }
	.history-mini { width: 48px; height: 36px; overflow: hidden; background: #fff; border: 1px solid var(--border); }
	.history-mini :global(svg) {
		width: 100%;
		height: 100%;
		display: block;
		overflow: hidden;
		clip-path: inset(0);
	}
	.confirm-layer {
		position: fixed; inset: 0; z-index: 600;
		display: flex; align-items: center; justify-content: center;
	}
	.confirm-backdrop {
		position: absolute; inset: 0; background: rgba(0,0,0,0.3);
	}
	.confirm-box {
		position: relative; background: #fff; border-radius: var(--r-lg);
		padding: 22px 24px; box-shadow: 0 8px 32px rgba(0,0,0,0.18);
		min-width: 280px; text-align: center;
	}
	.confirm-box p { margin-bottom: 16px; font-size: 13px; color: var(--fg); }
	.confirm-actions { display: flex; gap: 8px; justify-content: center; }

	/* ── Animations ─────────────────────────────────────────── */
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50%       { opacity: 0.4; transform: scale(0.7); }
	}
	@keyframes birdWalk {
		0% { transform: translate(-28px, 0) scaleX(1); }
		9% { transform: translate(-14px, -1px) scaleX(1); }
		18% { transform: translate(-14px, 0) scaleX(1); }
		28% { transform: translate(12px, -1px) scaleX(1); }
		36% { transform: translate(12px, 0) scaleX(1); }
		44% { transform: translate(5px, 0) scaleX(1); }
		48% { transform: translate(2px, 0) scaleX(1); }
		52% { transform: translate(0, 0) scaleX(-1); }
		62% { transform: translate(-18px, -1px) scaleX(-1); }
		72% { transform: translate(-18px, 0) scaleX(-1); }
		82% { transform: translate(10px, -1px) scaleX(-1); }
		90% { transform: translate(10px, 0) scaleX(-1); }
		96% { transform: translate(-6px, 0) scaleX(-1); }
		100% { transform: translate(-28px, 0) scaleX(1); }
	}
	@keyframes birdSideView {
		0%, 40%, 56%, 94%, 100% { opacity: 1; transform: scaleX(1); }
		46%, 50%, 98% { opacity: 0; transform: scaleX(0.72); }
	}
	@keyframes birdFrontView {
		0%, 42%, 56%, 96%, 100% { opacity: 0; transform: scaleX(0.86); }
		47%, 50%, 53%, 98% { opacity: 1; transform: scaleX(1); }
	}
	@keyframes birdThreeQuarterView {
		0%, 39%, 57%, 93%, 100% { opacity: 0; transform: rotate(0deg); }
		43%, 55%, 95%, 99% { opacity: 0.92; transform: rotate(3deg); }
	}
	@keyframes birdWing {
		0%, 18%, 38%, 55%, 72%, 100% { transform: rotate(0deg) scaleY(1); }
		22%, 24%, 26% { transform: rotate(-28deg) scaleY(0.75); }
		29% { transform: rotate(8deg) scaleY(1.08); }
		78%, 80% { transform: rotate(-18deg) scaleY(0.82); }
		82% { transform: rotate(6deg) scaleY(1.06); }
	}
	@keyframes birdPeck {
		0%, 42%, 58%, 100% { transform: rotate(0deg) translateY(0); }
		46%, 50%, 54% { transform: rotate(-16deg) translateY(5px); }
		48%, 52%, 56% { transform: rotate(5deg) translateY(0); }
	}
	@keyframes birdPreen {
		0%, 62%, 78%, 100% { transform: rotate(0deg); }
		66%, 70%, 74% { transform: rotate(9deg) translateX(1px); }
		68%, 72% { transform: rotate(-5deg) translateX(-1px); }
	}
	@keyframes birdHead {
		0%, 42%, 58%, 62%, 100% { transform: rotate(0deg); }
		46%, 50%, 54% { transform: rotate(-22deg) translate(-1px, 4px); }
		66%, 70%, 74% { transform: rotate(18deg) translate(5px, 2px); }
	}
	@keyframes birdStepA {
		0%, 100% { transform: rotate(0deg); }
		45% { transform: rotate(14deg) translateX(1px); }
	}
	@keyframes birdStepB {
		0%, 100% { transform: rotate(0deg); }
		45% { transform: rotate(-14deg) translateX(-1px); }
	}
</style>

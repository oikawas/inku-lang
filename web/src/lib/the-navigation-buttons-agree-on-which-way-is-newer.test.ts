// Run with: npm run test:unit  (node:test, no test dependency)
//
// Seventeen buttons move through one listing of works. Before this contract they
// disagreed with each other about which way is newer ("next" meant newer on the
// canvas and older in the modal), about what "latest" is counted in (works on the
// canvas, pages in the strip, so the same word was enabled in one box and greyed
// out in the other on the same screen), and about where a press lands when it
// crosses a page. Three of them switched off entirely whenever the selection was
// cleared, which six ordinary actions do without asking. And eight more faults
// only appear with timing: a resize that leaves the modal showing works from one
// place under another place's numbers, a listing fetch with nothing to stop a
// late answer overwriting a newer one, a double press at a page boundary that
// advances once.
//
// The gates below fall into three kinds, and the difference matters:
//
//   * Rules driven directly -- historyNavigation.ts is pure, so the judgement
//     every button reads is exercised for real.
//   * The manager driven for real through history-manager-harness.ts, against a
//     server that answers by offset. Nothing here can be satisfied by a
//     rewritten condition.
//   * Wiring read out of the source. `test:unit` is node --test with no DOM and
//     no way to evaluate a .svelte file, so for the parts that live in
//     components this is what can be measured: that the wiring is present. Each
//     one cuts out the region it is asking about first -- a pattern let loose on
//     a whole file is answered by some other occurrence in it.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative } from 'node:path';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';

import {
	alignHistoryOffset,
	historyNavDisabled,
	historyNavPosition,
	historyNavTarget,
	historyPageTarget,
	resolveStripSelection,
	type HistoryNavState
} from './historyNavigation.ts';
import { HistoryManagerState, refreshDerived, works } from './history-manager-harness.ts';

// ── reading the product's own source ────────────────────────────────────────

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, '..', '..');
const read = (rel: string): string => readFileSync(join(WEB, 'src', rel), 'utf8');

const JA = read('lib/i18n/ja.ts');
const EN = read('lib/i18n/en.ts');
const TYPES = read('lib/i18n/types.ts');
const PAGE = read('routes/+page.svelte');
const BROWSING = read('lib/features/history/browsing-state.svelte.ts');
const CANVAS = read('lib/components/CanvasPanel.svelte');
const STRIP = read('lib/components/HistoryStrip.svelte');
const MODAL = read('lib/components/HistoryManager.svelte');

/** The value of a plain string key, so a gate can read what the UI will show. */
function i18nValue(pack: string, key: string): string | null {
	const found = pack.match(new RegExp(`\\n\\t${key}: '([^']*)',`));
	return found ? found[1] : null;
}

/**
 * One function's body, cut out before anything is matched inside it.
 *
 * The closing brace is found by indentation, which is what tells a top-level
 * function in these files apart from every block nested in it.
 */
function bodyOf(source: string, header: string, closer = '\n\t}'): string {
	const start = source.indexOf(header);
	assert.ok(start >= 0, `not found in the source: ${header}`);
	const from = start + header.length;
	const end = source.indexOf(closer, from);
	assert.ok(end > from, `no closing brace found for: ${header}`);
	return source.slice(from, end);
}

/** The markup of one component element, from its tag to the `/>` that ends it. */
function elementOf(source: string, tag: string): string {
	const start = source.indexOf(`<${tag}`);
	assert.ok(start >= 0, `not found in the source: <${tag}`);
	const end = source.indexOf('\n\t\t\t/>', start);
	assert.ok(end > start, `no closing /> found for: <${tag}`);
	return source.slice(start, end);
}

/** Every `<button>` tag in a region, whole, so its attributes can be read. */
function buttonsIn(region: string): string[] {
	return region.match(/<button[^>]*>/g) ?? [];
}

// ── the state the rules are read from ───────────────────────────────────────

/** 83 works, 15 to a screen -- the listing the contract's tables were measured on. */
const strip = (over: Partial<HistoryNavState> = {}): HistoryNavState =>
	({ cursor: 5, offset: 0, total: 83, windowSize: 15, ...over });

// ── T-1 ─────────────────────────────────────────────────────────────────────
test('T-1  the six direction keys are named and worded for newer and older, and the old names are gone', () => {
	const expected: Record<string, [string, string]> = {
		historyNewer: ['← 新しい', '← newer'],
		historyOlder: ['古い →', 'older →'],
		tooltipCanvasNavNewer: ['新しい作品へ', 'To the newer work'],
		tooltipCanvasNavOlder: ['古い作品へ', 'To the older work'],
		tooltipHistoryNewerPage: ['1ページ新しい方へ', 'One page newer'],
		tooltipHistoryOlderPage: ['1ページ古い方へ', 'One page older']
	};
	for (const [key, [ja, en]] of Object.entries(expected)) {
		assert.equal(i18nValue(JA, key), ja, `ja.ts ${key}`);
		assert.equal(i18nValue(EN, key), en, `en.ts ${key}`);
		assert.match(TYPES, new RegExp(`\\n\\t${key}: string;`), `types.ts ${key}`);
	}

	// The whole point of the renaming: a direction key must not say "prev" or
	// "next", in either language, because those name a place in a sequence and
	// the two boxes had read the sequence in opposite directions.
	for (const [key, [ja, en]] of Object.entries(expected)) {
		for (const word of ['前', '次', 'prev', 'next']) {
			assert.ok(!ja.toLowerCase().includes(word), `ja ${key} still says ${word}: ${ja}`);
			assert.ok(!en.toLowerCase().includes(word), `en ${key} still says ${word}: ${en}`);
		}
	}

	const gone = ['historyPrev', 'historyNext', 'tooltipCanvasNavPrev', 'tooltipCanvasNavNext',
		'tooltipHistoryPrevPage', 'tooltipHistoryNextPage'];
	for (const key of gone) {
		for (const [name, pack] of [['ja.ts', JA], ['en.ts', EN], ['types.ts', TYPES]] as const) {
			assert.ok(!new RegExp(`\\b${key}\\b`).test(pack), `${name} still holds ${key}`);
		}
	}
});

// ── T-2 ─────────────────────────────────────────────────────────────────────
test('T-2  every canvas nav tooltip names the direction its own button moves', () => {
	// Read as pairs: a Tooltip's text key and the first onclick after it, which
	// is the button that tooltip belongs to. Four of them, in both the ordinary
	// canvas and the presentation overlay.
	const pairs = [...CANVAS.matchAll(/text=\{t\(\)\.(tooltipCanvasNav\w+)\}[\s\S]*?onclick=\{(onGoto\w+)\}/g)]
		.map((m) => [m[1], m[2]] as const);
	const directional = pairs.filter(([key]) => key !== 'tooltipCanvasNavLatest');
	assert.equal(directional.length, 4, `expected four directional nav buttons, read ${JSON.stringify(directional)}`);
	for (const [key, handler] of directional) {
		const shouldBe = handler === 'onGotoNext' ? 'tooltipCanvasNavNewer' : 'tooltipCanvasNavOlder';
		assert.equal(key, shouldBe, `${handler} is labelled ${key}`);
	}
	assert.equal(directional.filter(([k]) => k === 'tooltipCanvasNavNewer').length, 2);
	assert.equal(directional.filter(([k]) => k === 'tooltipCanvasNavOlder').length, 2);
});

// ── T-3 ─────────────────────────────────────────────────────────────────────
test('T-3  in presentation mode the screen reader is told what the tooltip says', () => {
	const controls = CANVAS.slice(CANVAS.indexOf('class="presentation-controls"'));
	const chunks = controls.split('<Tooltip').filter((c) => /onclick=\{onGoto(Next|Prev)\}/.test(c));
	assert.equal(chunks.length, 2, 'expected the two directional buttons of the overlay');
	for (const chunk of chunks) {
		const tooltipKey = chunk.match(/text=\{t\(\)\.(\w+)\}/)?.[1];
		const ariaKey = chunk.match(/aria-label=\{t\(\)\.(\w+)/)?.[1];
		assert.ok(tooltipKey, 'the button has no tooltip key');
		assert.ok(ariaKey, 'the button has no aria-label key');
		// Same key, not merely the same wording: two keys that agree today are
		// two keys that can be edited apart tomorrow, which is how the label came
		// to read out the opposite of the way the button moves.
		assert.equal(ariaKey, tooltipKey);
	}
});

// ── T-4 ─────────────────────────────────────────────────────────────────────
test('T-4  the button that goes to the end of the listing is called oldest, not first', () => {
	assert.equal(i18nValue(JA, 'historyOldest'), '最古');
	assert.equal(i18nValue(EN, 'historyOldest'), 'Oldest');
	assert.equal(i18nValue(JA, 'tooltipHistoryOldestPage'), '最も古いページへ');
	assert.equal(i18nValue(EN, 'tooltipHistoryOldestPage'), 'To the oldest page');
	for (const [name, pack] of [['ja.ts', JA], ['en.ts', EN], ['types.ts', TYPES]] as const) {
		assert.ok(!/\bhistoryFirst\b/.test(pack), `${name} still holds historyFirst`);
		assert.ok(!/\btooltipHistoryFirstPage\b/.test(pack), `${name} still holds tooltipHistoryFirstPage`);
	}
	// Both pagers in the modal -- the ordinary listing and the lineage groups.
	assert.equal((MODAL.match(/\{t\(\)\.historyOldest\}/g) ?? []).length, 2);
	assert.ok(!/historyFirst/.test(MODAL));
});

// ── T-5 ─────────────────────────────────────────────────────────────────────
test('T-5  with nothing selected all three canvas buttons can still be pressed', () => {
	const disabled = historyNavDisabled({ cursor: -1, offset: 0, total: 83, windowSize: 15 });
	assert.deepEqual(disabled, { latest: false, newer: false, older: false });
	assert.equal(historyNavPosition({ cursor: -1, offset: 0, total: 83, windowSize: 15 }), -1);
});

// ── T-6 ─────────────────────────────────────────────────────────────────────
test('T-6  with no works at all, none of them can', () => {
	assert.deepEqual(
		historyNavDisabled(strip({ total: 0, cursor: -1 })),
		{ latest: true, newer: true, older: true }
	);
	assert.deepEqual(
		historyNavDisabled(strip({ total: 0, cursor: 0 })),
		{ latest: true, newer: true, older: true }
	);
});

// ── T-7 ─────────────────────────────────────────────────────────────────────
test('T-7  latest is counted in works, so the top of page two is not the latest', () => {
	assert.deepEqual(
		historyNavDisabled(strip({ cursor: 0, offset: 0 })),
		{ latest: true, newer: true, older: false }
	);
	// The same cursor one page down is the sixteenth work, not the newest one.
	assert.deepEqual(
		historyNavDisabled(strip({ cursor: 0, offset: 15 })),
		{ latest: false, newer: false, older: false }
	);
});

// ── T-8 ─────────────────────────────────────────────────────────────────────
test('T-8  only the oldest work switches off the older button, and only it', () => {
	// total - 1: the last work there is.
	assert.deepEqual(
		historyNavDisabled(strip({ offset: 75, cursor: 7 })),
		{ latest: false, newer: false, older: true }
	);
	// One newer than that. Both sides of the boundary, so an off-by-one shows.
	assert.deepEqual(
		historyNavDisabled(strip({ offset: 75, cursor: 6 })),
		{ latest: false, newer: false, older: false }
	);
});

// ── T-9 ─────────────────────────────────────────────────────────────────────
test('T-9  from no selection, every direction arrives at the newest work', () => {
	const state = strip({ cursor: -1 });
	for (const button of ['latest', 'newer', 'older'] as const) {
		const target = historyNavTarget(state, button);
		assert.ok(target, `${button} gave no target`);
		// Stated as a global index, which is what all three boxes share: offset
		// plus the position within the page must come to work number zero.
		assert.notEqual(target.select, 'oldest-on-page');
		assert.equal(target.offset + (target.select as number), 0, `${button} landed elsewhere`);
	}
});

// ── T-10 ────────────────────────────────────────────────────────────────────
test('T-10  the page decides nothing about navigation by itself', () => {
	assert.ok(!PAGE.includes("from '$lib/historyNavigation'"), 'the page still imports the decision module');
	for (const fn of ['historyNavDisabled(', 'historyNavTarget(', 'historyPageTarget(', 'alignHistoryOffset(']) {
		assert.ok(BROWSING.includes(fn), `the browsing owner never calls ${fn}`);
		assert.ok(!PAGE.includes(fn), `+page.svelte still calls ${fn}`);
	}
	// Importing the module and then working the answer out anyway is exactly the
	// failure this contract is guarding against: the judgement moves out, the
	// thoroughfare stays where it was, and every rule gate above goes on passing.
	assert.ok(!/prevDisabled/.test(PAGE), '+page.svelte still builds prevDisabled');
	assert.ok(!/nextDisabled/.test(PAGE), '+page.svelte still builds nextDisabled');
});

// ── T-11 ────────────────────────────────────────────────────────────────────
test("T-11  the strip's Latest is no longer decided by which page it is on", () => {
	const latest = buttonsIn(STRIP).filter((b) => b.includes('history-latest-btn'));
	assert.equal(latest.length, 1);
	const disabled = latest[0].match(/disabled=\{([^}]*)\}/)?.[1];
	assert.ok(disabled, 'the Latest button has no disabled condition');
	assert.ok(!disabled.includes('historyPage'), `still counted in pages: ${disabled}`);
	// The demo lock stays in front of it, as it is in front of everything here.
	assert.ok(disabled.includes('interactionLocked'), `the demo lock was dropped: ${disabled}`);
});

// ── T-12 ────────────────────────────────────────────────────────────────────
test('T-12  a page back lands on the work next to the one that was on screen', () => {
	const newer = historyPageTarget(strip({ offset: 30, cursor: 0 }), 'newer');
	assert.deepEqual(newer, { offset: 15, select: 'oldest-on-page' });
	const older = historyPageTarget(strip({ offset: 30, cursor: 0 }), 'older');
	assert.deepEqual(older, { offset: 45, select: 0 });

	// And the page reads that decision rather than keeping its own. Landing on
	// the newest work of the newer page -- what this did before -- stepped over
	// everything between the two screens.
	const body = bodyOf(PAGE, 'async function gotoHistoryNewerPage(): Promise<void> {');
	assert.ok(!/loadIteration\(0\)/.test(body), `gotoHistoryNewerPage still lands on 0:\n${body}`);
});

// ── T-13 ────────────────────────────────────────────────────────────────────
test('T-13  a window that grows re-seats the offset, and no work falls between the screens', () => {
	// The measured example: ten thumbnails to a screen becoming twelve, standing
	// at offset 70. Left alone, "newer" fetched offset 48 and works 60 to 69
	// appeared on neither screen.
	const seated = alignHistoryOffset(70, 12, 83);
	assert.equal(seated, 60);

	const after = strip({ offset: seated, windowSize: 12, cursor: 0 });
	assert.equal(historyPageTarget(after, 'newer')?.offset, 48);
	assert.equal(historyPageTarget(after, 'older')?.offset, 72);

	// Stated as coverage rather than as three numbers: every work from the newer
	// screen's first to the older screen's last is on one of the three screens.
	const seen = new Set<number>();
	for (const offset of [48, seated, 72]) {
		for (let i = offset; i < Math.min(offset + 12, 83); i += 1) seen.add(i);
	}
	for (let i = 48; i < 84 && i < 83; i += 1) assert.ok(seen.has(i), `work ${i} is on no screen`);
});

// ── T-14 ────────────────────────────────────────────────────────────────────
test('T-14  a re-seated offset is always on the grid and never past the last page', () => {
	for (const windowSize of [1, 7, 10, 12, 15, 21]) {
		for (const total of [0, 1, 12, 83, 500]) {
			for (const offset of [0, 3, 70, 499, 10_000]) {
				const seated = alignHistoryOffset(offset, windowSize, total);
				assert.equal(seated % windowSize, 0, `${offset}/${windowSize}/${total} is off the grid`);
				assert.ok(seated >= 0);
				const lastPage = Math.floor(Math.max(0, total - 1) / windowSize) * windowSize;
				assert.ok(seated <= lastPage, `${offset}/${windowSize}/${total} is past the last page`);
			}
		}
	}
	// The listing shrank under the strip: page six of the old one does not exist.
	assert.equal(alignHistoryOffset(70, 12, 12), 0);
	assert.equal(alignHistoryOffset(70, 15, 12), 0);
});

// ── T-15 ────────────────────────────────────────────────────────────────────
test('T-15  every test that existed before this contract still runs and still passes', () => {
	// Run for real, and counted from the run rather than from the names in the
	// files: a rename plus an inversion reads as a deletion when counted by name,
	// and a test deleted outright reads as nothing at all.
	//
	// This file is left out of the child run -- including it would be this test
	// running itself -- so what the child reports is the suite as it stood
	// before this contract, and the new gates are answered for by the run that
	// is reading this line.
	const BASELINE = 191; // measured on 4f3e5193, the branch point
	const childEnv = () => {
		const env = { ...process.env, INKU_NAV_SUITE_CHILD: '1' };
		for (const key of Object.keys(env)) if (key.startsWith('NODE_TEST')) delete env[key];
		return env;
	};
	const files: string[] = [];
	const walk = (dir: string) => {
		for (const entry of readdirSync(dir, { withFileTypes: true })) {
			const full = join(dir, entry.name);
			if (entry.isDirectory()) walk(full);
			else if (entry.name.endsWith('.test.ts')) files.push(full);
		}
	};
	walk(join(WEB, 'src'));
	const others = files.filter((f) => f !== fileURLToPath(import.meta.url));
	assert.equal(others.length, files.length - 1, 'this file was not excluded from the child run');

	const run = spawnSync(
		process.execPath,
		['--import', './scripts/ts-extensionless-resolve.mjs', '--test', '--test-reporter=tap',
			...others.map((f) => relative(WEB, f))],
		// NODE_TEST_CONTEXT is how the runner tells a process it is already inside
		// one. Inherited, the child reports "skipping running files" and runs
		// nothing at all, which would leave this gate reading an empty tally.
		{ cwd: WEB, encoding: 'utf8', env: childEnv() }
	);
	const out = `${run.stdout ?? ''}${run.stderr ?? ''}`;
	const pass = Number(out.match(/^# pass (\d+)$/m)?.[1]);
	const fail = Number(out.match(/^# fail (\d+)$/m)?.[1]);
	assert.ok(Number.isFinite(pass) && Number.isFinite(fail), `could not read the child's tally:\n${out.slice(-2000)}`);
	assert.equal(fail, 0, `${fail} of the tests that were here before this contract now fail`);
	assert.ok(pass >= BASELINE, `${pass} passing, ${BASELINE} before this contract`);
});

// ── T-16 ────────────────────────────────────────────────────────────────────
test('T-16  the English vocabulary guard is clean', () => {
	const run = spawnSync(process.execPath, ['scripts/i18n-lint.mjs'], { cwd: WEB, encoding: 'utf8' });
	const out = `${run.stdout ?? ''}${run.stderr ?? ''}`;
	assert.equal(run.status, 0, out.slice(-2000));
	const tally = out.match(/i18n-lint: (\d+) English strings, (\d+) allowed exceptions, (\d+) warnings, (\d+) errors/);
	assert.ok(tally, `no summary line:\n${out.slice(-2000)}`);
	assert.equal(Number(tally[3]), 0, 'warnings');
	assert.equal(Number(tally[4]), 0, 'errors');
});

// ── the manager, driven for real ────────────────────────────────────────────

const CORPUS_TOTAL = 500;
const CORPUS = works(CORPUS_TOTAL, 'work');
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

/** Global index of a work, read back out of the id the corpus gave it. */
const numberOf = (item: { id?: string }): number => Number(item.id!.slice('work-'.length));

/**
 * A manager whose server answers by offset, and which can be told to hold one
 * answer back so a second question arrives while the first is still out.
 */
function makeCorpusManager() {
	const offsets: number[] = [];
	let held: (() => void) | null = null;
	let holdOffset: number | null = null;
	const apiFetch = async (path: string) => {
		const asked = new URL(path, 'http://localhost');
		const offset = Number(asked.searchParams.get('offset'));
		const limit = Number(asked.searchParams.get('limit'));
		offsets.push(offset);
		if (holdOffset === offset) {
			holdOffset = null;
			await new Promise<void>((resolve) => { held = resolve; });
		}
		return {
			ok: true,
			json: async () => ({ items: CORPUS.slice(offset, offset + limit), total: CORPUS_TOTAL })
		} as unknown as Response;
	};
	const manager = new HistoryManagerState(apiFetch, () => {});
	return {
		manager,
		offsets,
		hold: (offset: number) => { holdOffset = offset; },
		release: () => { held?.(); held = null; }
	};
}

/**
 * A manager standing on the given page, with that page's works in hand.
 *
 * The page size is seeded rather than set: setPageSize is what four of the
 * gates below are measuring, and a setup that went through it would report
 * every fault in it as a broken setup instead of as the fault it is.
 */
async function managerAt(pageSize: number, page: number) {
	const made = makeCorpusManager();
	made.manager.seedFromStrip([], CORPUS_TOTAL, 0, pageSize);
	refreshDerived(made.manager);
	made.manager.setPage(page);
	await settle();
	refreshDerived(made.manager);
	assert.equal(made.manager.offset, page * pageSize, 'setup: the manager is not where it was put');
	assert.equal(numberOf(made.manager.items[0]), page * pageSize, 'setup: the works are not the page');
	made.offsets.length = 0;
	return made;
}

// ── T-17 ────────────────────────────────────────────────────────────────────
test('T-17  a modal that gets smaller fetches the works its numbers now name', async () => {
	// Measured before the fix: the grid going from 52 to 40 moved offset from 156
	// to 120 and fetched nothing, so the modal said "121-160" over works 156-207.
	const { manager, offsets } = await managerAt(52, 3);
	manager.setPageSize(40);
	await settle();
	refreshDerived(manager);
	assert.equal(offsets.length, 1, `expected one fetch, got ${JSON.stringify(offsets)}`);
	assert.equal(manager.offset, 120);
	assert.equal(numberOf(manager.items[0]), manager.offset);
});

// ── T-18 ────────────────────────────────────────────────────────────────────
test('T-18  and so does one that gets bigger', async () => {
	const { manager } = await managerAt(40, 3);
	manager.setPageSize(52);
	await settle();
	refreshDerived(manager);
	assert.equal(manager.offset, 156);
	assert.equal(numberOf(manager.items[0]), manager.offset);
});

// ── T-19 ────────────────────────────────────────────────────────────────────
test('T-19  a page size that has not changed costs nothing', async () => {
	const { manager, offsets } = await managerAt(52, 3);
	manager.setPageSize(52);
	await settle();
	assert.deepEqual(offsets, []);
});

// ── T-20 ────────────────────────────────────────────────────────────────────
test('T-20  a request still out does not answer for a different place in the listing', async () => {
	// The duplicate-request guard is what makes opening the manager cost one page
	// instead of two, and it used to match on the page number. A page number is a
	// place divided by a page size, and when the size changes underneath it the
	// same number names somewhere else -- so the request for 120 was dropped as
	// already-asked and the answer for 156 arrived in its place.
	const made = makeCorpusManager();
	made.manager.seedFromStrip([], CORPUS_TOTAL, 0, 52);
	refreshDerived(made.manager);

	made.hold(156);
	made.manager.setPage(3);
	await settle();
	assert.deepEqual(made.offsets, [156], 'setup: the page-3 request did not go out and hang');

	made.manager.setPageSize(40);
	await settle();
	assert.ok(made.offsets.includes(120), `offset 120 was never asked for: ${JSON.stringify(made.offsets)}`);
	made.release();
	await settle();
});

// ── T-21 ────────────────────────────────────────────────────────────────────
test('T-21  while a listing is on its way, nothing may be pressed', () => {
	const busy = strip({ busy: true });
	assert.deepEqual(historyNavDisabled(busy), { latest: true, newer: true, older: true });
	// And it lets go again -- a flag that decided the answer for good would pass
	// the line above and switch the buttons off forever.
	assert.deepEqual(
		historyNavDisabled(strip({ busy: false })),
		{ latest: false, newer: false, older: false }
	);
	assert.equal(historyPageTarget(busy, 'older'), null);
});

// ── T-22 ────────────────────────────────────────────────────────────────────
test("T-22  a late listing answer cannot put its page back over a newer one", () => {
	const body = bodyOf(BROWSING, 'async fetchOffset(offset: number');
	const assignAt = body.indexOf('this.items = stripItems');
	assert.ok(assignAt > 0, 'the strip is no longer written where this gate is looking');
	const lastAwait = body.lastIndexOf('await ', assignAt);
	assert.ok(lastAwait > 0, 'nothing is awaited before the strip is written');
	const guard = /if \(requestId !== this\.fetchRequest\) return/g;
	const guards = [...body.matchAll(guard)].map((m) => m.index!);
	assert.ok(guards.length > 0, 'the listing fetch takes no request number');
	// Between the last await and the assignment, not merely somewhere above it:
	// a check that has an await after it is a check that has been overtaken.
	assert.ok(
		guards.some((at) => at > lastAwait && at < assignAt),
		'the strip is written without checking that this is still the current request'
	);
});

// ── T-23 ────────────────────────────────────────────────────────────────────
test('T-23  and neither can a late trash answer', () => {
	const body = bodyOf(BROWSING, 'async fetchTrashPage(): Promise<void> {');
	const assignAt = body.indexOf('this.trashItems = data.items');
	assert.ok(assignAt > 0, 'the trash list is no longer written where this gate is looking');
	const lastAwait = body.lastIndexOf('await ', assignAt);
	assert.ok(lastAwait > 0);
	const guards = [...body.matchAll(/if \(requestId !== this\.trashRequest\) return/g)].map((m) => m.index!);
	assert.ok(guards.length > 0, 'the trash fetch takes no request number');
	assert.ok(guards.some((at) => at > lastAwait && at < assignAt));
});

// ── T-24 ────────────────────────────────────────────────────────────────────
test('T-24  a tab chosen while the page was arriving is not put back', () => {
	for (const header of ['async function gotoPrev() {', 'async function gotoNext() {']) {
		const body = bodyOf(PAGE, header);
		const copiedAt = body.indexOf('const preservedTab = outputTab');
		assert.ok(copiedAt > 0, `${header} no longer keeps the tab`);
		const firstAwait = body.indexOf('await ');
		assert.ok(firstAwait > 0, `${header} awaits nothing`);
		// Read before the await and written back after it, the copy is a snapshot
		// taken across a suspension: whatever the user did in between is undone.
		assert.ok(copiedAt > firstAwait, `${header} still copies the tab before it waits`);
	}
});

// ── T-25 ────────────────────────────────────────────────────────────────────
test('T-25  during a demo, nothing may be pressed', () => {
	const locked = strip({ locked: true });
	assert.deepEqual(historyNavDisabled(locked), { latest: true, newer: true, older: true });
	assert.deepEqual(
		historyNavDisabled(strip({ locked: false })),
		{ latest: false, newer: false, older: false }
	);
	assert.equal(historyPageTarget(locked, 'newer'), null);
	assert.equal(historyNavTarget(locked, 'older'), null);
});

// ── T-26 ────────────────────────────────────────────────────────────────────
test('T-26  the demo lock reaches the canvas, and every nav button on it', () => {
	// It never used to: `interactionLocked` was handed to the strip alone, and
	// the canvas arrows went on working through a demo. The last guard inside
	// loadIteration stopped the work from changing but not the page from moving,
	// so the strip turned a page and the "current" frame sat on another work.
	const element = elementOf(PAGE, 'CanvasPanel');
	assert.match(element, /interactionLocked=\{demoRunning\}/);

	const nav = buttonsIn(CANVAS).filter((b) => /onclick=\{onGoto(Next|Prev|Latest)\}/.test(b));
	assert.equal(nav.length, 6, `expected six nav buttons on the canvas, found ${nav.length}`);
	for (const button of nav) {
		const disabled = button.match(/disabled=\{([^}]*)\}/)?.[1];
		assert.ok(disabled, `a nav button has no disabled condition: ${button}`);
		assert.ok(disabled.includes('interactionLocked'), `the demo lock is missing from: ${button}`);
	}
});

// ── T-27 ────────────────────────────────────────────────────────────────────
test('T-27  clearing the starred filter for the user is said out loud', () => {
	const body = bodyOf(BROWSING, 'async syncToItem(');
	const clearedAt = body.indexOf('this.starredOnly = false;');
	assert.ok(clearedAt > 0, 'the rescue no longer clears the filter');
	// The same block, not merely the same function: a notice further down would
	// fire on routes that never cleared anything.
	const blockEnd = body.indexOf('\n\t\t}', clearedAt);
	assert.ok(blockEnd > clearedAt);
	const block = body.slice(clearedAt, blockEnd);
	assert.match(block, /this\.deps\.onStarredFilterCleared\(\)/);

	for (const [name, pack] of [['ja.ts', JA], ['en.ts', EN], ['types.ts', TYPES]] as const) {
		assert.match(pack, /\bhistoryStarredFilterClearedNotice\b/, `${name} has no string for it`);
	}
	assert.ok(i18nValue(JA, 'historyStarredFilterClearedNotice'));
	assert.ok(i18nValue(EN, 'historyStarredFilterClearedNotice'));
});

// ── T-28 ────────────────────────────────────────────────────────────────────
test('T-28  the strip hands over the work that was pressed, not where it was sitting', () => {
	assert.match(STRIP, /onLoadItem: \(item: HistoryItem\) => void;/);
	assert.ok(!/onLoadIteration/.test(STRIP), 'the strip still hands over a position');
	assert.match(STRIP, /function handleThumbKeydown\(event: KeyboardEvent, item: HistoryItem\)/);
	// Both routes into a work: the pointer and the keyboard.
	assert.ok(!/onLoadItem\(i\)/.test(STRIP), 'the click still passes the position');
	assert.ok(!/handleThumbKeydown\(event, i\)/.test(STRIP), 'the keyboard still passes the position');
	assert.match(STRIP, /onLoadItem\(it\)/);
	assert.match(STRIP, /handleThumbKeydown\(event, it\)/);
});

// ── T-29 ────────────────────────────────────────────────────────────────────
test('T-29  a work is found again after the listing has shifted under it', () => {
	const before = CORPUS.slice(0, 15);
	const pressed = before[3];
	assert.equal(resolveStripSelection(before, pressed), 3);

	// A save in another window is taken in at the front every twelve seconds.
	const after = [{ ...CORPUS[0], id: 'work-new' }, ...before].slice(0, 15);
	assert.equal(resolveStripSelection(after, pressed), 4);

	// And off the end of the strip it is honestly not there.
	const gone = CORPUS.slice(60, 75);
	assert.equal(resolveStripSelection(gone, pressed), -1);
	assert.equal(resolveStripSelection(before, { id: undefined }), -1);
});

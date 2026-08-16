// Run with: npm run test:unit  (node:test, no test dependency)
//
// A DDL's language and the UI's language are independent. `instruction_lang`
// is resolved from the text, so a Japanese UI can be editing an English DDL --
// and until now the DDL editor offered its words in the UI's language, which
// meant it offered `円` to someone writing `a thin line`. A word taken from
// that panel is inserted into the DDL, so the panel offering the other
// language is offering the wrong word.
//
// T-90: the language of a text is read the way the server reads it.
// T-91: the DDL editor's words follow the DDL, not the UI, and follow it live.
// T-92: in the preview, the effect is the reader's language and the example --
//       a fragment of DDL -- is the word's.
// T-93: the saijiki drawer is not an editor, so its words stay the UI's.
// T-94: the vocabulary lint counts labels, and a language code is not one.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { instructionLangOf, resolveInstructionLang } from './instructionLang.ts';
import { localizePreview } from './saijiki-surface.ts';
import { saijikiWordsFor } from './saijiki.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (relative: string) => fs.readFileSync(path.join(here, relative), 'utf8');

const INLINE = './components/SaijikiInline.svelte';
const DIALOG = './components/DdlEditorDialog.svelte';
const DRAWER = './components/SaijikiDrawer.svelte';
const PAGE = '../routes/+page.svelte';

// ------------------------------------------------ T-90 (the server's reading)

// server/src/inku_server/language_support/registry.py: Japanese is tested
// first, Latin second, and a text carrying neither takes the fallback. The
// order is the judgment -- a text with both is Japanese -- so it is what these
// cases pin, not merely the two easy ends.
test('T-90: a text with any Japanese in it is Japanese, whatever else it has', () => {
	assert.equal(resolveInstructionLang('細い線を引く', 'en'), 'ja');
	assert.equal(resolveInstructionLang('a thin 線', 'en'), 'ja');
	assert.equal(resolveInstructionLang('Nature.風 twice', 'en'), 'ja');
	// Each of the three ranges the server names, on its own.
	assert.equal(resolveInstructionLang('ひ', 'en'), 'ja', 'hiragana');
	assert.equal(resolveInstructionLang('ヒ', 'en'), 'ja', 'katakana');
	assert.equal(resolveInstructionLang('線', 'en'), 'ja', 'kanji');
});

test('T-90: a text with no Japanese but some Latin is English', () => {
	assert.equal(resolveInstructionLang('a thin line, drawn twice', 'ja'), 'en');
	assert.equal(resolveInstructionLang('3 circles', 'ja'), 'en');
});

test('T-90: a text that says neither takes the fallback, either way', () => {
	for (const text of ['', '   ', '3 + 4', '——', '\n\n']) {
		assert.equal(resolveInstructionLang(text, 'ja'), 'ja', text);
		assert.equal(resolveInstructionLang(text, 'en'), 'en', text);
	}
});

test('T-90: the UI language is narrowed to a fallback the way the server narrows it', () => {
	assert.equal(instructionLangOf('ja'), 'ja');
	assert.equal(instructionLangOf('en'), 'en');
	// `fallback = ui_lang if ui_lang in SUPPORTED_INSTRUCTION_LANGS else "ja"`.
	for (const other of ['fr', '', null, undefined, 'auto', 'JA']) {
		assert.equal(instructionLangOf(other), 'ja', String(other));
	}
});

// ------------------------------------------- T-91 (the words follow the DDL)

test('T-91: the vocabulary has an English surface for the words to switch to', () => {
	// Both halves must exist, or "switch to English" has nothing to switch to.
	const ja = saijikiWordsFor('katachi', true);
	const en = saijikiWordsFor('katachi', false);
	assert.ok(ja.includes('円'), 'the Japanese surface lost 円');
	assert.ok(en.includes('circle'), 'the English surface lost circle');
	assert.equal(ja.length, en.length, 'the two surfaces are paired by position');
	assert.notDeepEqual(ja, en);
});

test('T-91: an English DDL under a Japanese UI resolves to the English words', () => {
	const uiLang = instructionLangOf('ja');
	const wordLang = resolveInstructionLang('a thin line, drawn twice', uiLang);
	assert.equal(wordLang, 'en');
	assert.ok(saijikiWordsFor('katachi', wordLang === 'ja').includes('circle'));
	// And the other way: a Japanese DDL under an English UI.
	const back = resolveInstructionLang('細い線を二度引く', instructionLangOf('en'));
	assert.equal(back, 'ja');
	assert.ok(saijikiWordsFor('katachi', back === 'ja').includes('円'));
});

test('T-91: the panel takes the language it offers, and no longer reads the UI', () => {
	const inline = read(INLINE);
	// The chips are built from the prop, not from the UI language pack.
	assert.match(inline, /saijikiWordsFor\(cat\.key, wordLang === 'ja'\)/);
	assert.doesNotMatch(
		inline,
		/t\(\)\.code/,
		'the inline panel still decides its words from the UI language'
	);
	assert.match(inline, /wordLang: ResolvedInstructionLang;/, 'wordLang is not a declared prop');
	// Required, not defaulted: a default would let a caller keep the old
	// behaviour silently, which is the failure this is guarding against.
	assert.doesNotMatch(inline, /wordLang\s*=\s*['"]/, 'wordLang has a default');
});

test('T-91: the editor resolves the language from the text it is holding, live', () => {
	const dialog = read(DIALOG);
	// `value` is the textarea's live content; `initialDdl` is what it opened
	// with. Reading the latter would freeze the words at open time, so a
	// rewrite from one language to the other would never switch them.
	assert.match(dialog, /const wordLang = \$derived\(resolveInstructionLang\(value, isJapanese \? 'ja' : 'en'\)\)/);
	assert.doesNotMatch(dialog, /resolveInstructionLang\(initialDdl/);
	// And it hands that language to the panel.
	const panel = dialog.slice(dialog.indexOf('<SaijikiInline'), dialog.indexOf('/>', dialog.indexOf('<SaijikiInline')));
	assert.match(panel, /\{wordLang\}/, 'the editor does not hand its language to the panel');
});

// --------------------------------- T-92 (the example is DDL, the effect is not)

test('T-92: the effect follows the reader and the example follows the word', () => {
	const entry = {
		effect: '一本の線を引きます。',
		effectEn: 'Draws a single line.',
		example: '太い線を引く',
		exampleEn: 'a thick line',
	};
	// The case this contract is about: Japanese UI, English DDL.
	assert.deepEqual(localizePreview(entry, { uiLang: 'ja', wordLang: 'en' }), {
		effect: '一本の線を引きます。',
		example: 'a thick line',
	});
	// The mirror, and the two where they agree.
	assert.deepEqual(localizePreview(entry, { uiLang: 'en', wordLang: 'ja' }), {
		effect: 'Draws a single line.',
		example: '太い線を引く',
	});
	assert.deepEqual(localizePreview(entry, { uiLang: 'ja', wordLang: 'ja' }), {
		effect: '一本の線を引きます。',
		example: '太い線を引く',
	});
	assert.deepEqual(localizePreview(entry, { uiLang: 'en', wordLang: 'en' }), {
		effect: 'Draws a single line.',
		example: 'a thick line',
	});
});

test('T-92: both preview builders take the word language and split the two texts', () => {
	const page = read(PAGE);
	const builtIn = page.slice(
		page.indexOf('function saijikiPreview('),
		page.indexOf('const PLUGIN_FALLBACK_SVG')
	);
	assert.ok(builtIn.length > 0, 'saijikiPreview moved');
	assert.match(builtIn, /word: string, wordLang: ResolvedInstructionLang\)/);
	// Every language choice in the built-in builder goes through the rule, so
	// no example can quietly keep following the UI.
	assert.doesNotMatch(builtIn, /isJa/, 'a language choice bypasses localizePreview');
	assert.equal(
		(builtIn.match(/localizePreview\(/g) ?? []).length,
		2,
		'the table entry and the unknown-word fallback do not both use the rule'
	);

	const plugin = page.slice(page.indexOf('function pluginPreview('), page.indexOf('// ── Color catalog'));
	assert.ok(plugin.length > 0, 'pluginPreview moved');
	assert.match(plugin, /wordLang: ResolvedInstructionLang\): SaijikiPreview/);
	// The note explains; the firing phrase is what a description would say.
	assert.match(plugin, /wordLang === 'ja' \? entry\.fires_on_ja : entry\.fires_on_en/);
	assert.match(plugin, /uiLang === 'ja' \? entry\.note_ja : entry\.note_en/);
});

// ------------------------------------------- T-93 (the drawer is unchanged)

test('T-94: the vocabulary lint does not count a language code as a label', () => {
	const lint = fs.readFileSync(path.join(here, '../../scripts/i18n-lint.mjs'), 'utf8');
	assert.match(lint, /const isLangCodePair = \(ja, en\) => ja === 'ja' && en === 'en';/);
	assert.match(lint, /if \(re !== BILINGUAL_LABEL && isLangCodePair\(m\[1\], m\[2\]\)\) continue;/);
	// Not a vacuous guard: the tree really does hold such ternaries, so the
	// inventory really was counting them. Two when this was written -- the DDL
	// editor's fallback language and the okugaki request's `language` field --
	// and the count is left open upward, since a third is not a regression.
	const pairs: string[] = [];
	const walk = (dir: string) => {
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) walk(full);
			else if (/\.(svelte|ts)$/.test(entry.name) && !entry.name.endsWith('.test.ts')) {
				if (/isJapanese \? 'ja' : 'en'/.test(fs.readFileSync(full, 'utf8'))) pairs.push(full);
			}
		}
	};
	walk(here);
	walk(path.join(here, '../routes'));
	assert.ok(pairs.length >= 2, `only ${pairs.length} language-code ternaries; the guard may be unreached`);
});

test('T-93: the saijiki drawer still offers the reader their own language', () => {
	const drawer = read(DRAWER);
	// No DDL is being written in the drawer, so there is no other language for
	// it to follow. It now says so instead of relying on the callee's default.
	assert.match(drawer, /const wordLang = \$derived\(instructionLangOf\(getLang\(\)\)\)/);
	assert.match(drawer, /saijikiWordsFor\(cat\.key, wordLang === 'ja'\)/);
	assert.doesNotMatch(drawer, /resolveInstructionLang/, 'the drawer reads a DDL it does not have');
});

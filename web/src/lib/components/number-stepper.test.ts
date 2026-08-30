// Run with: node --import ./scripts/ts-extensionless-resolve.mjs --test src/lib/components/number-stepper.test.ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { formatGroupedNumber, parseGroupedNumber } from '../groupedNumber.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const STEPPER = read('./NumberStepper.svelte');
const LIMITS = read('../features/settings/RenderLimitsSettings.svelte');
const DATABASE = read('../features/settings/DatabaseAdministrationSettings.svelte');
const APPEARANCE = read('../features/settings/AppearanceSettings.svelte');

test('settings numbers are displayed with groups of three digits', () => {
	assert.equal(formatGroupedNumber(999, 1), '999');
	assert.equal(formatGroupedNumber(1_000, 1), '1,000');
	assert.equal(formatGroupedNumber(100_000, 1), '100,000');
	assert.equal(formatGroupedNumber(1_234.5, 0.1), '1,234.5');
	assert.equal(parseGroupedNumber('100,000'), 100_000);
	assert.equal(parseGroupedNumber('1,234.5'), 1_234.5);
	assert.equal(parseGroupedNumber('not a number'), null);
});

test('the shared stepper owns the compact box and grouped text field', () => {
	assert.match(STEPPER, /width: min\(136px, 100%\);/);
	assert.match(STEPPER, /<input[\s\S]*?type="text"[\s\S]*?role="spinbutton"/);
	assert.match(STEPPER, /value=\{formatGroupedNumber\(current, step\)\}/);
	assert.match(STEPPER, /parseGroupedNumber\(input\.value\)/);
	assert.doesNotMatch(LIMITS, /\.limits-field :global\(\.number-stepper\)/);
});

test('database, limits, and retry count all use the one shared number box', () => {
	assert.equal((DATABASE.match(/<NumberStepper/g) ?? []).length, 4);
	assert.equal((LIMITS.match(/<NumberStepper/g) ?? []).length, 1);
	assert.equal((APPEARANCE.match(/<NumberStepper/g) ?? []).length, 1);
	assert.match(DATABASE, /\.db-backup-time-fields :global\(\.number-stepper\) \{ flex: 0 1 136px; \}/);
});

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createSvgImageAction, type SvgImageUrlEnvironment } from './svgImage.ts';

test('the SVG image action replaces and releases every object URL', () => {
	const created: Blob[] = [];
	const revoked: string[] = [];
	const environment: SvgImageUrlEnvironment = {
		createObjectURL(blob) {
			created.push(blob);
			return `blob:test-${created.length}`;
		},
		revokeObjectURL(url) {
			revoked.push(url);
		}
	};
	const removed: string[] = [];
	const node = {
		src: '',
		removeAttribute(name: string) {
			removed.push(name);
			if (name === 'src') this.src = '';
		}
	} as HTMLImageElement;

	const action = createSvgImageAction(environment)(node, '<svg id="first"/>');
	assert.equal(node.src, 'blob:test-1');
	assert.equal(created[0].type, 'image/svg+xml');

	action.update('<svg id="first"/>');
	assert.equal(created.length, 1, 'unchanged SVG must keep its current object URL');

	action.update('<svg id="second"/>');
	assert.equal(node.src, 'blob:test-2');
	assert.deepEqual(revoked, ['blob:test-1']);

	action.update('');
	assert.equal(node.src, '');
	assert.deepEqual(revoked, ['blob:test-1', 'blob:test-2']);
	assert.deepEqual(removed, ['src']);

	action.destroy();
	assert.deepEqual(revoked, ['blob:test-1', 'blob:test-2']);
});

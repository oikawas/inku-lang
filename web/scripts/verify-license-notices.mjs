import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const lock = JSON.parse(readFileSync('package-lock.json', 'utf8'));
const manifest = JSON.parse(readFileSync('static/licenses/manifest.json', 'utf8'));

const files = new Set(['inku-MIT.txt']);
for (const [name, notice] of Object.entries(manifest.packages)) {
	const version = lock.packages[`node_modules/${name}`]?.version;
	if (version !== notice.version) {
		throw new Error(`${name}: notice covers ${notice.version}, lock has ${version ?? 'no entry'}`);
	}
	files.add(notice.file);
}

files.add('README.txt');
files.add('manifest.json');
for (const directory of ['static/licenses', 'build/client/licenses']) {
	for (const file of files) {
		const path = join(directory, file);
		if (statSync(path).size === 0) throw new Error(`empty license notice: ${path}`);
	}
}

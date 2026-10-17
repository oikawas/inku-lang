import { cpSync, existsSync, lstatSync, mkdirSync, realpathSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const [productArg, build] = process.argv.slice(2);
if (!productArg || !build || !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/.test(build)) {
  throw new Error('Usage: npm run install:viewer -- /absolute/product-checkout unique-build-id');
}
const product = realpathSync(resolve(productArg));
if (!existsSync(join(product, 'web/svelte.config.js'))) throw new Error('Not a product checkout');
const parent = join(product, 'web/static/experimental/ddl-3d');
for (const path of ['web', 'web/static', 'web/static/experimental', 'web/static/experimental/ddl-3d']) {
  const target = join(product, path);
  if (existsSync(target) && lstatSync(target).isSymbolicLink()) throw new Error('Symlink destination refused');
}
if (!existsSync(join(root, 'dist/wasm/score_adapter_bg.wasm'))) throw new Error('Build WASM and viewer first');
mkdirSync(parent, { recursive: true });
const destination = join(parent, build);
mkdirSync(destination); // Never overwrite another build.
for (const child of readdirSync(join(root, 'dist'))) {
  cpSync(join(root, 'dist', child), join(destination, child), { recursive: true, errorOnExist: true, force: false });
}
console.log(`VITE_DDL_3D_VIEWER_URL=/experimental/ddl-3d/${build}/index.html`);

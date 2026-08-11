// Lets `node --test` import the app's own modules.
//
// The sources are written for Vite, which resolves `./saijiki` to
// `./saijiki.ts`. Node does not, so before this hook a test could only read a
// module as text -- it could never call it. Tests that must compare real
// output (the DDL highlighter against a frozen baseline, for one) need the
// function, not the file.
//
// It only fires after Node's own resolution has failed, so nothing that
// already resolved changes meaning.
import { registerHooks } from 'node:module';

const HAS_EXTENSION = /\.(ts|tsx|js|jsx|mjs|cjs|json|svelte|css)$/;

registerHooks({
	resolve(specifier, context, nextResolve) {
		try {
			return nextResolve(specifier, context);
		} catch (error) {
			if (specifier.startsWith('.') && !HAS_EXTENSION.test(specifier)) {
				return nextResolve(`${specifier}.ts`, context);
			}
			throw error;
		}
	}
});

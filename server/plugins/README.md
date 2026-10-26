# Plugin documents

This directory holds `*.inku-plugin.md` documents. Today the only one that is drawn from is
`nature-leaves.inku-plugin.md`: it switches the `Nature.leaves` package bundled with the shared core on and off
and gives its words, notes and Saijiki pictures. Any other document here is legacy Markdown; its words are
listed as "not used for drawing" and left out of drawings with a diagnostic.

To add vocabulary, an administrator adds a plugin file (`inku.plugin-package.v1`) from the Web settings
"Plugins" instead; see `PLUGIN.md` §5.1. Those files are kept in `INKU_PLUGIN_PACKAGE_DIR`, not here.

The server parses documents as data and never executes plugin code. Added, changed, and removed documents are
detected without a service restart; administrators can force a reload with `inku-cli plugin reload`.

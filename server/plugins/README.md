# Plugin packages

The Server reads installed `inku.plugin-package.v2` files from `INKU_PLUGIN_PACKAGE_DIR`. An administrator checks and installs JSON or zip files through Web settings or the package API. See [PLUGIN.md](../../PLUGIN.md).

The bundled `Nature.leaves` package and its artwork live in the shared core at `core/crates/inku-ddl/assets/nature-leaves-v2/` and reach the Server through the native `bundled_nature` action. This directory no longer contains declarative plugin documents.

# Declarative vocabulary plugins

Place UTF-8 `*.inku-plugin.md` vocabulary documents in this directory. The server parses them as data and never executes plugin code. Added, changed, and removed files are detected without a service restart; administrators can force a reload with `inku-cli plugin reload`.

A rejected document is not partially loaded. Inspect validation reasons with `inku-cli plugin list` or validate before installation with `inku-cli plugin validate FILE`.

Official vocabulary documents may be tracked here in future releases. Local or third-party documents should be reviewed before deciding whether they belong in repository history.

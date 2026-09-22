# inku User and Operations Manual

This manual explains how to use and operate inku. It is intended for first-time creators and system administrators who deploy and maintain the application. Web UI instructions reflect v2.15.15 (Web Build 1091). The canonical product specification is `SPEC.ja.md` at the repository root.

## Audience

- Image creators: people who create SVG / PNG images from a few written words using the Web UI or CLI
- System administrators: people who install inku on a server and manage the API, Web UI, database, logs, backups, users, and AI provider connections

## Documents

1. [Creating Images](./image-creation.md)
2. [inku-cli Reference](./cli-reference.md)
   * [AI Autonomous Operation & Testing Reference](./cli-reference-for-ai.md)
3. [Application Installation](./application-install.md)
4. [Server Configuration](./server-configuration.md)
5. [Revision History](./revision-history.md)

For everyday creative work, start with Creating Images. It covers drawing from descriptions and instructions, Lineage and the Library, resuming batches, layer animation, and text-size settings. For provider connections and user permissions, see Server Configuration.

## Templates

- [Environment variable template](./templates/inku-api.env.example)
- [FastAPI systemd service example](./templates/systemd/inku-api.service)
- [SvelteKit / Vite systemd service example](./templates/systemd/inku-server.service)

The templates are generic examples. Keep real hostnames, user names, paths, and secrets in server-side configuration files, not in Git-tracked documentation.

The Japanese and English manuals preserve the same feature boundaries and chapter structure. The Japanese manual is updated first, then the same intent is reflected here.

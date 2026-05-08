# inku User and Operations Manual

This manual explains how to use and operate inku. It is intended for people who have never used the application before, and for system administrators who need to deploy and maintain it.

## Audience

- Image creators: people who create SVG / PNG images from short written prompts using the Web UI or CLI
- System administrators: people who install inku on a server and manage the API, Web UI, database, logs, backups, users, and AI provider connections

## Documents

1. [Creating Images](./image-creation.md)
2. [Application Installation](./application-install.md)
3. [Server Configuration](./server-configuration.md)

## Templates

- [Environment variable template](./templates/inku-api.env.example)
- [FastAPI systemd service example](./templates/systemd/inku-api.service)
- [SvelteKit / Vite systemd service example](./templates/systemd/inku-server.service)
- [logrotate example](./templates/logrotate/inku)

The templates are generic examples. Keep real hostnames, user names, paths, and secrets in server-side configuration files, not in Git-tracked documentation.

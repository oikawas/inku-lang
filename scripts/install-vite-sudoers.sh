#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

sudo /usr/sbin/visudo -cf ops/sudoers/ddl-server-inku-vite
sudo install -o root -g root -m 0440 \
  ops/sudoers/ddl-server-inku-vite \
  /etc/sudoers.d/ddl-server-inku-vite
sudo /usr/sbin/visudo -cf /etc/sudoers.d/ddl-server-inku-vite
sudo -n /usr/bin/systemctl restart inku-vite.service

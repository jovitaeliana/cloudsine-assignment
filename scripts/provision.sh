#!/usr/bin/env bash
# Idempotent provisioning for a t2.micro Ubuntu 24.04 instance.
# Safe to re-run: checks for existing state before making changes.
set -euo pipefail

echo "[provision] updating apt"
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release

if ! command -v docker >/dev/null; then
    echo "[provision] installing docker engine and compose plugin"
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y
    sudo apt-get install -y \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin

    sudo usermod -aG docker ubuntu
else
    echo "[provision] docker already installed"
fi

if [ ! -f /swapfile ]; then
    echo "[provision] creating 2 GB swapfile"
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
else
    echo "[provision] swapfile already present"
fi

sudo mkdir -p /opt/cloudsine
sudo chown ubuntu:ubuntu /opt/cloudsine

echo "[provision] done. Log out and back in for docker group membership to take effect."

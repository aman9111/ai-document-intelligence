#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu server (tested for Oracle Cloud Ubuntu 22.04/24.04, ARM or x86).
# Installs Docker, opens ports 80/443 and adds swap. Run with:  bash deploy/setup-server.sh
set -euo pipefail

echo "==> Installing Docker"
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"

echo "==> Opening ports 80 and 443 in the server firewall"
# Oracle's Ubuntu images block everything except SSH with iptables, even after
# the ports are opened in the cloud console. These rules allow web traffic.
if sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
  echo "    already open"
else
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
  sudo iptables -I INPUT 6 -m state --state NEW -p udp --dport 443 -j ACCEPT
  if command -v netfilter-persistent > /dev/null; then
    sudo netfilter-persistent save
  fi
fi

echo "==> Adding 4 GB swap (helps while Docker builds the images)"
if [ ! -f /swapfile ]; then
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab > /dev/null
else
  echo "    swap already exists"
fi

echo
echo "Done. Log out and log in again (so 'docker' works without sudo), then follow deploy/DEPLOY.md."

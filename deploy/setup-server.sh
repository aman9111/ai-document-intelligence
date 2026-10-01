#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu 22.04/24.04 server (AWS EC2 or Oracle Cloud, ARM or x86).
# Installs Docker, opens ports 80/443 in the server firewall if needed, and adds swap.
# Run with:  bash deploy/setup-server.sh
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

echo "==> Checking the server firewall"
# Oracle's Ubuntu images block everything except SSH with an iptables REJECT rule,
# even after the ports are opened in the cloud console. AWS images don't do this
# (AWS uses Security Groups instead), so there is nothing to change there.
if sudo iptables -S INPUT | grep -q -- "-j REJECT"; then
  if sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
    echo "    ports 80/443 already open"
  else
    # Insert at the top, so they come before the REJECT rule
    sudo iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
    sudo iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
    sudo iptables -I INPUT 1 -p udp --dport 443 -j ACCEPT
    if command -v netfilter-persistent > /dev/null; then
      sudo netfilter-persistent save
    fi
    echo "    opened ports 80 and 443"
  fi
else
  echo "    no blocking rules found, nothing to change (open ports in your cloud firewall)"
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
echo "Done. Log out and log in again (so 'docker' works without sudo), then continue with the deploy guide."

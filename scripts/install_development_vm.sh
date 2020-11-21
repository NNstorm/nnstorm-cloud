#!/usr/bin/env bash

set -e

nvidia_driver=435

sudo apt update && sudo apt upgrade -y
sudo apt install -y \
     curl wget apt-transport-https ca-certificates software-properties-common "nvidia.*${nvidia_driver}" zsh tmux

# docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo apt install -y docker-ce
sudo usermod -aG docker ${USER}

# nvidia docker
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/${distribution}/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit nvidia-container-runtime
echo '{ "default-runtime": "nvidia", "runtimes": { "nvidia": { "path": "/usr/bin/nvidia-container-runtime", "runtimeArgs": [] } }}' > /tmp/tmp && sudo mv /tmp/tmp /etc/docker/daemon.json
sudo systemctl restart docker

# docker compose
sudo curl -L "https://github.com/docker/compose/releases/download/1.24.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

echo "Installation completed, rebooting VM."

sudo reboot
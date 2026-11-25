#!/usr/bin/env bash
# One-time Raspberry Pi setup for Jarvis (Pi 4 4GB or Pi 5, Raspberry Pi OS 64-bit).
# Run from the jarvis folder:   bash deploy/install_pi.sh
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(pwd)"

echo "== System packages"
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev portaudio19-dev espeak-ng libatlas-base-dev

echo "== Python packages (this takes a while on a Pi)"
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "== Backup voice (Piper 'Alan')"
mkdir -p voices
venv/bin/python -m piper.download_voices en_GB-alan-medium --data-dir voices || \
  echo "   (couldn't download the Piper voice; Jarvis will use the system voice as backup)"

if [ ! -f .env ]; then
  read -rp "Anthropic API key (sk-ant-..., leave empty to add later): " KEY
  [ -n "$KEY" ] && echo "ANTHROPIC_API_KEY=$KEY" > .env && chmod 600 .env
fi

echo "== Microphones found"
venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())" || true
echo "   If Jarvis doesn't hear you, set MIC_DEVICE in config.py to your USB mic's number."

read -rp "Start Jarvis automatically on boot? [y/N] " AUTO
if [[ "${AUTO,,}" == y* ]]; then
  sed -e "s|__USER__|$USER|g" -e "s|__DIR__|$DIR|g" -e "s|__UID__|$(id -u)|g" \
      deploy/jarvis.service | sudo tee /etc/systemd/system/jarvis.service >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable --now jarvis
  echo "Jarvis is running. Logs: journalctl -u jarvis -f   (or $DIR/jarvis.log)"
  echo "Stop: sudo systemctl stop jarvis   Disable: sudo systemctl disable jarvis"
else
  echo "Done. Start Jarvis with:  venv/bin/python main.py"
fi

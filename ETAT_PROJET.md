# État du projet parakeet-transcribe

## Packages créés

- `parakeet-transcribe-cuda_0.3.2_amd64.deb` - Version GPU NVIDIA
- `parakeet-transcribe-cpu_0.3.2_amd64.deb` - Version CPU (tout ordinateur)

## Binaires inclus

| Binaire | Description | `--help` | ffmpeg | unmute |
|---------|-------------|:--------:|:------:|:------:|
| `transcribe` | Transcription simple (TDT, multilingue) | oui | oui | — |
| `transcribe-daemon` | Daemon avec modèle préchargé | oui | — | — |
| `transcribe-client` | Client pour le daemon (auto-unmute, arrêt par Entrée) | oui | oui | oui |
| `transcribe-diarize` | Transcription + diarisation (TDT + Sortformer) | oui | oui | — |
| `transcribe-stream-diarize` | Streaming + diarisation (Nemotron, anglais) | oui | oui | oui |
| `dictee` | Push-to-talk avec animation | — | — | — |

## Modèles supportés (téléchargés à l'installation)

- **TDT** : Transcription multilingue (~2.5 Go)
- **Sortformer** : Diarisation (~50 Mo)
- **Nemotron** : Streaming anglais (~2.5 Go)

## Fichiers du package

```
/usr/bin/
  transcribe
  transcribe-daemon
  transcribe-client
  transcribe-diarize
  transcribe-stream-diarize
  dictee

/usr/lib/systemd/user/
  parakeet-transcribe.service

/usr/share/doc/parakeet-transcribe/
  README

/usr/share/man/man1/
  transcribe.1.gz
  transcribe-daemon.1.gz
  transcribe-client.1.gz
  transcribe-diarize.1.gz
  transcribe-stream-diarize.1.gz
  dictee.1.gz

/usr/share/parakeet-transcribe/
  tdt/         (modèle TDT)
  sortformer/  (modèle Sortformer)
  nemotron/    (modèle Nemotron)
```

## Installation

```bash
sudo dpkg -i parakeet-transcribe-cuda_0.3.2_amd64.deb  # ou -cpu
sudo apt-get install -f  # dépendances manquantes

systemctl --user daemon-reload
systemctl --user enable --now parakeet-transcribe
systemctl --user enable --now ydotool
```

## Configuration dictee

Dans `/usr/bin/dictee`, les variables d'animation :
```bash
BIN_PATH="/home/rapha/.local/bin/rapha_bin"
ANIMATION_CONFIG="circular"
ANIMATION_PARAM="-p center -w 1000 -H 150"
ANIMATION_APP="${BIN_PATH}/animation-speech"
```

## Reconstruction

```bash
cd ~/SOURCES/parakeet-rs_rapha
./build-deb.sh
```

## Maintainer

rcspam <rcspam4gh@gmail.com>

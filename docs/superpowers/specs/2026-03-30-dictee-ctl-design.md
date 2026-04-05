# dictee-ctl — Coordinateur central

**Date :** 2026-03-30
**Version cible :** 1.3
**Statut :** Approuve

## Probleme

3 frontends (script `dictee`, `dictee-tray.py`, plasmoid) + `dictee-transcribe.py` manipulent tous `/dev/shm/.dictee_state`, appellent `systemctl` et `dictee-switch-backend` directement. Des race conditions surviennent quand plusieurs actions arrivent en meme temps (diarisation + F9, switch backend pendant recording, double cancel ESC).

## Solution

Un daemon Python asyncio (`dictee-ctl.py`) qui centralise toute la coordination. Les frontends deviennent de simples clients qui envoient des commandes et recoivent l'etat. `dictee-switch-backend` est absorbe dans `dictee-ctl`.

Les frontends conservent l'execution (enregistrement micro via `parec`, saisie via `dotool`, post-traitement) — `dictee-ctl` ne fait que coordonner l'etat et gerer le daemon/VRAM.

## Machine a etats

```
                    +----------+
         +---------|  offline  |<------ daemon pas demarre
         |         +----------+
         | start-daemon    ^
         v                 | stop-daemon
    +----------+           |
    |   idle   |-----------+
    +----------+
      |  |  |
      |  |  +---- switch-backend --> switching --> idle
      |  |
      |  +------- diarize-on --> diarize-preparing --> diarize-ready
      |                                                    |
      |                                                    | record
      |                                                    v
      +-- record --> recording --> transcribing --> idle
                        ^              |
                        |              | (diarize actif)
                        |              v
                        |        diarize-transcribing --> idle
                        |
                     cancel --> idle
```

### Regles de transition

- `RECORD` / `RECORD_TRANSLATE` : accepte uniquement depuis `idle` ou `diarize-ready`
- `SWITCH_ASR` / `SWITCH_TRANS` : accepte uniquement depuis `idle`
- `DIARIZE_ON` : accepte uniquement depuis `idle`
- `CANCEL` : accepte uniquement depuis `recording`
- `DONE` : accepte depuis `recording`, `transcribing`, `diarize-transcribing`
- Chaque transition ecrit dans `/dev/shm/.dictee_state` (compatibilite polling existant)
- Mapping etats pour le state file : `diarize-preparing` → `switching`, `diarize-ready` → `idle`, `diarize-transcribing` → `transcribing`

### Timeouts

| Etat | Timeout | Action |
|------|---------|--------|
| recording | 120s | Reset idle, kill parec orphelin |
| transcribing | 30s | Reset idle, notif erreur |
| diarize-transcribing | 30s | Reset idle, notif erreur |
| switching | 15s | Reset idle, notif erreur |
| diarize-preparing | 20s | Reset idle, notif erreur, restore daemon |

## Protocole

### Transport

- Socket Unix stream : `/tmp/dictee-ctl-$(id -u).sock` (suffixe UID multi-utilisateur)
- Format texte, UTF-8, `\n` termine
- Chaque client envoie `HELLO <nom>\n` a la connexion (`dictee`, `tray`, `plasmoid`, `transcribe`)

### Commandes client -> serveur

| Commande | Reponse succes | Reponse erreur |
|----------|---------------|----------------|
| `HELLO <name>` | `OK hello` | — |
| `RECORD` | `OK recording` | `ERR state:<etat>` |
| `RECORD_TRANSLATE` | `OK recording` | `ERR state:<etat>` |
| `CANCEL` | `OK idle` | `ERR state:<etat>` |
| `DONE` | `OK idle` | — |
| `DIARIZE_ON` | `OK diarize-ready` | `ERR state:<etat>` / `ERR vram_insufficient` / `ERR not_configured` |
| `DIARIZE_OFF` | `OK idle` | — |
| `SWITCH_ASR <backend>` | `OK idle` | `ERR state:<etat>` |
| `SWITCH_TRANS <backend>` | `OK idle` | `ERR state:<etat>` |
| `START_DAEMON` | `OK idle` | `ERR already_running` |
| `STOP_DAEMON` | `OK offline` | `ERR state:<etat>` |
| `STATUS` | `OK <etat>` | — |
| `RELOAD_CONF` | `OK` | — |
| `PING` | `PONG` | — |

### Notifications serveur -> clients

Broadcast a tous les clients connectes :

```
STATE <etat>
```

### Commandes bloquantes

- `DIARIZE_ON` : bloquant (~5s) — stop daemon, free VRAM, wait, puis repond `OK`
- `SWITCH_ASR` : bloquant (~3s) — stop ancien daemon, start nouveau
- Les autres commandes repondent immediatement

## Robustesse

### Heartbeat

- Le client en `recording` envoie `PING` toutes les 2s
- Si `dictee-ctl` ne recoit plus de PING pendant 5s : client mort → reset idle, kill processus orphelins

### Crash recovery

- Au demarrage, `dictee-ctl` verifie `/dev/shm/.dictee_state` — si etat residuel actif (recording, transcribing) → reset idle
- Fichier lock `/tmp/dictee-ctl.lock` empeche deux instances
- Socket stale au demarrage : supprime apres verification via lock

### Identification client

- `HELLO <name>` a la connexion, `dictee-ctl` stocke nom + PID
- Seul le client qui a pris le recording peut envoyer `DONE` ou `CANCEL`
- Le log indique quel frontend a declenche chaque action

### Fallback si dictee-ctl absent

```bash
if ! response=$(dictee-ctl-client RECORD 2>/dev/null); then
    # Mode direct — comportement actuel
    write_state "recording"
    # ...
fi
```

Les frontends fonctionnent sans `dictee-ctl` (pas de regression).

### Gestion d'erreurs

| Scenario | Comportement |
|----------|-------------|
| Client meurt pendant recording | Pas de PING 5s → reset idle, kill parec |
| Daemon crash pendant transcription | Timeout 30s → reset idle, notif erreur |
| `dictee-ctl` crash | Systemd redemarre en 2s, clients en fallback |
| Deux `dictee-ctl` lances | Lock file, le second quitte |
| Socket stale au demarrage | Supprime apres verif lock |
| VRAM insuffisante pour diarize | Cleanup (stop daemon + unload ollama), si echec → `ERR vram_insufficient` |
| `dictee.conf` absent | `ERR not_configured` sur toute commande sauf `STATUS` |

## Journal

Log rotatif dans `/tmp/dictee-ctl.log` (Python `RotatingFileHandler`, max 100 Ko, 1 backup) :

```
2026-03-30 14:23:01 [dictee pid=12345] RECORD → OK recording
2026-03-30 14:23:05 [dictee pid=12345] PING
2026-03-30 14:23:08 [dictee pid=12345] DONE → OK idle
```

## Fichiers

### Nouveaux

| Fichier | Role | Taille estimee |
|---------|------|----------------|
| `dictee-ctl.py` | Daemon coordinateur asyncio | ~400 lignes |
| `dictee-ctl-client` | Script shell wrapper socat (dep: `socat`) | ~5 lignes |
| `dictee-ctl.service` | Service systemd user | ~12 lignes |

### Modifies

| Fichier | Changements |
|---------|------------|
| `dictee` | write_state/flock → `dictee-ctl-client` + fallback direct |
| `dictee-tray.py` | `subprocess.Popen(["dictee-switch-backend"])` → socket dictee-ctl + ecoute STATE |
| `dictee-transcribe.py` | `DIARIZE_ON`/`DIARIZE_OFF` via socket |
| `plasmoid/.../main.qml` | `executable.run("dictee-ctl-client ...")` |
| `plasmoid/.../FullRepresentation.qml` | Idem pour les boutons |

### Supprimes

| Fichier | Raison |
|---------|--------|
| `dictee-switch-backend` | Logique absorbee dans `dictee-ctl.py` |

## Service systemd

```ini
[Unit]
Description=Dictee coordinator
Before=dictee.service dictee-vosk.service dictee-whisper.service dictee-canary.service
After=default.target

[Service]
Type=simple
ExecStart=/usr/bin/dictee-ctl
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
```

`dictee-ctl` demarre avant les daemons ASR. C'est lui qui les demarre/arrete.

## Compatibilite arriere

- `/dev/shm/.dictee_state` continue d'etre ecrit par `dictee-ctl` → polling plasmoid fonctionne
- `dictee.conf` reste la source de verite pour la config
- `dictee-ctl` lit `dictee.conf` pour connaitre le backend actif
- Sans `dictee-ctl`, tout fonctionne comme avant (fallback dans chaque frontend)

## Sequence type — dictee via F9

```
dictee             dictee-ctl              daemon
  |                    |                      |
  |-- HELLO dictee --->|                      |
  |<-- OK hello -------|                      |
  |-- RECORD --------->|                      |
  |<-- OK recording ---|-- STATE recording -->| (broadcast)
  |                    |                      |
  | (parec enregistre) |                      |
  | (PING toutes 2s)   |                      |
  |                    |                      |
  |-- DONE ----------->|                      |
  |<-- OK idle --------|-- STATE idle ------->|
```

## Sequence type — diarisation via tray

```
tray               dictee-ctl
  |                    |
  |-- HELLO tray ----->|
  |-- DIARIZE_ON ----->| (stop daemon, free VRAM, wait ~5s)
  |<-- OK diarize-ready|-- STATE diarize-ready (broadcast)
  |                    |
  | (user presse F9)   |
dictee                 |
  |-- HELLO dictee --->|
  |-- RECORD --------->|
  |<-- OK recording ---|-- STATE recording (broadcast)
  | (parec + PING)     |
  |-- DONE ----------->| (restore daemon)
  |<-- OK idle ---------|-- STATE idle (broadcast)
```

## Packaging

- Ajouter `dictee-ctl.py`, `dictee-ctl-client`, `dictee-ctl.service` dans les 5 fichiers de build (build-deb.sh, build-rpm.sh, PKGBUILD, install.sh, build-deb.sh plasmoid)
- Retirer `dictee-switch-backend` des paquets
- Ajouter `socat` aux dependances (Depends/Requires)
- Preset systemd auto-enable pour `dictee-ctl.service`
- `dictee-setup.py` appelle `RELOAD_CONF` apres modification de `dictee.conf`

## Migration progressive

1. **Phase 1** : `dictee-ctl` existe, les frontends utilisent le fallback si absent
2. **Phase 2** : tous les frontends passent par `dictee-ctl`, fallback conserve
3. **Phase 3** : suppression du polling/flock/write_state dans les frontends (optionnel, v1.4)

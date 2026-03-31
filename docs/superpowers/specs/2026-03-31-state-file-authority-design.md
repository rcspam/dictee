# Design — State file comme source unique de vérité (v1.3)

Date : 2026-03-31
Branche : devel-1.3

## Contexte

L'architecture actuelle mélange frontend et backend : le plasmoid maintient son propre état QML en parallèle du fichier d'état, 3 chemins ESC concurrents existent, et la config (`DICTEE_DIARIZE`) sert de canal de communication temporaire. Résultat : race conditions, état incohérent, diarisation instable.

## Principe

Le fichier `/dev/shm/.dictee_state` est la **seule source de vérité**. Le backend (scripts) est le seul à y écrire. Les frontends (plasmoid, tray) le lisent et envoient des commandes.

## 1. États dans le fichier d'état

```
idle            — daemon actif, prêt
offline         — daemon arrêté
recording       — enregistrement en cours
transcribing    — transcription en cours
diarizing       — diarisation en cours
switching       — changement de backend
cancelled       — transitoire (→ idle)
preparing       — NOUVEAU : VRAM libérée pour diarisation
diarize-ready   — NOUVEAU : prêt à enregistrer en mode diarisation
```

**Qui écrit** : uniquement `dictee`, `dictee-switch-backend`, `dictee-reset` via `write_state()` protégé par flock.

**Qui lit** : plasmoid (polling 150ms), tray (QFileSystemWatcher), dictee-ptt (avant d'agir sur ESC).

## 2. Un seul chemin ESC

`dictee-ptt` (service systemd, evdev) est le seul gestionnaire d'ESC physique.

**Supprimé** :
- Listener ESC interne de `dictee` (`start_escape_listener` / python3 `/dev/input`)
- `Keys.onEscapePressed` du plasmoid envoyant cancel
- `onExpandedChanged` du plasmoid envoyant cancel

**Comportement ESC dans dictee-ptt** :
- Lit l'état fichier avant d'agir
- Si `recording`, `preparing`, `diarize-ready`, `diarizing` → `dictee --cancel`
- Si `idle`, `offline` → ignore (ESC passe normalement aux applications)

**Annulation depuis le plasmoid** :
- Uniquement via clic explicite sur le bouton (texte "click to cancel" pendant preparing)
- Fermer le popup ≠ annuler (l'état backend est préservé)

## 3. Le plasmoid comme pur lecteur d'état

Le plasmoid ne prédit plus l'état. Il lit le state file et affiche.

### `parseState()` — mapping état → UI

| State file     | Point couleur | Bouton diarize                            |
|----------------|---------------|-------------------------------------------|
| idle           | vert          | "Diarization" (enabled)                   |
| offline        | rouge         | disabled                                  |
| recording      | bleu/highlight| "Stop diarization" si activeButton=diarize|
| transcribing   | vert          | disabled                                  |
| diarizing      | violet #9B59B6| "Diarization in progress…" (disabled)     |
| preparing      | violet #9B59B6| "Preparing… (click to cancel)" (pulse)    |
| diarize-ready  | violet #9B59B6| "Start diarization" (vert)                |
| switching      | jaune         | disabled                                  |

### `handleAction()` — envoie des commandes, ne change pas l'état

```
dictate          → executable.run("dictee") ou executable.run("dictee --diarize")
dictate-translate→ executable.run("dictee --translate")
diarize-prepare  → executable.run("dictee-switch-backend diarize true")
cancel           → executable.run("dictee --cancel")
reset            → executable.run("dictee-reset $svc")
start-daemon     → executable.run("systemctl --user enable --now $svc")
stop-daemon      → executable.run("systemctl --user stop ...")
```

Plus de `root.state = "recording"` immédiat. Le plasmoid attend que le state file confirme.

### Propriétés QML supprimées

- `diarizeEnabled`, `diarizeFlowActive`, `diarizeResetCount`, `cancelledDuringPrepare`
- `dState` (machine à états locale du bouton diarize)
- `cleanupDiarize()`
- `onDiarizeEnabledChanged`, `onDiarizeResetCountChanged`
- `onExpandedChanged` cancel, `Keys.onEscapePressed` cancel, `_handleEsc()`
- Grace period 2s, debounce 800ms dans handleAction

### Propriété QML conservée

- `activeButton` — purement UI, pour savoir quel bouton afficher en rouge/actif pendant recording

### Boutons Dictation / Translate

```
enabled: fullRep.state === "idle" || fullRep.state === "recording"
```

Plus de vérification de `btnDiarize.dState`. Les états `preparing`, `diarize-ready` désactivent naturellement.

## 4. Le backend — `dictee` et `dictee-switch-backend`

### `dictee-switch-backend diarize true`

```bash
1. write_state "preparing"
2. set_conf DICTEE_PRE_DIARIZE_BACKEND $current_asr
3. systemctl --user disable --now dictee ...
4. Attendre GPU libre (boucle nvidia-smi)
5. write_state "diarize-ready"
```

Ne met plus `DICTEE_DIARIZE=true` dans la config. L'état fichier suffit.

### `dictee-switch-backend diarize false`

```bash
1. set_conf DICTEE_PRE_DIARIZE_BACKEND ""
2. systemctl --user enable --now $svc
3. write_state "idle"
```

### `dictee` — flag `--diarize` explicite

Le plasmoid passe `--diarize` quand `activeButton === "diarize"`. F9 ne le passe jamais.

**Start** (pas de PIDFILE) :

```bash
state=$(cat $STATE_FILE)
case $state in
    idle|diarize-ready)  ;;     # OK
    *)  exit 0 ;;               # bloqué
esac
write_state "recording"
pw-record ...
```

**Stop** (PIDFILE présent) :

```bash
write_state "transcribing"
stop_recording
if [ "$DIARIZE" = "true" ]; then
    write_state "diarizing"
    systemd-run dictee-transcribe --file $wav --diarize
else
    transcription normale...
    write_state "idle"
fi
```

### `dictee --cancel` — switch sur l'état fichier

```bash
state=$(cat $STATE_FILE)
case $state in
    idle|offline|cancelled)
        exit 0 ;;
    preparing|diarize-ready)
        write_state "cancelled"
        pkill -f "dictee-switch-backend diarize true"
        dictee-switch-backend diarize false ;;
    recording)
        write_state "cancelled"
        stop_recording / cleanup
        if PRE_DIARIZE_BACKEND is set; then
            dictee-switch-backend diarize false
        fi ;;
    diarizing)
        write_state "cancelled"
        pkill dictee-transcribe / diarize-only
        dictee-switch-backend diarize false ;;
    transcribing|switching)
        write_state "cancelled"
        write_state "idle" ;;
esac
```

Protégé par flock. Idempotent. Deux cancel simultanés : le second voit `cancelled` et sort.

### Listener ESC interne — supprimé

`start_escape_listener` / `stop_escape_listener` et le code python3 inline sont retirés. `dictee-ptt` gère ESC.

## 5. Le tray comme pur lecteur d'état

Même patron que le plasmoid :
- Lit le state file via QFileSystemWatcher
- Mapping des nouveaux états (preparing, diarize-ready) vers icônes violet
- Actions : envoie `dictee`, `dictee --cancel`, etc. — jamais de double nettoyage
- Cancel (molette) = `dictee --cancel` seul, plus de `dictee-switch-backend diarize false` en parallèle

## 6. Timers de sécurité

Les frontends gardent des timers en cas de crash. Ils envoient des commandes au backend, ne changent jamais l'état eux-mêmes.

| État bloqué    | Timeout | Action envoyée      |
|----------------|---------|----------------------|
| recording      | 60s     | `dictee --cancel`    |
| transcribing   | 15s     | `dictee-reset`       |
| diarizing      | 120s    | `dictee --cancel`    |
| switching      | 15s     | `dictee-reset`       |
| preparing      | 30s     | `dictee --cancel`    |
| diarize-ready  | 120s    | `dictee --cancel`    |

## 7. Fichiers impactés

### Modifications majeures
- `dictee` — cancel refactorisé (switch sur état), suppression ESC listener, start vérifie état, `--diarize` flag
- `dictee-switch-backend` — `diarize true` écrit `preparing`/`diarize-ready`, plus de `DICTEE_DIARIZE` config
- `plasmoid/.../main.qml` — suppression état local, handleAction simplifié, parseState étendu
- `plasmoid/.../FullRepresentation.qml` — suppression dState/ESC/cancel, bouton diarize lit fullRep.state
- `dictee-tray.py` — mapping nouveaux états, cancel simplifié

### Modifications mineures
- `dictee-ptt.py` — vérifier état avant d'agir sur ESC (si pas déjà fait)
- `dictee-common.sh` — aucun changement (write_state existe déjà)
- `dictee-reset` — aucun changement

### Pas de nouveau fichier / binaire

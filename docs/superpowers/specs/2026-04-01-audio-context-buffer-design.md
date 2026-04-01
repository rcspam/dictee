# Buffer de contexte audio — Spec

## Principe

Buffer circulaire qui accumule l'audio des dictees precedentes. Avant chaque nouvelle dictee, on prepend le buffer + marqueur "Alpha Bravo" au nouvel audio. Le daemon ASR transcrit le tout, on split sur "Alpha Bravo" et on ne garde que le nouveau texte. Le daemon a le contexte acoustique pour mieux reconnaitre les mots courts/techniques en debut de phrase.

## Configuration (`dictee.conf`)

| Variable | Defaut | Description |
|----------|--------|-------------|
| `DICTEE_AUDIO_CONTEXT` | `false` | Active/desactive le buffer de contexte |
| `DICTEE_AUDIO_CONTEXT_TIMEOUT` | `30` | Timeout d'expiration (secondes d'inactivite) ET taille max du buffer audio. Le buffer expire apres N secondes sans dictee non-vide, et l'audio accumule est tronque a N secondes max. |

## Fichiers runtime

| Fichier | Description |
|---------|-------------|
| `/dev/shm/.dictee_buffer_${UID}.wav` | Buffer audio (volatile, shared memory) |
| `/dev/shm/.dictee_buffer_ts_${UID}` | Timestamp epoch du dernier buffer sauvegarde |
| `/dev/shm/.dictee_combined_${UID}.wav` | Fichier temporaire concat (supprime apres transcription) |
| `assets/alpha-bravo.wav` | Marqueur audio (existant, 32 Ko, 16kHz mono) |

## Marqueur "Alpha Bravo"

- Fichier : `assets/alpha-bravo.wav` (1s, 16kHz mono, voix humaine FR)
- Regex de detection : `/[.,\s]*[Aa]lpha\s+[Bb]ravo[.,\s]*/`
- Valide 200/200 sur 4 backends (Parakeet, Vosk, Whisper, Canary)
- IMPORTANT : utiliser l'enregistrement FR (l'EN donne "Il fait bravo" sur Canary)

## Sequence

```
F9 → record → stop → recording.wav

SI contexte OFF ou pas de buffer ou buffer expire :
    transcribe recording.wav directement

SI contexte ON et buffer existe et non-expire :
    tronquer buffer a N secondes max (ffmpeg -sseof)
    concat buffer.wav + alpha-bravo.wav + recording.wav → combined.wav (ffmpeg)
    transcribe combined.wav
    split reponse sur regex Alpha Bravo
    SI marqueur trouve :
        coller uniquement la partie apres le marqueur
    SI marqueur PAS trouve :
        log warning (DICTEE_DEBUG)
        notification rouge a l'utilisateur
        coller le texte brut complet (ne pas perdre la dictee)
    supprimer combined.wav

SI transcription non-vide :
    sauver recording.wav comme buffer
    ecrire timestamp (epoch) dans fichier ts
SI transcription vide :
    ne pas toucher au buffer ni au timestamp
    (le buffer precedent non-vide reste valide jusqu'a expiration de ses 30s)
```

## Timer d'expiration

- Verification lazy au prochain F9 : `(now - timestamp) > TIMEOUT`
- Pas de processus en arriere-plan
- Le timestamp est ecrit uniquement quand on sauve un buffer non-vide
- Consequence : un F9 vide (silence) ne reset pas le timer, le contexte precedent reste disponible

## F9 consecutifs rapides

Pas de race condition : le script `dictee` est sequentiel. Un F9 pendant une transcription en cours est ignore (etat `transcribing` dans le state file). La sequence est toujours :

```
F9 → record → stop → concat → transcribe → sauve buffer → idle → F9 possible
```

## Concatenation ffmpeg

```bash
ffmpeg -y -i buffer.wav -i alpha-bravo.wav -i recording.wav \
  -filter_complex "[0][1][2]concat=n=3:v=0:a=1" -ar 16000 -ac 1 combined.wav
```

## Troncature buffer (taille max)

```bash
duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 buffer.wav)
if (( $(echo "$duration > $TIMEOUT" | bc -l) )); then
    ffmpeg -y -sseof -${TIMEOUT} -i buffer.wav -ar 16000 -ac 1 trimmed.wav
    mv trimmed.wav buffer.wav
fi
```

## UI — dictee-setup

- Checkbox "Buffer de contexte audio" → `DICTEE_AUDIO_CONTEXT`
- SpinBox "Duree du contexte (secondes)" → `DICTEE_AUDIO_CONTEXT_TIMEOUT`
- Label explicatif : "Accumule l'audio des dictees precedentes pour ameliorer la reconnaissance des mots courts ou techniques. Le buffer expire apres N secondes d'inactivite et ne depasse jamais N secondes d'audio."

## UI — Plasmoid

- **Config** (configGeneral.qml) : checkbox "Audio context buffer" (defaut persistant)
- **Popup** (FullRepresentation) : bouton toggle a cote du bouton principal, active/desactive a la volee
- Variable plasmoid : `cfg_audioContext` → lit/ecrit `DICTEE_AUDIO_CONTEXT` dans dictee.conf

## UI — Tray

- Menu checkable "Audio context" (meme modele que le toggle diarisation)
- Lit `DICTEE_AUDIO_CONTEXT` depuis dictee.conf
- Ecrit via `dictee-switch-backend context true/false`

## Dependances

- `ffmpeg` — deja present de facto (utilise par transcribe-client)
- Pas de nouvelle dependance

## Fichiers a modifier

1. **`dictee`** — logique buffer/concat/split/timer (~30-40 lignes)
2. **`dictee-setup.py`** — checkbox + spinbox + label explicatif
3. **`plasmoid/package/contents/ui/configGeneral.qml`** — checkbox config
4. **`plasmoid/package/contents/ui/FullRepresentation.qml`** — bouton toggle popup
5. **`dictee-tray.py`** — menu checkable
6. **`dictee-switch-backend`** — commande `context true/false`
7. **`build-deb.sh`** / **`build-rpm.sh`** / **`PKGBUILD`** — copier `alpha-bravo.wav` dans les assets installes
8. **i18n** — nouvelles chaines dans les 6 langues (fr, de, es, it, uk, pt)

## Hors perimetre

- Pas de modification du daemon Rust
- Pas de nouveau binaire
- Pas de nouvelle dependance systeme

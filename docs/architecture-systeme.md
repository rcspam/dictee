# Architecture système — services, scripts, IPC

Vue **plomberie système** de la pile dictée : services systemd, scripts shell/Python, fichiers d'état, sockets, D-Bus, liaisons exactes.

> Complément de [`architecture-pile.md`](architecture-pile.md) (vue applicative).

---

## 1. Les 7 services systemd (user-level)

Tous dans `~/.config/systemd/user/` (user install) ou `/usr/lib/systemd/user/` (paquet).

```mermaid
flowchart TB
    subgraph Target["🎯 systemd targets"]
        Default["default.target"]
        Graphical["graphical-session.target"]
    end

    subgraph ASR["Services ASR (mutuellement exclusifs — Conflicts=)"]
        direction LR
        SvcP["<b>dictee.service</b><br/>Parakeet TDT"]
        SvcV["<b>dictee-vosk.service</b><br/>Vosk"]
        SvcW["<b>dictee-whisper.service</b><br/>faster-whisper"]
        SvcC["<b>dictee-canary.service</b><br/>Canary GPU"]
    end

    subgraph UI["Services UI / entrée"]
        SvcPTT["<b>dictee-ptt.service</b><br/>evdev push-to-talk"]
        SvcTray["<b>dictee-tray.service</b><br/>systray"]
    end

    subgraph Kbd["Service injection clavier"]
        SvcDot["<b>dotoold.service</b><br/>dotool daemon"]
    end

    SvcP -.-> Default
    SvcV -.-> Default
    SvcW -.-> Default
    SvcC -.-> Default
    SvcDot -.-> Default
    SvcPTT -.->|PartOf| Graphical
    SvcTray -.->|BindsTo| Graphical

    SvcPTT -->|After| SvcP
    SvcTray -->|After| SvcP

    SvcP -. Conflicts .- SvcV
    SvcP -. Conflicts .- SvcW
    SvcP -. Conflicts .- SvcC
    SvcV -. Conflicts .- SvcW
    SvcV -. Conflicts .- SvcC
    SvcW -. Conflicts .- SvcC

    classDef tgt fill:#f3e5f5,stroke:#7b1fa2
    classDef asr fill:#fff3e0,stroke:#f57c00
    classDef ui fill:#e1f5ff,stroke:#0288d1
    classDef kbd fill:#fce4ec,stroke:#c2185b
    class Default,Graphical tgt
    class SvcP,SvcV,SvcW,SvcC asr
    class SvcPTT,SvcTray ui
    class SvcDot kbd
```

### Détails unit par unit

| Service | ExecStart | Restart | WantedBy / PartOf | `ExecStartPost` / `ExecStopPost` |
|---|---|---|---|---|
| `dictee.service` | `/usr/bin/transcribe-daemon` | `on-failure` (5 s) | `default.target` | `echo idle > /dev/shm/.dictee_state` / `echo offline > …` |
| `dictee-vosk.service` | `/usr/bin/transcribe-daemon-vosk` | `on-failure` (5 s) | `default.target` | idem |
| `dictee-whisper.service` | `/usr/bin/transcribe-daemon-whisper` | `on-failure` (5 s) | `default.target` | idem |
| `dictee-canary.service` | `/usr/bin/transcribe-daemon --canary` | `on-failure` (5 s) | `default.target` | idem |
| `dictee-ptt.service` | `/usr/bin/sg input -c "/usr/bin/dictee-ptt"` | `on-failure` (3 s) | `PartOf=graphical-session.target` | — |
| `dictee-tray.service` | `/usr/bin/dictee-tray` | `on-failure` (3 s) | `BindsTo=graphical-session.target` | — |
| `dotoold.service` | `/usr/bin/dotoold` | `on-failure` (2 s) | `default.target` | — |

**Env communes** : `EnvironmentFile=-%h/.config/dictee.conf`, `Environment=XDG_RUNTIME_DIR=/run/user/%U`.
**CUDA Parakeet** : `Environment=ORT_DYLIB_PATH=/usr/lib/dictee/libonnxruntime.so`.

---

## 2. Cycle de vie — démarrage à la session

```mermaid
sequenceDiagram
    autonumber
    participant L as Login manager
    participant SD as systemd --user
    participant Preset as user-preset
    participant ASR as dictee*.service
    participant PTT as dictee-ptt.service
    participant Tray as dictee-tray.service
    participant Dot as dotoold.service
    participant State as /dev/shm/.dictee_state

    L->>SD: session démarre
    SD->>Preset: applique preset (install.sh)
    Preset->>ASR: enable (un seul actif via Conflicts=)
    Preset->>PTT: enable
    Preset->>Tray: enable
    Preset->>Dot: enable

    SD->>Dot: start (default.target)
    SD->>ASR: start (default.target)
    ASR->>State: ExecStartPost → "idle"

    Note over SD,Graphical: graphical-session.target atteint
    SD->>PTT: start (After=ASR, PartOf=graphical)
    SD->>Tray: start (After=ASR, BindsTo=graphical)

    par Logout
        SD->>PTT: stop (PartOf → coupé)
        SD->>Tray: stop (BindsTo → coupé)
    and
        SD->>ASR: stop (à l'arrêt système)
        ASR->>State: ExecStopPost → "offline"
    end
```

---

## 3. Liaisons entre scripts — qui lance qui

```mermaid
flowchart LR
    subgraph User["Déclencheurs utilisateur"]
        K1["Touche F9<br/>(evdev)"]
        K2["Raccourci KDE<br/>(kglobalaccel)"]
        ClicT["Clic tray"]
        ClicP["Clic plasmoid"]
        CLI["CLI manuel"]
    end

    PTT["<b>dictee-ptt.py</b><br/>/dev/input/event*<br/>/dev/uinput"]
    KG["kglobalacceld<br/>(KDE)"]
    Tray["<b>dictee-tray.py</b>"]
    Plas["<b>plasmoid (QML)</b>"]

    Dictee["<b>dictee</b><br/>(bash)"]
    DicteeC["dictee-common.sh"]

    Switch["dictee-switch-backend"]
    Setup["dictee-setup.py"]
    Reset["dictee-reset"]

    Common["pw-record<br/>transcribe-client<br/>dictee-postprocess<br/>dotool<br/>notify-send<br/>pactl<br/>trans / curl ollama"]

    K1 --> PTT
    K2 --> KG
    ClicT --> Tray
    ClicP --> Plas
    CLI --> Dictee

    PTT -->|subprocess.Popen| Dictee
    KG -->|exec /usr/bin/dictee| Dictee
    Tray -->|subprocess.Popen| Dictee
    Tray -->|subprocess.Popen| Switch
    Tray -->|subprocess.Popen| Setup
    Tray -->|subprocess.Popen| Reset
    Plas -->|executable engine| Dictee
    Plas -->|executable engine| Switch

    Dictee -. source .-> DicteeC
    Dictee --> Common
    Switch -->|systemctl<br/>--user| Services[(systemd<br/>units)]

    classDef user fill:#e1f5ff,stroke:#0288d1
    classDef entry fill:#fff3e0,stroke:#f57c00
    classDef core fill:#ffebee,stroke:#c62828
    classDef tool fill:#e8f5e9,stroke:#388e3c
    class K1,K2,ClicT,ClicP,CLI user
    class PTT,KG,Tray,Plas entry
    class Dictee,DicteeC core
    class Switch,Setup,Reset,Common tool
```

---

## 4. La carte complète des fichiers d'état / IPC

```mermaid
flowchart LR
    subgraph Writers["✍️  Écrivains"]
        W1["dictee (bash)"]
        W2["dictee-ppt.py"]
        W3["transcribe-daemon"]
        W4["systemd<br/>ExecStartPost<br/>ExecStopPost"]
        W5["dictee-setup.py"]
    end

    subgraph DevShm["📍 /dev/shm/ (tmpfs — volatile)"]
        direction TB
        F1[".dictee_state<br/><i>+ .lock (flock 200)</i>"]
        F2[".dictee_buffer{UID}.wav<br/>.dictee_buffer_ts{UID}"]
        F3[".dictee_combined{UID}.wav<br/>.dictee_silence{UID}.wav"]
        F4[".dictee_last_word<br/><i>MARKER:word</i>"]
        F5[".dictee_audio_bands<br/><i>floats temps réel</i>"]
    end

    subgraph Tmp["📍 /tmp/"]
        direction TB
        T1["recording_dictee_pid-{UID}<br/><i>PID pw-record</i>"]
        T2["dictee_translate-{UID}<br/><i>flag existence</i>"]
        T3["dictee_diarize-{UID}<br/><i>flag existence</i>"]
        T4["dictee-ppt-{UID}.pid<br/><i>flock LOCK_EX</i>"]
        T5[".dictee_notify_sid-{UID}<br/><i>server ID D-Bus</i>"]
        T6["mut_dictee-{UID}<br/><i>état mute micro</i>"]
        T7["dictee-debug-{UID}.log"]
    end

    subgraph Runtime["📍 $XDG_RUNTIME_DIR (/run/user/UID/)"]
        R1["transcribe.sock<br/><i>AF_UNIX, 0600</i>"]
    end

    subgraph Config["📍 ~/.config/"]
        C1["dictee.conf<br/><i>shell-sourceable</i>"]
        C2["kglobalshortcutsrc<br/><i>[dictee]</i>"]
        C3["dictee/rules.conf<br/>dictionary.conf<br/>continuation.conf"]
    end

    subgraph Readers["👁  Lecteurs"]
        R_Dictee["dictee"]
        R_PTT["dictee-ppt"]
        R_Tray["dictee-tray"]
        R_Plas["plasmoid"]
        R_PP["dictee-postprocess"]
        R_Client["transcribe-client"]
        R_Daemon["transcribe-daemon"]
        R_KDE["KDE<br/>kglobalacceld"]
    end

    W1 --> F1
    W1 --> F2
    W1 --> F3
    W1 --> F4
    W1 --> T1
    W1 --> T2
    W1 --> T3
    W1 --> T5
    W1 --> T6
    W1 --> T7
    W2 --> F1
    W2 --> T4
    W3 --> F5
    W3 --> R1
    W4 --> F1
    W5 --> C1
    W5 --> C2
    W5 --> C3

    F1 -->|flock<br/>atomique| R_Dictee
    F1 -->|inotify /<br/>poll 150 ms| R_Tray
    F1 -->|ping-pong<br/>150 ms| R_Plas
    F1 --> R_PTT
    F2 --> R_Dictee
    F3 --> R_Client
    F4 --> R_Dictee
    F5 -->|ping-pong<br/>80 ms| R_Plas

    T1 --> R_PTT
    T1 --> R_Dictee
    T2 --> R_Tray
    T2 --> R_Dictee
    T3 --> R_Dictee
    T5 --> R_Dictee

    R1 <-->|protocole tab| R_Client
    R1 --- R_Daemon

    C1 --> R_Dictee
    C1 --> R_PTT
    C1 --> R_Tray
    C1 --> R_PP
    C2 --> R_KDE
    C3 --> R_PP

    classDef w fill:#ffebee,stroke:#c62828
    classDef shm fill:#fff3e0,stroke:#f57c00
    classDef tmp fill:#f5f5f5,stroke:#616161
    classDef run fill:#e8f5e9,stroke:#388e3c
    classDef cfg fill:#e1f5ff,stroke:#0288d1
    classDef r fill:#f3e5f5,stroke:#7b1fa2
    class W1,W2,W3,W4,W5 w
    class F1,F2,F3,F4,F5 shm
    class T1,T2,T3,T4,T5,T6,T7 tmp
    class R1 run
    class C1,C2,C3 cfg
    class R_Dictee,R_PTT,R_Tray,R_Plas,R_PP,R_Client,R_Daemon,R_KDE r
```

### Fiche par fichier

| Chemin | Contenu | Écrivain | Lecteur(s) | Protection | Nettoyage |
|---|---|---|---|---|---|
| `/dev/shm/.dictee_state` | mot-clé d'état | `dictee`, `dictee-ppt`, services | tous | `flock -n 200` sur `.dictee_state.lock` | reboot (tmpfs) |
| `/dev/shm/.dictee_state.lock` | *vide* | — | `write_state()` | lockfile | reboot |
| `/dev/shm/.dictee_buffer{UID}.wav` | WAV pré-enregistrement | `dictee` | `dictee` (concat) | — | `cleanup_session()` |
| `/dev/shm/.dictee_buffer_ts{UID}` | timestamp UNIX | `dictee` | `dictee` | — | `cleanup_session()` |
| `/dev/shm/.dictee_combined{UID}.wav` | WAV fusionné diarisation | `dictee` | `transcribe-client` | — | `cleanup_session()` |
| `/dev/shm/.dictee_silence{UID}.wav` | silence de jointure | `dictee` | `dictee` (concat) | — | `cleanup_session()` |
| `/dev/shm/.dictee_last_word` | `MARKER:mot` | `dictee` `save_last_word()` | `dictee` `apply_continuation()` | — | persistant |
| `/dev/shm/.dictee_audio_bands` | floats temps réel | `transcribe-daemon` | plasmoid (FFT) | overwrite continu | — |
| `/tmp/recording_dictee_pid-{UID}` | PID `pw-record` | `dictee` | `dictee-ppt` | — | `stop_recording()` |
| `/tmp/dictee_translate-{UID}` | *vide* (flag) | `dictee` | `dictee-tray`, `dictee` | — | `cleanup_session()` |
| `/tmp/dictee_diarize-{UID}` | *vide* (flag) | `dictee` | `dictee` | — | `cleanup_session()` |
| `/tmp/dictee-ppt-{UID}.pid` | PID du daemon PTT | `dictee-ppt` | `dictee-ppt` (self) | `fcntl.LOCK_EX \| LOCK_NB` | `atexit()` |
| `/tmp/.dictee_notify_sid-{UID}` | server ID D-Bus | `notify_dictee_async` | `close_notification` | — | fermeture notif |
| `/tmp/mut_dictee-{UID}` | `muted=1` | `dictee` | `restore_audio()` | — | `restore_audio()` |
| `/tmp/dictee-debug-{UID}.log` | logs `_dbg()` | `dictee-common.sh` | humain | append | manuel |
| `$XDG_RUNTIME_DIR/transcribe.sock` | — (socket) | `transcribe-daemon` | `transcribe-client` | 0600, `AF_UNIX` | unlink à l'arrêt |
| `~/.config/dictee.conf` | env vars | `dictee-setup.py`, `dictee-switch-backend` | tous (source) | 0600 | — |
| `~/.config/kglobalshortcutsrc` | `[dictee]` | `dictee-setup.py` (`kwriteconfig6`) | kglobalacceld | INI | — |

---

## 5. Socket `transcribe.sock` — protocole

```mermaid
sequenceDiagram
    participant C as transcribe-client
    participant S as transcribe-daemon

    Note over C,S: $XDG_RUNTIME_DIR/transcribe.sock (AF_UNIX, 0600)

    C->>S: connect()
    alt Simple
        C->>S: "audio.wav\n"
    else Avec timestamps
        C->>S: "audio.wav\ttimestamps\n"
    else Avec contexte (Canary)
        C->>S: "audio.wav\tcontext:texte précédent\n"
    else Override langue (Canary)
        C->>S: "audio.wav\tlang:fr\n"
    end
    S-->>C: "texte transcrit\n"
    C->>S: close()
```

---

## 6. Machine à états — transitions exactes

```mermaid
stateDiagram-v2
    [*] --> offline

    offline --> idle : dictee.service ExecStartPost
    idle --> offline : ExecStopPost ou dictee-reset

    idle --> recording : dictee write_state recording
    recording --> transcribing : fin pw-record
    recording --> cancelled : dictee --cancel
    cancelled --> idle : cleanup_session
    transcribing --> idle : texte injecte via dotool

    idle --> switching : dictee-switch-backend
    switching --> idle : systemctl restart OK

    idle --> preparing : dictee --diarize (Sortformer)
    preparing --> diarize_ready : modele charge
    diarize_ready --> diarizing : pw-record demarre
    diarizing --> idle : speakers attribues

    note right of idle
        /dev/shm/.dictee_state
        ecrit via flock 200 sur
        .dictee_state.lock
    end note
```

**Écrivains légitimes de l'état** : `dictee` (`write_state()`), `dictee-ppt` (via même lib), services systemd (`ExecStart/StopPost`), `dictee-switch-backend`.
**Lecteurs** : tous, sans verrou (lecture = ≤ 16 octets, atomique de facto).

---

## 7. D-Bus — notifications et raccourcis

```mermaid
flowchart LR
    subgraph Notif["org.freedesktop.Notifications"]
        direction TB
        N1["/org/freedesktop/Notifications"]
        M1["Notify() → server_id"]
        M2["CloseNotification(id)"]
    end

    subgraph KGA["org.kde.kglobalaccel"]
        direction TB
        K1["/kglobalaccel"]
        KM1["setShortcut(desktop, label, keys)"]
    end

    Dictee["dictee<br/>(bash)"] -->|notify-send<br/>--replace-id=424200| M1
    Common["dictee-common.sh<br/>notify_dictee_async()"] -->|capture server_id<br/>→ /tmp/.dictee_notify_sid-UID| M1
    Common -->|gdbus call ...<br/>CloseNotification| M2

    Setup["dictee-setup.py"] -->|kwriteconfig6| RC[("~/.config/<br/>kglobalshortcutsrc")]
    Setup -->|gdbus call| KM1
    KM1 -->|déclenche| KGAD["kglobalacceld<br/>(KDE)"]
    KGAD -->|exec| Dictee

    classDef bus fill:#f3e5f5,stroke:#7b1fa2
    classDef src fill:#ffebee,stroke:#c62828
    classDef cfg fill:#f5f5f5,stroke:#616161
    class Notif,KGA bus
    class Dictee,Common,Setup src
    class RC,KGAD cfg
```

**Points clés** :
- **ID de remplacement fixe** : `NOTIFY_ID=424200` (défini dans `dictee-common.sh:23`) — une seule notif dictée visible à la fois.
- **Fermeture fiable** : on stocke le `server_id` retourné par `Notify` dans `/tmp/.dictee_notify_sid-{UID}`, puis on appelle `CloseNotification(server_id)` via `gdbus` — contourne le bug KDE qui ignore `replace-id` sur les notifs expirées.
- **Aucun D-Bus** pour l'état dictée (pas de signal/property) : polling fichier + `flock`.

---

## 8. Raccourcis globaux — les deux voies

```mermaid
flowchart TB
    subgraph V1["Voie 1 — evdev / uinput (indépendant DE)"]
        direction LR
        Key1((touche<br/>F9)) -->|/dev/input/event*<br/>EVIOCGRAB exclusif| PTTb["dictee-ppt.py"]
        PTTb -->|/dev/uinput<br/>re-émission si ≠ F9| UI1((apps))
        PTTb -->|subprocess.Popen<br/>hold OU toggle| D1["dictee"]
    end

    subgraph V2["Voie 2 — kglobalaccel (KDE uniquement)"]
        direction LR
        Key2((Ctrl+;)) --> KWin["KWin / kglobalacceld"]
        KWin -->|D-Bus event| KGD[".desktop<br/>DBusActivatable"]
        KGD -->|exec| D2["/usr/bin/dictee"]
    end

    Setup["dictee-setup.py"] -.->|configure| PTTb
    Setup -.->|kwriteconfig6<br/>+ gdbus setShortcut| KWin

    classDef key fill:#e1f5ff,stroke:#0288d1
    classDef core fill:#ffebee,stroke:#c62828
    class Key1,Key2 key
    class D1,D2 core
```

| Voie | Portée | Mode | Permissions requises |
|---|---|---|---|
| **evdev + uinput** (`dictee-ppt`) | tout DE (X11/Wayland, KDE/GNOME/…) | hold **et** toggle | groupe `input`, udev rule `/etc/udev/rules.d/80-dotool.rules` |
| **kglobalaccel** (KDE) | KDE Plasma uniquement | toggle (press) | aucune |

---

## 9. Boucles de polling — fréquences

```mermaid
flowchart LR
    State["/dev/shm/.dictee_state"]
    Bands["/dev/shm/.dictee_audio_bands"]

    subgraph Tray["dictee-tray.py"]
        GL["GLib.timeout_add<br/>3000 ms"]
        IN["Gio.File.monitor_file<br/>(inotify)"]
        QT["QTimer<br/>3000 ms"]
        FW["QFileSystemWatcher"]
    end

    subgraph Plasmoid["plasmoid main.qml"]
        FP["fastPollTimer<br/><b>150 ms</b><br/>(ping-pong #A/#B)"]
        DP["daemonPollTimer<br/>pollingInterval<br/>(pause si recording)"]
        AT["audioTimer<br/><b>80 ms ≈ 12 fps</b>"]
    end

    State --> IN
    IN -->|changed| GL
    State --> FW
    FW -->|changed| QT
    State --> FP
    Bands --> AT

    DP -->|systemctl --user<br/>is-active| Sys[("services<br/>status")]

    classDef file fill:#f5f5f5,stroke:#616161
    classDef poll fill:#e8f5e9,stroke:#388e3c
    class State,Bands file
    class GL,IN,QT,FW,FP,DP,AT poll
```

---

## 10. Anatomie d'une dictée — tous les fichiers touchés

```mermaid
sequenceDiagram
    autonumber
    participant D as dictee
    participant ST as .dictee_state
    participant Rec as pw-record
    participant Pid as /tmp/recording_dictee_pid-UID
    participant Wav as ~/.cache/tmp_recording_dictee.wav
    participant Buf as .dictee_buffer{UID}.wav
    participant Sk as transcribe.sock
    participant Lw as .dictee_last_word
    participant Not as D-Bus Notify
    participant Sid as .dictee_notify_sid-UID

    D->>ST: write "recording" (flock)
    D->>Not: Notify "Enregistrement…"
    Not-->>D: server_id
    D->>Sid: store server_id
    D->>Rec: spawn async
    D->>Pid: write $!
    Rec->>Wav: stream WAV
    Note over D,Wav: utilisateur parle…
    D->>Rec: kill (stop)
    D->>Pid: rm
    D->>ST: write "transcribing"
    D->>Buf: concat buffer précédent
    D->>Sk: transcribe-client combined.wav
    Sk-->>D: texte
    D->>D: pipe dictee-postprocess
    D->>Lw: save_last_word
    D->>D: apply_continuation
    D->>D: dotool type
    D->>Sid: read server_id
    D->>Not: CloseNotification(server_id)
    D->>ST: write "idle"
    D->>D: cleanup_session (rm flags, buffers)
```

---

## 11. Install / uninstall — impact système

```mermaid
flowchart TB
    subgraph Inst["install.sh"]
        I1["install -d<br/>~/.config/systemd/user/"]
        I2["cp + sed<br/>/usr/bin ↔ $PREFIX/bin<br/>*.service"]
        I3["usermod -aG input<br/>(groupe input pour uinput)"]
        I4["/etc/udev/rules.d/<br/>80-dotool.rules"]
        I5["systemctl --user<br/>preset + enable + restart"]
    end

    subgraph Active["État après install"]
        A1["dotoold.service ✔"]
        A2["dictee-ppt.service ✔"]
        A3["dictee-tray.service ✔"]
        A4["dictee.service ✔<br/>(default backend)"]
    end

    subgraph FirstRun["Premier lancement"]
        F1{"DICTEE_SETUP_DONE<br/>dans dictee.conf ?"}
        F2["exec dictee-setup<br/>--wizard"]
        F3["dictée normale"]
    end

    I1 --> I2 --> I3 --> I4 --> I5
    I5 --> A1
    I5 --> A2
    I5 --> A3
    I5 --> A4

    A4 --> F1
    F1 -->|non| F2 --> F3
    F1 -->|oui| F3

    classDef inst fill:#fff3e0,stroke:#f57c00
    classDef act fill:#e8f5e9,stroke:#388e3c
    classDef first fill:#e1f5ff,stroke:#0288d1
    class I1,I2,I3,I4,I5 inst
    class A1,A2,A3,A4 act
    class F1,F2,F3 first
```

---

## 12. Matrice récapitulative *qui parle à qui*

| De ↓ / Vers → | `dictee` | `transcribe-daemon` | `dictee-ppt` | `dictee-tray` | plasmoid | systemd |
|---|---|---|---|---|---|---|
| **utilisateur** | CLI / KDE shortcut | — | F9 (evdev) | clic | clic | — |
| **`dictee`** | — | socket Unix | `/dev/shm/.dictee_state` | `/dev/shm/.dictee_state` | `/dev/shm/.dictee_state` | (lance `systemctl` si daemon absent) |
| **`dictee-ptt`** | `Popen("dictee")` | — | — | état | — | — |
| **`dictee-tray`** | `Popen("dictee [--translate/--cancel]")` | — | — | — | — | — |
| **plasmoid** | `executable.run("dictee")` | — | — | — | — | `systemctl --user enable/disable` |
| **`dictee-setup`** | — | — | `dictee.conf` | `dictee.conf` | — | — |
| **`dictee-switch-backend`** | — | restart service | — | — | — | `systemctl --user` |
| **`transcribe-daemon`** | réponse socket | — | — | — | `/dev/shm/.dictee_audio_bands` | `ExecStartPost → idle` |
| **systemd** | — | lance/arrête | lance/arrête | lance/arrête | — | — |

---

## 13. Points de panne potentiels (aide-mémoire)

| Symptôme | Point à vérifier |
|---|---|
| Icône systray « offline » alors que daemon tourne | `systemctl --user status dictee` + `cat /dev/shm/.dictee_state` (écrit par `ExecStartPost` ?) |
| F9 ne déclenche rien | Groupe `input` (`id | grep input`), `systemctl --user status dictee-ptt`, lockfile `/tmp/dictee-ppt-{UID}.pid` |
| Texte non injecté | `dotoold.service` actif ? udev rule `/etc/udev/rules.d/80-dotool.rules` ? |
| Notif reste à l'écran | `/tmp/.dictee_notify_sid-{UID}` lu ? `gdbus call … CloseNotification` OK ? |
| Deux backends ASR simultanés | `Conflicts=` violés → `systemctl --user list-units dictee*` |
| État figé « recording » | `flock` laissé bloqué sur `.dictee_state.lock` → `rm /dev/shm/.dictee_state*` + reset service |
| Plasmoid ne se rafraîchit pas | ping-pong source (`#A`/`#B`) bloqué → redémarrer plasmashell |
| Socket refusé | `ls -l $XDG_RUNTIME_DIR/transcribe.sock` (0600, présent ?) |
| Raccourci KDE perdu | `~/.config/kglobalshortcutsrc [dictee]` + `gdbus call setShortcut` |

---

*Généré le 2026-04-15 — dictée v1.3.0 / master. Complète `architecture-pile.md`.*

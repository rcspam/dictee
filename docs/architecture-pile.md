# Architecture de la pile **dictée**

Cartographie complète du projet : qui fait quoi, qui parle à qui, où sont les données.

> Tous les diagrammes sont en Mermaid. Dans VS Code, utiliser l'extension *Markdown Preview Mermaid Support*. Sur GitHub, le rendu est natif.

---

## 1. Vue d'ensemble — les 6 grandes couches

```mermaid
flowchart TB
    subgraph UI["🖥️  Couche utilisateur (UI / intégration desktop)"]
        direction LR
        Plasmoid["Plasmoid KDE<br/>(QML)"]
        Tray["dictee-tray.py<br/>(systray PyQt6)"]
        Setup["dictee-setup.py<br/>(GUI config)"]
        PTT["dictee-ptt.py<br/>(evdev F9)"]
    end

    subgraph Shell["🐚  Couche orchestration (bash)"]
        Dictee["<b>dictee</b><br/>script principal"]
        Common["dictee-common.sh<br/>(lib partagée)"]
    end

    subgraph ASR["🎤  Couche ASR (Rust / Python)"]
        direction LR
        Daemon["transcribe-daemon<br/>(Rust, socket)"]
        Client["transcribe-client<br/>(Rust)"]
        Vosk["vosk-transcribe<br/>(Python)"]
        Whisper["whisper-transcribe<br/>(faster-whisper)"]
    end

    subgraph PP["✍️  Couche post-traitement (Python)"]
        PostProc["dictee-postprocess.py"]
        LLM["Ollama<br/>(gemma3:4b)"]
        Translate["translate()<br/>trans / libre / ollama"]
    end

    subgraph Audio["🔊  Couche audio & injection"]
        direction LR
        Capture["pw-record / parecord<br/>/ arecord"]
        Inject["dotool<br/>(clavier virtuel)"]
    end

    subgraph State["🗂️  Couche état / IPC"]
        direction LR
        StateFile["/dev/shm/<br/>.dictee_state"]
        Socket["$XDG_RUNTIME_DIR/<br/>transcribe.sock"]
        Conf["~/.config/<br/>dictee.conf"]
        Notif["D-Bus<br/>Notifications"]
    end

    UI -->|lance| Shell
    PTT -->|start/stop| Shell
    Shell --> Audio
    Shell -->|WAV| ASR
    ASR -->|texte brut| Shell
    Shell -->|pipe stdin| PP
    PP -->|texte propre| Shell
    Shell --> Inject
    Shell <-->|lit/écrit| State
    UI <-->|lit| State
    Shell --> Notif

    classDef ui fill:#e1f5ff,stroke:#0288d1
    classDef sh fill:#fff3e0,stroke:#f57c00
    classDef asr fill:#f3e5f5,stroke:#7b1fa2
    classDef pp fill:#e8f5e9,stroke:#388e3c
    classDef io fill:#fce4ec,stroke:#c2185b
    classDef st fill:#f5f5f5,stroke:#616161

    class Plasmoid,Tray,Setup,PTT ui
    class Dictee,Common sh
    class Daemon,Client,Vosk,Whisper asr
    class PostProc,LLM,Translate pp
    class Capture,Inject io
    class StateFile,Socket,Conf,Notif st
```

---

## 2. Pipeline d'une dictée (runtime, flux temporel)

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant PTT as dictee-ptt.py
    participant D as dictee (bash)
    participant PW as pw-record
    participant C as transcribe-client
    participant S as transcribe-daemon
    participant PP as dictee-postprocess.py
    participant O as Ollama (opt.)
    participant T as translate() (opt.)
    participant DT as dotool
    participant ST as /dev/shm/.dictee_state
    participant N as notify-send

    U->>PTT: appui F9 (hold/toggle)
    PTT->>D: exec dictee
    D->>ST: write "recording"
    D->>N: "🎤 Enregistrement…"
    D->>PW: pw-record 16 kHz mono s16
    U--)PW: parole
    U->>PTT: relâche F9
    PTT->>D: signal stop
    D->>PW: kill (WAV finalisé)
    D->>ST: write "transcribing"
    D->>C: transcribe-client audio.wav
    C->>S: socket Unix (path\ttimestamps)
    S->>S: ONNX inference (Parakeet/Canary)
    S-->>C: texte brut
    C-->>D: stdout
    D->>PP: pipe (stdin)
    PP->>PP: regex → dict → nombres → capit.
    opt LLM activé
        PP->>O: HTTP /api/generate
        O-->>PP: texte corrigé
    end
    PP-->>D: texte propre
    opt traduction activée
        D->>T: translate()
        T-->>D: texte traduit
    end
    D->>DT: type <texte>
    DT-->>U: frappe clavier
    D->>ST: write "idle"
    D->>N: "✔ Terminé"
```

---

## 3. Dépendances entre processus (qui lance qui)

```mermaid
flowchart LR
    subgraph SD["systemd --user"]
        SvcASR["dictee[-vosk/-whisper/-canary].service<br/>(mutuellement exclusifs)"]
        SvcPTT["dictee-ptt.service"]
        SvcTray["dictee-tray.service"]
        SvcDot["dotoold.service (opt.)"]
    end

    SvcASR -->|ExecStart| DaemonBin["transcribe-daemon<br/>(binaire Rust)"]
    SvcPTT -->|ExecStart| PTTBin["dictee-ptt.py"]
    SvcTray -->|ExecStart| TrayBin["dictee-tray.py"]
    SvcDot -->|ExecStart| DotBin["dotoold"]

    PTTBin -->|exec| Dictee["dictee (bash)"]
    TrayBin -->|exec clic| Dictee
    Plasmoid["Plasmoid KDE (QML)"] -->|exec clic| Dictee

    Dictee -->|subprocess| PWRec["pw-record"]
    Dictee -->|subprocess| Client["transcribe-client"]
    Client -->|socket Unix| DaemonBin
    Dictee -->|pipe| PPPy["dictee-postprocess.py"]
    PPPy -->|HTTP opt.| Ollama["ollama serve<br/>:11434"]
    Dictee -->|HTTP/CLI| Trans["trans / libretranslate / ollama"]
    Dictee -->|subprocess| Dot["dotool"]
    Dot -. uinput .-> DotBin

    Setup["dictee-setup.py"] -->|écrit| Conf["~/.config/dictee.conf"]
    Conf -. EnvironmentFile .-> SvcASR
    Conf -. source .-> Dictee
    Conf -. lu .-> PTTBin
    Conf -. lu .-> TrayBin

    classDef svc fill:#fff3e0,stroke:#f57c00
    classDef bin fill:#f3e5f5,stroke:#7b1fa2
    classDef cfg fill:#f5f5f5,stroke:#616161
    class SvcASR,SvcPTT,SvcTray,SvcDot svc
    class DaemonBin,PTTBin,TrayBin,DotBin,Client,PWRec,Dot,PPPy,Trans,Ollama,DotBin bin
    class Conf cfg
```

---

## 4. Backends ASR — détail

```mermaid
flowchart TB
    subgraph RustStack["Pile Rust (parakeet-rs)"]
        direction TB
        LibRs["lib.rs<br/>API publique"]

        subgraph Bins["Binaires (src/bin/)"]
            BDaemon["transcribe_daemon.rs"]
            BClient["transcribe_client.rs"]
            BTrans["transcribe.rs"]
            BDiar["transcribe_diarize.rs"]
            BStream["transcribe_stream_diarize.rs"]
        end

        subgraph Models["Moteurs / modèles"]
            TDT["parakeet_tdt.rs<br/><i>FastConformer-TDT, 25 langues</i>"]
            Nemo["nemotron.rs<br/><i>streaming, EN</i>"]
            Canary["canary.rs<br/><i>AED + context</i>"]
            Sort["sortformer.rs<br/><i>diarisation 4 locuteurs</i>"]
        end

        subgraph Core["Cœur"]
            Audio["audio.rs<br/>STFT · mel · preemphasis"]
            Tok["vocab.rs<br/>SentencePiece"]
            TS["timestamps.rs<br/>DTW word-level"]
            Dec["decoder_tdt.rs<br/>decoder.rs"]
            Exec["execution.rs<br/>(ort)"]
        end
    end

    subgraph PyBackends["Backends Python"]
        VoskPy["vosk-transcribe<br/><i>kaldi-style, offline</i>"]
        WhisperPy["whisper-transcribe<br/><i>faster-whisper, DTW</i>"]
    end

    subgraph OnDisk["Modèles sur disque"]
        TDTFiles["models/tdt/<br/>encoder-model.onnx<br/>decoder_joint-model.onnx<br/>vocab.txt"]
        VoskFiles["~/.cache/vosk/<br/>vosk-model-*"]
        WhisperFiles["~/.cache/huggingface/<br/>faster-whisper-*"]
    end

    BDaemon --> TDT
    BDaemon --> Canary
    BDaemon --> Nemo
    BDiar --> TDT
    BDiar --> Sort
    BStream --> Nemo
    BStream --> Sort

    TDT --> Dec
    TDT --> Tok
    Canary --> Dec
    Canary --> Tok
    Nemo --> Dec
    TDT --> Audio
    Canary --> Audio
    Nemo --> Audio
    TDT --> TS
    Dec --> Exec
    Exec -->|ONNX Runtime<br/>CPU / CUDA| TDTFiles

    VoskPy --> VoskFiles
    WhisperPy --> WhisperFiles

    Dictee["dictee (bash)"] -->|DICTEE_ASR_BACKEND=parakeet| BClient
    Dictee -->|DICTEE_ASR_BACKEND=canary| BClient
    BClient -->|socket Unix| BDaemon
    Dictee -->|DICTEE_ASR_BACKEND=vosk| VoskPy
    Dictee -->|DICTEE_ASR_BACKEND=whisper| WhisperPy

    classDef rust fill:#ffebee,stroke:#c62828
    classDef py fill:#e3f2fd,stroke:#1565c0
    classDef model fill:#f5f5f5,stroke:#616161
    class LibRs,BDaemon,BClient,BTrans,BDiar,BStream,TDT,Nemo,Canary,Sort,Audio,Tok,TS,Dec,Exec rust
    class VoskPy,WhisperPy py
    class TDTFiles,VoskFiles,WhisperFiles model
```

### Protocole socket `transcribe.sock`

| Requête envoyée au daemon | Réponse |
|---|---|
| `path.wav` | texte |
| `path.wav\ttimestamps` | texte + mots horodatés (Parakeet TDT) |
| `path.wav\tcontext:previous` | texte avec contexte décodeur (Canary) |
| `path.wav\tlang:fr` | texte avec override langue (Canary) |

---

## 5. Post-traitement — pipeline détaillé

```mermaid
flowchart TB
    In([texte brut ASR]) --> S1

    subgraph Pipeline["dictee-postprocess.py"]
        S1["1. Annotations non-speech<br/><code>[bruit]</code>, <code>(rire)</code>, <code>&lt;unk&gt;</code>"]
        S2["2. Fillers / hésitations<br/>euh, hum, ben…<br/><i>par langue</i>"]
        S3["3. Commandes vocales<br/>point, virgule,<br/>nouvelle ligne…"]
        S4["4. Règles langue<br/>élisions FR, contractions<br/>IT/ES/PT/DE/NL/RO"]
        S5["5. Typographie<br/>NNBSP avant ! ? ;<br/>(français)"]
        S6["6. Conversion nombres<br/><i>text2num</i>"]
        S7["7. Dictionnaire<br/>exact-match par mot"]
        S8["8. Capitalisation<br/>auto début phrase"]
        S9{"DICTEE_LLM_<br/>POSTPROCESS<br/>=true ?"}
        S10["9. Correction LLM<br/>Ollama /api/generate"]
        S11["10. Continuation<br/>save_last_word +<br/>apply_continuation"]

        S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8 --> S9
        S9 -->|oui| S10 --> S11
        S9 -->|non| S11
    end

    S11 --> Out([texte propre])

    subgraph Configs["Fichiers de règles"]
        direction LR
        R1["rules.conf.default<br/>+ ~/.config/dictee/rules.conf"]
        R2["dictionary.conf.default<br/>+ ~/.config/dictee/dictionary.conf"]
        R3["continuation.conf.default<br/>+ ~/.config/dictee/continuation.conf"]
    end

    R1 -.-> S1
    R1 -.-> S2
    R1 -.-> S3
    R2 -.-> S7
    R3 -.-> S11

    classDef step fill:#e8f5e9,stroke:#388e3c
    classDef cfg fill:#f5f5f5,stroke:#616161
    classDef dec fill:#fff9c4,stroke:#f9a825
    class S1,S2,S3,S4,S5,S6,S7,S8,S10,S11 step
    class R1,R2,R3 cfg
    class S9 dec
```

### Variables d'environnement de contrôle

| Variable | Défaut | Effet |
|---|---|---|
| `DICTEE_LANG_SOURCE` | `fr` | sélectionne les sections `[xx]` des fichiers de règles |
| `DICTEE_PP_RULES` | `true` | active regex (steps 1–3) |
| `DICTEE_PP_ELISIONS` | `true` | active règles langue (step 4) |
| `DICTEE_PP_NUMBERS` | `true` | active conversion nombres (step 6) |
| `DICTEE_LLM_POSTPROCESS` | `false` | active step 9 |
| `DICTEE_LLM_MODEL` | `gemma3:4b` | modèle Ollama |
| `DICTEE_LLM_TIMEOUT` | `10s` | garde-fou LLM |
| `DICTEE_LLM_POSITION` | `hybrid` | `first` \| `last` \| `hybrid` |

---

## 6. Machine à états (vue plasmoid / tray)

```mermaid
stateDiagram-v2
    [*] --> offline : daemon non démarré

    offline --> idle : systemctl start <asr>.service
    idle --> offline : stop service

    idle --> recording : dictee (F9 / clic)
    recording --> transcribing : fin capture audio
    recording --> cancelled : dictee --cancel
    cancelled --> idle

    transcribing --> idle : texte injecté

    idle --> switching : dictee-switch-backend
    switching --> idle : backend changé

    idle --> preparing : diarize (chargement Sortformer)
    preparing --> diarize_ready : modèle chargé
    diarize_ready --> diarizing : capture démarrée
    diarizing --> idle : speakers attribués

    note right of offline
        /dev/shm/.dictee_state
        (flock 200, atomique)
    end note
```

États exacts écrits dans `/dev/shm/.dictee_state` :
`offline` · `idle` · `recording` · `transcribing` · `cancelled` · `switching` · `preparing` · `diarize-ready` · `diarizing`

---

## 7. Entrées/sorties d'état et IPC

```mermaid
flowchart LR
    subgraph Writers["Écrivent l'état"]
        Dictee["dictee"]
        PTT["dictee-ptt"]
        Svc["systemd units<br/>(ExecStartPost)"]
    end

    subgraph StateFiles["Fichiers d'état (tmpfs)"]
        direction TB
        F1["/dev/shm/.dictee_state<br/>+ .lock (flock 200)"]
        F2["/tmp/recording_dictee_pid-UID"]
        F3["/tmp/dictee_translate-UID<br/>/tmp/dictee_diarize-UID"]
        F4["/tmp/translate_dictee_backend-UID"]
        F5["/dev/shm/.dictee_buffer*.wav<br/>.dictee_combined*.wav"]
        F6["/dev/shm/.dictee_last_word"]
        F7["$XDG_RUNTIME_DIR/transcribe.sock"]
    end

    subgraph Readers["Lisent l'état"]
        Tray["dictee-tray"]
        Plasmoid["Plasmoid QML"]
        Dictee2["dictee (autres invoc.)"]
    end

    subgraph Bus["D-Bus"]
        Notif["org.freedesktop.Notifications<br/>(replace-id 424200)"]
    end

    Dictee --> F1
    Dictee --> F2
    Dictee --> F5
    Dictee --> F6
    PTT --> F1
    Svc --> F1

    F1 -->|QFileSystemWatcher<br/>poll 100 ms–3 s| Tray
    F1 -->|Plasma5Support<br/>DataSource| Plasmoid
    F1 -->|lecture<br/>atomique| Dictee2

    Dictee -->|gdbus<br/>notify-send| Notif
    Dictee <-->|Unix socket| F7
    F7 <-->|protocole tabulé| TClient["transcribe-client"]

    classDef w fill:#ffebee,stroke:#c62828
    classDef s fill:#f5f5f5,stroke:#616161
    classDef r fill:#e1f5ff,stroke:#0288d1
    classDef b fill:#fff3e0,stroke:#f57c00
    class Dictee,PTT,Svc w
    class F1,F2,F3,F4,F5,F6,F7 s
    class Tray,Plasmoid,Dictee2 r
    class Notif b
```

---

## 8. Traduction — les 4 voies

```mermaid
flowchart LR
    Texte[texte post-traité] --> Choix{DICTEE_TRANSLATE_<br/>BACKEND}

    Choix -->|trans<br/>défaut| TransShell["trans -b -e google<br/>fr:en &quot;…&quot;<br/><i>translate-shell</i>"]
    Choix -->|libretranslate| LT["HTTP POST<br/>localhost:5000/translate"]
    Choix -->|ollama| Ol["HTTP POST<br/>localhost:11434/api/generate<br/>modèle translategemma"]
    Choix -->|canary| Intern["Traduction native<br/>dans transcribe-daemon<br/><i>(bypass post-trad)</i>"]

    TransShell --> Out[texte traduit]
    LT --> Out
    Ol --> Out
    Intern --> Out

    classDef ext fill:#fff3e0,stroke:#f57c00
    classDef int fill:#e8f5e9,stroke:#388e3c
    class TransShell,LT,Ol ext
    class Intern int
```

> ⚠️  Parakeet TDT ne supporte **pas** de traduction interne ; seul Canary le fait.

---

## 9. Audio — chaîne capture & injection

```mermaid
flowchart LR
    subgraph In["Capture micro (fallback cascade)"]
        PW["pw-record<br/>(PipeWire)"]
        PA["parecord<br/>(PulseAudio)"]
        AL["arecord<br/>(ALSA)"]
    end

    subgraph Norm["Normalisation"]
        Rate["16 kHz mono s16"]
        FF["ffmpeg si<br/>format ≠ WAV"]
    end

    subgraph Mute["Contrôle micro / sortie"]
        Unmute["pactl<br/>set-source-mute 0"]
        MuteSpk["pactl<br/>set-sink-mute 1<br/>(anti-feedback)"]
    end

    PW --> Rate
    PA --> Rate
    AL --> Rate
    Rate --> FF
    FF --> WAV[/.cache/tmp_recording_dictee.wav/]

    Unmute -.-> PW
    MuteSpk -.->|pendant capture| PW

    subgraph Out["Injection"]
        Dotool["dotool<br/>type &lt;texte&gt;<br/>key enter, ctrl+v…"]
        Clip["wl-copy / xclip<br/>(clipboard opt.)"]
    end

    Txt[texte final] --> Dotool
    Txt --> Clip
    Dotool --> Kbd((Clavier<br/>virtuel))

    classDef in fill:#e3f2fd,stroke:#1565c0
    classDef out fill:#fce4ec,stroke:#c2185b
    class PW,PA,AL,Rate,FF in
    class Dotool,Clip out
```

---

## 10. Configuration — sources et consommateurs

```mermaid
flowchart LR
    subgraph Edit["Édition"]
        SetupGUI["dictee-setup.py<br/>(interface PyQt6)"]
    end

    subgraph Files["Fichiers de config"]
        direction TB
        Conf["~/.config/dictee.conf<br/><i>shell-sourceable</i>"]
        RulesD["/usr/share/dictee/<br/>rules.conf.default"]
        RulesU["~/.config/dictee/<br/>rules.conf (override)"]
        DictD["dictionary.conf.default"]
        DictU["dictionary.conf (user)"]
        ContD["continuation.conf.default"]
        ContU["continuation.conf (user)"]
    end

    subgraph Cons["Consommateurs"]
        DicteeC["dictee (source)"]
        PPC["dictee-postprocess.py"]
        SvcC["*.service<br/>(EnvironmentFile)"]
        PTTC["dictee-ptt.py"]
        TrayC["dictee-tray.py"]
    end

    SetupGUI -->|écrit| Conf
    SetupGUI -->|édite| RulesU
    SetupGUI -->|édite| DictU
    SetupGUI -->|édite| ContU

    Conf --> DicteeC
    Conf --> SvcC
    Conf --> PTTC
    Conf --> TrayC

    RulesD -.-> PPC
    RulesU -.->|override| PPC
    DictD -.-> PPC
    DictU -.->|override| PPC
    ContD -.-> DicteeC
    ContU -.->|override| DicteeC

    classDef edit fill:#e1f5ff,stroke:#0288d1
    classDef file fill:#f5f5f5,stroke:#616161
    classDef cons fill:#e8f5e9,stroke:#388e3c
    class SetupGUI edit
    class Conf,RulesD,RulesU,DictD,DictU,ContD,ContU file
    class DicteeC,PPC,SvcC,PTTC,TrayC cons
```

---

## 11. i18n — gettext à 3 domaines

| Composant | Domaine gettext | Fichiers |
|---|---|---|
| `dictee-setup.py`, `dictee-tray.py` | `dictee` | `po/{fr,de,es,it,uk,pt}.po` → `.mo` installés dans `~/.local/share/locale/` |
| Plasmoid KDE | `plasma_applet_com.github.rcspam.dictee` | `plasmoid/package/contents/locale/{fr,de,es,it,uk,pt}/` |
| `dictee.desktop` | inline | `Name[fr]=…`, `GenericName[fr]=…` |

6 langues UI supportées : **fr, de, es, it, uk, pt** (l'ASR, lui, gère 25 langues EU via Parakeet TDT).

---

## 12. Tests & CI

```mermaid
flowchart TB
    subgraph Local["Tests locaux"]
        TPP["tests/test-postprocess.py<br/><b>682 tests</b> unittest<br/>regex · dict · TRPP · ReDoS"]
        TPi["tests/test-pipeline.py<br/><b>148 tests</b><br/>pipeline complet"]
        TApp["test-apply-continuation.sh<br/><i>bash units</i>"]
        TWER["test-wer.py /<br/>test-wer-commonvoice.py<br/><i>WER vs CommonVoice</i>"]
        TStress["dictee-stress-test.sh"]
        Cargo["cargo test<br/>(+feature sortformer)"]
    end

    subgraph Manual["Protocoles manuels"]
        direction LR
        UIChk["docs/test-checklist-ui-pipeline.md<br/><b>39 checks</b>"]
        Vocal["docs/test-protocol-vocal.md<br/><b>38 checks</b>"]
    end

    subgraph CI["GitHub Actions"]
        Job1["job: test-postprocess<br/>XDG_CONFIG_HOME isolé"]
        Job2["job: lint<br/>msgfmt --check"]
    end

    TPP --> Job1
    TPi --> Job1

    classDef auto fill:#e8f5e9,stroke:#388e3c
    classDef man fill:#fff3e0,stroke:#f57c00
    classDef ci fill:#f3e5f5,stroke:#7b1fa2
    class TPP,TPi,TApp,TWER,TStress,Cargo auto
    class UIChk,Vocal man
    class Job1,Job2 ci
```

---

## 13. Build & packaging

```mermaid
flowchart LR
    Src[Source root<br/><b>dictee/, *.py, src/, plasmoid/</b>] --> BuildDeb["build-deb.sh<br/><i>dpkg-deb</i>"]
    Src --> BuildRpm["build-rpm.sh<br/><i>rpmbuild</i>"]
    Src --> PKGB["PKGBUILD<br/><i>Arch / makepkg</i>"]
    Src --> CargoB["cargo build --release<br/>± features cuda,sortformer"]

    BuildDeb -->|2 variants| Deb["dictee-cpu_1.3.0_amd64.deb<br/>dictee-cuda_1.3.0_amd64.deb<br/>dictee-plasmoid_*.deb"]
    BuildRpm -->|2 variants| Rpm["dictee-cpu-*.rpm<br/>dictee-cuda-*.rpm<br/>dictee-plasmoid-*.rpm"]
    CargoB --> TarBin["dictee-binaires-1.3.0.tar.gz"]
    Src --> TarSrc["dictee-1.3.0.source.tar.gz"]
    Src --> Plas["dictee-plasmoid_1.3.0.plasmoid<br/>dictee-plasmoid_1.3.0.tar.gz"]

    Deb --> Release((🏷️  Release GitHub<br/>10 assets))
    Rpm --> Release
    TarBin --> Release
    TarSrc --> Release
    Plas --> Release

    classDef src fill:#e1f5ff,stroke:#0288d1
    classDef build fill:#fff3e0,stroke:#f57c00
    classDef asset fill:#e8f5e9,stroke:#388e3c
    classDef rel fill:#f3e5f5,stroke:#7b1fa2
    class Src src
    class BuildDeb,BuildRpm,PKGB,CargoB build
    class Deb,Rpm,TarBin,TarSrc,Plas asset
    class Release rel
```

---

## 14. Tableau récapitulatif — qui fait quoi

| Fichier / binaire | Langage | Rôle | Appelé par | Appelle |
|---|---|---|---|---|
| `dictee` | bash | **Orchestrateur principal** | PTT, tray, plasmoid, CLI | pw-record, transcribe-client, postprocess.py, dotool, notify-send, trans/ollama |
| `dictee-common.sh` | bash | Lib partagée (state, notif, debug) | `dictee`, `dictee-ptt` | flock, gdbus |
| `dictee-setup.py` | PyQt6 | GUI config (wizard + pages) | user | écrit `dictee.conf`, `rules.conf`, `dictionary.conf`, `continuation.conf` |
| `dictee-tray.py` | PyQt6 / AppIndicator | Icône systray, état visuel | systemd user | subprocess `dictee` |
| `dictee-ptt.py` | Python evdev | Push-to-talk F9 (hold/toggle) | systemd user | `dictee` (start/stop) |
| `dictee-postprocess.py` | Python | Post-traitement 10 étapes | `dictee` (pipe) | Ollama (opt.), text2num |
| `transcribe-daemon` | Rust | ASR daemon (socket Unix) | systemd user | ONNX Runtime |
| `transcribe-client` | Rust | Envoie audio au daemon | `dictee` | socket, ffmpeg |
| `transcribe` | Rust | CLI 1-shot | debug | ONNX Runtime |
| `transcribe-diarize` | Rust | TDT + Sortformer | `dictee --diarize` | ONNX Runtime |
| `transcribe-stream-diarize` | Rust | Nemotron + Sortformer (EN) | scripts streaming | ONNX Runtime |
| `vosk-transcribe` | Python | Backend Vosk | `dictee` | vosk-api |
| `whisper-transcribe` | Python | Backend faster-whisper | `dictee` | faster-whisper |
| `plasmoid/` | QML | Widget KDE Plasma 6 | plasmashell | `dictee` via exec, `/dev/shm/.dictee_state` |
| `src/lib.rs` et modules | Rust | API ASR (Parakeet, Canary, Nemotron, Sortformer) | binaires `src/bin/` | ort, tokenizers, rustfft |

---

## 15. Chiffres clés

| | |
|---|---|
| **Lignes de `dictee`** | ~1700 (bash) |
| **Tests post-traitement** | 682 (unittest) |
| **Tests pipeline** | 148 |
| **Tests vocaux manuels** | 38 |
| **Tests UI manuels** | 39 |
| **Langues ASR** | 25 (EU via Parakeet TDT v3) |
| **Langues UI (gettext)** | 6 (fr, de, es, it, uk, pt) |
| **Backends ASR** | 4 (Parakeet, Canary, Vosk, Whisper) |
| **Backends traduction** | 4 (trans, LibreTranslate, Ollama, Canary interne) |
| **Assets release** | 10 (3 .deb + 3 .rpm + .plasmoid + 3 .tar.gz) |
| **États runtime** | 9 (offline → idle → recording → transcribing → … → diarizing) |

---

*Généré le 2026-04-15 — dictée v1.3.0 / master.*

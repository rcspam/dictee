# Port du moteur de réunion en direct dans la 1.3.7 : spec

Date : 2026-09-20. Branche cible : `release/1.3` (6ff9645), worktree
/home/rapha/SOURCES/RAPHA_STT/dictee-137
Branche de travail : `1.3.7/meeting-engine`.

Suite de la spec du 2026-09-19 (port de la fenêtre, UI seule). La fenêtre est
mergée et refuse de démarrer tant que le moteur n'a pas ses deux flags. Cette
spec donne à la 1.3 ce qui manque pour que la boucle réunion en direct marche
de bout en bout : démarrer, capturer avec aperçu, arrêter, passer la main à
`dictee-transcribe` avec les noms des locuteurs, rouvrir une réunion passée.

## 1. Ce qu'on porte, et ce qu'on ne porte pas

Cinq morceaux, tous avec une référence sur master.

1. `diarize-only --stream` (Rust). Trois commits master à rejouer dans l'ordre :
   7fb5a58 (mode stream, Sortformer gardé vivant entre les chunks, ids stables),
   47af16f (revue : `diarize()` devient un wrapper de `diarize_streaming()`,
   tests), 014f99f (chunk vide et NaN sans panic, tests unitaires). Ces trois
   commits sont tout l'écart de `src/sortformer.rs` entre la 1.3 et master.
   7fb5a58 s'applique proprement (`git apply --check`), les deux autres
   suivent sur un fichier alors identique à master.
2. `transcribe-client --json-timestamps` (Rust). Master ca6fdc1 ne s'applique
   pas (le client 1.3 a reçu entre-temps dfc23fe et 8c1f4b0, dont le parseur
   d'arguments avec `--socket`). Réécriture à la main sur ce parseur.
3. `dictee-transcribe.py` accepte `--diar-engine` et `--asr-model`. Sans ça,
   argparse refuse la ligne que la fenêtre lance à l'arrêt
   (dictee-meeting-live:3331-3333) et le relais meurt en silence, stderr étant
   redirigé vers DEVNULL.
4. `dictee-transcribe.py` lit `speakers.json`. Master 488171a, s'applique
   proprement, avec son test `tests/test-speaker-matching.py`.
5. Bouton History dans `dictee-transcribe.py`. Master b640953, 96800c5,
   63b6bee, à réécrire (contexte différent), ~55 lignes. Le bouton
   « Analyze another file… » de la fenêtre compte dessus
   (dictee-meeting-live:3354-3356).

On ne touche pas au daemon (`transcribe_daemon.rs`, 580 lignes d'écart avec
master) : il connaît déjà le mode `timestamps` (lignes 272, 463, 488). On ne
porte ni les moteurs de la 1.4 ni le refactor tab-state de juillet, décision
du programme 1.3.7.

## 2. Ce qui existe déjà sur la 1.3

- Le daemon répond `[0.50s - 1.20s] mot` par ligne à `chemin\ttimestamps`.
- `transcribe-client` a `parse_client_args` avec `--help` et `--socket`, et
  `send_to_daemon(path, socket)` (lignes 35-66, 98-104).
- `diarize-only` a `--sensitivity` (diarize_only.rs:44, 55-56).
- La fenêtre 1.3 lit `{"tokens":[{"text","start_s","end_s"}]}` sur la sortie du
  client (dictee-meeting-live:807-819, 1262, 1283-1287), et parle au daemon
  Parakeet par `$XDG_RUNTIME_DIR/transcribe.sock` (ligne 789), comme le client.
- La fenêtre écrit `speakers.json` (`name_map` + `anchors`, lignes 3305-3323)
  et `meeting.meta.json` (ligne 3237) dans le dossier de la réunion.
- `dictee-transcribe.py` propage les clés `DICTEE_*` de la conf aux binaires
  en deux endroits : `_ChunkedPipelineWorker.__init__` (ligne 839, fichiers de
  plus de `CHUNK_SECONDS` = 180 s) et `_on_transcribe` (ligne 3873, QProcess).
  Le troisième chemin, `_DiarizeTranscribeWorker`, passe par le daemon déjà
  chargé : le choix du modèle n'y est pas applicable.
- Côté Rust, `DICTEE_PARAKEET_QUANT=int8` fait préférer l'encodeur int8 ; toute
  autre valeur laisse fp32 s'il est présent (execution.rs:267-273,
  model_tdt.rs:63-66, transcribe_daemon.rs:324-326).
- Les attributs que 488171a manipule existent sur la 1.3 au niveau fenêtre :
  `_speaker_name_map`, `_rename_line_edits`, `_was_diarized`, `_segments`,
  `_populate_rename_fields`, `_text_edit._speaker_name_map`.
- `--file` au démarrage et le glisser-déposer appellent `_load_audio(path)`
  après `_file_input.setText` (lignes 2189-2190, 3104-3106).

## 3. Décisions

### transcribe-client : même contrat que master, sur le parseur 1.3

- `ClientArgs` gagne `json_timestamps: bool`, `parse_client_args` reconnaît
  `--json-timestamps`, l'aide le documente (le `--help` de la fenêtre cherche
  la chaîne `--json-timestamps`, dictee-meeting-live:117).
- Le mode ne vaut que pour le chemin « fichier en argument ». Avec stdin ou le
  micro, le flag est refusé avec un message clair, pas ignoré.
- `send_to_daemon_with_mode(path, mode, socket)` envoie `chemin\tmode`, lit
  jusqu'à EOF avec le même timeout de 120 s que `send_to_daemon`, et honore
  `--socket` comme le reste du client.
- `parse_timestamps_to_json` est copié de master (lignes 397-422) sans
  changement : même échappement, même format `{:.3}`. Une ligne qui ne
  commence pas par `[` ou dont l'intervalle ne se découpe pas en deux est
  ignorée. Sortie sur stdout, une seule ligne, code 0.
- Tests unitaires Rust dans le fichier : parseur (flag seul, flag avec
  `--socket`, flag sans fichier), formateur (entrée vide donne
  `{"tokens":[]}`, guillemets et antislash échappés, ligne mal formée
  ignorée, virgule décimale absente).

### diarize-only : rejouer les trois commits, dans l'ordre

Un cherry-pick par commit, message d'origine conservé. Si un conflit apparaît
sur 47af16f ou 014f99f, résolution en prenant master comme référence, puis
`diff` de `src/sortformer.rs` contre master pour vérifier qu'il n'en reste
aucun. `tests/test_diarize_stream.sh` est livré avec, mais il a besoin des
modèles : hors CI, à lancer sur le poste avant le packaging.

### dictee-transcribe : deux flags acceptés, un seul honoré

- `--diar-engine <nom>` : accepté, stocké, `_dbg` le journalise, rien d'autre.
  La 1.3 n'a que Sortformer.
- `--asr-model <spec>` : `parakeet-int8` et `parakeet-fp32` posent
  `DICTEE_PARAKEET_QUANT` à `int8` ou `fp32` dans l'env des binaires, aux deux
  endroits où la conf est propagée (839 et 3873), après la conf pour la
  surcharger. Toute autre valeur est journalisée par `_dbg` et ignorée : le
  modèle F9 de la conf s'applique. Le chemin daemon n'est pas concerné, et la
  spec le dit dans un commentaire à côté du routage.
- Le combo de la fenêtre propose des moteurs absents de la 1.3 (faster-whisper,
  Whisper-Rust, Nemotron, dictee-meeting-live:1746-1751). Ce n'est pas l'objet
  de cette spec ; avec un de ces choix, la fenêtre échoue déjà avant l'arrêt
  (daemon introuvable). Noté pour la 1.4.

### speakers.json : cherry-pick tel quel

488171a s'applique. Son test `tests/test-speaker-matching.py` entre dans
`rust.yml`. Point de vigilance à l'exécution : `_pending_speakers_data` est lu
au `__init__` à partir de `--file`, appliqué dans le finisseur après
`_populate_rename_fields`, consommé une seule fois. Le fix 1.3 d6d3882 (un
onglet neuf n'hérite pas des renommages d'un autre) ne doit pas effacer
l'application : vérifier l'ordre des deux dans le finisseur.

### History : réécrit, avec le lecteur

`list_past_meetings(base=None)` lit `DICTEE_MEETING_DIR` puis
`~/.local/share/dictee/meetings`, prend les dossiers qui contiennent
`audio.wav`, lit le titre dans `meeting.meta.json` sous `with`, trie du plus
récent au plus ancien (préfixe date). Bouton « History » à côté du champ
fichier, `QInputDialog.getItem`. Le choix fait ce que fait le glisser-déposer
(lignes 3104-3106) : `setText`, arrêt du lecteur, `_load_audio(path)`. Le
History de master a livré sans ce chargement et l'a corrigé le 2026-07-26
(« load the player when a file is picked from History or recents ») ; on ne
reproduit pas le trou.

### Packaging

Aucun nouveau fichier livré, aucun nouveau service, aucune dépendance. Les
quatre cibles ne changent que par le rebuild des binaires. `PKGBUILD` compile
depuis les sources et n'a rien à voir passer.

### Hors périmètre

`DICTEE_TRANSCRIBE_SOCKET` dans le client (master 85bac87) : la fenêtre ne
l'utilise que pour les daemons whisper, absents de la 1.3, et le client 1.3 a
`--socket` pour le même besoin. Le durcissement 5cf21b5 du daemon : le daemon
n'est pas touché. Les moteurs 1.4. Le refactor tab-state.

## 4. Critères de réussite

1. `transcribe-client --help` et `diarize-only --help` contiennent
   `--json-timestamps` et `--stream` ; `missing_live_engine_features()` rend
   `[]` ; `offscreen-check_meeting_live_window.py` reste vert.
2. `cargo test` vert dans le conteneur glibc 2.36, avec les nouveaux tests du
   client et de sortformer. `tests/test_diarize_stream.sh` vert sur le poste.
3. `dictee-transcribe --file x.wav --diarize --diar-engine auto --asr-model
   parakeet-int8` démarre, et `DICTEE_PARAKEET_QUANT=int8` est dans l'env du
   binaire lancé (test hors écran sur `_subprocess_env` et sur le
   `QProcessEnvironment`).
4. `tests/test-speaker-matching.py` et un nouveau `tests/test-transcribe-args.py`
   (argparse, `list_past_meetings` sur un dossier temporaire avec et sans
   `meeting.meta.json`, `DICTEE_MEETING_DIR` honoré) verts en local et dans
   `rust.yml`.
5. Dans la VM kubuntu-2604, avec le deb rebuild : une réunion démarre, l'aperçu
   affiche des tokens et des locuteurs, l'arrêt ouvre `dictee-transcribe` sur
   `audio.wav` avec la diarisation cochée, les noms saisis pendant la réunion
   sont préremplis dans le panneau de renommage, History liste la réunion et
   la rouvre avec le lecteur chargé.
6. Le reste de la 1.3 ne bouge pas : les 12 suites de la CI vertes, dictée F9
   et diarisation d'un enregistrement F9 inchangées dans la VM.

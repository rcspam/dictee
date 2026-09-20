# Port de la fenêtre de réunion en direct dans la 1.3.7 : spec

Date : 2026-09-19. Branche cible : `release/1.3`, worktree
/home/rapha/SOURCES/RAPHA_STT/dictee-137

## 1. Ce qu'on porte, et ce qu'on ne porte pas

On porte `dictee-meeting-live` de master tel qu'il est aujourd'hui (3431
lignes, commit de tête de master au 2026-09-19), avec son interface complète :
titre, source, modèle d'aperçu, ligne diarisation avec sensibilité, case
« ajouter le micro », boutons démarrer / arrêter / analyse, test du son,
panneau des niveaux, aperçu en direct repliable, comportement de fenêtre.

On ne porte pas le moteur. Deux options Rust que le script exige n'existent pas
sur la 1.3 et ne font pas partie de ce chantier :

- `transcribe-client <fichier> --json-timestamps` (master ca6fdc1, +137 lignes)
- `diarize-only --stream --sensitivity N` (master 7fb5a58, +130 lignes)

Tant qu'elles manquent, la fenêtre doit refuser de démarrer une réunion avec
un message clair. Le jour où elles sont portées, la fenêtre démarre sans
aucune modification : le refus est un test de capacité, pas un interrupteur.

Les moteurs optionnels que master détecte déjà à l'exécution restent gérés par
le code tel quel : Kyutai, MOSS, Whisper-Rust, `dictee-app-capture`. Absents
sur la 1.3, ils disparaissent des listes comme ils disparaissent sur un master
sans ces binaires.

## 2. Ce qui existe déjà sur la 1.3

- La page « Réunion en direct » de dictee-setup, identique à master : dossier,
  durée des chunks, toujours au-dessus, tous les bureaux. Clés
  `DICTEE_MEETING_DIR`, `DICTEE_MEETING_CHUNK_S`, `DICTEE_MEETING_ALWAYS_ON_TOP`,
  `DICTEE_MEETING_ALL_DESKTOPS`.
- Le mode « Meeting » du tray et du plasmoid : c'est la diarisation d'un
  enregistrement F9, livrée en 1.3.6. Il reste tel quel.
- `read_state()` dans dictee-ptt.py et dictee-tray.py, qui lit
  `/dev/shm/.dictee_state`.

## 3. Décisions

### Refus propre sans moteur

`start_meeting` vérifie d'abord les deux capacités. La vérification exécute
`transcribe-client --help` et cherche `json-timestamps`, puis
`diarize-only --help` et cherche `--stream`. Sur master les deux textes d'aide
contiennent ces mots ; sur la 1.3 aucun. Si l'une manque, la fenêtre affiche un
message dans sa barre d'état et une boîte d'erreur, et reste à l'état `idle`.
Rien d'autre ne change : sources, niveaux, test du son et réglages restent
utilisables.

### Traduction

Le script de master a 37 chaînes d'interface en dur, en français, plus 16
`setText(f"…")`. Le reste de dictee est en msgid anglais traduit dans six
langues. Le port passe tout en gettext, domaine `dictee`, même amorce que
dictee-transcribe.py. Les msgid sont en anglais, la traduction française est
fournie, les cinq autres langues reçoivent des entrées vides comme les 145 à
157 chaînes déjà en attente dans chaque catalogue.

### Deux boutons dans le plasmoid, pas un

Sur master, le bouton « Meeting » du plasmoid lance la fenêtre en direct et
l'ancien mode diarisation a disparu du widget. Sur la 1.3 ce mode est une
fonction livrée. Le port ajoute un bouton « Live meeting » à côté de
« Meeting », avec le point rouge clignotant pendant l'enregistrement, et ne
touche pas au bouton existant. Même chose dans le tray : une entrée
« Live meeting » distincte des deux entrées « Meeting » existantes.

Le bouton « Live meeting » est désactivé quand l'état est `meeting-ui-open` ou
`meeting-recording`, comme sur master.

### Les deux états partagés

La fenêtre écrit `meeting-ui-open` à l'ouverture, `meeting-recording` pendant
la capture, et `idle` en sortant, dans `/dev/shm/.dictee_state`. Trois
consommateurs doivent les connaître :

- dictee-ptt.py : pendant ces deux états, toutes les touches sont
  réémises sans être interprétées, y compris la touche de dictée. Sinon F9
  déclenche une dictée par-dessus la réunion.
- dictee-tray.py : icône pour chaque état, entrée « Live meeting » désactivée,
  et les deux états comptent comme « occupé » là où le tray décide de griser.
- plasmoid main.qml : le sondage qui retombe sur `offline` ne doit pas le faire
  pendant ces deux états.

Le script bash `dictee` n'a besoin d'aucun changement : le diff master contre
1.3 sur ce fichier ne contient rien sur la réunion.

### Packaging, les quatre cibles en même temps

Nouveau binaire livré, donc, dans le même commit : build-common.sh (copie et
liste des shebangs à patcher), build-rpm.sh (copie et liste), build-tar.sh
(liste), PKGBUILD, PKGBUILD-cuda, install.sh mode tarball. Huit lignes, toutes
identiques à celles de master.

### Hors périmètre

- Les deux options Rust.
- `dictee-stream`, l'état `streaming` du plasmoid et tout ce qui va avec.
- La page wiki meeting-live et sa traduction.
- La note connue de master : la fenêtre écrit `/dev/shm/.dictee_state` sans le
  flock que le script `dictee` utilise. Comportement identique à master,
  à traiter à part.

## 4. Critères de réussite

1. `dictee-meeting-live` se construit hors écran sur la 1.3 et présente les
   mêmes widgets que master : source, modèle, diarisation, test du son,
   niveaux, aperçu.
2. Sans les deux options Rust, démarrer une réunion laisse l'état à `idle` et
   affiche le message de refus. Avec des faux binaires dont l'aide contient les
   mots attendus, la vérification passe.
3. Aucune chaîne d'interface en français en dur ne reste dans le script ; les
   six catalogues compilent ; la fenêtre s'affiche en français avec
   `LANGUAGE=fr`.
4. Pendant `meeting-ui-open`, la touche de dictée pressée sur un clavier
   factice ressort sur le périphérique de sortie de dictee-ptt au lieu de
   déclencher une dictée.
5. Le tray et le plasmoid connaissent les deux états et exposent l'entrée
   « Live meeting ».
6. `build-deb.sh` produit un paquet contenant `/usr/bin/dictee-meeting-live`
   exécutable, et le tarball aussi.
7. Tout ce qui précède tourne en CI.

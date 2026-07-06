# Transcription de réunion en direct

dictee peut enregistrer une réunion en direct et transmettre l'audio à la fenêtre de transcription pour une diarisation complète, une analyse LLM et un export.

## Démarrage rapide

1. Cliquer sur le bouton **Live meeting** du plasmoid (ou menu de la zone de notification)
2. Cliquer **▶ Démarrer** dans la fenêtre qui s'ouvre
3. Parler — l'audio est capturé en continu
4. Cliquer **⏹ Arrêter et analyser** — la fenêtre de transcription s'ouvre automatiquement avec la diarisation activée

## Fonctionnement

dictee capture l'audio en continu avec `pw-record` dans un fichier WAV. Quand l'enregistrement est arrêté, il lance `dictee-transcribe --file audio.wav --diarize`, qui prend en charge :

- La transcription (Parakeet ou le backend configuré)
- La diarisation (Sortformer)
- L'analyse LLM (le profil configuré)
- L'export

## Organisation des fichiers

Chaque réunion crée un dossier :

```
~/.local/share/dictee/meetings/YYYY-MM-DD-HHMM/
├── audio.wav              # capture audio complète (16 kHz mono)
└── meeting.meta.json      # durée, taille audio, heure de fin
```

Les transcriptions, synthèses et exports sont produits par dictee-transcribe et enregistrés dans ce dossier.

## Choisir la source audio

Par défaut, une réunion enregistre votre microphone. Vous pouvez aussi choisir une autre source pour la réunion : un autre microphone, le son du système (tout ce que vous entendez) ou une seule application.

Quand vous choisissez une seule application (par exemple votre navigateur ou votre application de réunion), seul le son de cette application est enregistré. Vous continuez à l'entendre normalement, et l'enregistrement continue de fonctionner même si vous changez de haut-parleurs ou branchez un casque pendant la réunion. Les autres applications et votre propre microphone ne sont pas touchés.

Si vous voulez aussi enregistrer votre propre voix par-dessus l'application ou le son du système capturé, cochez **Ajouter le micro** dans la fenêtre de réunion.

## Aperçu en direct (optionnel)

La fenêtre de capture dispose d'une section « Aperçu en direct » repliable. Dépliez-la pour voir la transcription s'afficher fragment par fragment (~40 s d'intervalle) pendant l'enregistrement. Il s'agit d'un aperçu bonus — la vraie transcription + diarisation est effectuée par la fenêtre de dictée qui s'ouvre à l'arrêt.

La durée des fragments (20–60 s) est réglable dans dictee-setup → page Réunion.

## Paramètres (dictee-setup → page Réunion)

- **Dossier de sauvegarde** : par défaut `~/.local/share/dictee/meetings/`
- **Durée des fragments de l'aperçu en direct** : intervalle entre les mises à jour de l'aperçu (défaut 40 s, plage 20–60 s)

## Dépannage

- « pw-record not found » → installer PipeWire (`pipewire-pulse` ou équivalent)
- « dictee-transcribe introuvable » → installer `dictee-cpu` ou `dictee-cuda` >= 1.4
- Le PTT live (dictée F9) est désactivé pendant qu'une réunion est active

## Voir aussi

- [Diarisation (fichier)](diarization.fr.md)
- [Page matériel](hardware.fr.md)

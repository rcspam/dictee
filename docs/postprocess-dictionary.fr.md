# Post-traitement — Onglet Dictionnaire

## Vue d'ensemble

L'onglet **Dictionary** permet de configurer un dictionnaire de remplacement de mots. L'ASR transcrit parfois des mots courants avec une mauvaise casse ou orthographe — le dictionnaire les corrige automatiquement.

## Fichiers de configuration

- **Utilisateur** : `~/.config/dictee/dictionary.conf`
- **Système (défaut)** : `/usr/share/dictee/dictionary.conf.default`
- **Brouillon** : `~/.config/dictee/dictionary.conf.tmp` (modifications non enregistrées)
- Variables d'environnement :
  - `DICTEE_PP_DICT=true|false` — active/désactive le dictionnaire
  - `DICTEE_PP_FUZZY_DICT=true|false` — active/désactive le matching souple

## Format du fichier

```
# ── Dictionary [*] ──────────────────────────────────────────────────
[*] api=API
[*] url=URL
[*] linux=Linux

# ── Dictionary [en] ─────────────────────────────────────────────────
[en] ai=AI

# ── Dictionary [fr] ─────────────────────────────────────────────────
[fr] sncf=SNCF
```

- **Section** : `# ── Dictionary [lang] ──` — une section par langue
- **Entrée** : `[lang] MOT=REMPLACEMENT`
- **lang** : code ISO 639-1 ou `*` (toutes les langues)
- Les sections sont créées/supprimées automatiquement selon les entrées

## Modes de matching

### Exact (toujours actif)

Remplacement sur les frontières de mots, insensible à la casse avec préservation :
- `api` → `API`
- `Api` → `API`
- `API` → `API`

### Fuzzy / souple (jellyfish)

Utilise `jaro_winkler_similarity` de la bibliothèque jellyfish (seuil 0.85) pour tolérer les petites erreurs de l'ASR :
- `Gogle` → `Google` (score > 0.85)
- `Gooooogle` → pas de match (score < 0.85)

Nécessite `pip install jellyfish`. Contrôlé par la checkbox « Fuzzy matching (jellyfish) ».

## Interface utilisateur

### Mode formulaire (défaut)

- **Barre de recherche** : icône loupe du thème + filtre par langue
- **Sections repliables** : `▾ Dictionary [fr] (7 entries)` — clic pour replier/déplier
- **Édition en ligne** : chaque entrée est éditable directement (langue, mot, remplacement)
- **Bouton ✓** : apparaît quand on modifie une entrée existante. Confirme et sauvegarde.
- **Bouton ✕** : supprime l'entrée

### Ajout d'entrées (bouton « + Add »)

- La nouvelle ligne apparaît **en bas de la fenêtre**, hors du scroll, toujours visible
- Non affectée par le filtre de recherche
- Le bouton ✓ confirme : l'entrée est placée dans la section `Dictionary [lang]` correspondante
- Si la section n'existe pas, elle est créée
- Les autres nouvelles entrées en cours ne sont pas affectées par la confirmation d'une seule
- Les entrées incomplètes (mot ou remplacement vide) sont ignorées silencieusement

### Mode édition (bouton « Edit mode »)

- Éditeur texte monospace avec le contenu brut du fichier
- Recherche Ctrl+F avec navigation et compteur d'occurrences
- À la sortie du mode édition :
  - Validation syntaxique
  - Réorganisation automatique des entrées orphelines (placées dans `Dictionary [lang]`)
- Les modifications sont écrites dans le brouillon `.tmp`

### Barre d'actions

- **🔍** : recherche (Ctrl+F) dans le mode édition
- **+ Add** : ajouter une nouvelle entrée
- **Undo / Redo** : historique (max 20 niveaux)
- **Save** : copie le brouillon `.tmp` vers le fichier officiel
- **Revert to saved** : annule toutes les modifications non enregistrées
- **Factory reset** : restaure le dictionnaire par défaut depuis le fichier système

## Flux de données

```
                    ┌─────────────────┐
                    │ dictionary.conf │ (officiel)
                    └────────┬────────┘
                             │ copie à l'ouverture
                    ┌────────▼────────┐
                    │ dictionary.conf │.tmp (brouillon)
                    └────────┬────────┘
                             │ édition dans l'UI
                             │
                    ┌────────▼────────┐
          Save ────►│ dictionary.conf │ (officiel mis à jour)
                    └─────────────────┘
```

- Le brouillon `.tmp` est créé à l'ouverture de la fenêtre post-traitement
- Toutes les modifications (ajout, suppression, mode édition) écrivent dans le `.tmp`
- **Save** copie `.tmp` → officiel
- **Fermeture sans Save** : le `.tmp` est supprimé (modifications perdues)

## Filtrage

- **Recherche** : filtre sur le mot ET le remplacement (insensible à la casse)
- **Filtre langue** : combo avec toutes les langues présentes + « All languages »
- Le filtre reste actif après confirmation d'une nouvelle entrée
- Les nouvelles entrées non confirmées ne sont pas affectées par le filtre

## Pipeline de post-traitement

Le dictionnaire est appliqué à l'étape 7 du pipeline :

1. Règles regex (`rules.conf`)
2. Rejet mauvaise langue
3. Continuation
4. Élisions (FR)
5. Nombres (text2num)
6. Typographie (FR)
7. **Dictionnaire** ← ici
8. Capitalisation

L'ordre est important : le dictionnaire passe après les élisions et la typographie pour ne pas interférer avec ces traitements.

## Notes techniques

- La préservation de casse est automatique : si l'entrée est `linux=Linux`, alors `LINUX` → `LINUX`, `Linux` → `Linux`, `linux` → `Linux`
- Le fichier est rechargé à chaque transcription — pas besoin de redémarrer le daemon
- Le matching fuzzy ajoute ~10ms par transcription (négligeable)
- Les entrées `[*]` sont appliquées pour toutes les langues, les `[fr]` uniquement quand `DICTEE_LANG_SOURCE=fr`

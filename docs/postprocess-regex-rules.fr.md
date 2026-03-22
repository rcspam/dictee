# Post-traitement — Onglet Règles regex

## Vue d'ensemble

L'onglet **Regex rules** permet de configurer les règles de substitution regex appliquées au texte transcrit par l'ASR. Les règles sont exécutées séquentiellement, dans l'ordre du fichier.

## Fichiers de configuration

- **Utilisateur** : `~/.config/dictee/rules.conf`
- **Système (défaut)** : `/usr/share/dictee/rules.conf.default`
- Les règles utilisateur sont appliquées **après** les règles système
- Variable d'environnement : `DICTEE_PP_RULES=true|false`

## Format des règles

```
[lang] /PATTERN/REMPLACEMENT/FLAGS
```

- **lang** : code ISO 639-1 (`fr`, `en`, `de`, `es`, `it`, `pt`, `uk`) ou `*` (toutes les langues)
- **PATTERN** : expression régulière Python
- **REMPLACEMENT** : texte de remplacement (`\n` = retour ligne, `\t` = tabulation, `\1` = groupe capturé)
- **FLAGS** :
  - `i` — insensible à la casse
  - `g` — global (toutes les occurrences)
  - `m` — multiligne (`^` et `$` matchent début/fin de chaque ligne)

## Sections (STEPs)

Les règles sont organisées par sections exécutées dans l'ordre :

### STEP 1 — Annotations non-vocales

Supprime les annotations non-vocales ajoutées par Whisper/Parakeet.

```
[*] /\([^)]*\)//g        # (applaudissements), (musique), etc.
[*] /\[[^\]]*\]//g       # [musique], [rires], etc.
```

### STEP 2 — Mots de remplissage / hésitations

Supprime les mots de remplissage détectés par l'ASR.

```
[fr] /[,.\s]*\b(euh|euhm?|hum|hmm|ben|bah|hein)\b[,.\s]*/ /ig
[en] /[,.\s]*\b(uh|um|hmm|mm|mhm|mmm)\b[,.\s]*/ /ig
```

Chaque langue a ses propres mots d'hésitation.

### STEP 3 — Commandes vocales

Commandes vocales transformées en caractères de contrôle ou ponctuation. C'est la section la plus importante.

**Sous-sections par langue** : chaque langue a sa propre sous-section (`# ── French ──`, `# ── English ──`, etc.).

**Les règles `[*]` sont interdites** dans cette section — les commandes vocales sont spécifiques à chaque langue.

Exemples français :
```
[fr] /[,.\s]*point à la ligne[,.\s]*/.\n/ig
[fr] /[,.\s]*virgule[,.\s]*/, /ig
[fr] /[,.\s]*nouveau paragraphe[,.\s]*/\n\n/ig
```

**Patterns courants** :
- `[,.\s]*` — absorbe la ponctuation et les espaces que l'ASR ajoute autour des commandes
- `^[,.\s]*...[,.\s]*` avec flag `m` — matche en début de ligne (ex : "à la ligne" seul)
- `(?:a|b|c)` — alternations non-capturantes

**Gestion du cyrillique** : Parakeet confond parfois les commandes françaises avec du cyrillique sur les audios courts. Les règles `^[,.\s]*[А-Яа-я]...` capturent ces misdétections.

### STEP 4 — Déduplication de mots

Corrige un bug connu de Parakeet qui duplique des mots.

```
[*] /\b(\w+)\s+\1\b/\1/ig    # "je je" → "je"
```

### STEP 5 — Nettoyage de ponctuation

Déduplique la ponctuation (l'ASR + les commandes vocales peuvent doubler).

```
[*] /\.{3,}/…/g    # ... → …
[*] /\?+/?/g       # ?? → ?
[*] /!+/!/g        # !! → !
```

### STEP 6 — Nettoyage final

Nettoyage typographique final.

```
[*] /([.!?…»\)])([A-Za-zÀ-ÿ])/\1 \2/g    # Espace après ponctuation collée
[*] /(\S)«/\1 «/g                          # Espace avant guillemet ouvrant
```

## Interface utilisateur

### Formulaire « Add a rule »

- **Langue** : combo avec toutes les langues + `*`
- **Pattern** : ce que l'ASR dit
- **Remplacement** : le remplacement souhaité
- **Flags** : `ig` par défaut
- **Insert in** : combo avec les sections STEP + « At cursor » (défaut) + « End of file »
- **Position** : « at end » ou « at beginning » de la section (grisé si « At cursor »)
- **Record** : enregistre un audio, transcrit et remplit le champ pattern. Détection automatique du cyrillique.

### Insertion intelligente

- Les règles sont insérées dans la **sous-section langue** correspondante (`# ── French ──`)
- Si la sous-section n'existe pas, elle est créée automatiquement
- Les règles `[*]` sont insérées directement (pas de sous-section)
- Les règles `[*]` sont **interdites** dans STEP 3 (Commandes vocales)

### Recherche (Ctrl+F)

- Barre de recherche avec icône loupe du thème, navigation ▲/▼, compteur d'occurrences
- Recherche circulaire (boucle en fin de fichier)
- Sélection jaune foncé pendant la recherche
- Escape ou 2ème clic ferme la barre

### Bouton « ↓ Test »

Envoie le pattern de la ligne courante dans le panneau Test. Le pattern regex est converti en texte lisible (les séquences d'échappement sont retirées).

### Coloration syntaxique

- **Gris** : commentaires `#`
- **Jaune foncé gras** : en-têtes de section `═══`
- **Bleu gras** : `[lang]`
- **Orange** : pattern
- **Vert** : remplacement
- **Violet** : flags

## Ordre d'exécution dans le pipeline

L'ordre est critique. Les règles sont appliquées dans l'ordre du fichier :

1. Les annotations sont supprimées en premier (sinon elles seraient traitées comme du texte)
2. Les hésitations sont supprimées (sinon « euh virgule » serait interprété comme une commande)
3. Les commandes vocales sont converties (le cœur du traitement)
4. La déduplication passe après les commandes (sinon « point point » serait dédupliqué avant d'être converti)
5. La ponctuation est nettoyée après tout
6. Le nettoyage final assure la typographie

## Notes techniques

- Les élisions françaises (`l' arbre → l'arbre`) sont gérées par `fix_elisions()` dans `dictee-postprocess.py`, **pas** par les règles regex. Voir l'onglet « Language rules ».
- La typographie française (espaces insécables) est aussi gérée séparément.
- Les règles regex sont rechargées à chaque transcription — pas besoin de redémarrer le daemon.

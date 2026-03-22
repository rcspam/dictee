# Post-traitement — Onglet Language rules

## Vue d'ensemble

L'onglet **Language rules** contient les règles de post-traitement spécifiques à chaque langue qui ne peuvent pas être exprimées comme de simples substitutions regex. Ces règles gèrent les élisions, contractions, ponctuation inversée et conventions typographiques propres à chaque langue.

Les règles ne sont appliquées que lorsque la langue source (`DICTEE_LANG_SOURCE`) correspond.

## Langues supportées

### Français [fr]

**Élisions** (`DICTEE_PP_ELISIONS`)

Corrige les élisions manquantes devant les voyelles et h muets, avec gestion des h aspirés.

| Entrée | Sortie | Règle |
|--------|--------|-------|
| le arbre | l'arbre | élision article |
| de eau | d'eau | élision préposition |
| je ai | j'ai | élision pronom |
| si il vient | s'il vient | contraction spéciale |
| le haricot | le haricot | h aspiré — PAS d'élision |
| le homme | l'homme | h muet — élision |

Mots d'élision : `je, me, te, se, le, la, ne, de, que, ce`

Exceptions h aspiré : ~70 mots dont `hache, haie, haine, hall, hamac, handicap, hangar, haricot, hasard, haut, héros, hibou, hockey, homard, honte, hurler, hutte`...

**Typographie** (`DICTEE_PP_TYPOGRAPHY`)

Insère des espaces insécables avant la ponctuation haute française, conformément aux règles typographiques.

| Avant | Après |
|-------|-------|
| `mot:` | `mot :` (NBSP avant `:`) |
| `mot;` | `mot ;` (NNBSP avant `;`) |
| `mot!` | `mot !` (NNBSP avant `!`) |
| `mot?` | `mot ?` (NNBSP avant `?`) |
| `"texte"` | `« texte »` (guillemets français avec NBSP) |

NBSP = U+00A0, NNBSP = U+202F (espace fine insécable)

---

### Italiano [it]

**Élisions et contractions** (`DICTEE_PP_ELISIONS_IT`)

Gère les élisions italiennes devant les voyelles et les contractions prépositionnelles (prépositions articulées).

**Élisions :**

| Entrée | Sortie |
|--------|--------|
| lo uomo | l'uomo |
| la amica | l'amica |
| una amica | un'amica |
| di accordo | d'accordo |
| ci è | c'è |
| quello uomo | quell'uomo |
| come è | com'è |
| dove è | dov'è |

**Contractions prépositionnelles** (appliquées avant les élisions pour éviter les conflits) :

| Entrée | Sortie | Entrée | Sortie |
|--------|--------|--------|--------|
| di il | del | a il | al |
| di lo | dello | a lo | allo |
| di la | della | a la | alla |
| di i | dei | a i | ai |
| di gli | degli | a gli | agli |
| di le | delle | a le | alle |
| da il | dal | in il | nel |
| da lo | dallo | in lo | nello |
| da la | dalla | in la | nella |
| su il | sul | su lo | sullo |
| su la | sulla | su le | sulle |

La casse est préservée : `DI IL LIBRO` → `DEL LIBRO`, `Di Il` → `Del Il`.

---

### Español [es]

**Contractions et ponctuation inversée** (`DICTEE_PP_SPANISH`)

**Contractions** (seulement 2 en espagnol) :

| Entrée | Sortie | Note |
|--------|--------|------|
| a el parque | al parque | contraction obligatoire |
| de el libro | del libro | contraction obligatoire |
| a El Salvador | a El Salvador | nom propre — PAS de contraction |
| de El Greco | de El Greco | nom propre — PAS de contraction |

Les noms propres sont détectés par la majuscule qui suit `el`.

**Ponctuation inversée :**

| Entrée | Sortie |
|--------|--------|
| Cómo estás? | ¿Cómo estás? |
| Qué hora es? | ¿Qué hora es? |

Le `¿` inversé est ajouté devant les mots interrogatifs (`qué, quién, cómo, cuándo, dónde, por qué, cuál, cuánto`). Le `¡` inversé est ajouté devant les phrases exclamatives finissant par `!`.

Les marques déjà présentes ne sont pas dupliquées.

---

### Português [pt]

**Contractions** (`DICTEE_PP_PORTUGUESE`)

Le portugais a de nombreuses contractions fusionnées (pas d'apostrophe, les mots fusionnent).

**Préposition + articles :**

| Entrée | Sortie | Entrée | Sortie |
|--------|--------|--------|--------|
| de o | do | em o | no |
| de a | da | em a | na |
| de os | dos | em os | nos |
| de as | das | em as | nas |
| por o | pelo | em um | num |
| por a | pela | em uma | numa |
| por os | pelos | | |
| por as | pelas | | |

**Préposition + démonstratifs :**

| Entrée | Sortie | Entrée | Sortie |
|--------|--------|--------|--------|
| de este | deste | em este | neste |
| de esta | desta | em esta | nesta |
| de esse | desse | em esse | nesse |
| de essa | dessa | em essa | nessa |
| de aquele | daquele | em aquele | naquele |
| de aquilo | daquilo | | |

**Préposition + pronoms :**

| Entrée | Sortie | Entrée | Sortie |
|--------|--------|--------|--------|
| de ele | dele | em ele | nele |
| de ela | dela | em ela | nela |
| de eles | deles | em eles | neles |
| de elas | delas | em elas | nelas |

La casse est préservée : `De O livro` → `Do livro`, `DE O` → `DO`.

---

### Deutsch [de]

**Contractions et typographie** (`DICTEE_PP_GERMAN`)

**Contractions prépositionnelles :**

| Entrée | Sortie | Entrée | Sortie |
|--------|--------|--------|--------|
| an dem | am | an das | ans |
| auf das | aufs | bei dem | beim |
| in dem | im | in das | ins |
| von dem | vom | zu dem | zum |
| zu der | zur | | |

**Typographie :**

Les guillemets anglais `"texte"` sont convertis en guillemets allemands `„texte"` (U+201E ouverture en bas, U+201C fermeture en haut).

---

### Nederlands [nl]

**Contractions** (`DICTEE_PP_DUTCH`)

**Contractions pronom/article :**

| Entrée | Sortie | Note |
|--------|--------|------|
| het is mooi | 't is mooi | réduction d'article |
| een boek | 'n boek | uniquement devant minuscule |
| een Amsterdam | een Amsterdam | nom propre — PAS de contraction |

**Expressions temporelles :**

| Entrée | Sortie |
|--------|--------|
| in de morgens | 's morgens |
| in de avonds | 's avonds |
| in de nachts | 's nachts |
| in de middags | 's middags |

---

### Română [ro]

**Contractions et typographie** (`DICTEE_PP_ROMANIAN`)

**Contractions de négation :**

| Entrée | Sortie |
|--------|--------|
| nu am | n-am |
| nu ai | n-ai |
| nu a | n-a |
| nu au | n-au |
| nu o | n-o |

**Contractions prépositionnelles :**

| Entrée | Sortie |
|--------|--------|
| într o | într-o |
| într un | într-un |
| dintr o | dintr-o |
| dintr un | dintr-un |
| printr o | printr-o |
| printr un | printr-un |

**Typographie :**

Les guillemets anglais `"texte"` sont convertis en guillemets roumains `„texte"` (même style que l'allemand).

---

## Position dans le pipeline

Les règles de langue sont appliquées à l'**étape 6** du pipeline de post-traitement :

1. Règles regex (`rules.conf`)
2. Rejet mauvaise langue
3. Continuation
4. **Élisions (FR)** ← ici
5. **Italien / Espagnol / Portugais / Allemand / Néerlandais / Roumain** ← ici
6. Nombres (text2num)
7. Typographie (FR)
8. Dictionnaire
9. Capitalisation

Les règles de langue s'exécutent avant la conversion des nombres et le dictionnaire pour ne pas interférer avec ces étapes.

## Notes techniques

- Chaque langue est contrôlée par une variable d'environnement indépendante
- Les règles sont actives par défaut (`true`) — désactivées uniquement si explicitement mis à `false`
- La casse est préservée dans toutes les contractions (minuscules, Titre, MAJUSCULES)
- Les frontières de mots (`\b`) empêchent les faux positifs sur les sous-chaînes
- Les contractions sont appliquées avant les élisions (italien) pour éviter les conflits (ex : `di il` → `del` et non `d'il`)
- La détection des noms propres espagnols utilise la majuscule après `el` pour ne pas contracter `a El Salvador`
- Le néerlandais `een` → `'n` uniquement devant les minuscules pour ne pas contracter devant les noms propres
- Toutes les fonctions gèrent les chaînes vides sans erreur

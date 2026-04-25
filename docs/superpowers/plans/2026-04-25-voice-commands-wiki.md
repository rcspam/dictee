# Plan A — Page wiki Voice-Commands

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Créer une page wiki dédiée référençant toutes les commandes vocales pour les 7 langues supportées (fr, en, de, es, it, pt, uk), accessible depuis le sidebar et cross-linkée depuis les pages connexes.

**Architecture:** Une seule page Markdown par langue (EN + FR). Toutes les langues techniques (fr/en/de/es/it/pt/uk) sur la même page, organisées par ancres `#fr`, `#en`, etc. Tableaux par catégorie. Notes sur les valeurs configurables (SUFFIX, mot de continuation).

**Tech Stack:** Markdown GitHub Wiki (CommonMark + GitHub extensions). Repo `dictee.wiki` sur `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/`.

---

## File Structure

| Fichier | Rôle |
|---|---|
| `Voice-Commands.md` (création) | Page principale EN avec sections par langue |
| `fr-Voice-Commands.md` (création) | Version FR symétrique |
| `_Sidebar.md` (modif) | Ajouter entrée toplevel sous « Post-processing / Post-traitement » |
| `Numbers-Dates-Continuation.md` (modif EN+FR) | Cross-link en début de section « Resetting the continuation context » et dans la section « Voice commands » si elle existe |
| `Rules-and-Dictionary.md` (modif EN+FR) | Cross-link dans la section commandes vocales |

Source de données : `/home/rapha/SOURCES/RAPHA_STT/dictee/rules.conf.default` (état du repo dictee, branche master).

---

## Task 1: Audit des commandes vocales par langue

**Files:**
- Read: `/home/rapha/SOURCES/RAPHA_STT/dictee/rules.conf.default`
- Notes: aucun fichier créé, juste extraction mentale ou notes éphémères

- [ ] **Step 1: Extraire les règles par langue**

Pour chaque langue, lister les voice commands grouped par catégorie. Commande à utiliser :

```bash
for lang in fr en de es it pt uk; do
  echo "=== $lang ==="
  grep -E "^\[$lang\]" /home/rapha/SOURCES/RAPHA_STT/dictee/rules.conf.default
done
```

- [ ] **Step 2: Catégoriser**

Pour chaque langue, mapper les rules dans 7 catégories :
1. Continuation et reset (rules `\x04`, mot de continuation)
2. Sauts de ligne (rules `\n`, `\n\n`)
3. Ponctuation (`,`, `.`, `:`, `;`, `?`, `!`, `…`)
4. Guillemets et parenthèses (`"`, `«`, `»`, `(`, `)`)
5. Formatage Markdown (`#`, `##`, `###`)
6. Caractères spéciaux (`\t`, `_`, `-`)
7. Raccourcis clavier vocaux (`\x01` ctrl+j)

Note les variantes ASR (Cyrillic misdetections, alternatives orthographiques) en colonne « Variantes ».

- [ ] **Step 3: Vérifier les valeurs configurables**

```bash
grep -E "%SUFFIX_|CONTINUATION_WORDS_" /home/rapha/SOURCES/RAPHA_STT/dictee/rules.conf.default \
  /home/rapha/SOURCES/RAPHA_STT/dictee/dictee-postprocess.py \
  /home/rapha/SOURCES/RAPHA_STT/dictee/continuation.conf.default 2>/dev/null
```

Note : pour chaque langue, identifier le SUFFIX par défaut et le mot de continuation par défaut.

- [ ] **Step 4: Pas de commit (étape de recherche)**

---

## Task 2: Créer Voice-Commands.md (EN) — skeleton + section FR

**Files:**
- Create: `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/Voice-Commands.md`

- [ ] **Step 1: Créer le fichier avec header et TOC**

```markdown
# Voice Commands

dictée maps spoken keywords to typed text via post-processing rules. This page lists every voice command available, per language, with the resulting output and known ASR variants.

The rules live in `/usr/share/dictee/rules.conf.default` (system) and `~/.config/dictee/rules.conf` (user). Behavior is implemented in `dictee-postprocess.py`.

**See also:**
- [Rules and Dictionary](Rules-and-Dictionary) — how rules are loaded and applied
- [Numbers-Dates-Continuation](Numbers-Dates-Continuation) — number conversion and continuation context
- [Post-Processing-Overview](Post-Processing-Overview) — pipeline overview

## Languages

- [French (fr)](#french-fr)
- [English (en)](#english-en)
- [German (de)](#german-de)
- [Spanish (es)](#spanish-es)
- [Italian (it)](#italian-it)
- [Portuguese (pt)](#portuguese-pt)
- [Ukrainian (uk)](#ukrainian-uk)

## Configurable values

Two values inside voice commands are user-configurable via `dictee-setup`:

| Value | Where stored | Example default |
|---|---|---|
| `SUFFIX_<LANG>` | `~/.config/dictee.conf` | `SUFFIX_FR=final` (used in `point final` → `.`) |
| Continuation keyword | `~/.config/dictee/continuation.conf` | `minuscule` (FR), `continue` (EN), etc. |

Commands using these values are flagged below with `{suffix}` or `{cont}`.
```

- [ ] **Step 2: Section French (fr)**

Pour chaque catégorie, un tableau Commande / Résultat / Variantes ASR / Notes. Exemple pour FR :

```markdown
## French (fr)

### 1. Continuation and reset

| Spoken | Result | Notes |
|---|---|---|
| `{cont}` (default: `minuscule`) | continues previous sentence | Configurable + alias supported |
| `nouvelle phrase` / `nouvelles phrases` | resets continuation context | Anchored at start of dictation only |

### 2. Line breaks

| Spoken | Result | Variants |
|---|---|---|
| `à la ligne` | `\n` | also `la ligne` (Parakeet drops "à") |
| `retour à la ligne` / `saut de ligne` | `\n` | |
| `nouveau paragraphe` / `nouvel paragraphe` / `nouvelle alinéa` | `\n\n` | |
| `point à la ligne` | `.\n` | |
| `virgule à la ligne` | `,\n` | |
| `point virgule à la ligne` | `;\n` | |
| `deux points à la ligne` | `:\n` | |
| `point d'interrogation à la ligne` | `?\n` | |
| `point d'exclamation à la ligne` | `!\n` | |
| `points de suspension à la ligne` | `…\n` | |

### 3. Punctuation

| Spoken | Result | Notes |
|---|---|---|
| `virgule` | `,` | |
| `point {suffix}` (default: `point final`) | `.` | Suffix configurable to disambiguate from word "point" |
| `deux points {suffix}` | `: ` | |
| `point virgule` | `; ` | |
| `point d'interrogation` | `?` | |
| `point d'exclamation` | `!` | |
| `points de suspension` / `trois petits points` / `3 petits points` | `…` | |
| `apostrophe` | `'` | |

### 4. Quotes and brackets

| Spoken | Result |
|---|---|
| `ouvrir guillemets` / `ouvrez guillemets` / `ouvrir les guillemets` | `« ` |
| `fermer guillemets` / `fermez guillemets` / `fermer les guillemets` | ` »` |
| `ouvrir parenthèse` / `ouvrez parenthèse` / `ouvrir une parenthèse` | ` (` |
| `fermer parenthèse` / `fermez parenthèse` / `fermer la parenthèse` | `) ` |

### 5. Markdown formatting

| Spoken | Result |
|---|---|
| `dièse espace` / `# espace` | `# ` (h1) |
| `double dièse` / `dièse dièse espace` | `## ` (h2) |
| `triple dièse` / `dièse dièse dièse espace` | `### ` (h3) |

### 6. Special characters

| Spoken | Result |
|---|---|
| `tabulation` | `\t` |
| `tiret` | `- ` |
| `tiret bas` / `tire-et-bas` / `tiret du huit` | `_` |
| `tiret du six` | `-` |

### 7. Voice keyboard shortcuts

| Spoken | Result |
|---|---|
| `contrôle j` / `ctrl j` / `control j` | Ctrl+J (newline without submit) |

### ASR misdetection workarounds (fr)

Parakeet sometimes transcribes short FR audio as Cyrillic. The following Cyrillic patterns are also mapped to `\n` (« à la ligne ») as a recovery:

- patterns containing `лин` or `ляни` (broad)
- isolated `Карень`, `Аровин(я|и)`, `Олю...` — common misdetections
- `[àÀaA] la vigne`, `[Ll]a ligne`, `[Aa]llez ligne` — French phonetic confusions
```

- [ ] **Step 3: Vérifier le rendu local**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
# Rendu rapide via grip ou cat
grep -c "^###" Voice-Commands.md
# Doit retourner au moins 7 (les 7 catégories FR)
```

- [ ] **Step 4: Commit**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
git add Voice-Commands.md
git commit -m "docs(wiki): start Voice-Commands page (EN skeleton + French section)"
```

---

## Task 3: Voice-Commands.md (EN) — sections English et German

**Files:**
- Modify: `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/Voice-Commands.md`

- [ ] **Step 1: Ajouter section English (en)**

Append à la fin du fichier :

```markdown
## English (en)

### 1. Continuation and reset

| Spoken | Result | Notes |
|---|---|---|
| `{cont}` (default: `continue`) | continues previous sentence | Configurable + alias |
| `new sentence` / `new sentences` | resets continuation context | |

### 2. Line breaks

| Spoken | Result |
|---|---|
| `new line` / `next line` / `line break` | `\n` |
| `new paragraph` / `next paragraph` | `\n\n` |
| `period new line` / `full stop new line` | `.\n` |
| `comma new line` | `,\n` |
| `colon new line` | `:\n` |
| `semicolon new line` | `;\n` |
| `question mark new line` | `?\n` |
| `exclamation mark new line` / `exclamation point new line` | `!\n` |

### 3. Punctuation

| Spoken | Result | Notes |
|---|---|---|
| `comma` | `,` | |
| `period {suffix}` / `full stop {suffix}` | `.` | Suffix configurable |
| `colon {suffix}` | `: ` | |
| `semicolon` | `; ` | |
| `question mark` | `? ` | |
| `exclamation mark` / `exclamation point` | `! ` | |
| `ellipsis` / `dot dot dot` / `three dots` | `… ` | |

### 4. Quotes and brackets

| Spoken | Result |
|---|---|
| `open quote` / `start quote` / `open quotation marks` | `"` |
| `close quote` / `end quote` / `close quotation marks` | `"` |
| `open paren` / `open parenthesis` | ` (` |
| `close paren` / `close parenthesis` | `) ` |

### 5. Markdown formatting

| Spoken | Result |
|---|---|
| `hash space` | `# ` |
| `hash hash space` | `## ` |
| `hash hash hash space` | `### ` |

### 6. Special characters

| Spoken | Result |
|---|---|
| `tab` | `\t` |
| `hyphen` / `dash` | `- ` |
```

- [ ] **Step 2: Ajouter section German (de)**

Append :

```markdown
## German (de)

### 1. Continuation and reset

| Spoken | Result | Notes |
|---|---|---|
| `{cont}` (default: `klein`) | continues previous sentence | |
| `neuer Satz` / `neue Sätze` | resets continuation context | |

### 2. Line breaks

| Spoken | Result |
|---|---|
| `neue Zeile` / `Zeilenumbruch` | `\n` |
| `neuer Absatz` | `\n\n` |
| `Punkt neue Zeile` | `.\n` |
| `Komma neue Zeile` | `,\n` |
| `Doppelpunkt neue Zeile` | `:\n` |
| `Semikolon neue Zeile` | `;\n` |
| `Fragezeichen neue Zeile` | `?\n` |
| `Ausrufezeichen neue Zeile` | `!\n` |

### 3. Punctuation

| Spoken | Result | Notes |
|---|---|---|
| `Komma` | `,` | |
| `Punkt {suffix}` | `.` | Suffix configurable |
| `Doppelpunkt` | `: ` | |
| `Semikolon` | `; ` | |
| `Fragezeichen` | `?` | |
| `Ausrufezeichen` | `!` | |
| `Auslassungspunkte` / `drei Punkte` / `3 Punkte` | `…` | |

### 4. Quotes and brackets

| Spoken | Result |
|---|---|
| `Anführungszeichen auf` | `"` |
| `Anführungszeichen zu` | `"` |
| `Klammer auf` | `(` |
| `Klammer zu` | `)` |

### 5. Special characters

| Spoken | Result |
|---|---|
| `Tabulator` | `\t` |
| `Bindestrich` / `Strich` | `- ` |
```

- [ ] **Step 3: Commit**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
git add Voice-Commands.md
git commit -m "docs(wiki): Voice-Commands — add English and German sections"
```

---

## Task 4: Voice-Commands.md (EN) — sections Spanish, Italian, Portuguese, Ukrainian

**Files:**
- Modify: `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/Voice-Commands.md`

- [ ] **Step 1: Ajouter section Spanish (es)**

```markdown
## Spanish (es)

### 1. Continuation and reset

| Spoken | Result | Notes |
|---|---|---|
| `{cont}` (default: `minúscula`) | continues previous sentence | |
| `nueva frase` / `nuevas frases` | resets continuation context | |

### 2. Line breaks

| Spoken | Result |
|---|---|
| `nueva línea` | `\n` |
| `nuevo párrafo` / `punto y aparte` | `\n\n` |
| `signo de interrogación nueva línea` | `?\n` |
| `signo de exclamación nueva línea` | `!\n` |
| `dos puntos nueva línea` | `:\n` |
| `punto y coma nueva línea` | `;\n` |
| `coma nueva línea` | `,\n` |

### 3. Punctuation

| Spoken | Result | Notes |
|---|---|---|
| `coma {suffix}` | `, ` | |
| `punto {suffix}` / `punto final {suffix}` | `.` | |
| `dos puntos` | `: ` | |
| `punto y coma` | `; ` | |
| `(signo de) interrogación` | `?` | |
| `(signo de) exclamación` | `!` | |
| `puntos suspensivos` / `tres puntos` | `…` | |

### 4. Quotes and brackets

| Spoken | Result |
|---|---|
| `abrir comillas` | `"` |
| `cerrar comillas` | `"` |
| `abrir (el/los/la/las) paréntesis` | `(` |
| `cerrar (el/los/la/las) paréntesis` | `)` |

### 5. Special characters

| Spoken | Result |
|---|---|
| `tabulación` | `\t` |
| `guión` | `- ` |
```

- [ ] **Step 2: Ajouter section Italian (it)**

```markdown
## Italian (it)

### 1. Continuation and reset

| Spoken | Result | Notes |
|---|---|---|
| `{cont}` (default: `minuscola`) | continues previous sentence | |
| `nuova frase` / `nuove frasi` | resets continuation context | Plural changes vowel: `frase` → `frasi` |

### 2. Line breaks

| Spoken | Result |
|---|---|
| `nuova riga` / `a capo` | `\n` |
| `nuovo paragrafo` | `\n\n` |
| `punto interrogativo a capo` | `?\n` |
| `punto esclamativo a capo` | `!\n` |
| `due punti a capo` | `:\n` |
| `punto e virgola a capo` | `;\n` |
| `virgola a capo` | `,\n` |

### 3. Punctuation

| Spoken | Result | Notes |
|---|---|---|
| `virgola` | `, ` | |
| `punto {suffix}` | `.` | |
| `due punti` | `: ` | |
| `punto e virgola` | `; ` | |
| `(punto) interrogativo` | `?` | |
| `(punto) esclamativo` | `!` | |
| `puntini di sospensione` / `tre puntini` / `puntini` | `…` | |

### 4. Quotes and brackets

| Spoken | Result |
|---|---|
| `apri virgolette` | `"` |
| `chiudi virgolette` | `"` |
| `apri (la/le) parentesi` | `(` |
| `chiudi (la/le) parentesi` | `)` |

### 5. Special characters

| Spoken | Result |
|---|---|
| `tabulazione` | `\t` |
| `trattino` | `- ` |
```

- [ ] **Step 3: Ajouter section Portuguese (pt)**

```markdown
## Portuguese (pt)

### 1. Continuation and reset

| Spoken | Result | Notes |
|---|---|---|
| `{cont}` (default: `minúscula`) | continues previous sentence | |
| `nova frase` / `novas frases` | resets continuation context | |

### 2. Line breaks

| Spoken | Result |
|---|---|
| `nova linha` | `\n` |
| `novo parágrafo` | `\n\n` |
| `ponto de interrogação nova linha` | `?\n` |
| `ponto de exclamação nova linha` | `!\n` |
| `dois pontos nova linha` | `:\n` |
| `ponto e vírgula nova linha` | `;\n` |
| `vírgula nova linha` | `,\n` |

### 3. Punctuation

| Spoken | Result | Notes |
|---|---|---|
| `vírgula` | `, ` | |
| `ponto {suffix}` / `ponto final {suffix}` | `.` | |
| `dois pontos` | `: ` | |
| `ponto e vírgula` | `; ` | |
| `ponto de interrogação` | `?` | |
| `ponto de exclamação` | `!` | |
| `reticências` / `três pontos` | `…` | |

### 4. Quotes and brackets

| Spoken | Result |
|---|---|
| `abrir aspas` | `"` |
| `fechar aspas` | `"` |
| `abrir (os/as/o/a) parênteses` | `(` |
| `fechar (os/as/o/a) parênteses` | `)` |

### 5. Special characters

| Spoken | Result |
|---|---|
| `tabulação` | `\t` |
| `hífen` | `- ` |
```

- [ ] **Step 4: Ajouter section Ukrainian (uk)**

```markdown
## Ukrainian (uk)

### 1. Continuation and reset

| Spoken | Result | Notes |
|---|---|---|
| `{cont}` (default: `рядкова`) | continues previous sentence | |
| `нове речення` / `нові речення` | resets continuation context | |

### 2. Line breaks

| Spoken | Result |
|---|---|
| `новий рядок` | `\n` |
| `новий абзац` | `\n\n` |
| `знак питання новий рядок` | `?\n` |
| `знак оклику новий рядок` | `!\n` |
| `двокрапка новий рядок` | `:\n` |
| `крапка з комою новий рядок` | `;\n` |
| `кома новий рядок` | `,\n` |

### 3. Punctuation

| Spoken | Result | Notes |
|---|---|---|
| `кома {suffix}` | `, ` | |
| `крапка {suffix}` | `.` | |
| `двокрапка` | `: ` | |
| `крапка з комою` | `; ` | |
| `знак питання` | `?` | |
| `знак оклику` | `!` | |
| `три крапки` | `…` | |

### 4. Quotes and brackets

| Spoken | Result |
|---|---|
| `відкрити лапки` | `"` |
| `закрити лапки` | `"` |
| `відкрити дужки` | `(` |
| `закрити дужки` | `)` |

### 5. Special characters

| Spoken | Result |
|---|---|
| `табуляція` | `\t` |
| `дефіс` | `- ` |

> Note: number conversion (cardinals, decimals) is **not** supported for Ukrainian — text_to_num has no Ukrainian backend.
```

- [ ] **Step 5: Vérifier le fichier**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
# Compter les sections de niveau ## (langues) — doit être 7
grep -c "^## " Voice-Commands.md
# Compter les sections ### dans toutes les langues — doit être >= 35 (7 langues × 5+ catégories)
grep -c "^### " Voice-Commands.md
```

- [ ] **Step 6: Commit**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
git add Voice-Commands.md
git commit -m "docs(wiki): Voice-Commands — complete with es, it, pt, uk"
```

---

## Task 5: Créer fr-Voice-Commands.md (traduction symétrique)

**Files:**
- Create: `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/fr-Voice-Commands.md`

- [ ] **Step 1: Créer le fichier avec entête et TOC traduits**

```markdown
# Commandes vocales

dictée mappe des mots-clés parlés vers du texte tapé via des règles de post-traitement. Cette page liste toutes les commandes vocales disponibles, par langue, avec le résultat produit et les variantes ASR connues.

Les règles vivent dans `/usr/share/dictee/rules.conf.default` (système) et `~/.config/dictee/rules.conf` (utilisateur). Le comportement est implémenté dans `dictee-postprocess.py`.

**Voir aussi :**
- [Règles et dictionnaire](fr-Rules-and-Dictionary) — comment les règles sont chargées et appliquées
- [Numbers-Dates-Continuation](fr-Numbers-Dates-Continuation) — conversion des nombres et contexte de continuation
- [Vue d'ensemble du post-traitement](fr-Post-Processing-Overview)

## Langues

- [Français (fr)](#français-fr)
- [Anglais (en)](#anglais-en)
- [Allemand (de)](#allemand-de)
- [Espagnol (es)](#espagnol-es)
- [Italien (it)](#italien-it)
- [Portugais (pt)](#portugais-pt)
- [Ukrainien (uk)](#ukrainien-uk)

## Valeurs configurables

Deux valeurs dans les commandes vocales sont configurables par l'utilisateur via `dictee-setup` :

| Valeur | Stockée dans | Exemple par défaut |
|---|---|---|
| `SUFFIX_<LANG>` | `~/.config/dictee.conf` | `SUFFIX_FR=final` (utilisé dans `point final` → `.`) |
| Mot de continuation | `~/.config/dictee/continuation.conf` | `minuscule` (FR), `continue` (EN), etc. |

Les commandes utilisant ces valeurs sont marquées ci-dessous avec `{suffix}` ou `{cont}`.
```

- [ ] **Step 2: Copier les sections par langue depuis Voice-Commands.md**

Copier les 7 sections de langues (Français, Anglais, Allemand, Espagnol, Italien, Portugais, Ukrainien) depuis `Voice-Commands.md`, en traduisant les en-têtes de catégorie :
- `### 1. Continuation and reset` → `### 1. Continuation et reset`
- `### 2. Line breaks` → `### 2. Sauts de ligne`
- `### 3. Punctuation` → `### 3. Ponctuation`
- `### 4. Quotes and brackets` → `### 4. Guillemets et parenthèses`
- `### 5. Markdown formatting` → `### 5. Formatage Markdown`
- `### 6. Special characters` → `### 6. Caractères spéciaux`
- `### 7. Voice keyboard shortcuts` → `### 7. Raccourcis clavier vocaux`

Et les noms de langues en sections ## :
- `## French (fr)` → `## Français (fr)`
- `## English (en)` → `## Anglais (en)`
- `## German (de)` → `## Allemand (de)`
- `## Spanish (es)` → `## Espagnol (es)`
- `## Italian (it)` → `## Italien (it)`
- `## Portuguese (pt)` → `## Portugais (pt)`
- `## Ukrainian (uk)` → `## Ukrainien (uk)`

Et les en-têtes de tableaux :
- `| Spoken |` → `| Parlé |`
- `| Result |` → `| Résultat |`
- `| Notes |` → reste `| Notes |`
- `| Variants |` → `| Variantes |`

Le contenu (commandes parlées dans la langue cible et résultat) reste identique. Les traductions de la colonne « Notes » :
- `continues previous sentence` → `continue la phrase précédente`
- `resets continuation context` → `réinitialise le contexte de continuation`
- `Configurable + alias supported` → `Configurable + alias supportés`
- `Anchored at start of dictation only` → `Ancré au début de la dictée uniquement`
- `Suffix configurable to disambiguate from word "point"` → `Suffixe configurable pour désambiguïser du mot "point"`
- `Plural changes vowel` → `Le pluriel change la voyelle`
- `also "la ligne" (Parakeet drops "à")` → `aussi "la ligne" (Parakeet omet le "à")`

La section finale FR « ASR misdetection workarounds (fr) » devient « Workarounds de mauvaises détections ASR (fr) » avec contenu traduit.

La note finale UK devient :
> Note : la conversion des nombres (cardinaux, décimales) n'est **pas** supportée pour l'ukrainien — text_to_num n'a pas de backend ukrainien.

- [ ] **Step 3: Vérifier que les ancres TOC matchent les sections**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
grep "^##" fr-Voice-Commands.md | head -10
# Doit lister exactement les 7 sections ## de langues
```

- [ ] **Step 4: Commit**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
git add fr-Voice-Commands.md
git commit -m "docs(wiki): add fr-Voice-Commands (French translation)"
```

---

## Task 6: Mettre à jour _Sidebar.md

**Files:**
- Modify: `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/_Sidebar.md`

- [ ] **Step 1: Ajouter l'entrée Voice-Commands sous « Post-processing / Post-traitement »**

L'entrée doit suivre le format existant. Trouver le bloc dans le fichier :

```markdown
**Post-processing / Post-traitement**
- Overview · [🇬🇧](Post-Processing-Overview) · [🇫🇷](fr-Post-Processing-Overview)
- Rules-and-Dictionary · [🇬🇧](Rules-and-Dictionary) · [🇫🇷](fr-Rules-and-Dictionary)
- LLM-Correction · [🇬🇧](LLM-Correction) · [🇫🇷](fr-LLM-Correction)
- Numbers-Dates-Continuation · [🇬🇧](Numbers-Dates-Continuation) · [🇫🇷](fr-Numbers-Dates-Continuation)
```

Et le remplacer par :

```markdown
**Post-processing / Post-traitement**
- Overview · [🇬🇧](Post-Processing-Overview) · [🇫🇷](fr-Post-Processing-Overview)
- Rules-and-Dictionary · [🇬🇧](Rules-and-Dictionary) · [🇫🇷](fr-Rules-and-Dictionary)
- Voice-Commands · [🇬🇧](Voice-Commands) · [🇫🇷](fr-Voice-Commands)
- LLM-Correction · [🇬🇧](LLM-Correction) · [🇫🇷](fr-LLM-Correction)
- Numbers-Dates-Continuation · [🇬🇧](Numbers-Dates-Continuation) · [🇫🇷](fr-Numbers-Dates-Continuation)
```

Voice-Commands placé entre Rules-and-Dictionary et LLM-Correction (ordre logique : règles d'abord, commandes spécifiques ensuite, autres pp ensuite).

- [ ] **Step 2: Commit**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
git add _Sidebar.md
git commit -m "docs(wiki): add Voice-Commands entry in sidebar"
```

---

## Task 7: Cross-links depuis Numbers-Dates-Continuation et Rules-and-Dictionary

**Files:**
- Modify: `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/Numbers-Dates-Continuation.md`
- Modify: `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/fr-Numbers-Dates-Continuation.md`
- Modify: `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/Rules-and-Dictionary.md`
- Modify: `/home/rapha/SOURCES/RAPHA_STT/dictee.wiki/fr-Rules-and-Dictionary.md`

- [ ] **Step 1: Cross-link dans Numbers-Dates-Continuation.md (EN)**

Dans la section `### Resetting the continuation context` (ajoutée précédemment cette session), juste après le tableau des 3 mécanismes, ajouter une note :

```markdown
> **See also:** [Voice-Commands](Voice-Commands) — full reference of all voice commands across 7 languages.
```

- [ ] **Step 2: Cross-link dans fr-Numbers-Dates-Continuation.md (FR)**

Dans la section `### Réinitialiser le contexte de continuation`, après le tableau :

```markdown
> **Voir aussi :** [Commandes vocales](fr-Voice-Commands) — référence complète de toutes les commandes vocales pour les 7 langues.
```

- [ ] **Step 3: Cross-link dans Rules-and-Dictionary.md (EN)**

Trouver la section qui parle des voice commands dans le pipeline (probablement section "Voice commands" ou "Step 3" du pipeline). Ajouter un block citation au début ou à la fin :

```markdown
> **Reference:** see [Voice-Commands](Voice-Commands) for the complete user-facing list of voice commands per language.
```

Si la section précise n'existe pas, ajouter en haut du fichier après l'introduction.

- [ ] **Step 4: Cross-link dans fr-Rules-and-Dictionary.md (FR)**

Pareil :

```markdown
> **Référence :** voir [Commandes vocales](fr-Voice-Commands) pour la liste complète des commandes vocales par langue.
```

- [ ] **Step 5: Vérification — tous les liens internes pointent vers des fichiers existants**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
# Vérifier qu'on link bien Voice-Commands et fr-Voice-Commands (pas autre chose)
grep -nE "\[.*Voice.Commands\]|fr-Voice-Commands" Numbers-Dates-Continuation.md fr-Numbers-Dates-Continuation.md Rules-and-Dictionary.md fr-Rules-and-Dictionary.md
# Doit montrer au moins 4 lignes (1 par fichier)
```

- [ ] **Step 6: Commit**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
git add Numbers-Dates-Continuation.md fr-Numbers-Dates-Continuation.md Rules-and-Dictionary.md fr-Rules-and-Dictionary.md
git commit -m "docs(wiki): cross-link Voice-Commands from Numbers-Dates-Continuation and Rules-and-Dictionary"
```

---

## Task 8: Push final

**Files:** none (action git pure)

- [ ] **Step 1: Vérifier la liste des commits locaux**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
git log --oneline origin/master..HEAD
```

Expected : 6 commits (Tasks 2, 3, 4, 5, 6, 7 — Task 1 ne commite pas, Task 8 ne crée pas de commit).

- [ ] **Step 2: Push**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee.wiki/
git push origin master
```

Expected: tous les commits poussés vers GitHub Wiki.

- [ ] **Step 3: Vérifier le rendu sur GitHub**

Ouvrir manuellement : https://github.com/rcspam/dictee/wiki/Voice-Commands et https://github.com/rcspam/dictee/wiki/fr-Voice-Commands

Vérifier visuellement :
- Les sections par langue rendent correctement
- Le sidebar affiche bien la nouvelle entrée
- Les cross-links cliquables depuis Numbers-Dates-Continuation et Rules-and-Dictionary

- [ ] **Step 4: Mémoire — noter que Plan A est livré**

Mettre à jour `~/.claude/projects/-home-rapha-SOURCES-RAPHA-STT-dictee/memory/MEMORY.md` pour ajouter une référence au plan livré, et mettre à jour `project-rc3-reset-context-implemented.md` (ligne « Future : page wiki dédiée aux voice commands ») pour la marquer comme faite.

---

## Spec Coverage

| Section spec | Task |
|---|---|
| §9 Wiki page — Voice-Commands.md | Tasks 2, 3, 4 |
| §9 Wiki page — fr-Voice-Commands.md | Task 5 |
| §9 Wiki page — _Sidebar.md update | Task 6 |
| §9 Wiki page — cross-links | Task 7 |
| §13 Hors scope (search bar, edition…) | (rien à faire — le spec exclut explicitement) |

Les autres sections du spec (architecture, composants script, triggers, persistance, zoom) sont du scope du Plan B (Cheatsheet UI) et seront couvertes là.

## Estimated Time

~1h total : Task 1 (15 min audit), Task 2-4 (20 min EN sections), Task 5 (15 min FR translation), Task 6-7 (5 min sidebar + cross-links), Task 8 (5 min push + mémoire).

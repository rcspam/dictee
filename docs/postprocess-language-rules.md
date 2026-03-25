# Post-processing — Language rules tab

## Overview

The **Language rules** tab contains language-specific post-processing rules that cannot be expressed as simple regex substitutions. These rules handle elisions, contractions, inverted punctuation, and typographic conventions specific to each language.

Rules are only applied when the source language (`DICTEE_LANG_SOURCE`) matches the rule's language.

## Supported languages

### Français [fr]

**Elisions** (`DICTEE_PP_ELISIONS`)

Corrects missing elisions before vowels and mute h, with h aspiré exceptions.

| Input | Output | Rule |
|-------|--------|------|
| le arbre | l'arbre | article elision |
| de eau | d'eau | preposition elision |
| je ai | j'ai | pronoun elision |
| si il vient | s'il vient | special contraction |
| le haricot | le haricot | h aspiré — NO elision |
| le homme | l'homme | h muet — elision |

Elision words: `je, me, te, se, le, la, ne, de, que, ce`

H aspiré exceptions: ~70 words including `hache, haie, haine, hall, hamac, handicap, hangar, haricot, hasard, haut, héros, hibou, hockey, homard, honte, hurler, hutte`...

**Typography** (`DICTEE_PP_TYPOGRAPHY`)

Inserts non-breaking spaces before French high punctuation, as required by French typographic rules.

| Before | After |
|--------|-------|
| `mot:` | `mot :` (NBSP before `:`) |
| `mot;` | `mot ;` (NNBSP before `;`) |
| `mot!` | `mot !` (NNBSP before `!`) |
| `mot?` | `mot ?` (NNBSP before `?`) |
| `"text"` | `« text »` (French quotes with NBSP) |

NBSP = U+00A0, NNBSP = U+202F (narrow non-breaking space)

---

### Italiano [it]

**Elisions & contractions** (`DICTEE_PP_ELISIONS_IT`)

Handles Italian elisions before vowels and prepositional contractions (articulated prepositions).

**Elisions:**

| Input | Output |
|-------|--------|
| lo uomo | l'uomo |
| la amica | l'amica |
| una amica | un'amica |
| di accordo | d'accordo |
| ci è | c'è |
| quello uomo | quell'uomo |
| come è | com'è |
| dove è | dov'è |

**Prepositional contractions** (applied before elisions to avoid conflicts):

| Input | Output | Input | Output |
|-------|--------|-------|--------|
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

Case is preserved: `DI IL LIBRO` → `DEL LIBRO`, `Di Il` → `Del Il`.

---

### Español [es]

**Contractions & inverted punctuation** (`DICTEE_PP_SPANISH`)

**Contractions** (only 2 in Spanish):

| Input | Output | Note |
|-------|--------|------|
| a el parque | al parque | mandatory contraction |
| de el libro | del libro | mandatory contraction |
| a El Salvador | a El Salvador | proper noun — NO contraction |
| de El Greco | de El Greco | proper noun — NO contraction |

Proper nouns are detected by the capital letter following `el`.

**Inverted punctuation:**

| Input | Output |
|-------|--------|
| Cómo estás? | ¿Cómo estás? |
| Qué hora es? | ¿Qué hora es? |

Inverted `¿` is added before question words (`qué, quién, cómo, cuándo, dónde, por qué, cuál, cuánto`). Inverted `¡` is added before exclamatory sentences ending with `!`.

Already-present inverted marks are not duplicated.

---

### Português [pt]

**Contractions** (`DICTEE_PP_PORTUGUESE`)

Portuguese has extensive fused contractions (no apostrophe, words merge).

**Preposition + articles:**

| Input | Output | Input | Output |
|-------|--------|-------|--------|
| de o | do | em o | no |
| de a | da | em a | na |
| de os | dos | em os | nos |
| de as | das | em as | nas |
| por o | pelo | em um | num |
| por a | pela | em uma | numa |
| por os | pelos | | |
| por as | pelas | | |

**Preposition + demonstratives:**

| Input | Output | Input | Output |
|-------|--------|-------|--------|
| de este | deste | em este | neste |
| de esta | desta | em esta | nesta |
| de esse | desse | em esse | nesse |
| de essa | dessa | em essa | nessa |
| de aquele | daquele | em aquele | naquele |
| de aquilo | daquilo | | |

**Preposition + pronouns:**

| Input | Output | Input | Output |
|-------|--------|-------|--------|
| de ele | dele | em ele | nele |
| de ela | dela | em ela | nela |
| de eles | deles | em eles | neles |
| de elas | delas | em elas | nelas |

Case is preserved: `De O livro` → `Do livro`, `DE O` → `DO`.

---

### Deutsch [de]

**Contractions & typography** (`DICTEE_PP_GERMAN`)

**Prepositional contractions:**

| Input | Output | Input | Output |
|-------|--------|-------|--------|
| an dem | am | an das | ans |
| auf das | aufs | bei dem | beim |
| in dem | im | in das | ins |
| von dem | vom | zu dem | zum |
| zu der | zur | | |

**Typography:**

English quotes `"text"` are converted to German quotes `„text"` (U+201E opening below, U+201C closing above).

---

### Nederlands [nl]

**Contractions** (`DICTEE_PP_DUTCH`)

**Pronoun/article contractions:**

| Input | Output | Note |
|-------|--------|------|
| het is mooi | 't is mooi | article reduction |
| een boek | 'n boek | only before lowercase (not proper nouns) |
| een Amsterdam | een Amsterdam | proper noun — NO contraction |

**Time expressions:**

| Input | Output |
|-------|--------|
| in de morgens | 's morgens |
| in de avonds | 's avonds |
| in de nachts | 's nachts |
| in de middags | 's middags |

---

### Română [ro]

**Contractions & typography** (`DICTEE_PP_ROMANIAN`)

**Negation contractions:**

| Input | Output |
|-------|--------|
| nu am | n-am |
| nu ai | n-ai |
| nu a | n-a |
| nu au | n-au |
| nu o | n-o |

**Prepositional contractions:**

| Input | Output |
|-------|--------|
| într o | într-o |
| într un | într-un |
| dintr o | dintr-o |
| dintr un | dintr-un |
| printr o | printr-o |
| printr un | printr-un |

**Typography:**

English quotes `"text"` are converted to Romanian quotes `„text"` (same style as German).

---

## Pipeline position

Language rules are applied at **step 6** of the post-processing pipeline:

1. Regex rules (`rules.conf`)
2. Bad language rejection
3. Continuation
4. **Elisions (FR)** ← here
5. **Italian / Spanish / Portuguese / German / Dutch / Romanian** ← here
6. Numbers (text2num)
7. Typography (FR)
8. Dictionary
9. Capitalization

Language rules run before number conversion and dictionary to avoid interfering with those steps.

## Technical notes

- Each language's rules are controlled by an independent environment variable
- Rules default to `true` — they are active unless explicitly disabled
- Case is preserved in all contractions (lowercase, Title Case, UPPERCASE)
- Word boundaries (`\b`) prevent false positives on substrings
- Contractions are applied before elisions (Italian) to avoid conflicts (e.g., `di il` → `del` not `d'il`)
- Spanish proper noun detection uses capital letter after `el` to avoid contracting `a El Salvador`
- Dutch `een` → `'n` only before lowercase words to avoid contracting before proper nouns
- All functions handle empty strings safely

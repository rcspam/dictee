# Cheatsheet flottant des commandes vocales — Design

**Date** : 2026-04-25
**Statut** : Brainstormé, en attente de plan d'implémentation
**Auteur** : Session interactive avec rcspam

## 1. Objectif

Aider l'utilisateur à découvrir et se rappeler les commandes vocales pendant qu'il dicte, via une **carte flottante discrète, toujours au-dessus, sans décoration de fenêtre**, accessible par 4 chemins (bouton plasmoid, menu tray, raccourci global, auto-show 1ère install).

En parallèle, créer une **page wiki dédiée** documentant toutes les commandes vocales pour les 7 langues supportées.

### Contraintes utilisateur explicites

- Discret, pas imposant
- Aide *pendant* la dictée (donc utilisable depuis n'importe quelle fenêtre focalisée)
- Sans décoration de fenêtre, déplaçable facilement, flottante, toujours au-dessus
- Filtrage automatique sur la langue source courante (pas de UI sélecteur de langue)
- Mise à jour temps réel quand l'utilisateur change `SUFFIX_*` ou le mot de continuation dans dictee-setup
- Accessibilité : zoom intégré pour malvoyants

## 2. Architecture globale

**Nouveau script standalone** `dictee-cheatsheet` (Python + PyQt6, ~250 lignes), pas un widget enfant de `dictee-tray.py`. Processus autonome avec son propre cycle de vie.

**Pattern singleton** : QLocalServer/QLocalSocket sur `dictee-cheatsheet-${UID}`. Un seul script se lance vraiment ; les invocations suivantes envoient un message au server existant et exitent.

**CLI** :
- `dictee-cheatsheet` : lance ou raise (focus) la fenêtre
- `dictee-cheatsheet --toggle` : lance si absent, ferme si présent
- `dictee-cheatsheet --close` : ferme uniquement
- `dictee-cheatsheet --first-run` : montre la note d'onboarding une fois

## 3. Composants — fichiers à créer / modifier

| Fichier | Type | Lignes (estim.) | Rôle |
|---|---|---|---|
| `dictee-cheatsheet` | **création** | ~250 | Script principal Python, fenêtre Qt, watchers, IPC |
| `dictee-tray.py` | modif | ~10 | Entrée menu : « Toggle voice commands cheatsheet » |
| `plasmoid/.../FullRepresentation.qml` | modif | ~10 | Bouton ToolButton (icône `view-list-text`) à côté de la flèche reset |
| `plasmoid/.../main.qml` | modif | ~3 | Switch case `"cheatsheet"` → exec `dictee-cheatsheet --toggle` |
| `dictee-setup.py` | modif | ~30 | Onglet Raccourcis : nouveau champ « Aide commandes vocales » + capture clavier + register kglobalaccel |
| `build-deb.sh` | modif | ~3 | `cp dictee-cheatsheet pkg/dictee/usr/bin/` (cpu + cuda) |
| `build-rpm.sh` | modif | ~3 | Section `%files` + copie pendant prep (cpu + cuda) |
| `PKGBUILD` | modif | ~1 | `install -Dm755 dictee-cheatsheet ...` dans `package()` |

### Structure interne du script

```
dictee-cheatsheet
├── main()                              # parse args, singleton check, IPC dispatch
├── class CheatsheetCard(QWidget)       # fenêtre flottante
│   ├── __init__()                      # WindowFlags, layout, watchers, shortcuts
│   ├── _reload()                       # relit configs, reconstruit UI
│   ├── _render_category(cat_id, items)
│   ├── _apply_zoom(zoom_pt)
│   ├── mousePressEvent / mouseMoveEvent  # drag
│   ├── keyPressEvent                     # Ctrl++/-/0/W shortcuts
│   ├── closeEvent()                      # save geometry + zoom + cat states
│   └── _on_config_changed(path)          # via QFileSystemWatcher
├── COMMAND_TABLE                        # dict langue → catégorie → [(template_cmd, result)]
└── class IPCServer(QLocalServer)        # singleton + toggle commands
```

### `COMMAND_TABLE` — table curée

Hardcodée en Python dans le script. Format :
```python
COMMAND_TABLE = {
    'fr': {
        'continuation_reset': [
            ('{cont}', 'continue'),         # {cont} injecté = mot continuation
            ('nouvelle phrase', 'reset'),
        ],
        'sauts_de_ligne': [
            ('à la ligne', '↵'),
            ('retour à la ligne', '↵'),
            ('nouveau paragraphe', '↵↵'),
            ('point à la ligne', '.↵'),
            ...
        ],
        'ponctuation': [
            ('virgule', ','),
            ('point {suffix}', '.'),         # {suffix} = SUFFIX_FR config
            ('deux points', ':'),
            ...
        ],
        ...
    },
    'en': {...}, 'de': {...}, ...
}
```

Les templates `{cont}` et `{suffix}` sont remplacés au runtime par les valeurs courantes.

## 4. Data flow et configuration dynamique

### Sources lues au démarrage et surveillées

| Source | Lue pour | Watcher |
|---|---|---|
| `~/.config/dictee.conf` | `DICTEE_LANG_SOURCE`, `SUFFIX_FR`, `SUFFIX_EN`, etc. | QFileSystemWatcher |
| `~/.config/dictee/continuation.conf` | `CONTINUATION_WORDS_<LANG>` (1 mot principal + alias) | QFileSystemWatcher |
| `COMMAND_TABLE` (interne) | structure par lang × cat | — |

### `_reload()`

```
1. Lire dictee.conf → LANG, SUFFIX[LANG]
2. Lire continuation.conf → CONT_WORDS[LANG]
3. Pour chaque catégorie active :
   - Lookup COMMAND_TABLE[LANG][cat]
   - Substituer {suffix} par SUFFIX[LANG]
   - Substituer {cont} par CONT_WORDS[LANG][0] (premier alias = principal)
   - Si plusieurs alias : ajouter "(+ N autres)" en hover
4. Reconstruire le QGridLayout
```

### File watcher — robustesse

```python
def _on_config_changed(self, path):
    self._reload()
    # Re-add path : QFileSystemWatcher perd le watch sur rename atomique
    # (vim, dictee-setup save, etc.)
    if path not in self._watcher.files():
        self._watcher.addPath(path)
```

## 5. Triggers — flow d'invocation

### P — Bouton plasmoid

`FullRepresentation.qml`, à côté de la flèche reset rouge ligne ~850 :
```qml
PlasmaComponents.ToolButton {
    icon.name: "view-list-text"
    display: PlasmaComponents.AbstractButton.IconOnly
    onClicked: fullRep.actionRequested("cheatsheet")
    PlasmaComponents.ToolTip { text: i18n("Toggle voice commands cheatsheet") }
}
```

`main.qml`, switch lignes ~640 :
```qml
case "cheatsheet":
    executable.run("dictee-cheatsheet --toggle")
    break
```

### T — Menu tray

`dictee-tray.py` — ajout dans `_build_menu()` (versions PyQt6 ET AppIndicator) :
```python
# Label i18n via gettext domain "dictee" — traduit en FR par "Aide commandes vocales"
cheatsheet_action = QAction(_("Toggle voice commands cheatsheet"), self)
cheatsheet_action.triggered.connect(
    lambda: subprocess.Popen(["dictee-cheatsheet", "--toggle"])
)
menu.addAction(cheatsheet_action)
```

**i18n** : ajouter une entrée dans `po/dictee.pot` + traductions `po/{fr,de,es,it,pt,uk}.po`.

### K — Raccourci global KDE

- **Default** : `Ctrl+Alt+H`
- **Configurable** dans dictee-setup → onglet Raccourcis (existant)
- **Service** : action `dictee-cheatsheet-toggle`
- **Commande** : `/usr/bin/dictee-cheatsheet --toggle`
- **Enregistrement** : kglobalaccel via D-Bus (même pattern que les raccourcis F8/F9 existants)

### A — Auto-show 1ère install

`dictee-tray.py` dans `main()`, après le singleton lock :
```python
firstrun_marker = Path.home() / ".local/state/dictee/cheatsheet-firstrun.done"
if not firstrun_marker.exists():
    subprocess.Popen(["dictee-cheatsheet", "--first-run"])
    # Le marker sera créé par dictee-cheatsheet quand l'utilisateur ferme la carte
```

### Synchro d'état entre triggers

- Le script écrit son état dans `/dev/shm/.dictee_cheatsheet-${UID}` à chaque show/hide :
  - `1` quand visible, `0` quand cachée
- Le tray surveille via `QFileSystemWatcher` → met à jour le label menu
- Le plasmoid lit via `Plasma5Support DataSource` (executable polling) → optionnellement change l'apparence du bouton (différable, non-bloquant)

## 6. Persistance et configuration

### Layout des fichiers

| Donnée | Emplacement | Format | Qui écrit |
|---|---|---|---|
| Position fenêtre (x, y) | `~/.config/dictee/cheatsheet.conf` | INI via `QSettings` | dictee-cheatsheet (au close) |
| Taille fenêtre (w, h) | idem | idem | idem |
| Niveau de zoom (point size) | idem | idem | idem |
| Catégories pliées/dépliées | idem | idem | idem |
| First-run done marker | `~/.local/state/dictee/cheatsheet-firstrun.done` | fichier marker (existence) | dictee-cheatsheet (au 1er close après --first-run) |
| Raccourci clavier choisi | `~/.config/kglobalshortcutsrc` | INI KDE | dictee-setup via D-Bus kglobalaccel |
| Mention raccourci pour intro­spection | `~/.config/dictee.conf` : `DICTEE_SHORTCUT_CHEATSHEET=Ctrl+Alt+H` | INI dictee | **dictee-setup** uniquement |

### Pourquoi pas tout dans dictee.conf

Règle mémoire `feedback-no-sed.md` : dictee.conf est édité uniquement par dictee-setup. Donc l'état runtime (position, taille, zoom) va dans un fichier séparé géré par QSettings. Le first-run done est un marker filesystem.

### Valeurs initiales

- **Position** : si pas de valeur sauvée → coin haut-droite de l'écran primary, marge 16px
- **Taille** : 260×420 px
- **Zoom** : 12pt
- **Catégories** : `continuation_reset`, `sauts_de_ligne`, `ponctuation`, `brackets` dépliées ; `markdown`, `caracteres_speciaux`, `hotkeys` repliées
- **First-run** : non fait (déclenche auto-show via dictee-tray)

## 7. Spécification visuelle

### Apparence générale

- **Cadre** : `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`
- **Fond** : `rgba(28, 30, 35, 0.92)` (sombre semi-transparent)
- **Border** : `1px solid rgba(255, 255, 255, 0.10)`, radius 8px
- **Box-shadow** : `0 8px 24px rgba(0,0,0,0.35)`
- **Police par défaut** : Inter ou system-ui, 12pt

### Header (~40px haut)

```
┌─────────────────────────────────────────────────┐
│ 🎤 Commandes vocales (FR)        −  +  ×        │
└─────────────────────────────────────────────────┘
```

- Fond légèrement plus clair que le corps (`rgba(255,255,255,0.04)`)
- Drag handle = toute la zone non-bouton
- Boutons : zoom-out (−), zoom-in (+), close (×)
- Police header : 11pt × ratio_zoom

### Corps — catégories

```
▾ Continuation et reset
   minuscule (+miniscule)    → continue
   nouvelle phrase            → reset

▾ Sauts de ligne
   à la ligne                 → ↵
   ...

▸ Markdown                    (replié, click pour déplier)
```

- Titre catégorie : couleur accent bleue clair (`#8ec5ff`), bold, font-size header
- Click sur titre → toggle expand/collapse
- Lignes commande : QGridLayout 2 colonnes (commande / résultat), `gap: 4px 8px`, `padding-left: 8px`

### Footer (~24px bas)

```
Ctrl+Alt+H pour basculer · doc complète : wiki
```

- Fond légèrement plus sombre, opacité 0.5
- Lien « wiki » → ouvre la page Voice-Commands via `xdg-open`

### Resize grip

`QSizeGrip` Qt natif en bas-droite du layout principal. ~12×12 px, discret. Cursor change au hover, drag redimensionne.

### Drag

```python
def mousePressEvent(self, event):
    # Drag uniquement si :
    # - bouton gauche
    # - clic en dehors d'un élément interactif (titre catégorie, bouton)
    if event.button() == Qt.MouseButton.LeftButton and not self._on_interactive(event.pos()):
        self._drag_start = event.globalPosition().toPoint()
        self._win_start = self.pos()
        event.accept()

def mouseMoveEvent(self, event):
    if self._drag_start:
        delta = event.globalPosition().toPoint() - self._drag_start
        self.move(self._win_start + delta)
```

## 8. Zoom et accessibilité

### Paramètres

- **Police par défaut** : 12pt
- **Min** : 9pt — **Max** : 22pt
- **Pas** : 0.5pt (Qt accepte float via `setPointSizeF`)
- **Comportement fenêtre** : auto-resize proportionnel à chaque zoom

### Implémentation

```python
def _apply_zoom(self):
    self.setStyleSheet(self._build_stylesheet(self._zoom_pt))
    self.layout().invalidate()
    new_size = self.layout().sizeHint()
    screen = self.screen().availableGeometry()
    capped_w = min(new_size.width(), screen.width() - 32)
    capped_h = min(new_size.height(), screen.height() - 32)
    self.resize(capped_w, capped_h)
    # Si capped, le QScrollArea interne prend le relai
```

### Raccourcis internes (carte focalisée)

| Raccourci | Action |
|---|---|
| `Ctrl + +` (ou `Ctrl + =`) | zoom in |
| `Ctrl + −` | zoom out |
| `Ctrl + 0` | reset à 12pt |
| `Ctrl + W` ou `Échap` | ferme la carte |

Distinction :
- **`Ctrl + Alt + H`** = global (kglobalaccel) → toggle depuis n'importe quelle app
- **`Ctrl + +/−/0/W`** = local (QShortcut) → carte focalisée

`setFocusPolicy(Qt.StrongFocus)` pour permettre au widget d'avoir le focus clavier.

## 9. Page wiki dédiée

**Indépendante de la carte** : peut être livrée d'abord (zéro risque), la carte la référence en bas via lien.

### Fichiers

- `Voice-Commands.md` (EN)
- `fr-Voice-Commands.md` (FR)

### Contenu

- Toutes les langues sur la même page, sections par ancre `#fr`, `#en`, `#de`, `#es`, `#it`, `#pt`, `#uk`
- Pour chaque langue, sections matching la carte (continuation/reset, sauts ligne, ponctuation, guillemets, markdown, caractères spéciaux, raccourcis vocaux)
- Tableaux : Commande dite | Résultat | Variantes ASR | Notes
- Note sur SUFFIX configurable + continuation keyword configurable
- Section « How dictée processes voice commands » (lien vers Rules-and-Dictionary.md)

### Liens

- Ajout dans `_Sidebar.md` au top niveau
- Cross-link depuis `Numbers-Dates-Continuation.md` et `Rules-and-Dictionary.md`

## 10. Tests

### Triggers (4 chemins)

- [ ] P : ouvrir le plasmoid → cliquer bouton aide → carte apparaît / reclic ferme
- [ ] T : clic-droit tray → menu « Afficher l'aide » → carte apparaît / re-clic ferme
- [ ] K : presser Ctrl+Alt+H global → carte apparaît / re-press ferme
- [ ] A : supprimer le marker firstrun.done + relancer dictee-tray → carte apparaît avec bandeau onboarding

### Comportement carte

- [ ] Drag depuis n'importe où dans le fond (pas un titre de catégorie) déplace
- [ ] Drag depuis le coin bas-droite (size grip) redimensionne
- [ ] Plier/déplier une catégorie → animation propre, état persiste à fermeture/réouverture
- [ ] Ferme via croix × → position/taille/zoom/catégories sauvées
- [ ] Réouverture → position/taille/zoom/catégories restaurées identiquement

### Sync dynamique

- [ ] Carte ouverte → dictee-setup → changer SUFFIX_FR → Apply → la carte montre le nouveau suffix sans ré-ouverture
- [ ] Carte ouverte → dictee-setup → changer continuation FR → Apply → la carte affiche le nouveau mot
- [ ] Carte ouverte → changer DICTEE_LANG_SOURCE → Apply → la carte switch langue affichée

### Singleton

- [ ] Lancer `dictee-cheatsheet --toggle` 2× rapidement → une seule fenêtre, le 2e toggle ferme
- [ ] Lancer 3 instances en parallèle → toujours 1 fenêtre, IPC fonctionne

### Multi-monitor

- [ ] Position sauvée sur monitor secondaire, déconnecter monitor, ouvrir → carte recentrée sur primary

### Zoom

- [ ] Ctrl++ x N → fenêtre s'agrandit progressivement par pas de 0.5pt
- [ ] Ctrl++ jusqu'à dépasser l'écran → fenêtre cappée, scrollbar apparaît
- [ ] Ctrl+− jusqu'au minimum → texte 9pt, fenêtre se rétrécit
- [ ] Ctrl+0 → retour à 12pt
- [ ] Zoom max → contenu lisible (test avec un utilisateur malvoyant si possible)

## 11. Risques et mitigations

| Risque | Mitigation |
|---|---|
| Wayland refuse `WindowStaysOnTopHint` sous certains compositors | Test direct sur KWin Wayland (TUXEDO OS du dev). Documenter limitation si elle survient. |
| `QFileSystemWatcher` perd le watch au rewrite atomique | Ré-add le path dans `fileChanged`. |
| KGlobalAccel non disponible (GNOME, Sway, autre WM) | Détection desktop env. Sur GNOME : fallback xdotool / D-Bus différent. Sinon : raccourci configurable manuellement. |
| Crash du processus → state file `/dev/shm/.dictee_cheatsheet-${UID}` reste à `1` | Trap SIGTERM/SIGINT pour nettoyer. Dictee-tray contrôle si QLocalServer répond avant de croire le state file. |
| Très long fichier `continuation.conf` avec 10 alias | Carte tronque : « minuscule (+3 alias) » avec hover pour voir tous |
| Position fenêtre hors écran après déconnexion monitor | `screen().availableGeometry().contains(pos)` au open, recenter sur primary si false |
| Wayland : focus clavier sur frameless `Qt.Tool` | Tester `setFocusPolicy(Qt.StrongFocus)` + clic dans la carte. Si insuffisant, basculer sur `Qt.Window` avec frameless. |

## 12. Phases d'implémentation

**Phase 1 — Wiki page** (~1h, indépendante)
Créer `Voice-Commands.md` + `fr-Voice-Commands.md`, audit de `rules.conf.default`, mise à jour Sidebar + cross-links.

**Phase 2 — Cheatsheet UI** (~3-4h)
Script `dictee-cheatsheet`, intégration plasmoid + tray + raccourci kglobalaccel, persistance, zoom, IPC singleton, file watching.

**Phase 3 — Packaging** (~30min)
Modif `build-deb.sh`, `build-rpm.sh`, `PKGBUILD`. Vérification `grep -n "dictee-cheatsheet" build-deb.sh build-rpm.sh PKGBUILD` doit avoir matches partout.

## 13. Hors scope

- **Recherche dans la carte** : pas de search bar (ajout visuel non aligné avec « discret »)
- **Edition des commandes via la carte** : la carte est read-only ; modification toujours via dictee-setup
- **Raccourci voice command** « afficher l'aide » : friction inutile, méta-circulaire
- **Synchro multi-écran** au-delà du clamp basique : pas de mémorisation par moniteur
- **Onglets multi-langues** dans la carte : doc complète multilangue → page wiki uniquement
- **Animation d'apparition / fade** : ouverture instantanée, KISS
- **Dark/light theme switch** dans la carte : carte toujours sombre (cohérent avec « discret », fonctionne sur tout fond)

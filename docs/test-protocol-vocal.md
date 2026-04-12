# Protocole de test vocal — Pipeline dictee

Tests manuels avec microphone. Prerequis : daemon ASR actif, dictee-setup.py configure.

## A. Pipeline Normal (sans traduction)

- [ ] A1. FR : dicter "bonjour virgule comment allez-vous" → `Bonjour, comment allez-vous`
- [ ] A2. EN : dicter "hello comma how are you" → `Hello, how are you`
- [ ] A3. DE : dicter "Hallo Komma wie geht es Ihnen" → `Hallo, wie geht es Ihnen`
- [ ] A4. FR : dicter un mot de continuation final ("le", "de", "et") → indicateur `>>` affiche
- [ ] A5. FR : dicter un 2e push apres continuation → indicateur supprime, texte enchaine
- [ ] A6. FR : dicter "point a la ligne bonjour" → `.\nBonjour` (retour a la ligne)
- [ ] A7. FR : dicter un seul mot → short text fix applique (minuscule, pas de point)
- [ ] A8. FR : dicter "parles-tu" en fin de phrase → `>>` (tiret : check "tu")
- [ ] A9. FR : dicter "vingt-trois" → `23` (regles numbers)
- [ ] A10. FR : dicter avec commande suffixee "point suivi" → `.` (pas "point" comme texte)

## B. Pipeline Normal + Traduction

- [ ] B1. FR→EN backend trans : dicter "bonjour virgule comment allez-vous" → `Hello, how are you`
- [ ] B2. FR→EN backend libretranslate (si installe) : meme phrase → resultat similaire
- [ ] B3. FR→EN backend ollama (si actif) : meme phrase → resultat similaire
- [ ] B4. Verifier que PP normal a nettoye AVANT traduction : "virgule" → `,` avant traduction, pas "virgule" traduit
- [ ] B5. FR→EN : dicter avec continuation finale ("le") → `>>` sur le mot traduit ("the>>")
- [ ] B6. FR→ZH (paire non supportee) → erreur gracieuse, texte source tape + notification
- [ ] B7. FR→EN : dicter "point a la ligne bonjour" → traduction avec retour a la ligne preserve
- [ ] B8. Backend traduction eteint → texte source tape + notification d'erreur

## C. Pipeline Chaine Complete (PP Normal + Traduction + PP Traduction)

- [ ] C1. FR→EN avec PP trad actif : texte FR → PP → trad EN → PP trad EN → sortie
- [ ] C2. Verifier que les rules EN s'appliquent sur le texte traduit
- [ ] C3. Desactiver PP trad → mode bascule vers normal+translate, sortie = traduction brute
- [ ] C4. Comparer C1 et C3 → documenter les differences (le PP trad ameliore-t-il ?)
- [ ] C5. FR→DE full_chain : verifier que les regles DE (guillemets, contractions) s'appliquent
- [ ] C6. Continuation indicator sur le mot traduit final (langue cible)

## D. Exception Canary

- [ ] D1. Backend Canary, FR→EN : Canary traduit depuis l'audio directement
- [ ] D2. Canary + full_chain : PP trad EN s'applique sur la sortie Canary
- [ ] D3. Comparer Canary vs trans sur la meme phrase : documenter differences qualitatives
- [ ] D4. Canary + langue non supportee → fallback ou erreur gracieuse

## E. Robustesse

- [ ] E1. Daemon ASR arrete → dicter → erreur gracieuse, notification
- [ ] E2. Backend traduction non disponible → dicter en mode translate → texte source tape + notification
- [ ] E3. Ollama modele absent → dicter en mode translate → erreur gracieuse
- [ ] E4. Dicter du silence (en dessous du seuil RMS) → "Silence detecte", pas de transcription
- [ ] E5. Dicter tres longtemps (30s+) → timeout gracieux si applicable
- [ ] E6. Couper le reseau pendant une traduction → timeout + texte source tape

## F. Interface Test Panel (dictee-setup.py)

- [ ] F1. Toggle Traduction ON/OFF dans le test panel → output se met a jour
- [ ] F2. Toggle Enable PP trad dans la page PP → output se met a jour
- [ ] F3. Desactiver une etape (ex: Dict) → output change en temps reel
- [ ] F4. Mode Isoler → seule l'etape de la page active fonctionne
- [ ] F5. Changer la langue source → re-run automatique
- [ ] F6. Changer le backend traduction → re-run automatique
- [ ] F7. Enregistrer via le bouton micro → texte transcrit dans l'input
- [ ] F8. Zone details : steps PP normaux + traduction + steps PP trad (full_chain)
- [ ] F9. Continuation indicator sur le mot final (source ou cible selon le mode)
- [ ] F10. Resize input/output via grip → output suit

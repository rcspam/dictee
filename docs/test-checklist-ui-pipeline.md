# Checklist de test manuelle — UI Pipeline Post-traitement

Couvre la fenetre `dictee-setup.py` (PyQt6), mode sidebar.
Cocher chaque item apres verification.

## A. Rendu SVG diagramme pipeline

- [ ] 1. Diagramme bleu (Normal) visible avec les 7 etapes de base + LLM optionnel
- [ ] 2. Diagramme orange (Traduction) visible en dessous, LLM toujours barre
- [ ] 3. Scroll horizontal si fenetre etroite
- [ ] 4. Theme sombre : couleurs foreground/background correctes
- [ ] 5. Theme clair : couleurs foreground/background correctes
- [ ] 6. Icones endpoints : micro (debut bleu), ASR (milieu bleu), translate (milieu orange), crayon (fin)

## B. Toggle des etapes par clic

- [ ] 7. Clic etape bleue "Rules" : passe en tirets + barre → desactive
- [ ] 8. Re-clic "Rules" : retour actif
- [ ] 9. Clic etape orange "Dict" : seul _trpp_state change, bleu inchange
- [ ] 10. Clic LLM bleu : toggle, LLM orange reste desactive
- [ ] 11. Chaque etape (×7) toggle independamment dans chaque diagramme
- [ ] 12. Clic icone micro → navigue vers section Microphone ; clic ASR → section ASR ; clic translate → section Traduction

## C. Master switches

- [ ] 13. Decocher "Enable PP" (bleu) : tout le diagramme bleu grise
- [ ] 14. Recocher : retour aux etats individuels
- [ ] 15. Decocher "Enable PP for translation" (orange) : diagramme orange grise
- [ ] 16. Recocher : retour aux etats individuels
- [ ] 17. Les deux masters off : les deux diagrammes grises, sidebar PP sous-items grises
- [ ] 18. Un seul master on : sous-items actifs dans ce pipeline non grises (logique OR)

## D. Grisage sidebar

- [ ] 19. Sous-items PP (Rules, Continuation, Lang rules, Dict, LLM) refletent l'etat effectif = (normal_master AND normal_state) OR (translate_master AND trpp_state)
- [ ] 20. Items grises restent cliquables (navigation fonctionne)
- [ ] 21. Contenu des sous-pages desactive quand l'etape est effectivement off
- [ ] 22. Toggle on/off d'une etape : syntax highlighter rules se rafraichit correctement

## E. Notice Canary traduction

- [ ] 23. Backend Parakeet : notice verte invisible
- [ ] 24. Passer a Canary : notice verte apparait "La traduction est integree au moteur Canary..."
- [ ] 25. Revenir a Parakeet : notice disparait
- [ ] 26. Canary selectionne : combo backend traduction (cmb_trans_backend) cache
- [ ] 27. Autre backend : combo reapparait
- [ ] 28. Locale FR : texte de la notice en francais

## F. Persistance Apply → dictee.conf

- [ ] 29. Toggle etapes bleues + Apply → DICTEE_PP_RULES, DICTEE_PP_CONTINUATION, etc. corrects dans ~/.config/dictee/dictee.conf
- [ ] 30. Toggle etapes oranges + Apply → DICTEE_TRPP_RULES, DICTEE_TRPP_CONTINUATION, etc. corrects
- [ ] 31. Toggle masters + Apply → DICTEE_POSTPROCESS et DICTEE_PP_TRANSLATE corrects
- [ ] 32. Changer position LLM + Apply → DICTEE_LLM_POSITION correct
- [ ] 33. Changer short text max + Apply → DICTEE_PP_SHORT_TEXT_MAX et DICTEE_TRPP_SHORT_TEXT_MAX corrects
- [ ] 34. Fermer et rouvrir dictee-setup.py → tous les etats restaures depuis conf
- [ ] 35. Apply n'ajoute pas de cles non modifiees

## G. i18n

- [ ] 36. Tooltips des etapes SVG traduits dans la locale active
- [ ] 37. Hint "Cliquez sur les boutons..." traduit
- [ ] 38. Labels master checkboxes traduits
- [ ] 39. Notice Canary traduite dans la locale active

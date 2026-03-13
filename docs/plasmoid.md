# Widget KDE Plasma 6

[Retour au README principal](../README.md)

---

Widget natif KDE Plasma 6 avec visualisation audio en temps réel, état du daemon, et contrôles rapides.

## Installation

```bash
# Inclus dans le .deb, ou manuellement :
kpackagetool6 -t Plasma/Applet -i /usr/share/dictee/dictee.plasmoid

# Mettre à jour
kpackagetool6 -t Plasma/Applet -u /usr/share/dictee/dictee.plasmoid
```

Clic droit sur le panneau → « Ajouter des composants graphiques… » → chercher « Dictée ».

## Styles d'animation

Cinq styles disponibles, tous avec enveloppe Hanning, sensibilité par style, et couleurs arc-en-ciel optionnelles :

| Barres | Onde | Pulsation | Points | Forme d'onde |
|:------:|:----:|:---------:|:------:|:------------:|
| ![Barres](../plasmoid/assets/anim-bars.svg?v=2) | ![Onde](../plasmoid/assets/anim-wave.svg) | ![Pulsation](../plasmoid/assets/anim-pulse.svg) | ![Points](../plasmoid/assets/anim-dots.svg) | ![Forme d'onde](../plasmoid/assets/anim-waveform.svg) |

Mode arc-en-ciel : ![Rainbow](../plasmoid/assets/anim-rainbow.svg?v=2)

## Réglages

- **Volume micro** — réglage du niveau d'entrée directement depuis la config du widget
- **Seuil de silence** — met à zéro l'audio sous un seuil pour un silence net
- **Auto-calibration** — capture le bruit ambiant au démarrage pour une normalisation optimale
- **Sensibilité** — courbe de puissance par style d'animation (`pow(raw, 1/sens)`)
- **Forme d'enveloppe** — puissance Hanning ajustable (plate → pointue)
- **Centre d'enveloppe** — déplace le pic sur la plage de fréquences (80–4000 Hz)
- **Contrôles par style** — nombre de barres, espacement, rayon, vitesse, etc.

## Dépendances

- `python3-numpy` — calcul FFT pour la visualisation
- `pulseaudio-utils` — `parec` pour la capture audio en temps réel

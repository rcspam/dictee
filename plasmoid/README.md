# Dictee Plasmoid — KDE Plasma 6 Widget

A real-time audio visualizer widget for [Dictee](../README.md), the voice dictation system.

## Features

- Real-time microphone visualization during recording
- 5 animation styles with per-style sensitivity
- Rainbow color gradient option
- Noise gate for clean silence
- Configurable via KDE System Settings
- French translation included

## Animation Styles

| Style | Preview | Description |
|-------|---------|-------------|
| **Bars** | ![Bars](assets/anim-bars.svg) | Vertical bars with Hanning envelope |
| **Wave** | ![Wave](assets/anim-wave.svg) | Sinusoidal wave with fill option |
| **Pulse** | ![Pulse](assets/anim-pulse.svg) | Concentric pulsating rings |
| **Dots** | ![Dots](assets/anim-dots.svg) | Bouncing dots |
| **Waveform** | ![Waveform](assets/anim-waveform.svg) | Symmetric centered bars |

### Rainbow Mode

All styles support rainbow colors with configurable hue range:

![Rainbow](assets/anim-rainbow.svg)

## Installation

```bash
kpackagetool6 -t Plasma/Applet -i package/
```

## Configuration

Right-click the widget → Configure:

- **Polling interval** — daemon status check frequency
- **Noise gate** — threshold below which audio is zeroed
- **Calibrate** — record silence to calibrate background noise
- **Animation style** — choose from 5 styles
- **Rainbow colors** — enable with start/end hue
- **Per-style settings** — sensitivity, bar count, spacing, etc.

## Dependencies

- KDE Plasma 6
- `dictee` and `transcribe-daemon`
- Python 3 + NumPy (for audio analysis)
- PulseAudio/PipeWire (microphone access)

## Structure

```
package/
├── metadata.json
└── contents/
    ├── config/
    │   ├── config.qml
    │   └── main.xml
    ├── locale/fr/LC_MESSAGES/
    │   └── plasma_applet_com.github.rcspam.dictee.mo
    └── ui/
        ├── main.qml
        ├── CompactRepresentation.qml
        ├── FullRepresentation.qml
        ├── configGeneral.qml
        └── animations/
            ├── BarsAnimation.qml
            ├── WaveAnimation.qml
            ├── PulseAnimation.qml
            ├── DotsAnimation.qml
            └── WaveformAnimation.qml
```

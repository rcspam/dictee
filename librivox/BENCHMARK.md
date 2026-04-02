# Benchmark WER — Protocole et résultats

## Source audio

**Madame Bovary**, Chapitre 1, Gustave Flaubert — lu par un bénévole LibriVox.

- Fichier source : `madamebovary_01_flaubert_64kb.mp3` (22min40, 64kbps mono)
- Téléchargé depuis : https://librivox.org/madame-bovary-french-by-gustave-flaubert/
- Texte de référence : `bovary_ch01_reference.txt` (extrait de l'epub Wikisource)
- Epub source : https://fr.wikisource.org/wiki/Madame_Bovary/Texte_entier

## Découpage

65 segments WAV (16kHz mono s16), 8-20 secondes chacun, ~15 minutes total.
Coupés aux silences naturels (seuil -35dB, durée min 0.5s, coupe au milieu du silence).

```bash
# Convertir MP3 → WAV 16kHz mono
ffmpeg -y -i madamebovary_01_flaubert_64kb.mp3 -ar 16000 -ac 1 -sample_fmt s16 full.wav

# Détecter les silences
ffmpeg -i full.wav -af silencedetect=noise=-35dB:d=0.5 -f null - 2>&1 | grep silence_end

# Découper (script Python, segments de ~12s cible, 8-20s range)
# Voir le script de découpe dans le code source
```

Fichiers produits : `bovary_ch01_01.wav` à `bovary_ch01_65.wav`

## Protocole de benchmark

Pour chaque backend :

1. **Switch** : `dictee-switch-backend asr <backend>`
2. **Attendre** : 10 secondes (chargement modèle en VRAM)
3. **Warmup** : 3 transcriptions à blanc (premiers segments) — élimine la latence d'init CUDA
4. **Benchmark** : transcrire les 65 segments, mesurer le temps total
5. **Sauvegarder** : texte concaténé dans `bovary_ch01_<backend>.txt`

### Calcul WER

- Normalisation : minuscules, suppression ponctuation, apostrophes unifiées
- Référence tronquée aux ~2249 premiers mots (couverture audio effective)
- WER = (Substitutions + Insertions + Deletions) / Mots référence × 100
- Algorithme : distance d'édition de Levenshtein au niveau mot

```bash
# Lancer le benchmark complet (tous backends)
python3 benchmark_wer.py
```

## Résultats — 2026-04-02

Machine : Tuxedo InfinityBook Pro 16 Gen8, Intel i7-13xxxHX, NVIDIA RTX 4070 Laptop 8GB

| Backend | WER | Temps (920s audio) | RTF | GPU/CPU |
|---|---|---|---|---|
| **Canary Rust** | **6.5%** | 42.7s | 0.046x | GPU |
| **Parakeet TDT** | 8.0% | 11.3s | 0.012x | GPU |
| **Vosk** | 12.8% | 114.1s | 0.124x | CPU |
| **Whisper** (faster-whisper) | 13.7% | 32.2s | 0.035x | GPU |

RTF = Real-Time Factor (temps traitement / durée audio). Plus bas = plus rapide.

### Observations

- **Canary** : meilleure qualité (6.5% WER) mais ~4× plus lent que Parakeet (décodeur autorégressif)
- **Parakeet** : meilleur compromis vitesse/qualité (8.0% WER, le plus rapide)
- **Vosk** : qualité honorable en CPU-only (12.8%), mais 10× plus lent
- **Whisper** : étonnamment le moins précis (13.7%), vitesse intermédiaire
- Pour la dictée push-to-talk (segments 3-5s), tous les backends GPU sont <100ms — la différence est imperceptible
- L'écart Canary/Parakeet se creuse sur les segments longs (>15s)

### Comparaison avec benchmarks précédents (2026-03-25, MLS/LibriSpeech 20 clips)

| Backend | WER mars (voix multiples) | WER avril (LibriVox) |
|---|---|---|
| Parakeet FR | 8.0% | 8.0% |
| Canary FR | 8.1% | **6.5%** |

Canary s'améliore sur du texte long continu (meilleur contexte pour le décodeur AED).

## Reproduction

```bash
cd librivox/

# Prérequis : les 4 backends configurés et fonctionnels
# Vérifier : dictee-switch-backend status

# Lancer le benchmark
for backend in canary parakeet whisper vosk; do
    echo "=== $backend ==="
    dictee-switch-backend asr $backend
    sleep 10
    # Warmup
    for i in 1 2 3; do transcribe-client bovary_ch01_01.wav > /dev/null 2>&1; done
    # Benchmark
    time for f in bovary_ch01_*.wav; do
        transcribe-client "$f" >> "bovary_ch01_${backend}.txt" 2>/dev/null
        echo -n " " >> "bovary_ch01_${backend}.txt"
    done
done

# Calcul WER (nécessite Python)
python3 -c "
import re
def normalize(t):
    t = t.lower().replace('\u2019',\"'\")
    return re.sub(r'\s+',' ',re.sub(r'[^\w\s\x27-]',' ',t)).strip()
def wer(r,h):
    rw,hw=r.split(),h.split(); R,H=len(rw),len(hw)
    d=[[0]*(H+1) for _ in range(R+1)]
    for i in range(R+1): d[i][0]=i
    for j in range(H+1): d[0][j]=j
    for i in range(1,R+1):
        for j in range(1,H+1):
            d[i][j]=d[i-1][j-1] if rw[i-1]==hw[j-1] else min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+1)
    return d[R][H]/R*100
ref=normalize(open('bovary_ch01_reference.txt').read())
ref=' '.join(ref.split()[:2249])
for b in ['parakeet','canary','whisper','vosk']:
    hyp=normalize(open(f'bovary_ch01_{b}.txt').read())
    print(f'{b:12s} WER={wer(ref,hyp):.1f}%  mots={len(hyp.split())}')
"
```

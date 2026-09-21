# Port du moteur de réunion en direct dans la 1.3.7 : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Donner à la 1.3 les deux options Rust que la fenêtre `dictee-meeting-live` sonde (`diarize-only --stream`, `transcribe-client --json-timestamps`) et les trois ajouts de `dictee-transcribe.py` sans lesquels le relais à l'arrêt de la réunion ne marche pas (`--diar-engine` et `--asr-model` acceptés, `speakers.json` lu, bouton History).

**Architecture:** Le Rust vient de master : trois cherry-picks pour `diarize-only`, une réécriture à la main de ~80 lignes pour `transcribe-client` sur le parseur d'arguments de la 1.3. Le daemon n'est pas touché, il répond déjà au mode `timestamps`. Côté Python, chaque ajout est une fonction de module pure (testable sans Qt par extraction, comme `tests/test-transcribe-routing.py` le fait déjà) plus un branchement minimal dans `TranscribeWindow`. Les noms de locuteurs de `speakers.json` sont posés dans les tables de noms juste après leur remise à zéro dans les deux finisseurs, avant le rendu : le panneau de renommage et le texte les prennent sans code supplémentaire.

**Tech Stack:** Rust (ort, hound, sortformer), Python 3 + PyQt6, bash, podman (conteneur Debian 12 pour tout build Rust).

**Spec:** /home/rapha/SOURCES/RAPHA_STT/dictee-137/docs/superpowers/specs/2026-09-20-port-meeting-live-engine-1.3.7.md

## Global Constraints

- Branche `1.3.7/meeting-engine` (depuis `release/1.3` 6ff9645), worktree /home/rapha/SOURCES/RAPHA_STT/dictee-137. Référence master : dépôt /mnt/ff433a59-fbed-4db3-9e7d-aeb235009f1b/DEV/SOURCES/RAPHA_STT/dictee, commits 7fb5a58, 47af16f, 014f99f, ca6fdc1, 488171a, b640953, 96800c5, 63b6bee.
- `cargo` sur l'hôte est refusé par les hooks. Tout build et tout `cargo test` passent par `./packaging/cargo-glibc236.sh` (podman, sortie dans `target/glibc236/`). Les binaires qui en sortent s'exécutent sur l'hôte.
- Le daemon (`src/bin/transcribe_daemon.rs`) n'est pas modifié.
- Tout test Qt tourne avec `QT_QPA_PLATFORM=offscreen` et `XDG_CONFIG_HOME` pointé sur un dossier jetable contenant un `dictee.conf` avec `DICTEE_SETUP_DONE=true` (sinon `TranscribeWindow.__init__` ouvre une boîte modale de premier lancement, ligne 2166-2185).
- Aucun test ne lance de binaire Rust ni ne touche au vrai daemon.
- Langue : code, commentaires, messages de commit, msgid en anglais. Aucun tiret cadratin dans les textes.
- Aucun nouveau fichier livré : les quatre cibles de packaging ne changent que par le rebuild.

---

## Structure des fichiers

- Modifier : `src/sortformer.rs`, `src/bin/diarize_only.rs` (cherry-picks, Task 1)
- Créer : `tests/test_diarize_stream.sh` (vient avec 7fb5a58, Task 1)
- Modifier : `src/bin/transcribe_client.rs` (Task 2)
- Modifier : `dictee-transcribe.py` (Tasks 3, 4, 5)
- Créer : `tests/test-transcribe-args.py` (fonctions pures, Tasks 3, 4, 5)
- Créer : `tests/offscreen-check_transcribe_handoff.py` (fenêtre hors écran, Tasks 3, 4, 5)
- Modifier : `.github/workflows/rust.yml` (Task 6)
- Modifier : `pkg/` (rebuild, Task 7)

---

### Task 1 : `diarize-only --stream`, trois cherry-picks

**Files:**
- Modify: `src/sortformer.rs`, `src/bin/diarize_only.rs`
- Create: `tests/test_diarize_stream.sh`

**Interfaces:**
- Produces: `diarize-only --stream [--sensitivity N]` lit sur stdin des lignes `FILE: <chemin.wav>`, écrit un bloc de segments par fichier terminé par une ligne vide, et `[diarize-only --stream] ready` sur stderr au démarrage. C'est ce que la fenêtre attend (dictee-meeting-live, worker de diarisation).

- [ ] **Step 1 : vérifier le point de départ**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137
git branch --show-current          # 1.3.7/meeting-engine
git status --short | grep -v '^??' # vide
```

- [ ] **Step 2 : cherry-pick 7fb5a58**

```bash
git cherry-pick -x 7fb5a58
```

Attendu : « [1.3.7/meeting-engine …] feat(diarize-only): stream mode (Sortformer alive, IDs cohérents) », 3 fichiers (`src/bin/diarize_only.rs`, `src/sortformer.rs`, `tests/test_diarize_stream.sh`). `git apply --check` l'a validé le 2026-09-20.

- [ ] **Step 3 : cherry-pick 47af16f**

```bash
git cherry-pick -x 47af16f
```

Ce commit touche aussi `.gitignore` (3 lignes). En cas de conflit sur `.gitignore`, garder les deux côtés. En cas de conflit sur `src/sortformer.rs` ou `src/bin/diarize_only.rs`, résoudre en prenant le contenu de master à ce commit comme référence :

```bash
git -C /mnt/ff433a59-fbed-4db3-9e7d-aeb235009f1b/DEV/SOURCES/RAPHA_STT/dictee show 47af16f:src/sortformer.rs > /tmp/sortformer-47af16f.rs
diff /tmp/sortformer-47af16f.rs src/sortformer.rs
```

puis `git add` et `git cherry-pick --continue`.

- [ ] **Step 4 : cherry-pick 014f99f**

```bash
git cherry-pick -x 014f99f
```

Même règle de résolution.

- [ ] **Step 5 : vérifier que sortformer.rs est identique à master**

```bash
git diff --stat master -- src/sortformer.rs
```

Attendu : aucune sortie (fichier identique). Si une différence reste, elle vient d'une résolution de conflit : la corriger jusqu'à diff vide.

- [ ] **Step 6 : cargo test dans le conteneur**

```bash
./packaging/cargo-glibc236.sh test --release --features sortformer 2>&1 | tail -25
```

Attendu : `test result: ok` pour chaque cible, dont les deux tests `apply_preemphasis_*` de 014f99f. Un échec de compilation ici signale une résolution de conflit ratée en Step 3-4.

- [ ] **Step 7 : build du binaire et test shell sur le poste**

```bash
./packaging/cargo-glibc236.sh build --release --features sortformer --bin diarize-only
ls tests/fixtures/diarize_sample_30s.wav || cp /home/rapha/SOURCES/RAPHA_STT/dictee/tests/fixtures/diarize_sample_30s.wav tests/fixtures/
BIN=target/glibc236/release/diarize-only bash tests/test_diarize_stream.sh
```

Attendu : `PASS: stream mode emits 2 chunks` (ou plus). Le test a besoin des modèles Sortformer installés sur le poste (`/usr/share/dictee/sortformer` ou `models/`), il n'ira pas en CI.

- [ ] **Step 8 : vérifier le marqueur que la fenêtre sonde**

```bash
target/glibc236/release/diarize-only --help 2>&1 | grep -- '--stream'
```

Attendu : une ligne contenant `--stream`.

- [ ] **Step 9 : rien à commiter (les cherry-picks le sont), noter les hashes**

```bash
git log --oneline -3
```

---

### Task 2 : `transcribe-client --json-timestamps`

**Files:**
- Modify: `src/bin/transcribe_client.rs` (lignes 23-61 parseur, 77-95 aide, 100-110 mode fichier, 390-420 `send_to_daemon`, 422-475 tests)

**Interfaces:**
- Consumes: `parse_client_args(&[String]) -> Result<ClientArgs, String>`, `send_to_daemon(&str, &str)`, statique `SOCKET_PATH`.
- Produces: `transcribe-client <fichier> --json-timestamps [--socket p]` écrit sur stdout une ligne `{"tokens":[{"text":"…","start_s":0.500,"end_s":1.200},…]}` et sort en 0 ; `--help` contient `--json-timestamps`. Fonctions `send_to_daemon_with_mode(audio_path: &str, mode: &str, socket_path: &str) -> Result<String, Box<dyn Error>>` et `parse_timestamps_to_json(raw: &str) -> String`.

- [ ] **Step 1 : tests du parseur (échouent : le champ n'existe pas)**

Ajouter à la fin de `mod arg_tests` (avant l'accolade fermante, après `help_flag_is_parsed`) :

```rust
    #[test]
    fn json_timestamps_flag_is_parsed() {
        let p = parse_client_args(&argv(&["rec.wav", "--json-timestamps"])).unwrap();
        assert!(p.json_timestamps);
        assert_eq!(p.audio.as_deref(), Some("rec.wav"));
    }

    #[test]
    fn json_timestamps_with_socket() {
        let p = parse_client_args(&argv(&["--socket", "/tmp/x.sock", "--json-timestamps", "rec.wav"])).unwrap();
        assert!(p.json_timestamps);
        assert_eq!(p.socket.as_deref(), Some("/tmp/x.sock"));
        assert_eq!(p.audio.as_deref(), Some("rec.wav"));
    }

    #[test]
    fn json_timestamps_default_off() {
        assert!(!parse_client_args(&argv(&["rec.wav"])).unwrap().json_timestamps);
    }
```

- [ ] **Step 2 : lancer, vérifier l'échec de compilation**

```bash
./packaging/cargo-glibc236.sh test --release --bin transcribe-client 2>&1 | grep -E "error\[|no field" | head -3
```

Attendu : `no field \`json_timestamps\``.

- [ ] **Step 3 : le champ et la branche du parseur**

Dans `struct ClientArgs` (ligne 25-31), ajouter après `audio` :

```rust
    /// `--json-timestamps`: ask the daemon for word timestamps and print them
    /// as one JSON line. File mode only (what dictee-meeting-live drives).
    json_timestamps: bool,
```

Dans `parse_client_args`, ajouter une branche avant `s if s.starts_with('-')` :

```rust
            "--json-timestamps" => out.json_timestamps = true,
```

- [ ] **Step 4 : tests verts**

```bash
./packaging/cargo-glibc236.sh test --release --bin transcribe-client 2>&1 | tail -5
```

Attendu : `test result: ok. 10 passed`.

- [ ] **Step 5 : tests du formateur (échouent : fonction absente)**

Ajouter un second module de tests à la fin du fichier :

```rust
#[cfg(test)]
mod json_tests {
    use super::*;

    #[test]
    fn empty_input_gives_empty_tokens() {
        assert_eq!(parse_timestamps_to_json(""), r#"{"tokens":[]}"#);
    }

    #[test]
    fn two_words() {
        let raw = "[0.50s - 1.20s] Hello\n[1.20s - 1.80s] world";
        assert_eq!(
            parse_timestamps_to_json(raw),
            r#"{"tokens":[{"text":"Hello","start_s":0.500,"end_s":1.200},{"text":"world","start_s":1.200,"end_s":1.800}]}"#
        );
    }

    #[test]
    fn quotes_and_backslashes_are_escaped() {
        let raw = r#"[0.00s - 0.10s] say "hi" \ bye"#;
        assert_eq!(
            parse_timestamps_to_json(raw),
            r#"{"tokens":[{"text":"say \"hi\" \\ bye","start_s":0.000,"end_s":0.100}]}"#
        );
    }

    #[test]
    fn malformed_lines_are_skipped() {
        let raw = "garbage\n[broken\n[0.10s - 0.20s] ok\n\n[1.00s] nope";
        assert_eq!(
            parse_timestamps_to_json(raw),
            r#"{"tokens":[{"text":"ok","start_s":0.100,"end_s":0.200}]}"#
        );
    }

    #[test]
    fn output_is_valid_json_shape() {
        // The window does json.loads(stdout)["tokens"]: one line, no trailing newline.
        let out = parse_timestamps_to_json("[0.00s - 0.50s] a");
        assert!(out.starts_with("{\"tokens\":["));
        assert!(out.ends_with("]}"));
        assert!(!out.contains('\n'));
    }
}
```

- [ ] **Step 6 : lancer, vérifier l'échec**

```bash
./packaging/cargo-glibc236.sh test --release --bin transcribe-client 2>&1 | grep -E "cannot find function" | head -2
```

Attendu : `cannot find function \`parse_timestamps_to_json\``.

- [ ] **Step 7 : les deux fonctions**

Ajouter après `send_to_daemon` (après la ligne 420, avant `#[cfg(test)]`) :

```rust
/// Same round trip as `send_to_daemon`, with a mode word after the path
/// (`<path>\t<mode>`): the daemon then answers several lines and closes
/// the connection, so read to EOF instead of one line.
fn send_to_daemon_with_mode(audio_path: &str, mode: &str, socket_path: &str) -> Result<String, Box<dyn std::error::Error>> {
    let mut stream = UnixStream::connect(socket_path).map_err(|e| {
        format!(
            "Cannot connect to daemon at {}. Is transcribe-daemon running? Error: {}",
            socket_path, e
        )
    })?;
    stream.set_read_timeout(Some(Duration::from_secs(120)))?;

    writeln!(stream, "{}\t{}", audio_path, mode)?;
    stream.flush()?;

    let mut response = String::new();
    let reader = BufReader::new(&stream);
    for line in reader.lines() {
        let l = line?;
        if !response.is_empty() { response.push('\n'); }
        response.push_str(&l);
    }

    if response.starts_with("ERROR:") {
        Err(response.into())
    } else {
        Ok(response)
    }
}

/// Turn the daemon's timestamp lines (`[0.50s - 1.20s] word`) into one JSON
/// line `{"tokens":[{"text","start_s","end_s"},…]}`. Lines that do not fit
/// the shape are skipped. Copied from master (ca6fdc1) so the window reads
/// the same contract on both lines.
fn parse_timestamps_to_json(raw: &str) -> String {
    let mut tokens = Vec::new();
    for line in raw.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix('[') {
            if let Some(close) = rest.find(']') {
                let ts_part = &rest[..close];
                let text = rest[close + 1..].trim();
                let parts: Vec<&str> = ts_part.splitn(2, " - ").collect();
                if parts.len() == 2 {
                    let start_s: f64 = parts[0].trim_end_matches('s').parse().unwrap_or(0.0);
                    let end_s: f64 = parts[1].trim_end_matches('s').parse().unwrap_or(0.0);
                    // Escape for JSON: backslash and double quote are all the
                    // daemon can emit in a token; control characters never occur.
                    let escaped = text.replace('\\', "\\\\").replace('"', "\\\"");
                    tokens.push(format!(
                        "{{\"text\":\"{}\",\"start_s\":{:.3},\"end_s\":{:.3}}}",
                        escaped, start_s, end_s
                    ));
                }
            }
        }
    }
    format!("{{\"tokens\":[{}]}}", tokens.join(","))
}
```

- [ ] **Step 8 : tests verts**

```bash
./packaging/cargo-glibc236.sh test --release --bin transcribe-client 2>&1 | tail -5
```

Attendu : `test result: ok. 15 passed`. Si `json_timestamps_flag_is_parsed` compile mais que le compilateur avertit « function never used » pour les deux nouvelles fonctions, c'est attendu jusqu'au Step 9.

- [ ] **Step 9 : brancher le mode fichier, refuser les autres modes, documenter**

Remplacer le bloc « Mode 1 » (lignes 100-110) par :

```rust
    // Mode 1: Direct file path provided
    if let Some(audio) = parsed.audio.as_deref() {
        let audio_path = resolve_path(audio)?;
        let (wav_path, needs_cleanup) = ensure_wav(&audio_path)?;
        let result = if parsed.json_timestamps {
            send_to_daemon_with_mode(&wav_path, "timestamps", &socket_path)
                .map(|raw| parse_timestamps_to_json(&raw))
        } else {
            send_to_daemon(&wav_path, &socket_path)
        };
        if needs_cleanup {
            let _ = fs::remove_file(&wav_path);
        }
        println!("{}", result?);
        return Ok(());
    }

    // --json-timestamps only makes sense with a file: refuse loudly rather
    // than transcribe stdin or the mic and print plain text under a JSON flag.
    if parsed.json_timestamps {
        eprintln!("transcribe-client: --json-timestamps requires an audio file argument");
        std::process::exit(2);
    }
```

Dans l'aide (ligne 85-86), ajouter après la ligne `--socket` :

```rust
        eprintln!("  --json-timestamps  With <fichier>: print word timestamps as one JSON line");
```

- [ ] **Step 10 : build, tests, et le marqueur**

```bash
./packaging/cargo-glibc236.sh test --release --bin transcribe-client 2>&1 | tail -3
./packaging/cargo-glibc236.sh build --release --bin transcribe-client
target/glibc236/release/transcribe-client --help 2>&1 | grep -- '--json-timestamps'
target/glibc236/release/transcribe-client --json-timestamps < /dev/null; echo "rc=$?"
```

Attendu : tests ok ; une ligne d'aide avec `--json-timestamps` ; le dernier appel affiche le message de refus et `rc=2` (stdin non terminal sans fichier).

- [ ] **Step 11 : test de bout en bout avec le daemon du poste, si présent**

```bash
ls $XDG_RUNTIME_DIR/transcribe.sock && target/glibc236/release/transcribe-client tests/fixtures/diarize_sample_30s.wav --json-timestamps | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d["tokens"]), "tokens;", d["tokens"][:2])'
```

Attendu : un nombre de tokens > 0 et deux dicts avec `text`, `start_s`, `end_s`. Si le socket n'existe pas, sauter cette étape et le noter : le test VM le couvre.

- [ ] **Step 12 : commit**

```bash
git add src/bin/transcribe_client.rs
git commit -m "feat(transcribe-client): --json-timestamps, word timestamps as one JSON line

File mode asks the daemon for the timestamps mode and reformats its
[start - end] lines into {\"tokens\":[...]}, the contract dictee-meeting-live
reads. Refused with stdin or the microphone. Rewritten on the 1.3 arg
parser from master ca6fdc1; the daemon already speaks the mode."
```

---

### Task 3 : `dictee-transcribe` accepte `--diar-engine` et `--asr-model`

**Files:**
- Modify: `dictee-transcribe.py` (imports 28-40, `_ChunkedPipelineWorker.__init__` 821-841, `TranscribeWindow.__init__` 2114, `_on_transcribe` 3844-3876, `main()` 5417-5460)
- Create: `tests/test-transcribe-args.py`, `tests/offscreen-check_transcribe_handoff.py`

**Interfaces:**
- Produces: fonction de module `_asr_model_env(spec) -> dict` ; `_build_arg_parser() -> argparse.ArgumentParser` ; `TranscribeWindow(file_path=None, auto_diarize=False, parent=None, asr_model=None, diar_engine=None)` avec attribut `self._asr_model_env: dict` ; `_ChunkedPipelineWorker(audio_path, sensitivity, diarize=True, parent=None, extra_env=None)` ; méthode `TranscribeWindow._build_process_env() -> QProcessEnvironment`.

- [ ] **Step 1 : le test des fonctions pures (échoue : fonctions absentes)**

Créer `tests/test-transcribe-args.py` :

```python
#!/usr/bin/env python3
"""Tests for the dictee-transcribe command line and its meeting handoff helpers.

dictee-meeting-live hands the recorded meeting over with
`dictee-transcribe --file audio.wav --diarize --diar-engine auto --asr-model
parakeet-int8`. argparse must accept that line, parakeet-int8/fp32 must reach
the Rust binaries as DICTEE_PARAKEET_QUANT, speakers.json must be matched onto
the batch speaker labels, and History must list past meetings.

Pure functions are extracted from dictee-transcribe.py without importing it
(PyQt6 is not installed in every CI job), like tests/test-transcribe-routing.py.

Run: python3 tests/test-transcribe-args.py [-v]
"""

import argparse
import json
import os
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dictee-transcribe.py")


def _load_func(name, ns_extra=None):
    """Extract a top-level def by name and exec it into a fresh namespace.

    ns_extra seeds the globals the function body needs (os, json, argparse).
    """
    with open(SCRIPT, encoding="utf-8") as f:
        lines = f.readlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(f"def {name}(")), None)
    if start is None:
        raise RuntimeError(f"Function {name}() not found in {SCRIPT}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end = j
            break
    ns = dict(ns_extra or {})
    exec("".join(lines[start:end]), ns)
    return ns[name]


_asr_model_env = _load_func("_asr_model_env")
_build_arg_parser = _load_func("_build_arg_parser", {"argparse": argparse})


class AsrModelEnvTests(unittest.TestCase):

    def test_int8(self):
        self.assertEqual(_asr_model_env("parakeet-int8"), {"DICTEE_PARAKEET_QUANT": "int8"})

    def test_fp32(self):
        self.assertEqual(_asr_model_env("parakeet-fp32"), {"DICTEE_PARAKEET_QUANT": "fp32"})

    def test_other_engines_are_ignored(self):
        for spec in ("whisper", "whisper-rust", "nemotron", "kyutai", "", None):
            with self.subTest(spec=spec):
                self.assertEqual(_asr_model_env(spec), {})


class ArgParserTests(unittest.TestCase):

    def test_meeting_handoff_line_is_accepted(self):
        args = _build_arg_parser().parse_args(
            ["--file", "/x/audio.wav", "--diarize",
             "--diar-engine", "auto", "--asr-model", "parakeet-int8"])
        self.assertEqual(args.file, "/x/audio.wav")
        self.assertTrue(args.diarize)
        self.assertEqual(args.diar_engine, "auto")
        self.assertEqual(args.asr_model, "parakeet-int8")

    def test_analyze_another_file_line_is_accepted(self):
        args = _build_arg_parser().parse_args(["--asr-model", "parakeet-fp32"])
        self.assertIsNone(args.file)
        self.assertEqual(args.asr_model, "parakeet-fp32")

    def test_defaults(self):
        args = _build_arg_parser().parse_args([])
        self.assertIsNone(args.diar_engine)
        self.assertIsNone(args.asr_model)
        self.assertEqual(args.files, [])

    def test_positional_files_still_work(self):
        args = _build_arg_parser().parse_args(["a.wav", "b.wav"])
        self.assertEqual(args.files, ["a.wav", "b.wav"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 : lancer, vérifier l'échec**

```bash
python3 tests/test-transcribe-args.py 2>&1 | tail -2
```

Attendu : `RuntimeError: Function _asr_model_env() not found`.

- [ ] **Step 3 : les deux fonctions de module et la signature du constructeur**

Ajouter après `_read_conf` (après sa fin, avant la fonction suivante, vers la ligne 425) :

```python
def _asr_model_env(spec):
    """Env overrides for an `--asr-model` spec passed by dictee-meeting-live.

    Only the Parakeet variants exist on this line: int8 / fp32 map onto
    DICTEE_PARAKEET_QUANT, which the Rust binaries read (execution.rs,
    model_tdt.rs). Anything else (whisper, nemotron...) is ignored and the
    conf's own model applies.
    """
    if spec == "parakeet-int8":
        return {"DICTEE_PARAKEET_QUANT": "int8"}
    if spec == "parakeet-fp32":
        return {"DICTEE_PARAKEET_QUANT": "fp32"}
    return {}


def _build_arg_parser():
    parser = argparse.ArgumentParser(description="Dictee - Transcribe audio files")
    parser.add_argument("--file", "-f", help="Audio file to transcribe")
    parser.add_argument("--diarize", "-d", action="store_true",
                        help="Enable speaker diarization")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging to stderr and /tmp/dictee-transcribe.log")
    # Passed by dictee-meeting-live at the end of a meeting. Only Sortformer
    # exists on this line, so the engine is accepted and logged, nothing more.
    parser.add_argument("--diar-engine", default=None,
                        help="Diarization engine requested by the caller (accepted, ignored)")
    # parakeet-int8 / parakeet-fp32 are honoured (DICTEE_PARAKEET_QUANT);
    # other specs are ignored and the configured model applies.
    parser.add_argument("--asr-model", default=None,
                        help="ASR model spec (parakeet-int8, parakeet-fp32)")
    # Positional args: receive %F from .desktop / file-manager open-with /
    # CLI usage like `dictee-transcribe foo.wav`. Only the first one is
    # used (the UI handles a single file at a time).
    parser.add_argument("files", nargs="*",
                        help="Audio file path(s); first one is opened.")
    return parser
```

Dans `main()` (ligne 5417-5428), remplacer la construction du parseur par :

```python
    args = _build_arg_parser().parse_args()
```

(supprimer les `parser = …` et `parser.add_argument(…)` devenus redondants, y compris le commentaire sur `%F` déplacé dans `_build_arg_parser`). Et l'instanciation (ligne 5455-5458) devient :

```python
    win = TranscribeWindow(
        file_path=file_path,
        auto_diarize=args.diarize,
        asr_model=args.asr_model,
        diar_engine=args.diar_engine,
    )
```

Signature du constructeur (ligne 2114) :

```python
    def __init__(self, file_path=None, auto_diarize=False, parent=None,
                 asr_model=None, diar_engine=None):
        super().__init__(parent)
        # Overrides for the Rust binaries, from --asr-model (meeting handoff).
        # Applied on top of dictee.conf in every launch path that builds an
        # env for them: _on_transcribe (QProcess) and _ChunkedPipelineWorker.
        # The two-phase daemon path uses whatever model the daemon loaded.
        self._asr_model_env = _asr_model_env(asr_model)
        if asr_model and not self._asr_model_env:
            _dbg(f"--asr-model {asr_model!r} not available on this line, ignored")
        if diar_engine:
            _dbg(f"--diar-engine {diar_engine!r} accepted, Sortformer is the only engine here")
```

(la ligne `super().__init__(parent)` existante est conservée, les lignes ci-dessus s'insèrent juste après elle).

- [ ] **Step 4 : tests pures vertes**

```bash
python3 tests/test-transcribe-args.py -v 2>&1 | tail -3
```

Attendu : `OK`, 7 tests.

- [ ] **Step 5 : test hors écran de l'injection dans les deux env (échoue)**

Créer `tests/offscreen-check_transcribe_handoff.py` :

```python
#!/usr/bin/env python3
"""Offscreen checks of the dictee-transcribe side of the meeting handoff.

Builds the real TranscribeWindow (QT_QPA_PLATFORM=offscreen) against a
throwaway config so the first-run dialog never opens, then checks:
- --asr-model reaches both binary env builders as DICTEE_PARAKEET_QUANT
- speakers.json names land in the speaker maps before the panel is built
- History lists past meetings and loads the chosen one into the player path

No Rust binary is launched, no daemon is contacted.
"""
import importlib.util
import json
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_cfg = tempfile.mkdtemp(prefix="dictee-transcribe-test-cfg-")
with open(os.path.join(_cfg, "dictee.conf"), "w", encoding="utf-8") as f:
    f.write("DICTEE_SETUP_DONE=true\nDICTEE_PARAKEET_QUANT=int8\n")
os.environ["XDG_CONFIG_HOME"] = _cfg
os.environ["HOME"] = tempfile.mkdtemp(prefix="dictee-transcribe-test-home-")

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "dictee-transcribe.py")
spec = importlib.util.spec_from_file_location("dictee_transcribe", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication  # noqa: E402
app = QApplication([])

failures = []


def check(label, got, expected):
    if got == expected:
        print(f"PASS {label}")
    else:
        print(f"FAIL {label}: got {got!r}, expected {expected!r}")
        failures.append(label)


# --- 1. --asr-model reaches the binaries -------------------------------------

win = mod.TranscribeWindow(asr_model="parakeet-fp32", diar_engine="auto")
check("asr_model env computed", win._asr_model_env, {"DICTEE_PARAKEET_QUANT": "fp32"})

env = win._build_process_env()
check("QProcess env: --asr-model overrides the conf", env.value("DICTEE_PARAKEET_QUANT"), "fp32")

worker = mod._ChunkedPipelineWorker("/nonexistent/a.wav", 0.5, diarize=True,
                                    extra_env=win._asr_model_env)
check("chunked worker env: --asr-model overrides the conf",
      worker._subprocess_env.get("DICTEE_PARAKEET_QUANT"), "fp32")

plain = mod.TranscribeWindow()
check("no --asr-model: conf value kept in QProcess env",
      plain._build_process_env().value("DICTEE_PARAKEET_QUANT"), "int8")
check("no --asr-model: conf value kept in worker env",
      mod._ChunkedPipelineWorker("/nonexistent/a.wav", 0.5).
      _subprocess_env.get("DICTEE_PARAKEET_QUANT"), "int8")

if failures:
    print(f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("\nOK")
```

- [ ] **Step 6 : lancer, vérifier l'échec**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_transcribe_handoff.py 2>&1 | tail -3
```

Attendu : `AttributeError: 'TranscribeWindow' object has no attribute '_build_process_env'`.

- [ ] **Step 7 : `_build_process_env` et `extra_env`**

Dans `_on_transcribe`, remplacer les lignes 3862-3876 (de `env = self._process.processEnvironment()` à `self._process.setProcessEnvironment(env)`) par :

```python
        self._process.setProcessEnvironment(self._build_process_env())
```

et ajouter la méthode juste avant `def _on_transcribe` :

```python
    def _build_process_env(self):
        """Env for the Rust binaries launched through QProcess.

        ORT_DYLIB_PATH for CUDA builds (load-dynamic), then every DICTEE_*
        key of ~/.config/dictee.conf (the systemd services get them via
        EnvironmentFile=, a QProcess only inherits the shell env), then the
        --asr-model overrides on top so the meeting's choice wins.
        """
        env = QProcessEnvironment.systemEnvironment()
        ort_lib = "/usr/lib/dictee/libonnxruntime.so"
        if os.path.isfile(ort_lib):
            env.insert("ORT_DYLIB_PATH", ort_lib)
        for _k, _v in _read_conf().items():
            if _k.startswith("DICTEE_"):
                env.insert(_k, _v)
        for _k, _v in self._asr_model_env.items():
            env.insert(_k, _v)
        return env
```

Vérifier que `QProcessEnvironment` est déjà importé (il l'est, il est utilisé ligne 3864).

Dans `_ChunkedPipelineWorker.__init__` (ligne 821), la signature devient :

```python
    def __init__(self, audio_path, sensitivity, diarize=True, parent=None, extra_env=None):
```

et après la boucle de propagation de la conf (lignes 839-841), ajouter :

```python
        # --asr-model overrides from the meeting handoff, on top of the conf.
        for _k, _v in (extra_env or {}).items():
            self._subprocess_env[_k] = _v
```

À l'instanciation (ligne 3844-3845) :

```python
            self._chunked_worker = _ChunkedPipelineWorker(
                audio_path, sensitivity, diarize=diarize, parent=self,
                extra_env=self._asr_model_env)
```

- [ ] **Step 8 : hors écran vert**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_transcribe_handoff.py 2>&1 | tail -8
```

Attendu : 5 `PASS`, puis `OK`.

- [ ] **Step 9 : les suites existantes ne bougent pas**

```bash
python3 tests/test-transcribe-routing.py 2>&1 | tail -2
```

Attendu : `OK`.

- [ ] **Step 10 : commit**

```bash
git add dictee-transcribe.py tests/test-transcribe-args.py tests/offscreen-check_transcribe_handoff.py
git commit -m "feat(transcribe): accept --diar-engine and --asr-model from the meeting handoff

dictee-meeting-live ends a meeting with --diar-engine and --asr-model on
the command line; argparse refused both and the window never opened.
parakeet-int8/fp32 now reach the Rust binaries as DICTEE_PARAKEET_QUANT
in both launch paths (QProcess, chunked worker); the engine is logged."
```

---

### Task 4 : `speakers.json` prérempli à l'analyse

**Files:**
- Modify: `dictee-transcribe.py` (fonctions de module près de `_asr_model_env` ; `__init__` après le prefill CLI ligne 2187-2190 ; `_finish_transcription` après la remise à zéro lignes 4134-4135 ; `_on_finished` après la remise à zéro lignes 4308-4309)
- Modify: `tests/test-transcribe-args.py`, `tests/offscreen-check_transcribe_handoff.py`

**Interfaces:**
- Consumes: `speakers.json` écrit par la fenêtre : `{"name_map": {"0": "Alice"}, "anchors": {"0": [{"start": 1.0, "end": 2.5}, …]}}` (dictee-meeting-live:3305-3323), à côté de `audio.wav`. Segments batch : `[{"speaker": "Speaker 0", "start": f, "end": f, …}]` (sortie de `_parse_diarize_output`).
- Produces: fonctions de module `_load_speakers_json(file_path) -> dict | None`, `_match_anchors_to_batch_speakers(name_map, anchors, batch_segments) -> dict` ; méthode `TranscribeWindow._apply_pending_speakers()` qui remplit `self._speaker_name_map` et `self._text_edit._speaker_name_map` puis consomme `self._pending_speakers_data`.

- [ ] **Step 1 : tests purs (échouent)**

Ajouter à `tests/test-transcribe-args.py`, après les chargements existants :

```python
_load_speakers_json = _load_func("_load_speakers_json", {"os": os, "json": json, "_dbg": lambda *a: None})
_match_anchors = _load_func("_match_anchors_to_batch_speakers")
```

et les classes :

```python
class LoadSpeakersJsonTests(unittest.TestCase):

    def test_reads_file_next_to_audio(self):
        with tempfile.TemporaryDirectory() as d:
            data = {"name_map": {"0": "Alice"}, "anchors": {"0": [{"start": 0.0, "end": 1.0}]}}
            with open(os.path.join(d, "speakers.json"), "w", encoding="utf-8") as f:
                json.dump(data, f)
            self.assertEqual(_load_speakers_json(os.path.join(d, "audio.wav")), data)

    def test_missing_file_gives_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(_load_speakers_json(os.path.join(d, "audio.wav")))

    def test_no_path_gives_none(self):
        self.assertIsNone(_load_speakers_json(None))

    def test_corrupt_file_gives_none(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "speakers.json"), "w") as f:
                f.write("{not json")
            self.assertIsNone(_load_speakers_json(os.path.join(d, "audio.wav")))


class MatchAnchorsTests(unittest.TestCase):

    SEGS = [
        {"speaker": "Speaker 0", "start": 0.0, "end": 5.0, "text": "a"},
        {"speaker": "Speaker 1", "start": 5.0, "end": 10.0, "text": "b"},
        {"speaker": "Speaker 0", "start": 10.0, "end": 12.0, "text": "c"},
    ]

    def test_max_overlap_wins(self):
        name_map = {"0": "Alice", "1": "Bob"}
        anchors = {"0": [{"start": 0.5, "end": 4.0}], "1": [{"start": 6.0, "end": 9.0}]}
        self.assertEqual(_match_anchors(name_map, anchors, self.SEGS),
                         {"Speaker 0": "Alice", "Speaker 1": "Bob"})

    def test_one_batch_speaker_is_taken_once(self):
        # Both live speakers overlap Speaker 0; the more confident one gets it,
        # the other falls back to the next free label.
        name_map = {"0": "Alice", "1": "Bob"}
        anchors = {"0": [{"start": 0.0, "end": 5.0}],
                   "1": [{"start": 4.0, "end": 6.0}]}
        got = _match_anchors(name_map, anchors, self.SEGS)
        self.assertEqual(got["Speaker 0"], "Alice")
        self.assertEqual(got.get("Speaker 1"), "Bob")

    def test_no_overlap_no_name(self):
        name_map = {"0": "Alice"}
        anchors = {"0": [{"start": 50.0, "end": 60.0}]}
        self.assertEqual(_match_anchors(name_map, anchors, self.SEGS), {})

    def test_named_speaker_without_anchors_is_skipped(self):
        self.assertEqual(_match_anchors({"0": "Alice"}, {}, self.SEGS), {})

    def test_empty_segments(self):
        self.assertEqual(_match_anchors({"0": "Alice"}, {"0": [{"start": 0, "end": 1}]}, []), {})
```

- [ ] **Step 2 : lancer, vérifier l'échec**

```bash
python3 tests/test-transcribe-args.py 2>&1 | tail -2
```

Attendu : `RuntimeError: Function _load_speakers_json() not found`.

- [ ] **Step 3 : les deux fonctions de module**

Ajouter après `_build_arg_parser` :

```python
def _load_speakers_json(file_path):
    """speakers.json written by dictee-meeting-live next to the audio file.

    {"name_map": {"0": "Alice"}, "anchors": {"0": [{"start", "end"}, ...]}}.
    None when there is no file path, no file, or it does not parse.
    """
    if not file_path:
        return None
    path = os.path.join(os.path.dirname(os.path.abspath(file_path)), "speakers.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _dbg(f"speakers.json load error: {e!r}")
        return None
    if not isinstance(data, dict):
        return None
    _dbg(f"loaded speakers.json from {path}")
    return data


def _match_anchors_to_batch_speakers(name_map, anchors, batch_segments):
    """Match live-named speakers to batch speaker labels by overlap on anchors.

    name_map: {"0": "Alice"} (live speaker ids as strings), anchors:
    {"0": [{"start", "end"}, ...]}, batch_segments: output of
    _parse_diarize_output ({"speaker": "Speaker N", "start", "end", ...}).
    Greedy: the live speaker with the largest single overlap is assigned
    first, and a batch label is taken once. Returns {"Speaker N": name}.
    Same algorithm as master 488171a.
    """
    from collections import defaultdict
    overlap = defaultdict(lambda: defaultdict(float))
    for live_id, live_anchors in anchors.items():
        for anchor in live_anchors:
            a_start, a_end = anchor["start"], anchor["end"]
            for seg in batch_segments:
                ov = max(0.0, min(a_end, seg["end"]) - max(a_start, seg["start"]))
                if ov > 0:
                    overlap[live_id][seg["speaker"]] += ov
    used = set()
    result = {}
    by_confidence = sorted(
        name_map.keys(),
        key=lambda s: max(overlap[s].values()) if overlap[s] else 0,
        reverse=True)
    for live_id in by_confidence:
        candidates = [(label, ov) for label, ov in overlap[live_id].items() if label not in used]
        if not candidates:
            continue
        best = max(candidates, key=lambda c: c[1])[0]
        result[best] = name_map[live_id]
        used.add(best)
    return result
```

- [ ] **Step 4 : tests purs verts**

```bash
python3 tests/test-transcribe-args.py -v 2>&1 | tail -3
```

Attendu : `OK`, 16 tests.

- [ ] **Step 5 : test hors écran de l'application dans les finisseurs (échoue)**

Ajouter à `tests/offscreen-check_transcribe_handoff.py`, avant le bilan final :

```python
# --- 2. speakers.json fills the maps in both finishers ------------------------

_meeting = tempfile.mkdtemp(prefix="dictee-meeting-")
_audio = os.path.join(_meeting, "audio.wav")
open(_audio, "wb").close()
with open(os.path.join(_meeting, "speakers.json"), "w", encoding="utf-8") as f:
    json.dump({"name_map": {"0": "Alice", "1": "Bob"},
               "anchors": {"0": [{"start": 0.5, "end": 4.0}],
                           "1": [{"start": 6.0, "end": 9.0}]}}, f)

SEGS = [{"speaker": "Speaker 0", "start": 0.0, "end": 5.0, "text": "a"},
        {"speaker": "Speaker 1", "start": 5.0, "end": 10.0, "text": "b"}]

w = mod.TranscribeWindow(file_path=_audio)
check("speakers.json loaded at construction",
      (w._pending_speakers_data or {}).get("name_map"), {"0": "Alice", "1": "Bob"})

w._was_diarized = True
w._segments = list(SEGS)
w._speaker_name_map = {}
w._text_edit._speaker_name_map = {}
w._apply_pending_speakers()
check("names applied to the window map", w._speaker_name_map, {"Speaker 0": "Alice", "Speaker 1": "Bob"})
check("names applied to the target tab map", w._text_edit._speaker_name_map, {"Speaker 0": "Alice", "Speaker 1": "Bob"})
check("consumed once", w._pending_speakers_data, None)

w._speaker_name_map = {}
w._apply_pending_speakers()
check("second call is a no-op", w._speaker_name_map, {})

w2 = mod.TranscribeWindow(file_path=_audio)
w2._was_diarized = False
w2._segments = []
w2._apply_pending_speakers()
check("plain (non diarized) run: nothing applied, data kept for a later diarized run",
      (w2._pending_speakers_data or {}).get("name_map"), {"0": "Alice", "1": "Bob"})

# Both finishers reset the maps then build the panel: the apply call must sit
# between the two. Read the source rather than run a fake transcription.
src = open(SCRIPT, encoding="utf-8").read()
for fn in ("_finish_transcription", "_on_finished"):
    body = src.split(f"    def {fn}(")[1].split("\n    def ")[0]
    reset = body.find("self._text_edit._speaker_name_map = {}")
    apply_ = body.find("self._apply_pending_speakers()")
    refresh = body.find("self._refresh_rename_panel_for_target()", reset)
    check(f"{fn}: apply sits after the reset and before the panel refresh",
          reset != -1 and reset < apply_ < refresh, True)
```

- [ ] **Step 6 : lancer, vérifier l'échec**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_transcribe_handoff.py 2>&1 | grep -E "FAIL|Error" | head -3
```

Attendu : `AttributeError: 'TranscribeWindow' object has no attribute '_apply_pending_speakers'` (ou un FAIL sur `speakers.json loaded at construction`).

- [ ] **Step 7 : chargement au constructeur, méthode, deux appels**

Dans `__init__`, le bloc « Pre-fill from CLI args » (ligne 2187-2190) devient :

```python
        # Pre-fill from CLI args
        # Speaker names from a live meeting (speakers.json next to the audio):
        # loaded now, applied once the diarized run has its segments.
        self._pending_speakers_data = _load_speakers_json(file_path)
        if file_path:
            self._file_input.setText(file_path)
            self._load_audio(file_path)
```

Ajouter la méthode juste avant `def _finish_transcription` :

```python
    def _apply_pending_speakers(self):
        """Pour the live meeting's speaker names into the fresh run's maps.

        Called by both finishers right after they reset the maps and before
        _refresh_rename_panel_for_target / _apply_format_to, which read
        self._speaker_name_map and self._text_edit._speaker_name_map: the
        rename panel and the rendered text pick the names up without more
        code. Consumed on the first diarized run; a plain run keeps it.
        """
        data = getattr(self, "_pending_speakers_data", None)
        if not data or not self._was_diarized or not self._segments:
            return
        try:
            matched = _match_anchors_to_batch_speakers(
                data.get("name_map", {}) or {}, data.get("anchors", {}) or {}, self._segments)
        except Exception as e:
            _dbg(f"speakers.json apply error: {e!r}")
            matched = {}
        finally:
            self._pending_speakers_data = None
        if matched:
            self._speaker_name_map.update(matched)
            self._text_edit._speaker_name_map = dict(self._speaker_name_map)
            _dbg(f"speakers.json applied: {matched}")
```

Dans `_finish_transcription`, après les deux lignes de remise à zéro (4134-4135 : `self._speaker_name_map = {}` puis `self._text_edit._speaker_name_map = {}`), ajouter :

```python
        self._apply_pending_speakers()
```

Dans `_on_finished`, après ses deux lignes de remise à zéro (4308-4309, même paire), ajouter la même ligne.

- [ ] **Step 8 : hors écran vert**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_transcribe_handoff.py 2>&1 | tail -10
```

Attendu : tous `PASS`, `OK`. Les deux derniers checks lisent la source : si l'un échoue, l'appel n'est pas au bon endroit.

- [ ] **Step 9 : commit**

```bash
git add dictee-transcribe.py tests/test-transcribe-args.py tests/offscreen-check_transcribe_handoff.py
git commit -m "feat(transcribe): prefill speaker names from the live meeting's speakers.json

dictee-meeting-live writes name_map + anchors next to audio.wav; match
them onto the batch speaker labels by overlap (master 488171a) and set
the maps in both finishers right after their reset, so the rename panel
and the rendered text carry the names on the first paint."
```

---

### Task 5 : bouton History

**Files:**
- Modify: `dictee-transcribe.py` (import `QInputDialog` ligne 37 ; fonction de module ; bouton ligne 2216-2219 ; méthode près de `_on_browse` ligne 3055)
- Modify: `tests/test-transcribe-args.py`, `tests/offscreen-check_transcribe_handoff.py`

**Interfaces:**
- Produces: fonction de module `list_past_meetings(base=None) -> list[tuple[str, str]]` ; `TranscribeWindow._btn_history`, `TranscribeWindow._on_open_history()`.

- [ ] **Step 1 : tests purs (échouent)**

Ajouter à `tests/test-transcribe-args.py` :

```python
list_past_meetings = _load_func("list_past_meetings", {"os": os, "json": json})


class ListPastMeetingsTests(unittest.TestCase):

    def _mk(self, base, name, title=None, audio=True):
        d = os.path.join(base, name)
        os.makedirs(d)
        if audio:
            open(os.path.join(d, "audio.wav"), "wb").close()
        if title is not None:
            with open(os.path.join(d, "meeting.meta.json"), "w", encoding="utf-8") as f:
                json.dump({"title": title}, f)
        return os.path.join(d, "audio.wav")

    def test_recent_first_with_titles(self):
        with tempfile.TemporaryDirectory() as base:
            a = self._mk(base, "2026-09-01_10-00", "Kickoff")
            b = self._mk(base, "2026-09-20_15-44", "Weekly")
            self.assertEqual(list_past_meetings(base),
                             [("2026-09-20_15-44: Weekly", b), ("2026-09-01_10-00: Kickoff", a)])

    def test_missing_meta_uses_folder_name(self):
        with tempfile.TemporaryDirectory() as base:
            a = self._mk(base, "2026-09-01_10-00")
            self.assertEqual(list_past_meetings(base), [("2026-09-01_10-00", a)])

    def test_folder_without_audio_is_skipped(self):
        with tempfile.TemporaryDirectory() as base:
            self._mk(base, "2026-09-01_10-00", "Empty", audio=False)
            self.assertEqual(list_past_meetings(base), [])

    def test_corrupt_meta_uses_folder_name(self):
        with tempfile.TemporaryDirectory() as base:
            a = self._mk(base, "2026-09-01_10-00")
            with open(os.path.join(base, "2026-09-01_10-00", "meeting.meta.json"), "w") as f:
                f.write("{")
            self.assertEqual(list_past_meetings(base), [("2026-09-01_10-00", a)])

    def test_missing_base_is_empty(self):
        self.assertEqual(list_past_meetings("/nonexistent/dictee-meetings"), [])

    def test_env_dir_is_honoured(self):
        with tempfile.TemporaryDirectory() as base:
            a = self._mk(base, "2026-09-01_10-00", "Kickoff")
            old = os.environ.get("DICTEE_MEETING_DIR")
            os.environ["DICTEE_MEETING_DIR"] = base
            try:
                self.assertEqual(list_past_meetings(), [("2026-09-01_10-00: Kickoff", a)])
            finally:
                if old is None:
                    del os.environ["DICTEE_MEETING_DIR"]
                else:
                    os.environ["DICTEE_MEETING_DIR"] = old
```

- [ ] **Step 2 : lancer, vérifier l'échec**

```bash
python3 tests/test-transcribe-args.py 2>&1 | tail -2
```

Attendu : `RuntimeError: Function list_past_meetings() not found`.

- [ ] **Step 3 : la fonction de module**

Ajouter après `_match_anchors_to_batch_speakers` :

```python
def list_past_meetings(base=None):
    """[(label, audio_path)] of the meetings dictee-meeting-live recorded,
    most recent first (folder names start with the date). base defaults to
    DICTEE_MEETING_DIR, then ~/.local/share/dictee/meetings. A folder counts
    when it holds audio.wav; the label takes the title of meeting.meta.json
    when there is one.
    """
    base = base or os.environ.get(
        "DICTEE_MEETING_DIR",
        os.path.join(os.path.expanduser("~"), ".local/share/dictee/meetings"))
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base), reverse=True):
        d = os.path.join(base, name)
        audio = os.path.join(d, "audio.wav")
        if not os.path.isfile(audio):
            continue
        title = None
        meta = os.path.join(d, "meeting.meta.json")
        if os.path.isfile(meta):
            try:
                with open(meta, encoding="utf-8") as f:
                    title = json.load(f).get("title") or None
            except Exception:
                title = None
        out.append((f"{name}: {title}" if title else name, audio))
    return out
```

- [ ] **Step 4 : tests purs verts**

```bash
python3 tests/test-transcribe-args.py -v 2>&1 | tail -3
```

Attendu : `OK`, 22 tests.

- [ ] **Step 5 : test hors écran du bouton (échoue)**

Ajouter à `tests/offscreen-check_transcribe_handoff.py`, avant le bilan :

```python
# --- 3. History picks a meeting and loads it like a drop would ------------------

_hist = tempfile.mkdtemp(prefix="dictee-history-")
os.makedirs(os.path.join(_hist, "2026-09-20_15-44"))
_hist_audio = os.path.join(_hist, "2026-09-20_15-44", "audio.wav")
open(_hist_audio, "wb").close()
with open(os.path.join(_hist, "2026-09-20_15-44", "meeting.meta.json"), "w") as f:
    json.dump({"title": "Weekly"}, f)
os.environ["DICTEE_MEETING_DIR"] = _hist

h = mod.TranscribeWindow()
check("History button exists", hasattr(h, "_btn_history"), True)

loaded = []
h._load_audio = lambda p: loaded.append(p)


class _Pick:
    @staticmethod
    def getItem(parent, title, label, items, current=0, editable=True):
        return items[0], True


mod.QInputDialog = _Pick
h._on_open_history()
check("History sets the file field", h._file_input.text(), _hist_audio)
check("History loads the player", loaded, [_hist_audio])


class _Cancel:
    @staticmethod
    def getItem(parent, title, label, items, current=0, editable=True):
        return "", False


mod.QInputDialog = _Cancel
h._file_input.setText("")
loaded.clear()
h._on_open_history()
check("cancelled dialog changes nothing", (h._file_input.text(), loaded), ("", []))

shown = []


class _Msg:
    """Stands in for the module-level QMessageBox name (never patch the Qt
    class itself): records the information box instead of showing it."""
    @staticmethod
    def information(parent, title, text, *a, **k):
        shown.append(text)


_real_msgbox = mod.QMessageBox
mod.QMessageBox = _Msg
os.environ["DICTEE_MEETING_DIR"] = tempfile.mkdtemp(prefix="dictee-history-empty-")
h._on_open_history()
mod.QMessageBox = _real_msgbox
check("no meeting: one information box", len(shown), 1)
```

- [ ] **Step 6 : lancer, vérifier l'échec**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_transcribe_handoff.py 2>&1 | grep -E "FAIL|Error" | head -3
```

Attendu : `FAIL History button exists`.

- [ ] **Step 7 : import, bouton, méthode**

Ligne 37, ajouter `QInputDialog` à la liste importée de `PyQt6.QtWidgets` :

```python
    QMessageBox, QToolButton, QSizePolicy, QFrame, QToolTip, QInputDialog,
```

Après le bouton Browse (ligne 2219, `lay_file.addWidget(self._btn_browse)`), ajouter :

```python
        # Past meetings recorded by dictee-meeting-live (its "Analyze another
        # file" button opens this window empty and counts on History).
        self._btn_history = QPushButton(_("History"))
        self._btn_history.setToolTip(_("Open a past meeting"))
        self._btn_history.clicked.connect(self._on_open_history)
        lay_file.addWidget(self._btn_history)
```

(`setToolTip(_(...))` tel quel, comme `_btn_browse` ligne 2217 ; `_tip` est une fonction locale du constructeur, ligne 2135, pas une méthode.)

Après `_on_browse` (fin de la méthode qui commence ligne 3055), ajouter :

```python
    def _on_open_history(self):
        """Pick a past meeting and load it exactly like a drop does: field,
        player stopped, audio loaded. Master shipped History without the
        player load and had to fix it (2026-07-26)."""
        items = list_past_meetings()
        if not items:
            QMessageBox.information(self, _("History"), _("No past meeting found."))
            return
        labels = [lbl for lbl, _p in items]
        choice, ok = QInputDialog.getItem(
            self, _("Past meetings"), _("Meeting:"), labels, 0, False)
        if not ok or not choice:
            return
        path = dict(items)[choice]
        _dbg(f"_on_open_history: {path}")
        self._file_input.setText(path)
        if self._player is not None:
            self._player.stop()
        self._load_audio(path)
```

- [ ] **Step 8 : hors écran vert, i18n**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_transcribe_handoff.py 2>&1 | tail -8
grep -c 'msgid "History"' po/dictee.pot
```

Attendu : tous `PASS`, `OK`. Si le `grep` rend 0, les quatre nouveaux msgid (`History`, `Open a past meeting`, `No past meeting found.`, `Past meetings`, `Meeting:`) manquent au catalogue : les ajouter à `po/dictee.pot` et aux six `.po` avec traduction (fr : « Historique », « Ouvrir une réunion passée », « Aucune réunion passée trouvée. », « Réunions passées », « Réunion : »), puis `msgfmt --check -o po/fr.mo po/fr.po` pour chaque langue. Si `Meeting:` existe déjà (le pot a `Meeting`), vérifier avec `grep -n 'msgid "Meeting:"' po/dictee.pot` avant d'ajouter.

- [ ] **Step 9 : commit**

```bash
git add dictee-transcribe.py tests/test-transcribe-args.py tests/offscreen-check_transcribe_handoff.py po/
git commit -m "feat(transcribe): History button to reopen a past meeting

Lists DICTEE_MEETING_DIR (else ~/.local/share/dictee/meetings), most
recent first, titled from meeting.meta.json. The pick loads the player
like a drop does. dictee-meeting-live's \"Analyze another file\" relies on it."
```

---

### Task 6 : la fenêtre démarre, la CI lance les nouveaux tests

**Files:**
- Modify: `.github/workflows/rust.yml` (job `test-transcribe-routing` ligne 173-178, job `test-key-capture` étape « Run live meeting window tests » ligne 125-132)

- [ ] **Step 1 : le test de capacité rend vide avec les binaires rebuilds**

```bash
PATH="$PWD/target/glibc236/release:$PATH" python3 - <<'EOF'
import importlib.machinery, importlib.util
l = importlib.machinery.SourceFileLoader("ml", "dictee-meeting-live")
s = importlib.util.spec_from_loader("ml", l); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print("missing:", m.missing_live_engine_features())
EOF
```

Attendu : `missing: []`.

- [ ] **Step 2 : les tests de la fenêtre restent verts**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py 2>&1 | tail -2
python3 tests/test-meeting-live-wiring.py 2>&1 | tail -1
```

Attendu : `OK` deux fois. Le premier fabrique ses propres faux binaires pour le test de capacité, il ne dépend pas du PATH.

- [ ] **Step 3 : brancher les tests dans rust.yml**

Dans le job `test-transcribe-routing`, après l'étape existante :

```yaml
    - name: Run dictee-transcribe command line and handoff helper tests
      run: python3 tests/test-transcribe-args.py -v
```

Dans le job `test-key-capture`, dans l'étape « Run live meeting window tests », ajouter une ligne au bloc `run: |` :

```yaml
        python3 tests/offscreen-check_transcribe_handoff.py
```

- [ ] **Step 4 : toute la CI en local**

```bash
export QT_QPA_PLATFORM=offscreen
for t in tests/test-postprocess.py tests/test-keycode-tables.py tests/test-key-capture.py tests/offscreen-check_anim_speech_update.py tests/test-meeting-slug.py tests/test-ptt-meeting-passthrough.py tests/test-meeting-live-wiring.py tests/offscreen-check_meeting_live_window.py tests/offscreen-check_transcribe_handoff.py tests/test-keyboard-rescan.py tests/test-keyboard-detection.py tests/test-transcribe-routing.py tests/test-transcribe-args.py; do python3 $t >/dev/null 2>&1 && echo "OK   $t" || echo "FAIL $t"; done
bash tests/test-apply-continuation.sh >/dev/null 2>&1 && echo "OK   apply-continuation" || echo "FAIL apply-continuation"
env -i PATH="$PATH" HOME="$HOME" LANG=C LC_ALL=C QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_transcribe_handoff.py | tail -1
```

Attendu : 14 `OK`, et `OK` en locale C (le runner GitHub est en ASCII, cf. 6ff9645).

- [ ] **Step 5 : commit**

```bash
git add .github/workflows/rust.yml
git commit -m "ci: run the dictee-transcribe handoff tests"
```

---

### Task 7 : rebuild et packaging

**Files:**
- Modify: `pkg/` (arbre de packaging, artefact), `.dev/dist/` (non suivi)

- [ ] **Step 1 : build complet des quatre cibles**

```bash
./build-deb.sh 2>&1 | tail -6
./build-rpm.sh 2>&1 | tail -4
./build-tar.sh 2>&1 | tail -3
```

Attendu : « Built: .dev/dist/dictee-cpu_1.3.7~rc3-2_amd64.deb », les rpm et le tarball, sans erreur. Le numéro de version reste rc3-2 / rc3 ici, l'alignement et le bump rc4 sont l'étape 6 du programme.

- [ ] **Step 2 : les binaires du paquet ont les flags**

```bash
D=$(mktemp -d); dpkg-deb -x .dev/dist/dictee-cpu_1.3.7~rc3-2_amd64.deb $D
$D/usr/bin/transcribe-client --help 2>&1 | grep -c -- '--json-timestamps'
$D/usr/bin/diarize-only --help 2>&1 | grep -c -- '--stream'
grep -c "_on_open_history\|_apply_pending_speakers\|_asr_model_env" $D/usr/bin/dictee-transcribe
rm -rf $D
```

Attendu : `1`, `1`, un nombre ≥ 3.

- [ ] **Step 3 : commiter l'arbre pkg/ rebuild**

```bash
git add pkg/
git commit -m "chore(pkg): sync the packaging tree rebuilt with the live meeting engine"
```

- [ ] **Step 4 : pousser la branche pour la CI**

```bash
git push -u github 1.3.7/meeting-engine
gh run list -R rcspam/dictee --branch 1.3.7/meeting-engine --limit 1
```

Attendu : un run `Rust` en cours, puis vert sur les 11 jobs. Le test VM (étape 5 du programme) se fait avec le deb de `.dev/dist/`, poussé dans la VM par le guest-agent (mémoire `vm-libvirt-test-procedure`). Le merge dans `release/1.3` attend le test VM.

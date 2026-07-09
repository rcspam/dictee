// live_diarize_poc.rs — POC for the live (streaming) protocol on top of the
// src/diar multi-speaker engine. NOT product code, NOT packaged.
//
// Protocol under validation:
//   1. Bootstrap: once `--bootstrap-secs` of audio are available, run the full
//      AHC -> PLDA -> VBx clustering on the training embeddings accumulated so
//      far, producing speaker centroids.
//   2. Cruise: each new chunk's speaker embeddings are labeled instantly by
//      constrained cosine assignment against the current centroids (same
//      assignment rule as the offline pipeline).
//   3. New-voice event: when a training-quality embedding sits farther than
//      `--new-voice-dist` (cosine distance) from every centroid, re-run the
//      full clustering on everything accumulated (rate-limited by
//      `--cooldown-secs`) and relabel the past chunks.
//   4. Fidelity check: compare the live label matrix against the offline
//      reference run (best label mapping), and emit both RTTMs for DER
//      scoring.
//
// Chunk-local inference (segmentation + masked embeddings) is computed
// per 10 s window independently in pipeline.rs, so the offline artifacts
// replayed chronologically are bit-identical to what a real live run would
// produce. This POC therefore runs inference once (offline) and simulates
// the arrival timeline on the embedding stream.
//
// Clustering/centroid/assignment blocks below mirror pipeline.rs (which is
// pub(crate)); they are intentional copies for the POC only.

#[cfg(feature = "diar")]
mod poc {
    use std::time::Instant;

    use ndarray::{s, Array1, Array2};

    use parakeet_rs::diar::ahc::{self, AhcConfig};
    use parakeet_rs::diar::pipeline::{
        ChunkSpeakerClusters, FRAME_DURATION_SECONDS, FRAME_STEP_SECONDS,
        SEGMENTATION_STEP_SECONDS, SEGMENTATION_WINDOW_SECONDS,
    };
    use parakeet_rs::diar::plda::PldaTransform;
    use parakeet_rs::diar::reconstruct::Reconstructor;
    use parakeet_rs::diar::segment::{merge_segments, to_rttm};
    use parakeet_rs::diar::utils::cosine_similarity;
    use parakeet_rs::diar::vbx::{cluster_vbx, VbxConfig};
    use parakeet_rs::diar::{Diarizer, PipelineConfig};
    use parakeet_rs::ExecutionConfig;

    struct Args {
        wav: String,
        models_dir: std::path::PathBuf,
        bootstrap_secs: f64,
        new_voice_dist: f32,
        cooldown_secs: f64,
        threshold: f32,
        periodic_secs: f64,
        out_dir: std::path::PathBuf,
        file_id: String,
    }

    fn parse_args() -> Result<Args, Box<dyn std::error::Error>> {
        let argv: Vec<String> = std::env::args().collect();
        let mut wav = None;
        let mut models_dir = None;
        let mut bootstrap_secs = 30.0f64;
        let mut new_voice_dist = 0.6f32;
        let mut cooldown_secs = 10.0f64;
        let mut threshold = 0.6f32;
        let mut periodic_secs = 0.0f64;
        let mut out_dir = std::path::PathBuf::from(".");
        let mut i = 1;
        while i < argv.len() {
            match argv[i].as_str() {
                "--models-dir" => {
                    models_dir = Some(std::path::PathBuf::from(&argv[i + 1]));
                    i += 1;
                }
                "--bootstrap-secs" => {
                    bootstrap_secs = argv[i + 1].parse()?;
                    i += 1;
                }
                "--new-voice-dist" => {
                    new_voice_dist = argv[i + 1].parse()?;
                    i += 1;
                }
                "--cooldown-secs" => {
                    cooldown_secs = argv[i + 1].parse()?;
                    i += 1;
                }
                "--threshold" => {
                    threshold = argv[i + 1].parse()?;
                    i += 1;
                }
                "--periodic-secs" => {
                    periodic_secs = argv[i + 1].parse()?;
                    i += 1;
                }
                "--out-dir" => {
                    out_dir = std::path::PathBuf::from(&argv[i + 1]);
                    i += 1;
                }
                s if s.starts_with('-') => {
                    return Err(format!("unknown option '{s}'").into());
                }
                s => wav = Some(s.to_string()),
            }
            i += 1;
        }
        let wav = wav.ok_or(
            "usage: live-diarize-poc <wav-16k-mono> [--models-dir D] [--bootstrap-secs 30] \
             [--new-voice-dist 0.6] [--cooldown-secs 10] [--threshold 0.6] \
             [--periodic-secs 0] [--out-dir .]",
        )?;
        let models_dir = match models_dir {
            Some(d) => d,
            None => {
                let home = std::env::var("HOME")?;
                std::path::PathBuf::from(format!("{home}/.local/share/dictee/diar"))
            }
        };
        let file_id = std::path::Path::new(&wav)
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("poc")
            .to_string();
        Ok(Args {
            wav,
            models_dir,
            bootstrap_secs,
            new_voice_dist,
            cooldown_secs,
            threshold,
            periodic_secs,
            out_dir,
            file_id,
        })
    }

    // ── Copies of pub(crate) pipeline.rs logic (POC only) ───────────────────

    /// Mirror of pipeline.rs `weighted_centroids`.
    fn weighted_centroids(
        train: &Array2<f32>,
        gamma: &Array2<f32>,
        kept: &[usize],
    ) -> Array2<f32> {
        let mut centroids = Array2::<f32>::zeros((kept.len(), train.ncols()));
        for (out_idx, &spk) in kept.iter().enumerate() {
            let weights = gamma.column(spk);
            let weight_sum = weights.sum().max(1e-8);
            for (row_idx, w) in weights.iter().enumerate() {
                centroids
                    .row_mut(out_idx)
                    .scaled_add(*w / weight_sum, &train.row(row_idx));
            }
        }
        centroids
    }

    /// Mirror of pipeline.rs `AssignmentSearch` (constrained one-cluster-per-
    /// local-speaker maximization).
    struct AssignmentSearch<'a> {
        scores: &'a Array2<f32>,
        active_local: &'a [usize],
        target: usize,
        used: Vec<bool>,
        current: Vec<(usize, usize)>,
        best_score: f32,
        best: Vec<(usize, usize)>,
    }

    impl<'a> AssignmentSearch<'a> {
        fn run(&mut self, position: usize, score: f32) {
            if self.current.len() == self.target {
                if score > self.best_score {
                    self.best_score = score;
                    self.best = self.current.clone();
                }
                return;
            }
            if position == self.active_local.len() {
                return;
            }
            let remaining = self.active_local.len() - position;
            let needed = self.target - self.current.len();
            if remaining > needed {
                self.run(position + 1, score);
            }
            let spk = self.active_local[position];
            for cluster in 0..self.used.len() {
                if self.used[cluster] {
                    continue;
                }
                self.used[cluster] = true;
                self.current.push((spk, cluster));
                self.run(position + 1, score + self.scores[[spk, cluster]]);
                self.current.pop();
                self.used[cluster] = false;
            }
        }
    }

    fn best_assignment(
        scores: &Array2<f32>,
        active_local: &[usize],
        num_clusters: usize,
    ) -> Vec<(usize, usize)> {
        let target = active_local.len().min(num_clusters);
        let mut search = AssignmentSearch {
            scores,
            active_local,
            target,
            used: vec![false; num_clusters],
            current: Vec::new(),
            best_score: f32::NEG_INFINITY,
            best: Vec::new(),
        };
        search.run(0, 0.0);
        search.best
    }

    /// Mirror of pipeline.rs `assign_chunk_embeddings` for ONE chunk.
    /// Returns (assignments, worst training-quality min-distance in chunk).
    fn assign_one_chunk(
        segs: &ndarray::ArrayView3<f32>,
        embs: &ndarray::ArrayView3<f32>,
        chunk: usize,
        centroids: &Array2<f32>,
        train_rows: &[(usize, usize)],
    ) -> (Vec<(usize, usize)>, Option<f32>) {
        let num_local = embs.shape()[1];
        let k = centroids.nrows();
        let mut active_local = Vec::new();
        let mut scores = Array2::<f32>::from_elem((num_local, k), f32::NEG_INFINITY);
        for spk in 0..num_local {
            let is_active = segs.slice(s![chunk, .., spk]).sum() > 0.0;
            if !is_active {
                continue;
            }
            active_local.push(spk);
            let emb = embs.slice(s![chunk, spk, ..]);
            if emb.iter().any(|v| !v.is_finite()) {
                continue;
            }
            for c in 0..k {
                scores[[spk, c]] = 1.0 + cosine_similarity(&emb, &centroids.row(c));
            }
        }
        let finite_min = scores
            .iter()
            .copied()
            .filter(|v| v.is_finite())
            .fold(f32::INFINITY, f32::min);
        if finite_min.is_finite() {
            let mask = finite_min - 1.0;
            scores.mapv_inplace(|v| if v.is_finite() { v } else { mask });
        }
        let assignments = best_assignment(&scores, &active_local, k);

        // New-voice signal: only training-quality rows of this chunk qualify.
        let worst = train_rows
            .iter()
            .filter(|(c, _)| *c == chunk)
            .map(|(_, spk)| {
                let emb = embs.slice(s![chunk, *spk, ..]);
                (0..k)
                    .map(|c| 1.0 - cosine_similarity(&emb, &centroids.row(c)))
                    .fold(f32::INFINITY, f32::min)
            })
            .fold(None, |acc: Option<f32>, d| {
                Some(acc.map_or(d, |a| a.max(d)))
            });
        (assignments, worst)
    }

    /// Full re-clustering on the accumulated training rows. Mirror of
    /// pipeline.rs `TrainingEmbeddings::cluster` up to the centroids.
    fn recluster(
        train_rows: &[(usize, usize)],
        embs: &ndarray::ArrayView3<f32>,
        plda: &PldaTransform,
        ahc_cfg: &AhcConfig,
        vbx_cfg: &VbxConfig,
    ) -> (Array2<f32>, std::time::Duration) {
        let t = Instant::now();
        let dim = embs.shape()[2];
        let mut train = Array2::<f32>::zeros((train_rows.len(), dim));
        for (row, (chunk, spk)) in train_rows.iter().enumerate() {
            train
                .slice_mut(s![row, ..])
                .assign(&embs.slice(s![*chunk, *spk, ..]));
        }
        let ahc_labels = ahc::cluster(&train.view(), ahc_cfg.clone());
        let feats = plda.transform(&train.view(), 128);
        let phi = plda.phi();
        let (gamma, pi): (Array2<f32>, Array1<f32>) =
            cluster_vbx(&ahc_labels, &feats.view(), &phi.slice(s![..128]), vbx_cfg);
        let mut kept: Vec<usize> = pi
            .iter()
            .enumerate()
            .filter_map(|(idx, w)| (*w > 1e-7).then_some(idx))
            .collect();
        if kept.is_empty() && !pi.is_empty() {
            let best = pi
                .iter()
                .enumerate()
                .max_by(|a, b| a.1.total_cmp(b.1))
                .map(|(idx, _)| idx)
                .unwrap_or(0);
            kept.push(best);
        }
        let centroids = weighted_centroids(&train, &gamma, &kept);
        (centroids, t.elapsed())
    }

    /// Training-row filter for ONE chunk. Mirror of pipeline.rs
    /// `ChunkEmbeddings::training_set`.
    fn training_rows_of_chunk(
        segs: &ndarray::ArrayView3<f32>,
        embs: &ndarray::ArrayView3<f32>,
        chunk: usize,
    ) -> Vec<(usize, usize)> {
        let num_frames = segs.shape()[1] as f32;
        let num_local = segs.shape()[2];
        let single_active: Vec<bool> = segs
            .slice(s![chunk, .., ..])
            .rows()
            .into_iter()
            .map(|row| (row.iter().copied().sum::<f32>() - 1.0).abs() < 1e-6)
            .collect();
        let mut rows = Vec::new();
        for spk in 0..num_local {
            let clean_frames = segs
                .slice(s![chunk, .., spk])
                .iter()
                .zip(single_active.iter())
                .filter_map(|(v, single)| single.then_some(*v))
                .sum::<f32>();
            let emb = embs.slice(s![chunk, spk, ..]);
            let valid = emb.iter().all(|v| v.is_finite());
            if valid && clean_frames >= 0.2 * num_frames {
                rows.push((chunk, spk));
            }
        }
        rows
    }

    /// Mirror of pipeline.rs chunk frame geometry (pub(crate) helpers).
    fn closest_frame(ts: f64) -> usize {
        ((ts - 0.5 * FRAME_DURATION_SECONDS) / FRAME_STEP_SECONDS).round() as usize
    }

    // ── POC driver ───────────────────────────────────────────────────────────

    pub fn run() -> Result<(), Box<dyn std::error::Error>> {
        let args = parse_args()?;

        let mut reader = hound::WavReader::open(&args.wav)?;
        let spec = reader.spec();
        if spec.sample_rate != 16000 || spec.channels != 1 {
            return Err("POC expects a 16 kHz mono WAV".into());
        }
        let audio: Vec<f32> = match spec.sample_format {
            hound::SampleFormat::Float => {
                reader.samples::<f32>().collect::<Result<Vec<_>, _>>()?
            }
            hound::SampleFormat::Int => reader
                .samples::<i16>()
                .map(|s| s.map(|v| v as f32 / 32768.0))
                .collect::<Result<Vec<_>, _>>()?,
        };
        let audio_secs = audio.len() as f64 / 16000.0;

        let provider = parakeet_rs::best_provider();
        let cfg = ExecutionConfig::new().with_execution_provider(provider);
        let mut diarizer = match Diarizer::from_dir(&args.models_dir, Some(cfg)) {
            Ok(d) => d,
            Err(e) if provider != parakeet_rs::ExecutionProvider::Cpu => {
                eprintln!("[poc] GPU init failed ({e}); retrying on CPU.");
                let cpu = ExecutionConfig::new()
                    .with_execution_provider(parakeet_rs::ExecutionProvider::Cpu);
                Diarizer::from_dir(&args.models_dir, Some(cpu))?
            }
            Err(e) => return Err(e.into()),
        };

        let mut pipe_cfg = PipelineConfig::default();
        pipe_cfg.ahc.threshold = args.threshold;

        // Offline reference run (also provides the chunk-local artifacts the
        // live simulation replays).
        let t = Instant::now();
        let full = diarizer.diarize(&audio, &pipe_cfg)?;
        let offline_time = t.elapsed();

        let segs = full.segmentations.view();
        let embs = full.embeddings.view();
        let off = &full.hard_clusters;
        let num_chunks = segs.shape()[0];
        let step = SEGMENTATION_STEP_SECONDS;
        let win = SEGMENTATION_WINDOW_SECONDS;

        let plda = PldaTransform::from_dir(&args.models_dir)?;

        // ── Live simulation ──────────────────────────────────────────────────
        let num_local = if segs.ndim() < 3 { 0 } else { segs.shape()[2] };
        let mut live = Array2::<i32>::from_elem((num_chunks, num_local), -2);
        let mut train_rows: Vec<(usize, usize)> = Vec::new();
        let mut centroids: Option<Array2<f32>> = None;
        let mut last_recluster = f64::NEG_INFINITY;
        let mut events: Vec<(f64, &'static str, usize, f64)> = Vec::new();
        let mut assign_ms: Vec<f64> = Vec::new();
        let mut worst_dists: Vec<f32> = Vec::new();

        let relabel_all = |upto: usize,
                               live: &mut Array2<i32>,
                               cents: &Array2<f32>,
                               train_rows: &[(usize, usize)]| {
            for c in 0..=upto {
                let (assigns, _) = assign_one_chunk(&segs, &embs, c, cents, train_rows);
                for spk in 0..num_local {
                    live[[c, spk]] = -2;
                }
                for (spk, cluster) in assigns {
                    live[[c, spk]] = cluster as i32;
                }
            }
        };

        for chunk in 0..num_chunks {
            let avail = chunk as f64 * step + win;
            train_rows.extend(training_rows_of_chunk(&segs, &embs, chunk));

            let Some(cents) = centroids.as_ref() else {
                if avail >= args.bootstrap_secs && train_rows.len() >= 2 {
                    let (c, dur) = recluster(
                        &train_rows,
                        &embs,
                        &plda,
                        &pipe_cfg.ahc,
                        &pipe_cfg.vbx,
                    );
                    events.push((avail, "bootstrap", train_rows.len(), dur.as_secs_f64() * 1e3));
                    relabel_all(chunk, &mut live, &c, &train_rows);
                    centroids = Some(c);
                    last_recluster = avail;
                }
                continue;
            };

            let t = Instant::now();
            let (assigns, worst) = assign_one_chunk(&segs, &embs, chunk, cents, &train_rows);
            assign_ms.push(t.elapsed().as_secs_f64() * 1e3);
            for (spk, cluster) in assigns {
                live[[chunk, spk]] = cluster as i32;
            }
            if let Some(w) = worst {
                worst_dists.push(w);
            }

            let new_voice = worst.is_some_and(|w| w > args.new_voice_dist);
            let periodic_due =
                args.periodic_secs > 0.0 && avail - last_recluster >= args.periodic_secs;
            if (new_voice || periodic_due) && avail - last_recluster >= args.cooldown_secs {
                let kind = if new_voice { "new-voice" } else { "periodic" };
                let (c, dur) = recluster(
                    &train_rows,
                    &embs,
                    &plda,
                    &pipe_cfg.ahc,
                    &pipe_cfg.vbx,
                );
                events.push((avail, kind, train_rows.len(), dur.as_secs_f64() * 1e3));
                relabel_all(chunk, &mut live, &c, &train_rows);
                centroids = Some(c);
                last_recluster = avail;
            }
        }

        // Short-file fallback: never bootstrapped.
        if centroids.is_none() && train_rows.len() >= 2 {
            let (c, dur) =
                recluster(&train_rows, &embs, &plda, &pipe_cfg.ahc, &pipe_cfg.vbx);
            events.push((audio_secs, "final-only", train_rows.len(), dur.as_secs_f64() * 1e3));
            relabel_all(num_chunks - 1, &mut live, &c, &train_rows);
        }

        // ── Fidelity: best live->offline label mapping over active pairs ────
        let mut pair_counts: std::collections::HashMap<(i32, i32), usize> =
            std::collections::HashMap::new();
        let mut total = 0usize;
        let mut live_unassigned = 0usize;
        for chunk in 0..num_chunks {
            for spk in 0..num_local {
                let o = off.0[[chunk, spk]];
                if o < 0 {
                    continue;
                }
                total += 1;
                let l = live[[chunk, spk]];
                if l < 0 {
                    live_unassigned += 1;
                    continue;
                }
                *pair_counts.entry((l, o)).or_insert(0) += 1;
            }
        }
        let mut pairs: Vec<((i32, i32), usize)> = pair_counts.into_iter().collect();
        pairs.sort_by(|a, b| b.1.cmp(&a.1));
        let mut used_live = std::collections::HashSet::new();
        let mut used_off = std::collections::HashSet::new();
        let mut matched = 0usize;
        for ((l, o), count) in &pairs {
            if used_live.contains(l) || used_off.contains(o) {
                continue;
            }
            used_live.insert(*l);
            used_off.insert(*o);
            matched += count;
        }

        let off_speakers: std::collections::HashSet<i32> =
            off.0.iter().copied().filter(|v| *v >= 0).collect();
        let live_speakers: std::collections::HashSet<i32> =
            live.iter().copied().filter(|v| *v >= 0).collect();

        // ── Live RTTM through the engine's own reconstruction ───────────────
        let start_frames: Vec<usize> = (0..num_chunks)
            .map(|i| closest_frame(i as f64 * step + 0.5 * FRAME_DURATION_SECONDS))
            .collect();
        let output_frames = if num_chunks == 0 {
            0
        } else {
            closest_frame(
                win + (num_chunks - 1) as f64 * step + 0.5 * FRAME_DURATION_SECONDS,
            ) + 1
        };
        let live_clusters = ChunkSpeakerClusters(live.clone());
        let reconstructor = Reconstructor::with_clusters(
            &full.segmentations,
            &live_clusters,
            &start_frames,
            0,
        );
        let speaker_count = reconstructor.speaker_count(output_frames);
        let discrete = reconstructor.reconstruct_smoothed(&speaker_count, 0.1);
        let live_segments = merge_segments(
            &discrete.to_segments(FRAME_STEP_SECONDS, FRAME_DURATION_SECONDS),
            0.0,
        );

        std::fs::create_dir_all(&args.out_dir)?;
        let live_rttm = args.out_dir.join(format!("{}-live.rttm", args.file_id));
        let off_rttm = args.out_dir.join(format!("{}-offline.rttm", args.file_id));
        std::fs::write(&live_rttm, to_rttm(&live_segments, &args.file_id))?;
        std::fs::write(&off_rttm, full.rttm(&args.file_id))?;

        // ── Report ───────────────────────────────────────────────────────────
        println!("== live-diarize-poc report ==");
        println!("file: {} ({:.0}s, {} chunks)", args.wav, audio_secs, num_chunks);
        println!(
            "params: bootstrap={}s new-voice-dist={} cooldown={}s threshold={} periodic={}s",
            args.bootstrap_secs,
            args.new_voice_dist,
            args.cooldown_secs,
            args.threshold,
            args.periodic_secs
        );
        println!("offline run: {:.1}s wall", offline_time.as_secs_f64());
        println!("events ({}):", events.len());
        for (t, kind, rows, ms) in &events {
            println!("  t={:>7.1}s {:<10} rows={:<5} cluster={:.0}ms", t, kind, rows, ms);
        }
        if !assign_ms.is_empty() {
            let mean = assign_ms.iter().sum::<f64>() / assign_ms.len() as f64;
            let max = assign_ms.iter().cloned().fold(0.0f64, f64::max);
            println!(
                "per-chunk assignment: mean={:.3}ms max={:.3}ms (n={})",
                mean,
                max,
                assign_ms.len()
            );
        }
        if !worst_dists.is_empty() {
            let mut sorted = worst_dists.clone();
            sorted.sort_by(f32::total_cmp);
            let p = |q: f64| sorted[((sorted.len() - 1) as f64 * q) as usize];
            println!(
                "chunk worst-dist distribution: p50={:.3} p90={:.3} p99={:.3} max={:.3}",
                p(0.5),
                p(0.9),
                p(0.99),
                sorted[sorted.len() - 1]
            );
        }
        println!(
            "speakers: offline={} live={}",
            off_speakers.len(),
            live_speakers.len()
        );
        println!(
            "label agreement vs offline: {:.2}% ({} / {} active pairs, {} live-unassigned)",
            100.0 * matched as f64 / total.max(1) as f64,
            matched,
            total,
            live_unassigned
        );
        println!("rttm: {} / {}", live_rttm.display(), off_rttm.display());
        Ok(())
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(not(feature = "diar"))]
    {
        eprintln!("This POC requires the 'diar' feature.");
        std::process::exit(1);
    }
    #[cfg(feature = "diar")]
    poc::run()
}

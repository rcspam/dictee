//! Transcription pieces: a recording's speaker timeline cut into pieces that an ASR model
//! transcribes one by one, each piece keeping the speaker it belongs to.
//!
//! From the diarizer's speaker probabilities, one row every 10 ms: one speaker per frame, the most
//! probable one above the threshold (speech two people say at once is not transcribed twice); a
//! speaker's short pauses stay inside the piece; stretches too short to transcribe are dropped;
//! turns longer than the maximum are cut at their quietest 100 ms, never closer than half the
//! maximum to either end, so that a long turn does not reach the ASR model in one block.

use crate::sortformer::SpeakerSegment;
use ndarray::ArrayView2;

/// Audio samples in a 10 ms frame at 16 kHz.
const FRAME_SAMPLES: usize = 160;
/// Frames in the window whose energy picks a cut point (100 ms).
const QUIET_WINDOW: usize = 10;

/// How the timeline is cut, in seconds.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PieceParams {
    /// Longest piece; longer turns are cut.
    pub max_len: f32,
    /// A speaker's pause shorter than this stays inside the piece.
    pub max_gap: f32,
    /// Audio added before and after each piece.
    pub margin: f32,
    /// Shorter stretches are dropped.
    pub min_len: f32,
}

impl Default for PieceParams {
    fn default() -> Self {
        Self {
            max_len: 15.0,
            max_gap: 0.5,
            margin: 0.0,
            min_len: 0.3,
        }
    }
}

/// A speaker's frames `start..end`.
#[derive(Debug, Clone, Copy, PartialEq)]
struct Run {
    start: usize,
    end: usize,
    speaker: usize,
}

/// Frames in `seconds`.
fn frames(seconds: f32) -> usize {
    (seconds * 100.0).round() as usize
}

/// Runs of the frames' speaker: the most probable one above `threshold` (the lower id on a tie),
/// none on the frames where nobody is above it.
fn exclusive_runs(probs: ArrayView2<f32>, threshold: f32) -> Vec<Run> {
    let mut runs: Vec<Run> = Vec::new();
    for (f, row) in probs.rows().into_iter().enumerate() {
        let best = row
            .iter()
            .enumerate()
            .filter(|&(_, &p)| p > threshold)
            .fold(None, |best: Option<(usize, f32)>, (speaker, &p)| match best {
                Some((_, top)) if top >= p => best,
                _ => Some((speaker, p)),
            });
        match (best, runs.last_mut()) {
            (Some((speaker, _)), Some(last)) if last.speaker == speaker && last.end == f => {
                last.end = f + 1
            }
            (Some((speaker, _)), _) => runs.push(Run {
                start: f,
                end: f + 1,
                speaker,
            }),
            (None, _) => {}
        }
    }
    runs
}

/// Joins the consecutive runs of a speaker separated by fewer than `max_gap` frames.
fn bridge(runs: Vec<Run>, max_gap: usize) -> Vec<Run> {
    let mut out: Vec<Run> = Vec::with_capacity(runs.len());
    for run in runs {
        match out.last_mut() {
            Some(last)
                if last.speaker == run.speaker && run.start.saturating_sub(last.end) < max_gap =>
            {
                last.end = run.end
            }
            _ => out.push(run),
        }
    }
    out
}

/// Mean power of each 10 ms frame (the last one may be shorter).
fn frame_energy(audio: &[f32]) -> Vec<f32> {
    audio
        .chunks(FRAME_SAMPLES)
        .map(|frame| frame.iter().map(|x| x * x).sum::<f32>() / frame.len() as f32)
        .collect()
}

/// Cuts the runs longer than `max_len` frames at their quietest 100 ms, every piece at least half
/// of `max_len` long.
fn cut_long(runs: Vec<Run>, energy: &[f32], max_len: usize) -> Vec<Run> {
    let half = max_len / 2;
    let loudness = |centre: usize| -> f32 {
        let from = centre.saturating_sub(QUIET_WINDOW / 2).min(energy.len());
        let to = (centre + QUIET_WINDOW / 2).min(energy.len());
        energy[from..to].iter().sum()
    };
    let mut out = Vec::with_capacity(runs.len());
    for run in runs {
        let mut start = run.start;
        while run.end - start > max_len {
            let (first, last) = (start + half, (start + max_len).min(run.end - half));
            let cut = (first..=last).fold(first, |best, c| {
                if loudness(c) < loudness(best) {
                    c
                } else {
                    best
                }
            });
            out.push(Run {
                start,
                end: cut,
                speaker: run.speaker,
            });
            start = cut;
        }
        out.push(Run { start, ..run });
    }
    out
}

/// Transcription pieces of a recording, sorted by start, from its speaker probabilities (one row
/// every 10 ms) and its 16 kHz mono audio.
pub fn transcription_pieces(
    probs: ArrayView2<f32>,
    audio: &[f32],
    threshold: f32,
    params: &PieceParams,
) -> Vec<SpeakerSegment> {
    let max_gap = frames(params.max_gap);
    let min_len = frames(params.min_len);
    // dropping a flicker can join the two halves of the turn it interrupted: bridge again after
    let runs: Vec<Run> = bridge(exclusive_runs(probs, threshold), max_gap)
        .into_iter()
        .filter(|run| run.end - run.start >= min_len)
        .collect();
    let runs = cut_long(
        bridge(runs, max_gap),
        &frame_energy(audio),
        frames(params.max_len),
    );
    let duration = audio.len() as f32 / (FRAME_SAMPLES * 100) as f32;
    runs.into_iter()
        .map(|run| SpeakerSegment {
            start: (run.start as f32 / 100.0 - params.margin).max(0.0),
            end: (run.end as f32 / 100.0 + params.margin).min(duration),
            speaker_id: run.speaker,
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::Array2;

    fn run(start: usize, end: usize, speaker: usize) -> Run {
        Run { start, end, speaker }
    }

    /// Probabilities of `frames` frames where `speaker` has `p` on `from..to`, zero elsewhere.
    fn talk(probs: &mut Array2<f32>, speaker: usize, from: usize, to: usize, p: f32) {
        for f in from..to {
            probs[[f, speaker]] = p;
        }
    }

    #[test]
    fn each_frame_goes_to_the_most_probable_speaker_above_the_threshold() {
        let mut probs = Array2::<f32>::zeros((20, 8));
        talk(&mut probs, 0, 0, 10, 0.9);
        talk(&mut probs, 1, 5, 15, 0.6); // overlaps speaker 0 on 5..10, weaker
        talk(&mut probs, 2, 12, 14, 0.8); // stronger than speaker 1 on 12..14
        talk(&mut probs, 3, 16, 18, 0.3); // below the threshold
        assert_eq!(
            exclusive_runs(probs.view(), 0.5),
            vec![run(0, 10, 0), run(10, 12, 1), run(12, 14, 2), run(14, 15, 1)]
        );
    }

    #[test]
    fn equal_probabilities_go_to_the_lower_speaker() {
        let mut probs = Array2::<f32>::zeros((4, 8));
        talk(&mut probs, 5, 0, 4, 0.7);
        talk(&mut probs, 2, 0, 4, 0.7);
        assert_eq!(exclusive_runs(probs.view(), 0.5), vec![run(0, 4, 2)]);
    }

    #[test]
    fn short_pauses_of_a_speaker_are_bridged_but_not_across_someone_else() {
        let runs = vec![run(0, 10, 0), run(15, 30, 0), run(50, 60, 0), run(62, 70, 1), run(71, 80, 0)];
        assert_eq!(
            bridge(runs, 10),
            vec![run(0, 30, 0), run(50, 60, 0), run(62, 70, 1), run(71, 80, 0)]
        );
    }

    #[test]
    fn frame_energy_is_the_mean_power_of_each_ten_ms() {
        let mut audio = vec![0.5f32; 160];
        audio.extend(vec![0.0f32; 160]);
        audio.extend(vec![1.0f32; 80]);
        assert_eq!(frame_energy(&audio), vec![0.25, 0.0, 1.0]);
    }

    #[test]
    fn long_turns_are_cut_at_their_quietest_point() {
        // 25 s of speech with quiet 100 ms at 3 s, 7 s, 16 s and 23 s; pieces of at most 10 s
        let mut energy = vec![1.0f32; 2500];
        for dip in [300, 700, 1600, 2300] {
            energy[dip - 5..dip + 5].fill(0.0);
        }
        // the dip at 3 s is too early (pieces of at least 5 s), the one at 23 s too late
        assert_eq!(
            cut_long(vec![run(0, 2500, 4)], &energy, 1000),
            vec![run(0, 700, 4), run(700, 1600, 4), run(1600, 2500, 4)]
        );
    }

    #[test]
    fn turns_within_the_maximum_are_left_whole() {
        let energy = vec![1.0f32; 1200];
        let runs = vec![run(0, 1000, 0), run(1000, 1100, 1)];
        assert_eq!(cut_long(runs.clone(), &energy, 1000), runs);
    }

    #[test]
    fn pieces_drop_flickers_bridge_pauses_and_add_the_margin() {
        // 3 s of audio: speaker 0 on 0-1.5 s with a 30 ms flicker of speaker 1 at 0.80 s,
        // speaker 0 again on 1.7-2.0 s, speaker 1 on 2.2-2.9 s
        let mut probs = Array2::<f32>::zeros((301, 8));
        talk(&mut probs, 0, 0, 150, 0.9);
        talk(&mut probs, 1, 80, 83, 0.95);
        talk(&mut probs, 0, 170, 200, 0.9);
        talk(&mut probs, 1, 220, 290, 0.9);
        let audio = vec![0.1f32; 48_000];
        let params = PieceParams {
            margin: 0.1,
            ..PieceParams::default()
        };
        let pieces: Vec<(f32, f32, usize)> = transcription_pieces(probs.view(), &audio, 0.5, &params)
            .into_iter()
            .map(|p| (p.start, p.end, p.speaker_id))
            .collect();
        let close = |a: f32, b: f32| (a - b).abs() < 1e-4;
        let expected = [(0.0, 2.1, 0), (2.1, 3.0, 1)];
        assert_eq!(pieces.len(), expected.len(), "{pieces:?}");
        for (got, want) in pieces.iter().zip(expected) {
            assert!(
                close(got.0, want.0) && close(got.1, want.1) && got.2 == want.2,
                "{pieces:?}"
            );
        }
    }
}

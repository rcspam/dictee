//! Transcription pieces: a recording's speaker timeline cut into pieces that an ASR model
//! transcribes one by one, each piece keeping the speaker it belongs to.
//!
//! From the diarizer's speaker probabilities, one row every 10 ms: one speaker per frame, the most
//! probable one above the threshold (speech two people say at once is not transcribed twice); a
//! speaker's short pauses stay inside the piece; stretches too short to transcribe are dropped;
//! turns longer than the maximum (30 s, what Whisper takes at once) are cut in the longest pause
//! the diarizer heard inside them, else at their quietest 100 ms, never closer than half the
//! maximum to either end.

use ndarray::{s, Array2, ArrayView2, Axis};

/// A speaker's stretch of a recording, in seconds.
#[derive(Debug, Clone)]
pub struct SpeakerSegment {
    pub start: f32,
    pub end: f32,
    pub speaker_id: usize,
}

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
            max_len: 30.0,
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

/// Where to cut within `first..=last`: the longest pause the diarizer heard, else the quietest
/// 100 ms.
fn cut_point(energy: &[f32], silent: &[bool], first: usize, last: usize) -> usize {
    let loudness = |centre: usize| -> f32 {
        let from = centre.saturating_sub(QUIET_WINDOW / 2).min(energy.len());
        let to = (centre + QUIET_WINDOW / 2).min(energy.len());
        energy[from..to].iter().sum()
    };
    longest_pause(silent, first, last).unwrap_or_else(|| {
        (first..=last).fold(first, |best, c| {
            if loudness(c) < loudness(best) {
                c
            } else {
                best
            }
        })
    })
}

/// Middle of the longest stretch of `silent` frames within `first..=last`, if any.
fn longest_pause(silent: &[bool], first: usize, last: usize) -> Option<usize> {
    let mut best: Option<(usize, usize)> = None; // (start, length)
    let mut start = None;
    for f in first..=last + 1 {
        let quiet = f <= last && silent.get(f).copied().unwrap_or(false);
        match (quiet, start) {
            (true, None) => start = Some(f),
            (false, Some(from)) => {
                if best.is_none_or(|(_, len)| f - from > len) {
                    best = Some((from, f - from));
                }
                start = None;
            }
            _ => {}
        }
    }
    best.map(|(from, len)| from + len / 2)
}

/// Cuts the runs longer than `max_len` frames, every piece at least half of `max_len` long: in the
/// longest pause the diarizer heard (`silent`: no speaker above the threshold), else at the
/// quietest 100 ms of the sound.
fn cut_long(runs: Vec<Run>, energy: &[f32], silent: &[bool], max_len: usize) -> Vec<Run> {
    let half = max_len / 2;
    let mut out = Vec::with_capacity(runs.len());
    for run in runs {
        let mut start = run.start;
        while run.end - start > max_len {
            let (first, last) = (start + half, (start + max_len).min(run.end - half));
            let cut = cut_point(energy, silent, first, last);
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
    let silent: Vec<bool> = probs
        .rows()
        .into_iter()
        .map(|row| row.iter().all(|&p| p <= threshold))
        .collect();
    let runs = cut_long(
        bridge(runs, max_gap),
        &frame_energy(audio),
        &silent,
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

/// The pieces of `transcription_pieces` for a recording that arrives bit by bit, its speaker
/// probabilities a little behind its audio. A piece comes out once no later frame can change it: a
/// pause of `max_gap` after it, or, inside a long turn, a cut whose window can no longer move.
/// `finish` gives the rest.
pub struct PieceStream {
    threshold: f32,
    params: PieceParams,
    /// Probabilities of the open frames, from frame `base` on.
    probs: Array2<f32>,
    /// Energy of the frames from `base` on, as far as the audio goes.
    energy: Vec<f32>,
    /// Audio of a frame not complete yet.
    partial: Vec<f32>,
    base: usize,
    samples: usize,
    /// Pieces already given out end there (a long turn comes out in several).
    emitted_until: usize,
}

impl PieceStream {
    pub fn new(threshold: f32, params: PieceParams) -> Self {
        Self {
            threshold,
            params,
            probs: Array2::zeros((0, 0)),
            energy: Vec::new(),
            partial: Vec::new(),
            base: 0,
            samples: 0,
            emitted_until: 0,
        }
    }

    /// Adds the probabilities of the next 10 ms frames and the next audio (16 kHz mono, possibly
    /// ahead of them); returns the pieces this settles, in seconds since the start.
    pub fn push(&mut self, probs: ArrayView2<f32>, audio: &[f32]) -> Vec<SpeakerSegment> {
        self.probs = if self.probs.ncols() == 0 {
            probs.to_owned()
        } else {
            ndarray::concatenate![Axis(0), self.probs, probs]
        };
        self.samples += audio.len();
        self.partial.extend_from_slice(audio);
        let complete = self.partial.len() / FRAME_SAMPLES * FRAME_SAMPLES;
        self.energy.extend(frame_energy(&self.partial[..complete]));
        self.partial.drain(..complete);
        self.settle(false)
    }

    /// End of the recording: the pieces left.
    pub fn finish(&mut self) -> Vec<SpeakerSegment> {
        let partial = std::mem::take(&mut self.partial);
        self.energy.extend(frame_energy(&partial));
        self.settle(true)
    }

    fn settle(&mut self, at_end: bool) -> Vec<SpeakerSegment> {
        let frontier = self.probs.nrows();
        if frontier == 0 {
            return Vec::new();
        }
        let (max_gap, max_len) = (frames(self.params.max_gap), frames(self.params.max_len));
        let half = max_len / 2;
        let min_len = frames(self.params.min_len);
        let bridged = bridge(exclusive_runs(self.probs.view(), self.threshold), max_gap);
        // the last stretch can still grow, its speaker going on or back within max_gap: whether it
        // is too short is not known yet, keep it for now
        let unsure = bridged
            .last()
            .copied()
            .filter(|run| !at_end && run.end + max_gap > frontier && run.end - run.start < min_len);
        let runs: Vec<Run> = bridged
            .into_iter()
            .filter(|run| run.end - run.start >= min_len || Some(*run) == unsure)
            .collect();
        let silent: Vec<bool> = self
            .probs
            .rows()
            .into_iter()
            .map(|row| row.iter().all(|&p| p <= self.threshold))
            .collect();

        let mut settled: Vec<Run> = Vec::new();
        let mut closed_until = None;
        for run in bridge(runs.clone(), max_gap) {
            if at_end || run.end + max_gap <= frontier {
                // no later frame can bridge it: cut it as the whole recording would
                settled.extend(cut_long(vec![run], &self.energy, &silent, max_len));
                closed_until = Some(run.end);
                continue;
            }
            // the open turn: the cuts whose window is complete, whatever its end turns out to be.
            // It ends at least where its stretches sure to stay end
            let known_end = runs
                .iter()
                .filter(|r| r.start >= run.start && r.end <= run.end && Some(**r) != unsure)
                .map(|r| r.end)
                .max()
                .unwrap_or(run.start);
            let mut start = run.start;
            while known_end >= start + max_len + half {
                let cut = cut_point(&self.energy, &silent, start + half, start + max_len);
                settled.push(Run {
                    start,
                    end: cut,
                    speaker: run.speaker,
                });
                start = cut;
            }
            break; // a later turn ends later still
        }

        let duration = self.samples as f32 / (FRAME_SAMPLES * 100) as f32;
        let margin = self.params.margin;
        let (base, emitted_until) = (self.base, self.emitted_until);
        let fresh: Vec<Run> = settled
            .into_iter()
            .filter(|run| base + run.end > emitted_until)
            .collect();
        if let Some(last) = fresh.last() {
            self.emitted_until = base + last.end;
        }
        let pieces: Vec<SpeakerSegment> = fresh
            .into_iter()
            .map(|run| SpeakerSegment {
                start: ((base + run.start) as f32 / 100.0 - margin).max(0.0),
                end: ((base + run.end) as f32 / 100.0 + margin).min(duration),
                speaker_id: run.speaker,
            })
            .collect();
        // the frames before the last closed turn can go: no piece will start there any more
        if let Some(until) = closed_until {
            self.probs = self.probs.slice(s![until.., ..]).to_owned();
            self.energy.drain(..until.min(self.energy.len()));
            self.base += until;
        }
        pieces
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::{s, Array2};

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
    fn long_turns_are_cut_in_the_longest_pause_the_diarizer_heard() {
        // 50 s of one voice; the diarizer heard pauses at 12 s (0.2 s), 20 s (0.4 s), 26 s (0.1 s)
        let energy = vec![1.0f32; 5000];
        let mut silent = vec![false; 5000];
        for (from, len) in [(1200, 20), (2000, 40), (2600, 10)] {
            silent[from..from + len].fill(true);
        }
        // pieces of at most 30 s and at least 15 s: the pause at 12 s is too early, the one at
        // 20 s the longest of the other two; cut in its middle
        assert_eq!(
            cut_long(vec![run(0, 5000, 1)], &energy, &silent, 3000),
            vec![run(0, 2020, 1), run(2020, 5000, 1)]
        );
    }

    #[test]
    fn without_a_pause_long_turns_are_cut_at_their_quietest_point() {
        // 25 s of speech with quiet 100 ms at 3 s, 7 s, 16 s and 23 s; pieces of at most 10 s
        let mut energy = vec![1.0f32; 2500];
        for dip in [300, 700, 1600, 2300] {
            energy[dip - 5..dip + 5].fill(0.0);
        }
        // the dip at 3 s is too early (pieces of at least 5 s), the one at 23 s too late
        assert_eq!(
            cut_long(vec![run(0, 2500, 4)], &energy, &vec![false; 2500], 1000),
            vec![run(0, 700, 4), run(700, 1600, 4), run(1600, 2500, 4)]
        );
    }

    #[test]
    fn turns_within_the_maximum_are_left_whole() {
        let energy = vec![1.0f32; 1200];
        let runs = vec![run(0, 1000, 0), run(1000, 1100, 1)];
        assert_eq!(cut_long(runs.clone(), &energy, &vec![true; 1200], 1000), runs);
    }

    #[test]
    fn pieces_cut_a_long_turn_where_the_diarizer_heard_a_pause() {
        // 40 s of speaker 2 with a 0.3 s pause at 22 s, kept inside the turn (under max_gap);
        // the sound is flat, so only the diarizer can place the cut
        let mut probs = Array2::<f32>::zeros((4001, 8));
        talk(&mut probs, 2, 0, 2200, 0.9);
        talk(&mut probs, 2, 2230, 4000, 0.9);
        let audio = vec![0.1f32; 640_000];
        let pieces: Vec<(f32, f32, usize)> =
            transcription_pieces(probs.view(), &audio, 0.5, &PieceParams::default())
                .into_iter()
                .map(|p| (p.start, p.end, p.speaker_id))
                .collect();
        let close = |a: f32, b: f32| (a - b).abs() < 1e-4;
        let expected = [(0.0, 22.15, 2), (22.15, 40.0, 2)];
        assert_eq!(pieces.len(), expected.len(), "{pieces:?}");
        for (got, want) in pieces.iter().zip(expected) {
            assert!(
                close(got.0, want.0) && close(got.1, want.1) && got.2 == want.2,
                "{pieces:?}"
            );
        }
    }

    /// Two minutes of three speakers: a flicker to drop, a short pause to bridge, a silence, and a
    /// 63 s turn with three short pauses where it gets cut.
    fn meeting() -> (Array2<f32>, Vec<f32>) {
        let mut probs = Array2::<f32>::zeros((12_001, 8));
        talk(&mut probs, 0, 0, 1_000, 0.9);
        talk(&mut probs, 1, 400, 410, 0.95); // flicker
        talk(&mut probs, 0, 1_020, 1_400, 0.9); // after a 0.2 s pause
        talk(&mut probs, 2, 1_400, 2_000, 0.8);
        talk(&mut probs, 1, 2_200, 8_500, 0.9); // after 2 s of silence, 63 s long
        for pause in [4_000, 5_500, 7_000] {
            talk(&mut probs, 1, pause, pause + 30, 0.1);
        }
        talk(&mut probs, 0, 8_500, 9_000, 0.9);
        let audio: Vec<f32> = (0..12_000 * 160).map(|i| 0.1 * ((i % 97) as f32 / 97.0)).collect();
        (probs, audio)
    }

    #[test]
    fn pieces_streamed_are_the_whole_recording_ones() {
        let (probs, audio) = meeting();
        let whole = transcription_pieces(probs.view(), &audio, 0.5, &PieceParams::default());
        let mut stream = PieceStream::new(0.5, PieceParams::default());
        let mut streamed = Vec::new();
        let (mut frame, mut step) = (0, 0);
        // the probabilities lag the audio by a little, as Nemotron 3's look-ahead makes them
        while frame < probs.nrows() {
            let n = [7, 100, 333, 1, 1_201][step % 5].min(probs.nrows() - frame);
            let sound = &audio[(frame * 160).min(audio.len())..((frame + n) * 160).min(audio.len())];
            streamed.extend(stream.push(probs.slice(s![frame..frame + n, ..]), sound));
            frame += n;
            step += 1;
        }
        streamed.extend(stream.finish());
        let key = |p: &SpeakerSegment| (p.start, p.end, p.speaker_id);
        assert_eq!(
            streamed.iter().map(key).collect::<Vec<_>>(),
            whole.iter().map(key).collect::<Vec<_>>()
        );
        assert!(whole.len() >= 6, "{:?}", whole.iter().map(key).collect::<Vec<_>>());
    }

    /// Pieces of the whole recording, as (start, end, speaker).
    fn whole_pieces(probs: &Array2<f32>, audio: &[f32]) -> Vec<(f32, f32, usize)> {
        transcription_pieces(probs.view(), audio, 0.5, &PieceParams::default())
            .iter()
            .map(|p| (p.start, p.end, p.speaker_id))
            .collect()
    }

    /// Pieces of the recording pushed `steps` frames at a time (in turn), as (start, end, speaker).
    fn streamed_pieces(probs: &Array2<f32>, audio: &[f32], steps: &[usize]) -> Vec<(f32, f32, usize)> {
        let mut stream = PieceStream::new(0.5, PieceParams::default());
        let mut pieces = Vec::new();
        let mut frame = 0;
        for &step in steps.iter().cycle() {
            if frame >= probs.nrows() {
                break;
            }
            let end = (frame + step).min(probs.nrows());
            let sound = &audio[(frame * 160).min(audio.len())..(end * 160).min(audio.len())];
            pieces.extend(stream.push(probs.slice(s![frame..end, ..]), sound));
            frame = end;
        }
        pieces.extend(stream.finish());
        pieces.iter().map(|p| (p.start, p.end, p.speaker_id)).collect()
    }

    #[test]
    fn a_turn_that_has_just_started_again_is_not_dropped_as_too_short() {
        // speaker 0, a 0.25 s flicker of speaker 1, speaker 0 again 0.43 s after its end: the whole
        // recording bridges the two halves (the flicker goes, the gap is under 0.5 s)
        let mut probs = Array2::<f32>::zeros((2_101, 8));
        talk(&mut probs, 0, 0, 1_000, 0.9);
        talk(&mut probs, 1, 1_005, 1_030, 0.9);
        talk(&mut probs, 0, 1_043, 2_000, 0.9);
        let audio = vec![0.1f32; 2_100 * 160];
        let whole = whole_pieces(&probs, &audio);
        assert_eq!(whole.len(), 1, "{whole:?}");
        // pushed 7 frames at a time, the stream sees the second half when it is a few frames long
        assert_eq!(streamed_pieces(&probs, &audio, &[7]), whole);
    }

    #[test]
    fn a_short_stretch_a_later_one_can_still_join_is_not_dropped_yet() {
        // speaker 0, a flicker of speaker 1, 0.2 s of speaker 0, a 0.3 s silence, speaker 0 again:
        // the 0.2 s joins what follows, the flicker goes, the whole recording is one piece
        let mut probs = Array2::<f32>::zeros((1_601, 8));
        talk(&mut probs, 0, 0, 1_000, 0.9);
        talk(&mut probs, 1, 1_005, 1_015, 0.9);
        talk(&mut probs, 0, 1_020, 1_040, 0.9);
        talk(&mut probs, 0, 1_070, 1_500, 0.9);
        let audio = vec![0.1f32; 1_600 * 160];
        let whole = whole_pieces(&probs, &audio);
        assert_eq!(whole, vec![(0.0, 15.0, 0)]);
        // at 10.6 s the stream has the 0.2 s and the silence after it, not what comes next
        assert_eq!(streamed_pieces(&probs, &audio, &[10]), whole);
    }

    #[test]
    fn a_long_turn_that_has_just_stopped_is_cut_where_the_whole_recording_cuts_it() {
        // a 44.8 s turn: its first cut must leave 15 s after it, so it goes in the pause at 20 s,
        // not in the longer one at 29.9 s; the stream has heard 45 s when the turn may still resume
        let mut probs = Array2::<f32>::zeros((5_001, 8));
        talk(&mut probs, 0, 0, 4_480, 0.9);
        talk(&mut probs, 0, 2_000, 2_003, 0.1);
        talk(&mut probs, 0, 2_985, 2_995, 0.1);
        let audio = vec![0.1f32; 5_000 * 160];
        let whole = whole_pieces(&probs, &audio);
        assert_eq!(whole, vec![(0.0, 20.01, 0), (20.01, 44.8, 0)]);
        assert_eq!(streamed_pieces(&probs, &audio, &[10]), whole);
    }

    #[test]
    fn random_recordings_streamed_give_the_whole_recording_pieces() {
        // a linear congruential generator: the same recordings on every run
        let mut seed: u64 = 7;
        let mut next = move |n: usize| -> usize {
            seed = seed
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1_442_695_040_888_963_407);
            (seed >> 33) as usize % n
        };
        for recording in 0..300 {
            let len = 500 + next(4_500);
            let mut probs = Array2::<f32>::zeros((len, 8));
            let mut frame = 0;
            while frame < len {
                // a stretch of one of four speakers or of silence, from a flicker to a minute
                let stretch = [1 + next(29), 30 + next(40), 40 + next(500), 1_000 + next(5_000)];
                let end = (frame + stretch[next(4)]).min(len);
                let speaker = next(5);
                if speaker < 4 {
                    talk(&mut probs, speaker, frame, end, 0.51 + next(49) as f32 / 100.0);
                    if next(3) == 0 {
                        // someone else at the same time
                        let from = frame + next(end - frame);
                        let to = (from + 1 + next(200)).min(end);
                        talk(&mut probs, next(4), from, to, 0.51 + next(49) as f32 / 100.0);
                    }
                    for _ in 0..next(5) {
                        // a pause the diarizer heard
                        let from = frame + next(end - frame);
                        talk(&mut probs, speaker, from, (from + 1 + next(80)).min(end), 0.1);
                    }
                }
                frame = end;
            }
            let audio: Vec<f32> = (0..len * 160 - next(160))
                .map(|i| ((i / 160 * 7_919) % 101) as f32 / 1_000.0)
                .collect();
            let steps: Vec<usize> = (0..5)
                .map(|_| [1, 3, 7, 10, 49, 104, 333, 1_201][next(8)])
                .collect();
            assert_eq!(
                streamed_pieces(&probs, &audio, &steps),
                whole_pieces(&probs, &audio),
                "recording {recording}, steps {steps:?}"
            );
        }
    }

    #[test]
    fn a_piece_comes_out_once_nothing_can_change_it() {
        let (probs, audio) = meeting();
        let mut stream = PieceStream::new(0.5, PieceParams::default());
        // up to 14.4 s: the first turn of speaker 0 (0-14 s) can still be bridged until 14.5 s
        let early = stream.push(probs.slice(s![..1_440, ..]), &audio[..1_440 * 160]);
        assert!(early.is_empty(), "{early:?}");
        let later = stream.push(probs.slice(s![1_440..1_460, ..]), &audio[1_440 * 160..1_460 * 160]);
        assert_eq!(later.len(), 1, "{later:?}");
        assert_eq!((later[0].start, later[0].speaker_id), (0.0, 0));
    }

    #[test]
    fn pieces_last_up_to_thirty_seconds_by_default() {
        assert_eq!(PieceParams::default().max_len, 30.0);
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

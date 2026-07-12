use ndarray::Array2;

/// A single speaker turn with start/end times in seconds
#[derive(Debug, Clone, PartialEq)]
pub struct Segment {
    /// Start time in seconds
    pub start: f64,
    /// End time in seconds
    pub end: f64,
    /// Speaker label (e.g. "SPEAKER_00")
    pub speaker: String,
    /// Weakest assignment margin over the segment's frames (`+INF` when no
    /// confidence channel is available). Small values mark turns the audio did
    /// not clearly attribute; used only by confidence-aware absorption.
    pub confidence: f64,
}

impl Segment {
    /// Create a new segment with no confidence information (`+INF`).
    pub fn new(start: f64, end: f64, speaker: impl Into<String>) -> Self {
        Self {
            start,
            end,
            speaker: speaker.into(),
            confidence: f64::INFINITY,
        }
    }

    /// Create a new segment carrying an assignment-margin confidence.
    pub fn with_confidence(
        start: f64,
        end: f64,
        speaker: impl Into<String>,
        confidence: f64,
    ) -> Self {
        Self {
            start,
            end,
            speaker: speaker.into(),
            confidence,
        }
    }

    /// Duration in seconds
    pub fn duration(&self) -> f64 {
        self.end - self.start
    }
}

impl std::fmt::Display for Segment {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(
            f,
            "SPEAKER file 1 {:.3} {:.3} <NA> <NA> {} <NA> <NA>",
            self.start,
            self.duration(),
            self.speaker
        )
    }
}

/// Convert binary activation matrix to speaker segments (no confidence channel).
pub fn to_segments(
    activations: &Array2<f32>,
    frame_step: f64,
    frame_duration: f64,
) -> Vec<Segment> {
    let empty = Array2::<f32>::zeros((activations.nrows(), 0));
    to_segments_with_confidence(activations, &empty, frame_step, frame_duration)
}

/// Convert binary activations to segments, tagging each with the weakest
/// assignment margin over its frames.
///
/// `frame_confidence` is `(frames, clusters)` and column-aligned with
/// `activations`; a speaker column beyond its width (or a `+INF` entry) yields
/// `+INF` confidence, i.e. "never absorb on confidence".
pub fn to_segments_with_confidence(
    activations: &Array2<f32>,
    frame_confidence: &Array2<f32>,
    frame_step: f64,
    frame_duration: f64,
) -> Vec<Segment> {
    let (_num_frames, num_speakers) = activations.dim();
    let has_confidence = frame_confidence.ncols() > 0;
    let mut segments = Vec::new();

    for speaker_idx in 0..num_speakers {
        let label = format!("SPEAKER_{speaker_idx:02}");
        let column = activations.column(speaker_idx);

        if column.is_empty() {
            continue;
        }

        // Confidence at a frame for this speaker; +INF means "unknown".
        let conf_at = |frame_idx: usize| -> f64 {
            if has_confidence && speaker_idx < frame_confidence.ncols() {
                frame_confidence[[frame_idx, speaker_idx]] as f64
            } else {
                f64::INFINITY
            }
        };

        let mut start = frame_middle(0, frame_step, frame_duration);
        let mut is_active = column[0] > 0.5;
        let mut last_timestamp = start;
        let mut run_confidence = if is_active { conf_at(0) } else { f64::INFINITY };

        for (frame_idx, &value) in column.iter().enumerate().skip(1) {
            let timestamp = frame_middle(frame_idx, frame_step, frame_duration);
            last_timestamp = timestamp;

            if is_active {
                if value < 0.5 {
                    segments.push(Segment::with_confidence(
                        start,
                        timestamp,
                        &label,
                        run_confidence,
                    ));
                    start = timestamp;
                    is_active = false;
                } else {
                    run_confidence = run_confidence.min(conf_at(frame_idx));
                }
            } else if value > 0.5 {
                start = timestamp;
                is_active = true;
                run_confidence = conf_at(frame_idx);
            }
        }

        if is_active {
            segments.push(Segment::with_confidence(
                start,
                last_timestamp,
                &label,
                run_confidence,
            ));
        }
    }

    segments.sort_by(|a, b| a.start.total_cmp(&b.start));
    segments
}

fn frame_middle(frame_idx: usize, frame_step: f64, frame_duration: f64) -> f64 {
    frame_idx as f64 * frame_step + 0.5 * frame_duration
}

/// Merge consecutive same-speaker segments with gap smaller than max_gap
pub fn merge_segments(segments: &[Segment], max_gap: f64) -> Vec<Segment> {
    if segments.is_empty() {
        return Vec::new();
    }

    let mut merged: Vec<Segment> = vec![segments[0].clone()];

    for seg in &segments[1..] {
        // Edition-2021 port note: the upstream let-chain is split into a
        // nested condition (let-chains need edition 2024).
        if let Some(last) = merged.last_mut() {
            if seg.speaker == last.speaker && (seg.start - last.end) < max_gap {
                last.end = seg.end;
                last.confidence = last.confidence.min(seg.confidence);
                continue;
            }
        }

        merged.push(seg.clone());
    }

    merged
}

/// Absorb spurious speaker "islands" back into the surrounding talker.
///
/// The segmentation/clustering stage occasionally drops a short turn of one
/// speaker into the middle of a continuous stretch of another — either a plain
/// blip (a 0.5 s Speaker-0 island inside a Speaker-1 sentence on tightly-cut
/// audio) or a slightly longer turn whose short, noisy embedding was assigned
/// to the wrong talker with a razor-thin margin. An island is absorbed (the
/// bracketing speaker spans the gap) when it is cleanly bracketed by two
/// segments of the SAME other speaker (no time overlap) AND either:
///   * it is shorter than `min_duration` (duration-based, `0` disables), or
///   * its assignment `confidence` is below `confidence_margin`
///     (`0` disables) — this catches longer islands the audio never clearly
///     attributed, while a longer island with a crisp embedding (large margin)
///     is kept.
///
/// Islands at a real boundary (neighbours differ) or overlapping their
/// neighbours (genuine simultaneous speech) are left intact — no guess is made
/// where the timeline is ambiguous. Segments must be start-sorted (they are,
/// after `to_segments`).
pub fn enforce_min_turn(
    segments: &[Segment],
    min_duration: f64,
    confidence_margin: f64,
) -> Vec<Segment> {
    let confidence_enabled = confidence_margin > 0.0;
    if (min_duration <= 0.0 && !confidence_enabled) || segments.len() < 3 {
        return segments.to_vec();
    }
    let mut segs: Vec<Segment> = segments.to_vec();
    let mut i = 1;
    while i + 1 < segs.len() {
        let island = &segs[i];
        let prev = &segs[i - 1];
        let next = &segs[i + 1];
        let bracketed_same = prev.speaker == next.speaker && prev.speaker != island.speaker;
        // Clean bracket: island sits in the gap, overlapping neither neighbour
        // (a small epsilon tolerates float boundaries touching).
        let no_overlap = island.start >= prev.end - 1e-6 && next.start >= island.end - 1e-6;
        let too_short = island.duration() < min_duration;
        let low_confidence = confidence_enabled && island.confidence < confidence_margin;
        if (too_short || low_confidence) && bracketed_same && no_overlap {
            segs[i - 1].end = segs[i + 1].end; // prev speaker spans the island
            segs[i - 1].confidence = segs[i - 1].confidence.min(segs[i + 1].confidence);
            segs.drain(i..=i + 1); // remove island + merged-in next
            i = i.saturating_sub(1).max(1); // re-examine around the merge
        } else {
            i += 1;
        }
    }
    segs
}

/// Format segments as RTTM output
pub fn to_rttm(segments: &[Segment], file_id: &str) -> String {
    segments
        .iter()
        .map(|s| {
            format!(
                "SPEAKER {file_id} 1 {:.6} {:.6} <NA> <NA> {} <NA> <NA>\n",
                s.start,
                s.duration(),
                s.speaker
            )
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::array;

    #[test]
    fn single_segment_timing() {
        let activations = array![[0.0], [1.0], [1.0], [1.0], [0.0]];
        let segments = to_segments(&activations, 0.1, 0.2);

        assert_eq!(segments.len(), 1);
        assert_eq!(segments[0].speaker, "SPEAKER_00");
        assert!((segments[0].start - 0.2).abs() < 1e-9);
        assert!((segments[0].end - 0.5).abs() < 1e-9);
        assert!((segments[0].duration() - 0.3).abs() < 1e-9);
    }

    #[test]
    fn multi_speaker_sorted_by_start() {
        let activations = array![[0.0, 1.0], [0.0, 1.0], [1.0, 0.0], [1.0, 0.0],];
        let segments = to_segments(&activations, 0.1, 0.2);

        assert_eq!(segments.len(), 2);
        assert_eq!(segments[0].speaker, "SPEAKER_01");
        assert!((segments[0].start - 0.1).abs() < 1e-9);
        assert_eq!(segments[1].speaker, "SPEAKER_00");
        assert!((segments[1].start - 0.3).abs() < 1e-9);
    }

    #[test]
    fn merge_close_segments() {
        let segments = vec![
            Segment::new(0.0, 1.0, "SPEAKER_00"),
            Segment::new(1.05, 2.0, "SPEAKER_00"),
        ];
        let merged = merge_segments(&segments, 0.1);

        assert_eq!(merged.len(), 1);
        assert!((merged[0].end - 2.0).abs() < 1e-9);
    }

    #[test]
    fn no_merge_far_segments() {
        let segments = vec![
            Segment::new(0.0, 1.0, "SPEAKER_00"),
            Segment::new(2.0, 3.0, "SPEAKER_00"),
        ];
        let merged = merge_segments(&segments, 0.1);

        assert_eq!(merged.len(), 2);
    }

    #[test]
    fn rttm_format() {
        let segments = vec![Segment::new(1.5, 3.0, "SPEAKER_00")];
        let rttm = to_rttm(&segments, "meeting");

        assert_eq!(
            rttm,
            "SPEAKER meeting 1 1.500000 1.500000 <NA> <NA> SPEAKER_00 <NA> <NA>\n"
        );
    }

    #[test]
    fn empty_input() {
        let activations = Array2::<f32>::zeros((0, 0));
        let segments = to_segments(&activations, 0.1, 0.2);
        assert!(segments.is_empty());

        let merged = merge_segments(&[], 0.1);
        assert!(merged.is_empty());

        let rttm = to_rttm(&[], "file");
        assert!(rttm.is_empty());
    }

    #[test]
    fn all_zeros_no_segments() {
        let activations = array![[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]];
        let segments = to_segments(&activations, 0.1, 0.2);
        assert!(segments.is_empty());
    }

    #[test]
    fn display_trait_rttm_line() {
        let seg = Segment::new(1.0, 2.5, "SPEAKER_01");
        let display = format!("{seg}");
        assert_eq!(
            display,
            "SPEAKER file 1 1.000 1.500 <NA> <NA> SPEAKER_01 <NA> <NA>"
        );
    }

    #[test]
    fn min_turn_absorbs_short_island_between_same_speaker() {
        // 0.5 s Speaker 0 island inside a continuous Speaker 1 stretch.
        let segs = vec![
            Segment::new(0.0, 10.0, "SPEAKER_01"),
            Segment::new(10.0, 10.5, "SPEAKER_00"),
            Segment::new(10.5, 20.0, "SPEAKER_01"),
        ];
        let out = enforce_min_turn(&segs, 0.6, 0.0);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].speaker, "SPEAKER_01");
        assert_eq!(out[0].start, 0.0);
        assert_eq!(out[0].end, 20.0);
    }

    #[test]
    fn min_turn_keeps_island_at_a_real_boundary() {
        // Short segment with DIFFERENT neighbours = a real transition, kept.
        let segs = vec![
            Segment::new(0.0, 10.0, "SPEAKER_00"),
            Segment::new(10.0, 10.4, "SPEAKER_01"),
            Segment::new(10.4, 20.0, "SPEAKER_02"),
        ];
        let out = enforce_min_turn(&segs, 0.6, 0.0);
        assert_eq!(out.len(), 3);
    }

    #[test]
    fn min_turn_keeps_overlapping_island() {
        // Genuine simultaneous speech (island overlaps its neighbours) is kept.
        let segs = vec![
            Segment::new(0.0, 10.5, "SPEAKER_01"),
            Segment::new(10.0, 10.4, "SPEAKER_00"),
            Segment::new(10.2, 20.0, "SPEAKER_01"),
        ];
        let out = enforce_min_turn(&segs, 0.6, 0.0);
        assert_eq!(out.len(), 3);
    }

    #[test]
    fn min_turn_disabled_is_identity() {
        let segs = vec![
            Segment::new(0.0, 10.0, "SPEAKER_01"),
            Segment::new(10.0, 10.5, "SPEAKER_00"),
            Segment::new(10.5, 20.0, "SPEAKER_01"),
        ];
        assert_eq!(enforce_min_turn(&segs, 0.0, 0.0).len(), 3);
    }

    #[test]
    fn confidence_absorbs_low_margin_island_longer_than_min_duration() {
        // A 1.48 s island (longer than min_duration) with a razor-thin margin,
        // bracketed by the same speaker: the audio never picked it, absorb it.
        let segs = vec![
            Segment::with_confidence(0.0, 35.8, "SPEAKER_00", 0.4),
            Segment::with_confidence(35.8, 37.28, "SPEAKER_01", 0.02),
            Segment::with_confidence(37.28, 50.0, "SPEAKER_00", 0.4),
        ];
        // Duration filter alone (0.5 s) would NOT touch the 1.48 s island.
        let out = enforce_min_turn(&segs, 0.5, 0.1);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].speaker, "SPEAKER_00");
        assert_eq!(out[0].start, 0.0);
        assert_eq!(out[0].end, 50.0);
    }

    #[test]
    fn confidence_keeps_high_margin_island() {
        // Same geometry but a crisp margin: a real, confidently-attributed turn
        // is preserved even with confidence absorption enabled.
        let segs = vec![
            Segment::with_confidence(0.0, 35.8, "SPEAKER_00", 0.4),
            Segment::with_confidence(35.8, 37.28, "SPEAKER_01", 0.6),
            Segment::with_confidence(37.28, 50.0, "SPEAKER_00", 0.4),
        ];
        let out = enforce_min_turn(&segs, 0.5, 0.1);
        assert_eq!(out.len(), 3);
    }

    #[test]
    fn confidence_disabled_ignores_low_margin() {
        // margin threshold 0.0 = disabled: a low-confidence long island stays.
        let segs = vec![
            Segment::with_confidence(0.0, 35.8, "SPEAKER_00", 0.4),
            Segment::with_confidence(35.8, 37.28, "SPEAKER_01", 0.02),
            Segment::with_confidence(37.28, 50.0, "SPEAKER_00", 0.4),
        ];
        assert_eq!(enforce_min_turn(&segs, 0.5, 0.0).len(), 3);
    }

    #[test]
    fn confidence_never_absorbs_at_a_real_boundary() {
        // Low margin but DIFFERENT neighbours = a genuine transition, kept.
        let segs = vec![
            Segment::with_confidence(0.0, 35.8, "SPEAKER_00", 0.4),
            Segment::with_confidence(35.8, 37.28, "SPEAKER_01", 0.02),
            Segment::with_confidence(37.28, 50.0, "SPEAKER_02", 0.4),
        ];
        assert_eq!(enforce_min_turn(&segs, 0.5, 0.1).len(), 3);
    }

    #[test]
    fn to_segments_with_confidence_tags_weakest_frame() {
        // Speaker 0 active over 3 frames; frame confidences 0.9, 0.1, 0.8.
        // The segment inherits the weakest link (0.1).
        let activations = array![[1.0], [1.0], [1.0], [0.0]];
        let frame_confidence = array![[0.9f32], [0.1], [0.8], [f32::INFINITY]];
        let segments = to_segments_with_confidence(&activations, &frame_confidence, 0.1, 0.2);
        assert_eq!(segments.len(), 1);
        assert!((segments[0].confidence - 0.1).abs() < 1e-6);
    }
}

use crate::decoder::TimedToken;

/// Timestamp output mode for transcription results
///
/// Determines how token-level timestamps are grouped and presented:
/// - `Tokens`: Raw token-level output from the model (most detailed)
/// - `Words`: Tokens grouped into individual words
/// - `Sentences`: Tokens grouped by sentence boundaries (., ?, !)
///
/// # Model-Specific Recommendations
///
/// - **Parakeet CTC (English)**: Use `Words` mode. The CTC model only outputs lowercase
///   alphabet without punctuation, so sentence segmentation is not possible.
/// - **Parakeet TDT (Multilingual)**: Use `Sentences` mode. The TDT model predicts
///   punctuation, enabling natural sentence boundaries.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TimestampMode {
    /// Raw token-level timestamps from the model
    Tokens,
    /// Word-level timestamps (groups subword tokens)
    Words,
    /// Sentence-level timestamps (groups by punctuation)
    ///
    /// Note: Only works with models that predict punctuation (e.g., Parakeet TDT).
    /// CTC models don't predict punctuation, so use `Words` mode instead.
    Sentences,
}

impl Default for TimestampMode {
    fn default() -> Self {
        Self::Tokens
    }
}

/// Convert token timestamps to the requested output mode
///
/// Takes raw token-level timestamps from the model and optionally groups them
/// into words or sentences while preserving the original timing information.
///
/// # Arguments
///
/// * `tokens` - Raw token-level timestamps from model output
/// * `mode` - Desired grouping level (Tokens, Words, or Sentences)
///
/// # Returns
///
/// Vector of TimedToken with timestamps at the requested granularity
pub fn process_timestamps(tokens: &[TimedToken], mode: TimestampMode) -> Vec<TimedToken> {
    match mode {
        TimestampMode::Tokens => tokens.to_vec(),
        TimestampMode::Words => group_by_words(tokens),
        TimestampMode::Sentences => group_by_sentences(tokens),
    }
}

/// Absolute ceiling (in words) on the repeating block we try to collapse — a
/// perf bound only, mirroring the Whisper backend's MAX_REPEAT_BLOCK.
const MAX_REPEAT_BLOCK: usize = 32;

/// Collapse pathological consecutive repetition to a single occurrence while
/// leaving a legitimate single doubling ("nous nous", "très très") intact.
///
/// A block of 1..=MAX_REPEAT_BLOCK words repeated 3+ times in a row is reduced
/// to one copy; anything repeated only twice is kept. This mirrors the Whisper
/// backend's text-level `clean_repetitive_text` (src/whisper.rs) but operates
/// on timed word tokens so word/sentence timestamps stay consistent with the
/// rebuilt text. Comparison is case-insensitive (Parakeet-TDT capitalizes the
/// first word of a sentence). Pure function — no model state.
fn collapse_repeated_words(words: Vec<TimedToken>) -> Vec<TimedToken> {
    let n = words.len();
    if n == 0 {
        return words;
    }
    let lower: Vec<String> = words.iter().map(|w| w.text.to_lowercase()).collect();
    let mut out: Vec<TimedToken> = Vec::with_capacity(n);
    let mut i = 0;
    while i < n {
        // Find the block length k whose consecutive repetition (reps*k) covers
        // the most words, among blocks repeated 3+ times. Prefer the smallest k
        // on ties so "a a a a" collapses as one word, not the 2-word block.
        let max_k = MAX_REPEAT_BLOCK.min((n - i) / 3);
        let mut best_k = 0;
        let mut best_reps = 0;
        for k in 1..=max_k {
            let mut reps = 1;
            while i + (reps + 1) * k <= n && lower[i + reps * k..i + (reps + 1) * k] == lower[i..i + k] {
                reps += 1;
            }
            if reps >= 3 && reps * k > best_reps * best_k {
                best_k = k;
                best_reps = reps;
            }
        }
        if best_k > 0 {
            // Keep one copy of the block, skip all its repetitions.
            for w in words[i..i + best_k].iter() {
                out.push(w.clone());
            }
            i += best_reps * best_k;
        } else {
            out.push(words[i].clone());
            i += 1;
        }
    }
    out
}

// Group tokens into words based on word boundary markers
fn group_by_words(tokens: &[TimedToken]) -> Vec<TimedToken> {
    if tokens.is_empty() {
        return Vec::new();
    }

    let mut words = Vec::new();
    let mut current_word_text = String::new();
    let mut current_word_start = 0.0;

    for (i, token) in tokens.iter().enumerate() {
        // Space-only tokens (from SentencePiece ▁ word boundaries) act as word separators
        // but don't contribute text. Save current word if we hit one.
        if token.text.trim().is_empty() {
            if !current_word_text.is_empty() {
                words.push(TimedToken {
                    text: current_word_text.clone(),
                    start: current_word_start,
                    end: if i > 0 { tokens[i - 1].end } else { token.end },
                });
                current_word_text.clear();
            }
            continue;
        }

        // Check if this starts a new word (SentencePiece uses ▁ or space prefix)
        // Also treat PURE punctuation marks (like ".", ",") as separate words
        // But NOT contractions like "'re" or "'s" or hyphenations like "-two" (ex. twenty-two) which should attach to previous word
        let is_pure_punctuation =
            !token.text.is_empty() && token.text.chars().all(|c| c.is_ascii_punctuation());

        // Check if this is a contraction or hyphenation suffix
        // These should NOT start a new word - they attach to the previous word
        let token_without_marker = token.text.trim_start_matches('▁').trim_start_matches(' ');
        let is_contraction = token_without_marker.starts_with('\'');
        let is_hyphenation = token_without_marker.starts_with('-');

        let starts_word =
            (token.text.starts_with('▁') || token.text.starts_with(' ') || is_pure_punctuation)
                && !is_contraction
                && !is_hyphenation
                || i == 0;

        if starts_word && !current_word_text.is_empty() {
            words.push(TimedToken {
                text: current_word_text.clone(),
                start: current_word_start,
                end: tokens[i - 1].end,
            });
            current_word_text.clear();
        }

        // Start new word or append to current
        if current_word_text.is_empty() {
            current_word_start = token.start;
        }

        // Add token text, removing word boundary markers
        let token_text = token.text.trim_start_matches('▁').trim_start_matches(' ');
        current_word_text.push_str(token_text);
    }

    // Add final word
    if !current_word_text.is_empty() {
        words.push(TimedToken {
            text: current_word_text,
            start: current_word_start,
            end: tokens.last().unwrap().end,
        });
    }

    collapse_repeated_words(words)
}

// Unpunctuated-output guards (2026-07-21, SUMM-RE 004c_PAPH regression):
// Parakeet sometimes decodes minutes of audio with zero punctuation, and a
// grouping that only breaks on .?! then collapses a whole 180-s chunk into
// one segment. The chunked pipeline dedups by segment midpoint inside a
// half-overlap zone of 37.5 s, so segments MUST stay well below that or
// overlap text gets duplicated. Split at a clear pause once the sentence is
// already abnormally long, and cap the duration as a backstop. Healthy
// punctuated sentences end on .?! long before 10 s and are unaffected.
const SENTENCE_PAUSE_SPLIT_SECS: f32 = 1.5;
const SENTENCE_PAUSE_MIN_LEN_SECS: f32 = 10.0;
const SENTENCE_MAX_SECS: f32 = 30.0;

// Group words into sentences based on punctuation
fn group_by_sentences(tokens: &[TimedToken]) -> Vec<TimedToken> {
    // First get word-level grouping
    let words = group_by_words(tokens);
    if words.is_empty() {
        return Vec::new();
    }

    let mut sentences = Vec::new();
    let mut current_sentence: Vec<TimedToken> = Vec::new();

    for word in words {
        // Flush BEFORE adding the word when the model stopped punctuating:
        // at a clear pause once the run is already long, or at the hard cap.
        if let (Some(first), Some(last)) = (current_sentence.first(), current_sentence.last()) {
            let run_len = last.end - first.start;
            let pause = word.start - last.end;
            let split_on_pause =
                pause >= SENTENCE_PAUSE_SPLIT_SECS && run_len >= SENTENCE_PAUSE_MIN_LEN_SECS;
            let split_on_cap = word.end - first.start > SENTENCE_MAX_SECS;
            if split_on_pause || split_on_cap {
                let sentence_text = format_sentence(&current_sentence);
                if !sentence_text.is_empty() {
                    sentences.push(TimedToken {
                        text: sentence_text,
                        start: first.start,
                        end: last.end,
                    });
                }
                current_sentence.clear();
            }
        }

        current_sentence.push(word.clone());

        // Check if word ends with sentence terminator
        let ends_sentence =
            word.text.contains('.') || word.text.contains('?') || word.text.contains('!');

        if ends_sentence {
            let sentence_text = format_sentence(&current_sentence);
            let start = current_sentence.first().unwrap().start;
            let end = current_sentence.last().unwrap().end;

            if !sentence_text.is_empty() {
                sentences.push(TimedToken {
                    text: sentence_text,
                    start,
                    end,
                });
            }
            current_sentence.clear();
        }
    }

    // Add final sentence if exists
    if !current_sentence.is_empty() {
        let sentence_text = format_sentence(&current_sentence);
        let start = current_sentence.first().unwrap().start;
        let end = current_sentence.last().unwrap().end;

        if !sentence_text.is_empty() {
            sentences.push(TimedToken {
                text: sentence_text,
                start,
                end,
            });
        }
    }

    sentences
}

// Join words with punctuation spacing
fn format_sentence(words: &[TimedToken]) -> String {
    let result: Vec<&str> = words.iter().map(|w| w.text.as_str()).collect();

    // Join words, but don't add space before certain punctuation
    let mut output = String::new();
    for (i, word) in result.iter().enumerate() {
        // Check if this word is standalone punctuation that shouldn't have space before it
        // Contractions like "'re" or "'s" should have spaces before them
        let is_standalone_punct = word.len() == 1
            && word
                .chars()
                .all(|c| matches!(c, '.' | ',' | '!' | '?' | ';' | ':' | ')'));

        if i > 0 && !is_standalone_punct {
            output.push(' ');
        }
        output.push_str(word);
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_word_grouping() {
        let tokens = vec![
            TimedToken {
                text: "▁Hello".to_string(),
                start: 0.0,
                end: 0.5,
            },
            TimedToken {
                text: "▁world".to_string(),
                start: 0.5,
                end: 1.0,
            },
        ];

        let words = group_by_words(&tokens);
        assert_eq!(words.len(), 2);
        assert_eq!(words[0].text, "Hello");
        assert_eq!(words[1].text, "world");
    }

    #[test]
    fn test_word_grouping_with_hyphenated_word() {
        let tokens = vec![
            TimedToken {
                text: "▁twenty".to_string(),
                start: 0.0,
                end: 0.3,
            },
            TimedToken {
                text: "-two".to_string(),
                start: 0.3,
                end: 0.6,
            },
            TimedToken {
                text: "▁apples".to_string(),
                start: 0.6,
                end: 1.0,
            },
        ];

        let words = group_by_words(&tokens);
        assert_eq!(words.len(), 2);
        assert_eq!(words[0].text, "twenty-two");
        assert_eq!(words[1].text, "apples");
        assert_eq!(words[0].start, 0.0);
        assert_eq!(words[0].end, 0.6);
        assert_eq!(words[1].start, 0.6);
        assert_eq!(words[1].end, 1.0);
    }

    // Regression: 2026-07-21, SUMM-RE meeting 004c_PAPH. Parakeet decoded
    // three whole 180-s chunks with ZERO punctuation (not even commas);
    // group_by_sentences only breaks on .?! so each chunk collapsed into a
    // single 179-s "sentence". Downstream, the chunked pipeline's midpoint
    // dedup kept those blobs whole, duplicating the overlap zones and
    // corrupting 7.5 of the meeting's 21 minutes. Unpunctuated output must
    // still yield bounded segments, split at natural pauses.
    #[test]
    fn test_unpunctuated_sentence_splits_on_pause() {
        // 20+ s of speech, no punctuation at all, with a 2-s silence after
        // an 11.9-s run: expect a split at the pause, not one blob.
        let mut tokens = Vec::new();
        for i in 0..20 {
            let start = if i < 12 { i as f32 } else { i as f32 + 2.0 };
            tokens.push(TimedToken {
                text: format!("▁mot{}", i),
                start,
                end: start + 0.9,
            });
        }
        let sentences = group_by_sentences(&tokens);
        assert_eq!(
            sentences.len(),
            2,
            "a >=1.5-s pause in a long unpunctuated run must split: {:?}",
            sentences.iter().map(|s| (s.start, s.end)).collect::<Vec<_>>()
        );
        assert!(sentences[0].end < 12.0 && sentences[1].start > 11.0);
    }

    #[test]
    fn test_unpunctuated_sentence_duration_is_capped() {
        // 180 s of continuous unpunctuated speech (no pause anywhere):
        // the duration backstop must still bound every segment, otherwise
        // the chunked pipeline's dedup (half-overlap zone = 37.5 s) breaks.
        let tokens: Vec<TimedToken> = (0..360)
            .map(|i| TimedToken {
                text: format!("▁mot{}", i),
                start: i as f32 * 0.5,
                end: i as f32 * 0.5 + 0.5,
            })
            .collect();
        let sentences = group_by_sentences(&tokens);
        assert!(
            sentences.len() > 1,
            "180 s of unpunctuated speech must not be one sentence"
        );
        for s in &sentences {
            assert!(
                s.end - s.start <= 30.5,
                "sentence {:.1}-{:.1} exceeds the 30-s cap",
                s.start,
                s.end
            );
        }
    }

    #[test]
    fn test_punctuated_sentences_unaffected_by_split_rules() {
        // Healthy output: short punctuated sentences with small gaps must
        // group exactly as before the pause/cap rules.
        let mut tokens = Vec::new();
        for i in 0..3 {
            let base = i as f32 * 3.0;
            tokens.push(TimedToken {
                text: format!("▁Phrase{}", i),
                start: base,
                end: base + 1.0,
            });
            tokens.push(TimedToken {
                text: "▁courte".to_string(),
                start: base + 1.0,
                end: base + 2.0,
            });
            tokens.push(TimedToken {
                text: ".".to_string(),
                start: base + 2.0,
                end: base + 2.1,
            });
        }
        let sentences = group_by_sentences(&tokens);
        assert_eq!(sentences.len(), 3);
        assert_eq!(sentences[0].text, "Phrase0 courte.");
    }

    #[test]
    fn test_sentence_grouping() {
        let tokens = vec![
            TimedToken {
                text: "▁Hello".to_string(),
                start: 0.0,
                end: 0.5,
            },
            TimedToken {
                text: "▁world".to_string(),
                start: 0.5,
                end: 1.0,
            },
            TimedToken {
                text: ".".to_string(),
                start: 1.0,
                end: 1.1,
            },
        ];

        let sentences = group_by_sentences(&tokens);
        assert_eq!(sentences.len(), 1);
        assert_eq!(sentences[0].text, "Hello world.");
        assert_eq!(sentences[0].start, 0.0);
        assert_eq!(sentences[0].end, 1.1);
    }

    #[test]
    fn test_repetition_preservation() {
        let words = vec![
            TimedToken {
                text: "uh".to_string(),
                start: 0.0,
                end: 0.5,
            },
            TimedToken {
                text: "uh".to_string(),
                start: 0.5,
                end: 1.0,
            },
            TimedToken {
                text: "hello".to_string(),
                start: 1.0,
                end: 1.5,
            },
        ];

        let result = format_sentence(&words);
        assert_eq!(result, "uh uh hello");
    }

    #[test]
    fn test_space_token_separates_words_from_digits() {
        // Simulates "like 100" tokenized as [" like", " ", "1", "0", "0"]
        // The space-only token should act as word boundary
        let tokens = vec![
            TimedToken {
                text: " like".to_string(),
                start: 0.0,
                end: 0.5,
            },
            TimedToken {
                text: " ".to_string(), // Space-only token from ▁
                start: 0.5,
                end: 0.5,
            },
            TimedToken {
                text: "1".to_string(),
                start: 0.5,
                end: 0.6,
            },
            TimedToken {
                text: "0".to_string(),
                start: 0.6,
                end: 0.7,
            },
            TimedToken {
                text: "0".to_string(),
                start: 0.7,
                end: 0.8,
            },
        ];

        let words = group_by_words(&tokens);
        assert_eq!(words.len(), 2);
        assert_eq!(words[0].text, "like");
        assert_eq!(words[1].text, "100");

        // Also test sentence formatting
        let sentence = format_sentence(&words);
        assert_eq!(sentence, "like 100");
    }

    // Regression: group_by_words dropped the second of ANY immediate
    // duplicate word (case-insensitive), so real dictation like the French
    // "nous nous sommes" or "très très bien" silently lost a word. A single
    // doubling is legitimate emphasis and must survive; only pathological
    // 3+ repeats (model stutter) are collapsed — mirroring the Whisper
    // backend's clean_repetitive_text policy (src/whisper.rs).
    #[test]
    fn test_word_grouping_preserves_legitimate_doubling() {
        let tokens = vec![
            TimedToken { text: "▁Nous".to_string(), start: 0.0, end: 0.4 },
            TimedToken { text: "▁nous".to_string(), start: 0.4, end: 0.8 },
            TimedToken { text: "▁sommes".to_string(), start: 0.8, end: 1.2 },
        ];
        let words = group_by_words(&tokens);
        assert_eq!(
            words.iter().map(|w| w.text.as_str()).collect::<Vec<_>>(),
            vec!["Nous", "nous", "sommes"]
        );
    }

    #[test]
    fn test_word_grouping_collapses_pathological_repeats() {
        // 3+ identical consecutive words (model stutter loop) must still
        // collapse to a single occurrence — the legitimate reason the old
        // dedup existed. Timestamps of the kept copy are preserved.
        let tokens = vec![
            TimedToken { text: "▁le".to_string(), start: 0.0, end: 0.3 },
            TimedToken { text: "▁le".to_string(), start: 0.3, end: 0.6 },
            TimedToken { text: "▁le".to_string(), start: 0.6, end: 0.9 },
            TimedToken { text: "▁le".to_string(), start: 0.9, end: 1.2 },
            TimedToken { text: "▁chat".to_string(), start: 1.2, end: 1.6 },
        ];
        let words = group_by_words(&tokens);
        assert_eq!(
            words.iter().map(|w| w.text.as_str()).collect::<Vec<_>>(),
            vec!["le", "chat"]
        );
        assert_eq!(words[0].start, 0.0);
    }

    #[test]
    fn test_sentence_grouping_preserves_doubling() {
        let tokens = vec![
            TimedToken { text: "▁très".to_string(), start: 0.0, end: 0.3 },
            TimedToken { text: "▁très".to_string(), start: 0.3, end: 0.6 },
            TimedToken { text: "▁bien".to_string(), start: 0.6, end: 0.9 },
            TimedToken { text: ".".to_string(), start: 0.9, end: 1.0 },
        ];
        let sentences = group_by_sentences(&tokens);
        assert_eq!(sentences.len(), 1);
        assert_eq!(sentences[0].text, "très très bien.");
    }
}

use std::collections::HashMap;

use crate::decoder::{TimedToken, TranscriptionResult};
use crate::vocab::Vocabulary;

/// Token decoder for Canary AED models.
///
/// Decodes Canary token IDs into text, filtering out special tokens
/// (`<|...|>`, `<unk>`, `<pad>`) and replacing SentencePiece `▁` (U+2581)
/// with regular spaces.
#[derive(Debug)]
pub struct CanaryDecoder {
    vocab: HashMap<usize, String>,
}

impl CanaryDecoder {
    /// Build a CanaryDecoder from a [`Vocabulary`] loaded from vocab.txt.
    ///
    /// The `▁` character is replaced with a space during construction so that
    /// decoded text is ready to use.
    pub fn from_vocabulary(vocab: &Vocabulary) -> Self {
        let mut map = HashMap::new();
        for id in 0..vocab.size() {
            if let Some(token) = vocab.id_to_text(id) {
                if !token.is_empty() {
                    map.insert(id, token.replace('▁', " "));
                }
            }
        }
        Self { vocab: map }
    }

    /// Build a CanaryDecoder from a pre-built HashMap (useful for tests).
    ///
    /// The `▁` character is replaced with a space, same as [`from_vocabulary`].
    pub fn from_vocab_map(vocab: HashMap<usize, String>) -> Self {
        let vocab = vocab
            .into_iter()
            .map(|(id, tok)| (id, tok.replace('▁', " ")))
            .collect();
        Self { vocab }
    }

    /// Returns `true` if the token should be filtered out during decoding.
    fn is_special_token(text: &str) -> bool {
        // Filter <|...|> control tokens
        if text.starts_with("<|") && text.ends_with("|>") {
            return true;
        }
        // Filter <unk> (id 0) and <pad> (id 2)
        if text == "<unk>" || text == "<pad>" {
            return true;
        }
        false
    }

    /// Look up raw vocab text for a token ID (including special tokens).
    pub fn vocab_lookup(&self, id: usize) -> Option<&str> {
        self.vocab.get(&id).map(|s| s.as_str())
    }

    /// Decode a slice of token IDs into a string, filtering special tokens.
    pub fn decode(&self, token_ids: &[i64]) -> String {
        let mut result = String::new();
        for &id in token_ids {
            if let Some(text) = self.vocab.get(&(id as usize)) {
                if !Self::is_special_token(text) {
                    result.push_str(text);
                }
            }
        }
        // Trim leading/trailing whitespace produced by SentencePiece spaces
        result.trim().to_string()
    }

    /// Decode token IDs with estimated timestamps.
    ///
    /// Since Canary AED does not produce frame-level alignments the way CTC or
    /// TDT models do, timestamps are estimated by distributing the total audio
    /// duration proportionally across non-special tokens.
    pub fn decode_with_timestamps(
        &self,
        token_ids: &[i64],
        _logprobs: &[f32],
        _encoder_frames: usize,
        audio_duration_s: f32,
    ) -> TranscriptionResult {
        // Collect non-special tokens with their texts
        let mut texts: Vec<String> = Vec::new();
        for &id in token_ids {
            if let Some(text) = self.vocab.get(&(id as usize)) {
                if !Self::is_special_token(text) {
                    texts.push(text.clone());
                }
            }
        }

        let n = texts.len();
        if n == 0 {
            return TranscriptionResult {
                text: String::new(),
                tokens: Vec::new(),
            };
        }

        // Distribute duration proportionally across tokens
        let duration_per_token = audio_duration_s / n as f32;
        let mut timed_tokens = Vec::with_capacity(n);
        let mut full_text = String::new();

        for (i, text) in texts.iter().enumerate() {
            let start = i as f32 * duration_per_token;
            let end = (i + 1) as f32 * duration_per_token;
            full_text.push_str(text);
            timed_tokens.push(TimedToken {
                text: text.clone(),
                start,
                end,
            });
        }

        TranscriptionResult {
            text: full_text.trim().to_string(),
            tokens: timed_tokens,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: build a vocab HashMap from (id, token) pairs.
    fn make_vocab(entries: &[(usize, &str)]) -> HashMap<usize, String> {
        entries.iter().map(|(id, tok)| (*id, tok.to_string())).collect()
    }

    #[test]
    fn test_decode_basic() {
        // Simulate tokens for "Bonjour le monde."
        // SentencePiece: ▁Bonjour ▁le ▁monde .
        let vocab = make_vocab(&[
            (100, "▁Bonjour"),
            (101, "▁le"),
            (102, "▁monde"),
            (103, "."),
        ]);
        let decoder = CanaryDecoder::from_vocab_map(vocab);
        let result = decoder.decode(&[100, 101, 102, 103]);
        assert_eq!(result, "Bonjour le monde.");
    }

    #[test]
    fn test_decode_filters_special_tokens() {
        // Mix control tokens with normal text
        let vocab = make_vocab(&[
            (0, "<unk>"),
            (2, "<pad>"),
            (10, "<|startoftranscript|>"),
            (11, "<|fr|>"),
            (12, "<|pnc|>"),
            (13, "<|startofcontext|>"),
            (100, "▁Bonjour"),
            (101, "▁le"),
            (102, "▁monde"),
            (103, "."),
            (200, "<|endoftext|>"),
        ]);
        let decoder = CanaryDecoder::from_vocab_map(vocab);
        let result = decoder.decode(&[0, 2, 10, 11, 12, 13, 100, 101, 102, 103, 200]);
        assert_eq!(result, "Bonjour le monde.");
    }

    #[test]
    fn test_decode_empty() {
        let vocab = make_vocab(&[]);
        let decoder = CanaryDecoder::from_vocab_map(vocab);
        let result = decoder.decode(&[]);
        assert_eq!(result, "");
    }

    #[test]
    fn test_decode_with_timestamps() {
        let vocab = make_vocab(&[
            (10, "<|startoftranscript|>"),
            (100, "▁Bonjour"),
            (101, "▁le"),
            (102, "▁monde"),
            (103, "."),
            (200, "<|endoftext|>"),
        ]);
        let decoder = CanaryDecoder::from_vocab_map(vocab);

        let token_ids: Vec<i64> = vec![10, 100, 101, 102, 103, 200];
        let logprobs = vec![0.0f32; 6];
        let result = decoder.decode_with_timestamps(&token_ids, &logprobs, 256, 4.0);

        // Only 4 non-special tokens → 1.0s each
        assert_eq!(result.text, "Bonjour le monde.");
        assert_eq!(result.tokens.len(), 4);

        // Check proportional timestamps
        assert!((result.tokens[0].start - 0.0).abs() < 1e-6);
        assert!((result.tokens[0].end - 1.0).abs() < 1e-6);
        assert!((result.tokens[1].start - 1.0).abs() < 1e-6);
        assert!((result.tokens[1].end - 2.0).abs() < 1e-6);
        assert!((result.tokens[3].start - 3.0).abs() < 1e-6);
        assert!((result.tokens[3].end - 4.0).abs() < 1e-6);
    }
}

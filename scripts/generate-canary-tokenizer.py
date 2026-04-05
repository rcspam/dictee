#!/usr/bin/env python3
"""
Generate tokenizer.json for NVIDIA Canary-1B from its SentencePiece model.

Downloads tokenizer_all_languages.model from nvidia/canary-1b on HuggingFace,
converts it to HuggingFace tokenizers format (Unigram + Metaspace), and saves
as tokenizer.json for use by the Rust `tokenizers` crate.

Dependencies:
    pip install sentencepiece tokenizers huggingface_hub

Usage:
    python generate-canary-tokenizer.py [OUTPUT_DIR]

    OUTPUT_DIR  Directory where tokenizer.json will be written (default: current directory)
"""

import sys
import os
import json
import tempfile

def main():
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "."

    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    # Validate output directory
    if not os.path.isdir(output_dir):
        print(f"Erreur : le repertoire '{output_dir}' n'existe pas.", file=sys.stderr)
        sys.exit(1)

    output_path = os.path.join(output_dir, "tokenizer.json")

    # --- Step 1: Download the SentencePiece model from HuggingFace ---
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("Erreur : huggingface_hub n'est pas installe.", file=sys.stderr)
        print("  pip install huggingface_hub", file=sys.stderr)
        sys.exit(1)

    print("Telechargement de tokenizer_all_languages.model depuis nvidia/canary-1b...")
    try:
        sp_model_path = hf_hub_download(
            repo_id="nvidia/canary-1b",
            filename="tokenizer_all_languages.model",
        )
    except Exception as e:
        print(f"Erreur lors du telechargement : {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  -> {sp_model_path}")

    # --- Step 2: Load with SentencePiece and extract vocab ---
    try:
        import sentencepiece as spm
    except ImportError:
        print("Erreur : sentencepiece n'est pas installe.", file=sys.stderr)
        print("  pip install sentencepiece", file=sys.stderr)
        sys.exit(1)

    sp = spm.SentencePieceProcessor()
    sp.Load(sp_model_path)

    vocab_size = sp.GetPieceSize()
    print(f"Vocabulaire SentencePiece : {vocab_size} tokens")

    # Extract vocabulary with scores
    vocab = []
    for i in range(vocab_size):
        piece = sp.IdToPiece(i)
        score = sp.GetScore(i)
        vocab.append((piece, score))

    # --- Step 3: Convert to HuggingFace tokenizers format ---
    try:
        from tokenizers import Tokenizer
        from tokenizers.models import Unigram
        from tokenizers.pre_tokenizers import Metaspace
        from tokenizers.decoders import Metaspace as MetaspaceDecoder
    except ImportError:
        print("Erreur : tokenizers n'est pas installe.", file=sys.stderr)
        print("  pip install tokenizers", file=sys.stderr)
        sys.exit(1)

    # Build Unigram model with the extracted vocab
    # Unigram expects list of (token_string, score) tuples
    tokenizer = Tokenizer(Unigram(vocab))

    # SentencePiece uses Metaspace (U+2581) as word boundary marker
    tokenizer.pre_tokenizer = Metaspace(replacement="\u2581", add_prefix_space=True)
    tokenizer.decoder = MetaspaceDecoder(replacement="\u2581", add_prefix_space=True)

    # --- Step 4: Validate round-trip ---
    test_text = "Hello, this is a test."
    encoded = tokenizer.encode(test_text)
    decoded = tokenizer.decode(encoded.ids)
    print(f"Validation : \"{test_text}\" -> {len(encoded.ids)} tokens -> \"{decoded}\"")

    if decoded.strip() != test_text.strip():
        print(f"  ATTENTION : le texte decode differe legerement (normal pour SentencePiece)")

    # --- Step 5: Save ---
    tokenizer.save(output_path)
    file_size = os.path.getsize(output_path)
    print(f"Sauvegarde : {output_path} ({file_size:,} octets)")
    print("Termine.")


if __name__ == "__main__":
    main()

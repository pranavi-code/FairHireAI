"""Download and validate the exact BERT base used by FI training."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, BertModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--source", default="google-bert/bert-base-uncased")
    args = parser.parse_args()
    output = Path(args.output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(args.source, use_fast=True)
    model = BertModel.from_pretrained(args.source)
    tokenizer.save_pretrained(output)
    model.save_pretrained(output, safe_serialization=True)

    local_tokenizer = AutoTokenizer.from_pretrained(output, use_fast=True, local_files_only=True)
    local_model = BertModel.from_pretrained(output, local_files_only=True)
    encoded = local_tokenizer("local BERT validation", return_tensors="pt")
    with torch.no_grad():
        shape = list(local_model(**encoded).last_hidden_state.shape)
    summary = {
        "source": args.source,
        "output_root": str(output),
        "vocabulary_size": local_tokenizer.vocab_size,
        "hidden_size": local_model.config.hidden_size,
        "layers": local_model.config.num_hidden_layers,
        "validation_shape": shape,
    }
    (output / "roleready_cache_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print("BERT CACHE PASSED")


if __name__ == "__main__":
    main()

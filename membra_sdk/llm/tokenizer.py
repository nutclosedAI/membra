"""MEMBRA Byte-Level Tokenizer — Simple, handles all text, no training required.

Unlike BPE which needs a training corpus, byte-level tokenization:
- vocab = 256 (all byte values)
- Every string is valid
- No out-of-vocabulary tokens
- Simple encode/decode

This is the tokenizer used by GPT-2 before BPE merge rules are applied.
For small models and terminal use, it's fast, correct, and zero-dependency.
"""
import json
from typing import List


class ByteTokenizer:
    """Byte-level tokenizer: encode/decode via UTF-8 bytes."""

    def __init__(self):
        self.vocab_size = 256
        self.bos_token = 256  # sentinel, not in vocab
        self.eos_token = 257  # sentinel, not in vocab

    def encode(self, text: str) -> List[int]:
        """Encode string to list of byte values."""
        return list(text.encode("utf-8"))

    def decode(self, tokens: List[int]) -> str:
        """Decode list of byte values to string."""
        # Filter valid byte values
        bytes_data = bytes(t for t in tokens if 0 <= t < 256)
        return bytes_data.decode("utf-8", errors="replace")

    def encode_with_bos(self, text: str) -> List[int]:
        """Encode with beginning-of-sequence marker."""
        return [self.bos_token] + self.encode(text)

    def encode_with_eos(self, text: str) -> List[int]:
        """Encode with end-of-sequence marker."""
        return self.encode(text) + [self.eos_token]

    def encode_full(self, text: str) -> List[int]:
        """Encode with both BOS and EOS markers."""
        return [self.bos_token] + self.encode(text) + [self.eos_token]

    def __len__(self) -> int:
        return self.vocab_size

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump({"type": "byte", "vocab_size": self.vocab_size}, f)

    @classmethod
    def load(cls, path: str) -> "ByteTokenizer":
        with open(path) as f:
            data = json.load(f)
        assert data.get("type") == "byte"
        return cls()

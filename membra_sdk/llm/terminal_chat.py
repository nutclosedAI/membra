"""MEMBRA Terminal Chat — Streaming, keyboard-native LLM interface.

No browser. No Gradio. Pure terminal with:
- Real-time token streaming
- Keyboard shortcuts (Ctrl+C interrupt, Ctrl+D exit)
- Command mode (/validate, /vote, /job, /status)
- Rich text rendering with markdown support
- Conversation history
- Model stats display
"""
import os
import sys
import time
from typing import List, Optional

import torch

from .gpt import GPTConfig, LLMGPT
from .tokenizer import ByteTokenizer


def get_device() -> str:
    """Best available device: CUDA > MPS (Apple Silicon) > CPU."""
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class TerminalChat:
    """Terminal-native chat interface for LLMGPT."""

    def __init__(
        self,
        model: Optional[LLMGPT] = None,
        tokenizer: Optional[ByteTokenizer] = None,
        config: Optional[GPTConfig] = None,
        device: Optional[str] = None,
        max_new_tokens: int = 512,
        temperature: float = 0.8,
        top_k: int = 40,
    ):
        self.device = device or get_device()
        self.tokenizer = tokenizer or ByteTokenizer()
        self.config = config or GPTConfig()

        if model is None:
            print(f"Initializing LLMGPT ({self.config.param_count:,} params) on {self.device}...")
            self.model = LLMGPT(self.config).to(self.device)
            print(f"Model ready. {self.model.count_parameters():,} parameters.")
        else:
            self.model = model.to(self.device)

        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_k = top_k
        self.history: List[str] = []
        self.system_prompt = (
            "You are MEMBRA, a terminal-native AI validator. "
            "You evaluate code, tests, and artifacts. "
            "You vote on job quality. You are honest, precise, and concise.\n\n"
        )

    def _print_banner(self):
        print("=" * 60)
        print("  MEMBRA LLMGPT — Terminal-Native AI Validator")
        print(f"  Model: {self.config.n_layer}L/{self.config.n_head}H/{self.config.n_embd}D")
        print(f"  Params: {self.model.count_parameters():,}")
        print(f"  Device: {self.model.device_info()}")
        print("=" * 60)
        print("Commands: /validate <job_id>  /vote <job_id>  /status  /quit")
        print("         /help for more")
        print()

    def _build_prompt(self, user_input: str) -> str:
        """Build full prompt from history + system prompt."""
        prompt = self.system_prompt
        for i, msg in enumerate(self.history[-6:]):  # keep last 6 exchanges
            role = "User" if i % 2 == 0 else "MEMBRA"
            prompt += f"{role}: {msg}\n"
        prompt += f"User: {user_input}\nMEMBRA:"
        return prompt

    def _stream_response(self, prompt: str):
        """Stream tokens to terminal with real-time output."""
        tokens = self.tokenizer.encode(prompt)
        idx = torch.tensor([tokens], dtype=torch.long, device=self.device)

        response_tokens = []
        start = time.time()

        try:
            for tok in self.model.generate_streaming(
                idx,
                max_new_tokens=self.max_new_tokens,
                temperature=self.temperature,
                top_k=self.top_k,
                stop_tokens=[self.tokenizer.eos_token, ord("\nUser:")],
            ):
                response_tokens.append(tok)
                char = self.tokenizer.decode([tok])
                print(char, end="", flush=True)
        except KeyboardInterrupt:
            print("\n[interrupted]")

        elapsed = time.time() - start
        print()  # newline
        return self.tokenizer.decode(response_tokens), elapsed

    def _handle_command(self, cmd: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        parts = cmd.strip().split()
        if not parts:
            return False

        action = parts[0].lower()

        if action == "/quit" or action == "/q":
            print("Goodbye.")
            sys.exit(0)

        elif action == "/help" or action == "/h":
            print("Commands:")
            print("  /validate <job_id>    — Evaluate job artifacts as validator")
            print("  /vote <job_id>        — Submit validator vote for job")
            print("  /status               — Show model status")
            print("  /clear                — Clear conversation history")
            print("  /save <path>          — Save conversation to file")
            print("  /quit                 — Exit")

        elif action == "/status":
            print(f"Model: {self.config.n_layer}L/{self.config.n_head}H/{self.config.n_embd}D")
            print(f"Params: {self.model.count_parameters():,}")
            print(f"Device: {self.model.device_info()}")
            print(f"History: {len(self.history)} messages")

        elif action == "/clear":
            self.history = []
            print("History cleared.")

        elif action == "/save":
            path = parts[1] if len(parts) > 1 else "membra_chat.txt"
            with open(path, "w") as f:
                for msg in self.history:
                    f.write(msg + "\n")
            print(f"Saved to {path}")

        elif action == "/validate":
            job_id = parts[1] if len(parts) > 1 else "latest"
            print(f"[Validator mode: evaluating job {job_id}...]")
            print("  (Connect to Solana program for real validation)")
            # Placeholder: in real usage, load artifacts and evaluate
            print("  → ACCEPT (score: 87) — clean code, tests pass, no security flags")

        elif action == "/vote":
            job_id = parts[1] if len(parts) > 1 else "latest"
            print(f"[Submitting validator vote for job {job_id}...]")
            print("  (Requires Solana wallet and devnet connection)")

        else:
            print(f"Unknown command: {action}. Type /help for list.")

        return True

    def run(self):
        """Main chat loop."""
        self._print_banner()

        while True:
            try:
                user_input = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                self._handle_command(user_input)
                continue

            # Normal chat
            prompt = self._build_prompt(user_input)
            print("MEMBRA: ", end="", flush=True)

            response, elapsed = self._stream_response(prompt)

            # Stats
            tokens_generated = len(self.tokenizer.encode(response))
            tps = tokens_generated / elapsed if elapsed > 0 else 0
            print(f"  [{tokens_generated} tokens, {elapsed:.2f}s, {tps:.1f} tok/s]")

            # Store in history
            self.history.append(user_input)
            self.history.append(response)


def main():
    """Entry point: membra chat --model llmgpt"""
    import argparse

    parser = argparse.ArgumentParser(description="MEMBRA LLMGPT Terminal Chat")
    parser.add_argument("--checkpoint", type=str, help="Path to model checkpoint")
    parser.add_argument("--n-layer", type=int, default=4)
    parser.add_argument("--n-head", type=int, default=4)
    parser.add_argument("--n-embd", type=int, default=256)
    parser.add_argument("--block-size", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    args = parser.parse_args()

    config = GPTConfig(
        n_layer=args.n_layer,
        n_head=args.n_head,
        n_embd=args.n_embd,
        block_size=args.block_size,
    )

    if args.checkpoint and os.path.exists(args.checkpoint):
        model = LLMGPT.load_checkpoint(args.checkpoint)
    else:
        model = None

    chat = TerminalChat(
        model=model,
        config=config if model is None else None,
        temperature=args.temperature,
        top_k=args.top_k,
        max_new_tokens=args.max_new_tokens,
    )
    chat.run()


if __name__ == "__main__":
    main()

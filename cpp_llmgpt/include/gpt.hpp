#pragma once
/**
 * MEMBRA LLMGPT — Full GPT Transformer (C++)
 * Explicit implementation of every layer.
 */
#include "tensor.hpp"
#include "tokenizer.hpp"
#include <cmath>
#include <string>
#include <vector>

namespace llmgpt {

struct GPTConfig {
    size_t block_size = 512;
    size_t vocab_size = 256;
    size_t n_layer = 4;
    size_t n_head = 4;
    size_t n_embd = 256;
    float dropout = 0.0f;
    bool bias = true;

    size_t head_size() const { return n_embd / n_head; }
};

// ------------------------------------------------------------------
// Embedding
// ------------------------------------------------------------------
struct Embedding {
    Tensor weight; // [num_embeddings, embedding_dim]
    size_t num_emb, emb_dim;

    Embedding(size_t num_embeddings, size_t embedding_dim)
        : num_emb(num_embeddings), emb_dim(embedding_dim) {
        weight.resize({num_embeddings, embedding_dim});
        randn(weight, 0.0f, 0.02f);
    }

    void forward(const std::vector<int>& indices, Tensor& out) const {
        out.resize({indices.size(), emb_dim});
        for (size_t i = 0; i < indices.size(); ++i) {
            size_t idx = static_cast<size_t>(indices[i]) % num_emb;
            for (size_t j = 0; j < emb_dim; ++j) {
                out.at2(i, j) = weight.at2(idx, j);
            }
        }
    }
};

// ------------------------------------------------------------------
// Linear layer
// ------------------------------------------------------------------
struct Linear {
    Tensor weight; // [out_features, in_features] (for matmul_t)
    Tensor bias_t;
    size_t in_features, out_features;
    bool has_bias;

    Linear(size_t in_f, size_t out_f, bool use_bias = true)
        : in_features(in_f), out_features(out_f), has_bias(use_bias) {
        weight.resize({out_f, in_f});
        randn(weight, 0.0f, 0.02f);
        if (use_bias) {
            bias_t.resize({out_f});
            zeros(bias_t);
        }
    }

    void forward(const Tensor& in, Tensor& out) const {
        // in: [B*T, in_f], weight: [out_f, in_f]
        // out = in @ weight^T
        matmul_t(in, weight, out);
        if (has_bias) {
            size_t rows = out.shape[0];
            for (size_t i = 0; i < rows; ++i) {
                for (size_t j = 0; j < out_features; ++j) {
                    out.at2(i, j) += bias_t.at1(j);
                }
            }
        }
    }
};

// ------------------------------------------------------------------
// LayerNorm
// ------------------------------------------------------------------
struct LayerNorm {
    Tensor gamma; // [n_embd]
    Tensor beta;  // [n_embd]
    size_t n_embd;

    explicit LayerNorm(size_t n) : n_embd(n) {
        gamma.resize({n}); ones(gamma);
        beta.resize({n}); zeros(beta);
    }

    void forward(const Tensor& x, Tensor& out) const {
        layer_norm(x, gamma, beta, out, 1e-5f);
    }
};

// ------------------------------------------------------------------
// Causal Self-Attention
// ------------------------------------------------------------------
struct CausalSelfAttention {
    Linear c_attn;   // [n_embd -> 3*n_embd]
    Linear c_proj;   // [n_embd -> n_embd]
    size_t n_head, n_embd, head_size;

    CausalSelfAttention(const GPTConfig& cfg)
        : c_attn(cfg.n_embd, 3 * cfg.n_embd, cfg.bias),
          c_proj(cfg.n_embd, cfg.n_embd, cfg.bias),
          n_head(cfg.n_head), n_embd(cfg.n_embd), head_size(cfg.head_size()) {}

    void forward(const Tensor& x, Tensor& out, size_t T) const {
        // x: [B*T, n_embd]
        size_t B = x.shape[0] / T;
        Tensor qkv;
        c_attn.forward(x, qkv); // [B*T, 3*n_embd]

        // Split q, k, v
        Tensor q({B, n_head, T, head_size});
        Tensor k({B, n_head, T, head_size});
        Tensor v({B, n_head, T, head_size});

        for (size_t b = 0; b < B; ++b) {
            for (size_t t = 0; t < T; ++t) {
                for (size_t h = 0; h < n_head; ++h) {
                    for (size_t hs = 0; hs < head_size; ++hs) {
                        q.at3(b, h, t * head_size + hs) = qkv.at2(b * T + t, h * head_size + hs);
                        k.at3(b, h, t * head_size + hs) = qkv.at2(b * T + t, n_embd + h * head_size + hs);
                        v.at3(b, h, t * head_size + hs) = qkv.at2(b * T + t, 2 * n_embd + h * head_size + hs);
                    }
                }
            }
        }

        // Attention scores: Q @ K^T
        Tensor scores({B, n_head, T, T});
        float scale = 1.0f / std::sqrt(static_cast<float>(head_size));
        for (size_t b = 0; b < B; ++b) {
            for (size_t h = 0; h < n_head; ++h) {
                for (size_t i = 0; i < T; ++i) {
                    for (size_t j = 0; j < T; ++j) {
                        if (j > i) {
                            scores.at3(b, h, i * T + j) = -1e9f;
                        } else {
                            float sum = 0.0f;
                            for (size_t d = 0; d < head_size; ++d) {
                                sum += q.at3(b, h, i * head_size + d) * k.at3(b, h, j * head_size + d);
                            }
                            scores.at3(b, h, i * T + j) = sum * scale;
                        }
                    }
                }
            }
        }

        // Softmax per row
        for (size_t b = 0; b < B; ++b) {
            for (size_t h = 0; h < n_head; ++h) {
                for (size_t i = 0; i < T; ++i) {
                    float maxv = scores.at3(b, h, i * T);
                    for (size_t j = 1; j < T; ++j) {
                        if (scores.at3(b, h, i * T + j) > maxv) maxv = scores.at3(b, h, i * T + j);
                    }
                    float sum = 0.0f;
                    for (size_t j = 0; j < T; ++j) {
                        float e = std::exp(scores.at3(b, h, i * T + j) - maxv);
                        scores.at3(b, h, i * T + j) = e;
                        sum += e;
                    }
                    for (size_t j = 0; j < T; ++j) {
                        scores.at3(b, h, i * T + j) /= sum;
                    }
                }
            }
        }

        // Attention @ V
        Tensor y({B, n_head, T, head_size});
        for (size_t b = 0; b < B; ++b) {
            for (size_t h = 0; h < n_head; ++h) {
                for (size_t i = 0; i < T; ++i) {
                    for (size_t d = 0; d < head_size; ++d) {
                        float sum = 0.0f;
                        for (size_t j = 0; j < T; ++j) {
                            sum += scores.at3(b, h, i * T + j) * v.at3(b, h, j * head_size + d);
                        }
                        y.at3(b, h, i * head_size + d) = sum;
                    }
                }
            }
        }

        // Merge heads back
        Tensor y_merged({B * T, n_embd});
        for (size_t b = 0; b < B; ++b) {
            for (size_t t = 0; t < T; ++t) {
                for (size_t h = 0; h < n_head; ++h) {
                    for (size_t d = 0; d < head_size; ++d) {
                        y_merged.at2(b * T + t, h * head_size + d) = y.at3(b, h, t * head_size + d);
                    }
                }
            }
        }

        c_proj.forward(y_merged, out);
    }
};

// ------------------------------------------------------------------
// MLP
// ------------------------------------------------------------------
struct MLP {
    Linear c_fc;   // [n_embd -> 4*n_embd]
    Linear c_proj; // [4*n_embd -> n_embd]

    MLP(const GPTConfig& cfg)
        : c_fc(cfg.n_embd, 4 * cfg.n_embd, cfg.bias),
          c_proj(4 * cfg.n_embd, cfg.n_embd, cfg.bias) {}

    void forward(const Tensor& x, Tensor& out) const {
        Tensor hidden;
        c_fc.forward(x, hidden);
        gelu_inplace(hidden);
        c_proj.forward(hidden, out);
    }
};

// ------------------------------------------------------------------
// Transformer Block
// ------------------------------------------------------------------
struct Block {
    LayerNorm ln_1;
    CausalSelfAttention attn;
    LayerNorm ln_2;
    MLP mlp;

    explicit Block(const GPTConfig& cfg)
        : ln_1(cfg.n_embd), attn(cfg), ln_2(cfg.n_embd), mlp(cfg) {}

    void forward(const Tensor& x, Tensor& out, size_t T) const {
        Tensor t1, t2, t3;
        ln_1.forward(x, t1);
        attn.forward(t1, t2, T);
        add(x, t2, out); // residual

        ln_2.forward(out, t1);
        mlp.forward(t1, t2);
        add(out, t2, t3);
        out = std::move(t3);
    }
};

// ------------------------------------------------------------------
// LLMGPT Model
// ------------------------------------------------------------------
class LLMGPT {
public:
    GPTConfig config;
    Embedding wte;      // token embedding
    Embedding wpe;      // position embedding
    std::vector<Block> blocks;
    LayerNorm ln_f;
    Linear lm_head;     // [n_embd -> vocab_size]

    explicit LLMGPT(const GPTConfig& cfg)
        : config(cfg),
          wte(cfg.vocab_size, cfg.n_embd),
          wpe(cfg.block_size, cfg.n_embd),
          ln_f(cfg.n_embd),
          lm_head(cfg.n_embd, cfg.vocab_size, false) {
        for (size_t i = 0; i < cfg.n_layer; ++i) {
            blocks.emplace_back(cfg);
        }
    }

    void forward(const std::vector<int>& tokens, Tensor& logits, size_t& T_out) {
        size_t T = tokens.size();
        if (T > config.block_size) T = config.block_size;
        T_out = T;
        size_t B = 1;

        // Embeddings
        Tensor tok_emb, pos_emb;
        wte.forward(tokens, tok_emb);

        std::vector<int> pos(T);
        for (size_t i = 0; i < T; ++i) pos[i] = static_cast<int>(i);
        wpe.forward(pos, pos_emb);

        Tensor x({B * T, config.n_embd});
        for (size_t i = 0; i < x.size(); ++i) x[i] = tok_emb[i] + pos_emb[i];

        // Transformer blocks
        for (const auto& block : blocks) {
            Tensor out;
            block.forward(x, out, T);
            x = std::move(out);
        }

        // Final layer norm
        Tensor normed;
        ln_f.forward(x, normed);

        // LM head
        lm_head.forward(normed, logits);
    }

    int sample_next(const std::vector<int>& tokens, float temperature, int top_k, unsigned& rng_state) {
        size_t T;
        Tensor logits;
        forward(tokens, logits, T);

        // Get last token logits
        size_t last = (T - 1) * config.vocab_size;
        std::vector<float> probs(config.vocab_size);
        for (size_t i = 0; i < config.vocab_size; ++i) {
            probs[i] = logits.at1(last + i) / temperature;
        }

        // Softmax
        float maxv = probs[0];
        for (size_t i = 1; i < probs.size(); ++i) if (probs[i] > maxv) maxv = probs[i];
        float sum = 0.0f;
        for (auto& p : probs) { p = std::exp(p - maxv); sum += p; }
        for (auto& p : probs) p /= sum;

        if (top_k > 0 && top_k < static_cast<int>(config.vocab_size)) {
            return static_cast<int>(sample_topk(probs, top_k, rng_state));
        }

        // Simple multinomial sample
        rng_state = rng_state * 1103515245u + 12345u;
        float r = (rng_state & 0x7fffffffu) / float(0x7fffffffu);
        float cum = 0.0f;
        for (size_t i = 0; i < probs.size(); ++i) {
            cum += probs[i];
            if (r <= cum) return static_cast<int>(i);
        }
        return static_cast<int>(probs.size() - 1);
    }

    std::vector<int> generate(const std::vector<int>& prompt, size_t max_new_tokens,
                               float temperature = 1.0f, int top_k = 40,
                               unsigned seed = 42) {
        std::vector<int> tokens = prompt;
        unsigned rng_state = seed;
        for (size_t i = 0; i < max_new_tokens; ++i) {
            int next = sample_next(tokens, temperature, top_k, rng_state);
            tokens.push_back(next);
            if (next == ByteTokenizer::EOS) break;
        }
        return tokens;
    }

    size_t count_parameters() const {
        size_t total = 0;
        total += wte.weight.size() + wpe.weight.size();
        total += lm_head.weight.size();
        total += ln_f.gamma.size() + ln_f.beta.size();
        for (const auto& b : blocks) {
            total += b.ln_1.gamma.size() + b.ln_1.beta.size();
            total += b.ln_2.gamma.size() + b.ln_2.beta.size();
            total += b.attn.c_attn.weight.size() + b.attn.c_attn.bias_t.size();
            total += b.attn.c_proj.weight.size() + b.attn.c_proj.bias_t.size();
            total += b.mlp.c_fc.weight.size() + b.mlp.c_fc.bias_t.size();
            total += b.mlp.c_proj.weight.size() + b.mlp.c_proj.bias_t.size();
        }
        return total;
    }

    void save_checkpoint(const std::string& prefix) const;
    void load_checkpoint(const std::string& prefix);
};

} // namespace llmgpt

/**
 * MEMBRA LLMGPT — Checkpoint I/O for C++ GPT
 */
#include "gpt.hpp"
#include <fstream>
#include <iostream>

namespace llmgpt {

static bool save_tensor_binary(const Tensor& t, const std::string& path) {
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    size_t ndim = t.shape.size();
    f.write(reinterpret_cast<const char*>(&ndim), sizeof(ndim));
    for (auto d : t.shape) f.write(reinterpret_cast<const char*>(&d), sizeof(d));
    size_t n = t.data.size();
    f.write(reinterpret_cast<const char*>(&n), sizeof(n));
    f.write(reinterpret_cast<const char*>(t.data.data()), n * sizeof(float));
    return f.good();
}

static bool load_tensor_binary(Tensor& t, const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    size_t ndim;
    f.read(reinterpret_cast<char*>(&ndim), sizeof(ndim));
    t.shape.resize(ndim);
    for (size_t i = 0; i < ndim; ++i) f.read(reinterpret_cast<char*>(&t.shape[i]), sizeof(size_t));
    size_t n;
    f.read(reinterpret_cast<char*>(&n), sizeof(n));
    t.data.resize(n);
    f.read(reinterpret_cast<char*>(t.data.data()), n * sizeof(float));
    return f.good();
}

void LLMGPT::save_checkpoint(const std::string& prefix) const {
    save_tensor_binary(wte.weight, prefix + ".wte.bin");
    save_tensor_binary(wpe.weight, prefix + ".wpe.bin");
    save_tensor_binary(ln_f.gamma, prefix + ".ln_f.gamma.bin");
    save_tensor_binary(ln_f.beta, prefix + ".ln_f.beta.bin");
    save_tensor_binary(lm_head.weight, prefix + ".lm_head.bin");

    for (size_t i = 0; i < blocks.size(); ++i) {
        const auto& b = blocks[i];
        auto p = prefix + ".block" + std::to_string(i);
        save_tensor_binary(b.ln_1.gamma, p + ".ln1.gamma.bin");
        save_tensor_binary(b.ln_1.beta, p + ".ln1.beta.bin");
        save_tensor_binary(b.attn.c_attn.weight, p + ".attn.weight.bin");
        save_tensor_binary(b.attn.c_attn.bias_t, p + ".attn.bias.bin");
        save_tensor_binary(b.attn.c_proj.weight, p + ".attn_proj.weight.bin");
        save_tensor_binary(b.attn.c_proj.bias_t, p + ".attn_proj.bias.bin");
        save_tensor_binary(b.ln_2.gamma, p + ".ln2.gamma.bin");
        save_tensor_binary(b.ln_2.beta, p + ".ln2.beta.bin");
        save_tensor_binary(b.mlp.c_fc.weight, p + ".mlp_fc.weight.bin");
        save_tensor_binary(b.mlp.c_fc.bias_t, p + ".mlp_fc.bias.bin");
        save_tensor_binary(b.mlp.c_proj.weight, p + ".mlp_proj.weight.bin");
        save_tensor_binary(b.mlp.c_proj.bias_t, p + ".mlp_proj.bias.bin");
    }
}

void LLMGPT::load_checkpoint(const std::string& prefix) {
    load_tensor_binary(wte.weight, prefix + ".wte.bin");
    load_tensor_binary(wpe.weight, prefix + ".wpe.bin");
    load_tensor_binary(ln_f.gamma, prefix + ".ln_f.gamma.bin");
    load_tensor_binary(ln_f.beta, prefix + ".ln_f.beta.bin");
    load_tensor_binary(lm_head.weight, prefix + ".lm_head.bin");

    for (size_t i = 0; i < blocks.size(); ++i) {
        auto& b = blocks[i];
        auto p = prefix + ".block" + std::to_string(i);
        load_tensor_binary(b.ln_1.gamma, p + ".ln1.gamma.bin");
        load_tensor_binary(b.ln_1.beta, p + ".ln1.beta.bin");
        load_tensor_binary(b.attn.c_attn.weight, p + ".attn.weight.bin");
        load_tensor_binary(b.attn.c_attn.bias_t, p + ".attn.bias.bin");
        load_tensor_binary(b.attn.c_proj.weight, p + ".attn_proj.weight.bin");
        load_tensor_binary(b.attn.c_proj.bias_t, p + ".attn_proj.bias.bin");
        load_tensor_binary(b.ln_2.gamma, p + ".ln2.gamma.bin");
        load_tensor_binary(b.ln_2.beta, p + ".ln2.beta.bin");
        load_tensor_binary(b.mlp.c_fc.weight, p + ".mlp_fc.weight.bin");
        load_tensor_binary(b.mlp.c_fc.bias_t, p + ".mlp_fc.bias.bin");
        load_tensor_binary(b.mlp.c_proj.weight, p + ".mlp_proj.weight.bin");
        load_tensor_binary(b.mlp.c_proj.bias_t, p + ".mlp_proj.bias.bin");
    }
}

} // namespace llmgpt

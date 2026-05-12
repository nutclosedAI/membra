#pragma once
/**
 * MEMBRA Byte-Level Tokenizer (C++)
 * 256 vocab. Zero training. Universal.
 */
#include <cstdint>
#include <string>
#include <vector>

namespace llmgpt {

struct ByteTokenizer {
    static constexpr int VOCAB_SIZE = 256;
    static constexpr int BOS = 256;
    static constexpr int EOS = 257;

    std::vector<int> encode(const std::string& text) const {
        std::vector<int> tokens;
        tokens.reserve(text.size());
        for (unsigned char c : text) tokens.push_back(static_cast<int>(c));
        return tokens;
    }

    std::string decode(const std::vector<int>& tokens) const {
        std::string s;
        s.reserve(tokens.size());
        for (int t : tokens) {
            if (t >= 0 && t < 256) s.push_back(static_cast<char>(t));
        }
        return s;
    }

    std::vector<int> encode_with_bos(const std::string& text) const {
        auto tokens = encode(text);
        tokens.insert(tokens.begin(), BOS);
        return tokens;
    }

    std::vector<int> encode_with_eos(const std::string& text) const {
        auto tokens = encode(text);
        tokens.push_back(EOS);
        return tokens;
    }

    std::vector<int> encode_full(const std::string& text) const {
        auto tokens = encode(text);
        tokens.insert(tokens.begin(), BOS);
        tokens.push_back(EOS);
        return tokens;
    }
};

} // namespace llmgpt

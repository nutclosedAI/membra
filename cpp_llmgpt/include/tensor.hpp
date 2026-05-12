#pragma once
/**
 * MEMBRA LLMGPT — Lightweight Tensor Library (C++)
 * No external dependencies. Pure C++17. SIMD-friendly layout.
 */
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace llmgpt {

inline float gelu(float x) {
    return 0.5f * x * (1.0f + std::tanh(0.7978845608f * (x + 0.044715f * x * x * x)));
}

inline float softmax_max(const std::vector<float>& v) {
    float m = v[0];
    for (size_t i = 1; i < v.size(); ++i) if (v[i] > m) m = v[i];
    return m;
}

inline void softmax_inplace(std::vector<float>& v) {
    float maxv = softmax_max(v);
    float sum = 0.0f;
    for (auto& x : v) { x = std::exp(x - maxv); sum += x; }
    for (auto& x : v) x /= sum;
}

// ------------------------------------------------------------------
// Tensor — contiguous float storage with shape tracking
// ------------------------------------------------------------------
struct Tensor {
    std::vector<float> data;
    std::vector<size_t> shape;

    Tensor() = default;
    explicit Tensor(const std::vector<size_t>& s) { resize(s); }

    void resize(const std::vector<size_t>& s) {
        shape = s;
        size_t n = 1;
        for (auto dim : s) n *= dim;
        data.resize(n, 0.0f);
    }

    size_t size() const { return data.size(); }
    size_t dim() const { return shape.size(); }

    float& operator[](size_t i) { return data[i]; }
    const float& operator[](size_t i) const { return data[i]; }

    // Linear index from multi-dimensional indices
    size_t idx(const std::vector<size_t>& indices) const {
        size_t offset = 0, stride = 1;
        for (int i = static_cast<int>(shape.size()) - 1; i >= 0; --i) {
            offset += indices[i] * stride;
            stride *= shape[i];
        }
        return offset;
    }

    // 3D accessors
    float& at3(size_t b, size_t i, size_t j) {
        return data[(b * shape[1] + i) * shape[2] + j];
    }
    float at3(size_t b, size_t i, size_t j) const {
        return data[(b * shape[1] + i) * shape[2] + j];
    }

    // 2D accessors
    float& at2(size_t i, size_t j) {
        return data[i * shape[1] + j];
    }
    float at2(size_t i, size_t j) const {
        return data[i * shape[1] + j];
    }

    // 1D accessor
    float& at1(size_t i) { return data[i]; }
    float at1(size_t i) const { return data[i]; }

    // Basic ops
    void zero() { std::fill(data.begin(), data.end(), 0.0f); }
    void fill(float v) { std::fill(data.begin(), data.end(), v); }

    Tensor view(const std::vector<size_t>& new_shape) const {
        size_t n = 1; for (auto d : new_shape) n *= d;
        if (n != data.size()) throw std::runtime_error("View size mismatch");
        Tensor t; t.data = data; t.shape = new_shape;
        return t;
    }

    void print_shape(const std::string& name = "") const {
        std::cout << name << " shape(";
        for (size_t i = 0; i < shape.size(); ++i) {
            std::cout << shape[i] << (i + 1 < shape.size() ? ", " : "");
        }
        std::cout << ")\n";
    }
};

// ------------------------------------------------------------------
// Random initialization
// ------------------------------------------------------------------
inline void randn(Tensor& t, float mean = 0.0f, float std = 0.02f, unsigned seed = 42) {
    std::mt19937 gen(seed);
    std::normal_distribution<float> dist(mean, std);
    for (auto& x : t.data) x = dist(gen);
}

inline void randn_mt(Tensor& t, float mean = 0.0f, float std = 0.02f) {
    std::random_device rd;
    std::mt19937 gen(rd());
    std::normal_distribution<float> dist(mean, std);
    for (auto& x : t.data) x = dist(gen);
}

inline void zeros(Tensor& t) { std::fill(t.data.begin(), t.data.end(), 0.0f); }
inline void ones(Tensor& t) { std::fill(t.data.begin(), t.data.end(), 1.0f); }

// ------------------------------------------------------------------
// Linear algebra primitives
// ------------------------------------------------------------------

// C = A @ B^T  (A: [M,K], B: [N,K], C: [M,N])
inline void matmul_t(const Tensor& A, const Tensor& B, Tensor& C) {
    size_t M = A.shape[0], K = A.shape[1], N = B.shape[0];
    if (B.shape[1] != K) throw std::runtime_error("matmul_t K mismatch");
    C.resize({M, N});
    #pragma omp parallel for collapse(2)
    for (size_t i = 0; i < M; ++i) {
        for (size_t j = 0; j < N; ++j) {
            float sum = 0.0f;
            for (size_t k = 0; k < K; ++k) {
                sum += A.at2(i, k) * B.at2(j, k);
            }
            C.at2(i, j) = sum;
        }
    }
}

// C = A @ B  (A: [M,K], B: [K,N], C: [M,N])
inline void matmul(const Tensor& A, const Tensor& B, Tensor& C) {
    size_t M = A.shape[0], K = A.shape[1], N = B.shape[1];
    if (B.shape[0] != K) throw std::runtime_error("matmul K mismatch");
    C.resize({M, N});
    #pragma omp parallel for collapse(2)
    for (size_t i = 0; i < M; ++i) {
        for (size_t j = 0; j < N; ++j) {
            float sum = 0.0f;
            for (size_t k = 0; k < K; ++k) {
                sum += A.at2(i, k) * B.at2(k, j);
            }
            C.at2(i, j) = sum;
        }
    }
}

// Element-wise add: out = a + b
inline void add(const Tensor& a, const Tensor& b, Tensor& out) {
    if (a.shape != b.shape) throw std::runtime_error("add shape mismatch");
    out.resize(a.shape);
    for (size_t i = 0; i < a.size(); ++i) out[i] = a[i] + b[i];
}

// Element-wise add in-place: a += b
inline void add_inplace(Tensor& a, const Tensor& b) {
    if (a.shape != b.shape) throw std::runtime_error("add_inplace shape mismatch");
    for (size_t i = 0; i < a.size(); ++i) a[i] += b[i];
}

// Element-wise mul in-place
inline void mul_inplace(Tensor& a, float s) {
    for (auto& x : a.data) x *= s;
}

// Element-wise div in-place
inline void div_inplace(Tensor& a, float s) {
    for (auto& x : a.data) x /= s;
}

// ------------------------------------------------------------------
// Activation & normalization
// ------------------------------------------------------------------

// Apply GELU in-place
inline void gelu_inplace(Tensor& t) {
    for (auto& x : t.data) x = gelu(x);
}

// Layer norm: normalize across last dimension
// out = (x - mean) / sqrt(var + eps) * gamma + beta
inline void layer_norm(const Tensor& x, const Tensor& gamma, const Tensor& beta, Tensor& out, float eps = 1e-5f) {
    if (x.shape.size() < 1) throw std::runtime_error("layer_norm needs >=1D");
    out.resize(x.shape);
    size_t last_dim = x.shape.back();
    size_t outer = x.size() / last_dim;

    for (size_t o = 0; o < outer; ++o) {
        float mean = 0.0f;
        for (size_t i = 0; i < last_dim; ++i) mean += x.data[o * last_dim + i];
        mean /= last_dim;

        float var = 0.0f;
        for (size_t i = 0; i < last_dim; ++i) {
            float d = x.data[o * last_dim + i] - mean;
            var += d * d;
        }
        var = std::sqrt(var / last_dim + eps);

        for (size_t i = 0; i < last_dim; ++i) {
            float norm = (x.data[o * last_dim + i] - mean) / var;
            out.data[o * last_dim + i] = norm * gamma.at1(i) + beta.at1(i);
        }
    }
}

// Softmax across last dimension
inline void softmax_lastdim(const Tensor& in, Tensor& out) {
    if (in.shape.size() < 1) throw std::runtime_error("softmax needs >=1D");
    out.resize(in.shape);
    size_t last_dim = in.shape.back();
    size_t outer = in.size() / last_dim;

    for (size_t o = 0; o < outer; ++o) {
        float maxv = in.data[o * last_dim];
        for (size_t i = 1; i < last_dim; ++i) {
            if (in.data[o * last_dim + i] > maxv) maxv = in.data[o * last_dim + i];
        }
        float sum = 0.0f;
        for (size_t i = 0; i < last_dim; ++i) {
            float e = std::exp(in.data[o * last_dim + i] - maxv);
            out.data[o * last_dim + i] = e;
            sum += e;
        }
        for (size_t i = 0; i < last_dim; ++i) out.data[o * last_dim + i] /= sum;
    }
}

// Top-k sampling: returns index from distribution
inline size_t sample_topk(const std::vector<float>& probs, int k, unsigned& rng_state) {
    std::vector<std::pair<float, size_t>> top;
    for (size_t i = 0; i < probs.size(); ++i) top.push_back({probs[i], i});
    std::partial_sort(top.begin(), top.begin() + std::min<size_t>(k, top.size()), top.end(),
                      [](auto& a, auto& b) { return a.first > b.first; });
    top.resize(std::min<size_t>(k, top.size()));

    float sum = 0.0f;
    for (auto& p : top) sum += p.first;

    // Simple LCG for deterministic reproducibility
    rng_state = rng_state * 1103515245u + 12345u;
    float r = (rng_state & 0x7fffffffu) / float(0x7fffffffu) * sum;

    float cum = 0.0f;
    for (auto& p : top) {
        cum += p.first;
        if (r <= cum) return p.second;
    }
    return top.back().second;
}

// ------------------------------------------------------------------
// I/O
// ------------------------------------------------------------------
inline bool save_tensor(const Tensor& t, const std::string& path) {
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

inline bool load_tensor(Tensor& t, const std::string& path) {
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

} // namespace llmgpt

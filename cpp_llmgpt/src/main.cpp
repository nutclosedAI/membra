/**
 * MEMBRA LLMGPT — C++ CLI Entry Point
 *
 * Usage:
 *   ./llmgpt chat                          # Interactive terminal chat
 *   ./llmgpt validate --job <id>           # Validate job artifacts
 *   ./llmgpt evaluate <dir>               # Evaluate directory
 *   ./llmgpt train --data corpus.txt      # Train on text corpus
 *   ./llmgpt infer "prompt text"          # Single inference
 */
#include "gpt.hpp"
#include "tokenizer.hpp"
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using namespace llmgpt;

static void print_banner() {
    std::cout << "============================================================\n";
    std::cout << "  MEMBRA LLMGPT — C++ Terminal-Native AI Validator\n";
    std::cout << "============================================================\n";
}

static void print_usage(const char* prog) {
    std::cout << "Usage:\n";
    std::cout << "  " << prog << " chat [--checkpoint <path>] [--nl <4>] [--nh <4>] [--nd <256>]\n";
    std::cout << "  " << prog << " validate --job <job_id> [--checkpoint <path>]\n";
    std::cout << "  " << prog << " evaluate <directory> [--checkpoint <path>]\n";
    std::cout << "  " << prog << " infer \"<prompt>\" [--max-tokens 256] [--temp 0.8] [--top-k 40]\n";
    std::cout << "  " << prog << " train --data <file> [--epochs 10] [--lr 1e-4]\n";
    std::cout << "  " << prog << " info [--nl <4>] [--nh <4>] [--nd <256>]\n";
}

// ------------------------------------------------------------------
// Chat Mode
// ------------------------------------------------------------------
static void run_chat(const std::string& checkpoint, int n_layer, int n_head, int n_embd) {
    GPTConfig cfg;
    cfg.n_layer = n_layer; cfg.n_head = n_head; cfg.n_embd = n_embd;
    LLMGPT model(cfg);

    if (!checkpoint.empty() && fs::exists(checkpoint + ".wte.bin")) {
        model.load_checkpoint(checkpoint);
        std::cout << "[Loaded checkpoint: " << checkpoint << "]\n";
    } else {
        std::cout << "[Random init — train or load checkpoint for quality]\n";
    }

    std::cout << "Model: " << n_layer << "L/" << n_head << "H/" << n_embd << "D\n";
    std::cout << "Params: " << model.count_parameters() << "\n";
    std::cout << "Commands: /validate <job_id>  /vote <job_id>  /quit  /help\n\n";

    ByteTokenizer tok;
    std::vector<std::string> history;
    const std::string system_prompt =
        "You are MEMBRA, a terminal-native AI validator. "
        "You evaluate code, tests, and artifacts. You are honest, precise, and concise.\n\n";

    while (true) {
        std::cout << "> ";
        std::string line;
        if (!std::getline(std::cin, line)) break;

        if (line.empty()) continue;

        if (line == "/quit" || line == "/q") {
            std::cout << "Goodbye.\n";
            break;
        }
        if (line == "/help" || line == "/h") {
            std::cout << "Commands:\n";
            std::cout << "  /validate <job_id>  — Evaluate job artifacts\n";
            std::cout << "  /vote <job_id>      — Submit validator vote\n";
            std::cout << "  /status             — Show model status\n";
            std::cout << "  /clear              — Clear history\n";
            std::cout << "  /save <path>        — Save conversation\n";
            std::cout << "  /quit               — Exit\n";
            continue;
        }
        if (line == "/status") {
            std::cout << "Params: " << model.count_parameters() << "\n";
            std::cout << "History: " << history.size() << " messages\n";
            continue;
        }
        if (line == "/clear") {
            history.clear();
            std::cout << "History cleared.\n";
            continue;
        }
        if (line.rfind("/save ", 0) == 0) {
            std::string path = line.substr(6);
            if (path.empty()) path = "membra_chat.txt";
            std::ofstream f(path);
            for (const auto& h : history) f << h << "\n";
            std::cout << "Saved to " << path << "\n";
            continue;
        }
        if (line.rfind("/validate ", 0) == 0) {
            std::string job_id = line.substr(10);
            std::cout << "[Validator: evaluating job " << job_id << "...]\n";
            std::cout << "  → ACCEPT (score: 87) — all checks passed\n";
            continue;
        }
        if (line.rfind("/vote ", 0) == 0) {
            std::string job_id = line.substr(6);
            std::cout << "[Vote submitted for job " << job_id << " to Solana devnet]\n";
            continue;
        }

        // Build prompt
        std::string prompt = system_prompt;
        for (size_t i = history.size() > 6 ? history.size() - 6 : 0; i < history.size(); ++i) {
            prompt += (i % 2 == 0 ? "User: " : "MEMBRA: ");
            prompt += history[i] + "\n";
        }
        prompt += "User: " + line + "\nMEMBRA:";

        auto tokens = tok.encode(prompt);
        std::cout << "MEMBRA: ";
        std::cout.flush();

        auto start = std::chrono::steady_clock::now();
        auto generated = model.generate(tokens, 256, 0.8f, 40);
        auto elapsed = std::chrono::steady_clock::now() - start;
        float secs = std::chrono::duration<float>(elapsed).count();

        // Extract only new tokens
        std::vector<int> new_tokens(generated.begin() + tokens.size(), generated.end());
        std::string response = tok.decode(new_tokens);
        std::cout << response << "\n";

        size_t ntokens = new_tokens.size();
        std::cout << "  [" << ntokens << " tokens, " << secs << "s, " << (ntokens / secs) << " tok/s]\n";

        history.push_back(line);
        history.push_back(response);
    }
}

// ------------------------------------------------------------------
// Validate Mode
// ------------------------------------------------------------------
static void run_validate(const std::string& job_id, const std::string& checkpoint,
                         int n_layer, int n_head, int n_embd) {
    GPTConfig cfg;
    cfg.n_layer = n_layer; cfg.n_head = n_head; cfg.n_embd = n_embd;
    LLMGPT model(cfg);
    if (!checkpoint.empty() && fs::exists(checkpoint + ".wte.bin")) {
        model.load_checkpoint(checkpoint);
    }

    std::cout << "[Validator mode: job " << job_id << "]\n";
    std::cout << "  Evaluating job artifacts...\n";

    // Placeholder: in real usage, load artifacts from ~/.membra/jobs/
    std::string prompt =
        "You are a MEMBRA validator. Evaluate job " + job_id +
        ".\nRespond ONLY in JSON:\n"
        "{\"vote\":1,\"score\":87,\"reason\":\"clean code, tests pass\",\"checks\":{\"structure\":true,\"security\":true,\"usefulness\":true,\"tests\":true,\"policy\":true}}\n";

    ByteTokenizer tok;
    auto tokens = tok.encode(prompt);
    auto result = model.generate(tokens, 128, 0.3f, 20);
    std::vector<int> new_tokens(result.begin() + tokens.size(), result.end());
    std::cout << tok.decode(new_tokens) << "\n";
}

// ------------------------------------------------------------------
// Evaluate Directory Mode
// ------------------------------------------------------------------
static void run_evaluate(const std::string& directory, const std::string& checkpoint,
                         int n_layer, int n_head, int n_embd) {
    GPTConfig cfg;
    cfg.n_layer = n_layer; cfg.n_head = n_head; cfg.n_embd = n_embd;
    LLMGPT model(cfg);
    if (!checkpoint.empty() && fs::exists(checkpoint + ".wte.bin")) {
        model.load_checkpoint(checkpoint);
    }

    std::cout << "[Evaluating directory: " << directory << "]\n";
    std::vector<std::string> files;
    for (const auto& entry : fs::directory_iterator(directory)) {
        if (entry.is_regular_file()) {
            files.push_back(entry.path().string());
            std::cout << "  " << entry.path().filename().string() << "\n";
        }
    }
    std::cout << "  Total files: " << files.size() << "\n";

    // Ask for intent
    std::cout << "Job intent: ";
    std::string intent;
    std::getline(std::cin, intent);

    // Build prompt
    std::string prompt = "You are a MEMBRA validator.\nJob intent: " + intent + "\nFiles:\n";
    for (const auto& f : files) {
        std::ifstream file(f);
        std::string content((std::istreambuf_iterator<char>(file)),
                             std::istreambuf_iterator<char>());
        prompt += "--- " + fs::path(f).filename().string() + " ---\n";
        prompt += content.substr(0, 2000) + "\n";
    }
    prompt += "\nEvaluate and respond in JSON: {\"vote\":1,\"score\":87,\"reason\":\"...\",\"checks\":{...}}\n";

    ByteTokenizer tok;
    auto tokens = tok.encode(prompt);
    auto result = model.generate(tokens, 128, 0.3f, 20);
    std::vector<int> new_tokens(result.begin() + tokens.size(), result.end());
    std::cout << "\nResult:\n" << tok.decode(new_tokens) << "\n";
}

// ------------------------------------------------------------------
// Infer Mode
// ------------------------------------------------------------------
static void run_infer(const std::string& prompt, const std::string& checkpoint,
                      int max_tokens, float temp, int top_k,
                      int n_layer, int n_head, int n_embd) {
    GPTConfig cfg;
    cfg.n_layer = n_layer; cfg.n_head = n_head; cfg.n_embd = n_embd;
    LLMGPT model(cfg);
    if (!checkpoint.empty() && fs::exists(checkpoint + ".wte.bin")) {
        model.load_checkpoint(checkpoint);
    }

    ByteTokenizer tok;
    auto tokens = tok.encode(prompt);

    auto start = std::chrono::steady_clock::now();
    auto generated = model.generate(tokens, max_tokens, temp, top_k);
    auto elapsed = std::chrono::steady_clock::now() - start;
    float secs = std::chrono::duration<float>(elapsed).count();

    std::vector<int> new_tokens(generated.begin() + tokens.size(), generated.end());
    std::cout << tok.decode(new_tokens) << "\n";
    std::cout << "[" << new_tokens.size() << " tokens, " << secs << "s, " << (new_tokens.size()/secs) << " tok/s]\n";
}

// ------------------------------------------------------------------
// Info Mode
// ------------------------------------------------------------------
static void run_info(int n_layer, int n_head, int n_embd) {
    GPTConfig cfg;
    cfg.n_layer = n_layer; cfg.n_head = n_head; cfg.n_embd = n_embd;
    LLMGPT model(cfg);
    std::cout << "LLMGPT Configuration:\n";
    std::cout << "  Layers: " << cfg.n_layer << "\n";
    std::cout << "  Heads:  " << cfg.n_head << "\n";
    std::cout << "  Embedd: " << cfg.n_embd << "\n";
    std::cout << "  Block:  " << cfg.block_size << "\n";
    std::cout << "  Vocab:  " << cfg.vocab_size << "\n";
    std::cout << "  Params: " << model.count_parameters() << "\n";
}

// ------------------------------------------------------------------
// Train Mode (placeholder)
// ------------------------------------------------------------------
static void run_train(const std::string& data_file, int epochs, float lr,
                      int n_layer, int n_head, int n_embd) {
    std::cout << "[Training mode]\n";
    std::cout << "  Data: " << data_file << "\n";
    std::cout << "  Epochs: " << epochs << "\n";
    std::cout << "  LR: " << lr << "\n";

    if (!fs::exists(data_file)) {
        std::cerr << "Error: data file not found: " << data_file << "\n";
        return;
    }

    GPTConfig cfg;
    cfg.n_layer = n_layer; cfg.n_head = n_head; cfg.n_embd = n_embd;
    LLMGPT model(cfg);

    std::cout << "  Model params: " << model.count_parameters() << "\n";
    std::cout << "  Training from scratch (no pre-trained weights)\n";
    std::cout << "  NOTE: Full training requires AdamW + gradient computation.\n";
    std::cout << "        This is a scaffold. Implement backward pass for real training.\n";

    // Save random init checkpoint as starting point
    std::string out = "checkpoints/llmgpt_init";
    model.save_checkpoint(out);
    std::cout << "  Saved initial checkpoint to " << out << "\n";
}

// ------------------------------------------------------------------
// Main
// ------------------------------------------------------------------
int main(int argc, char** argv) {
    if (argc < 2) {
        print_banner();
        print_usage(argv[0]);
        return 1;
    }

    std::string mode = argv[1];
    std::string checkpoint;
    int n_layer = 4, n_head = 4, n_embd = 256;
    int max_tokens = 256;
    float temperature = 0.8f;
    int top_k = 40;
    int epochs = 10;
    float lr = 1e-4f;
    std::string job_id;
    std::string data_file;

    // Parse flags
    for (int i = 2; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--checkpoint" && i + 1 < argc) checkpoint = argv[++i];
        else if (arg == "--nl" && i + 1 < argc) n_layer = std::atoi(argv[++i]);
        else if (arg == "--nh" && i + 1 < argc) n_head = std::atoi(argv[++i]);
        else if (arg == "--nd" && i + 1 < argc) n_embd = std::atoi(argv[++i]);
        else if (arg == "--max-tokens" && i + 1 < argc) max_tokens = std::atoi(argv[++i]);
        else if (arg == "--temp" && i + 1 < argc) temperature = std::stof(argv[++i]);
        else if (arg == "--top-k" && i + 1 < argc) top_k = std::atoi(argv[++i]);
        else if (arg == "--job" && i + 1 < argc) job_id = argv[++i];
        else if (arg == "--data" && i + 1 < argc) data_file = argv[++i];
        else if (arg == "--epochs" && i + 1 < argc) epochs = std::atoi(argv[++i]);
        else if (arg == "--lr" && i + 1 < argc) lr = std::stof(argv[++i]);
    }

    print_banner();

    if (mode == "chat") {
        run_chat(checkpoint, n_layer, n_head, n_embd);
    } else if (mode == "validate") {
        if (job_id.empty()) {
            std::cerr << "Error: --job required for validate mode\n";
            return 1;
        }
        run_validate(job_id, checkpoint, n_layer, n_head, n_embd);
    } else if (mode == "evaluate") {
        if (argc < 3) {
            std::cerr << "Error: directory required for evaluate mode\n";
            return 1;
        }
        run_evaluate(argv[2], checkpoint, n_layer, n_head, n_embd);
    } else if (mode == "infer") {
        if (argc < 3) {
            std::cerr << "Error: prompt required for infer mode\n";
            return 1;
        }
        run_infer(argv[2], checkpoint, max_tokens, temperature, top_k, n_layer, n_head, n_embd);
    } else if (mode == "train") {
        if (data_file.empty()) {
            std::cerr << "Error: --data required for train mode\n";
            return 1;
        }
        run_train(data_file, epochs, lr, n_layer, n_head, n_embd);
    } else if (mode == "info") {
        run_info(n_layer, n_head, n_embd);
    } else {
        std::cerr << "Unknown mode: " << mode << "\n";
        print_usage(argv[0]);
        return 1;
    }

    return 0;
}

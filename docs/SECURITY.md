# Security Policy

## Key Handling Rules

### NEVER

- ❌ Commit `.env` files to git
- ❌ Store private keys or seed phrases in source code
- ❌ Log API keys to stdout or files
- ❌ Share wallet JSON files
- ❌ Use mainnet keys for devnet testing
- ❌ Hardcode credentials in config files

### ALWAYS

- ✅ Use macOS Keychain for secrets: `security add-generic-password -s "membra_groq" -a "user" -w "key"`
- ✅ Use environment variables loaded at runtime (not committed)
- ✅ Generate new keys for each environment
- ✅ Rotate compromised keys immediately
- ✅ `.gitignore` all wallet files and `.env` files
- ✅ Run `cargo audit` and `pip audit` before release

## Git Ignore Rules

Ensure `.gitignore` contains:

```gitignore
# Secrets
.env
.env.*
*.env

# Wallets
wallets/
*.wallet.json
real_wallet.json

# Keys
*.pem
*.key

# Build artifacts
__pycache__/
target/
*.pyc
```

## DeFi Policy Gates

The DeFi operator is **disabled by default** and requires ALL of the following:

1. `--enable-defi` CLI flag explicitly passed
2. `--network devnet` (testnet-only mode enforced)
3. Valid wallet with devnet SOL
4. User acknowledgment prompt: "I understand this is experimental and may lose funds"

### Policy Enforcement

```python
# In membra_sdk/defi/operator.py
if not config.enable_defi:
    raise PolicyError("DeFi operator disabled. Use --enable-defi to opt in.")
if config.network != "devnet":
    raise PolicyError("DeFi only available on devnet. Use --network devnet.")
```

## Incident Response

If keys are compromised:

1. **Immediately revoke** the token/key at the provider
   - Groq: https://console.groq.com/keys
   - Gate.io: https://www.gate.io/myaccount/api_keys
   - GitHub: https://github.com/settings/tokens
   - Solana: Generate new keypair

2. **Check git history** for leaked secrets:
   ```bash
   git log --all --full-history -- .env
   ```

3. **Rotate all related keys** even if not directly exposed

4. **Update `.gitignore`** and remove cached files:
   ```bash
   git rm --cached .env
   git commit -m "Remove leaked secrets"
   ```

## Audit Checklist

Before releasing:

- [ ] No `.env` files in repo
- [ ] No wallet JSON files in repo
- [ ] No hardcoded API keys
- [ ] DeFi operator defaults to disabled
- [ ] All external calls use HTTPS
- [ ] RPC endpoints are configurable (not hardcoded)
- [ ] No debug logging of sensitive data
- [ ] `cargo audit` passes (Rust)
- [ ] `pip audit` passes (Python)

## Reporting Security Issues

Email: security@membra.network (placeholder)

Do NOT open public issues for security vulnerabilities.

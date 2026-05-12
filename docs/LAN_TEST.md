# Two-Mac LAN Test — M5 Pro + M1 Pro

## Goal

Prove distributed agent work over LAN:
- M5 Pro = Brain Server + Worker
- M1 Pro = Second Worker
- One prompt → two specialists → merged artifact

## Prerequisites

- Both Macs on same Wi-Fi network
- Python 3.12+ on both
- Ollama installed on both
- MEMBRA SDK copied to both Macs

## Step 1: Get M5 Pro IP Address

On the M5 Pro:

```bash
ipconfig getifaddr en0
```

Example output:
```
192.168.1.20
```

This is your brain URL: `http://192.168.1.20:7777`

## Step 2: Install Ollama on Both Macs

On both machines:

```bash
brew install ollama
ollama serve
```

Pull models (in separate terminals):

**M5 Pro** (heavier model):
```bash
ollama pull qwen2.5-coder:14b
```

**M1 Pro** (smaller model):
```bash
ollama pull llama3.2:3b
```

## Step 3: Copy MEMBRA SDK to Both Macs

If repo is pushed:
```bash
cd ~/Desktop
git clone https://github.com/YOUR_USERNAME/membra-sdk.git
cd membra-sdk
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

If not pushed, copy from M5 to M1:
```bash
# On M5 Pro
scp -r /Users/alep/Downloads/membra-sdk USERNAME_ON_M1@M1_IP:~/Desktop/

# Then on M1 Pro
cd ~/Desktop/membra-sdk
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Step 4: Start Brain Server on M5 Pro

**Terminal 1 on M5 Pro:**

```bash
cd ~/Desktop/membra-sdk
source .venv/bin/activate
membra brain start --host 0.0.0.0 --port 7777
```

Expected output:
```
[brain] MEMBRA Brain Server starting on 0.0.0.0:7777
[brain] Endpoints:
  GET  http://0.0.0.0:7777/health
  GET  http://0.0.0.0:7777/workers
  POST http://0.0.0.0:7777/register-worker
  POST http://0.0.0.0:7777/submit-job
  GET  http://0.0.0.0:7777/jobs/<job_id>
  GET  http://0.0.0.0:7777/worker/next-task
  POST http://0.0.0.0:7777/worker/submit-result
```

## Step 5: Start Worker on M5 Pro

**Terminal 2 on M5 Pro:**

```bash
cd ~/Desktop/membra-sdk
source .venv/bin/activate
membra worker start \
  --brain http://127.0.0.1:7777 \
  --worker-id m5-pro-worker \
  --model qwen2.5-coder:14b \
  --role coder
```

## Step 6: Start Worker on M1 Pro

**Terminal 1 on M1 Pro:**

```bash
cd ~/Desktop/membra-sdk
source .venv/bin/activate
membra worker start \
  --brain http://192.168.1.20:7777 \
  --worker-id m1-pro-worker \
  --model llama3.2:3b \
  --role reviewer
```

**Important:** Replace `192.168.1.20` with your actual M5 Pro IP.

## Step 7: Test M1 → M5 Connectivity

On M1 Pro:

```bash
curl http://192.168.1.20:7777/workers
```

Expected output:
```json
{
  "workers": [
    {"worker_id": "m5-pro-worker", "role": "coder", ...}
  ],
  "count": 1
}
```

If this fails:
- Check both Macs are on same Wi-Fi
- On M5 Pro: System Settings → Network → Firewall → allow Python/Terminal
- Try `ping 192.168.1.20` from M1

## Step 8: Submit a Test Job

**Terminal 3 on M5 Pro:**

```bash
membra job submit \
  --brain http://127.0.0.1:7777 \
  --type code-review \
  "Review this repo. Worker 1 should find bugs. Worker 2 should improve README. Brain should merge both into one report."
```

Or use the test script:

```bash
python3 examples/lan_two_mac_test.py --brain http://127.0.0.1:7777
```

## Step 9: Check Job Status

```bash
membra job status JOB_ID --brain http://127.0.0.1:7777
```

## Expected Success Output

You should see logs like:

**Brain Server:**
```
[brain] worker registered: m5-pro-worker role=coder
[brain] worker registered: m1-pro-worker role=reviewer
[brain] job accepted: job-001 (5 tasks)
[brain] assigned task-001 to m5-pro-worker
[brain] assigned task-002 to m1-pro-worker
[brain] m5-pro-worker completed task-001 output_hash=abc...
[brain] m1-pro-worker completed task-002 output_hash=def...
[brain] job finalized: job-001 artifact=xyz...
```

**Workers:**
```
[worker:m5-pro-worker] Claimed task task-001...
[worker:m5-pro-worker] Submitted result for task-001...
[worker:m5-pro-worker] Stats: Tasks completed: 3
```

## Firewall Troubleshooting

If M1 cannot reach M5:

1. **M5 Pro:** System Settings → Network → Firewall
2. Click "Options..."
3. Ensure "Block all incoming connections" is OFF
4. Add Python to allowed apps, OR
5. Temporarily disable firewall for testing:
   ```bash
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
   ```

## Success Metrics

| Metric | Target |
|--------|--------|
| M1 reaches M5 brain | ✅ `curl /workers` returns JSON |
| Both workers register | ✅ Two workers in `/workers` list |
| Job accepted | ✅ Brain returns job ID |
| Tasks assigned | ✅ Each worker gets tasks matching role |
| Results submitted | ✅ Both workers submit results |
| Job finalized | ✅ Brain merges outputs, creates artifact hash |

## Benchmark

After success, run this benchmark:

```bash
python3 examples/lan_two_mac_test.py --brain http://127.0.0.1:7777 --benchmark
```

Compare:
| Setup | Time for 6 tasks |
|-------|-----------------|
| Single Mac (serial) | ~12 minutes |
| Two-Mac MEMBRA | ~7 minutes |

Success is **more jobs completed per hour**, not faster single-token streaming.

## Next Steps

After this works:
1. Add more workers (old MacBook, cloud VM, Raspberry Pi)
2. Assign specific models to specific workers
3. Add Stripe payment for verified artifacts
4. Anchor proof hashes to Solana devnet

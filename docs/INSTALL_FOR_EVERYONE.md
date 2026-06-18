# MIDAS for non-developers

This guide is for people who do not use a terminal every day.

## Will MIDAS run on every computer?

MIDAS is cross-platform, but it is not magic. It needs a recent computer and a
few normal system pieces.

| System | Status | What you need |
|---|---|---|
| Windows 10/11 | Supported | Python 3.11+, internet for first install, browser |
| macOS | Supported | Python 3.11+, internet for first install, browser |
| Linux | Supported | Python 3.11+, internet for first install, browser, keyring/libsecret recommended |
| Old Windows / locked work PC | Not guaranteed | Admin policy or antivirus may block Python/venv/keychain |
| Phone/tablet only | Not supported | MIDAS is a desktop/local agent |

Core MIDAS only needs Python and a browser. Extra features need extra tools:

- Cloud AI: one API key, for example OpenAI, Anthropic, OpenRouter, Groq, or Google.
- Local AI: Ollama installed and running, no API key.
- Video rendering: Node.js, npm/npx, Remotion, and ffmpeg.
- Voice: built-in offline draft works; Edge TTS/Kokoro/Piper/XTTS are optional.
- Docker/MCP/browser automation: optional, detected by the Capabilities page.

MIDAS never installs extra tools silently. It tells you what is missing and asks
for approval before risky or external actions.

## Easiest Windows path

1. Download the ZIP from GitHub or clone the repo.
2. Extract it somewhere simple, for example `Documents\MIDAS`.
3. Open the folder.
4. Double-click `Launch MIDAS.bat`.
5. A black window opens. Keep it open.
6. The first run installs MIDAS into a private `.venv` folder.
7. Your browser opens at the local dashboard.
8. Click `Start`.

If the browser does not open, the black window prints a `Direct link`. Copy it
into your browser.

## Easiest macOS path

1. Download the ZIP from GitHub or clone the repo.
2. Extract it somewhere simple, for example `Documents/MIDAS`.
3. Open the folder.
4. Double-click `Launch MIDAS.command`.
5. If macOS blocks it, open Terminal in the folder and run:

```bash
chmod +x "Launch MIDAS.command" launch-midas.sh
./launch-midas.sh
```

6. Keep the terminal open while using MIDAS.
7. The browser opens at the local dashboard.

## Easiest Linux path

```bash
cd ~/Documents/MIDAS
chmod +x launch-midas.sh
./launch-midas.sh
```

Keep the terminal open while using MIDAS.

## What the user sees after launch

### 1. Local dashboard opens

The URL looks like:

```text
http://127.0.0.1:8765/login?token=...
```

This is local-only. It runs on the user's own computer.

### 2. Start page

The user clicks `Start`.

MIDAS asks for one of two options:

- Use local Ollama if detected.
- Paste one cloud API key.

The user does not need to understand providers. MIDAS detects common key
prefixes and fills the provider choice.

### 3. API key

The user pastes a key in the password box and clicks `Connect`.

MIDAS stores the key in the OS keychain when available. The browser never gets
the key back.

### 4. Channels

The user can connect notifications:

- Telegram
- Discord
- Slack
- WhatsApp
- Email
- SMS

This is optional. The user can click `Skip for now` and still use the dashboard.

### 5. First mission

The user chooses a starter persona or types a niche.

Examples:

- `Montreal dentists`
- `freelance designers`
- `local restaurants`
- `beginner course creators`

Then they click `Run the mission`.

MIDAS researches, drafts, and queues any risky action in `Approvals`.

### 6. Chat

The user clicks `Chat` and can talk normally:

```text
Create a simple offer I can sell this week.
Make a short video script for this offer.
Draft a cold email, but do not send it.
What can you do on this computer for free?
```

## What every beginner must understand

MIDAS has two modes of action:

- Safe read/draft work: it can do it immediately.
- Risky or external work: it creates an approval card first.

Examples that require approval:

- sending an email;
- publishing content;
- creating a Stripe object;
- writing files;
- running code;
- installing or using external tools.

## Best public wording

Use this in public docs:

> Download MIDAS, double-click Launch MIDAS, paste one API key or use local
> Ollama, then talk to the dashboard. MIDAS drafts work automatically, but asks
> before sending, publishing, spending, writing files, or running code.


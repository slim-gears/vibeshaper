# Contributing to VibeShaper

Thanks for helping! Bug reports, new providers, new tools and fixes are all welcome.

## Reporting a bug

Open an [issue](https://github.com/slim-gears/vibeshaper/issues/new/choose) and include:

- what you asked for, and what happened instead;
- the provider and model you used;
- your Fusion version and operating system;
- the relevant part of `vibeshaper.log` (in `%APPDATA%\VibeShaper` on Windows, `~/Library/Application Support/VibeShaper` on macOS). It contains your prompts and the model's replies, so check it before you share it.

## Development environment

### What you need

| | Needed for |
|---|---|
| [Autodesk Fusion](https://www.autodesk.com/products/fusion-360) on Windows or macOS | Running the add-in |
| git | Getting the code |
| Python 3.11 or newer | The tests and the panel preview only. The add-in itself runs on Fusion's own Python. If you have no Python installed, Fusion's works (see [Running the tests](#running-the-tests)). |
| A model: [Ollama](https://ollama.com) with a model that supports tools, or a [Gemini API key](https://aistudio.google.com) (it has a free tier) | Trying anything in Fusion |
| A web browser | Working on the chat panel |
| [Visual Studio Code](https://code.visualstudio.com) with the Python extension | Optional, for stepping through the add-in in Fusion |

The add-in uses only Python's standard library, so there is nothing to install with pip.

### Getting the add-in running

1. Clone the repository. The folder must be named `VibeShaper`, because Fusion expects the folder, `VibeShaper.py` and `VibeShaper.manifest` to share a name.
   ```bash
   git clone https://github.com/slim-gears/vibeshaper.git VibeShaper
   ```
   You can clone it anywhere. Either put it in Fusion's `AddIns` folder (see the [README](README.md#-installation)), or keep it where you like and add it in Fusion with the **+** button in the Add-Ins dialog.
2. In Fusion, open **Utilities → Add-Ins**, select VibeShaper and click **Run**. A VibeShaper button appears under **Solid → Create**.
3. Set up a model: see [Using Local Ollama](README.md#using-local-ollama-recommended-for-privacy) or [Using Google Gemini](README.md#using-google-gemini).
4. After changing code, click **Stop** and then **Run** again. VibeShaper reloads its modules, providers and tools, so you don't need to restart Fusion. Fusion reads the manifest only at startup, though, so restart it if you change that.

### Finding out what happened

- **Text Commands** (in Fusion, **File → View → Show Text Commands**): short messages from the add-in, including errors with tracebacks.
- **`vibeshaper.log`**, in your settings folder (`%APPDATA%\VibeShaper` on Windows, `~/Library/Application Support/VibeShaper` on macOS): every request to the model and its full reply.
- **`last_response.txt`**, in the same folder: the model's most recent reply on its own.
- **Debugging**: in the Add-Ins dialog, choose **Debug** instead of **Run**. Fusion opens Visual Studio Code attached to the add-in, where you can set breakpoints.

### What the tests can't check

The tests run against a simulated Fusion, so they cover the logic but not real geometry. After changing how designs are built (`dsl.py`) or anything that calls the Fusion API, try it in Fusion too. The designs in `examples/` make a quick check: paste one's JSON into the chat and it is built directly, without a model.

## Running the tests

The tests run on plain Python 3.11 or newer, without Fusion:

```bash
python test_dsl.py
```

They use a simulated Fusion and a temporary folder for settings and logs. If you have no Python installed, Fusion's own works: on Windows it's under `%LOCALAPPDATA%\Autodesk\webdeploy\production\<id>\Python\python.exe`.

GitHub runs the same tests on Linux and Windows for every push and pull request.

## Working on the chat panel

The panel (`palette/`) is plain HTML, CSS and JavaScript. You can work on it in a normal browser with a built-in fake backend:

```bash
python -m http.server 8765 --directory palette
```

Then open `http://localhost:8765/index.html?mock&demo` (`mock` uses the fake backend, `demo` fills in a sample chat).

## How the code is organized

| Path | What it does |
|---|---|
| `VibeShaper.py` | The add-in: Fusion commands, the panel bridge, settings, running builds and tools |
| `llm.py` | Talking to the model: system prompt, retries, the tool loop, logging |
| `dsl.py` | Validating the JSON design and building it in Fusion ([DSL_SPEC.md](DSL_SPEC.md)) |
| `chat.py` | Chats, versions and saving them in the document |
| `userdata.py` | Where settings and logs are kept |
| `providers/` | Model provider plugins (Ollama, Gemini) |
| `tools/` | Tool plugins the model can call (design inspection) |
| `palette/` | The chat panel |

### The one rule: the core knows no plugin

Everything specific to a provider or a tool lives in its plugin. The core (`VibeShaper.py`, `llm.py`, `chat.py`, `dsl.py`, `userdata.py`, the registries and the panel) must never name a provider, a provider setting, a tool or a toolkit. A test enforces this.

If a feature differs per provider or per model (thinking, images, tools), add it to the plugin interface (`providers/base.py`, `tools/base.py`) and let plugins report it, rather than checking for a particular provider in the core.

- **New provider**: see [Adding Custom Providers](README.md#-adding-custom-providers).
- **New tools**: see [Adding Tools](README.md#adding-tools).

## Pull requests

- Keep each pull request to one change, and add or update tests for it.
- Make sure `python test_dsl.py` passes.
- Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md) for anything users will notice.
- Code comments and messages should be short and plain.
- Using a coding agent? It should follow [AGENTS.md](AGENTS.md); most agents read it automatically, and `CLAUDE.md` and `GEMINI.md` point to it.

## Releasing (maintainers)

The version is never written by hand. It comes from git tags, and the build writes it into the manifest of the zip ([.github/scripts/version.sh](.github/scripts/version.sh)). The manifest in the repository keeps the placeholder `0.0.0-dev`, which is also what Fusion shows for a cloned copy.

1. Move the **Unreleased** notes in `CHANGELOG.md` under a new version heading, e.g. `## [0.3.0]`, and add its link at the bottom.
2. Commit, then tag and push:
   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```
3. GitHub Actions runs the tests, builds `VibeShaper-0.3.0.zip` with version 0.3.0 in its manifest, and publishes a Release with the changelog section as its notes. A tag like `v0.3.0-beta.1` becomes a pre-release.

Every push to `main` also produces a test build, downloadable under **Artifacts** on that run's page. Its version says how far it is past the last release, e.g. `0.3.0+dev.4.1a2b3c4` (4 commits after v0.3.0).

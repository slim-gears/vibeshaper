# Contributing to VibeShaper

Thanks for helping! Bug reports, new providers, new tools and fixes are all welcome.

## Reporting a bug

Open an [issue](https://github.com/slim-gears/vibeshaper/issues/new/choose) and include:

- what you asked for, and what happened instead;
- the provider and model you used;
- your Fusion version and operating system;
- the relevant part of `vibeshaper.log` (in `%APPDATA%\VibeShaper` on Windows, `~/Library/Application Support/VibeShaper` on macOS). It contains your prompts and the model's replies, so check it before you share it.

## Setting up

1. Clone the repository into Fusion's `AddIns` folder (see the [README](README.md#-installation)). The folder must be named `VibeShaper`.
2. In Fusion, open **Utilities → Add-Ins**, select VibeShaper and click **Run**.
3. After changing code, click **Stop** and then **Run** again. VibeShaper reloads its modules, providers and tools, so you don't need to restart Fusion.

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

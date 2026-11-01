# Changelog

All notable changes to VibeShaper (called PromptCAD up to 0.2.0). The format follows [Keep a Changelog](https://keepachangelog.com/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0]

### Changed
- **Renamed from PromptCAD to VibeShaper.** The add-in folder, its files, the settings folder (`%APPDATA%\VibeShaper`, `~/Library/Application Support/VibeShaper`) and the timeline group names all use the new name. To keep your settings, move them over from the old `PromptCAD` folder. Chats saved in designs by PromptCAD aren't shown.

## [0.2.0]

First public version.

### Added
- **Chat panel** docked in Fusion: describe a part, then refine it in follow-up messages. The model keeps the whole conversation.
- **Regenerate in place**: each chat owns one timeline group, and a new version replaces the previous one in a single undoable step. A failed rebuild leaves the previous version untouched.
- **Versions, JSON and parameters**: restore an earlier version, view or edit a version's JSON and build it, or change a parameter without asking the model.
- **Chats saved in the design**, so you can reopen a file later and keep refining. A chat can be deleted from the chat menu; the parts it built stay in the timeline.
- **Self-healing builds**: build errors go back to the model for a corrected design (up to 5 tries, configurable).
- **Build into a new component or a new body**, per chat.
- **Live streaming** of the model's reasoning, with Stop (Esc) at any time.
- **Pluggable providers**: Ollama (local) and Google Gemini, with model capabilities (images, thinking, tools) shown in the model menu and a per-model Think switch.
- **Design tools**: models that support tool calling can look at the open design (components, bodies, sketches, the timeline, parameters, the selection, distances) before building. Other models get a short text summary instead.
- **Pluggable tools**: toolkits are plugins in `tools/`, like providers.
- Settings and logs are kept in the user's own folder (`%APPDATA%\PromptCAD`, `~/Library/Application Support/PromptCAD`), outside the add-in.

[Unreleased]: https://github.com/slim-gears/vibeshaper/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/slim-gears/vibeshaper/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/slim-gears/vibeshaper/releases/tag/v0.2.0

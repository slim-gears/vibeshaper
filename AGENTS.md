# Guidelines for coding agents

VibeShaper is an Autodesk Fusion add-in that turns a chat with an AI model into a parametric design. These guidelines apply to any coding agent working in this repository. [CONTRIBUTING.md](CONTRIBUTING.md) has the setup, the code map and the release steps; read it first.

## Principles

Each rule has a reason. When a situation isn't covered, follow the reason.

1. **Extend, don't modify.** New behaviour goes in through an extension point: a plugin behind an interface. If a change would make the core know about one particular plugin (its name, its settings, a special case for it), add or widen the interface instead, and let plugins report what they can do.
   *Why:* the core stays stable, and features can be added or removed without touching each other.

2. **Each part owns only its own data.** A plugin sees what it needs and nothing else. Storage, threading and the UI belong to the host code that calls it.
   *Why:* parts stay replaceable and can be tested on their own.

3. **Keep one source for each fact.** Don't copy a value that can be derived (versions, generated files, lists that mirror the code). Derive it at build or run time.
   *Why:* copies drift out of date.

4. **Every behaviour change comes with a test that runs without the host application.** If code can't be tested that way, put a thin layer between it and the host that the tests can replace.
   *Why:* CI is the only reviewer every contributor shares, human or agent.

5. **Enforce important rules with tests, not just words.** When you introduce a rule that matters, add a check that fails when it's broken.
   *Why:* written rules get forgotten; failing tests don't.

6. **Keep changes small and in scope.** Don't rename, reformat or refactor unrelated code in the same change. If you notice something else worth fixing, mention it instead.
   *Why:* small changes are easy to review and to undo.

7. **Add no dependencies without asking.** Use Python's standard library and plain HTML, CSS and JavaScript.
   *Why:* the add-in installs by unzipping a folder; there is no package manager inside Fusion.

8. **Keep secrets and personal data out of the repository, logs, error messages and test files.**
   *Why:* the repository is public, and users attach logs to bug reports.

9. **Write for the user.** UI text, documentation, errors, comments and commit messages are short, plain and specific.

10. **Say what you didn't verify.** If something can only be checked in Fusion, or you're unsure, say so rather than claiming it works. Ask when a decision is the maintainer's to make.

## Facts you'd otherwise get wrong

- **Tests** are one plain script, not pytest: `python test_dsl.py`. It prints `ok` when everything passes and stops at the first failure with a traceback. CI runs it on Python 3.11 and 3.14, on Linux and Windows.
- **Fusion isn't available to the tests.** They use stand-ins for Fusion's API defined in `test_dsl.py`. Anything that builds real geometry must also be tried in Fusion, so say when a change needs that.
- **Fusion's API may only be called on its main thread.** Work that takes time (talking to a model) runs on a worker thread and asks the main thread to act through Fusion custom events.
- **The extension points** are `providers/` (AI model providers), `tools/` (tools the model can call), `features/` (DSL timeline operations), `features/entities/` (sketch entity types), and `shapes/` (ready-made parts that expand into plain DSL steps, discovered from both `.py` `BaseShape` plugins and declarative `.json` macros). Each Python extension point has a base class in its `base.py` and is discovered automatically.
- **The version is never written by hand.** It comes from git tags at build time.
- **User-visible changes** get a line under *Unreleased* in [CHANGELOG.md](CHANGELOG.md).

# Contributing

Thanks for helping. This is a small, independent project, built and tested against one DWARF 3, so reports from other
setups are as useful as code.

## Before you open an issue

- Questions and "is this possible?" go in Discussions, or the **Idea or request** issue form.
- For a bug, use the bug form and attach **Settings → Devices & services → DWARF 3 → ⋮ → Download diagnostics**.
  Diagnostics hide your scope's address and leave out its Wi-Fi details. Still glance through logs and screenshots for
  addresses, coordinates and tokens before posting them.
- Say whether you use **Read-only** or **Full control**, and your relay app version in the second case.

## Working on the code

The integration is in `custom_components/dwarf`, the relay app wrapper in `dwarf3_relay`, and the dashboard card in
`custom_components/dwarf/frontend`. Tests are in `tests`.

```
uv venv --python 3.13
uv pip install pytest-homeassistant-custom-component PyTurboJPEG av numpy ruff
.venv/bin/ruff check .
.venv/bin/python -m pytest -q
```

This is what CI runs. CI also runs `hassfest` and the HACS check, and both must pass with no ignores.

Things to keep in mind:

- **Strings:** keep `strings.json` and `translations/en.json` in step.
- **Behaviour changes:** update the README in the same pull request.
- **No real scope needed for tests:** they use fakes. If you did try the change on a real scope, say which firmware.
- **The card:** say which layout you checked (desktop, tablet, phone) and whether you tried light and dark themes.
- **Small pull requests** that do one thing are easiest to review. For anything big, open an issue or discussion first.

## Releases

Maintainer only. Bump `version` in `custom_components/dwarf/manifest.json`, then push a tag with the same version
(`v0.7.2`). The release workflow refuses a tag that does not match the manifest.

## Licence

By contributing you agree that your work is released under the MIT licence, like the rest of the project. The brand
images in `custom_components/dwarf/brand/` belong to DWARFLAB and are not covered by it.

# Humanize Helper

Humanize Helper is a Windows desktop companion for moving selected text between Microsoft Word and Clever AI Humanizer. It watches for copied text while Word is active, sends that text to the humanizer through a browser extension, and lets you copy the returned text or paste it back into Word.

> **Academic integrity:** This is an AI-assisted rewriting workflow. It does not remove AI involvement, establish human authorship, or guarantee a particular AI-detector result. Do not use it to misrepresent AI-assisted writing as unaided work or to evade institutional rules. Follow your university, journal, and supervisor’s disclosure requirements; verify every claim, quotation, citation, and reference yourself.

## What it does

- Watches the Windows clipboard only when Microsoft Word is the foreground application.
- Opens or reuses a Clever AI Humanizer tab in the selected browser and automates the supported humanization flow.
- Reads the result from the page instead of clicking the website’s clipboard control.
- Shows a floating popup with **Humanize**, **Copy**, **Paste**, and undo actions.
- Provides a dashboard to turn the background helper on or off, check extension connectivity, and open browser extension settings or the extension folder.
- Installs per-user on Windows using the setup wizard; administrator access is not required.

## How it works

1. The desktop helper detects a clipboard change when Word is in the foreground and displays a non-activating popup.
2. The helper runs a WebSocket bridge on `127.0.0.1` with a randomly generated, per-user authentication token.
3. The browser extension connects to that local bridge and opens or reuses a Clever AI Humanizer tab.
4. The extension enters the selected text, requests the humanizer’s output, and sends the result back to the desktop helper.
5. You choose whether to copy the result or paste it into Word. The helper retains the original text for undo.

**Text leaves your computer:** selected text is sent to Clever AI Humanizer by the browser extension. This project is not affiliated with or endorsed by that service. Review its current privacy policy and terms before use. Do not send confidential, personal, unpublished, or otherwise restricted research unless you have permission to share it with that service.

The local bridge binds to loopback (`127.0.0.1`) and uses a randomly generated token stored in the per-user Humanize Helper configuration. The generated `desktop_app/config.json` and `browser_extension/config.js` are intentionally excluded from this public repository.

Screenshots are not included in this release. The existing captures contain research text and browser/account details and have been excluded rather than published.

## Install on Windows

1. Download and run [`SetupWizard/HumanizeHelperSetup.exe`](SetupWizard/HumanizeHelperSetup.exe).
2. Turn on Humanize Helper in the dashboard.
3. Choose Chrome, Edge, or Opera, then open **Open extensions**.
4. Enable Developer mode and choose **Load unpacked**. Select the installed `browser_extension` folder shown by **Show extension folder**.
5. If the extension is already loaded, click **Reload** on its browser extensions page.

Browsers do not allow this installer to silently install an unpublished unpacked extension. The extension must be loaded once by the user. After an update, reload it from the extensions page.

## Requirements

- Windows 10 or later (64-bit recommended)
- Microsoft Word desktop
- Chrome, Microsoft Edge, or Opera
- An account/session with Clever AI Humanizer if required by that service
- Internet access for the humanization request

## Build from source

Install Python 3.10+ and the .NET Framework 4.x C# compiler, then run in PowerShell:

```powershell
.\SetupWizard\build.ps1
```

The build produces `SetupWizard\HumanizeHelperSetup.exe`. It installs the PyInstaller build dependency from `SetupWizard\requirements-build.txt`.

For source development, run the helper from the repository root:

```powershell
python -m desktop_app.app
```

The helper creates the per-user configuration and writes a local `browser_extension\config.js` with a unique token. Do not commit or share that generated file. `browser_extension\config.example.js` is a safe test fixture, not a production credential.

## Tests

Run the mock-browser integration and unit tests on Windows:

```powershell
python -m unittest tests.test_integration_and_failures tests.test_unit
```

`tests.test_live_clever_ai` and `tests.test_word_live` are separate live/manual integration checks. They contact the third-party service or interact with Microsoft Word and are not part of the command above.

## Known limitations

- The extension depends on the third-party site’s page structure and may need updates if that site changes.
- Browser extension loading is a manual step because this is an unpacked extension.
- The project does not guarantee stylistic quality, factual accuracy, originality, detector scores, or compliance with academic policies.
- Keep your own copy of source material and check the returned text carefully before using it.

## Developer

Created by **Thendo Aubrey Nemafhohoni**.

## License

This project is released under the [MIT License](LICENSE).

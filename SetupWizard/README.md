# Humanize Helper Setup Wizard

The finished installer is `HumanizeHelperSetup.exe`. It installs the self-contained Windows app, the Word COM helper, and the browser extension for the current Windows account. The default destination is `%LOCALAPPDATA%\Programs\HumanizeHelper`; administrator access is not required. During an upgrade it closes the previous Humanize Helper app before replacing its files.

The Start menu and desktop shortcuts open a dashboard with an On/Off control. The optional sign-in shortcut starts the helper automatically. The installer also registers an entry in Windows Apps for uninstalling the app; the user's settings are retained when it is removed.

After humanizing, use **Copy** in the floating result window to copy the complete result to the Windows clipboard, or **Paste** to replace the selected text in Word.

## Browser extension setup

The installer copies the unpacked extension into the installation folder. Browser security does not allow this installer to silently install an unpublished unpacked extension. After setup:

1. Turn on the helper in the dashboard and check that it reports the browser extension as connected.
2. Open the extension settings for Chrome, Edge, or Opera.
3. If Humanize Helper Bridge is already installed, click **Reload**. Otherwise, enable Developer mode, select **Load unpacked**, and choose the installed `browser_extension` folder. This version injects the page alert guard directly, so it does not depend on a separate guard file.
4. Keep Developer mode enabled so the unpacked extension remains available.

The installer initializes a per-user authentication token and writes it into both the private settings and the extension configuration before opening the extension folder.

## Build the installer

On 64-bit Windows with Python 3.10+ and the .NET Framework 4.x C# compiler:

```powershell
.\SetupWizard\build.ps1
```

The build installs the PyInstaller build dependency, packages the app as a standalone EXE, stages the extension (excluding generated per-user configuration), embeds the package in the setup wizard, and writes `SetupWizard\HumanizeHelperSetup.exe`.

Developer: Thendo Aubrey Nemafhohoni

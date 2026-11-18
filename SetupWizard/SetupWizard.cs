using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;
using System.Management;

internal static class SetupWizard
{
    private const string ProductName = "Humanize Helper";
    private const string DeveloperName = "Thendo Aubrey Nemafhohoni";
    private static string installDirectory;
    private static TextBox directoryBox;
    private static CheckBox startupCheckBox;
    private static CheckBox dashboardCheckBox;
    private static CheckBox extensionFolderCheckBox;
    private static Label introLabel;
    private static Label folderLabel;
    private static Label extensionNote;
    private static Label statusLabel;
    private static Button installButton;
    private static Button browseButton;
    private static Button cancelButton;
    private static Button finishButton;

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length > 0 && String.Equals(args[0], "--uninstall", StringComparison.OrdinalIgnoreCase))
        {
            return Uninstall();
        }
        if (args.Length > 0 && String.Equals(args[0], "--verify-package", StringComparison.OrdinalIgnoreCase))
        {
            return VerifyPackage();
        }

        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(CreateWizard());
        return 0;
    }

    private static Form CreateWizard()
    {
        Form form = new Form();
        form.Text = "Humanize Helper Setup";
        form.ClientSize = new Size(620, 438);
        form.FormBorderStyle = FormBorderStyle.FixedDialog;
        form.MaximizeBox = false;
        form.MinimizeBox = true;
        form.StartPosition = FormStartPosition.CenterScreen;
        form.BackColor = Color.FromArgb(17, 25, 22);
        form.ForeColor = Color.FromArgb(231, 242, 235);
        form.Font = new Font("Segoe UI", 9F);

        Label title = new Label();
        title.Text = "Install Humanize Helper";
        title.Font = new Font("Segoe UI", 20F, FontStyle.Bold);
        title.ForeColor = Color.White;
        title.Location = new Point(32, 24);
        title.AutoSize = true;
        form.Controls.Add(title);

        introLabel = new Label();
        introLabel.Text = "A private, per-user installation. No administrator access is required.";
        introLabel.ForeColor = Color.FromArgb(160, 185, 171);
        introLabel.Location = new Point(35, 67);
        introLabel.AutoSize = true;
        form.Controls.Add(introLabel);

        folderLabel = new Label();
        folderLabel.Text = "Install location";
        folderLabel.Location = new Point(35, 115);
        folderLabel.AutoSize = true;
        form.Controls.Add(folderLabel);

        directoryBox = new TextBox();
        directoryBox.Location = new Point(35, 140);
        directoryBox.Size = new Size(445, 27);
        directoryBox.Text = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs", "HumanizeHelper");
        form.Controls.Add(directoryBox);

        browseButton = new Button();
        browseButton.Text = "Browse...";
        browseButton.Location = new Point(490, 138);
        browseButton.Size = new Size(92, 29);
        browseButton.Click += delegate
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.Description = "Choose where to install Humanize Helper";
                dialog.SelectedPath = directoryBox.Text;
                if (dialog.ShowDialog(form) == DialogResult.OK)
                    directoryBox.Text = dialog.SelectedPath;
            }
        };
        StyleButton(browseButton, false);
        form.Controls.Add(browseButton);

        startupCheckBox = new CheckBox();
        startupCheckBox.Text = "Start Humanize Helper when I sign in to Windows";
        startupCheckBox.Location = new Point(35, 190);
        startupCheckBox.AutoSize = true;
        startupCheckBox.Checked = true;
        form.Controls.Add(startupCheckBox);

        extensionNote = new Label();
        extensionNote.Text =
            "The browser extension will be installed with the app. For security, your browser will ask you to load it once: turn on Developer mode, choose “Load unpacked”, and select the browser_extension folder.";
        extensionNote.Location = new Point(35, 232);
        extensionNote.Size = new Size(540, 66);
        extensionNote.ForeColor = Color.FromArgb(160, 185, 171);
        extensionNote.Font = new Font("Segoe UI", 9F);
        form.Controls.Add(extensionNote);

        statusLabel = new Label();
        statusLabel.Text = "Created by " + DeveloperName;
        statusLabel.Location = new Point(35, 330);
        statusLabel.Size = new Size(540, 34);
        statusLabel.ForeColor = Color.FromArgb(112, 137, 122);
        form.Controls.Add(statusLabel);

        installButton = new Button();
        installButton.Text = "Install";
        installButton.Location = new Point(381, 374);
        installButton.Size = new Size(112, 38);
        installButton.Click += delegate { Install(form); };
        StyleButton(installButton, true);
        form.Controls.Add(installButton);

        cancelButton = new Button();
        cancelButton.Text = "Cancel";
        cancelButton.Location = new Point(503, 374);
        cancelButton.Size = new Size(79, 38);
        cancelButton.DialogResult = DialogResult.Cancel;
        StyleButton(cancelButton, false);
        form.Controls.Add(cancelButton);
        form.CancelButton = cancelButton;

        dashboardCheckBox = new CheckBox();
        dashboardCheckBox.Text = "Open the dashboard";
        dashboardCheckBox.Checked = true;
        dashboardCheckBox.Visible = false;
        extensionFolderCheckBox = new CheckBox();
        extensionFolderCheckBox.Text = "Open the extension folder after setup";
        extensionFolderCheckBox.Checked = true;
        extensionFolderCheckBox.Visible = false;
        finishButton = new Button();
        finishButton.Text = "Finish";
        finishButton.Location = installButton.Location;
        finishButton.Size = installButton.Size;
        finishButton.Visible = false;
        StyleButton(finishButton, true);
        form.Controls.Add(dashboardCheckBox);
        form.Controls.Add(extensionFolderCheckBox);
        form.Controls.Add(finishButton);

        return form;
    }

    private static void StyleButton(Button button, bool primary)
    {
        button.FlatStyle = FlatStyle.Flat;
        button.FlatAppearance.BorderSize = 0;
        button.BackColor = primary ? Color.FromArgb(53, 189, 131) : Color.FromArgb(39, 54, 47);
        button.ForeColor = primary ? Color.FromArgb(9, 32, 23) : Color.White;
        button.Font = new Font("Segoe UI", 9F, FontStyle.Bold);
        button.Cursor = Cursors.Hand;
    }

    private static void Install(Form form)
    {
        string selectedPath = directoryBox.Text.Trim();
        if (String.IsNullOrWhiteSpace(selectedPath))
        {
            MessageBox.Show(form, "Choose an installation folder.", ProductName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        try
        {
            installDirectory = Path.GetFullPath(selectedPath);
            statusLabel.Text = "Installing files...";
            installButton.Enabled = false;
            Application.DoEvents();

            StopExistingHelper();
            StopLegacyPythonHelper();
            Directory.CreateDirectory(installDirectory);
            ExtractPayload(installDirectory);
            string appPath = Path.Combine(installDirectory, "HumanizeHelper.exe");
            if (!File.Exists(appPath))
                throw new FileNotFoundException("The Humanize Helper application was not found in the installation package.");

            CreateShortcuts(appPath);
            RegisterUninstaller();

            introLabel.Visible = false;
            folderLabel.Visible = false;
            directoryBox.Visible = false;
            browseButton.Visible = false;
            directoryBox.Enabled = false;
            startupCheckBox.Enabled = false;
            startupCheckBox.Visible = false;
            extensionNote.Text =
                "Extension files are updated. If it is already installed, click Reload on your browser’s extensions page. Otherwise turn on Developer mode, choose “Load unpacked”, and select this folder:\n\n" +
                Path.Combine(installDirectory, "browser_extension");
            extensionNote.Location = new Point(35, 100);
            extensionNote.Size = new Size(540, 145);
            installButton.Visible = false;
            statusLabel.Location = new Point(35, 255);
            statusLabel.Text = "Installed successfully. Load the unpacked extension in your browser to finish setup.";
            dashboardCheckBox.Location = new Point(35, 300);
            extensionFolderCheckBox.Location = new Point(35, 330);
            dashboardCheckBox.Visible = true;
            extensionFolderCheckBox.Visible = true;
            finishButton.Visible = true;
            finishButton.Click += delegate
            {
                try
                {
                    using (Process prepare = Process.Start(appPath, "--prepare-extension"))
                    {
                        if (prepare == null || !prepare.WaitForExit(15000) || prepare.ExitCode != 0)
                            throw new InvalidOperationException("The browser extension could not be initialized.");
                    }
                    if (dashboardCheckBox.Checked)
                        Process.Start(appPath, "--dashboard");
                    if (extensionFolderCheckBox.Checked)
                        Process.Start("explorer.exe", "\"" + Path.Combine(installDirectory, "browser_extension") + "\"");
                }
                catch (Exception ex)
                {
                    MessageBox.Show(form, "The installation completed, but a window could not be opened:\n" + ex.Message,
                        ProductName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
                form.Close();
            };
            cancelButton.Visible = false;
        }
        catch (Exception ex)
        {
            installButton.Enabled = true;
            statusLabel.Text = "Installation failed.";
            MessageBox.Show(form, "Humanize Helper could not be installed.\n\n" + ex.Message,
                ProductName + " Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static void StopExistingHelper()
    {
        string dataDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "HumanizeHelper");
        string pidPath = Path.Combine(dataDirectory, "helper.pid");
        if (!File.Exists(pidPath))
            return;

        int processId;
        if (!Int32.TryParse(File.ReadAllText(pidPath).Trim(), out processId))
        {
            File.Delete(pidPath);
            return;
        }

        Process helper;
        try
        {
            helper = Process.GetProcessById(processId);
            if (!String.Equals(helper.ProcessName, "HumanizeHelper", StringComparison.OrdinalIgnoreCase))
            {
                File.Delete(pidPath);
                return;
            }
        }
        catch (ArgumentException)
        {
            File.Delete(pidPath);
            return;
        }

        Directory.CreateDirectory(dataDirectory);
        File.WriteAllText(Path.Combine(dataDirectory, "stop.request"), "stop");
        for (int attempt = 0; attempt < 100; attempt++)
        {
            if (helper.HasExited || !File.Exists(pidPath))
            {
                if (File.Exists(pidPath))
                    File.Delete(pidPath);
                return;
            }
            System.Threading.Thread.Sleep(100);
        }

        throw new TimeoutException(
            "Humanize Helper is still running. Close it from the system tray and run setup again.");
    }

    private static void StopLegacyPythonHelper()
    {
        using (ManagementObjectSearcher searcher = new ManagementObjectSearcher(
            "SELECT ProcessId, Name, CommandLine FROM Win32_Process WHERE Name = 'pythonw.exe' OR Name = 'python.exe'"))
        using (ManagementObjectCollection processes = searcher.Get())
        {
            foreach (ManagementObject entry in processes)
            {
                string commandLine = Convert.ToString(entry["CommandLine"]) ?? "";
                string name = Convert.ToString(entry["Name"]) ?? "";
                string normalizedCommandLine = commandLine.Replace('/', '\\');
                if (!String.Equals(name, "pythonw.exe", StringComparison.OrdinalIgnoreCase) &&
                    !String.Equals(name, "python.exe", StringComparison.OrdinalIgnoreCase))
                    continue;
                string legacyAppPath = FindLegacyAppPath(normalizedCommandLine);
                if (String.IsNullOrEmpty(legacyAppPath))
                    continue;

                int processId = Convert.ToInt32(entry["ProcessId"]);
                Process legacy = Process.GetProcessById(processId);
                legacy.Kill();
                if (!legacy.WaitForExit(5000))
                    throw new TimeoutException("The previous Humanize Helper process could not be stopped for upgrade.");
            }
        }
    }

    private static string FindLegacyAppPath(string commandLine)
    {
        int quoteStart = 0;
        while (quoteStart < commandLine.Length)
        {
            quoteStart = commandLine.IndexOf('"', quoteStart);
            if (quoteStart < 0)
                return null;
            int quoteEnd = commandLine.IndexOf('"', quoteStart + 1);
            if (quoteEnd < 0)
                return null;

            string candidate = commandLine.Substring(quoteStart + 1, quoteEnd - quoteStart - 1);
            quoteStart = quoteEnd + 1;
            if (!candidate.EndsWith("\\desktop_app\\app.py", StringComparison.OrdinalIgnoreCase) ||
                !File.Exists(candidate))
                continue;

            string projectRoot = Directory.GetParent(Directory.GetParent(candidate).FullName).FullName;
            string appConfig = Path.Combine(projectRoot, "desktop_app", "config.py");
            string extensionManifest = Path.Combine(projectRoot, "browser_extension", "manifest.json");
            if (File.Exists(appConfig) && File.Exists(extensionManifest) &&
                File.ReadAllText(appConfig).IndexOf("cleverhumanizer.ai", StringComparison.OrdinalIgnoreCase) >= 0)
                return candidate;
        }
        return null;
    }

    private static void ExtractPayload(string destination)
    {
        Assembly assembly = Assembly.GetExecutingAssembly();
        using (Stream stream = assembly.GetManifestResourceStream("payload.zip"))
        {
            if (stream == null)
                throw new InvalidOperationException("The setup package does not contain its application files.");
            using (ZipArchive archive = new ZipArchive(stream, ZipArchiveMode.Read))
            {
                string root = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string relativePath = entry.FullName.Replace('/', Path.DirectorySeparatorChar)
                        .Replace('\\', Path.DirectorySeparatorChar);
                    string target = Path.GetFullPath(Path.Combine(destination, relativePath));
                    if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("The setup package contains an invalid file path.");
                    if (entry.FullName.EndsWith("/", StringComparison.Ordinal) ||
                        entry.FullName.EndsWith("\\", StringComparison.Ordinal))
                    {
                        Directory.CreateDirectory(target);
                        continue;
                    }
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    using (Stream source = entry.Open())
                    using (FileStream output = File.Create(target))
                        source.CopyTo(output);
                }
            }
        }
    }

    private static int VerifyPackage()
    {
        Assembly assembly = Assembly.GetExecutingAssembly();
        using (Stream stream = assembly.GetManifestResourceStream("payload.zip"))
        {
            if (stream == null)
                return 1;
            using (ZipArchive archive = new ZipArchive(stream, ZipArchiveMode.Read))
            {
                bool hasApplication = false;
                bool hasWordHelper = false;
                bool hasExtensionManifest = false;
                bool hasGeneratedConfig = false;
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string name = entry.FullName.Replace('\\', '/');
                    if (name == "HumanizeHelper.exe") hasApplication = true;
                    if (name == "word_com_helper.exe") hasWordHelper = true;
                    if (name == "browser_extension/manifest.json") hasExtensionManifest = true;
                    if (name == "browser_extension/config.js") hasGeneratedConfig = true;
                }
                return hasApplication && hasWordHelper && hasExtensionManifest && !hasGeneratedConfig ? 0 : 1;
            }
        }
    }

    private static void CreateShortcuts(string appPath)
    {
        string startMenu = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Humanize Helper");
        Directory.CreateDirectory(startMenu);
        CreateShortcut(Path.Combine(startMenu, "Humanize Helper.lnk"), appPath, "--dashboard");
        string desktopShortcut = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Humanize Helper.lnk");
        CreateShortcut(desktopShortcut, appPath, "--dashboard");

        string uninstaller = Path.Combine(installDirectory, "Uninstall.exe");
        File.Copy(Application.ExecutablePath, uninstaller, true);
        CreateShortcut(Path.Combine(startMenu, "Uninstall Humanize Helper.lnk"), uninstaller, "--uninstall");

        string startupShortcut = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Startup), "Humanize Helper.lnk");
        if (startupCheckBox.Checked)
            CreateShortcut(startupShortcut, appPath, "");
        else if (File.Exists(startupShortcut))
            File.Delete(startupShortcut);
    }

    private static void CreateShortcut(string shortcutPath, string target, string arguments)
    {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType == null)
            throw new InvalidOperationException("Windows Script Host is unavailable, so shortcuts could not be created.");
        object shell = Activator.CreateInstance(shellType);
        object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell,
            new object[] { shortcutPath });
        Type shortcutType = shortcut.GetType();
        shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { target });
        shortcutType.InvokeMember("Arguments", BindingFlags.SetProperty, null, shortcut, new object[] { arguments });
        shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut,
            new object[] { installDirectory });
        shortcutType.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut, new object[] { ProductName });
        shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
    }

    private static void RegisterUninstaller()
    {
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(
            @"Software\Microsoft\Windows\CurrentVersion\Uninstall\HumanizeHelper"))
        {
            key.SetValue("DisplayName", ProductName);
            key.SetValue("DisplayVersion", "1.0.3");
            key.SetValue("Publisher", DeveloperName);
            key.SetValue("InstallLocation", installDirectory);
            key.SetValue("UninstallString", "\"" + Path.Combine(installDirectory, "Uninstall.exe") + "\" --uninstall");
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        }
    }

    private static int Uninstall()
    {
        string directory = Path.GetDirectoryName(Application.ExecutablePath);
        DialogResult answer = MessageBox.Show(
            "Remove Humanize Helper from this Windows account?\n\nYour settings will be kept.",
            "Uninstall Humanize Helper", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
        if (answer != DialogResult.Yes)
            return 0;

        string dataDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "HumanizeHelper");
        Directory.CreateDirectory(dataDirectory);
        File.WriteAllText(Path.Combine(dataDirectory, "stop.request"), "stop");
        string pidPath = Path.Combine(dataDirectory, "helper.pid");
        for (int i = 0; i < 50 && File.Exists(pidPath); i++)
            System.Threading.Thread.Sleep(100);

        DeleteIfExists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup), "Humanize Helper.lnk"));
        DeleteIfExists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Humanize Helper.lnk"));
        DeleteDirectoryIfExists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Humanize Helper"));
        using (RegistryKey key = Registry.CurrentUser.OpenSubKey(
            @"Software\Microsoft\Windows\CurrentVersion\Uninstall", true))
            if (key != null)
                key.DeleteSubKeyTree("HumanizeHelper", false);

        string escaped = directory.Replace("'", "''");
        ProcessStartInfo cleanup = new ProcessStartInfo();
        cleanup.FileName = "powershell.exe";
        cleanup.Arguments = "-NoProfile -WindowStyle Hidden -Command \"Start-Sleep -Seconds 2; Remove-Item -LiteralPath '" +
            escaped + "' -Recurse -Force\"";
        cleanup.CreateNoWindow = true;
        cleanup.UseShellExecute = false;
        Process.Start(cleanup);
        return 0;
    }

    private static void DeleteIfExists(string path)
    {
        if (File.Exists(path))
            File.Delete(path);
    }

    private static void DeleteDirectoryIfExists(string path)
    {
        if (Directory.Exists(path))
            Directory.Delete(path, true);
    }
}

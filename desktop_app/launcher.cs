using System;
using System.Diagnostics;
using System.IO;
using System.Management;
using System.Windows.Forms;

class HumanizeHelperLauncher
{
    static void StopExistingInstances()
    {
        try
        {
            using (var searcher = new ManagementObjectSearcher(
                "SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'pythonw.exe' OR Name = 'python.exe'"))
            {
                foreach (ManagementObject obj in searcher.Get())
                {
                    string cmd = (obj["CommandLine"] ?? "").ToString();
                    if (cmd.IndexOf("desktop_app", StringComparison.OrdinalIgnoreCase) >= 0 &&
                        cmd.IndexOf("app.py", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        int pid = Convert.ToInt32(obj["ProcessId"]);
                        try
                        {
                            Process.GetProcessById(pid).Kill();
                        }
                        catch { }
                    }
                }
            }
        }
        catch { }
    }

    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            StopExistingInstances();
            System.Threading.Thread.Sleep(150);

            string exeDir = AppDomain.CurrentDomain.BaseDirectory;
            string appPy = Path.Combine(exeDir, "app.py");
            if (!File.Exists(appPy))
            {
                appPy = Path.Combine(exeDir, "desktop_app", "app.py");
            }
            if (!File.Exists(appPy))
            {
                MessageBox.Show(
                    "Could not find desktop_app\\app.py next to HumanizeHelper.exe.",
                    "Humanize Helper Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return 1;
            }

            string pythonw = @"C:\Program Files\IBM\SPSS Statistics\Python3\pythonw.exe";
            if (!File.Exists(pythonw))
            {
                pythonw = "pythonw.exe";
            }

            string workDir = Path.GetDirectoryName(Path.GetDirectoryName(Path.GetFullPath(appPy)));
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = pythonw,
                Arguments = "\"" + appPy + "\"",
                WorkingDirectory = workDir,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            Process.Start(psi);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "Failed to start Humanize Helper: " + ex.Message,
                "Humanize Helper Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
    }
}

using System;
using System.Runtime.InteropServices;
using System.Text;

class WordComHelper
{
    [DllImport("user32.dll")]
    static extern bool SetForegroundWindow(IntPtr hWnd);

    static string EscapeJson(string s)
    {
        if (s == null) return "";
        return s.Replace("\\", "\\\\")
                .Replace("\"", "\\\"")
                .Replace("\r", "\\r")
                .Replace("\n", "\\n")
                .Replace("\t", "\\t");
    }

    static int Main(string[] args)
    {
        if (args.Length == 0)
        {
            // If user double-clicked word_com_helper.exe directly in Explorer, start the GUI app
            try
            {
                string exeDir = AppDomain.CurrentDomain.BaseDirectory;
                string appPy = System.IO.Path.Combine(exeDir, "app.py");
                string pythonw = @"C:\Program Files\IBM\SPSS Statistics\Python3\pythonw.exe";
                System.Diagnostics.ProcessStartInfo psi = new System.Diagnostics.ProcessStartInfo
                {
                    FileName = pythonw,
                    Arguments = "\"" + appPy + "\"",
                    WorkingDirectory = System.IO.Path.GetDirectoryName(exeDir.TrimEnd('\\')),
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                System.Diagnostics.Process.Start(psi);
            }
            catch { }
            return 0;
        }
        Console.OutputEncoding = Encoding.UTF8;
        Console.InputEncoding = Encoding.UTF8;
        string cmd = args[0].ToLowerInvariant();

        dynamic word = null;
        try
        {
            word = Marshal.GetActiveObject("Word.Application");
        }
        catch
        {
            Console.WriteLine("{\"ok\":false,\"error\":\"WORD_NOT_RUNNING\"}");
            return 0;
        }

        try
        {
            int docCount = (int)word.Documents.Count;
            if (docCount == 0)
            {
                Console.WriteLine("{\"ok\":false,\"error\":\"NO_OPEN_DOCUMENT\"}");
                return 0;
            }

            dynamic win = word.ActiveWindow;
            dynamic sel = win.Selection;
            int hwnd = 0;
            try { hwnd = (int)win.Hwnd; } catch { }

            if (cmd == "status")
            {
                string selText = "";
                int start = 0, end = 0;
                string fontName = "";
                float fontSize = 0f;
                try
                {
                    selText = (string)sel.Text ?? "";
                    start = (int)sel.Start;
                    end = (int)sel.End;
                    fontName = (string)sel.Font.Name ?? "";
                    fontSize = (float)sel.Font.Size;
                }
                catch { }

                Console.WriteLine(
                    "{\"ok\":true,\"hwnd\":" + hwnd +
                    ",\"start\":" + start +
                    ",\"end\":" + end +
                    ",\"fontName\":\"" + EscapeJson(fontName) + "\"" +
                    ",\"fontSize\":" + fontSize.ToString(System.Globalization.CultureInfo.InvariantCulture) +
                    ",\"selectedText\":\"" + EscapeJson(selText) + "\"}"
                );
                return 0;
            }
            else if (cmd == "verify_or_paste")
            {
                // Stdin contains JSON or raw text: first line expected original, rest is humanized text
                string expectedText = Console.In.ReadToEnd();
                try { word.Activate(); } catch { }
                if (hwnd != 0) { try { SetForegroundWindow((IntPtr)hwnd); } catch { } }

                string beforeFont = "";
                float beforeSize = 0f;
                int selStart = (int)sel.Start;
                int selEnd = (int)sel.End;
                try
                {
                    beforeFont = (string)sel.Font.Name ?? "";
                    beforeSize = (float)sel.Font.Size;
                }
                catch { }

                // Check if Ctrl+V already replaced the selection; if selection is still the original highlight,
                // execute Word's native PasteAndFormat(wdFormatPlainText = 22) from the clipboard.
                dynamic doc = word.ActiveDocument;
                string currentDocText = (string)doc.Content.Text ?? "";
                string normalizedExpected = (expectedText ?? "").Replace("\r\n", "\r").Trim();

                bool alreadyInDoc = normalizedExpected.Length > 0 && currentDocText.Contains(normalizedExpected);
                if (!alreadyInDoc)
                {
                    try
                    {
                        // wdFormatPlainText = 22 ("Keep Text Only (A)")
                        sel.PasteAndFormat(22);
                    }
                    catch
                    {
                        sel.TypeText(expectedText);
                    }
                }

                // Inspect post-paste range formatting and content
                int newPos = (int)sel.End;
                int checkStart = Math.Max(0, selStart);
                int checkEnd = Math.Max(checkStart, newPos);
                dynamic checkRange = doc.Range(checkStart, checkEnd);
                string afterText = (string)checkRange.Text ?? "";
                string afterFont = "";
                float afterSize = 0f;
                try
                {
                    afterFont = (string)checkRange.Font.Name ?? "";
                    afterSize = (float)checkRange.Font.Size;
                }
                catch { }

                bool fontMismatch = (!string.IsNullOrEmpty(beforeFont) && !string.IsNullOrEmpty(afterFont) && beforeFont != afterFont)
                                    || (beforeSize > 0 && afterSize > 0 && Math.Abs(beforeSize - afterSize) > 0.5f);

                Console.WriteLine(
                    "{\"ok\":true,\"hwnd\":" + hwnd +
                    ",\"replacedText\":\"" + EscapeJson(afterText) + "\"" +
                    ",\"beforeFont\":\"" + EscapeJson(beforeFont) + "\"" +
                    ",\"afterFont\":\"" + EscapeJson(afterFont) + "\"" +
                    ",\"beforeSize\":" + beforeSize.ToString(System.Globalization.CultureInfo.InvariantCulture) +
                    ",\"afterSize\":" + afterSize.ToString(System.Globalization.CultureInfo.InvariantCulture) +
                    ",\"formattingWarning\":" + (fontMismatch ? "true" : "false") + "}"
                );
                return 0;
            }
            else if (cmd == "verify_or_undo")
            {
                string originalText = Console.In.ReadToEnd();
                try { word.Activate(); } catch { }
                if (hwnd != 0) { try { SetForegroundWindow((IntPtr)hwnd); } catch { } }

                dynamic doc = word.ActiveDocument;
                string currentDocText = (string)doc.Content.Text ?? "";
                string normalizedOrig = (originalText ?? "").Replace("\r\n", "\r").Trim();

                if (normalizedOrig.Length > 0 && !currentDocText.Contains(normalizedOrig))
                {
                    doc.Undo(1);
                }

                string updatedDocText = (string)doc.Content.Text ?? "";
                bool restored = normalizedOrig.Length == 0 || updatedDocText.Contains(normalizedOrig);
                Console.WriteLine(
                    "{\"ok\":" + (restored ? "true" : "false") +
                    ",\"hwnd\":" + hwnd +
                    ",\"restored\":" + (restored ? "true" : "false") + "}"
                );
                return 0;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("{\"ok\":false,\"error\":\"" + EscapeJson(ex.Message) + "\"}");
        }
        return 0;
    }
}


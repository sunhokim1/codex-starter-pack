using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace StarterManager
{
    // The only diagnostic dependencies are a private fixture settings file and this fake operation.
    // Never construct CoreOperation, HttpsTransport, PowerShellInstaller or WindowsActivityGuard here.
    public static class AppDiagnostics
    {
        static int checks;
        static string failedCheck;
        // DoEvents owns a temporary message loop and can uninstall WinForms' ambient
        // synchronization context on exit. Keep the diagnostic STA context across pumps,
        // as the production Application.Run loop does for the lifetime of the app.
        static void Events()
        {
            var context = SynchronizationContext.Current;
            try { Application.DoEvents(); }
            finally { SynchronizationContext.SetSynchronizationContext(context); }
        }
        static void Assert(bool value) { Assert(value, "상태 검증"); }
        static void Assert(bool value, string name) { checks++; if (!value) { failedCheck = name; throw new Exception("진단 실패"); } }
        sealed class FixtureOperation : IManagerOperation, IDisposable
        {
            public int Calls;
            public Phase Phase = Phase.Checking;
            public bool Cancelable = true, Fail, Unexpected;
            public readonly ManualResetEvent Entered = new ManualResetEvent(false), Release = new ManualResetEvent(false);
            public Result Run(string target, CancellationToken cancel, Action<Progress> report)
            {
                Interlocked.Increment(ref Calls);
                report(new Progress(Phase, "격리된 진단 작업입니다.", Cancelable)); Entered.Set();
                if (Cancelable) WaitHandle.WaitAny(new[] { Release, cancel.WaitHandle }); else Release.WaitOne();
                if (Cancelable) cancel.ThrowIfCancellationRequested();
                if (Unexpected) throw new IOException("fixture-secret-do-not-display");
                if (Fail) throw new ManagerException("격리된 오류입니다. 다시 확인해 주세요.");
                return new Result { Decision = Decision.Current, Version = "0.3.3", Message = "격리된 확인을 완료했습니다." };
            }
            public void Dispose() { Release.Dispose(); Entered.Dispose(); }
        }
        static void Pump(Func<bool> condition)
        {
            var timeout = Stopwatch.StartNew();
            while (!condition())
            {
                if (timeout.ElapsedMilliseconds > 10000) throw new Exception("진단 시간 초과");
                Events(); Thread.Sleep(5);
            }
            Events();
        }
        static int CountControls(Control root)
        {
            int count = 1;
            foreach (Control child in root.Controls) { Assert(child.IsHandleCreated, "컨트롤 생성: " + child.GetType().Name); count += CountControls(child); }
            return count;
        }
        static void SettingsTests(string fixture, string project)
        {
            string path = Path.Combine(fixture, "settings.json");
            var settings = new AppSettings(path); string notice;
            Assert(settings.Load(out notice) == null && notice == null);
            settings.Save(project); Assert(settings.Load(out notice) == project && notice == null);
            settings.Save(project); Assert(Directory.GetFiles(fixture, "*.manager-*").Length == 0);
            File.WriteAllText(path, "broken"); Assert(settings.Load(out notice) == null && notice != null);
            File.WriteAllText(path, "{\"schema\":2,\"target\":\"hidden\"}"); Assert(settings.Load(out notice) == null && notice != null);
            File.WriteAllText(path, Data.Json(new { schema = 1, target = "relative" })); Assert(settings.Load(out notice) == null);
            settings.Save(project);
            string moved = project + "-moved"; Directory.Move(project, moved);
            Assert(settings.Load(out notice) == null && notice != null); Directory.Move(moved, project);
            File.Delete(path); Directory.CreateDirectory(path);
            Assert(settings.Load(out notice) == null && notice != null);
            bool failed = false; try { settings.Save(project); } catch { failed = true; } Assert(failed);
            Directory.Delete(path); settings.Save(project);
            string original = File.ReadAllText(path);
            failed = false; try { settings.Save(Path.GetPathRoot(project)); } catch { failed = true; }
            Assert(failed && File.ReadAllText(path) == original);
        }
        static void Smoke(AppSettings settings)
        {
            using (var operation = new FixtureOperation())
            using (var form = new ManagerForm(settings, () => operation, false))
            {
                form.Show(); Events();
                Assert(CountControls(form) >= 13, "컨트롤 수");
                Assert(form.Visible && !form.Busy && form.TargetChangeEnabled, "대기 화면");
                Assert(operation.Calls == 0 && form.StatusText == "대기 중", "자동 설치 차단");
                form.Close(); Assert(form.IsDisposed, "폼 해제");
            }
        }
        static void LifecycleTests(AppSettings settings)
        {
            // Remembered target starts automatically, work runs off the STA, duplicate requests are ignored.
            using (var op = new FixtureOperation())
            using (var form = new ManagerForm(settings, () => op, true))
            {
                form.Show(); Pump(() => op.Entered.WaitOne(0) && form.StatusText == "최신 버전 확인 중");
                Assert(form.Busy && !form.TargetChangeEnabled, "작업 중 폴더 변경 차단"); form.StartCheck(); Assert(op.Calls == 1, "중복 요청 차단");
                form.RequestStop(false); Pump(() => !form.Busy);
                Assert(form.StatusText == "취소 완료" && form.TargetChangeEnabled, "취소 후 대기");
                op.Release.Set(); form.StartCheck(); Pump(() => !form.Busy);
                Assert(op.Calls == 2 && form.StatusText == "완료 · 스타터팩 0.3.3", "재시도 완료: " + form.StatusText);
                form.Close();
            }
            // Each irreversible phase must keep the real Form alive until its worker finishes.
            foreach (var phase in new[] { Phase.Recovering, Phase.Preparing, Phase.Installing, Phase.Publishing })
            using (var op = new FixtureOperation { Phase = phase, Cancelable = false })
            using (var form = new ManagerForm(settings, () => op, true))
            {
                form.Show(); Pump(() => op.Entered.WaitOne(0) && form.HistoryText.Length > 0);
                form.Close(); Events();
                Assert(form.Busy && form.ClosePending && !form.IsDisposed && !form.TargetChangeEnabled);
                op.Release.Set(); Pump(() => form.IsDisposed); Assert(op.Calls == 1);
            }
            using (var op = new FixtureOperation { Fail = true, Cancelable = false, Phase = Phase.Installing })
            using (var form = new ManagerForm(settings, () => op, true))
            {
                form.Show(); Pump(() => op.Entered.WaitOne(0)); form.Close(); op.Release.Set(); Pump(() => !form.Busy);
                Assert(!form.IsDisposed && !form.ClosePending && form.StatusText.Contains("오류"));
                op.Fail = false; form.StartCheck(); Pump(() => !form.Busy);
                Assert(form.StatusText.Contains("완료")); form.Close();
            }
            using (var op = new FixtureOperation { Unexpected = true })
            using (var form = new ManagerForm(settings, () => op, true))
            {
                op.Release.Set(); form.Show(); Pump(() => !form.Busy);
                Assert(form.StatusText.Contains("오류") && !form.HistoryText.Contains("fixture-secret"));
                foreach (Control container in form.Controls) foreach (Control control in container.Controls) Assert(!control.Text.Contains("fixture-secret"));
                form.Close();
            }
        }
        public static int Run(string mode, string fixtureRoot)
        {
            checks = 0; string fixture = null, root = null;
            try
            {
                // Caller must explicitly supply an existing root. Never infer a user profile path.
                root = Path.GetFullPath(fixtureRoot); new FileStore().Safe(root);
                if (!Directory.Exists(root)) return 2;
                fixture = Path.Combine(root, "g-" + Guid.NewGuid().ToString("N").Substring(0, 8));
                Directory.CreateDirectory(fixture);
                string project = Path.Combine(fixture, "한글 ' $ & []"); Directory.CreateDirectory(project);
                var settings = new AppSettings(Path.Combine(fixture, "settings.json"));
                // Keep one STA window alive across test forms so WinForms retains its UI context.
                using (var anchor = new Form { ShowInTaskbar = false, Opacity = 0 })
                {
                    anchor.Show();
                    SynchronizationContext.SetSynchronizationContext(new WindowsFormsSynchronizationContext());
                    Events();
                    if (mode == "--self-test") { SettingsTests(fixture, project); LifecycleTests(settings); }
                    else settings.Save(project);
                    Smoke(settings); anchor.Close();
                }
                Assert(Directory.GetFileSystemEntries(project).Length == 0);
                new FileStore().Write(Path.Combine(root, mode.Substring(2) + "-result.json"), Data.Utf8(Data.Json(new { status = "passed", assertions = checks, network = false, realInstallation = false, userSettings = false, actualForm = true })));
                return 0;
            }
            catch (Exception error)
            {
                // No raw exception text: even diagnostic failures must not disclose file contents.
                if (root != null && Directory.Exists(root))
                    new FileStore().Write(Path.Combine(root, mode.Substring(2) + "-result.json"), Data.Utf8(Data.Json(new { status = "failed", assertions = checks, category = error.GetType().Name, check = failedCheck })));
                return 1;
            }
            finally
            {
                if (fixture != null && fixture.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) Directory.Delete(fixture, true);
            }
        }
    }
}

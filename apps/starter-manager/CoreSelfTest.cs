using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;

namespace StarterManager
{
    public static class CoreSelfTest
    {
        static int checks;
        static void Assert(bool value, string name) { checks++; if (!value) throw new Exception("fixture 실패: " + name); }
        static void Throws(Action action, string name)
        { bool caught = false; try { action(); } catch (Exception) { caught = true; } Assert(caught, name); }
        sealed class Network : ITransport
        {
            public int Resolves; public bool Fail, Mismatch; public List<string> Urls = new List<string>();
            public static readonly string Commit = new string('a', 40);
            public static readonly byte[] Source = Data.Utf8("fixture immutable source");
            public byte[] Get(string url, int limit, CancellationToken cancellation)
            {
                HttpsTransport.Validate(url); Urls.Add(url); cancellation.ThrowIfCancellationRequested();
                if (Fail) throw new ManagerException("fixture network failure");
                if (url.Contains("api.github.com")) { Resolves++; return Data.Utf8("{\"sha\":\"" + Commit + "\"}"); }
                if (url == "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/" + Commit + "/.ai/config.yaml") return Data.Utf8("starter:\n  version: '0.3.3'\n");
                if (url.EndsWith("release.json"))
                {
                    var hashes = new Dictionary<string, string>();
                    foreach (var name in new[] { "assets/sev/sev_service.py", "assets/runner/run.py", "assets/runner/project.py", "assets/runner/runtime_safety.py" }) hashes.Add("universal-ai-starter/" + name, Data.Hash(Source));
                    foreach (var name in Transaction.CoreFiles.Where(n => n != ".ai/sev.json")) hashes.Add("universal-ai-starter/assets/starter/" + name, Data.Hash(Data.Utf8("fixture " + name)));
                    return Data.Utf8(Data.Json(new { version = Mismatch ? "0.3.2" : "0.3.3", sha256 = hashes }));
                }
                const string starter = "/assets/starter/";
                if (url.Contains(starter)) return Data.Utf8("fixture " + url.Substring(url.IndexOf(starter, StringComparison.Ordinal) + starter.Length));
                return Data.Utf8("# fixture installer never executed");
            }
        }
        sealed class Idle : IActivityGuard
        {
            public bool Busy; public int Calls;
            public void AssertIdle(string target) { Calls++; if (Busy) throw new ManagerException("fixture busy"); }
        }
        sealed class Installer : IInstaller
        {
            readonly FileStore files; readonly string fixture;
            public int Calls; public bool Fail, Incomplete, ChangeSettings; public Action During;
            public Installer(FileStore files, string fixture) { this.files = files; this.fixture = fixture; }
            public void Install(string script, string stage, Snapshot snapshot, string work)
            {
                Calls++; if (During != null) During();
                foreach (var name in Transaction.CoreFiles)
                {
                    var path = Path.Combine(stage, name);
                    if (files.Read(path) == null) files.Write(path, Data.Utf8("fixture " + name));
                }
                foreach (var name in new[] { "AGENTS.md", ".gitignore" })
                {
                    var path = Path.Combine(stage, name);
                    string old = Data.Decode(files.Read(path));
                    string block = name == "AGENTS.md" ? "<!-- starter-sev:start -->\nfixture\n<!-- starter-sev:end -->" : "# starter-private:start\nfixture\n# starter-private:end";
                    string begin = name == "AGENTS.md" ? "<!-- starter-sev:start -->" : "# starter-private:start";
                    string end = name == "AGENTS.md" ? "<!-- starter-sev:end -->" : "# starter-private:end";
                    int first = old.IndexOf(begin, StringComparison.Ordinal), last = old.IndexOf(end, StringComparison.Ordinal);
                    string merged = first < 0 ? old.TrimEnd() + "\n\n" + block + "\n" : old.Substring(0, first) + block + old.Substring(last + end.Length);
                    files.Write(path, Data.Utf8(merged));
                }
                var deployment = Path.Combine(fixture, "r-" + Guid.NewGuid().ToString("N").Substring(0, 8)); files.MakeDirectory(deployment);
                var config = new Dictionary<string, object> { { "version", "0.3.3" }, { "deployment", deployment }, { "skills", Path.Combine(fixture, "skills") } };
                files.MakeDirectory((string)config["skills"]);
                var paths = new Dictionary<string, string> { { "python", "venv/Scripts/python.exe" }, { "service", "sev_service.py" }, { "state", "service.json" }, { "runner", "runner/run.py" }, { "project_runner", "runner/project.py" } };
                foreach (var pair in paths)
                {
                    var path = Path.Combine(deployment, pair.Value); config.Add(pair.Key, path);
                    files.Write(path, pair.Key == "state" ? Data.Utf8("{\"port\":12345,\"pid\":42,\"token\":\"fixture-only\"}") : Network.Source);
                }
                files.Write(Path.Combine(deployment, "runtime_safety.py"), Network.Source);
                files.Write(Path.Combine(deployment, "runner/runtime_safety.py"), Network.Source);
                if (Incomplete) files.Delete((string)config["runner"]);
                if (ChangeSettings) files.Write(Path.Combine(stage, ".ai/models.yaml"), Data.Utf8("should be blocked"));
                files.Write(Path.Combine(stage, ".ai/sev.json"), Data.Utf8(Data.Json(config)));
                files.Write(Path.Combine(stage, ".ai/installation.lock"), Data.Utf8("0"));
                if (Fail) throw new ManagerException("fixture installer failure");
            }
        }
        sealed class FaultFiles : FileStore
        {
            public string FailPath; public bool Armed, AfterWrite;
            public override void Write(string path, byte[] bytes)
            {
                if (Armed && path == FailPath)
                {
                    Armed = false;
                    if (AfterWrite) base.Write(path, bytes);
                    throw new IOException("fixture publication interruption");
                }
                base.Write(path, bytes);
            }
        }
        static string Project(string root, string name) { var path = Path.Combine(root, name); Directory.CreateDirectory(path); return path; }
        static Result Run(FileStore files, Network network, Installer installer, Idle idle, string project, string root)
        { return new ManagerCore(files, network, installer, idle, Path.Combine(root, "locks")).Run(project, CancellationToken.None, null); }
        public static int Execute(string root)
        {
            root = Path.GetFullPath(root); Directory.CreateDirectory(root);
            string fixture = Path.Combine(root, "m-" + Guid.NewGuid().ToString("N").Substring(0, 8)); Directory.CreateDirectory(fixture);
            try
            {
                var files = new FaultFiles(); var network = new Network(); var installer = new Installer(files, fixture); var idle = new Idle();
                var project = Project(fixture, "한글 ' $ & [프로젝트]");
                var other = Project(fixture, "other"); File.WriteAllText(Path.Combine(other, "keep.txt"), "other-project");
                Assert(Data.Version("0.10.0") > Data.Version("0.9.9"), "numeric version");
                Throws(() => Data.Version("0.3.3-preview"), "unknown version fails closed");
                var result = Run(files, network, installer, idle, project, fixture);
                Assert(result.Changed && result.Decision == Decision.Missing, "missing and special path");
                Assert(network.Resolves == 1 && network.Urls.Where(u => !u.Contains("api.github.com")).All(u => u.Contains(Network.Commit)), "one immutable snapshot");
                Assert(!Directory.Exists(Path.Combine(project, ".ai/starter-manager/stage")), "stage cleanup");
                var original = File.ReadAllBytes(Path.Combine(project, ".ai/sev.json"));
                int calls = installer.Calls;
                Assert(Run(files, network, installer, idle, project, fixture).Decision == Decision.Current && installer.Calls == calls, "same healthy skipped");
                var config = Data.Parse(Data.Decode(original));
                files.Delete(Data.Text(config, "runner"));
                Assert(Run(files, network, installer, idle, project, fixture).Decision == Decision.Repair, "broken runtime repaired");
                original = files.Read(Path.Combine(project, ".ai/sev.json"));
                config = Data.Parse(Data.Decode(original)); config["version"] = "0.3.2";
                files.Write(Path.Combine(project, ".ai/sev.json"), Data.Utf8(Data.Json(config)));
                Assert(Run(files, network, installer, idle, project, fixture).Decision == Decision.Update, "older version updated");
                original = files.Read(Path.Combine(project, ".ai/sev.json"));
                config = Data.Parse(Data.Decode(original)); config["version"] = "9.0.0";
                files.Write(Path.Combine(project, ".ai/sev.json"), Data.Utf8(Data.Json(config))); calls = installer.Calls;
                Assert(Run(files, network, installer, idle, project, fixture).Decision == Decision.Newer && calls == installer.Calls, "no downgrade including broken newer");
                files.Write(Path.Combine(project, ".ai/sev.json"), original);
                network.Fail = true;
                Throws(() => Run(files, network, installer, idle, project, fixture), "network failure"); network.Fail = false;
                Assert(Data.Hash(original) == Data.Hash(files.Read(Path.Combine(project, ".ai/sev.json"))), "network preserves connection");
                network.Mismatch = true; Throws(() => Run(files, network, installer, idle, project, fixture), "metadata mismatch"); network.Mismatch = false;
                idle.Busy = true; Throws(() => Run(files, network, installer, idle, project, fixture), "active workflow"); idle.Busy = false;
                var invalid = Project(fixture, "unknown-version"); files.MakeDirectory(Path.Combine(invalid, ".ai"));
                files.Write(Path.Combine(invalid, ".ai/sev.json"), Data.Utf8("{}"));
                Throws(() => Run(files, network, installer, idle, invalid, fixture), "ambiguous existing config no overwrite");
                var failure = Project(fixture, "installer-failure"); installer.Fail = true;
                Throws(() => Run(files, network, installer, idle, failure, fixture), "installer failure"); installer.Fail = false;
                Assert(files.Read(Path.Combine(failure, "AGENTS.md")) == null && files.Read(Path.Combine(failure, ".ai/sev.json")) == null, "stage failure target unchanged");
                installer.Incomplete = true;
                Throws(() => Run(files, network, installer, idle, failure, fixture), "incomplete installation"); installer.Incomplete = false;
                Assert(files.Read(Path.Combine(failure, ".ai/sev.json")) == null, "incomplete install never linked");
                var concurrent = Project(fixture, "concurrent");
                installer.During = () => files.Write(Path.Combine(concurrent, "AGENTS.md"), Data.Utf8("user edit during install"));
                Throws(() => Run(files, network, installer, idle, concurrent, fixture), "concurrent edit prevents publish"); installer.During = null;
                Assert(Data.Decode(files.Read(Path.Combine(concurrent, "AGENTS.md"))) == "user edit during install", "concurrent edit retained");
                var preserve = Project(fixture, "preserve");
                foreach (var name in Transaction.CoreFiles.Where(n => n != ".ai/sev.json")) files.Write(Path.Combine(preserve, name), Data.Utf8("user " + name));
                files.Write(Path.Combine(preserve, "code.cs"), Data.Utf8("user code"));
                files.Write(Path.Combine(preserve, ".env"), Data.Utf8("fixture secret"));
                installer.ChangeSettings = true; Throws(() => Run(files, network, installer, idle, preserve, fixture), "settings mutation rejected"); installer.ChangeSettings = false;
                Run(files, network, installer, idle, preserve, fixture);
                Assert(Data.Decode(files.Read(Path.Combine(preserve, ".ai/models.yaml"))) == "user .ai/models.yaml", "models preserved");
                Assert(Data.Decode(files.Read(Path.Combine(preserve, "PROJECT.md"))) == "user PROJECT.md", "project facts preserved");
                Assert(Data.Decode(files.Read(Path.Combine(preserve, "README.md"))) == "user README.md", "README preserved");
                Assert(Data.Decode(files.Read(Path.Combine(preserve, "AGENTS.md"))).StartsWith("user AGENTS.md"), "user guidance preserved");
                Assert(Data.Decode(files.Read(Path.Combine(preserve, ".env"))) == "fixture secret" && Data.Decode(files.Read(Path.Combine(preserve, "code.cs"))) == "user code", "code and secrets untouched");
                Assert(File.ReadAllText(Path.Combine(other, "keep.txt")) == "other-project", "other project unchanged");
                config = Data.Parse(Data.Decode(files.Read(Path.Combine(preserve, ".ai/sev.json")))); config["version"] = "0.3.2";
                var previous = Data.Utf8(Data.Json(config)); files.Write(Path.Combine(preserve, ".ai/sev.json"), previous);
                files.FailPath = Path.Combine(preserve, ".ai/sev.json"); files.Armed = true; files.AfterWrite = true;
                Throws(() => Run(files, network, installer, idle, preserve, fixture), "failure after replacing existing connection"); files.AfterWrite = false;
                Assert(Data.Hash(previous) == Data.Hash(files.Read(Path.Combine(preserve, ".ai/sev.json"))), "existing connection restored from journal");
                Assert(Data.Hash(files.Read(Data.Text(config, "service"))) == Data.Hash(Network.Source), "previous runtime unchanged");
                // Crash after any individual publication: restore only the write-ahead images.
                for (int point = 0; point < Transaction.CoreFiles.Length; point++)
                {
                    var interrupted = Project(fixture, "publish-" + point);
                    files.FailPath = Path.Combine(interrupted, Transaction.CoreFiles[point]); files.Armed = true;
                    Throws(() => Run(files, network, installer, idle, interrupted, fixture), "publish fault " + point);
                    Assert(Transaction.CoreFiles.All(n => files.Read(Path.Combine(interrupted, n)) == null), "rollback " + point);
                    Assert(Run(files, network, installer, idle, interrupted, fixture).Changed, "retry " + point);
                }
                var crash = Project(fixture, "crash"); var transaction = new Transaction(files, crash);
                transaction.Prepare(); transaction.Installing();
                Assert(new Transaction(files, crash).Recover(), "restart during installing");
                transaction = new Transaction(files, crash); transaction.Prepare();
                Assert(new Transaction(files, crash).Recover(), "restart after prepare");
                transaction = new Transaction(files, crash); transaction.Prepare(); transaction.Installing();
                installer.Install("fixture", transaction.Stage, Snapshot.Fetch(network, CancellationToken.None), transaction.Work);
                transaction.Publish(() => { });
                Assert(new Transaction(files, crash).Recover() && Transaction.CoreFiles.All(n => files.Read(Path.Combine(crash, n)) == null), "restart after publishing before commit");
                transaction = new Transaction(files, crash); transaction.Prepare(); transaction.Installing();
                installer.Install("fixture", transaction.Stage, Snapshot.Fetch(network, CancellationToken.None), transaction.Work);
                transaction.Publish(() => { });
                files.Write(Path.Combine(crash, "AGENTS.md"), Data.Utf8("concurrent user edit"));
                Throws(() => new Transaction(files, crash).Recover(), "concurrent edit recovery conflict");
                Assert(Data.Decode(files.Read(Path.Combine(crash, "AGENTS.md"))) == "concurrent user edit", "conflict content preserved");
                Assert(!System.Text.Encoding.UTF8.GetString(File.ReadAllBytes(Path.Combine(crash, ".ai/starter-manager/journal.json"))).Contains("concurrent user edit"), "journal no plaintext user data");
                foreach (var url in new[] { "http://api.github.com/repos/sunhokim1/codex-starter-pack/commits/main", "https://evil.example/", "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/main/scripts/install_from_github.ps1", "https://api.github.com/repos/sunhokim1/codex-starter-pack/commits/main?x=1" })
                    Throws(() => HttpsTransport.Validate(url), "url rejected");
                // Real Windows native process smoke, no network/installer/runtime execution.
                string smoke = Path.Combine(fixture, "native.txt");
                Assert(OwnedProcess.Run("[IO.File]::WriteAllText(" + PowerShellInstaller.Literal(smoke) + ",'ok');exit 0", fixture) == 0 && File.ReadAllText(smoke) == "ok", "job-owned PowerShell smoke");
                // Validate argument boundaries and the actual saved-script result protocol.
                var protocol = Project(fixture, "protocol ' $ & [한글]");
                var script = Path.Combine(protocol, "installer.ps1");
                var snap = Snapshot.Fetch(network, CancellationToken.None);
                files.Write(script, Data.Utf8("param([switch]$Manager,[string]$Target,[string]$SnapshotCommit,[string]$ExpectedVersion)\n" +
                    "@{schema=1;status='installed';exitCode=0;version=$ExpectedVersion;snapshot=$SnapshotCommit;target=$Target;autostart=$false;personalSkillReplaced=$false}|ConvertTo-Json -Compress\nexit 0"));
                snap.InstallerHash = Data.Hash(files.Read(script));
                new PowerShellInstaller(files).Install(script, protocol, snap, protocol);
                Assert(true, "PowerShell result and special arguments");
                // Lock probe is a second OS process, matching the Python msvcrt first-byte region.
                string lockPath = Path.Combine(fixture, "byte.lock");
                using (new ByteLease(files, lockPath))
                {
                    int code = OwnedProcess.Run("$s=[IO.File]::Open(" + PowerShellInstaller.Literal(lockPath) + ",[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite);try{$s.Lock(0,1);exit 9}catch{exit 0}finally{$s.Dispose()}", fixture);
                    Assert(code == 0, "cross process byte lock contention");
                }
                Assert(OwnedProcess.Run("$s=[IO.File]::Open(" + PowerShellInstaller.Literal(lockPath) + ",[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite);try{$s.Lock(0,1);$s.Unlock(0,1);exit 0}finally{$s.Dispose()}", fixture) == 0, "byte lock released");
                foreach (var busyLock in new[] { Path.Combine(fixture, "locks/manager.lock"), Path.Combine(project, ".ai/installation.lock"), Path.Combine(project, ".ai/project-workflow/lock") })
                {
                    var lockInfo = new System.Diagnostics.ProcessStartInfo(System.Reflection.Assembly.GetExecutingAssembly().Location, "--hold-lock \"" + busyLock + "\"") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true };
                    using (var holder = System.Diagnostics.Process.Start(lockInfo))
                    {
                        try
                        {
                            Assert(holder.StandardOutput.ReadLine() == "locked", "manager lease fixture ready");
                            Throws(() => Run(files, network, installer, idle, project, fixture), "manager refuses active lease");
                        }
                        finally { holder.StandardInput.WriteLine(); if (!holder.WaitForExit(5000)) holder.Kill(); }
                    }
                }
                var active = Project(fixture, "active");
                files.Write(Path.Combine(active, ".ai/project-workflow/state.json"), Data.Utf8("{\"status\":\"running\"}"));
                Throws(() => new WindowsActivityGuard(files).AssertIdle(active), "actual workflow state guard");
                files.Delete(Path.Combine(active, ".ai/project-workflow/state.json"));
                files.Write(Path.Combine(active, ".ai/reports/task.json"), Data.Utf8("{\"status\":\"running\"}"));
                Throws(() => new WindowsActivityGuard(files).AssertIdle(active), "actual uncertain quick report guard");
                string childPid = Path.Combine(fixture, "child.pid");
                var probeInfo = new System.Diagnostics.ProcessStartInfo(System.Reflection.Assembly.GetExecutingAssembly().Location, "--job-crash-probe \"" + childPid + "\"") { UseShellExecute = false, CreateNoWindow = true };
                using (var probe = System.Diagnostics.Process.Start(probeInfo))
                {
                    try
                    {
                        var clock = System.Diagnostics.Stopwatch.StartNew();
                        while (!File.Exists(childPid) && !probe.HasExited && clock.Elapsed.TotalSeconds < 10) Thread.Sleep(25);
                        Assert(File.Exists(childPid), "crash supervisor child started");
                        int pid = Int32.Parse(File.ReadAllText(childPid));
                        probe.Kill(); probe.WaitForExit();
                        bool alive = true; clock.Restart();
                        while (alive && clock.Elapsed.TotalSeconds < 10)
                        {
                            try { using (var child = System.Diagnostics.Process.GetProcessById(pid)) alive = !child.HasExited; } catch (ArgumentException) { alive = false; }
                            if (alive) Thread.Sleep(25);
                        }
                        Assert(!alive, "forced manager termination kills descendant");
                    }
                    finally { if (!probe.HasExited) { probe.Kill(); probe.WaitForExit(); } }
                }
                Console.WriteLine("PASS: " + checks + " deterministic fixture assertions; native process/byte-lock smoke. No network or real installation.");
                return 0;
            }
            finally
            {
                // The generated absolute target is verified inside the explicitly supplied fixture root.
                if (fixture.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) Directory.Delete(fixture, true);
            }
        }
    }
    public static class CoreTestProgram
    {
        public static int Main(string[] args)
        {
            try
            {
                if (args.Length == 2 && args[0] == "--self-test") return CoreSelfTest.Execute(args[1]);
                if (args.Length == 2 && args[0] == "--hold-lock")
                {
                    using (new ByteLease(new FileStore(), Path.GetFullPath(args[1]))) { Console.WriteLine("locked"); Console.ReadLine(); }
                    return 0;
                }
                if (args.Length == 2 && args[0] == "--job-crash-probe")
                {
                    var child = Convert.ToBase64String(System.Text.Encoding.Unicode.GetBytes("Start-Sleep -Seconds 30"));
                    return OwnedProcess.Run("$p=Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList '-NoProfile','-NonInteractive','-EncodedCommand','" + child + "';[IO.File]::WriteAllText(" + PowerShellInstaller.Literal(args[1]) + ",[string]$p.Id);Start-Sleep -Seconds 30", Path.GetDirectoryName(args[1]));
                }
                Console.Error.WriteLine("사용법: StarterManager.CoreTests.exe --self-test <fixture-root>"); return 2;
            }
            catch (Exception e) { Console.Error.WriteLine(e.GetType().Name + ": " + e.Message); return 1; }
        }
    }
}

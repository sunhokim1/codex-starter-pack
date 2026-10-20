using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Management;
using System.Runtime.InteropServices;
using System.Text;

namespace StarterManager
{
    public sealed class WindowsActivityGuard : IActivityGuard
    {
        readonly FileStore files;
        public WindowsActivityGuard(FileStore files) { this.files = files; }
        public void AssertIdle(string project)
        {
            var bytes = files.Read(Path.Combine(project, ".ai/project-workflow/state.json"));
            if (bytes != null)
            {
                var state = Data.Parse(Data.Decode(bytes));
                // A released byte lock does not prove that a crashed controller's children stopped.
                if (Data.Text(state, "status") != "completed")
                    throw new ManagerException("완료되지 않은 프로젝트 workflow가 있습니다. 작업과 자손 프로세스를 먼저 정리한 뒤 다시 확인해 주세요.");
            }
            foreach (var path in files.Files(Path.Combine(project, ".ai/reports")))
            {
                if (!path.EndsWith(".json", StringComparison.OrdinalIgnoreCase)) continue;
                var report = Data.Parse(Data.Decode(files.Read(path)));
                if (Data.Text(report, "status") == "running") throw new ManagerException("실행 중이거나 중단 상태인 작업 기록이 있습니다. 작업 종료를 먼저 확인해 주세요.");
            }
            try
            {
                // Quick runner has no shared lock in 0.3.3. Reject any runner/native execution,
                // including another project, rather than guessing its working directory from WMI.
                using (var search = new ManagementObjectSearcher("SELECT Name,CommandLine FROM Win32_Process"))
                {
                search.Options.Timeout = TimeSpan.FromSeconds(10);
                using (var processes = search.Get())
                foreach (ManagementObject process in processes)
                {
                    using (process)
                    {
                        string name = (process["Name"] as string ?? "").ToLowerInvariant();
                        if (!(name.StartsWith("python") || name.StartsWith("codex"))) continue;
                        string command = process["CommandLine"] as string;
                        if (command == null) throw new ManagerException("실행 상태를 확인할 수 없는 개발 프로세스가 있습니다. 종료 후 다시 확인해 주세요.");
                        command = command.ToLowerInvariant();
                        if (command.Contains("run.py") || command.Contains("project.py") ||
                            (name.StartsWith("codex") && (command.Contains(" exec") || command.Contains(" sandbox"))))
                            throw new ManagerException("개발 작업이 실행 중입니다. 작업 종료 후 다시 확인해 주세요.");
                    }
                }
                }
            }
            catch (ManagerException) { throw; }
            catch { throw new ManagerException("실행 상태를 안전하게 확인할 수 없습니다. 설치하지 않았습니다. 잠시 후 다시 확인해 주세요."); }
        }
    }

    public sealed class PowerShellInstaller : IInstaller
    {
        readonly FileStore files;
        public PowerShellInstaller(FileStore files) { this.files = files; }
        public static string Literal(string text)
        {
            // Paths remain data, never PowerShell source literals.
            return "([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + Convert.ToBase64String(Encoding.UTF8.GetBytes(text)) + "')))";
        }
        public void Install(string script, string stage, Snapshot snapshot, string work)
        {
            string result = Path.Combine(work, "result.json"); files.Delete(result);
            files.Safe(script);
            if (snapshot.InstallerHash == null || Data.Hash(files.Read(script)) != snapshot.InstallerHash)
                throw new ManagerException("저장된 설치기 무결성 확인에 실패했습니다.");
            string command = "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';" +
                // The installer calls exit: consume each result synchronously, before exit unwinds the pipeline.
                // Execute only the already downloaded immutable file, without changing execution policy.
                "$bytes=[IO.File]::ReadAllBytes(" + Literal(script) + ");$h=[Security.Cryptography.SHA256]::Create();try{$hash=([BitConverter]::ToString($h.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()};" +
                "if($hash -cne '" + snapshot.InstallerHash + "'){exit 1};" +
                "& ([scriptblock]::Create([Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xfeff))) -Manager -Target " + Literal(stage) + " -SnapshotCommit " + Literal(snapshot.Commit) +
                " -ExpectedVersion " + Literal(snapshot.Version) + " 2>$null | ForEach-Object {" +
                "if($_ -is [string]){try{$j=ConvertFrom-Json -InputObject $_ -ErrorAction Stop;if($j.schema -eq 1 -and $j.status){" +
                "[IO.File]::WriteAllText(" + Literal(result) + ",[string]$_,(New-Object Text.UTF8Encoding($false)))}}catch{}}};exit $LASTEXITCODE";
            int exit = OwnedProcess.Run(command, work);
            var bytes = files.Read(result);
            if (exit != 0 || bytes == null) throw new ManagerException("설치기가 실패했습니다. Python 3.11 이상, Codex CLI 설치·로그인, native sandbox 준비를 확인해 주세요. 권한을 자동 변경하지 않습니다.");
            var json = Data.Parse(Data.Decode(bytes));
            object schema, code, autostart, skills;
            if (!json.TryGetValue("schema", out schema) || !(schema is int) || (int)schema != 1 ||
                !json.TryGetValue("exitCode", out code) || !(code is int) || (int)code != 0 ||
                Data.Text(json, "status") != "installed" || Data.Text(json, "version") != snapshot.Version ||
                Data.Text(json, "snapshot") != snapshot.Commit || !String.Equals(Data.Text(json, "target"), stage, StringComparison.OrdinalIgnoreCase) ||
                !json.TryGetValue("autostart", out autostart) || !(autostart is bool) || (bool)autostart ||
                !json.TryGetValue("personalSkillReplaced", out skills) || !(skills is bool) || (bool)skills)
                throw new ManagerException("설치기의 완료 결과가 계약과 다릅니다. 프로젝트에 반영하지 않았습니다.");
        }
    }

    // Start suspended, assign the job, then resume: no child can escape during assignment.
    // Forced manager termination kills the installer tree. After a successful install,
    // release kill-on-close so the newly created persistent service can survive normally.
    public static class OwnedProcess
    {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct Startup { public int cb; public string reserved, desktop, title; public int x, y, width, height, charsX, charsY, fill, flags; public short show, reservedSize; public IntPtr reservedBytes, input, output, error; }
        [StructLayout(LayoutKind.Sequential)]
        struct ProcessInfo { public IntPtr process, thread; public uint pid, tid; }
        [StructLayout(LayoutKind.Sequential)]
        struct BasicLimit { public long processTime, jobTime; public uint flags; public UIntPtr minimum, maximum; public uint active; public UIntPtr affinity; public uint priority, scheduling; }
        [StructLayout(LayoutKind.Sequential)]
        struct IoCounters { public ulong readOps, writeOps, otherOps, readBytes, writeBytes, otherBytes; }
        [StructLayout(LayoutKind.Sequential)]
        struct ExtendedLimit { public BasicLimit basic; public IoCounters io; public UIntPtr processMemory, jobMemory, peakProcess, peakJob; }
        [StructLayout(LayoutKind.Sequential)]
        struct Accounting { public long user, kernel, periodUser, periodKernel; public uint faults, total, active, terminated; }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern bool CreateProcess(string app, StringBuilder command, IntPtr pa, IntPtr ta, bool inherit, uint flags, IntPtr environment, string directory, ref Startup startup, out ProcessInfo process);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError = true)] static extern bool SetInformationJobObject(IntPtr job, int kind, ref ExtendedLimit info, uint size);
        [DllImport("kernel32.dll", SetLastError = true)] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll")] static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
        [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr process, out uint code);
        [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr process, uint code);
        [DllImport("kernel32.dll")] static extern bool TerminateJobObject(IntPtr job, uint code);
        [DllImport("kernel32.dll")] static extern bool QueryInformationJobObject(IntPtr job, int kind, out Accounting info, uint size, IntPtr length);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
        static void StopTree(IntPtr job)
        {
            TerminateJobObject(job, 1);
            var clock = Stopwatch.StartNew();
            while (clock.Elapsed.TotalSeconds < 10)
            {
                Accounting info;
                if (!QueryInformationJobObject(job, 1, out info, (uint)Marshal.SizeOf(typeof(Accounting)), IntPtr.Zero)) break;
                if (info.active == 0) return;
                System.Threading.Thread.Sleep(25);
            }
            throw new ProcessUncertainException("설치 자손 프로세스 종료를 확인할 수 없습니다. journal을 보존하고 재실행 시 복구 상태를 점검해 주세요.");
        }
        public static int Run(string command, string directory)
        {
            string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell/v1.0/powershell.exe");
            string arguments = "\"" + powershell + "\" -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand " + Convert.ToBase64String(Encoding.Unicode.GetBytes(command));
            IntPtr job = CreateJobObject(IntPtr.Zero, null); ProcessInfo pi = new ProcessInfo();
            try
            {
                if (job == IntPtr.Zero) throw new ManagerException("설치 프로세스 보호를 만들 수 없습니다.");
                var limits = new ExtendedLimit(); limits.basic.flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(limits))) throw new ManagerException("설치 프로세스 보호를 설정할 수 없습니다.");
                var startup = new Startup(); startup.cb = Marshal.SizeOf(startup);
                if (!CreateProcess(powershell, new StringBuilder(arguments), IntPtr.Zero, IntPtr.Zero, false, 0x08000004, IntPtr.Zero, directory, ref startup, out pi))
                    throw new ManagerException("Windows PowerShell을 시작할 수 없습니다.");
                if (!AssignProcessToJobObject(job, pi.process)) { TerminateProcess(pi.process, 1); throw new ManagerException("설치 프로세스를 보호할 수 없어 실행하지 않았습니다."); }
                if (ResumeThread(pi.thread) == UInt32.MaxValue) throw new ManagerException("설치 프로세스를 실행할 수 없습니다.");
                if (WaitForSingleObject(pi.process, UInt32.MaxValue) != 0) throw new ManagerException("설치 프로세스 종료 확인에 실패했습니다.");
                uint code;
                if (!GetExitCodeProcess(pi.process, out code)) throw new ManagerException("설치 종료코드를 확인할 수 없습니다.");
                if (code == 0)
                {
                    limits.basic.flags = 0;
                    if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(limits))) throw new ManagerException("새 서비스의 프로세스 보호 전환에 실패했습니다.");
                }
                else StopTree(job);
                return unchecked((int)code);
            }
            catch
            {
                if (job != IntPtr.Zero) StopTree(job);
                throw;
            }
            finally
            {
                if (job != IntPtr.Zero) CloseHandle(job);
                if (pi.thread != IntPtr.Zero) CloseHandle(pi.thread);
                if (pi.process != IntPtr.Zero) CloseHandle(pi.process);
            }
        }
    }
}

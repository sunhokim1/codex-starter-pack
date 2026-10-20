using System;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Drawing;

[assembly: AssemblyTitle("Codex Starter 관리자")]
[assembly: AssemblyVersion("0.1.0.0")]
[assembly: AssemblyFileVersion("0.1.0.0")]

namespace StarterManager
{
    public sealed class AppSettings
    {
        readonly FileStore files = new FileStore();
        readonly string path;
        public AppSettings(string path) { this.path = Path.GetFullPath(path); }
        public static string ValidateTarget(string target)
        {
            if (String.IsNullOrWhiteSpace(target) || !Path.IsPathRooted(target)) throw new IOException();
            string full = Path.GetFullPath(target).TrimEnd(Path.DirectorySeparatorChar);
            new FileStore().Safe(full);
            if (!Directory.Exists(full) || full == Path.GetPathRoot(full).TrimEnd(Path.DirectorySeparatorChar)) throw new IOException();
            if ((Path.Combine(full, ".ai/starter-manager/stage/.ai/verification.yaml") + ".manager-" + new string('0', 32)).Length >= 260) throw new IOException();
            // Verify directory access without creating project files or enumerating their contents.
            using (var entries = Directory.EnumerateFileSystemEntries(full).GetEnumerator()) entries.MoveNext();
            return full;
        }
        public string Load(out string notice)
        {
            notice = null;
            try
            {
                var bytes = files.Read(path);
                if (bytes == null) return null;
                var config = Data.Parse(Data.Decode(bytes)); object schema;
                if (!config.TryGetValue("schema", out schema) || !(schema is int) || (int)schema != 1) throw new IOException();
                return ValidateTarget(Data.Text(config, "target"));
            }
            catch
            {
                notice = "저장된 설정이나 프로젝트 폴더를 사용할 수 없습니다. 폴더를 다시 선택해 주세요.";
                return null;
            }
        }
        public void Save(string target)
        {
            target = ValidateTarget(target);
            files.Write(path, Data.Utf8(Data.Json(new { schema = 1, target = target })));
        }
    }

    public interface IManagerOperation
    {
        Result Run(string target, CancellationToken cancel, Action<Progress> progress);
    }
    public sealed class CoreOperation : IManagerOperation
    {
        readonly ManagerCore core;
        public CoreOperation(string sharedLocks)
        {
            var files = new FileStore();
            core = new ManagerCore(files, new HttpsTransport(), new PowerShellInstaller(files), new WindowsActivityGuard(files), sharedLocks);
        }
        public Result Run(string target, CancellationToken cancel, Action<Progress> progress) { return core.Run(target, cancel, progress); }
    }

    public sealed class ManagerForm : Form
    {
        readonly AppSettings settings;
        readonly Func<IManagerOperation> operation;
        readonly bool automatic;
        readonly Label targetLabel = new Label(), stateLabel = new Label(), detailLabel = new Label();
        readonly TextBox history = new TextBox();
        readonly Button change = new Button(), retry = new Button(), stop = new Button();
        readonly ProgressBar bar = new ProgressBar();
        CancellationTokenSource cancellation;
        string target;
        bool busy, closePending, canCancel, receiveProgress;
        int generation;
        public bool Busy { get { return busy; } }
        public bool ClosePending { get { return closePending; } }
        public string StatusText { get { return stateLabel.Text; } }
        public bool TargetChangeEnabled { get { return change.Enabled; } }
        public string HistoryText { get { return history.Text; } }

        public ManagerForm(AppSettings settings, Func<IManagerOperation> operation, bool automatic)
        {
            this.settings = settings; this.operation = operation; this.automatic = automatic;
            Text = "Codex Starter 관리자 · 앱 0.1.0";
            Font = new Font("Malgun Gothic", 10F);
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(780, 620); MinimumSize = new Size(720, 620);
            StartPosition = FormStartPosition.CenterScreen;
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(20), ColumnCount = 1, RowCount = 8 };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            foreach (int height in new[] { 40, 56, 42, 72, 24, 132, 48 }) layout.RowStyles.Add(new RowStyle(SizeType.Absolute, height));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            var title = new Label { Text = "프로젝트 스타터팩 자동 관리", Font = new Font(Font.FontFamily, 16F, FontStyle.Bold), Dock = DockStyle.Fill };
            targetLabel.Dock = DockStyle.Fill; targetLabel.AutoEllipsis = true;
            stateLabel.Dock = DockStyle.Fill; stateLabel.Font = new Font(Font, FontStyle.Bold);
            detailLabel.Dock = DockStyle.Fill; detailLabel.AutoEllipsis = true;
            bar.Dock = DockStyle.Fill; bar.Style = ProgressBarStyle.Blocks;
            var preparation = new Label { Dock = DockStyle.Fill, Padding = new Padding(0, 10, 0, 0), Text = "준비사항: Python 3.11 이상, 네이티브 Codex CLI 설치·로그인 및 네이티브 샌드박스 준비가 필요합니다.\r\n빈 폴더와 기존 프로젝트를 지원합니다. 설치 중에는 개발 작업과 파일 편집을 멈춰 주세요.\r\n선택한 프로젝트의 연결만 처리합니다. 권한·인증·자동시작을 자동 변경하지 않습니다." };
            var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
            change.Text = "폴더 선택 / 변경"; retry.Text = "다시 확인"; stop.Text = "취소";
            foreach (var button in new[] { change, retry, stop }) { button.AutoSize = true; button.Height = 34; actions.Controls.Add(button); }
            history.Dock = DockStyle.Fill; history.Multiline = true; history.ReadOnly = true; history.ScrollBars = ScrollBars.Vertical;
            layout.Controls.Add(title); layout.Controls.Add(targetLabel); layout.Controls.Add(stateLabel); layout.Controls.Add(detailLabel);
            layout.Controls.Add(bar); layout.Controls.Add(preparation); layout.Controls.Add(actions); layout.Controls.Add(history); Controls.Add(layout);
            change.Click += delegate { SelectFolder(); };
            retry.Click += delegate { StartCheck(); };
            stop.Click += delegate { RequestStop(false); };
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (busy) { e.Cancel = true; RequestStop(true); } };
            string notice; target = settings.Load(out notice);
            targetLabel.Text = target == null ? "프로젝트 폴더: 선택하지 않음" : "프로젝트 폴더: " + target;
            stateLabel.Text = "대기 중"; detailLabel.Text = notice ?? "폴더를 선택하면 최신 버전을 확인하고 필요한 설치·업데이트를 자동 진행합니다.";
            SetButtons();
            Shown += delegate { if (this.automatic) { if (target == null) SelectFolder(); else StartCheck(); } };
        }
        void SetButtons()
        {
            change.Enabled = !busy; retry.Enabled = !busy && target != null;
            stop.Enabled = busy && !closePending;
            stop.Text = canCancel ? "취소" : "완료 후 닫기";
            bar.Style = busy ? ProgressBarStyle.Marquee : ProgressBarStyle.Blocks;
        }
        void SelectFolder()
        {
            if (busy) return;
            using (var dialog = new FolderBrowserDialog { Description = "스타터팩을 관리할 프로젝트 폴더를 선택하세요.", ShowNewFolderButton = true, SelectedPath = target ?? "" })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                try { settings.Save(dialog.SelectedPath); target = AppSettings.ValidateTarget(dialog.SelectedPath); }
                catch { stateLabel.Text = "폴더 선택 오류"; detailLabel.Text = "폴더 접근 또는 설정 저장에 실패했습니다. 쓰기 가능한 프로젝트와 사용자 설정 위치를 확인해 주세요."; return; }
                targetLabel.Text = "프로젝트 폴더: " + target; StartCheck();
            }
        }
        static string PhaseText(Phase phase)
        {
            switch (phase)
            {
                case Phase.Checking: return "최신 버전 확인 중";
                case Phase.Downloading: return "설치 파일 다운로드 중";
                case Phase.Preparing: return "백업 및 설치 준비 중";
                case Phase.Installing: return "스타터팩 설치 중";
                case Phase.Publishing: return "프로젝트 연결 검증·반영 중";
                case Phase.Recovering: return "복구 상태 확인 중";
                case Phase.Complete: return "완료";
                default: return "오류";
            }
        }
        void ShowProgress(Progress progress)
        {
            canCancel = progress.CanCancel;
            stateLabel.Text = PhaseText(progress.Phase);
            detailLabel.Text = progress.Message;
            // Only controlled core messages are retained. No process output, file content or exception dump.
            if (history.TextLength > 12000) history.Clear();
            history.AppendText(stateLabel.Text + ": " + progress.Message + Environment.NewLine);
            if (closePending) detailLabel.Text += " 완료 후 창을 닫습니다.";
            SetButtons();
        }
        public void RequestStop(bool closing)
        {
            if (!busy) return;
            if (closing || !canCancel) closePending = true;
            // The core deliberately ignores cancellation once preparation starts.
            cancellation.Cancel();
            detailLabel.Text = canCancel ? "취소를 요청했습니다. 안전하게 정리될 때까지 기다려 주세요." : "안전한 설치·복구 완료 후 창을 닫습니다. 프로세스를 강제 종료하지 마세요.";
            SetButtons();
        }
        public async void StartCheck()
        {
            if (busy || target == null) return;
            try { target = AppSettings.ValidateTarget(target); }
            catch
            {
                target = null; targetLabel.Text = "프로젝트 폴더: 다시 선택 필요";
                stateLabel.Text = "폴더 확인 필요"; detailLabel.Text = "프로젝트 폴더가 없거나 접근할 수 없습니다. 폴더를 다시 선택해 주세요."; SetButtons(); return;
            }
            busy = true; closePending = false; canCancel = true; receiveProgress = true;
            int run = ++generation;
            cancellation = new CancellationTokenSource();
            var token = cancellation.Token;
            var uiProgress = new System.Progress<Progress>(p => { if (busy && receiveProgress && run == generation && !IsDisposed) ShowProgress(p); });
            stateLabel.Text = "확인 시작"; detailLabel.Text = "프로젝트 상태를 안전하게 확인합니다."; SetButtons();
            bool mayClose = false;
            try
            {
                var result = await Task.Run(() => operation().Run(target, token, p => ((IProgress<Progress>)uiProgress).Report(p)));
                receiveProgress = false;
                stateLabel.Text = "완료 · 스타터팩 " + result.Version; detailLabel.Text = result.Message;
                mayClose = true;
            }
            catch (OperationCanceledException) { receiveProgress = false; stateLabel.Text = "취소 완료"; detailLabel.Text = "확인을 취소했습니다. 다시 확인할 수 있습니다."; mayClose = true; }
            catch (Exception error)
            {
                receiveProgress = false;
                stateLabel.Text = "오류 · 다시 확인 필요";
                detailLabel.Text = error is ManagerException || error is ProcessUncertainException ? error.Message : "작업을 완료하지 못했습니다. 폴더 접근권한과 준비사항을 확인한 뒤 다시 시도해 주세요. 반복되면 관리기 문서의 복구 안내를 확인하세요.";
                // Errors remain visible even if closing was requested, particularly uncertain processes.
            }
            finally { busy = false; canCancel = false; cancellation.Dispose(); cancellation = null; SetButtons(); }
            if (closePending && mayClose) Close(); else { closePending = false; SetButtons(); }
        }
    }

    public static class Program
    {
        [STAThread]
        public static int Main(string[] args)
        {
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            // Dispatch diagnostics BEFORE constructing any production service or user settings path.
            if (args.Length != 0)
            {
                if (args.Length == 2 && (args[0] == "--self-test" || args[0] == "--smoke-test")) return AppDiagnostics.Run(args[0], args[1]);
                return 2;
            }
            try
            {
                string identity = System.Security.Principal.WindowsIdentity.GetCurrent().User.Value;
                using (var singleton = new Mutex(false, "Local\\CodexStarterManager-" + Data.Hash(Data.Utf8(identity))))
                {
                    bool acquired;
                    try { acquired = singleton.WaitOne(0); } catch (AbandonedMutexException) { acquired = true; }
                    if (!acquired) { MessageBox.Show("관리기가 이미 실행 중입니다. 기존 창을 확인해 주세요.", "Codex Starter 관리자"); return 1; }
                    try
                    {
                        string home = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CodexStarterManager");
                        using (var form = new ManagerForm(new AppSettings(Path.Combine(home, "settings.json")), () => new CoreOperation(home), true)) Application.Run(form);
                    }
                    finally { singleton.ReleaseMutex(); }
                }
                return 0;
            }
            catch { MessageBox.Show("관리기를 시작할 수 없습니다. 사용자 설정 위치와 실행 환경을 확인해 주세요.", "Codex Starter 관리자 오류"); return 1; }
        }
    }
}

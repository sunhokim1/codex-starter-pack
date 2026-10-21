using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace StarterManager
{
    public enum Phase { Checking, Downloading, Preparing, Installing, Publishing, Recovering, Complete, Error }
    public enum Decision { Missing, Current, Update, Repair, Newer }
    public sealed class Progress
    {
        public Phase Phase; public string Message; public bool CanCancel;
        public Progress(Phase phase, string message, bool cancel) { Phase = phase; Message = message; CanCancel = cancel; }
    }
    public sealed class Result
    {
        public Decision Decision; public string Version; public bool Changed;
        public string Message;
    }
    public sealed class ManagerException : Exception
    {
        public ManagerException(string message) : base(message) { }
    }
    public sealed class ProcessUncertainException : Exception
    {
        public ProcessUncertainException(string message) : base(message) { }
    }
    public static class Data
    {
        public static Dictionary<string, object> Parse(string value)
        {
            var json = new JavaScriptSerializer { MaxJsonLength = 2 * 1024 * 1024, RecursionLimit = 32 };
            var result = json.DeserializeObject(value) as Dictionary<string, object>;
            if (result == null) throw new ManagerException("JSON 형식을 확인할 수 없습니다.");
            return result;
        }
        public static string Json(object value) { return new JavaScriptSerializer { MaxJsonLength=16*1024*1024 }.Serialize(value); }
        public static string Text(Dictionary<string, object> obj, string key)
        {
            object value; return obj.TryGetValue(key, out value) ? value as string : null;
        }
        public static string Hash(byte[] value)
        {
            if (value == null) return null;
            using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(value)).Replace("-", "").ToLowerInvariant();
        }
        public static Version Version(string value)
        {
            if (value == null || !Regex.IsMatch(value, @"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"))
                throw new ManagerException("지원하지 않는 버전 형식입니다. 연결을 변경하지 않았습니다.");
            Version parsed;
            if (!System.Version.TryParse(value, out parsed)) throw new ManagerException("버전 범위를 초과했습니다.");
            return parsed;
        }
        public static byte[] Utf8(string value) { return new UTF8Encoding(false, true).GetBytes(value); }
        public static string Decode(byte[] bytes) { return new UTF8Encoding(false, true).GetString(bytes).TrimStart('\ufeff'); }
    }

    // File operations are virtual so fixtures can inject publication failures without touching a PC installation.
    public class FileStore
    {
        readonly Dictionary<string, FileStream> barriers = new Dictionary<string, FileStream>(StringComparer.OrdinalIgnoreCase);
        sealed class Barrier : IDisposable
        {
            readonly FileStore owner;
            public Barrier(FileStore owner) { this.owner = owner; }
            public void Dispose() { foreach (var stream in owner.barriers.Values) stream.Dispose(); owner.barriers.Clear(); }
        }
        public virtual IDisposable GuardSettings(string target)
        {
            var barrier = new Barrier(this);
            try
            {
                foreach (var relative in new[] { ".ai/models.yaml", ".ai/routing.yaml", ".ai/verification.yaml" })
                {
                    string path = Path.GetFullPath(Path.Combine(target, relative)); Safe(path);
                    if (File.Exists(path)) barriers.Add(path, new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.None));
                }
                return barrier;
            }
            catch { barrier.Dispose(); throw new ManagerException("프로젝트 설정 파일이 사용 중입니다. 작업 종료 후 다시 확인해 주세요."); }
        }
        public virtual void Safe(string path)
        {
            if (!Path.IsPathRooted(path)) throw new ManagerException("절대 경로가 필요합니다.");
            var current = Path.GetFullPath(path);
            while (!String.IsNullOrEmpty(current))
            {
                if ((File.Exists(current) || Directory.Exists(current)) &&
                    (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new ManagerException("링크 또는 junction 경로에는 설치하지 않습니다.");
                var parent = Path.GetDirectoryName(current);
                if (parent == current) break;
                current = parent;
            }
        }
        public virtual byte[] Read(string path)
        {
            Safe(path);
            FileStream held;
            if (barriers.TryGetValue(Path.GetFullPath(path), out held))
            {
                if (held.Length > 2 * 1024 * 1024) throw new ManagerException("프로젝트 관리 파일 크기 제한을 초과했습니다.");
                var bytes = new byte[(int)held.Length]; held.Position = 0; int offset = 0, count;
                while (offset < bytes.Length && (count = held.Read(bytes, offset, bytes.Length - offset)) > 0) offset += count;
                return bytes;
            }
            if (Directory.Exists(path)) throw new ManagerException("파일 위치에 폴더가 있습니다.");
            if (!File.Exists(path)) return null;
            if (new FileInfo(path).Length > (path.EndsWith("journal.json") ? 16 : 2) * 1024 * 1024) throw new ManagerException("프로젝트 관리 파일 크기 제한을 초과했습니다.");
            return File.ReadAllBytes(path);
        }
        public virtual bool FilePresent(string path) { Safe(path); return File.Exists(path) && new FileInfo(path).Length > 0; }
        public virtual bool DirectoryPresent(string path) { Safe(path); return Directory.Exists(path); }
        public virtual void MakeDirectory(string path) { Safe(path); Directory.CreateDirectory(path); }
        public virtual void Write(string path, byte[] bytes)
        {
            Safe(path); MakeDirectory(Path.GetDirectoryName(path));
            var temp = path + ".manager-" + Guid.NewGuid().ToString("N");
            try
            {
                using (var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                { stream.Write(bytes, 0, bytes.Length); stream.Flush(true); }
                if (File.Exists(path)) File.Replace(temp, path, null); else File.Move(temp, path);
            }
            finally { if (File.Exists(temp)) File.Delete(temp); }
        }
        public virtual void Delete(string path) { Safe(path); if (File.Exists(path)) File.Delete(path); }
        public virtual void DeleteEmptyDirectory(string path)
        {
            Safe(path);
            if (Directory.Exists(path) && Directory.GetFileSystemEntries(path).Length == 0) Directory.Delete(path);
        }
        public virtual string[] Files(string path)
        {
            Safe(path); if (!Directory.Exists(path)) return new string[0];
            var list = new List<string>();
            foreach (var file in Directory.GetFiles(path)) { Safe(file); list.Add(file); }
            foreach (var dir in Directory.GetDirectories(path)) { Safe(dir); list.AddRange(Files(dir)); }
            return list.ToArray();
        }
    }

    public interface ITransport { byte[] Get(string url, int limit, CancellationToken cancellation); }
    public sealed class HttpsTransport : ITransport
    {
        public static Uri Validate(string value)
        {
            Uri uri;
            if (!Uri.TryCreate(value, UriKind.Absolute, out uri) || uri.Scheme != "https" || uri.Port != 443 ||
                uri.UserInfo != "" || uri.Query != "" || uri.Fragment != "") throw new ManagerException("허용되지 않은 다운로드 주소입니다.");
            bool api = uri.Host == "api.github.com" && uri.AbsolutePath == "/repos/sunhokim1/codex-starter-pack/commits/main";
            bool raw = uri.Host == "raw.githubusercontent.com" && Regex.IsMatch(uri.AbsolutePath,
                @"^/sunhokim1/codex-starter-pack/[0-9a-f]{40}/(scripts/install_from_github\.ps1|distribution/releases/0\.4\.0/universal-ai-starter/release\.json)$");
            if (!api && !raw) throw new ManagerException("허용되지 않은 다운로드 주소입니다.");
            return uri;
        }
        public byte[] Get(string url,int limit,CancellationToken cancellation) {
            for(int attempt=0;;attempt++) {
                try { return Download(url,limit,cancellation); }
                catch(ManagerException) { cancellation.ThrowIfCancellationRequested(); if(attempt>=1)throw; }
            }
        }
        byte[] Download(string url, int limit, CancellationToken cancellation)
        {
            if (limit <= 0 || limit > 2 * 1024 * 1024) throw new ArgumentOutOfRangeException("limit");
            var uri = Validate(url);
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            var request = (HttpWebRequest)WebRequest.Create(uri);
            request.AllowAutoRedirect = false; request.Timeout = 30000; request.ReadWriteTimeout = 15000;
            request.UserAgent = "Codex-Starter-Manager/0.2.0";
            request.Accept = "application/vnd.github+json";
            using (cancellation.Register(request.Abort))
            using (var deadline = new Timer(delegate { request.Abort(); }, null, 60000, Timeout.Infinite))
            {
                try
                {
                    using (var response = (HttpWebResponse)request.GetResponse())
                    {
                        if (response.StatusCode != HttpStatusCode.OK || response.ContentLength > limit) throw new IOException();
                        using (var input = response.GetResponseStream())
                        using (var output = new MemoryStream())
                        {
                            var buffer = new byte[8192]; int count;
                            while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                            {
                                cancellation.ThrowIfCancellationRequested();
                                if (output.Length + count > limit) throw new IOException();
                                output.Write(buffer, 0, count);
                            }
                            if (output.Length == 0) throw new IOException();
                            return output.ToArray();
                        }
                    }
                }
                catch (Exception error)
                {
                    cancellation.ThrowIfCancellationRequested();
                    if (!(error is WebException) && !(error is IOException)) throw;
                    throw new ManagerException("다운로드에 실패했습니다. 기존 설치는 유지됩니다. 네트워크를 확인한 뒤 다시 확인해 주세요.");
                }
            }
        }
    }
    public sealed class Snapshot
    {
        public const string SupportedVersion = "0.4.0";
        public string Commit, Version, InstallerHash; public Dictionary<string, string> Hashes;
        public string BaseUrl { get { return "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/" + Commit; } }
        public static Snapshot Fetch(ITransport network, CancellationToken cancel)
        {
            var commit = Data.Text(Data.Parse(Data.Decode(network.Get("https://api.github.com/repos/sunhokim1/codex-starter-pack/commits/main", 1024 * 1024, cancel))), "sha");
            if (commit == null || !Regex.IsMatch(commit, "^[0-9a-f]{40}$")) throw new ManagerException("main commit을 확인할 수 없습니다.");
            var snapshot = new Snapshot { Commit = commit, Version = SupportedVersion, Hashes = new Dictionary<string, string>(StringComparer.Ordinal) };
            var release = Data.Parse(Data.Decode(network.Get(snapshot.BaseUrl + "/distribution/releases/0.4.0/universal-ai-starter/release.json", 1024 * 1024, cancel)));
            object hashes; var map = release.TryGetValue("sha256", out hashes) ? hashes as Dictionary<string, object> : null;
            if (Data.Text(release, "version") != snapshot.Version || map == null || map.Count == 0 || map.Count > 256)
                throw new ManagerException("배포 metadata가 일치하지 않습니다.");
            foreach (var pair in map)
            {
                if (!Regex.IsMatch(pair.Key, @"^universal-ai-starter/[a-zA-Z0-9_./-]+$") || pair.Key.Split('/').Any(p => p == ".." || p == "." || p == "") ||
                    !(pair.Value is string) || !Regex.IsMatch((string)pair.Value, "^[0-9a-f]{64}$")) throw new ManagerException("배포 해시 목록이 올바르지 않습니다.");
                snapshot.Hashes.Add(pair.Key, (string)pair.Value);
            }
            if (snapshot.Hashes.Keys.Distinct(StringComparer.OrdinalIgnoreCase).Count() != snapshot.Hashes.Count ||
                snapshot.Hashes.Keys.Any(k => k.Split('/').Any(p => p.EndsWith(".") || Regex.IsMatch(p,@"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",RegexOptions.IgnoreCase))))
                throw new ManagerException("Windows 경로 별칭이 있는 배포입니다.");
            foreach (var key in new[] { "contracts/upstream.lock.json", "assets/rev/service.py", "assets/runner/run.py", "assets/runner/project.py", "assets/runner/runtime_safety.py" })
                if (!snapshot.Hashes.ContainsKey("universal-ai-starter/" + key)) throw new ManagerException("필수 배포 해시가 없습니다.");
            string installerHash;
            if (!snapshot.Hashes.TryGetValue("universal-ai-starter/scripts/install_from_github.ps1", out installerHash))
                throw new ManagerException("검증된 설치기 해시가 없습니다.");
            snapshot.InstallerHash = installerHash;
            return snapshot;
        }
    }

    public sealed class RuntimeInspector
    {
        readonly FileStore files;
        public RuntimeInspector(FileStore files) { this.files = files; }
        public Dictionary<string, object> Config(string target)
        {
            var value = files.Read(Path.Combine(target, ".ai/rev-install.json"));
            if (value == null)
            {
                var legacy = files.Read(Path.Combine(target, ".ai/sev.json"));
                return legacy == null ? null : Data.Parse(Data.Decode(legacy));
            }
            var config = Data.Parse(Data.Decode(value));
            var connection = files.Read(Path.Combine(target, ".ai/rev.json"));
            if (connection != null) config["connection"] = Data.Parse(Data.Decode(connection));
            return config;
        }
        public bool Healthy(Dictionary<string, object> config, Snapshot snapshot)
        {
            try
            {
                if (config == null || Data.Text(config, "version") != snapshot.Version) return false;
                var deployment = Data.Text(config, "deployment");
                if (String.IsNullOrEmpty(deployment) || !Path.IsPathRooted(deployment) || !files.DirectoryPresent(deployment)) return false;
                foreach (var pair in new Dictionary<string, string> { { "runner", "assets/runner/run.py" }, { "project_runner", "assets/runner/project.py" } })
                {
                    var path = Data.Text(config, pair.Key);
                    if (path == null || !Path.IsPathRooted(path) || !String.Equals(Path.GetFullPath(path), Path.GetFullPath(Path.Combine(deployment, pair.Value)), StringComparison.OrdinalIgnoreCase) || !files.FilePresent(path)) return false;
                }
                var python = Data.Text(config, "python");
                if (python == null || !Path.IsPathRooted(python) || !files.FilePresent(python)) return false;
                object raw; var connection = config.TryGetValue("connection", out raw) ? raw as Dictionary<string, object> : null;
                if (connection == null || connection.Count != 6 || !(connection["contract_version"] is int) || (int)connection["contract_version"] != 1 || Data.Text(connection, "runtime_version") != snapshot.Version || String.IsNullOrWhiteSpace(Data.Text(connection, "runtime_id"))) return false;
                if (!Regex.IsMatch(Data.Text(connection, "token_env") ?? "", "^[A-Z][A-Z0-9_]*$")) return false;
                if (!Regex.IsMatch(Data.Text(connection, "endpoint") ?? "", @"^http://(127\.0\.0\.1|\[::1\]):[0-9]+/?$")) return false;
                Uri endpoint;
                if (!Uri.TryCreate(Data.Text(connection, "endpoint"), UriKind.Absolute, out endpoint) || endpoint.Scheme != "http" || (endpoint.Host != "127.0.0.1" && endpoint.Host != "[::1]") || endpoint.Port < 1 || endpoint.Port > 65535 || endpoint.UserInfo != "" || endpoint.Query != "" || endpoint.Fragment != "" || endpoint.AbsolutePath != "/") return false;
                string lockHash;
                if (!snapshot.Hashes.TryGetValue("universal-ai-starter/contracts/upstream.lock.json", out lockHash) || Data.Text(connection, "lock_sha256") != lockHash) return false;
                foreach (var hash in snapshot.Hashes)
                {
                    string relative = hash.Key.Substring("universal-ai-starter/".Length);
                    if (Data.Hash(files.Read(Path.Combine(deployment, relative))) != hash.Value) return false;
                }
                // Static source/connection integrity only; no authenticated inference/readiness claim.
                return true;
            }
            catch (Exception e)
            {
                if (e is IOException || e is ArgumentException || e is ManagerException || e is UnauthorizedAccessException || e is KeyNotFoundException) return false;
                throw;
            }
        }
        public Dictionary<string, object> SourceConfig(string target)
        {
            var bytes = files.Read(Path.Combine(target, ".ai/source-install.json"));
            return bytes == null ? null : Data.Parse(Data.Decode(bytes));
        }
        public Decision Decide(string target, Snapshot snapshot)
        {
            var config = SourceConfig(target);
            if (config == null) {
                if (files.DirectoryPresent(Path.Combine(target,".ai/starter-source"))) throw new ManagerException("영수증 없는 관리 소스입니다. 개별 검토가 필요합니다.");
                return Decision.Missing;
            }
            var installed = Data.Version(Data.Text(config,"version"));
            if (installed > Data.Version(snapshot.Version)) return Decision.Newer;
            object raw; var hashes = config.TryGetValue("sha256",out raw) ? raw as Dictionary<string,object> : null;
            if (hashes == null || hashes.Count == 0 || hashes.Count > 257 || !config.ContainsKey("schema") || !Object.Equals(config["schema"],1)) throw new ManagerException("소스 영수증을 확인할 수 없습니다.");
            foreach (var pair in hashes) {
                if (!Transaction.SourcePath(pair.Key) || !(pair.Value is string) || !Regex.IsMatch((string)pair.Value,"^[0-9a-f]{64}$") ||
                    Data.Hash(files.Read(Path.Combine(target,pair.Key))) != (string)pair.Value) throw new ManagerException("관리 소스가 수정되거나 없습니다. 개별 검토 후 업데이트하세요.");
            }
            var actual = files.Files(Path.Combine(target,".ai/starter-source")).Select(p => p.Substring(target.Length+1).Replace('\\','/'));
            if (!new HashSet<string>(actual,StringComparer.Ordinal).SetEquals(hashes.Keys)) throw new ManagerException("알 수 없는 관리 소스 파일이 있습니다. 검토가 필요합니다.");
            if (!hashes.ContainsKey(".ai/starter-source/release.json")) throw new ManagerException("소스 release metadata가 없습니다.");
            var release=Data.Parse(Data.Decode(files.Read(Path.Combine(target,".ai/starter-source/release.json"))));
            object releaseRaw; var releaseHashes=release.TryGetValue("sha256",out releaseRaw) ? releaseRaw as Dictionary<string,object> : null;
            if (releaseHashes==null || releaseHashes.Count!=hashes.Count-1 || Data.Text(release,"version")!=Data.Text(config,"version") ||
                releaseHashes.Any(p=>!p.Key.StartsWith("universal-ai-starter/",StringComparison.Ordinal) || !hashes.ContainsKey(".ai/starter-source/"+p.Key.Substring("universal-ai-starter/".Length)) || !Object.Equals(hashes[".ai/starter-source/"+p.Key.Substring("universal-ai-starter/".Length)],p.Value)))
                throw new ManagerException("소스 영수증과 release metadata가 다릅니다.");
            var expected = snapshot.Hashes.ToDictionary(p => ".ai/starter-source/"+p.Key.Substring("universal-ai-starter/".Length), p => p.Value);
            if (hashes.Keys.Any(k => k != ".ai/starter-source/release.json" && !expected.ContainsKey(k))) throw new ManagerException("삭제된 관리 소스 경로를 검토해야 합니다.");
            bool same = installed == Data.Version(snapshot.Version) && expected.All(p => hashes.ContainsKey(p.Key) && Object.Equals(hashes[p.Key],p.Value));
            return same ? Decision.Current : Decision.Update;
        }

    }

    // Separate manager locks never overlap the installer's shared-runtime byte lock.
    // The actual target lock can be held because the installer targets the isolated stage.
    public sealed class ByteLease : IDisposable
    {
        FileStream stream;
        public ByteLease(FileStore files, string path)
        {
            files.Safe(path); files.MakeDirectory(Path.GetDirectoryName(path));
            try
            {
                stream = new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.ReadWrite);
                stream.Lock(0, 1);
            }
            catch { if (stream != null) stream.Dispose(); throw new ManagerException("다른 설치 또는 프로젝트 작업이 실행 중입니다. 종료 후 다시 확인해 주세요."); }
        }
        public void Dispose() { if (stream != null) { stream.Dispose(); stream = null; } }
    }
    public interface IActivityGuard { void AssertIdle(string project); }
    public interface IInstaller { void Install(string script, string stage, Snapshot snapshot, string work); }

    public sealed class JournalEntry
    {
        public string Relative { get; set; } public string Before { get; set; } public string After { get; set; }
    }
    public sealed class Journal
    {
        public int Schema { get; set; } public string Target { get; set; } public string Phase { get; set; }
        public List<JournalEntry> Entries { get; set; }
    }
    public sealed class Transaction
    {
        public static readonly string[] CoreFiles = { "AGENTS.md", ".gitignore", "PROJECT.md", "README.md", ".ai/config.yaml", ".ai/models.yaml", ".ai/routing.yaml", ".ai/verification.yaml", ".ai/source-install.json" };
        public static bool SourcePath(string name) {
            return name != null && name.StartsWith(".ai/starter-source/",StringComparison.Ordinal) &&
                Regex.IsMatch(name,@"^[a-zA-Z0-9_./-]+$") && !name.Split('/').Any(p => p == "" || p == "." || p == ".." || p.EndsWith(".") || Regex.IsMatch(p,@"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",RegexOptions.IgnoreCase));
        }
        readonly string[] managed;
        readonly FileStore files; readonly string target, root, journalPath;
        Journal journal;
        public string Stage { get { return Path.Combine(root, "stage"); } }
        public string Work { get { return root; } }
        public Transaction(FileStore files, string target, Snapshot snapshot = null)
        {
            this.files = files; this.target = target;
            managed = snapshot == null ? CoreFiles : CoreFiles.Concat(snapshot.Hashes.Keys.Select(k => ".ai/starter-source/"+k.Substring("universal-ai-starter/".Length))).Concat(new[]{".ai/starter-source/release.json"}).ToArray();
            root = Path.GetFullPath(Path.Combine(target, ".ai/starter-manager")); journalPath = Path.Combine(root, "journal.json");
        }
        void Save()
        {
            var bytes = Data.Utf8(Data.Json(journal));
            if (bytes.Length > 16 * 1024 * 1024) throw new ManagerException("복구 기록의 안전한 크기 제한을 초과했습니다.");
            files.Write(journalPath, ProtectedData.Protect(bytes, Data.Utf8(target), DataProtectionScope.CurrentUser));
        }
        public bool Recover()
        {
            var bytes = files.Read(journalPath); if (bytes == null) return false;
            try { journal = new JavaScriptSerializer { MaxJsonLength=16*1024*1024 }.Deserialize<Journal>(Data.Decode(ProtectedData.Unprotect(bytes, Data.Utf8(target), DataProtectionScope.CurrentUser))); }
            catch { throw new ManagerException("복구 journal을 읽을 수 없습니다. 파일을 보존했습니다. 수동 점검이 필요합니다."); }
            if (journal == null || journal.Schema != 1 || journal.Target != target || journal.Entries == null || journal.Entries.Count > 520 ||
                journal.Entries.Select(e => e.Relative).Distinct(StringComparer.OrdinalIgnoreCase).Count() != journal.Entries.Count ||
                journal.Entries.Any(e => !CoreFiles.Contains(e.Relative) && !SourcePath(e.Relative))) throw new ManagerException("복구 journal 경계가 올바르지 않습니다. 수동 점검이 필요합니다.");
            if (journal.Phase == "committed" || journal.Phase == "rolledback") { Clean(); return true; }
            if (journal.Phase != "prepared" && journal.Phase != "installing" && journal.Phase != "publishing")
                throw new ManagerException("불확실한 복구 단계입니다. 수동 점검이 필요합니다.");
            if (journal.Phase != "publishing")
            {
                // Before publication the manager has never changed these project files.
                // In particular, do not resurrect a file that the user deleted meanwhile.
                journal.Phase = "rolledback"; Save(); Clean(); return true;
            }
            // Preflight every entry before any restoration. Do not overwrite a concurrent edit.
            foreach (var entry in journal.Entries)
            {
                var current = Data.Hash(files.Read(Path.Combine(target, entry.Relative)));
                if (current != HashEncoded(entry.Before) && current != HashEncoded(entry.After))
                    throw new ManagerException("설치 이후 변경된 파일이 있어 자동 복구를 멈췄습니다. journal을 보존했습니다. 수동 병합 후 다시 확인해 주세요.");
            }
            foreach (var entry in journal.Entries.AsEnumerable().Reverse())
            {
                var path = Path.Combine(target, entry.Relative);
                // Recheck immediately before replacing, including after an earlier interrupted recovery.
                if (Data.Hash(files.Read(path)) == HashEncoded(entry.Before)) continue;
                if (Data.Hash(files.Read(path)) != HashEncoded(entry.After)) throw new ManagerException("복구 중 파일이 변경되었습니다. 수동 점검이 필요합니다.");
                if (entry.Before == null) {
                    files.Delete(path);
                    var dir=Path.GetDirectoryName(path);
                    while(dir != target) { files.DeleteEmptyDirectory(dir); dir=Path.GetDirectoryName(dir); }
                } else files.Write(path, Convert.FromBase64String(entry.Before));
            }
            journal.Phase = "rolledback"; Save(); Clean(); return true;
        }
        static string HashEncoded(string value) { return value == null ? null : Data.Hash(Convert.FromBase64String(value)); }
        public void Prepare()
        {
            if (files.Read(journalPath) != null) throw new ManagerException("이전 작업 복구가 필요합니다.");
            // A stale stage without a journal may contain private files. Never reuse it.
            if (files.DirectoryPresent(Stage)) throw new ManagerException("이전 staging 폴더가 남아 있습니다. 수동 점검 후 정리해 주세요.");
            // Keep transient copies out of git even if installation stops before publication.
            var ignore = Path.Combine(root, ".gitignore"); var ignored = files.Read(ignore);
            if (ignored == null) files.Write(ignore, Data.Utf8("*\n"));
            else if (Data.Decode(ignored) != "*\n") throw new ManagerException("관리기 전용 폴더에 사용자 파일이 있습니다. 설치하지 않았습니다.");
            files.MakeDirectory(Stage);
            journal = new Journal { Schema = 1, Target = target, Phase = "prepared", Entries = new List<JournalEntry>() };
            foreach (var name in managed)
            {
                var bytes = files.Read(Path.Combine(target, name));
                journal.Entries.Add(new JournalEntry { Relative = name, Before = bytes == null ? null : Convert.ToBase64String(bytes) });
            }
            Save();
            foreach (var entry in journal.Entries)
                if (entry.Before != null) files.Write(Path.Combine(Stage, entry.Relative), Convert.FromBase64String(entry.Before));
        }
        public void Installing() { journal.Phase = "installing"; Save(); }
        public void Uncertain() { journal.Phase = "uncertain"; Save(); }
        public void Publish(Action guard)
        {
            // Only these known files may be published. Existing user core/settings remain byte-identical.
            foreach (var entry in journal.Entries)
            {
                var bytes = files.Read(Path.Combine(Stage, entry.Relative));
                if (bytes == null) throw new ManagerException("설치된 프로젝트 파일이 불완전합니다.");
                entry.After = Convert.ToBase64String(bytes);
                if (entry.Before != null && !SourcePath(entry.Relative) && entry.Relative != ".ai/source-install.json" && entry.Before != entry.After)
                    throw new ManagerException("설치기가 기존 프로젝트 지침·설정을 변경했습니다. 반영하지 않았습니다.");
            }
            guard();
            foreach (var entry in journal.Entries)
                if (Data.Hash(files.Read(Path.Combine(target, entry.Relative))) != HashEncoded(entry.Before))
                    throw new ManagerException("설치 중 프로젝트 파일이 변경되었습니다. 기존 파일을 보존하고 반영을 중단했습니다.");
            journal.Phase = "publishing"; Save(); // Write-ahead: all before and after images durable before first project write.
            foreach (var entry in journal.Entries)
            {
                guard();
                var path = Path.Combine(target, entry.Relative);
                if (Data.Hash(files.Read(path)) != HashEncoded(entry.Before)) throw new ManagerException("반영 중 파일이 변경되었습니다. 복구가 필요합니다.");
                if (entry.Before != entry.After) files.Write(path, Convert.FromBase64String(entry.After));
            }
        }
        public void Commit() { journal.Phase = "committed"; Save(); Clean(); }
        static void AssertManagedMerge(string before, string after, string name)
        {
            string begin = name == "AGENTS.md" ? "<!-- starter-sev:start -->" : "# starter-private:start";
            string end = name == "AGENTS.md" ? "<!-- starter-sev:end -->" : "# starter-private:end";
            Func<string, string> remove = delegate(string text) {
                text = text.Replace("\r\n", "\n");
                int first = text.IndexOf(begin, StringComparison.Ordinal), last = text.IndexOf(end, StringComparison.Ordinal);
                if (first < 0 && last < 0) return text.TrimEnd();
                if (first < 0 || last < first || text.IndexOf(begin, first + begin.Length, StringComparison.Ordinal) >= 0 || text.IndexOf(end, last + end.Length, StringComparison.Ordinal) >= 0)
                    throw new ManagerException("관리 지침 경계가 중복되거나 손상되었습니다.");
                return text.Remove(first, last + end.Length - first).TrimEnd();
            };
            if (remove(before) != remove(after)) throw new ManagerException("사용자 지침 또는 ignore 내용 변경을 차단했습니다.");
        }
        void Clean()
        {
            // No recursive deletion: only known bounded files, checked for reparse points on every access.
            foreach (var entry in journal.Entries)
            {
                var path = Path.Combine(Stage, entry.Relative);
                if (files.Read(path) != null) files.Delete(path);
            }
            foreach (var entry in journal.Entries) {
                var dir = Path.GetDirectoryName(Path.Combine(Stage,entry.Relative));
                while (dir != Stage && dir.StartsWith(Stage+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) { files.DeleteEmptyDirectory(dir); dir=Path.GetDirectoryName(dir); }
            }
            foreach (var leaf in new[] { "installer.ps1", "result.json" }) files.Delete(Path.Combine(root, leaf));
            files.Delete(Path.Combine(Stage, ".ai/installation.lock"));
            // Remove only empty directories; unknown files are retained for inspection.
            foreach (var dir in new[] { Path.Combine(Stage, ".ai"), Stage })
                files.DeleteEmptyDirectory(dir);
            files.Delete(journalPath);
        }
    }

    public sealed class ManagerCore
    {
        readonly FileStore files; readonly ITransport network; readonly IInstaller installer; readonly IActivityGuard activity; readonly string sharedLocks;
        public ManagerCore(FileStore files, ITransport network, IInstaller installer, IActivityGuard activity, string sharedLocks)
        { this.files = files; this.network = network; this.installer = installer; this.activity = activity; this.sharedLocks = sharedLocks; }
        public Result Run(string folder, CancellationToken cancel, Action<Progress> progress)
        {
            Action<Phase, string, bool> report = (p, message, canCancel) => { if (progress != null) progress(new Progress(p, message, canCancel)); };
            string target = Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar);
            files.Safe(target);
            if (!files.DirectoryPresent(target) || target == Path.GetPathRoot(target).TrimEnd(Path.DirectorySeparatorChar)) throw new ManagerException("프로젝트 폴더를 선택해 주세요. 드라이브 루트는 사용할 수 없습니다.");
            if ((Path.Combine(target, ".ai/starter-manager/stage/.ai/verification.yaml") + ".manager-" + new string('0', 32)).Length >= 260)
                throw new ManagerException("현재 .NET Framework의 안전한 staging 경로 길이를 초과했습니다. 더 짧은 프로젝트 경로를 선택해 주세요.");
            using (new ByteLease(files, Path.Combine(sharedLocks, "manager.lock")))
            using (new ByteLease(files, Path.Combine(target, ".ai/installation.lock")))
            using (new ByteLease(files, Path.Combine(target, ".ai/project-workflow/lock")))
            using (new ByteLease(files, Path.Combine(target, ".ai/rev-workflow/lock")))
            using (files.GuardSettings(target))
            {
                activity.AssertIdle(target);
                var transaction = new Transaction(files, target);
                report(Phase.Recovering, "이전 작업의 복구 상태를 확인합니다.", false);
                transaction.Recover();
                cancel.ThrowIfCancellationRequested();
                report(Phase.Checking, "최신 배포 정보를 확인합니다.", true);
                var snapshot = Snapshot.Fetch(network, cancel);
                foreach(var key in snapshot.Hashes.Keys) {
                    string stagePath=Path.Combine(target,".ai/starter-manager/stage/.ai/starter-source/"+key.Substring("universal-ai-starter/".Length));
                    if ((stagePath+".manager-"+new string('0',32)).Length>=260) throw new ManagerException("관리 소스 staging 경로가 너무 깁니다. 더 짧은 프로젝트 경로를 선택하세요.");
                }
                var inspector = new RuntimeInspector(files);
                var decision = inspector.Decide(target, snapshot);
                if (decision == Decision.Current || decision == Decision.Newer)
                {
                    string message = decision == Decision.Current ? "starter 최신 상태입니다. Rev 준비는 별도 확인이 필요합니다. 실제 추론은 확인하지 않았습니다." : "더 높은 버전이 연결되어 있습니다. downgrade하지 않습니다. 손상 시 해당 버전 관리기로 복구해 주세요.";
                    report(Phase.Complete, message, false);
                    return new Result { Decision = decision, Version = snapshot.Version, Changed = false, Message = message };
                }
                report(Phase.Downloading,"고정 snapshot의 설치기를 검증합니다.",true);
                var script = network.Get(snapshot.BaseUrl+"/scripts/install_from_github.ps1", 1024*1024,cancel);
                if (Data.Hash(script) != snapshot.InstallerHash) throw new ManagerException("고정 설치기 해시 불일치입니다.");
                transaction = new Transaction(files,target,snapshot);
                transaction.Prepare();
                try {
                    string scriptPath=Path.Combine(transaction.Work,"installer.ps1"); files.Write(scriptPath,script);
                    cancel.ThrowIfCancellationRequested(); transaction.Installing();
                    report(Phase.Installing,"격리 공간에 starter 소스·클라이언트를 설치합니다.",false);
                    installer.Install(scriptPath,transaction.Stage,snapshot,transaction.Work);
                    if (inspector.Decide(transaction.Stage,snapshot) != Decision.Current) throw new ManagerException("설치 후 소스 무결성 검증 실패입니다.");
                    cancel.ThrowIfCancellationRequested();
                    report(Phase.Publishing,"검증된 소스를 안전하게 반영합니다.",false);
                    transaction.Publish(()=> { cancel.ThrowIfCancellationRequested(); activity.AssertIdle(target); });
                    if (inspector.Decide(target,snapshot)!=Decision.Current) throw new ManagerException("반영 후 소스 무결성 확인 실패입니다.");
                    transaction.Commit();
                } catch (ProcessUncertainException) { transaction.Uncertain(); throw; }
                catch { transaction.Recover(); throw; }
                string installedMessage="starter 설치·업데이트 완료. Rev 준비가 필요합니다. 기존 실행 연결과 완료 기록은 보존했습니다.";
                report(Phase.Complete,installedMessage,false);
                return new Result { Decision=decision,Version=snapshot.Version,Changed=true,Message=installedMessage };
            }
        }
    }
}

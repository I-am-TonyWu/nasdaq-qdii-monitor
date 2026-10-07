using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Management;
using System.Net;
using System.Net.NetworkInformation;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using Microsoft.Win32;

namespace NasdaqQDII {
    internal sealed class Options {
        internal string StateRoot, Home, Result, Command, RemoteConfigure;
        internal int Port = 8765;
        internal bool NoBrowser, NoShortcuts, ExtractOnly, Autostart, Isolated;
        internal static Options Parse(string[] args) {
            var o = new Options();
            for (int i = 0; i < args.Length; i++) {
                string a = args[i];
                switch(a) {
                    case "--state-root": o.StateRoot = Path.GetFullPath(args[++i]); o.Isolated = true; break;
                    case "--remote-configure": o.RemoteConfigure=Path.GetFullPath(args[++i]); break;
                    case "--home": o.Home = Path.GetFullPath(args[++i]); break;
                    case "--port": o.Port = Int32.Parse(args[++i]); break;
                    case "--result": o.Result = Path.GetFullPath(args[++i]); break;
                    case "--command": o.Command = args[++i]; break;
                    case "--extract-only": o.ExtractOnly = true; break;
                    case "--no-browser": o.NoBrowser = true; break;
                    case "--no-shortcuts": o.NoShortcuts = true; break;
                    case "--autostart": o.Autostart = true; o.NoBrowser = true; break;
                    default: throw new ArgumentException("未知参数：" + a);
                }
            }
            if(o.Port < 1024 || o.Port > 65535) throw new ArgumentException("端口必须在1024–65535之间。");
            o.StateRoot = o.StateRoot ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NasdaqQDII");
            return o;
        }
    }
    internal static class Paths {
        internal static Options Options;
        internal static string Root, Home, Payload, Launcher, PayloadId;
        internal static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 64 * 1024 * 1024 };
        static readonly object LogGate = new object();
        internal static string Url { get { return "http://127.0.0.1:" + Options.Port + "/"; } }
        internal static string HomeId { get { return Hash(Encoding.UTF8.GetBytes(Path.GetFullPath(Home).TrimEnd(Path.DirectorySeparatorChar).ToLowerInvariant())).Substring(0,24); } }
        internal static string Logs { get { return Path.Combine(Root,"logs"); } }
        internal static string Python { get { return Path.Combine(Payload,"python","python.exe"); } }
        internal static string Quote(string value) {
            var b = new StringBuilder("\""); int slash = 0;
            foreach(char c in value) {
                if(c == '\\') { slash++; continue; }
                if(c == '"') { b.Append('\\',slash*2+1); b.Append('"'); }
                else { b.Append('\\',slash); b.Append(c); }
                slash = 0;
            }
            b.Append('\\',slash*2); b.Append('"'); return b.ToString();
        }
        internal static string Hash(byte[] bytes) { using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant(); }
        internal static string IOPath(string path) { if(path.StartsWith(@"\\?\")) return path;string full=Path.GetFullPath(path);return full.StartsWith(@"\\")?@"\\?\UNC\"+full.Substring(2):@"\\?\"+full; }
        internal static string FileHash(string path) { using(var s=File.OpenRead(IOPath(path))) using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(s)).Replace("-","").ToLowerInvariant(); }
        internal static void Log(string text, bool service=false) {
            try { lock(LogGate) {
                Directory.CreateDirectory(Logs);
                string p=Path.Combine(Logs,service?"service.log":"desktop.log");
                if(File.Exists(p) && new FileInfo(p).Length>4*1024*1024) { if(File.Exists(p+".old")) File.Delete(p+".old"); File.Move(p,p+".old"); }
                File.AppendAllText(p,DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")+" "+text+Environment.NewLine,new UTF8Encoding(false));
            }} catch { }
        }
        internal static void Initialize(Options options) {
            Options=options; Root=options.StateRoot;
            Directory.CreateDirectory(Root);
            string saved=Path.Combine(Root,"data-home.txt");
            Home=options.Home;
            if(Home==null && File.Exists(saved)) Home=File.ReadAllText(saved,Encoding.UTF8).Trim();
            if(Home==null) {
                var parent=new DirectoryInfo(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location));
                for(int i=0;i<6 && parent!=null;i++,parent=parent.Parent) {
                    if(File.Exists(Path.Combine(parent.FullName,"app","cli.py")) && File.Exists(Path.Combine(parent.FullName,"config","source_registry.json")) && File.Exists(Path.Combine(parent.FullName,"data","latest.json"))) { Home=parent.FullName; break; }
                }
            }
            Home=Path.GetFullPath(Home ?? Path.Combine(Root,"workspace"));
            Directory.CreateDirectory(Path.Combine(Home,"data")); Directory.CreateDirectory(Path.Combine(Home,"logs"));
            File.WriteAllText(saved,Home,new UTF8Encoding(false));
            var asm=Assembly.GetExecutingAssembly();
            using(var r=new StreamReader(asm.GetManifestResourceStream("payload.id"))) PayloadId=r.ReadToEnd().Trim();
            if(PayloadId.Length!=64 || PayloadId.Any(c=>!Uri.IsHexDigit(c))) throw new IOException("内置运行包校验信息无效。");
            Payload=Extract(asm,PayloadId);
            Launcher=Assembly.GetExecutingAssembly().Location;
            if(!options.Isolated) {
                string installed=Path.Combine(Root,"app","NasdaqQDII.exe"); Directory.CreateDirectory(Path.GetDirectoryName(installed));
                if(!String.Equals(Path.GetFullPath(Launcher),Path.GetFullPath(installed),StringComparison.OrdinalIgnoreCase)) {
                    if(!File.Exists(installed) || FileHash(installed)!=FileHash(Launcher)) {
                        if(File.Exists(installed)) File.Copy(installed,installed+".previous",true);
                        File.Copy(Launcher,installed,true);
                    }
                    Launcher=installed;
                }
                if(!options.NoShortcuts) CreateShortcuts();
            }
        }
        internal static string Extract(Assembly asm,string id) {
            string releases=Path.Combine(Root,"releases"); Directory.CreateDirectory(releases);
            string target=Path.Combine(releases,id.Substring(0,20));
            string marker=Path.Combine(target,".complete");
            if(File.Exists(marker) && File.ReadAllText(marker).Trim()==id && File.Exists(Path.Combine(target,"python","python.exe")) && File.Exists(Path.Combine(target,"app","desktop_worker.py")) && File.Exists(Path.Combine(target,"web","index.html"))) return target;
            if(Directory.Exists(target)) throw new IOException("该运行版本解压不完整。请查看日志并重新安装运行文件，数据目录不受影响。");
            string stage=Path.Combine(releases,id.Substring(0,12)+".tmp-"+Guid.NewGuid().ToString("N").Substring(0,8)); Directory.CreateDirectory(IOPath(stage));
            try {
                using(var stream=asm.GetManifestResourceStream("payload.zip")) {
                    using(var sha=SHA256.Create()) { if(BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant()!=id) throw new IOException("内置运行包SHA-256校验失败。"); }
                    stream.Position=0;
                    using(var zip=new ZipArchive(stream,ZipArchiveMode.Read)) {
                        var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                        foreach(var entry in zip.Entries) {
                            string path=Path.GetFullPath(Path.Combine(stage,entry.FullName.Replace('/',Path.DirectorySeparatorChar)));
                            if(!path.StartsWith(stage+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase) || !seen.Add(path)) throw new IOException("运行包含有无效或重复路径。");
                            if(entry.FullName.EndsWith("/")) { Directory.CreateDirectory(IOPath(path)); continue; }
                            Directory.CreateDirectory(IOPath(Path.GetDirectoryName(path))); entry.ExtractToFile(IOPath(path));
                        }
                    }
                }
                var manifest=Json.Deserialize<Dictionary<string,string>>(File.ReadAllText(Path.Combine(stage,"payload-manifest.json"),Encoding.UTF8));
                foreach(var file in manifest) {
                    string path=Path.GetFullPath(Path.Combine(stage,file.Key));
                    if(!path.StartsWith(stage+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase) || !File.Exists(IOPath(path)) || FileHash(path)!=file.Value) throw new IOException("运行文件校验失败："+file.Key);
                }
                File.WriteAllText(IOPath(Path.Combine(stage,".complete")),id,new UTF8Encoding(false)); Directory.Move(IOPath(stage),IOPath(target)); return target;
            } catch {
                string full=Path.GetFullPath(stage),basePath=Path.GetFullPath(releases)+Path.DirectorySeparatorChar;
                if(full.StartsWith(basePath,StringComparison.OrdinalIgnoreCase) && Path.GetFileName(full).Contains(".tmp-")) try { Directory.Delete(IOPath(full),true); } catch { }
                throw;
            }
        }
        static void CreateShortcuts() {
            string desktop=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"纳指观察.lnk");
            string menu=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"纳指观察.lnk");
            foreach(string path in new[]{desktop,menu}) try {
                Type t=Type.GetTypeFromProgID("WScript.Shell"); object shell=Activator.CreateInstance(t), shortcut=null;
                try {
                    shortcut=t.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{path}); var s=shortcut.GetType();
                    s.InvokeMember("TargetPath",BindingFlags.SetProperty,null,shortcut,new object[]{Launcher});
                    s.InvokeMember("WorkingDirectory",BindingFlags.SetProperty,null,shortcut,new object[]{Path.GetDirectoryName(Launcher)});
                    s.InvokeMember("IconLocation",BindingFlags.SetProperty,null,shortcut,new object[]{Launcher+",0"});
                    s.InvokeMember("Description",BindingFlags.SetProperty,null,shortcut,new object[]{"纳斯达克与QDII每日观察"});
                    s.InvokeMember("Save",BindingFlags.InvokeMethod,null,shortcut,null);
                } finally { if(shortcut!=null) Marshal.FinalReleaseComObject(shortcut); Marshal.FinalReleaseComObject(shell); }
            } catch(Exception ex) { Log("创建快捷方式："+ex.Message); }
        }
        internal static ProcessStartInfo Worker(string command) {
            var info=new ProcessStartInfo(Python,"-B -X utf8 -m app.desktop_worker --home "+Quote(Home)+" "+command+(command=="serve"?" --port "+Options.Port:"")) {
                UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=Payload,
                RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
            };
            ConfigureProxy(info); return info;
        }
        internal static void ConfigureProxy(ProcessStartInfo info) {
            using(var k=Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Internet Settings")) {
                if(k!=null && Convert.ToInt32(k.GetValue("ProxyEnable",0))==1) {
                    string raw=Convert.ToString(k.GetValue("ProxyServer",""));
                    foreach(string protocol in new[]{"http","https"}) {
                        string key=protocol.ToUpperInvariant()+"_PROXY"; if(!String.IsNullOrWhiteSpace(info.EnvironmentVariables[key])) continue;
                        string chosen=raw;
                        if(raw.Contains("=")) { var dict=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase); foreach(string part in raw.Split(';')) { var v=part.Split(new[]{'='},2); if(v.Length==2) dict[v[0].Trim()]=v[1].Trim(); } if(!dict.TryGetValue(protocol,out chosen)) dict.TryGetValue("http",out chosen); }
                        if(String.IsNullOrWhiteSpace(chosen)) continue; if(!chosen.Contains("://")) chosen="http://"+chosen;
                        Uri u; if(Uri.TryCreate(chosen,UriKind.Absolute,out u) && (u.Scheme=="http" || u.Scheme=="https")) info.EnvironmentVariables[key]=chosen;
                    }
                }
            }
            info.EnvironmentVariables["NO_PROXY"]="localhost,127.0.0.1,::1,"+info.EnvironmentVariables["NO_PROXY"];
        }
        internal static Dictionary<string,object> Health() {
            try {
                var req=(HttpWebRequest)WebRequest.Create(Url+"api/health"); req.Proxy=null; req.Timeout=3500; req.ReadWriteTimeout=3500;
                using(var response=req.GetResponse()) using(var reader=new StreamReader(response.GetResponseStream(),Encoding.UTF8)) { string raw=reader.ReadToEnd(); if(raw.Length>65536) return null; return Json.Deserialize<Dictionary<string,object>>(raw); }
            } catch(WebException) { return null; } catch(ArgumentException) { return null; }
        }
    }
    internal static class Startup {
        const string Key=@"Software\Microsoft\Windows\CurrentVersion\Run",Name="NasdaqQDII";
        internal static bool Enabled { get { using(var key=Registry.CurrentUser.OpenSubKey(Key)) return key!=null && Convert.ToString(key.GetValue(Name,""))==Paths.Quote(Paths.Launcher)+" --autostart"; } }
        internal static void Set(bool enabled) {
            if(Paths.Options.Isolated) throw new InvalidOperationException("隔离验证模式不修改登录启动。");
            using(var key=Registry.CurrentUser.CreateSubKey(Key)) { if(enabled) key.SetValue(Name,Paths.Quote(Paths.Launcher)+" --autostart"); else key.DeleteValue(Name,false); }
        }
    }
    internal sealed class Runtime : IDisposable {
        internal Process Service; Job serviceJob,taskJob; internal bool Borrowed,HasSnapshot; internal string Detail="正在启动"; DateTime started;
        internal string TaskName="",LastTask="",LastTaskResult=""; internal int? LastExit; readonly object taskGate=new object(); bool disposed;
        internal bool TaskBusy { get { lock(taskGate) return TaskName.Length>0; } }
        internal int? ServicePid { get { try { return Service!=null && !Service.HasExited?(int?)Service.Id:null; } catch(InvalidOperationException) { return null; } } }
        internal bool Tick() {
            if(disposed) return false;
            int pid=ListeningPid(Paths.Options.Port);
            if(Service!=null && Service.HasExited) { int code=Service.ExitCode; StopService(); throw new IOException("服务已退出（"+code+"），可点击启动服务重试。"); }
            if(pid!=0) {
                var health=Paths.Health(); object application,home,status;
                bool identity=health!=null && health.TryGetValue("application",out application) && Convert.ToString(application)=="nasdaq-qdii-monitor" && health.TryGetValue("home_id",out home) && Convert.ToString(home)==Paths.HomeId;
                bool legacy=false;
                if(!identity && health!=null && health.TryGetValue("status",out status) && Convert.ToString(status)=="ok" && health.ContainsKey("readonly") && Convert.ToBoolean(health["readonly"])) {
                    legacy=LegacyOwner(pid);
                }
                if(identity || legacy) {
                    if(Service!=null && pid!=Service.Id) throw new IOException("端口由另一服务占用，程序不会关闭它。");
                    Borrowed=Service==null; HasSnapshot=health.ContainsKey("has_snapshot") && Convert.ToBoolean(health["has_snapshot"]);
                    Detail=Borrowed?"已连接原项目服务，沿用现有数据与自动任务":"程序服务运行中"; return true;
                }
                if(Service!=null && pid==Service.Id && (DateTime.UtcNow-started).TotalSeconds<60) { Detail="服务正在初始化"; return false; }
                throw new IOException("端口 "+Paths.Options.Port+" 已被其他程序占用；请在设置中换端口，原程序不会被关闭。");
            }
            if(Service!=null) { if((DateTime.UtcNow-started).TotalSeconds>60) { StopService(); throw new IOException("服务启动超时，请查看日志并重试。"); } Detail="服务正在初始化"; return false; }
            serviceJob=new Job(); Service=new Process { StartInfo=Paths.Worker("serve") }; Borrowed=false;
            Service.OutputDataReceived+=(s,e)=>{if(e.Data!=null) Paths.Log(e.Data,true);}; Service.ErrorDataReceived+=(s,e)=>{if(e.Data!=null) Paths.Log(e.Data,true);};
            try { Service.Start(); serviceJob.Assign(Service); Service.BeginOutputReadLine(); Service.BeginErrorReadLine(); started=DateTime.UtcNow; Detail="服务正在初始化"; Paths.Log("启动程序服务 PID "+Service.Id); return false; } catch { StopService(); throw; }
        }
        internal bool BeginTask(string command,ProcessStartInfo info=null) {
            lock(taskGate) { if(disposed || TaskName.Length>0) return false; TaskName=command; LastExit=null; }
            System.Threading.Tasks.Task.Run(()=> {
                int code=-1;
                try {
                    using(var p=new Process { StartInfo=info ?? Paths.Worker(command) }) {
                        var tail=new StringBuilder(); object tailGate=new object();
                        DataReceivedEventHandler receive=(s,e)=>{if(e.Data!=null) { Paths.Log(command+": "+e.Data,true); lock(tailGate) { tail.AppendLine(e.Data); if(tail.Length>6000) tail.Remove(0,tail.Length-6000); } }};
                        p.OutputDataReceived+=receive; p.ErrorDataReceived+=receive;
                        lock(taskGate) { if(disposed) return; taskJob=new Job(); p.Start(); taskJob.Assign(p); }
                        p.BeginOutputReadLine(); p.BeginErrorReadLine(); p.WaitForExit(); code=p.ExitCode;
                        lock(taskGate) LastTaskResult=tail.ToString().Trim();
                    }
                } catch(Exception ex) { lock(taskGate) LastTaskResult=ex.Message; Paths.Log(command+"失败："+ex.Message); }
                finally { lock(taskGate) { if(taskJob!=null) { taskJob.Dispose(); taskJob=null; } LastTask=command; LastExit=code; TaskName=""; } }
            }); return true;
        }
        internal void StopService() {
            if(serviceJob!=null) { serviceJob.Dispose(); serviceJob=null; }
            if(Service!=null) { try { if(!Service.HasExited && !Service.WaitForExit(2500)) Service.Kill(); } catch { } Service.Dispose(); Service=null; }
            Borrowed=false;
        }
        internal static int ListeningPid(int port) {
            int length=0; GetExtendedTcpTable(IntPtr.Zero,ref length,false,2,5,0); if(length<4) return 0;
            IntPtr buffer=Marshal.AllocHGlobal(length);
            try {
                if(GetExtendedTcpTable(buffer,ref length,false,2,5,0)!=0) return 0;
                int count=Marshal.ReadInt32(buffer),size=Marshal.SizeOf(typeof(TcpRow));
                for(int i=0;i<count && 4+(i+1)*size<=length;i++) {
                    var r=(TcpRow)Marshal.PtrToStructure(IntPtr.Add(buffer,4+i*size),typeof(TcpRow));
                    int actual=(int)(((r.Port&255)<<8)|((r.Port>>8)&255));
                    if(r.State==2 && actual==port) return (int)r.Pid;
                }
            } finally { Marshal.FreeHGlobal(buffer); }
            return IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners().Any(e=>e.Port==port)?-1:0;
        }
        static bool LegacyOwner(int pid) {
            try {
                using(var p=Process.GetProcessById(pid)) {
                    string exe=p.MainModule.FileName;
                    if(new[]{"python.exe","pythonw.exe"}.Any(n=>String.Equals(exe,Path.Combine(Paths.Home,".venv","Scripts",n),StringComparison.OrdinalIgnoreCase))) return true;
                    if(!new[]{"python.exe","pythonw.exe"}.Contains(Path.GetFileName(exe),StringComparer.OrdinalIgnoreCase)) return false;
                }
                using(var row=new ManagementObject("Win32_Process.Handle='"+pid+"'")) {
                    row.Get();int parent=Convert.ToInt32(row["ParentProcessId"]);
                    using(var p=Process.GetProcessById(parent)) return new[]{"python.exe","pythonw.exe"}.Any(n=>String.Equals(p.MainModule.FileName,Path.Combine(Paths.Home,".venv","Scripts",n),StringComparison.OrdinalIgnoreCase));
                }
            } catch { return false; }
        }
        [StructLayout(LayoutKind.Sequential)] struct TcpRow { public uint State,Address,Port,RemoteAddress,RemotePort,Pid; }
        [DllImport("iphlpapi.dll",SetLastError=true)] static extern uint GetExtendedTcpTable(IntPtr table,ref int length,bool order,int family,int tableClass,uint reserved);
        public void Dispose() { lock(taskGate) { disposed=true; if(taskJob!=null) { taskJob.Dispose(); taskJob=null; } } StopService(); }
    }
    internal sealed class Job : IDisposable {
        IntPtr handle;
        [StructLayout(LayoutKind.Sequential)] struct Basic { public long ProcessTime,JobTime; public uint Flags; public UIntPtr Min,Max; public uint Active; public UIntPtr Affinity; public uint Priority,Scheduling; }
        [StructLayout(LayoutKind.Sequential)] struct Io { public ulong ReadOps,WriteOps,OtherOps,ReadBytes,WriteBytes,OtherBytes; }
        [StructLayout(LayoutKind.Sequential)] struct Limits { public Basic Basic; public Io Io; public UIntPtr ProcessMemory,JobMemory,PeakProcessMemory,PeakJobMemory; }
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attrs,string name);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int type,IntPtr info,uint length);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
        internal Job() {
            handle=CreateJobObject(IntPtr.Zero,null); if(handle==IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
            var limits=new Limits(); limits.Basic.Flags=0x2000; int size=Marshal.SizeOf(limits); IntPtr data=Marshal.AllocHGlobal(size);
            try { Marshal.StructureToPtr(limits,data,false); if(!SetInformationJobObject(handle,9,data,(uint)size)) { int code=Marshal.GetLastWin32Error(); Dispose(); throw new System.ComponentModel.Win32Exception(code); } } finally { Marshal.FreeHGlobal(data); }
        }
        internal void Assign(Process p) { if(!AssignProcessToJobObject(handle,p.Handle)) throw new System.ComponentModel.Win32Exception(); }
        public void Dispose() { if(handle!=IntPtr.Zero) { CloseHandle(handle); handle=IntPtr.Zero; } }
    }
}

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("纳指观察")]
[assembly: AssemblyDescription("纳斯达克与QDII本机观察程序")]
[assembly: AssemblyVersion("0.5.0.0")]
[assembly: AssemblyFileVersion("0.5.0.0")]

namespace NasdaqQDII {
    internal static class Icons {
        [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr icon);
        internal static Bitmap Draw(int size,Color color) {
            var image=new Bitmap(size,size);
            using(var g=Graphics.FromImage(image)) {
                g.SmoothingMode=SmoothingMode.AntiAlias; g.Clear(Color.Transparent); g.ScaleTransform(size/64f,size/64f);
                using(var path=new GraphicsPath()) { path.AddArc(2,2,18,18,180,90); path.AddArc(44,2,18,18,270,90); path.AddArc(44,44,18,18,0,90); path.AddArc(2,44,18,18,90,90); path.CloseFigure(); using(var b=new SolidBrush(color)) g.FillPath(b,path); }
                using(var pen=new Pen(Color.FromArgb(13,38,56),7)) { pen.StartCap=LineCap.Round; pen.EndCap=LineCap.Round; pen.LineJoin=LineJoin.Round; g.DrawLines(pen,new[]{new PointF(20,47),new PointF(20,17),new PointF(44,47),new PointF(44,17)}); }
            } return image;
        }
        internal static Icon Make(Color color) {
            using(var bitmap=Draw(32,color)) { IntPtr h=bitmap.GetHicon(); try { using(var icon=Icon.FromHandle(h)) return (Icon)icon.Clone(); } finally { DestroyIcon(h); } }
        }
    }
    internal sealed class TrayContext : ApplicationContext {
        readonly Runtime runtime=new Runtime(); readonly object serviceGate=new object();
        readonly NotifyIcon tray; readonly Control dispatcher=new Control(); readonly System.Windows.Forms.Timer timer;
        readonly Icon readyIcon=Icons.Make(Color.FromArgb(75,215,173)),waitingIcon=Icons.Make(Color.FromArgb(239,191,102)),errorIcon=Icons.Make(Color.FromArgb(238,112,119)),pausedIcon=Icons.Make(Color.FromArgb(162,177,188));
        readonly ToolStripMenuItem statusMenu,openMenu,startMenu,stopMenu,collectMenu,fundMenu,retryMenu,backupMenu;
        SettingsWindow panel; readonly RemoteRuntime remote=new RemoteRuntime();
        bool enabled=true,ready,opened,initialCollect,closing,failed; int polling;
        volatile string statusJson="{\"state\":\"starting\"}"; string state="starting",message="正在准备服务";
        internal TrayContext() {
            var handle=dispatcher.Handle;
            var menu=new ContextMenuStrip { Font=new Font("Microsoft YaHei UI",10),ShowImageMargin=false };
            statusMenu=new ToolStripMenuItem("正在启动…") { Enabled=false };
            openMenu=new ToolStripMenuItem("打开观察网站",null,(s,e)=>OpenWeb());
            collectMenu=new ToolStripMenuItem("立即采集",null,(s,e)=>Run("collect"));
            fundMenu=new ToolStripMenuItem("更新基金",null,(s,e)=>Run("funds"));
            retryMenu=new ToolStripMenuItem("补采未齐数据",null,(s,e)=>Run("retry"));
            backupMenu=new ToolStripMenuItem("备份数据库",null,(s,e)=>Run("backup"));
            startMenu=new ToolStripMenuItem("启动 / 重试服务",null,(s,e)=>Enable());
            stopMenu=new ToolStripMenuItem("停止程序服务",null,(s,e)=>Disable());
            menu.Items.AddRange(new ToolStripItem[]{statusMenu,new ToolStripSeparator(),openMenu,collectMenu,fundMenu,retryMenu,backupMenu,new ToolStripSeparator(),startMenu,stopMenu,new ToolStripMenuItem("设置与自动任务",null,(s,e)=>ShowPanel()),new ToolStripMenuItem("查看日志",null,(s,e)=>OpenFolder(Paths.Logs)),new ToolStripSeparator(),new ToolStripMenuItem("退出程序",null,(s,e)=>Exit())});
            tray=new NotifyIcon { Visible=true,Icon=waitingIcon,Text="纳指观察：正在启动",ContextMenuStrip=menu };
            tray.DoubleClick+=(s,e)=>{if(ready) OpenWeb(); else ShowPanel();};
            timer=new System.Windows.Forms.Timer { Interval=3000 }; timer.Tick+=(s,e)=>Poll(); timer.Start();
            Microsoft.Win32.SystemEvents.SessionEnding+=OnSessionEnding;
            Task.Run((Action)PipeLoop); UpdateUi(); Poll();
        }
        void OnSessionEnding(object sender,Microsoft.Win32.SessionEndingEventArgs e) { closing=true; lock(serviceGate) runtime.Dispose(); remote.Dispose(); }
        void Poll() {
            if(closing || Interlocked.CompareExchange(ref polling,1,0)!=0) return;
            Task.Run(()=> {
                try { lock(serviceGate) {
                    if(closing) return;
                    if(enabled && !failed) { ready=runtime.Tick(); state=ready?"ready":"starting"; message=runtime.Detail; }
                    else if(!enabled) { ready=false; state="paused"; message="程序服务已暂停"; }
                    if(ready && !runtime.HasSnapshot) message=runtime.TaskBusy?"首次数据采集中，请等待完成":"服务已启动，尚无数据快照";
                    if(ready && !runtime.HasSnapshot && !initialCollect && !Paths.Options.Isolated) { initialCollect=true; runtime.BeginTask("collect"); }
                    Publish();
                } remote.Tick(ready); } catch(Exception ex) { failed=true; ready=false; state="error"; message=ex.Message; Paths.Log("服务："+ex.Message); Publish(); }
                finally { Interlocked.Exchange(ref polling,0); if(!closing) try { dispatcher.BeginInvoke((Action)UpdateUi); } catch(InvalidOperationException) { } }
            });
        }
        void Publish() {
            statusJson=Paths.Json.Serialize(new {
                application="nasdaq-qdii-desktop",version="0.5.0",state=state,detail=message,url=Paths.Url,
                home=Paths.Home,dataDirectory=Path.Combine(Paths.Home,"data"),payload=Paths.Payload,
                servicePid=runtime.ServicePid,serviceOwned=runtime.ServicePid.HasValue,attachedExisting=runtime.Borrowed,
                hasSnapshot=runtime.HasSnapshot,taskBusy=runtime.TaskBusy,task=runtime.TaskName,lastTask=runtime.LastTask,
                lastExit=runtime.LastExit,lastResult=runtime.LastTaskResult,autoStart=!Paths.Options.Isolated && Startup.Enabled,
                remoteEnabled=remote.Enabled,remoteConnected=remote.Connected,remoteStatus=remote.Status,remotePid=remote.Pid,remoteUrl="https://"+remote.Domain,
                trayVisible=tray.Visible,updatedAt=DateTimeOffset.UtcNow.ToString("o")
            });
        }
        void UpdateUi() {
            if(closing) return;
            tray.Icon=state=="ready"?readyIcon:state=="error"?errorIcon:state=="paused"?pausedIcon:waitingIcon;
            string label=state=="ready"?"运行中":state=="error"?"需要处理":state=="paused"?"已暂停":"正在启动";
            tray.Text="纳指观察："+label; statusMenu.Text=runtime.TaskBusy?TaskLabel(runtime.TaskName)+"…":message;
            openMenu.Enabled=ready; startMenu.Enabled=!enabled || failed; stopMenu.Enabled=ready && !runtime.Borrowed;
            foreach(var item in new[]{collectMenu,fundMenu,retryMenu,backupMenu}) item.Enabled=!runtime.TaskBusy;
            if(panel!=null && !panel.IsDisposed) {
                panel.Headline.Text="纳指观察 · "+label; panel.Detail.Text=message;
                panel.TaskStatus.Text=runtime.TaskBusy?TaskLabel(runtime.TaskName)+"，完成情况见日志":runtime.LastExit.HasValue?(TaskLabel(runtime.LastTask)+(runtime.LastExit==0?"完成":"失败（"+runtime.LastExit+"）")+"\n"+LastLine(runtime.LastTaskResult)):"采集与备份在后台运行，窗口可以关闭到托盘。";
                panel.PortApply.Enabled=!runtime.TaskBusy; panel.RemoteStatus.Text=remote.Status; panel.Startup.Checked=!Paths.Options.Isolated && Startup.Enabled;
            }
            if(ready && runtime.HasSnapshot && !opened && !Paths.Options.NoBrowser) { opened=true; OpenWeb(); }
            if(!Paths.Options.NoBrowser && ((!runtime.HasSnapshot && ready) || failed) && panel==null) ShowPanel();
        }
        static string LastLine(string text) { return String.IsNullOrEmpty(text)?"":text.Split(new[]{'\r','\n'},StringSplitOptions.RemoveEmptyEntries).LastOrDefault() ?? ""; }
        static string TaskLabel(string command) { switch(command) { case "collect":return "全量采集";case "funds":return "基金更新";case "retry":return "定向补采";case "backup":return "数据库备份";case "install-tasks":return "自动任务配置";default:return command; } }
        void Run(string command) { if(!runtime.BeginTask(command)) { if(!Paths.Options.NoBrowser) MessageBox.Show("已有任务正在运行，请等待完成。","纳指观察"); } Publish(); UpdateUi(); }
        void Enable() { lock(serviceGate) { enabled=true;failed=false; } Poll(); }
        void Disable() { remote.Stop(); lock(serviceGate) { enabled=false;failed=false;runtime.StopService(); } Poll(); }
        void OpenWeb() { try { Process.Start(new ProcessStartInfo(Paths.Url+"#overview") { UseShellExecute=true }); } catch(Exception ex) { Paths.Log("打开网站："+ex.Message); if(!Paths.Options.NoBrowser) MessageBox.Show(ex.Message,"无法打开浏览器"); } }
        static void OpenFolder(string path) { Directory.CreateDirectory(path); Process.Start(new ProcessStartInfo(path) { UseShellExecute=true }); }
        void ShowPanel() {
            if(panel!=null && !panel.IsDisposed) { panel.Show();panel.Activate();return; }
            panel=new SettingsWindow(OpenWeb,Run,InstallTasks,ApplyPort,()=>{remote.Stop();Poll();});panel.Icon=readyIcon;
            panel.FormClosed+=(s,e)=>panel=null;UpdateUi();panel.Show();
        }
        void ApplyPort(int value) {
            remote.Stop();
            lock(serviceGate) { runtime.StopService();Paths.Options.Port=value;File.WriteAllText(Path.Combine(Paths.Root,"port.txt"),value.ToString());enabled=true;failed=false;opened=false; }
            Poll();
        }
        void InstallTasks() {
            if(Paths.Options.Isolated) return;
            if(runtime.TaskBusy) { MessageBox.Show("请先等待当前任务完成。","纳指观察");return; }
            if(MessageBox.Show("将登记北京时间的8个本机任务：启动、采集、补采、基金、早报预览、备份和周档。\n\n原项目的同名任务会先备份，再更新路径；正在运行的原服务任务会保留。邮件保持预览。\n\n是否启用？","配置自动任务",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes) return;
            string powershell=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),@"WindowsPowerShell\v1.0\powershell.exe");
            var info=new ProcessStartInfo(powershell,"-NoProfile -ExecutionPolicy Bypass -File "+Paths.Quote(Path.Combine(Paths.Payload,"desktop","install-tasks.ps1"))+" -DataHome "+Paths.Quote(Paths.Home)+" -LauncherPath "+Paths.Quote(Paths.Launcher)) { UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=Paths.Payload,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8 };
            runtime.BeginTask("install-tasks",info);Publish();UpdateUi();
        }
        void PipeLoop() {
            var security=new PipeSecurity();security.SetAccessRuleProtection(true,false);security.AddAccessRule(new PipeAccessRule(WindowsIdentity.GetCurrent().User,PipeAccessRights.FullControl,AccessControlType.Allow));
            while(!closing) try {
                using(var pipe=new NamedPipeServerStream(Program.PipeName,PipeDirection.InOut,1,PipeTransmissionMode.Byte,PipeOptions.Asynchronous,4096,4096,security)) {
                    var connected=pipe.BeginWaitForConnection(null,null);while(!closing && !connected.AsyncWaitHandle.WaitOne(200)) { } if(closing) return;pipe.EndWaitForConnection(connected);
                    using(var reader=new StreamReader(pipe,Encoding.UTF8,false,1024,true)) {
                        var read=reader.ReadLineAsync();if(!read.Wait(3000)) continue;string cmd=read.Result;
                        string result=statusJson;
                        if(cmd!="status") {
                            bool accepted=false;
                            dispatcher.Invoke((Action)(()=> {
                                switch(cmd) {
                                    case "open":OpenWeb();accepted=true;break;case "show":ShowPanel();accepted=true;break;
                                    case "start":Enable();accepted=true;break;case "stop":Disable();accepted=true;break;
                                    case "remote-stop":var config=RemoteSettings.Load();config.Enabled=false;config.Save();remote.Stop();accepted=true;break;
                                    case "restart":remote.Stop();lock(serviceGate) runtime.StopService();Enable();accepted=true;break;
                                    case "collect":case "funds":case "retry":case "backup":accepted=runtime.BeginTask(cmd);break;
                                    case "exit":accepted=true;dispatcher.BeginInvoke((Action)Exit);break;
                                }
                                Publish();UpdateUi();
                            }));result=Paths.Json.Serialize(new {accepted=accepted});
                        }
                        byte[] bytes=Encoding.UTF8.GetBytes(result+"\n");pipe.Write(bytes,0,bytes.Length);pipe.Flush();
                    }
                }
            } catch(Exception ex) { if(!closing) { Paths.Log("本机IPC："+ex.Message);Thread.Sleep(200); } }
        }
        async void Exit() {
            if(closing) return;closing=true;timer.Stop();tray.Text="纳指观察：正在退出";
            await Task.Run(()=>{lock(serviceGate) runtime.Dispose(); remote.Dispose();});tray.Visible=false;tray.Dispose();if(panel!=null) panel.Close();ExitThread();
        }
        protected override void Dispose(bool disposing) {
            if(disposing) {closing=true;timer.Dispose();lock(serviceGate) runtime.Dispose(); remote.Dispose();tray.Visible=false;tray.Dispose();readyIcon.Dispose();waitingIcon.Dispose();errorIcon.Dispose();pausedIcon.Dispose();dispatcher.Dispose();Microsoft.Win32.SystemEvents.SessionEnding-=OnSessionEnding;}
            base.Dispose(disposing);
        }
    }
    internal static class Program {
        internal static string PipeName;
        static string Send(string command) {
            using(var pipe=new NamedPipeClientStream(".",PipeName,PipeDirection.InOut,PipeOptions.Asynchronous)) {pipe.Connect(5000);byte[] bytes=Encoding.UTF8.GetBytes(command+"\n");pipe.Write(bytes,0,bytes.Length);pipe.Flush();using(var reader=new StreamReader(pipe)) {var r=reader.ReadLineAsync();if(!r.Wait(12000)) throw new IOException("程序暂未响应，请查看日志。");return r.Result;}}
        }
        static void Result(Options o,string json) { if(o.Result!=null) {Directory.CreateDirectory(Path.GetDirectoryName(o.Result));File.WriteAllText(o.Result,json,new UTF8Encoding(false));}else Console.WriteLine(json); }
        [STAThread] static int Main(string[] args) {
            AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling",false);
            AppContext.SetSwitch("Switch.System.IO.BlockLongPaths",false);
            Options o=null;
            try {
                o=Options.Parse(args);Paths.Options=o;Paths.Root=o.StateRoot;
                PipeName="NasdaqQDII-"+WindowsIdentity.GetCurrent().User.Value+"-"+Process.GetCurrentProcess().SessionId+"-"+Paths.Hash(Encoding.UTF8.GetBytes(o.StateRoot.ToLowerInvariant())).Substring(0,16);
                if(o.Command!=null) {Result(o,Send(o.Command));return 0;}
                if(o.RemoteConfigure!=null) {
                    if(o.Isolated)throw new InvalidOperationException("隔离模式不修改云端配置。");
                    Paths.Initialize(o);var requested=Paths.Json.Deserialize<RemoteSettings>(File.ReadAllText(o.RemoteConfigure,Encoding.UTF8));requested.Validate();
                    var saved=RemoteSettings.Load();
                    if(saved.AccessAppId.Length>0 || saved.TunnelId.Length>0) {
                        if(saved.Domain!=requested.Domain || saved.AccountId!=requested.AccountId || saved.ZoneId!=requested.ZoneId)throw new IOException("已有远程资源属于其他配置。");
                        requested.AccessAppId=saved.AccessAppId;requested.Audience=saved.Audience;requested.TunnelId=saved.TunnelId;requested.DnsId=saved.DnsId;
                    }
                    requested.Enabled=false;requested.Save();
                    new CloudflareClient(RemoteSecrets.ApiToken(requested)).Configure(requested,text=>Paths.Log(text));
                    Result(o,Paths.Json.Serialize(new{configured=true,domain=requested.Domain,tunnelId=requested.TunnelId,accessAppId=requested.AccessAppId}));return 0;
                }
                if(o.ExtractOnly) {Paths.Initialize(o);Result(o,Paths.Json.Serialize(new{payload=Paths.Payload,python=Paths.Python,home=Paths.Home,payloadId=Paths.PayloadId}));return 0;}
                bool first;using(var mutex=new Mutex(true,"Local\\"+PipeName,out first)) {
                    if(!first) {if(!o.NoBrowser) try {Send("open");}catch{}return 0;}
                    try {
                        Paths.Initialize(o);
                        if(Array.IndexOf(args,"--port")<0 && File.Exists(Path.Combine(Paths.Root,"port.txt"))) {int saved;if(Int32.TryParse(File.ReadAllText(Path.Combine(Paths.Root,"port.txt")),out saved) && saved>=1024 && saved<=65535) o.Port=saved;}
                        Paths.Log("程序启动 v0.5.0；数据 "+Paths.Home);
                        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
                        using(var context=new TrayContext()) Application.Run(context);
                    } finally {mutex.ReleaseMutex();}
                } return 0;
            } catch(Exception ex) {
                Paths.Log("启动失败："+ex);
                if(o!=null && o.Result!=null) Result(o,Paths.Json.Serialize(new{error=ex.Message}));
                if(o==null || (!o.NoBrowser && o.Command==null)) MessageBox.Show(ex.Message,"纳指观察启动失败",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;
            }
        }
    }
}

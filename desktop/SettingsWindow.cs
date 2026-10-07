using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace NasdaqQDII {
    internal sealed class SettingsWindow : Form {
        internal Label Headline,Detail,TaskStatus,RemoteStatus;
        internal CheckBox Startup;
        internal NumericUpDown Port;
        internal Button PortApply;
        internal TabControl Tabs;
        internal bool Working;
        float displayScale=1;
        static readonly Color Navy=Color.FromArgb(17,39,57),Muted=Color.FromArgb(82,103,121),Teal=Color.FromArgb(18,115,101);
        internal SettingsWindow(Action open,Action<string> run,Action install,Action<int> applyPort,Action remoteChanged) {
            Text="纳指观察 · 设置与自动任务";Font=new Font("Microsoft YaHei UI",10);BackColor=Color.White;
            AutoScaleMode=AutoScaleMode.None;ClientSize=new Size(680,610);MinimumSize=new Size(420,380);
            StartPosition=FormStartPosition.CenterScreen;MaximizeBox=true;
            var shell=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=3,Padding=new Padding(20),BackColor=Color.White};
            shell.RowStyles.Add(new RowStyle(SizeType.AutoSize));shell.RowStyles.Add(new RowStyle(SizeType.Percent,100));shell.RowStyles.Add(new RowStyle(SizeType.AutoSize));Controls.Add(shell);
            var header=Stack();header.Margin=new Padding(0,0,0,14);
            Headline=Label("纳指观察",15,true);Detail=Label("正在读取状态…");header.Controls.Add(Headline);header.Controls.Add(Detail);shell.Controls.Add(header,0,0);
            Tabs=new TabControl {Dock=DockStyle.Fill,Margin=new Padding(0),Padding=new Point(16,8)};shell.Controls.Add(Tabs,0,1);
            var local=Page("运行与数据");var schedule=Page("自动任务");var remote=Page("远程访问");
            Add(local,Label("日常操作",12,true));
            Add(local,Buttons(new[]{"打开观察网站","立即采集","更新基金"},new Action[]{open,()=>run("collect"),()=>run("funds")}));
            Add(local,Buttons(new[]{"补采未齐数据","备份数据库","查看日志"},new Action[]{()=>run("retry"),()=>run("backup"),()=>OpenFolder(Paths.Logs)}));
            TaskStatus=Label("采集与备份在后台运行。");Add(local,TaskStatus);
            Add(local,Label("数据目录",12,true));Add(local,Label(Paths.Home));
            Add(local,Buttons(new[]{"打开数据目录"},new Action[]{()=>OpenFolder(Path.Combine(Paths.Home,"data"))}));
            Add(local,Label("本机服务",12,true));
            var portLine=new FlowLayoutPanel {AutoSize=true,Dock=DockStyle.Top,WrapContents=true,Margin=new Padding(0,4,0,10)};
            portLine.Controls.Add(new Label{Text="端口",AutoSize=true,Margin=new Padding(0,12,12,0)});
            Port=new NumericUpDown{Width=110,Minimum=1024,Maximum=65535,Value=Paths.Options.Port,Margin=new Padding(0,7,12,0)};portLine.Controls.Add(Port);
            PortApply=Button("应用端口 / 重试",()=>applyPort((int)Port.Value));portLine.Controls.Add(PortApply);Add(local,portLine);
            Add(schedule,Label("北京时间 · 自动采集",12,true));
            var times=new TableLayoutPanel{AutoSize=true,Dock=DockStyle.Top,ColumnCount=2,Margin=new Padding(0,4,0,16)};
            times.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));times.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            string[,] rows={{"行情采集","06:30、06:45、12:30"},{"基金更新","09:10、14:30、20:30"},{"定向补采","07:15–17:15，每 30 分钟"},{"快照 / 早报","06:55 冻结；07:00 生成预览"},{"数据备份","07:10"},{"周末归档","周六 12:30"}};
            for(int i=0;i<rows.GetLength(0);i++){times.RowStyles.Add(new RowStyle(SizeType.AutoSize));var name=Label(rows[i,0]);name.Margin=new Padding(0,5,24,7);times.Controls.Add(name,0,i);var value=Label(rows[i,1]);value.Margin=new Padding(0,5,0,7);times.Controls.Add(value,1,i);}Add(schedule,times);
            Add(schedule,Buttons(new[]{"启用 / 修复自动任务"},new Action[]{install}));
            Add(schedule,Label("自动任务由 Windows 任务计划运行。早报仅生成预览。"));
            Startup=new CheckBox{Text="登录 Windows 后自动启动程序",AutoSize=true,Enabled=!Paths.Options.Isolated,Margin=new Padding(0,14,0,8)};
            Startup.Checked=!Paths.Options.Isolated && NasdaqQDII.Startup.Enabled;
            Startup.CheckedChanged+=(s,e)=>{if(!Paths.Options.Isolated && Startup.Checked!=NasdaqQDII.Startup.Enabled)try{NasdaqQDII.Startup.Set(Startup.Checked);}catch(Exception ex){MessageBox.Show(this,ex.Message,"设置失败");}};Add(schedule,Startup);
            Add(schedule,Label("关闭设置窗口会保留托盘；退出程序会停止本程序启动的服务。"));
            BuildRemote(remote,remoteChanged);
            var footer=new FlowLayoutPanel{Dock=DockStyle.Fill,AutoSize=true,FlowDirection=FlowDirection.RightToLeft,Margin=new Padding(0,14,0,0)};
            footer.Controls.Add(Button("关闭到托盘",Close));footer.Controls.Add(new Label{Text="v0.5.0",AutoSize=true,ForeColor=Muted,Margin=new Padding(0,12,20,0)});shell.Controls.Add(footer,0,2);
            Resize+=(s,e)=>{
                bool compact=ClientSize.Height/displayScale<500;
                shell.Padding=new Padding((int)((compact?12:20)*displayScale));
                header.Margin=new Padding(0,0,0,(int)((compact?6:14)*displayScale));
                footer.Margin=new Padding(0,(int)((compact?6:14)*displayScale),0,0);
            };
            Load+=(s,e)=>{
                // Dynamic forms have no designer DPI baseline. Disable implicit Font
                // scaling and scale once from our explicit 96-DPI layout.
                using(var g=CreateGraphics()) {displayScale=g.DpiX/96f;if(displayScale>1.01f)Scale(new SizeF(displayScale,displayScale));}
                var area=Screen.FromControl(this).WorkingArea;MinimumSize=new Size(Math.Min(MinimumSize.Width,area.Width-24),Math.Min(MinimumSize.Height,area.Height-24));
                Size=new Size(Math.Min(Width,area.Width-24),Math.Min(Height,area.Height-24));
                Location=new Point(area.Left+(area.Width-Width)/2,area.Top+(area.Height-Height)/2);
            };
            FormClosing+=(s,e)=>{if(Working)e.Cancel=true;};
        }
        static void OpenFolder(string path) {Directory.CreateDirectory(path);System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(path){UseShellExecute=true});}
        static Label Label(string text,float size=10,bool bold=false) {return new Label{Text=text,AutoSize=true,MaximumSize=new Size(595,0),ForeColor=bold?Navy:Muted,Font=new Font("Microsoft YaHei UI",size,bold?FontStyle.Bold:FontStyle.Regular),Margin=new Padding(0,3,0,9),UseMnemonic=false};}
        static TableLayoutPanel Stack() {var stack=new TableLayoutPanel{AutoSize=true,AutoSizeMode=AutoSizeMode.GrowAndShrink,Dock=DockStyle.Top,ColumnCount=1,Margin=new Padding(0)};stack.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));return stack;}
        TableLayoutPanel Page(string title) {var page=new TabPage(title){BackColor=Color.White,Padding=new Padding(18),AutoScroll=true};Tabs.TabPages.Add(page);var stack=Stack();page.Controls.Add(stack);return stack;}
        static void Add(TableLayoutPanel parent,Control child) {parent.RowStyles.Add(new RowStyle(SizeType.AutoSize));parent.Controls.Add(child,0,parent.RowCount++);}
        static Button Button(string text,Action action) {var b=new Button{Text=text,AutoSize=true,AutoSizeMode=AutoSizeMode.GrowAndShrink,MinimumSize=new Size(142,38),Padding=new Padding(12,5,12,5),Margin=new Padding(0,0,10,8),FlatStyle=FlatStyle.System};b.Click+=(s,e)=>action();return b;}
        static FlowLayoutPanel Buttons(string[] names,Action[] actions) {var row=new FlowLayoutPanel{Dock=DockStyle.Top,AutoSize=true,WrapContents=true,Margin=new Padding(0,4,0,2)};for(int i=0;i<names.Length;i++)row.Controls.Add(Button(names[i],actions[i]));return row;}
        static TextBox Input(TableLayoutPanel page,string label,string text,bool secret=false,bool multiline=false) {Add(page,Label(label));var box=new TextBox{Text=text,UseSystemPasswordChar=secret,Multiline=multiline,Dock=DockStyle.Top,Height=multiline?65:30,Margin=new Padding(0,0,0,12),ScrollBars=multiline?ScrollBars.Vertical:ScrollBars.None};Add(page,box);return box;}
        void BuildRemote(TableLayoutPanel page,Action changed) {
            RemoteSettings config;string readError=null;
            try{config=RemoteSettings.Load();}catch{config=new RemoteSettings();readError="远程配置读取失败，请检查程序目录的 remote.json 与 .previous 备份。";}
            Add(page,Label("通过 Cloudflare 远程访问",12,true));
            Add(page,Label("独立隧道 + 邮箱登录。先核对 Access 保护，再发布域名。"));
            RemoteStatus=Label(config.Enabled?"远程访问已启用":"远程访问未启用");RemoteStatus.ForeColor=Teal;Add(page,RemoteStatus);
            var domain=Input(page,"访问域名",config.Domain);
            var ids=new TableLayoutPanel{AutoSize=true,Dock=DockStyle.Top,ColumnCount=2,Margin=new Padding(0)};ids.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));ids.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));
            var left=Stack();left.Margin=new Padding(0,0,12,0);var right=Stack();ids.Controls.Add(left,0,0);ids.Controls.Add(right,1,0);Add(page,ids);
            var account=Input(left,"Cloudflare 账户 ID",config.AccountId);var zone=Input(right,"域名区域 ID",config.ZoneId);
            var team=Input(page,"Zero Trust 团队名称",config.TeamName);
            var emails=Input(page,"允许登录的邮箱（每行一个）",String.Join(Environment.NewLine,config.Emails),false,true);
            var reuse=new CheckBox{Text="共用 codex-web 的 API Token（当前 Windows 账户）",AutoSize=true,Checked=config.UseCodexToken,Margin=new Padding(0,3,0,10)};Add(page,reuse);
            var token=Input(page,"独立 API Token（Windows 加密保存）","",true);token.Enabled=!reuse.Checked;reuse.CheckedChanged+=(s,e)=>token.Enabled=!reuse.Checked;
            var status=Label("权限：Tunnel 编辑、DNS 编辑、区域读取、Access 应用与策略编辑。");Add(page,status);
            Action<bool> busy=value=>{Working=value;Tabs.Enabled=!value;UseWaitCursor=value;};
            Func<RemoteSettings> read=()=>{
                // Resource IDs stay bound to the original domain/account; no implicit takeover.
                if((config.AccessAppId.Length>0 || config.TunnelId.Length>0) && (domain.Text.Trim()!=config.Domain || account.Text.Trim()!=config.AccountId || zone.Text.Trim()!=config.ZoneId)) throw new ArgumentException("已有远程资源时不能直接切换域名或账户，请使用独立配置。");
                config.Domain=domain.Text;config.AccountId=account.Text.Trim();config.ZoneId=zone.Text.Trim();config.TeamName=team.Text;config.Emails=RemoteSettings.ParseEmails(emails.Text);config.UseCodexToken=reuse.Checked;config.OriginPort=Paths.Options.Port;config.Validate();
                if(!reuse.Checked && !String.IsNullOrWhiteSpace(token.Text)) {RemoteSecrets.Save("api-token",token.Text.Trim());token.Clear();}
                return config;
            };
            var row=Buttons(new[]{"检查 Token","配置并启用","暂停远程访问","打开远程网站"},new Action[]{()=>{},()=>{},()=>{},()=>{}});
            var buttons=row.Controls.OfType<Button>().ToArray();Add(page,row);
            buttons[0].Click+=async(s,e)=>{try{var wanted=read();busy(true);status.Text="正在检查…";status.Text=await Task.Run(()=>new CloudflareClient(RemoteSecrets.ApiToken(wanted)).Check(wanted));}catch(Exception ex){status.Text=ex.Message;}finally{busy(false);}};
            buttons[1].Click+=async(s,e)=>{try{var wanted=read();busy(true);wanted.Enabled=false;wanted.Save();changed();await Task.Run(()=>new CloudflareClient(RemoteSecrets.ApiToken(wanted)).Configure(wanted,text=>{if(!IsDisposed)BeginInvoke((Action)(()=>status.Text=text));}));status.Text="已完成配置与核对，隧道正在连接。";changed();}catch(Exception ex){status.Text=ex.Message;}finally{busy(false);}};
            buttons[2].Click+=(s,e)=>{config=RemoteSettings.Load();config.Enabled=false;config.Save();changed();status.Text="远程连接已暂停；云端 Access 与 DNS 保留。";};
            buttons[3].Click+=(s,e)=>System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("https://"+config.Domain){UseShellExecute=true});
            Add(page,Label("此电脑需联网并保持程序运行。API Token 与隧道 Token 分别保存。"));
            if(Paths.Options.Isolated || readError!=null){foreach(var button in buttons.Take(3))button.Enabled=false;status.Text=readError??"隔离验证模式不修改云端配置。";}
        }
    }
}

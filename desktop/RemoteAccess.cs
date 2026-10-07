using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Mail;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace NasdaqQDII {
    internal sealed class RemoteSettings {
        public string Domain="nasdaq.tonywu.link", AccountId="", ZoneId="", TeamName="";
        public string TunnelId="", AccessAppId="", Audience="", DnsId="";
        public string[] Emails=new string[0];
        public bool Enabled=false, UseCodexToken=true;
        public int OriginPort=8765;
        internal static string FilePath { get { return Path.Combine(Paths.Root,"remote.json"); } }
        internal static RemoteSettings Load() { return File.Exists(FilePath)?Paths.Json.Deserialize<RemoteSettings>(File.ReadAllText(FilePath,Encoding.UTF8)):new RemoteSettings(); }
        internal void Save() {
            Directory.CreateDirectory(Paths.Root); string temp=FilePath+".tmp";
            File.WriteAllText(temp,Paths.Json.Serialize(this),new UTF8Encoding(false));
            if(File.Exists(FilePath)) File.Replace(temp,FilePath,FilePath+".previous"); else File.Move(temp,FilePath);
        }
        internal void Validate() {
            Domain=Domain.Trim().ToLowerInvariant(); TeamName=TeamName.Trim().Replace(".cloudflareaccess.com","");
            if(!Regex.IsMatch(Domain,@"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")) throw new ArgumentException("请输入完整域名，不含 https:// 或路径。");
            if(!Regex.IsMatch(AccountId,@"^[a-fA-F0-9]{32}$") || !Regex.IsMatch(ZoneId,@"^[a-fA-F0-9]{32}$")) throw new ArgumentException("账户 ID 和区域 ID 需为 32 位十六进制字符。");
            if(!Regex.IsMatch(TeamName,@"^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$")) throw new ArgumentException("请输入 Cloudflare Zero Trust 团队名称。");
            if(OriginPort<1024 || OriginPort>65535) throw new ArgumentException("本机端口无效。");
            Emails=ParseEmails(String.Join("\n",Emails??new string[0]));
        }
        internal static string[] ParseEmails(string text) {
            var emails=text.Split(new[]{'\r','\n',',',';'},StringSplitOptions.RemoveEmptyEntries).Select(x=>x.Trim()).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
            if(emails.Length==0 || emails.Length>50) throw new ArgumentException("请输入允许登录的完整邮箱，每行一个。");
            foreach(var email in emails) { MailAddress address; try { address=new MailAddress(email); } catch { throw new ArgumentException("邮箱格式无效。"); } if(address.Address!=email || email.Contains("*") || !email.Contains(".")) throw new ArgumentException("邮箱格式无效，不支持通配符。"); }
            return emails;
        }
    }
    internal static class RemoteSecrets {
        internal static bool HasCodexToken { get { using(var key=Registry.CurrentUser.OpenSubKey(@"Software\CodexWebTray\Secrets")) return key!=null && key.GetValue("cloudflare-token") is byte[]; } }
        internal static string ApiToken(RemoteSettings settings) {
            if(settings.UseCodexToken) {
                using(var key=Registry.CurrentUser.OpenSubKey(@"Software\CodexWebTray\Secrets")) {
                    byte[] value=key==null?null:key.GetValue("cloudflare-token") as byte[];
                    if(value==null) throw new IOException("未找到 codex-web 加密保存的 API Token。可改用独立 Token。");
                    return Encoding.UTF8.GetString(ProtectedData.Unprotect(value,null,DataProtectionScope.CurrentUser));
                }
            }
            return Read("api-token");
        }
        internal static string Read(string name) {
            string file=Path.Combine(Paths.Root,"secrets",name+".dat");
            if(!File.Exists(file)) throw new IOException("尚未保存 "+(name=="api-token"?"API Token":"隧道凭据")+"。");
            return Encoding.UTF8.GetString(ProtectedData.Unprotect(File.ReadAllBytes(file),null,DataProtectionScope.CurrentUser));
        }
        internal static void Save(string name,string value) {
            string directory=Path.Combine(Paths.Root,"secrets");Directory.CreateDirectory(directory);
            var bytes=ProtectedData.Protect(Encoding.UTF8.GetBytes(value),null,DataProtectionScope.CurrentUser);
            string file=Path.Combine(directory,name+".dat"),temp=file+".tmp";File.WriteAllBytes(temp,bytes);
            if(File.Exists(file)) File.Replace(temp,file,null); else File.Move(temp,file);
        }
    }
    internal sealed class CloudflareClient {
        readonly string token;
        internal static Func<string,string,object,object> TestTransport=null;
        internal CloudflareClient(string value) { if(String.IsNullOrWhiteSpace(value)) throw new ArgumentException("请配置 API Token。"); token=value; }
        internal object Request(string method,string resource,object body=null) {
            if(TestTransport!=null) return TestTransport(method,resource,body);
            ServicePointManager.SecurityProtocol|=SecurityProtocolType.Tls12;
            var req=(HttpWebRequest)WebRequest.Create("https://api.cloudflare.com/client/v4/"+resource);
            req.Method=method;req.Headers["Authorization"]="Bearer "+token;req.ContentType="application/json";
            req.Timeout=20000;req.ReadWriteTimeout=20000;req.AllowAutoRedirect=false;req.Proxy=WebRequest.GetSystemWebProxy();req.UserAgent="NasdaqQDII/0.5.0";
            try {
                if(body!=null) { var bytes=Encoding.UTF8.GetBytes(Paths.Json.Serialize(body));req.ContentLength=bytes.Length;using(var stream=req.GetRequestStream()) stream.Write(bytes,0,bytes.Length); }
                using(var response=req.GetResponse()) using(var reader=new StreamReader(response.GetResponseStream())) {
                    var envelope=Paths.Json.Deserialize<Dictionary<string,object>>(reader.ReadToEnd());
                    if(!envelope.ContainsKey("success") || !Object.Equals(envelope["success"],true)) throw new IOException("Cloudflare 未确认操作成功。请重新读取核对。");
                    return envelope["result"];
                }
            } catch(WebException ex) {
                var response=ex.Response as HttpWebResponse; string code=response==null?ex.Status.ToString():((int)response.StatusCode).ToString();
                if(response!=null) response.Close();
                throw new IOException("Cloudflare "+method+" "+resource.Split('?')[0]+" 失败（"+code+"）。需要 Tunnel 编辑、DNS 编辑、区域读取、Access 应用与策略编辑权限；网络超时后请重新读取核对。");
            }
        }
        internal static Dictionary<string,object> Dict(object value) { return (Dictionary<string,object>)value; }
        internal static object[] List(object value) { var list=value as IEnumerable;return list==null || value is string?new object[0]:list.Cast<object>().ToArray(); }
        internal static string Text(Dictionary<string,object> value,string key) { object result;return value.TryGetValue(key,out result)?Convert.ToString(result):""; }
        internal string Check(RemoteSettings s) {
            s.Validate(); var verified=Dict(Request("GET","user/tokens/verify"));
            if(Text(verified,"status")!="active") throw new IOException("API Token 未处于有效状态。");
            var zone=Dict(Request("GET","zones/"+s.ZoneId));
            if(Text(Dict(zone["account"]),"id")!=s.AccountId || !(s.Domain==Text(zone,"name") || s.Domain.EndsWith("."+Text(zone,"name")))) throw new IOException("域名、区域或账户不匹配。");
            Request("GET","zones/"+s.ZoneId+"/dns_records?name="+Uri.EscapeDataString(s.Domain));
            Request("GET","accounts/"+s.AccountId+"/cfd_tunnel?is_deleted=false");
            Request("GET","accounts/"+s.AccountId+"/access/apps");
            return "Token 有效，账户与域名匹配；读取权限通过。编辑权限将在配置时逐项验证。";
        }
        static object[] EmailRules(string[] emails) { return emails.Select(e=>(object)new{email=new{email=e}}).ToArray(); }
        internal static void ValidatePolicies(object raw,string[] expected) {
            var policies=List(raw); if(policies.Length!=1) throw new IOException("Access 策略不是独占的单条邮箱 Allow，停止以免扩大权限。");
            var p=Dict(policies[0]);
            if(Text(p,"decision")!="allow" || List(p.ContainsKey("exclude")?p["exclude"]:null).Length!=0 || List(p.ContainsKey("require")?p["require"]:null).Length!=0) throw new IOException("Access 策略含有非预期规则。");
            var actual=new List<string>();
            foreach(var rule in List(p["include"])) { var r=Dict(rule); if(r.Count!=1 || !r.ContainsKey("email")) throw new IOException("Access 仅支持指定邮箱登录。");actual.Add(Text(Dict(r["email"]),"email")); }
            if(!actual.OrderBy(x=>x,StringComparer.OrdinalIgnoreCase).SequenceEqual(expected.OrderBy(x=>x,StringComparer.OrdinalIgnoreCase),StringComparer.OrdinalIgnoreCase)) throw new IOException("云端允许邮箱与本机配置不一致，停止连接。");
        }
        internal void VerifyProtection(RemoteSettings s) {
            var app=Dict(Request("GET","accounts/"+s.AccountId+"/access/apps/"+s.AccessAppId));
            if(Text(app,"domain")!=s.Domain || Text(app,"type")!="self_hosted" || Text(app,"aud")!=s.Audience) throw new IOException("Access 应用身份不匹配，停止连接。");
            ValidatePolicies(Request("GET","accounts/"+s.AccountId+"/access/apps/"+s.AccessAppId+"/policies"),s.Emails);
        }
        internal void Configure(RemoteSettings s,Action<string> progress) {
            s.Validate();Check(s);
            string account="accounts/"+s.AccountId;
            string appName="Nasdaq QDII · "+s.Domain, tunnelName="nasdaq-qdii-"+s.Domain;
            progress("正在核对域名与独立资源…");
            var dns=List(Request("GET","zones/"+s.ZoneId+"/dns_records?name="+Uri.EscapeDataString(s.Domain)));
            if(dns.Length>0 && (dns.Length!=1 || String.IsNullOrEmpty(s.DnsId) || Text(Dict(dns[0]),"id")!=s.DnsId)) throw new IOException("域名已有 DNS 记录；为避免覆盖其他服务，请先在控制台核对。");
            var apps=List(Request("GET",account+"/access/apps"));
            var matching=apps.Select(Dict).Where(a=>Text(a,"domain")==s.Domain).ToArray();
            if(String.IsNullOrEmpty(s.AccessAppId) && matching.Length>0) throw new IOException("此域名已有 Access 应用；请使用它的原配置，不会自动接管。");
            progress("先建立仅指定邮箱可登录的 Access 保护…");
            if(String.IsNullOrEmpty(s.AccessAppId)) {
                var app=Dict(Request("POST",account+"/access/apps",new{name=appName,domain=s.Domain,type="self_hosted",session_duration="24h",auto_redirect_to_identity=false,app_launcher_visible=false,
                    policies=new[]{new{name="Nasdaq owner only",decision="allow",include=EmailRules(s.Emails),exclude=new object[0],require=new object[0],precedence=1}}}));
                s.AccessAppId=Text(app,"id");s.Audience=Text(app,"aud");s.Enabled=false;s.Save();
            }
            VerifyProtection(s);
            progress("正在建立独立隧道…");
            if(String.IsNullOrEmpty(s.TunnelId)) {
                var tunnels=List(Request("GET",account+"/cfd_tunnel?is_deleted=false&name="+Uri.EscapeDataString(tunnelName)));
                if(tunnels.Length>0) throw new IOException("已有同名隧道，停止自动接管。请在控制台核对。");
                var tunnel=Dict(Request("POST",account+"/cfd_tunnel",new{name=tunnelName,config_src="cloudflare"}));
                s.TunnelId=Text(tunnel,"id");s.Enabled=false;s.Save();
            }
            var info=Dict(Request("GET",account+"/cfd_tunnel/"+s.TunnelId));
            if(Text(info,"name")!=tunnelName || Text(info,"config_src")!="cloudflare") throw new IOException("隧道不是本应用的独立远程管理隧道。");
            var ingress=BuildIngress(s);
            Request("PUT",account+"/cfd_tunnel/"+s.TunnelId+"/configurations",new{config=new{ingress=ingress}});
            var readback=Dict(Request("GET",account+"/cfd_tunnel/"+s.TunnelId+"/configurations"));
            ValidateIngress(Dict(readback["config"])["ingress"],s);
            string tunnelToken=Convert.ToString(Request("GET",account+"/cfd_tunnel/"+s.TunnelId+"/token"));
            if(String.IsNullOrWhiteSpace(tunnelToken)) throw new IOException("没有取得隧道运行凭据。");
            RemoteSecrets.Save("tunnel-token",tunnelToken);
            progress("Access 保护已核对，正在配置 DNS…");
            string target=s.TunnelId+".cfargotunnel.com";
            if(dns.Length==0) {
                var created=Dict(Request("POST","zones/"+s.ZoneId+"/dns_records",new{type="CNAME",name=s.Domain,content=target,proxied=true,ttl=1,comment="Nasdaq QDII private Access tunnel"}));
                s.DnsId=Text(created,"id");s.Save();
            } else { var record=Dict(dns[0]);if(Text(record,"type")!="CNAME" || Text(record,"content")!=target || !Object.Equals(record["proxied"],true)) throw new IOException("DNS 指向与隧道不一致，停止自动覆盖。"); }
            var confirmed=Dict(Request("GET","zones/"+s.ZoneId+"/dns_records/"+s.DnsId));
            if(Text(confirmed,"name")!=s.Domain || Text(confirmed,"type")!="CNAME" || Text(confirmed,"content")!=target || !Object.Equals(confirmed["proxied"],true)) throw new IOException("DNS 保存后核对不一致，远程连接保持关闭。");
            VerifyProtection(s);
            s.Enabled=true;s.Save();progress("配置完成：Access、隧道、DNS 均已重新读取核对。");
        }
        internal static object[] BuildIngress(RemoteSettings s) {
            return new object[]{new{hostname=s.Domain,service="http://127.0.0.1:"+s.OriginPort,originRequest=new{access=new{required=true,teamName=s.TeamName,audTag=new[]{s.Audience}}}},new{service="http_status:404"}};
        }
        internal static void ValidateIngress(object value,RemoteSettings s) {
            var rules=List(value);if(rules.Length!=2) throw new IOException("隧道路由含非预期规则。");
            var first=Dict(rules[0]);var fallback=Dict(rules[1]);
            if(Text(first,"hostname")!=s.Domain || Text(first,"service")!="http://127.0.0.1:"+s.OriginPort || Text(fallback,"service")!="http_status:404" || fallback.ContainsKey("hostname")) throw new IOException("隧道路由身份不匹配。");
            var access=Dict(Dict(first["originRequest"])["access"]);
            if(!Object.Equals(access["required"],true) || Text(access,"teamName")!=s.TeamName || !List(access["audTag"]).Select(Convert.ToString).SequenceEqual(new[]{s.Audience})) throw new IOException("隧道没有启用指定 Access JWT 验证。");
        }
    }
    internal sealed class RemoteRuntime : IDisposable {
        Process process;Job job;DateTime retryAfter;readonly object gate=new object();bool disposed,checking;int port,generation;
        internal string Status="远程访问未启用";volatile bool connected;string readinessUrl;
        internal bool Enabled;internal string Domain="nasdaq.tonywu.link";
        internal bool Connected { get { return connected; } }
        internal int? Pid { get { lock(gate) {try{return process!=null && !process.HasExited?(int?)process.Id:null;}catch{return null;}} } }
        internal void Tick(bool localReady) {
            RemoteSettings settings;
            try {settings=RemoteSettings.Load();Enabled=settings.Enabled;Domain=settings.Domain;}catch{Enabled=false;Status="远程配置读取失败，请检查 remote.json";Stop();return;}
            lock(gate) {
                if(disposed)return;
                if(!settings.Enabled || Paths.Options.Isolated || !localReady) {StopLocked();Status=settings.Enabled?"等待本机服务就绪":"远程访问未启用";return;}
                if(settings.OriginPort!=Paths.Options.Port) {StopLocked();Status="本机端口已变化，请在远程访问页重新配置";return;}
                if(process!=null && (process.HasExited || port!=settings.OriginPort)) {StopLocked();Status="隧道连接已中断，30 秒后自动重试";retryAfter=DateTime.UtcNow.AddSeconds(30);}
                if(process!=null) {CheckReady();return;}
                if(checking || DateTime.UtcNow<retryAfter)return;
                checking=true;int current=generation;Status="正在核对 Access 保护…";
                // Cloud API calls stay off the UI and service locks. Stop/exit can
                // invalidate this generation even while a request is pending.
                System.Threading.Tasks.Task.Run(()=>Connect(settings,current));
            }
        }
        void Connect(RemoteSettings settings,int current) {
            try {
                var client=new CloudflareClient(RemoteSecrets.ApiToken(settings));client.VerifyProtection(settings);
                var config=CloudflareClient.Dict(client.Request("GET","accounts/"+settings.AccountId+"/cfd_tunnel/"+settings.TunnelId+"/configurations"));
                CloudflareClient.ValidateIngress(CloudflareClient.Dict(config["config"])["ingress"],settings);
                lock(gate) {
                    if(disposed || current!=generation)return;
                    string executable=Path.Combine(Paths.Payload,"cloudflared","cloudflared.exe");
                    var info=new ProcessStartInfo(executable,"tunnel --no-autoupdate --protocol http2 --metrics 127.0.0.1:0 run") {UseShellExecute=false,CreateNoWindow=true,RedirectStandardError=true,RedirectStandardOutput=true,WorkingDirectory=Paths.Payload};
                    Paths.ConfigureProxy(info);info.EnvironmentVariables["TUNNEL_TOKEN"]=RemoteSecrets.Read("tunnel-token");
                    process=new Process{StartInfo=info};job=new Job();port=settings.OriginPort;connected=false;
                    DataReceivedEventHandler receive=(sender,e)=> {
                        if(e.Data==null)return;
                        var match=Regex.Match(e.Data,@"Starting metrics server on (127\.0\.0\.1:[0-9]+)/metrics");
                        if(match.Success)readinessUrl="http://"+match.Groups[1].Value+"/ready";
                        if(e.Data.Contains("Registered tunnel connection")){connected=true;Status="远程访问已连接 · 仅指定邮箱登录";}
                    };
                    process.ErrorDataReceived+=receive;process.OutputDataReceived+=receive;
                    process.Start();job.Assign(process);process.BeginErrorReadLine();process.BeginOutputReadLine();Status="正在连接 Cloudflare…";
                }
            }catch(Exception ex){lock(gate){if(!disposed && current==generation){StopLocked();Status=ex.Message;retryAfter=DateTime.UtcNow.AddSeconds(30);Paths.Log("远程访问："+ex.Message);}}}
            finally {lock(gate)checking=false;}
        }
        void CheckReady() {
            if(String.IsNullOrEmpty(readinessUrl))return;
            try {var request=(HttpWebRequest)WebRequest.Create(readinessUrl);request.Proxy=null;request.Timeout=800;using(var response=request.GetResponse())connected=true;}
            catch(WebException){connected=false;}
            Status=connected?"远程访问已连接 · 仅指定邮箱登录":"连接已中断，Cloudflare 正在重连…";
        }
        void StopLocked() {
            generation++;connected=false;readinessUrl=null;
            if(job!=null){job.Dispose();job=null;}
            if(process!=null){try{if(!process.HasExited && !process.WaitForExit(2000))process.Kill();}catch{}process.Dispose();process=null;}
        }
        internal void Stop() {lock(gate)StopLocked();}
        public void Dispose() {lock(gate){disposed=true;StopLocked();}}
    }
}

// Source-only verification helper; not compiled into the release executable.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Windows.Forms;

namespace NasdaqQDII {
    internal static class DesktopTests {
        static int count;static void Check(bool okay,string name) {if(!okay)throw new Exception(name);count++;Console.WriteLine("PASS "+name);}
        static Dictionary<string,object> Obj(object raw) {return Paths.Json.Deserialize<Dictionary<string,object>>(Paths.Json.Serialize(raw));}
        static object Canonical(object raw) {return Paths.Json.DeserializeObject(Paths.Json.Serialize(raw));}
        static RemoteSettings Sample() {return new RemoteSettings{Domain="nasdaq.example.com",AccountId=new string('a',32),ZoneId=new string('b',32),TeamName="owner",Emails=new[]{"owner@example.com"},OriginPort=18765};}
        [STAThread] static int Main(string[] args) {
            try {
                Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
                string output=Path.GetFullPath(args[0]);Directory.CreateDirectory(output);
                Paths.Root=Path.Combine(output,"state");Paths.Home=Path.Combine(output,"synthetic data");Paths.Payload=output;Paths.Options=new Options{StateRoot=Paths.Root,Home=Paths.Home,Isolated=true,Port=18765};
                Directory.CreateDirectory(Paths.Root);Directory.CreateDirectory(Paths.Home);
                Security();Layouts(output);Console.WriteLine("Passed "+count+" desktop checks");return 0;
            }catch(Exception ex){Console.Error.WriteLine(ex);return 1;}
        }
        static void Security() {
            var valid=Sample();valid.Validate();Check(valid.Emails.Length==1,"Valid isolated domain and email configuration");
            foreach(var bad in new[]{"https://nasdaq.example.com","nasdaq.example.com/path","*.example.com","../a"}) {
                var s=Sample();s.Domain=bad;bool rejected=false;try{s.Validate();}catch(ArgumentException){rejected=true;}Check(rejected,"Reject invalid hostname: "+bad);
            }
            foreach(var bad in new[]{"*","owner@*","Name <owner@example.com>"}) {bool rejected=false;try{RemoteSettings.ParseEmails(bad);}catch(ArgumentException){rejected=true;}Check(rejected,"Reject broad/invalid login selector");}
            Check(RemoteSettings.ParseEmails("owner@example.com\nOWNER@example.com").Length==1,"Deduplicate login emails");
            object good=Canonical(new[]{new{decision="allow",include=new[]{new{email=new{email="owner@example.com"}}},exclude=new object[0],require=new object[0]}});
            CloudflareClient.ValidatePolicies(good,valid.Emails);Check(true,"Only exact mailbox allow rule accepted");
            foreach(var bad in new object[]{new[]{new{decision="bypass",include=new[]{new{everyone=new{}}}}},new[]{new{decision="allow",include=new[]{new{everyone=new{}}}}},new[]{new{decision="allow",include=new[]{new{email=new{email="other@example.com"}}}}},new object[0]}) {
                bool rejected=false;try{CloudflareClient.ValidatePolicies(Canonical(bad),valid.Emails);}catch{rejected=true;}Check(rejected,"Fail closed on unexpected Access policy");
            }
            valid.Audience="test-audience";CloudflareClient.ValidateIngress(Canonical(CloudflareClient.BuildIngress(valid)),valid);Check(true,"Loopback origin and required JWT route validate");
            var ingress=CloudflareClient.List(Canonical(CloudflareClient.BuildIngress(valid)));var access=CloudflareClient.Dict(CloudflareClient.Dict(CloudflareClient.Dict(ingress[0])["originRequest"])["access"]);access["required"]=false;
            bool routeRejected=false;try{CloudflareClient.ValidateIngress(ingress,valid);}catch{routeRejected=true;}Check(routeRejected,"Refuse tunnel without JWT validation");
            RemoteSecrets.Save("api-token","synthetic-test-secret");Check(RemoteSecrets.Read("api-token")=="synthetic-test-secret","DPAPI encrypted secret roundtrip");
            Check(!System.Text.Encoding.UTF8.GetString(File.ReadAllBytes(Path.Combine(Paths.Root,"secrets","api-token.dat"))).Contains("synthetic-test-secret"),"Secret is not stored as plain text");
            valid.Save();Check(RemoteSettings.Load().Domain==valid.Domain,"Remote configuration roundtrip");
            Configure(good);ResponsiveRemoteStop(good);CorruptRemoteConfig();
        }
        static void Configure(object policy) {
            var s=Sample();var writes=new List<string>();bool protectedAlready=false;object config=null;
            CloudflareClient.TestTransport=(method,path,body)=>{
                if(method!="GET")writes.Add(method+" "+path);
                if(path=="user/tokens/verify")return Obj(new{status="active"});
                if(path=="zones/"+s.ZoneId)return Obj(new{name="example.com",account=new{id=s.AccountId}});
                if(path.Contains("dns_records")) {
                    if(method=="POST") {Check(protectedAlready,"DNS published only after Access verification");return Obj(new{id="dns-test"});}
                    if(path.EndsWith("/dns-test"))return Obj(new{name=s.Domain,type="CNAME",content="tunnel-test.cfargotunnel.com",proxied=true});
                    return new object[0];
                }
                if(path.EndsWith("/access/apps") && method=="POST")return Obj(new{id="app-test",aud="test-audience",domain=s.Domain,type="self_hosted"});
                if(path.EndsWith("/access/apps"))return new object[0];
                if(path.EndsWith("/access/apps/app-test/policies")){protectedAlready=true;return policy;}
                if(path.EndsWith("/access/apps/app-test"))return Obj(new{id="app-test",aud="test-audience",domain=s.Domain,type="self_hosted"});
                if(path.EndsWith("/cfd_tunnel") && method=="POST")return Obj(new{id="tunnel-test"});
                if(path.Contains("cfd_tunnel?"))return new object[0];
                if(path.EndsWith("/cfd_tunnel/tunnel-test"))return Obj(new{name="nasdaq-qdii-"+s.Domain,config_src="cloudflare"});
                if(path.EndsWith("/configurations")){if(method=="PUT")config=CloudflareClient.Dict(Canonical(body))["config"];return Obj(new{config=config});}
                if(path.EndsWith("/token"))return "synthetic-tunnel-token";
                throw new Exception("Unexpected resource "+path);
            };
            new CloudflareClient("test").Configure(s,text=>{});
            Check(s.Enabled && s.TunnelId=="tunnel-test" && s.AccessAppId=="app-test","Provision independent resources and persist identifiers");
            Check(writes.Count==4 && !writes.Any(x=>x.Contains("codex")),"Only four expected writes, no codex-web modification");
            var broken=Sample();CloudflareClient.TestTransport=(method,path,body)=>{
                if(path=="user/tokens/verify")return Obj(new{status="active"});
                if(path=="zones/"+broken.ZoneId)return Obj(new{name="example.com",account=new{id=broken.AccountId}});
                if(path.Contains("dns_records")||path.Contains("cfd_tunnel?")||path.EndsWith("/access/apps")&&method=="GET")return new object[0];
                throw new IOException("Synthetic write permission denied");
            };
            bool denied=false;try{new CloudflareClient("test").Configure(broken,text=>{});}catch(IOException){denied=true;}
            Check(denied && !broken.Enabled && broken.DnsId=="","Denied write never enables remote access or publishes DNS");
            var collision=Sample();CloudflareClient.TestTransport=(method,path,body)=>{
                if(path=="user/tokens/verify")return Obj(new{status="active"});
                if(path=="zones/"+collision.ZoneId)return Obj(new{name="example.com",account=new{id=collision.AccountId}});
                if(path.Contains("dns_records"))return Canonical(new[]{new{id="foreign-dns"}});
                if(method!="GET")throw new Exception("Unexpected mutation");return new object[0];
            };
            bool conflict=false;try{new CloudflareClient("test").Configure(collision,text=>{});}catch(IOException){conflict=true;}Check(conflict,"Existing unrelated DNS is not overwritten");
            CloudflareClient.TestTransport=null;
            // Keep visual screenshots free of account, email and credential fixtures.
            new RemoteSettings().Save();
        }
        static void ResponsiveRemoteStop(object policy) {
            var s=Sample();s.UseCodexToken=false;s.AccessAppId="app-test";s.TunnelId="tunnel-test";s.Audience="test-audience";s.Enabled=true;s.Save();
            Paths.Options.Isolated=false;
            using(var entered=new System.Threading.ManualResetEvent(false))using(var release=new System.Threading.ManualResetEvent(false))using(var runtime=new RemoteRuntime()) {
                CloudflareClient.TestTransport=(method,path,body)=>{
                    entered.Set();release.WaitOne(5000);
                    if(path.EndsWith("/policies"))return policy;
                    if(path.EndsWith("/configurations"))return Obj(new{config=new{ingress=CloudflareClient.BuildIngress(s)}});
                    return Obj(new{domain=s.Domain,type="self_hosted",aud=s.Audience});
                };
                var clock=System.Diagnostics.Stopwatch.StartNew();runtime.Tick(true);Check(clock.ElapsedMilliseconds<500,"Remote API verification does not block local polling");
                Check(entered.WaitOne(3000),"Remote verification runs asynchronously");clock.Restart();runtime.Stop();Check(clock.ElapsedMilliseconds<500,"Stop remains responsive during pending API request");
                release.Set();System.Threading.Thread.Sleep(300);Check(runtime.Pid==null,"Cancelled verification cannot launch a tunnel later");
                CloudflareClient.TestTransport=null;
            }
            Paths.Options.Isolated=true;new RemoteSettings().Save();
        }
        static void CorruptRemoteConfig() {
            File.WriteAllText(RemoteSettings.FilePath,"{bad-json");
            using(var runtime=new RemoteRuntime()){runtime.Tick(true);Check(!runtime.Enabled && runtime.Pid==null && runtime.Status.Contains("读取失败"),"Corrupt remote configuration remains disabled");}
            using(var form=new SettingsWindow(()=>{},x=>{},()=>{},x=>{},()=>{})){Check(form.Tabs.TabCount==3,"Local settings still open with corrupt remote configuration");}
            new RemoteSettings().Save();
        }
        static void Layouts(string output) {
            foreach(float scale in new[]{1f,1.25f,1.5f,2f}) {
                using(var form=new SettingsWindow(()=>{},x=>{},()=>{},x=>{},()=>{})) {
                    form.Show();Application.DoEvents();
                    var fonts=Descendants(form).Concat(new[]{form}).ToDictionary(c=>c,c=>c.Font);
                    using(var graphics=form.CreateGraphics())form.Scale(new SizeF(scale*96f/graphics.DpiX,scale*96f/graphics.DpiY));
                    foreach(var item in fonts)item.Key.Font=new Font(item.Value.FontFamily,item.Value.SizeInPoints*scale,item.Value.Style);
                    form.ClientSize=new Size((int)(680*scale),(int)(610*scale));
                    for(int i=0;i<3;i++) {
                        form.Tabs.SelectedIndex=i;Application.DoEvents();
                        var tab=form.Tabs.TabPages[i];var labels=Descendants(tab).OfType<Label>().Where(c=>c.Visible).ToArray();
                        Check(labels.All(l=>l.Height>=l.Font.Height),"Visible labels retain text height at "+scale+", tab "+i);
                        Check(form.Tabs.Right<=form.ClientSize.Width && form.Tabs.Bottom<form.ClientSize.Height,"Tabs fit form at "+scale+", tab "+i);
                        using(var bitmap=new Bitmap(form.Width,form.Height)){form.DrawToBitmap(bitmap,new Rectangle(Point.Empty,bitmap.Size));bitmap.Save(Path.Combine(output,"settings-"+scale.ToString("0.00",System.Globalization.CultureInfo.InvariantCulture)+"-tab"+i+".png"),ImageFormat.Png);}
                    }
                    form.Close();
                }
            }
            using(var narrow=new SettingsWindow(()=>{},x=>{},()=>{},x=>{},()=>{})) {narrow.Show();narrow.Size=new Size(430,430);narrow.Tabs.SelectedIndex=2;Application.DoEvents();Check(narrow.Tabs.SelectedTab.AutoScroll,"Small window remote settings scroll");using(var bitmap=new Bitmap(narrow.Width,narrow.Height)){narrow.DrawToBitmap(bitmap,new Rectangle(Point.Empty,bitmap.Size));bitmap.Save(Path.Combine(output,"settings-small.png"),ImageFormat.Png);}narrow.Close();}
        }
        static IEnumerable<Control> Descendants(Control root) {foreach(Control c in root.Controls){yield return c;foreach(var child in Descendants(c))yield return child;}}
    }
}

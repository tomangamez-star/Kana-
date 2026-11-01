package ai.montai.kana;

import android.app.Activity;
import android.os.Bundle;
import android.os.Build;
import android.view.WindowInsets;
import android.widget.FrameLayout;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.webkit.*;
import android.net.Uri;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.*;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import java.util.concurrent.*;

public class MainActivity extends Activity {
    private WebView web;
    private SharedPreferences prefs;
    private final ExecutorService executor=Executors.newFixedThreadPool(3);
    private static final String ALIAS="kana.connection.v1";
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved); prefs=getSharedPreferences("kana",MODE_PRIVATE);
        getWindow().setStatusBarColor(Color.rgb(13,13,24));getWindow().setNavigationBarColor(Color.rgb(13,13,24));
        web=new WebView(this);web.setBackgroundColor(Color.rgb(10,11,20));FrameLayout root=new FrameLayout(this);root.addView(web,new FrameLayout.LayoutParams(-1,-1));setContentView(root);
        if(Build.VERSION.SDK_INT>=35){getWindow().setDecorFitsSystemWindows(false);root.setOnApplyWindowInsetsListener((v,insets)->{android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());v.setPadding(bars.left,bars.top,bars.right,bars.bottom);return insets;});}
        WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(false);s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setJavaScriptCanOpenWindowsAutomatically(false);s.setSupportMultipleWindows(false);
        web.setWebViewClient(new WebViewClient(){@Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){return true;}});
        web.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onJsConfirm(WebView v,String url,String message,JsResult result){new android.app.AlertDialog.Builder(MainActivity.this).setMessage(message).setPositiveButton("Confirm",(d,w)->result.confirm()).setNegativeButton("Cancel",(d,w)->result.cancel()).setOnCancelListener(d->result.cancel()).show();return true;}
        });
        web.addJavascriptInterface(new Bridge(),"KanaNative");
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){return true;}
            @Override public WebResourceResponse shouldInterceptRequest(WebView v,WebResourceRequest r){Uri u=r.getUrl();if("kana.local".equals(u.getHost())){String p=u.getPath();if("/style.css".equals(p)||"/app.js".equals(p)){try{return new WebResourceResponse(p.endsWith("css")?"text/css":"application/javascript","UTF-8",getAssets().open(p.substring(1)));}catch(Exception ignored){}}}return new WebResourceResponse("text/plain","UTF-8",new ByteArrayInputStream(new byte[0]));}
        });
        try{InputStream in=getAssets().open("index.html");String html=new String(read(in,200000),StandardCharsets.UTF_8);web.loadDataWithBaseURL("https://kana.local/",html,"text/html","UTF-8",null);}catch(Exception e){throw new RuntimeException("Missing app assets");}

    }
    private static byte[] read(InputStream in,int limit)throws Exception{try(InputStream stream=in;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[8192];int n;while((n=stream.read(b))!=-1){if(out.size()+n>limit)throw new IOException("Response too large");out.write(b,0,n);}return out.toByteArray();}}
    private synchronized SecretKey secretKey()throws Exception{KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);if(!ks.containsAlias(ALIAS)){KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");generator.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());generator.generateKey();}return (SecretKey)ks.getKey(ALIAS,null);}
    private String encrypt(String value)throws Exception{Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,secretKey());return Base64.encodeToString(c.getIV(),Base64.NO_WRAP)+":"+Base64.encodeToString(c.doFinal(value.getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP);}
    private String decrypt(String value)throws Exception{if(value.isEmpty())return "";String[] p=value.split(":",2);Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,secretKey(),new GCMParameterSpec(128,Base64.decode(p[0],Base64.NO_WRAP)));return new String(c.doFinal(Base64.decode(p[1],Base64.NO_WRAP)),StandardCharsets.UTF_8);}
    private void result(String id,Object data,String error){try{JSONObject r=new JSONObject();if(error!=null)r.put("error",error);else r.put("data",data);String script="window.nativeResult("+JSONObject.quote(id)+","+r.toString()+")";runOnUiThread(()->{if(web!=null)web.evaluateJavascript(script,null);});}catch(Exception ignored){}}
    private JSONObject requestServer(String server,String access,String path,String method,String body)throws Exception{
        if(!path.matches("/api/(status|messages|chat|memories|memories/[a-f0-9-]+|models|settings)(\\?before=[0-9.]+)?"))throw new IOException("Invalid API route");
        if(!method.matches("GET|POST|PUT|DELETE"))throw new IOException("Invalid method");
        HttpURLConnection c=(HttpURLConnection)new URL(server+path).openConnection();
        c.setInstanceFollowRedirects(false);c.setConnectTimeout(20000);c.setReadTimeout(85000);c.setRequestMethod(method);c.setRequestProperty("Authorization","Bearer "+access);c.setRequestProperty("Content-Type","application/json");
        try{if(!body.isEmpty()){if(body.length()>20000)throw new IOException("Message too large");c.setDoOutput(true);try(OutputStream out=c.getOutputStream()){out.write(body.getBytes(StandardCharsets.UTF_8));}}
            int code=c.getResponseCode();InputStream in=code>=200&&code<300?c.getInputStream():c.getErrorStream();String raw=in==null?"{}":new String(read(in,3000000),StandardCharsets.UTF_8);
            if(code<200||code>=300){String msg="Server returned "+code+". Check your Render URL and deployment.";try{Object detail=new JSONObject(raw).opt("detail");if(detail instanceof String)msg=(String)detail;}catch(Exception ignored){}throw new IOException(msg);}
            return new JSONObject(raw);
        }finally{c.disconnect();}
    }
    public class Bridge{
        @JavascriptInterface public void configuration(String id){executor.execute(()->{try{JSONObject r=new JSONObject();r.put("url",prefs.getString("url",""));result(id,r,null);}catch(Exception e){result(id,null,"Could not read connection settings.");}});}
        @JavascriptInterface public void configure(String id,String server,String access){executor.execute(()->{try{
            serverCheck(server);String clean=server.replaceAll("/+$","");String old=prefs.getString("url","");String token=access.trim();if(token.isEmpty()&&clean.equals(old))token=decrypt(prefs.getString("key",""));if(token.length()<24)throw new IOException("Enter your server access key (at least 24 characters).");
            requestServer(clean,token,"/api/status","GET","");prefs.edit().putString("url",clean).putString("key",encrypt(token)).commit();JSONObject r=new JSONObject();r.put("url",clean);result(id,r,null);
        }catch(Exception e){result(id,null,safeError(e));}});}
        @JavascriptInterface public void request(String id,String path,String method,String body){executor.execute(()->{try{String server=prefs.getString("url","");if(server.isEmpty())throw new IOException("Connect your Render server in Settings.");result(id,requestServer(server,decrypt(prefs.getString("key","")),path,method,body),null);}catch(Exception e){result(id,null,safeError(e));}});}
    }
    private void serverCheck(String server)throws Exception{URI u=new URI(server);if(!"https".equals(u.getScheme())||u.getHost()==null||u.getUserInfo()!=null||u.getQuery()!=null||u.getFragment()!=null||!(u.getPath().isEmpty()||u.getPath().equals("/")))throw new IOException("Use an HTTPS server address with no path, such as https://your-kana.onrender.com");}
    private String safeError(Exception e){if(e instanceof SocketTimeoutException)return "Server timed out. Render may be waking up. Retry shortly.";if(e instanceof javax.net.ssl.SSLException)return "Secure connection failed. Check your server certificate.";if(e instanceof UnknownHostException)return "Server not found. Check the URL and internet connection.";if(e instanceof IOException)return e.getMessage();return "Connection failed. Check Settings and try again.";}
    @Override public void onBackPressed(){web.evaluateJavascript("(function(){let d=document.querySelector('dialog[open]');if(d){d.close();return true}return false})()",value->{if(!"true".equals(value))super.onBackPressed();});}
    @Override protected void onDestroy(){executor.shutdownNow();if(web!=null){web.removeJavascriptInterface("KanaNative");web.destroy();web=null;}super.onDestroy();}
}

package io.github.galakcv.cahier;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.core.content.FileProvider;
import androidx.webkit.WebViewAssetLoader;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Abre o app do celular (HTML/CSS/JS em assets/www) num WebView, sem internet.
 *
 * Os arquivos são servidos em https://appassets.androidplatform.net/www/ pelo WebViewAssetLoader,
 * uma origem segura: módulos ES, IndexedDB e a Content Security Policy funcionam como no navegador.
 * O progresso fica no IndexedDB dessa origem, dentro dos dados do app.
 */
public class MainActivity extends Activity {
    private static final String HOST = "appassets.androidplatform.net";
    private static final String START_URL = "https://" + HOST + "/www/index.html";
    private static final int PICK_FILE = 41;

    private static final Map<String, String> MIME = new HashMap<>();
    static {
        MIME.put("html", "text/html");
        MIME.put("js", "text/javascript");
        MIME.put("mjs", "text/javascript");
        MIME.put("css", "text/css");
        MIME.put("json", "application/json");
        MIME.put("webmanifest", "application/manifest+json");
        MIME.put("svg", "image/svg+xml");
        MIME.put("png", "image/png");
        MIME.put("ico", "image/x-icon");
        MIME.put("txt", "text/plain");
    }

    private WebView web;
    private ValueCallback<Uri[]> pendingChooser;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if ((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
        }

        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true); // para ler o arquivo escolhido em "Importar arquivo"
        s.setSupportMultipleWindows(false);
        s.setTextZoom(100); // o tamanho do texto é ajustado nas Preferências do próprio app

        final WebViewAssetLoader loader = new WebViewAssetLoader.Builder()
                .setDomain(HOST)
                .addPathHandler("/www/", this::openAsset)
                .build();

        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return loader.shouldInterceptRequest(request.getUrl());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri url = request.getUrl();
                if (HOST.equals(url.getHost())) return false;
                // Links externos (créditos, página de downloads) abrem no navegador.
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, url));
                } catch (ActivityNotFoundException ignored) {
                    // nenhum navegador instalado
                }
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (pendingChooser != null) pendingChooser.onReceiveValue(null);
                pendingChooser = callback;
                // "*/*": muitos gerenciadores não reconhecem o tipo .json e deixariam o arquivo cinza.
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("*/*");
                try {
                    startActivityForResult(Intent.createChooser(pick, "Escolher arquivo do Cahier"), PICK_FILE);
                    return true;
                } catch (ActivityNotFoundException e) {
                    pendingChooser = null;
                    Toast.makeText(MainActivity.this, "Nenhum gerenciador de arquivos encontrado.", Toast.LENGTH_LONG).show();
                    return false;
                }
            }
        });

        web.addJavascriptInterface(new Bridge(), "CahierAndroid");

        if (savedInstanceState == null || web.restoreState(savedInstanceState) == null) {
            web.loadUrl(START_URL);
        }
    }

    private WebResourceResponse openAsset(String path) {
        if (path.isEmpty()) path = "index.html";
        if (path.contains("..")) return null;
        try {
            InputStream in = getAssets().open("www/" + path);
            int dot = path.lastIndexOf('.');
            String ext = dot >= 0 ? path.substring(dot + 1).toLowerCase(Locale.ROOT) : "";
            String mime = MIME.containsKey(ext) ? MIME.get(ext) : "application/octet-stream";
            WebResourceResponse r = new WebResourceResponse(mime, "utf-8", in);
            Map<String, String> headers = new HashMap<>();
            headers.put("Cache-Control", "no-cache");
            r.setResponseHeaders(headers);
            return r;
        } catch (IOException e) {
            return null;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == PICK_FILE) {
            if (pendingChooser != null) {
                pendingChooser.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
                pendingChooser = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        web.saveState(outState);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @SuppressWarnings("deprecation")
    private void applySystemBars(boolean dark) {
        Window w = getWindow();
        int color = Color.parseColor(dark ? "#131826" : "#FBFCFE");
        w.setStatusBarColor(color);
        w.setNavigationBarColor(color);
        View decor = w.getDecorView();
        int flags = decor.getSystemUiVisibility();
        flags = dark ? flags & ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR : flags | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            flags = dark ? flags & ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR : flags | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        }
        decor.setSystemUiVisibility(flags);
    }

    /** Funções nativas disponíveis no JavaScript como window.CahierAndroid. */
    public final class Bridge {
        @JavascriptInterface
        public String versionName() {
            try {
                PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
                return info.versionName;
            } catch (Exception e) {
                return "";
            }
        }

        /** Grava o arquivo de sincronização e abre o menu "Compartilhar" (WhatsApp, e-mail, Drive, Arquivos…). */
        @JavascriptInterface
        public boolean shareFile(String name, String text) {
            try {
                File dir = new File(getCacheDir(), "exports");
                if (!dir.isDirectory() && !dir.mkdirs()) return false;
                File[] old = dir.listFiles();
                if (old != null) for (File f : old) f.delete();
                String safe = name.replaceAll("[^A-Za-z0-9._-]", "_");
                if (safe.isEmpty()) safe = "cahier-sync.json";
                File file = new File(dir, safe);
                try (OutputStream out = new FileOutputStream(file)) {
                    out.write(text.getBytes(StandardCharsets.UTF_8));
                }
                Uri uri = FileProvider.getUriForFile(MainActivity.this, getPackageName() + ".files", file);
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("application/json");
                send.putExtra(Intent.EXTRA_STREAM, uri);
                send.putExtra(Intent.EXTRA_SUBJECT, "Progresso do Cahier");
                send.setClipData(ClipData.newRawUri(safe, uri));
                send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                final Intent chooser = Intent.createChooser(send, "Enviar progresso do Cahier");
                chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                runOnUiThread(() -> {
                    try {
                        startActivity(chooser);
                    } catch (ActivityNotFoundException e) {
                        Toast.makeText(MainActivity.this, "Nenhum app para enviar o arquivo.", Toast.LENGTH_LONG).show();
                    }
                });
                return true;
            } catch (Exception e) {
                return false;
            }
        }

        /** Ajusta a cor das barras do sistema ao tema escolhido no app. */
        @JavascriptInterface
        public void setDarkTheme(boolean dark) {
            runOnUiThread(() -> applySystemBars(dark));
        }
    }
}

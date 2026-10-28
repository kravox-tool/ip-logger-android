package com.kravox.iplogger

import android.annotation.SuppressLint
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.util.Log
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {

    companion object { private const val TAG = "IPLogger" }

    private lateinit var webView: WebView
    private val pool = Executors.newSingleThreadExecutor()

    @Volatile private var module: PyObject? = null
    @Volatile private var pythonStarted = false
    @Volatile private var cols = 80
    @Volatile private var rows = 24
    @Volatile private var cfProcess: Process? = null

    private var lastBack = 0L

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        webView = WebView(this)
        setContentView(webView)

        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            useWideViewPort = true
        }
        webView.setBackgroundColor(0xFF0B0F14.toInt())
        webView.addJavascriptInterface(JsBridge(), "Android")
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                startPython()
            }
        }
        webView.loadUrl("file:///android_asset/terminal.html")
    }

    // ---------------------------------------------------------------- Python

    private fun startPython() {
        if (pythonStarted) return
        pythonStarted = true
        pool.execute {
            try {
                if (!Python.isStarted()) Python.start(AndroidPlatform(applicationContext))
                val mod = Python.getInstance().getModule("iplogger")
                module = mod
                mod.callAttr(
                    "main",
                    PyBridge(),
                    filesDir.absolutePath,
                    applicationInfo.nativeLibraryDir + "/libcloudflared.so",
                    cols,
                    rows
                )
            } catch (t: Throwable) {
                Log.e(TAG, "Fallo al iniciar Python", t)
                writeJs("\r\n\u001b[91m[!] Error al iniciar Python: $t\u001b[0m\r\n")
            }
        }
    }

    private fun stopAll() {
        try { module?.callAttr("shutdown") } catch (_: Throwable) {}
        try { cfProcess?.destroy() } catch (_: Throwable) {}
    }

    // ------------------------------------------------------------- Terminal

    private fun writeJs(data: String) {
        val js = "window.termWrite(" + JSONObject.quote(data) + ");"
        runOnUiThread { try { webView.evaluateJavascript(js, null) } catch (_: Throwable) {} }
    }

    /** Puente llamado desde JavaScript (hilo del WebView). */
    inner class JsBridge {
        @JavascriptInterface
        fun write(data: String) = writeJs(data)

        @JavascriptInterface
        fun size(c: Int, r: Int) {
            cols = c; rows = r
            val m = module ?: return
            pool.execute { try { m.callAttr("set_size", c, r) } catch (_: Throwable) {} }
        }

        @JavascriptInterface
        fun line(text: String) {
            val m = module ?: return
            pool.execute { try { m.callAttr("push_line", text) } catch (t: Throwable) { Log.e(TAG, "push_line", t) } }
        }

        @JavascriptInterface
        fun ready() = startPython()

        @JavascriptInterface
        fun shutdown() = stopAll()
    }

    /** Puente entregado a Python (llamado desde el hilo de Python). */
    inner class PyBridge {
        @Suppress("unused")
        fun write(data: String) = writeJs(data)

        @Suppress("unused")
        fun clipboard(text: String) {
            runOnUiThread {
                val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(ClipData.newPlainText("IP Logger", text))
            }
        }

        @Suppress("unused")
        fun toast(text: String) {
            runOnUiThread { Toast.makeText(this@MainActivity, text, Toast.LENGTH_SHORT).show() }
        }

        /** Plan B: si el subprocess de Python falla, lanzamos cloudflared desde Java. */
        @Suppress("unused")
        fun runCloudflared(target: String, home: String): String {
            return try {
                val cf = File(applicationInfo.nativeLibraryDir, "libcloudflared.so")
                if (!cf.exists()) return ""
                cf.setExecutable(true, false)

                val pb = ProcessBuilder(cf.absolutePath, "tunnel", "--no-autoupdate", "--url", target)
                pb.directory(File(home))
                pb.environment()["HOME"] = home
                pb.redirectErrorStream(true)

                val proc = pb.start()
                cfProcess = proc

                val q = LinkedBlockingQueue<String>()
                val t = Thread {
                    try {
                        BufferedReader(InputStreamReader(proc.inputStream)).use { r ->
                            var l = r.readLine()
                            while (l != null) { q.put(l); l = r.readLine() }
                        }
                    } catch (_: Throwable) {}
                }
                t.isDaemon = true
                t.start()

                val deadline = System.currentTimeMillis() + 90_000
                while (System.currentTimeMillis() < deadline) {
                    val line = q.poll(500, TimeUnit.MILLISECONDS) ?: continue
                    for (w in line.replace("|", " ").split(" ")) {
                        val c = w.trim().trim('"')
                        if (c.contains("trycloudflare.com")) return c
                    }
                }
                ""
            } catch (t: Throwable) {
                Log.e(TAG, "cloudflared via Java falló", t)
                ""
            }
        }

        @Suppress("unused")
        fun stopCloudflared() {
            try { cfProcess?.destroy() } catch (_: Throwable) {}
        }
    }

    // -------------------------------------------------------------- Ciclo

    @Deprecated("Compatibilidad")
    override fun onBackPressed() {
        val now = System.currentTimeMillis()
        if (now - lastBack < 2000) {
            stopAll()
            super.onBackPressed()
        } else {
            lastBack = now
            Toast.makeText(this, "Pulsa atrás otra vez para salir", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onDestroy() {
        stopAll()
        super.onDestroy()
    }
}

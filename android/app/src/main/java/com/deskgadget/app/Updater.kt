package com.deskgadget.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/** A newer build published on GitHub. */
data class AppUpdate(
    val version: String,
    val notes: String,
    val apkUrl: String?,
    val pageUrl: String,
)

/**
 * Checks the public releases feed. No library, no background service: one small
 * HTTPS request when the app opens (at most every three days) or on demand.
 */
object Updater {
    private const val API = "https://api.github.com/repos/issacjohn/deskgadget/releases/latest"
    private const val EVERY_MS = 3L * 24 * 60 * 60 * 1000
    private const val PREFS = "updates"

    fun currentVersion(context: Context): String = try {
        context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "0"
    } catch (_: Exception) {
        "0"
    }

    fun shouldAutoCheck(context: Context): Boolean {
        val last = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong("last_check", 0)
        return System.currentTimeMillis() - last > EVERY_MS
    }

    fun markChecked(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putLong("last_check", System.currentTimeMillis()).apply()
    }

    /** Blocking; call from a background dispatcher. Null means up to date or offline. */
    fun check(context: Context): AppUpdate? {
        val conn = (URL(API).openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000
            readTimeout = 8000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("User-Agent", "DeskGadget")
        }
        return try {
            if (conn.responseCode != 200) return null
            val json = JSONObject(conn.inputStream.bufferedReader().readText())
            val tag = json.optString("tag_name").removePrefix("v").trim()
            if (tag.isBlank() || !isNewer(tag, currentVersion(context))) return null

            var apk: String? = null
            val assets = json.optJSONArray("assets")
            if (assets != null) {
                for (i in 0 until assets.length()) {
                    val asset = assets.getJSONObject(i)
                    if (asset.optString("name").lowercase().endsWith(".apk")) {
                        apk = asset.optString("browser_download_url")
                        break
                    }
                }
            }
            AppUpdate(
                version = tag,
                notes = cleanNotes(json.optString("body")),
                apkUrl = apk,
                pageUrl = json.optString("html_url"),
            )
        } catch (_: Exception) {
            null
        } finally {
            conn.disconnect()
        }
    }

    private fun cleanNotes(body: String): String = body.lines()
        .map {
            it.trim()
                .removePrefix("- ")
                .removePrefix("* ")
                .removePrefix("> ")
                .replace("**", "")
                .replace("__", "")
                .replace("`", "")
        }
        .filter { it.isNotBlank() && !it.startsWith("#") && !it.startsWith("![") }
        .joinToString("\n")
        .take(1400)

    fun isNewer(remote: String, current: String): Boolean {
        fun parts(value: String) = value.split(".", "-").mapNotNull { it.toIntOrNull() }
        val a = parts(remote)
        val b = parts(current)
        for (i in 0 until maxOf(a.size, b.size)) {
            val x = a.getOrElse(i) { 0 }
            val y = b.getOrElse(i) { 0 }
            if (x != y) return x > y
        }
        return false
    }

    /** Downloads the release APK into the app's own folder. Blocking; use Dispatchers.IO. */
    fun download(context: Context, update: AppUpdate, onProgress: (Int) -> Unit): File? {
        val url = update.apkUrl ?: return null
        val dir = File(context.getExternalFilesDir("updates"), "").apply { mkdirs() }
        dir.listFiles()?.forEach { if (it.name.endsWith(".apk") || it.name.endsWith(".part")) it.delete() }
        val target = File(dir, "DeskGadget-${update.version}.apk")
        val part = File(dir, "DeskGadget-${update.version}.part")
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL(url).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = true
                connectTimeout = 20000
                readTimeout = 30000
                setRequestProperty("User-Agent", "DeskGadget")
                setRequestProperty("Accept", "application/octet-stream")
            }
            if (conn.responseCode !in 200..299) return null
            val total = conn.contentLengthLong
            conn.inputStream.use { input ->
                part.outputStream().use { out ->
                    val buffer = ByteArray(64 * 1024)
                    var read: Int
                    var done = 0L
                    while (input.read(buffer).also { read = it } > 0) {
                        out.write(buffer, 0, read)
                        done += read
                        if (total > 0) {
                            onProgress(((done * 100) / total).toInt().coerceIn(0, 100))
                        }
                    }
                }
            }
            if (target.exists()) target.delete()
            if (!part.renameTo(target)) {
                part.copyTo(target, overwrite = true)
                part.delete()
            }
            onProgress(100)
            target
        } catch (_: Exception) {
            part.delete()
            null
        } finally {
            conn?.disconnect()
        }
    }

    fun canInstall(context: Context): Boolean = try {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.packageManager.canRequestPackageInstalls()
        } else {
            true
        }
    } catch (_: Exception) {
        false
    }

    fun openInstallSettings(context: Context) {
        try {
            context.startActivity(
                Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:${context.packageName}"),
                ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        } catch (_: Exception) {
        }
    }

    /**
     * Hands the APK to the system installer. Returns false when the user still
     * has to allow installs from DeskGadget, in which case the settings page is
     * opened and the caller can offer "Install" again.
     */
    fun install(context: Context, file: File): Boolean {
        if (!canInstall(context)) {
            openInstallSettings(context)
            return false
        }
        return try {
            val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
            context.startActivity(
                Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
            )
            true
        } catch (_: Exception) {
            false
        }
    }

    fun open(context: Context, url: String) {
        try {
            context.startActivity(
                Intent(Intent.ACTION_VIEW, Uri.parse(url))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        } catch (_: Exception) {
        }
    }
}

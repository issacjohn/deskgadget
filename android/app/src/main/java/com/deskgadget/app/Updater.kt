package com.deskgadget.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import org.json.JSONArray
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
    private const val LATEST = "https://api.github.com/repos/issacjohn/deskgadget/releases/latest"
    private const val RELEASES = "https://api.github.com/repos/issacjohn/deskgadget/releases?per_page=20"
    private const val EVERY_MS = 3L * 24 * 60 * 60 * 1000
    private const val PREFS = "updates"

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun currentVersion(context: Context): String = try {
        context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "0"
    } catch (_: Exception) {
        "0"
    }

    /** Beta builds come from pre-releases; stable builds from GitHub's "latest". */
    fun betaEnabled(context: Context): Boolean = prefs(context).getBoolean("beta", false)

    fun setBetaEnabled(context: Context, enabled: Boolean) {
        prefs(context).edit()
            .putBoolean("beta", enabled)
            .putLong("last_check", 0)  // the next open checks the new channel
            .apply()
    }

    fun shouldAutoCheck(context: Context): Boolean {
        val last = prefs(context).getLong("last_check", 0)
        return System.currentTimeMillis() - last > EVERY_MS
    }

    fun markChecked(context: Context) {
        prefs(context).edit().putLong("last_check", System.currentTimeMillis()).apply()
    }

    /** Blocking; call from a background dispatcher. Null means up to date or offline. */
    fun check(context: Context): AppUpdate? {
        val releases = fetch(if (betaEnabled(context)) RELEASES else LATEST) ?: return null
        val current = currentVersion(context)
        for (json in releases) {
            if (json.optBoolean("draft")) continue
            val tag = json.optString("tag_name").removePrefix("v").trim()
            if (tag.isBlank() || !isNewer(tag, current)) continue
            val apk = firstApk(json) ?: continue
            return AppUpdate(
                version = tag,
                notes = cleanNotes(json.optString("body")),
                apkUrl = apk,
                pageUrl = json.optString("html_url"),
            )
        }
        return null
    }

    /** One release or a list, depending on the endpoint. Newest first. */
    private fun fetch(url: String): List<JSONObject>? {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000
            readTimeout = 8000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("User-Agent", "DeskGadget")
        }
        return try {
            if (conn.responseCode != 200) return null
            val text = conn.inputStream.bufferedReader().readText()
            if (text.trimStart().startsWith("[")) {
                val array = JSONArray(text)
                (0 until array.length()).map { array.getJSONObject(it) }
            } else {
                listOf(JSONObject(text))
            }
        } catch (_: Exception) {
            null
        } finally {
            conn.disconnect()
        }
    }

    private fun firstApk(json: JSONObject): String? {
        val assets = json.optJSONArray("assets") ?: return null
        for (i in 0 until assets.length()) {
            val asset = assets.getJSONObject(i)
            if (asset.optString("name").lowercase().endsWith(".apk")) {
                return asset.optString("browser_download_url")
            }
        }
        return null
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

    /** Semver-aware: 1.3.7 > 1.3.6, 1.3.6-beta.2 > 1.3.6-beta.1, 1.3.6 > 1.3.6-beta.9. */
    fun isNewer(remote: String, current: String): Boolean {
        fun parse(value: String): Pair<List<Int>, List<String>?> {
            val clean = value.removePrefix("v").trim()
            val core = clean.substringBefore("-")
            val pre = clean.substringAfter("-", "")
                .takeIf { it.isNotBlank() }
                ?.split(".")
            return core.split(".").map { it.toIntOrNull() ?: 0 } to pre
        }

        val (remoteCore, remotePre) = parse(remote)
        val (currentCore, currentPre) = parse(current)
        for (i in 0 until maxOf(remoteCore.size, currentCore.size)) {
            val a = remoteCore.getOrElse(i) { 0 }
            val b = currentCore.getOrElse(i) { 0 }
            if (a != b) return a > b
        }

        if (remotePre == null && currentPre == null) return false
        if (remotePre == null) return true          // stable beats its own beta
        if (currentPre == null) return false        // a beta is older than the stable
        for (i in 0 until maxOf(remotePre.size, currentPre.size)) {
            val a = remotePre.getOrElse(i) { "" }
            val b = currentPre.getOrElse(i) { "" }
            if (a == b) continue
            val an = a.toIntOrNull()
            val bn = b.toIntOrNull()
            if (an != null && bn != null) return an > bn
            if (an != null) return false            // numeric < alphanumeric
            if (bn != null) return true
            return a > b
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

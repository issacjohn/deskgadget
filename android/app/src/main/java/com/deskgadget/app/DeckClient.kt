package com.deskgadget.app

import android.content.Context
import android.os.Build
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume

enum class ConnStatus { IDLE, CONNECTING, CONNECTED, RECONNECTING, ERROR }

data class PageData(
    val id: String,
    val title: String,
    val accent: String,
    val blocks: List<JSONObject>,
    val refreshable: Boolean = false,
)

data class DeckState(
    val status: ConnStatus = ConnStatus.IDLE,
    val serverName: String = "DESKGadget",
    val endpoint: String = "",
    val pages: List<PageData> = emptyList(),
    val error: String? = null,
    val toast: String? = null,
    val toastId: Long = 0,
    val theme: String = "liquid",
    val keepScreen: Boolean = false,
)

/**
 * Single WebSocket connection to the PC. Survives orientation changes and
 * reconnects with backoff. Pages arrive as declarative blocks so new server
 * modules never require an app update.
 */
class DeckClient private constructor(private val app: Context) {

    companion object {
        @Volatile
        private var instance: DeckClient? = null

        fun get(context: Context): DeckClient =
            instance ?: synchronized(this) {
                instance ?: DeckClient(context.applicationContext).also { instance = it }
            }
    }

    private val prefs = Prefs(app)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val http = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    private val _state = MutableStateFlow(DeckState())
    val state: StateFlow<DeckState> = _state.asStateFlow()

    @Volatile private var socket: WebSocket? = null
    @Volatile private var target: String? = null
    private var loopJob: Job? = null
    private var heartbeatJob: Job? = null
    private val candidates = java.util.concurrent.CopyOnWriteArrayList<String>()
    @Volatile private var active = 0

    val lastHost: String get() = prefs.host
    val lastPort: Int get() = prefs.port

    fun connect(host: String, port: Int) {
        val clean = host.trim().removePrefix("http://").removePrefix("ws://").substringBefore("/")
        if (clean.isEmpty()) {
            _state.update { it.copy(status = ConnStatus.ERROR, error = "Enter the PC's address") }
            return
        }
        val wired = LocalLink.isWiredHost(clean)
        // 127.0.0.1 is the adb reverse tunnel, not a transport of its own:
        // remembering it as "the Wi-Fi address" would break the next launch
        val loopback = clean == "127.0.0.1" || clean == "localhost"
        if (!loopback) prefs.remember(clean, port, wired)
        target = wsUrl(clean, port)
        candidates.clear()
        candidates += target!!
        // the other transport, so pulling the cable (or losing Wi-Fi) still works
        if (!loopback) {
            prefs.saved(!wired)?.let { (h, p) ->
                wsUrl(h, p).takeIf { it !in candidates }?.let { candidates += it }
            }
        }
        val usb = wsUrl("127.0.0.1", port)
        if (usb !in candidates) candidates += usb
        active = 0
        _state.update {
            it.copy(
                endpoint = httpBase(clean, port),
                status = if (it.pages.isEmpty()) ConnStatus.CONNECTING else ConnStatus.RECONNECTING,
                error = null,
            )
        }
        loopJob?.cancel()
        loopJob = scope.launch { runLoop() }
    }

    private fun wsUrl(host: String, port: Int) = "ws://$host:$port/ws"

    private fun httpBase(host: String, port: Int) = "http://$host:$port"

    private fun httpFromWs(url: String): String {
        val authority = url.removePrefix("ws://").removePrefix("wss://").substringBefore("/")
        return "http://$authority"
    }

    fun autoConnect() {
        if (loopJob != null) return
        // a plugged-in cable wins: its subnet cannot be reached over Wi-Fi
        val pick = (if (LocalLink.hasWired()) prefs.saved(true) else null)
            ?: prefs.saved(false)
            ?: prefs.host.takeIf { it.isNotBlank() }?.let { it to prefs.port }
        if (pick != null) connect(pick.first, pick.second)
    }

    /** Ask the PC to open a URL in its browser, in front of whatever is running. */
    fun openUrl(url: String): Boolean {
        val live = socket ?: return false
        val msg = JSONObject()
            .put("v", 1)
            .put("type", "open_url")
            .put("url", url)
        return runCatching { live.send(msg.toString()) }.isSuccess
    }

    fun disconnect() {
        target = null
        loopJob?.cancel()
        loopJob = null
        socket?.close(1000, "bye")
        socket = null
        // drop the pages too: otherwise the app stays on a dead deck with no
        // way back. Clearing them returns the user to the connect screen.
        _state.update {
            it.copy(
                status = ConnStatus.IDLE,
                pages = emptyList(),
                endpoint = "",
                error = null,
                toast = null,
            )
        }
    }

    private suspend fun runLoop() {
        var attempt = 0
        while (target != null) {
            val url = candidates.getOrNull(active) ?: break
            _state.update {
                it.copy(status = if (it.pages.isEmpty()) ConnStatus.CONNECTING else ConnStatus.RECONNECTING)
            }
            val stayed = runOnce(url)
            if (target == null) break
            attempt = if (stayed) 0 else attempt + 1

            if (!stayed) {
                // one endpoint died: hop to the next candidate (LAN <-> USB)
                if (candidates.size > 1) active = (active + 1) % candidates.size
                // every full lap, ask the network for the server in case its IP moved
                val lap = (candidates.size * 2).coerceAtLeast(2)
                if (attempt % lap == 0) {
                    val hits = discover()
                    hits.forEach { (host, port, wired) ->
                        val url = wsUrl(host, port)
                        if (url !in candidates) candidates += url
                        prefs.remember(host, port, wired)
                        Log.i("DeckClient", "discovered server at $host:$port (wired=$wired)")
                    }
                    // prefer a cable address when one is actually plugged in
                    val preferWired = LocalLink.hasWired()
                    val pick = hits.firstOrNull { !preferWired || it.third } ?: hits.firstOrNull()
                    pick?.let { active = candidates.indexOf(wsUrl(it.first, it.second)) }
                }
            }
            delay((700L * (attempt + 1)).coerceAtMost(5000L))
        }
    }

    /** Races mDNS against the UDP beacon and merges every address that answered. */
    private suspend fun discover(): List<Triple<String, Int, Boolean>> = coroutineScope {
        val byMdns = async {
            mdnsProbe()?.let { (host, port) ->
                listOf(Triple(host, port, LocalLink.isWiredHost(host)))
            } ?: emptyList()
        }
        val byUdp = async {
            withContext(Dispatchers.IO) {
                UdpDiscovery.probe(prefs.port).map { Triple(it.host, it.port, it.wired) }
            }
        }
        (byMdns.await() + byUdp.await()).distinctBy { it.first to it.second }
    }

    private suspend fun mdnsProbe(): Pair<String, Int>? {
        val probe = LanDiscovery(app)
        return try {
            kotlinx.coroutines.withTimeoutOrNull(3200) {
                suspendCancellableCoroutine { cont ->
                    probe.start(onFound = { found ->
                        if (cont.isActive) cont.resume(found.host to found.port)
                    })
                    cont.invokeOnCancellation { probe.stop() }
                }
            }
        } catch (e: Exception) {
            null
        } finally {
            probe.stop()
        }
    }

    private suspend fun runOnce(url: String): Boolean = suspendCancellableCoroutine { cont ->
        var opened = false
        val listener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                opened = true
                socket = webSocket
                webSocket.send(hello())
                _state.update {
                    it.copy(status = ConnStatus.CONNECTED, error = null, endpoint = httpFromWs(url))
                }
                // app-level heartbeat so the server can tell a live link from a dead one
                heartbeatJob?.cancel()
                heartbeatJob = scope.launch {
                    while (true) {
                        delay(15_000)
                        val live = socket ?: break
                        live.send("""{"v":1,"type":"ping"}""")
                    }
                }
            }

            override fun onMessage(webSocket: WebSocket, text: String) = handle(text)

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w("DeckClient", "socket failure: ${t.message}")
                socket = null
                heartbeatJob?.cancel()
                if (cont.isActive) cont.resume(false)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                socket = null
                heartbeatJob?.cancel()
                if (!opened) _state.update { it.copy(error = "Can't reach the PC") }
                if (cont.isActive) cont.resume(opened)
            }
        }
        val ws = http.newWebSocket(Request.Builder().url(url).build(), listener)
        cont.invokeOnCancellation { ws.cancel() }
    }

    private fun hello(): String {
        val info = JSONObject()
            .put("name", Build.MODEL.replace('_', ' '))
            .put("model", Build.MODEL)
            .put("sdk", Build.VERSION.SDK_INT)
        return JSONObject()
            .put("v", 1)
            .put("type", "hello")
            .put("device_id", prefs.deviceId)
            .put("device", info)
            .toString()
    }

    private fun handle(text: String) {
        try {
            val msg = JSONObject(text)
            when (msg.optString("type")) {
                "welcome" -> {
                    val srv = msg.optJSONObject("server")
                    val name = srv?.optString("name").orEmpty()
                    val pages = parsePages(msg.optJSONArray("pages"))
                    // remember every address the PC has: the LAN one for Wi-Fi,
                    // the tether one when the phone is on the cable
                    val lanPort = srv?.optInt("port", prefs.port) ?: prefs.port
                    val lanHosts = LinkedHashSet<String>()
                    srv?.optString("lan_ip").orEmpty().takeIf { it.isNotBlank() }?.let { lanHosts += it }
                    srv?.optJSONArray("lan_ips")?.let { arr ->
                        for (i in 0 until arr.length()) {
                            arr.optString(i).takeIf { it.isNotBlank() }?.let { lanHosts += it }
                        }
                    }
                    lanHosts.forEach { host ->
                        prefs.remember(host, lanPort, LocalLink.isWiredHost(host))
                        val url = wsUrl(host, lanPort)
                        if (url !in candidates) candidates += url
                    }
                    _state.update {
                        it.copy(
                            status = ConnStatus.CONNECTED,
                            serverName = name.ifBlank { it.serverName },
                            pages = pages,
                            theme = msg.optString("theme", it.theme),
                            keepScreen = msg.optBoolean("keep_screen", it.keepScreen),
                        )
                    }
                }
                "layout" -> {
                    val pages = parsePages(msg.optJSONArray("pages"))
                    _state.update {
                        it.copy(
                            pages = pages,
                            theme = msg.optString("theme", it.theme),
                            keepScreen = msg.optBoolean("keep_screen", it.keepScreen),
                        )
                    }
                }
                "page" -> {
                    val page = parsePage(msg.getJSONObject("page"))
                    _state.update { s ->
                        val list = s.pages.toMutableList()
                        val idx = list.indexOfFirst { it.id == page.id }
                        if (idx >= 0) list[idx] = page else list.add(page)
                        s.copy(pages = list)
                    }
                }
                "toast" -> {
                    val t = msg.optString("text")
                    _state.update { it.copy(toast = t, toastId = System.currentTimeMillis()) }
                }
            }
        } catch (e: Exception) {
            Log.w("DeckClient", "bad message: ${e.message}")
        }
    }

    private fun parsePages(arr: JSONArray?): List<PageData> {
        if (arr == null) return emptyList()
        val out = ArrayList<PageData>(arr.length())
        for (i in 0 until arr.length()) out.add(parsePage(arr.getJSONObject(i)))
        return out
    }

    private fun parsePage(o: JSONObject): PageData {
        val blocks = ArrayList<JSONObject>()
        val arr = o.optJSONArray("blocks")
        if (arr != null) for (i in 0 until arr.length()) blocks.add(arr.getJSONObject(i))
        return PageData(
            id = o.optString("id", o.optString("module", "")),
            title = o.optString("title", ""),
            accent = o.optString("accent", "#7CE7FF"),
            blocks = blocks,
            refreshable = o.optBoolean("refreshable", false),
        )
    }

    fun sendAction(module: String, action: String, payload: JSONObject? = null) {
        val ws = socket ?: return
        val msg = JSONObject()
            .put("v", 1)
            .put("type", "action")
            .put("module", module)
            .put("action", action)
        if (payload != null) msg.put("payload", payload)
        ws.send(msg.toString())
    }

    fun moduleForPage(pageId: String): String = pageId
}

// Phone microphone -> /ws/mic as 48 kHz mono PCM16.
package com.deskgadget.app

import android.Manifest
import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response as HttpCallResponse
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.abs
import kotlin.math.max

/**
 * Captures the microphone and streams raw 48 kHz mono PCM16 to the PC.
 *
 * The PC picks the output device, so selecting a virtual cable there is what
 * makes this show up as a microphone in call apps.
 */
class MicStream(endpoint: String) {
    private val url = when {
        endpoint.startsWith("https://") -> "wss://" + endpoint.removePrefix("https://")
        endpoint.startsWith("http://") -> "ws://" + endpoint.removePrefix("http://")
        else -> "ws://$endpoint"
    }.trimEnd('/') + "/ws/mic"

    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    @Volatile private var socket: WebSocket? = null
    private val open = AtomicBoolean(false)
    private val running = AtomicBoolean(false)
    private val sent = AtomicInteger(0)
    @Volatile private var level = 0f
    @Volatile private var failure: String? = null

    private var record: AudioRecord? = null
    private var thread: Thread? = null

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: HttpCallResponse) {
            socket = webSocket
            open.set(true)
            failure = null
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            open.set(false)
            if (socket === webSocket) socket = null
        }

        override fun onFailure(
            webSocket: WebSocket,
            t: Throwable,
            response: HttpCallResponse?,
        ) {
            open.set(false)
            failure = t.message ?: "microphone link failed"
            if (socket === webSocket) socket = null
        }
    }

    private fun connect() {
        if (socket != null) return
        val request = Request.Builder().url(url).header("X-Device", Build.MODEL).build()
        socket = client.newWebSocket(request, listener)
    }

    fun start() {
        if (running.getAndSet(true)) return
        connect()
        thread = Thread({ capture() }, "deskgadget-mic").apply {
            isDaemon = true
            start()
        }
    }

    fun ensure() {
        if (running.get()) connect()
    }

    fun stop() {
        running.set(false)
        runCatching { thread?.join(400) }
        thread = null
        runCatching { record?.stop() }
        runCatching { record?.release() }
        record = null
        runCatching { socket?.close(1000, null) }
        socket = null
        open.set(false)
        level = 0f
    }

    fun isOpen(): Boolean = open.get()
    fun takeCount(): Int = sent.getAndSet(0)
    fun level(): Float = level
    fun error(): String? = failure

    @SuppressLint("MissingPermission")
    private fun capture() {
        val rate = 48_000
        val chunkBytes = 1_920  // 20 ms of mono PCM16
        val min = AudioRecord.getMinBufferSize(
            rate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (min <= 0) {
            failure = "This phone cannot record at 48 kHz"
            running.set(false)
            return
        }
        val recorder = runCatching {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                rate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                max(min, chunkBytes * 10),
            )
        }.getOrNull()
        if (recorder == null || recorder.state != AudioRecord.STATE_INITIALIZED) {
            runCatching { recorder?.release() }
            failure = "Microphone unavailable"
            running.set(false)
            return
        }
        record = recorder
        runCatching { recorder.startRecording() }.onFailure {
            failure = it.message ?: "Microphone unavailable"
            running.set(false)
            return
        }

        // Keep the room out of the call: the platform echo canceller and noise
        // suppressor are on by default (and quietly skipped when unsupported).
        val session = recorder.audioSessionId
        val noise = runCatching {
            if (NoiseSuppressor.isAvailable()) NoiseSuppressor.create(session) else null
        }.getOrNull()
        val echo = runCatching {
            if (AcousticEchoCanceler.isAvailable()) AcousticEchoCanceler.create(session) else null
        }.getOrNull()
        val gain = runCatching {
            if (AutomaticGainControl.isAvailable()) AutomaticGainControl.create(session) else null
        }.getOrNull()
        runCatching { noise?.enabled = true }
        runCatching { echo?.enabled = true }
        runCatching { gain?.enabled = true }

        val buffer = ByteArray(chunkBytes)
        while (running.get()) {
            val read = recorder.read(buffer, 0, buffer.size)
            if (read <= 0) continue

            // peak-ish level for the UI, decays between chunks
            var peak = 0
            var i = 0
            while (i + 1 < read) {
                val sample = (buffer[i].toInt() and 0xFF) or (buffer[i + 1].toInt() shl 8)
                peak = max(peak, abs(sample.toShort().toInt()))
                i += 2
            }
            level = max(peak / 32768f, level * 0.82f)

            val ws = socket
            if (ws == null || !open.get() || ws.queueSize() > 400_000) continue
            if (ws.send(ByteString.of(*buffer.copyOf(read)))) sent.incrementAndGet()
        }

        runCatching { gain?.release() }
        runCatching { echo?.release() }
        runCatching { noise?.release() }
        runCatching { recorder.stop() }
        runCatching { recorder.release() }
        record = null
    }
}

package com.deskgadget.app

import android.util.Log
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.SocketTimeoutException

/**
 * Finds the server even when mDNS is blocked and the PC's IP has changed.
 *
 * Broadcasts a tiny probe on every local link and takes what answers. The
 * address a reply arrived *from* is the one that is guaranteed to route back
 * over that same link: on USB tethering that is the PC's `192.168.42.x`, not
 * the LAN address it advertises. The advertised list is only a fallback.
 */
object UdpDiscovery {

    private const val PROBE = "DeskGadget?"

    data class Reply(val name: String, val host: String, val port: Int, val wired: Boolean)

    fun probe(port: Int, timeoutMs: Long = 2000, usbOnly: Boolean = false): List<Reply> {
        val links = LocalLink.available()
        val scope = if (usbOnly) links.filter { it.wired } else links
        if (scope.isEmpty() && usbOnly) return emptyList()

        var sock: DatagramSocket? = null
        return try {
            sock = DatagramSocket().apply {
                broadcast = true
                soTimeout = 300
            }
            val payload = PROBE.toByteArray()
            val targets = LinkedHashSet<InetAddress>()

            scope.forEach { link ->
                runCatching { targets.add(InetAddress.getByName(link.broadcast)) }
            }
            // a wildcard broadcast still helps on phones that hide interfaces
            if (!usbOnly) {
                runCatching { targets.add(InetAddress.getByName("255.255.255.255")) }
            }
            if (targets.isEmpty()) return emptyList()

            targets.forEach { address ->
                runCatching {
                    sock.send(DatagramPacket(payload, payload.size, address, port))
                }
            }

            val found = LinkedHashMap<String, Reply>()
            val deadline = System.currentTimeMillis() + timeoutMs
            while (System.currentTimeMillis() < deadline) {
                val buffer = ByteArray(512)
                val packet = DatagramPacket(buffer, buffer.size)
                try {
                    sock.receive(packet)
                } catch (e: SocketTimeoutException) {
                    continue
                }
                val text = String(packet.data, 0, packet.length).trim()
                val json = runCatching { JSONObject(text) }.getOrNull() ?: continue

                val replyPort = json.optInt("port", port)
                val name = json.optString("name").ifBlank { "DeskGadget" }
                val hosts = LinkedHashSet<String>()

                // the sender address is the reachable one for this link
                packet.address?.hostAddress?.let { hosts.add(it) }
                json.optString("ip").takeIf { it.isNotBlank() }?.let { hosts.add(it) }
                json.optJSONArray("ips")?.let { arr ->
                    for (i in 0 until arr.length()) {
                        arr.optString(i).takeIf { it.isNotBlank() }?.let { hosts.add(it) }
                    }
                }

                val sender = packet.address?.hostAddress
                hosts
                    .filterNot { it.startsWith("127.") || it.startsWith("169.254.") }
                    .filterNot { usbOnly && it != sender && !links.any { l -> l.wired && l.contains(it) } }
                    .forEach { host ->
                        if (host !in found) {
                            val wired = links.any { it.wired && it.contains(host) }
                            found[host] = Reply(name, host, replyPort, wired)
                        }
                    }
            }
            found.values.toList()
        } catch (e: Exception) {
            Log.w("UdpDiscovery", "probe failed: ${e.message}")
            emptyList()
        } finally {
            runCatching { sock?.close() }
        }
    }
}

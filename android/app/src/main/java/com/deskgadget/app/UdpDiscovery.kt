package com.deskgadget.app

import android.util.Log
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException
import java.util.Collections

/**
 * Finds the server even when mDNS is blocked and the PC's IP has changed.
 * Broadcasts a tiny probe to every local broadcast address and takes the first
 * answer; the server replies with the address it currently has.
 */
object UdpDiscovery {

    private const val PROBE = "DESKGADGET?"

    fun probe(port: Int, timeoutMs: Long = 2600): Pair<String, Int>? {
        var sock: DatagramSocket? = null
        return try {
            sock = DatagramSocket().apply {
                broadcast = true
                soTimeout = 350
            }
            val payload = PROBE.toByteArray()
            val targets = LinkedHashSet<InetAddress>()

            runCatching { targets.add(InetAddress.getByName("255.255.255.255")) }
            runCatching {
                Collections.list(NetworkInterface.getNetworkInterfaces()).forEach { nif ->
                    nif.interfaceAddresses.forEach { address ->
                        address.broadcast?.let { targets.add(it) }
                    }
                }
            }
            targets.forEach { address ->
                runCatching {
                    sock.send(DatagramPacket(payload, payload.size, address, port))
                }
            }

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
                val ip = json.optString("ip")
                if (ip.isNotBlank()) return ip to json.optInt("port", port)
            }
            null
        } catch (e: Exception) {
            Log.w("UdpDiscovery", "probe failed: ${e.message}")
            null
        } finally {
            runCatching { sock?.close() }
        }
    }
}

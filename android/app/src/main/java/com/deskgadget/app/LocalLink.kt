package com.deskgadget.app

import java.net.Inet4Address
import java.net.NetworkInterface

/**
 * A local IPv4 link. [wired] is true for USB tethering (and Ethernet), false
 * for Wi-Fi — that difference is what lets the app treat a cable as its own
 * transport instead of one more address to guess at.
 */
data class LocalLink(
    val address: String,
    val broadcast: String,
    val prefix: Int,
    val wired: Boolean,
) {
    /** True when [host] is on this link's subnet. */
    fun contains(host: String): Boolean {
        val own = ipv4(address) ?: return false
        val peer = ipv4(host) ?: return false
        if (prefix !in 1..32) return false
        val mask = (0xffffffffL shl (32 - prefix)) and 0xffffffffL
        return (own and mask) == (peer and mask)
    }

    companion object {
        private fun ipv4(value: String): Long? {
            val parts = value.trim().split('.')
            if (parts.size != 4) return null
            var result = 0L
            for (part in parts) {
                if (!part.matches(Regex("0|[1-9][0-9]{0,2}"))) return null
                val number = part.toIntOrNull() ?: return null
                if (number !in 0..255) return null
                result = (result shl 8) or number.toLong()
            }
            return result
        }

        /** Android exposes USB tethering as rndis0 / usb0 / ncm0 on most phones. */
        fun isWiredName(name: String) =
            Regex("^(rndis|usb|ncm|eth|enx)", RegexOption.IGNORE_CASE).containsMatchIn(name)

        private val ignore =
            Regex("^(rmnet|ccmni|pdp|wwan|tun|tap|lo)", RegexOption.IGNORE_CASE)

        /** Re-read on every attempt, so plugging the cable in needs no restart. */
        fun available(): List<LocalLink> = try {
            NetworkInterface.getNetworkInterfaces()?.toList().orEmpty().flatMap { nif ->
                if (!nif.isUp || nif.isLoopback || ignore.containsMatchIn(nif.name)) {
                    emptyList()
                } else {
                    nif.interfaceAddresses.mapNotNull { entry ->
                        val local = (entry.address as? Inet4Address)?.hostAddress
                        val broadcast = entry.broadcast?.hostAddress
                        if (local == null || broadcast == null) null
                        else LocalLink(local, broadcast, entry.networkPrefixLength.toInt(), isWiredName(nif.name))
                    }
                }
            }.distinctBy { it.address }.take(8)
        } catch (e: Exception) {
            emptyList()
        }

        fun hasWired(): Boolean = available().any { it.wired }

        /** Which transport an address belongs to. */
        fun isWiredHost(host: String): Boolean =
            available().any { it.wired && it.contains(host) }
    }
}

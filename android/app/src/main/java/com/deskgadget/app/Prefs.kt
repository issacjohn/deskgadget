package com.deskgadget.app

import android.content.Context
import java.util.UUID

/** Small persisted settings bag. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("deskgadget", Context.MODE_PRIVATE)

    /** Last address used, whatever the transport. */
    var host: String
        get() = sp.getString("host", "") ?: ""
        set(value) = sp.edit().putString("host", value).apply()

    var port: Int
        get() = sp.getInt("port", 8787)
        set(value) = sp.edit().putInt("port", value).apply()

    /** Wi-Fi / Ethernet address the server reported. */
    var lanHost: String
        get() = sp.getString("lan_host", "") ?: ""
        set(value) = sp.edit().putString("lan_host", value).apply()

    var lanPort: Int
        get() = sp.getInt("lan_port", 8787)
        set(value) = sp.edit().putInt("lan_port", value).apply()

    /** USB tethering address — a different subnet from the LAN one. */
    var usbHost: String
        get() = sp.getString("usb_host", "") ?: ""
        set(value) = sp.edit().putString("usb_host", value).apply()

    var usbPort: Int
        get() = sp.getInt("usb_port", 8787)
        set(value) = sp.edit().putInt("usb_port", value).apply()

    /** Remember an endpoint under the transport it actually belongs to. */
    fun remember(host: String, port: Int, wired: Boolean) {
        this.host = host
        this.port = port
        if (wired) {
            usbHost = host
            usbPort = port
        } else {
            lanHost = host
            lanPort = port
        }
    }

    /** The saved endpoint for a transport, if one was ever used. */
    fun saved(wired: Boolean): Pair<String, Int>? {
        val h = if (wired) usbHost else lanHost
        if (h.isBlank()) return null
        return h to (if (wired) usbPort else lanPort)
    }

    val deviceId: String
        get() = sp.getString("device_id", null) ?: UUID.randomUUID().toString().also {
            sp.edit().putString("device_id", it).apply()
        }
}

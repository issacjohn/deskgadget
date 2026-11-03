package com.deskgadget.app

import android.content.Context
import java.util.UUID

/** Small persisted settings bag. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("deskgadget", Context.MODE_PRIVATE)

    var host: String
        get() = sp.getString("host", "") ?: ""
        set(value) = sp.edit().putString("host", value).apply()

    var port: Int
        get() = sp.getInt("port", 8787)
        set(value) = sp.edit().putInt("port", value).apply()

    /** Last LAN address the server reported, used when the USB bridge drops. */
    var lanHost: String
        get() = sp.getString("lan_host", "") ?: ""
        set(value) = sp.edit().putString("lan_host", value).apply()

    var lanPort: Int
        get() = sp.getInt("lan_port", 8787)
        set(value) = sp.edit().putInt("lan_port", value).apply()

    val deviceId: String
        get() = sp.getString("device_id", null) ?: UUID.randomUUID().toString().also {
            sp.edit().putString("device_id", it).apply()
        }
}

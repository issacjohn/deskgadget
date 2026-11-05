package com.deskgadget.app

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.util.Log

/** Finds `_deskgadget._tcp.` servers on the local network. */
class LanDiscovery(context: Context) {

    data class Found(val name: String, val host: String, val port: Int)

    private val app = context.applicationContext
    private val nsd = app.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val wifi = app.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    private var multicastLock: WifiManager.MulticastLock? = null
    private var listener: NsdManager.DiscoveryListener? = null
    private val resolving = HashSet<String>()

    fun start(onFound: (Found) -> Unit, onLost: (String) -> Unit = {}) {
        if (listener != null) return
        // mDNS replies are multicast; without this lock many devices never see them
        try {
            multicastLock = wifi?.createMulticastLock("deskgadget-mdns")?.apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (e: Exception) {
            Log.w("LanDiscovery", "multicast lock failed: ${e.message}")
        }
        val cb = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {}

            override fun onServiceFound(info: NsdServiceInfo) {
                if (info.serviceType != "_deskgadget._tcp." || resolving.contains(info.serviceName)) return
                resolving.add(info.serviceName)
                resolve(info, onFound) { resolving.remove(info.serviceName) }
            }

            override fun onServiceLost(info: NsdServiceInfo) {
                onLost(info.serviceName)
                resolving.remove(info.serviceName)
            }

            override fun onDiscoveryStopped(serviceType: String) {}

            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.w("LanDiscovery", "start failed $errorCode")
                stop()
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
        }
        listener = cb
        runCatching { nsd.discoverServices("_deskgadget._tcp.", NsdManager.PROTOCOL_DNS_SD, cb) }
            .onFailure { listener = null }
    }

    @Suppress("DEPRECATION")
    private fun resolve(info: NsdServiceInfo, onFound: (Found) -> Unit, done: () -> Unit) {
        nsd.resolveService(info, object : NsdManager.ResolveListener {
            override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) = done()

            override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                val host = serviceInfo.host?.hostAddress
                if (!host.isNullOrBlank()) {
                    onFound(Found(serviceInfo.serviceName, host, serviceInfo.port))
                }
                done()
            }
        })
    }

    fun stop() {
        listener?.let { runCatching { nsd.stopServiceDiscovery(it) } }
        listener = null
        try {
            multicastLock?.let { if (it.isHeld) it.release() }
        } catch (e: Exception) {
            Log.w("LanDiscovery", "multicast release failed")
        }
        multicastLock = null
    }
}

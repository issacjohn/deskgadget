package com.deskgadget.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : ComponentActivity() {

    private lateinit var client: DeckClient

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // full screen: hide the status and navigation bars, swipe to reveal them
        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)
        androidx.core.view.WindowCompat.getInsetsController(window, window.decorView).apply {
            hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior =
                androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }

        client = DeckClient.get(this)
        askNotificationPermission()
        client.autoConnect()

        setContent {
            DeckTheme {
                val state by client.state.collectAsState()

                // light themes need dark status-bar icons
                LaunchedEffect(state.theme) {
                    val light = paletteFor(state.theme).light
                    androidx.core.view.WindowCompat.getInsetsController(window, window.decorView).apply {
                        isAppearanceLightStatusBars = light
                        isAppearanceLightNavigationBars = light
                    }
                }

                // dashboard-controlled "keep this phone awake" for desk use
                LaunchedEffect(state.keepScreen) {
                    if (state.keepScreen) {
                        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    } else {
                        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    }
                }

                    LaunchedEffect(state.status) {
                        if (state.status == ConnStatus.CONNECTED) {
                            startDeckService()
                        } else if (state.pages.isEmpty()) {
                            stopDeckService()
                        }
                    }

                    if (state.pages.isEmpty()) {
                        LiquidBackdrop(paletteFor(state.theme)) {
                            ConnectScreen(
                                state = state,
                                prefs = Prefs(this@MainActivity),
                                onConnect = { host, port -> client.connect(host, port) },
                            )
                        }
                    } else {
                        LiquidBackdrop(paletteFor(state.theme)) {
                            DeckScreen(
                                state = state,
                                onAction = { module, action, payload ->
                                    client.sendAction(module, action, payload)
                                },
                                onDisconnect = {
                                    client.disconnect()
                                    stopDeckService()
                                },
                            )
                        }
                    }
            }
        }
    }

    /** Hardware volume rocker drives the PC, the whole point of the app. */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.action == KeyEvent.ACTION_DOWN) {
            val media = client.state.value.pages.any { it.id == "media" }
            if (media) {
                when (event.keyCode) {
                    KeyEvent.KEYCODE_VOLUME_UP -> {
                        client.sendAction("media", "volume_up")
                        return true
                    }
                    KeyEvent.KEYCODE_VOLUME_DOWN -> {
                        client.sendAction("media", "volume_down")
                        return true
                    }
                }
            }
        }
        return super.dispatchKeyEvent(event)
    }

    private fun startDeckService() {
        runCatching {
            ContextCompat.startForegroundService(this, Intent(this, DeckService::class.java))
        }
    }

    private fun stopDeckService() {
        runCatching { stopService(Intent(this, DeckService::class.java)) }
    }

    private fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    21,
                )
            }
        }
    }
}

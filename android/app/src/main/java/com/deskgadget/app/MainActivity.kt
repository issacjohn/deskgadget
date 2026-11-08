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
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

class MainActivity : ComponentActivity() {

    private lateinit var client: DeckClient

    private fun setKeepScreen(on: Boolean) {
        if (on) {
            window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }

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

                // The dashboard is a companion screen: keep the display on while
                // it is in front. The dashboard can additionally pin it awake
                // when the app is not visible.
                val keepAlways by rememberUpdatedState(state.keepScreen)
                val lifecycle = LocalLifecycleOwner.current
                DisposableEffect(lifecycle) {
                    val observer = LifecycleEventObserver { _, event ->
                        when (event) {
                            Lifecycle.Event.ON_RESUME -> setKeepScreen(true)
                            Lifecycle.Event.ON_PAUSE -> setKeepScreen(keepAlways)
                            else -> {}
                        }
                    }
                    lifecycle.lifecycle.addObserver(observer)
                    onDispose { lifecycle.lifecycle.removeObserver(observer) }
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
                                onOpenUrl = { url ->
                                    // the PC does the opening; the phone is only a remote.
                                    // If the link is down, fall back to the phone browser.
                                    if (!client.openUrl(url)) {
                                        runCatching {
                                            startActivity(
                                                Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url))
                                            )
                                        }
                                    }
                                },
                            )
                        }
                    }
            }
        }
    }

    /** Notifications or a swipe can bring the bars back; tuck them away again. */
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (!hasFocus) return
        androidx.core.view.WindowCompat.getInsetsController(window, window.decorView).apply {
            hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior =
                androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
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

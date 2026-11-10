package com.deskgadget.app

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.PagerState
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ContentPaste
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.DesktopWindows
import androidx.compose.material.icons.rounded.GridView
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.Newspaper
import androidx.compose.material.icons.rounded.PowerSettingsNew
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Storage
import androidx.compose.material.icons.rounded.TouchApp
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material.icons.rounded.WbSunny
import androidx.compose.material.icons.rounded.PhotoCamera
import androidx.compose.material.icons.rounded.Widgets
import androidx.compose.material.icons.rounded.Window
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.SubcomposeLayout
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Density
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/* ============================== connect ============================== */

/** One PC the phone can reach, with the transport it answered on. */
private data class ServerChoice(
    val name: String,
    val host: String,
    val port: Int,
    val wired: Boolean,
)

@Composable
fun ConnectScreen(
    state: DeckState,
    prefs: Prefs,
    onConnect: (String, Int) -> Unit,
) {
    val context = LocalContext.current
    val discovery = remember { LanDiscovery(context) }
    var found by remember { mutableStateOf<List<ServerChoice>>(emptyList()) }
    var host by remember { mutableStateOf(prefs.host.ifBlank { "" }) }
    var port by remember { mutableStateOf(prefs.port.toString()) }
    var scanning by remember { mutableStateOf(true) }
    var didAuto by remember { mutableStateOf(false) }

    fun addServer(name: String, h: String, p: Int, wired: Boolean) {
        if (h.isBlank()) return
        found = (found.filterNot { it.host == h && it.port == p } +
            ServerChoice(name, h, p, wired))
        scanning = false
    }

    DisposableEffect(Unit) {
        discovery.start(
            onFound = { f -> addServer(f.name, f.host, f.port, LocalLink.isWiredHost(f.host)) },
            onLost = {},
        )
        onDispose { discovery.stop() }
    }

    // The beacon finds the PC over Wi-Fi, Ethernet and USB tethering. Keep
    // probing while this screen is open, so plugging a cable in is noticed.
    LaunchedEffect(Unit) {
        while (true) {
            val cable = LocalLink.hasWired()
            val hits = withContext(Dispatchers.IO) {
                // a plugged-in cable is its own subnet: ask there first
                val usb = if (cable) UdpDiscovery.probe(prefs.port, 1200, usbOnly = true) else emptyList()
                val rest = UdpDiscovery.probe(prefs.port, 1400)
                usb + rest
            }
            hits.forEach { addServer(it.name, it.host, it.port, it.wired) }
            delay(4000)
        }
    }

    LaunchedEffect(Unit) {
        delay(4500)
        scanning = false
    }

    var usbAttempt by remember { mutableIntStateOf(0) }
    var usbHelp by remember { mutableStateOf(false) }
    val latestStatus = rememberUpdatedState(state.status)

    fun connectUsb() {
        usbAttempt += 1
        onConnect("127.0.0.1", 8787)
    }

    // 127.0.0.1 only answers when ADB forwarding or USB tethering is live.
    LaunchedEffect(usbAttempt) {
        if (usbAttempt == 0) return@LaunchedEffect
        delay(6000)
        if (latestStatus.value != ConnStatus.CONNECTED) usbHelp = true
    }

    // nothing saved and exactly one PC answered: connect without a tap
    LaunchedEffect(found, host, state.status) {
        val noSaved = prefs.saved(false) == null && prefs.saved(true) == null
        if (!didAuto && noSaved && host.isBlank() && found.size == 1) {
            didAuto = true
            val only = found.first()
            host = only.host
            port = only.port.toString()
            onConnect(only.host, only.port)
        }
    }

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val wide = maxWidth > maxHeight
        val compact = maxHeight < 400.dp
        CompositionLocalProvider(LocalCompactLayout provides compact) {
        if (wide) {
            Row(
                Modifier
                    .fillMaxSize()
                    .systemBarsPadding()
                    .padding(horizontal = 40.dp, vertical = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f).padding(end = 36.dp)) {
                    BrandBlock()
                    Spacer(Modifier.height(16.dp))
                    QuickSetupCard()
                }
                Box(Modifier.weight(1.15f).fillMaxHeight()) {
                    Column(
                        Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.Center,
                    ) {
                        ConnectCard(
                            state = state,
                            host = host,
                            port = port,
                            found = found,
                            scanning = scanning,
                            onHost = { host = it },
                            onPort = { port = it },
                            onConnect = onConnect,
                            onConnectUsb = { connectUsb() },
                        )
                    }
                }
            }
        } else {
            Column(
                Modifier
                    .fillMaxSize()
                    .systemBarsPadding()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 24.dp, vertical = 20.dp),
            ) {
                Spacer(Modifier.height(26.dp))
                BrandBlock()
                Spacer(Modifier.height(34.dp))
                ConnectCard(
                    state = state,
                    host = host,
                    port = port,
                    found = found,
                    scanning = scanning,
                    onHost = { host = it },
                    onPort = { port = it },
                    onConnect = onConnect,
                    onConnectUsb = { connectUsb() },
                )
                Spacer(Modifier.height(22.dp))
                QuickSetupCard()
                Spacer(Modifier.height(28.dp))
            }
        }
        }
    }

    if (usbHelp) {
        UsbHelpDialog(
            onClose = { usbHelp = false },
            onRetry = {
                usbHelp = false
                connectUsb()
            },
        )
    }
}

@Composable
private fun UsbHelpDialog(onClose: () -> Unit, onRetry: () -> Unit) {
    Dialog(onDismissRequest = onClose) {
        Column(
            Modifier
                .width(360.dp)
                .clip(RoundedCornerShape(24.dp))
                .background(Color(0xF20A0F16))
                .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(24.dp))
                .padding(20.dp)
        ) {
            Text(
                "USB cable not ready",
                color = Ink,
                fontSize = 18.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                "Turn on USB tethering on this phone: Settings > Connections > "
                    + "Mobile hotspot & tethering > USB tethering.\n\n"
                    + "Or enable USB debugging (ADB) so the Windows app can forward the port.",
                color = Muted,
                fontSize = 12.5.sp,
                lineHeight = 18.sp,
            )
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(
                    Modifier
                        .weight(1f)
                        .height(44.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(14.dp))
                        .clickable(role = Role.Button, onClick = onClose),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("Close", color = Ink.copy(alpha = 0.82f), fontSize = 13.sp)
                }
                Box(
                    Modifier
                        .weight(1f)
                        .height(44.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(Brush.linearGradient(listOf(Color(0xFF7CE7FF), Color(0xFFB69CFF))))
                        .clickable(role = Role.Button, onClick = onRetry),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "Try again",
                        color = Color(0xFF06121A),
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}

@Composable
private fun BrandBlock() {
    Text(
        "DeskGadget",
        color = Ink,
        fontSize = 26.sp,
        fontWeight = FontWeight.SemiBold,
        letterSpacing = 7.sp,
    )
    Spacer(Modifier.height(8.dp))
    Text("Your PC, one swipe away.", color = Muted, fontSize = 14.sp)
}

/** Where a brand-new user gets the PC half of DeskGadget. */
private const val SERVER_URL = "https://github.com/issacjohn/deskgadget/releases/latest"
private const val SERVER_LABEL = "github.com/issacjohn/deskgadget/releases"

@Composable
private fun QuickSetupCard() {
    val context = LocalContext.current
    var copied by remember { mutableStateOf(false) }
    var noBrowser by remember { mutableStateOf(false) }

    LaunchedEffect(copied) {
        if (copied) {
            delay(2000)
            copied = false
        }
    }

    fun copyLink() {
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
        clipboard?.setPrimaryClip(ClipData.newPlainText("DeskGadget server", SERVER_URL))
        copied = true
    }

    fun openRelease() {
        val opened = runCatching {
            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(SERVER_URL)))
        }.isSuccess
        if (!opened) {
            // a stripped-down deck phone may have no browser: leave the link
            // on the clipboard so it can be opened on the PC
            noBrowser = true
            copyLink()
        }
    }

    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(Color(0x1A7CE7FF))
            .border(1.dp, Color(0x337CE7FF), RoundedCornerShape(18.dp))
            .padding(horizontal = 16.dp, vertical = 12.dp)
    ) {
        Text(
            "Quick setup",
            color = Ink,
            fontSize = 17.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(8.dp))

        SetupStep(1, "Install the Windows app on your PC.")
        Spacer(Modifier.height(5.dp))
        SetupStep(2, "Download it below, then launch it on the PC.")
        Spacer(Modifier.height(5.dp))
        SetupStep(3, "Open this app - it connects automatically.")
        Spacer(Modifier.height(10.dp))

        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .weight(1f)
                    .height(48.dp)
                    .clip(RoundedCornerShape(13.dp))
                    .background(Brush.linearGradient(listOf(Color(0xFF7CE7FF), Color(0xFFB69CFF))))
                    .clickable(role = Role.Button) { openRelease() },
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    "Download for Windows",
                    color = Color(0xFF06121A),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
            Spacer(Modifier.width(8.dp))
            Box(
                Modifier
                    .height(48.dp)
                    .clip(RoundedCornerShape(13.dp))
                    .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(13.dp))
                    .clickable(role = Role.Button) { copyLink() }
                    .padding(horizontal = 14.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    if (copied) "Copied" else "Copy link",
                    color = Ink.copy(alpha = 0.85f),
                    fontSize = 11.5.sp,
                )
            }
        }

        Spacer(Modifier.height(6.dp))
        Text(
            SERVER_LABEL,
            color = Color(0xFF7CE7FF),
            fontSize = 11.sp,
            textDecoration = TextDecoration.Underline,
            modifier = Modifier.clickable { openRelease() },
        )

        Spacer(Modifier.height(7.dp))
        if (noBrowser) {
            Text(
                "Link copied - open it on your PC.",
                color = Color(0xFFFFC48A),
                fontSize = 10.sp,
            )
        } else {
            Text(
                "Wi-Fi  ·  ADB (USB or wireless)  ·  USB tethering",
                color = Faint,
                fontSize = 10.sp,
            )
        }
    }
}

@Composable
private fun SetupStep(number: Int, text: String) {
    Row {
        Box(
            Modifier
                .size(18.dp)
                .clip(CircleShape)
                .background(Color(0x267CE7FF)),
            contentAlignment = Alignment.Center,
        ) {
            Text("$number", color = Color(0xFF7CE7FF), fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.width(9.dp))
        Text(text, color = Muted, fontSize = 11.sp, lineHeight = 15.sp)
    }
}

@Composable
private fun ConnectCard(
    state: DeckState,
    host: String,
    port: String,
    found: List<ServerChoice>,
    scanning: Boolean,
    onHost: (String) -> Unit,
    onPort: (String) -> Unit,
    onConnect: (String, Int) -> Unit,
    onConnectUsb: () -> Unit,
) {
    val compact = LocalCompactLayout.current
    var manual by remember { mutableStateOf(false) }
    val showForm = found.isEmpty() || manual
    val err = state.error

    GlassPanel(Modifier.fillMaxWidth()) {
        Text("CONNECT", color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
        Spacer(Modifier.height(if (compact) 6.dp else 10.dp))
        Text(
            "Pick your PC on the network",
            color = Ink,
            fontSize = if (compact) 18.sp else 20.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(4.dp))

        if (!showForm) {
            Text(
                err ?: "Tap your PC to connect.",
                color = if (err != null) Color(0xFFFF8CA8) else Muted,
                fontSize = if (compact) 11.5.sp else 12.5.sp,
                lineHeight = if (compact) 15.sp else 18.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(if (compact) 10.dp else 14.dp))

            found.forEach { server ->
                ServerRow(server) {
                    onHost(server.host)
                    onPort(server.port.toString())
                    onConnect(server.host, server.port)
                }
                Spacer(Modifier.height(if (compact) 6.dp else 8.dp))
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Connect via USB",
                    color = Color(0xFF7CE7FF),
                    fontSize = 11.sp,
                    modifier = Modifier
                        .clickable(role = Role.Button, onClick = onConnectUsb)
                        .padding(vertical = 5.dp),
                )
                Spacer(Modifier.weight(1f))
                Text(
                    "Enter address manually",
                    color = Color(0xFF7CE7FF),
                    fontSize = 11.sp,
                    modifier = Modifier
                        .clickable(role = Role.Button) { manual = true }
                        .padding(vertical = 5.dp),
                )
            }
        } else {
            if (found.isEmpty()) {
                Text(
                    "Same Wi-Fi finds it automatically. On a cable, use USB tethering or ADB - "
                        + "the PC appears here too.",
                    color = Muted,
                    fontSize = if (compact) 11.5.sp else 12.5.sp,
                    lineHeight = if (compact) 15.sp else 18.sp,
                )
                Spacer(Modifier.height(if (compact) 8.dp else 14.dp))

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        Modifier
                            .size(8.dp)
                            .clip(CircleShape)
                            .background(
                                when {
                                    err != null -> Color(0xFFFF8CA8)
                                    scanning -> Color(0xFF7CE7FF)
                                    else -> Color(0xFF5E6879)
                                }
                            )
                    )
                    Spacer(Modifier.width(10.dp))
                    Text(
                        when {
                            err != null -> err
                            scanning -> "Looking for DeskGadget on your network…"
                            else -> "No server found — is the Windows app running?"
                        },
                        color = if (err != null) Color(0xFFFF8CA8) else Faint,
                        fontSize = 11.5.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Spacer(Modifier.height(if (compact) 8.dp else 12.dp))
            } else {
                Text(
                    "Enter the address printed on the PC dashboard.",
                    color = Muted,
                    fontSize = if (compact) 11.5.sp else 12.5.sp,
                )
                Spacer(Modifier.height(if (compact) 8.dp else 12.dp))
            }

            Text("PC ADDRESS", color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
            Spacer(Modifier.height(if (compact) 5.dp else 8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(14.dp))
                        .background(Color(0x33000000))
                        .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(14.dp))
                        .padding(horizontal = 14.dp, vertical = if (compact) 10.dp else 13.dp)
                ) {
                    BasicTextField(
                        value = host,
                        onValueChange = onHost,
                        singleLine = true,
                        textStyle = TextStyle(color = Ink, fontSize = 15.sp),
                        cursorBrush = SolidColor(Color(0xFF7CE7FF)),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                        decorationBox = { inner ->
                            if (host.isEmpty()) {
                                Text("192.168.0.10", color = Faint, fontSize = 15.sp)
                            }
                            inner()
                        },
                    )
                }
                Spacer(Modifier.width(8.dp))
                Box(
                    Modifier
                        .width(78.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(Color(0x33000000))
                        .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(14.dp))
                        .padding(horizontal = 12.dp, vertical = if (compact) 10.dp else 13.dp)
                ) {
                    BasicTextField(
                        value = port,
                        onValueChange = { onPort(it.filter(Char::isDigit).take(5)) },
                        singleLine = true,
                        textStyle = TextStyle(color = Ink, fontSize = 15.sp),
                        cursorBrush = SolidColor(Color(0xFF7CE7FF)),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    )
                }
            }

            Spacer(Modifier.height(if (compact) 10.dp else 14.dp))
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(if (compact) 48.dp else 52.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(Brush.linearGradient(listOf(Color(0xFF7CE7FF), Color(0xFFB69CFF))))
                    .clickable(enabled = state.status != ConnStatus.CONNECTING) {
                        onConnect(host, port.toIntOrNull() ?: 8787)
                    },
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    if (state.status == ConnStatus.CONNECTING) "Connecting…" else "Connect",
                    color = Color(0xFF06121A),
                    fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }

            if (found.isEmpty()) {
                Spacer(Modifier.height(if (compact) 7.dp else 10.dp))
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(if (compact) 40.dp else 44.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(14.dp))
                        .clickable(role = Role.Button, onClick = onConnectUsb),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("Connect via USB (127.0.0.1)", color = Ink.copy(alpha = 0.8f), fontSize = 12.5.sp)
                }
            } else {
                Text(
                    "Back to discovered PCs",
                    color = Color(0xFF7CE7FF),
                    fontSize = 11.sp,
                    modifier = Modifier
                        .padding(top = 2.dp)
                        .clickable(role = Role.Button) { manual = false }
                        .padding(vertical = 5.dp),
                )
            }
        }
    }
}

@Composable
private fun ServerRow(server: ServerChoice, onPick: () -> Unit) {
    val compact = LocalCompactLayout.current
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(Color(0x14FFFFFF))
            .clickable(role = Role.Button, onClick = onPick)
            .padding(horizontal = 12.dp, vertical = if (compact) 9.dp else 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(Color(0xFF5BE49B))
        )
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(
                server.name,
                color = Ink,
                fontSize = if (compact) 13.5.sp else 14.sp,
                fontWeight = FontWeight.Medium,
            )
            Text("${server.host}:${server.port}", color = Faint, fontSize = if (compact) 10.sp else 11.sp)
        }
        Text(
            if (server.wired) "USB" else "WI-FI",
            color = if (server.wired) Color(0xFF7CFFB2) else Faint,
            fontSize = 9.sp,
            letterSpacing = 1.sp,
        )
        Spacer(Modifier.width(10.dp))
        Text("Connect", color = Color(0xFF7CE7FF), fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold)
    }
}

/* ============================== deck ============================== */

@Composable
fun DeckScreen(
    state: DeckState,
    onAction: (String, String, JSONObject?) -> Unit,
    onDisconnect: () -> Unit,
    onOpenUrl: (String) -> Unit,
) {
    val pages = state.pages
    // a home grid is only worth a page when there is more than one module
    val hasHome = pages.size >= 2
    val homeOffset = if (hasHome) 1 else 0
    val pager = rememberPagerState(pageCount = { pages.size + homeOffset })
    val scope = rememberCoroutineScope()
    var toastVisible by remember { mutableStateOf(false) }
    var supportOpen by remember { mutableStateOf(false) }
    val context = LocalContext.current
    var betaUpdates by remember { mutableStateOf(Updater.betaEnabled(context)) }
    var update by remember { mutableStateOf<AppUpdate?>(null) }
    var upToDate by remember { mutableStateOf(false) }
    var checking by remember { mutableStateOf(false) }
    var downloading by remember { mutableStateOf(false) }
    var progress by remember { mutableIntStateOf(0) }
    var updateFile by remember { mutableStateOf<File?>(null) }
    var needPermission by remember { mutableStateOf(false) }
    var downloadFailed by remember { mutableStateOf(false) }
    val mainHandler = remember { Handler(Looper.getMainLooper()) }

    fun resetDownload() {
        downloading = false
        progress = 0
        updateFile = null
        needPermission = false
        downloadFailed = false
    }

    // once every three days, quietly look for a newer release
    LaunchedEffect(Unit) {
        if (Updater.shouldAutoCheck(context)) {
            Updater.markChecked(context)
            val found = withContext(Dispatchers.IO) { Updater.check(context) }
            if (found != null) {
                resetDownload()
                update = found
            }
        }
    }

    val checkNow: () -> Unit = {
        if (!checking) {
            checking = true
            scope.launch {
                val found = withContext(Dispatchers.IO) { Updater.check(context) }
                checking = false
                if (found != null) {
                    resetDownload()
                    update = found
                } else {
                    upToDate = true
                }
            }
        }
    }

    LaunchedEffect(state.toastId) {
        if (state.toastId > 0) {
            toastVisible = true
            delay(2200)
            toastVisible = false
        }
    }

    val clock by produceState(initialValue = clockText(), Unit) {
        while (true) {
            value = clockText()
            delay(15_000)
        }
    }

    BoxWithConstraints(Modifier.fillMaxSize().systemBarsPadding()) {
        val compact = maxWidth < 960.dp || maxHeight < 480.dp
        val select: (Int) -> Unit = { index ->
            scope.launch { pager.animateScrollToPage(index) }
        }

        Row(Modifier.fillMaxSize()) {
            ModuleRail(
                pages = pages,
                pager = pager,
                offset = homeOffset,
                hasHome = hasHome,
                compact = compact,
                onSelect = select,
            )
            Column(Modifier.weight(1f).fillMaxHeight()) {
                DeckTopBar(
                    state = state,
                    title = if (hasHome && pager.currentPage == 0) "Home" else {
                        pages.getOrNull(pager.currentPage - homeOffset)?.title.orEmpty()
                    },
                    clock = clock,
                    compact = compact,
                    onDisconnect = onDisconnect,
                    onSupport = { supportOpen = true },
                )

            if (pages.isEmpty()) {
                EmptyState(Modifier.weight(1f))
            } else {
                CompositionLocalProvider(LocalCompactLayout provides compact) {
                    Box(Modifier.weight(1f)) {
                        HorizontalPager(
                            state = pager,
                            modifier = Modifier.fillMaxSize(),
                            pageSpacing = 0.dp,
                            contentPadding = PaddingValues(vertical = 4.dp),
                        ) { index ->
                            if (hasHome && index == 0) {
                                HomePage(pages = pages, onOpen = { moduleIndex -> select(moduleIndex + homeOffset) })
                            } else {
                                PageView(
                                    page = pages[index - homeOffset],
                                    endpoint = state.endpoint,
                                    onAction = onAction,
                                    compact = compact,
                                )
                            }
                        }

                        if (pages.size + homeOffset > 1) {
                            Row(
                                Modifier
                                    .align(Alignment.BottomCenter)
                                    .padding(bottom = 3.dp),
                                horizontalArrangement = Arrangement.spacedBy(5.dp),
                            ) {
                                repeat(pages.size + homeOffset) { i ->
                                    val on = pager.currentPage == i
                                    Box(
                                        Modifier
                                            .size(if (on) 5.dp else 3.5.dp)
                                            .clip(CircleShape)
                                            .background(if (on) Ink.copy(alpha = 0.85f) else Faint.copy(alpha = 0.45f))
                                    )
                                }
                            }
                        }
                    }
                }
            }
            }
        }

        AnimatedVisibility(
            visible = toastVisible && state.toast != null,
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 30.dp),
            enter = fadeIn(),
            exit = fadeOut(),
        ) {
            GlassPill {
                Text(state.toast ?: "", color = Ink, fontSize = 12.sp)
            }
        }

        if (supportOpen) {
            SupportSheet(
                version = Updater.currentVersion(context),
                beta = betaUpdates,
                checking = checking,
                onBeta = { on ->
                    betaUpdates = on
                    Updater.setBetaEnabled(context, on)
                    // switching channels should look for that channel's build now
                    if (on) checkNow()
                },
                onCoffee = {
                    supportOpen = false
                    onOpenUrl(COFFEE_URL)
                },
                onCheckUpdates = {
                    supportOpen = false
                    checkNow()
                },
                onDisconnect = {
                    supportOpen = false
                    onDisconnect()
                },
                onClose = { supportOpen = false },
            )
        }

        update?.let { found ->
            UpdateDialog(
                update = found,
                downloading = downloading,
                progress = progress,
                readyToInstall = updateFile != null,
                needsPermission = needPermission,
                downloadFailed = downloadFailed,
                onDownload = {
                    if (!downloading) {
                        if (found.apkUrl == null) {
                            Updater.open(context, found.pageUrl)
                            update = null
                        } else {
                            downloading = true
                            progress = 0
                            downloadFailed = false
                            needPermission = false
                            scope.launch {
                                val file = withContext(Dispatchers.IO) {
                                    Updater.download(context, found) { p ->
                                        mainHandler.post { progress = p }
                                    }
                                }
                                downloading = false
                                if (file != null) {
                                    updateFile = file
                                    needPermission = !Updater.install(context, file)
                                } else {
                                    downloadFailed = true
                                }
                            }
                        }
                    }
                },
                onInstall = {
                    updateFile?.let { file ->
                        needPermission = !Updater.install(context, file)
                    }
                },
                onSettings = { Updater.openInstallSettings(context) },
                onLater = {
                    Updater.markChecked(context)
                    update = null
                    resetDownload()
                },
            )
        }

        if (upToDate) {
            InfoDialog(
                title = "You're up to date",
                body = "DeskGadget ${Updater.currentVersion(context)} is the latest version.",
                onClose = { upToDate = false },
            )
        }
    }
}

@Composable
private fun UpdateDialog(
    update: AppUpdate,
    downloading: Boolean,
    progress: Int,
    readyToInstall: Boolean,
    needsPermission: Boolean,
    downloadFailed: Boolean,
    onDownload: () -> Unit,
    onInstall: () -> Unit,
    onSettings: () -> Unit,
    onLater: () -> Unit,
) {
    Dialog(onDismissRequest = onLater) {
        Column(
            Modifier
                .width(370.dp)
                .clip(RoundedCornerShape(22.dp))
                .background(Color(0xFB0C1119))
                .border(1.dp, Color(0x26FFFFFF), RoundedCornerShape(22.dp))
                .padding(horizontal = 20.dp, vertical = 18.dp),
        ) {
            Text(
                "UPDATE AVAILABLE",
                color = Color(0xFF7CE7FF),
                fontSize = 9.5.sp,
                letterSpacing = 2.sp,
            )
            Spacer(Modifier.height(7.dp))
            Text(
                "DeskGadget ${update.version}",
                color = Ink,
                fontSize = 19.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(3.dp))
            Text("A newer build is ready on GitHub.", color = Faint, fontSize = 11.5.sp)

            if (update.notes.isNotBlank()) {
                Spacer(Modifier.height(13.dp))
                Text(
                    update.notes,
                    color = Ink.copy(alpha = 0.86f),
                    fontSize = 12.sp,
                    lineHeight = 17.sp,
                    modifier = Modifier
                        .heightIn(max = 142.dp)
                        .verticalScroll(rememberScrollState()),
                )
            }

            if (downloading) {
                Spacer(Modifier.height(14.dp))
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "Downloading",
                        color = Muted,
                        fontSize = 11.sp,
                        modifier = Modifier.weight(1f),
                    )
                    Text("$progress%", color = Ink, fontSize = 11.sp, fontWeight = FontWeight.Medium)
                }
                Spacer(Modifier.height(6.dp))
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(4.dp)
                        .clip(RoundedCornerShape(2.dp))
                        .background(Color(0x22FFFFFF)),
                ) {
                    Box(
                        Modifier
                            .fillMaxWidth((progress.coerceIn(0, 100) / 100f))
                            .fillMaxHeight()
                            .background(Color(0xFF7CE7FF)),
                    )
                }
            }

            if (needsPermission) {
                Spacer(Modifier.height(12.dp))
                Text(
                    "Allow installs from DeskGadget, then tap Install again.",
                    color = Color(0xFFFFC96B),
                    fontSize = 11.sp,
                    lineHeight = 15.sp,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "Open settings",
                    color = Color(0xFF7CE7FF),
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.clickable(onClick = onSettings),
                )
            }

            if (downloadFailed) {
                Spacer(Modifier.height(12.dp))
                Text(
                    "Download failed. Check the connection and try again.",
                    color = Color(0xFFFF8CA8),
                    fontSize = 11.sp,
                    lineHeight = 15.sp,
                )
            }

            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(
                    Modifier
                        .weight(1f)
                        .height(40.dp)
                        .clip(RoundedCornerShape(11.dp))
                        .background(Color(0x14FFFFFF))
                        .clickable(onClick = onLater),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("Later", color = Ink, fontSize = 12.5.sp, fontWeight = FontWeight.Medium)
                }
                Box(
                    Modifier
                        .weight(1f)
                        .height(40.dp)
                        .clip(RoundedCornerShape(11.dp))
                        .background(if (downloading) Color(0x337CE7FF) else Color(0xFF7CE7FF))
                        .then(if (downloading) Modifier else Modifier.clickable(onClick = if (readyToInstall) onInstall else onDownload)),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        when {
                            downloading -> "Downloading…"
                            readyToInstall -> "Install"
                            else -> "Download"
                        },
                        color = if (downloading) Color(0xFF06121A).copy(alpha = 0.65f) else Color(0xFF06121A),
                        fontSize = 12.5.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}

@Composable
private fun InfoDialog(title: String, body: String, onClose: () -> Unit) {
    Dialog(onDismissRequest = onClose) {
        Column(
            Modifier
                .width(320.dp)
                .clip(RoundedCornerShape(20.dp))
                .background(Color(0xFB0C1119))
                .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(20.dp))
                .padding(horizontal = 20.dp, vertical = 18.dp),
        ) {
            Text(title, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(5.dp))
            Text(body, color = Faint, fontSize = 12.sp, lineHeight = 17.sp)
            Spacer(Modifier.height(16.dp))
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(38.dp)
                    .clip(RoundedCornerShape(11.dp))
                    .background(Color(0x14FFFFFF))
                    .clickable(onClick = onClose),
                contentAlignment = Alignment.Center,
            ) {
                Text("OK", color = Ink, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

private const val COFFEE_URL = "https://buymeacoffee.com/issac_john"

/**
 * Deliberately quiet: the header only shows a small heart, and both the
 * support link and disconnect live in here so neither clutters the deck.
 */
@Composable
private fun SupportSheet(
    version: String,
    beta: Boolean,
    checking: Boolean,
    onBeta: (Boolean) -> Unit,
    onCoffee: () -> Unit,
    onCheckUpdates: () -> Unit,
    onDisconnect: () -> Unit,
    onClose: () -> Unit,
) {
    Dialog(onDismissRequest = onClose) {
        Column(
            Modifier
                .width(304.dp)
                .clip(RoundedCornerShape(22.dp))
                .background(Color(0xFB0C1119))
                .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(22.dp))
                .padding(horizontal = 18.dp, vertical = 16.dp),
        ) {
            Box(
                Modifier
                    .align(Alignment.CenterHorizontally)
                    .width(34.dp)
                    .height(3.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(Color(0x33FFFFFF))
            )
            Spacer(Modifier.height(10.dp))
            Text("DeskGadget", color = Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(2.dp))
            Text("Your PC, one swipe away.", color = Faint, fontSize = 11.sp)
            Spacer(Modifier.height(14.dp))

            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .clickable(onClick = onCoffee)
                    .padding(horizontal = 10.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("\u2665", color = Color(0xFFFFD166), fontSize = 13.sp)
                Spacer(Modifier.width(10.dp))
                Text("Buy me a coffee", color = Ink.copy(alpha = 0.9f), fontSize = 13.sp)
                Spacer(Modifier.weight(1f))
                Text("buymeacoffee.com", color = Faint, fontSize = 9.5.sp)
            }

            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .clickable(onClick = onCheckUpdates)
                    .padding(horizontal = 10.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("↻", color = Ink.copy(alpha = 0.9f), fontSize = 14.sp)
                Spacer(Modifier.width(10.dp))
                Text(
                    if (checking) "Checking for updates…" else "Check for updates",
                    color = Ink.copy(alpha = 0.9f),
                    fontSize = 13.sp,
                )
                Spacer(Modifier.weight(1f))
                Text("v$version", color = Faint, fontSize = 9.5.sp)
            }

            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .clickable { onBeta(!beta) }
                    .padding(horizontal = 10.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Beta builds", color = Ink.copy(alpha = 0.9f), fontSize = 13.sp)
                Spacer(Modifier.weight(1f))
                Text(
                    if (beta) "ON" else "OFF",
                    color = if (beta) Color(0xFF7CE7FF) else Faint,
                    fontSize = 9.5.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = 1.sp,
                )
            }
            Text(
                "Pre-release updates, for testing new builds.",
                color = Faint,
                fontSize = 9.5.sp,
                modifier = Modifier.padding(start = 10.dp, bottom = 3.dp),
            )

            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .clickable(onClick = onDisconnect)
                    .padding(horizontal = 10.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Disconnect", color = Color(0xFFFF8CA8), fontSize = 13.sp)
            }

            Spacer(Modifier.height(4.dp))
            Text(
                "Close",
                color = Faint,
                fontSize = 11.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .clickable(onClick = onClose)
                    .padding(vertical = 7.dp),
            )
        }
    }
}

/**
 * Landscape navigation: a slim rail instead of a tab strip. It gives every
 * module a full touch target, keeps the page title off the content and scales
 * from a small phone to a tablet.
 */
@Composable
private fun ModuleRail(
    pages: List<PageData>,
    pager: PagerState,
    offset: Int,
    hasHome: Boolean,
    compact: Boolean,
    onSelect: (Int) -> Unit,
) {
    val palette = LocalPalette.current
    val width = if (compact) 84.dp else 104.dp
    val shape = RoundedCornerShape(if (compact) 20.dp else 24.dp)
    val homeAccent = palette.monoAccent ?: Color(0xFF7CE7FF)
    val activeIndex = pager.currentPage - offset

    Column(
        Modifier
            .padding(
                start = 10.dp,
                top = if (compact) 4.dp else 10.dp,
                bottom = if (compact) 4.dp else 10.dp,
            )
            .width(width)
            .fillMaxHeight()
            .clip(shape)
            .background(Brush.verticalGradient(listOf(palette.glassTop, palette.glassBottom)))
            .border(1.dp, palette.borderMid, shape)
            .padding(horizontal = 6.dp, vertical = if (compact) 4.dp else 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            Icons.Rounded.DesktopWindows,
            contentDescription = null,
            tint = homeAccent.copy(alpha = 0.9f),
            modifier = Modifier.size(if (compact) 17.dp else 19.dp),
        )
        Spacer(Modifier.height(if (compact) 6.dp else 12.dp))
        if (hasHome) {
            RailItem(
                icon = Icons.Rounded.GridView,
                label = "Home",
                active = pager.currentPage == 0,
                compact = compact,
                accent = homeAccent,
                onClick = { onSelect(0) },
            )
            Spacer(Modifier.height(4.dp))
        }
        val listState = rememberLazyListState()
        // Keep the module you swiped to visible, even when the rail scrolls.
        LaunchedEffect(activeIndex) {
            if (pages.isNotEmpty()) {
                listState.animateScrollToItem(activeIndex.coerceIn(0, pages.size - 1))
            }
        }
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(if (compact) 1.dp else 4.dp),
        ) {
            items(count = pages.size) { index ->
                RailItem(
                    icon = iconForModule(pages[index].id),
                    label = pages[index].title,
                    active = activeIndex == index,
                    compact = compact,
                    accent = hexColor(pages[index].accent),
                    onClick = { onSelect(index + offset) },
                )
            }
        }
    }
}

/** Phone landscape: a bottom dock uses the width and keeps every label. */
@Composable
private fun ModuleDock(
    pages: List<PageData>,
    pager: PagerState,
    offset: Int,
    hasHome: Boolean,
    onSelect: (Int) -> Unit,
) {
    val palette = LocalPalette.current
    val shape = RoundedCornerShape(20.dp)
    val activeIndex = if (hasHome && pager.currentPage == 0) -1 else pager.currentPage - offset
    val listState = rememberLazyListState()
    val leading = if (hasHome) 1 else 0

    LaunchedEffect(activeIndex, pages.size) {
        val target = activeIndex + leading
        if (target >= 0 && pages.isNotEmpty()) {
            listState.animateScrollToItem(target.coerceAtMost(pages.size + leading - 1))
        }
    }

    Box(
        Modifier
            .fillMaxWidth()
            .padding(start = 12.dp, end = 12.dp, top = 2.dp, bottom = 8.dp),
    ) {
        LazyRow(
            state = listState,
            modifier = Modifier
                .fillMaxWidth()
                .clip(shape)
                .background(Brush.verticalGradient(listOf(palette.glassTop, palette.glassBottom)))
                .border(1.dp, palette.borderMid, shape)
                .padding(horizontal = 6.dp, vertical = 5.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (hasHome) {
                item {
                    DockItem(
                        icon = Icons.Rounded.GridView,
                        label = "Home",
                        active = activeIndex == -1,
                        accent = palette.monoAccent ?: Color(0xFF7CE7FF),
                        onClick = { onSelect(0) },
                    )
                }
            }
            items(count = pages.size) { index ->
                DockItem(
                    icon = iconForModule(pages[index].id),
                    label = pages[index].title,
                    active = activeIndex == index,
                    accent = hexColor(pages[index].accent),
                    onClick = { onSelect(index + offset) },
                )
            }
        }
    }
}

@Composable
private fun DockItem(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    active: Boolean,
    accent: Color,
    onClick: () -> Unit,
) {
    Column(
        Modifier
            .widthIn(min = 62.dp)
            .heightIn(min = 44.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (active) accent.copy(alpha = 0.14f) else Color.Transparent)
            .clickable(role = Role.Tab, onClick = onClick)
            .padding(horizontal = 6.dp, vertical = 5.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = if (active) accent else Faint,
            modifier = Modifier.size(16.dp),
        )
        Spacer(Modifier.height(2.dp))
        Text(
            label,
            color = if (active) Ink else Muted,
            fontSize = 8.5.sp,
            fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun RailItem(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    active: Boolean,
    compact: Boolean,
    accent: Color,
    onClick: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .heightIn(min = if (compact) 44.dp else 58.dp)
            .clip(RoundedCornerShape(if (compact) 12.dp else 14.dp))
            .background(if (active) accent.copy(alpha = 0.14f) else Color.Transparent)
            .clickable(role = Role.Tab, onClick = onClick)
            .padding(horizontal = 2.dp, vertical = if (compact) 5.dp else 7.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = if (active) accent else Faint,
            modifier = Modifier.size(if (compact) 16.dp else 18.dp),
        )
        Spacer(Modifier.height(3.dp))
        Text(
            label,
            color = if (active) Ink else Ink.copy(alpha = 0.76f),
            fontSize = if (compact) 9.sp else 10.5.sp,
            fontWeight = if (active) FontWeight.SemiBold else FontWeight.Medium,
            letterSpacing = 0.1.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** Slim top bar: status, clock and actions. The rail already names the page. */
@Composable
private fun DeckTopBar(
    state: DeckState,
    title: String,
    clock: String,
    compact: Boolean,
    onDisconnect: () -> Unit,
    onSupport: () -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(
                start = if (compact) 14.dp else 18.dp,
                end = 12.dp,
                top = 4.dp,
                bottom = 2.dp,
            ),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        ConnectionStatus(state)
        if (title.isNotBlank()) {
            Spacer(Modifier.width(12.dp))
            Text(
                title.uppercase(),
                color = Faint,
                fontSize = if (compact) 8.5.sp else 9.5.sp,
                letterSpacing = 1.6.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.widthIn(max = if (compact) 150.dp else 220.dp),
            )
        }
        Spacer(Modifier.weight(1f))
        Text(
            clock,
            color = Muted,
            fontSize = if (compact) 10.sp else 11.sp,
            letterSpacing = 0.8.sp,
        )
        Spacer(Modifier.width(4.dp))
        HeaderIconChip(
            Icons.Rounded.PowerSettingsNew,
            Color(0xFFFFA3B8),
            "Disconnect",
            onDisconnect,
        )
        HeaderChip("\u2665", onClick = onSupport)
    }
}

/** Tab-style module switcher, mirroring the swipe position. */
@Composable
private fun ModuleTabs(
    pages: List<PageData>,
    pager: PagerState,
    offset: Int,
    modifier: Modifier = Modifier,
    onSelect: (Int) -> Unit,
) {
    val spread = pages.size in 3..6
    if (spread) {
        Row(modifier = modifier, verticalAlignment = Alignment.Bottom) {
            pages.forEachIndexed { index, page ->
                TabItem(
                    page = page,
                    active = pager.currentPage - offset == index,
                    modifier = Modifier.weight(1f),
                    onClick = { onSelect(index + offset) },
                )
            }
        }
    } else {
        val listState = rememberLazyListState()
        val activeIndex = (pager.currentPage - offset).coerceIn(0, (pages.size - 1).coerceAtLeast(0))
        // keep the current module's tab in view when the deck is swiped
        LaunchedEffect(activeIndex) {
            listState.animateScrollToItem(activeIndex)
        }
        LazyRow(
            state = listState,
            modifier = modifier,
            verticalAlignment = Alignment.Bottom,
        ) {
            items(count = pages.size) { index ->
                TabItem(
                    page = pages[index],
                    active = activeIndex == index,
                    modifier = Modifier.widthIn(min = 108.dp),
                    underlineWidth = 44.dp,
                    onClick = { onSelect(index + offset) },
                )
            }
        }
    }
}

/** The "home" tab that returns to the tile grid. */
@Composable
private fun HomeTab(active: Boolean, onClick: () -> Unit) {
    Column(
        Modifier
            .clip(RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 2.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            imageVector = Icons.Rounded.GridView,
            contentDescription = "Home",
            tint = if (active) Ink else Faint,
            modifier = Modifier.size(13.dp),
        )
        Spacer(Modifier.height(2.dp))
        Box(
            Modifier
                .width(18.dp)
                .height(1.5.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(if (active) LocalPalette.current.monoAccent ?: Ink else Color.Transparent)
        )
    }
}

/** Module tiles with their live value — sized to fit the panel, no scrolling. */
@Composable
private fun HomePage(pages: List<PageData>, onOpen: (Int) -> Unit) {
    val compact = LocalCompactLayout.current
    Column(
        Modifier
            .fillMaxSize()
            .padding(
                start = if (compact) 18.dp else 24.dp,
                end = if (compact) 18.dp else 24.dp,
                top = if (compact) 4.dp else 8.dp,
                bottom = if (compact) 10.dp else 16.dp,
            ),
    ) {
        Text(
            "YOUR DESK, AT A GLANCE",
            color = Faint,
            fontSize = if (compact) 8.5.sp else 9.5.sp,
            letterSpacing = 2.2.sp,
        )
        Spacer(Modifier.height(if (compact) 2.dp else 4.dp))
        Text(
            "Everything in reach.",
            color = Ink,
            fontSize = if (compact) 19.sp else 26.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = (-0.4).sp,
        )
        Spacer(Modifier.height(if (compact) 10.dp else 14.dp))

        // Work the grid out from the space actually available. Tiles keep a
        // sane height instead of stretching: with one or two modules the grid
        // would otherwise become two full-height slabs.
        BoxWithConstraints(Modifier.fillMaxSize()) {
            val roomy = maxWidth >= 900.dp
            val count = pages.size.coerceAtLeast(1)
            // Up to four modules sit in one calm row. From five upwards the
            // grid uses two rows, which keeps the tiles from becoming slabs.
            val maxColumns = if (roomy) 6 else 4
            val columns = if (count <= 4) {
                count
            } else {
                ((count + 1) / 2).coerceIn(3, maxColumns)
            }
            val rows = ((count + columns - 1) / columns).coerceAtLeast(1)
            val gap = if (rows > 2) 7.dp else if (roomy) 12.dp else 9.dp
            val compactTile = !roomy || rows > 2

            val naturalRowHeight = (maxHeight - gap * (rows - 1)) / rows
            val rowHeight = minOf(
                naturalRowHeight,
                when {
                    rows > 1 -> if (roomy) 300.dp else 260.dp
                    count == 1 -> if (roomy) 240.dp else 220.dp
                    else -> if (roomy) 230.dp else 200.dp
                },
            )
            val rawTileWidth = (maxWidth - gap * (columns - 1)) / columns
            val tileWidth = when (count) {
                1 -> minOf(rawTileWidth, if (roomy) 560.dp else 520.dp)
                2 -> minOf(rawTileWidth, if (roomy) 420.dp else 380.dp)
                3 -> minOf(rawTileWidth, if (roomy) 380.dp else 340.dp)
                else -> rawTileWidth
            }

            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center) {
                repeat(rows) { row ->
                    val start = row * columns
                    val end = minOf(count, start + columns)
                    if (row > 0) Spacer(Modifier.height(gap))
                    Row(
                        Modifier.fillMaxWidth().height(rowHeight),
                        horizontalArrangement = Arrangement.spacedBy(gap, Alignment.CenterHorizontally),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        for (index in start until end) {
                            ModuleTile(
                                page = pages[index],
                                compact = compactTile,
                                modifier = Modifier.width(tileWidth).fillMaxHeight(),
                                onClick = { onOpen(index) },
                            )
                        }
                    }
                }
                if (count <= 2) {
                    Spacer(Modifier.height(14.dp))
                    Text(
                        "Add more modules in the dashboard on your PC.",
                        color = Faint,
                        fontSize = 11.sp,
                    )
                }
            }
        }
    }
}

@Composable
private fun ModuleTile(
    page: PageData,
    compact: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val accent = hexColor(page.accent)
    val shape = RoundedCornerShape(if (compact) 16.dp else 22.dp)
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val flash = rememberTapFlash(pressed)
    Column(
        modifier
            .clip(shape)
            .background(
                Brush.verticalGradient(
                    if (flash) {
                        listOf(accent.copy(alpha = 0.38f), accent.copy(alpha = 0.16f))
                    } else {
                        listOf(accent.copy(alpha = 0.18f), Color(0x08FFFFFF))
                    }
                )
            )
            .border(1.dp, Color(0x22FFFFFF), shape)
            .clickable(interactionSource = interaction, indication = null, onClick = onClick)
            .padding(
                horizontal = if (compact) 11.dp else 15.dp,
                vertical = if (compact) 9.dp else 14.dp,
            ),
    ) {
        Icon(
            imageVector = iconForModule(page.id),
            contentDescription = null,
            tint = accent,
            modifier = Modifier.size(if (compact) 14.dp else 19.dp),
        )
        Spacer(Modifier.weight(1f))
        Text(
            page.title,
            color = Ink,
            fontSize = if (compact) 11.5.sp else 14.5.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(if (compact) 2.dp else 4.dp))
        Text(
            moduleSummary(page),
            color = Muted,
            fontSize = if (compact) 9.5.sp else 11.5.sp,
            lineHeight = if (compact) 12.sp else 14.sp,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** The most useful single value on the page, for the tile subtitle. */
private fun moduleSummary(page: PageData): String {
    fun first(type: String): JSONObject? =
        page.blocks.firstOrNull { it.optString("type") == type }

    first("nowplaying")?.let { b ->
        val artist = b.optString("artist")
        val title = b.optString("title")
        return if (artist.isNotBlank()) "$title · $artist" else title
    }
    first("hero")?.let { b ->
        val value = b.optString("value")
        if (value.isNotBlank()) return value + b.optString("unit")
    }
    first("gauges")?.let { b ->
        val items = b.optJSONArray("items")
        if (items != null && items.length() > 0) {
            val g = items.getJSONObject(0)
            return "${g.optString("label")} ${g.optInt("value")}${g.optString("suffix")}".trim()
        }
    }
    first("nowplaying")?.let { b ->
        val artist = b.optString("artist")
        val title = b.optString("title")
        return if (artist.isNotBlank()) "$title · $artist" else title
    }
    first("slider")?.let { b -> return "${b.optInt("value")}%" }
    first("news")?.let { b ->
        val items = b.optJSONArray("items")
        if (items != null && items.length() > 0) {
            return items.getJSONObject(0).optString("title")
        }
    }
    first("shortcuts")?.let { b ->
        val n = b.optJSONArray("items")?.length() ?: 0
        return if (n == 1) "1 shortcut" else "$n shortcuts"
    }
    first("toggles")?.let { b ->
        val n = b.optJSONArray("items")?.length() ?: 0
        return if (n == 1) "1 switch" else "$n switches"
    }
    first("meters")?.let { b ->
        val items = b.optJSONArray("items")
        if (items != null && items.length() > 0) {
            val m = items.getJSONObject(0)
            return "${m.optString("label")} ${Math.round(m.optDouble("value", 0.0))}%"
        }
    }
    first("kv")?.let { b ->
        val items = b.optJSONArray("items")
        if (items != null && items.length() > 0) {
            val kv = items.getJSONObject(0)
            return "${kv.optString("label")} ${kv.optString("value")}".trim()
        }
    }
    first("list")?.let { b ->
        val n = b.optJSONArray("items")?.length() ?: 0
        return if (n == 1) "1 item" else "$n items"
    }
    first("controls")?.let { return "Tap to control" }
    return "Tap to open"
}

@Composable
private fun TabItem(
    page: PageData,
    active: Boolean,
    modifier: Modifier = Modifier,
    underlineWidth: androidx.compose.ui.unit.Dp? = null,
    onClick: () -> Unit,
) {
    val accent = LocalPalette.current.monoAccent ?: hexColor(page.accent)
    Column(
        modifier
            .clip(RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 1.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                imageVector = iconForModule(page.id),
                contentDescription = null,
                tint = if (active) Ink else Faint,
                modifier = Modifier.size(11.dp),
            )
            Spacer(Modifier.width(4.dp))
            Text(
                page.title,
                color = if (active) Ink else Muted,
                fontSize = 8.5.sp,
                letterSpacing = 0.2.sp,
                maxLines = 1,
            )
        }
        Spacer(Modifier.height(1.dp))
        Box(
            Modifier
                .then(
                    if (underlineWidth != null) Modifier.width(underlineWidth)
                    else Modifier.fillMaxWidth()
                )
                .height(1.5.dp)
                .clip(RoundedCornerShape(50))
                .background(if (active) accent else Color.Transparent)
        )
    }
}

@Composable
private fun HeaderChip(label: String, onClick: () -> Unit) {
    val shape = RoundedCornerShape(50)
    Box(
        Modifier
            .height(44.dp)
            .clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier
                .clip(shape)
                .background(Color(0x14FFFFFF))
                .border(1.dp, Color(0x1FFFFFFF), shape)
                .padding(horizontal = 10.dp, vertical = 4.dp)
        ) {
            Text(label, color = Muted, fontSize = 10.sp)
        }
    }
}

/** A round header action that matches the heart chip, with a full touch target. */
@Composable
private fun HeaderIconChip(
    icon: ImageVector,
    tint: Color,
    description: String,
    onClick: () -> Unit,
) {
    Box(
        Modifier
            .size(44.dp)
            .clip(CircleShape)
            .clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier
                .size(30.dp)
                .clip(CircleShape)
                .background(Color(0x14FFFFFF))
                .border(1.dp, Color(0x1FFFFFFF), CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                icon,
                contentDescription = description,
                tint = tint,
                modifier = Modifier.size(15.dp),
            )
        }
    }
}

@Composable
private fun ConnectionStatus(state: DeckState) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(
                    when (state.status) {
                        ConnStatus.CONNECTED -> Color(0xFF5BE49B)
                        ConnStatus.RECONNECTING -> Color(0xFFFFC96B)
                        else -> Color(0xFFFF8CA8)
                    }
                )
        )
        Spacer(Modifier.width(6.dp))
        Text(
            when (state.status) {
                ConnStatus.CONNECTED -> state.serverName
                ConnStatus.RECONNECTING -> "Reconnecting…"
                else -> "Offline"
            },
            color = Ink.copy(alpha = 0.82f),
            fontSize = 10.sp,
            maxLines = 1,
        )
    }
}

private fun iconForModule(id: String): ImageVector = when (id) {
    "system" -> Icons.Rounded.Speed
    "weather" -> Icons.Rounded.WbSunny
    "media" -> Icons.Rounded.MusicNote
    "shortcuts" -> Icons.Rounded.GridView
    "camera" -> Icons.Rounded.PhotoCamera
    "audiomesh" -> Icons.Rounded.GraphicEq
    "news" -> Icons.Rounded.Newspaper
    "windows" -> Icons.Rounded.Window
    "clipboard" -> Icons.Rounded.ContentPaste
    "wol" -> Icons.Rounded.PowerSettingsNew
    "drives" -> Icons.Rounded.Storage
    "timer" -> Icons.Rounded.Timer
    "touchpad" -> Icons.Rounded.TouchApp
    else -> Icons.Rounded.Widgets
}

@Composable
private fun StatusPill(state: DeckState) {
    GlassPill {
        Box(
            Modifier
                .size(7.dp)
                .clip(CircleShape)
                .background(
                    when (state.status) {
                        ConnStatus.CONNECTED -> Color(0xFF5BE49B)
                        ConnStatus.RECONNECTING -> Color(0xFFFFC96B)
                        else -> Color(0xFFFF8CA8)
                    }
                )
        )
        Spacer(Modifier.width(8.dp))
        Text(
            when (state.status) {
                ConnStatus.CONNECTED -> state.serverName
                ConnStatus.RECONNECTING -> "Reconnecting…"
                else -> "Offline"
            },
            color = Ink.copy(alpha = 0.85f),
            fontSize = 11.5.sp,
            maxLines = 1,
        )
    }
}

@Composable
private fun EmptyState(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("No modules yet", color = Ink, fontSize = 17.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(6.dp))
            Text(
                "Tick modules for this phone in the Windows dashboard.",
                color = Muted,
                fontSize = 12.5.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 40.dp),
            )
        }
    }
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
private fun PageView(
    page: PageData,
    endpoint: String,
    onAction: (String, String, JSONObject?) -> Unit,
    compact: Boolean,
) {
    if (!page.refreshable) {
        AdaptiveBody(page, endpoint, onAction, compact)
        return
    }

    var refreshing by remember(page.id) { mutableStateOf(false) }
    // a new page payload (or a timeout) ends the spinner
    LaunchedEffect(page.blocks) { refreshing = false }
    LaunchedEffect(refreshing) {
        if (refreshing) {
            delay(6000)
            refreshing = false
        }
    }

    androidx.compose.material3.pulltorefresh.PullToRefreshBox(
        isRefreshing = refreshing,
        onRefresh = {
            refreshing = true
            onAction(page.id, "refresh", null)
        },
        modifier = Modifier.fillMaxSize(),
    ) {
        AdaptiveBody(page, endpoint, onAction, compact)
    }
}

/**
 * Phones keep their current sizing; tablets and other big panels get larger
 * type (up to 1.4x) so labels stay legible from across a desk.
 */
@Composable
private fun AdaptiveBody(
    page: PageData,
    endpoint: String,
    onAction: (String, String, JSONObject?) -> Unit,
    compact: Boolean,
) {
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val base = LocalDensity.current
        val boost = (maxWidth.value / 900f).coerceIn(1f, 1.4f)
        CompositionLocalProvider(
            LocalDensity provides Density(base.density, base.fontScale * boost)
        ) {
            PageBody(page, endpoint, onAction, compact)
        }
    }
}

@Composable
private fun PageBody(
    page: PageData,
    endpoint: String,
    onAction: (String, String, JSONObject?) -> Unit,
    compact: Boolean,
) {
    val accent = LocalPalette.current.monoAccent ?: hexColor(page.accent)
    val blocks = page.blocks

    // A page with a single block (the launcher, or a one-widget plugin) stretches
    // to fill the whole viewport instead of leaving dead space underneath.
    if (blocks.size == 1 && blocks[0].optString("type") == "touchpad") {
        // A trackpad has to own the whole panel, including the height, so it is
        // laid out without the scrolling wrapper used by content pages.
        BlockView(
            block = blocks[0],
            module = page.id,
            accent = accent,
            endpoint = endpoint,
            onAction = { action, payload -> onAction(page.id, action, payload) },
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = if (compact) 6.dp else 20.dp)
                .padding(top = if (compact) 2.dp else 8.dp, bottom = 8.dp),
        )
        return
    }

    if (blocks.size == 1 && blocks[0].optString("type") == "camera") {
        BlockView(
            block = blocks[0],
            module = page.id,
            accent = accent,
            endpoint = endpoint,
            onAction = { action, payload -> onAction(page.id, action, payload) },
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = if (compact) 6.dp else 20.dp)
                .padding(top = if (compact) 2.dp else 8.dp, bottom = 8.dp),
        )
        return
    }

    if (blocks.size <= 1) {
        val scroll = rememberScrollState()
        BoxWithConstraints(Modifier.fillMaxSize()) {
            Column(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = maxHeight)
                    .verticalScroll(scroll)
                    .padding(horizontal = if (compact) 6.dp else 20.dp)
                    .padding(top = if (compact) 2.dp else 8.dp, bottom = 8.dp),
                verticalArrangement = Arrangement.Center,
            ) {
                blocks.forEach { block ->
                    BlockView(
                        block = block,
                        module = page.id,
                        accent = accent,
                        endpoint = endpoint,
                        onAction = { action, payload -> onAction(page.id, action, payload) },
                    )
                }
            }
            if (scroll.canScrollForward) {
                Box(
                    Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .height(28.dp)
                        .background(
                            Brush.verticalGradient(listOf(Color.Transparent, Color(0xE604060A)))
                        )
                )
            }
        }
        return
    }

    // Only the System page is dense enough to need scaling; every other page
    // keeps its natural size and scrolls if it has to.
    if (page.id == "system") {
        AutoFit(Modifier.fillMaxSize()) {
            BlocksColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = if (compact) 6.dp else 20.dp)
                    .padding(top = if (compact) 2.dp else 8.dp, bottom = 8.dp),
                blocks = blocks,
                module = page.id,
                accent = accent,
                endpoint = endpoint,
                compact = compact,
                onAction = onAction,
            )
        }
        return
    }

    val scroll = rememberScrollState()
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val viewport = maxHeight
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(scroll)
                .padding(horizontal = if (compact) 6.dp else 20.dp)
                .padding(top = if (compact) 2.dp else 8.dp, bottom = 8.dp),
        ) {
            // short pages sit in the middle of the panel instead of clinging to
            // the top; tall ones still scroll normally
            Column(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = (viewport - 12.dp).coerceAtLeast(0.dp)),
                verticalArrangement = Arrangement.Center,
            ) {
                BlocksColumn(
                    modifier = Modifier.fillMaxWidth(),
                    blocks = blocks,
                    module = page.id,
                    accent = accent,
                    endpoint = endpoint,
                    compact = compact,
                    onAction = onAction,
                )
            }
        }
        if (scroll.canScrollForward) {
            Box(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .height(28.dp)
                    .background(
                        Brush.verticalGradient(
                            listOf(Color.Transparent, Color(0xE604060A))
                        )
                    )
            )
        }
    }
}

@Composable
private fun BlocksColumn(
    modifier: Modifier,
    blocks: List<JSONObject>,
    module: String,
    accent: Color,
    endpoint: String,
    compact: Boolean,
    onAction: (String, String, JSONObject?) -> Unit,
) {
    BoxWithConstraints(modifier) {
    val threeUp = compact && maxWidth >= 700.dp && blocks.size >= 6
    Column(Modifier.fillMaxWidth()) {
        if (compact && blocks.any { it.has("col") }) {
            val columns = blocks.groupBy { it.optInt("col", 0) }.toSortedMap().values.toList()
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                columns.forEach { col ->
                    Column(Modifier.weight(1f)) {
                        col.forEach { block ->
                            BlockView(
                                block = block,
                                module = module,
                                accent = accent,
                                endpoint = endpoint,
                                onAction = { action, payload -> onAction(module, action, payload) },
                            )
                            Spacer(Modifier.height(12.dp))
                        }
                    }
                }
            }
        } else if (threeUp) {
            val columns = balanceColumns(blocks, 3)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                columns.forEach { col ->
                    Column(Modifier.weight(1f)) {
                        col.forEach { block ->
                            BlockView(
                                block = block,
                                module = module,
                                accent = accent,
                                endpoint = endpoint,
                                onAction = { action, payload -> onAction(module, action, payload) },
                            )
                            Spacer(Modifier.height(12.dp))
                        }
                    }
                }
            }
        } else if (compact) {
            val (left, right) = balanceBlocks(blocks)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Column(Modifier.weight(1f)) {
                    left.forEach { block ->
                        BlockView(
                            block = block,
                            module = module,
                            accent = accent,
                            endpoint = endpoint,
                            onAction = { action, payload -> onAction(module, action, payload) },
                        )
                        Spacer(Modifier.height(12.dp))
                    }
                }
                Column(Modifier.weight(1f)) {
                    right.forEach { block ->
                        BlockView(
                            block = block,
                            module = module,
                            accent = accent,
                            endpoint = endpoint,
                            onAction = { action, payload -> onAction(module, action, payload) },
                        )
                        Spacer(Modifier.height(12.dp))
                    }
                }
            }
        } else {
            blocks.forEach { block ->
                BlockView(
                    block = block,
                    module = module,
                    accent = accent,
                    endpoint = endpoint,
                    onAction = { action, payload -> onAction(module, action, payload) },
                )
                Spacer(Modifier.height(13.dp))
            }
        }
    }
    }
}

/**
 * Splits blocks into [count] stacks, greedily handing each block to the shortest
 * stack so the columns end up level. Order is preserved within a column.
 */
private fun balanceColumns(blocks: List<JSONObject>, count: Int): List<List<JSONObject>> {
    val columns = MutableList(count) { mutableListOf<JSONObject>() }
    val heights = FloatArray(count)
    for (block in blocks) {
        val target = heights.indices.minBy { heights[it] }
        columns[target].add(block)
        heights[target] += estimateHeight(block)
    }
    return columns
}

/**
 * Scales its content down until it fits the available height. Pages are built
 * from cards of very different sizes, so measuring once and scaling beats
 * making the user scroll a desk panel.
 */
@Composable
private fun AutoFit(
    modifier: Modifier = Modifier,
    minScale: Float = 0.55f,
    content: @Composable () -> Unit,
) {
    SubcomposeLayout(modifier) { constraints ->
        val width = constraints.maxWidth
        val height = constraints.maxHeight
        val placeable = subcompose(0, content).first().measure(
            Constraints(
                minWidth = width,
                maxWidth = width,
                minHeight = 0,
                maxHeight = Constraints.Infinity,
            )
        )
        val scale = if (placeable.height > 0) {
            (height.toFloat() / placeable.height).coerceIn(minScale, 1f)
        } else {
            1f
        }
        layout(width, height) {
            val x = ((width - placeable.width * scale) / 2f).toInt().coerceAtLeast(0)
            placeable.placeWithLayer(x, 0) {
                scaleX = scale
                scaleY = scale
                transformOrigin = TransformOrigin(0f, 0f)
            }
        }
    }
}

/**
 * Splits cards into two columns at the point where the two stacks end up closest
 * in height, so one side doesn't end halfway up the screen while the other runs
 * off the bottom. Order is preserved: top-to-bottom on the left, then the right.
 */
private fun balanceBlocks(blocks: List<JSONObject>): Pair<List<JSONObject>, List<JSONObject>> {
    if (blocks.size <= 1) return blocks to emptyList()
    val heights = blocks.map { estimateHeight(it) }
    val total = heights.sum()
    var bestSplit = 1
    var bestDelta = Float.MAX_VALUE
    var running = 0f
    for (i in 1 until blocks.size) {
        running += heights[i - 1]
        val delta = kotlin.math.abs(total - 2 * running)
        if (delta < bestDelta) {
            bestDelta = delta
            bestSplit = i
        }
    }
    return blocks.take(bestSplit) to blocks.drop(bestSplit)
}

/** Rough card heights in dp, used only for column balancing. */
private fun estimateHeight(block: JSONObject): Float {
    val items = block.optJSONArray("items")?.length() ?: 0
    return when (block.optString("type")) {
        "hero" -> 178f
        "gauges" -> 132f
        "sparkline" -> 128f
        "meters" -> 44f + 68f * items
        "kv" -> 82f
        "list" -> 62f + 44f * items
        "controls" -> 126f
        "slider" -> 96f
        "shortcuts" -> 210f
        else -> 150f
    }
}

private fun clockText(): String =
    SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())

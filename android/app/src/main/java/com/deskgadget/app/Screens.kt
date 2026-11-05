package com.deskgadget.app

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.GridView
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.WbSunny
import androidx.compose.material.icons.rounded.Widgets
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.layout.SubcomposeLayout
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
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
                    Spacer(Modifier.height(26.dp))
                    TipText()
                }
                Box(Modifier.weight(1.15f).fillMaxHeight()) {
                    Column(
                        Modifier
                            .fillMaxSize()
                            .verticalScroll(rememberScrollState()),
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
                        )
                        Spacer(Modifier.height(6.dp))
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
                )
                Spacer(Modifier.height(22.dp))
                TipText()
                Spacer(Modifier.height(28.dp))
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

@Composable
private fun TipText() {
    Text(
        "Tip: USB debugging on? The Windows app forwards the port, so 127.0.0.1 works. "
            + "No debugging? USB tethering is enough - no adb, no developer options.",
        color = Faint,
        fontSize = 11.5.sp,
        lineHeight = 17.sp,
    )
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
) {
    GlassPanel(Modifier.fillMaxWidth()) {
        Text("CONNECT", color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
        Spacer(Modifier.height(10.dp))
        Text(
            "Pick your PC on the network",
            color = Ink,
            fontSize = 20.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "Start the DeskGadget server on Windows. Same Wi-Fi finds it automatically. "
                + "For a cable, turn on USB tethering - no USB debugging needed - and the PC "
                + "appears here over USB too.",
            color = Muted,
            fontSize = 12.5.sp,
            lineHeight = 18.sp,
        )
        Spacer(Modifier.height(16.dp))

        if (found.isNotEmpty()) {
            found.forEach { server ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(16.dp))
                        .background(Color(0x14FFFFFF))
                        .clickable {
                            onHost(server.host)
                            onPort(server.port.toString())
                            onConnect(server.host, server.port)
                        }
                        .padding(horizontal = 14.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        Modifier
                            .size(9.dp)
                            .clip(CircleShape)
                            .background(Color(0xFF5BE49B))
                    )
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(server.name, color = Ink, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                        Text("${server.host}:${server.port}", color = Faint, fontSize = 11.sp)
                    }
                    Text(
                        if (server.wired) "USB" else "WI-FI",
                        color = if (server.wired) Color(0xFF7CFFB2) else Faint,
                        fontSize = 9.sp,
                        letterSpacing = 1.sp,
                    )
                    Spacer(Modifier.width(10.dp))
                    Text("Connect", color = Color(0xFF7CE7FF), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                }
                Spacer(Modifier.height(8.dp))
            }
            Spacer(Modifier.height(4.dp))
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(if (scanning) Color(0xFF7CE7FF) else Color(0xFF5E6879))
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    if (scanning) "Looking for DeskGadget on your network…"
                    else "No server found automatically — enter the address below.",
                    color = Faint,
                    fontSize = 12.sp,
                )
            }
            Spacer(Modifier.height(12.dp))
        }

        Text("PC ADDRESS", color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(14.dp))
                    .background(Color(0x33000000))
                    .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(14.dp))
                    .padding(horizontal = 14.dp, vertical = 13.dp)
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
                    .padding(horizontal = 12.dp, vertical = 13.dp)
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

        Spacer(Modifier.height(14.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .height(52.dp)
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

        Spacer(Modifier.height(10.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .height(44.dp)
                .clip(RoundedCornerShape(14.dp))
                .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(14.dp))
                .clickable { onConnect("127.0.0.1", 8787) },
            contentAlignment = Alignment.Center,
        ) {
            Text("Use USB (127.0.0.1)", color = Ink.copy(alpha = 0.8f), fontSize = 12.5.sp)
        }

        val err = state.error
        if (err != null) {
            Spacer(Modifier.height(12.dp))
            Text(err, color = Color(0xFFFF8CA8), fontSize = 12.sp, lineHeight = 17.sp)
        }
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
        val wide = maxWidth > maxHeight
        val select: (Int) -> Unit = { index ->
            scope.launch { pager.animateScrollToPage(index) }
        }

        Column(Modifier.fillMaxSize()) {
            if (wide) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(start = 16.dp, end = 14.dp, top = 3.dp, bottom = 0.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    ConnectionStatus(state)
                    Spacer(Modifier.width(12.dp))
                    if (hasHome) {
                        HomeTab(active = pager.currentPage == 0, onClick = { select(0) })
                        Spacer(Modifier.width(4.dp))
                    }
                    ModuleTabs(pages, pager, homeOffset, Modifier.weight(1f), select)
                    Spacer(Modifier.width(10.dp))
                    if (hasHome && pager.currentPage > 0) {
                        pages.getOrNull(pager.currentPage - 1)?.let { active ->
                            Text(
                                active.title.uppercase(),
                                color = Muted,
                                fontSize = 9.sp,
                                letterSpacing = 1.2.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.widthIn(max = 130.dp),
                            )
                            Spacer(Modifier.width(8.dp))
                        }
                    }
                    Text(clock, color = Muted, fontSize = 10.sp, letterSpacing = 0.8.sp)
                    Spacer(Modifier.width(8.dp))
                    HeaderChip("\u2665", onClick = { supportOpen = true })
                }
            } else {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .padding(start = 16.dp, end = 16.dp, top = 6.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        ConnectionStatus(state)
                        Spacer(Modifier.weight(1f))
                        Text(clock, color = Muted, fontSize = 10.sp, letterSpacing = 0.8.sp)
                        Spacer(Modifier.width(8.dp))
                        HeaderChip("\u2665", onClick = { supportOpen = true })
                    }
                    Spacer(Modifier.height(3.dp))
                    ModuleTabs(pages, pager, homeOffset, Modifier.fillMaxWidth(), select)
                }
            }

            if (pages.isEmpty()) {
                EmptyState(Modifier.weight(1f))
            } else {
                CompositionLocalProvider(LocalCompactLayout provides wide) {
                    Box(Modifier.weight(1f)) {
                        HorizontalPager(
                            state = pager,
                            modifier = Modifier.fillMaxSize(),
                            pageSpacing = 0.dp,
                            contentPadding = if (wide) {
                                PaddingValues(vertical = 4.dp)
                            } else {
                                PaddingValues(vertical = 4.dp)
                            },
                        ) { index ->
                            if (hasHome && index == 0) {
                                HomePage(pages = pages, onOpen = { moduleIndex -> select(moduleIndex + homeOffset) })
                            } else {
                                PageView(
                                    page = pages[index - homeOffset],
                                    endpoint = state.endpoint,
                                    onAction = onAction,
                                    compact = wide,
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
                onCoffee = {
                    supportOpen = false
                    onOpenUrl(COFFEE_URL)
                },
                onDisconnect = {
                    supportOpen = false
                    onDisconnect()
                },
                onClose = { supportOpen = false },
            )
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
    onCoffee: () -> Unit,
    onDisconnect: () -> Unit,
    onClose: () -> Unit,
) {
    Dialog(onDismissRequest = onClose) {
        Column(
            Modifier
                .width(304.dp)
                .clip(RoundedCornerShape(22.dp))
                .background(Color(0xF00C1119))
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
    Column(
        Modifier
            .fillMaxSize()
            .padding(start = 18.dp, end = 18.dp, top = 4.dp, bottom = 10.dp),
    ) {
        Text(
            "YOUR DESK, AT A GLANCE",
            color = Faint,
            fontSize = 8.5.sp,
            letterSpacing = 2.sp,
        )
        Spacer(Modifier.height(2.dp))
        Text(
            "Everything in reach.",
            color = Ink,
            fontSize = 19.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(10.dp))

        // Work the grid out from the space actually available: every module
        // gets a tile, and the tiles share the height instead of scrolling.
        BoxWithConstraints(Modifier.fillMaxSize()) {
            val count = pages.size.coerceAtLeast(1)
            val columns = ((maxWidth / 122.dp).toFloat() + 0.5f).toInt()
                .coerceIn(2, 6)
                .coerceAtMost(count)
            val rows = ((count + columns - 1) / columns).coerceAtLeast(1)
            val gap = if (rows > 2) 7.dp else 9.dp
            val compact = rows > 2

            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(gap)) {
                repeat(rows) { row ->
                    Row(
                        Modifier.weight(1f),
                        horizontalArrangement = Arrangement.spacedBy(gap),
                    ) {
                        repeat(columns) { column ->
                            val index = row * columns + column
                            if (index < count) {
                                ModuleTile(
                                    page = pages[index],
                                    compact = compact,
                                    modifier = Modifier.weight(1f).fillMaxHeight(),
                                    onClick = { onOpen(index) },
                                )
                            } else {
                                Spacer(Modifier.weight(1f))
                            }
                        }
                    }
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
    val shape = RoundedCornerShape(if (compact) 16.dp else 20.dp)
    Column(
        modifier
            .clip(shape)
            .background(
                Brush.verticalGradient(
                    listOf(accent.copy(alpha = 0.18f), Color(0x08FFFFFF))
                )
            )
            .border(1.dp, Color(0x22FFFFFF), shape)
            .clickable(onClick = onClick)
            .padding(
                horizontal = if (compact) 11.dp else 13.dp,
                vertical = if (compact) 9.dp else 12.dp,
            ),
    ) {
        Icon(
            imageVector = iconForModule(page.id),
            contentDescription = null,
            tint = accent,
            modifier = Modifier.size(if (compact) 14.dp else 17.dp),
        )
        Spacer(Modifier.weight(1f))
        Text(
            page.title,
            color = Ink,
            fontSize = if (compact) 11.5.sp else 13.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(2.dp))
        Text(
            moduleSummary(page),
            color = Muted,
            fontSize = if (compact) 9.5.sp else 10.5.sp,
            lineHeight = if (compact) 12.sp else 13.sp,
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
            .clip(shape)
            .background(Color(0x14FFFFFF))
            .border(1.dp, Color(0x1FFFFFFF), shape)
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 3.dp)
    ) {
        Text(label, color = Muted, fontSize = 9.5.sp)
    }
}

@Composable
private fun ConnectionStatus(state: DeckState) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(5.dp)
                .clip(CircleShape)
                .background(
                    when (state.status) {
                        ConnStatus.CONNECTED -> Color(0xFF5BE49B)
                        ConnStatus.RECONNECTING -> Color(0xFFFFC96B)
                        else -> Color(0xFFFF8CA8)
                    }
                )
        )
        Spacer(Modifier.width(5.dp))
        Text(
            when (state.status) {
                ConnStatus.CONNECTED -> state.serverName
                ConnStatus.RECONNECTING -> "Reconnecting…"
                else -> "Offline"
            },
            color = Ink.copy(alpha = 0.8f),
            fontSize = 9.5.sp,
            maxLines = 1,
        )
    }
}

private fun iconForModule(id: String): ImageVector = when (id) {
    "system" -> Icons.Rounded.Speed
    "weather" -> Icons.Rounded.WbSunny
    "media" -> Icons.Rounded.MusicNote
    "shortcuts" -> Icons.Rounded.GridView
    "audiomesh" -> Icons.Rounded.GraphicEq
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
        PageBody(page, endpoint, onAction, compact)
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
        PageBody(page, endpoint, onAction, compact)
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
    if (blocks.size <= 1) {
        val scroll = rememberScrollState()
        BoxWithConstraints(Modifier.fillMaxSize()) {
            Column(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = maxHeight)
                    .verticalScroll(scroll)
                    .padding(horizontal = if (compact) 18.dp else 20.dp)
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

    Box(Modifier.fillMaxSize()) {
        AutoFit(Modifier.fillMaxSize()) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = if (compact) 18.dp else 20.dp)
                .padding(top = if (compact) 2.dp else 8.dp, bottom = 8.dp),
        ) {
        if (compact) {
            val (left, right) = balanceBlocks(blocks)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Column(Modifier.weight(1f)) {
                    left.forEach { block ->
                        BlockView(
                            block = block,
                            module = page.id,
                            accent = accent,
                            endpoint = endpoint,
                            onAction = { action, payload -> onAction(page.id, action, payload) },
                        )
                        Spacer(Modifier.height(12.dp))
                    }
                }
                Column(Modifier.weight(1f)) {
                    right.forEach { block ->
                        BlockView(
                            block = block,
                            module = page.id,
                            accent = accent,
                            endpoint = endpoint,
                            onAction = { action, payload -> onAction(page.id, action, payload) },
                        )
                        Spacer(Modifier.height(12.dp))
                    }
                }
            }
        } else {
            blocks.forEach { block ->
                BlockView(
                    block = block,
                    module = page.id,
                    accent = accent,
                    endpoint = endpoint,
                    onAction = { action, payload -> onAction(page.id, action, payload) },
                )
                Spacer(Modifier.height(13.dp))
            }
        }
        }
        }
    }
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
            placeable.placeWithLayer(0, 0) {
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

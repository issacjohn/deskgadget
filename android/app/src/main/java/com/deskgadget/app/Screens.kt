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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/* ============================== connect ============================== */

@Composable
fun ConnectScreen(
    state: DeckState,
    prefs: Prefs,
    onConnect: (String, Int) -> Unit,
) {
    val context = LocalContext.current
    val discovery = remember { LanDiscovery(context) }
    var found by remember { mutableStateOf<List<LanDiscovery.Found>>(emptyList()) }
    var host by remember { mutableStateOf(prefs.host.ifBlank { "" }) }
    var port by remember { mutableStateOf(prefs.port.toString()) }
    var scanning by remember { mutableStateOf(true) }

    DisposableEffect(Unit) {
        discovery.start(
            onFound = { f ->
                found = (found.filterNot { it.host == f.host && it.port == f.port } + f)
                scanning = false
            },
            onLost = {},
        )
        onDispose { discovery.stop() }
    }

    LaunchedEffect(Unit) {
        delay(4500)
        scanning = false
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
        "DESKGADGET",
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
        "Tip: with the cable plugged in, the Windows app forwards the port automatically — "
            + "no Wi-Fi and no USB debugging prompts beyond the first one.",
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
    found: List<LanDiscovery.Found>,
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
            "Start the DESKGadget server on Windows. The phone and PC must share a Wi-Fi network, "
                + "or connect over USB and use 127.0.0.1.",
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
                    if (scanning) "Looking for DESKGadget on your network…"
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
) {
    val pages = state.pages
    val pager = rememberPagerState(pageCount = { pages.size })
    val scope = rememberCoroutineScope()
    var toastVisible by remember { mutableStateOf(false) }

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
                    ModuleTabs(pages, pager, Modifier.weight(1f), select)
                    Spacer(Modifier.width(10.dp))
                    Text(clock, color = Muted, fontSize = 10.sp, letterSpacing = 0.8.sp)
                    Spacer(Modifier.width(8.dp))
                    HeaderChip("Disconnect", onDisconnect)
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
                        HeaderChip("Disconnect", onDisconnect)
                    }
                    Spacer(Modifier.height(3.dp))
                    ModuleTabs(pages, pager, Modifier.fillMaxWidth(), select)
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
                            PageView(
                                page = pages[index],
                                endpoint = state.endpoint,
                                onAction = onAction,
                                compact = wide,
                            )
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
    }
}

/** Tab-style module switcher, mirroring the swipe position. */
@Composable
private fun ModuleTabs(
    pages: List<PageData>,
    pager: PagerState,
    modifier: Modifier = Modifier,
    onSelect: (Int) -> Unit,
) {
    val spread = pages.size in 3..6
    if (spread) {
        Row(modifier = modifier, verticalAlignment = Alignment.Bottom) {
            pages.forEachIndexed { index, page ->
                TabItem(
                    page = page,
                    active = pager.currentPage == index,
                    modifier = Modifier.weight(1f),
                    onClick = { onSelect(index) },
                )
            }
        }
    } else {
        Row(
            modifier = modifier.horizontalScroll(rememberScrollState()),
            verticalAlignment = Alignment.Bottom,
        ) {
            pages.forEachIndexed { index, page ->
                TabItem(
                    page = page,
                    active = pager.currentPage == index,
                    modifier = Modifier.widthIn(min = 108.dp),
                    underlineWidth = 44.dp,
                    onClick = { onSelect(index) },
                )
            }
        }
    }
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

    val scroll = rememberScrollState()
    Box(Modifier.fillMaxSize()) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(scroll)
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

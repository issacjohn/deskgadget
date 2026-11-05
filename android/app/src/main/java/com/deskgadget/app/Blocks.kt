package com.deskgadget.app

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.SkipPrevious
import androidx.compose.material.icons.rounded.VolumeDown
import androidx.compose.material.icons.rounded.VolumeOff
import androidx.compose.material.icons.rounded.VolumeUp
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import coil.compose.AsyncImage
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

private fun JSONObject.arr(key: String): JSONArray = optJSONArray(key) ?: JSONArray()
private fun JSONObject.str(key: String, def: String = ""): String = optString(key, def)
private fun JSONObject.num(key: String, def: Double = 0.0): Double = optDouble(key, def)

@Composable
fun BlockView(
    block: JSONObject,
    module: String,
    accent: Color,
    endpoint: String,
    onAction: (String, JSONObject?) -> Unit,
    modifier: Modifier = Modifier,
) {
    when (block.str("type")) {
        "hero" -> HeroCard(block, accent, modifier) { action, payload -> onAction(action, payload) }
        "gauges" -> GaugeCard(block, accent, modifier)
        "sparkline" -> SparkCard(block, accent, modifier)
        "meters" -> MetersCard(block, accent, modifier)
        "kv" -> KvCard(block, modifier)
        "list" -> ListCard(block, accent, modifier) { action, payload -> onAction(action, payload) }
        "news" -> NewsBlock(block, accent) { action, payload -> onAction(action, payload) }
        "toggles" -> TogglesCard(block, accent) { id ->
            onAction(block.str("action", "mic_toggle"), JSONObject().put("id", id))
        }
        "controls" -> ControlsCard(block, accent) { id -> onAction(id, null) }
        "slider" -> SliderCard(block, accent) { id, value ->
            onAction(id, JSONObject().put("value", value))
        }
        "nowplaying" -> NowPlayingCard(block, accent, endpoint) { seconds ->
            onAction(block.str("action"), JSONObject().put("value", seconds))
        }
        "textinput" -> TextInputCard(block, accent) { action, text ->
            onAction(action, JSONObject().put("text", text))
        }
        "shortcuts" -> ShortcutsCard(block, accent, endpoint) { id ->
            onAction("launch", JSONObject().put("id", id))
        }
    }
}

/* ----------------------------- hero ----------------------------- */

@Composable
private fun HeroCard(
    block: JSONObject,
    accent: Color,
    modifier: Modifier,
    onAction: (String, JSONObject?) -> Unit,
) {
    val compact = LocalCompactLayout.current
    val value = block.str("value", "--")
    val unit = block.str("unit")
    val icon = block.optString("icon").takeIf { it.isNotBlank() }
    val cardAccent = if (block.optString("accent").isNotBlank()) hexColor(block.str("accent"), accent) else accent
    val progress = block.optDouble("progress", -1.0)
    val valueSize = when {
        value.length > 5 -> if (compact) 30.sp else 44.sp
        compact -> 46.sp
        else -> 76.sp
    }

    GlassPanel(modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    block.str("label").uppercase(),
                    color = Muted,
                    fontSize = 10.sp,
                    letterSpacing = 2.sp,
                    fontWeight = FontWeight.Medium,
                )
                Spacer(Modifier.height(if (compact) 4.dp else 10.dp))
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(
                        value,
                        color = Ink,
                        fontSize = valueSize,
                        fontWeight = FontWeight.Light,
                        letterSpacing = (-2).sp,
                        fontFamily = FontFamily.SansSerif,
                        maxLines = 1,
                    )
                    if (unit.isNotBlank()) {
                        Text(
                            unit,
                            color = cardAccent,
                            fontSize = if (compact) 20.sp else 26.sp,
                            fontWeight = FontWeight.Light,
                            modifier = Modifier.padding(bottom = if (compact) 6.dp else 12.dp, start = 2.dp),
                        )
                    }
                }
                val sub = block.str("sub")
                if (sub.isNotBlank()) {
                    Spacer(Modifier.height(if (compact) 3.dp else 6.dp))
                    Text(sub, color = Muted, fontSize = if (compact) 11.5.sp else 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
            if (icon != null) {
                WeatherGlyph(
                    kind = icon,
                    isDay = block.optBoolean("is_day", true),
                    tint = cardAccent,
                    modifier = Modifier.size(if (compact) 56.dp else 92.dp),
                )
            }
        }
        val slider = block.optJSONObject("slider")
        if (slider != null) {
            Spacer(Modifier.height(if (compact) 8.dp else 14.dp))
            InlineSlider(
                initial = slider.optDouble("value", 0.0).toFloat(),
                minV = slider.optDouble("min", 0.0).toFloat(),
                maxV = slider.optDouble("max", 100.0).toFloat(),
                accent = cardAccent,
            ) { v ->
                onAction(
                    slider.optString("action", "set_volume"),
                    JSONObject().put("value", v),
                )
            }
        } else if (progress >= 0) {
            Spacer(Modifier.height(if (compact) 10.dp else 16.dp))
            ProgressTrack(progress.toFloat().coerceIn(0f, 1f), cardAccent)
        }
    }
}

/* ----------------------------- gauges ----------------------------- */

@Composable
private fun GaugeCard(block: JSONObject, accent: Color, modifier: Modifier) {
    val compact = LocalCompactLayout.current
    val ring = if (compact) 74.dp else 88.dp
    val items = block.arr("items")
    GlassPanel(modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            for (i in 0 until items.length()) {
                val item = items.getJSONObject(i)
                Box(contentAlignment = Alignment.Center) {
                    Canvas(Modifier.size(ring)) {
                        val stroke = 6.dp.toPx()
                        val inset = stroke / 2
                        val arcSize = Size(size.width - stroke, size.height - stroke)
                        drawArc(
                            color = Color(0x1FFFFFFF),
                            startAngle = -90f,
                            sweepAngle = 360f,
                            useCenter = false,
                            topLeft = Offset(inset, inset),
                            size = arcSize,
                            style = Stroke(stroke, cap = StrokeCap.Round),
                        )
                        val frac = (item.num("value") / 100.0).toFloat().coerceIn(0f, 1f)
                        drawArc(
                            brush = Brush.sweepGradient(listOf(accent.copy(alpha = 0.35f), accent)),
                            startAngle = -90f,
                            sweepAngle = 360f * frac,
                            useCenter = false,
                            topLeft = Offset(inset, inset),
                            size = arcSize,
                            style = Stroke(stroke, cap = StrokeCap.Round),
                        )
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            "${item.num("value").toInt()}${item.str("suffix")}",
                            color = Ink,
                            fontSize = if (compact) 17.sp else 20.sp,
                            fontWeight = FontWeight.Medium,
                        )
                        Spacer(Modifier.height(1.dp))
                        Text(
                            item.str("label").uppercase(),
                            color = Muted,
                            fontSize = 7.5.sp,
                            letterSpacing = 0.9.sp,
                        )
                    }
                }
            }
        }
    }
}

/* ----------------------------- sparkline ----------------------------- */

@Composable
private fun SparkCard(block: JSONObject, accent: Color, modifier: Modifier) {
    val compact = LocalCompactLayout.current
    val points = block.arr("points")
    val minV = block.num("min", 0.0)
    val maxV = block.num("max", 100.0)
    val values = ArrayList<Float>(points.length())
    for (i in 0 until points.length()) values.add(points.getDouble(i).toFloat())

    GlassPanel(modifier.fillMaxWidth()) {
        Text(
            block.str("label").uppercase(),
            color = Muted,
            fontSize = 10.sp,
            letterSpacing = 2.sp,
        )
        Spacer(Modifier.height(12.dp))
        Canvas(
            Modifier
                .fillMaxWidth()
                .height(if (compact) 50.dp else 84.dp)
        ) {
            if (values.size < 2) return@Canvas
            val range = (maxV - minV).toFloat().coerceAtLeast(0.001f)
            val stepX = size.width / (values.size - 1)
            val path = Path()
            val fill = Path()
            values.forEachIndexed { i, v ->
                val x = i * stepX
                val y = size.height - ((v - minV.toFloat()) / range).coerceIn(0f, 1f) * size.height
                if (i == 0) {
                    path.moveTo(x, y)
                    fill.moveTo(x, size.height)
                    fill.lineTo(x, y)
                } else {
                    path.lineTo(x, y)
                    fill.lineTo(x, y)
                }
            }
            fill.lineTo(size.width, size.height)
            fill.close()
            drawPath(
                fill,
                Brush.verticalGradient(
                    listOf(accent.copy(alpha = 0.30f), accent.copy(alpha = 0.02f))
                ),
            )
            drawPath(
                path,
                brush = Brush.horizontalGradient(listOf(accent.copy(alpha = 0.5f), accent)),
                style = Stroke(width = 2.2.dp.toPx(), cap = StrokeCap.Round),
            )
            val tipY = size.height - (((values.lastOrNull() ?: 0f) - minV.toFloat()) / range).coerceIn(0f, 1f) * size.height
            drawCircle(accent, radius = 3.dp.toPx(), center = Offset(size.width, tipY))
        }
    }
}

private fun lastY(values: List<Float>, minV: Double, range: Float, height: Float): Float {
    val v = values.last()
    return height - ((v - minV.toFloat()) / range).coerceIn(0f, 1f) * height
}

/* ----------------------------- meters ----------------------------- */

@Composable
private fun MetersCard(block: JSONObject, accent: Color, modifier: Modifier) {
    val items = block.arr("items")
    GlassPanel(modifier.fillMaxWidth()) {
        for (i in 0 until items.length()) {
            val item = items.getJSONObject(i)
            if (i > 0) Spacer(Modifier.height(if (LocalCompactLayout.current) 13.dp else 18.dp))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    item.str("label").uppercase(),
                    color = Muted,
                    fontSize = 10.sp,
                    letterSpacing = 1.8.sp,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    "${item.num("value").toInt()}%",
                    color = Ink,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                )
            }
            Spacer(Modifier.height(9.dp))
            ProgressTrack((item.num("value") / 100.0).toFloat().coerceIn(0f, 1f), accent)
            Spacer(Modifier.height(7.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(item.str("left"), color = Faint, fontSize = 11.sp)
                Text(item.str("right"), color = Faint, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun ProgressTrack(fraction: Float, accent: Color) {
    Box(
        Modifier
            .fillMaxWidth()
            .height(7.dp)
            .clip(RoundedCornerShape(50))
            .background(Color(0x1FFFFFFF))
    ) {
        Box(
            Modifier
                .fillMaxWidth(fraction)
                .height(7.dp)
                .clip(RoundedCornerShape(50))
                .background(Brush.horizontalGradient(listOf(accent.copy(alpha = 0.55f), accent)))
        )
    }
}

/* ----------------------------- kv ----------------------------- */

@Composable
private fun KvCard(block: JSONObject, modifier: Modifier) {
    val items = block.arr("items")
    GlassPanel(
        modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 16.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            for (i in 0 until items.length()) {
                val item = items.getJSONObject(i)
                Column(horizontalAlignment = Alignment.Start) {
                    Text(
                        item.str("label").uppercase(),
                        color = Faint,
                        fontSize = 9.5.sp,
                        letterSpacing = 1.5.sp,
                    )
                    Spacer(Modifier.height(5.dp))
                    Text(
                        item.str("value"),
                        color = Ink,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }
        }
    }
}

/* ----------------------------- list ----------------------------- */

@Composable
private fun ListCard(
    block: JSONObject,
    accent: Color,
    modifier: Modifier,
    onAction: (String, JSONObject?) -> Unit,
) {
    val compact = LocalCompactLayout.current
    val items = block.arr("items")
    GlassPanel(modifier.fillMaxWidth(), contentPadding = PaddingValues(horizontal = 18.dp, vertical = 16.dp)) {
        val title = block.str("title")
        if (title.isNotBlank()) {
            Text(title.uppercase(), color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
            Spacer(Modifier.height(8.dp))
        }
        for (i in 0 until items.length()) {
            val item = items.getJSONObject(i)
            if (i > 0) {
                Box(Modifier.fillMaxWidth().height(1.dp).background(Color(0x0FFFFFFF)))
            }
            Row(
                Modifier
                    .fillMaxWidth()
                    .then(
                        if (item.optString("action").isNotBlank()) {
                            Modifier.clickable {
                                onAction(
                                    item.optString("action"),
                                    JSONObject()
                                        .put("url", item.optString("url"))
                                        .put("id", item.optString("id")),
                                )
                            }
                        } else {
                            Modifier
                        }
                    )
                    .padding(vertical = if (compact) 6.dp else 11.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                val icon = item.optString("icon")
                if (icon.isNotBlank()) {
                    WeatherGlyph(
                        kind = icon,
                        isDay = true,
                        tint = accent,
                        modifier = Modifier.size(24.dp).padding(end = 2.dp),
                    )
                    Spacer(Modifier.width(12.dp))
                }
                Column(Modifier.weight(1f)) {
                    Text(item.str("title"), color = Ink, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val sub = item.str("sub")
                    if (sub.isNotBlank()) {
                        Text(sub, color = Faint, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                Text(
                    item.str("value"),
                    color = Ink.copy(alpha = 0.86f),
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                )
            }
        }
    }
}

/* ----------------------------- controls ----------------------------- */

@Composable
private fun ControlsCard(block: JSONObject, accent: Color, onPress: (String) -> Unit) {
    val items = block.arr("items")
    val transport = block.str("style") == "transport"
    GlassPanel(
        Modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = if (transport) 20.dp else 16.dp),
    ) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = if (transport) Arrangement.SpaceEvenly else Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            for (i in 0 until items.length()) {
                val item = items.getJSONObject(i)
                val primary = item.optBoolean("primary", false)
                val id = item.str("id")
                val label = item.str("label")
                if (transport) {
                    TransportButton(
                        icon = iconFor(item.str("icon")),
                        primary = primary,
                        accent = accent,
                        size = if (primary) 76 else 58,
                    ) { onPress(id) }
                } else {
                    PillButton(
                        icon = iconFor(item.str("icon")),
                        label = label,
                        accent = accent,
                        modifier = Modifier.weight(1f),
                    ) { onPress(id) }
                }
            }
        }
    }
}

private fun iconFor(name: String): ImageVector = when (name) {
    "prev" -> Icons.Rounded.SkipPrevious
    "next" -> Icons.Rounded.SkipNext
    "play_pause" -> Icons.Rounded.PlayArrow
    "pause" -> Icons.Rounded.Pause
    "volume_up" -> Icons.Rounded.VolumeUp
    "volume_down" -> Icons.Rounded.VolumeDown
    "mute" -> Icons.Rounded.VolumeOff
    else -> Icons.Rounded.PlayArrow
}

@Composable
private fun TransportButton(
    icon: ImageVector,
    primary: Boolean,
    accent: Color,
    size: Int,
    onClick: () -> Unit,
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.92f else 1f, label = "press")

    Box(
        Modifier
            .size(size.dp)
            .scale(scale)
            .clip(CircleShape)
            .background(
                if (primary) {
                    Brush.linearGradient(listOf(accent, accent.copy(alpha = 0.65f)))
                } else {
                    Brush.linearGradient(listOf(Color(0x1FFFFFFF), Color(0x0DFFFFFF)))
                }
            )
            .border(
                1.dp,
                if (primary) Color.Transparent else Color(0x33FFFFFF),
                CircleShape,
            )
            .pressable(interaction, onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = if (primary) Color(0xFF08121A) else Ink,
            modifier = Modifier.size((size * 0.42f).dp),
        )
    }
}

@Composable
private fun PillButton(
    icon: ImageVector,
    label: String,
    accent: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val shape = RoundedCornerShape(18.dp)
    Column(
        modifier
            .clip(shape)
            .background(
                Brush.linearGradient(
                    if (pressed) {
                        listOf(accent.copy(alpha = 0.26f), accent.copy(alpha = 0.14f))
                    } else {
                        listOf(Color(0x18FFFFFF), Color(0x08FFFFFF))
                    }
                )
            )
            .border(1.dp, Color(0x24FFFFFF), shape)
            .pressable(interaction, onClick)
            .padding(vertical = 13.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(icon, contentDescription = label, tint = accent, modifier = Modifier.size(22.dp))
        Spacer(Modifier.height(7.dp))
        Text(
            label,
            color = Muted,
            fontSize = 10.5.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

private fun Modifier.pressable(
    interaction: MutableInteractionSource,
    onClick: () -> Unit,
): Modifier = this.clickable(interactionSource = interaction, indication = null, onClick = onClick)

/* ----------------------------- toggles ----------------------------- */

@Composable
private fun TogglesCard(block: JSONObject, accent: Color, onToggle: (String) -> Unit) {
    val items = block.arr("items")
    GlassPanel(Modifier.fillMaxWidth()) {
        val title = block.str("title")
        if (title.isNotBlank()) {
            Text(title.uppercase(), color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
            Spacer(Modifier.height(8.dp))
        }
        for (i in 0 until items.length()) {
            val item = items.getJSONObject(i)
            ToggleRow(item, accent) { onToggle(item.optString("id")) }
        }
    }
}

@Composable
private fun ToggleRow(item: JSONObject, accent: Color, onToggle: () -> Unit) {
    val on = item.optBoolean("on", false)
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .clickable { onToggle() }
            .padding(vertical = 7.dp, horizontal = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = Icons.Rounded.Mic,
            contentDescription = null,
            tint = if (on) accent else Faint,
            modifier = Modifier.size(18.dp),
        )
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(
                item.optString("label"),
                color = Ink,
                fontSize = 14.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(if (on) "Muted" else "Live", color = Muted, fontSize = 10.5.sp)
        }
        Spacer(Modifier.width(10.dp))
        Box(
            Modifier
                .width(42.dp)
                .height(24.dp)
                .clip(RoundedCornerShape(50))
                .background(if (on) accent else Color(0x33FFFFFF))
        ) {
            Box(
                Modifier
                    .align(if (on) Alignment.CenterEnd else Alignment.CenterStart)
                    .padding(3.dp)
                    .size(18.dp)
                    .clip(CircleShape)
                    .background(if (on) Color(0xFF08121A) else Color(0xFFC9D4E4))
            )
        }
    }
}

/* ----------------------------- news ----------------------------- */

@Composable
private fun NewsBlock(
    block: JSONObject,
    accent: Color,
    onAction: (String, JSONObject?) -> Unit,
) {
    val items = block.arr("items")
    Column(Modifier.fillMaxWidth()) {
        val title = block.str("title")
        if (title.isNotBlank()) {
            Text(
                title.uppercase(),
                color = Muted,
                fontSize = 10.sp,
                letterSpacing = 2.sp,
                modifier = Modifier.padding(start = 4.dp, bottom = 10.dp),
            )
        }
        for (i in 0 until items.length()) {
            val item = items.getJSONObject(i)
            NewsCard(item, accent) {
                onAction("open", JSONObject().put("url", item.optString("url")))
            }
            Spacer(Modifier.height(10.dp))
        }
    }
}

@Composable
private fun NewsCard(item: JSONObject, accent: Color, onOpen: () -> Unit) {
    val palette = LocalPalette.current
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.985f else 1f, label = "news")
    val shape = RoundedCornerShape(20.dp)
    val source = item.optString("source")
    val image = item.optString("image")

    Row(
        Modifier
            .fillMaxWidth()
            .scale(scale)
            .clip(shape)
            .background(Brush.linearGradient(listOf(palette.glassTop, palette.glassBottom)))
            .border(1.dp, palette.borderMid, shape)
            .pressable(interaction, onOpen)
            .padding(14.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Box(
            Modifier
                .size(54.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(accent.copy(alpha = 0.12f)),
            contentAlignment = Alignment.Center,
        ) {
            if (image.isNotBlank()) {
                AsyncImage(
                    model = image,
                    contentDescription = source,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize().padding(9.dp),
                )
            } else {
                Text(
                    source.take(1).uppercase(),
                    color = accent,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    source.uppercase(),
                    color = accent,
                    fontSize = 9.5.sp,
                    letterSpacing = 1.4.sp,
                    maxLines = 1,
                    modifier = Modifier.weight(1f),
                )
                Text(item.optString("ago"), color = Muted, fontSize = 10.sp)
            }
            Spacer(Modifier.height(5.dp))
            Text(
                item.optString("title"),
                color = Ink,
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
                lineHeight = 22.sp,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

/* ----------------------------- slider ----------------------------- */

@Composable
private fun SliderCard(
    block: JSONObject,
    accent: Color,
    onCommit: (String, Int) -> Unit,
) {
    val action = block.str("action")
    GlassPanel(Modifier.fillMaxWidth(), contentPadding = PaddingValues(horizontal = 18.dp, vertical = 18.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                block.str("label").uppercase(),
                color = Muted,
                fontSize = 10.sp,
                letterSpacing = 2.sp,
                modifier = Modifier.weight(1f),
            )
            Text(
                "${block.num("value", 50.0).toInt()}%",
                color = accent,
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
        Spacer(Modifier.height(14.dp))
        InlineSlider(
            initial = block.num("value", 50.0).toFloat(),
            minV = block.num("min", 0.0).toFloat(),
            maxV = block.num("max", 100.0).toFloat(),
            accent = accent,
        ) { v -> onCommit(action, v) }
    }
}

/** Track + thumb used by the slider block and by hero cards that carry a control. */
@Composable
private fun TextInputCard(
    block: JSONObject,
    accent: Color,
    onSend: (String, String) -> Unit,
) {
    var text by remember { mutableStateOf("") }
    val action = block.str("action")
    val ready = text.isNotBlank()

    GlassPanel(
        Modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 16.dp),
    ) {
        Text(
            block.str("label").uppercase().ifBlank { "SEND TEXT" },
            color = Muted,
            fontSize = 10.sp,
            letterSpacing = 2.sp,
        )
        Spacer(Modifier.height(10.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(Color(0x33000000))
                .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(12.dp))
                .padding(horizontal = 12.dp, vertical = 10.dp)
        ) {
            BasicTextField(
                value = text,
                onValueChange = { text = it },
                textStyle = TextStyle(color = Ink, fontSize = 13.sp),
                cursorBrush = SolidColor(accent),
                maxLines = 3,
                decorationBox = { inner ->
                    if (text.isEmpty()) {
                        Text(
                            block.str("placeholder").ifBlank { "Type here…" },
                            color = Faint,
                            fontSize = 13.sp,
                        )
                    }
                    inner()
                },
            )
        }
        Spacer(Modifier.height(10.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .height(42.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(if (ready) accent else Color(0x14FFFFFF))
                .clickable(enabled = ready) {
                    onSend(action, text)
                    text = ""
                },
            contentAlignment = Alignment.Center,
        ) {
            Text(
                block.str("button").ifBlank { "Send" },
                color = if (ready) Color(0xFF06121A) else Faint,
                fontSize = 12.5.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

/** Track + thumb used by the slider block and by hero cards that carry a control. */
@Composable
private fun NowPlayingCard(
    block: JSONObject,
    accent: Color,
    endpoint: String,
    onSeek: (Int) -> Unit,
) {
    val duration = block.num("duration", 0.0).toFloat()
    val position = block.num("position", 0.0).toFloat()
    val rawArt = block.str("artwork")
    // the server sends a root-relative path; Coil needs a full URL
    val artwork = if (rawArt.startsWith("/")) endpoint.trimEnd('/') + rawArt else rawArt

    GlassPanel(
        Modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(58.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(Color(0x14FFFFFF)),
                contentAlignment = Alignment.Center,
            ) {
                if (artwork.isNotBlank()) {
                    AsyncImage(
                        model = artwork,
                        contentDescription = null,
                        contentScale = androidx.compose.ui.layout.ContentScale.Crop,
                        modifier = Modifier.fillMaxSize(),
                    )
                } else {
                    androidx.compose.material3.Icon(
                        imageVector = Icons.Rounded.MusicNote,
                        contentDescription = null,
                        tint = accent.copy(alpha = 0.85f),
                        modifier = Modifier.size(24.dp),
                    )
                }
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    block.str("title"),
                    color = Ink,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                val artist = block.str("artist")
                if (artist.isNotBlank()) {
                    Spacer(Modifier.height(2.dp))
                    Text(
                        artist,
                        color = Muted,
                        fontSize = 12.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                val source = block.str("source")
                if (source.isNotBlank()) {
                    Spacer(Modifier.height(3.dp))
                    Text(
                        source.uppercase(),
                        color = accent.copy(alpha = 0.9f),
                        fontSize = 8.5.sp,
                        letterSpacing = 1.4.sp,
                    )
                }
            }
        }
        if (duration > 0f) {
            Spacer(Modifier.height(12.dp))
            InlineSlider(
                initial = position,
                minV = 0f,
                maxV = duration,
                accent = accent,
            ) { v -> onSeek(v) }
            Row(Modifier.fillMaxWidth()) {
                Text(fmtTime(position), color = Faint, fontSize = 10.sp, modifier = Modifier.weight(1f))
                Text(fmtTime(duration), color = Faint, fontSize = 10.sp)
            }
        }
    }
}

private fun fmtTime(seconds: Float): String {
    val total = seconds.toInt().coerceAtLeast(0)
    return "%d:%02d".format(total / 60, total % 60)
}

/** Track + thumb used by the slider block and by hero cards that carry a control. */
@Composable
private fun InlineSlider(    initial: Float,
    minV: Float,
    maxV: Float,
    accent: Color,
    modifier: Modifier = Modifier,
    onCommit: (Int) -> Unit,
) {
    var value by remember { mutableFloatStateOf(initial) }
    var width by remember { mutableStateOf(1f) }
    var dragging by remember { mutableStateOf(false) }

    // server pushes move the thumb, but never while the finger is on it
    LaunchedEffect(initial, dragging) {
        if (!dragging) value = initial
    }

    Canvas(
        modifier
            .fillMaxWidth()
            .height(32.dp)
            .onSizeChanged { width = it.width.toFloat().coerceAtLeast(1f) }
            .pointerInput(minV, maxV) {
                detectTapGestures { offset ->
                    val frac = (offset.x / width).coerceIn(0f, 1f)
                    value = minV + frac * (maxV - minV)
                    onCommit(value.toInt())
                }
            }
            .pointerInput(minV, maxV) {
                detectDragGestures(
                    onDragStart = { offset ->
                        dragging = true
                        val frac = (offset.x / width).coerceIn(0f, 1f)
                        value = minV + frac * (maxV - minV)
                    },
                    onDrag = { change, _ ->
                        change.consume()
                        val frac = (change.position.x / width).coerceIn(0f, 1f)
                        value = minV + frac * (maxV - minV)
                    },
                    onDragEnd = {
                        dragging = false
                        onCommit(value.toInt())
                    },
                    onDragCancel = { dragging = false },
                )
            }
    ) {
        val trackH = 8.dp.toPx()
        val cy = size.height / 2f
        drawRoundRect(
            color = Color(0x1FFFFFFF),
            topLeft = Offset(0f, cy - trackH / 2f),
            size = Size(size.width, trackH),
            cornerRadius = CornerRadius(trackH / 2f),
        )
        val frac = ((value - minV) / (maxV - minV)).coerceIn(0f, 1f)
        drawRoundRect(
            brush = Brush.horizontalGradient(listOf(accent.copy(alpha = 0.5f), accent)),
            topLeft = Offset(0f, cy - trackH / 2f),
            size = Size(size.width * frac, trackH),
            cornerRadius = CornerRadius(trackH / 2f),
        )
        val thumbX = size.width * frac
        drawCircle(Color(0x33000000), radius = 13.dp.toPx() * (if (dragging) 1.15f else 1f), center = Offset(thumbX, cy))
        drawCircle(Color.White, radius = 10.dp.toPx(), center = Offset(thumbX, cy))
        drawCircle(accent, radius = 5.dp.toPx(), center = Offset(thumbX, cy))
    }
}

/* ----------------------------- shortcuts ----------------------------- */

@Composable
private fun ShortcutsCard(
    block: JSONObject,
    accent: Color,
    endpoint: String,
    onLaunch: (String) -> Unit,
) {
    val compact = LocalCompactLayout.current
    val items = block.arr("items")
    val serverColumns = block.optInt("columns", 3).coerceIn(2, 4)
    // choose enough columns that the grid stays within two rows on a wide screen
    val columns = if (compact) {
        val needed = ((items.length() + 1) / 2).coerceIn(3, 5)
        maxOf(serverColumns, needed)
    } else {
        serverColumns
    }
    GlassPanel(Modifier.fillMaxWidth()) {        val title = block.str("title")
        if (title.isNotBlank()) {
            Text(title.uppercase(), color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
            Spacer(Modifier.height(14.dp))
        }
        var index = 0
        while (index < items.length()) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                for (c in 0 until columns) {
                    if (index < items.length()) {
                        val item = items.getJSONObject(index)
                        ShortcutTile(
                            label = item.str("label"),
                            iconUrl = endpoint + item.str("icon"),
                            accent = accent,
                            modifier = Modifier.weight(1f),
                        ) { onLaunch(item.str("id")) }
                    } else {
                        Spacer(Modifier.weight(1f))
                    }
                    index++
                }
            }
            if (index < items.length()) Spacer(Modifier.height(10.dp))
        }
    }
}

@Composable
private fun ShortcutTile(
    label: String,
    iconUrl: String,
    accent: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val shape = RoundedCornerShape(20.dp)
    val scale by animateFloatAsState(if (pressed) 0.95f else 1f, label = "tile")
    val compact = LocalCompactLayout.current

    Column(
        modifier
            .scale(scale)
            .clip(shape)
            .background(
                Brush.linearGradient(listOf(Color(0x18FFFFFF), Color(0x07FFFFFF)))
            )
            .border(1.dp, Color(0x26FFFFFF), shape)
            .pressable(interaction, onClick)
            .padding(vertical = if (compact) 10.dp else 14.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        AsyncImage(
            model = iconUrl,
            contentDescription = label,
            contentScale = androidx.compose.ui.layout.ContentScale.Crop,
            modifier = Modifier
                .size(if (compact) 32.dp else 42.dp)
                .clip(RoundedCornerShape(8.dp)),
        )
        Spacer(Modifier.height(if (compact) 6.dp else 9.dp))
        Text(
            label,
            color = Ink.copy(alpha = 0.9f),
            fontSize = if (compact) 10.5.sp else 10.5.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(horizontal = 4.dp),
        )
    }
}

private fun Modifier.clickableWith(
    interaction: MutableInteractionSource,
    onClick: () -> Unit,
): Modifier = this.pressable(interaction, onClick)

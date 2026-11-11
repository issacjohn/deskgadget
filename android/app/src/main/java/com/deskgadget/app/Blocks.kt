package com.deskgadget.app

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.runtime.mutableIntStateOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response as HttpCallResponse
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Circle
import androidx.compose.material.icons.rounded.DesktopWindows
import androidx.compose.material.icons.rounded.FlashOff
import androidx.compose.material.icons.rounded.FlashOn
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.GridView
import androidx.compose.material.icons.rounded.Keyboard
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Straighten
import androidx.compose.material.icons.rounded.Sync
import androidx.compose.material.icons.rounded.Thermostat
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.MicOff
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PhotoCamera
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.PowerSettingsNew
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.SkipPrevious
import androidx.compose.material.icons.rounded.Videocam
import androidx.compose.material.icons.rounded.VideocamOff
import androidx.compose.material.icons.rounded.VolumeDown
import androidx.compose.material.icons.rounded.VolumeOff
import androidx.compose.material.icons.rounded.VolumeUp
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
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
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import coil.compose.AsyncImage
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
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
        "cpu" -> CpuCard(block, accent, modifier) { onAction("cpu_sensor", null) }
        "storage" -> StorageCard(block, accent, modifier)
        "gpu", "thermals" -> GpuCard(block, accent, modifier)
        "kv" -> KvCard(block, modifier)
        "list" -> ListCard(block, accent, endpoint, modifier) { action, payload -> onAction(action, payload) }
        "news" -> NewsBlock(block, accent) { action, payload -> onAction(action, payload) }
        "toggles" -> TogglesCard(block, accent) { id ->
            onAction(block.str("action", "mic_toggle"), JSONObject().put("id", id))
        }
        "controls" -> ControlsCard(block, accent, modifier) { id -> onAction(id, null) }
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
        "hours" -> HoursCard(block, accent, modifier)
        "note" -> NoteCard(block, modifier)
        "touchpad" -> TouchpadCard(block, accent, modifier) { action, payload ->
            onAction(action, payload)
        }
        "camera" -> CameraCard(block, accent, endpoint, modifier)
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
                    Text(sub, color = Muted, fontSize = if (compact) 12.5.sp else 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                // Compact detail figures (feels like, humidity, wind) live inside
                // the hero instead of taking a whole card of their own.
                val stats = block.optJSONArray("stats")
                if (stats != null && stats.length() > 0) {
                    Spacer(Modifier.height(if (compact) 8.dp else 12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(if (compact) 18.dp else 24.dp)) {
                        for (i in 0 until stats.length()) {
                            val stat = stats.getJSONObject(i)
                            Column {
                                Text(
                                    stat.str("label").uppercase(),
                                    color = Faint,
                                    fontSize = 9.sp,
                                    letterSpacing = 1.2.sp,
                                    maxLines = 1,
                                )
                                Spacer(Modifier.height(3.dp))
                                Text(
                                    stat.str("value"),
                                    color = Ink,
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Medium,
                                    maxLines = 1,
                                )
                            }
                        }
                    }
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
    val preferred = if (compact) 74.dp else 88.dp
    val items = block.arr("items")
    GlassPanel(modifier.fillMaxWidth()) {
      BoxWithConstraints(Modifier.fillMaxWidth()) {
        val count = items.length().coerceAtLeast(1)
        val gap = 10.dp
        // never draw a ring wider than its share of the card
        val ring = minOf(preferred, (maxWidth - gap * (count - 1)) / count)
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(gap, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            for (i in 0 until count) {
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

/* --------------------------- cpu / memory / gpu --------------------------- */

@Composable
private fun CpuCard(
    block: JSONObject,
    accent: Color,
    modifier: Modifier,
    onEnableSensor: () -> Unit,
) {
    val compact = LocalCompactLayout.current
    val bare = LocalBareCards.current
    val value = block.num("value", 0.0).toInt()
    val temp = thermalValue(block, "temp")
    val points = block.arr("points")
    val minV = block.num("min", 0.0)
    val maxV = block.num("max", 100.0)
    val values = ArrayList<Float>(points.length())
    for (i in 0 until points.length()) values.add(points.getDouble(i).toFloat())

    GlassPanel(if (bare) modifier.fillMaxSize() else modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("CPU", color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
            Spacer(Modifier.weight(1f))
            Text(
                "${block.optInt("threads", 0)} THREADS",
                color = Faint,
                fontSize = 7.5.sp,
                letterSpacing = 1.1.sp,
            )
        }
        Spacer(Modifier.height(if (compact) 6.dp else 12.dp))
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            Column(Modifier.weight(1f)) {
                Text("UTILIZATION", color = Muted, fontSize = 8.5.sp, letterSpacing = 1.2.sp)
                Text(
                    "$value%",
                    color = Ink,
                    fontSize = if (compact) 22.sp else 32.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
            Column(Modifier.weight(1f)) {
                Text("THERMAL", color = Muted, fontSize = 8.5.sp, letterSpacing = 1.2.sp)
                Text(
                    if (temp == null) "—" else "${temp.toInt()}°C",
                    color = if (temp == null) Faint else thermalColor(temp),
                    fontSize = if (compact) 22.sp else 32.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                if (temp == null) {
                    Text(
                        "ENABLE",
                        color = accent,
                        fontSize = 8.sp,
                        letterSpacing = 1.sp,
                        modifier = Modifier
                            .clip(RoundedCornerShape(50))
                            .background(accent.copy(alpha = 0.16f))
                            .clickableNoRipple(onEnableSensor)
                            .padding(horizontal = 8.dp, vertical = 3.dp),
                    )
                } else {
                    Text(
                        block.str("temp_name").ifBlank { "sensor" },
                        color = Faint,
                        fontSize = 9.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
        Spacer(Modifier.height(if (compact) 6.dp else 10.dp))
        val chart = if (bare) {
            Modifier
                .fillMaxWidth()
                .weight(1f)
                .heightIn(min = 34.dp)
        } else {
            Modifier
                .fillMaxWidth()
                .height(58.dp)
        }
        Canvas(chart) {
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
            val tipY = size.height - (((values.lastOrNull() ?: 0f) - minV.toFloat()) / range)
                .coerceIn(0f, 1f) * size.height
            drawCircle(accent, radius = 3.dp.toPx(), center = Offset(size.width, tipY))
        }
    }
}

@Composable
private fun StorageCard(block: JSONObject, accent: Color, modifier: Modifier) {
    val compact = LocalCompactLayout.current
    val bare = LocalBareCards.current
    val items = block.arr("items")

    GlassPanel(if (bare) modifier.fillMaxSize() else modifier.fillMaxWidth()) {
        Text("CAPACITY", color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
        Spacer(Modifier.height(if (compact) 2.dp else 12.dp))
        Column(
            if (bare) Modifier.weight(1f).fillMaxWidth() else Modifier.fillMaxWidth(),
            verticalArrangement = if (bare) {
                Arrangement.SpaceEvenly
            } else {
                Arrangement.spacedBy(16.dp)
            },
        ) {
            for (i in 0 until items.length()) {
                CapacityRow(items.getJSONObject(i), accent, compact)
            }
        }
    }
}

@Composable
private fun CapacityRow(item: JSONObject, accent: Color, compact: Boolean) {
    val pct = item.num("value").toInt()
    val frac = (pct / 100f).coerceIn(0f, 1f)
    val tint = if (pct >= 90) Color(0xFFFFC96B) else accent

    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
            Text(
                item.str("label").uppercase(),
                color = Muted,
                fontSize = 8.5.sp,
                letterSpacing = 1.6.sp,
                modifier = Modifier.weight(1f),
            )
            Text(
                "$pct%",
                color = Ink,
                fontSize = if (compact) 17.sp else 21.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
        Spacer(Modifier.height(2.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .height(if (compact) 9.dp else 11.dp)
                .clip(RoundedCornerShape(50))
                .background(Color(0x16FFFFFF)),
        ) {
            Box(
                Modifier
                    .fillMaxWidth(frac)
                    .fillMaxHeight()
                    .clip(RoundedCornerShape(50))
                    .background(
                        Brush.horizontalGradient(
                            listOf(tint.copy(alpha = 0.45f), tint)
                        )
                    ),
            )
            Canvas(Modifier.matchParentSize()) {
                for (i in 1..3) {
                    val x = size.width * i / 4f
                    drawLine(
                        Color(0x66000000),
                        Offset(x, 0f),
                        Offset(x, size.height),
                        strokeWidth = 1.dp.toPx(),
                    )
                }
            }
        }
        Spacer(Modifier.height(2.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                "${item.str("used")} of ${item.str("total")}",
                color = Faint,
                fontSize = 8.sp,
            )
            Text("${item.str("free")} free", color = Faint, fontSize = 8.sp)
        }
    }
}

@Composable
private fun GpuCard(block: JSONObject, accent: Color, modifier: Modifier) {
    val compact = LocalCompactLayout.current
    val bare = LocalBareCards.current
    val temp = thermalValue(block, "temp")
    val name = block.str("name").ifBlank { "GPU" }
    val tint = temp?.let { thermalColor(it) } ?: Faint
    val net = block.arr("net")

    GlassPanel(if (bare) modifier.fillMaxSize() else modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("GPU", color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
            Spacer(Modifier.weight(1f))
            Text("THERMAL", color = Faint, fontSize = 7.5.sp, letterSpacing = 1.1.sp)
        }
        Spacer(Modifier.height(if (compact) 6.dp else 12.dp))
        Text(
            if (temp == null) "—" else "${temp.toInt()}°",
            color = tint,
            fontSize = if (compact) 34.sp else 44.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            name.uppercase(),
            color = Faint,
            fontSize = 8.sp,
            letterSpacing = 0.5.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(10.dp))
        Canvas(
            Modifier
                .fillMaxWidth()
                .height(10.dp)
        ) {
            val radius = size.height / 2f
            drawRoundRect(
                brush = Brush.horizontalGradient(
                    listOf(
                        Color(0xFF5BE49B),
                        Color(0xFF5BE49B),
                        Color(0xFFFFC96B),
                        Color(0xFFFF8CA8),
                    )
                ),
                size = Size(size.width, size.height),
                cornerRadius = CornerRadius(radius, radius),
            )
            if (temp != null) {
                val x = (size.width * (temp / 100f))
                    .coerceIn(size.height, size.width - size.height)
                drawCircle(
                    Color(0xFF0A0C10),
                    radius = size.height * 0.62f,
                    center = Offset(x, radius),
                )
                drawCircle(
                    Color.White,
                    radius = size.height * 0.36f,
                    center = Offset(x, radius),
                )
            }
        }
        Spacer(Modifier.height(5.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("0", color = Faint, fontSize = 7.5.sp)
            Text("60", color = Faint, fontSize = 7.5.sp)
            Text("80", color = Faint, fontSize = 7.5.sp)
            Text("100°C", color = Faint, fontSize = 7.5.sp)
        }
        val hot = thermalValue(block, "hot")
        val memory = thermalValue(block, "memory")
        if (hot != null || memory != null) {
            Spacer(Modifier.height(10.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                if (hot != null) MiniThermal("HOT SPOT", hot)
                if (memory != null) MiniThermal("MEMORY", memory)
            }
        }
        Spacer(Modifier.weight(1f))
        if (net.length() > 0) {
            Spacer(Modifier.height(6.dp))
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(1.dp)
                    .background(Color(0x12FFFFFF))
            )
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                for (i in 0 until net.length()) {
                    val item = net.getJSONObject(i)
                    Column {
                        Text(
                            item.str("label").uppercase(),
                            color = Muted,
                            fontSize = 7.5.sp,
                            letterSpacing = 1.1.sp,
                        )
                        Spacer(Modifier.height(3.dp))
                        Text(
                            item.str("value"),
                            color = Ink,
                            fontSize = if (compact) 13.sp else 15.sp,
                            fontWeight = FontWeight.Medium,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun MiniThermal(label: String, value: Float) {
    Column {
        Text(label, color = Muted, fontSize = 7.5.sp, letterSpacing = 1.1.sp)
        Spacer(Modifier.height(2.dp))
        Text(
            "${value.toInt()}°C",
            color = thermalColor(value),
            fontSize = 13.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

private fun thermalValue(block: JSONObject, key: String): Float? {
    if (!block.has(key) || block.isNull(key)) return null
    val value = block.optDouble(key, Double.NaN)
    return if (value.isNaN()) null else value.toFloat().coerceIn(0f, 120f)
}

private fun thermalColor(value: Float): Color = when {
    value < 60f -> Color(0xFF5BE49B)
    value < 80f -> Color(0xFFFFC96B)
    else -> Color(0xFFFF8CA8)
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
private fun KvItem(item: JSONObject, modifier: Modifier) {
    Column(modifier, horizontalAlignment = Alignment.Start) {
        Text(
            item.str("label").uppercase(),
            color = Faint,
            fontSize = 9.5.sp,
            letterSpacing = 1.2.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(5.dp))
        val text = item.str("value")
        Text(
            text,
            color = Ink,
            // long values such as IPv4 addresses get a slightly tighter size
            // instead of being cut off in a narrow column
            fontSize = if (text.length > 12) 12.5.sp else 15.sp,
            fontWeight = FontWeight.Medium,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun KvCard(block: JSONObject, modifier: Modifier) {
    val items = block.arr("items")
    val perRow = if (items.length() > 3) 2 else items.length().coerceAtLeast(1)
    val bare = LocalBareCards.current
    GlassPanel(
        if (bare) modifier.fillMaxSize() else modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 16.dp),
    ) {
        Column(
            if (bare) Modifier.fillMaxSize() else Modifier.fillMaxWidth(),
            verticalArrangement = if (bare) Arrangement.SpaceBetween else Arrangement.spacedBy(12.dp),
        ) {
            var index = 0
            while (index < items.length()) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    repeat(perRow) {
                        if (index < items.length()) {
                            KvItem(items.getJSONObject(index), Modifier.weight(1f))
                            index++
                        } else {
                            Spacer(Modifier.weight(1f))
                        }
                    }
                }
            }
        }
    }
}

/* ----------------------------- hours ----------------------------- */

/** A horizontal strip of upcoming hours — reads at a glance in landscape. */
@Composable
private fun HoursCard(block: JSONObject, accent: Color, modifier: Modifier) {
    val items = block.arr("items")
    GlassPanel(
        modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 11.dp),
    ) {
        val title = block.str("title")
        if (title.isNotBlank()) {
            Text(title.uppercase(), color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
            Spacer(Modifier.height(7.dp))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for (i in 0 until items.length()) {
                val item = items.getJSONObject(i)
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        item.str("label"),
                        color = Faint,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(4.dp))
                    WeatherGlyph(
                        kind = item.str("icon", "cloud"),
                        isDay = item.optBoolean("is_day", true),
                        tint = accent,
                        modifier = Modifier.size(22.dp),
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        item.str("value"),
                        color = Ink,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        maxLines = 1,
                    )
                }
            }
        }
    }
}

/* ----------------------------- note ----------------------------- */

/** Long text such as the PC clipboard: readable body copy, not a list row. */
@Composable
private fun NoteCard(block: JSONObject, modifier: Modifier) {
    GlassPanel(
        modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 16.dp),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                block.str("label").uppercase(),
                color = Muted,
                fontSize = 10.5.sp,
                letterSpacing = 2.sp,
                modifier = Modifier.weight(1f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            val meta = block.str("meta")
            if (meta.isNotBlank()) {
                Text(meta, color = Faint, fontSize = 10.sp, maxLines = 1)
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(
            block.str("text"),
            color = Ink,
            fontSize = 15.sp,
            lineHeight = 21.sp,
            maxLines = 7,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/* ----------------------------- list ----------------------------- */

@Composable
private fun ListCard(
    block: JSONObject,
    accent: Color,
    endpoint: String,
    modifier: Modifier,
    onAction: (String, JSONObject?) -> Unit,
) {
    val compact = LocalCompactLayout.current
    val items = block.arr("items")
    GlassPanel(modifier.fillMaxWidth(), contentPadding = PaddingValues(horizontal = 18.dp, vertical = 16.dp)) {
        val title = block.str("title")
        if (title.isNotBlank()) {
            Text(title.uppercase(), color = Muted, fontSize = 10.5.sp, letterSpacing = 2.sp)
            Spacer(Modifier.height(8.dp))
        }
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            // A long single-column list (open windows, wake targets) wastes half
            // the panel in landscape, so split it once there is room.
            val twoUp = items.length() > 5 && maxWidth >= 620.dp
            val half = (items.length() + 1) / 2
            if (twoUp) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    ListColumn(items, 0, half, accent, endpoint, compact, onAction, Modifier.weight(1f))
                    ListColumn(items, half, items.length(), accent, endpoint, compact, onAction, Modifier.weight(1f))
                }
            } else {
                ListColumn(items, 0, items.length(), accent, endpoint, compact, onAction, Modifier.fillMaxWidth())
            }
        }
    }
}

@Composable
private fun ListColumn(
    items: JSONArray,
    from: Int,
    to: Int,
    accent: Color,
    endpoint: String,
    compact: Boolean,
    onAction: (String, JSONObject?) -> Unit,
    modifier: Modifier,
) {
    Column(modifier) {
        for (i in from until to) {
            if (i > from) {
                Box(Modifier.fillMaxWidth().height(1.dp).background(Color(0x0FFFFFFF)))
            }
            ListRow(items.getJSONObject(i), accent, endpoint, compact, onAction)
        }
    }
}

@Composable
private fun ListRow(
    item: JSONObject,
    accent: Color,
    endpoint: String,
    compact: Boolean,
    onAction: (String, JSONObject?) -> Unit,
) {
    val action = item.optString("action")
    val hasAction = action.isNotBlank()
    Row(
        Modifier
            .fillMaxWidth()
            .then(
                if (hasAction) {
                    Modifier.clickable {
                        onAction(
                            action,
                            JSONObject()
                                .put("url", item.optString("url"))
                                .put("id", item.optString("id")),
                        )
                    }
                } else {
                    Modifier
                }
            )
            .padding(vertical = if (compact) 7.dp else 11.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val image = item.optString("image")
        val icon = item.optString("icon")
        if (image.isNotBlank()) {
            AsyncImage(
                model = endpoint.trimEnd('/') + image,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .size(30.dp)
                    .clip(RoundedCornerShape(8.dp)),
            )
            Spacer(Modifier.width(12.dp))
        } else if (icon.isNotBlank()) {
            WeatherGlyph(
                kind = icon,
                isDay = true,
                tint = accent,
                modifier = Modifier.size(26.dp).padding(end = 2.dp),
            )
            Spacer(Modifier.width(12.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(item.str("title"), color = Ink, fontSize = 15.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            val sub = item.str("sub")
            if (sub.isNotBlank()) {
                Text(sub, color = Faint, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        val value = item.str("value")
        if (value.isNotBlank()) {
            Spacer(Modifier.width(10.dp))
            Text(
                value,
                color = if (hasAction) accent else Ink.copy(alpha = 0.86f),
                fontSize = if (hasAction) 12.5.sp else 15.sp,
                fontWeight = if (hasAction) FontWeight.Bold else FontWeight.Medium,
                letterSpacing = if (hasAction) 1.4.sp else 0.sp,
                maxLines = 1,
            )
        }
    }
}

/* ----------------------------- controls ----------------------------- */

@Composable
private fun ActionTile(
    item: JSONObject,
    accent: Color,
    modifier: Modifier = Modifier,
    onPress: (String) -> Unit,
) {
    val id = item.str("id")
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val flash = rememberTapFlash(pressed)
    Column(
        modifier
            .fillMaxHeight()
            .clip(RoundedCornerShape(16.dp))
            .background(if (flash) accent.copy(alpha = 0.30f) else Color(0x14FFFFFF))
            .clickable(interactionSource = interaction, indication = null) { onPress(id) }
            .padding(horizontal = 6.dp, vertical = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            imageVector = iconFor(item.str("icon")),
            contentDescription = null,
            tint = accent,
            modifier = Modifier.size(18.dp),
        )
        Spacer(Modifier.height(5.dp))
        Text(
            item.str("label"),
            color = Ink,
            fontSize = 10.5.sp,
            maxLines = 2,
            lineHeight = 12.sp,
            textAlign = TextAlign.Center,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun ControlsCard(
    block: JSONObject,
    accent: Color,
    modifier: Modifier = Modifier,
    onPress: (String) -> Unit,
) {
    val items = block.arr("items")
    val transport = block.str("style") == "transport"
    val stack = block.str("style") == "stack"
    val bare = LocalBareCards.current
    GlassPanel(
        if (bare) modifier.fillMaxSize() else modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = if (transport) 20.dp else 16.dp),
    ) {
        if (block.str("style") == "grid") {
            val rows = (items.length() + 1) / 2
            Column(
                if (bare) Modifier.fillMaxSize() else Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                for (row in 0 until rows) {
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .then(if (bare) Modifier.weight(1f) else Modifier.height(46.dp)),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        for (slot in 0 until 2) {
                            val index = row * 2 + slot
                            if (index < items.length()) {
                                ActionTile(
                                    items.getJSONObject(index),
                                    accent,
                                    Modifier.weight(1f),
                                ) { onPress(it) }
                            } else {
                                Spacer(Modifier.weight(1f))
                            }
                        }
                    }
                }
            }
            return@GlassPanel
        }
        if (stack) {
            Column(
                if (bare) Modifier.fillMaxSize() else Modifier,
                verticalArrangement = if (bare) Arrangement.SpaceBetween else Arrangement.spacedBy(8.dp),
            ) {
                for (i in 0 until items.length()) {
                    val item = items.getJSONObject(i)
                    val id = item.str("id")
                    val rowInteraction = remember { MutableInteractionSource() }
                    val rowPressed by rowInteraction.collectIsPressedAsState()
                    val rowFlash = rememberTapFlash(rowPressed)
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(14.dp))
                            .background(if (rowFlash) accent.copy(alpha = 0.30f) else Color(0x14FFFFFF))
                            .clickable(
                                interactionSource = rowInteraction,
                                indication = null,
                            ) { onPress(id) }
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            imageVector = iconFor(item.str("icon")),
                            contentDescription = null,
                            tint = accent,
                            modifier = Modifier.size(16.dp),
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(item.str("label"), color = Ink, fontSize = 12.5.sp)
                    }
                }
            }
            return@GlassPanel
        }
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
    "play" -> Icons.Rounded.PlayArrow
    "play_pause" -> Icons.Rounded.PlayArrow
    "pause" -> Icons.Rounded.Pause
    "mic" -> Icons.Rounded.Mic
    "volume_up" -> Icons.Rounded.VolumeUp
    "volume_down" -> Icons.Rounded.VolumeDown
    "mute" -> Icons.Rounded.VolumeOff
    "lock" -> Icons.Rounded.Lock
    "thermo" -> Icons.Rounded.Thermostat
    "screen_off" -> Icons.Rounded.PowerSettingsNew
    "power" -> Icons.Rounded.PowerSettingsNew
    "desktop" -> Icons.Rounded.DesktopWindows
    "grid" -> Icons.Rounded.GridView
    "sync" -> Icons.Rounded.Sync
    "graphic_eq" -> Icons.Rounded.GraphicEq
    "music_note" -> Icons.Rounded.MusicNote
    "straighten" -> Icons.Rounded.Straighten
    "refresh" -> Icons.Rounded.Refresh
    "camera" -> Icons.Rounded.PhotoCamera
    else -> Icons.Rounded.Circle
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
    val flash = rememberTapFlash(pressed)
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
        Box(
            Modifier
                .matchParentSize()
                .clip(CircleShape)
                .background(if (flash) Color(0x44FFFFFF) else Color.Transparent)
        )
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
    val flash = rememberTapFlash(pressed)
    val shape = RoundedCornerShape(18.dp)
    Column(
        modifier
            .clip(shape)
            .background(
                Brush.linearGradient(
                    if (flash) {
                        listOf(accent.copy(alpha = 0.32f), accent.copy(alpha = 0.18f))
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

/**
 * Lead story + two columns of briefs on a landscape panel: one headline to
 * catch the eye, the rest scannable, and nothing hidden below the fold.
 */
@Composable
private fun NewsBlock(
    block: JSONObject,
    accent: Color,
    onAction: (String, JSONObject?) -> Unit,
) {
    val items = block.arr("items")
    if (items.length() == 0) return
    val title = block.str("title")

    // Balance the last page instead of leaving it with one or two stories:
    // 20 stories become 7 + 7 + 6, not 9 + 9 + 2.
    val pageCount = ((items.length() + 8) / 9).coerceAtLeast(1)
    val perPage = ((items.length() + pageCount - 1) / pageCount).coerceAtLeast(1)
    var page by remember { mutableStateOf(0) }
    LaunchedEffect(items.length()) { page = 0 }
    val startIndex = (page * perPage).coerceAtMost((items.length() - 1).coerceAtLeast(0))

    fun open(item: JSONObject) {
        onAction("open", JSONObject().put("url", item.optString("url")))
    }

    Column(Modifier.fillMaxWidth()) {
        if (title.isNotBlank()) {
            Row(
                Modifier.fillMaxWidth().padding(start = 4.dp, end = 4.dp, bottom = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    title.uppercase(),
                    color = Muted,
                    fontSize = 10.5.sp,
                    letterSpacing = 2.sp,
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    "${items.length()} STORIES",
                    color = Faint,
                    fontSize = 9.sp,
                    letterSpacing = 1.4.sp,
                )
                if (pageCount > 1) {
                    Spacer(Modifier.width(10.dp))
                    PagerArrow("‹", enabled = page > 0, accent = accent) { page-- }
                    Box(
                        Modifier
                            .padding(horizontal = 4.dp)
                            .clip(RoundedCornerShape(50))
                            .background(accent.copy(alpha = 0.16f))
                            .border(1.dp, accent.copy(alpha = 0.38f), RoundedCornerShape(50))
                            .padding(horizontal = 10.dp, vertical = 4.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            "${page + 1} / $pageCount",
                            color = accent,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            letterSpacing = 0.5.sp,
                        )
                    }
                    PagerArrow("›", enabled = page < pageCount - 1, accent = accent) { page++ }
                }
            }
        }

        BoxWithConstraints(Modifier.fillMaxWidth()) {
            if (maxWidth < 600.dp) {
                // portrait / narrow: simple stacked cards
                val endIndex = (startIndex + perPage).coerceAtMost(items.length())
                for (i in startIndex until endIndex) {
                    val item = items.getJSONObject(i)
                    NewsCard(item, accent) { open(item) }
                    Spacer(Modifier.height(10.dp))
                }
            } else {
                // 8 briefs = 4 rows, which fits the short landscape panel; the
                // rest stay in the feed data for the next refresh
                val endIndex = (startIndex + perPage).coerceAtMost(items.length())
                val briefCount = (endIndex - startIndex - 1).coerceAtLeast(0).coerceAtMost(8)
                val rest = (1..briefCount).map { items.getJSONObject(startIndex + it) }
                val half = (rest.size + 1) / 2
                val rows = (rest.size + 1) / 2
                // a three-row minimum keeps the lead card tall enough for a
                // five-line headline on short final pages
                val leadHeight = (rows.coerceAtLeast(3) * 64).dp
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    LeadCard(
                        items.getJSONObject(startIndex),
                        accent,
                        Modifier.weight(1.08f).height(leadHeight),
                    ) { open(items.getJSONObject(startIndex)) }
                    BriefColumn(rest.take(half), accent, Modifier.weight(1f)) { open(it) }
                    BriefColumn(rest.drop(half), accent, Modifier.weight(1f)) { open(it) }
                }
            }
        }
    }
}

@Composable
private fun PagerArrow(label: String, enabled: Boolean, accent: Color, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val flash = rememberTapFlash(pressed)
    Box(
        Modifier
            .size(48.dp)
            .then(if (enabled) Modifier.pressable(interaction, onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier
                .size(38.dp)
                .clip(CircleShape)
                .background(
                    when {
                        flash -> accent.copy(alpha = 0.45f)
                        enabled -> accent.copy(alpha = 0.18f)
                        else -> Color(0x0AFFFFFF)
                    }
                )
                .border(
                    1.dp,
                    if (enabled) accent.copy(alpha = 0.45f) else Color(0x0FFFFFFF),
                    CircleShape,
                ),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                label,
                color = if (enabled) accent else Faint.copy(alpha = 0.45f),
                fontSize = 20.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun LeadCard(item: JSONObject, accent: Color, modifier: Modifier, onOpen: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val flash = rememberTapFlash(pressed)
    val source = item.optString("source")
    val image = item.optString("image")

    Box(modifier) {
        GlassPanel(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                NewsMark(image, source, accent, 26.dp)
                Spacer(Modifier.width(9.dp))
                Text(
                    source.uppercase(),
                    color = accent.copy(alpha = 0.95f),
                    fontSize = 9.5.sp,
                    letterSpacing = 1.3.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Text(item.optString("ago"), color = Faint, fontSize = 9.5.sp)
            }
            Spacer(Modifier.height(10.dp))
            Text(
                item.str("title"),
                color = Ink,
                fontSize = 18.sp,
                lineHeight = 23.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 5,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.weight(1f))
            Box(
                Modifier
                    .width(34.dp)
                    .height(2.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(accent)
            )
        }
        if (flash) {
            Box(
                Modifier
                    .matchParentSize()
                    .clip(RoundedCornerShape(28.dp))
                    .background(accent.copy(alpha = 0.10f))
            )
        }
        Box(
            Modifier
                .matchParentSize()
                .pressable(interaction, onOpen)
        )
    }
}

@Composable
private fun BriefColumn(
    items: List<JSONObject>,
    accent: Color,
    modifier: Modifier,
    onOpen: (JSONObject) -> Unit,
) {
    Column(modifier) {
        items.forEachIndexed { index, item ->
            BriefRow(item, accent) { onOpen(item) }
            if (index != items.lastIndex) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(1.dp)
                        .background(Color(0x12FFFFFF))
                )
            }
        }
    }
}

@Composable
private fun BriefRow(item: JSONObject, accent: Color, onOpen: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val flash = rememberTapFlash(pressed)
    val source = item.optString("source")
    val image = item.optString("image")

    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(if (flash) accent.copy(alpha = 0.16f) else Color.Transparent)
            .pressable(interaction, onOpen)
            .padding(horizontal = 8.dp, vertical = 7.dp),
        verticalAlignment = Alignment.Top,
    ) {
        NewsMark(image, source, accent, 18.dp)
        Spacer(Modifier.width(9.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    source.uppercase(),
                    color = accent.copy(alpha = 0.85f),
                    fontSize = 8.5.sp,
                    letterSpacing = 1.1.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Text(item.optString("ago"), color = Faint, fontSize = 8.5.sp)
            }
            Spacer(Modifier.height(3.dp))
            Text(
                item.str("title"),
                color = Ink.copy(alpha = 0.94f),
                fontSize = 12.sp,
                lineHeight = 14.5.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun NewsMark(image: String, source: String, accent: Color, size: androidx.compose.ui.unit.Dp) {
    Box(
        Modifier
            .size(size)
            .clip(RoundedCornerShape(size / 4))
            .background(accent.copy(alpha = 0.12f)),
        contentAlignment = Alignment.Center,
    ) {
        if (image.isNotBlank()) {
            AsyncImage(
                model = image,
                contentDescription = source,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize().padding(size / 8),
            )
        } else {
            Text(
                source.take(1).uppercase(),
                color = accent,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
            )
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
        NewsMark(image, source, accent, 44.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    source.uppercase(),
                    color = accent,
                    fontSize = 9.sp,
                    letterSpacing = 1.3.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Text(item.optString("ago"), color = Faint, fontSize = 9.sp)
            }
            Spacer(Modifier.height(4.dp))
            Text(
                item.str("title"),
                color = Ink,
                fontSize = 15.sp,
                lineHeight = 19.sp,
                fontWeight = FontWeight.Medium,
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
            fontSize = 10.5.sp,
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
                textStyle = TextStyle(color = Ink, fontSize = 14.sp),
                cursorBrush = SolidColor(accent),
                maxLines = 3,
                decorationBox = { inner ->
                    if (text.isEmpty()) {
                        Text(
                            block.str("placeholder").ifBlank { "Type here…" },
                            color = Faint,
                            fontSize = 14.sp,
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
                .height(46.dp)
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

/* ----------------------------- touchpad ----------------------------- */

/**
 * A big, quiet trackpad: one finger moves, a tap clicks, two fingers scroll.
 * Every pointer change is consumed so the deck's page swipe never steals a drag.
 */
@Composable
private fun TouchpadCard(
    block: JSONObject,
    accent: Color,
    modifier: Modifier,
    onAction: (String, JSONObject?) -> Unit,
) {
    val sensitivity = block.num("sensitivity", 1.0).toFloat().coerceIn(0.25f, 3f)
    var dot by remember { mutableStateOf(Offset.Unspecified) }
    var touched by remember { mutableStateOf(false) }
    var keyboardOpen by remember { mutableStateOf(false) }
    var text by remember { mutableStateOf("") }
    val focusRequester = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val focusManager = LocalFocusManager.current

    LaunchedEffect(keyboardOpen) {
        if (keyboardOpen) {
            delay(140)
            focusRequester.requestFocus()
            keyboard?.show()
        }
    }

    GlassPanel(modifier.fillMaxSize(), contentPadding = PaddingValues(0.dp)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(start = 18.dp, end = 18.dp, top = 13.dp, bottom = 7.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    block.str("label").uppercase().ifBlank { "TOUCHPAD" },
                    color = Muted,
                    fontSize = 10.5.sp,
                    letterSpacing = 2.sp,
                    modifier = Modifier.weight(1f),
                )
                Row(
                    Modifier
                        .height(34.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(
                            if (keyboardOpen) accent.copy(alpha = 0.18f) else Color(0x14FFFFFF)
                        )
                        .border(
                            1.dp,
                            if (keyboardOpen) accent.copy(alpha = 0.5f) else Color(0x1FFFFFFF),
                            RoundedCornerShape(10.dp),
                        )
                        .clickable {
                            if (keyboardOpen) {
                                keyboardOpen = false
                                text = ""
                                focusManager.clearFocus()
                                keyboard?.hide()
                            } else {
                                keyboardOpen = true
                            }
                        }
                        .padding(horizontal = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(
                        Icons.Rounded.Keyboard,
                        contentDescription = "Keyboard",
                        tint = if (keyboardOpen) accent else Muted,
                        modifier = Modifier.size(15.dp),
                    )
                    Spacer(Modifier.width(5.dp))
                    Text(
                        "KEYBOARD",
                        color = if (keyboardOpen) Ink else Muted,
                        fontSize = 8.5.sp,
                        letterSpacing = 1.1.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Spacer(Modifier.width(10.dp))
                Text(
                    String.format("%.1fx", sensitivity),
                    color = Faint,
                    fontSize = 10.sp,
                )
            }
            if (keyboardOpen) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        Modifier
                            .weight(1f)
                            .height(46.dp)
                            .clip(RoundedCornerShape(14.dp))
                            .background(Color(0x1F000000))
                            .border(1.dp, Color(0x22FFFFFF), RoundedCornerShape(14.dp))
                            .padding(horizontal = 14.dp),
                        contentAlignment = Alignment.CenterStart,
                    ) {
                        BasicTextField(
                            value = text,
                            onValueChange = { text = it },
                            textStyle = TextStyle(color = Ink, fontSize = 15.sp),
                            cursorBrush = SolidColor(accent),
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                            keyboardActions = KeyboardActions(
                                onSend = {
                                    if (text.isNotEmpty()) {
                                        onAction("type", JSONObject().put("text", text))
                                        text = ""
                                    }
                                },
                            ),
                            modifier = Modifier.fillMaxWidth().focusRequester(focusRequester),
                            decorationBox = { inner ->
                                if (text.isEmpty()) {
                                    Text("Type on the PC…", color = Faint, fontSize = 13.sp)
                                }
                                inner()
                            },
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    TouchButton("SEND", accent, Modifier.width(82.dp)) {
                        if (text.isNotEmpty()) {
                            onAction("type", JSONObject().put("text", text))
                            text = ""
                        }
                    }
                    Spacer(Modifier.width(6.dp))
                    TouchButton("DONE", accent, Modifier.width(82.dp)) {
                        keyboardOpen = false
                        text = ""
                        focusManager.clearFocus()
                        keyboard?.hide()
                    }
                }
            } else {
            Box(
                Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(horizontal = 10.dp)
                    .clip(RoundedCornerShape(18.dp))
                    .background(Color(0x1F000000))
                    .border(1.dp, Color(0x14FFFFFF), RoundedCornerShape(18.dp))
                    .pointerInput(sensitivity) {
                        awaitEachGesture {
                            val down = awaitFirstDown(requireUnconsumed = false)
                            down.consume()
                            touched = true
                            var last = down.position
                            var lastSent = down.uptimeMillis
                            var ax = 0f
                            var ay = 0f
                            var travel = 0f
                            var scrollY = down.position.y
                            var twoFinger = false
                            dot = down.position
                            while (true) {
                                val event = awaitPointerEvent()
                                val pressed = event.changes.filter { it.pressed }
                                if (pressed.isEmpty()) {
                                    if (!twoFinger && travel < 14f) {
                                        onAction("tap", JSONObject().put("button", "left"))
                                    }
                                    dot = Offset.Unspecified
                                    break
                                }
                                if (pressed.size >= 2) {
                                    twoFinger = true
                                    val avgY = pressed.map { it.position.y }.average().toFloat()
                                    val dy = avgY - scrollY
                                    scrollY = avgY
                                    if (abs(dy) > 0.7f) {
                                        onAction("scroll", JSONObject().put("dy", -dy / 3f))
                                    }
                                    dot = pressed.first().position
                                    pressed.forEach { it.consume() }
                                    continue
                                }
                                val change = pressed.first()
                                val delta = change.position - last
                                last = change.position
                                if (delta.getDistance() > 0f) {
                                    travel += delta.getDistance()
                                    ax += delta.x
                                    ay += delta.y
                                    dot = change.position
                                    val now = change.uptimeMillis
                                    if (now - lastSent >= 16) {
                                        lastSent = now
                                        if (abs(ax) >= 0.5f || abs(ay) >= 0.5f) {
                                            onAction(
                                                "move",
                                                JSONObject()
                                                    .put("dx", ax * sensitivity)
                                                    .put("dy", ay * sensitivity),
                                            )
                                            ax = 0f
                                            ay = 0f
                                        }
                                    }
                                }
                                change.consume()
                                event.changes.forEach { it.consume() }
                            }
                        }
                    },
                contentAlignment = Alignment.Center,
            ) {
                val hint = block.str("hint")
                if (hint.isNotBlank() && !touched) {
                    Text(
                        hint,
                        color = Faint,
                        fontSize = 12.sp,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        modifier = Modifier.padding(horizontal = 30.dp),
                    )
                }
                Canvas(Modifier.fillMaxSize()) {
                    val p = dot
                    if (p != Offset.Unspecified) {
                        drawCircle(accent.copy(alpha = 0.20f), radius = 24.dp.toPx(), center = p)
                        drawCircle(accent.copy(alpha = 0.8f), radius = 3.dp.toPx(), center = p)
                    }
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                TouchButton("LEFT", accent, Modifier.weight(1f)) {
                    onAction("tap", JSONObject().put("button", "left"))
                }
                TouchButton("RIGHT", accent, Modifier.weight(1f)) {
                    onAction("tap", JSONObject().put("button", "right"))
                }
                TouchButton("MIDDLE", accent, Modifier.weight(1f)) {
                    onAction("tap", JSONObject().put("button", "middle"))
                }
            }
            }
        }
    }
}

@Composable
private fun TouchButton(label: String, accent: Color, modifier: Modifier, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val flash = rememberTapFlash(pressed)
    Box(
        modifier
            .height(38.dp)
            .clip(RoundedCornerShape(11.dp))
            .background(if (flash) accent.copy(alpha = 0.28f) else Color(0x14FFFFFF))
            .border(1.dp, Color(0x1FFFFFFF), RoundedCornerShape(11.dp))
            .pressable(interaction, onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = if (flash) Ink else Muted,
            fontSize = 11.5.sp,
            letterSpacing = 1.4.sp,
            fontWeight = FontWeight.SemiBold,
        )
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
    GlassPanel(Modifier.fillMaxWidth()) {
        val title = block.str("title")
        if (title.isNotBlank()) {
            Text(title.uppercase(), color = Muted, fontSize = 10.5.sp, letterSpacing = 2.sp)
            Spacer(Modifier.height(14.dp))
        }
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            // a tablet has room for more tiles in the same two rows
            val auto = (maxWidth.value / 190f).toInt().coerceIn(3, 6)
            val cols = maxOf(columns, auto).coerceAtMost(items.length().coerceAtLeast(1))
            Column(Modifier.fillMaxWidth()) {
                var index = 0
                while (index < items.length()) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        for (c in 0 until cols) {
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
            .padding(vertical = if (compact) 12.dp else 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        AsyncImage(
            model = iconUrl,
            contentDescription = label,
            contentScale = ContentScale.Crop,
            modifier = Modifier
                .size(if (compact) 44.dp else 54.dp)
                .clip(RoundedCornerShape(9.dp)),
        )
        Spacer(Modifier.height(if (compact) 7.dp else 10.dp))
        Text(
            label,
            color = Ink.copy(alpha = 0.9f),
            fontSize = 12.5.sp,
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

/* ----------------------------- camera ----------------------------- */

private data class PcCamera(val installed: Boolean, val name: String?)

/** What the Windows side reports: whether the filter is set up and our camera's name. */
private fun fetchPcCamera(endpoint: String, model: String): PcCamera? {
    val base = when {
        endpoint.startsWith("http://") || endpoint.startsWith("https://") -> endpoint
        else -> "http://$endpoint"
    }.trimEnd('/')
    val conn = runCatching {
        URL("$base/api/camera/virtual").openConnection() as HttpURLConnection
    }.getOrNull() ?: return null
    return try {
        conn.connectTimeout = 2500
        conn.readTimeout = 2500
        conn.setRequestProperty("Accept", "application/json")
        if (conn.responseCode != 200) return null
        val json = JSONObject(conn.inputStream.bufferedReader().readText())
        var name: String? = null
        json.optJSONArray("cameras")?.let { cameras ->
            for (i in 0 until cameras.length()) {
                val camera = cameras.getJSONObject(i)
                if (camera.optString("device").equals(model, ignoreCase = true)) {
                    name = camera.optString("name").ifBlank { null }
                }
            }
        }
        PcCamera(json.optBoolean("installed", false), name)
    } catch (_: Exception) {
        null
    } finally {
        conn.disconnect()
    }
}

private fun openAppSettings(context: Context) {
    runCatching {
        context.startActivity(
            Intent(
                Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.fromParts("package", context.packageName, null),
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}

@Composable
private fun CameraCard(
    block: JSONObject,
    accent: Color,
    endpoint: String,
    modifier: Modifier,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val compact = LocalCompactLayout.current
    var granted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
        )
    }
    var denied by rememberSaveable { mutableStateOf(false) }
    val permission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { allowed ->
        granted = allowed
        denied = !allowed
    }
    var micGranted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED
        )
    }
    var audioOn by rememberSaveable { mutableStateOf(true) }
    val micPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { allowed ->
        micGranted = allowed
        if (allowed) audioOn = true
    }
    val mic = remember(endpoint) { MicStream(endpoint) }

    var lens by rememberSaveable { mutableIntStateOf(CameraSelector.LENS_FACING_BACK) }
    var live by remember { mutableStateOf(false) }
    var previewPaused by remember { mutableStateOf(false) }
    val liveRef = remember { AtomicBoolean(false) }
    var previewView by remember { mutableStateOf<PreviewView?>(null) }
    var provider by remember { mutableStateOf<ProcessCameraProvider?>(null) }
    var hasFront by remember { mutableStateOf(true) }
    var hasBack by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var retry by remember { mutableIntStateOf(0) }
    var fps by remember { mutableIntStateOf(0) }
    var torch by remember { mutableStateOf(false) }
    var cameraRef by remember { mutableStateOf<Camera?>(null) }
    var pcCamera by remember { mutableStateOf<PcCamera?>(null) }
    val resolutions = remember {
        listOf(
            android.util.Size(1920, 1080),
            android.util.Size(1280, 720),
            android.util.Size(640, 480),
        )
    }
    val resolutionLabels = remember { listOf("1080p", "720p", "480p") }
    var resolutionIndex by rememberSaveable { mutableIntStateOf(1) }

    // Tell the user which Windows camera this phone feeds; it is the whole point
    // of the module once the PC side is set up.
    LaunchedEffect(endpoint) {
        while (true) {
            pcCamera = withContext(Dispatchers.IO) { fetchPcCamera(endpoint, Build.MODEL) }
            delay(4000)
        }
    }

    val stream = remember(endpoint) { CameraStream(endpoint) }
    val analyzer = remember { Executors.newSingleThreadExecutor() }
    val lastFrame = remember { AtomicLong(0L) }

    LaunchedEffect(Unit) {
        while (true) {
            delay(1000)
            fps = stream.takeCount()
        }
    }

    // The main link reconnects on its own; the camera socket has to do the
    // same or the deck says LIVE while sending nothing.
    LaunchedEffect(live) {
        while (live) {
            if (!stream.isOpen()) stream.start()
            delay(1500)
        }
    }

    // Audio rides along with the camera: same start, same stop.
    LaunchedEffect(live, audioOn, micGranted) {
        if (live && audioOn && micGranted) mic.start() else mic.stop()
    }
    LaunchedEffect(live, audioOn, micGranted) {
        while (live && audioOn && micGranted) {
            mic.ensure()
            delay(1500)
        }
    }

    // A phone left on this screen should not keep the sensor and preview hot.
    LaunchedEffect(live, previewPaused) {
        if (live || previewPaused) return@LaunchedEffect
        delay(60_000)
        previewPaused = true
    }

    LaunchedEffect(granted, lens, previewView, resolutionIndex, retry, previewPaused) {
        val view = previewView ?: return@LaunchedEffect
        if (!granted) return@LaunchedEffect
        if (previewPaused) {
            runCatching { provider?.unbindAll() }
            cameraRef = null
            return@LaunchedEffect
        }
        val camera = runCatching { awaitCameraProvider(context) }.getOrNull()
        if (camera == null) {
            error = "Camera unavailable"
            return@LaunchedEffect
        }
        provider = camera
        hasFront = camera.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)
        hasBack = camera.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA)
        val selector = when {
            lens == CameraSelector.LENS_FACING_FRONT && hasFront -> CameraSelector.DEFAULT_FRONT_CAMERA
            lens == CameraSelector.LENS_FACING_BACK && hasBack -> CameraSelector.DEFAULT_BACK_CAMERA
            hasBack -> CameraSelector.DEFAULT_BACK_CAMERA
            hasFront -> CameraSelector.DEFAULT_FRONT_CAMERA
            else -> null
        }
        if (selector == null) {
            error = "No camera found"
            return@LaunchedEffect
        }

        val preview = Preview.Builder().build().also {
            it.setSurfaceProvider(view.surfaceProvider)
        }
        val analysis = ImageAnalysis.Builder()
            .setTargetResolution(resolutions[resolutionIndex])
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
        analysis.setAnalyzer(analyzer) { image ->
            if (!liveRef.get()) {
                image.close()
                return@setAnalyzer
            }
            val now = SystemClock.elapsedRealtime()
            if (now - lastFrame.get() < 33) {
                image.close()
                return@setAnalyzer
            }
            lastFrame.set(now)
            try {
                val rotation = image.imageInfo.rotationDegrees
                image.toJpeg(50)?.let { jpeg -> stream.send(jpeg, rotation) }
            } catch (_: Exception) {
                // a dropped frame is fine; keep the preview smooth
            } finally {
                image.close()
            }
        }

        withContext(Dispatchers.Main) {
            runCatching {
                camera.unbindAll()
                val bound = camera.bindToLifecycle(lifecycleOwner, selector, preview, analysis)
                cameraRef = bound
                bound.cameraControl.enableTorch(
                    torch && lens == CameraSelector.LENS_FACING_BACK
                )
                error = null
            }.onFailure { error = it.message ?: "Camera failed" }
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            runCatching { provider?.unbindAll() }
            analyzer.shutdown()
            stream.close()
            mic.stop()
        }
    }

    GlassPanel(modifier.fillMaxSize()) {
        BoxWithConstraints(Modifier.fillMaxSize()) {
            val wide = maxWidth > maxHeight * 1.15f
            val dense = maxHeight < 330.dp
            val gap = if (dense) 12.dp else 20.dp
            val corner = if (dense) 16.dp else 18.dp

            val preview: @Composable (Modifier) -> Unit = { paneModifier ->
                Box(
                    paneModifier
                        .clip(RoundedCornerShape(corner))
                        .background(Color(0xFF05070C))
                        .border(
                            1.dp,
                            if (live) Color(0x555BE49B) else Color(0x1AFFFFFF),
                            RoundedCornerShape(corner),
                        )
                        .semantics {
                            contentDescription = if (live) {
                                "Live camera preview, sending to the PC"
                            } else {
                                "Camera preview"
                            }
                        },
                ) {
                    if (granted) {
                        AndroidView(
                            factory = { ctx ->
                                PreviewView(ctx).apply {
                                    scaleType = PreviewView.ScaleType.FILL_CENTER
                                    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                                }
                            },
                            modifier = Modifier.fillMaxSize(),
                            update = { previewView = it },
                        )
                    } else {
                        Column(
                            Modifier.align(Alignment.Center).padding(24.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                        ) {
                            Icon(
                                Icons.Rounded.Lock,
                                contentDescription = null,
                                tint = Muted,
                                modifier = Modifier.size(26.dp),
                            )
                            Spacer(Modifier.height(10.dp))
                            Text(
                                "Camera access needed",
                                color = Ink,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.SemiBold,
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                "Nothing leaves this phone until you start sending.",
                                color = Muted,
                                fontSize = 11.5.sp,
                                textAlign = TextAlign.Center,
                            )
                        }
                    }

                    if (previewPaused && !live) {
                        Box(
                            Modifier
                                .fillMaxSize()
                                .background(Color(0xF205070C))
                                .clickable { previewPaused = false },
                            contentAlignment = Alignment.Center,
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(
                                    Icons.Rounded.PowerSettingsNew,
                                    contentDescription = null,
                                    tint = Color(0xFF7CE7FF),
                                    modifier = Modifier.size(26.dp),
                                )
                                Spacer(Modifier.height(8.dp))
                                Text(
                                    "Preview paused to keep the phone cool",
                                    color = Ink,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.SemiBold,
                                )
                                Spacer(Modifier.height(3.dp))
                                Text(
                                    "Tap to resume",
                                    color = Muted,
                                    fontSize = 11.sp,
                                )
                            }
                        }
                    }

                    CameraBadge(
                        live = live,
                        fps = fps,
                        granted = granted,
                        modifier = Modifier.align(Alignment.TopStart).padding(12.dp),
                    )

                    if (granted) {
                        // scrim so the PC name stays readable over any image
                        Box(
                            Modifier
                                .align(Alignment.BottomCenter)
                                .fillMaxWidth()
                                .height(72.dp)
                                .background(
                                    Brush.verticalGradient(
                                        listOf(Color.Transparent, Color(0xAA05070C))
                                    )
                                ),
                        )
                        PcCameraBar(
                            state = pcCamera,
                            live = live,
                            modifier = Modifier
                                .align(Alignment.BottomStart)
                                .padding(12.dp),
                        )
                    }
                }
            }

            val controls: @Composable (Modifier, Boolean) -> Unit = { panelModifier, footer ->
                val body: @Composable (Modifier, Boolean) -> Unit = { bodyModifier, expand ->
                    Column(bodyModifier) {
                        Text(
                            block.str("title").ifBlank { "Phone camera" },
                            color = Ink,
                            fontSize = if (dense) 17.sp else 20.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Spacer(Modifier.height(2.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            val needsSettings = !granted && denied
                            Text(
                                error ?: when {
                                    needsSettings -> "Permission denied — open Settings"
                                    !granted -> "Allow the camera to see a preview"
                                    live && audioOn && micGranted -> "Your PC is receiving this view and sound"
                                    live -> "Your PC is receiving this view"
                                    else -> "Preview only - nothing leaves this phone"
                                },
                                color = when {
                                    error != null -> Color(0xFFFF8CA8)
                                    needsSettings -> Color(0xFF7CE7FF)
                                    live -> Color(0xFF5BE49B)
                                    else -> Muted
                                },
                                fontSize = 11.5.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier
                                    .weight(1f, fill = false)
                                    .clickable(enabled = needsSettings) { openAppSettings(context) },
                            )
                            if (error != null) {
                                Text(
                                    "Retry",
                                    color = Color(0xFF7CE7FF),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier
                                        .clickable {
                                            error = null
                                            retry += 1
                                        }
                                        .padding(start = 8.dp, top = 6.dp, bottom = 6.dp),
                                )
                            }
                        }

                        if (expand) Spacer(Modifier.weight(1f))

                        ControlLabel("LENS")
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Row(
                                Modifier
                                    .weight(1f)
                                    .selectableGroup(),
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                            ) {
                                SelectChip(
                                    "Back",
                                    selected = lens == CameraSelector.LENS_FACING_BACK,
                                    enabled = hasBack,
                                    modifier = Modifier.weight(1f),
                                ) {
                                    if (hasBack) {
                                        lens = CameraSelector.LENS_FACING_BACK
                                        error = null
                                    }
                                }
                                SelectChip(
                                    "Front",
                                    selected = lens == CameraSelector.LENS_FACING_FRONT,
                                    enabled = hasFront,
                                    modifier = Modifier.weight(1f),
                                ) {
                                    if (hasFront) {
                                        lens = CameraSelector.LENS_FACING_FRONT
                                        torch = false
                                        runCatching { cameraRef?.cameraControl?.enableTorch(false) }
                                        error = null
                                    }
                                }
                            }
                            Spacer(Modifier.width(6.dp))
                            TorchButton(
                                on = torch,
                                enabled = hasBack && lens == CameraSelector.LENS_FACING_BACK,
                            ) {
                                if (hasBack && lens == CameraSelector.LENS_FACING_BACK) {
                                    torch = !torch
                                    runCatching { cameraRef?.cameraControl?.enableTorch(torch) }
                                }
                            }
                            Spacer(Modifier.width(6.dp))
                            MicButton(
                                on = audioOn && micGranted,
                                enabled = granted,
                            ) {
                                if (!micGranted) {
                                    micPermission.launch(Manifest.permission.RECORD_AUDIO)
                                } else {
                                    audioOn = !audioOn
                                }
                            }
                        }

                        Spacer(Modifier.height(if (dense) 2.dp else 6.dp))
                        Row(verticalAlignment = Alignment.Bottom) {
                            ControlLabel("QUALITY")
                            Spacer(Modifier.weight(1f))
                            val size = resolutions[resolutionIndex]
                            Text(
                                if (live) {
                                    "${size.width}×${size.height} · $fps fps"
                                } else {
                                    "${size.width}×${size.height} · up to 30 fps"
                                },
                                color = Faint,
                                fontSize = 9.5.sp,
                                modifier = Modifier.padding(bottom = 2.dp),
                            )
                        }
                        Spacer(Modifier.height(2.dp))
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .selectableGroup(),
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            val hints = remember { listOf("Full HD", "HD", "Light") }
                            resolutionLabels.forEachIndexed { index, label ->
                                QualityChip(
                                    label = label,
                                    hint = hints[index],
                                    selected = resolutionIndex == index,
                                    modifier = Modifier.weight(1f),
                                ) {
                                    resolutionIndex = index
                                    error = null
                                }
                            }
                        }
                    }
                }

                if (footer) {
                    Box(panelModifier) {
                        body(Modifier.fillMaxSize().padding(bottom = 60.dp), true)
                        CameraPrimaryButton(
                            granted = granted,
                            live = live,
                            onAllow = { permission.launch(Manifest.permission.CAMERA) },
                            onToggle = {
                                live = !live
                                liveRef.set(live)
                                if (live) {
                                    previewPaused = false
                                    stream.start()
                                } else {
                                    stream.stop()
                                    fps = 0
                                }
                            },
                            modifier = Modifier.align(Alignment.BottomCenter),
                        )
                    }
                } else {
                    Column(panelModifier) {
                        body(Modifier.fillMaxWidth(), false)
                        Spacer(Modifier.height(8.dp))
                        CameraPrimaryButton(
                            granted = granted,
                            live = live,
                            onAllow = { permission.launch(Manifest.permission.CAMERA) },
                            onToggle = {
                                live = !live
                                liveRef.set(live)
                                if (live) {
                                    previewPaused = false
                                    stream.start()
                                } else {
                                    stream.stop()
                                    fps = 0
                                }
                            },
                        )
                    }
                }
            }

            if (wide) {
                Row(Modifier.fillMaxSize()) {
                    preview(Modifier.weight(1.2f).fillMaxHeight())
                    controls(
                        Modifier
                            .weight(1f)
                            .fillMaxHeight()
                            .padding(start = gap),
                        true,
                    )
                }
            } else {
                Column(Modifier.fillMaxSize()) {
                    preview(Modifier.weight(1f).fillMaxWidth())
                    Spacer(Modifier.height(if (dense) 8.dp else 12.dp))
                    controls(Modifier.fillMaxWidth(), false)
                }
            }
        }
    }
}

@Composable
private fun CameraBadge(
    live: Boolean,
    fps: Int,
    granted: Boolean,
    modifier: Modifier,
) {
    // Only a LIVE badge pulses; a READY one should not keep the GPU awake.
    val pulse = if (live) {
        val transition = rememberInfiniteTransition(label = "live-dot")
        val value by transition.animateFloat(
            initialValue = 1f,
            targetValue = 0.45f,
            animationSpec = infiniteRepeatable(
                animation = tween(900, easing = LinearEasing),
                repeatMode = RepeatMode.Reverse,
            ),
            label = "live-dot-alpha",
        )
        value
    } else {
        1f
    }
    val (text, tint) = when {
        !granted -> "NO ACCESS" to Color(0xFFFFC96B)
        live -> ("LIVE" + (if (fps > 0) " · $fps FPS" else "")) to Color(0xFF5BE49B)
        else -> "READY" to Color(0xFF7CE7FF)
    }
    Row(
        modifier
            .clip(RoundedCornerShape(50))
            .background(Color(0x99000000))
            .padding(horizontal = 9.dp, vertical = 4.dp)
            .semantics { stateDescription = text },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(tint.copy(alpha = pulse))
        )
        Spacer(Modifier.width(6.dp))
        Text(
            text,
            color = Color.White,
            fontSize = 9.sp,
            letterSpacing = 1.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

/** "PC sees: DeskGadget Camera - SM-G980F", or the reason it does not. */
@Composable
private fun PcCameraBar(state: PcCamera?, live: Boolean, modifier: Modifier) {
    if (state == null) return
    val name = state.name
    val (text, tint) = when {
        !state.installed -> "PC camera not set up" to Color(0xFFFFC96B)
        name != null -> name to Color(0xFF5BE49B)
        live -> "PC is connecting…" to Muted
        else -> "PC camera ready" to Muted
    }
    Row(
        modifier
            .clip(RoundedCornerShape(10.dp))
            .background(Color(0xB305070C))
            .padding(horizontal = 9.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            Icons.Rounded.DesktopWindows,
            contentDescription = null,
            tint = tint,
            modifier = Modifier.size(13.dp),
        )
        Spacer(Modifier.width(7.dp))
        Text(
            text,
            color = Color.White.copy(alpha = 0.92f),
            fontSize = 10.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun ControlLabel(text: String) {
    Text(
        text,
        color = Muted,
        fontSize = 9.5.sp,
        letterSpacing = 1.4.sp,
        modifier = Modifier.padding(bottom = 1.dp),
    )
}

@Composable
private fun SelectChip(
    label: String,
    selected: Boolean,
    enabled: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(12.dp)
    Box(
        modifier
            .height(48.dp)
            .clip(shape)
            .background(if (selected) Color(0x337CE7FF) else Color(0x14FFFFFF))
            .border(
                1.dp,
                if (selected) Color(0x667CE7FF) else Color(0x1FFFFFFF),
                shape,
            )
            .selectable(
                selected = selected,
                enabled = enabled,
                role = Role.RadioButton,
                onClick = onClick,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = when {
                !enabled -> Faint.copy(alpha = 0.4f)
                selected -> Color(0xFF7CE7FF)
                else -> Ink.copy(alpha = 0.85f)
            },
            fontSize = 12.sp,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium,
        )
    }
}

@Composable
private fun QualityChip(
    label: String,
    hint: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(12.dp)
    Column(
        modifier
            .height(48.dp)
            .clip(shape)
            .background(if (selected) Color(0x337CE7FF) else Color(0x14FFFFFF))
            .border(
                1.dp,
                if (selected) Color(0x667CE7FF) else Color(0x1FFFFFFF),
                shape,
            )
            .selectable(selected = selected, role = Role.RadioButton, onClick = onClick)
            .padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            label,
            color = if (selected) Color(0xFF7CE7FF) else Ink.copy(alpha = 0.85f),
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            hint,
            color = if (selected) Color(0xAA7CE7FF) else Faint,
            fontSize = 8.5.sp,
            letterSpacing = 0.3.sp,
        )
    }
}

@Composable
private fun TorchButton(on: Boolean, enabled: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(12.dp)
    Box(
        Modifier
            .size(48.dp)
            .clip(shape)
            .background(if (on) Color(0x33FFC96B) else Color(0x14FFFFFF))
            .border(1.dp, if (on) Color(0x66FFC96B) else Color(0x1FFFFFFF), shape)
            .toggleable(value = on, enabled = enabled, role = Role.Switch, onValueChange = { onClick() })
            .semantics {
                contentDescription = "Torch"
                if (!enabled) stateDescription = "Unavailable with the front camera"
            },
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            if (on) Icons.Rounded.FlashOn else Icons.Rounded.FlashOff,
            contentDescription = null,
            tint = when {
                !enabled -> Faint.copy(alpha = 0.4f)
                on -> Color(0xFFFFC96B)
                else -> Ink.copy(alpha = 0.8f)
            },
            modifier = Modifier.size(20.dp),
        )
    }
}

@Composable
private fun MicButton(on: Boolean, enabled: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(12.dp)
    Box(
        Modifier
            .size(48.dp)
            .clip(shape)
            .background(if (on) Color(0x335BE49B) else Color(0x14FFFFFF))
            .border(1.dp, if (on) Color(0x665BE49B) else Color(0x1FFFFFFF), shape)
            .toggleable(value = on, enabled = enabled, role = Role.Switch, onValueChange = { onClick() })
            .semantics {
                contentDescription = "Microphone"
                if (on) stateDescription = "Sending audio to the PC"
            },
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            if (on) Icons.Rounded.Mic else Icons.Rounded.MicOff,
            contentDescription = null,
            tint = when {
                !enabled -> Faint.copy(alpha = 0.4f)
                on -> Color(0xFF5BE49B)
                else -> Ink.copy(alpha = 0.8f)
            },
            modifier = Modifier.size(20.dp),
        )
    }
}

@Composable
private fun CameraPrimaryButton(
    granted: Boolean,
    live: Boolean,
    onAllow: () -> Unit,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val label: String
    val background: Brush
    val foreground: Color
    val border: Color
    val action: () -> Unit
    when {
        !granted -> {
            label = "Allow camera"
            background = SolidColor(Color(0xFF7CE7FF))
            foreground = Color(0xFF06121A)
            border = Color(0x337CE7FF)
            action = onAllow
        }
        live -> {
            label = "Stop sending"
            background = SolidColor(Color(0x14FFFFFF))
            foreground = Color(0xFFFF8CA8)
            border = Color(0x66FF8CA8)
            action = onToggle
        }
        else -> {
            label = "Start sending"
            background = SolidColor(Color(0xFF7CE7FF))
            foreground = Color(0xFF06121A)
            border = Color(0x337CE7FF)
            action = onToggle
        }
    }
    val shape = RoundedCornerShape(16.dp)
    Row(
        modifier
            .fillMaxWidth()
            .height(52.dp)
            .clip(shape)
            .background(background)
            .border(1.dp, border, shape)
            .clickable(onClick = action)
            .semantics { contentDescription = label },
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (live) {
            Box(Modifier.size(9.dp).clip(CircleShape).background(Color(0xFFFF8CA8)))
        } else {
            Icon(
                if (granted) Icons.Rounded.Videocam else Icons.Rounded.PhotoCamera,
                contentDescription = null,
                tint = foreground,
                modifier = Modifier.size(19.dp),
            )
        }
        Spacer(Modifier.width(8.dp))
        Text(
            label,
            color = foreground,
            fontSize = 13.5.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

private fun ImageProxy.toJpeg(quality: Int): ByteArray? {
    val nv21 = toNv21() ?: return null
    val yuv = YuvImage(nv21, ImageFormat.NV21, width, height, null)
    val out = ByteArrayOutputStream()
    yuv.compressToJpeg(Rect(0, 0, width, height), quality, out)
    return out.toByteArray()
}

/** YUV_420_888 to NV21 in one pass; avoids CameraX's slow RGBA conversion. */
private fun ImageProxy.toNv21(): ByteArray? {
    if (planes.size < 3) return null
    val yPlane = planes[0]
    val uPlane = planes[1]
    val vPlane = planes[2]
    if (width <= 0 || height <= 0) return null

    val nv21 = ByteArray(width * height * 3 / 2)
    val yBuffer = yPlane.buffer
    yBuffer.rewind()
    if (yPlane.pixelStride == 1 && yPlane.rowStride == width) {
        yBuffer.get(nv21, 0, width * height)
    } else {
        val row = ByteArray(width)
        for (r in 0 until height) {
            yBuffer.position(r * yPlane.rowStride)
            yBuffer.get(row, 0, width)
            System.arraycopy(row, 0, nv21, r * width, width)
        }
    }

    val uBuffer = uPlane.buffer
    val vBuffer = vPlane.buffer
    val chromaHeight = height / 2
    val chromaWidth = width / 2
    var pos = width * height
    for (r in 0 until chromaHeight) {
        for (c in 0 until chromaWidth) {
            nv21[pos++] = vBuffer.get(r * vPlane.rowStride + c * vPlane.pixelStride)
            nv21[pos++] = uBuffer.get(r * uPlane.rowStride + c * uPlane.pixelStride)
        }
    }
    return nv21
}

private suspend fun awaitCameraProvider(context: Context): ProcessCameraProvider =
    suspendCancellableCoroutine { cont ->
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener(
            {
                try {
                    cont.resume(future.get())
                } catch (exc: Exception) {
                    cont.resumeWithException(exc)
                }
            },
            ContextCompat.getMainExecutor(context),
        )
    }

/** Persistent binary socket: one rotation byte, then the JPEG. */
private class CameraStream(endpoint: String) {
    private val url = when {
        endpoint.startsWith("https://") -> "wss://" + endpoint.removePrefix("https://")
        endpoint.startsWith("http://") -> "ws://" + endpoint.removePrefix("http://")
        else -> "ws://$endpoint"
    }.trimEnd('/') + "/ws/camera"

    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private val counter = AtomicInteger(0)
    private val open = AtomicBoolean(false)
    @Volatile private var socket: WebSocket? = null

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: HttpCallResponse) {
            socket = webSocket
            open.set(true)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            open.set(false)
            if (socket === webSocket) socket = null
        }

        override fun onFailure(
            webSocket: WebSocket,
            t: Throwable,
            response: HttpCallResponse?,
        ) {
            open.set(false)
            if (socket === webSocket) socket = null
        }
    }

    fun start() {
        if (socket != null) return
        val request = Request.Builder().url(url).header("X-Device", Build.MODEL).build()
        socket = client.newWebSocket(request, listener)
    }

    fun send(jpeg: ByteArray, rotation: Int) {
        val ws = socket ?: return
        if (!open.get()) return
        if (ws.queueSize() > 1_500_000) return
        val payload = ByteArray(jpeg.size + 1)
        payload[0] = ((((rotation / 90) % 4) + 4) % 4).toByte()
        System.arraycopy(jpeg, 0, payload, 1, jpeg.size)
        if (ws.send(ByteString.of(*payload))) counter.incrementAndGet()
    }

    fun takeCount(): Int = counter.getAndSet(0)

    fun isOpen(): Boolean = open.get()

    fun stop() {
        socket?.close(1000, "stop")
        socket = null
        open.set(false)
    }

    fun close() {
        stop()
        runCatching { client.dispatcher.executorService.shutdown() }
        runCatching { client.connectionPool.evictAll() }
    }
}


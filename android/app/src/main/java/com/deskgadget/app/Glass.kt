package com.deskgadget.app

import android.graphics.RenderEffect
import android.graphics.Shader
import android.os.Build
import androidx.compose.animation.core.withInfiniteAnimationFrameNanos
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.asComposeRenderEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import kotlin.math.cos
import kotlin.math.sin

/** Pure function so both the full-screen background and each glass card draw
 *  the exact same liquid, letting cards refract what is behind them. */
fun DrawScope.drawLiquid(time: Float, root: Size, palette: Palette) {
    if (root.width <= 0f) return
    val w = root.width
    val h = root.height

    drawRect(
        Brush.verticalGradient(
            colors = listOf(palette.bgTop, palette.bgMid, palette.bgBottom),
            startY = 0f,
            endY = h,
        )
    )

    // radii follow the short edge so portrait and landscape feel equally dense
    val base = minOf(w, h)

    palette.blobs.forEach { blob ->
        val cx = w * (blob.x + 0.05f * sin(time * blob.speed + blob.phase))
        val cy = h * (blob.y + 0.04f * cos(time * blob.speed * 0.8f + blob.phase))
        val r = base * blob.radius
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(blob.color.copy(alpha = blob.alpha), blob.color.copy(alpha = 0f)),
                center = Offset(cx, cy),
                radius = r,
            ),
            radius = r,
            center = Offset(cx, cy),
        )
    }

    // vignette keeps the corners dark enough for legible chrome
    if (palette.vignette > 0f) {
        drawRect(
            Brush.radialGradient(
                colors = listOf(Color.Transparent, palette.bgBottom.copy(alpha = palette.vignette)),
                center = Offset(w * 0.5f, h * 0.45f),
                radius = maxOf(w, h) * 0.78f,
            )
        )
    }
}

private val LocalLiquidTime = staticCompositionLocalOf { mutableFloatStateOf(0f) }
private val LocalRootSize = staticCompositionLocalOf { IntSize.Zero }

/** Current look; set by [LiquidBackdrop] and read by cards and chrome. */
val LocalPalette = staticCompositionLocalOf { LiquidPalette }

/** True when the window is wider than it is tall, so cards tighten their padding. */
val LocalCompactLayout = staticCompositionLocalOf { false }

/** Full-screen animated backdrop. Wrap the whole app in this. */
@Composable
fun LiquidBackdrop(
    palette: Palette = LiquidPalette,
    content: @Composable BoxScope.() -> Unit,
) {
    val time = remember { mutableFloatStateOf(0f) }
    var size by remember { mutableStateOf(IntSize.Zero) }

    LaunchedEffect(Unit) {
        var last = 0L
        while (true) {
            withInfiniteAnimationFrameNanos { now ->
                if (now - last > 33_000_000L) { // ~30fps is plenty for slow blobs
                    time.floatValue = now / 1_000_000_000f
                    last = now
                }
            }
        }
    }

    androidx.compose.runtime.CompositionLocalProvider(
        LocalLiquidTime provides time,
        LocalRootSize provides size,
        LocalPalette provides palette,
    ) {
        Box(Modifier.fillMaxSize().onGloballyPositioned { size = it.size }) {
            Canvas(Modifier.fillMaxSize()) {
                drawLiquid(time.floatValue, Size(this.size.width, this.size.height), palette)
            }
            content()
        }
    }
}

/**
 * Frosted panel. On Android 12+ the card redraws the animated backdrop behind
 * it through a blur render effect, so it genuinely refracts the background
 * instead of faking it with a flat translucent fill.
 */
@Composable
fun GlassPanel(
    modifier: Modifier = Modifier,
    shape: Shape = RoundedCornerShape(28.dp),
    contentPadding: PaddingValues? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val time = LocalLiquidTime.current
    val root = LocalRootSize.current
    val compact = LocalCompactLayout.current
    val palette = LocalPalette.current
    val pad = contentPadding ?: if (compact) PaddingValues(14.dp) else PaddingValues(20.dp)
    var pos by remember { mutableStateOf(Offset.Zero) }

    Box(
        modifier
            .onGloballyPositioned { pos = it.positionInRoot() }
            .shadow(
                elevation = if (compact) 14.dp else 20.dp,
                shape = shape,
                clip = false,
                ambientColor = Color(0x70000000),
                spotColor = Color(0x99000000),
            )
            .clip(shape)
    ) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            Canvas(
                Modifier
                    .matchParentSize()
                    .graphicsLayer {
                        val r = palette.blur.dp.toPx()
                        renderEffect = RenderEffect.createBlurEffect(r, r, Shader.TileMode.CLAMP)
                            .asComposeRenderEffect()
                        alpha = 0.92f
                    }
            ) {
                translate(-pos.x, -pos.y) {
                    drawLiquid(
                        time.floatValue,
                        Size(root.width.toFloat(), root.height.toFloat()),
                        palette,
                    )
                }
            }
        } else {
            Box(
                Modifier.matchParentSize().background(
                    Brush.linearGradient(
                        listOf(Color(0x1FFFFFFF), Color(0x0AFFFFFF))
                    )
                )
            )
        }

        // tonal tint + top sheen
        Box(
            Modifier.matchParentSize().background(
                Brush.linearGradient(
                    colors = listOf(palette.glassTop, palette.glassBottom, palette.sheenBottom),
                )
            )
        )

        // hairline border, brighter top-left
        Box(
            Modifier.matchParentSize().border(
                width = 1.dp,
                brush = Brush.linearGradient(
                    listOf(palette.borderTop, palette.borderMid, palette.borderBottom),
                ),
                shape = shape,
            )
        )

        Column(Modifier.padding(pad), content = content)
    }
}

/** Compact glass pill, used for chips and buttons. */
@Composable
fun GlassPill(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val shape = RoundedCornerShape(50)
    val palette = LocalPalette.current
    val base = modifier
        .clip(shape)
        .background(
            Brush.linearGradient(listOf(palette.glassTop, palette.glassBottom))
        )
        .border(1.dp, palette.borderMid, shape)
        .padding(horizontal = 16.dp, vertical = 9.dp)

    if (onClick != null) {
        Box(base.clickableNoRipple(onClick)) { content() }
    } else {
        Box(base) { content() }
    }
}

fun Modifier.clickableNoRipple(onClick: () -> Unit): Modifier =
    this.clickable(interactionSource = null, indication = null, onClick = onClick)

package com.deskgadget.app

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke

/** Hand-drawn weather glyphs (no emoji, no icon pack) so the palette stays consistent. */
@Composable
fun WeatherGlyph(
    kind: String,
    isDay: Boolean,
    tint: Color,
    modifier: Modifier = Modifier,
) {
    val sunColor = if (isDay) Color(0xFFFFC96B) else Color(0xFFBFD2FF)
    Canvas(modifier) {
        val s = size.minDimension
        when (kind) {
            "sun" -> drawSun(center = Offset(size.width / 2, size.height / 2), radius = s * 0.22f, color = sunColor)
            "cloud-sun" -> {
                drawSun(Offset(size.width * 0.64f, size.height * 0.34f), s * 0.15f, sunColor)
                drawCloud(Offset(size.width * 0.44f, size.height * 0.60f), s * 0.68f)
            }
            "cloud" -> drawCloud(Offset(size.width * 0.5f, size.height * 0.52f), s * 0.82f)
            "rain" -> {
                drawCloud(Offset(size.width * 0.5f, size.height * 0.44f), s * 0.74f)
                drawRain(s)
            }
            "snow" -> {
                drawCloud(Offset(size.width * 0.5f, size.height * 0.44f), s * 0.74f)
                drawSnow(s)
            }
            "storm" -> {
                drawCloud(Offset(size.width * 0.5f, size.height * 0.42f), s * 0.74f)
                drawBolt(s)
            }
            "fog" -> {
                drawCloud(Offset(size.width * 0.5f, size.height * 0.40f), s * 0.70f)
                val c = Color(0xFFB9C6D8).copy(alpha = 0.75f)
                for (i in 0 until 3) {
                    val y = size.height * (0.68f + i * 0.11f)
                    val inset = size.width * (0.18f + i * 0.06f)
                    drawLine(c, Offset(inset, y), Offset(size.width - inset, y), strokeWidth = s * 0.045f, cap = StrokeCap.Round)
                }
            }
            else -> drawCloud(Offset(size.width * 0.5f, size.height * 0.5f), s * 0.8f)
        }
        // subtle accent halo so glyphs pick up the page's colour
        drawCircle(
            brush = androidx.compose.ui.graphics.Brush.radialGradient(
                listOf(tint.copy(alpha = 0.16f), Color.Transparent),
                center = Offset(size.width / 2, size.height / 2),
                radius = s * 0.5f,
            ),
            radius = s * 0.5f,
            center = Offset(size.width / 2, size.height / 2),
        )
    }
}

private fun DrawScope.drawSun(center: Offset, radius: Float, color: Color) {
    drawCircle(color.copy(alpha = 0.95f), radius = radius, center = center)
    val rays = 8
    val inner = radius * 1.42f
    val outer = radius * 1.92f
    for (i in 0 until rays) {
        val a = Math.toRadians((i * 360.0 / rays) - 90.0)
        val dx = kotlin.math.cos(a).toFloat()
        val dy = kotlin.math.sin(a).toFloat()
        drawLine(
            color.copy(alpha = 0.8f),
            Offset(center.x + dx * inner, center.y + dy * inner),
            Offset(center.x + dx * outer, center.y + dy * outer),
            strokeWidth = radius * 0.26f,
            cap = StrokeCap.Round,
        )
    }
}

private fun DrawScope.drawCloud(center: Offset, width: Float) {
    val c = Color(0xFFDCE6F5)
    val w = width
    val h = w * 0.52f
    val left = center.x - w / 2
    val top = center.y - h / 2
    val baseY = top + h * 0.72f
    // body
    drawRoundRect(
        brush = androidx.compose.ui.graphics.Brush.verticalGradient(
            listOf(Color(0xFFF2F7FF), Color(0xFFC3D2E6)),
            startY = top,
            endY = top + h,
        ),
        topLeft = Offset(left + w * 0.06f, baseY - h * 0.26f),
        size = Size(w * 0.88f, h * 0.44f),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(h * 0.22f),
    )
    // puffs
    drawCircle(Color(0xFFEAF1FB), radius = w * 0.20f, center = Offset(left + w * 0.30f, baseY - h * 0.26f))
    drawCircle(Color(0xFFF2F7FF), radius = w * 0.24f, center = Offset(left + w * 0.50f, baseY - h * 0.40f))
    drawCircle(Color(0xFFDCE6F5), radius = w * 0.17f, center = Offset(left + w * 0.70f, baseY - h * 0.24f))
    // soft underside shade
    drawLine(
        Color(0x22000000),
        Offset(left + w * 0.14f, baseY + h * 0.16f),
        Offset(left + w * 0.86f, baseY + h * 0.16f),
        strokeWidth = h * 0.06f,
        cap = StrokeCap.Round,
    )
}

private fun DrawScope.drawRain(s: Float) {
    val c = Color(0xFF7CC7FF)
    for (i in 0 until 3) {
        val x = size.width * (0.32f + i * 0.18f)
        drawLine(
            c,
            Offset(x, size.height * 0.72f),
            Offset(x - s * 0.03f, size.height * 0.88f),
            strokeWidth = s * 0.05f,
            cap = StrokeCap.Round,
        )
    }
}

private fun DrawScope.drawSnow(s: Float) {
    val c = Color(0xFFCFE8FF)
    for (i in 0 until 3) {
        drawCircle(c, radius = s * 0.035f, center = Offset(size.width * (0.32f + i * 0.18f), size.height * (0.78f + (i % 2) * 0.08f)))
    }
}

private fun DrawScope.drawBolt(s: Float) {
    val p = Path()
    val cx = size.width * 0.5f
    val y = size.height * 0.63f
    p.moveTo(cx + s * 0.04f, y)
    p.lineTo(cx - s * 0.09f, y + s * 0.16f)
    p.lineTo(cx - s * 0.01f, y + s * 0.16f)
    p.lineTo(cx - s * 0.07f, y + s * 0.31f)
    p.lineTo(cx + s * 0.10f, y + s * 0.11f)
    p.lineTo(cx + s * 0.01f, y + s * 0.11f)
    p.close()
    drawPath(p, Color(0xFFFFD166))
}

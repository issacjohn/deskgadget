package com.deskgadget.app

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val DeepBg = Color(0xFF05070C)
val GlassFill = Color(0x14FFFFFF)

fun hexColor(value: String?, fallback: Color = Color(0xFF7CE7FF)): Color = try {
    Color(android.graphics.Color.parseColor(value))
} catch (e: Exception) {
    fallback
}

/** One animated colour field behind the whole app. */
data class Blob(
    val color: Color,
    val alpha: Float,
    val x: Float,
    val y: Float,
    val radius: Float,
    val speed: Float,
    val phase: Float,
)

/**
 * A complete look: backdrop, glass tint, chrome and text tones. Kept data-only
 * so the server can pick one by id and the app stays a renderer.
 */
data class Palette(
    val id: String,
    val name: String,
    val bgTop: Color,
    val bgMid: Color,
    val bgBottom: Color,
    val blobs: List<Blob>,
    val vignette: Float,
    val glassTop: Color,
    val glassBottom: Color,
    val borderTop: Color,
    val borderMid: Color,
    val borderBottom: Color,
    val sheenTop: Color,
    val sheenBottom: Color,
    val blur: Float,
    val ink: Color = Color(0xFFEDF2FA),
    val muted: Color = Color(0xFF9AA6BA),
    val faint: Color = Color(0xFF6C7889),
    /** When set, every module accent is replaced by this colour. */
    val monoAccent: Color? = null,
    /** Light backgrounds need dark status-bar icons. */
    val light: Boolean = false,
)

val LiquidPalette = Palette(
    id = "liquid",
    name = "Liquid",
    bgTop = Color(0xFF05070C),
    bgMid = Color(0xFF080C15),
    bgBottom = Color(0xFF04060A),
    blobs = listOf(
        Blob(Color(0xFF5B4BFF), 0.52f, 0.16f, 0.14f, 0.92f, 0.32f, 0f),
        Blob(Color(0xFF00D6C6), 0.38f, 0.92f, 0.22f, 0.78f, 0.23f, 2f),
        Blob(Color(0xFFFF3D8B), 0.34f, 0.34f, 0.86f, 0.95f, 0.29f, 2.2f),
        Blob(Color(0xFF2C6BFF), 0.34f, 0.86f, 0.92f, 0.70f, 0.26f, 3f),
    ),
    vignette = 0.80f,
    glassTop = Color(0x14FFFFFF),
    glassBottom = Color(0x08FFFFFF),
    borderTop = Color(0x4DFFFFFF),
    borderMid = Color(0x12FFFFFF),
    borderBottom = Color(0x22FFFFFF),
    sheenTop = Color(0x1AFFFFFF),
    sheenBottom = Color(0x0AFFFFFF),
    blur = 26f,
)

/** Maximum frost: brighter fill, thicker light borders, heavy blur. */
val FullGlassPalette = Palette(
    id = "glass",
    name = "Full Glass",
    bgTop = Color(0xFF090D14),
    bgMid = Color(0xFF0E141E),
    bgBottom = Color(0xFF06090E),
    blobs = listOf(
        Blob(Color(0xFF6C8BFF), 0.34f, 0.20f, 0.12f, 0.95f, 0.21f, 0f),
        Blob(Color(0xFF6FE7FF), 0.26f, 0.86f, 0.24f, 0.85f, 0.18f, 1.8f),
        Blob(Color(0xFFBFD0E8), 0.16f, 0.50f, 0.88f, 0.90f, 0.15f, 3.1f),
        Blob(Color(0xFF5FF0C8), 0.14f, 0.12f, 0.82f, 0.65f, 0.24f, 2.4f),
    ),
    vignette = 0.66f,
    glassTop = Color(0x1CFFFFFF),
    glassBottom = Color(0x0EFFFFFF),
    borderTop = Color(0x94FFFFFF),
    borderMid = Color(0x30FFFFFF),
    borderBottom = Color(0x4DFFFFFF),
    sheenTop = Color(0x26FFFFFF),
    sheenBottom = Color(0x0EFFFFFF),
    blur = 42f,
)

val GraphitePalette = Palette(
    id = "graphite",
    name = "Graphite",
    bgTop = Color(0xFF07080B),
    bgMid = Color(0xFF0C0E13),
    bgBottom = Color(0xFF050608),
    blobs = listOf(
        Blob(Color(0xFF8FA0B8), 0.22f, 0.18f, 0.16f, 0.90f, 0.16f, 0f),
        Blob(Color(0xFF3A4557), 0.30f, 0.84f, 0.30f, 0.80f, 0.13f, 2f),
        Blob(Color(0xFF5A6474), 0.18f, 0.40f, 0.90f, 0.85f, 0.11f, 3f),
    ),
    vignette = 0.86f,
    glassTop = Color(0x12FFFFFF),
    glassBottom = Color(0x07FFFFFF),
    borderTop = Color(0x3DFFFFFF),
    borderMid = Color(0x12FFFFFF),
    borderBottom = Color(0x1FFFFFFF),
    sheenTop = Color(0x14FFFFFF),
    sheenBottom = Color(0x08FFFFFF),
    blur = 22f,
    monoAccent = Color(0xFFC9D4E4),
)

val AuroraPalette = Palette(
    id = "aurora",
    name = "Aurora",
    bgTop = Color(0xFF04100C),
    bgMid = Color(0xFF07161A),
    bgBottom = Color(0xFF030A0A),
    blobs = listOf(
        Blob(Color(0xFF10B981), 0.44f, 0.14f, 0.18f, 0.92f, 0.24f, 0f),
        Blob(Color(0xFF22D3EE), 0.34f, 0.88f, 0.20f, 0.82f, 0.20f, 1.6f),
        Blob(Color(0xFFA3E635), 0.22f, 0.44f, 0.90f, 0.86f, 0.17f, 2.8f),
    ),
    vignette = 0.72f,
    glassTop = Color(0x1AFFFFFF),
    glassBottom = Color(0x0AFFFFFF),
    borderTop = Color(0x59FFFFFF),
    borderMid = Color(0x14FFFFFF),
    borderBottom = Color(0x29FFFFFF),
    sheenTop = Color(0x1FFFFFFF),
    sheenBottom = Color(0x0DFFFFFF),
    blur = 28f,
)

/** True black: OLED-friendly, colour still comes from the modules. */
val BlackPalette = Palette(
    id = "black",
    name = "OLED Black",
    bgTop = Color(0xFF000000),
    bgMid = Color(0xFF000000),
    bgBottom = Color(0xFF000000),
    // no colour field at all, so the background stays at true #000000
    blobs = emptyList(),
    vignette = 0f,
    glassTop = Color(0x0AFFFFFF),
    glassBottom = Color(0x04FFFFFF),
    borderTop = Color(0x2EFFFFFF),
    borderMid = Color(0x10FFFFFF),
    borderBottom = Color(0x1AFFFFFF),
    sheenTop = Color(0x0FFFFFFF),
    sheenBottom = Color(0x05FFFFFF),
    blur = 24f,
    ink = Color(0xFFFFFFFF),
    muted = Color(0xFFA2A8B4),
    faint = Color(0xFF6B7280),
)

/** Bright frosted daylight: white glass over pastel, dark type. */
val WhitePalette = Palette(
    id = "white",
    name = "White",
    bgTop = Color(0xFFF8FAFD),
    bgMid = Color(0xFFEEF2F8),
    bgBottom = Color(0xFFE3E9F2),
    blobs = listOf(
        Blob(Color(0xFF9FB7FF), 0.42f, 0.18f, 0.14f, 0.95f, 0.18f, 0f),
        Blob(Color(0xFF7FE3EE), 0.32f, 0.88f, 0.22f, 0.85f, 0.15f, 1.7f),
        Blob(Color(0xFFCBB8FF), 0.30f, 0.40f, 0.90f, 0.90f, 0.13f, 2.9f),
    ),
    vignette = 0.16f,
    glassTop = Color(0xB3FFFFFF),
    glassBottom = Color(0x80FFFFFF),
    borderTop = Color(0xE6FFFFFF),
    borderMid = Color(0x59FFFFFF),
    borderBottom = Color(0x8CFFFFFF),
    sheenTop = Color(0xCCFFFFFF),
    sheenBottom = Color(0x4DFFFFFF),
    blur = 34f,
    ink = Color(0xFF0D1524),
    muted = Color(0xFF4E5A70),
    faint = Color(0xFF7C879B),
    light = true,
)

val Palettes: List<Palette> = listOf(
    LiquidPalette,
    FullGlassPalette,
    BlackPalette,
    WhitePalette,
    GraphitePalette,
    AuroraPalette,
)

fun paletteFor(id: String?): Palette = Palettes.firstOrNull { it.id == id } ?: LiquidPalette

/* Text tones follow the active palette, so a light theme gets dark type
   without every call site knowing about themes. */
val Ink: Color
    @Composable @ReadOnlyComposable get() = LocalPalette.current.ink

val Muted: Color
    @Composable @ReadOnlyComposable get() = LocalPalette.current.muted

val Faint: Color
    @Composable @ReadOnlyComposable get() = LocalPalette.current.faint

@Composable
fun DeckTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Color(0xFF7CE7FF),
            secondary = Color(0xFFB69CFF),
            background = DeepBg,
            surface = Color(0xFF0A0E17),
            onBackground = Ink,
            onSurface = Ink,
        ),
        typography = MaterialTheme.typography.copy(
            displayLarge = TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.Light,
                fontSize = 76.sp,
                letterSpacing = (-3).sp,
            ),
            titleLarge = TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.SemiBold,
                fontSize = 22.sp,
                letterSpacing = (-0.2).sp,
            ),
            labelSmall = TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.Medium,
                fontSize = 10.sp,
                letterSpacing = 2.sp,
            ),
        ),
        content = content,
    )
}

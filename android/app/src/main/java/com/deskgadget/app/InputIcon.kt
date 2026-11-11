package com.deskgadget.app

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp

/**
 * A keyboard with a mouse tucked into the corner, for the combined
 * pointer/typing module.
 */
private const val KEYBOARD_PATH =
    "M20 5H4c-1.1 0-1.99.9-1.99 2L2 17c0 1.1.9 2 2 2h16c1.1 0 2-.9 " +
        "2-2V7c0-1.1-.9-2-2-2zm-9 3h2v2h-2V8zm0 3h2v2h-2v-2zM8 8h2v2H8V8zm0 " +
        "3h2v2H8v-2zm-1 2H5v-2h2v2zm0-3H5V8h2v2zm9 7H8v-2h8v2zm0-4h-2v-2h2v2zm0-3h-2V8h2v2zm3 " +
        "3h-2v-2h2v2zm0-3h-2V8h2v2z"

private const val MOUSE_PATH =
    "M13 1.07V9h7c0-4.08-3.05-7.44-7-7.93zM4 15c0 4.42 3.58 8 8 8s8-3.58 " +
        "8-8v-4H4v4zm7-13.93C7.05 1.56 4 4.92 4 9h7V1.07z"

val InputIcon: ImageVector by lazy {
    ImageVector.Builder(
        name = "InputIcon",
        defaultWidth = 24.dp,
        defaultHeight = 24.dp,
        viewportWidth = 24f,
        viewportHeight = 24f,
    ).apply {
        addGroup(scaleX = 0.66f, scaleY = 0.66f)
        addPath(
            PathParser().parsePathString(KEYBOARD_PATH).toNodes(),
            fill = SolidColor(Color.Black),
        )
        clearGroup()
        addGroup(scaleX = 0.44f, scaleY = 0.44f, translationX = 12.8f, translationY = 11.0f)
        addPath(
            PathParser().parsePathString(MOUSE_PATH).toNodes(),
            fill = SolidColor(Color.Black),
        )
        clearGroup()
    }.build()
}

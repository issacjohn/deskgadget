package com.deskgadget.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.drawable.Icon
import android.os.IBinder

/**
 * Keeps the process (and therefore the WebSocket) alive while the phone is
 * showing the deck or sitting on a desk with the screen off.
 *
 * Closing the app means disappearing: swiping the task away stops the service,
 * closes the link and removes this notification. The notification also carries
 * a Disconnect action for the same thing without opening the app.
 */
class DeckService : Service() {

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Connection", NotificationManager.IMPORTANCE_LOW).apply {
                    description = "Keeps the link to your PC alive"
                    setShowBadge(false)
                }
            )
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_DISCONNECT) {
            DeckClient.get(this).disconnect()
            stopSelf()
            return START_NOT_STICKY
        }

        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val close = PendingIntent.getService(
            this,
            1,
            Intent(this, DeckService::class.java).setAction(ACTION_DISCONNECT),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notification: Notification = Notification.Builder(this, CHANNEL)
            .setContentTitle("DeskGadget")
            .setContentText("Connected to your PC - swipe away or Disconnect to stop")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentIntent(open)
            .addAction(
                Notification.Action.Builder(
                    Icon.createWithResource(this, android.R.drawable.ic_menu_close_clear_cancel),
                    "Disconnect",
                    close,
                ).build()
            )
            .setOngoing(true)
            .build()
        startForeground(1, notification)
        return START_NOT_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        DeckClient.get(this).disconnect()
        stopSelf()
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        private const val CHANNEL = "deskgadget-link"
        private const val ACTION_DISCONNECT = "com.deskgadget.app.DISCONNECT"
    }
}

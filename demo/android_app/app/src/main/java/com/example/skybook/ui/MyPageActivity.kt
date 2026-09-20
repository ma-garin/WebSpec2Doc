package com.example.skybook.ui

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.tabs.TabLayout
import com.example.skybook.R
import com.example.skybook.data.Booking
import com.example.skybook.data.BookingStore
import com.example.skybook.util.Nav

class MyPageActivity : AppCompatActivity() {

    private lateinit var tabs: TabLayout
    private lateinit var bookingsPanel: View
    private lateinit var profilePanel: View
    private lateinit var list: LinearLayout
    private lateinit var emptyView: View
    private lateinit var profileEmail: TextView
    private lateinit var logoutButton: MaterialButton

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!BookingStore.loggedIn) {
            val intent = Intent(this, LoginActivity::class.java)
            intent.putExtra("login_required", true)
            startActivity(intent)
            finish()
            return
        }

        setContentView(R.layout.activity_mypage)

        tabs = findViewById(R.id.mypage_tabs)
        bookingsPanel = findViewById(R.id.mypage_bookings_panel)
        profilePanel = findViewById(R.id.mypage_profile_panel)
        list = findViewById(R.id.mypage_list)
        emptyView = findViewById(R.id.mypage_empty)
        profileEmail = findViewById(R.id.mypage_profile_email)
        logoutButton = findViewById(R.id.mypage_logout)

        tabs.addOnTabSelectedListener(object : TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: TabLayout.Tab) {
                showPanel(tab.position)
            }

            override fun onTabUnselected(tab: TabLayout.Tab) {}

            override fun onTabReselected(tab: TabLayout.Tab) {}
        })

        profileEmail.text = BookingStore.email

        logoutButton.setOnClickListener {
            BookingStore.loggedIn = false
            val intent = Intent(this, LoginActivity::class.java)
            intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            startActivity(intent)
            finish()
        }

        val bottomNav: BottomNavigationView = findViewById(R.id.bottom_nav)
        Nav.setupBottomNav(this, bottomNav, R.id.nav_mypage)

        showPanel(0)
        renderBookings()
    }

    private fun showPanel(position: Int) {
        bookingsPanel.visibility = if (position == 0) View.VISIBLE else View.GONE
        profilePanel.visibility = if (position == 1) View.VISIBLE else View.GONE
    }

    private fun renderBookings() {
        list.removeAllViews()
        val bookings = BookingStore.bookings

        if (bookings.isEmpty()) {
            emptyView.visibility = View.VISIBLE
            list.visibility = View.GONE
            return
        }

        emptyView.visibility = View.GONE
        list.visibility = View.VISIBLE

        val inflater = LayoutInflater.from(this)
        for (booking in bookings) {
            val itemView = inflater.inflate(R.layout.item_booking, list, false)
            itemView.contentDescription = "mypage_booking_${booking.pnr}"

            val pnrText: TextView = itemView.findViewById(R.id.item_booking_pnr)
            val infoText: TextView = itemView.findViewById(R.id.item_booking_info)
            val statusText: TextView = itemView.findViewById(R.id.item_booking_status)
            val cancelButton: MaterialButton = itemView.findViewById(R.id.item_booking_cancel)

            pnrText.text = "PNR: ${booking.pnr}"
            infoText.text = "${booking.flightId}　${booking.date}　座席 ${booking.seat}　${booking.total}円"
            statusText.text = booking.status
            statusText.contentDescription = "mypage_status_${booking.pnr}"
            cancelButton.contentDescription = "mypage_cancel_${booking.pnr}"
            cancelButton.isEnabled = booking.status != "取消済"
            cancelButton.setOnClickListener {
                confirmCancel(booking)
            }

            list.addView(itemView)
        }
    }

    private fun confirmCancel(booking: Booking) {
        MaterialAlertDialogBuilder(this)
            .setTitle("予約の取消")
            .setMessage("PNR ${booking.pnr} の予約を取り消しますか？")
            .setPositiveButton("取消する") { _, _ ->
                booking.status = "取消済"
                renderBookings()
            }
            .setNegativeButton("キャンセル", null)
            .show()
    }
}

package com.example.skybook.ui

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.skybook.R
import com.example.skybook.data.BookingStore

class FlightDetailActivity : AppCompatActivity() {

    private lateinit var seatSelectedView: TextView
    private lateinit var seatErrorView: TextView
    private var rulesVisible = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_flight_detail)

        val flight = BookingStore.flight

        val titleView: TextView = findViewById(R.id.flight_title)
        val routeView: TextView = findViewById(R.id.flight_route)
        val timeView: TextView = findViewById(R.id.flight_time)
        val priceView: TextView = findViewById(R.id.flight_price)
        val rulesToggle: Button = findViewById(R.id.flight_rules_toggle)
        val rulesPanel: View = findViewById(R.id.flight_rules_panel)
        val seatOpen: Button = findViewById(R.id.flight_seat_open)
        val nextButton: Button = findViewById(R.id.flight_next)
        seatSelectedView = findViewById(R.id.flight_seat_selected)
        seatErrorView = findViewById(R.id.flight_seat_error)

        if (flight != null) {
            titleView.text = flight.id
            routeView.text = flight.from + " → " + flight.to
            timeView.text = flight.dep + " - " + flight.arr
        }
        priceView.text = String.format(java.util.Locale.getDefault(), "%,d円", BookingStore.subtotal())

        rulesPanel.visibility = View.GONE
        rulesToggle.setOnClickListener {
            rulesVisible = !rulesVisible
            rulesPanel.visibility = if (rulesVisible) View.VISIBLE else View.GONE
        }

        updateSeatDisplay()
        seatErrorView.visibility = View.GONE

        seatOpen.setOnClickListener {
            val dialog = SeatDialogFragment.newInstance()
            dialog.onSeatConfirmed = { seat ->
                BookingStore.seat = seat
                updateSeatDisplay()
                seatErrorView.text = ""
                seatErrorView.visibility = View.GONE
            }
            dialog.show(supportFragmentManager, "seat_dialog")
        }

        nextButton.setOnClickListener {
            if (BookingStore.seat.isEmpty()) {
                seatErrorView.text = "座席を選んでください"
                seatErrorView.visibility = View.VISIBLE
            } else {
                seatErrorView.text = ""
                seatErrorView.visibility = View.GONE
                startActivity(Intent(this, PassengerActivity::class.java))
            }
        }
    }

    private fun updateSeatDisplay() {
        val seat = BookingStore.seat
        seatSelectedView.text = if (seat.isNotEmpty()) seatLabel(seat) else ""
    }

    private fun seatLabel(seat: String): String {
        val col = seat.last()
        val type = when (col) {
            'A', 'F' -> "窓側"
            'C', 'D' -> "通路側"
            else -> "中央"
        }
        return seat + "（" + type + "）"
    }
}

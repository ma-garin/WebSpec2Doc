package com.example.skybook.ui

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.example.skybook.R
import com.example.skybook.data.BookingStore

class DebugActivity : AppCompatActivity() {

    private lateinit var dumpView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_debug)

        dumpView = findViewById(R.id.debug_dump)
        val resetButton: MaterialButton = findViewById(R.id.debug_reset)

        resetButton.setOnClickListener {
            BookingStore.reset()
            renderDump()
        }

        renderDump()
    }

    private fun renderDump() {
        val sb = StringBuilder()
        sb.append("loggedIn: ").append(BookingStore.loggedIn).append("\n")
        sb.append("email: ").append(BookingStore.email).append("\n")
        sb.append("from: ").append(BookingStore.from).append("\n")
        sb.append("to: ").append(BookingStore.to).append("\n")
        sb.append("depart: ").append(BookingStore.depart).append("\n")
        sb.append("returnDate: ").append(BookingStore.returnDate).append("\n")
        sb.append("adults: ").append(BookingStore.adults).append("\n")
        sb.append("seatClass: ").append(BookingStore.seatClass).append("\n")
        sb.append("flight: ").append(BookingStore.flight?.id ?: "null").append("\n")
        sb.append("seat: ").append(BookingStore.seat).append("\n")
        sb.append("couponApplied: ").append(BookingStore.couponApplied).append("\n")

        sb.append("passengers (").append(BookingStore.passengers.size).append("):\n")
        for (passenger in BookingStore.passengers) {
            sb.append("  - ")
                .append(passenger.lastKana).append(" ")
                .append(passenger.firstKana).append(", ")
                .append(passenger.birth).append(", ")
                .append(passenger.gender).append("\n")
        }

        sb.append("bookings (").append(BookingStore.bookings.size).append("):\n")
        for (booking in BookingStore.bookings) {
            sb.append("  - ")
                .append(booking.pnr).append(" ")
                .append(booking.flightId).append(" ")
                .append(booking.date).append(" 座席")
                .append(booking.seat).append(" ")
                .append(booking.total).append("円 ")
                .append(booking.status).append("\n")
        }

        dumpView.text = sb.toString()
    }
}

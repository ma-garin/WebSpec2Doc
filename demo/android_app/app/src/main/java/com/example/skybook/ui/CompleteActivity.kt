package com.example.skybook.ui

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.skybook.R
import com.example.skybook.data.BookingStore
import com.example.skybook.data.FlightData
import com.google.android.material.appbar.MaterialToolbar
import java.util.Locale

class CompleteActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_complete)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        val pnr = intent.getStringExtra("pnr") ?: ""

        val pnrView = findViewById<TextView>(R.id.complete_pnr)
        val summaryView = findViewById<TextView>(R.id.complete_summary)
        pnrView.text = pnr

        val flight = BookingStore.flight
        val fromName = flight?.let { FlightData.airportName(it.from) } ?: ""
        val toName = flight?.let { FlightData.airportName(it.to) } ?: ""
        val total = String.format(Locale.US, "%,d円", BookingStore.total())
        summaryView.text = "${flight?.id ?: ""}  $fromName → $toName\n" +
            "搭乗日: ${BookingStore.depart}\n" +
            "座席: ${BookingStore.seat}\n" +
            "搭乗者数: ${BookingStore.passengers.size} 名\n" +
            "合計金額: $total"

        findViewById<Button>(R.id.complete_to_mypage).setOnClickListener {
            val i = Intent(this, MyPageActivity::class.java)
            i.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            startActivity(i)
        }

        findViewById<Button>(R.id.complete_to_home).setOnClickListener {
            val i = Intent(this, SearchActivity::class.java)
            i.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            startActivity(i)
        }
    }
}

package com.example.skybook.ui

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.chip.Chip
import com.google.android.material.tabs.TabLayout
import com.example.skybook.R
import com.example.skybook.data.BookingStore
import com.example.skybook.data.Flight
import com.example.skybook.data.FlightData

class ResultsActivity : AppCompatActivity() {

    private lateinit var resultsListScroll: View
    private lateinit var resultsList: LinearLayout
    private lateinit var resultsEmpty: View
    private lateinit var resultsSummary: TextView
    private lateinit var resultsTabs: TabLayout
    private lateinit var chipDirect: Chip
    private lateinit var chipMorning: Chip
    private lateinit var chipEvening: Chip

    private var allResults: List<Flight> = emptyList()
    private var sortMode: String = "recommend"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_results)

        resultsListScroll = findViewById(R.id.results_list_scroll)
        resultsList = findViewById(R.id.results_list)
        resultsEmpty = findViewById(R.id.results_empty)
        resultsSummary = findViewById(R.id.results_summary)
        resultsTabs = findViewById(R.id.results_tabs)
        chipDirect = findViewById(R.id.results_filter_direct)
        chipMorning = findViewById(R.id.results_filter_morning)
        chipEvening = findViewById(R.id.results_filter_evening)

        val backButton: Button = findViewById(R.id.results_back)
        backButton.setOnClickListener { finish() }

        val from = BookingStore.from
        val to = BookingStore.to
        allResults = FlightData.search(from, to)

        resultsSummary.text = FlightData.airportName(from) + " → " + FlightData.airportName(to) +
            "　" + BookingStore.depart + "　大人" + BookingStore.adults + "名"

        resultsTabs.getTabAt(0)?.contentDescription = "results_tab_recommend"
        resultsTabs.getTabAt(1)?.contentDescription = "results_tab_cheapest"
        resultsTabs.getTabAt(2)?.contentDescription = "results_tab_fastest"

        resultsTabs.addOnTabSelectedListener(object : TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: TabLayout.Tab) {
                sortMode = when (tab.position) {
                    1 -> "cheapest"
                    2 -> "fastest"
                    else -> "recommend"
                }
                renderList()
            }

            override fun onTabUnselected(tab: TabLayout.Tab) {}
            override fun onTabReselected(tab: TabLayout.Tab) {}
        })

        chipDirect.setOnCheckedChangeListener { _, _ -> renderList() }
        chipMorning.setOnCheckedChangeListener { _, _ -> renderList() }
        chipEvening.setOnCheckedChangeListener { _, _ -> renderList() }

        renderList()
    }

    private fun depMinutes(flight: Flight): Int {
        val parts = flight.dep.split(":")
        return parts[0].toInt() * 60 + parts[1].toInt()
    }

    private fun filtered(): List<Flight> {
        var list = allResults
        if (chipDirect.isChecked) {
            list = list.filter { it.direct }
        }
        if (chipMorning.isChecked) {
            list = list.filter { depMinutes(it) < 12 * 60 }
        }
        if (chipEvening.isChecked) {
            list = list.filter { depMinutes(it) >= 17 * 60 }
        }
        return list
    }

    private fun sorted(list: List<Flight>): List<Flight> {
        return when (sortMode) {
            "cheapest" -> list.sortedBy { it.price }
            "fastest" -> list.sortedBy { depMinutes(it) }
            else -> list
        }
    }

    private fun renderList() {
        val list = sorted(filtered())
        resultsList.removeAllViews()

        if (list.isEmpty()) {
            resultsEmpty.visibility = View.VISIBLE
            resultsListScroll.visibility = View.GONE
            return
        }

        resultsEmpty.visibility = View.GONE
        resultsListScroll.visibility = View.VISIBLE

        val inflater = LayoutInflater.from(this)
        for (flight in list) {
            val card = inflater.inflate(R.layout.item_flight, resultsList, false)
            card.contentDescription = "results_item_" + flight.id
            card.tag = "results_item_" + flight.id

            val nameView: TextView = card.findViewById(R.id.item_flight_name)
            val timeView: TextView = card.findViewById(R.id.item_flight_time)
            val priceView: TextView = card.findViewById(R.id.item_flight_price)
            val selectButton: Button = card.findViewById(R.id.item_flight_select)

            nameView.text = flight.id
            val viaText = if (flight.direct) "直行" else "経由 " + (flight.via ?: "")
            timeView.text = flight.dep + " - " + flight.arr + "　" + viaText
            priceView.text = String.format(java.util.Locale.getDefault(), "%,d円", flight.price)

            selectButton.contentDescription = "results_select_" + flight.id
            selectButton.tag = "results_select_" + flight.id
            selectButton.setOnClickListener {
                BookingStore.flight = flight
                startActivity(Intent(this, FlightDetailActivity::class.java))
            }

            resultsList.addView(card)
        }
    }
}

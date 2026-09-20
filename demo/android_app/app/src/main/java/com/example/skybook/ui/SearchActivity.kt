package com.example.skybook.ui

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.CheckBox
import android.widget.EditText
import android.widget.RadioGroup
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.button.MaterialButton
import com.google.android.material.datepicker.MaterialDatePicker
import com.example.skybook.R
import com.example.skybook.data.BookingStore
import com.example.skybook.data.FlightData
import com.example.skybook.util.Nav
import com.example.skybook.util.Validators
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

class SearchActivity : AppCompatActivity() {

    private lateinit var fromSpinner: Spinner
    private lateinit var toSpinner: Spinner
    private lateinit var toError: TextView
    private lateinit var departInput: EditText
    private lateinit var departError: TextView
    private lateinit var returnInput: EditText
    private lateinit var returnError: TextView
    private lateinit var adultsText: TextView
    private var adults = 1
    private lateinit var classGroup: RadioGroup
    private lateinit var advancedPanel: View
    private var advancedExpanded = false
    private lateinit var directOnlyCheck: CheckBox
    private lateinit var maxPriceInput: EditText
    private lateinit var maxPriceError: TextView

    private val dateFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_search)

        fromSpinner = findViewById(R.id.search_from)
        toSpinner = findViewById(R.id.search_to)
        toError = findViewById(R.id.search_to_error)
        departInput = findViewById(R.id.search_depart)
        departError = findViewById(R.id.search_depart_error)
        returnInput = findViewById(R.id.search_return)
        returnError = findViewById(R.id.search_return_error)
        adultsText = findViewById(R.id.search_adults)
        classGroup = findViewById(R.id.search_class)
        advancedPanel = findViewById(R.id.search_advanced_panel)
        directOnlyCheck = findViewById(R.id.search_direct_only)
        maxPriceInput = findViewById(R.id.search_max_price)
        maxPriceError = findViewById(R.id.search_max_price_error)

        val airportLabels = FlightData.AIRPORTS.map { "${it.code} ${it.name}" }
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, airportLabels)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        fromSpinner.adapter = adapter
        toSpinner.adapter = adapter

        adultsText.text = adults.toString()

        findViewById<MaterialButton>(R.id.search_adults_minus).setOnClickListener {
            if (adults > 1) {
                adults -= 1
                adultsText.text = adults.toString()
            }
        }
        findViewById<MaterialButton>(R.id.search_adults_plus).setOnClickListener {
            if (adults < 9) {
                adults += 1
                adultsText.text = adults.toString()
            }
        }

        findViewById<MaterialButton>(R.id.search_depart_pick).setOnClickListener {
            showDatePicker(departInput)
        }
        findViewById<MaterialButton>(R.id.search_return_pick).setOnClickListener {
            showDatePicker(returnInput)
        }

        val advancedToggle: MaterialButton = findViewById(R.id.search_advanced_toggle)
        advancedToggle.setOnClickListener {
            advancedExpanded = !advancedExpanded
            advancedPanel.visibility = if (advancedExpanded) View.VISIBLE else View.GONE
        }

        val bottomNav: BottomNavigationView = findViewById(R.id.bottom_nav)
        Nav.setupBottomNav(this, bottomNav, R.id.nav_search)

        findViewById<MaterialButton>(R.id.search_submit).setOnClickListener { attemptSearch() }
    }

    private fun showDatePicker(target: EditText) {
        val picker = MaterialDatePicker.Builder.datePicker()
            .setTitleText("日付を選択")
            .build()
        picker.addOnPositiveButtonClickListener { selection: Long ->
            val date = Instant.ofEpochMilli(selection).atZone(ZoneOffset.UTC).toLocalDate()
            target.setText(date.format(dateFormatter))
        }
        picker.show(supportFragmentManager, "date_picker")
    }

    private fun attemptSearch() {
        toError.text = ""
        toError.visibility = View.GONE
        departError.text = ""
        departError.visibility = View.GONE
        returnError.text = ""
        returnError.visibility = View.GONE
        maxPriceError.text = ""
        maxPriceError.visibility = View.GONE

        val fromAirport = FlightData.AIRPORTS[fromSpinner.selectedItemPosition]
        val toAirport = FlightData.AIRPORTS[toSpinner.selectedItemPosition]

        var firstErrorView: View? = null

        if (fromAirport.code == toAirport.code) {
            toError.text = "出発地と到着地が同じです"
            toError.visibility = View.VISIBLE
            firstErrorView = toSpinner
        }

        val departText = departInput.text?.toString().orEmpty()
        val departDate = Validators.parseDate(departText)
        val today = LocalDate.now()
        if (departDate == null || departDate.isBefore(today) || departDate.isAfter(today.plusDays(330))) {
            departError.text = "出発日は今日から330日以内の日付を指定してください"
            departError.visibility = View.VISIBLE
            if (firstErrorView == null) firstErrorView = departInput
        }

        val returnText = returnInput.text?.toString().orEmpty()
        if (returnText.isNotEmpty()) {
            val returnDate = Validators.parseDate(returnText)
            if (returnDate == null || (departDate != null && returnDate.isBefore(departDate))) {
                returnError.text = "復路日は出発日以降の日付にしてください"
                returnError.visibility = View.VISIBLE
                if (firstErrorView == null) firstErrorView = returnInput
            }
        }

        val maxPriceText = maxPriceInput.text?.toString().orEmpty()
        if (maxPriceText.isNotEmpty()) {
            val maxPrice = maxPriceText.toIntOrNull()
            if (maxPrice == null || maxPrice < 5000 || maxPrice > 100000) {
                maxPriceError.text = "上限価格は5000〜100000で入力してください"
                maxPriceError.visibility = View.VISIBLE
                if (firstErrorView == null) firstErrorView = maxPriceInput
            }
        }

        firstErrorView?.let {
            it.requestFocus()
            return
        }

        val seatClass = when (classGroup.checkedRadioButtonId) {
            R.id.search_class_premium -> "premium"
            R.id.search_class_business -> "business"
            else -> "economy"
        }

        BookingStore.from = fromAirport.code
        BookingStore.to = toAirport.code
        BookingStore.depart = departText
        BookingStore.returnDate = returnText
        BookingStore.adults = adults
        BookingStore.seatClass = seatClass

        startActivity(Intent(this, ResultsActivity::class.java))
    }
}

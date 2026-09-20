package com.example.skybook.ui

import android.content.DialogInterface
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioGroup
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.skybook.R
import com.example.skybook.data.Booking
import com.example.skybook.data.BookingStore
import com.example.skybook.data.FlightData
import com.example.skybook.util.Validators
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.time.YearMonth
import java.util.Locale

class PaymentActivity : AppCompatActivity() {

    private lateinit var summary: TextView
    private lateinit var couponInput: EditText
    private lateinit var couponError: TextView
    private lateinit var discount: TextView
    private lateinit var total: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_payment)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        summary = findViewById(R.id.payment_summary)
        couponInput = findViewById(R.id.payment_coupon)
        couponError = findViewById(R.id.payment_coupon_error)
        discount = findViewById(R.id.payment_discount)
        total = findViewById(R.id.payment_total)

        val couponApply = findViewById<Button>(R.id.payment_coupon_apply)
        val methodGroup = findViewById<RadioGroup>(R.id.payment_method)
        val cardPanel = findViewById<LinearLayout>(R.id.payment_card_panel)
        val convPanel = findViewById<LinearLayout>(R.id.payment_conv_panel)
        val bankPanel = findViewById<LinearLayout>(R.id.payment_bank_panel)

        val cardNumber = findViewById<EditText>(R.id.payment_card_number)
        val cardNumberError = findViewById<TextView>(R.id.payment_card_number_error)
        val cardExpiry = findViewById<EditText>(R.id.payment_card_expiry)
        val cardExpiryError = findViewById<TextView>(R.id.payment_card_expiry_error)
        val cardCvv = findViewById<EditText>(R.id.payment_card_cvv)
        val cardCvvError = findViewById<TextView>(R.id.payment_card_cvv_error)
        val cardName = findViewById<EditText>(R.id.payment_card_name)
        val cardNameError = findViewById<TextView>(R.id.payment_card_name_error)

        val convStore = findViewById<Spinner>(R.id.payment_conv_store)
        convStore.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            listOf("セブン", "ローソン", "ファミマ")
        )

        val submit = findViewById<Button>(R.id.payment_submit)

        updateSummary()

        couponApply.setOnClickListener {
            val code = couponInput.text.toString().trim().uppercase(Locale.ROOT)
            if (code == "SKY10") {
                BookingStore.couponApplied = true
                couponError.text = ""
                couponError.visibility = View.GONE
                discount.text = "クーポン SKY10 適用中（10%引き）"
                discount.visibility = View.VISIBLE
            } else {
                BookingStore.couponApplied = false
                discount.visibility = View.GONE
                couponError.text = "無効なクーポンです"
                couponError.visibility = View.VISIBLE
            }
            updateSummary()
        }

        methodGroup.setOnCheckedChangeListener { _, checkedId ->
            cardPanel.visibility = if (checkedId == R.id.payment_method_card) View.VISIBLE else View.GONE
            convPanel.visibility = if (checkedId == R.id.payment_method_conv) View.VISIBLE else View.GONE
            bankPanel.visibility = if (checkedId == R.id.payment_method_bank) View.VISIBLE else View.GONE
        }

        submit.setOnClickListener {
            var ok = true
            var firstErrorView: View? = null

            if (methodGroup.checkedRadioButtonId == R.id.payment_method_card) {
                val number = cardNumber.text.toString().trim()
                if (!Validators.isDigits(number, 16, 16) || number != "4242424242424242") {
                    cardNumberError.text = "カードが承認されませんでした"
                    cardNumberError.visibility = View.VISIBLE
                    if (firstErrorView == null) firstErrorView = cardNumber
                    ok = false
                } else {
                    cardNumberError.text = ""
                    cardNumberError.visibility = View.GONE
                }

                val expiry = cardExpiry.text.toString().trim()
                if (!isExpiryValid(expiry)) {
                    cardExpiryError.text = "有効な期限（MM/YY・未来の日付）を入力してください"
                    cardExpiryError.visibility = View.VISIBLE
                    if (firstErrorView == null) firstErrorView = cardExpiry
                    ok = false
                } else {
                    cardExpiryError.text = ""
                    cardExpiryError.visibility = View.GONE
                }

                val cvv = cardCvv.text.toString().trim()
                if (!Validators.isDigits(cvv, 3, 3)) {
                    cardCvvError.text = "3桁の数字で入力してください"
                    cardCvvError.visibility = View.VISIBLE
                    if (firstErrorView == null) firstErrorView = cardCvv
                    ok = false
                } else {
                    cardCvvError.text = ""
                    cardCvvError.visibility = View.GONE
                }

                val name = cardName.text.toString().trim()
                if (name.isEmpty() || !Regex("^[A-Z ]+$").matches(name)) {
                    cardNameError.text = "英大文字とスペースのみで入力してください"
                    cardNameError.visibility = View.VISIBLE
                    if (firstErrorView == null) firstErrorView = cardName
                    ok = false
                } else {
                    cardNameError.text = ""
                    cardNameError.visibility = View.GONE
                }
            }

            if (ok) {
                showConfirmDialog()
            } else {
                firstErrorView?.requestFocus()
            }
        }
    }

    private fun isExpiryValid(s: String): Boolean {
        val m = Regex("^(0[1-9]|1[0-2])/([0-9]{2})$").matchEntire(s) ?: return false
        val month = m.groupValues[1].toInt()
        val year = 2000 + m.groupValues[2].toInt()
        val expiry = YearMonth.of(year, month)
        return !expiry.isBefore(YearMonth.now())
    }

    private fun updateSummary() {
        val flight = BookingStore.flight
        val classLabel = when (BookingStore.seatClass) {
            "premium" -> "プレミアム"
            "business" -> "ビジネス"
            else -> "エコノミー"
        }
        val fromName = flight?.let { FlightData.airportName(it.from) } ?: ""
        val toName = flight?.let { FlightData.airportName(it.to) } ?: ""
        summary.text = "${flight?.id ?: ""}  $fromName → $toName\n" +
            "大人 ${BookingStore.adults} 名 / $classLabel / 座席 ${BookingStore.seat}"
        total.text = "合計 " + formatYen(BookingStore.total())
        if (BookingStore.couponApplied) {
            discount.text = "クーポン SKY10 適用中（10%引き）"
            discount.visibility = View.VISIBLE
        }
    }

    private fun formatYen(n: Int): String {
        return String.format(Locale.US, "%,d円", n)
    }

    private fun showConfirmDialog() {
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle("予約確認")
            .setMessage("この内容で予約を確定します。よろしいですか？")
            .setPositiveButton("確定") { d, _ ->
                val flight = BookingStore.flight
                val booking = Booking(
                    pnr = BookingStore.newPnr(),
                    flightId = flight?.id ?: "",
                    date = BookingStore.depart,
                    seat = BookingStore.seat,
                    total = BookingStore.total(),
                    status = "確定"
                )
                BookingStore.bookings.add(booking)
                val intent = Intent(this, CompleteActivity::class.java)
                intent.putExtra("pnr", booking.pnr)
                startActivity(intent)
                d.dismiss()
            }
            .setNegativeButton("キャンセル") { d, _ -> d.dismiss() }
            .show()

        dialog.getButton(DialogInterface.BUTTON_POSITIVE)?.contentDescription = "payment_confirm_ok"
        dialog.getButton(DialogInterface.BUTTON_NEGATIVE)?.contentDescription = "payment_confirm_cancel"
    }
}

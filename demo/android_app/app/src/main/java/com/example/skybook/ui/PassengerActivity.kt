package com.example.skybook.ui

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.skybook.R
import com.example.skybook.data.BookingStore
import com.example.skybook.data.Passenger
import com.example.skybook.util.Validators
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.datepicker.MaterialDatePicker
import java.time.Instant
import java.time.ZoneOffset

class PassengerActivity : AppCompatActivity() {

    private data class PaxRefs(
        val lastKana: EditText,
        val lastKanaError: TextView,
        val firstKana: EditText,
        val firstKanaError: TextView,
        val birth: EditText,
        val birthError: TextView,
        val genderGroup: RadioGroup,
        val genderError: TextView,
        val phone: EditText,
        val phoneError: TextView,
        val email: EditText,
        val emailError: TextView
    )

    private val paxRefsList = mutableListOf<PaxRefs>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_passenger)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        val container = findViewById<LinearLayout>(R.id.pax_container)
        val inflater = LayoutInflater.from(this)
        val adults = if (BookingStore.adults > 0) BookingStore.adults else 1

        for (i in 0 until adults) {
            val itemView = inflater.inflate(R.layout.item_passenger, container, false)
            val suffix = "_${i + 1}"

            itemView.findViewById<TextView>(R.id.pax_item_title).text = "搭乗者情報 ${i + 1}"

            val lastKana = itemView.findViewById<EditText>(R.id.pax_last_kana)
            lastKana.contentDescription = "pax_last_kana$suffix"
            val lastKanaError = itemView.findViewById<TextView>(R.id.pax_last_kana_error)
            lastKanaError.contentDescription = "pax_last_kana_error$suffix"

            val firstKana = itemView.findViewById<EditText>(R.id.pax_first_kana)
            firstKana.contentDescription = "pax_first_kana$suffix"
            val firstKanaError = itemView.findViewById<TextView>(R.id.pax_first_kana_error)
            firstKanaError.contentDescription = "pax_first_kana_error$suffix"

            val birth = itemView.findViewById<EditText>(R.id.pax_birth)
            birth.contentDescription = "pax_birth$suffix"
            val birthPick = itemView.findViewById<Button>(R.id.pax_birth_pick)
            birthPick.contentDescription = "pax_birth_pick$suffix"
            val birthError = itemView.findViewById<TextView>(R.id.pax_birth_error)
            birthError.contentDescription = "pax_birth_error$suffix"

            val genderGroup = itemView.findViewById<RadioGroup>(R.id.pax_gender)
            genderGroup.contentDescription = "pax_gender$suffix"
            itemView.findViewById<RadioButton>(R.id.pax_gender_male).contentDescription =
                "pax_gender_male$suffix"
            itemView.findViewById<RadioButton>(R.id.pax_gender_female).contentDescription =
                "pax_gender_female$suffix"
            itemView.findViewById<RadioButton>(R.id.pax_gender_other).contentDescription =
                "pax_gender_other$suffix"
            val genderError = itemView.findViewById<TextView>(R.id.pax_gender_error)
            genderError.contentDescription = "pax_gender_error$suffix"

            val phoneLabel = itemView.findViewById<TextView>(R.id.pax_phone_label)
            val phone = itemView.findViewById<EditText>(R.id.pax_phone)
            val phoneError = itemView.findViewById<TextView>(R.id.pax_phone_error)
            val emailLabel = itemView.findViewById<TextView>(R.id.pax_email_label)
            val email = itemView.findViewById<EditText>(R.id.pax_email)
            val emailError = itemView.findViewById<TextView>(R.id.pax_email_error)

            if (i == 0) {
                phone.contentDescription = "pax_phone_1"
                phoneError.contentDescription = "pax_phone_error_1"
                email.contentDescription = "pax_email_1"
                emailError.contentDescription = "pax_email_error_1"
                phoneLabel.visibility = View.VISIBLE
                phone.visibility = View.VISIBLE
                phoneError.visibility = View.GONE
                emailLabel.visibility = View.VISIBLE
                email.visibility = View.VISIBLE
                emailError.visibility = View.GONE
            } else {
                phoneLabel.visibility = View.GONE
                phone.visibility = View.GONE
                phoneError.visibility = View.GONE
                emailLabel.visibility = View.GONE
                email.visibility = View.GONE
                emailError.visibility = View.GONE
            }

            birthPick.setOnClickListener {
                val picker = MaterialDatePicker.Builder.datePicker()
                    .setTitleText("生年月日を選択")
                    .build()
                picker.addOnPositiveButtonClickListener { millis ->
                    val date = Instant.ofEpochMilli(millis).atZone(ZoneOffset.UTC).toLocalDate()
                    birth.setText(date.toString())
                }
                picker.show(supportFragmentManager, "pax_birth_picker$suffix")
            }

            container.addView(itemView)

            paxRefsList.add(
                PaxRefs(
                    lastKana, lastKanaError, firstKana, firstKanaError,
                    birth, birthError, genderGroup, genderError,
                    phone, phoneError, email, emailError
                )
            )
        }

        val terms = findViewById<CheckBox>(R.id.pax_terms)
        val termsError = findViewById<TextView>(R.id.pax_terms_error)
        val back = findViewById<Button>(R.id.pax_back)
        val next = findViewById<Button>(R.id.pax_next)

        back.setOnClickListener { finish() }

        next.setOnClickListener {
            var firstErrorView: View? = null
            val passengers = mutableListOf<Passenger>()

            for ((i, refs) in paxRefsList.withIndex()) {
                var itemOk = true

                val lastKana = refs.lastKana.text.toString().trim()
                if (lastKana.isEmpty() || lastKana.length > 20 || !Validators.isKatakana(lastKana)) {
                    refs.lastKanaError.text = "全角カタカナで1〜20文字で入力してください"
                    refs.lastKanaError.visibility = View.VISIBLE
                    if (firstErrorView == null) firstErrorView = refs.lastKana
                    itemOk = false
                } else {
                    refs.lastKanaError.text = ""
                    refs.lastKanaError.visibility = View.GONE
                }

                val firstKana = refs.firstKana.text.toString().trim()
                if (firstKana.isEmpty() || firstKana.length > 20 || !Validators.isKatakana(firstKana)) {
                    refs.firstKanaError.text = "全角カタカナで1〜20文字で入力してください"
                    refs.firstKanaError.visibility = View.VISIBLE
                    if (firstErrorView == null) firstErrorView = refs.firstKana
                    itemOk = false
                } else {
                    refs.firstKanaError.text = ""
                    refs.firstKanaError.visibility = View.GONE
                }

                val birthStr = refs.birth.text.toString().trim()
                val birthDate = if (birthStr.isEmpty()) null else Validators.parseDate(birthStr)
                val age = if (birthDate != null) Validators.ageOn(birthStr) else null
                if (birthStr.isEmpty() || birthDate == null || age == null || age < 12 || age > 120) {
                    refs.birthError.text = "12歳以上120歳以下の日付を入力してください"
                    refs.birthError.visibility = View.VISIBLE
                    if (firstErrorView == null) firstErrorView = refs.birth
                    itemOk = false
                } else {
                    refs.birthError.text = ""
                    refs.birthError.visibility = View.GONE
                }

                val genderId = refs.genderGroup.checkedRadioButtonId
                if (genderId == -1) {
                    refs.genderError.text = "性別を選択してください"
                    refs.genderError.visibility = View.VISIBLE
                    if (firstErrorView == null) firstErrorView = refs.genderGroup
                    itemOk = false
                } else {
                    refs.genderError.text = ""
                    refs.genderError.visibility = View.GONE
                }

                if (i == 0) {
                    val phoneVal = refs.phone.text.toString().trim()
                    if (!Validators.isDigits(phoneVal, 10, 11)) {
                        refs.phoneError.text = "10〜11桁の数字で入力してください"
                        refs.phoneError.visibility = View.VISIBLE
                        if (firstErrorView == null) firstErrorView = refs.phone
                        itemOk = false
                    } else {
                        refs.phoneError.text = ""
                        refs.phoneError.visibility = View.GONE
                    }

                    val emailVal = refs.email.text.toString().trim()
                    if (!Validators.isEmail(emailVal)) {
                        refs.emailError.text = "メールアドレスの形式で入力してください"
                        refs.emailError.visibility = View.VISIBLE
                        if (firstErrorView == null) firstErrorView = refs.email
                        itemOk = false
                    } else {
                        refs.emailError.text = ""
                        refs.emailError.visibility = View.GONE
                    }
                }

                if (itemOk) {
                    val genderValue = when (genderId) {
                        R.id.pax_gender_male -> "male"
                        R.id.pax_gender_female -> "female"
                        R.id.pax_gender_other -> "other"
                        else -> ""
                    }
                    passengers.add(Passenger(lastKana, firstKana, birthStr, genderValue))
                }
            }

            if (!terms.isChecked) {
                termsError.text = "利用規約への同意が必要です"
                termsError.visibility = View.VISIBLE
                if (firstErrorView == null) firstErrorView = terms
            } else {
                termsError.text = ""
                termsError.visibility = View.GONE
            }

            if (firstErrorView == null && passengers.size == paxRefsList.size) {
                BookingStore.passengers.clear()
                BookingStore.passengers.addAll(passengers)
                startActivity(Intent(this, PaymentActivity::class.java))
            } else {
                firstErrorView?.requestFocus()
            }
        }
    }
}

package com.example.skybook.ui

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import com.example.skybook.R
import com.example.skybook.data.BookingStore
import com.example.skybook.util.Validators

class LoginActivity : AppCompatActivity() {

    private lateinit var emailInput: TextInputEditText
    private lateinit var passwordInput: TextInputEditText
    private lateinit var emailError: TextView
    private lateinit var passwordError: TextView
    private lateinit var formError: TextView
    private lateinit var loginNotice: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        emailInput = findViewById(R.id.login_email)
        passwordInput = findViewById(R.id.login_password)
        emailError = findViewById(R.id.login_email_error)
        passwordError = findViewById(R.id.login_password_error)
        formError = findViewById(R.id.login_form_error)
        loginNotice = findViewById(R.id.mypage_login_notice)

        loginNotice.visibility = if (intent.getBooleanExtra("login_required", false)) {
            View.VISIBLE
        } else {
            View.GONE
        }

        val submitButton: MaterialButton = findViewById(R.id.login_submit)
        submitButton.setOnClickListener { attemptLogin() }

        val guestButton: MaterialButton = findViewById(R.id.login_guest)
        guestButton.setOnClickListener {
            BookingStore.loggedIn = false
            goToSearch()
        }
    }

    private fun attemptLogin() {
        emailError.text = ""
        emailError.visibility = View.GONE
        passwordError.text = ""
        passwordError.visibility = View.GONE
        formError.text = ""
        formError.visibility = View.GONE

        val email = emailInput.text?.toString().orEmpty()
        val password = passwordInput.text?.toString().orEmpty()

        var firstErrorView: View? = null
        var hasFieldError = false

        if (email.isEmpty() || email.length > 64 || !Validators.isEmail(email)) {
            emailError.text = "メールアドレスの形式で入力してください"
            emailError.visibility = View.VISIBLE
            hasFieldError = true
            firstErrorView = emailInput
        }

        if (password.isEmpty() || password.length < 8 || password.length > 32) {
            passwordError.text = "パスワードは8〜32文字で入力してください"
            passwordError.visibility = View.VISIBLE
            hasFieldError = true
            if (firstErrorView == null) firstErrorView = passwordInput
        }

        if (hasFieldError) {
            firstErrorView?.requestFocus()
            return
        }

        if (Validators.isEmail(email) && password == "password123") {
            BookingStore.loggedIn = true
            BookingStore.email = email
            goToSearch()
        } else {
            formError.text = "メールアドレスまたはパスワードが違います"
            formError.visibility = View.VISIBLE
            emailInput.requestFocus()
        }
    }

    private fun goToSearch() {
        startActivity(Intent(this, SearchActivity::class.java))
        finish()
    }
}

package com.example.skybook.ui

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.button.MaterialButton
import com.google.android.material.switchmaterial.SwitchMaterial
import com.example.skybook.R
import com.example.skybook.util.Nav

class SettingsActivity : AppCompatActivity() {

    private val handler = Handler(Looper.getMainLooper())
    private var tapCount = 0
    private val idleMillis = 2000L
    private val requiredTaps = 7
    private val resetRunnable = Runnable { tapCount = 0 }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val languageSpinner: Spinner = findViewById(R.id.settings_language)
        val adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            arrayOf("日本語", "English")
        )
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        languageSpinner.adapter = adapter

        val notifySwitch: SwitchMaterial = findViewById(R.id.settings_notify)
        notifySwitch.isChecked = true

        val versionText: TextView = findViewById(R.id.settings_version)
        val debugLink: MaterialButton = findViewById(R.id.settings_debug_link)
        versionText.text = "バージョン 1.0.0"
        debugLink.visibility = View.GONE

        versionText.setOnClickListener {
            handler.removeCallbacks(resetRunnable)
            tapCount += 1
            if (tapCount >= requiredTaps) {
                debugLink.visibility = View.VISIBLE
                tapCount = 0
            } else {
                handler.postDelayed(resetRunnable, idleMillis)
            }
        }

        debugLink.setOnClickListener {
            startActivity(Intent(this, DebugActivity::class.java))
        }

        val bottomNav: BottomNavigationView = findViewById(R.id.bottom_nav)
        Nav.setupBottomNav(this, bottomNav, R.id.nav_settings)
    }

    override fun onDestroy() {
        handler.removeCallbacks(resetRunnable)
        super.onDestroy()
    }
}

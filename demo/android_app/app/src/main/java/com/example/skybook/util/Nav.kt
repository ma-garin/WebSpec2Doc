package com.example.skybook.util

import android.app.Activity
import android.content.Intent
import com.example.skybook.R
import com.example.skybook.ui.MyPageActivity
import com.example.skybook.ui.SearchActivity
import com.example.skybook.ui.SettingsActivity
import com.google.android.material.bottomnavigation.BottomNavigationView

object Nav {

    fun setupBottomNav(activity: Activity, view: BottomNavigationView, current: Int) {
        view.selectedItemId = current

        view.setOnItemSelectedListener { item ->
            if (item.itemId == current) {
                return@setOnItemSelectedListener false
            }

            val targetClass = when (item.itemId) {
                R.id.nav_search -> SearchActivity::class.java
                R.id.nav_mypage -> MyPageActivity::class.java
                R.id.nav_settings -> SettingsActivity::class.java
                else -> null
            }

            if (targetClass != null) {
                val intent = Intent(activity, targetClass)
                intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
                activity.startActivity(intent)
                true
            } else {
                false
            }
        }
    }
}

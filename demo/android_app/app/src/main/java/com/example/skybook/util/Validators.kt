package com.example.skybook.util

import java.time.LocalDate
import java.time.Period
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

object Validators {

    private val EMAIL_REGEX = Regex("^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$")
    private val KATAKANA_REGEX = Regex("^[\\u30A1-\\u30FA\\u30FC]+$")
    private val DATE_FORMATTER: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd")

    fun isEmail(s: String): Boolean {
        return EMAIL_REGEX.matches(s)
    }

    fun isKatakana(s: String): Boolean {
        if (s.isEmpty()) {
            return false
        }
        return KATAKANA_REGEX.matches(s)
    }

    fun isDigits(s: String, min: Int, max: Int): Boolean {
        if (s.length < min || s.length > max) {
            return false
        }
        return s.all { it.isDigit() }
    }

    fun ageOn(birthIso: String, today: LocalDate = LocalDate.now()): Int? {
        val birth = parseDate(birthIso) ?: return null
        if (birth.isAfter(today)) {
            return null
        }
        return Period.between(birth, today).years
    }

    fun parseDate(s: String): LocalDate? {
        return try {
            LocalDate.parse(s, DATE_FORMATTER)
        } catch (e: DateTimeParseException) {
            null
        }
    }
}

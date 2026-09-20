package com.example.skybook.data

data class Passenger(
    val lastKana: String,
    val firstKana: String,
    val birth: String,
    val gender: String
)

data class Booking(
    val pnr: String,
    val flightId: String,
    val date: String,
    val seat: String,
    val total: Int,
    var status: String
)

object BookingStore {

    var loggedIn: Boolean = false
    var email: String = ""

    var from: String = ""
    var to: String = ""
    var depart: String = ""
    var returnDate: String = ""
    var adults: Int = 1
    var seatClass: String = "economy"

    var flight: Flight? = null
    var seat: String = ""

    val passengers: MutableList<Passenger> = mutableListOf()

    var couponApplied: Boolean = false

    val bookings: MutableList<Booking> = mutableListOf()

    fun classFactor(): Double {
        return when (seatClass) {
            "premium" -> 1.4
            "business" -> 2.2
            else -> 1.0
        }
    }

    fun subtotal(): Int {
        val price = flight?.price ?: 0
        return (price * adults * classFactor()).toInt()
    }

    fun total(): Int {
        val sub = subtotal()
        return if (couponApplied) {
            (sub * 0.9).toInt()
        } else {
            sub
        }
    }

    fun newPnr(): String {
        val chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return (1..6).map { chars.random() }.joinToString("")
    }

    fun reset() {
        loggedIn = false
        email = ""
        from = ""
        to = ""
        depart = ""
        returnDate = ""
        adults = 1
        seatClass = "economy"
        flight = null
        seat = ""
        passengers.clear()
        couponApplied = false
        bookings.clear()
    }
}

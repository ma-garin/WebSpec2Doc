package com.example.skybook.data

data class Airport(
    val code: String,
    val name: String
)

data class Flight(
    val id: String,
    val from: String,
    val to: String,
    val dep: String,
    val arr: String,
    val price: Int,
    val direct: Boolean,
    val via: String?
)

object FlightData {

    val AIRPORTS: List<Airport> = listOf(
        Airport("HND", "羽田"),
        Airport("NRT", "成田"),
        Airport("ITM", "伊丹"),
        Airport("KIX", "関西"),
        Airport("CTS", "新千歳"),
        Airport("FUK", "福岡"),
        Airport("OKA", "那覇")
    )

    val FLIGHTS: List<Flight> = listOf(
        Flight("SB101", "HND", "CTS", "07:30", "09:05", 18900, true, null),
        Flight("SB205", "HND", "CTS", "10:15", "11:50", 15400, true, null),
        Flight("SB330", "HND", "CTS", "18:40", "20:15", 22100, true, null),
        Flight("SB412", "HND", "FUK", "08:00", "09:55", 21000, true, null),
        Flight("SB520", "ITM", "OKA", "09:20", "11:35", 24800, true, null),
        Flight("SB777", "NRT", "OKA", "13:00", "17:10", 19300, false, "FUK")
    )

    fun search(from: String, to: String): List<Flight> {
        return FLIGHTS.filter { it.from == from && it.to == to }
    }

    fun airportName(code: String): String {
        return AIRPORTS.firstOrNull { it.code == code }?.name ?: code
    }
}

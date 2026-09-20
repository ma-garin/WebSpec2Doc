package com.example.skybook.ui

import android.app.Dialog
import android.os.Bundle
import android.view.LayoutInflater
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.DialogFragment
import com.example.skybook.R
import com.google.android.material.button.MaterialButton

class SeatDialogFragment : DialogFragment() {

    companion object {
        private val OCCUPIED = setOf("1A", "1B", "2C", "3D", "4F", "5E")

        fun newInstance(): SeatDialogFragment = SeatDialogFragment()
    }

    var onSeatConfirmed: ((String) -> Unit)? = null

    private var selectedSeat: String? = null

    override fun onCreateDialog(savedInstanceState: Bundle?): Dialog {
        val view = LayoutInflater.from(requireContext()).inflate(R.layout.dialog_seat, null, false)

        val seatIdToView = linkedMapOf(
            "1A" to R.id.seat_1A, "1B" to R.id.seat_1B, "1C" to R.id.seat_1C,
            "1D" to R.id.seat_1D, "1E" to R.id.seat_1E, "1F" to R.id.seat_1F,
            "2A" to R.id.seat_2A, "2B" to R.id.seat_2B, "2C" to R.id.seat_2C,
            "2D" to R.id.seat_2D, "2E" to R.id.seat_2E, "2F" to R.id.seat_2F,
            "3A" to R.id.seat_3A, "3B" to R.id.seat_3B, "3C" to R.id.seat_3C,
            "3D" to R.id.seat_3D, "3E" to R.id.seat_3E, "3F" to R.id.seat_3F,
            "4A" to R.id.seat_4A, "4B" to R.id.seat_4B, "4C" to R.id.seat_4C,
            "4D" to R.id.seat_4D, "4E" to R.id.seat_4E, "4F" to R.id.seat_4F,
            "5A" to R.id.seat_5A, "5B" to R.id.seat_5B, "5C" to R.id.seat_5C,
            "5D" to R.id.seat_5D, "5E" to R.id.seat_5E, "5F" to R.id.seat_5F,
            "6A" to R.id.seat_6A, "6B" to R.id.seat_6B, "6C" to R.id.seat_6C,
            "6D" to R.id.seat_6D, "6E" to R.id.seat_6E, "6F" to R.id.seat_6F
        )

        val seatButtons = linkedMapOf<String, MaterialButton>()
        for ((seatId, viewId) in seatIdToView) {
            seatButtons[seatId] = view.findViewById(viewId)
        }

        for ((seatId, button) in seatButtons) {
            if (OCCUPIED.contains(seatId)) {
                button.isEnabled = false
            } else {
                button.setOnClickListener {
                    selectedSeat = seatId
                    for ((otherId, otherButton) in seatButtons) {
                        otherButton.alpha = if (otherId == seatId) 1.0f else 0.6f
                    }
                }
            }
        }

        val confirmButton: MaterialButton = view.findViewById(R.id.seat_confirm)
        val cancelButton: MaterialButton = view.findViewById(R.id.seat_cancel)

        confirmButton.setOnClickListener {
            val seat = selectedSeat
            if (seat != null) {
                onSeatConfirmed?.invoke(seat)
                dismiss()
            }
        }
        cancelButton.setOnClickListener {
            dismiss()
        }

        return AlertDialog.Builder(requireContext())
            .setView(view)
            .create()
    }
}

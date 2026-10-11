const form = document.getElementById("bookingForm");
const message = document.getElementById("message");
const summary = document.getElementById("summary");
const roomSelect = document.getElementById("room_type");
const checkIn = document.getElementById("check_in");
const checkOut = document.getElementById("check_out");
const guests = document.getElementById("guests");

const today = new Date().toISOString().split("T")[0];
checkIn.min = today;
checkOut.min = today;

const type = new URLSearchParams(window.location.search).get("type");
if (type) {
  roomSelect.value = type;
}

function showMessage(text, ok) {
  message.textContent = text;
  message.className = ok ? "msg ok" : "msg bad";
}

function nightsBetween() {
  if (!checkIn.value || !checkOut.value) {
    return 0;
  }
  return Math.round((new Date(checkOut.value) - new Date(checkIn.value)) / 86400000);
}

async function updateSummary() {
  const option = roomSelect.selectedOptions[0];
  guests.max = option.dataset.max;
  const nights = nightsBetween();

  if (nights <= 0) {
    summary.textContent = "Choose your check-in and check-out dates to see the total.";
    return;
  }

  const total = nights * Number(option.dataset.price);
  let text = `${nights} night${nights > 1 ? "s" : ""}, total ETB ${total.toLocaleString()}.`;

  try {
    const response = await fetch(`/api/availability?check_in=${checkIn.value}&check_out=${checkOut.value}`);
    const data = await response.json();
    if (response.ok) {
      const left = data[roomSelect.value];
      text += left > 0 ? ` ${left} left for these dates.` : " Sold out for these dates.";
    } else {
      text = data.error;
    }
  } catch (error) {
    text += " Availability could not be checked.";
  }

  summary.textContent = text;
}

checkIn.addEventListener("change", () => {
  checkOut.min = checkIn.value || today;
  updateSummary();
});
checkOut.addEventListener("change", updateSummary);
roomSelect.addEventListener("change", updateSummary);

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    const response = await fetch("/api/bookings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        guest: document.getElementById("guest").value,
        room_type: roomSelect.value,
        check_in: checkIn.value,
        check_out: checkOut.value,
        guests: guests.value,
      }),
    });
    const data = await response.json();

    if (!response.ok) {
      showMessage(data.error || "Booking failed", false);
      return;
    }

    form.reset();
    updateSummary();
    showMessage(`Booking received. Your booking ID is #${data.booking.id}. Use it with your name on the Track booking page.`, true);
  } catch (error) {
    showMessage("Could not reach the server. Try again.", false);
  }
});

updateSummary();

const form = document.getElementById("lookupForm");
const result = document.getElementById("result");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.getElementById("bookingId").value;
  const guest = document.getElementById("guestName").value.trim();

  try {
    const response = await fetch(`/api/bookings/${id}?guest=${encodeURIComponent(guest)}`);
    const data = await response.json();

    if (!response.ok) {
      result.textContent = data.error;
      result.className = "msg bad status-form";
      return;
    }

    result.textContent = `Booking #${data.id} for ${data.guest}\n${data.room}, ${data.guests} guest(s)\n${data.check_in} to ${data.check_out} (${data.nights} nights)\nTotal: ETB ${Number(data.total_price).toLocaleString()}\nStatus: ${data.status}`;
    result.className = "msg ok status-form";
  } catch (error) {
    result.textContent = "Could not reach the server. Try again.";
    result.className = "msg bad status-form";
  }
});

const container = document.getElementById("bookingsContainer");
const token = localStorage.getItem("adminToken");

if (!token) {
  window.location.href = "/admin/login";
}

const headers = {
  Authorization: `Bearer ${token}`,
  "Content-Type": "application/json",
};

function logout() {
  localStorage.removeItem("adminToken");
  window.location.href = "/admin/login";
}

async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401 || response.status === 403) {
    logout();
    return null;
  }
  return response;
}

function countStatus(bookings, status) {
  return bookings.filter((booking) => booking.status === status).length;
}

async function loadBookings() {
  const response = await api("/api/admin/bookings");
  if (!response) {
    return;
  }
  const bookings = await response.json();

  document.getElementById("totalBookings").textContent = bookings.length;
  document.getElementById("pendingBookings").textContent = countStatus(bookings, "pending");
  document.getElementById("confirmedBookings").textContent = countStatus(bookings, "confirmed");
  document.getElementById("cancelledBookings").textContent = countStatus(bookings, "cancelled");

  container.innerHTML = bookings.length ? "" : "No bookings yet.";

  bookings.forEach((booking) => {
    const card = document.createElement("div");
    card.className = "order-card";
    card.innerHTML = `
      <h3>Booking #${booking.id}</h3>
      <p><strong>Guest:</strong> ${escapeHtml(booking.guest)}</p>
      <p><strong>Room:</strong> ${escapeHtml(booking.room)}, ${booking.guests} guest(s)</p>
      <p><strong>Stay:</strong> ${booking.check_in} to ${booking.check_out} (${booking.nights} nights)</p>
      <p><strong>Total:</strong> ETB ${Number(booking.total_price).toFixed(2)}</p>
      <label>
        Status:
        <select class="booking-status-select" data-id="${booking.id}">
          ${["pending", "confirmed", "cancelled"]
            .map((status) => `<option value="${status}" ${booking.status === status ? "selected" : ""}>${status}</option>`)
            .join("")}
        </select>
      </label>
      <button type="button" class="delete-order-button delete-booking-button" data-id="${booking.id}">Delete Booking</button>
    `;
    container.appendChild(card);
  });
}

container.addEventListener("change", async (event) => {
  const select = event.target.closest(".booking-status-select");
  if (!select) {
    return;
  }
  const response = await api(`/api/admin/bookings/${select.dataset.id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status: select.value }),
  });
  if (response && !response.ok) {
    alert((await response.json()).error);
  }
  loadBookings();
});

container.addEventListener("click", async (event) => {
  const button = event.target.closest(".delete-booking-button");
  if (!button || !confirm(`Delete booking #${button.dataset.id}?`)) {
    return;
  }
  await api(`/api/admin/bookings/${button.dataset.id}`, { method: "DELETE" });
  loadBookings();
});

document.getElementById("logoutButton").addEventListener("click", logout);

loadBookings();

const errorMessage = document.getElementById("errorMessage");
const orderResult = document.getElementById("orderResult");

const form = document.getElementById("orderLookupForm");
const orderIdInput = document.getElementById("orderId");
const customerNameInput = document.getElementById("customerName");

function orderCardHtml(data) {
  return `
    <div class="order-card">

        <h2>Order #${data.id}</h2>

        <p>
            <strong>Customer:</strong>
            ${escapeHtml(data.customer)}
        </p>

        <p>
            <strong>Items:</strong>
            ${escapeHtml(data.items)}
        </p>

        <p>
            <strong>Quantity:</strong>
            ${data.quantity}
        </p>

        <p>
            <strong>Total:</strong>
            ETB ${Number(data.total_price).toFixed(2)}
        </p>

        <div class="order-status">
            <strong>Status:</strong>

            <span class="status-badge status-${escapeHtml(data.status)}">
                ${escapeHtml(data.status)}
            </span>
        </div>

    </div>
  `;
}

async function lookupOrder(orderId, customerName) {
  errorMessage.textContent = "";
  orderResult.innerHTML = "";

  try {
    const response = await fetch(
      `/api/orders/${orderId}?customer=${encodeURIComponent(customerName)}`
    );

    const data = await response.json();

    if (!response.ok) {
      errorMessage.textContent = data.error || "Order not found.";
      return;
    }

    orderResult.innerHTML = orderCardHtml(data);
  } catch (error) {
    console.error("Order lookup error:", error);

    errorMessage.textContent = "Something went wrong. Please try again.";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();

  const orderId = orderIdInput.value;
  const customerName = customerNameInput.value.trim();

  if (!orderId || !customerName) {
    errorMessage.textContent = "Both order ID and name are required.";
    return;
  }

  lookupOrder(orderId, customerName);
});

const params = new URLSearchParams(window.location.search);
const prefillId = params.get("id");
const prefillCustomer = params.get("customer");
if (prefillId) {
  orderIdInput.value = prefillId;
}

if (prefillCustomer) {
  customerNameInput.value = prefillCustomer;
}

if (prefillId && prefillCustomer) {
  lookupOrder(prefillId, prefillCustomer);
}

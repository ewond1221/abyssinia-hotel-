const ordersContainer = document.getElementById("ordersContainer");
const logoutButton = document.getElementById("logoutButton");
const token = localStorage.getItem("adminToken");

if (!token) {
  window.location.href = "/admin/login";
}

async function loadOrders() {
  try {
    const response = await fetch("/api/admin/orders", {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (response.status === 401 || response.status === 403) {
      localStorage.removeItem("adminToken");
      window.location.href = "/admin/login";
      return;
    }

    if (!response.ok) {
      throw new Error("Failed to load orders");
    }

    const orders = await response.json();
    const totalOrders = orders.length;

    const pendingOrders = orders.filter(
      (order) => order.status === "pending",
    ).length;

    const completedOrders = orders.filter(
      (order) => order.status === "completed",
    ).length;

    const cancelledOrders = orders.filter(
      (order) => order.status === "cancelled",
    ).length;

    document.getElementById("totalOrders").textContent = totalOrders;
    document.getElementById("pendingOrders").textContent = pendingOrders;
    document.getElementById("completedOrders").textContent = completedOrders;
    document.getElementById("cancelledOrders").textContent = cancelledOrders;

    ordersContainer.innerHTML = "";

    if (orders.length === 0) {
      ordersContainer.textContent = "No orders found.";
      return;
    }

    orders.forEach((order) => {
      const orderElement = document.createElement("div");
      orderElement.classList.add("order-card");
      orderElement.innerHTML = `
        <h3>Order #${order.id}</h3>
        <p>
          <strong>Customer:</strong>
          ${escapeHtml(order.customer)}
        </p>
        <p>
          <strong>Items:</strong>
          ${escapeHtml(order.items)}
        </p>
        <p>
          <strong>Quantity:</strong>
          ${order.quantity}
        </p>
        <p>
          <strong>Total:</strong>
          ETB ${Number(order.total_price).toFixed(2)}
        </p>
        <p>
          <strong>Status:</strong>
          ${escapeHtml(order.status)}
        </p>
        <label>
          Status:
          <select class="order-status-select" data-order-id="${order.id}">
            <option value="pending" ${order.status === "pending" ? "selected" : ""}>Pending</option>
            <option value="preparing" ${order.status === "preparing" ? "selected" : ""}>Preparing</option>
            <option value="completed" ${order.status === "completed" ? "selected" : ""}>Completed</option>
          </select>
        </label>
        <button type="button" class="delete-order-button" data-order-id="${order.id}">
          Delete Order
        </button>
      `;
      ordersContainer.appendChild(orderElement);
    });

    document.querySelectorAll(".order-status-select").forEach((select) => {
      select.addEventListener("change", async () => {
        const orderId = select.dataset.orderId;
        const newStatus = select.value;

        try {
          const response = await fetch(`/api/admin/orders/${orderId}/status`, {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              status: newStatus,
            }),
          });

          if (response.status === 401 || response.status === 403) {
            localStorage.removeItem("adminToken");
            window.location.href = "/admin/login";
            return;
          }

          const data = await response.json();

          if (!response.ok) {
            alert(data.error || "Failed to update order status");
            return;
          }

          alert(`Order #${orderId} is now ${newStatus}.`);
          await loadOrders();
        } catch (error) {
          console.error("Status update error:", error);
          alert("Something went wrong while updating the status.");
        }
      });
    });

    const deleteButtons = document.querySelectorAll(".delete-order-button");
    deleteButtons.forEach((button) => {
      button.addEventListener("click", async () => {
        const orderId = button.dataset.orderId;
        const confirmed = window.confirm(`Are you sure you want to delete order #${orderId}?`);

        if (!confirmed) {
          return;
        }

        try {
          const response = await fetch(`/api/admin/orders/${orderId}`, {
            method: "DELETE",
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });

          if (response.status === 401 || response.status === 403) {
            localStorage.removeItem("adminToken");
            window.location.href = "/admin/login";
            return;
          }

          const data = await response.json();

          if (!response.ok) {
            alert(data.error || "Failed to delete order");
            return;
          }

          alert("Order deleted successfully.");
          await loadOrders();
        } catch (error) {
          console.error("Delete order error:", error);
          alert("Something went wrong while deleting the order.");
        }
      });
    });
  } catch (error) {
    console.error("Load orders error:", error);
    ordersContainer.textContent = "Unable to load orders.";
  }
}

if (logoutButton) {
  logoutButton.addEventListener("click", () => {
    localStorage.removeItem("adminToken");
    window.location.href = "/admin/login";
  });
}

loadOrders();

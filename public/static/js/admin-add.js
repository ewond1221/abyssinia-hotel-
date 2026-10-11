const errorMessage = document.getElementById("errorMessage");
const menuItemsGrid = document.getElementById("menuItemsGrid");
const customItemsContainer = document.getElementById("customItemsContainer");
const addCustomItemButton = document.getElementById("addCustomItemButton");
const submitOrderButton = document.getElementById("submitOrderButton");

const token = localStorage.getItem("adminToken");

if (!token) {
  window.location.href = "/admin/login";
}

let menu = [];
let customRowCount = 0;

function getCustomRows() {
  return Array.from(document.querySelectorAll(".custom-item-row"));
}

function readCustomRow(row) {
  return {
    name: row.querySelector(".custom-item-name").value.trim(),
    price: parseFloat(row.querySelector(".custom-item-price").value),
    qty: parseInt(row.querySelector(".custom-item-qty").value, 10),
  };
}

function updateOrderTotals() {
  let totalQty = 0;
  let totalPrice = 0;

  document.querySelectorAll(".menu-item-qty").forEach((input) => {
    const qty = parseInt(input.value) || 0;
    const price = parseFloat(input.dataset.price);
    totalQty += qty;
    totalPrice += qty * price;
  });

  getCustomRows().forEach((row) => {
    const { price, qty } = readCustomRow(row);
    if (qty > 0 && !isNaN(price) && price >= 0) {
      totalQty += qty;
      totalPrice += price * qty;
    }
  });

  document.getElementById("orderTotalQty").textContent = totalQty;
  document.getElementById("orderTotalPrice").textContent = totalPrice.toFixed(2);
}

function addCustomItemRow() {
  customRowCount += 1;

  const row = document.createElement("div");
  row.className = "custom-item-row";
  row.dataset.rowId = `custom-${customRowCount}`;

  row.innerHTML = `
    <input type="text" class="custom-item-name" placeholder="Item name" />
    <input type="number" class="custom-item-price" placeholder="Unit price (ETB)" min="0" step="0.01" />
    <input type="number" class="custom-item-qty" placeholder="Qty" min="1" value="1" />
    <button type="button" class="btn-remove-row">Remove</button>
  `;

  customItemsContainer.appendChild(row);

  row.querySelectorAll("input").forEach((input) => {
    input.addEventListener("input", updateOrderTotals);
  });

  row.querySelector(".btn-remove-row").addEventListener("click", () => {
    row.remove();
    updateOrderTotals();
  });
}

if (addCustomItemButton) {
  addCustomItemButton.addEventListener("click", addCustomItemRow);
}

async function loadMenu() {
  try {
    const response = await fetch("/api/menu");
    menu = await response.json();

    menuItemsGrid.innerHTML = menu.map((item) => `
      <div class="menu-item">
        <div class="menu-item-name">${escapeHtml(item.name)}</div>
        <div class="menu-item-price">ETB ${Number(item.price).toFixed(2)}</div>
        <input
          type="number"
          class="menu-item-qty"
          min="0"
          value="0"
          data-id="${escapeHtml(item.id)}"
          data-price="${Number(item.price)}"
        />
      </div>
    `).join("");

    document.querySelectorAll(".menu-item-qty").forEach((input) => {
      input.addEventListener("input", updateOrderTotals);
    });
  } catch (error) {
    console.error("Load menu error:", error);
    menuItemsGrid.textContent = "Unable to load menu.";
  }
}

if (submitOrderButton) {
  submitOrderButton.addEventListener("click", async () => {
    const customer = document.getElementById("customer").value.trim();

    errorMessage.textContent = "";

    if (!customer) {
      errorMessage.textContent = "Customer name is required";
      return;
    }

    const items = [];

    document.querySelectorAll(".menu-item-qty").forEach((input) => {
      const qty = parseInt(input.value) || 0;
      if (qty > 0) {
        items.push({ item_id: input.dataset.id, qty });
      }
    });

    let customError = null;

    getCustomRows().forEach((row) => {
      const { name, price, qty } = readCustomRow(row);

      if (!name && !qty) {
        return;
      }

      if (!name) {
        customError = "Every custom item needs a name";
        return;
      }

      if (isNaN(price) || price < 0) {
        customError = `Enter a valid price for "${name}"`;
        return;
      }

      if (!qty || qty < 1) {
        customError = `Enter a valid quantity for "${name}"`;
        return;
      }

      items.push({ custom: true, name, price, qty });
    });

    if (customError) {
      errorMessage.textContent = customError;
      return;
    }

    if (items.length === 0) {
      errorMessage.textContent = "Select at least one menu item or add a custom item";
      return;
    }

    try {
      const response = await fetch("/api/admin/orders", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          customer,
          items,
        }),
      });

      if (response.status === 401 || response.status === 403) {
        localStorage.removeItem("adminToken");
        window.location.href = "/admin/login";
        return;
      }

      const data = await response.json();

      if (!response.ok) {
        errorMessage.textContent = data.error || "Failed to create order";
        return;
      }

      alert(`Order #${data.order.id} created successfully!`);
      window.location.href = "/admin/dashboard";
    } catch (error) {
      console.error("Add order error:", error);
      errorMessage.textContent = "Something went wrong while creating the order.";
    }
  });
}

if (token) {
  loadMenu();
}
